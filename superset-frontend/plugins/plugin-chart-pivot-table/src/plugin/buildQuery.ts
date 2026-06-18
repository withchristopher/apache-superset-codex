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
import buildGroupbyCombinations from './utilities';

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

  // Emit one query per rollup level so the database computes each
  // subtotal/grand total at its own granularity, rather than re-aggregating
  // already-aggregated cells client-side (which is wrong for non-additive
  // metrics). See SIP.md. The combination order is fixed by
  // buildGroupbyCombinations and relied upon by transformProps to zip each
  // result back to the level that produced it.
  const groupbyCombinations: Groupby[] = buildGroupbyCombinations(formData);
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
