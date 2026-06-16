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

"""
MCP tool: update_dashboard

This tool performs a partial update of dashboard metadata (title, slug,
published state, tags, CSS, and selected json_metadata settings).
"""

import logging
from typing import Any

from fastmcp import Context
from sqlalchemy.exc import SQLAlchemyError
from superset_core.mcp.decorators import tool, ToolAnnotations

from superset.commands.exceptions import CommandException
from superset.extensions import event_logger
from superset.mcp_service.dashboard.schemas import (
    DashboardInfo,
    serialize_chart_summary,
    UpdateDashboardRequest,
    UpdateDashboardResponse,
)
from superset.mcp_service.privacy import user_can_view_data_model_metadata
from superset.mcp_service.utils.url_utils import get_superset_base_url
from superset.utils import json

logger = logging.getLogger(__name__)

# Direct dashboard columns accepted by UpdateDashboardCommand
# (subset of DashboardPutSchema).
_DIRECT_FIELDS = (
    "dashboard_title",
    "slug",
    "published",
    "css",
    "tags",
)

# Convenience fields stored inside the dashboard's json_metadata blob.
_METADATA_FIELDS = (
    "cross_filters_enabled",
    "refresh_frequency",
    "filter_bar_orientation",
)


def _build_update_properties(
    request: UpdateDashboardRequest, dashboard: Any
) -> tuple[dict[str, Any], list[str]]:
    """Build the UpdateDashboardCommand properties dict from the request.

    Returns ``(properties, updated_fields)`` where *updated_fields* lists
    the request fields that will be changed.

    json_metadata is a stringified JSON blob and
    ``DashboardDAO.set_dash_metadata`` resets absent keys to defaults
    (e.g. ``expanded_slices`` -> {}). To avoid silently destroying state,
    the dashboard's FULL current json_metadata is read, the requested
    changes are merged in, and the complete blob is written back.
    """
    properties: dict[str, Any] = {}
    updated_fields: list[str] = []

    for field in _DIRECT_FIELDS:
        value = getattr(request, field)
        if value is not None:
            properties[field] = value
            updated_fields.append(field)

    metadata_changes = {
        field: value
        for field in _METADATA_FIELDS
        if (value := getattr(request, field)) is not None
    }
    if metadata_changes:
        try:
            current_metadata = json.loads(dashboard.json_metadata or "{}")
        except (ValueError, TypeError):
            logger.warning(
                "Failed to parse existing json_metadata for dashboard %s; "
                "starting from an empty metadata object",
                dashboard.id,
            )
            current_metadata = {}
        if not isinstance(current_metadata, dict):
            current_metadata = {}
        properties["json_metadata"] = json.dumps(
            {**current_metadata, **metadata_changes}
        )
        updated_fields.extend(metadata_changes)

    return properties, updated_fields


def _find_and_authorize_dashboard(
    dashboard_id: int,
) -> tuple[Any, UpdateDashboardResponse | None]:
    """Return (dashboard, None) on success or (None, error_response) on failure."""
    from superset import security_manager
    from superset.daos.dashboard import DashboardDAO
    from superset.exceptions import SupersetSecurityException

    dashboard = DashboardDAO.find_by_id(dashboard_id)
    if not dashboard:
        return None, UpdateDashboardResponse(
            error=(
                f"Dashboard with ID {dashboard_id} not found."
                " Use list_dashboards to get valid dashboard IDs."
            ),
        )

    try:
        security_manager.raise_for_ownership(dashboard)
    except SupersetSecurityException:
        return None, UpdateDashboardResponse(
            permission_denied=True,
            error=(
                f"You don't have permission to edit dashboard "
                f"'{dashboard.dashboard_title}' (ID: {dashboard_id})."
            ),
        )

    return dashboard, None


def _serialize_updated_dashboard(
    updated_dashboard: Any, updated_fields: list[str]
) -> UpdateDashboardResponse:
    """Build the success response, re-fetching with eager-loaded relationships.

    The preceding command commit may invalidate the session in multi-tenant
    environments; on re-fetch failure, return a minimal response using only
    scalar attributes that are already loaded — relationship fields (tags,
    slices) would trigger lazy-loading on the same dead session.
    """
    from sqlalchemy.orm import subqueryload

    from superset import db
    from superset.daos.dashboard import DashboardDAO
    from superset.models.dashboard import Dashboard
    from superset.models.slice import Slice

    dashboard_url = (
        f"{get_superset_base_url()}/superset/dashboard/{updated_dashboard.id}/"
    )

    try:
        updated_dashboard = (
            DashboardDAO.find_by_id(
                updated_dashboard.id,
                query_options=[
                    subqueryload(Dashboard.slices).subqueryload(Slice.tags),
                    subqueryload(Dashboard.tags),
                ],
            )
            or updated_dashboard
        )
    except SQLAlchemyError:
        logger.warning(
            "Re-fetch of dashboard %s failed; returning minimal response",
            updated_dashboard.id,
            exc_info=True,
        )
        try:
            db.session.rollback()  # pylint: disable=consider-using-transaction
        except SQLAlchemyError:
            logger.warning(
                "Database rollback failed during dashboard re-fetch error handling",
                exc_info=True,
            )
        return UpdateDashboardResponse(
            dashboard=DashboardInfo(
                id=updated_dashboard.id,
                dashboard_title=updated_dashboard.dashboard_title,
                published=updated_dashboard.published,
                url=dashboard_url,
            ),
            dashboard_url=dashboard_url,
            updated_fields=updated_fields,
            error=None,
        )

    from superset.mcp_service.dashboard.schemas import serialize_tag_object

    include_data_model_metadata = user_can_view_data_model_metadata()
    dashboard_info = DashboardInfo(
        id=updated_dashboard.id,
        dashboard_title=updated_dashboard.dashboard_title,
        slug=updated_dashboard.slug,
        description=updated_dashboard.description,
        css=updated_dashboard.css,
        certified_by=updated_dashboard.certified_by,
        certification_details=updated_dashboard.certification_details,
        published=updated_dashboard.published,
        created_on=updated_dashboard.created_on,
        changed_on=updated_dashboard.changed_on,
        uuid=str(updated_dashboard.uuid) if updated_dashboard.uuid else None,
        url=dashboard_url,
        chart_count=len(updated_dashboard.slices),
        tags=[
            obj
            for tag in getattr(updated_dashboard, "tags", [])
            if (obj := serialize_tag_object(tag)) is not None
        ],
        charts=[
            obj
            for chart in getattr(updated_dashboard, "slices", [])
            if (
                obj := serialize_chart_summary(
                    chart,
                    include_data_model_metadata=include_data_model_metadata,
                )
            )
            is not None
        ],
    )

    return UpdateDashboardResponse(
        dashboard=dashboard_info,
        dashboard_url=dashboard_url,
        updated_fields=updated_fields,
        error=None,
    )


@tool(
    tags=["mutate"],
    class_permission_name="Dashboard",
    method_permission_name="write",
    annotations=ToolAnnotations(
        title="Update dashboard",
        readOnlyHint=False,
        destructiveHint=False,
    ),
)
def update_dashboard(
    request: UpdateDashboardRequest, ctx: Context
) -> UpdateDashboardResponse:
    """Partially update an existing dashboard's metadata.

    Only the provided fields are changed; everything else is preserved
    (including layout, charts, and the rest of json_metadata).

    Updatable fields:
    - dashboard_title, slug, published, css
    - tags (a FULL REPLACEMENT list of IDs; discover them with list_tags)
    - cross_filters_enabled, refresh_frequency (seconds, 0 = off),
      filter_bar_orientation ("VERTICAL" | "HORIZONTAL")

    Use when:
    - Renaming, publishing, or unpublishing a dashboard
    - Replacing a dashboard's tags
    - Adjusting styling (CSS) or refresh behavior

    Do NOT use for:
    - Adding charts (use add_chart_to_existing_dashboard)
    - Creating dashboards (use generate_dashboard)

    Returns the updated dashboard info, its URL, and the list of fields
    that were changed.
    """
    try:
        from superset.commands.dashboard.exceptions import (
            DashboardForbiddenError,
            DashboardInvalidError,
            DashboardNotFoundError,
        )
        from superset.commands.dashboard.update import UpdateDashboardCommand

        with event_logger.log_context(action="mcp.update_dashboard.validation"):
            dashboard, auth_error = _find_and_authorize_dashboard(request.dashboard_id)
            if auth_error is not None:
                return auth_error

            properties, updated_fields = _build_update_properties(request, dashboard)
            if not properties:
                return UpdateDashboardResponse(
                    error=(
                        "No fields provided to update. Provide at least one "
                        "field (e.g. dashboard_title, published, tags)."
                    ),
                )

            # The REST update path hardens user-supplied CSS via the marshmallow
            # DashboardPutSchema (validate_css); this tool bypasses that schema,
            # so apply the same check before persisting to avoid storing CSS the
            # API would reject (e.g. @import, script-scheme URLs).
            if "css" in properties:
                from marshmallow import ValidationError

                from superset.dashboards.schemas import validate_css

                try:
                    validate_css(properties["css"])
                except ValidationError as ex:
                    detail = (
                        "; ".join(str(m) for m in ex.messages)
                        if isinstance(ex.messages, list)
                        else str(ex.messages)
                    )
                    return UpdateDashboardResponse(
                        error=f"Dashboard CSS is invalid: {detail}",
                    )

        with event_logger.log_context(action="mcp.update_dashboard.db_write"):
            try:
                command = UpdateDashboardCommand(request.dashboard_id, properties)
                updated_dashboard = command.run()
            except DashboardNotFoundError:
                return UpdateDashboardResponse(
                    error=(
                        f"Dashboard with ID {request.dashboard_id} not found."
                        " Use list_dashboards to get valid dashboard IDs."
                    ),
                )
            except DashboardForbiddenError:
                return UpdateDashboardResponse(
                    permission_denied=True,
                    error=(
                        f"You don't have permission to edit dashboard "
                        f"ID {request.dashboard_id}."
                    ),
                )
            except DashboardInvalidError as ex:
                return UpdateDashboardResponse(
                    error=f"Dashboard update is invalid: {ex.normalized_messages()}",
                )

        logger.info(
            "Updated dashboard %s (fields: %s)",
            request.dashboard_id,
            ", ".join(updated_fields),
        )

        return _serialize_updated_dashboard(updated_dashboard, updated_fields)

    except (CommandException, SQLAlchemyError, KeyError, ValueError, TypeError) as e:
        from superset import db

        try:
            db.session.rollback()  # pylint: disable=consider-using-transaction
        except SQLAlchemyError:
            logger.warning(
                "Database rollback failed during error handling", exc_info=True
            )
        logger.error("Error updating dashboard: %s", e)
        return UpdateDashboardResponse(
            error=f"Failed to update dashboard: {str(e)}",
        )
