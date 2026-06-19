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

from sqlalchemy import column, select
from sqlalchemy.dialects import postgresql

from superset.common.grouping_sets import (
    grouping_id_column,
    grouping_sets_clause,
)


def _compile(stmt) -> str:
    return str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).replace("\n", " ")


def test_grouping_sets_clause_emits_rollup_levels() -> None:
    a, b = column("a"), column("b")
    # rollup hierarchy: leaf (a, b), row subtotal (a), grand total ()
    stmt = select(a, b).group_by(grouping_sets_clause([[a, b], [a], []]))
    sql = _compile(stmt)
    assert "GROUPING SETS((a, b), (a), ())" in sql


def test_grouping_sets_single_level() -> None:
    a = column("a")
    stmt = select(a).group_by(grouping_sets_clause([[a]]))
    assert "GROUPING SETS((a))" in _compile(stmt)


def test_grouping_id_marker_column() -> None:
    a = column("a")
    stmt = select(a, grouping_id_column(a, "a__grouping"))
    sql = _compile(stmt).lower()
    assert "grouping(a) as a__grouping" in sql
