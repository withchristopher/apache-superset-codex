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

export type MaskedEmail = {
  raw: string;
  masked: string;
  mailto: string;
};

const MASK = '***';

/**
 * Masks an email address for display and telemetry while preserving enough
 * domain context for support workflows.
 */
export function maskEmail(email?: string | null): string {
  const normalizedEmail = email?.trim();

  if (!normalizedEmail) {
    return '';
  }

  const atIndex = normalizedEmail.lastIndexOf('@');
  if (atIndex <= 0 || atIndex === normalizedEmail.length - 1) {
    return MASK;
  }

  const localPart = normalizedEmail.slice(0, atIndex);
  const domain = normalizedEmail.slice(atIndex + 1);
  const visibleLocalPart = localPart.slice(0, 1);

  return `${visibleLocalPart}${MASK}@${domain}`;
}

/**
 * Builds a display-safe wrapper for code paths that need both the raw address
 * and the masked representation without confusing the two values.
 */
export function getMaskedEmail(email?: string | null): MaskedEmail | null {
  const normalizedEmail = email?.trim();

  if (!normalizedEmail) {
    return null;
  }

  return {
    raw: normalizedEmail,
    masked: maskEmail(normalizedEmail),
    mailto: `mailto:${encodeURIComponent(normalizedEmail)}`,
  };
}
