"""Duplicating gift plans and repeating a recurring occasion's plans.

"Duplicate" pre-fills the plan form from an existing plan. "Plan again" lists the plans of
the last occurrence of a repeating event (or of the global Birthday event, whose occurrences
are the recipients' birthdays) and recreates the chosen ones as new ``Idea`` plans due on the
next occurrence. Copies never carry a reaction, and never inherit sharing: the user who
creates them is their only owner.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from datetime import timedelta
from urllib.parse import urlencode

from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from gift_manager.birthdays import PLAN_COVERAGE_DAYS
from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import Relation
from gift_manager.models import RelationStatus
from gift_manager.services import PermissionService
from gift_manager.statuses import is_abandoned_status

DUPLICATE_OF_PARAM = "duplicate_of"

_PERIODS = {
    "daily": relativedelta(days=1),
    "weekly": relativedelta(weeks=1),
    "monthly": relativedelta(months=1),
    "yearly": relativedelta(years=1),
}


@dataclass(frozen=True)
class RepeatCandidate:
    """A plan of the last occurrence that can be recreated, with the date of its copy."""

    relation: Relation
    due_date: date | None


def duplicate_plan_url(relation: Relation) -> str:
    """Return the plan creation URL pre-filled with a copy of ``relation``."""
    query = urlencode({DUPLICATE_OF_PARAM: relation.relation_id})
    return f"{reverse('gift_manager:relation_create')}?{query}"


def duplicate_initial(relation: Relation) -> dict:
    """Return the plan form's initial values for a copy of ``relation``.

    The status is left to its default (``Idea``); the reaction, claim and comments are never
    copied, while the surprise flag is: the recipient is the same.
    """
    return {
        "recipient": relation.recipient_key,
        "gift": relation.gift_id,
        "event": relation.event_id,
        "due_date": relation.due_date,
        "comment": relation.comment,
        "url": relation.url,
        "price": relation.price,
        "is_surprise": relation.is_surprise,
    }


def parse_duplicate_source(user, raw_value: str) -> Relation | None:
    """Return the plan to duplicate, or None when it is invalid or not visible to the user."""
    try:
        relation_id = uuid.UUID(raw_value)
    except ValueError:
        return None
    return (
        Relation.objects.accessible_by(user)
        .filter(relation_id=relation_id)
        .select_related("person", "group", "gift")
        .first()
    )


def supports_plan_again(event: Event) -> bool:
    """Return whether an event has occurrences to plan again (repeating, or Birthday)."""
    return event.is_birthday or event.is_recurring


def _period(event: Event) -> relativedelta:
    """Return the span between two occurrences (birthdays are yearly)."""
    return _PERIODS["yearly" if event.is_birthday else event.recurrence]


def _next_date(event: Event, relation: Relation, today: date) -> date | None:
    """Return the date of the copy: the next occurrence, or the recipient's next birthday."""
    if event.is_birthday:
        return relation.person.next_birthday(today) if relation.person_id else None
    return event.next_occurrence(today)


def _pair_key(relation: Relation) -> tuple:
    return (relation.gift_id, relation.person_id, relation.group_id)


def _usable_plans(user, event: Event) -> list[Relation]:
    """Return the event's plans whose gift and recipient the user may use for a new plan.

    The same visibility rules as the plan form apply, so a copy never exposes an object
    the user cannot see.
    """
    return list(
        Relation.objects.accessible_by(user)
        .filter(event=event, gift__in=Gift.objects.accessible_by(user))
        .filter(
            Q(person__isnull=False, person__in=Person.objects.accessible_by(user))
            | Q(group__isnull=False, group__in=PersonGroup.objects.accessible_by(user))
        )
        .select_related("person", "group", "gift", "status")
        .distinct()
    )


def find_repeat_candidates(user, event: Event, today: date | None = None) -> list[RepeatCandidate]:
    """Return the plans of the event's last occurrence that were not planned again yet.

    Per gift and recipient, the latest live (not abandoned) plan due in the last occurrence
    is offered, unless a live plan for the same pair already covers the next occurrence.
    Occurrences are told apart by a boundary a little before the next date, so plans bought
    early for the next occurrence count as already repeated.
    """
    if not supports_plan_again(event):
        return []
    today = today or timezone.localdate()
    period = _period(event)

    by_pair: dict[tuple, list[Relation]] = {}
    for plan in _usable_plans(user, event):
        if not is_abandoned_status(plan.status):
            by_pair.setdefault(_pair_key(plan), []).append(plan)

    candidates = []
    for plans in by_pair.values():
        next_date = _next_date(event, plans[0], today)
        reference = next_date or today
        previous = reference - period
        lead = timedelta(days=min(PLAN_COVERAGE_DAYS, (reference - previous).days // 2))
        boundary = reference - lead

        already_planned = any(
            plan.due_date >= boundary if plan.due_date else next_date is None for plan in plans
        )
        sources = [
            plan for plan in plans if plan.due_date and previous - lead <= plan.due_date < boundary
        ]
        if already_planned or not sources:
            continue
        candidates.append(
            RepeatCandidate(
                relation=max(sources, key=lambda plan: plan.due_date), due_date=next_date
            )
        )

    candidates.sort(
        key=lambda candidate: (
            candidate.relation.recipient_name.lower(),
            candidate.relation.gift.name.lower(),
        )
    )
    return candidates


def repeat_plans(
    user, event: Event, relation_ids: list[uuid.UUID], today: date | None = None
) -> list[Relation]:
    """Create the chosen candidates as new ``Idea`` plans owned by ``user`` alone.

    Identifiers that are not current candidates for this user are ignored.
    """
    chosen = set(relation_ids)
    candidates = [
        candidate
        for candidate in find_repeat_candidates(user, event, today)
        if candidate.relation.relation_id in chosen
    ]
    created = []
    with transaction.atomic():
        for candidate in candidates:
            source = candidate.relation
            copy = Relation.objects.create(
                person=source.person,
                group=source.group,
                gift=source.gift,
                event=event,
                status_id=RelationStatus.get_default_pk(),
                due_date=candidate.due_date,
                comment=source.comment,
                url=source.url,
                price=source.price,
                is_surprise=source.is_surprise,
            )
            PermissionService.create_or_update_permission(
                user, copy, permission_level=PermissionLevel.OWNER, object_attr="relation"
            )
            created.append(copy)
    return created
