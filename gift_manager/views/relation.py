"""Relation-related views."""

from datetime import timedelta
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.db.models import Case
from django.db.models import CharField
from django.db.models import Q
from django.db.models import TextField
from django.db.models import Value
from django.db.models import When
from django.db.models.functions import Coalesce
from django.db.models.functions import Concat
from django.db.models.functions import NullIf
from django.http import HttpResponse
from django.http import JsonResponse
from django.urls import reverse
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.html import conditional_escape
from django.utils.text import slugify
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from django.views.decorators.http import require_POST
from django.views.generic import DetailView

from gift_manager.forms import GiftRelationForm
from gift_manager.forms import PersonGroupRelationForm
from gift_manager.forms import PersonRelationForm
from gift_manager.forms import RelationForm
from gift_manager.mixins.permissions import PermissionContextMixin
from gift_manager.mixins.permissions import PermissionUpdateMixin
from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import PermissionLevel
from gift_manager.models import Relation
from gift_manager.models import RelationStatus
from gift_manager.services import PermissionService
from gift_manager.views.base import BaseCreateView
from gift_manager.views.base import BaseDeleteView
from gift_manager.views.base import BaseDetailView
from gift_manager.views.base import BaseListView
from gift_manager.views.base import BaseUpdateView

COMPLETED_STATUS_SLUGS = {"given", "done", "completed"}


def gift_plan_status_class(status) -> str:
    """Return the shared CSS status class for a gift plan status."""
    slug = slugify(str(status or "")) or "unknown"
    return f"gift-plan-status--{slug}"


def is_completed_status(status) -> bool:
    """Return whether a status should be treated as completed in workspace grouping."""
    slug = slugify(str(status or ""))
    return slug in COMPLETED_STATUS_SLUGS


def gift_plan_urgency_key(relation, *, today=None, window_days=7) -> str:
    """Return the urgency bucket for a gift plan."""
    today = today or timezone.localdate()
    if is_completed_status(relation.status):
        return "completed"
    if relation.due_date is None:
        return "no_date"
    if relation.due_date < today:
        return "overdue"
    if relation.due_date <= today + timedelta(days=window_days):
        return "due_soon"
    return "later"


class PersonRelationCreateView(BaseCreateView):
    model = Relation
    form_class = PersonRelationForm
    context_object_name = "relation"
    object_type = gettext_noop("Gift Plan")
    htmx_template_name = "gift_manager/includes/relation_form_partial.html"
    form_fields_template = "gift_manager/includes/forms/relation_fields.html"
    form_css_class = "relation-form"
    form_type = "relation"

    def get_success_url(self):
        return reverse("gift_manager:person_detail", kwargs={"pk": self.kwargs["pk"]})

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["person_id"] = self.kwargs["pk"]  # Pass the person ID to the form
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form_action_url"] = reverse(
            "gift_manager:person_relation_create", kwargs={"pk": self.kwargs["pk"]}
        )
        return context

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["gift"].queryset = Gift.objects.accessible_by(self.request.user).order_by(
            "name"
        )
        form.fields["event"].queryset = Event.objects.accessible_by(self.request.user).order_by(
            "name"
        )
        return form


class PersonGroupRelationCreateView(BaseCreateView):
    model = Relation
    form_class = PersonGroupRelationForm
    context_object_name = "relation"
    object_type = gettext_noop("Gift Plan")
    htmx_template_name = "gift_manager/includes/relation_form_partial.html"
    form_fields_template = "gift_manager/includes/forms/relation_fields.html"
    form_css_class = "relation-form"
    form_type = "relation"

    def get_success_url(self):
        url = reverse("gift_manager:person_group_detail", kwargs={"pk": self.kwargs["pk"]})
        query = urlencode({"tab": "gifts"})
        return f"{url}?{query}"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["group_id"] = self.kwargs["pk"]  # Pass the group ID to the form
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form_action_url"] = reverse(
            "gift_manager:person_group_relation_create", kwargs={"pk": self.kwargs["pk"]}
        )
        return context

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["gift"].queryset = Gift.objects.accessible_by(self.request.user).order_by(
            "name"
        )
        form.fields["event"].queryset = Event.objects.accessible_by(self.request.user).order_by(
            "name"
        )
        return form


class GiftRelationCreateView(BaseCreateView):
    model = Relation
    form_class = GiftRelationForm
    context_object_name = "relation"
    object_type = gettext_noop("Gift Plan")
    htmx_template_name = "gift_manager/includes/relation_form_partial.html"
    form_fields_template = "gift_manager/includes/forms/relation_fields.html"
    form_css_class = "relation-form"
    form_type = "relation"

    def get_success_url(self):
        return reverse("gift_manager:gift_detail", kwargs={"pk": self.kwargs["pk"]})

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["gift_id"] = self.kwargs["pk"]  # Pass the gift ID to the form
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form_action_url"] = reverse(
            "gift_manager:gift_relation_create", kwargs={"pk": self.kwargs["pk"]}
        )
        return context

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["event"].queryset = Event.objects.accessible_by(self.request.user).order_by(
            "name"
        )
        return form


class GiftRelationDeleteView(BaseDeleteView):
    model = Relation
    pk_name = "relation_id"
    object_type = "relation"
    display_object_type = gettext_noop("gift plan")

    def get_success_url(self):
        url = reverse("gift_manager:person_group_detail", kwargs={"pk": self.kwargs["pk"]})
        query = urlencode({"tab": "gifts"})
        return f"{url}?{query}"


class RelationStatusListView(BaseListView):
    model = RelationStatus
    template_name = "gift_manager/status_list.html"
    object_type = "Status"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.column_names = {
            "status": gettext("Status"),
        }

    def get_queryset(self):
        """Return RelationStatus."""
        return RelationStatus.objects.values("pk", *self.column_names).order_by("pk")


class RelationStatusDetailView(BaseDetailView):
    model = RelationStatus
    template_name = "gift_manager/relation_status_detail.html"
    context_object_name = "status"
    pk_name = "pk"  # RelationStatus uses default 'id' field, not 'status_id'

    def get_queryset(self):
        """Return all RelationStatus objects without user filtering.

        RelationStatus is a global lookup table shared by all users,
        so it doesn't have a 'shared_with' field.
        """
        return RelationStatus.objects.all()

    def get_context_data(self, **kwargs):
        # Skip BaseDetailView's mixins that expect 'shared_with' field
        # Call DetailView's get_context_data directly
        context = DetailView.get_context_data(self, **kwargs)

        # Add relations that have this status (filtered by user)
        # Use with_related_objects() to avoid N+1 queries when accessing
        # person, group, gift, event in the template
        context["relations"] = (
            Relation.objects.accessible_by(self.request.user)
            .with_related_objects()
            .filter(status=self.object)
        )
        return context


class RelationListView(PermissionContextMixin, BaseListView):
    model = Relation
    template_name = "gift_manager/relation_list.html"
    object_type = gettext_noop("Gift Plans")
    workspace_window_days = 7
    workspace_group_order = ("overdue", "due_soon", "later", "no_date", "completed")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.column_names = {
            "gift__name": gettext("Gift"),
            "comment": gettext("Comment"),
            "related_object": gettext("Recipient"),
            "event": gettext("Event"),
            "status__status": gettext("Status"),
            "due_date": gettext("Due date"),
        }

    def get_queryset(self):
        return (
            Relation.objects.accessible_by(self.request.user)
            .annotate(
                related_object=Coalesce(
                    NullIf(
                        Concat(
                            "person__first_name",
                            Value(" "),
                            "person__family_name",
                            output_field=TextField(),
                        ),
                        Value(" "),
                    ),
                    "group__name",
                    output_field=TextField(),
                ),
                recipient_type=Case(
                    When(person__isnull=False, then=Value("person")),
                    default=Value("group"),
                    output_field=CharField(),
                ),
            )
            .order_by("status__pk", "person__first_name", "person__family_name", "gift__name")
            .values(
                "relation_id",
                "gift__name",
                "gift__gift_id",
                "comment",
                "related_object",
                "recipient_type",
                "person__person_id",
                "group__group_id",
                "event__name",
                "event__event_id",
                "status",
                "due_date",
            )
        )

    def get_workspace_queryset(self):
        """Return relation instances optimized for the card workspace."""
        return (
            Relation.objects.accessible_by(self.request.user)
            .with_related_objects()
            .prefetch_related("gift__tags")
            .order_by("due_date", "status__pk", "gift__name")
        )

    def get_workspace_groups(self, relations):
        """Group gift plans by urgency for the primary workspace."""
        today = timezone.localdate()
        groups = {
            "overdue": {
                "key": "overdue",
                "label": gettext("Overdue"),
                "description": gettext("Due before today"),
                "icon": "fa-triangle-exclamation",
                "cards": [],
            },
            "due_soon": {
                "key": "due_soon",
                "label": gettext("Due soon"),
                "description": gettext("Due in the next 7 days"),
                "icon": "fa-clock",
                "cards": [],
            },
            "later": {
                "key": "later",
                "label": gettext("Later"),
                "description": gettext("Due after the next 7 days"),
                "icon": "fa-calendar",
                "cards": [],
            },
            "no_date": {
                "key": "no_date",
                "label": gettext("No due date"),
                "description": gettext("Needs a deadline"),
                "icon": "fa-calendar-plus",
                "cards": [],
            },
            "completed": {
                "key": "completed",
                "label": gettext("Completed"),
                "description": gettext("Already given or finished"),
                "icon": "fa-circle-check",
                "cards": [],
            },
        }

        for relation in relations:
            card = self.get_workspace_card(relation, today)
            groups[card["urgency_key"]]["cards"].append(card)

        return [groups[key] for key in self.workspace_group_order if groups[key]["cards"]]

    def get_workspace_card(self, relation, today):
        """Return presentation data for a single gift-plan card."""
        urgency_key = gift_plan_urgency_key(
            relation,
            today=today,
            window_days=self.workspace_window_days,
        )
        permission = PermissionService.get_permission(relation, self.request.user)
        return {
            "relation": relation,
            "urgency_key": urgency_key,
            "status_class": gift_plan_status_class(relation.status),
            "detail_url": reverse(
                "gift_manager:relation_detail", kwargs={"pk": relation.relation_id}
            ),
            "edit_url": reverse("gift_manager:relation_edit", kwargs={"pk": relation.relation_id}),
            "delete_url": reverse(
                "gift_manager:relation_delete", kwargs={"pk": relation.relation_id}
            ),
            "can_edit": permission >= PermissionLevel.EDITOR,
            "can_delete": permission >= PermissionLevel.OWNER,
        }

    def get_workspace_summary(self, workspace_groups):
        """Return compact counts for the workspace summary strip."""
        counts = {group["key"]: len(group["cards"]) for group in workspace_groups}
        total = sum(counts.values())
        attention = counts.get("overdue", 0) + counts.get("due_soon", 0)
        return {
            "total": total,
            "attention": attention,
            "overdue": counts.get("overdue", 0),
            "due_soon": counts.get("due_soon", 0),
            "no_date": counts.get("no_date", 0),
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["relation_statuses"] = RelationStatus.objects.all()
        workspace_groups = self.get_workspace_groups(self.get_workspace_queryset())
        context["workspace_groups"] = workspace_groups
        context["workspace_summary"] = self.get_workspace_summary(workspace_groups)
        return context


class RelationCreateView(BaseCreateView):
    model = Relation
    form_class = RelationForm
    success_url = reverse_lazy("gift_manager:relations")
    context_object_name = "relation"
    object_type = gettext_noop("Gift Plan")
    htmx_template_name = "gift_manager/includes/relation_form_partial.html"
    form_fields_template = "gift_manager/includes/forms/relation_fields.html"
    form_css_class = "relation-form"
    form_type = "relation"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        hide_person = self.request.GET.get("hide_person", "false") == "true"
        kwargs["hide_person"] = hide_person
        hide_group = self.request.GET.get("hide_group", "false") == "true"
        kwargs["hide_group"] = hide_group
        kwargs["user"] = self.request.user
        return kwargs

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["gift"].queryset = Gift.objects.accessible_by(self.request.user).order_by(
            "name"
        )
        form.fields["event"].queryset = Event.objects.accessible_by(self.request.user).order_by(
            "name"
        )
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form_action_url"] = reverse("gift_manager:relation_create")
        return context


class RelationUpdateView(PermissionUpdateMixin, BaseUpdateView):
    model = Relation
    form_class = RelationForm
    pk_name = "relation_id"
    context_object_name = "relation"
    object_type = gettext_noop("Gift Plan")
    detail_url_name = "relation_detail"
    htmx_template_name = "gift_manager/includes/relation_form_partial.html"
    form_fields_template = "gift_manager/includes/forms/relation_fields.html"
    form_css_class = "relation-form"
    form_type = "relation"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        hide_person = self.request.GET.get("hide_person", "false") == "true"
        kwargs["hide_person"] = hide_person
        hide_group = self.request.GET.get("hide_group", "false") == "true"
        kwargs["hide_group"] = hide_group
        kwargs["user"] = self.request.user
        return kwargs

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["gift"].queryset = Gift.objects.accessible_by(self.request.user).order_by(
            "name"
        )
        form.fields["event"].queryset = Event.objects.accessible_by(self.request.user).order_by(
            "name"
        )
        return form

    def get_success_url(self):
        if self.object.person_id is not None:
            pk = self.object.person.person_id
            url = "person_detail"
        else:
            pk = self.object.group.group_id
            url = "person_group_detail"
        return reverse(f"gift_manager:{url}", kwargs={"pk": pk})


class RelationDeleteView(BaseDeleteView):
    model = Relation
    success_url = reverse_lazy("gift_manager:relations")
    pk_name = "relation_id"
    object_type = "relation"
    display_object_type = gettext_noop("gift plan")


class RelationDetailView(BaseDetailView):
    model = Relation
    template_name = "gift_manager/relation_detail.html"
    context_object_name = "relation"
    pk_name = "relation_id"
    htmx_template_name = "gift_manager/includes/relation_detail_partial.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["gift_plan_status_class"] = gift_plan_status_class(self.object.status)
        context["gift_plan_urgency_key"] = gift_plan_urgency_key(self.object)

        # Add action buttons
        is_editor = context["is_editor"]
        context["action_buttons"] = [
            {
                "type": "edit",
                "url": reverse(
                    "gift_manager:relation_edit", kwargs={"pk": self.object.relation_id}
                ),
                "label": _("Edit gift plan"),
                "enabled": is_editor,
                "tooltip": _("You do not have permission to edit this object")
                if not is_editor
                else None,
            },
            {
                "type": "delete",
                "url": reverse(
                    "gift_manager:relation_delete", kwargs={"pk": self.object.relation_id}
                ),
                "label": _("Delete gift plan"),
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


@login_required
@require_POST
def update_relation_status(request):
    relation_id = request.POST.get("relation_id")
    try:
        new_status = int(request.POST.get("new_status"))
    except (TypeError, ValueError):
        return JsonResponse({"error": gettext("Choose a valid status.")}, status=400)

    try:
        relation = Relation.objects.get(Q(relation_id=relation_id) & Q(shared_with=request.user))
        if PermissionService.get_permission(relation, request.user) < PermissionLevel.EDITOR:
            return JsonResponse({"error": gettext("You cannot edit this gift plan.")}, status=403)

        relation.status = RelationStatus.objects.get(pk=new_status)
        relation.save()

        # Build HTML manually to avoid template recursion issues
        relation_statuses = RelationStatus.objects.all()
        options_html = ""
        for stat in relation_statuses:
            selected = "selected" if new_status == stat.pk else ""
            options_html += (
                f'<option value="{stat.pk}" {selected}>{conditional_escape(stat.status)}</option>'
            )

        status_class = gift_plan_status_class(relation.status)
        status_select_class = (
            f"form-select form-select-sm status-selector gift-plan-status-select {status_class}"
        )
        html = f"""<form id="status-form-{relation.relation_id}" class="gift-plan-status-form">
            <select class="{status_select_class}"
                    name="new_status"
                    data-relation-id="{relation.relation_id}"
                    data-update-url="{reverse("gift_manager:relation_status_update")}">
                {options_html}
            </select>
        </form>"""

        return HttpResponse(html)

    except Relation.DoesNotExist:
        return JsonResponse({"error": gettext("Gift Plan not found")}, status=404)
    except RelationStatus.DoesNotExist:
        return JsonResponse({"error": gettext("Choose a valid status.")}, status=400)
