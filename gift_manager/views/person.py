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
from gift_manager.mixins.performance import OptimizedDetailMixin
from gift_manager.mixins.performance import OptimizedFormMixin
from gift_manager.mixins.performance import OptimizedListMixin
from gift_manager.mixins.progressive_enhancement import ProgressiveEnhancementListMixin
from gift_manager.mixins.progressive_enhancement import ProgressiveEnhancementFormMixin
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import Relation
from gift_manager.models import RelationStatus
from gift_manager.views.base import BaseCreateView
from gift_manager.views.base import BaseDeleteView
from gift_manager.views.base import BaseDetailView
from gift_manager.views.base import BaseListView
from gift_manager.views.base import BaseUpdateView
from gift_manager.mixins.permissions import PermissionContextMixin, SingleObjectPermissionMixin


class PersonListView(ProgressiveEnhancementListMixin, OptimizedListMixin, PermissionContextMixin, BaseListView):
    model = Person
    template_name = "gift_manager/person_list.html"
    fallback_template_name = "gift_manager/fallback/list_fallback.html"
    no_js_template_name = "gift_manager/fallback/list_fallback.html"
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
        from django.db import connection

        base_queryset = (
            Person.objects.accessible_by(self.request.user)
            .order_by("family_name", "first_name")
            .values("person_id", "user_link_id", *list(set(self.column_names.keys()).difference(["groups"])))
        )

        # Use database-specific aggregation
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
        # For SQLite and other databases, use a simpler approach
        return base_queryset.prefetch_related("groups")

    def get_fallback_columns(self):
        """Get column definitions for fallback table."""
        return [
            {'field': 'first_name', 'label': _('First Name'), 'type': 'text'},
            {'field': 'family_name', 'label': _('Family Name'), 'type': 'text'},
            {'field': 'email_address', 'label': _('Email'), 'type': 'text'},
            {'field': 'created_at', 'label': _('Created'), 'type': 'date'},
        ]


class PersonCreateView(ProgressiveEnhancementFormMixin, OptimizedFormMixin, BaseCreateView):
    model = Person
    form_class = PersonForm
    success_url = reverse_lazy("gift_manager:persons")
    context_object_name = "person"
    object_type = "Person"
    htmx_template_name = "gift_manager/includes/person_form_partial.html"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["groups"].queryset = PersonGroup.objects.accessible_by(
            self.request.user
        ).order_by("name")
        return form


class PersonUpdateView(ProgressiveEnhancementFormMixin, OptimizedFormMixin, BaseUpdateView):
    model = Person
    form_class = PersonForm
    pk_name = "person_id"
    context_object_name = "person"
    object_type = "Person"
    detail_url_name = "person_detail"
    htmx_template_name = "gift_manager/includes/person_form_partial.html"

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


class PersonDetailView(OptimizedDetailMixin, SingleObjectPermissionMixin, BaseDetailView):
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
