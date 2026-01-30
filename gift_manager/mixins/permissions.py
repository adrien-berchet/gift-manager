"""Permission-related mixins for views."""

import json
from typing import Dict, Any

from django.contrib.auth.models import User

from gift_manager.models import PermissionLevel
from gift_manager.services import PermissionService


class PermissionContextMixin:
    """Mixin to add permission context data to views."""

    def get_permission_context(self, objects=None) -> Dict[str, Any]:
        """Get permission context for the current user and objects.

        Args:
            objects: List of objects to check permissions for.
                    If None, uses self.get_queryset() or self.object_list

        Returns:
            Dict containing permission data for templates
        """
        if not self.request.user.is_authenticated:
            return {
                'user_permissions': {},
                'user_permissions_json': '{}',
                'permission_levels': PermissionLevel.CHOICES
            }

        # Get objects to check permissions for
        if objects is None:
            if hasattr(self, 'object_list') and self.object_list is not None:
                objects = self.object_list
            elif hasattr(self, 'get_queryset'):
                try:
                    objects = self.get_queryset()
                except Exception:
                    objects = []
            else:
                objects = []

        # Build permission mapping
        permissions = {}
        for obj in objects:
            try:
                # Get the primary key for the object
                pk = getattr(obj, 'pk', None)
                if pk is None:
                    # Try common ID field names
                    for id_field in ['id', 'person_id', 'gift_id', 'event_id', 'relation_id', 'group_id', 'tag_id']:
                        if hasattr(obj, id_field):
                            pk = getattr(obj, id_field)
                            break

                if pk:
                    permission = PermissionService.get_permission(obj, self.request.user)
                    permissions[str(pk)] = permission
            except (AttributeError, TypeError):
                # Skip objects that don't support permissions
                continue

        return {
            'user_permissions': permissions,
            'user_permissions_json': json.dumps(permissions),
            'permission_levels': PermissionLevel.CHOICES
        }

    def get_context_data(self, **kwargs) -> Dict[str, Any]:
        """Add permission context to the template context."""
        context = super().get_context_data(**kwargs)
        context.update(self.get_permission_context())
        return context


class SingleObjectPermissionMixin:
    """Mixin to add permission context for a single object."""

    def get_context_data(self, **kwargs) -> Dict[str, Any]:
        """Add permission context for the current object."""
        context = super().get_context_data(**kwargs)

        if hasattr(self, 'object') and self.object and self.request.user.is_authenticated:
            try:
                permission = PermissionService.get_permission(self.object, self.request.user)
                context.update({
                    'user_permission': permission,
                    'can_edit': permission >= PermissionLevel.EDITOR,
                    'can_delete': permission >= PermissionLevel.OWNER,
                    'can_share': permission >= PermissionLevel.EDITOR,
                    'can_view': permission > PermissionLevel.NONE,
                    'permission_level_name': PermissionLevel.get_label(permission)
                })
            except (AttributeError, TypeError):
                # Object doesn't support permissions
                context.update({
                    'user_permission': PermissionLevel.NONE,
                    'can_edit': False,
                    'can_delete': False,
                    'can_share': False,
                    'can_view': False,
                    'permission_level_name': 'None'
                })

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
        if hasattr(queryset.model, 'shared_with'):
            return queryset.filter(shared_with=self.request.user)

        # For other objects, we'd need to check permissions individually
        # This is less efficient but more accurate
        allowed_ids = []
        for obj in queryset:
            try:
                permission = PermissionService.get_permission(obj, self.request.user)
                if permission >= required_permission:
                    # Get the primary key
                    pk = getattr(obj, 'pk', None)
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
        if hasattr(self, 'get_object'):
            try:
                obj = self.get_object()
                if request.user.is_authenticated:
                    permission = PermissionService.get_permission(obj, request.user)
                    if permission < self.required_permission:
                        from django.contrib import messages
                        from django.shortcuts import redirect
                        messages.error(request, self.permission_denied_message)
                        return redirect('gift_manager:index')
                else:
                    from django.contrib.auth.views import redirect_to_login
                    return redirect_to_login(request.get_full_path())
            except (AttributeError, TypeError):
                # Object doesn't support permissions - allow access
                pass

        return super().dispatch(request, *args, **kwargs)
