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

import { getMaskedEmail, maskEmail } from './emailMask';

test('masks a valid email address', () => {
  expect(maskEmail('jdoe@example.com')).toBe('j***@example.com');
});

test('trims email addresses before masking', () => {
  expect(maskEmail('  user.name@example.org  ')).toBe('u***@example.org');
});

test('returns empty string for empty values', () => {
  expect(maskEmail()).toBe('');
  expect(maskEmail(null)).toBe('');
  expect(maskEmail('')).toBe('');
});

test('redacts malformed email-like values', () => {
  expect(maskEmail('not-an-email')).toBe('***');
  expect(maskEmail('@example.com')).toBe('***');
  expect(maskEmail('user@')).toBe('***');
});

test('returns raw, masked, and mailto values for boundary-safe consumers', () => {
  expect(getMaskedEmail('jdoe+alerts@example.com')).toEqual({
    raw: 'jdoe+alerts@example.com',
    masked: 'j***@example.com',
    mailto: 'mailto:jdoe%2Balerts%40example.com',
  });
});

test('returns null when no email value exists', () => {
  expect(getMaskedEmail()).toBeNull();
});
