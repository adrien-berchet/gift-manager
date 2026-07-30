from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import PermissionDenied
from django.db.models import Model
from django.utils.translation import gettext

from gift_manager.models import PermissionLevel
from gift_manager.models import PersonGroup
from gift_manager.models import PersonGroupPermission


class PermissionService:
    """Service for managing permissions."""

    VALID_PERMISSION_LEVELS = {
        PermissionLevel.VIEWER,
        PermissionLevel.EDITOR,
        PermissionLevel.OWNER,
    }

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
    def get_effective_permission(cls, obj, user) -> int:
        """Get permission including ownership implied by user_link."""
        if user.is_superuser:
            return PermissionLevel.OWNER

        if isinstance(obj, PersonGroup):
            return cls.get_effective_permission_for_group(obj, user)

        permission = cls.get_permission(obj, user)
        if getattr(obj, "user_link_id", None) == user.id:
            return max(permission, PermissionLevel.OWNER)
        return permission

    @classmethod
    def validate_permission_level(cls, permission_level: int) -> int:
        """Validate a shareable permission level."""
        if permission_level not in cls.VALID_PERMISSION_LEVELS:
            raise ValueError(gettext("Invalid permission value."))
        return permission_level

    @classmethod
    def assert_can_manage_permission(
        cls,
        actor,
        obj,
        target_user,
        permission_level: int | None,
    ) -> None:
        """Validate that actor can change target_user's permission on obj."""
        actor_permission = cls.get_effective_permission(obj, actor)
        if actor_permission < PermissionLevel.OWNER:
            raise PermissionDenied(
                gettext("You do not have permission to manage sharing for this object.")
            )

        if permission_level is not None:
            cls.validate_permission_level(permission_level)

        target_permission = cls.get_permission(obj, target_user)
        target_effective_permission = cls.get_effective_permission(obj, target_user)
        target_is_friend = cls.users_are_friends(actor, target_user)
        expanding_non_friend_access = (
            permission_level is not None
            and permission_level > target_permission
            and not target_is_friend
        )
        if target_permission == PermissionLevel.NONE and not target_is_friend:
            raise PermissionDenied(gettext("Objects can only be shared with friends."))

        if expanding_non_friend_access:
            raise PermissionDenied(gettext("Objects can only be shared with friends."))

        is_demoting_or_removing_owner = (
            target_effective_permission == PermissionLevel.OWNER
            and permission_level != PermissionLevel.OWNER
        )
        if is_demoting_or_removing_owner and len(cls._owner_user_ids(obj)) <= 1:
            raise PermissionDenied(gettext("At least one owner is required."))

    @classmethod
    def assert_can_leave_object(cls, user, obj) -> None:
        """Validate that user can remove their own access to obj."""
        user_permission = cls.get_effective_permission(obj, user)
        if user_permission < PermissionLevel.VIEWER:
            raise PermissionDenied(gettext("You do not have access to this object."))

        if isinstance(obj, PersonGroup) and cls.get_permission(obj, user) == PermissionLevel.NONE:
            raise PermissionDenied(gettext("This group access is inherited from a parent group."))

        if user_permission == PermissionLevel.OWNER and len(cls._owner_user_ids(obj)) <= 1:
            raise PermissionDenied(gettext("At least one owner is required."))

    @classmethod
    def has_other_access_holder(cls, obj, user) -> bool:
        """Return whether someone besides user has effective access to obj."""
        if obj.shared_with.exclude(id=user.id).exists():
            return True

        linked_user_id = getattr(obj, "user_link_id", None)
        if linked_user_id is not None and linked_user_id != user.id:
            return True

        if isinstance(obj, PersonGroup):
            return (
                PersonGroupPermission.objects.filter(
                    group__in=obj.get_ancestors(use_cache=False),
                    inherit_permissions=True,
                )
                .exclude(user=user)
                .exists()
            )

        return False

    @staticmethod
    def users_are_friends(actor, target_user) -> bool:
        """Return whether target_user is one of actor's friends."""
        try:
            return actor.profile.friends.filter(user=target_user).exists()
        except (AttributeError, ObjectDoesNotExist):
            return False

    @classmethod
    def _owner_user_ids(cls, obj) -> set[int]:
        """Return users who currently have effective owner permission on obj."""
        model = cls.get_permission_model(obj)
        object_attr = cls._get_permission_object_attr(obj, model)
        owner_ids = set(
            model.objects.filter(
                **{object_attr: obj},
                permission_type=PermissionLevel.OWNER,
            ).values_list("user_id", flat=True)
        )

        linked_user_id = getattr(obj, "user_link_id", None)
        if linked_user_id is not None:
            owner_ids.add(linked_user_id)

        if isinstance(obj, PersonGroup):
            owner_ids.update(
                PersonGroupPermission.objects.filter(
                    group__in=obj.get_ancestors(use_cache=False),
                    inherit_permissions=True,
                    permission_type=PermissionLevel.OWNER,
                ).values_list("user_id", flat=True)
            )

        return owner_ids

    @classmethod
    def _get_permission_object_attr(cls, obj, model, object_attr=None) -> str:
        """Resolve the permission model field that points at obj."""
        if object_attr is not None:
            return object_attr

        try:
            return model.filter_name
        except AttributeError:
            return obj.__class__.__name__.lower()

    @classmethod
    def get_effective_permission_for_group(cls, group, user) -> int:
        """Get the permission for a user on a PersonGroup, considering cascade inheritance.

        This method returns the highest level from direct permissions and parent
        groups with inherit_permissions=True.

        Args:
            group: PersonGroup instance
            user: User instance

        Returns:
            int: The effective permission level
        """
        direct_permission = PersonGroupPermission.objects.filter(user=user, group=group).first()
        direct_level = (
            direct_permission.permission_type if direct_permission else PermissionLevel.NONE
        )

        ancestors = group.get_ancestors()
        inherited_permissions = PersonGroupPermission.objects.filter(
            user=user, group__in=ancestors, inherit_permissions=True
        )

        inherited_level = PermissionLevel.NONE
        if inherited_permissions.exists():
            inherited_level = max(p.permission_type for p in inherited_permissions)

        return max(direct_level, inherited_level)

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
        permission_level = cls.validate_permission_level(permission_level)
        model = cls.get_permission_model(obj)
        if not model:
            raise ValueError(gettext("Could not determine permission model for this object type"))

        object_attr = cls._get_permission_object_attr(obj, model, object_attr)
        filter_kwargs = {"user": user, object_attr: obj}

        permission_obj, _ = model.objects.get_or_create(
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

        object_attr = cls._get_permission_object_attr(obj, model)
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
