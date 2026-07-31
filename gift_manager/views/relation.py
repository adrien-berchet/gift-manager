"""Relation-related views."""

from datetime import date
from datetime import timedelta
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Case
from django.db.models import CharField
from django.db.models import Prefetch
from django.db.models import TextField
from django.db.models import Value
from django.db.models import When
from django.db.models.functions import Coalesce
from django.db.models.functions import Concat
from django.db.models.functions import NullIf
from django.http import HttpResponse
from django.http import HttpResponseBadRequest
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.html import conditional_escape
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from django.views.decorators.http import require_POST
from django.views.generic import DetailView

from gift_manager.forms import GiftRelationForm
from gift_manager.forms import PersonGroupRelationForm
from gift_manager.forms import PersonRelationForm
from gift_manager.forms import RelationForm
from gift_manager.gift_plan_actions import ACTION_STATUS_SLUGS
from gift_manager.gift_plan_actions import build_gift_plan_quick_actions
from gift_manager.gift_plan_actions import gift_plan_has_contextual_edit_action
from gift_manager.mixins.permissions import PermissionContextMixin
from gift_manager.mixins.permissions import PermissionUpdateMixin
from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import PermissionLevel
from gift_manager.models import Relation
from gift_manager.models import RelationPermission
from gift_manager.models import RelationStatus
from gift_manager.services import PermissionService
from gift_manager.statuses import is_idea_status
from gift_manager.statuses import is_terminal_status
from gift_manager.statuses import relation_status_slug
from gift_manager.views.base import BaseCreateView
from gift_manager.views.base import BaseDeleteView
from gift_manager.views.base import BaseDetailView
from gift_manager.views.base import BaseListView
from gift_manager.views.base import BaseUpdateView
from gift_manager.views.base import HTMXResponseMixin


def gift_plan_status_class(status) -> str:
    """Return the shared CSS status class for a gift plan status."""
    return f"gift-plan-status--{relation_status_slug(status)}"


def is_completed_status(status) -> bool:
    """Return whether a status should be treated as completed in workspace grouping."""
    return is_terminal_status(status)


def gift_plan_urgency_key(relation, *, today=None, window_days=7) -> str:
    """Return the urgency bucket for a gift plan."""
    today = today or timezone.localdate()
    if is_completed_status(relation.status):
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


def gift_plan_has_missing_event(relation) -> bool:
    """Return whether an active gift plan is missing an event."""
    return gift_plan_requires_planning_fields(relation) and relation.event_id is None


def gift_plan_requires_planning_fields(relation) -> bool:
    """Return whether a gift plan status expects concrete planning details."""
    return not is_idea_status(relation.status) and not is_completed_status(relation.status)


class PersonRelationCreateView(BaseCreateView):
    model = Relation
    form_class = PersonRelationForm
    context_object_name = "relation"
    object_type = gettext_noop("Gift Plan")
    htmx_template_name = "gift_manager/includes/relation_form_partial.html"
    form_fields_template = "gift_manager/includes/forms/relation_fields.html"
    form_css_class = "relation-form"
    form_type = "relation"

    def get_success_url(self):
        return reverse("gift_manager:person_detail", kwargs={"pk": self.kwargs["pk"]})

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["person_id"] = self.kwargs["pk"]  # Pass the person ID to the form
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form_action_url"] = reverse(
            "gift_manager:person_relation_create", kwargs={"pk": self.kwargs["pk"]}
        )
        return context

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["gift"].queryset = Gift.objects.accessible_by(self.request.user).order_by(
            "name"
        )
        form.fields["event"].queryset = Event.objects.accessible_by(self.request.user).order_by(
            "name"
        )
        return form


class PersonGroupRelationCreateView(BaseCreateView):
    model = Relation
    form_class = PersonGroupRelationForm
    context_object_name = "relation"
    object_type = gettext_noop("Gift Plan")
    htmx_template_name = "gift_manager/includes/relation_form_partial.html"
    form_fields_template = "gift_manager/includes/forms/relation_fields.html"
    form_css_class = "relation-form"
    form_type = "relation"

    def get_success_url(self):
        url = reverse("gift_manager:person_group_detail", kwargs={"pk": self.kwargs["pk"]})
        query = urlencode({"tab": "gifts"})
        return f"{url}?{query}"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["group_id"] = self.kwargs["pk"]  # Pass the group ID to the form
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form_action_url"] = reverse(
            "gift_manager:person_group_relation_create", kwargs={"pk": self.kwargs["pk"]}
        )
        return context

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["gift"].queryset = Gift.objects.accessible_by(self.request.user).order_by(
            "name"
        )
        form.fields["event"].queryset = Event.objects.accessible_by(self.request.user).order_by(
            "name"
        )
        return form


class GiftRelationCreateView(BaseCreateView):
    model = Relation
    form_class = GiftRelationForm
    context_object_name = "relation"
    object_type = gettext_noop("Gift Plan")
    htmx_template_name = "gift_manager/includes/relation_form_partial.html"
    form_fields_template = "gift_manager/includes/forms/relation_fields.html"
    form_css_class = "relation-form"
    form_type = "relation"

    def get_success_url(self):
        return reverse("gift_manager:gift_detail", kwargs={"pk": self.kwargs["pk"]})

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["gift_id"] = self.kwargs["pk"]  # Pass the gift ID to the form
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form_action_url"] = reverse(
            "gift_manager:gift_relation_create", kwargs={"pk": self.kwargs["pk"]}
        )
        return context

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["event"].queryset = Event.objects.accessible_by(self.request.user).order_by(
            "name"
        )
        return form


class GiftRelationDeleteView(BaseDeleteView):
    model = Relation
    pk_name = "relation_id"
    object_type = "relation"
    display_object_type = gettext_noop("gift plan")

    def get_success_url(self):
        url = reverse("gift_manager:person_group_detail", kwargs={"pk": self.kwargs["pk"]})
        query = urlencode({"tab": "gifts"})
        return f"{url}?{query}"


class RelationStatusListView(BaseListView):
    model = RelationStatus
    template_name = "gift_manager/status_list.html"
    object_type = "Status"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.column_names = {
            "status": gettext("Status"),
        }

    def get_queryset(self):
        """Return RelationStatus."""
        return RelationStatus.objects.values("pk", *self.column_names).order_by("pk")


class RelationStatusDetailView(BaseDetailView):
    model = RelationStatus
    template_name = "gift_manager/relation_status_detail.html"
    context_object_name = "status"
    pk_name = "pk"  # RelationStatus uses default 'id' field, not 'status_id'

    def get_queryset(self):
        """Return all RelationStatus objects without user filtering.

        RelationStatus is a global lookup table shared by all users,
        so it doesn't have a 'shared_with' field.
        """
        return RelationStatus.objects.all()

    def get_context_data(self, **kwargs):
        # Skip BaseDetailView's mixins that expect 'shared_with' field
        # Call DetailView's get_context_data directly
        context = DetailView.get_context_data(self, **kwargs)

        # Add relations that have this status (filtered by user)
        # Use with_related_objects() to avoid N+1 queries when accessing
        # person, group, gift, event in the template
        context["relations"] = (
            Relation.objects.accessible_by(self.request.user)
            .with_related_objects()
            .filter(status=self.object)
        )
        return context


class RelationListView(PermissionContextMixin, BaseListView):
    model = Relation
    template_name = "gift_manager/relation_list.html"
    object_type = gettext_noop("Gift Plans")
    workspace_window_days = 7
    workspace_group_order = (
        "overdue",
        "due_soon",
        "needs_details",
        "later",
        "ideas",
        "completed",
    )
    attention_urgency_keys = frozenset(("overdue", "due_soon"))
    show_workspace = True
    show_advanced_list = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.column_names = {
            "gift__name": gettext("Gift"),
            "comment": gettext("Comment"),
            "related_object": gettext("Recipient"),
            "event": gettext("Event"),
            "status__status": gettext("Status"),
            "due_date": gettext("Due date"),
        }

    def get_queryset(self):
        if not self.show_advanced_list:
            return Relation.objects.none()

        return (
            Relation.objects.accessible_by(self.request.user)
            .annotate(
                related_object=Coalesce(
                    NullIf(
                        Concat(
                            "person__first_name",
                            Value(" "),
                            "person__family_name",
                            output_field=TextField(),
                        ),
                        Value(" "),
                    ),
                    "group__name",
                    output_field=TextField(),
                ),
                recipient_type=Case(
                    When(person__isnull=False, then=Value("person")),
                    default=Value("group"),
                    output_field=CharField(),
                ),
            )
            .order_by("status__pk", "person__first_name", "person__family_name", "gift__name")
            .values(
                "relation_id",
                "gift__name",
                "gift__gift_id",
                "comment",
                "related_object",
                "recipient_type",
                "person__person_id",
                "group__group_id",
                "event__name",
                "event__event_id",
                "status",
                "due_date",
            )
        )

    def get_workspace_queryset(self):
        """Return relation instances optimized for the card workspace."""
        return (
            Relation.objects.accessible_by(self.request.user)
            .with_related_objects()
            .prefetch_related(
                "gift__tags",
                Prefetch(
                    "relationpermission_set",
                    queryset=RelationPermission.objects.filter(user=self.request.user).only(
                        "permission_type",
                        "relation_id",
                    ),
                    to_attr="current_user_permissions",
                ),
            )
            .order_by("due_date", "status__pk", "gift__name")
        )

    def get_workspace_groups(self, relations):
        """Group gift plans by urgency for the primary workspace."""
        today = timezone.localdate()
        event_options = list(
            Event.objects.accessible_by(self.request.user)
            .only("id", "event_id", "name")
            .order_by("name")
        )
        groups = {
            "overdue": {
                "key": "overdue",
                "label": gettext("Overdue"),
                "description": gettext("Due before today"),
                "icon": "fa-triangle-exclamation",
                "cards": [],
            },
            "due_soon": {
                "key": "due_soon",
                "label": gettext("Due soon"),
                "description": gettext("Due in the next 7 days"),
                "icon": "fa-clock",
                "cards": [],
            },
            "later": {
                "key": "later",
                "label": gettext("Later"),
                "description": gettext("Due after the next 7 days"),
                "icon": "fa-calendar",
                "cards": [],
            },
            "needs_details": {
                "key": "needs_details",
                "label": gettext("Needs details"),
                "description": gettext("Missing due date or event"),
                "icon": "fa-list-check",
                "cards": [],
            },
            "ideas": {
                "key": "ideas",
                "label": gettext("Ideas"),
                "description": gettext("Open-ended ideas to revisit later"),
                "icon": "fa-lightbulb",
                "cards": [],
            },
            "completed": {
                "key": "completed",
                "label": gettext("Completed"),
                "description": gettext("Already given or finished"),
                "icon": "fa-circle-check",
                "cards": [],
            },
        }

        for relation in relations:
            card = self.get_workspace_card(relation, today, event_options)
            groups[card["urgency_key"]]["cards"].append(card)

        return [groups[key] for key in self.workspace_group_order if groups[key]["cards"]]

    def get_workspace_card(self, relation, today, event_options=None):
        """Return presentation data for a single gift-plan card."""
        urgency_key = gift_plan_urgency_key(
            relation,
            today=today,
            window_days=self.workspace_window_days,
        )
        permission = self.get_workspace_card_permission(relation)
        can_edit = permission >= PermissionLevel.EDITOR
        quick_actions = build_gift_plan_quick_actions(relation, urgency_key, can_edit=can_edit)
        has_planning_action = any(action["kind"] == "planning" for action in quick_actions)
        has_missing_event = gift_plan_has_missing_event(relation)
        return {
            "relation": relation,
            "urgency_key": urgency_key,
            "status_class": gift_plan_status_class(relation.status),
            "detail_url": reverse(
                "gift_manager:relation_detail", kwargs={"pk": relation.relation_id}
            ),
            "edit_url": reverse("gift_manager:relation_edit", kwargs={"pk": relation.relation_id}),
            "delete_url": reverse(
                "gift_manager:relation_delete", kwargs={"pk": relation.relation_id}
            ),
            "quick_action_url": reverse(
                "gift_manager:relation_quick_action", kwargs={"pk": relation.relation_id}
            ),
            "quick_actions": quick_actions,
            "has_contextual_edit_action": gift_plan_has_contextual_edit_action(quick_actions),
            "event_options": event_options if has_planning_action else [],
            "has_missing_event": has_missing_event,
            "missing_event_label": gettext("Missing event") if has_missing_event else "",
            "can_edit": can_edit,
            "can_delete": permission >= PermissionLevel.OWNER,
        }

    def get_workspace_card_permission(self, relation) -> int:
        """Return the current user's permission using workspace prefetch data."""
        current_user_permissions = getattr(relation, "current_user_permissions", None)
        if current_user_permissions is not None:
            if not current_user_permissions:
                return PermissionLevel.NONE
            return current_user_permissions[0].permission_type

        return PermissionService.get_permission(relation, self.request.user)

    def get_workspace_summary(self, workspace_groups):
        """Return compact counts for the workspace summary strip."""
        counts = {group["key"]: len(group["cards"]) for group in workspace_groups}
        total = sum(counts.values())
        attention = (
            counts.get("overdue", 0) + counts.get("due_soon", 0) + counts.get("needs_details", 0)
        )
        return {
            "total": total,
            "attention": attention,
            "overdue": counts.get("overdue", 0),
            "due_soon": counts.get("due_soon", 0),
            "needs_details": counts.get("needs_details", 0),
            "ideas": counts.get("ideas", 0),
        }

    def get_advanced_list_row_state(self, relation, today):
        """Return row metadata used to mark attention-worthy advanced list rows."""
        urgency_key = gift_plan_urgency_key(
            relation,
            today=today,
            window_days=self.workspace_window_days,
        )
        needs_attention = urgency_key in self.attention_urgency_keys
        has_missing_due_date = gift_plan_has_missing_due_date(relation)
        has_missing_event = gift_plan_has_missing_event(relation)
        missing_data_labels = []
        if has_missing_due_date:
            missing_data_labels.append(gettext("Missing due date"))
        if has_missing_event:
            missing_data_labels.append(gettext("Missing event"))
        attention_labels = {
            "overdue": gettext("Overdue"),
            "due_soon": gettext("Due soon"),
        }
        return {
            "urgency_key": urgency_key,
            "needs_attention": needs_attention,
            "attention_label": attention_labels.get(urgency_key, "") if needs_attention else "",
            "has_missing_data": has_missing_due_date or has_missing_event,
            "missing_data_label": ", ".join(missing_data_labels),
            "has_missing_due_date": has_missing_due_date,
            "missing_due_date_label": gettext("Missing due date") if has_missing_due_date else "",
            "has_missing_event": has_missing_event,
            "missing_event_label": gettext("Missing event") if has_missing_event else "",
        }

    def add_advanced_list_row_state(self, rows):
        """Enrich advanced list rows with server-side urgency metadata."""
        relation_ids = [row["relation_id"] for row in rows if row.get("relation_id")]
        if not relation_ids:
            return rows

        relations_by_id = {
            str(relation.relation_id): relation
            for relation in Relation.objects.accessible_by(self.request.user)
            .with_related_objects()
            .filter(relation_id__in=relation_ids)
        }
        today = timezone.localdate()

        for row in rows:
            relation = relations_by_id.get(str(row.get("relation_id")))
            if relation is None:
                row.update(
                    {
                        "urgency_key": "unknown",
                        "needs_attention": False,
                        "attention_label": "",
                        "has_missing_data": False,
                        "missing_data_label": "",
                        "has_missing_due_date": False,
                        "missing_due_date_label": "",
                        "has_missing_event": False,
                        "missing_event_label": "",
                    }
                )
                continue

            row.update(self.get_advanced_list_row_state(relation, today))
        return rows

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["show_workspace"] = self.show_workspace
        context["show_advanced_list"] = self.show_advanced_list
        context["relation_statuses"] = RelationStatus.objects.all()

        if self.show_advanced_list:
            data_rows = self.add_advanced_list_row_state(list(context["data"]))
            context["data"] = data_rows
            context["object_list"] = data_rows

        if self.show_workspace:
            workspace_groups = self.get_workspace_groups(self.get_workspace_queryset())
            context["workspace_groups"] = workspace_groups
            context["workspace_summary"] = self.get_workspace_summary(workspace_groups)
        return context


class RelationAdvancedListView(RelationListView):
    object_type = gettext_noop("Advanced Gift Plans List")
    show_workspace = False
    show_advanced_list = True


class RelationCreateView(BaseCreateView):
    model = Relation
    form_class = RelationForm
    success_url = reverse_lazy("gift_manager:relations")
    context_object_name = "relation"
    object_type = gettext_noop("Gift Plan")
    htmx_template_name = "gift_manager/includes/relation_form_partial.html"
    form_fields_template = "gift_manager/includes/forms/relation_fields.html"
    form_css_class = "relation-form"
    form_type = "relation"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        hide_person = self.request.GET.get("hide_person", "false") == "true"
        kwargs["hide_person"] = hide_person
        hide_group = self.request.GET.get("hide_group", "false") == "true"
        kwargs["hide_group"] = hide_group
        kwargs["user"] = self.request.user
        return kwargs

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["gift"].queryset = Gift.objects.accessible_by(self.request.user).order_by(
            "name"
        )
        form.fields["event"].queryset = Event.objects.accessible_by(self.request.user).order_by(
            "name"
        )
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form_action_url"] = reverse("gift_manager:relation_create")
        return context


class RelationUpdateView(PermissionUpdateMixin, BaseUpdateView):
    model = Relation
    form_class = RelationForm
    pk_name = "relation_id"
    context_object_name = "relation"
    object_type = gettext_noop("Gift Plan")
    detail_url_name = "relation_detail"
    htmx_template_name = "gift_manager/includes/relation_form_partial.html"
    form_fields_template = "gift_manager/includes/forms/relation_fields.html"
    form_css_class = "relation-form"
    form_type = "relation"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        hide_person = self.request.GET.get("hide_person", "false") == "true"
        kwargs["hide_person"] = hide_person
        hide_group = self.request.GET.get("hide_group", "false") == "true"
        kwargs["hide_group"] = hide_group
        kwargs["user"] = self.request.user
        return kwargs

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["gift"].queryset = Gift.objects.accessible_by(self.request.user).order_by(
            "name"
        )
        form.fields["event"].queryset = Event.objects.accessible_by(self.request.user).order_by(
            "name"
        )
        return form

    def get_success_url(self):
        if self.object.person_id is not None:
            pk = self.object.person.person_id
            url = "person_detail"
        else:
            pk = self.object.group.group_id
            url = "person_group_detail"
        return reverse(f"gift_manager:{url}", kwargs={"pk": pk})


class RelationDeleteView(BaseDeleteView):
    model = Relation
    success_url = reverse_lazy("gift_manager:relations")
    pk_name = "relation_id"
    object_type = "relation"
    display_object_type = gettext_noop("gift plan")


class RelationDetailView(BaseDetailView):
    model = Relation
    template_name = "gift_manager/relation_detail.html"
    context_object_name = "relation"
    pk_name = "relation_id"
    htmx_template_name = "gift_manager/includes/relation_detail_partial.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["gift_plan_status_class"] = gift_plan_status_class(self.object.status)
        context["gift_plan_urgency_key"] = gift_plan_urgency_key(self.object)

        # Add action buttons
        is_editor = context["is_editor"]
        context["action_buttons"] = [
            {
                "type": "edit",
                "url": reverse(
                    "gift_manager:relation_edit", kwargs={"pk": self.object.relation_id}
                ),
                "label": _("Edit gift plan"),
                "enabled": is_editor,
                "tooltip": _("You do not have permission to edit this object")
                if not is_editor
                else None,
            },
            {
                "type": "delete",
                "url": reverse(
                    "gift_manager:relation_delete", kwargs={"pk": self.object.relation_id}
                ),
                "label": _("Delete gift plan"),
                "enabled": True,
                "tooltip": _(
                    "You do not have permission to delete this object so it will only be "
                    "unshared with you"
                )
                if not is_editor
                else None,
            },
        ]
        return context


def _get_relation_status_by_slug(status_slug: str) -> RelationStatus:
    """Return a relation status by canonical slug."""
    for status in RelationStatus.objects.all():
        if relation_status_slug(status) == status_slug:
            return status
    raise RelationStatus.DoesNotExist


def _relation_quick_action_response(message: str) -> HttpResponse:
    """Return a no-swap HTMX response that refreshes card lists."""
    response = HttpResponse("")
    response["HX-Reswap"] = "none"
    response["HX-Trigger"] = HTMXResponseMixin.build_hx_trigger_header(
        [
            "list:update",
            {"showNotification": {"message": message, "type": "success"}},
        ]
    )
    return response


def _available_relation_quick_action_names(relation) -> set[str]:
    """Return POST-capable quick action names for the relation's current card bucket."""
    urgency_key = gift_plan_urgency_key(relation)
    actions = build_gift_plan_quick_actions(relation, urgency_key, can_edit=True)
    return {action["name"] for action in actions if action["kind"] != "edit"}


def _set_relation_quick_action_due_date(relation, due_date_value: str | None) -> None:
    """Set a relation due date from a quick-action date value."""
    if not due_date_value:
        raise ValueError
    relation.due_date = date.fromisoformat(due_date_value)
    relation.save(update_fields=["due_date"])


def _set_relation_quick_action_status(relation, action: str) -> None:
    """Set a relation status for a status quick action."""
    relation.status = _get_relation_status_by_slug(ACTION_STATUS_SLUGS[action])
    relation.save(update_fields=["status"])


def _set_relation_quick_action_plan(
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

    relation.status = _get_relation_status_by_slug("planned")
    relation.event = event
    relation.due_date = due_date
    relation.save(update_fields=["status", "event", "due_date"])


def _apply_relation_quick_action(relation, user, action: str, post_data) -> str:
    """Apply a validated quick action and return its success message."""
    if action == "plan":
        try:
            _set_relation_quick_action_plan(
                relation,
                user,
                event_id=post_data.get("event"),
                due_date_value=post_data.get("due_date"),
            )
        except ValueError as exc:
            msg = gettext("Choose a valid event and due date.")
            raise ValueError(msg) from exc
        return gettext("Gift plan marked as planned.")

    if action == "set_date":
        try:
            _set_relation_quick_action_due_date(relation, post_data.get("due_date"))
        except ValueError as exc:
            msg = gettext("Choose a valid due date.")
            raise ValueError(msg) from exc
        return gettext("Due date updated.")

    _set_relation_quick_action_status(relation, action)
    messages = {
        "given": gettext("Gift plan marked as given."),
        "purchased": gettext("Gift plan marked as purchased."),
        "planned": gettext("Gift plan marked as planned."),
        "abandoned": gettext("Gift plan abandoned."),
    }
    return messages[action]


@login_required
@require_POST
def relation_quick_action(request, pk):
    """Apply a small gift-plan card action and trigger card list refreshes."""
    relation = get_object_or_404(Relation.objects.accessible_by(request.user), relation_id=pk)
    if PermissionService.get_effective_permission(relation, request.user) < PermissionLevel.EDITOR:
        return JsonResponse({"error": gettext("You cannot edit this gift plan.")}, status=403)

    action = request.POST.get("action")
    if action not in _available_relation_quick_action_names(relation):
        return JsonResponse(
            {"error": gettext("This quick action is not available for this gift plan.")},
            status=400,
        )

    try:
        message = _apply_relation_quick_action(relation, request.user, action, request.POST)
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))
    except RelationStatus.DoesNotExist:
        return JsonResponse(
            {"error": gettext("Required relation status is not configured.")},
            status=400,
        )
    return _relation_quick_action_response(message)


@login_required
@require_POST
def update_relation_status(request):
    relation_id = request.POST.get("relation_id")
    try:
        new_status = int(request.POST.get("new_status"))
    except (TypeError, ValueError):
        return JsonResponse({"error": gettext("Choose a valid status.")}, status=400)

    try:
        relation = Relation.objects.accessible_by(request.user).get(relation_id=relation_id)
        if (
            PermissionService.get_effective_permission(relation, request.user)
            < PermissionLevel.EDITOR
        ):
            return JsonResponse({"error": gettext("You cannot edit this gift plan.")}, status=403)

        relation.status = RelationStatus.objects.get(pk=new_status)
        relation.save()

        # Build HTML manually to avoid template recursion issues
        relation_statuses = RelationStatus.objects.all()
        options_html = ""
        for stat in relation_statuses:
            selected = "selected" if new_status == stat.pk else ""
            options_html += (
                f'<option value="{stat.pk}" {selected}>{conditional_escape(stat.status)}</option>'
            )

        status_class = gift_plan_status_class(relation.status)
        status_select_class = (
            f"form-select form-select-sm status-selector gift-plan-status-select {status_class}"
        )
        html = f"""<form id="status-form-{relation.relation_id}" class="gift-plan-status-form">
            <select class="{status_select_class}"
                    name="new_status"
                    data-relation-id="{relation.relation_id}"
                    data-update-url="{reverse("gift_manager:relation_status_update")}"
                    data-current-value="{relation.status_id}">
                {options_html}
            </select>
        </form>"""

        return HttpResponse(html)

    except Relation.DoesNotExist:
        return JsonResponse({"error": gettext("Gift Plan not found")}, status=404)
    except RelationStatus.DoesNotExist:
        return JsonResponse({"error": gettext("Choose a valid status.")}, status=400)
