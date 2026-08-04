"""Recipient-oriented views."""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.db.models import Prefetch
from django.urls import reverse
from django.utils.translation import gettext
from django.views.generic import TemplateView

from gift_manager.mixins.permissions import PermissionContextMixin
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import Relation
from gift_manager.views.person import get_person_grid_column_names
from gift_manager.views.person import get_person_grid_queryset
from gift_manager.views.person import populate_person_grid_group_info
from gift_manager.views.person_group import get_person_group_management_context


class RecipientListView(LoginRequiredMixin, PermissionContextMixin, TemplateView):
    """Show people and groups together as gift plan recipients."""

    template_name = "gift_manager/recipient_list.html"
    login_url = "/accounts/login/"
    model = Person

    valid_views = {"all", "people", "groups"}

    def get_recipient_view(self) -> str:
        """Return the active recipient mode from the query string."""
        requested_view = self.request.GET.get("view", "all")
        if requested_view == "persons":
            return "people"
        if requested_view in self.valid_views:
            return requested_view
        return "all"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        recipient_view = self.get_recipient_view()

        accessible_groups = PersonGroup.objects.accessible_by(user).order_by("name").distinct()
        accessible_persons = (
            Person.objects.accessible_by(user).order_by("family_name", "first_name").distinct()
        )

        context["recipient_view"] = recipient_view

        if recipient_view == "people":
            person_column_names = get_person_grid_column_names()
            person_grid_data = list(get_person_grid_queryset(user, person_column_names))
            populate_person_grid_group_info(person_grid_data)
            person_permission_context = self.get_permission_context(person_grid_data)
            context["person_grid_data"] = person_grid_data
            context["person_column_names"] = person_column_names
            context["person_user_permissions_json"] = person_permission_context[
                "user_permissions_json"
            ]
            context["recipients"] = []
            context["person_count"] = len(person_grid_data)
            context["group_count"] = accessible_groups.count()
            context["recipient_count"] = context["person_count"] + context["group_count"]
            return context

        if recipient_view == "groups":
            group_context = get_person_group_management_context(user)
            context["person_group_grid_data"] = group_context["data"]
            context["person_group_column_names"] = group_context["column_names"]
            context["person_group_tree_data"] = group_context["tree_data"]
            context["person_group_has_hierarchy"] = group_context["has_hierarchy"]
            context["person_group_user_permissions_json"] = group_context["user_permissions_json"]
            context["recipients"] = []
            context["person_count"] = accessible_persons.count()
            context["group_count"] = len(group_context["data"])
            context["recipient_count"] = context["person_count"] + context["group_count"]
            return context

        persons = list(
            accessible_persons.prefetch_related(
                Prefetch(
                    "groups",
                    queryset=accessible_groups,
                    to_attr="accessible_groups",
                )
            )
        )
        groups = list(
            accessible_groups.prefetch_related(
                Prefetch(
                    "child_groups",
                    queryset=accessible_groups,
                    to_attr="accessible_child_groups",
                ),
                Prefetch(
                    "person_set",
                    queryset=accessible_persons,
                    to_attr="accessible_members",
                ),
            )
        )
        accessible_relations = Relation.objects.accessible_by(user)
        person_plan_counts = {
            item["person_id"]: item["count"]
            for item in accessible_relations.filter(person_id__isnull=False)
            .values("person_id")
            .annotate(count=Count("pk"))
        }
        group_plan_counts = {
            item["group_id"]: item["count"]
            for item in accessible_relations.filter(group_id__isnull=False)
            .values("group_id")
            .annotate(count=Count("pk"))
        }

        recipients = [
            {
                "key": f"person:{person.person_id}",
                "type": "person",
                "type_label": gettext("Person"),
                "name": str(person),
                "detail_url": reverse(
                    "gift_manager:person_detail", kwargs={"pk": person.person_id}
                ),
                "gift_plan_url": reverse(
                    "gift_manager:person_relation_create", kwargs={"pk": person.person_id}
                ),
                "groups": list(person.accessible_groups),
                "member_count": None,
                "child_count": None,
                "plan_count": person_plan_counts.get(person.pk, 0),
            }
            for person in persons
        ]
        recipients.extend(
            [
                {
                    "key": f"group:{group.group_id}",
                    "type": "group",
                    "type_label": gettext("Group"),
                    "name": group.name,
                    "detail_url": reverse(
                        "gift_manager:person_group_detail", kwargs={"pk": group.group_id}
                    ),
                    "gift_plan_url": reverse(
                        "gift_manager:person_group_relation_create",
                        kwargs={"pk": group.group_id},
                    ),
                    "groups": [],
                    "member_count": len(group.accessible_members),
                    "child_count": len(group.accessible_child_groups),
                    "plan_count": group_plan_counts.get(group.pk, 0),
                }
                for group in groups
            ]
        )

        all_recipients = sorted(recipients, key=lambda item: item["name"].lower())

        context["recipients"] = all_recipients
        context["person_count"] = len(persons)
        context["group_count"] = len(groups)
        context["recipient_count"] = len(all_recipients)

        return context
