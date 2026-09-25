"""Presentation data for gift-plan cards shared by the Dashboard and workspace."""

from collections.abc import Sequence

from django.urls import reverse
from django.utils.translation import gettext

from gift_manager.gift_plan_actions import build_gift_plan_quick_actions
from gift_manager.gift_plan_actions import gift_plan_has_contextual_edit_action
from gift_manager.gift_plan_actions import gift_plan_has_missing_event
from gift_manager.models import Event
from gift_manager.models import PermissionLevel
from gift_manager.models import Relation
from gift_manager.statuses import can_rate_status
from gift_manager.statuses import is_abandoned_status
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
        "detail_url": reverse("gift_manager:relation_detail", kwargs={"pk": relation.relation_id}),
        "edit_url": reverse("gift_manager:relation_edit", kwargs={"pk": relation.relation_id}),
        "quick_action_url": reverse(
            "gift_manager:relation_quick_action", kwargs={"pk": relation.relation_id}
        ),
        "reaction_url": reverse(
            "gift_manager:relation_reaction", kwargs={"pk": relation.relation_id}
        ),
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
