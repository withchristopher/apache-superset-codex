<!--
Licensed to the Apache Software Foundation (ASF) under one or more
contributor license agreements.  See the NOTICE file distributed with
this work for additional information regarding copyright ownership.
The ASF licenses this file to you under the Apache License, Version 2.0
(the "License"); you may not use this file except in compliance with
the License.  You may obtain a copy of the License at

  http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
-->

# Report Modal Reducer Roadmap

The report modal reducer stores reports, chart subscriptions, and alert/report
list entries by the resource key used by the UI. This roadmap records the next
feature-oriented reducer improvements so the reports UI can evolve without
reintroducing divergent state-shape logic.

## State ownership

- Keep dashboard reports keyed by dashboard id under `dashboards`.
- Keep chart reports and subscriptions keyed by chart id under `charts`.
- Keep alert/report list entries keyed by report id under `alerts_reports`.
- Route all create, subscribe, edit, and delete paths through shared key
  selection helpers so each action applies the same state-shape contract.

## Feature roadmap

1. **Typed report API payloads**
   - Replace partial response casts with API response types that reflect the
     fields returned by `/api/v1/report/` create, subscribe, update, and delete
     workflows.
   - Add compile-time coverage for `creation_method` so unsupported values do
     not create orphan reducer buckets.
2. **Normalized loading and error state**
   - Add reducer-owned status fields for fetch, create, update, subscribe, and
     delete flows.
   - Surface reducer status to the modal so submit controls and inline errors do
     not depend solely on toast side effects.
3. **Selector-first reads**
   - Introduce selectors for dashboard, chart, and alert/report lookups.
   - Migrate component reads to selectors before changing the internal state
     representation.
4. **Subscription parity**
   - Add explicit reducer tests for subscription upserts on dashboard and chart
     reports.
   - Align subscription success messaging with report creation messaging after
     the reducer state contract is fully covered.
5. **Migration safety**
   - Preserve the existing state keys until all consumers read through selectors.
   - Update this roadmap when a phase is completed so follow-up work keeps the
     reducer contract discoverable.

## Validation checklist

- Run the reducer unit test whenever the report keying rules change.
- Run frontend pre-commit hooks after staging reducer or documentation changes.
- Confirm report creation, subscription, edit, and delete actions use the same
  helper path for state updates.
