from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count
from django.db.models import Max
from django.db.models import Model
from django.db.models import Q
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy

from gift_manager.models import PermissionLevel
from gift_manager.models import PersonGroup
from gift_manager.models import PersonGroupPermission
from gift_manager.models import Relation

GLOBAL_OBJECT_REMOVAL_ERROR = gettext_lazy(
    "This object is available to everyone and cannot be removed."
)


class PermissionService:
    """Service for managing permissions."""

    @staticmethod
    @contextmanager
    def locked_for_permission_change(obj) -> Iterator[None]:
        """Serialize permission changes on obj for the duration of the block.

        Checks such as "at least one owner is required" read the current permissions and
        then write, so two concurrent requests could both pass the check and remove every
        owner. Holding the object's row lock across check and write makes the second
        request see the first one's result. Row locks are a no-op on SQLite.
        """
        with transaction.atomic():
            PermissionService.lock_object(obj)
            yield

    @staticmethod
    def lock_object(obj) -> None:
        """Take obj's row lock until the surrounding transaction ends (needs atomic)."""
        type(obj)._base_manager.select_for_update().filter(pk=obj.pk).first()  # noqa: SLF001

    VALID_PERMISSION_LEVELS = {
        PermissionLevel.VIEWER,
        PermissionLevel.EDITOR,
        PermissionLevel.OWNER,
    }

    DELETE_RESULT_DELETED = "deleted"
    DELETE_RESULT_UNSHARED = "shared_removed"

    # What "delete" means for a user on an object (see delete_mode_for)
    DELETE_MODE_DELETE = "delete"
    DELETE_MODE_LEAVE = "leave"
    DELETE_MODE_HANDOVER = "handover"
    DELETE_MODE_NONE = "none"

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
    def get_permission_map(cls, obj) -> dict[int, int]:
        """Return every user's direct permission level on obj, in one query."""
        model = cls.get_permission_model(obj)
        object_attr = cls._get_permission_object_attr(obj, model)
        return dict(
            model.objects.filter(**{object_attr: obj}).values_list("user_id", "permission_type")
        )

    @classmethod
    def get_effective_permission(cls, obj, user) -> int:
        """Get permission level for an object and user."""
        if getattr(obj, "is_global", False):
            # Global objects (e.g. the Birthday event) are shared by every user and read-only
            # for everyone, superusers included: changing them would affect every account
            return PermissionLevel.VIEWER
        if user.is_superuser:
            return PermissionLevel.OWNER

        if isinstance(obj, PersonGroup):
            return cls.get_effective_permission_for_group(obj, user)

        return cls.get_permission(obj, user)

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

        if getattr(obj, "is_global", False):
            # Access comes from the object being global, there is no permission to remove
            raise PermissionDenied(GLOBAL_OBJECT_REMOVAL_ERROR)

        if isinstance(obj, PersonGroup) and cls.get_permission(obj, user) == PermissionLevel.NONE:
            raise PermissionDenied(gettext("This group access is inherited from a parent group."))

        if cls._needs_handover(user, obj):
            # Leaving would leave the object without an active owner
            raise PermissionDenied(gettext("At least one owner is required."))

    @classmethod
    def delete_mode_for(cls, user, obj) -> tuple[str, str | None]:
        """Return what deleting ``obj`` does for ``user`` and, when nothing, why.

        Mirrors ``delete_or_leave``: while someone else holds access, deleting only removes the
        user's own access ("leave"); otherwise editors delete the object. Public tags and global
        objects are visible to everyone, so there is nothing to delete or leave.
        """
        if getattr(obj, "is_public", False):
            return cls.DELETE_MODE_NONE, gettext("A public tag cannot be deleted or left.")
        if getattr(obj, "is_global", False):
            return cls.DELETE_MODE_NONE, str(GLOBAL_OBJECT_REMOVAL_ERROR)
        if cls.has_other_access_holder(obj, user):
            return cls._shared_delete_mode(user, obj)
        if cls.get_effective_permission(obj, user) >= PermissionLevel.EDITOR:
            return cls.DELETE_MODE_DELETE, None
        return cls.DELETE_MODE_NONE, gettext("You do not have permission to delete this object.")

    @classmethod
    def _shared_delete_mode(cls, user, obj) -> tuple[str, str | None]:
        """Delete mode while someone else holds access: leave, hand over, or nothing."""
        if cls._needs_handover(user, obj) and cls.handover_candidates(user, obj):
            return cls.DELETE_MODE_HANDOVER, None
        try:
            cls.assert_can_leave_object(user, obj)
        except PermissionDenied as exc:
            return cls.DELETE_MODE_NONE, str(exc)
        return cls.DELETE_MODE_LEAVE, None

    @classmethod
    def delete_modes_for(cls, user, model, object_ids, id_field: str) -> dict[str, str]:
        """Return the delete mode of each object of a list, keyed by its public id.

        See ``delete_states_for``, which also gives why nothing is possible.
        """
        return {
            object_id: mode
            for object_id, (mode, _reason) in cls.delete_states_for(
                user, model, object_ids, id_field
            ).items()
        }

    @classmethod
    def delete_states_for(
        cls, user, model, object_ids, id_field: str
    ) -> dict[str, tuple[str, str | None]]:
        """Return ``delete_mode_for`` of each object of a list, keyed by its public id.

        For grid rows: the permissions of the whole list are read at once instead of several
        queries per row. Groups inherit access from their ancestors, so they keep the
        per-object rule.

        Args:
            user: The user looking at the list.
            model: The model of the listed objects.
            object_ids: Their public ids (``person_id``, ``gift_id``...).
            id_field: The name of that public id field.
        """
        object_ids = [object_id for object_id in object_ids if object_id]
        if not object_ids:
            return {}
        objects = list(model.objects.filter(**{f"{id_field}__in": object_ids}))
        if model is PersonGroup:
            return {str(getattr(obj, id_field)): cls.delete_mode_for(user, obj) for obj in objects}

        permission_model = model.shared_with.through
        object_attr = permission_model.filter_name
        holders: dict[int, list[tuple[int, int, bool]]] = {}
        for object_pk, user_id, level, is_active in permission_model.objects.filter(
            **{f"{object_attr}__in": objects}
        ).values_list(f"{object_attr}_id", "user_id", "permission_type", "user__is_active"):
            holders.setdefault(object_pk, []).append((user_id, level, is_active))
        try:
            friend_ids = set(user.profile.friends.values_list("user_id", flat=True))
        except ObjectDoesNotExist:
            friend_ids = set()
        return {
            str(getattr(obj, id_field)): cls._delete_state_from_holders(
                user, obj, holders.get(obj.pk, []), friend_ids
            )
            for obj in objects
        }

    @classmethod
    def with_delete_modes(cls, user, objects, id_field: str) -> list:
        """Return ``objects`` as a list, each carrying its ``delete_mode`` for ``user``."""
        objects = list(objects)
        if objects:
            modes = cls.delete_modes_for(
                user, type(objects[0]), [getattr(obj, id_field) for obj in objects], id_field
            )
            for obj in objects:
                obj.delete_mode = modes.get(str(getattr(obj, id_field)), cls.DELETE_MODE_NONE)
        return objects

    @classmethod
    def _delete_state_from_holders(  # noqa: PLR0911 - one return per case of the rule
        cls, user, obj, holders, friend_ids
    ) -> tuple[str, str | None]:
        """Apply the rule of ``delete_mode_for`` to an object's (user, level, active) holders."""
        if getattr(obj, "is_public", False):
            return cls.DELETE_MODE_NONE, gettext("A public tag cannot be deleted or left.")
        if getattr(obj, "is_global", False):
            return cls.DELETE_MODE_NONE, str(GLOBAL_OBJECT_REMOVAL_ERROR)
        direct = next(
            (level for user_id, level, _active in holders if user_id == user.pk),
            PermissionLevel.NONE,
        )
        effective = PermissionLevel.OWNER if user.is_superuser else direct
        others = [holder for holder in holders if holder[0] != user.pk]
        if not others:
            if effective >= PermissionLevel.EDITOR:
                return cls.DELETE_MODE_DELETE, None
            return cls.DELETE_MODE_NONE, gettext(
                "You do not have permission to delete this object."
            )

        other_active_owner = any(
            level == PermissionLevel.OWNER and is_active for _user_id, level, is_active in others
        )
        needs_handover = direct == PermissionLevel.OWNER and not other_active_owner
        if needs_handover:
            has_candidate = any(
                is_active and user_id in friend_ids for user_id, _level, is_active in others
            )
            if has_candidate:
                return cls.DELETE_MODE_HANDOVER, None
            # Leaving would leave the object without an active owner
            return cls.DELETE_MODE_NONE, gettext("At least one owner is required.")
        if effective < PermissionLevel.VIEWER:
            return cls.DELETE_MODE_NONE, gettext("You do not have access to this object.")
        return cls.DELETE_MODE_LEAVE, None

    @classmethod
    def _needs_handover(cls, user, obj) -> bool:
        """Whether ``user`` is the only active owner of ``obj`` and must name a new one to leave.

        Only a direct owner permission can be handed over: inherited group ownership and a
        superuser's implicit access are not removed by leaving.
        """
        if getattr(obj, "is_global", False):
            return False
        if cls.get_permission(obj, user) != PermissionLevel.OWNER:
            return False
        active_owner_ids = set(
            User.objects.filter(pk__in=cls._owner_user_ids(obj), is_active=True).values_list(
                "pk", flat=True
            )
        )
        return active_owner_ids <= {user.pk}

    @classmethod
    def handover_candidates(cls, user, obj) -> list:
        """Return who can take over ``obj`` from its only owner ``user``, editors first.

        Only users the object is directly shared with and who are still ``user``'s friends:
        handing over must not extend access to anyone new.
        """
        model = cls.get_permission_model(obj)
        object_attr = cls._get_permission_object_attr(obj, model)
        permissions = (
            model.objects.filter(**{object_attr: obj})
            .exclude(user=user)
            .select_related("user")
            .order_by("-permission_type", "user__username")
        )
        try:
            friend_ids = set(user.profile.friends.values_list("user_id", flat=True))
        except ObjectDoesNotExist:
            friend_ids = set()
        return [
            permission.user
            for permission in permissions
            if permission.user.is_active and permission.user_id in friend_ids
        ]

    @classmethod
    def _hand_over(cls, actor, obj, new_owner) -> None:
        """Make ``new_owner`` an owner of ``obj`` so its only owner ``actor`` can leave it."""
        if new_owner is None or new_owner not in cls.handover_candidates(actor, obj):
            raise PermissionDenied(gettext("Choose who becomes the new owner."))
        cls.create_or_update_permission(new_owner, obj, permission_level=PermissionLevel.OWNER)

    @classmethod
    def delete_or_leave(cls, actor, obj, *, is_leave_request: bool = False, new_owner=None) -> str:
        """Delete an object, or remove actor's access if it is shared with other users.

        Args:
            actor: The user requesting the deletion or leave.
            obj: The model instance to delete or leave.
            is_leave_request: If True, actor explicitly requested to leave access (does not
                require editor permission, but still enforces assert_can_leave_object).
            new_owner: When actor is the only owner of a shared object, the user (one of
                ``handover_candidates``) who becomes its owner before actor leaves it.

        Returns:
            "shared_removed" if actor's access was removed while other users retain access.
            "deleted" if the object was completely deleted.

        Raises:
            PermissionDenied: If actor lacks permission to delete the object or leave access.
        """
        cls.lock_object(obj)

        if cls.has_other_access_holder(obj, actor) and cls._needs_handover(actor, obj):
            cls._hand_over(actor, obj, new_owner)

        if is_leave_request:
            cls.assert_can_leave_object(actor, obj)
            cls.delete_permission(actor, obj)
            return cls.DELETE_RESULT_UNSHARED

        if cls.has_other_access_holder(obj, actor):
            permission = cls.get_effective_permission(obj, actor)
            if permission < PermissionLevel.EDITOR:
                raise PermissionDenied(
                    gettext("Use the leave access action to remove your own access.")
                )
            cls.assert_can_leave_object(actor, obj)
            cls.delete_permission(actor, obj)
            return cls.DELETE_RESULT_UNSHARED

        permission = cls.get_effective_permission(obj, actor)
        if permission < PermissionLevel.EDITOR:
            raise PermissionDenied(gettext("You do not have permission to delete this object."))

        obj.delete()
        return cls.DELETE_RESULT_DELETED

    @classmethod
    def has_other_access_holder(cls, obj, user) -> bool:
        """Return whether someone besides user has effective access to obj."""
        if obj.shared_with.exclude(id=user.id).exists():
            return True

        if isinstance(obj, PersonGroup):
            return (
                PersonGroupPermission.objects.filter(
                    group__in=PersonGroup.hierarchy_subquery([obj], ancestors=True),
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

        if isinstance(obj, PersonGroup):
            owner_ids.update(
                PersonGroupPermission.objects.filter(
                    group__in=PersonGroup.hierarchy_subquery([obj], ancestors=True),
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
        ancestors = PersonGroup.hierarchy_subquery([group], ancestors=True)
        level = (
            PersonGroupPermission.objects.filter(user=user)
            .filter(Q(group=group) | Q(group__in=ancestors, inherit_permissions=True))
            .aggregate(level=Max("permission_type"))["level"]
        )
        return PermissionLevel.NONE if level is None else level

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


@dataclass(frozen=True)
class BudgetSummary:
    """Totals of the priced gift plans of a person or an event.

    ``planned`` covers every plan that is not abandoned, ``spent`` only the plans already
    purchased or given, and ``without_price`` counts the non-abandoned plans with no price.
    """

    planned: Decimal
    spent: Decimal
    without_price: int

    @property
    def has_data(self) -> bool:
        """Return whether there is anything to show (a price or an unpriced plan)."""
        return bool(self.planned or self.spent or self.without_price)


def _status_is(*names: str) -> Q:
    """Match plans whose status is one of *names* (canonical English status names)."""
    return Q(status__status_en__in=names) | (
        Q(status__status_en__isnull=True) & Q(status__status__in=names)
    )


class BudgetService:
    """Budget totals computed from the plans a user can access."""

    ABANDONED = _status_is("Abandoned")
    SPENT = _status_is("Purchased", "Given")

    @classmethod
    def for_person(cls, user, person) -> BudgetSummary:
        """Return the budget of the plans addressed to *person* (group plans excluded)."""
        return cls._summarize(Relation.objects.accessible_by(user).filter(person=person))

    @classmethod
    def for_event(cls, user, event) -> BudgetSummary:
        """Return the budget of the plans attached to *event*."""
        return cls._summarize(Relation.objects.accessible_by(user).filter(event=event))

    @classmethod
    def _summarize(cls, relations) -> BudgetSummary:
        price = Coalesce("price", "gift__price")
        open_plans = ~cls.ABANDONED
        totals = relations.annotate(effective_price_db=price).aggregate(
            planned=Sum("effective_price_db", filter=open_plans),
            spent=Sum("effective_price_db", filter=cls.SPENT),
            without_price=Count(
                "pk", filter=open_plans & Q(effective_price_db__isnull=True), distinct=True
            ),
        )
        return BudgetSummary(
            planned=totals["planned"] or Decimal(0),
            spent=totals["spent"] or Decimal(0),
            without_price=totals["without_price"],
        )
