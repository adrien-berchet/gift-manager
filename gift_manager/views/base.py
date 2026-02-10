"""Base classes and mixins for views."""

import json
import logging
from copy import deepcopy

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.db import transaction
from django.http import Http404
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.urls import reverse_lazy
from django.utils.translation import gettext
from django.views.generic import CreateView
from django.views.generic import DeleteView
from django.views.generic import DetailView
from django.views.generic import ListView
from django.views.generic import UpdateView

from gift_manager.models import PermissionLevel
from gift_manager.models import Profile
from gift_manager.permissions import PERMISSION_LEVELS
from gift_manager.services import PermissionService
from gift_manager.views.common import get_user

logger = logging.getLogger(__name__)


class HTMXResponseMixin:
    """Mixin to handle HTMX-specific responses and template selection."""

    htmx_template_name = None
    close_modal = False
    close_offcanvas = False

    def dispatch(self, request, *args, **kwargs):
        """Detect HTMX requests and store the flag."""
        self.is_htmx = request.headers.get("HX-Request") == "true"
        return super().dispatch(request, *args, **kwargs)

    def get_template_names(self):
        """Return HTMX-specific template if available and request is HTMX."""
        if self.is_htmx and hasattr(self, "htmx_template_name") and self.htmx_template_name:
            return [self.htmx_template_name]
        return super().get_template_names()

    def form_valid(self, form):
        """Handle successful form submission with HTMX-specific responses."""
        response = super().form_valid(form)

        logger.debug(
            f"[HTMXResponseMixin.form_valid] is_htmx={self.is_htmx}, response status={getattr(response, 'status_code', 'N/A')}"
        )

        if self.is_htmx:
            # Build HX-Trigger events
            triggers = []

            # Always trigger list update for CRUD operations
            triggers.append("list:update")

            # Add modal/offcanvas close triggers if specified
            if getattr(self, "close_modal", False):
                triggers.append("modal:close")
            if getattr(self, "close_offcanvas", False):
                triggers.append("offcanvas:close")

            # Add success notification
            if hasattr(self, "get_success_message"):
                success_message = self.get_success_message()
                if success_message:
                    triggers.append(
                        json.dumps(
                            {"showNotification": {"message": success_message, "type": "success"}}
                        )
                    )

            # For HTMX requests, don't redirect - return empty response with triggers
            if hasattr(response, "status_code") and response.status_code == 302:
                response = HttpResponse("")

            # Set HX-Trigger header on the final response
            if triggers:
                trigger_value = ", ".join(triggers)
                response["HX-Trigger"] = trigger_value
                logger.debug(f"[HTMXResponseMixin.form_valid] Set HX-Trigger: {trigger_value}")

        logger.debug(
            f"[HTMXResponseMixin.form_valid] Final response status={getattr(response, 'status_code', 'N/A')}, headers={dict(response.items()) if hasattr(response, 'items') else 'N/A'}"
        )
        return response

    def form_invalid(self, form):
        """Handle form validation errors with HTMX-specific responses."""
        response = super().form_invalid(form)

        if self.is_htmx:
            # Add error notification trigger
            error_message = "Please correct the errors below."
            response["HX-Trigger"] = json.dumps(
                {"showNotification": {"message": error_message, "type": "error"}}
            )

        return response

    def delete(self, request, *args, **kwargs):
        """Handle DELETE requests with HTMX-specific responses."""
        response = super().delete(request, *args, **kwargs)

        if self.is_htmx:
            # Build HX-Trigger events for delete operations
            triggers = []

            # Always trigger list update for delete operations
            triggers.append("list:update")

            # Add modal close trigger if specified
            if getattr(self, "close_modal", False):
                triggers.append("modal:close")

            # Add success notification
            if hasattr(self, "get_success_message"):
                success_message = self.get_success_message()
                if success_message:
                    triggers.append(
                        json.dumps(
                            {"showNotification": {"message": success_message, "type": "success"}}
                        )
                    )

            # Set HX-Trigger header
            if triggers:
                response["HX-Trigger"] = ", ".join(triggers)

            # For HTMX requests, don't redirect - return empty response
            if hasattr(response, "status_code") and response.status_code == 302:
                return HttpResponse("")

        return response

    def get_success_message(self):
        """Override in subclasses to provide success messages."""
        return


class FilterByUserMixin:
    """Mixin to filter objects by the current user."""

    def get_queryset(self):
        return self.model.objects.accessible_by(self.request.user)


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

    def get_context_data(self, **kwargs) -> dict:
        context = super().get_context_data(**kwargs)
        context["is_editor"] = (
            PermissionService.get_permission(self.object, self.request.user)
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

    def get_context_data(self, **kwargs) -> dict:
        context = super().get_context_data(**kwargs)
        context["type"] = self.object_type
        context["translated_type"] = gettext(self.object_type)
        context["column_names"] = self.column_names
        return context


class SharedUsersMixin:
    """Mixin to add shared users with their permissions to the context."""

    def get_context_data(self, **kwargs) -> dict:
        context = super().get_context_data(**kwargs)

        # Get the users with whom this object is shared, with their permissions
        shared_users = []
        for user in self.object.shared_with.exclude(id=self.request.user.id).order_by("username"):
            permission = PermissionService.get_permission(self.object, user)
            permission_label = PermissionLevel.get_label(permission)
            shared_users.append(
                {"user": user, "permission": permission, "permission_label": permission_label}
            )

        context["shared_users"] = shared_users
        return context


class CreatePermissionMixin:
    """Mixin to add shared user permissions to CreateView forms."""

    def get_initial(self) -> dict:
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

    def get_context_data(self, **kwargs) -> dict:
        context = super().get_context_data(**kwargs)
        if hasattr(self, "unshared_friends"):
            context["unshared_friends"] = self.unshared_friends

        # Add the permission levels available for the dropdown menus
        # Force evaluation of lazy translations in the current language context
        context["permission_levels"] = [
            {"value": level["value"], "label": str(level["label"])} for level in PERMISSION_LEVELS
        ]
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
                    PermissionService.create_or_update_permission(
                        user, self.object, permission_level=permission
                    )

                except (ValueError, TypeError) as e:
                    logger.warning("Invalid permission value: %s", e)
                    messages.error(self.request, gettext("Invalid permission value."))
                except User.DoesNotExist:
                    logger.warning("User not found: %s", user_id)
                    messages.error(self.request, gettext("User not found."))

        return response


class BaseCreateView(LoginRequiredMixin, CreatePermissionMixin, HTMXResponseMixin, CreateView):
    """Base class for create views."""

    template_name = "gift_manager/create_form.html"
    htmx_template_name = "gift_manager/includes/form_partial.html"
    close_offcanvas = True
    login_url = "/accounts/login/"

    def get_context_data(self, **kwargs) -> dict:
        context = super().get_context_data(**kwargs)
        context["type"] = self.object_type
        context["translated_type"] = gettext(self.object_type)
        context["action"] = gettext("Create")
        context["cancel_url"] = self.get_cancel_url()
        return context

    def get_cancel_url(self) -> str:
        """URL to redirect to when the cancel button is clicked."""
        # Prefer dynamic success URL if provided by subclass
        try:
            url = self.get_success_url()
            if url:
                return url
        except Exception:  # noqa: S110
            pass
        # Fallback to static success_url if defined
        return getattr(self, "success_url", "/")

    def form_valid(self, form):
        try:
            with transaction.atomic():
                # Only set user_link if the model has that field
                if hasattr(form.instance, "user_link"):
                    logger.debug(
                        f"[BaseCreateView.form_valid] Setting user_link to {self.request.user} (id={self.request.user.id})"
                    )
                    form.instance.user_link = self.request.user
                else:
                    logger.debug(
                        f"[BaseCreateView.form_valid] Model {form.instance.__class__.__name__} has no user_link field"
                    )

                response = super().form_valid(form)

                # Log the saved instance
                pk_field = getattr(form.instance, "pk", None) or getattr(
                    form.instance, f"{form.instance.__class__.__name__.lower()}_id", None
                )
                saved_user_link = getattr(form.instance, "user_link", None)
                logger.debug(
                    f"[BaseCreateView.form_valid] After save: pk={pk_field}, user_link={saved_user_link}"
                )

                PermissionService.create_or_update_permission(
                    self.request.user,
                    form.instance,
                    permission_level=PermissionLevel.OWNER,
                    object_attr=self.context_object_name,
                )
                return response
        except Exception as e:
            logger.exception("Error in BaseCreateView.form_valid: %s", e)
            raise

    def get_success_message(self):
        """Return success message for create operations."""
        return gettext("{} created successfully").format(gettext(self.object_type))


class EditPermissionMixin:
    """Mixin to add shared user permissions to UpdateView forms."""

    def get_initial(self) -> dict:
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
                permission = PermissionService.get_permission(self.object, friend)
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
                        "permission": None,
                        "form_id": f"share_{friend.id}",  # Unique identifier for the form
                        "is_shared": False,
                    }
                )

        self.friends_list = friends_list
        return initial

    def get_context_data(self, **kwargs) -> dict:
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

    def post(self, request, *args, **kwargs):  # noqa: PLR0911
        self.object = self.get_object()
        self.is_htmx = request.headers.get("HX-Request") == "true"

        # Case 1: Update an existing permission
        if "update_permission" in request.POST:
            return self._handle_update_permission(request)

        # Case 2: Remove an existing sharing
        if "remove_share" in request.POST:
            return self._handle_remove_share(request)

        # Case 3: Share the object with a new user
        if "share_with" in request.POST:
            return self._handle_share_with(request)

        # HTMX permission change (no explicit action parameter)
        if self.is_htmx and "permission" in request.POST:
            permission_value = request.POST.get("permission")
            if permission_value == "not_shared":
                return self._handle_remove_share(request)

            # Check if user is already shared
            user_id = request.POST.get("user_id")
            user = User.objects.get(id=user_id)
            is_shared = self.object.shared_with.filter(id=user.id).exists()

            if is_shared:
                return self._handle_update_permission(request)
            return self._handle_share_with(request)

        # For other cases, call the parent post method
        return super().post(request, *args, **kwargs)

    def _handle_update_permission(self, request) -> HttpResponse:
        """Update an existing permission."""
        permission_value = request.POST.get("permission")

        try:
            user, username = get_user(request.POST.get("user_id"))

            # If the permission is "not_shared", redirect to the share removal method
            if permission_value == "not_shared":
                return self._handle_remove_share(request)

            # Update the permission
            new_permission = int(permission_value)
            PermissionService.create_or_update_permission(
                user, self.object, permission_level=new_permission
            )

            permission_label = PermissionLevel.get_label(new_permission)
            message = gettext("Permission for '{username}' changed to '{permission_level}'").format(
                username=username, permission_level=permission_label
            )

            if self.is_htmx:
                # Return HTML partial for HTMX with trigger for notification

                response = render(
                    request,
                    "gift_manager/includes/permission_row_partial.html",
                    {
                        "shared_user": user,
                        "permission": new_permission,
                        "permission_levels": PERMISSION_LEVELS,
                        "is_shared": True,
                        "update_url": request.path,
                    },
                )
                response["HX-Trigger"] = json.dumps({"showSuccess": message})
                return response

            # Fallback for non-HTMX requests
            messages.success(request, message)
            return self.get(request)

        except User.DoesNotExist:
            logger.warning("User not found for permission update: %s", request.POST.get("user_id"))
            return self._handle_error(request, gettext("User not found."))
        except (ValueError, TypeError) as e:
            logger.warning("Invalid permission value: %s", e)
            return self._handle_error(request, gettext("Invalid permission value."))

    def _handle_remove_share(self, request) -> HttpResponse:
        """Remove an existing sharing."""
        try:
            user, username = get_user(request.POST.get("user_id"))

            # Remove the permission
            PermissionService.delete_permission(user, self.object)

            message = gettext("Sharing with '{username}' removed successfully").format(
                username=username
            )

            if self.is_htmx:
                # Return HTML partial for HTMX with trigger for notification

                response = render(
                    request,
                    "gift_manager/includes/permission_row_partial.html",
                    {
                        "shared_user": user,
                        "permission": None,
                        "permission_levels": PERMISSION_LEVELS,
                        "is_shared": False,
                        "update_url": request.path,
                    },
                )
                response["HX-Trigger"] = json.dumps({"showSuccess": message})
                return response

            # Fallback for non-HTMX requests
            messages.success(request, message)
            return self.get(request)

        except User.DoesNotExist:
            logger.warning("User not found for share removal: %s", request.POST.get("user_id"))
            return self._handle_error(request, gettext("User not found."))

    def _handle_share_with(self, request) -> HttpResponse:
        """Share the object with a new user."""
        try:
            permission = int(request.POST.get("permission", PermissionLevel.VIEWER))
            user, username = get_user(request.POST.get("user_id"))

            # Create or update the permission
            PermissionService.create_or_update_permission(
                user, self.object, permission_level=permission
            )

            message = gettext("Object shared with '{username}' successfully").format(
                username=username
            )

            if self.is_htmx:
                # Return HTML partial for HTMX with trigger for notification

                response = render(
                    request,
                    "gift_manager/includes/permission_row_partial.html",
                    {
                        "shared_user": user,
                        "permission": permission,
                        "permission_levels": PERMISSION_LEVELS,
                        "is_shared": True,
                        "update_url": request.path,
                    },
                )
                response["HX-Trigger"] = json.dumps({"showSuccess": message})
                return response

            # Fallback for non-HTMX requests
            messages.success(request, message)
            return self.get(request)

        except User.DoesNotExist:
            logger.warning("User not found for sharing: %s", request.POST.get("user_id"))
            return self._handle_error(request, gettext("User not found."))
        except (ValueError, TypeError) as e:
            logger.warning("Invalid permission value for sharing: %s", e)
            return self._handle_error(request, gettext("Invalid permission value."))

    def _handle_error(self, request, error_message: str) -> HttpResponse:
        """Handle errors by returning appropriate response.

        Args:
            request: The HTTP request.
            error_message: The error message to display to the user.
        """
        messages.error(request, error_message)
        return self.get(request)


class BaseUpdateView(
    FilterByUserMixin,
    GetObjectByTokenMixin,
    LoginRequiredMixin,
    EditPermissionMixin,
    HTMXResponseMixin,
    UpdateView,
):
    """Base class for update views."""

    template_name = "gift_manager/edit_form.html"
    htmx_template_name = "gift_manager/includes/form_partial.html"
    close_offcanvas = True
    login_url = "/accounts/login/"

    def get_context_data(self, **kwargs) -> dict:
        context = super().get_context_data(**kwargs)
        context["type"] = self.object_type
        context["translated_type"] = gettext(self.object_type)
        context["action"] = gettext("Edit")
        context["cancel_url"] = self.get_cancel_url()
        return context

    def get_cancel_url(self) -> str:
        """URL to redirect to when the cancel button is clicked."""
        return reverse_lazy(
            f"gift_manager:{self.detail_url_name}", kwargs={"pk": self.kwargs["pk"]}
        )

    def form_valid(self, form):
        with transaction.atomic():
            # Only set user_link if the model has that field
            if hasattr(form.instance, "user_link"):
                form.instance.user_link = self.request.user
            response = super().form_valid(form)
            PermissionService.create_or_update_permission(
                self.request.user,
                form.instance,
                permission_level=PermissionLevel.EDITOR,
                object_attr=self.context_object_name,
            )
            return response

    def get_success_url(self) -> str:
        return reverse(
            f"gift_manager:{self.detail_url_name}",
            kwargs={"pk": getattr(self.object, self.pk_name)},
        )

    def get_success_message(self):
        """Return success message for update operations."""
        return gettext("{} updated successfully").format(gettext(self.object_type))


class DeleteSharedMixin:
    """Mixin to delete shared objects."""

    def post(self, request, *args, **kwargs):
        """Overload the delete method to handle conditional deletion.

        If the object is shared with other users, only the sharing with the current user is removed.
        Otherwise, the object is completely deleted.
        """
        with transaction.atomic():
            self.object = self.get_object()
            success_url = self.get_success_url()

            # Check if the object is shared with other users
            other_users = self.object.shared_with.exclude(id=request.user.id)

            if other_users.exists():
                # If shared, only remove the sharing with the current user
                self.object.shared_with.remove(request.user)

                # Delete the corresponding permission as well
                self.object.shared_with.through.objects.filter(
                    user=request.user, **{self.object_type: self.object}
                ).delete()

                success_message = gettext(
                    "You no longer have access to this {}, but it remains shared with other users"
                ).format(gettext(self.object_type).lower())
            else:
                # If not shared, completely delete the object
                self.object.delete()
                success_message = gettext("{} successfully deleted").format(
                    gettext(self.object_type)
                )

            # Handle HTMX vs regular requests
            is_htmx = getattr(self, "is_htmx", False)
            logger.debug(f"Delete request - is_htmx: {is_htmx}, headers: {request.headers}")

            if is_htmx:
                # For HTMX requests, return appropriate response with triggers
                response = HttpResponse("")

                # Build HX-Trigger events
                triggers = []
                triggers.append("list:update")

                if getattr(self, "close_modal", False):
                    triggers.append("modal:close")

                triggers.append(
                    json.dumps(
                        {"showNotification": {"message": success_message, "type": "success"}}
                    )
                )

                response["HX-Trigger"] = ", ".join(triggers)
                logger.debug(f"HTMX response - HX-Trigger: {response['HX-Trigger']}")
                return response
            # For regular requests, add message and redirect
            logger.debug(f"Regular response - redirecting to: {success_url}")
            messages.success(request, success_message)
            return redirect(success_url)


class CancelToPreviousMixin:
    """Mixin to redirect to the previous page or a default URL."""

    def get_context_data(self, **kwargs) -> dict:
        context = super().get_context_data(**kwargs)
        # Retrieve the referer URL (previous page) or use the default URL
        referer = self.request.META.get("HTTP_REFERER")
        context["cancel_url"] = referer if referer else self.success_url
        return context


class DeleteConfirmationMixin:
    """Mixin to provide delete confirmation data for modal templates."""

    def get_entity_icon(self):
        """Return the FontAwesome icon class for the entity type."""
        icon_map = {
            "person": "user",
            "gift": "gift",
            "event": "calendar-alt",
            "relation": "hand-holding-heart",
            "persongroup": "layer-group",
            "gifttag": "tag",
        }
        return icon_map.get(self.object_type.lower(), "cube")

    def get_entity_details(self):
        """Return a list of additional details to display for the entity."""
        details = []

        # Add common details based on object attributes
        if hasattr(self.object, "email_address") and self.object.email_address:
            details.append(f"Email: {self.object.email_address}")

        if hasattr(self.object, "created_at") and self.object.created_at:
            details.append(f"Created: {self.object.created_at.strftime('%Y-%m-%d')}")

        if hasattr(self.object, "usual_date") and self.object.usual_date:
            details.append(f"Date: {self.object.usual_date}")

        if hasattr(self.object, "price") and self.object.price:
            details.append(f"Price: ${self.object.price}")

        return details

    def get_related_objects(self):
        """Return information about related objects that will be affected."""
        related = []

        # Check for common relationships
        if hasattr(self.object, "gifts") and hasattr(self.object.gifts, "count"):
            count = self.object.gifts.count()
            if count > 0:
                related.append(
                    {"name": "gift", "name_plural": "gifts", "count": count, "icon": "gift"}
                )

        if hasattr(self.object, "events") and hasattr(self.object.events, "count"):
            count = self.object.events.count()
            if count > 0:
                related.append(
                    {
                        "name": "event",
                        "name_plural": "events",
                        "count": count,
                        "icon": "calendar-alt",
                    }
                )

        if hasattr(self.object, "relations") and hasattr(self.object.relations, "count"):
            count = self.object.relations.count()
            if count > 0:
                related.append(
                    {
                        "name": "relation",
                        "name_plural": "relations",
                        "count": count,
                        "icon": "hand-holding-heart",
                    }
                )

        return related

    def get_cascade_warning(self):
        """Return a warning message about cascade deletions if applicable."""
        # Override in subclasses for specific cascade warnings
        return

    def get_additional_fields(self):
        """Return additional form fields needed for deletion."""
        return {}


class BaseDeleteView(
    FilterByUserMixin,
    GetObjectByTokenMixin,
    LoginRequiredMixin,
    DeleteSharedMixin,
    CancelToPreviousMixin,
    DeleteConfirmationMixin,
    HTMXResponseMixin,
    DeleteView,
):
    """Base class for delete views."""

    template_name = "gift_manager/confirm_delete.html"
    htmx_template_name = "gift_manager/includes/delete_confirmation_modal.html"
    close_modal = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "entity_type": gettext(self.object_type),
                "entity_name": str(self.object),
                "entity_description": getattr(self.object, "description", None),
                "entity_icon": self.get_entity_icon(),
                "entity_details": self.get_entity_details(),
                "delete_url": self.request.path,
                "related_objects": self.get_related_objects(),
                "cascade_warning": self.get_cascade_warning(),
                "additional_fields": self.get_additional_fields(),
            }
        )
        return context

    def get_success_message(self):
        """Return success message for delete operations."""
        return gettext("{} deleted successfully").format(gettext(self.object_type))


class BaseDetailView(
    FilterByUserMixin,
    GetObjectByTokenMixin,
    LoginRequiredMixin,
    ContextPermissionMixin,
    SharedUsersMixin,
    HTMXResponseMixin,
    DetailView,
):
    """Base class for detail views."""

    htmx_template_name = "gift_manager/includes/detail_partial.html"
    login_url = "/accounts/login/"
    redirect_field_name = "redirect_to"
