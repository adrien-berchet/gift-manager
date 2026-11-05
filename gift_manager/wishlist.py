"""Business rules for wishes: listing, claiming, planning and plan synchronisation.

Privacy boundary: the wisher never learns whether a wish is claimed or planned. Every function
that a wisher could reach therefore denies them *before* it looks at the claim state, so the
outcome is identical whatever that state is.
"""

from collections.abc import Iterable

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
from django.utils.translation import gettext as _

from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import Relation
from gift_manager.models import RelationPermission
from gift_manager.models import Wish
from gift_manager.services import PermissionService
from gift_manager.statuses import is_abandoned_status
from gift_manager.statuses import is_given_status

CLAIM_FIELDS = ["claimed_by", "claimed_at"]


def _lock(wish: Wish) -> Wish:
    """Return the wish re-read from the database under a row lock (needs ``atomic``)."""
    return Wish.objects.select_for_update().get(pk=wish.pk)


def _owner_ids(relation: Relation) -> set[int]:
    """Return the plan's owners, using the snapshot taken before it was deleted if any."""
    stashed = getattr(relation, "_wish_owner_ids", None)
    if stashed is not None:
        return set(stashed)
    return set(
        RelationPermission.objects.filter(
            relation_id=relation.pk, permission_type=PermissionLevel.OWNER
        ).values_list("user_id", flat=True)
    )


def _active_plans_owned_by(wish: Wish, user: User) -> list[Relation]:
    """Return the non-abandoned plans fulfilling *wish* that *user* owns."""
    permissions = RelationPermission.objects.filter(
        user=user,
        permission_type=PermissionLevel.OWNER,
        relation__wish=wish,
    ).select_related("relation__status")
    return [p.relation for p in permissions if not is_abandoned_status(p.relation.status)]


def _release(wish: Wish) -> None:
    wish.claimed_by = None
    wish.claimed_at = None


def purge_if_orphaned(wish: Wish) -> bool:
    """Permanently delete a wish soft-deleted by the wisher once no claim or active plan remains."""
    if not wish.is_deleted_by_wisher:
        return False
    if wish.claimed_by_id is not None:
        return False
    active = [
        plan
        for plan in wish.fulfilling_plans.select_related("status")
        if not is_abandoned_status(plan.status)
    ]
    if not active:
        wish.delete()
        return True
    return False


def get_active_plan_for_wish(wish: Wish, friend: User, person: Person) -> Relation | None:
    """Return an active plan owned by *friend* fulfilling *wish* for *person*, or None."""
    for relation in _active_plans_owned_by(wish, friend):
        if relation.person_id == person.pk:
            return relation
    return None


def get_wisher_wishes(wisher: User, *, include_archived: bool = False) -> QuerySet[Wish]:
    """Return the wisher's own wishes, hiding archived ones unless asked."""
    wishes = Wish.objects.for_wisher(wisher)
    if not include_archived:
        wishes = wishes.filter(is_archived=False)
    return wishes


def get_friend_visible_wishes(wisher: User, friend: User) -> QuerySet[Wish]:
    """Return the wishes of *wisher* that their confirmed *friend* may see."""
    if not PermissionService.users_are_friends(friend, wisher):
        raise PermissionDenied(_("You can only view wishlists of confirmed friends."))
    return Wish.objects.visible_to_friend(friend, wisher)


def claim_wish(wish: Wish, friend: User) -> Wish:
    """Reserve *wish* for *friend*; use the returned instance, it holds the fresh state."""
    with transaction.atomic():
        wish = _lock(wish)
        if friend.pk == wish.wisher_id:
            raise PermissionDenied(_("You cannot claim your own wish."))
        if not PermissionService.users_are_friends(friend, wish.wisher):
            raise PermissionDenied(_("Only confirmed friends can claim wishes."))
        if wish.claimed_by_id == friend.pk:
            return wish
        if wish.is_archived or wish.is_fulfilled:
            raise ValidationError(_("Cannot claim an archived or fulfilled wish."))
        if wish.claimed_by_id is not None:
            raise ValidationError(_("This wish has already been claimed by another friend."))
        wish.claimed_by = friend
        wish.claimed_at = timezone.now()
        wish.save(update_fields=CLAIM_FIELDS)
        return wish


def release_wish_claim(wish: Wish, actor: User) -> Wish:
    """Drop the claim on *wish*; only its claimer (or a superuser) may, and never the wisher."""
    with transaction.atomic():
        wish = _lock(wish)
        if actor.pk == wish.wisher_id:
            raise PermissionDenied(_("You cannot release claims on your own wish."))
        if not (actor.is_superuser or PermissionService.users_are_friends(actor, wish.wisher)):
            raise PermissionDenied(_("Only confirmed friends can release claims."))
        if wish.claimed_by_id is None:
            return wish
        if actor.pk != wish.claimed_by_id and not actor.is_superuser:
            raise PermissionDenied(_("Only the user who claimed this wish can release the claim."))
        if _active_plans_owned_by(wish, wish.claimed_by):
            raise ValidationError(
                _("Abandon or delete the gift plan for this wish before releasing the claim.")
            )
        _release(wish)
        wish.save(update_fields=CLAIM_FIELDS)
        purge_if_orphaned(wish)
        return wish


def plan_wish(wish: Wish, friend: User, person: Person, event: Event | None = None) -> Relation:
    """Claim *wish* for *friend* and create the private surprise plan that fulfils it.

    Calling it again for the same friend and person returns the existing plan.
    """
    if friend.pk == wish.wisher_id:
        raise PermissionDenied(_("You cannot claim your own wish."))
    if not PermissionService.users_are_friends(friend, wish.wisher):
        raise PermissionDenied(_("Only confirmed friends can claim wishes."))
    if wish.is_archived or wish.is_fulfilled:
        raise ValidationError(_("Cannot claim an archived or fulfilled wish."))
    if person.account_id != wish.wisher_id:
        raise ValidationError(_("The recipient person must represent the wisher of this wish."))
    if PermissionService.get_effective_permission(person, friend) < PermissionLevel.EDITOR:
        raise PermissionDenied(_("You need edit rights on this person to plan a gift for them."))
    if (
        event is not None
        and PermissionService.get_effective_permission(event, friend) < PermissionLevel.VIEWER
    ):
        raise PermissionDenied(_("You do not have access to this event."))

    with transaction.atomic():
        wish = _lock(wish)
        existing = get_active_plan_for_wish(wish, friend, person)
        if existing:
            return existing

        claim_wish(wish, friend)
        gift = Gift.objects.create(name=wish.title, url=wish.url, comment=wish.notes)
        PermissionService.create_or_update_permission(
            friend, gift, permission_level=PermissionLevel.OWNER
        )
        relation = Relation(person=person, gift=gift, event=event, wish=wish, is_surprise=True)
        relation.full_clean()
        relation.save()
        PermissionService.create_or_update_permission(
            friend, relation, permission_level=PermissionLevel.OWNER, object_attr="relation"
        )
        return relation


def sync_wish_on_plan_change(relation: Relation, *, is_deleted: bool = False) -> None:
    """Re-derive a wish's fulfilled flag and claim from the plans that fulfil it."""
    if relation.wish_id is None:
        return
    with transaction.atomic():
        wish = Wish.objects.select_for_update().filter(pk=relation.wish_id).first()
        if wish is None:
            return

        plans = Relation.objects.filter(wish=wish).select_related("status")
        if is_deleted:
            plans = plans.exclude(pk=relation.pk)
        active = [plan for plan in plans if not is_abandoned_status(plan.status)]
        has_given = any(is_given_status(plan.status) for plan in active)

        update_fields = []
        if wish.is_fulfilled != has_given:
            wish.is_fulfilled = has_given
            update_fields.append("is_fulfilled")

        if not active:
            # A claim can exist without any plan, so only the claimer's own plan releases it.
            if wish.claimed_by_id is not None and wish.claimed_by_id in _owner_ids(relation):
                _release(wish)
                update_fields += CLAIM_FIELDS
        elif wish.claimed_by_id is None and not is_deleted:
            # The plan came back to life: hand the wish back to its first owner if still a friend.
            owner_id = _first_owner_id(relation)
            if owner_id is not None and _is_friend_of_wisher(owner_id, wish):
                wish.claimed_by_id = owner_id
                wish.claimed_at = timezone.now()
                update_fields += CLAIM_FIELDS

        if update_fields:
            wish.save(update_fields=update_fields)

        if purge_if_orphaned(wish):
            relation.wish_id = None


def _first_owner_id(relation: Relation) -> int | None:
    return (
        RelationPermission.objects.filter(
            relation_id=relation.pk, permission_type=PermissionLevel.OWNER
        )
        .order_by("pk")
        .values_list("user_id", flat=True)
        .first()
    )


def _is_friend_of_wisher(user_id: int, wish: Wish) -> bool:
    owner = User.objects.filter(pk=user_id, is_active=True).first()
    return owner is not None and PermissionService.users_are_friends(owner, wish.wisher)


def release_claims_after_unfriending(user: User, former_friend: User) -> None:
    """Unlink plans and drop claims each ex-friend held on the other's wishes."""
    with transaction.atomic():
        affected_wishes = []
        for wisher, giver in ((user, former_friend), (former_friend, user)):
            Relation.objects.filter(
                wish__wisher=wisher,
                relationpermission__user=giver,
                relationpermission__permission_type=PermissionLevel.OWNER,
            ).update(wish=None)
            claims = list(Wish.objects.filter(wisher=wisher, claimed_by=giver))
            Wish.objects.filter(wisher=wisher, claimed_by=giver).update(
                claimed_by=None, claimed_at=None
            )
            affected_wishes.extend(claims)
        for w in affected_wishes:
            w.refresh_from_db()
            purge_if_orphaned(w)


def detach_plans(plans: Iterable[Relation]) -> None:
    """Unlink plans from their wishes, dropping orphaned claims but keeping is_fulfilled."""
    plans_list = list(plans)
    if not plans_list:
        return

    plan_data = []
    for p in plans_list:
        if p.wish_id is not None:
            owner_ids = set(
                RelationPermission.objects.filter(
                    relation=p, permission_type=PermissionLevel.OWNER
                ).values_list("user_id", flat=True)
            )
            plan_data.append((p.pk, p.wish_id, owner_ids))

    if not plan_data:
        return

    Relation.objects.filter(pk__in=[pd[0] for pd in plan_data]).update(wish=None)

    wish_ids = {pd[1] for pd in plan_data}
    for w_id in wish_ids:
        with transaction.atomic():
            wish = Wish.objects.select_for_update().filter(pk=w_id).first()
            if wish is None:
                continue
            claimer_id = wish.claimed_by_id
            if claimer_id is not None:
                all_detached_owners = set()
                for _rel_pk, wish_pk, owners in plan_data:
                    if wish_pk == w_id:
                        all_detached_owners.update(owners)
                if claimer_id in all_detached_owners:
                    remaining_active = _active_plans_owned_by(wish, wish.claimed_by)
                    if not remaining_active:
                        wish.claimed_by = None
                        wish.claimed_at = None
                        wish.save(update_fields=CLAIM_FIELDS)
            purge_if_orphaned(wish)


def format_claimer_label(
    wish: Wish, viewer: User, viewer_friend_ids: set[int] | None = None
) -> str:
    """Return the claim pill text *viewer* may see; the wisher always gets an empty string.

    ``viewer_friend_ids`` holds User ids and spares one friendship query per wish.
    """
    if viewer.pk == wish.wisher_id:
        return ""
    if viewer_friend_ids is not None:
        is_wisher_friend = wish.wisher_id in viewer_friend_ids
    else:
        is_wisher_friend = PermissionService.users_are_friends(viewer, wish.wisher)
    if not (viewer.is_superuser or is_wisher_friend):
        return ""
    if wish.claimed_by_id is None:
        return _("Already given") if wish.is_fulfilled else _("Available")
    if viewer.pk == wish.claimed_by_id:
        return _("Claimed by you")
    if viewer_friend_ids is not None:
        knows_claimer = wish.claimed_by_id in viewer_friend_ids
    else:
        knows_claimer = PermissionService.users_are_friends(viewer, wish.claimed_by)
    if knows_claimer:
        return _("Claimed by @%(username)s") % {"username": wish.claimed_by.username}
    return _("Claimed by a friend")


def delete_wish(wish: Wish, actor: User) -> None:
    """Delete *wish*, or soft-delete it when a claim or active plan still depends on it."""
    if actor.pk != wish.wisher_id and not actor.is_superuser:
        raise PermissionDenied(_("Only the wisher can delete this wish."))
    with transaction.atomic():
        wish = _lock(wish)
        active = [
            plan
            for plan in wish.fulfilling_plans.select_related("status")
            if not is_abandoned_status(plan.status)
        ]
        if wish.claimed_by_id is not None or active:
            wish.is_deleted_by_wisher = True
            wish.is_archived = True
            wish.save(update_fields=["is_deleted_by_wisher", "is_archived"])
        else:
            wish.delete()
