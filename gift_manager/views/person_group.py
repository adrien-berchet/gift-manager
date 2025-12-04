"""PersonGroup-related views."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.urls import reverse_lazy
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from ..forms import PersonGroupAddMultiplePersonsForm
from ..forms import PersonGroupForm
from ..models import Person
from ..models import PersonGroup
from ..models import Relation
from ..models import RelationStatus
from .base import BaseCreateView
from .base import BaseDeleteView
from .base import BaseDetailView
from .base import BaseListView
from .base import BaseUpdateView


class PersonGroupListView(BaseListView):
    model = PersonGroup
    template_name = "gift_manager/person_group_list.html"
    object_type = "Groups"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.column_names = {
            "name": gettext("Group name"),
        }

    def get_queryset(self):
        return PersonGroup.objects.accessible_by(self.request.user).values(
            "group_id", *self.column_names
        )


class PersonGroupCreateView(BaseCreateView):
    model = PersonGroup
    form_class = PersonGroupForm
    success_url = reverse_lazy("gift_manager:person_groups")
    context_object_name = "group"
    object_type = "Person group"


class PersonGroupUpdateView(BaseUpdateView):
    model = PersonGroup
    form_class = PersonGroupForm
    pk_name = "group_id"
    context_object_name = "group"
    object_type = "Person group"
    detail_url_name = "person_group_detail"


def add_multiple_persons_to_group(request, pk):
    group = get_object_or_404(PersonGroup, group_id=pk)
    if request.method == "POST":
        form = PersonGroupAddMultiplePersonsForm(request.POST, user=request.user, group=group)
        if form.is_valid():
            form.save(group)
            return redirect("gift_manager:person_group_detail", pk=pk)
    else:
        form = PersonGroupAddMultiplePersonsForm(user=request.user, group=group)

    return render(
        request,
        "gift_manager/person_group_add_person_form.html",
        {
            "group": group,
            "form": form,
        },
    )


def remove_person_from_group(request, pk, person_id):  # noqa: ARG001
    with transaction.atomic():
        group = get_object_or_404(PersonGroup, group_id=pk)
        person = get_object_or_404(Person, person_id=person_id)
        person.groups.remove(group)
        return redirect("gift_manager:person_group_detail", pk=pk)


class PersonGroupDeleteView(BaseDeleteView):
    model = PersonGroup
    success_url = reverse_lazy("gift_manager:person_groups")
    pk_name = "group_id"
    object_type = "group"


class PersonGroupDetailView(BaseDetailView):
    model = PersonGroup
    template_name = "gift_manager/person_group_detail.html"
    context_object_name = "group"
    pk_name = "group_id"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["persons"] = (
            Person.objects.accessible_by(self.request.user)
            .filter(groups=self.object)
            .prefetch_related("groups")
        )
        context["gifts"] = (
            Relation.objects.accessible_by(self.request.user)
            .filter(group=self.object, gift__isnull=False)
            .select_related("gift", "event", "status")
            .prefetch_related("gift__tags")
            .order_by("status__pk")
        )
        context["relation_statuses"] = RelationStatus.objects.all()

        # Add action buttons
        is_editor = context["is_editor"]
        context["action_buttons"] = [
            {
                "type": "edit",
                "url": reverse(
                    "gift_manager:person_group_edit", kwargs={"pk": self.object.group_id}
                ),
                "label": _("Edit group"),
                "enabled": is_editor,
                "tooltip": _("You do not have permission to edit this object")
                if not is_editor
                else None,
            },
            {
                "type": "delete",
                "url": reverse(
                    "gift_manager:person_group_delete", kwargs={"pk": self.object.group_id}
                ),
                "label": _("Delete group"),
                "enabled": True,
                "tooltip": _(
                    "You do not have permission to delete this object so it will only be unshared with you"
                )
                if not is_editor
                else None,
            },
        ]
        return context
