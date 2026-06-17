# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""merging two heads

Revision ID: 33a0aac0a26a
Revises: ('c6219cac9270', '78a40c08b4be')
Create Date: 2026-06-16 16:00:00.000000

"""

# revision identifiers, used by Alembic.
revision = "33a0aac0a26a"
down_revision = ("c6219cac9270", "78a40c08b4be")


def upgrade() -> None:
    """Merge auth-session and semantic-layer migration branches."""


def downgrade() -> None:
    """No-op: merge revisions have no schema changes to revert."""
