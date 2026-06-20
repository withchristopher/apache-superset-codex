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
import {
  AdhocColumn,
  buildQueryContext,
  ensureIsArray,
  isPhysicalColumn,
  QueryFormColumn,
  QueryFormOrderBy,
  TimeGranularity,
} from '@superset-ui/core';
import { Groupby, PivotTableQueryFormData } from '../types';
import buildGroupbyCombinations, { allMetricsAdditive } from './utilities';

// Build the query `columns` for a single rollup level (one prefix of row dims
// crossed with one prefix of column dims), applying temporal BASE_AXIS handling.
function getQueryColumns(
  groupby: Groupby,
  formData: PivotTableQueryFormData,
  timeGrainSqla: TimeGranularity | undefined,
): QueryFormColumn[] {
  // TODO: add deduping of AdhocColumns
  return Array.from(
    new Set([
      ...ensureIsArray<QueryFormColumn>(groupby.rows),
      ...ensureIsArray<QueryFormColumn>(groupby.columns),
    ]),
  ).map(col => {
    if (
      isPhysicalColumn(col) &&
      timeGrainSqla &&
      (formData?.temporal_columns_lookup?.[col] ||
        formData.granularity_sqla === col)
    ) {
      return {
        timeGrain: timeGrainSqla,
        columnType: 'BASE_AXIS',
        sqlExpression: col,
        label: col,
        expressionType: 'SQL',
      } as AdhocColumn;
    }
    return col;
  });
}

export default function buildQuery(formData: PivotTableQueryFormData) {
  const { extra_form_data } = formData;
  const time_grain_sqla =
    extra_form_data?.time_grain_sqla || formData.time_grain_sqla;

  // Additive fast-path: when every metric is additive (SUM/COUNT/MIN/MAX), the
  // subtotals/grand totals can be derived by reducing the leaf rows on the
  // client, so a single full-detail query suffices and transformProps
  // synthesizes the rollup levels. Non-additive metrics need the database to
  // compute each rollup level, so we emit one query per level (the combination
  // order is fixed by buildGroupbyCombinations and relied upon by
  // transformProps to map each result back to its level). See SIP.md.
  const additive = allMetricsAdditive(ensureIsArray(formData.metrics));
  const groupbyCombinations: Groupby[] = additive
    ? [
        {
          rows: ensureIsArray<QueryFormColumn>(formData.groupbyRows),
          columns: ensureIsArray<QueryFormColumn>(formData.groupbyColumns),
        },
      ]
    : buildGroupbyCombinations(formData);
  const queriesColumns: QueryFormColumn[][] = groupbyCombinations.map(groupby =>
    getQueryColumns(groupby, formData, time_grain_sqla),
  );

  return buildQueryContext(formData, baseQueryObject => {
    const { series_limit_metric, metrics, order_desc } = baseQueryObject;
    let orderBy: QueryFormOrderBy[] | undefined;
    if (series_limit_metric) {
      orderBy = [[series_limit_metric, !order_desc]];
    } else if (Array.isArray(metrics) && metrics[0]) {
      orderBy = [[metrics[0], !order_desc]];
    }
    return queriesColumns.map(columns => ({
      ...baseQueryObject,
      orderby: orderBy,
      columns,
    }));
  });
}
