"""Person-related views."""

from django.contrib.postgres.aggregates import JSONBAgg
from django.db.models import F
from django.db.models import Func
from django.db.models import Q
from django.db.models import Value
from django.urls import reverse
from django.urls import reverse_lazy
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from gift_manager.forms import PersonForm
from gift_manager.mixins.fallback_mode import FallbackModeFormMixin
from gift_manager.mixins.fallback_mode import FallbackModeListMixin
from gift_manager.mixins.performance import BatchOperationMixin
from gift_manager.mixins.performance import QueryOptimizationMixin
from gift_manager.mixins.permissions import PermissionContextMixin
from gift_manager.mixins.permissions import PermissionUpdateMixin
from gift_manager.mixins.permissions import SingleObjectPermissionMixin
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import Relation
from gift_manager.models import RelationStatus
from gift_manager.views.base import BaseCreateView
from gift_manager.views.base import BaseDeleteView
from gift_manager.views.base import BaseDetailView
from gift_manager.views.base import BaseListView
from gift_manager.views.base import BaseUpdateView


def get_person_grid_column_names():
    """Return translated column labels for the person management grid."""
    return {
        "first_name": gettext("First name"),
        "family_name": gettext("Family name"),
        "email_address": gettext("Email address"),
        "groups": gettext("Groups"),
    }


def get_person_grid_queryset(user, column_names=None):
    """Return person rows formatted for the shared Grid.js management view."""
    from django.db import connection

    column_names = column_names or get_person_grid_column_names()
    value_fields = [field for field in column_names if field != "groups"]
    base_queryset = (
        Person.objects.accessible_by(user)
        .order_by("family_name", "first_name")
        .values(
            "person_id",
            "user_link_id",
            *value_fields,
        )
    )

    if connection.vendor == "postgresql":
        return base_queryset.annotate(
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
    return base_queryset.prefetch_related("groups")


def populate_person_grid_group_info(data) -> None:
    """Populate group metadata when the database cannot annotate JSON rows."""
    items = [item for item in data if isinstance(item, dict)]
    person_ids = [item.get("person_id") for item in items if not item.get("groups_info")]
    if not person_ids:
        return

    groups_by_person = {person_id: [] for person_id in person_ids}
    for row in (
        Person.objects.filter(person_id__in=person_ids)
        .values("person_id", "groups__group_id", "groups__name")
        .order_by("groups__name")
    ):
        group_id = row["groups__group_id"]
        group_name = row["groups__name"]
        if group_id and group_name:
            groups_by_person[row["person_id"]].append({"id": str(group_id), "name": group_name})

    for item in items:
        if not item.get("groups_info"):
            item["groups_info"] = groups_by_person.get(item["person_id"], [])


class PersonListView(
    FallbackModeListMixin,
    QueryOptimizationMixin,
    BatchOperationMixin,
    PermissionContextMixin,
    BaseListView,
):
    model = Person
    template_name = "gift_manager/person_list.html"
    fallback_template_name = "gift_manager/fallback/list_fallback.html"
    no_js_template_name = "gift_manager/fallback/list_fallback.html"
    object_type = "Persons"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.column_names = get_person_grid_column_names()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        populate_person_grid_group_info(context.get("data", []))
        context["unique_groups"] = (
            PersonGroup.objects.accessible_by(self.request.user)
            .values("name")
            .distinct()
            .order_by("name")
        )

        return context

    def _populate_group_info_fallback(self, data) -> None:
        """Populate group metadata when the database cannot annotate JSON rows."""
        populate_person_grid_group_info(data)

    def get_queryset(self):
        """Return Persons for the current user or shared with the user."""
        return get_person_grid_queryset(self.request.user, self.column_names)

    def get_fallback_columns(self):
        """Get column definitions for fallback table."""
        return [
            {"field": "first_name", "label": _("First Name"), "type": "text"},
            {"field": "family_name", "label": _("Family Name"), "type": "text"},
            {"field": "email_address", "label": _("Email"), "type": "text"},
            {"field": "created_at", "label": _("Created"), "type": "date"},
        ]


class PersonCreateView(FallbackModeFormMixin, QueryOptimizationMixin, BaseCreateView):
    model = Person
    form_class = PersonForm
    success_url = reverse_lazy("gift_manager:persons")
    context_object_name = "person"
    object_type = "Person"
    htmx_template_name = "gift_manager/includes/person_form_partial.html"
    form_fields_template = "gift_manager/includes/forms/person_fields.html"
    form_css_class = "person-form"
    form_type = "person-edit"
    close_offcanvas = True

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["groups"].queryset = PersonGroup.objects.accessible_by(
            self.request.user
        ).order_by("name")
        return form


class PersonUpdateView(
    PermissionUpdateMixin, FallbackModeFormMixin, QueryOptimizationMixin, BaseUpdateView
):
    model = Person
    form_class = PersonForm
    pk_name = "person_id"
    context_object_name = "person"
    object_type = "Person"
    detail_url_name = "person_detail"
    htmx_template_name = "gift_manager/includes/person_form_partial.html"
    form_fields_template = "gift_manager/includes/forms/person_fields.html"
    form_css_class = "person-form"
    form_type = "person-edit"
    close_offcanvas = True

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


class PersonDetailView(QueryOptimizationMixin, SingleObjectPermissionMixin, BaseDetailView):
    model = Person
    template_name = "gift_manager/person_detail.html"
    context_object_name = "person"
    pk_name = "person_id"
    htmx_template_name = "gift_manager/includes/person_detail_partial.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get all groups this person belongs to
        person_groups = list(self.object.groups.all())

        # Get all ancestor groups (parent groups) for inheritance
        all_groups_with_ancestors = set(person_groups)
        ancestor_groups_only = set()
        for group in person_groups:
            ancestors = group.get_ancestors()
            ancestor_groups_only.update(ancestors)
            all_groups_with_ancestors.update(ancestors)

        # Add groups to context for display
        context["direct_groups"] = person_groups
        context["ancestor_groups"] = sorted(ancestor_groups_only, key=lambda g: g.name)

        # Query relations for person directly and all related groups (including ancestors)
        context["relations"] = (
            Relation.objects.accessible_by(self.request.user)
            .filter(Q(person=self.object) | Q(group__in=all_groups_with_ancestors))
            .select_related("status", "gift", "event", "person", "group")
            .prefetch_related("gift__tags")
            .order_by("status__pk", "gift__name")
        )
        context["relation_statuses"] = RelationStatus.objects.all()

        # Build action buttons configuration
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
                    "You do not have permission to delete this object so it will only be "
                    "unshared with you"
                )
                if not is_editor
                else None,
            },
        ]

        return context
