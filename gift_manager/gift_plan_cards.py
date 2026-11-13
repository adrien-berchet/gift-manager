"""Presentation data for gift-plan cards shared by the Dashboard and workspace."""

from collections.abc import Sequence
from datetime import date
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext

from gift_manager.gift_plan_actions import build_gift_plan_quick_actions
from gift_manager.gift_plan_actions import gift_plan_has_contextual_edit_action
from gift_manager.gift_plan_actions import gift_plan_has_missing_event
from gift_manager.gift_plan_actions import gift_plan_requires_planning_fields
from gift_manager.models import Event
from gift_manager.models import PermissionLevel
from gift_manager.models import Relation
from gift_manager.plan_repeat import duplicate_plan_url
from gift_manager.received_gifts import revealable_relation_pks
from gift_manager.services import PermissionService
from gift_manager.statuses import GIVEN_STATUS_SLUGS
from gift_manager.statuses import can_rate_status
from gift_manager.statuses import is_abandoned_status
from gift_manager.statuses import is_given_status
from gift_manager.statuses import is_idea_status
from gift_manager.statuses import is_terminal_status
from gift_manager.statuses import relation_status_slug


def gift_plan_status_class(status) -> str:
    """Return the shared CSS status class for a gift-plan status."""
    return f"gift-plan-status--{relation_status_slug(status)}"


def build_gift_plan_card(
    relation: Relation,
    *,
    urgency_key: str,
    permission: int,
    event_options: Sequence[Event] | None = None,
    can_reveal: bool = False,
) -> dict:
    """Build a card using the caller's grouping and resolved permission.

    Permission lookup stays with the caller so prefetched workspace permissions
    can be reused without adding a query for every card.
    """
    can_edit = permission >= PermissionLevel.EDITOR
    quick_actions = build_gift_plan_quick_actions(relation, urgency_key, can_edit=can_edit)
    has_planning_action = any(action["kind"] == "planning" for action in quick_actions)
    has_missing_event = gift_plan_has_missing_event(relation)
    return {
        "relation": relation,
        "urgency_key": urgency_key,
        "status_class": gift_plan_status_class(relation.status),
        "is_given": is_given_status(relation.status),
        "detail_url": reverse("gift_manager:relation_detail", kwargs={"pk": relation.relation_id}),
        "edit_url": reverse("gift_manager:relation_edit", kwargs={"pk": relation.relation_id}),
        "duplicate_url": duplicate_plan_url(relation),
        "quick_action_url": reverse(
            "gift_manager:relation_quick_action", kwargs={"pk": relation.relation_id}
        ),
        "reaction_url": reverse(
            "gift_manager:relation_reaction", kwargs={"pk": relation.relation_id}
        ),
        "reveal_url": reverse("gift_manager:relation_reveal", kwargs={"pk": relation.relation_id})
        if can_reveal
        else "",
        "can_reveal": can_reveal,
        "quick_actions": quick_actions,
        "has_contextual_edit_action": gift_plan_has_contextual_edit_action(quick_actions),
        "event_options": event_options if has_planning_action and event_options is not None else [],
        "has_missing_event": has_missing_event,
        "missing_event_label": gettext("Missing event") if has_missing_event else "",
        "can_edit": can_edit,
        "can_rate_inline": can_edit
        and can_rate_status(relation.status)
        and relation.reaction_rating is None,
        "can_edit_reaction": can_edit and relation.has_visible_reaction,
        "reaction_is_estimate": is_abandoned_status(relation.status),
    }


DASHBOARD_QUICK_ACTION_DUE_SOON_DAYS = 7
DASHBOARD_STALE_AFTER_DAYS = 30
DASHBOARD_REACTION_WINDOW_DAYS = 30
DASHBOARD_PAGINATED_ACTION_GROUPS = frozenset(("overdue", "upcoming", "incomplete"))
DASHBOARD_COMPACT_ACTION_GROUPS = frozenset(("overdue", "upcoming", "incomplete"))
DASHBOARD_MAX_RENDERED_ACTIONS_PER_GROUP = 24


def _build_dashboard_action_item(
    relation: Relation,
    action_key: str,
    user,
    permission: int | None = None,
    *,
    can_reveal: bool = False,
) -> dict:
    """Return presentation data for a dashboard gift-plan action."""
    urgency_key = {
        "upcoming": "due_soon",
        "incomplete": "needs_details",
        "stale": "later",
        "reaction": "completed",
    }.get(action_key, action_key)
    if permission is None:
        permission = PermissionService.get_permission(relation, user)
    return build_gift_plan_card(
        relation,
        urgency_key=urgency_key,
        permission=permission,
        can_reveal=can_reveal,
    )


def _awaits_reaction(relation: Relation, *, today: date) -> bool:
    """Return whether a recently given, unrated gift plan is waiting for a reaction."""
    is_given = relation_status_slug(relation.status) in GIVEN_STATUS_SLUGS
    if not is_given or relation.reaction_rating is not None:
        return False

    given_on = (
        timezone.localtime(relation.status_changed_at).date()
        if relation.status_changed_at
        else relation.due_date
    )
    return given_on is not None and given_on >= today - timedelta(
        days=DASHBOARD_REACTION_WINDOW_DAYS
    )


def _classify_dashboard_group_key(
    relation: Relation,
    *,
    today: date,
    due_soon_end: date,
    stale_before,
) -> str | None:
    """Return the active dashboard bucket key for a non-terminal plan, or None."""
    if relation.due_date and relation.due_date < today:
        return "overdue"
    if relation.due_date and relation.due_date <= due_soon_end:
        return "upcoming"
    if relation.due_date is None and is_idea_status(relation.status):
        return None
    if gift_plan_requires_planning_fields(relation) and (
        relation.due_date is None or relation.event_id is None
    ):
        return "incomplete"
    if relation.creation_date and relation.creation_date <= stale_before:
        return "stale"
    return None


def build_gift_plan_action_groups(
    relations: list[Relation],
    *,
    user,
    today: date,
    now,
    due_soon_days: int = DASHBOARD_QUICK_ACTION_DUE_SOON_DAYS,
) -> list[dict]:
    """Build priority-ordered dashboard action groups for gift plans.

    ``due_soon_days`` is the length of the "Due soon" window; the reminder digest widens it
    to the lookahead chosen by the user.
    """
    due_soon_end = today + timedelta(days=due_soon_days)
    stale_before = now - timedelta(days=DASHBOARD_STALE_AFTER_DAYS)
    groups = {
        "overdue": {
            "key": "overdue",
            "label": gettext("Overdue"),
            "icon": "fa-triangle-exclamation",
            "items": [],
        },
        "upcoming": {
            "key": "upcoming",
            "label": gettext("Due soon"),
            "icon": "fa-clock",
            "items": [],
        },
        "incomplete": {
            "key": "incomplete",
            "label": gettext("Needs details"),
            "icon": "fa-list-check",
            "items": [],
        },
        "stale": {
            "key": "stale",
            "label": gettext("Stale"),
            "icon": "fa-hourglass-half",
            "items": [],
        },
        "reaction": {
            "key": "reaction",
            "label": gettext("Awaiting reaction"),
            "icon": "fa-heart",
            "items": [],
        },
    }

    reaction_entries: list[tuple[Relation, int]] = []
    for relation in relations:
        if is_terminal_status(relation.status):
            if _awaits_reaction(relation, today=today):
                permission = PermissionService.get_effective_permission(relation, user)
                if permission >= PermissionLevel.EDITOR:
                    reaction_entries.append((relation, permission))
            continue

        group_key = _classify_dashboard_group_key(
            relation,
            today=today,
            due_soon_end=due_soon_end,
            stale_before=stale_before,
        )
        if group_key is not None:
            groups[group_key]["items"].append(
                _build_dashboard_action_item(relation, group_key, user)
            )

    if reaction_entries:
        revealable_pks = revealable_relation_pks([rel for rel, _perm in reaction_entries], user)
        for relation, permission in reaction_entries:
            groups["reaction"]["items"].append(
                _build_dashboard_action_item(
                    relation,
                    "reaction",
                    user,
                    permission,
                    can_reveal=relation.pk in revealable_pks,
                )
            )

    group_order = ("overdue", "upcoming", "incomplete", "stale", "reaction")
    action_groups = [groups[key] for key in group_order if groups[key]["items"]]
    for group in action_groups:
        is_paginated = group["key"] in DASHBOARD_PAGINATED_ACTION_GROUPS
        group["is_paginated"] = is_paginated
        group["is_compact"] = group["key"] in DASHBOARD_COMPACT_ACTION_GROUPS
        group["workspace_focus"] = {
            "overdue": "overdue",
            "upcoming": "due_soon",
            "incomplete": "needs_details",
        }.get(group["key"], "")
        display_limit = DASHBOARD_MAX_RENDERED_ACTIONS_PER_GROUP if is_paginated else 4
        group["display_items"] = group["items"][:display_limit]
    return action_groups


def build_dashboard_summary(action_groups: list[dict], unassigned_gift_count: int) -> dict:
    """Return compact action counts for the dashboard summary strip."""
    action_counts = {group["key"]: len(group["items"]) for group in action_groups}
    # Unassigned gifts are ideas kept for later, not something to act on: they have their own
    # tile (and gift list filter) but do not count as needing attention
    attention_count = sum(count for key, count in action_counts.items() if key != "reaction")
    return {
        "attention": attention_count,
        "overdue": action_counts.get("overdue", 0),
        "upcoming": action_counts.get("upcoming", 0),
        "incomplete": action_counts.get("incomplete", 0),
        "stale": action_counts.get("stale", 0),
        "reaction": action_counts.get("reaction", 0),
        "unassigned_gifts": unassigned_gift_count,
    }
