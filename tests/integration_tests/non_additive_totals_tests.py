# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

"""
End-to-end acceptance tests for non-additive metric totals (Table chart).

Companion to tests/unit_tests/charts/test_non_additive_totals.py and the
root SIP.md. These exercise the real ``api/v1/chart/data`` query path against
the example ``birth_names`` table.

Findings these tests pin down:

* **Bucket A (SQL-aggregate grand total)** is already correct for the Table
  chart, because the "Show summary" row is produced by a *separate query with
  no GROUP BY* (``columns=[]``). The database evaluates the metric expression
  over all rows, so a ratio / distinct count is right even though summing the
  per-group cells would be wrong. These are asserted as regression guards.
* **Bucket B (post-processing % columns)** is broken: the totals query is built
  with ``post_processing=[]`` (see plugin-chart-table ``buildQuery.ts``), so a
  contribution / percent column never appears in the summary row (#37627,
  #34350). Marked ``xfail(strict=True)`` until the POC carries post-processing
  into the totals computation.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from superset.charts.schemas import ChartDataQueryContextSchema
from superset.common.query_context import QueryContext
from superset.utils.core import QueryStatus
from tests.integration_tests.base_tests import SupersetTestCase
from tests.integration_tests.fixtures.birth_names_dashboard import (
    load_birth_names_dashboard_with_slices,  # noqa: F401
    load_birth_names_data,  # noqa: F401
)
from tests.integration_tests.fixtures.query_context import get_query_context

# A non-additive ratio metric: fraction of births in California.
# Inlined CASE over physical columns (num, state); * 1.0 forces float division
# so SQLite doesn't truncate the ratio to integer 0.
RATIO_METRIC = {
    "expressionType": "SQL",
    "sqlExpression": "SUM(CASE WHEN state = 'CA' THEN num ELSE 0 END) * 1.0 / SUM(num)",
    "label": "ca_share",
}

DISTINCT_METRIC = {
    "expressionType": "SIMPLE",
    "column": {"column_name": "name"},
    "aggregate": "COUNT_DISTINCT",
    "label": "distinct_names",
}


def _result_df(payload: dict[str, Any]):
    # Use get_query_result (not get_payload) to avoid the flask-caching/Redis
    # layer, so these tests run against just the metadata + results DB.
    query_context: QueryContext = ChartDataQueryContextSchema().load(payload)
    query_object = query_context.queries[0]
    result = query_context.get_query_result(query_object)
    assert result.status == QueryStatus.SUCCESS, result.errors
    return result.df


def _base_payload(metric: dict[str, Any], columns: list[str]):
    payload = get_query_context("birth_names")
    query = payload["queries"][0]
    query["metrics"] = [metric]
    query["columns"] = columns
    query["groupby"] = columns
    query["orderby"] = []
    query["post_processing"] = []
    query["is_timeseries"] = False
    query["row_limit"] = None
    return payload


@pytest.mark.usefixtures("load_birth_names_dashboard_with_slices")
class TestNonAdditiveTotalsTable(SupersetTestCase):
    def test_ratio_grand_total_is_db_computed_not_summed(self):
        """
        Bucket A regression guard: the grand total of a ratio metric is the
        ratio of the summed parts (DB-computed at no-GROUP-BY), and is NOT the
        sum of the per-group ratios.
        """
        self.login("admin")

        # Per-group ratios (grouped by state).
        per_group = _result_df(_base_payload(RATIO_METRIC, ["state"]))
        summed_ratios = per_group["ca_share"].sum()

        # Grand total: no GROUP BY -> the summary-row query the table chart runs.
        grand_total_df = _result_df(_base_payload(RATIO_METRIC, []))
        grand_total = grand_total_df["ca_share"].iloc[0]

        # The grand total is a genuine ratio in [0, 1] ...
        assert 0.0 <= grand_total <= 1.0
        # ... and summing the per-group ratios is the wrong answer the SIP fixes
        # for pivot subtotals; the table grand-total path already avoids it.
        assert not np.isclose(grand_total, summed_ratios), (
            f"grand total {grand_total} should differ from summed per-group "
            f"ratios {summed_ratios}"
        )

    def test_distinct_count_grand_total_is_db_computed(self):
        """
        Bucket A regression guard: COUNT_DISTINCT grand total is computed over
        all rows, so it is <= the sum of per-group distinct counts (no
        double-counting of names that appear in multiple groups).
        """
        self.login("admin")

        per_group = _result_df(_base_payload(DISTINCT_METRIC, ["state"]))
        summed = per_group["distinct_names"].sum()

        grand_total_df = _result_df(_base_payload(DISTINCT_METRIC, []))
        grand_total = grand_total_df["distinct_names"].iloc[0]

        assert grand_total <= summed
        # names recur across states, so the true distinct total is strictly less
        assert grand_total < summed

    @pytest.mark.xfail(
        strict=True,
        reason="POC not implemented: the table 'Show summary' totals query is "
        "built with post_processing=[], so percent/contribution columns are "
        "absent from the summary row (#37627, #34350).",
    )
    def test_percent_column_present_in_summary_row(self):
        """
        Bucket B: a contribution/percent column must appear in the totals
        (summary) row. Today the totals query strips post_processing, so the
        column is missing -> the summary shows zeros/blank.
        """
        self.login("admin")

        payload = _base_payload({"label": "sum__num"}, ["gender"])
        payload["queries"][0]["post_processing"] = [
            {
                "operation": "contribution",
                "options": {
                    "columns": ["sum__num"],
                    "orientation": "column",
                    "rename_columns": ["sum__num_pct"],
                },
            }
        ]
        # The summary row mirrors how the frontend builds the totals query:
        # same metrics, no columns, and (the bug) post_processing dropped.
        totals_payload = _base_payload({"label": "sum__num"}, [])
        totals_df = _result_df(totals_payload)

        assert "sum__num_pct" in totals_df.columns, (
            "percent column must be recomputed for the summary row"
        )
