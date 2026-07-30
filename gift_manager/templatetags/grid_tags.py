"""Custom template tags for Grid.js integration."""

import json
from typing import Any

from django import template
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import SafeString

register = template.Library()


def _safe_json(value: Any) -> SafeString:
    """Serialize JSON for direct use in script blocks without raw HTML tokens."""
    serialized = json.dumps(value)
    serialized = serialized.replace("&", "\\u0026").replace("<", "\\u003C").replace(">", "\\u003E")
    return SafeString(serialized)


@register.simple_tag
def grid_action_urls(object_type: str, object_id: str, actions: list[str] | None = None) -> str:
    """Generate action button URLs for Grid.js.

    Args:
        object_type: The type of object (e.g., 'person', 'gift', 'event')
        object_id: The object's ID
        actions: List of actions to include (default: ['details', 'edit', 'delete'])

    Returns:
        JSON string of action URLs
    """
    if actions is None:
        actions = ["details", "edit", "delete"]

    url_map = {}
    for action in actions:
        try:
            if action == "give":
                # Special case for add_relation
                url_name = f"gift_manager:{object_type}_add_relation"
            elif action == "details":
                url_name = f"gift_manager:{object_type}_detail"
            elif action == "edit":
                url_name = f"gift_manager:{object_type}_update"
            elif action == "delete":
                url_name = f"gift_manager:{object_type}_delete"
            else:
                url_name = f"gift_manager:{object_type}_{action}"

            url_map[action] = reverse(url_name, args=[object_id])
        except Exception:
            # Skip actions that don't have URLs
            continue

    return _safe_json(url_map)


@register.filter
def to_grid_data(queryset, columns: dict | None = None) -> str:
    """Convert a Django queryset to Grid.js data format.

    Args:
        queryset: Django queryset or list of dicts
        columns: Optional dict of column names to extract

    Returns:
        JSON string suitable for Grid.js
    """
    data = []

    for item in queryset:
        if isinstance(item, dict):
            # Handle dict (from .values())
            if columns:
                row = [item.get(col, "") for col in columns.keys()]
            else:
                row = list(item.values())
        # Handle model instance
        elif columns:
            row = [getattr(item, col, "") for col in columns.keys()]
        else:
            row = [str(item)]

        data.append(row)

    return _safe_json(data)


@register.filter
def to_grid_columns(columns: dict, actions: list[str] | None = None) -> str:
    """Convert column definitions to Grid.js column format.

    Args:
        columns: Dict of column_key: column_label
        actions: Optional list of action buttons to include

    Returns:
        JSON string of column definitions for Grid.js
    """
    grid_columns = []

    for col_key, col_label in columns.items():
        grid_columns.append({"id": col_key, "name": str(col_label)})

    # Add actions column if specified
    if actions:
        grid_columns.append(
            {
                "id": "actions",
                "name": "Actions",
                "sort": False,
            }
        )

    return _safe_json(grid_columns)


@register.simple_tag
def grid_data_row(item: dict, columns: dict, id_field: str = "id") -> str:
    """Convert a single item to a Grid.js data row.

    Args:
        item: Dict representing a single row
        columns: Dict of column keys
        id_field: Name of the ID field

    Returns:
        JavaScript array literal for a Grid.js row
    """
    row_data = []

    for col_key in columns:
        value = item.get(col_key, "")

        # Handle special cases
        if isinstance(value, (list, dict)):
            row_data.append(value)
        elif value is None:
            row_data.append("")
        else:
            row_data.append(str(value))

    # Add ID field
    id_value = item.get(id_field, "")
    row_data.append(str(id_value))

    return _safe_json(row_data)


@register.simple_tag(takes_context=True)
def grid_create_button(context: dict, object_type: str, label: str | None = None) -> str:
    """Generate a create button for list views.

    Args:
        context: Template context (for i18n)
        object_type: The type of object (e.g., 'person', 'gift')
        label: Optional custom label (default: 'Create new {object_type}')

    Returns:
        HTML for create button
    """
    if label is None:
        label = f"Create new {object_type}"

    try:
        url = reverse(f"gift_manager:{object_type}_create")
        return format_html(
            '<a href="{}" class="btn btn-primary mb-3"><i class="fas fa-plus me-2"></i>{}</a>',
            url,
            label,
        )
    except Exception:
        return ""


@register.filter
def format_grid_value(value: Any, column_type: str = "text") -> str:
    """Format a value for display in Grid.js based on column type.

    Args:
        value: The value to format
        column_type: Type of column ('text', 'date', 'email', 'list')

    Returns:
        Formatted string value
    """
    if value is None:
        return ""

    if column_type == "list" and isinstance(value, (list, tuple)):
        # For lists, return comma-separated values
        return ", ".join(str(v) for v in value)
    if column_type == "date":
        # Format dates
        if hasattr(value, "strftime"):
            return value.strftime("%Y-%m-%d")
        return str(value)
    if column_type == "email":
        # Email with mailto link
        return format_html('<a href="mailto:{}">{}</a>', value, value)
    return str(value)


@register.simple_tag
def grid_config(
    pagination_limit: int = 10,
    search: bool = True,
    sort: bool = True,
    resizable: bool = True,
) -> str:
    """Generate Grid.js configuration object.

    Args:
        pagination_limit: Number of items per page
        search: Enable search
        sort: Enable sorting
        resizable: Enable column resizing

    Returns:
        JSON string of Grid.js configuration
    """
    config = {
        "pagination": {"enabled": True, "limit": pagination_limit},
        "search": {"enabled": search},
        "sort": {"enabled": sort},
        "resizable": resizable,
    }

    return _safe_json(config)
