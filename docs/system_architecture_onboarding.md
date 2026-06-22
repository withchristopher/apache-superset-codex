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

# Superset System Architecture Onboarding Guide

This document summarizes Apache Superset's runtime architecture for senior engineers. It focuses on the path from application state through API calls and query execution to end-user rendering, with architectural risks and refactoring opportunities called out explicitly.

## Executive summary

Superset is a Flask/Python backend and React/TypeScript frontend organized around three large interactive surfaces:

1. **Dashboards**: layout, native filters, chart instances, cross-filtering, and edit state.
2. **Explore**: chart authoring controls, datasource metadata, chart preview, save flows, and URL/form-data synchronization.
3. **SQL Lab**: editor tabs, query execution, query history, and persisted client state.

The frontend uses a hybrid state model:

- A single Redux Toolkit store (`setupStore`) aggregates legacy reducers, typed hooks, thunk middleware, listener middleware, logging middleware, and RTK Query's API slice.
- Chart data fetching still primarily uses thunk action creators and `SupersetClient` directly.
- Newer resource fetching uses RTK Query-style endpoint injection over a common `supersetClientQuery` base query.
- Chart rendering is plugin-driven: chart plugins register metadata, build-query functions, React components, control panels, and transform functions in `@superset-ui/core` registries.

The backend exposes REST APIs through Flask-AppBuilder views. The main visualization data path is `POST /api/v1/chart/data`, which validates a client-built query context, checks access through `ChartDataCommand.validate()`, executes a `QueryContext`, applies cache/async behavior, and serializes JSON/CSV/XLSX responses.

## State management and store architecture

### Global Redux store

The canonical frontend store is created in `superset-frontend/src/views/store.ts`. `setupStore()` composes these major state domains:

- `sqlLab`
- `messageToasts`
- bootstrap-derived `common` and `user`
- `charts`
- unified `datasources`
- dashboard slices (`dashboardInfo`, `dashboardFilters`, `nativeFilters`, `dashboardState`, `dashboardLayout`, `sliceEntities`)
- Explore slices (`saveModal`, `explore`)
- `dataMask`
- `reports`
- `database`
- RTK Query's `queryApi` reducer

Middleware differs by environment flag: when Redux default middleware is enabled, Superset uses Redux Toolkit defaults plus listener middleware, logger middleware, and RTK Query middleware; otherwise it explicitly installs listener middleware, thunk, logger middleware, and RTK Query middleware.

A noteworthy coupling point is `CombinedDatasourceReducers`, which routes dashboard datasource actions to the dashboard datasource reducer and all other datasource actions to the Explore datasource reducer. The source code notes that this is a temporary merger of Dashboard and Explore reducer semantics and that a larger action/reducer unification is needed.

### Store hydration

Dashboard state is bootstrapped through API resource hooks and then hydrated into Redux:

1. `DashboardPage` fetches dashboard metadata, chart definitions, and datasets.
2. Once dashboard and charts are ready, it resolves permalink/native-filter/Rison URL state.
3. It dispatches `hydrateDashboard()` with dashboard metadata, charts, data masks, active tabs, and chart states.
4. `hydrateDashboard()` builds chart query state, slice entity maps, layout state, native filter state, cross-filter configuration, permissions, and dashboard runtime state in one large thunk action.
5. Reducers consume the `HYDRATE_DASHBOARD` action to replace their slices.

The dashboard hydration action is intentionally broad: it normalizes backend dashboard payloads, mutates chart metadata into layout state, derives permissions from the logged-in user, constructs native filter state, and initializes chart query entries. This makes first render relatively centralized but also makes dashboard boot behavior a tightly coupled integration point.

### Chart state

Chart instances live in `state.charts`, keyed by chart id or temporary key. Each chart holds query status, render status, abort controller, latest query form data, query responses, annotation query state, and rendering errors. The chart reducer responds to lifecycle actions such as:

- `CHART_UPDATE_STARTED`
- `CHART_UPDATE_SUCCEEDED`
- `CHART_UPDATE_STOPPED`
- `CHART_UPDATE_FAILED`
- `CHART_RENDERING_SUCCEEDED`
- `CHART_RENDERING_FAILED`
- `TRIGGER_QUERY`
- `RENDER_TRIGGERED`
- `HYDRATE_DASHBOARD` / `HYDRATE_EXPLORE`

This reducer stores non-serializable `AbortController` instances for cancellation. The store configuration explicitly ignores `queryController` paths in serializability checks when Redux default middleware is used.

### RTK Query resource layer

Superset has a shared RTK Query base API in `src/hooks/apiResources/queryApi.ts`. `supersetClientQuery` wraps `SupersetClient.request`, appends Rison-encoded URL params as `?q=...`, forwards the RTK abort signal, and normalizes errors into a common `ClientErrorObject` shape. Feature-specific resource files inject endpoints into this shared API slice.

Dashboard resource hooks currently use a custom `useApiV1Resource`/`useTransformedResource` pattern for dashboard metadata, charts, and datasets. Other areas such as SQL Lab resources use `api.injectEndpoints()` directly.

## Async request lifecycle

### Resource-fetch lifecycle

For dashboard boot:

1. React mounts `DashboardPage`.
2. Hooks call backend resource endpoints:
   - `/api/v1/dashboard/<id>?q=...`
   - `/api/v1/dashboard/<id>/charts`
   - `/api/v1/dashboard/<id>/datasets`
3. Resource state returns `result`, `error`, and status values to the component.
4. Effects dispatch dashboard hydration and datasource status updates.
5. Dataset errors produce a toast, while dashboard/chart fetch errors are thrown to the error boundary.

### Chart query lifecycle

The chart query path is legacy thunk-driven:

1. `Chart` watches `triggerQuery`. If true, it calls `runQuery()`.
2. `runQuery()` optionally defers when dashboard virtualization says the chart is out of view, then dispatches `postChartFormData(formData, force, timeout, chartId, dashboardId, ownState)`.
3. The chart action builds a query payload using Explore utilities and chart plugin build-query functions.
4. It dispatches `CHART_UPDATE_STARTED` with an `AbortController`.
5. It posts to the chart data API through `SupersetClient`.
6. On success, it dispatches `CHART_UPDATE_SUCCEEDED` with query responses.
7. On failure, it normalizes backend or network errors and dispatches `CHART_UPDATE_FAILED`.
8. `ChartRenderer` receives `queriesResponse` from Redux and renders `SuperChart`.
9. `SuperChart` invokes render callbacks; the container dispatches rendering success/failure actions and logs timing/error metadata.

### Backend chart-data lifecycle

The `POST /api/v1/chart/data` endpoint performs the server-side half of the lifecycle:

1. It accepts JSON or CSV-export form data.
2. It constructs a `QueryContext` from the payload.
3. It creates `ChartDataCommand(query_context)` and calls `validate()`.
4. Validation delegates to `query_context.raise_for_access()` for datasource/chart access enforcement.
5. It decides whether to use global async queries based on feature flag, result format/type, and cache timeout.
6. In async mode, it attempts a cached result first; otherwise it validates the async token, starts a background job, and returns HTTP 202 job metadata.
7. In synchronous mode, it executes `command.run()` and sends a formatted response.
8. `ChartDataCommand.run()` delegates caching and payload construction to `QueryContext.get_payload()`.
9. `QueryContext` delegates data formatting, cache keys, dataframe payloads, query execution, and access checks to `QueryContextProcessor`.
10. `_send_chart_response()` serializes JSON results, table-like exports, ZIPs, or streaming CSV as appropriate.

## Rendering and execution pipeline

### Dashboard rendering

Dashboard rendering is layout-driven:

1. Hydration creates `dashboardLayout.present`, `sliceEntities.slices`, and `charts` state.
2. The connected Dashboard container maps Redux slices to `Dashboard` component props.
3. `DashboardComponent` recursively resolves each layout node's component type from `componentLookup` and passes derived layout, edit, filter, and dimension props.
4. Chart holder/grid components eventually render the shared `Chart` component.
5. `Chart` runs or defers query execution, then chooses loading/error/no-results/render paths based on chart state.
6. `ChartRenderer` builds the runtime chart props and renders `SuperChart`.
7. `SuperChart`/`SuperChartCore` loads the plugin component and transform function from registries, preprocesses props, applies plugin transforms, and renders the visualization React component.

### Explore rendering

Explore combines connected Redux state with local React hooks:

- `ExploreViewContainer` connects controls, datasource, form data, save modal state, and chart state.
- Control changes update Explore reducer state and form-data-derived chart query state.
- URL state is debounced and persisted through Explore utility functions.
- The preview chart uses the same chart state/actions and `SuperChart` rendering path as dashboards.

### Query execution and serialization

The backend `QueryContext` is the execution abstraction. It contains datasource, query objects, result type/format, cache settings, and form data. It delegates to `QueryContextProcessor` for dataframe retrieval, data conversion, cache payloads, and security checks. This means frontend chart plugins generate a client-side query context shape, while backend command/query-context classes enforce and execute it.

## Plugin and extension architecture

### Static chart plugins

Chart plugins extend `ChartPlugin` from `@superset-ui/core`. A plugin provides:

- metadata
- a chart React component or lazy loader
- a transform-props function or lazy loader
- an optional build-query function or lazy loader
- control panel configuration

On `register()`, the plugin stores these artifacts in registries:

- chart metadata registry
- chart component registry
- chart control panel registry
- chart transform-props registry
- chart build-query registry

`MainPreset` bundles the built-in visualization plugins and registers them during application setup. Feature flags control optional plugin inclusion, such as experimental chart plugins or AG Grid table.

### Dynamic plugins

Dynamic plugins are runtime-loaded JavaScript bundles controlled by the `DYNAMIC_PLUGINS` feature flag. `DynamicPluginProvider`:

1. Initializes plugin context from chart metadata registry state.
2. Defines shared modules (`react`, `react-dom`, `lodash`, `@superset-ui/core`, `@superset-ui/chart-controls`) for dynamic bundles.
3. Calls `/dynamic-plugins/api/read` to fetch plugin bundle metadata.
4. Imports each bundle using `webpackIgnore` so the browser loads the configured URL.
5. Tracks mounting/error state in React context.
6. Listens for registry changes and updates exposed plugin metadata.

Dynamic plugins share the same registries as static plugins once loaded. This makes plugin rendering uniform, but it also means registry state is global mutable process state in the browser.

## Service and API communication layers

### Frontend clients

Superset uses three overlapping client layers:

1. **`SupersetClient` direct calls**: used heavily by chart actions, chart client utilities, and legacy flows.
2. **`ChartClient`**: a lightweight abstraction in `@superset-ui/core` for loading form data, datasource metadata, query data, annotations, or all chart data. It switches between the legacy `/superset/explore_json/` endpoint and `/api/v1/chart/data` based on plugin metadata.
3. **RTK Query API slice**: `api` and `supersetClientQuery` provide standardized endpoint injection, cancellation, error shaping, and cache tags.

This overlap reflects an incremental migration rather than a single service layer.

### Backend API structure

Backend APIs are Flask-AppBuilder views and command objects:

- Model REST APIs handle CRUD/list/import/export behavior for resources such as charts and dashboards.
- Specialized APIs handle query data (`ChartDataRestApi`), Explore form data, Explore permalinks, SQL Lab resources, and dynamic plugins.
- Commands encapsulate business logic and validation (`ChartDataCommand`, chart create/update/delete commands, async query job commands, import/export commands).
- DAOs and SQLAlchemy models back metadata persistence.
- Security is enforced at route level with FAB decorators and at object/query level by command/query-context access checks for data-bearing resources.

## Component and module hierarchy

### Frontend high-level hierarchy

```text
superset-frontend/src
├── views/store.ts                     # app store composition
├── dashboard/
│   ├── containers/DashboardPage.tsx    # fetch and hydrate dashboard
│   ├── actions/hydrate.ts             # normalize dashboard runtime state
│   ├── reducers/                      # dashboard state slices
│   ├── components/                    # layout, filter bar, grid, edit UI
│   └── util/                          # filters, layout, permissions, CSS, URLs
├── explore/
│   ├── components/ExploreViewContainer # chart authoring surface
│   ├── reducers/                      # form data, controls, save modal
│   ├── actions/                       # datasource, save, hydrate, controls
│   └── exploreUtils/                  # query payloads, URLs, form-data persistence
├── SqlLab/
│   ├── reducers/                      # editor/query state
│   ├── actions/                       # query and editor actions
│   └── middlewares/                   # persisted SQL Lab state enhancer
├── components/Chart/                  # shared chart lifecycle/render container
├── components/DynamicPlugins/         # runtime plugin loading context
├── hooks/apiResources/                # API hooks and RTK Query endpoints
└── visualizations/presets/            # built-in plugin registration
```

### Superset UI core hierarchy

```text
superset-frontend/packages/superset-ui-core/src/chart
├── clients/ChartClient.ts
├── components/
│   ├── SuperChartCore.tsx
│   ├── StatefulChart.tsx
│   └── ChartDataProvider.tsx
├── models/
│   ├── ChartPlugin.ts
│   ├── ChartProps.ts
│   └── ChartMetadata.ts
├── registries/
│   ├── ChartComponentRegistrySingleton.ts
│   ├── ChartBuildQueryRegistrySingleton.ts
│   ├── ChartControlPanelRegistrySingleton.ts
│   ├── ChartMetadataRegistrySingleton.ts
│   └── ChartTransformPropsRegistrySingleton.ts
└── types/
```

### Backend high-level hierarchy

```text
superset/
├── charts/
│   ├── api.py                         # chart metadata REST API
│   ├── data/api.py                    # chart data endpoint and serialization
│   └── schemas.py                     # chart/query-context schemas
├── commands/
│   └── chart/data/get_data_command.py # chart data validation/execution command
├── common/
│   ├── query_context.py               # query context execution facade
│   ├── query_context_processor.py     # payload, cache, query execution details
│   └── query_object.py                # normalized query object
├── dashboards/                        # dashboard APIs, commands, filters, schemas
├── explore/                           # Explore API, permalink and form-data APIs
├── models/                            # SQLAlchemy metadata models
├── daos/                              # persistence access objects
├── views/                             # legacy FAB views and APIs
└── extensions/                        # security manager, event logger, cache, celery
```

## Dependency relationships between major modules

### Frontend dependencies

- Dashboard depends on shared chart lifecycle modules, data-mask state, native filters, Explore `applyDefaultFormData`, dashboard utilities, and API resource hooks.
- Explore depends on shared chart actions/reducer, datasource actions shared with dashboard, plugin context, Explore utilities, and control-panel packages.
- Chart lifecycle depends on `@superset-ui/core` registries, Explore query-building utilities, data-mask actions, logging, dashboard datasource metadata, and `SupersetClient`.
- Plugin registration depends on feature flags and global registries.
- RTK Query resource hooks depend on `SupersetClient`, but chart thunks do not use RTK Query.

### Backend dependencies

- Chart data APIs depend on schemas, commands, async job commands, security manager, cache utilities, and response serialization helpers.
- `ChartDataCommand` depends on `QueryContext` and command exception types.
- `QueryContext` depends on datasource abstractions, query objects, result format/type enums, and `QueryContextProcessor`.
- Dashboard/chart metadata APIs depend on model APIs, DAOs, command classes, filters, and SQLAlchemy models.

## End-to-end data flow: state to rendering

### Dashboard chart data flow

```text
Browser route /superset/dashboard/<id>
  ↓
DashboardPage
  ↓ fetches
/api/v1/dashboard/<id>, /charts, /datasets
  ↓
hydrateDashboard thunk
  ↓ builds
state.dashboardInfo, state.dashboardLayout, state.sliceEntities, state.charts, state.nativeFilters, state.dataMask
  ↓
Connected Dashboard container
  ↓
DashboardComponent recursively renders layout nodes
  ↓
Chart holder renders Chart
  ↓
Chart sees triggerQuery and dispatches postChartFormData
  ↓
Chart action builds query_context payload and posts /api/v1/chart/data
  ↓
ChartDataRestApi.data validates QueryContext via ChartDataCommand
  ↓
QueryContextProcessor executes/caches/formats query result
  ↓
JSON payload returns to chart action
  ↓
CHART_UPDATE_SUCCEEDED updates state.charts[chartId].queriesResponse
  ↓
ChartRenderer renders SuperChart
  ↓
SuperChartCore loads plugin component + transformProps from registries
  ↓
Plugin transform maps ChartProps to visualization props
  ↓
End-user visualization renders
```

### Explore chart data flow

```text
Explore page bootstrap / form-data state
  ↓
ExploreViewContainer controls and datasource panels mutate Explore Redux state
  ↓
Control state converts to form_data
  ↓
Shared Chart component dispatches chart query actions
  ↓
Backend /api/v1/chart/data executes QueryContext
  ↓
state.charts receives query responses
  ↓
Explore chart panel renders via ChartRenderer → SuperChart → plugin component
```

### Dynamic plugin flow

```text
DynamicPluginProvider mount
  ↓
FeatureFlag.DynamicPlugins check
  ↓
GET /dynamic-plugins/api/read
  ↓
defineSharedModules + dynamic import(bundle_url)
  ↓
Plugin bundle calls configure(...).register()
  ↓
Chart registries notify listeners
  ↓
Plugin context refreshes metadata/keys
  ↓
Explore viz picker and SuperChart can resolve the new chart type
```

## Architectural bottlenecks

1. **Large dashboard hydration thunk**
   - `hydrateDashboard()` performs normalization, layout repair, new chart placement, filter initialization, permission derivation, cross-filter configuration, and state creation. This concentrates many failure modes in one thunk and makes incremental dashboard boot difficult.

2. **Hybrid async/data-fetch architecture**
   - RTK Query, custom resource hooks, direct `SupersetClient` calls, `ChartClient`, and thunk-based chart requests coexist. This increases duplicated error handling, cancellation behavior, and caching semantics.

3. **Global mutable plugin registries**
   - Plugin resolution relies on global singleton registries. This is simple and powerful, but can complicate test isolation, runtime unload/reload behavior, tenant isolation, and incremental plugin lifecycle management.

4. **Chart reducer stores transport concerns**
   - Chart state includes `AbortController` objects and both query and render lifecycle state. This couples transport cancellation, backend response status, rendering status, and UI error display.

5. **Client-built query context**
   - The frontend builds query context through plugin `buildQuery` functions, while the backend validates and executes it. This split is flexible but means schema evolution must coordinate plugin packages, Explore controls, dashboard state, and backend schemas.

6. **Dashboard-wide render invalidation risk**
   - Native filters, data masks, layout state, and chart state are highly interconnected. Broad state updates can fan out into many connected components unless selectors and memoization boundaries are carefully maintained.

7. **Async query dependency on cache**
   - Global async queries are disabled when cache timeout disables caching, because async results are retrieved through cache keys. This couples async scalability to cache correctness and capacity.

## Tightly coupled modules

- **Dashboard ↔ Explore**: Dashboard hydration imports Explore `applyDefaultFormData`, chart actions import Explore utilities, and `CombinedDatasourceReducers` merges dashboard and Explore datasource state.
- **Chart lifecycle ↔ Explore utilities**: Chart actions use Explore helpers to build chart data payloads and chart URLs.
- **Frontend plugin buildQuery ↔ backend `ChartDataQueryContextSchema`**: Plugin query builders must produce payloads accepted by backend schemas and processors.
- **Dashboard filters ↔ dataMask ↔ chart form data**: Native filters and cross-filters update `dataMask`, which is merged into chart extra form data before execution.
- **Dynamic plugin provider ↔ chart metadata registry**: Dynamic plugin context observes registry mutations rather than owning plugin lifecycle through an explicit plugin manager.
- **SQL Lab store persistence ↔ global store enhancer**: SQL Lab state persistence is installed as a global store enhancer even though the concern is scoped to one feature surface.

## Scalability concerns

1. **Initial dashboard load fan-out**: Dashboard pages need separate dashboard, charts, and datasets requests before hydration. Large dashboards amplify payload size, normalization work, and Redux state churn.
2. **Chart query concurrency**: Many charts can dispatch concurrent POSTs. Abort/cancel is available, but concurrency control is distributed across chart components and middleware rather than centralized.
3. **Cache pressure from async chart data**: Async chart results depend on cache keys and stored query contexts. High-cardinality dashboards or frequently changing filters can increase cache churn.
4. **Dynamic bundle loading**: Dynamic plugins are fetched all at once by `fetchAll()`. Large plugin inventories or slow external hosts can delay plugin availability and produce inconsistent registry state.
5. **Store size and serialization**: Dashboard layout, slices, chart responses, filter masks, and SQL Lab state can all be large. Persisted SQL Lab state and Redux DevTools can become expensive on large sessions.
6. **Global registries in multi-app pages**: Superset can mount multiple React apps in a page, and global registries/store debugging behavior need careful coordination.

## Refactoring opportunities

### High-impact opportunities

1. **Unify datasource state and actions**
   - Replace `CombinedDatasourceReducers` with a shared datasource domain model used by Dashboard and Explore. This would reduce action branching and type coercion.

2. **Move chart data fetching to a typed service layer**
   - Introduce a chart-data API service with common cancellation, async polling, cache hit handling, error normalization, and telemetry. Then migrate thunk actions and `ChartClient` to that service or to RTK Query endpoints.

3. **Decompose dashboard hydration**
   - Split `hydrateDashboard()` into pure normalization functions with focused tests: layout normalization, chart query initialization, native filter initialization, permission derivation, cross-filter configuration, and URL/permalink state resolution.

4. **Separate chart query state from render state**
   - Model query lifecycle and render lifecycle as separate slices or typed substates. Keep non-serializable cancellation handles outside Redux in middleware or a request manager.

5. **Create an explicit plugin manager abstraction**
   - Wrap global registries in a lifecycle-aware manager that can load, unload, validate, and isolate dynamic plugins. Provide manifest support for lazy-by-chart loading.

6. **Increase backend ownership of query context defaults**
   - Push more query-context defaulting and validation to typed backend endpoints, reducing client/backend schema drift. Keep plugin-specific query construction but centralize compatibility checks.

### Incremental opportunities

- Convert remaining broad `connect()` usage to typed hooks where it improves selector locality.
- Add memoized selectors for high-fanout dashboard state derived from data masks and filters.
- Standardize all resource hooks on the RTK Query base API or clearly document exceptions.
- Add documentation and tests for async chart-query cache behavior.
- Introduce a request concurrency policy for dashboards, such as viewport-aware batching or priority queues.
- Lazy-load dynamic plugins by requested visualization type rather than importing all bundles on provider mount.

## Onboarding guidance for senior engineers

- Start with `src/views/store.ts` to understand state domains and middleware.
- For dashboards, trace `DashboardPage` → `hydrateDashboard()` → connected `Dashboard` → `DashboardComponent` → `Chart`.
- For chart execution, trace `Chart` → chart actions → `/api/v1/chart/data` → `ChartDataCommand` → `QueryContext`.
- For rendering, trace `ChartRenderer` → `SuperChart`/`SuperChartCore` → plugin registries → plugin component.
- For plugins, read `ChartPlugin`, `MainPreset`, and `DynamicPluginProvider` together.
- Treat Dashboard, Explore, and chart lifecycle as a coupled subsystem; changes in one frequently affect the others.
- Prefer adding typed, pure normalization and service-layer seams before attempting large rewrites.
