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

## @superset-ui/core

[![Version](https://img.shields.io/npm/v/@superset-ui/core.svg?style=flat)](https://www.npmjs.com/package/@superset-ui/core)
[![Libraries.io](https://img.shields.io/librariesio/release/npm/%40superset-ui%2Fcore?style=flat)](https://libraries.io/npm/@superset-ui%2Fcore)

The core package for Apache Superset's frontend. It provides shared utilities,
types, and abstractions used across all Superset chart plugins and UI components.

Key modules include:

- **query** — Utilities for building and sending queries to the Superset backend
- **number-format** — Number formatting helpers powered by d3-format
- **time-format** — Time/date formatting helpers powered by d3-time-format
- **connection** — HTTP client for communicating with the Superset REST API
- **translation** — i18n utilities (`t()`, `tn()`) for internationalizing strings
- **chart** — Base classes and types for building chart plugins

#### Example usage

```js
import { getNumberFormatter, t, makeApi } from '@superset-ui/core';

// Format a number
const formatter = getNumberFormatter('.2f');
console.log(formatter(1234.5)); // "1234.50"

// Translate a string
console.log(t('Hello %s', 'world'));

// Call a Superset API endpoint
const fetchDashboards = makeApi({ method: 'GET', endpoint: '/api/v1/dashboard' });
```

### Development

`@data-ui/build-config` is used to manage the build configuration for this package
including babel builds, jest testing, eslint, and prettier.

Run tests:

```bash
cd superset-frontend
npx jest packages/superset-ui-core
```