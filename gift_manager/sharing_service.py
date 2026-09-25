"""Single entry point for granting access to an object.

Sharing a gift plan (relation) grants access to the gift, the recipient and the
event it displays, so every UI path that shares an object goes through
``SharingService.grant`` and gets the same cascade and the same checks.
"""

from django.core.exceptions import PermissionDenied
from django.db import transaction

from gift_manager.models import PermissionLevel
from gift_manager.models import PersonGroup
from gift_manager.models import Relation
from gift_manager.services import PermissionService

INSUFFICIENT_SHARE_PERMISSION_ERROR = "You do not have permission to share this object."
PERMISSION_ESCALATION_ERROR = "You cannot grant a higher permission than your own."

# Relation attributes whose objects are displayed with the relation
RELATION_CASCADE_ATTRIBUTES = ("gift", "person", "group", "event")


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
