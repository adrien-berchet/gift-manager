"""Event-related views."""

from django.db.models import Case, IntegerField, Value, When
from django.urls import reverse_lazy
from django.utils.translation import gettext

from ..forms import EventForm
from ..models import Event, Relation, RelationStatus
from .base import BaseCreateView, BaseDeleteView, BaseDetailView, BaseListView, BaseUpdateView


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
            .annotate(
                status_order=Case(
                    When(status__status__iexact="idea", then=Value(0)),
                    When(status__status__iexact="to buy", then=Value(1)),
                    When(status__status__iexact="bought", then=Value(2)),
                    When(status__status__iexact="given", then=Value(3)),
                    default=Value(99),
                    output_field=IntegerField(),
                )
            )
            .order_by("status_order", "status__status")
        )
        context["relation_statuses"] = RelationStatus.objects.all()
        context["shared_with"] = self.object.shared_with.exclude(id=self.request.user.id)
        return context
