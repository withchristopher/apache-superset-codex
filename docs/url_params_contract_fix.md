<!--
Licensed to the Apache Software Foundation (ASF) under one
or more contributor license agreements.  See the NOTICE file
distributed with this work for additional information
regarding copyright ownership.  The ASF licenses this file
to you under the Apache License, Version 2.0 (the
"License"); you may not use this file except in compliance
with the License.  You may obtain a copy of the License at

  http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing,
software distributed under the License is distributed on an
"AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
KIND, either express or implied.  See the License for the
specific language governing permissions and limitations
under the License.
-->

# `url_params` Query Contract Investigation

## Summary

The broken contract parameter is `url_params`. Dashboard and Explore URLs can
carry arbitrary query parameters that are copied into chart `form_data` and then
made available to backend template helpers such as `url_param()`. The chart-data
API contract requires those parameters to be present on each query object in the
V1 chart-data request body, not only on the top-level `form_data` payload.

The regression path was in the shared query-context builder. The default query
object includes `url_params`, but chart plugins and native-filter/customization
query builders can replace the generated query object with a partial object. In
that case the shared builder returned queries without `url_params`, causing API
consumers downstream to lose URL-derived template parameters.

## Root Cause

`buildQueryContext()` delegates final query construction to chart-specific query
builders. Some builders return objects that do not spread the base query object.
When a builder omits the base query fields, `url_params` is dropped from the
serialized V1 payload even though it remains on `form_data`.

This violates the established contract used by the backend Jinja context, which
reads URL parameters from `form_data.queries[0].url_params` for chart data
requests.

## Affected Areas

- Shared query utilities: `buildQueryObject()` creates the base `url_params`
  field, and `buildQueryContext()` serializes final query objects.
- API consumers: `getChartDataRequest()` sends the V1 chart-data payload built by
  `buildV1ChartDataPayload()`.
- State-management and hydration: dashboard hydration merges URL query strings
  into each chart's `form_data.url_params`.
- Serializers/request schema: chart-data request schemas allow `url_params` in
  query form data.
- Downstream components: chart plugins, native-filter query builders, chart
  customizations, and backend Jinja helpers consume the final query payload.

## Fix

The fix is applied in `buildQueryContext()` after custom query builders and query
mutators run. Each final query receives a backward-compatible `url_params`
fallback:

1. Preserve a query builder's explicit `query.url_params` value.
2. Otherwise copy `formData.url_params` onto the query.
3. Otherwise emit `{}` to preserve the existing empty-object contract.

This centralizes the compatibility guarantee in the shared serializer instead of
patching individual chart plugins.

## Regression Coverage

New unit tests cover:

- custom query builders that omit `url_params`;
- custom query builders that intentionally override query-level `url_params`;
- the empty-object fallback when neither the query nor `form_data` provides
  `url_params`.

## Validation Notes

The standard `npm run test` workflow could not execute in this container because
frontend dependencies were not installed and `npm ci` was blocked by a registry
`403 Forbidden` response for `@babel/core`. The attempted commands and their
outcomes are recorded in the final task summary.
