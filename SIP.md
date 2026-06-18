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

# [SIP] Correct totals and subtotals for non-additive metrics in Table and Pivot Table charts

> **Status:** DRAFT / prototype development zone. This document and the
> accompanying failing tests + POC live together on a draft PR so the proposal
> and the implementation can be rounded out in lockstep. The SIP will be
> numbered by a committer upon acceptance. See
> [SIP-0](https://github.com/apache/superset/issues/5602) for the process.

## Motivation

Superset computes the totals and subtotals shown in Table and Pivot Table
charts by **re-aggregating values that have already been aggregated** (or by
running a total query that ignores the metric's post-processing). This is
correct only for *additive* metrics (`SUM`, `COUNT`, `MIN`, `MAX`). For any
**non-additive** metric, the result is mathematically wrong:

- A ratio metric `SUM(actual) / SUM(target)` shows a total equal to the sum of
  the per-row ratios instead of `SUM(all actual) / SUM(all target)`.
- A `COUNT(DISTINCT user)` shows a total equal to the sum of the per-group
  distinct counts (double-counting anything that appears in more than one
  group) instead of the true distinct count over all rows.
- `AVG`, `MEDIAN`, `PERCENTILE`, `STDDEV` and friends are summed, which is
  meaningless.
- Superset's own "Percentage metrics" / contribution columns are summed in the
  Table chart summary row, producing totals that are not even on a percentage
  scale.

This is one of the longest-standing and most-reported correctness gaps in the
charting layer. It blocks migrations from Tableau / Power BI / Qlik / Excel,
all of which get this right, and it spans **both** the Pivot Table and the
regular Table chart, which today use two completely different (and separately
broken) total mechanisms.

### Consolidated issues this SIP resolves

Tracking / bug reports (consolidated under
[#25747](https://github.com/apache/superset/issues/25747) as the canonical
issue):

- [#25747](https://github.com/apache/superset/issues/25747) — Pivot table
  totals wrong for non-additive (ratio) metrics *(canonical / umbrella)*
- [#32260](https://github.com/apache/superset/issues/32260) — completion
  percentage subtotal/sum wrong in pivot table
- [#38674](https://github.com/apache/superset/issues/38674) — pivot Grand Total
  sums percentages instead of recomputing the ratio metric
- [#36165](https://github.com/apache/superset/issues/36165) — Table summary
  value wrong for `COUNT_DISTINCT`
- [#37627](https://github.com/apache/superset/issues/37627) — Table percentage
  metrics column shows zeros with "Show summary" enabled *(still repros on
  6.0.0)*
- [#34350](https://github.com/apache/superset/issues/34350),
  [#34425](https://github.com/apache/superset/issues/34425),
  [#34426](https://github.com/apache/superset/issues/34426) — Table percentage
  totals wrong / page-scoped

Design discussion: [#29297](https://github.com/apache/superset/discussions/29297)
("Totals in Table Charts" — the original root-cause analysis).

Out of scope (tracked separately, NOT addressed here): the v6
`DISTINCT_AVG` / `DISTINCT_SUM` SQL-generation regression
([#39223](https://github.com/apache/superset/issues/39223)), the per-metric
aggregation *configuration* feature ([SIP-179
/ #34245](https://github.com/apache/superset/issues/34245),
[#38036](https://github.com/apache/superset/discussions/38036)), the
Subtotal→Subvalue labeling change
([#35089](https://github.com/apache/superset/issues/35089)), and the AntV S2
pivot rewrite ([SIP-205 / #38586](https://github.com/apache/superset/issues/38586)).

## The core principle

> **Totals and subtotals must be computed by the database at the grouping
> granularity they are displayed for. They must never be derived on the client
> (or in post-processing) by re-aggregating already-aggregated cells.**

The key insight that keeps this tractable:

> **A metric defined as a SQL aggregate expression is correct at *any* grouping
> level if the same expression is evaluated grouped at that level.**

`SUM(actual)/SUM(target)` grouped by nothing is the correct grand-total ratio;
`COUNT(DISTINCT user)` grouped by `region` is the correct per-region distinct
count. We do **not** need to parse the metric, infer a weighted-sum heuristic,
or build a formula mini-language. We only need to stop summing cells and ask the
database for the total/subtotal rows.

### How the reported cases partition

- **Bucket A — SQL-aggregate metrics** (the large majority: ratios, `AVG`,
  `COUNT_DISTINCT`, percentiles…). Fully solved by computing each
  total/subtotal level in the database. No per-metric special-casing.
- **Bucket B — post-processing metrics** (Superset "Percentage metrics" /
  contribution columns, window/cumulative ops). These are not SQL aggregates;
  their totals need bespoke logic (recompute from the re-aggregated base, or
  display as `100%` / blank, never a raw sum). This is a small, bounded set.

## Proposed Change

A single, shared, **server-side** total/subtotal mechanism used by both the
Table and Pivot Table charts, replacing the client-side pivot aggregation and
the naive `df.sum()` table summary.

### 1. Detect additivity (fast path)

Introduce a first-class notion of metric additivity, reusing/extending the
existing `ADDITIVE_METRIC_TYPES` set (`superset/connectors/sqla/models.py`) and
the aggregate list in `METRIC_MAP_TYPE` (`superset/utils/core.py`):

- Additive aggregates: `SUM`, `COUNT`, `MIN`, `MAX` (and additive composites
  thereof).
- Everything else (`AVG`, `COUNT_DISTINCT`, `MEDIAN`, `PERCENTILE`, `STDDEV`,
  ratio/composite SQL, post-processing metrics) is non-additive.

If **every** metric in a request is additive, the current cheap aggregation
path is already correct — keep it. We only pay for DB rollups when a
non-additive metric is present. This neutralizes most of the performance
objection.

### 2. Compute non-additive totals/subtotals via GROUPING SETS (single query)

When non-additive metrics are present, the query layer emits the required
rollup levels using native SQL `GROUPING SETS` (equivalently `ROLLUP` for the
pivot subtotal hierarchy), with `GROUPING()` markers so each returned row can be
attributed to its level. One scan computes the detail cells, every subtotal
level, and the grand total together.

For a pivot with row dims `R = [r1, r2]` and column dims `C = [c1]`, the grouping
sets are the rollup hierarchy: `{r1,r2,c1}` (cells), `{r1,c1}`, `{c1}`,
`{r1,r2}`, `{r1}`, `{}` (grand total).

### 3. Multi-query fallback where GROUPING SETS is unsupported

Add a `supports_grouping_sets` capability to the DB engine spec (following the
existing `supports_*` / `allows_*` idiom in `superset/db_engine_specs/base.py`,
defaulting to `False`, overridden `True` for Postgres, BigQuery, Snowflake,
Trino/Presto, MySQL 8+, etc.). Where unsupported (e.g. SQLite, older MySQL),
fall back to issuing one query per grouping level behind the same interface, so
chart code is agnostic. This is the approach prototyped in
[PR #34592](https://github.com/apache/superset/pull/34592) for the pivot table;
we generalize it as the fallback rather than the primary path.

### 4. Post-processing metrics (Bucket B)

Percentage/contribution column totals are recomputed from the re-aggregated
base metric (or shown as `100%` / blank), never summed. The Table chart summary
path (`superset/common/query_context_processor.py`) stops doing a blind
`df[col].sum()` over every numeric column.

### 5. Unify Table and Pivot Table

Both charts route through the same total/subtotal computation so that
[#37627](https://github.com/apache/superset/issues/37627) (table) and
[#25747](https://github.com/apache/superset/issues/25747) (pivot) cannot drift
apart again.

### 6. Product decision: what does a total *mean* under a row limit / pagination?

Proposed default: totals reflect the **full filtered dataset at the grouping
level** (matching Tableau / Power BI / Excel and the expectation in
[#34425](https://github.com/apache/superset/issues/34425)), with an honest
label/tooltip clarifying it is computed over all matching rows, not the
displayed page. A "displayed rows only" mode can be offered later as a
non-default; it should not block this SIP. *(Open for discussion in #29297.)*

## New or Changed Public Interfaces

- **DB engine spec:** new `supports_grouping_sets: bool` capability flag
  (default `False`) on `BaseEngineSpec`, overridden per dialect.
- **Query layer** (`superset/models/helpers.py`, `query_object`,
  `query_context_processor`): ability to request and emit grouping-set rollups
  and to attribute returned rows to a grouping level.
- **Metric metadata:** a derived `is_additive` notion exposed at query-build
  time (no required user-facing field; inferred from the aggregate).
- **Pivot Table plugin** (`plugin-chart-pivot-table`): consumes server-computed
  subtotals/totals; the client-side `aggregateFunction` control is removed (its
  semantics are subsumed). React-pivottable no longer computes margins.
- **Table plugin** (`plugin-chart-table`): summary row sourced from the shared
  mechanism; behavior of the `show_totals` totals query changes for
  non-additive / percentage columns.
- No new REST endpoints.

## New dependencies

None anticipated. `GROUPING SETS` / `ROLLUP` are standard SQL emitted through
the existing SQLAlchemy/engine-spec layer; no new npm or PyPI packages.

## Migration Plan and Compatibility

- No database (metadata) migration required.
- Behavioral change: totals/subtotals for non-additive metrics will change from
  (wrong) sums to correct values. This is a correctness fix but is technically a
  visible change in displayed numbers; it will be called out in `UPDATING.md`.
- Additive-only charts are unaffected (fast path).
- Engines without `GROUPING SETS` transparently use the multi-query fallback;
  the only difference is query count/cost, not results.
- Consider a feature flag for the rollout if we want an opt-in period.

## Validation / TDD test matrix

The POC is developed test-first: each known reported case is encoded as a
failing test, and the implementation drives them green. The matrix below is the
acceptance set (to be expanded as cases surface).

| # | Source issue | Chart | Metric / aggregate | Expected total behavior |
|---|---|---|---|---|
| 1 | #25747 / #32260 / #38674 | Pivot | ratio `SUM(a)/SUM(b)` | grand total & subtotals = `SUM(a)/SUM(b)` at that level, not Σ(ratios) |
| 2 | #36165 | Table | `COUNT(DISTINCT x)` | summary = distinct count over all rows, not Σ(per-group counts) |
| 3 | — | Pivot | `AVG(x)` | subtotal/total = `AVG` over the level's rows, not mean-of-means |
| 4 | #37627 / #34350 | Table | Percentage metric (contribution) | summary recomputed on % scale, not Σ(percentages) / zeros |
| 5 | #34425 | Table | percentage under pagination/row limit | total over full filtered dataset, label clarifies scope |
| 6 | regression guard | both | all-additive (`SUM`,`COUNT`) | unchanged from current correct behavior, no extra queries |
| 7 | capability | both | non-additive on engine w/o GROUPING SETS | multi-query fallback yields identical results |

## Prior art / existing attempts

- [PR #34592](https://github.com/apache/superset/pull/34592)
  "fix(pivot-table): Correct totals for non-additive metrics" — implements the
  multi-query (one query per groupby combination) approach for the pivot table.
  Note it is **entirely frontend**: `buildQuery.ts` emits one query object per
  groupby combination (via a new `plugin/utilities.ts::buildGroupbyCombinations`)
  and the existing multi-query machinery runs them as separate queries; there is
  no backend change. This maps precisely onto our **fallback** path. We adopt
  `buildGroupbyCombinations` (and its `utilities.test.ts`) as salvage, use the
  buildQuery/transformProps changes as reference, and add the single-query
  GROUPING SETS primary path plus Table-chart coverage on top.
  No other open PR implements a fix (#38213 is the SIP-179 config feature;
  #30903 is tangential).

## Rejected Alternatives

- **Formula-aware engine / metric mini-language** (proposed in #25747,
  #29297). Unnecessary for SQL-aggregate metrics — evaluating the same
  expression at the target grouping is exact — and fragile for arbitrary user
  SQL. Reserved (in reduced form) only for Bucket B post-processing metrics.
- **One query per grouping combination as the primary mechanism**
  (PR #34592). Correct but `O(2^(R+C))` queries/scans; kept only as the
  fallback where GROUPING SETS is unavailable.
- **Client-side re-aggregation done "more cleverly"** (weighted sums, etc.).
  Cannot recover information destroyed by the first aggregation (e.g. distinct
  counts); fundamentally cannot be correct.
- **New rendering engine (AntV S2 — SIP-205 / #38586).** Routes around the
  problem but still needs correct data from the backend; orthogonal to this fix
  and parked behind the Extensions project.
- **Cosmetic relabeling only** (rename Total→Summary, Subtotal→Subvalue — the
  resolution reached in #29297 and #35089). Useful for honesty about scope but
  does not fix the numbers; complementary, not a substitute.
