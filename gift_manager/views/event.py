"""Event-related views."""

from django.urls import reverse
from django.urls import reverse_lazy
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from ..forms import EventForm
from ..models import Event
from ..models import Relation
from ..models import RelationStatus
from .base import BaseCreateView
from .base import BaseDeleteView
from .base import BaseDetailView
from .base import BaseListView
from .base import BaseUpdateView


class EventListView(BaseListView):
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
        return Event.objects.accessible_by(self.request.user).values("event_id", *self.column_names)


class EventCreateView(BaseCreateView):
    model = Event
    form_class = EventForm
    success_url = reverse_lazy("gift_manager:events")
    context_object_name = "event"
    object_type = "Event"


class EventUpdateView(BaseUpdateView):
    model = Event
    form_class = EventForm
    pk_name = "event_id"
    context_object_name = "event"
    object_type = "Event"
    detail_url_name = "event_detail"


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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["relations"] = (
            Relation.objects.accessible_by(self.request.user)
            .filter(event=self.object)
            .select_related("person", "group", "gift", "event", "status")
            .order_by("status__pk")
        )
        context["relation_statuses"] = RelationStatus.objects.all()
        context["shared_with"] = self.object.shared_with.exclude(id=self.request.user.id)

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
                    "You do not have permission to delete this object so it will only be unshared with you"
                )
                if not is_editor
                else None,
            },
        ]
        return context
