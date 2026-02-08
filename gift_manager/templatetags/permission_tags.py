"""Template tags for permission-based UI adaptations."""

from django import template
from django.contrib.auth.models import User

from gift_manager.models import PermissionLevel
from gift_manager.services import PermissionService

register = template.Library()


@register.simple_tag
def user_permission(obj, user):
    """Get the permission level for a user on an object.

    Args:
        obj: The object to check permissions for
        user: The user to check permissions for

    Returns:
        int: The permission level (PermissionLevel constant)
    """
    if not obj or not user or not isinstance(user, User):
        return PermissionLevel.NONE

    try:
        return PermissionService.get_permission(obj, user)
    except (AttributeError, TypeError):
        return PermissionLevel.NONE


@register.simple_tag
def can_edit(obj, user):
    """Check if user can edit the object.

    Args:
        obj: The object to check permissions for
        user: The user to check permissions for

    Returns:
        bool: True if user has EDITOR or OWNER permission
    """
    permission = user_permission(obj, user)
    return permission >= PermissionLevel.EDITOR


@register.simple_tag
def can_delete(obj, user):
    """Check if user can delete the object.

    Args:
        obj: The object to check permissions for
        user: The user to check permissions for

    Returns:
        bool: True if user has OWNER permission
    """
    permission = user_permission(obj, user)
    return permission >= PermissionLevel.OWNER


@register.simple_tag
def can_share(obj, user):
    """Check if user can share the object.

    Args:
        obj: The object to check permissions for
        user: The user to check permissions for

    Returns:
        bool: True if user has EDITOR or OWNER permission
    """
    permission = user_permission(obj, user)
    return permission >= PermissionLevel.EDITOR


@register.simple_tag
def can_view(obj, user):
    """Check if user can view the object.

    Args:
        obj: The object to check permissions for
        user: The user to check permissions for

    Returns:
        bool: True if user has any permission level above NONE
    """
    permission = user_permission(obj, user)
    return permission > PermissionLevel.NONE


@register.filter
def permission_level_name(permission_level):
    """Get the human-readable name for a permission level.

    Args:
        permission_level: The permission level integer

    Returns:
        str: The human-readable permission level name
    """
    return PermissionLevel.get_label(permission_level)


@register.inclusion_tag("gift_manager/includes/permission_actions.html", takes_context=True)
def permission_actions(context, obj, actions=None):
    """Render action buttons based on user permissions.

    Args:
        context: Template context
        obj: The object to check permissions for
        actions: List of actions to include (default: ['edit', 'delete', 'share'])

    Returns:
        dict: Context for the template
    """
    if actions is None:
        actions = ["edit", "delete", "share"]

    user = context.get("user")
    if not user or not user.is_authenticated:
        return {"actions": []}

    permission = user_permission(obj, user)

    # Define action requirements
    action_requirements = {
        "view": PermissionLevel.VIEWER,
        "edit": PermissionLevel.EDITOR,
        "delete": PermissionLevel.OWNER,
        "share": PermissionLevel.EDITOR,
        "create": PermissionLevel.NONE,  # Create doesn't require object permissions
    }

    # Filter actions based on permissions
    allowed_actions = []
    for action in actions:
        required_level = action_requirements.get(action, PermissionLevel.OWNER)
        if permission >= required_level:
            allowed_actions.append({"name": action, "enabled": True, "tooltip": None})
        else:
            # Add disabled action with tooltip
            allowed_actions.append(
                {
                    "name": action,
                    "enabled": False,
                    "tooltip": f"You do not have permission to {action} this object",
                }
            )

    return {
        "obj": obj,
        "actions": allowed_actions,
        "user_permission": permission,
        "permission_level_name": PermissionLevel.get_label(permission),
    }
