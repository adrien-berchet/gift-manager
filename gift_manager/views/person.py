"""Person-related views."""

from django.contrib.postgres.aggregates import JSONBAgg
from django.db.models import F
from django.db.models import Func
from django.db.models import Q
from django.db.models import Value
from django.urls import reverse_lazy
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from ..forms import PersonForm
from ..models import Person
from ..models import PersonGroup
from ..models import Relation
from ..models import RelationStatus
from .base import BaseCreateView
from .base import BaseDeleteView
from .base import BaseDetailView
from .base import BaseListView
from .base import BaseUpdateView


class PersonListView(BaseListView):
    model = Person
    template_name = "gift_manager/person_list.html"
    object_type = "Persons"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.column_names = {
            "first_name": gettext("First name"),
            "family_name": gettext("Family name"),
            "email_address": gettext("Email address"),
            "groups": gettext("Groups"),
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["unique_groups"] = (
            PersonGroup.objects.accessible_by(self.request.user)
            .values("name")
            .distinct()
            .order_by("name")
        )

        return context

    def get_queryset(self):
        """Return Persons for the current user or shared with the user."""
        return (
            Person.objects.accessible_by(self.request.user)
            .values("person_id", *list(set(self.column_names.keys()).difference(["groups"])))
            .annotate(
                groups_info=JSONBAgg(
                    Func(
                        Value("id"),
                        F("groups__group_id"),
                        Value("name"),
                        F("groups__name"),
                        function="jsonb_build_object",
                    ),
                    filter=Q(groups__group_id__isnull=False),
                    distinct=True,
                ),
            )
        )


class PersonCreateView(BaseCreateView):
    model = Person
    form_class = PersonForm
    success_url = reverse_lazy("gift_manager:persons")
    context_object_name = "person"
    object_type = "Person"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["groups"].queryset = PersonGroup.objects.accessible_by(
            self.request.user
        ).order_by("name")
        return form


class PersonUpdateView(BaseUpdateView):
    model = Person
    form_class = PersonForm
    pk_name = "person_id"
    context_object_name = "person"
    object_type = "Person"
    detail_url_name = "person_detail"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["groups"].queryset = PersonGroup.objects.accessible_by(
            self.request.user
        ).order_by("name")
        return form


class PersonDeleteView(BaseDeleteView):
    model = Person
    success_url = reverse_lazy("gift_manager:persons")
    pk_name = "person_id"
    object_type = "person"


class PersonDetailView(BaseDetailView):
    model = Person
    template_name = "gift_manager/person_detail.html"
    context_object_name = "person"
    pk_name = "person_id"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["relations"] = (
            Relation.objects.accessible_by(self.request.user)
            .filter(Q(person=self.object) | Q(group__in=self.object.groups.all()))
            .select_related("status", "gift", "event", "person", "group")
            .prefetch_related("gift__tags")
            .order_by("status__pk")
        )
        context["relation_statuses"] = RelationStatus.objects.all()

        # Build action buttons configuration
        from django.urls import reverse

        is_editor = context.get("is_editor", False)

        context["action_buttons"] = [
            {
                "type": "edit",
                "url": reverse("gift_manager:person_edit", kwargs={"pk": self.object.person_id}),
                "label": _("Edit person"),
                "enabled": is_editor,
                "tooltip": _("You do not have permission to edit this object")
                if not is_editor
                else None,
            },
            {
                "type": "delete",
                "url": reverse("gift_manager:person_delete", kwargs={"pk": self.object.person_id}),
                "label": _("Delete person"),
                "enabled": True,  # Always enabled, but tooltip explains behavior
                "tooltip": _(
                    "You do not have permission to delete this object so it will only be unshared with you"
                )
                if not is_editor
                else None,
            },
        ]

        return context
