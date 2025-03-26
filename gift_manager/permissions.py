from django.db.models import Model
from django.utils.translation import gettext

from gift_manager.models import PermissionLevel

PERMISSION_LEVELS = [
    {
        "value": PermissionLevel.VIEWER,
        "label": PermissionLevel.get_label(PermissionLevel.VIEWER, case="title"),
    },
    {
        "value": PermissionLevel.EDITOR,
        "label": PermissionLevel.get_label(PermissionLevel.EDITOR, case="title"),
    },
    {
        "value": PermissionLevel.OWNER,
        "label": PermissionLevel.get_label(PermissionLevel.OWNER, case="title"),
    },
]


def get_permission_model(obj) -> type[Model] | None:
    """Get the permission model for the given object."""
    try:
        return obj.shared_with.through
    except AttributeError:
        raise TypeError(
            gettext(
                "Could not determine the model of the object because it does not have a "
                "'shared_with' attribute"
            )
        ) from None


def get_permission(obj, user, filter_name=None):
    """Get the permission type for the user on the object."""
    model = get_permission_model(obj)
    if filter_name is None:
        try:
            filter_name = model.filter_name
        except KeyError:
            raise ValueError(
                gettext("Could not determine filter name for this object type")
            ) from None
    permission = model.objects.filter(**{"user": user, filter_name: obj}).first()
    return permission.permission_type if permission else PermissionLevel.NONE


def get_permission_label(obj, user, filter_name, case="lower"):
    """Get the permission label for the user on the object."""
    permission_value = get_permission(obj, user, filter_name)
    return PermissionLevel.get_label(permission_value, case=case)


def create_or_update_permission(
    user, obj, *, permission_level=PermissionLevel.VIEWER, object_attr=None
):
    """Create or update a permission for a user on an object.

    Args:
        user: The user to grant permission to
        obj: The object to grant permission on
        permission_level: The permission level to grant
        object_attr: The name used to retrieve the object from the permission model

    Returns:
        Model: The created or updated permission object
    """
    model = get_permission_model(obj)
    if not model:
        raise ValueError(gettext("Could not determine permission model for this object type"))

    if object_attr is None:
        object_attr = obj.__class__.__name__.lower()
    filter_kwargs = {"user": user, object_attr: obj}

    permission_obj, created = model.objects.get_or_create(
        **filter_kwargs, defaults={"permission_type": permission_level}
    )

    if permission_obj.permission_type != permission_level:
        permission_obj.permission_type = permission_level
        permission_obj.save()

    # Ensure the user is added to shared_with
    if hasattr(obj, "shared_with") and user not in obj.shared_with.all():
        obj.shared_with.add(user)

    return permission_obj


def delete_permission(user, obj):
    """Delete a user's permission on an object.

    Args:
        user: The user whose permission should be deleted
        obj: The object on which the permission was granted

    Returns:
        bool: True if deletion succeeded, False otherwise
    """
    model = get_permission_model(obj)
    if not model:
        raise ValueError(gettext("Could not determine permission model for this object type"))

    object_attr = obj.__class__.__name__.lower()
    filter_kwargs = {"user": user, object_attr: obj}

    try:
        permission_obj = model.objects.get(**filter_kwargs)
        permission_obj.delete()

        # Also remove the user from shared_with
        if hasattr(obj, "shared_with") and user in obj.shared_with.all():
            obj.shared_with.remove(user)

        return True  # noqa: TRY300
    except model.DoesNotExist:
        return False
