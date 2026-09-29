"""Single entry point for granting access to an object.

Sharing a gift plan (relation) grants access to the gift, the recipient and the
event it displays, so every UI path that shares an object goes through
``SharingService.grant`` and gets the same cascade and the same checks. Editing a
shared relation to point at other objects goes through
``SharingService.cascade_relation_reassignment`` for the same reason.
"""

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils.translation import gettext_lazy

from gift_manager.models import PermissionLevel
from gift_manager.models import PersonGroup
from gift_manager.models import Relation
from gift_manager.services import PermissionService

INSUFFICIENT_SHARE_PERMISSION_ERROR = "You do not have permission to share this object."
PERMISSION_ESCALATION_ERROR = "You cannot grant a higher permission than your own."

RELATION_EXPOSURE_ERROR = gettext_lazy(
    "This gift plan is shared with people who cannot see this choice, "
    "and you are not allowed to share it with them."
)

# Relation attributes whose objects are displayed with the relation
RELATION_CASCADE_ATTRIBUTES = ("gift", "person", "group", "event")


class RelationExposureDenied(PermissionDenied):
    """A relation edit would show an object to users the actor cannot share it with."""

    def __init__(self, attribute: str):
        super().__init__(RELATION_EXPOSURE_ERROR)
        self.attribute = attribute
        self.message = RELATION_EXPOSURE_ERROR


class SharingService:
    """Grant permissions on an object and on what it exposes."""

    @staticmethod
    def related_objects(obj) -> list:
        """Return the objects that must be shared along with obj."""
        if not isinstance(obj, Relation):
            return []
        related = (getattr(obj, name) for name in RELATION_CASCADE_ATTRIBUTES)
        return [item for item in related if item is not None]

    @staticmethod
    def relation_related_ids(relation) -> dict[str, int | None]:
        """Snapshot the related object ids of a relation, to detect later changes."""
        return {name: getattr(relation, f"{name}_id") for name in RELATION_CASCADE_ATTRIBUTES}

    @staticmethod
    def assert_can_share(actor, obj, permission_level: int) -> None:
        """Require owner-level authority on obj and forbid granting more than the actor holds."""
        actor_permission = PermissionService.get_effective_permission(obj, actor)
        if actor_permission < PermissionLevel.OWNER:
            raise PermissionDenied(INSUFFICIENT_SHARE_PERMISSION_ERROR)
        if permission_level > actor_permission:
            raise PermissionDenied(PERMISSION_ESCALATION_ERROR)

    @classmethod
    def grant(cls, actor, obj, user, permission_level: int) -> None:
        """Grant user access to obj and, for relations, to the related objects.

        Callers validate the authority on ``obj`` itself (it may not be saved with
        an owner yet when a create form shares it). Related objects are checked here,
        but only where the grant would raise the user's access: existing equal or
        higher access is neither required to be shareable nor downgraded.
        All or nothing.
        """
        permission_level = PermissionService.validate_permission_level(permission_level)
        with transaction.atomic():
            expanded = [
                related
                for related in cls.related_objects(obj)
                if PermissionService.get_effective_permission(related, user) < permission_level
            ]
            for related in expanded:
                cls.assert_can_share(actor, related, permission_level)

            PermissionService.create_or_update_permission(
                user, obj, permission_level=permission_level
            )
            for related in expanded:
                PermissionService.create_or_update_permission(
                    user,
                    related,
                    permission_level=permission_level,
                    object_attr="group" if isinstance(related, PersonGroup) else None,
                )

    @classmethod
    def relation_reassignment_grants(cls, actor, relation, previous_ids: dict) -> list[tuple]:
        """Return the (user, object, level) grants a relation edit needs, without writing.

        ``previous_ids`` comes from ``relation_related_ids`` taken before the edit. Every
        other user with access to the relation would now see its new gift, recipient or
        event. Where that raises their access, the actor must be allowed to share the new
        object at the user's relation level (the rule of ``grant``); otherwise
        RelationExposureDenied names the offending attribute. Existing equal or higher
        access needs nothing and is never downgraded.
        """
        changed = [
            (name, getattr(relation, name))
            for name in RELATION_CASCADE_ATTRIBUTES
            if getattr(relation, f"{name}_id") is not None
            and getattr(relation, f"{name}_id") != previous_ids.get(name)
        ]
        if not changed or relation.pk is None:
            return []

        audience = PermissionService.get_permission_map(relation)
        audience.pop(actor.id, None)
        users = User.objects.in_bulk(list(audience))
        grants = []
        for name, related in changed:
            for user_id, level in audience.items():
                user = users[user_id]
                if PermissionService.get_effective_permission(related, user) >= level:
                    continue
                try:
                    cls.assert_can_share(actor, related, level)
                except PermissionDenied as exc:
                    raise RelationExposureDenied(name) from exc
                grants.append((user, related, level))
        return grants

    @classmethod
    def cascade_relation_reassignment(cls, actor, relation, previous_ids: dict) -> None:
        """Check a relation edit and cascade its new related objects to the audience.

        All or nothing: nothing is granted when any change is refused. Run it in the
        transaction that saves the relation so a refusal also discards the edit.
        """
        with transaction.atomic():
            if relation.pk is not None:
                # Read the audience after any concurrent sharing change on the relation
                PermissionService.lock_object(relation)
            for user, related, level in cls.relation_reassignment_grants(
                actor, relation, previous_ids
            ):
                PermissionService.create_or_update_permission(
                    user,
                    related,
                    permission_level=level,
                    object_attr="group" if isinstance(related, PersonGroup) else None,
                )
