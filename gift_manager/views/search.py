"""HTMX-powered search functionality for real-time filtering."""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import JsonResponse
from django.views import View

from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import GiftTag
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import Relation


class HTMXSearchMixin:
    """Mixin to add HTMX search functionality to list views."""

    search_fields = []  # Define in subclasses

    def get_search_queryset(self, queryset, search_term):
        """Filter queryset based on search term."""
        if not search_term or not self.search_fields:
            return queryset

        # Build Q object for OR search across all search fields
        search_q = Q()
        for field in self.search_fields:
            search_q |= Q(**{f"{field}__icontains": search_term})

        return queryset.filter(search_q)

    def get_queryset(self):
        """Override to add search filtering."""
        queryset = super().get_queryset()
        search_term = self.request.GET.get("search", "").strip()

        if search_term:
            queryset = self.get_search_queryset(queryset, search_term)

        return queryset

    def get_context_data(self, **kwargs):
        """Add search term to context."""
        context = super().get_context_data(**kwargs)
        context["search_term"] = self.request.GET.get("search", "")
        return context


class HTMXListSearchView(LoginRequiredMixin, HTMXSearchMixin, View):
    """Base view for HTMX search requests."""

    model = None
    template_name = None
    search_fields = []
    context_object_name = "data"

    def get_queryset(self):
        """Get base queryset for the model with user filtering."""
        # Use the model's manager method for proper user filtering
        if hasattr(self.model.objects, "accessible_by"):
            return self.model.objects.accessible_by(self.request.user)
        # Fallback for models without accessible_by method
        return self.model.objects.filter(user_link=self.request.user)

    def get_search_data(self, queryset):
        """Convert queryset to data format expected by templates."""
        # This should be overridden in subclasses to match the format
        # used in the original list views
        return list(queryset.values())

    def get(self, request, *args, **kwargs):
        """Handle HTMX search requests."""
        search_term = request.GET.get("search", "").strip()

        # Get base queryset
        queryset = self.get_queryset()

        # Apply search filtering
        if search_term:
            queryset = self.get_search_queryset(queryset, search_term)

        # Convert to data format
        data = self.get_search_data(queryset)

        # Return JSON response for HTMX
        return JsonResponse({"data": data, "count": len(data), "search_term": search_term})


class PersonSearchView(HTMXListSearchView):
    """HTMX search view for persons."""

    model = Person
    search_fields = ["first_name", "family_name", "email_address"]

    def get_search_data(self, queryset):
        """Convert person queryset to data format."""
        data = []
        for person in queryset:
            # Get groups info
            groups_info = []
            for group in person.groups.all():
                groups_info.append({"id": str(group.person_group_id), "name": group.name})

            data.append(
                {
                    "person_id": str(person.person_id),
                    "first_name": person.first_name,
                    "family_name": person.family_name,
                    "email_address": person.email_address or "",
                    "groups_info": groups_info,
                }
            )

        return data


class GiftSearchView(HTMXListSearchView):
    """HTMX search view for gifts."""

    model = Gift
    search_fields = ["name", "comment"]

    def get_search_data(self, queryset):
        """Convert gift queryset to data format."""
        data = []
        for gift in queryset:
            # Get tags info
            tags_info = []
            for tag in gift.tags.all():
                tags_info.append({"id": str(tag.gift_tag_id), "name": tag.name})

            data.append(
                {
                    "gift_id": str(gift.gift_id),
                    "name": gift.name,
                    "comment": gift.comment or "",
                    "tags_info": tags_info,
                }
            )

        return data


class EventSearchView(HTMXListSearchView):
    """HTMX search view for events."""

    model = Event
    search_fields = ["name", "comment"]

    def get_search_data(self, queryset):
        """Convert event queryset to data format."""
        data = []
        for event in queryset:
            data.append(
                {
                    "event_id": str(event.event_id),
                    "name": event.name,
                    "comment": event.comment or "",
                    "usual_date": event.usual_date,
                    "absolute_date": event.absolute_date,
                    "recurrence": event.recurrence,
                }
            )

        return data


class RelationSearchView(HTMXListSearchView):
    """HTMX search view for relations."""

    model = Relation
    search_fields = ["person__first_name", "person__family_name", "gift__name", "event__name"]

    def get_search_data(self, queryset):
        """Convert relation queryset to data format."""
        data = []
        for relation in queryset:
            data.append(
                {
                    "relation_id": str(relation.relation_id),
                    "person_name": f"{relation.person.first_name} {relation.person.family_name}",
                    "gift_name": relation.gift.name if relation.gift else "",
                    "event_name": relation.event.name if relation.event else "",
                    "status": relation.status.status if relation.status else "",
                }
            )

        return data


class PersonGroupSearchView(HTMXListSearchView):
    """HTMX search view for person groups."""

    model = PersonGroup
    search_fields = ["name"]

    def get_search_data(self, queryset):
        """Convert person group queryset to data format."""
        data = []
        for group in queryset:
            data.append(
                {
                    "person_group_id": str(group.group_id),
                    "name": group.name,
                    "comment": "",  # PersonGroup doesn't have comment field, use empty string
                }
            )

        return data


class GiftTagSearchView(HTMXListSearchView):
    """HTMX search view for gift tags."""

    model = GiftTag
    search_fields = ["name"]

    def get_search_data(self, queryset):
        """Convert gift tag queryset to data format."""
        data = []
        for tag in queryset:
            data.append({"gift_tag_id": str(tag.tag_id), "name": tag.name})

        return data
