"""Service functions for managing person-account links."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Exists
from django.db.models import OuterRef
from django.db.models import Q
from django.db.models import QuerySet
from django.utils.translation import gettext as _

from gift_manager.invitations import accounts_owning_email
from gift_manager.invitations import normalize_email
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import PersonPermission
from gift_manager.models import Profile
from gift_manager.models import Relation
from gift_manager.services import PermissionService

if TYPE_CHECKING:
    from django.contrib.auth.models import User


class LinkRefused(ValidationError):  # noqa: N818
    """Raised when a person-account link operation is rejected by business rules."""


def _owner_ids(person: Person) -> set[int]:
    """Return the set of user IDs who currently hold an OWNER permission on ``person``."""
    return set(
        PersonPermission.objects.filter(
            person=person,
            permission_type=PermissionLevel.OWNER,
        ).values_list("user_id", flat=True)
    )


def owned_persons(user: User) -> QuerySet[Person]:
    """Return person records where ``user`` holds an OWNER permission row."""
    return Person.objects.filter(
        personpermission__user=user,
        personpermission__permission_type=PermissionLevel.OWNER,
    ).distinct()


def duplicate_conflicts(
    person: Person, account: User, owner_ids: set[int] | None = None
) -> list[Person]:
    """Return other person records linked to ``account`` owned by any owner of ``person``."""
    if owner_ids is None:
        owner_ids = _owner_ids(person)
    if not owner_ids:
        return []
    return list(
        Person.objects.filter(
            account=account,
            personpermission__user_id__in=owner_ids,
            personpermission__permission_type=PermissionLevel.OWNER,
        )
        .exclude(pk=person.pk)
        .distinct()
    )


def link(person: Person, account: User, actor: User) -> Person:
    """Link a person record to an account.

    Requires ``actor`` to be an OWNER if linking to their own account, or at least
    EDITOR and friends with ``account`` if linking to someone else. At least one
    owner of ``person`` must also be friends with ``account``.
    """
    with transaction.atomic():
        PermissionService.lock_object(person)
        person.refresh_from_db(fields=["account", "link_suggestion_dismissed_account"])

        actor_perm = PermissionService.get_effective_permission(person, actor)
        if actor_perm < PermissionLevel.EDITOR:
            raise PermissionDenied(_("You do not have permission to edit this person."))

        if person.account_id == account.id:
            return person

        if account == actor:
            if actor_perm != PermissionLevel.OWNER:
                raise LinkRefused(
                    _("Only an owner of this person can mark it as you."),
                    code="self_needs_owner",
                )
        else:
            if not PermissionService.users_are_friends(actor, account):
                raise LinkRefused(
                    _("You can only link a person to one of your friends."),
                    code="not_friend",
                )

            owner_ids = _owner_ids(person)
            has_friend_owner = Profile.objects.filter(
                user_id__in=owner_ids, friends__user=account
            ).exists()
            if not has_friend_owner:
                raise LinkRefused(
                    _("Nobody who owns this person is friends with this account."),
                    code="no_friend_owner",
                )

        conflicts = duplicate_conflicts(person, account)
        if conflicts:
            raise LinkRefused(
                _("One of this person's owners already has a person linked to this account."),
                code="duplicate",
            )

        person.account = account
        person.link_suggestion_dismissed_account = None
        person.save(update_fields=["account", "link_suggestion_dismissed_account"])

        # Release claims account holds on surprise plans that are now hidden from them
        Relation.objects.hidden_surprises_for(account).filter(claimed_by=account).update(
            claimed_by=None, claimed_at=None
        )

        return person


def unlink(person: Person, actor: User) -> None:
    """Remove the account link from a person record."""
    with transaction.atomic():
        PermissionService.lock_object(person)
        person.refresh_from_db(fields=["account"])

        actor_perm = PermissionService.get_effective_permission(person, actor)
        if actor_perm < PermissionLevel.EDITOR:
            raise PermissionDenied(_("You do not have permission to edit this person."))

        if person.account_id is None:
            return

        person.account = None
        person.save(update_fields=["account"])


def revealed_surprise_count(person: Person) -> int:
    """Return number of surprise plans shared with ``person.account`` revealed if unlinked."""
    account = person.account
    if account is None:
        return 0

    return (
        Relation.objects.filter(shared_with=account)
        .hidden_surprises_for(account)
        .exclude(
            pk__in=Relation.objects.hidden_surprises_for(account, excluding_person=person).values(
                "pk"
            )
        )
        .count()
    )


def remove_links_after_unfriending(user: User, former_friend: User) -> int:
    """Unlink records between former friends when no remaining owner is friends with the account."""
    owner = PermissionLevel.OWNER
    self_owned = PersonPermission.objects.filter(
        person=OuterRef("pk"),
        user=OuterRef("account"),
        permission_type=owner,
    )
    friend_owner = PersonPermission.objects.filter(
        person=OuterRef("pk"),
        permission_type=owner,
        user__profile__friends__user=OuterRef("account"),
    )
    affected = (
        Person.objects.filter(
            Q(
                account=user,
                personpermission__user=former_friend,
                personpermission__permission_type=owner,
            )
            | Q(
                account=former_friend,
                personpermission__user=user,
                personpermission__permission_type=owner,
            )
        )
        .exclude(Exists(self_owned))
        .exclude(Exists(friend_owner))
    )

    pks = list(affected.values_list("pk", flat=True).distinct())
    if not pks:
        return 0
    return Person.objects.filter(pk__in=pks).update(account=None)


@dataclass(frozen=True)
class LinkChoice:
    """A choice displayed in the person-account link form."""

    value: str
    label: str
    account: User | None
    disabled: bool
    conflicts: tuple[Person, ...]


def link_label(person: Person, viewer: User) -> str:
    """Return a short human-readable label describing who this person is linked to."""
    if person.account_id is None:
        return ""
    if person.account_id == viewer.pk:
        return _("This is you")
    username = person.account.username if person.account else ""
    return _("Linked to %(username)s") % {"username": username}


def _candidate_conflicts(
    candidate_ids: set[int],
    owner_ids: set[int],
    person_pk: int,
    actor: User,
) -> tuple[dict[int, list[Person]], dict[int, list[Person]]]:
    all_conflicts: dict[int, list[Person]] = {}
    accessible_conflicts: dict[int, list[Person]] = {}
    if not (owner_ids and candidate_ids):
        return all_conflicts, accessible_conflicts

    conflicts_qs = (
        Person.objects.filter(
            account_id__in=candidate_ids,
            personpermission__user_id__in=owner_ids,
            personpermission__permission_type=PermissionLevel.OWNER,
        )
        .exclude(pk=person_pk)
        .distinct()
    )
    accessible_pks = set(
        Person.objects.accessible_by(actor)
        .filter(pk__in=conflicts_qs.values("pk"))
        .values_list("pk", flat=True)
    )
    for cp in conflicts_qs:
        all_conflicts.setdefault(cp.account_id, []).append(cp)
        if cp.pk in accessible_pks:
            accessible_conflicts.setdefault(cp.account_id, []).append(cp)
    return all_conflicts, accessible_conflicts


def _make_choice(
    account: User,
    label: str,
    person: Person,
    all_conflicts: dict[int, list[Person]],
    accessible_conflicts: dict[int, list[Person]],
) -> LinkChoice:
    if person.account_id == account.pk:
        disabled = False
        conflicts = ()
    else:
        disabled = bool(all_conflicts.get(account.pk))
        conflicts = tuple(accessible_conflicts.get(account.pk, []))
    return LinkChoice(
        value=str(account.pk),
        label=label,
        account=account,
        disabled=disabled,
        conflicts=conflicts,
    )


def _friend_candidates(actor: User, owner_ids: set[int]) -> list[User]:
    """Return friends of ``actor`` who are also friends with at least one owner of the person."""
    if not (hasattr(actor, "profile") and owner_ids):
        return []
    friends_qs = actor.profile.friends.filter(
        user__in=Profile.objects.filter(user_id__in=owner_ids).values("friends__user")
    ).select_related("user")
    seen_ids: set[int] = set()
    candidates: list[User] = []
    for friend_profile in friends_qs:
        if friend_profile.user_id not in seen_ids:
            seen_ids.add(friend_profile.user_id)
            candidates.append(friend_profile.user)
    return candidates


def link_choices(person: Person, actor: User) -> list[LinkChoice]:
    """Return the ordered list of account choices for linking this person record."""
    owner_ids = _owner_ids(person)
    is_owner = actor.pk in owner_ids

    choices: list[LinkChoice] = [
        LinkChoice(
            value="",
            label=_("No one"),
            account=None,
            disabled=False,
            conflicts=(),
        )
    ]

    friends_dict = {u.pk: u for u in _friend_candidates(actor, owner_ids)}

    # If currently linked to someone not actor and not in friends_dict:
    if person.account_id and person.account_id != actor.pk and person.account:
        friends_dict.setdefault(person.account_id, person.account)

    friends = sorted(friends_dict.values(), key=lambda u: u.username.lower())

    candidate_accounts: list[User] = []
    if is_owner or person.account_id == actor.pk:
        candidate_accounts.append(actor)
    candidate_accounts.extend(friends)

    candidate_ids = {u.id for u in candidate_accounts}

    all_conflicts, accessible_conflicts = _candidate_conflicts(
        candidate_ids, owner_ids, person.pk, actor
    )

    if is_owner or person.account_id == actor.pk:
        choices.append(_make_choice(actor, _("Me"), person, all_conflicts, accessible_conflicts))

    choices.extend(
        _make_choice(friend, friend.username, person, all_conflicts, accessible_conflicts)
        for friend in friends
    )

    return choices


def _clean_person_email(person: Person) -> str | None:
    raw_email = person.email
    if not raw_email:
        return None
    try:
        clean = normalize_email(raw_email)
    except ValidationError:
        return None
    return clean or None


def _suggest_self_or_none(
    person: Person, viewer: User, viewer_perm: int, clean_email: str, owner_ids: set[int]
) -> tuple[bool, User | None]:
    if not accounts_owning_email([viewer], clean_email):
        return False, None
    if (
        viewer_perm == PermissionLevel.OWNER
        and person.link_suggestion_dismissed_account_id != viewer.pk
        and not duplicate_conflicts(person, viewer, owner_ids=owner_ids)
    ):
        return True, viewer
    return True, None


def _suggest_friend(
    person: Person, viewer: User, clean_email: str, owner_ids: set[int]
) -> User | None:
    candidates = _friend_candidates(viewer, owner_ids)
    matching_friends = accounts_owning_email(candidates, clean_email)
    matching_friends.sort(key=lambda u: (u.username.lower(), u.pk))
    for friend in matching_friends:
        if person.link_suggestion_dismissed_account_id != friend.pk and not duplicate_conflicts(
            person, friend, owner_ids=owner_ids
        ):
            return friend
    return None


def link_suggestion(person: Person, viewer: User) -> User | None:
    """Return a suggested account to link to this person, or None.

    Matches an unlinked record's email to the viewer (self-link) or to a friend
    of the viewer who is also friends with an owner of the record.
    """
    if person.account_id is not None:
        return None

    clean_email = _clean_person_email(person)
    if not clean_email:
        return None

    viewer_perm = PermissionService.get_effective_permission(person, viewer)
    if viewer_perm < PermissionLevel.EDITOR:
        return None

    owner_ids = _owner_ids(person)

    is_viewer_match, self_user = _suggest_self_or_none(
        person, viewer, viewer_perm, clean_email, owner_ids
    )
    if is_viewer_match:
        return self_user

    return _suggest_friend(person, viewer, clean_email, owner_ids)


def dismiss_link_suggestion(person: Person, account: User, actor: User) -> None:
    """Dismiss the link suggestion of ``account`` on ``person``."""
    with transaction.atomic():
        PermissionService.lock_object(person)
        person.refresh_from_db(fields=["account", "link_suggestion_dismissed_account"])

        actor_perm = PermissionService.get_effective_permission(person, actor)
        if actor_perm < PermissionLevel.EDITOR:
            raise PermissionDenied(_("You do not have permission to edit this person."))

        if person.account_id is not None:
            return

        person.link_suggestion_dismissed_account = account
        person.save(update_fields=["link_suggestion_dismissed_account"])
