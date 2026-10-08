"""Event-related views."""

import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.urls import reverse_lazy
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from gift_manager.forms import EventForm
from gift_manager.mixins.fallback_mode import FallbackModeFormMixin
from gift_manager.mixins.fallback_mode import FallbackModeListMixin
from gift_manager.mixins.performance import BatchOperationMixin
from gift_manager.mixins.performance import QueryOptimizationMixin
from gift_manager.mixins.permissions import PermissionContextMixin
from gift_manager.mixins.permissions import PermissionUpdateMixin
from gift_manager.models import Event
from gift_manager.models import Relation
from gift_manager.models import RelationStatus
from gift_manager.plan_repeat import find_repeat_candidates
from gift_manager.plan_repeat import repeat_plans
from gift_manager.plan_repeat import supports_plan_again
from gift_manager.services import GLOBAL_OBJECT_REMOVAL_ERROR
from gift_manager.services import BudgetService
from gift_manager.views.base import BaseCreateView
from gift_manager.views.base import BaseDeleteView
from gift_manager.views.base import BaseDetailView
from gift_manager.views.base import BaseListView
from gift_manager.views.base import BaseUpdateView
from gift_manager.views.base import QueryStringPrefillMixin


class EventListView(
    FallbackModeListMixin,
    QueryOptimizationMixin,
    BatchOperationMixin,
    PermissionContextMixin,
    BaseListView,
):
    model = Event
    template_name = "gift_manager/event_list.html"
    fallback_template_name = "gift_manager/fallback/list_fallback.html"
    no_js_template_name = "gift_manager/fallback/list_fallback.html"
    object_type = "Events"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.column_names = {
            "name": gettext("Event name"),
            "comment": gettext("Comment"),
            "schedule": gettext("Schedule"),
        }

    def get_queryset(self):
        """Return Events for the current user or shared with the user."""
        return Event.objects.for_list_display(self.request.user).order_by("name")

    def get_fallback_columns(self):
        """Get column definitions for fallback table."""
        return [
            {"field": "name", "label": _("Event name"), "type": "text"},
            {"field": "comment", "label": _("Comment"), "type": "text"},
            {"field": "schedule_type", "label": _("Schedule type"), "type": "text"},
            {"field": "date", "label": _("Date"), "type": "date"},
        ]


class EventCreateView(
    QueryStringPrefillMixin, FallbackModeFormMixin, QueryOptimizationMixin, BaseCreateView
):
    model = Event
    form_class = EventForm
    success_url = reverse_lazy("gift_manager:events")
    context_object_name = "event"
    object_type = "Event"
    htmx_template_name = "gift_manager/includes/event_form_partial.html"
    form_fields_template = "gift_manager/includes/forms/event_fields.html"
    form_css_class = "event-form"
    form_type = "event-edit"
    close_offcanvas = True
    prefill_fields = {"name": "name"}


class EventUpdateView(
    PermissionUpdateMixin, FallbackModeFormMixin, QueryOptimizationMixin, BaseUpdateView
):
    model = Event
    form_class = EventForm
    pk_name = "event_id"
    context_object_name = "event"
    object_type = "Event"
    detail_url_name = "event_detail"
    htmx_template_name = "gift_manager/includes/event_form_partial.html"
    form_fields_template = "gift_manager/includes/forms/event_fields.html"
    form_css_class = "event-form"
    form_type = "event-edit"
    close_offcanvas = True


class EventDeleteView(BaseDeleteView):
    model = Event
    success_url = reverse_lazy("gift_manager:events")
    pk_name = "event_id"
    object_type = "event"


class EventDetailView(BaseDetailView):
    model = Event
    template_name = "gift_manager/event_detail.html"
    context_object_name = "event"
    pk_name = "event_id"
    htmx_template_name = "gift_manager/includes/event_detail_partial.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["relations"] = (
            Relation.objects.accessible_by(self.request.user)
            .filter(event=self.object)
            .select_related("person", "group", "gift", "event", "status")
            .order_by("status__pk", "person__first_name", "person__family_name", "gift__name")
        )
        context["relation_statuses"] = RelationStatus.objects.all()
        context["budget"] = BudgetService.for_event(self.request.user, self.object)

        # Add action buttons
        is_editor = context["is_editor"]
        context["action_buttons"] = [
            {
                "type": "edit",
                "url": reverse("gift_manager:event_edit", kwargs={"pk": self.object.event_id}),
                "label": _("Edit event"),
                "enabled": is_editor,
                "tooltip": _("You do not have permission to edit this object")
                if not is_editor
                else None,
            },
            {
                "type": "delete",
                "url": reverse("gift_manager:event_delete", kwargs={"pk": self.object.event_id}),
                "label": _("Delete event"),
                # A global event (Birthday) is visible to everyone: regular users cannot
                # delete it, and there is no access of theirs to remove
                "enabled": is_editor or not self.object.is_global,
                "tooltip": GLOBAL_OBJECT_REMOVAL_ERROR
                if self.object.is_global and not is_editor
                else _(
                    "You do not have permission to delete this object so it will only be "
                    "unshared with you"
                )
                if not is_editor
                else None,
            },
        ]
        if supports_plan_again(self.object):
            context["action_buttons"].insert(
                1,
                {
                    "type": "custom",
                    "url": reverse(
                        "gift_manager:event_plan_again", kwargs={"pk": self.object.event_id}
                    ),
                    "label": _("Plan again"),
                    "icon": "fas fa-rotate-right",
                    "btn_class": "btn-secondary",
                },
            )
        return context


def parse_uuids(raw_values) -> list[uuid.UUID]:
    """Return the valid UUIDs among posted values, ignoring the others."""
    return [uuid.UUID(raw) for raw in raw_values if _is_uuid(raw)]


def _is_uuid(raw) -> bool:
    try:
        uuid.UUID(raw)
    except ValueError:
        return False
    return True


@login_required
@require_http_methods(["GET", "POST"])
def event_plan_again(request, pk):
    """List the last occurrence's plans of a repeating event and recreate the chosen ones."""
    event = get_object_or_404(Event.objects.accessible_by(request.user), event_id=pk)
    if not supports_plan_again(event):
        raise Http404

    if request.method == "POST":
        relation_ids = parse_uuids(request.POST.getlist("relations"))
        created = repeat_plans(request.user, event, relation_ids)
        # The event page lists the new plans, so only the empty outcome needs a message
        if not created:
            messages.info(request, gettext("No gift plan was created."))
        return redirect("gift_manager:event_detail", pk=event.event_id)

    return render(
        request,
        "gift_manager/event_plan_again.html",
        {
            "event": event,
            "candidates": find_repeat_candidates(request.user, event),
        },
    )
