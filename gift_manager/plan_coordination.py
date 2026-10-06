"""Coordination between the collaborators of a gift plan: claim, comments and surprise flag.

Every rule lives here so views stay thin. Access is decided by
``PermissionService.get_effective_permission``; on top of it, a surprise plan addressed to the
acting user is treated as inaccessible, the same way ``Relation.objects.accessible_by`` hides it.
"""

from collections.abc import Iterable

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy
from django.utils.translation import ngettext

from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import Relation
from gift_manager.models import RelationComment
from gift_manager.services import PermissionService

MAX_COMMENT_LENGTH = 2000

COMMENT_BLANK_ERROR = gettext_lazy("Write a comment before sending it.")
COMMENT_TOO_LONG_ERROR = gettext_lazy("A comment can have at most %(limit)d characters.")


class AlreadyClaimed(Exception):  # noqa: N818
    """The gift plan is already claimed by another collaborator."""

    def __init__(self, claimed_by: User | None):
        super().__init__(gettext("This gift plan is already claimed."))
        self.claimed_by = claimed_by


def _require_level(relation: Relation, user: User, minimum: int) -> int:
    """Return the user's permission level on the plan, or raise ``PermissionDenied``.

    A surprise plan addressed to the user counts as inaccessible whatever their level.
    """
    level = PermissionService.get_effective_permission(relation, user)
    if level < minimum:
        raise PermissionDenied(gettext("You do not have permission to do this on this gift plan."))
    if Relation.objects.hidden_surprises_for(user).filter(pk=relation.pk).exists():
        raise PermissionDenied(gettext("You do not have permission to do this on this gift plan."))
    return level


def claim(relation: Relation, user: User) -> Relation:
    """Claim the plan for ``user``: they are the one buying the gift.

    Claiming a plan you already hold changes nothing; a plan held by someone else raises
    ``AlreadyClaimed``. The row lock makes the second of two concurrent claims see the first.
    """
    _require_level(relation, user, PermissionLevel.VIEWER)
    with transaction.atomic():
        PermissionService.lock_object(relation)
        current = Relation.objects.select_related("claimed_by").get(pk=relation.pk)
        if current.claimed_by_id is not None and current.claimed_by_id != user.pk:
            raise AlreadyClaimed(current.claimed_by)
        if current.claimed_by_id is None:
            Relation.objects.filter(pk=relation.pk).update(
                claimed_by=user, claimed_at=timezone.now()
            )
    relation.refresh_from_db(fields=["claimed_by", "claimed_at"])
    return relation


def release(relation: Relation, user: User) -> None:
    """Release the claim: allowed to the claimer and to the owners of the plan."""
    level = _require_level(relation, user, PermissionLevel.VIEWER)
    with transaction.atomic():
        PermissionService.lock_object(relation)
        claimed_by_id = (
            Relation.objects.filter(pk=relation.pk).values_list("claimed_by_id", flat=True).get()
        )
        if claimed_by_id is None:
            return
        if claimed_by_id != user.pk and level < PermissionLevel.OWNER:
            raise PermissionDenied(gettext("Only the person who claimed this gift can release it."))
        Relation.objects.filter(pk=relation.pk).update(claimed_by=None, claimed_at=None)
    relation.refresh_from_db(fields=["claimed_by", "claimed_at"])


def add_comment(relation: Relation, user: User, text: str) -> RelationComment:
    """Add a comment from ``user``; the text is stripped, non-blank and length-limited."""
    _require_level(relation, user, PermissionLevel.VIEWER)
    text = (text or "").strip()
    if not text:
        raise ValidationError(COMMENT_BLANK_ERROR)
    if len(text) > MAX_COMMENT_LENGTH:
        raise ValidationError(COMMENT_TOO_LONG_ERROR, params={"limit": MAX_COMMENT_LENGTH})
    return RelationComment.objects.create(relation=relation, author=user, text=text)


def delete_comment(comment: RelationComment, user: User) -> None:
    """Delete a comment: allowed to its author and to the owners of the plan."""
    level = _require_level(comment.relation, user, PermissionLevel.VIEWER)
    if comment.author_id != user.pk and level < PermissionLevel.OWNER:
        raise PermissionDenied(gettext("You cannot delete this comment."))
    comment.delete()


def can_be_surprise_for_owners(
    recipient: Person | PersonGroup | None, owner_ids: Iterable[int]
) -> bool:
    """Return whether a plan for ``recipient`` can be a surprise, given the plan's owners.

    It cannot when the recipient is a person linked to one of the owners: they would be hiding
    the plan from themselves. A group recipient is always possible; its owners are never hidden.
    """
    return not (isinstance(recipient, Person) and recipient.user_link_id in set(owner_ids))


def can_be_surprise(relation: Relation) -> bool:
    """Return whether the surprise flag can be set on an existing plan."""
    owner_ids = {
        user_id
        for user_id, level in PermissionService.get_permission_map(relation).items()
        if level == PermissionLevel.OWNER
    }
    return can_be_surprise_for_owners(relation.recipient, owner_ids)


def set_surprise(relation: Relation, user: User, *, value: bool) -> None:
    """Set or clear the surprise flag; it stays off where ``can_be_surprise`` is false."""
    _require_level(relation, user, PermissionLevel.EDITOR)
    relation.is_surprise = bool(value) and can_be_surprise(relation)
    relation.save(update_fields=["is_surprise"])


def default_surprise_for(recipient: Person | PersonGroup | None, creator: User) -> bool:
    """Return the surprise flag a new plan for ``recipient`` starts with.

    On when the recipient is an app user other than the creator: a linked person, or a group
    (nested groups included) with such a member.
    """
    if isinstance(recipient, Person):
        return recipient.user_link_id is not None and recipient.user_link_id != creator.pk
    if isinstance(recipient, PersonGroup):
        return (
            recipient.get_all_members(include_nested=True)
            .filter(user_link__isnull=False)
            .exclude(user_link=creator)
            .exists()
        )
    return False


def coordination_context(relation: Relation, user: User) -> dict:
    """Return what the plan's detail page needs to show the claim and the comment thread."""
    level = PermissionService.get_effective_permission(relation, user)
    is_owner = level >= PermissionLevel.OWNER
    claimed_by = relation.claimed_by if relation.is_claimed else None
    return {
        "claimed_by": claimed_by,
        "claimed_at": relation.claimed_at if claimed_by else None,
        "can_claim": claimed_by is None,
        "can_release": claimed_by is not None and (claimed_by.pk == user.pk or is_owner),
        "can_comment": True,
        "comments": [
            {"obj": comment, "can_delete": comment.author_id == user.pk or is_owner}
            for comment in relation.comments.select_related("author")
        ],
        "can_set_surprise": level >= PermissionLevel.EDITOR and can_be_surprise(relation),
    }


def hidden_recipient_ids(relation: Relation) -> set[int]:
    """Return the users a surprise plan is hidden from, in a constant number of queries.

    These are the linked user of the recipient person, or the linked users of the members of the
    recipient group (nested groups included), except the owners of the plan. It is the same rule
    as ``Relation.objects.hidden_surprises_for``, computed from the plan's side so a list of
    people can be checked at once.
    """
    if not relation.is_surprise:
        return set()
    candidates: set[int | None] = set()
    if relation.person_id is not None:
        candidates = {relation.person.user_link_id} - {None}
    elif relation.group_id is not None:
        candidates = set(
            relation.group.get_all_members(include_nested=True)
            .filter(user_link__isnull=False)
            .values_list("user_link_id", flat=True)
        )
    if not candidates:
        return set()
    owner_ids = {
        user_id
        for user_id, level in PermissionService.get_permission_map(relation).items()
        if level == PermissionLevel.OWNER
    }
    return candidates - owner_ids


def surprise_sharing_warning(obj: object, users: Iterable[User]) -> str:
    """Return a warning when ``obj`` is a surprise plan that some of ``users`` cannot see.

    Sharing still goes through (the sharer may have a reason); the warning tells them that
    those people will not see the plan. Empty when there is nothing to warn about.
    """
    if not isinstance(obj, Relation):
        return ""
    hidden = hidden_recipient_ids(obj)
    names = sorted(user.username for user in users if user.pk in hidden)
    if not names:
        return ""
    return ngettext(
        "%(names)s will not be able to see the gift plan “%(gift)s”: it is a surprise for them.",
        "%(names)s will not be able to see the gift plan “%(gift)s”: it is a surprise for them.",
        len(names),
    ) % {"names": ", ".join(names), "gift": obj.gift.name}
