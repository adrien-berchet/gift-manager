"""Base classes and mixins for views."""

from copy import deepcopy

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from ..models import PermissionLevel, Profile
from ..permissions import (
    PERMISSION_LEVELS,
    create_or_update_permission,
    delete_permission,
    get_permission,
)
from .common import get_user


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


class ContextPermissionMixin:
    """Mixin to add permission context to the view."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_editor"] = (
            get_permission(self.object, self.request.user) >= PermissionLevel.EDITOR
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
            permission = get_permission(self.object, user)
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

                    # Create or update the permission for this user
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
        all_shared_with = self.object.shared_with.all()

        # Process all friends and determine their sharing status
        for friend in friend_users:
            # Check if the friend is already shared with
            is_shared = friend in all_shared_with

            if is_shared:
                permission = get_permission(self.object, friend)
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

            # If the permission is "not_shared", redirect to the share removal method
            if permission_value == "not_shared":
                return self._handle_remove_share(request)

            # Update the permission
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

            # Remove the permission
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

            # Create or update the permission
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
