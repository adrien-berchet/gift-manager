"""Permission-related mixins for views."""

import json
import logging
from typing import Any

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.http import HttpResponse
from django.http import JsonResponse

from gift_manager.models import PermissionLevel
from gift_manager.services import PermissionService

logger = logging.getLogger(__name__)


class PermissionContextMixin:
    """Mixin to add permission context data to views."""

    def get_permission_context(self, objects=None) -> dict[str, Any]:
        """Get permission context for the current user and objects.

        Args:
            objects: List of objects to check permissions for.
                    If None, uses self.get_queryset() or self.object_list

        Returns:
            Dict containing permission data for templates
        """
        if not self.request.user.is_authenticated:
            return {
                "user_permissions": {},
                "user_permissions_json": "{}",
                "permission_levels": PermissionLevel.CHOICES,
            }

        # Get objects to check permissions for
        if objects is None:
            if hasattr(self, "object_list") and self.object_list is not None:
                objects = self.object_list
            elif hasattr(self, "get_queryset"):
                try:
                    objects = self.get_queryset()
                except Exception:
                    objects = []
            else:
                objects = []

        # Build permission mapping
        permissions = self._build_permissions_mapping(objects)

        return {
            "user_permissions": permissions,
            "user_permissions_json": json.dumps(permissions),
            "permission_levels": PermissionLevel.CHOICES,
        }

    def _build_permissions_mapping(self, objects) -> dict[str, int]:
        """Build a mapping of object IDs to permission levels.

        Handles both model instances and dictionaries from .values() querysets.

        Args:
            objects: Iterable of model instances or dictionaries

        Returns:
            Dict mapping object IDs (as strings) to permission levels
        """
        permissions = {}

        # Common ID field names for different entity types
        id_fields = ["id", "person_id", "gift_id", "event_id", "relation_id", "group_id", "tag_id"]

        # Check if objects are dictionaries (from .values() queryset)
        objects_list = list(objects)
        if not objects_list:
            return permissions

        first_obj = objects_list[0]
        is_dict = isinstance(first_obj, dict)

        if is_dict:
            # Objects are dictionaries from .values() - need to query permissions directly
            permissions = self._build_permissions_from_dicts(objects_list, id_fields)
        else:
            # Objects are model instances - use PermissionService directly
            permissions = self._build_permissions_from_instances(objects_list, id_fields)

        return permissions

    def _build_permissions_from_dicts(self, objects: list, id_fields: list) -> dict[str, int]:
        """Build permissions mapping from dictionary objects.

        When queryset uses .values(), we get dictionaries instead of model instances.
        We need to query the permission model directly using IDs.

        Args:
            objects: List of dictionaries from .values() queryset
            id_fields: List of possible ID field names to check

        Returns:
            Dict mapping object IDs (as strings) to permission levels
        """
        permissions = {}

        if not objects:
            return permissions

        # Extract IDs from dictionaries
        first_obj = objects[0]
        id_field = None
        for field in id_fields:
            if field in first_obj:
                id_field = field
                break

        if not id_field:
            return permissions

        # Get the model from the view to find the permission model
        model = getattr(self, "model", None)
        if not model:
            return permissions

        # Get the permission model using the shared_with through table
        try:
            permission_model = model.shared_with.through
        except AttributeError:
            return permissions

        # Get the filter name from the permission model
        try:
            filter_field = permission_model.filter_name
        except AttributeError:
            # Fall back to model name lowercase
            filter_field = model.__name__.lower()

        # Extract all IDs from the objects
        object_ids = [obj[id_field] for obj in objects if obj.get(id_field)]

        if not object_ids:
            return permissions

        # Query all permissions at once for better performance
        # Use FK traversal (e.g., person__person_id__in) because id_field (e.g., person_id)
        # is a UUID field on the model, not the actual primary key
        filter_kwargs = {"user": self.request.user, f"{filter_field}__{id_field}__in": object_ids}
        permission_queryset = permission_model.objects.filter(**filter_kwargs).select_related(
            filter_field
        )

        # Build the permissions mapping from explicit permission records
        for perm in permission_queryset:
            # Get the id_field value from the related object (e.g., perm.person.person_id)
            related_obj = getattr(perm, filter_field)
            obj_id = getattr(related_obj, id_field)
            permissions[str(obj_id)] = perm.permission_type

        # Also check for ownership via user_link field
        # Objects where user_link matches the current user should get OWNER permission
        user_id = self.request.user.id
        logger.debug(
            f"[_build_permissions_from_dicts] Checking ownership. user_id={user_id} (type={type(user_id).__name__})"
        )

        for obj in objects:
            obj_id = str(obj.get(id_field))
            # Check if user_link field exists and matches current user
            user_link_id = obj.get("user_link_id") or obj.get("user_link")
            logger.debug(
                f"[_build_permissions_from_dicts] obj_id={obj_id}, "
                f"user_link_id={user_link_id} (type={type(user_link_id).__name__ if user_link_id else 'None'}), "
                f"match={user_link_id == user_id if user_link_id else False}"
            )
            if user_link_id is not None and user_link_id == user_id:
                # User is the owner, grant OWNER permission
                permissions[obj_id] = PermissionLevel.OWNER
                logger.debug(f"[_build_permissions_from_dicts] Granted OWNER to {obj_id}")
            elif obj_id not in permissions:
                # No permission found, will default to NONE
                logger.debug(f"[_build_permissions_from_dicts] No permission for {obj_id}")

        logger.debug(f"[_build_permissions_from_dicts] Final permissions: {permissions}")
        return permissions

    def _build_permissions_from_instances(self, objects: list, id_fields: list) -> dict[str, int]:
        """Build permissions mapping from model instances.

        Args:
            objects: List of model instances
            id_fields: List of possible ID field names to check

        Returns:
            Dict mapping object IDs (as strings) to permission levels.
            Keys are UUID fields (e.g. group_id, person_id) when available,
            since Grid.js templates use UUIDs for entity identification.
        """
        permissions = {}

        for obj in objects:
            try:
                # Prefer UUID id fields (e.g. group_id, person_id) over auto-generated pk,
                # because Grid.js templates use UUIDs as entity identifiers for permission lookups.
                obj_id = None
                for id_field in id_fields:
                    if id_field != "id" and hasattr(obj, id_field):
                        obj_id = getattr(obj, id_field)
                        if obj_id is not None:
                            break

                # Fall back to pk if no UUID field found
                if obj_id is None:
                    obj_id = getattr(obj, "pk", None)

                if obj_id:
                    permission = PermissionService.get_permission(obj, self.request.user)
                    permissions[str(obj_id)] = permission
            except (AttributeError, TypeError):
                # Skip objects that don't support permissions
                continue

        return permissions

    def get_context_data(self, **kwargs) -> dict[str, Any]:
        """Add permission context to the template context."""
        context = super().get_context_data(**kwargs)
        context.update(self.get_permission_context())
        return context


class SingleObjectPermissionMixin:
    """Mixin to add permission context for a single object."""

    def get_context_data(self, **kwargs) -> dict[str, Any]:
        """Add permission context for the current object."""
        context = super().get_context_data(**kwargs)

        if hasattr(self, "object") and self.object and self.request.user.is_authenticated:
            try:
                permission = PermissionService.get_permission(self.object, self.request.user)
                context.update(
                    {
                        "user_permission": permission,
                        "can_edit": permission >= PermissionLevel.EDITOR,
                        "can_delete": permission >= PermissionLevel.OWNER,
                        "can_share": permission >= PermissionLevel.EDITOR,
                        "can_view": permission > PermissionLevel.NONE,
                        "permission_level_name": PermissionLevel.get_label(permission),
                    }
                )
            except (AttributeError, TypeError):
                # Object doesn't support permissions
                context.update(
                    {
                        "user_permission": PermissionLevel.NONE,
                        "can_edit": False,
                        "can_delete": False,
                        "can_share": False,
                        "can_view": False,
                        "permission_level_name": "None",
                    }
                )

        return context


class BulkPermissionMixin:
    """Mixin to handle bulk operations with permission checking."""

    def check_bulk_permissions(self, objects, required_permission=PermissionLevel.EDITOR):
        """Check permissions for bulk operations.

        Args:
            objects: List of objects to check
            required_permission: Minimum permission level required

        Returns:
            Tuple of (allowed_objects, denied_objects)
        """
        if not self.request.user.is_authenticated:
            return [], list(objects)

        allowed = []
        denied = []

        for obj in objects:
            try:
                permission = PermissionService.get_permission(obj, self.request.user)
                if permission >= required_permission:
                    allowed.append(obj)
                else:
                    denied.append(obj)
            except (AttributeError, TypeError):
                # Object doesn't support permissions - deny by default
                denied.append(obj)

        return allowed, denied

    def filter_by_permission(self, queryset, required_permission=PermissionLevel.VIEWER):
        """Filter queryset to only include objects user has permission for.

        Args:
            queryset: Django queryset to filter
            required_permission: Minimum permission level required

        Returns:
            Filtered queryset
        """
        if not self.request.user.is_authenticated:
            return queryset.none()

        # For objects with shared_with relationship, filter by that
        if hasattr(queryset.model, "shared_with"):
            return queryset.filter(shared_with=self.request.user)

        # For other objects, we'd need to check permissions individually
        # This is less efficient but more accurate
        allowed_ids = []
        for obj in queryset:
            try:
                permission = PermissionService.get_permission(obj, self.request.user)
                if permission >= required_permission:
                    # Get the primary key
                    pk = getattr(obj, "pk", None)
                    if pk:
                        allowed_ids.append(pk)
            except (AttributeError, TypeError):
                continue

        return queryset.filter(pk__in=allowed_ids)


class PermissionRequiredMixin:
    """Mixin to require specific permission level for view access."""

    required_permission = PermissionLevel.VIEWER
    permission_denied_message = "You do not have permission to access this object."

    def dispatch(self, request, *args, **kwargs):
        """Check permissions before processing the request."""
        # Get the object if this is a detail/edit/delete view
        if hasattr(self, "get_object"):
            try:
                obj = self.get_object()
                if request.user.is_authenticated:
                    permission = PermissionService.get_permission(obj, request.user)
                    if permission < self.required_permission:
                        from django.contrib import messages
                        from django.shortcuts import redirect

                        messages.error(request, self.permission_denied_message)
                        return redirect("gift_manager:index")
                else:
                    from django.contrib.auth.views import redirect_to_login

                    return redirect_to_login(request.get_full_path())
            except (AttributeError, TypeError):
                # Object doesn't support permissions - allow access
                pass

        return super().dispatch(request, *args, **kwargs)


class PermissionUpdateMixin:
    """Mixin to handle HTMX permission updates in edit views (Phase 1)."""

    def post(self, request, *args, **kwargs):
        """Handle both form submission and HTMX permission updates."""
        # Check if this is an HTMX permission update request
        is_perm_update = self.is_permission_update_request(request)
        logger.debug(
            f"[PermissionUpdateMixin] POST request - "
            f"is_htmx={bool(request.headers.get('HX-Request'))}, "
            f"has_user_id={'user_id' in request.POST}, "
            f"has_permission={'permission' in request.POST}, "
            f"is_perm_update={is_perm_update}"
        )

        if is_perm_update:
            logger.info("[PermissionUpdateMixin] Handling permission update request")
            return self.handle_permission_update(request)

        # Otherwise, handle as normal form submission
        logger.debug("[PermissionUpdateMixin] Handling as normal form submission")
        return super().post(request, *args, **kwargs)

    def is_permission_update_request(self, request):
        """Check if this is an HTMX or AJAX permission update request."""
        # Check for HTMX permission update
        is_htmx_perm_update = (
            request.headers.get("HX-Request")
            and "user_id" in request.POST
            and "permission" in request.POST
        )

        # Check for AJAX permission update (from FormInitializer)
        is_ajax_perm_update = (
            request.headers.get("X-Permission-Update")
            and "user_id" in request.POST
            and "permission_level" in request.POST
        )

        return is_htmx_perm_update or is_ajax_perm_update

    def handle_permission_update(self, request):
        """Handle HTMX or AJAX permission update for a friend."""
        from django.contrib.auth.models import User

        try:
            user_id = request.POST.get("user_id")
            # Support both 'permission' (HTMX) and 'permission_level' (AJAX)
            permission = request.POST.get("permission") or request.POST.get("permission_level")

            # Get the object being shared
            self.object = self.get_object()

            # Get the friend user
            friend = User.objects.get(id=user_id)

            # Update or remove permission
            if permission == "not_shared":
                PermissionService.assert_can_manage_permission(
                    request.user,
                    self.object,
                    friend,
                    None,
                )
                PermissionService.delete_permission(friend, self.object)
                logger.info(f"Removed permission for user {friend.username} on {self.object}")
            else:
                permission_level = int(permission)
                PermissionService.assert_can_manage_permission(
                    request.user,
                    self.object,
                    friend,
                    permission_level,
                )
                PermissionService.create_or_update_permission(
                    friend, self.object, permission_level=permission_level
                )
                logger.info(
                    f"Updated permission to {permission} for user {friend.username} on {self.object}"
                )

            return self._permission_update_success_response(request)

        except User.DoesNotExist:
            logger.error(f"User {user_id} not found")
            return self._permission_update_error_response(request, "User not found", 404)
        except Http404:
            raise
        except PermissionDenied:
            raise
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid permission update request: {e}")
            return self._permission_update_error_response(request, "Invalid permission value", 400)
        except Exception as e:
            logger.error(f"Error updating permission: {e}", exc_info=True)
            return self._permission_update_error_response(request, str(e), 500)

    def _permission_update_success_response(self, request) -> HttpResponse:
        """Return the successful response for a permission update request."""
        if request.headers.get("X-Permission-Update"):
            return JsonResponse({"status": "success", "message": "Permission updated"})

        response = HttpResponse(status=204)
        response["HX-Trigger"] = "permissionUpdated"
        return response

    def _permission_update_error_response(self, request, message: str, status: int) -> HttpResponse:
        """Return an error response matching the request style."""
        if request.headers.get("X-Permission-Update"):
            return JsonResponse({"status": "error", "message": message}, status=status)

        response = HttpResponse(message, status=status)
        response["HX-Trigger"] = "showNotification"
        return response
