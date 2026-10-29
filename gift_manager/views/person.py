"""Person-related views."""

from functools import cached_property

from django.contrib import messages
from django.contrib.postgres.aggregates import JSONBAgg
from django.core.exceptions import ValidationError
from django.db.models import F
from django.db.models import Func
from django.db.models import Q
from django.db.models import Value
from django.urls import reverse
from django.urls import reverse_lazy
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from gift_manager import account_links
from gift_manager.account_links import LinkRefused
from gift_manager.account_links import clean_person_email
from gift_manager.account_links import format_link_label
from gift_manager.account_links import link_suggestion
from gift_manager.email_encoding import decode_email
from gift_manager.forms import PersonForm
from gift_manager.invitations import best_email_for_account
from gift_manager.invitations import user_has_email
from gift_manager.invitations import user_is_friends_with_email
from gift_manager.metadata_visibility import VisibleMetadata
from gift_manager.mixins.fallback_mode import FallbackModeFormMixin
from gift_manager.mixins.fallback_mode import FallbackModeListMixin
from gift_manager.mixins.performance import QueryOptimizationMixin
from gift_manager.mixins.permissions import PermissionContextMixin
from gift_manager.mixins.permissions import PermissionUpdateMixin
from gift_manager.mixins.permissions import SingleObjectPermissionMixin
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import Profile
from gift_manager.models import Relation
from gift_manager.models import RelationStatus
from gift_manager.services import BudgetService
from gift_manager.statuses import is_abandoned_status
from gift_manager.statuses import is_given_status
from gift_manager.statuses import is_terminal_status
from gift_manager.views.base import BaseCreateView
from gift_manager.views.base import BaseDeleteView
from gift_manager.views.base import BaseDetailView
from gift_manager.views.base import BaseListView
from gift_manager.views.base import BaseUpdateView
from gift_manager.views.base import QueryStringPrefillMixin
from gift_manager.views.suggestions import suggestions_url_for


def get_person_grid_column_names():
    """Return translated column labels for the person management grid."""
    return {
        "first_name": gettext("First name"),
        "family_name": gettext("Family name"),
        "email_address": gettext("Email address"),
        "groups": gettext("Groups"),
    }


def get_person_grid_queryset(user, column_names=None, accessible_groups=None):
    """Return person rows formatted for the shared Grid.js management view."""
    from django.db import connection

    column_names = column_names or get_person_grid_column_names()
    if accessible_groups is None:
        accessible_groups = PersonGroup.objects.accessible_by(user)
    accessible_group_ids = accessible_groups.values("pk")
    value_fields = [field for field in column_names if field != "groups"]
    base_queryset = (
        Person.objects.accessible_by(user)
        .order_by("family_name", "first_name")
        .values(
            "person_id",
            *value_fields,
            "account_id",
            "account__username",
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
                filter=Q(groups__group_id__isnull=False, groups__pk__in=accessible_group_ids),
                distinct=True,
            ),
        )
    return base_queryset.prefetch_related("groups")


def populate_person_grid_group_info(data, user, accessible_groups=None) -> None:
    """Populate group metadata when the database cannot annotate JSON rows."""
    items = [item for item in data if isinstance(item, dict)]
    person_ids = [item.get("person_id") for item in items if not item.get("groups_info")]
    if not person_ids:
        return

    if accessible_groups is None:
        accessible_groups = PersonGroup.objects.accessible_by(user)
    accessible_group_ids = accessible_groups.values("pk")
    groups_by_person = {person_id: [] for person_id in person_ids}
    for row in (
        Person.objects.filter(person_id__in=person_ids)
        .filter(groups__pk__in=accessible_group_ids)
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


def get_person_grid_data(items, viewer=None) -> list:
    """Format person items into rows for Grid.js."""
    rows = []
    for item in items:
        person_id = str(item.get("person_id") or "")
        groups_info = [
            {
                "id": str(group["id"]),
                "name": str(group["name"]),
                "url": reverse("gift_manager:person_group_detail", args=[group["id"]]),
            }
            for group in item.get("groups_info") or []
        ]
        raw_email = item.get("email_address")
        email = decode_email(raw_email) if raw_email else ""
        link_label = format_link_label(
            item.get("account_id"),
            item.get("account__username"),
            viewer,
        )
        rows.append(
            [
                "",  # Checkbox placeholder - Index 0
                item.get("first_name") or "",  # Index 1
                item.get("family_name") or "",  # Index 2
                email or "",  # Index 3
                groups_info,  # Index 4
                person_id,  # Index 5
                reverse("gift_manager:person_relation_create", args=[person_id]),  # Index 6
                reverse("gift_manager:person_detail", args=[person_id]),  # Index 7
                reverse("gift_manager:person_edit", args=[person_id]),  # Index 8
                reverse("gift_manager:person_delete", args=[person_id]),  # Index 9
                link_label,  # Index 10
            ]
        )
    return rows


class PersonListView(
    FallbackModeListMixin,
    QueryOptimizationMixin,
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

    def get_grid_data(self, items) -> list:
        """Format person items into rows for Grid.js."""
        viewer = getattr(self.request, "user", None) if hasattr(self, "request") else None
        return get_person_grid_data(items, viewer=viewer)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        items = context.get("data", [])
        populate_person_grid_group_info(items, self.request.user)
        context["unique_groups"] = (
            PersonGroup.objects.accessible_by(self.request.user)
            .values("name")
            .distinct()
            .order_by("name")
        )
        context["grid_data"] = self.get_grid_data(items)
        return context

    def _populate_group_info_fallback(self, data) -> None:
        """Populate group metadata when the database cannot annotate JSON rows."""
        populate_person_grid_group_info(data, self.request.user)

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

    def get_fallback_field_value(self, obj, field_name: str) -> object:
        """Return fallback cell values, decoding the stored (encrypted) email."""
        value = super().get_fallback_field_value(obj, field_name)
        if field_name == "email_address":
            return decode_email(value) or ""
        return value


class PersonCreateView(
    QueryStringPrefillMixin, FallbackModeFormMixin, QueryOptimizationMixin, BaseCreateView
):
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
    prefill_fields = {"name": "first_name"}

    @cached_property
    def link_friend(self) -> Profile | None:
        """Resolve the friend profile specified in link_to query or POST data."""
        raw_val = self.request.POST.get("link_to") or self.request.GET.get("link_to")
        if not raw_val:
            return None
        try:
            profile_pk = int(raw_val)
        except (ValueError, TypeError, OverflowError):
            return None

        if not self.request.user.is_authenticated:
            return None

        try:
            return (
                Profile.objects.select_related("user")
                .filter(pk=profile_pk, friends=self.request.user.profile)
                .first()
            )
        except (AttributeError, Profile.DoesNotExist):
            return None

    def get_initial(self):
        initial = super().get_initial()
        friend_profile = self.link_friend
        if friend_profile:
            friend_user = friend_profile.user
            first_name = friend_user.first_name or ""
            family_name = friend_user.last_name or ""
            if not first_name and not family_name:
                first_name = friend_user.username
            initial["first_name"] = first_name
            initial["family_name"] = family_name
            best_email = best_email_for_account(friend_user)
            if best_email:
                initial["email_address"] = best_email

        group_id = self.request.GET.get("group")
        if not group_id:
            return initial

        try:
            group = PersonGroup.objects.accessible_by(self.request.user).get(group_id=group_id)
        except (PersonGroup.DoesNotExist, ValidationError, ValueError):
            return initial

        initial["groups"] = [group.pk]
        return initial

    def get_context_data(self, **kwargs) -> dict:
        context = super().get_context_data(**kwargs)
        context["link_friend"] = self.link_friend
        return context

    def get_success_url(self) -> str:
        if self.link_friend:
            return reverse("gift_manager:profile_detail")
        return super().get_success_url()

    def form_valid(self, form):
        response = super().form_valid(form)
        friend_profile = self.link_friend
        if friend_profile:
            try:
                account_links.link(self.object, friend_profile.user, self.request.user)
                messages.success(
                    self.request,
                    _("Linked to %(username)s.") % {"username": friend_profile.user.username},
                )
            except LinkRefused as exc:
                msg = exc.message if hasattr(exc, "message") else str(exc)
                messages.warning(self.request, msg)
        return response

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.set_user(self.request.user)
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
        form.set_user(self.request.user)
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
    select_related_fields = ["account"]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        visible_group_ids = VisibleMetadata.for_request(self.request).group_ids

        # Get all groups this person belongs to
        person_groups = list(self.object.groups.all())

        # The person's groups and all their ancestors, for the inherited plans
        all_groups_with_ancestors = PersonGroup.hierarchy_subquery(
            person_groups, ancestors=True, include_start=True
        )
        # Only expose ancestors reached through groups the user can see
        visible_groups = [g for g in person_groups if g.pk in visible_group_ids]
        ancestor_groups_only = PersonGroup.objects.filter(
            pk__in=PersonGroup.hierarchy_subquery(visible_groups, ancestors=True)
        ).filter(pk__in=visible_group_ids)

        # Add groups to context for display, limited to the groups the user can see
        context["direct_groups"] = [g for g in person_groups if g.pk in visible_group_ids]
        context["ancestor_groups"] = sorted(ancestor_groups_only, key=lambda g: g.name)

        # Query relations for person directly and all related groups (including ancestors)
        relations = list(
            Relation.objects.accessible_by(self.request.user)
            .filter(Q(person=self.object) | Q(group__in=all_groups_with_ancestors))
            .select_related("status", "gift", "event", "person", "group", "claimed_by")
            .prefetch_related("gift__tags")
            .order_by("status__pk", "gift__name")
        )
        # Given plans live in the gift history and abandoned ones in their own section:
        # each plan is shown once.
        context["relations"] = [r for r in relations if not is_terminal_status(r.status)]
        context["abandoned_relations"] = [r for r in relations if is_abandoned_status(r.status)]
        context["given_count"] = sum(1 for r in relations if is_given_status(r.status))
        context["relation_statuses"] = RelationStatus.objects.all()
        context["budget"] = BudgetService.for_person(self.request.user, self.object)
        context["gift_history_url"] = reverse(
            "gift_manager:person_gift_history", kwargs={"pk": self.object.person_id}
        )
        context["suggestions_url"] = suggestions_url_for(self.object)
        # Interests are gift tags: only the ones the viewer can see are shown
        visible_tag_ids = VisibleMetadata.for_request(self.request).tag_ids
        context["interests"] = sorted(
            (tag for tag in self.object.interests.all() if tag.pk in visible_tag_ids),
            key=lambda tag: tag.name.lower(),
        )
        context["link_suggestion"] = link_suggestion(self.object, self.request.user)

        # Build action buttons configuration
        is_editor = context.get("is_editor", False)

        action_buttons = [
            {
                "type": "edit",
                "url": reverse("gift_manager:person_edit", kwargs={"pk": self.object.person_id}),
                "label": _("Edit person"),
                "enabled": is_editor,
                "tooltip": _("You do not have permission to edit this object")
                if not is_editor
                else None,
            },
        ]
        if is_editor:
            action_buttons.append(
                {
                    "type": "custom",
                    "url": reverse(
                        "gift_manager:person_link_account",
                        kwargs={"pk": self.object.person_id},
                    ),
                    "label": _("Change link") if self.object.account_id else _("Link account"),
                    "icon": "fas fa-link",
                    "btn_class": "btn-outline-secondary",
                }
            )
            clean_email = (
                clean_person_email(self.object) if self.object.account_id is None else None
            )
            if (
                clean_email
                and not user_has_email(self.request.user, clean_email)
                and not user_is_friends_with_email(self.request.user, clean_email)
            ):
                action_buttons.append(
                    {
                        "type": "custom",
                        "url": reverse("gift_manager:send_invitation")
                        + f"?person={self.object.person_id}",
                        "label": _("Invite to Gift Manager"),
                        "icon": "fas fa-envelope",
                        "btn_class": "btn-outline-secondary",
                    }
                )
        action_buttons.append(
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
            }
        )

        context["action_buttons"] = action_buttons

        return context
