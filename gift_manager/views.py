from collections.abc import Sequence
from copy import deepcopy
from typing import TypeAlias
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.contrib.postgres.aggregates import ArrayAgg
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Model
from django.db.models import Q
from django.db.models import TextField
from django.db.models import Value
from django.db.models.functions import Coalesce
from django.db.models.functions import Concat
from django.db.models.functions import NullIf
from django.http import Http404
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext
from django.views.decorators.http import require_POST
from django.views.generic import DeleteView
from django.views.generic import DetailView
from django.views.generic import ListView
from django.views.generic import UpdateView
from django.views.generic import View
from django.views.generic.edit import CreateView

from .forms import EventForm
from .forms import GiftForm
from .forms import GiftRelationForm
from .forms import PersonForm
from .forms import PersonGroupAddMultiplePersonsForm
from .forms import PersonGroupForm
from .forms import PersonGroupRelationForm
from .forms import PersonRelationForm
from .forms import RelationForm
from .models import Event
from .models import Gift
from .models import Invitation
from .models import PermissionLevel
from .models import Person
from .models import PersonGroup
from .models import Profile
from .models import Relation
from .models import RelationStatus
from .permissions import PERMISSION_LEVELS
from .permissions import create_or_update_permission
from .permissions import delete_permission

# Type definitions for clarity
ModelType: TypeAlias = type[Model]
SharedObjectType = Person | PersonGroup | Gift | Event | Relation


def get_user(user_id, *, return_id=False) -> tuple[User, str] | tuple[User, str, str]:
    user = User.objects.get(id=user_id)
    username = user.username
    if return_id:
        return user, username, user_id
    return user, username


def home(request):
    """Home page view."""
    return render(request, "gift_manager/home.html")


class ProfileDetailView(LoginRequiredMixin, DetailView):
    model = Profile
    template_name = "gift_manager/profile_detail.html"
    context_object_name = "profile"

    def get_object(self):
        return Profile.objects.get(user=self.request.user)


class SendInvitationView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        return render(request, "gift_manager/send_invitation.html")

    def post(self, request, *args, **kwargs):
        recipient_email = request.POST.get("recipient_email")
        invitation = Invitation.objects.create(sender=request.user, recipient_email=recipient_email)
        invitation_link = request.build_absolute_uri(
            reverse("gift_manager:accept_invitation", args=[invitation.token])
        )
        send_mail(
            subject=gettext("Join my friends on Gift Manager"),
            message=(
                f"{gettext('To accept the invitation, click on the following link:')} "
                f"{invitation_link}"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
        )
        return redirect("gift_manager:profile_detail")


class AcceptInvitationView(View):
    def get(self, request, *args, **kwargs):
        token = self.kwargs.get("token")
        invitation = get_object_or_404(Invitation, token=token, accepted=False)
        # If the user is already logged in, establish the friendship relationship
        if request.user.is_authenticated:
            invitation.accepted = True
            invitation.accepted_at = timezone.now()
            invitation.save()
            # Create or get the user's profile
            user_profile, _ = Profile.objects.get_or_create(user=request.user)
            sender_profile, _ = Profile.objects.get_or_create(user=invitation.sender)
            # Add the sender to the user's friends and vice versa
            user_profile.friends.add(sender_profile)
            sender_profile.friends.add(user_profile)
            user_profile.save()
            sender_profile.save()
            messages.success(
                request, gettext("You are now friend with {}").format(invitation.sender.username)
            )
            return redirect("gift_manager:profile_detail")
        # Otherwise, redirect to the registration with the token
        # (to be handled in the registration process)
        return redirect(f"{reverse('account_signup')}?invitation_token={token}")


class RemoveFriendView(LoginRequiredMixin, View):
    def post(self, request, friend_id, *args, **kwargs):
        with transaction.atomic():
            friend_profile = get_object_or_404(Profile, pk=friend_id)
            user_profile = get_object_or_404(Profile, user=request.user)

            # Remove the friend relationship (symmetric)
            if friend_profile in user_profile.friends.all():
                user_profile.friends.remove(friend_profile)

            # Remove all shared objects between the two users
            persons_shared = Person.objects.filter(shared_with=request.user)
            for person in persons_shared:
                if friend_profile.user in person.shared_with.all():
                    person.shared_with.remove(friend_profile.user)

        return redirect("gift_manager:profile_detail")

    def get(self, *args, **kwargs):
        # Redirect to the profile detail page
        return redirect("gift_manager:profile_detail")


class FilterByUserMixin:
    """Mixin to filter objects by the current user."""

    def get_queryset(self):
        return self.model.objects.filter(Q(shared_with=self.request.user))


class GetObjectByTokenMixin:
    """Mixin to get an object by its token."""

    pk_name = None

    def get_object(self, queryset=None):
        queryset = self.get_queryset()
        obj_id = self.kwargs.get("pk")
        if obj_id is None:
            msg = "No object found matching the query"
            raise Http404(msg)
        if self.pk_name is None:
            msg = "pk_name attribute is required"
            raise AttributeError(msg)
        kwargs = {self.pk_name: obj_id}
        return get_object_or_404(queryset, **kwargs)


def get_permission(obj, user, filter_name):
    """Get the permission type for the user on the object."""
    permission = obj.shared_with.through.objects.filter(**{"user": user, filter_name: obj}).first()
    return permission.permission_type if permission else PermissionLevel.VIEWER


def get_permission_label(obj, user, filter_name):
    """Get the permission label for the user on the object."""
    permission_value = get_permission(obj, user, filter_name)
    return PermissionLevel.get_label(permission_value)


class ContextPermissionMixin:
    """Mixin to add permission context to the view."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_editor"] = (
            get_permission(self.object, self.request.user, self.context_object_name)
            >= PermissionLevel.EDITOR
        )
        return context


class BaseListView(LoginRequiredMixin, ListView):
    """Base class for list views."""

    template_name = None  # Will be defined in the subclasses
    context_object_name = "data"
    login_url = "/accounts/login/"
    redirect_field_name = "redirect_to"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.column_names = {}  # Will be defined in the subclasses

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["type"] = self.object_type
        context["translated_type"] = gettext(self.object_type)
        context["column_names"] = self.column_names
        return context


class SharedUsersMixin:
    """Mixin to add shared users with their permissions to the context."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get the users with whom this object is shared, with their permissions
        shared_users = []
        for user in self.object.shared_with.exclude(id=self.request.user.id):
            permission = get_permission(self.object, user, self.context_object_name)
            permission_label = PermissionLevel.get_label(permission)
            shared_users.append(
                {"user": user, "permission": permission, "permission_label": permission_label}
            )

        context["shared_users"] = shared_users
        return context


class CreatePermissionMixin:
    """Mixin to add shared user permissions to CreateView forms."""

    def get_initial(self):
        initial = super().get_initial()

        # Get the current user profile and its friends
        current_user_profile = Profile.objects.get(user=self.request.user)
        friend_profiles = current_user_profile.friends.all()
        friend_users = User.objects.filter(profile__in=friend_profiles)

        # Prepare the lists for the shared users and unshared friends
        self.unshared_friends = [
            {
                "user": friend,
                "form_id": f"share_{friend.id}",  # Unique identifier for the form
            }
            for friend in friend_users
        ]
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if hasattr(self, "unshared_friends"):
            context["unshared_friends"] = self.unshared_friends

        # Add the permission levels available for the dropdown menus
        context["permission_levels"] = deepcopy(PERMISSION_LEVELS)
        return context

    def form_valid(self, form):
        """Process the form and add shared user permissions."""
        # Save the object and get the response
        response = super().form_valid(form)

        # Process the shared users
        for key, value in self.request.POST.items():
            if (
                key.startswith("share_with_") and value
            ):  # Not empty value means the user is selected
                try:
                    user_id = key.split("_")[-1]
                    permission = int(value)
                    user = User.objects.get(id=user_id)

                    # Créer ou mettre à jour la permission pour cet utilisateur
                    create_or_update_permission(user, self.object, permission_level=permission)

                except Exception as e:
                    messages.error(self.request, str(e))

        return response


class BaseCreateView(LoginRequiredMixin, CreatePermissionMixin, CreateView):
    """Base class for create views."""

    template_name = "gift_manager/create_form.html"
    login_url = "/accounts/login/"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["type"] = self.object_type
        context["translated_type"] = gettext(self.object_type)
        context["action"] = gettext("Create")
        context["cancel_url"] = self.get_cancel_url()
        return context

    def get_cancel_url(self):
        """URL to redirect to when the cancel button is clicked."""
        return self.success_url

    def form_valid(self, form):
        with transaction.atomic():
            form.instance.user = self.request.user
            response = super().form_valid(form)
            create_or_update_permission(
                self.request.user,
                form.instance,
                permission_level=PermissionLevel.EDITOR,
                object_attr=self.context_object_name,
            )
            return response


class EditPermissionMixin:
    """Mixin to add shared user permissions to UpdateView forms."""

    def get_initial(self):
        initial = super().get_initial()
        self.object = self.get_object()

        # Get the current user profile and its friends
        current_user_profile = Profile.objects.get(user=self.request.user)
        friend_profiles = current_user_profile.friends.all()
        friend_users = User.objects.filter(profile__in=friend_profiles).order_by("username")

        # Prepare the lists for the shared users and unshared friends
        friends_list = []
        object_type = self.context_object_name
        all_shared_with = self.object.shared_with.all()

        # Process all friends and determine their sharing status
        for friend in friend_users:
            # Check if the friend is already shared with
            is_shared = friend in all_shared_with

            if is_shared:
                permission = get_permission(self.object, friend, object_type)
                permission_label = PermissionLevel.get_label(permission)

                friends_list.append(
                    {
                        "user": friend,
                        "permission": permission,
                        "permission_label": permission_label,
                        "form_id": f"perm_{friend.id}",  # Unique identifier for the form
                        "is_shared": True,
                    }
                )
            else:
                friends_list.append(
                    {
                        "user": friend,
                        "form_id": f"share_{friend.id}",  # Unique identifier for the form
                        "is_shared": False,
                    }
                )

        self.friends_list = friends_list
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if hasattr(self, "shared_users"):
            context["shared_users"] = self.shared_users
        if hasattr(self, "unshared_friends"):
            context["unshared_friends"] = self.unshared_friends
        if hasattr(self, "friends_list"):
            context["friends_list"] = self.friends_list

        # Add the permission levels available for the dropdown menus
        context["permission_levels"] = deepcopy(PERMISSION_LEVELS)
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

        # Case 1: Update an existing permission
        if "update_permission" in request.POST:
            return self._handle_update_permission(request)

        # Case 2: Remove an existing sharing
        if "remove_share" in request.POST:
            return self._handle_remove_share(request)

        # Case 3: Share the object with a new user
        if "share_with" in request.POST:
            return self._handle_share_with(request)

        # For other cases, call the parent post method
        return super().post(request, *args, **kwargs)

    def _handle_update_permission(self, request) -> JsonResponse:
        """Update an existing permission."""
        permission_value = request.POST.get("permission")

        try:
            user, username = get_user(request.POST.get("user_id"))

            # Si la permission est "not_shared", rediriger vers la méthode de suppression de partage
            if permission_value == "not_shared":
                return self._handle_remove_share(request)

            # Mettre à jour la permission
            new_permission = int(permission_value)
            create_or_update_permission(user, self.object, permission_level=new_permission)

            permission_label = PermissionLevel.get_label(new_permission)
            message = gettext("Permission for '{username}' changed to '{permission_level}'").format(
                username=username, permission_level=permission_label
            )

            if self.is_ajax:
                return JsonResponse(
                    {
                        "success": True,
                        "message": message,
                        "user": {"id": user.id, "username": username},
                        "permission": new_permission,
                    }
                )
            messages.success(request, message)
            return self.get(request)

        except Exception as e:
            return self._handle_error(request, e)

    def _handle_remove_share(self, request) -> JsonResponse:
        """Remove an existing sharing."""
        try:
            user, username = get_user(request.POST.get("user_id"))

            # Supprimer la permission
            delete_permission(user, self.object)

            message = gettext("Sharing with '{username}' removed successfully").format(
                username=username
            )

            if self.is_ajax:
                return JsonResponse(
                    {
                        "success": True,
                        "message": message,
                        "user": {"id": user.id, "username": username},
                    }
                )
            messages.success(request, message)
            return self.get(request)

        except Exception as e:
            return self._handle_error(request, e)

    def _handle_share_with(self, request) -> JsonResponse:
        """Share the object with a new user."""
        permission = int(request.POST.get("permission", PermissionLevel.VIEWER))

        try:
            user, username = get_user(request.POST.get("user_id"))

            # Créer ou mettre à jour la permission
            create_or_update_permission(user, self.object, permission_level=permission)

            message = gettext("Object shared with '{username}' successfully").format(
                username=username
            )

            if self.is_ajax:
                return JsonResponse(
                    {
                        "success": True,
                        "message": message,
                        "user": {"id": user.id, "username": username},
                        "permission": permission,
                    }
                )
            messages.success(request, message)
            return self.get(request)

        except Exception as e:
            return self._handle_error(request, e)

    def _handle_error(self, request, exception) -> JsonResponse:
        """Handle exceptions by returning appropriate response."""
        if self.is_ajax:
            return JsonResponse({"success": False, "message": str(exception)})
        messages.error(request, str(exception))
        return self.get(request)


class BaseUpdateView(
    FilterByUserMixin, GetObjectByTokenMixin, LoginRequiredMixin, EditPermissionMixin, UpdateView
):
    """Base class for update views."""

    template_name = "gift_manager/edit_form.html"
    login_url = "/accounts/login/"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["type"] = self.object_type
        context["translated_type"] = gettext(self.object_type)
        context["action"] = gettext("Edit")
        context["cancel_url"] = self.get_cancel_url()
        return context

    def get_cancel_url(self):
        """URL to redirect to when the cancel button is clicked."""
        return reverse_lazy(
            f"gift_manager:{self.detail_url_name}", kwargs={"pk": self.kwargs["pk"]}
        )

    def form_valid(self, form):
        with transaction.atomic():
            form.instance.user = self.request.user
            response = super().form_valid(form)
            create_or_update_permission(
                self.request.user,
                form.instance,
                permission_level=PermissionLevel.EDITOR,
                object_attr=self.context_object_name,
            )
            return response

    def get_success_url(self):
        return reverse(
            f"gift_manager:{self.detail_url_name}",
            kwargs={"pk": getattr(self.object, self.pk_name)},
        )


class DeleteSharedMixin:
    """Mixin to delete shared objects."""

    def post(self, request, *args, **kwargs):
        """Overload the delete method to handle conditional deletion.

        If the person is shared with other users, only the sharing with the current user is removed.
        Otherwise, the person is completely deleted.
        """
        with transaction.atomic():
            self.object = self.get_object()
            success_url = self.get_success_url()

            # Check if the person is shared with other users
            other_users = self.object.shared_with.exclude(id=request.user.id)

            if other_users.exists():
                # If shared, only remove the sharing with the current user
                self.object.shared_with.remove(request.user)

                # Delete the corresponding permission as well
                self.object.shared_with.through.objects.filter(
                    user=request.user, **{self.object_type: self.object}
                ).delete()

                messages.success(
                    request,
                    gettext(
                        "You no longer have access to this person, but it remains shared with "
                        "other users"
                    ),
                )
            else:
                # If not shared, completely delete the object
                self.object.delete()
                messages.success(request, gettext("Person successfully deleted"))

            return redirect(success_url)


class CancelToPreviousMixin:
    """Mixin to redirect to the previous page or a default URL."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Retrieve the referer URL (previous page) or use the default URL
        referer = self.request.META.get("HTTP_REFERER")
        context["cancel_url"] = referer if referer else self.success_url
        return context


class BaseDeleteView(
    FilterByUserMixin,
    GetObjectByTokenMixin,
    LoginRequiredMixin,
    DeleteSharedMixin,
    CancelToPreviousMixin,
    DeleteView,
):
    """Base class for delete views."""

    template_name = "gift_manager/confirm_delete.html"


class BaseDetailView(
    FilterByUserMixin,
    GetObjectByTokenMixin,
    LoginRequiredMixin,
    ContextPermissionMixin,
    SharedUsersMixin,
    DetailView,
):
    """Base class for detail views."""

    login_url = "/accounts/login/"
    redirect_field_name = "redirect_to"


class PersonListView(BaseListView):
    model = Person
    template_name = "gift_manager/person_list.html"
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
            PersonGroup.objects.filter(shared_with=self.request.user)
            .values("name")
            .distinct()
            .order_by("name")
        )

        return context

    def get_queryset(self):
        """Return Persons for the current user or shared with the user."""
        queryset = (
            Person.objects.filter(Q(shared_with=self.request.user))
            .values("person_id", *list(set(self.column_names.keys()).difference(["groups"])))
            .annotate(
                group_names=Coalesce(
                    ArrayAgg("groups__name", distinct=True),  # Retrieve the list of group names
                    [],
                ),
                group_ids=Coalesce(
                    ArrayAgg("groups__group_id", distinct=True),  # Retrieve the list of group UUIDs
                    [],
                ),
            )
        )

        # Transform the list of group names and UUIDs into a list of tuples
        for person in queryset:
            person["grouped_groups"] = [
                (i, j)
                for i, j in list(zip(person["group_names"], person["group_ids"]))
                if i is not None and j is not None
            ]

        return queryset


class PersonCreateView(BaseCreateView):
    model = Person
    form_class = PersonForm
    success_url = reverse_lazy("gift_manager:persons")
    context_object_name = "person"
    object_type = "Person"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["groups"].queryset = PersonGroup.objects.filter(
            shared_with=self.request.user
        ).order_by("name")
        return form


class PersonUpdateView(BaseUpdateView):
    model = Person
    form_class = PersonForm
    pk_name = "person_id"
    context_object_name = "person"
    object_type = "Person"
    detail_url_name = "person_detail"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["groups"].queryset = PersonGroup.objects.filter(
            shared_with=self.request.user
        ).order_by("name")
        return form


class PersonDeleteView(BaseDeleteView):
    model = Person
    success_url = reverse_lazy("gift_manager:persons")
    pk_name = "person_id"
    object_type = "person"


class PersonDetailView(BaseDetailView):
    model = Person
    template_name = "gift_manager/person_detail.html"
    context_object_name = "person"
    pk_name = "person_id"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["relations"] = Relation.objects.filter(
            (Q(person=self.object) | Q(group__in=self.object.groups.all()))
            & Q(shared_with=self.request.user)
        ).select_related("status")
        context["relation_statuses"] = RelationStatus.objects.all()
        return context


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
        return PersonGroup.objects.filter(Q(shared_with=self.request.user)).values(
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
        context["persons"] = Person.objects.filter(
            groups=self.object, shared_with=self.request.user
        )
        context["gifts"] = Relation.objects.filter(
            group=self.object, shared_with=self.request.user, gift__isnull=False
        )
        context["shared_with"] = self.object.shared_with.exclude(id=self.request.user.id)
        return context


class GiftListView(BaseListView):
    model = Gift
    template_name = "gift_manager/gift_list.html"
    object_type = "Gifts"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.column_names = {
            "name": gettext("Gift name"),
            "comment": gettext("Comment"),
            "tags": gettext("Tags"),
        }

    def get_queryset(self):
        """Return Gifts for the current user or shared with the user."""
        return Gift.objects.filter(Q(shared_with=self.request.user)).values(
            "gift_id", *self.column_names
        )


class GiftCreateView(BaseCreateView):
    model = Gift
    form_class = GiftForm
    success_url = reverse_lazy("gift_manager:gifts")
    context_object_name = "gift"
    object_type = "Gift"


class GiftUpdateView(BaseUpdateView):
    model = Gift
    form_class = GiftForm
    pk_name = "gift_id"
    context_object_name = "gift"
    object_type = "Gift"
    detail_url_name = "gift_detail"


class GiftDeleteView(BaseDeleteView):
    model = Gift
    success_url = reverse_lazy("gift_manager:gifts")
    pk_name = "gift_id"
    object_type = "gift"


class GiftDetailView(BaseDetailView):
    model = Gift
    template_name = "gift_manager/gift_detail.html"
    context_object_name = "gift"
    pk_name = "gift_id"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["relations"] = Relation.objects.filter(
            gift=self.object, shared_with=self.request.user
        )
        context["shared_with"] = self.object.shared_with.exclude(id=self.request.user.id)
        return context


class EventListView(BaseListView):
    model = Event
    template_name = "gift_manager/event_list.html"
    object_type = "Events"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.column_names = {
            "name": gettext("Event name"),
            "comment": gettext("Comment"),
            "usual_date": gettext("Usual date"),
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["type"] = "Events"
        context["translated_type"] = gettext("Events")
        context["column_names"] = self.column_names
        return context

    def get_queryset(self):
        """Return Events for the current user or shared with the user."""
        return Event.objects.filter(Q(shared_with=self.request.user)).values(
            "event_id", *self.column_names
        )


class EventCreateView(BaseCreateView):
    model = Event
    form_class = EventForm
    success_url = reverse_lazy("gift_manager:events")
    context_object_name = "event"
    object_type = "Event"


class EventUpdateView(BaseUpdateView):
    model = Event
    form_class = EventForm
    pk_name = "event_id"
    context_object_name = "event"
    object_type = "Event"
    detail_url_name = "event_detail"


class EventDeleteView(BaseDeleteView):
    model = Event
    success_url = reverse_lazy("gift_manager:events")
    pk_name = "event_id"
    object_type = "event"


class EventDetailView(BaseDetailView):
    model = Event
    template_name = "gift_manager/event_detail.html"
    context_object_name = "event"
    pk_name = "event_id"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["relations"] = Relation.objects.filter(
            event=self.object, shared_with=self.request.user
        ).select_related("person", "group", "gift", "event", "status")
        context["shared_with"] = self.object.shared_with.exclude(id=self.request.user.id)
        return context


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
        form.fields["gift"].queryset = Gift.objects.filter(shared_with=self.request.user).order_by(
            "name"
        )
        form.fields["event"].queryset = Event.objects.filter(
            shared_with=self.request.user
        ).order_by("name")
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
        form.fields["gift"].queryset = Gift.objects.filter(shared_with=self.request.user).order_by(
            "name"
        )
        form.fields["event"].queryset = Event.objects.filter(
            shared_with=self.request.user
        ).order_by("name")
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
            Person.objects.filter(shared_with=self.request.user)
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
        form.fields["group"].queryset = PersonGroup.objects.filter(
            shared_with=self.request.user
        ).order_by("name")
        form.fields["event"].queryset = Event.objects.filter(
            shared_with=self.request.user
        ).order_by("name")
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
        context["relations"] = Relation.objects.filter(
            Q(status=self.object) & Q(shared_with=self.request.user)
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
            Relation.objects.filter(Q(shared_with=self.request.user))
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
            Person.objects.filter(shared_with=self.request.user)
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
        form.fields["gift"].queryset = Gift.objects.filter(shared_with=self.request.user).order_by(
            "name"
        )
        form.fields["event"].queryset = Event.objects.filter(
            shared_with=self.request.user
        ).order_by("name")
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
            Person.objects.filter(shared_with=self.request.user)
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
        form.fields["gift"].queryset = Gift.objects.filter(shared_with=self.request.user).order_by(
            "name"
        )
        form.fields["event"].queryset = Event.objects.filter(
            shared_with=self.request.user
        ).order_by("name")
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
            Person.objects.filter(shared_with=request.user)
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
            PersonGroup.objects.filter(shared_with=request.user)
            .prefetch_related("person_set")
            .order_by("name")
        )
        gifts = Gift.objects.filter(shared_with=request.user).order_by("name")
        events = Event.objects.filter(shared_with=request.user).order_by("name")
        relations = (
            Relation.objects.filter(shared_with=request.user)
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

            # Get selected objects by type
            selection = self._get_selection_from_request(request)

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
