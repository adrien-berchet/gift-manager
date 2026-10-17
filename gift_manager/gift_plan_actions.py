"""Shared helpers for gift-plan card quick actions."""

from datetime import date
from datetime import datetime
from datetime import timedelta

from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext

from gift_manager.models import Event
from gift_manager.models import Relation
from gift_manager.models import RelationStatus
from gift_manager.sharing_service import RelationExposureDenied
from gift_manager.sharing_service import SharingService
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


def gift_plan_requires_planning_fields(relation) -> bool:
    """Return whether the relation should have concrete planning details."""
    return not is_idea_status(relation.status) and not is_terminal_status(relation.status)


def gift_plan_has_missing_event(relation) -> bool:
    """Return whether the relation needs an event to complete its planning details."""
    return gift_plan_requires_planning_fields(relation) and relation.event_id is None


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
        urgency_key in {"overdue", "due_soon", "later"}
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

    if urgency_key in {"overdue", "due_soon"} and gift_plan_has_missing_event(relation):
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


QUICK_ACTION_UNDO_SALT = "gift_manager.relation_quick_action_undo"
QUICK_ACTION_UNDO_MAX_AGE = 300
UNDOABLE_QUICK_ACTIONS = frozenset(("given", "purchased", "abandoned", "set_date"))
REACTION_PROMPT_ACTIONS = frozenset(("given", "abandoned"))


def gift_plan_urgency_key(relation, *, today=None, window_days=7) -> str:
    """Return the urgency bucket for a gift plan."""
    today = today or timezone.localdate()
    if is_terminal_status(relation.status):
        urgency_key = "completed"
    elif relation.due_date is None:
        urgency_key = "ideas" if is_idea_status(relation.status) else "needs_details"
    elif relation.due_date < today:
        urgency_key = "overdue"
    elif relation.due_date <= today + timedelta(days=window_days):
        urgency_key = "due_soon"
    elif gift_plan_requires_planning_fields(relation) and relation.event_id is None:
        urgency_key = "needs_details"
    else:
        urgency_key = "later"
    return urgency_key


def gift_plan_has_missing_due_date(relation) -> bool:
    """Return whether an active gift plan is missing a due date."""
    return gift_plan_requires_planning_fields(relation) and relation.due_date is None


def _get_relation_status_by_slug(status_slug: str) -> RelationStatus:
    """Return a relation status by canonical slug."""
    for status in RelationStatus.objects.all():
        if relation_status_slug(status) == status_slug:
            return status
    raise RelationStatus.DoesNotExist


def relation_undo_state(relation, *, field: str) -> dict:
    """Return the JSON-safe values an undo token tracks for a relation."""
    if field == "due_date":
        return {"due_date": relation.due_date.isoformat() if relation.due_date else None}
    changed_at = relation.status_changed_at
    return {
        "status": relation.status_id,
        "status_changed_at": changed_at.isoformat() if changed_at else None,
        # A reaction saved meanwhile must block the undo: it would stay on the reverted plan
        "reaction_rating": relation.reaction_rating,
        "reaction_note": relation.reaction_note,
    }


def build_quick_action_undo(relation, user, action: str, previous: dict) -> dict:
    """Return the notification payload that lets the user revert a quick action."""
    field = "due_date" if action == "set_date" else "status"
    token = signing.dumps(
        {
            "relation": str(relation.relation_id),
            "user": user.pk,
            "field": field,
            "previous": previous,
            "current": relation_undo_state(relation, field=field),
        },
        salt=QUICK_ACTION_UNDO_SALT,
    )
    return {
        "url": reverse(
            "gift_manager:relation_quick_action_undo", kwargs={"pk": relation.relation_id}
        ),
        "token": token,
        "label": gettext("Undo"),
    }


def available_relation_quick_action_names(relation) -> set[str]:
    """Return POST-capable quick action names for the relation's current card bucket."""
    urgency_key = gift_plan_urgency_key(relation)
    actions = build_gift_plan_quick_actions(relation, urgency_key, can_edit=True)
    return {action["name"] for action in actions if action["kind"] != "edit"}


def set_relation_quick_action_due_date(relation, due_date_value: str | None) -> None:
    """Set a relation due date from a quick-action date value."""
    if not due_date_value:
        raise ValueError
    relation.due_date = date.fromisoformat(due_date_value)
    relation.save(update_fields=["due_date"])


def set_relation_quick_action_status(relation, action: str) -> None:
    """Set a relation status for a status quick action."""
    relation.status = _get_relation_status_by_slug(ACTION_STATUS_SLUGS[action])
    relation.save(update_fields=["status"])


def set_relation_quick_action_plan(
    relation,
    user,
    *,
    event_id: str | None,
    due_date_value: str | None,
) -> None:
    """Set concrete planning fields and mark an idea as planned."""
    if not event_id or not due_date_value:
        raise ValueError

    try:
        due_date = date.fromisoformat(due_date_value)
        event = Event.objects.accessible_by(user).get(event_id=event_id)
    except (Event.DoesNotExist, ValidationError, ValueError) as exc:
        raise ValueError from exc

    previous_related_ids = SharingService.relation_related_ids(relation)
    relation.status = _get_relation_status_by_slug("planned")
    relation.event = event
    relation.due_date = due_date
    with transaction.atomic():
        # The new event is shown to everyone the gift plan is shared with
        SharingService.cascade_relation_reassignment(user, relation, previous_related_ids)
        relation.save(update_fields=["status", "event", "due_date"])


def apply_relation_quick_action(relation, user, action: str, post_data) -> str:
    """Apply a validated quick action and return its success message."""
    if action == "plan":
        try:
            set_relation_quick_action_plan(
                relation,
                user,
                event_id=post_data.get("event"),
                due_date_value=post_data.get("due_date"),
            )
        except ValueError as exc:
            msg = gettext("Choose a valid event and due date.")
            raise ValueError(msg) from exc
        except RelationExposureDenied as exc:
            raise ValueError(str(exc.message)) from exc
        return gettext("Gift plan marked as planned.")

    if action == "set_date":
        try:
            set_relation_quick_action_due_date(relation, post_data.get("due_date"))
        except ValueError as exc:
            msg = gettext("Choose a valid due date.")
            raise ValueError(msg) from exc
        return gettext("Due date updated.")

    set_relation_quick_action_status(relation, action)
    messages = {
        "given": gettext("Gift plan marked as given."),
        "purchased": gettext("Gift plan marked as purchased."),
        "planned": gettext("Gift plan marked as planned."),
        "abandoned": gettext("Gift plan abandoned."),
    }
    return messages[action]


def restore_relation_from_undo(relation, payload: dict) -> bool:
    """Restore the previous values when the relation still matches the undone state."""
    field = payload["field"]
    if relation_undo_state(relation, field=field) != payload["current"]:
        return False

    previous = payload["previous"]
    if field == "due_date":
        updates = {
            "due_date": date.fromisoformat(previous["due_date"]) if previous["due_date"] else None
        }
    else:
        changed_at = previous["status_changed_at"]
        updates = {
            "status_id": previous["status"],
            "status_changed_at": datetime.fromisoformat(changed_at) if changed_at else None,
        }
    # A queryset update keeps status_changed_at: save() would stamp it with now().
    Relation.objects.filter(pk=relation.pk).update(**updates)
    return True
