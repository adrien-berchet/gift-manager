"""Gift history of a recipient and repeat-gift detection.

Both read through ``Relation.objects.accessible_by(user)``, so a user only ever sees the
gift plans they can access.
"""

from dataclasses import dataclass

from django.db.models import Q
from django.db.models import QuerySet

from gift_manager.models import Gift
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import Relation
from gift_manager.statuses import is_abandoned_status
from gift_manager.statuses import is_idea_status


@dataclass(frozen=True)
class HistoryEntry:
    """One gift plan of the history, with the group name only when the viewer may see it."""

    relation: Relation
    group_name: str | None


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
    groups = set(person.groups.all())
    for group in list(groups):
        groups.update(group.get_ancestors())
    return _base_queryset(user).filter(Q(person=person) | Q(group__in=groups))


def group_history_queryset(user, group: PersonGroup) -> QuerySet:
    """Return the plans targeted at a group directly."""
    return _base_queryset(user).filter(group=group)


def build_gift_history(relations, visible_group_ids: set[int]) -> list[HistoryYear]:
    """Group plans by year, newest year first; ideas are not history and are left out."""
    by_year: dict[int | None, list[HistoryEntry]] = {}
    for relation in relations:
        if is_idea_status(relation.status):
            continue
        group_name = (
            relation.group.name
            if relation.group_id is not None and relation.group_id in visible_group_ids
            else None
        )
        by_year.setdefault(history_year(relation), []).append(HistoryEntry(relation, group_name))

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
