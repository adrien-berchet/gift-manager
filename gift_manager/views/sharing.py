"""Sharing-related views."""

from collections.abc import Sequence
from copy import deepcopy

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import TextField, Value
from django.db.models.functions import Concat
from django.shortcuts import redirect, render
from django.utils.translation import gettext
from django.views.generic import View

from ..models import Event, Gift, Person, PersonGroup, PermissionLevel, Relation
from ..permissions import PERMISSION_LEVELS, create_or_update_permission


class ShareObjectsView(LoginRequiredMixin, View):
    """View for sharing objects with friends."""

    template_name = "gift_manager/share_objects.html"

    def get(self, request):
        """Display the sharing form."""
        # Get user's friends
        friends = User.objects.filter(
            pk__in=request.user.profile.friends.all().values_list("user_id", flat=True)
        ).select_related("profile")

        # Get the user's objects for each type
        persons = (
            Person.objects.accessible_by(request.user)
            .annotate(
                complete_name=Concat(
                    "family_name",
                    Value(" "),
                    "first_name",
                    output_field=TextField(),
                ),
            )
            .prefetch_related("groups")
            .order_by("complete_name")
        )
        person_groups = (
            PersonGroup.objects.accessible_by(request.user)
            .prefetch_related("person_set")
            .order_by("name")
        )
        gifts = Gift.objects.accessible_by(request.user).order_by("name")
        events = Event.objects.accessible_by(request.user).order_by("name")
        relations = (
            Relation.objects.accessible_by(request.user)
            .select_related("person", "group", "gift", "event")
            .order_by(
                "person__family_name",
                "person__first_name",
                "group__name",
                "gift__name",
                "event__name",
                "status__status",
            )
        )

        context = {
            "friends": friends,
            "persons": persons,
            "person_groups": person_groups,
            "gifts": gifts,
            "events": events,
            "relations": relations,
            "permission_levels": deepcopy(PERMISSION_LEVELS),
        }

        return render(request, self.template_name, context)

    def post(self, request):
        """Process sharing of selected objects."""
        with transaction.atomic():
            # Get selected friends
            friends = self._get_selected_friends(request)
            if not friends:
                messages.error(request, gettext("Please select at least one friend."))
                return self.get(request)

            # Get selected objects by type
            selection = self._get_selection_from_request(request)

            # Check if at least one object is selected
            if not any(selection.values()):
                messages.error(request, gettext("Please select at least one object to share."))
                return self.get(request)

            # Get selected permission level (default to VIEWER if not specified)
            permission_level = int(request.POST.get("permission_level", PermissionLevel.VIEWER))

            # Option to share persons in a group
            share_group_persons = "share_group_persons" in request.POST

            # Perform sharing for each object type
            shared_items = {}

            if selection["person_ids"]:
                shared_items["persons"] = self._share_persons(
                    selection["person_ids"], friends, permission_level
                )

            if selection["person_group_ids"]:
                shared_items["person_groups"] = self._share_person_groups(
                    selection["person_group_ids"],
                    friends,
                    share_members=share_group_persons,
                    permission_level=permission_level,
                )

            if selection["gift_ids"]:
                shared_items["gifts"] = self._share_gifts(
                    selection["gift_ids"], friends, permission_level
                )

            if selection["event_ids"]:
                shared_items["events"] = self._share_events(
                    selection["event_ids"], friends, permission_level
                )

            if selection["relation_ids"]:
                shared_items["relations"] = self._share_relations(
                    selection["relation_ids"], friends, permission_level
                )

            # Success message
            messages.success(
                request, gettext("Successfully shared items with {} friend(s)").format(len(friends))
            )

            return redirect("gift_manager:share_objects")

    def _get_selected_friends(self, request) -> Sequence[User]:
        """Get selected friends from the request.

        Args:
            request: The HTTP request

        Returns:
            Sequence of selected users
        """
        friend_ids = request.POST.getlist("friends")
        return User.objects.filter(id__in=friend_ids)

    def _get_selection_from_request(self, request) -> dict[str, list[str]]:
        """Get the IDs of selected objects from the request.

        Args:
            request: The HTTP request

        Returns:
            Dictionary containing the IDs of selected objects by type
        """
        return {
            "person_ids": request.POST.getlist("persons"),
            "person_group_ids": request.POST.getlist("person_groups"),
            "gift_ids": request.POST.getlist("gifts"),
            "event_ids": request.POST.getlist("events"),
            "relation_ids": request.POST.getlist("relations"),
        }

    def _share_persons(
        self, person_ids: list[str], friends: Sequence[User], permission_level: int
    ) -> int:
        """Share selected persons with selected friends.

        Args:
            person_ids: List of person IDs to share
            friends: Sequence of friends to share with
            permission_level: Permission level to apply

        Returns:
            Number of shared persons
        """
        persons = Person.objects.filter(person_id__in=person_ids)

        for person in persons:
            for friend in friends:
                create_or_update_permission(friend, person, permission_level=permission_level)

        return len(persons)

    def _share_person_groups(
        self,
        person_group_ids: list[str],
        friends: Sequence[User],
        *,
        share_members: bool = False,
        permission_level: int,
    ) -> int:
        """Share selected groups with selected friends.

        Args:
            person_group_ids: List of group IDs to share
            friends: Sequence of friends to share with
            share_members: If True, the persons in the groups are also shared
            permission_level: Permission level to apply

        Returns:
            Number of shared groups
        """
        groups = PersonGroup.objects.filter(group_id__in=person_group_ids)

        for group in groups:
            # Share the group
            for friend in friends:
                with transaction.atomic():
                    create_or_update_permission(
                        friend, group, permission_level=permission_level, object_attr="group"
                    )

                    # If requested, also share the persons in the group
                    if share_members:
                        for person in group.person_set.all():
                            create_or_update_permission(
                                friend, person, permission_level=permission_level
                            )

        return len(groups)

    def _share_gifts(
        self, gift_ids: list[str], friends: Sequence[User], permission_level: int
    ) -> int:
        """Share selected gifts with selected friends.

        Args:
            gift_ids: List of gift IDs to share
            friends: Sequence of friends to share with
            permission_level: Permission level to apply

        Returns:
            Number of shared gifts
        """
        gifts = Gift.objects.filter(gift_id__in=gift_ids)

        for gift in gifts:
            for friend in friends:
                create_or_update_permission(friend, gift, permission_level=permission_level)

        return len(gifts)

    def _share_events(
        self, event_ids: list[str], friends: Sequence[User], permission_level: int
    ) -> int:
        """Share selected events with selected friends.

        Args:
            event_ids: List of event IDs to share
            friends: Sequence of friends to share with
            permission_level: Permission level to apply

        Returns:
            Number of shared events
        """
        events = Event.objects.filter(event_id__in=event_ids)

        for event in events:
            for friend in friends:
                create_or_update_permission(friend, event, permission_level=permission_level)

        return len(events)

    def _share_relations(
        self, relation_ids: list[str], friends: Sequence[User], permission_level: int
    ) -> int:
        """Share selected relations with selected friends.

        Includes cascade sharing of related objects.

        Args:
            relation_ids: List of relation IDs to share
            friends: Sequence of friends to share with
            permission_level: Permission level to apply

        Returns:
            Number of shared relations
        """
        relations = Relation.objects.filter(relation_id__in=relation_ids)

        for friend in friends:
            for relation in relations:
                with transaction.atomic():
                    # Share the relation itself
                    create_or_update_permission(friend, relation, permission_level=permission_level)

                    # Share the associated gift
                    if relation.gift:
                        create_or_update_permission(
                            friend, relation.gift, permission_level=permission_level
                        )

                    # Share the associated person
                    if relation.person:
                        create_or_update_permission(
                            friend, relation.person, permission_level=permission_level
                        )

                    # Share the associated group
                    if relation.group:
                        create_or_update_permission(
                            friend,
                            relation.group,
                            permission_level=permission_level,
                            object_attr="group",
                        )

                    # Share the associated event
                    if relation.event:
                        create_or_update_permission(
                            friend, relation.event, permission_level=permission_level
                        )

        return len(relations)
