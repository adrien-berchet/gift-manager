"""Filter related tag and group metadata down to what a user may see.

A user can legitimately access a gift or a person without having access to every
tag or group attached to it. Anything that renders or serializes those related
objects must go through this module so private names and identifiers never leak.
"""

from gift_manager.models import GiftTag
from gift_manager.models import PersonGroup


class VisibleMetadata:
    """Tags and groups visible to one user, resolved with one query each.

    Instances are cached on the user object, which lives for a single request.
    """

    def __init__(self, user):
        self.user = user
        self._tag_ids = None
        self._group_ids = None

    @classmethod
    def for_user(cls, user) -> "VisibleMetadata":
        """Return the per-request instance for user."""
        cached = getattr(user, "_visible_metadata", None)
        if cached is None:
            cached = cls(user)
            user._visible_metadata = cached  # noqa: SLF001
        return cached

    @property
    def _is_authenticated(self) -> bool:
        return bool(self.user and self.user.is_authenticated)

    @property
    def tag_ids(self) -> set[int]:
        if self._tag_ids is None:
            self._tag_ids = (
                set(GiftTag.objects.accessible_by(self.user).values_list("pk", flat=True))
                if self._is_authenticated
                else set()
            )
        return self._tag_ids

    @property
    def group_ids(self) -> set[int]:
        if self._group_ids is None:
            self._group_ids = (
                set(PersonGroup.objects.accessible_by(self.user).values_list("pk", flat=True))
                if self._is_authenticated
                else set()
            )
        return self._group_ids

    def tags(self, gift) -> list[GiftTag]:
        """Return the tags of gift the user can see."""
        return [tag for tag in gift.tags.all() if tag.pk in self.tag_ids]

    def groups(self, person) -> list[PersonGroup]:
        """Return the groups of person the user can see."""
        return [group for group in person.groups.all() if group.pk in self.group_ids]
