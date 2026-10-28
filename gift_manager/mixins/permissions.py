"""Permission-related mixins for views."""

import json
import logging
from typing import Any

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.http import HttpResponse
from django.http import JsonResponse

from gift_manager.models import PermissionLevel
from gift_manager.plan_coordination import surprise_sharing_warning
from gift_manager.services import PermissionService
from gift_manager.sharing_service import SharingService

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

    def _build_permissions_from_dicts(  # noqa: PLR0911
        self, objects: list, id_fields: list
    ) -> dict[str, int]:
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

        if model.__name__ == "PersonGroup" and id_field == "group_id":
            for group in model.objects.filter(group_id__in=object_ids):
                permissions[str(group.group_id)] = PermissionService.get_effective_permission(
                    group, self.request.user
                )
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
                    permission = PermissionService.get_effective_permission(obj, self.request.user)
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
                permission = PermissionService.get_effective_permission(
                    self.object, self.request.user
                )
                context.update(
                    {
                        "user_permission": permission,
                        "can_edit": permission >= PermissionLevel.EDITOR,
                        "can_delete": permission >= PermissionLevel.OWNER,
                        "can_share": permission >= PermissionLevel.OWNER,
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

            # Update or remove permission, serialized with other changes on this object
            warning = ""
            with PermissionService.locked_for_permission_change(self.object):
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
                    SharingService.grant(request.user, self.object, friend, permission_level)
                    logger.info(
                        f"Updated permission to {permission} for user {friend.username} "
                        f"on {self.object}"
                    )
                    warning = surprise_sharing_warning(self.object, [friend])

            return self._permission_update_success_response(request, warning=warning)

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

    def _permission_update_success_response(self, request, warning: str = "") -> HttpResponse:
        """Return the successful response for a permission update request.

        ``warning`` tells the sharer that a surprise plan is hidden from the person they just
        shared it with; it is shown as a notification.
        """
        if request.headers.get("X-Permission-Update"):
            data = {"status": "success", "message": "Permission updated"}
            if warning:
                data["warning"] = warning
            return JsonResponse(data)

        response = HttpResponse(status=204)
        if warning:
            response["HX-Trigger"] = json.dumps(
                {
                    "permissionUpdated": "",
                    "showNotification": {"message": warning, "type": "warning"},
                }
            )
        else:
            response["HX-Trigger"] = "permissionUpdated"
        return response

    def _permission_update_error_response(self, request, message: str, status: int) -> HttpResponse:
        """Return an error response matching the request style."""
        if request.headers.get("X-Permission-Update"):
            return JsonResponse({"status": "error", "message": message}, status=status)

        response = HttpResponse(message, status=status)
        response["HX-Trigger"] = "showNotification"
        return response
