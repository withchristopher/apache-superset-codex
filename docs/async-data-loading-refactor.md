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

# Async Data Loading Refactor Results

## Scope

This change set focuses on the chart data-loading path used by Explore and dashboard chart execution/rendering flows. It also updates the global async query event waiter used when `GLOBAL_ASYNC_QUERIES` returns a pending job response.

## Findings

- Chart requests already used `AbortController` for the initial HTTP request, but the async event wait that follows an HTTP `202` response did not accept the same cancellation signal. A superseded request could therefore keep an async listener registered until the server-side job emitted an event.
- Chart action thunks guarded stale success and failure dispatches before dispatching terminal actions, but reducers did not independently validate that a terminal action belonged to the active request. Adding reducer-level validation keeps state safe even if terminal actions are dispatched out of order by existing or future callers.
- The existing stopped-action reducer already guarded against stale abort handling. Success and failure now follow the same synchronization pattern.

## Implementation Results

- `waitForAsyncData` accepts an optional `AbortSignal`, rejects with an abort-shaped error when cancelled, unregisters the async listener, and ignores later events for the cancelled request.
- Chart data response handling forwards the active request signal into the async query waiter, so stale requests are cancelled consistently across both the initial HTTP request and the async result wait.
- `CHART_UPDATE_SUCCEEDED` and `CHART_UPDATE_FAILED` actions carry the originating request controller when dispatched from chart data loading.
- The chart reducer ignores stale success and failure actions whose controller does not match the chart state's active controller.
- Tests were added for async waiter cancellation and reducer-level stale terminal-action protection.

## Compatibility Notes

- Existing callers can continue to call `waitForAsyncData(asyncResponse)` without options.
- Existing callers can continue to dispatch `chartUpdateSucceeded` and `chartUpdateFailed` without a controller; reducer validation only applies when a controller is present.
- The refactor preserves the existing Redux flow: `CHART_UPDATE_STARTED`, query trigger/form-data updates, terminal success/failure/stopped actions, and warning/log dispatch behavior are unchanged apart from stale-action suppression.

## Validation

Attempted targeted Jest validation with:

```bash
cd superset-frontend && npm run test -- src/components/Chart/chartReducers.test.ts src/middleware/asyncEvent.test.ts --runInBand
```

The command could not execute in this container because `cross-env` is not installed in `superset-frontend/node_modules`. No test failures were observed because the Jest process did not start.
