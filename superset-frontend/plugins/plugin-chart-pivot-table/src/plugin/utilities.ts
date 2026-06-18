/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */

import { QueryFormColumn } from '@superset-ui/core';
import {
  Groupby,
  MetricsLayoutEnum,
  PivotTableQueryFormData,
} from '../types';

/**
 * Enumerate the groupby combinations needed to compute correct subtotals and
 * grand totals for non-additive metrics. Each combination is one rollup level:
 * a prefix of the row dimensions crossed with a prefix of the column
 * dimensions. The empty `{rows: [], columns: []}` combination is the grand
 * total. Every level is then queried independently so the database computes the
 * metric at that granularity (see SIP.md), rather than re-aggregating cells.
 */
export default function buildGroupbyCombinations(
  formData: PivotTableQueryFormData,
): Groupby[] {
  let columns: QueryFormColumn[] = formData.groupbyColumns ?? [];
  let rows: QueryFormColumn[] = formData.groupbyRows ?? [];

  [rows, columns] = formData.transposePivot ? [columns, rows] : [rows, columns];

  const rowsCombinations = [[] as QueryFormColumn[], ...rows.map((_, i) => rows.slice(0, i + 1))];
  const colsCombinations = [
    [] as QueryFormColumn[],
    ...columns.map((_, i) => columns.slice(0, i + 1)),
  ];

  let groupbyCombinations: Groupby[] = rowsCombinations.flatMap(row =>
    colsCombinations.map(col => ({ rows: row, columns: col })),
  );

  if (formData.combineMetric) {
    if (formData.metricsLayout === MetricsLayoutEnum.ROWS) {
      groupbyCombinations = groupbyCombinations.filter(
        combination => combination.rows.length === rows.length,
      );
    } else {
      groupbyCombinations = groupbyCombinations.filter(
        combination => combination.columns.length === columns.length,
      );
    }
  }

  return groupbyCombinations;
}
