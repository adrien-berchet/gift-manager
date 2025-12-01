from django.db.models import Model
from django.utils.translation import gettext

from gift_manager.models import PermissionLevel


class PermissionService:
    """Service for managing permissions."""

    @staticmethod
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

    @classmethod
    def get_permission(cls, obj, user, filter_name=None) -> int:
        """Get the permission type for the user on the object."""
        model = cls.get_permission_model(obj)
        if filter_name is None:
            try:
                filter_name = model.filter_name
            except KeyError:
                raise ValueError(
                    gettext("Could not determine filter name for this object type")
                ) from None
        permission = model.objects.filter(**{"user": user, filter_name: obj}).first()
        return permission.permission_type if permission else PermissionLevel.NONE

    @classmethod
    def get_permission_label(cls, obj, user, filter_name, case="lower") -> str:
        """Get the permission label for the user on the object."""
        permission_value = cls.get_permission(obj, user, filter_name)
        return PermissionLevel.get_label(permission_value, case=case)

    @classmethod
    def create_or_update_permission(
        cls, user, obj, *, permission_level=PermissionLevel.VIEWER, object_attr=None
    ) -> Model:
        """Create or update a permission for a user on an object."""
        model = cls.get_permission_model(obj)
        if not model:
            raise ValueError(gettext("Could not determine permission model for this object type"))

        if object_attr is None:
            # Use the filter_name from the permission model if available
            try:
                object_attr = model.filter_name
            except AttributeError:
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

    @classmethod
    def delete_permission(cls, user, obj) -> bool:
        """Delete a user's permission on an object."""
        model = cls.get_permission_model(obj)
        if not model:
            raise ValueError(gettext("Could not determine permission model for this object type"))

        # Use the filter_name from the permission model if available
        try:
            object_attr = model.filter_name
        except AttributeError:
            object_attr = obj.__class__.__name__.lower()
        filter_kwargs = {"user": user, object_attr: obj}

        try:
            permission_obj = model.objects.get(**filter_kwargs)
            permission_obj.delete()

            # Also remove the user from shared_with
            if hasattr(obj, "shared_with") and user in obj.shared_with.all():
                obj.shared_with.remove(user)
        except model.DoesNotExist:
            return False
        else:
            return True
