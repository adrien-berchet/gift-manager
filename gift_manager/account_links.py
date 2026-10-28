"""Service functions for managing person-account links."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Exists
from django.db.models import OuterRef
from django.db.models import Q
from django.db.models import QuerySet
from django.utils.translation import gettext as _

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


def duplicate_conflicts(person: Person, account: User) -> list[Person]:
    """Return other person records linked to ``account`` owned by any owner of ``person``."""
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
