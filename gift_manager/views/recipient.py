"""Recipient-oriented views."""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Prefetch
from django.urls import reverse
from django.utils.translation import gettext
from django.views.generic import TemplateView

from gift_manager.models import Person
from gift_manager.models import PersonGroup


class RecipientListView(LoginRequiredMixin, TemplateView):
    """Show people and groups together as gift plan recipients."""

    template_name = "gift_manager/recipient_list.html"
    login_url = "/accounts/login/"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        accessible_groups = PersonGroup.objects.accessible_by(user).order_by("name").distinct()
        accessible_persons = (
            Person.objects.accessible_by(user).order_by("family_name", "first_name").distinct()
        )

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
                }
                for group in groups
            ]
        )

        context["recipients"] = sorted(recipients, key=lambda item: item["name"].lower())
        context["person_count"] = len(persons)
        context["group_count"] = len(groups)
        context["recipient_count"] = len(recipients)
        return context
