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
SQL building blocks for the pivot-table non-additive totals optimization
(SIP.md, phase 3b). When a datasource engine reports
``supports_grouping_sets``, the N per-rollup-level queries can be collapsed into
a single ``GROUPING SETS`` query: the database computes every level in one scan,
and each returned row is attributed to its level via ``GROUPING()`` markers.

These are the engine-agnostic SQL primitives. Wiring them into the query context
(emitting one query and splitting the result back into per-level results) is the
remaining integration; see SIP.md.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, tuple_
from sqlalchemy.sql.elements import ColumnElement


def grouping_sets_clause(
    groups: Sequence[Sequence[ColumnElement]],
) -> ColumnElement:
    """
    Build a ``GROUP BY GROUPING SETS (...)`` clause from rollup column groups.

    Each group is the set of columns grouped at one rollup level; the empty
    group ``()`` is the grand total. For example, groups ``[[a, b], [a], []]``
    produce ``GROUPING SETS ((a, b), (a), ())``.

    :param groups: one column list per rollup level
    :return: a clause element suitable for ``select(...).group_by(...)``
    """
    return func.grouping_sets(*[tuple_(*group) for group in groups])


def grouping_id_column(column: ColumnElement, label: str) -> ColumnElement:
    """
    Build a ``GROUPING(col) AS label`` marker column.

    In a ``GROUPING SETS`` result, ``GROUPING(col)`` is ``0`` when ``col`` is
    part of the row's grouping level and ``1`` when it has been rolled up
    (aggregated away). Selecting one marker per groupby column lets the caller
    attribute each returned row to its rollup level when splitting the single
    result back into per-level results.

    :param column: the groupby column to probe
    :param label: the output label for the marker
    :return: the labelled ``GROUPING(col)`` column
    """
    return func.grouping(column).label(label)
