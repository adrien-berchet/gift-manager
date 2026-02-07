"""Event-related views."""

from django.urls import reverse
from django.urls import reverse_lazy
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from gift_manager.forms import EventForm
from gift_manager.mixins.permissions import PermissionContextMixin
from gift_manager.mixins.permissions import PermissionUpdateMixin
from gift_manager.models import Event
from gift_manager.models import Relation
from gift_manager.models import RelationStatus
from gift_manager.views.base import BaseCreateView
from gift_manager.views.base import BaseDeleteView
from gift_manager.views.base import BaseDetailView
from gift_manager.views.base import BaseListView
from gift_manager.views.base import BaseUpdateView


class EventListView(PermissionContextMixin, BaseListView):
    model = Event
    template_name = "gift_manager/event_list.html"
    object_type = "Events"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.column_names = {
            "name": gettext("Event name"),
            "comment": gettext("Comment"),
            "usual_date": gettext("Usual date"),
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["type"] = "Events"
        context["translated_type"] = gettext("Events")
        context["column_names"] = self.column_names
        return context

    def get_queryset(self):
        """Return Events for the current user or shared with the user."""
        return (
            Event.objects.accessible_by(self.request.user)
            .values("event_id", *self.column_names)
            .order_by("name")
        )


class EventCreateView(BaseCreateView):
    model = Event
    form_class = EventForm
    success_url = reverse_lazy("gift_manager:events")
    context_object_name = "event"
    object_type = "Event"
    htmx_template_name = "gift_manager/includes/event_form_partial.html"


class EventUpdateView(PermissionUpdateMixin, BaseUpdateView):
    model = Event
    form_class = EventForm
    pk_name = "event_id"
    context_object_name = "event"
    object_type = "Event"
    detail_url_name = "event_detail"
    htmx_template_name = "gift_manager/includes/event_form_partial.html"


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
