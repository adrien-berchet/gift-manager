"""Sharing-related views."""

import logging
from collections.abc import Sequence
from copy import deepcopy

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import TextField
from django.db.models import Value
from django.db.models.functions import Concat
from django.shortcuts import redirect
from django.shortcuts import render
from django.utils.translation import gettext
from django.views.generic import View

from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import Relation
from gift_manager.permissions import PERMISSION_LEVELS
from gift_manager.permissions import create_or_update_permission
from gift_manager.services import PermissionService

logger = logging.getLogger(__name__)

NON_FRIEND_SHARE_ERROR = "Objects can only be shared with friends."
UNSHAREABLE_OBJECT_ERROR = "One or more selected objects cannot be shared."
INSUFFICIENT_SHARE_PERMISSION_ERROR = "You do not have permission to share this object."
PERMISSION_ESCALATION_ERROR = "You cannot grant a higher permission than your own."


class ShareObjectsView(LoginRequiredMixin, View):
    """View for sharing objects with friends."""

    template_name = "gift_manager/share_objects.html"
    minimum_share_permission = PermissionLevel.EDITOR

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

    def post(self, request):  # noqa: C901, PLR0911
        """Process sharing of selected objects."""
        try:
            with transaction.atomic():
                # Get selected friends
                friends = self._get_selected_friends(request)
                if not friends:
                    logger.info("User %s tried to share without selecting friends", request.user)
                    messages.error(request, gettext("Please select at least one friend."))
                    return self.get(request)

                # Get selected objects by type
                selection = self._get_selection_from_request(request)

                # Check if at least one object is selected
                if not any(selection.values()):
                    logger.info("User %s tried to share without selecting objects", request.user)
                    messages.error(request, gettext("Please select at least one object to share."))
                    return self.get(request)

                # Get selected permission level (default to VIEWER if not specified)
                try:
                    permission_level = int(
                        request.POST.get("permission_level", PermissionLevel.VIEWER)
                    )
                    if permission_level not in [
                        PermissionLevel.VIEWER,
                        PermissionLevel.EDITOR,
                        PermissionLevel.OWNER,
                    ]:
                        msg = (
                            f"Invalid permission level provided by user {request.user}: "
                            f"{permission_level}"
                        )
                        logger.warning(msg)
                        raise ValueError(msg)  # noqa: TRY301
                except (ValueError, TypeError) as e:
                    logger.warning(
                        "Invalid permission level provided by user %s: %s", request.user, e
                    )
                    messages.error(request, gettext("Invalid permission level selected."))
                    return self.get(request)

                # Options for sharing groups
                share_group_persons = "share_group_persons" in request.POST
                share_child_groups = "share_child_groups" in request.POST

                # Perform sharing for each object type
                shared_items = {}

                if selection["person_ids"]:
                    shared_items["persons"] = self._share_persons(
                        selection["person_ids"],
                        friends,
                        permission_level,
                        actor=request.user,
                    )

                if selection["person_group_ids"]:
                    shared_items["person_groups"] = self._share_person_groups(
                        selection["person_group_ids"],
                        friends,
                        share_members=share_group_persons,
                        share_children=share_child_groups,
                        permission_level=permission_level,
                        actor=request.user,
                    )

                if selection["gift_ids"]:
                    shared_items["gifts"] = self._share_gifts(
                        selection["gift_ids"],
                        friends,
                        permission_level,
                        actor=request.user,
                    )

                if selection["event_ids"]:
                    shared_items["events"] = self._share_events(
                        selection["event_ids"],
                        friends,
                        permission_level,
                        actor=request.user,
                    )

                if selection["relation_ids"]:
                    shared_items["relations"] = self._share_relations(
                        selection["relation_ids"],
                        friends,
                        permission_level,
                        actor=request.user,
                    )

            # Success message
            total_shared = sum(shared_items.values())
            logger.info(
                "User %s shared %s items with %s friend(s) at permission level %s",
                request.user,
                total_shared,
                len(friends),
                permission_level,
            )
            messages.success(
                request, gettext("Successfully shared items with {} friend(s)").format(len(friends))
            )

            return redirect("gift_manager:share_objects")

        except PermissionDenied as e:
            logger.warning("Permission denied for user %s in ShareObjectsView: %s", request.user, e)
            messages.error(
                request, gettext("You don't have permission to share one or more selected objects.")
            )
            return self.get(request)

        except ValidationError as e:
            logger.info("Validation error in ShareObjectsView for user %s: %s", request.user, e)
            messages.error(request, gettext("Invalid data provided. Please check your selections."))
            return self.get(request)

        except Exception:
            logger.exception("Unexpected error in ShareObjectsView for user %s", request.user)
            messages.error(request, gettext("An unexpected error occurred while sharing objects."))
            return self.get(request)

    def _get_selected_friends(self, request) -> Sequence[User]:
        """Get selected friends from the request.

        Args:
            request: The HTTP request

        Returns:
            Sequence of selected users
        """
        friend_ids = self._parse_user_ids(request.POST.getlist("friends"))
        if not friend_ids:
            return []

        allowed_friend_profiles = request.user.profile.friends.all()
        friends = list(
            User.objects.filter(id__in=friend_ids, profile__in=allowed_friend_profiles)
            .select_related("profile")
            .order_by("username")
        )
        found_friend_ids = {friend.id for friend in friends}
        if found_friend_ids != friend_ids:
            logger.warning(
                "User %s tried to share with non-friend or unknown users: %s",
                request.user,
                sorted(friend_ids - found_friend_ids),
            )
            raise PermissionDenied(NON_FRIEND_SHARE_ERROR)

        return friends

    def _parse_user_ids(self, raw_ids: list[str]) -> set[int]:
        """Parse posted user IDs and reject malformed values."""
        try:
            return {int(raw_id) for raw_id in raw_ids}
        except (TypeError, ValueError) as e:
            raise ValidationError(gettext("Invalid friend selection.")) from e

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
        self,
        person_ids: list[str],
        friends: Sequence[User],
        permission_level: int,
        *,
        actor: User,
    ) -> int:
        """Share selected persons with selected friends.

        Args:
            person_ids: List of person IDs to share
            friends: Sequence of friends to share with
            permission_level: Permission level to apply
            actor: User performing the share

        Returns:
            Number of shared persons
        """
        persons = self._get_shareable_objects(
            actor,
            Person,
            "person_id",
            person_ids,
            permission_level,
            object_label="persons",
        )

        for person in persons:
            for friend in friends:
                self._share_object_with_friend(friend, person, permission_level)

        return len(persons)

    def _share_person_groups(
        self,
        person_group_ids: list[str],
        friends: Sequence[User],
        *,
        share_members: bool = False,
        share_children: bool = False,
        permission_level: int,
        actor: User,
    ) -> int:
        """Share selected groups with selected friends.

        Args:
            person_group_ids: List of group IDs to share
            friends: Sequence of friends to share with
            share_members: If True, the persons in the groups are also shared
            share_children: If True, all child groups are also shared
            permission_level: Permission level to apply
            actor: User performing the share

        Returns:
            Number of shared groups
        """
        groups = self._get_shareable_objects(
            actor,
            PersonGroup,
            "group_id",
            person_group_ids,
            permission_level,
            object_label="person groups",
        )

        # Collect all groups to share (including children if requested)
        all_groups_to_share = set()
        for group in groups:
            all_groups_to_share.add(group)
            if share_children:
                # Add all descendant groups
                all_groups_to_share.update(group.get_descendants())

        for group in all_groups_to_share:
            self._validate_share_permission(actor, group, permission_level, "person groups")

            if share_members:
                for person in group.person_set.all():
                    self._validate_share_permission(actor, person, permission_level, "persons")

        # Share all groups
        for group in all_groups_to_share:
            for friend in friends:
                with transaction.atomic():
                    self._share_object_with_friend(friend, group, permission_level)

                    # If requested, also share the persons in the group
                    if share_members:
                        for person in group.person_set.all():
                            self._share_object_with_friend(friend, person, permission_level)

        return len(all_groups_to_share)

    def _share_gifts(
        self,
        gift_ids: list[str],
        friends: Sequence[User],
        permission_level: int,
        *,
        actor: User,
    ) -> int:
        """Share selected gifts with selected friends.

        Args:
            gift_ids: List of gift IDs to share
            friends: Sequence of friends to share with
            permission_level: Permission level to apply
            actor: User performing the share

        Returns:
            Number of shared gifts
        """
        gifts = self._get_shareable_objects(
            actor,
            Gift,
            "gift_id",
            gift_ids,
            permission_level,
            object_label="gifts",
        )

        for gift in gifts:
            for friend in friends:
                self._share_object_with_friend(friend, gift, permission_level)

        return len(gifts)

    def _share_events(
        self,
        event_ids: list[str],
        friends: Sequence[User],
        permission_level: int,
        *,
        actor: User,
    ) -> int:
        """Share selected events with selected friends.

        Args:
            event_ids: List of event IDs to share
            friends: Sequence of friends to share with
            permission_level: Permission level to apply
            actor: User performing the share

        Returns:
            Number of shared events
        """
        events = self._get_shareable_objects(
            actor,
            Event,
            "event_id",
            event_ids,
            permission_level,
            object_label="events",
        )

        for event in events:
            for friend in friends:
                self._share_object_with_friend(friend, event, permission_level)

        return len(events)

    def _share_relations(
        self,
        relation_ids: list[str],
        friends: Sequence[User],
        permission_level: int,
        *,
        actor: User,
    ) -> int:
        """Share selected relations with selected friends.

        Includes cascade sharing of related objects.

        Args:
            relation_ids: List of relation IDs to share
            friends: Sequence of friends to share with
            permission_level: Permission level to apply
            actor: User performing the share

        Returns:
            Number of shared relations
        """
        relations = self._get_shareable_objects(
            actor,
            Relation,
            "relation_id",
            relation_ids,
            permission_level,
            object_label="relations",
        )

        for friend in friends:
            for relation in relations:
                with transaction.atomic():
                    # Share the relation itself
                    self._share_object_with_friend(friend, relation, permission_level)

                    # Share the associated gift
                    if relation.gift:
                        self._validate_share_permission(
                            actor, relation.gift, permission_level, "gifts"
                        )
                        self._share_object_with_friend(friend, relation.gift, permission_level)

                    # Share the associated person
                    if relation.person:
                        self._validate_share_permission(
                            actor, relation.person, permission_level, "persons"
                        )
                        self._share_object_with_friend(friend, relation.person, permission_level)

                    # Share the associated group
                    if relation.group:
                        self._validate_share_permission(
                            actor, relation.group, permission_level, "person groups"
                        )
                        self._share_object_with_friend(friend, relation.group, permission_level)

                    # Share the associated event
                    if relation.event:
                        self._validate_share_permission(
                            actor, relation.event, permission_level, "events"
                        )
                        self._share_object_with_friend(friend, relation.event, permission_level)

        return len(relations)

    def _get_shareable_objects(
        self,
        actor: User,
        model,
        id_field: str,
        object_ids: list[str],
        permission_level: int,
        *,
        object_label: str,
    ) -> list:
        """Return selected objects only when every posted ID is shareable by the actor."""
        requested_ids = {str(object_id) for object_id in object_ids}
        if not requested_ids:
            return []
        if "" in requested_ids:
            raise ValidationError(gettext("Invalid object selection."))

        objects = list(
            model.objects.accessible_by(actor).filter(**{f"{id_field}__in": requested_ids})
        )
        found_ids = {str(getattr(obj, id_field)) for obj in objects}
        if found_ids != requested_ids:
            logger.warning(
                "User %s tried to share unauthorized or unknown %s: %s",
                actor,
                object_label,
                sorted(requested_ids - found_ids),
            )
            raise PermissionDenied(UNSHAREABLE_OBJECT_ERROR)

        for obj in objects:
            self._validate_share_permission(actor, obj, permission_level, object_label)

        return objects

    def _validate_share_permission(
        self, actor: User, obj, permission_level: int, object_label: str
    ) -> None:
        """Require editor-level share authority and block grants above actor permission."""
        actor_permission = self._get_actor_permission(actor, obj)
        if actor_permission < self.minimum_share_permission:
            logger.warning(
                "User %s with permission %s tried to share %s object %s",
                actor,
                actor_permission,
                object_label,
                obj,
            )
            raise PermissionDenied(INSUFFICIENT_SHARE_PERMISSION_ERROR)

        if permission_level > actor_permission:
            logger.warning(
                "User %s with permission %s tried to grant permission %s on %s object %s",
                actor,
                actor_permission,
                permission_level,
                object_label,
                obj,
            )
            raise PermissionDenied(PERMISSION_ESCALATION_ERROR)

    def _get_actor_permission(self, actor: User, obj) -> int:
        """Return actor permission, treating legacy linked Person owners as owners."""
        return PermissionService.get_effective_permission(obj, actor)

    def _share_object_with_friend(self, friend: User, obj, permission_level: int) -> None:
        """Create or update one object permission for a friend."""
        object_attr = "group" if isinstance(obj, PersonGroup) else None
        create_or_update_permission(
            friend,
            obj,
            permission_level=permission_level,
            object_attr=object_attr,
        )
