"""Gift history of a recipient and repeat-gift detection.

Both read through ``Relation.objects.accessible_by(user)``, so a user only ever sees the
gift plans they can access.
"""

from dataclasses import dataclass

from django.db.models import Q
from django.db.models import QuerySet

from gift_manager.models import Gift
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import ReceivedGift
from gift_manager.models import Relation
from gift_manager.models import RelationPermission
from gift_manager.received_gifts import revealable_relation_pks
from gift_manager.statuses import is_abandoned_status
from gift_manager.statuses import is_given_status


@dataclass(frozen=True)
class HistoryEntry:
    """One gift plan of the history, with the name of the recipient it was planned for.

    ``group_name`` is set only when the viewer may see the group. Neither name is set for
    the recipient whose history is shown.
    """

    relation: Relation
    group_name: str | None
    person_name: str | None
    can_rate_inline: bool = False
    can_reveal: bool = False


@dataclass(frozen=True)
class HistoryYear:
    """The history entries of one year (``None`` when no date is known)."""

    year: int | None
    entries: list[HistoryEntry]


def history_year(relation: Relation) -> int | None:
    """Return the year a plan belongs to: its event, due date, last status change or creation."""
    for value in (
        relation.event.date if relation.event_id else None,
        relation.due_date,
        relation.status_changed_at,
        relation.creation_date,
    ):
        if value is not None:
            return value.year
    return None


def _base_queryset(user) -> QuerySet:
    return (
        Relation.objects.accessible_by(user)
        .select_related("status", "gift", "event", "person", "group")
        .distinct()
    )


def person_history_queryset(user, person: Person) -> QuerySet:
    """Return the plans for a person, directly or through one of their groups (ancestors too)."""
    memberships = Person.groups.through.objects.filter(person=person).values("persongroup_id")
    groups = PersonGroup.hierarchy_subquery(memberships, ancestors=True, include_start=True)
    return _base_queryset(user).filter(Q(person=person) | Q(group__in=groups))


def group_history_queryset(user, group: PersonGroup) -> QuerySet:
    """Return the plans targeted at a group, or at one of its members (nested groups included)."""
    groups = PersonGroup.hierarchy_subquery([group], include_start=True)
    return _base_queryset(user).filter(Q(group=group) | Q(person__groups__in=groups))


def build_gift_history(
    relations,
    visible_group_ids: set[int],
    *,
    person: Person | None = None,
    group: PersonGroup | None = None,
    user=None,
) -> list[HistoryYear]:
    """Group the plans that were given by year, newest year first; other plans are left out.

    ``person`` or ``group`` is the recipient whose history is shown: plans addressed to it
    directly carry no recipient name.
    """
    relations = list(relations)
    given_relations = [r for r in relations if is_given_status(r.status)]
    editable_relation_pks: set[int] = set()
    revealable_pks: set[int] = set()
    if user is not None:
        if getattr(user, "is_superuser", False):
            editable_relation_pks = {r.pk for r in relations}
        else:
            unrated_pks = [r.pk for r in given_relations if r.reaction_rating is None]
            if unrated_pks:
                editable_relation_pks = set(
                    RelationPermission.objects.filter(
                        user=user,
                        relation_id__in=unrated_pks,
                        permission_type__gte=PermissionLevel.EDITOR,
                    ).values_list("relation_id", flat=True)
                )
        revealable_pks = revealable_relation_pks(given_relations, user)

    by_year: dict[int | None, list[HistoryEntry]] = {}
    for relation in given_relations:
        group_name = (
            relation.group.name
            if relation.group_id is not None
            and relation.group_id in visible_group_ids
            and (group is None or relation.group_id != group.pk)
            else None
        )
        person_name = (
            str(relation.person)
            if relation.person_id is not None
            and (person is None or relation.person_id != person.pk)
            else None
        )
        can_rate_inline = relation.reaction_rating is None and relation.pk in editable_relation_pks
        by_year.setdefault(history_year(relation), []).append(
            HistoryEntry(
                relation,
                group_name,
                person_name,
                can_rate_inline=can_rate_inline,
                can_reveal=relation.pk in revealable_pks,
            )
        )

    years = sorted(by_year, key=lambda year: (year is None, -(year or 0)))
    return [
        HistoryYear(year, sorted(by_year[year], key=lambda e: e.relation.gift.name.lower()))
        for year in years
    ]


def find_repeat_gift_plans(
    user, *, person: Person | None, group: PersonGroup | None, gift: Gift, exclude=None
) -> list[Relation]:
    """Return the viewer's plans giving ``gift`` to the same recipient again.

    Abandoned plans do not count: the gift was never given. ``exclude`` is the plan being
    edited, which is not a repeat of itself.
    """
    queryset = Relation.objects.accessible_by(user).filter(gift=gift)
    if person is not None:
        queryset = queryset.filter(person=person)
    elif group is not None:
        queryset = queryset.filter(group=group)
    else:
        return []
    if exclude is not None and exclude.pk is not None:
        queryset = queryset.exclude(pk=exclude.pk)
    queryset = queryset.select_related("status", "event").order_by("-creation_date")
    return [relation for relation in queryset if not is_abandoned_status(relation.status)]


def find_regift_warnings(user, person: Person | None, gift_name: str):
    """Return received gifts the viewer recorded receiving from *person* matching *gift_name*."""
    if not person or not gift_name or not user or not user.is_authenticated:
        return []

    memberships = Person.groups.through.objects.filter(person=person).values("persongroup_id")
    groups = PersonGroup.hierarchy_subquery(memberships, ancestors=True, include_start=True)

    giver_filter = Q(giver_persons=person) | Q(giver_groups__in=groups)
    if person.account_id is not None:
        giver_filter |= Q(giver_accounts=person.account)

    candidates = (
        ReceivedGift.objects.for_user(user)
        .filter(giver_filter)
        .distinct()
        .prefetch_related("giver_persons", "giver_groups")
        .select_related("event")
        .order_by("-received_on")
    )

    norm_target = " ".join(gift_name.split()).casefold()
    matches = []
    for candidate in candidates:
        norm_title = " ".join(candidate.title.split()).casefold()
        if norm_title == norm_target:
            matches.append(candidate)
    return matches
