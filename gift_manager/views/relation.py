"""Relation-related views."""

from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.db.models import Q, TextField, Value
from django.db.models.functions import Coalesce, Concat, NullIf
from django.http import JsonResponse
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext
from django.views.decorators.http import require_POST

from ..forms import GiftRelationForm, PersonGroupRelationForm, PersonRelationForm, RelationForm
from ..models import Event, Gift, Person, PersonGroup, Relation, RelationStatus
from .base import BaseCreateView, BaseDeleteView, BaseDetailView, BaseListView, BaseUpdateView


class PersonRelationCreateView(BaseCreateView):
    model = Relation
    form_class = PersonRelationForm
    context_object_name = "relation"
    object_type = "Relation"

    def get_success_url(self):
        return reverse("gift_manager:person_detail", kwargs={"pk": self.kwargs["pk"]})

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["person_id"] = self.kwargs["pk"]  # Pass the person ID to the form
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


class PersonGroupRelationCreateView(BaseCreateView):
    model = Relation
    form_class = PersonGroupRelationForm
    context_object_name = "relation"
    object_type = "Relation"

    def get_success_url(self):
        url = reverse("gift_manager:person_group_detail", kwargs={"pk": self.kwargs["pk"]})
        query = urlencode({"tab": "gifts"})
        return f"{url}?{query}"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["group_id"] = self.kwargs["pk"]  # Pass the group ID to the form
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


class GiftRelationCreateView(BaseCreateView):
    model = Relation
    form_class = GiftRelationForm
    context_object_name = "relation"
    object_type = "Relation"

    def get_success_url(self):
        return reverse("gift_manager:gift_detail", kwargs={"pk": self.kwargs["pk"]})

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["gift_id"] = self.kwargs["pk"]  # Pass the gift ID to the form
        return kwargs

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["person"].queryset = (
            Person.objects.accessible_by(self.request.user)
            .annotate(
                complete_name=Concat(
                    "family_name",
                    Value(" "),
                    "first_name",
                    output_field=TextField(),
                ),
            )
            .order_by("complete_name")
        )
        form.fields["group"].queryset = PersonGroup.objects.accessible_by(
            self.request.user
        ).order_by("name")
        form.fields["event"].queryset = Event.objects.accessible_by(self.request.user).order_by(
            "name"
        )
        return form


class GiftRelationDeleteView(BaseDeleteView):
    model = Relation
    pk_name = "relation_id"
    object_type = "relation"

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
        return RelationStatus.objects.values("pk", *self.column_names)


class RelationStatusDetailView(BaseDetailView):
    model = RelationStatus
    template_name = "gift_manager/relation_status_detail.html"
    context_object_name = "status"
    pk_name = "status_id"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["relations"] = Relation.objects.accessible_by(self.request.user).filter(
            status=self.object
        )
        return context


class RelationListView(BaseListView):
    model = Relation
    template_name = "gift_manager/relation_list.html"
    object_type = "Relations"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.column_names = {
            "gift__name": gettext("Gift"),
            "comment": gettext("Comment"),
            "related_object": gettext("Offered to"),
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
                )
            )
            .values(
                "relation_id",
                "gift__name",
                "gift__gift_id",
                "comment",
                "related_object",
                "person__person_id",
                "group__group_id",
                "event__name",
                "event__event_id",
                "status",
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["relation_statuses"] = RelationStatus.objects.all()
        return context


class RelationCreateView(BaseCreateView):
    model = Relation
    form_class = RelationForm
    success_url = reverse_lazy("gift_manager:relations")
    context_object_name = "relation"
    object_type = "Gifting"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        hide_person = self.request.GET.get("hide_person", "false") == "true"
        kwargs["hide_person"] = hide_person
        hide_group = self.request.GET.get("hide_group", "false") == "true"
        kwargs["hide_group"] = hide_group
        return kwargs

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["person"].queryset = (
            Person.objects.accessible_by(self.request.user)
            .annotate(
                complete_name=Concat(
                    "family_name",
                    Value(" "),
                    "first_name",
                    output_field=TextField(),
                ),
            )
            .order_by("complete_name")
        )
        form.fields["group"].queryset = PersonGroup.objects.accessible_by(
            self.request.user
        ).order_by("name")
        form.fields["gift"].queryset = Gift.objects.accessible_by(self.request.user).order_by(
            "name"
        )
        form.fields["event"].queryset = Event.objects.accessible_by(self.request.user).order_by(
            "name"
        )
        return form


class RelationUpdateView(BaseUpdateView):
    model = Relation
    form_class = RelationForm
    pk_name = "relation_id"
    context_object_name = "relation"
    object_type = "Relation"
    detail_url_name = "relation_detail"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        hide_person = self.request.GET.get("hide_person", "false") == "true"
        kwargs["hide_person"] = hide_person
        hide_group = self.request.GET.get("hide_group", "false") == "true"
        kwargs["hide_group"] = hide_group
        return kwargs

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["person"].queryset = (
            Person.objects.accessible_by(self.request.user)
            .annotate(
                complete_name=Concat(
                    "family_name",
                    Value(" "),
                    "first_name",
                    output_field=TextField(),
                ),
            )
            .order_by("complete_name")
        )
        form.fields["group"].queryset = PersonGroup.objects.accessible_by(
            self.request.user
        ).order_by("name")
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


class RelationDetailView(BaseDetailView):
    model = Relation
    template_name = "gift_manager/relation_detail.html"
    context_object_name = "relation"
    pk_name = "relation_id"


@login_required
@require_POST
def update_relation_status(request):
    relation_id = request.POST.get("relation_id")
    new_status = request.POST.get("new_status")
    try:
        relation = Relation.objects.get(Q(relation_id=relation_id) & Q(shared_with=request.user))
        relation.status_id = new_status
        relation.save()
        return JsonResponse({"success": True})
    except Relation.DoesNotExist:
        return JsonResponse({"error": gettext("Gifting not found")}, status=404)
