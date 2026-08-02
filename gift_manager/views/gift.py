"""Gift-related views."""

from django.contrib.postgres.aggregates import JSONBAgg
from django.db.models import F
from django.db.models import Func
from django.db.models import Q
from django.db.models import Value
from django.shortcuts import render
from django.urls import reverse
from django.urls import reverse_lazy
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from gift_manager.forms import GiftForm
from gift_manager.forms import GiftRelationForm
from gift_manager.mixins.performance import BatchOperationMixin
from gift_manager.mixins.performance import QueryOptimizationMixin
from gift_manager.mixins.permissions import PermissionContextMixin
from gift_manager.mixins.permissions import PermissionUpdateMixin
from gift_manager.mixins.permissions import SingleObjectPermissionMixin
from gift_manager.mixins.progressive_enhancement import ProgressiveEnhancementFormMixin
from gift_manager.mixins.progressive_enhancement import ProgressiveEnhancementListMixin
from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import GiftTag
from gift_manager.models import Relation
from gift_manager.models import RelationStatus
from gift_manager.permissions import PERMISSION_LEVELS
from gift_manager.views.base import BaseCreateView
from gift_manager.views.base import BaseDeleteView
from gift_manager.views.base import BaseDetailView
from gift_manager.views.base import BaseListView
from gift_manager.views.base import BaseUpdateView


class GiftListView(
    ProgressiveEnhancementListMixin,
    QueryOptimizationMixin,
    BatchOperationMixin,
    PermissionContextMixin,
    BaseListView,
):
    model = Gift
    template_name = "gift_manager/gift_list.html"
    fallback_template_name = "gift_manager/fallback/list_fallback.html"
    no_js_template_name = "gift_manager/fallback/list_fallback.html"
    object_type = "Gifts"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.column_names = {
            "name": gettext("Gift name"),
            "comment": gettext("Comment"),
            "tags": gettext("Tags"),
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["unique_tags"] = (
            GiftTag.objects.accessible_by(self.request.user)
            .values("name")
            .distinct()
            .order_by("name")
        )
        return context

    def get_queryset(self):
        """Return Gifts for the current user or shared with the user."""
        from django.db import connection

        base_queryset = Gift.objects.accessible_by(self.request.user).order_by("name")

        # Use database-specific aggregation
        if connection.vendor == "postgresql":
            return base_queryset.annotate(
                tags_info=JSONBAgg(
                    Func(
                        Value("id"),
                        F("tags__tag_id"),
                        Value("name"),
                        F("tags__name"),
                        function="jsonb_build_object",
                    ),
                    filter=Q(tags__tag_id__isnull=False),
                    distinct=True,
                ),
            ).values("gift_id", "name", "comment", "tags_info")
        # For SQLite and other databases, use a simpler approach
        return base_queryset.prefetch_related("tags").values("gift_id", "name", "comment")

    def get_fallback_columns(self):
        """Get column definitions for fallback table."""
        return [
            {"field": "name", "label": _("Gift name"), "type": "text"},
            {"field": "comment", "label": _("Comment"), "type": "text"},
        ]


class GiftCreateView(ProgressiveEnhancementFormMixin, QueryOptimizationMixin, BaseCreateView):
    model = Gift
    form_class = GiftForm
    success_url = reverse_lazy("gift_manager:gifts")
    context_object_name = "gift"
    object_type = "Gift"
    htmx_template_name = "gift_manager/includes/gift_form_partial.html"
    form_fields_template = "gift_manager/includes/forms/gift_fields.html"
    form_css_class = "gift-form"
    form_type = "gift"
    close_offcanvas = True
    create_gift_plan_action = "create_gift_plan"
    gift_plan_template_name = "gift_manager/includes/relation_form_partial.html"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["tags"].queryset = GiftTag.objects.accessible_by(self.request.user).order_by(
            "name"
        )
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["secondary_submit_actions"] = [
            {
                "name": "after_save",
                "value": self.create_gift_plan_action,
                "label": _("Save and create gift plan"),
                "icon": "fas fa-gift",
                "css_class": "btn btn-outline-primary form-secondary-submit-action",
            }
        ]
        return context

    def should_create_gift_plan_after_save(self) -> bool:
        return self.request.POST.get("after_save") == self.create_gift_plan_action

    def get_success_url(self):
        if self.should_create_gift_plan_after_save():
            return reverse("gift_manager:gift_relation_create", kwargs={"pk": self.object.gift_id})
        return super().get_success_url()

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.is_htmx and self.should_create_gift_plan_after_save():
            return self.render_gift_plan_form_after_create()
        return response

    def render_gift_plan_form_after_create(self):
        form = GiftRelationForm(gift_id=self.object.gift_id, user=self.request.user)
        form.fields["event"].queryset = Event.objects.accessible_by(self.request.user).order_by(
            "name"
        )
        self.get_initial()

        context = {
            "form": form,
            "object": None,
            "type": gettext("Gift Plan"),
            "translated_type": gettext("Gift Plan"),
            "action": gettext("Create"),
            "cancel_url": reverse("gift_manager:gift_detail", kwargs={"pk": self.object.gift_id}),
            "form_action_url": self.get_success_url(),
            "form_fields_template": "gift_manager/includes/forms/relation_fields.html",
            "form_css_class": "relation-form",
            "form_type": "relation",
            "form_surface": "offcanvas",
            "sharing_mode": "create",
            "show_sharing_section": True,
            "unshared_friends": getattr(self, "unshared_friends", []),
            "permission_levels": [
                {"value": level["value"], "label": str(level["label"])}
                for level in PERMISSION_LEVELS
            ],
        }
        response = render(self.request, self.gift_plan_template_name, context)
        triggers = ["list:update"]
        success_message = self.get_success_message()
        if success_message:
            triggers.append({"showNotification": {"message": success_message, "type": "success"}})
        response["HX-Trigger"] = self.build_hx_trigger_header(triggers)
        return response


class GiftUpdateView(
    PermissionUpdateMixin, ProgressiveEnhancementFormMixin, QueryOptimizationMixin, BaseUpdateView
):
    model = Gift
    form_class = GiftForm
    pk_name = "gift_id"
    context_object_name = "gift"
    object_type = "Gift"
    detail_url_name = "gift_detail"
    htmx_template_name = "gift_manager/includes/gift_form_partial.html"
    form_fields_template = "gift_manager/includes/forms/gift_fields.html"
    form_css_class = "gift-form"
    form_type = "gift"
    close_offcanvas = True

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["tags"].queryset = GiftTag.objects.accessible_by(self.request.user).order_by(
            "name"
        )
        return form


class GiftDeleteView(BaseDeleteView):
    model = Gift
    success_url = reverse_lazy("gift_manager:gifts")
    pk_name = "gift_id"
    object_type = "gift"


class GiftDetailView(SingleObjectPermissionMixin, BaseDetailView):
    model = Gift
    template_name = "gift_manager/gift_detail.html"
    context_object_name = "gift"
    pk_name = "gift_id"
    htmx_template_name = "gift_manager/includes/gift_detail_partial.html"

    def get_context_data(self, **kwargs) -> dict:
        context = super().get_context_data(**kwargs)
        context["relations"] = (
            Relation.objects.accessible_by(self.request.user)
            .filter(gift=self.object)
            .select_related("status", "person", "group", "event")
            .order_by(
                "status__pk",
                "person__first_name",
                "person__family_name",
                "group__name",
                "event__name",
            )
        )
        context["relation_statuses"] = RelationStatus.objects.all()

        # Add action buttons
        is_editor = context["is_editor"]
        context["action_buttons"] = [
            {
                "type": "edit",
                "url": reverse("gift_manager:gift_edit", kwargs={"pk": self.object.gift_id}),
                "label": _("Edit gift"),
                "enabled": is_editor,
                "tooltip": _("You do not have permission to edit this object")
                if not is_editor
                else None,
            },
            {
                "type": "delete",
                "url": reverse("gift_manager:gift_delete", kwargs={"pk": self.object.gift_id}),
                "label": _("Delete gift"),
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
