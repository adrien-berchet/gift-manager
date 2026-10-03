from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count
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
        """Get permission including ownership implied by user_link."""
        if user.is_superuser:
            return PermissionLevel.OWNER

        if isinstance(obj, PersonGroup):
            return cls.get_effective_permission_for_group(obj, user)

        permission = cls.get_permission(obj, user)
        if getattr(obj, "user_link_id", None) == user.id:
            return max(permission, PermissionLevel.OWNER)
        if getattr(obj, "is_global", False):
            # Global objects (e.g. the Birthday event) are read-only for everyone
            return max(permission, PermissionLevel.VIEWER)
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

        if getattr(obj, "is_global", False):
            # Access comes from the object being global, there is no permission to remove
            raise PermissionDenied(GLOBAL_OBJECT_REMOVAL_ERROR)

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
