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
"""Add dataset-level source time zone

Adds ``tables.source_timezone`` — the IANA zone the dataset's naive temporal
columns are stored in. A separate revision from ``fb9ce2cddbe8`` so environments
that already applied that revision get this column on a deterministic upgrade
path. Nullable, default NULL — additive, inert, reversible.

Revision ID: b943f45a4e2d
Revises: fb9ce2cddbe8
Create Date: 2026-06-09 15:00:00.000000

"""

import sqlalchemy as sa

from superset.migrations.shared.utils import add_columns, drop_columns

# revision identifiers, used by Alembic.
revision = "b943f45a4e2d"
down_revision = "fb9ce2cddbe8"


def upgrade():
    add_columns(
        "tables",
        sa.Column("source_timezone", sa.String(length=64), nullable=True),
    )


def downgrade():
    drop_columns("tables", "source_timezone")
