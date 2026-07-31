"""Shared helpers for gift-plan card quick actions."""

from django.utils.translation import gettext

from gift_manager.statuses import is_idea_status
from gift_manager.statuses import is_terminal_status
from gift_manager.statuses import relation_status_slug

ACTION_STATUS_SLUGS = {
    "given": "given",
    "purchased": "purchased",
    "planned": "planned",
    "abandoned": "abandoned",
}


def _status_action(name: str, label: str, icon: str, button_class: str) -> dict:
    """Return metadata for a status-changing card action."""
    return {
        "kind": "status",
        "name": name,
        "label": label,
        "icon": icon,
        "button_class": button_class,
    }


def _edit_action() -> dict:
    """Return metadata for the contextual full edit action."""
    return {
        "kind": "edit",
        "name": "add_details",
        "label": gettext("Add details"),
        "icon": "fa-pen-to-square",
        "button_class": "btn-primary",
    }


def _date_action() -> dict:
    """Return metadata for the direct date-setting action."""
    return {
        "kind": "date",
        "name": "set_date",
        "label": gettext("Set date"),
        "icon": "fa-calendar-plus",
        "button_class": "btn-outline-primary",
    }


def _planning_action() -> dict:
    """Return metadata for the direct planning action."""
    return {
        "kind": "planning",
        "name": "plan",
        "label": gettext("Plan"),
        "icon": "fa-calendar-check",
        "button_class": "btn-outline-primary",
    }


def _requires_planning_fields(relation) -> bool:
    """Return whether the relation should have concrete planning details."""
    return not is_idea_status(relation.status) and not is_terminal_status(relation.status)


def _has_missing_event(relation) -> bool:
    """Return whether the relation needs an event to complete its planning details."""
    return _requires_planning_fields(relation) and relation.event_id is None


def build_gift_plan_quick_actions(relation, urgency_key: str, *, can_edit: bool) -> list[dict]:
    """Return the quick actions that should be shown for a gift-plan card."""
    if not can_edit:
        return []

    current_status_slug = relation_status_slug(relation.status)
    current_status_is_terminal = is_terminal_status(relation.status)
    actions = []

    if urgency_key in {"overdue", "due_soon"} and not current_status_is_terminal:
        actions.append(
            _status_action(
                "given",
                gettext("Given"),
                "fa-circle-check",
                "btn-success",
            )
        )

    if (
        urgency_key in {"due_soon", "later"}
        and not current_status_is_terminal
        and current_status_slug != "purchased"
    ):
        actions.append(
            _status_action(
                "purchased",
                gettext("Purchased"),
                "fa-bag-shopping",
                "btn-outline-primary",
            )
        )

    if urgency_key in {"overdue", "due_soon"} and _has_missing_event(relation):
        actions.append(_edit_action())

    if urgency_key == "needs_details":
        actions.append(_edit_action())
        if relation.due_date is None:
            actions.append(_date_action())

    if urgency_key == "ideas" and not current_status_is_terminal:
        if current_status_slug != "planned":
            actions.append(_planning_action())
        actions.append(
            _status_action(
                "abandoned",
                gettext("Abandon"),
                "fa-ban",
                "btn-outline-secondary",
            )
        )

    return actions


def gift_plan_has_contextual_edit_action(actions: list[dict]) -> bool:
    """Return whether quick actions already include an edit-panel action."""
    return any(action["kind"] == "edit" for action in actions)
