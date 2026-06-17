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

/**
 * Flask-AppBuilder authentication type values from bootstrap ``conf.AUTH_TYPE``.
 *
 * Keep in sync with ``flask_appbuilder.const`` (AUTH_OID, AUTH_DB, AUTH_LDAP,
 * AUTH_REMOTE_USER, AUTH_OAUTH, AUTH_SAML).
 */
export enum AuthType {
  AuthOID = 0,
  AuthDB = 1,
  AuthLDAP = 2,
  AuthRemoteUser = 3,
  AuthOauth = 4,
  AuthSAML = 5,
}
