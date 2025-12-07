from django.db.models import Model
from django.utils.text import capfirst

# Use _PERMISSION_LABEL_DICT directly to preserve lazy translations
from gift_manager.models import _PERMISSION_LABEL_DICT
from gift_manager.models import PermissionLevel
from gift_manager.services import PermissionService

PERMISSION_LEVELS = [
    {
        "value": PermissionLevel.VIEWER,
        "label": capfirst(_PERMISSION_LABEL_DICT[PermissionLevel.VIEWER]),
    },
    {
        "value": PermissionLevel.EDITOR,
        "label": capfirst(_PERMISSION_LABEL_DICT[PermissionLevel.EDITOR]),
    },
    {
        "value": PermissionLevel.OWNER,
        "label": capfirst(_PERMISSION_LABEL_DICT[PermissionLevel.OWNER]),
    },
]


def get_permission_model(obj) -> type[Model] | None:
    """Get the permission model for the given object."""
    return PermissionService.get_permission_model(obj)


def get_permission(obj, user, filter_name=None):
    """Get the permission type for the user on the object."""
    return PermissionService.get_permission(obj, user, filter_name)


def get_permission_label(obj, user, filter_name, case="lower"):
    """Get the permission label for the user on the object."""
    return PermissionService.get_permission_label(obj, user, filter_name, case)


def create_or_update_permission(
    user, obj, *, permission_level=PermissionLevel.VIEWER, object_attr=None
):
    """Create or update a permission for a user on an object."""
    return PermissionService.create_or_update_permission(
        user, obj, permission_level=permission_level, object_attr=object_attr
    )


def delete_permission(user, obj):
    """Delete a user's permission on an object."""
    return PermissionService.delete_permission(user, obj)
