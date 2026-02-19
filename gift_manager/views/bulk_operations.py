"""Views for handling bulk operations on entities."""

import json
import logging
from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpRequest
from django.http import HttpResponse
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views import View
from django.views.generic import TemplateView

from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import GiftTag
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import Relation
from gift_manager.permissions import PermissionService
from gift_manager.services import PermissionLevel

logger = logging.getLogger(__name__)


class BulkOperationView(LoginRequiredMixin, View):
    """Handle bulk operations on multiple entities."""

    # Map entity types to their models
    ENTITY_MODELS = {
        "person": Person,
        "gift": Gift,
        "event": Event,
        "relation": Relation,
        "persongroup": PersonGroup,
        "gifttag": GiftTag,
    }

    # Map entity types to their UUID lookup field (not the auto-generated PK)
    ENTITY_UUID_FIELDS = {
        "person": "person_id",
        "gift": "gift_id",
        "event": "event_id",
        "relation": "relation_id",
        "persongroup": "group_id",
        "gifttag": "tag_id",
    }

    def post(self, request: HttpRequest) -> HttpResponse:
        """Handle bulk operation requests."""
        try:
            # Parse request data
            if request.content_type == "application/json":
                data = json.loads(request.body)
            else:
                data = request.POST

            action = data.get("action")
            entity_type = data.get("entity_type")
            entity_ids = data.get("entity_ids", [])

            # Validate input
            if not action or not entity_type or not entity_ids:
                return JsonResponse(
                    {"success": False, "error": _("Missing required parameters")}, status=400
                )

            if entity_type not in self.ENTITY_MODELS:
                return JsonResponse(
                    {"success": False, "error": _("Invalid entity type")}, status=400
                )

            # Convert single ID to list
            if isinstance(entity_ids, str):
                entity_ids = [entity_ids]

            # Handle different bulk actions
            if action == "bulk_delete":
                return self.handle_bulk_delete(request, entity_type, entity_ids)
            if action == "bulk_share":
                return self.handle_bulk_share(request, entity_type, entity_ids)
            return JsonResponse(
                {"success": False, "error": _("Unknown action: {}").format(action)}, status=400
            )

        except json.JSONDecodeError:
            return JsonResponse({"success": False, "error": _("Invalid JSON data")}, status=400)
        except Exception as e:
            logger.exception("Error in bulk operation: %s", e)
            return JsonResponse(
                {"success": False, "error": _("An error occurred while processing the request")},
                status=500,
            )

    def handle_bulk_delete(
        self, request: HttpRequest, entity_type: str, entity_ids: list[str]
    ) -> HttpResponse:
        """Handle bulk delete operation."""
        model = self.ENTITY_MODELS[entity_type]
        results = {
            "success": True,
            "deleted": [],
            "failed": [],
            "shared_removed": [],
            "permission_denied": [],
        }

        try:
            with transaction.atomic():
                for entity_id in entity_ids:
                    try:
                        # Get the object with permission check (use UUID field, not auto PK)
                        uuid_field = self.ENTITY_UUID_FIELDS.get(entity_type, model._meta.pk.name)
                        obj = get_object_or_404(
                            model.objects.accessible_by(request.user),
                            **{uuid_field: entity_id},
                        )

                        # Check if user has at least EDITOR permission
                        # Creator (user_link) is treated as OWNER
                        is_creator = hasattr(obj, "user_link") and obj.user_link == request.user
                        permission_level = PermissionService.get_permission(obj, request.user)
                        if not is_creator and permission_level < PermissionLevel.EDITOR:
                            results["permission_denied"].append(str(entity_id))
                            continue

                        # Check if object is shared with other users
                        other_users = obj.shared_with.exclude(id=request.user.id)

                        if other_users.exists():
                            # Remove sharing with current user only
                            obj.shared_with.remove(request.user)
                            PermissionService.delete_permission(request.user, obj)
                            results["shared_removed"].append(str(entity_id))
                        else:
                            # Delete the object completely
                            obj.delete()
                            results["deleted"].append(str(entity_id))

                    except Exception as e:
                        logger.warning("Failed to delete %s %s: %s", entity_type, entity_id, e)
                        results["failed"].append({"id": str(entity_id), "error": str(e)})

                # Generate success message
                deleted_count = len(results["deleted"])
                shared_removed_count = len(results["shared_removed"])
                failed_count = len(results["failed"])
                permission_denied_count = len(results["permission_denied"])

                if deleted_count > 0 or shared_removed_count > 0:
                    message_parts = []
                    if deleted_count > 0:
                        message_parts.append(_("{} items deleted").format(deleted_count))
                    if shared_removed_count > 0:
                        message_parts.append(_("{} items unshared").format(shared_removed_count))

                    success_message = ", ".join(message_parts)
                    if failed_count > 0:
                        success_message += _(", {} items failed").format(failed_count)
                    if permission_denied_count > 0:
                        success_message += _(
                            ", {} items skipped (insufficient permissions)"
                        ).format(permission_denied_count)

                    results["message"] = success_message
                else:
                    results["success"] = False
                    if permission_denied_count > 0:
                        results["error"] = _("Insufficient permissions to delete {} items").format(
                            permission_denied_count
                        )
                    else:
                        results["error"] = _("No items could be processed")

        except Exception as e:
            logger.exception("Error in bulk delete: %s", e)
            results["success"] = False
            results["error"] = _("An error occurred during bulk delete")

        return JsonResponse(results)

    def handle_bulk_share(
        self, request: HttpRequest, entity_type: str, entity_ids: list[str]
    ) -> HttpResponse:
        """Handle bulk share operation."""
        # For now, return the share URL with selected IDs
        # This will be handled by the frontend to redirect to the share page
        share_url = f"/share/?entity_type={entity_type}&ids={','.join(entity_ids)}"

        return JsonResponse(
            {
                "success": True,
                "redirect_url": share_url,
                "message": _("Redirecting to share page..."),
            }
        )


class BulkDeleteConfirmationView(LoginRequiredMixin, TemplateView):
    """View for bulk delete confirmation modal."""

    template_name = "gift_manager/includes/bulk_delete_confirmation_modal.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Add bulk delete confirmation context."""
        context = super().get_context_data(**kwargs)

        entity_type = self.request.GET.get("entity_type", "")
        entity_ids = self.request.GET.get("entity_ids", "").split(",")
        entity_ids = [id.strip() for id in entity_ids if id.strip()]

        # Get entity model and objects
        model = BulkOperationView.ENTITY_MODELS.get(entity_type)
        entities = []

        if model and entity_ids:
            try:
                # Filter by user permissions (use UUID field, not auto PK)
                uuid_field = BulkOperationView.ENTITY_UUID_FIELDS.get(
                    entity_type, model._meta.pk.name
                )
                queryset = model.objects.accessible_by(self.request.user)
                entities = list(queryset.filter(**{f"{uuid_field}__in": entity_ids}))
            except Exception as e:
                logger.warning("Error fetching entities for bulk delete confirmation: %s", e)

        count = len(entities)
        warning_message = ""

        if entity_type == "gift":
            warning_message = ngettext(
                "You are about to delete one gift.",
                "You are about to delete %(count)s gifts.",
                count,
            ) % {"count": count}
        elif entity_type == "person":
            warning_message = ngettext(
                "You are about to delete one person.",
                "You are about to delete %(count)s people.",
                count,
            ) % {"count": count}
        elif entity_type == "event":
            warning_message = ngettext(
                "You are about to delete one event.",
                "You are about to delete %(count)s events.",
                count,
            ) % {"count": count}
        elif entity_type == "relation":
            warning_message = ngettext(
                "You are about to delete one gifting.",
                "You are about to delete %(count)s giftings.",
                count,
            ) % {"count": count}
        elif entity_type == "persongroup":
            warning_message = ngettext(
                "You are about to delete one person group.",
                "You are about to delete %(count)s person groups.",
                count,
            ) % {"count": count}
        elif entity_type == "gifttag":
            warning_message = ngettext(
                "You are about to delete one gift tag.",
                "You are about to delete %(count)s gift tags.",
                count,
            ) % {"count": count}
        else:
            # Fallback for any other type - although all should be covered
            warning_message = ngettext(
                "You are about to delete %(count)s item.",
                "You are about to delete %(count)s items.",
                count,
            ) % {"count": count}

        context.update(
            {
                "entity_type": entity_type,
                "entity_ids": entity_ids,
                "entities": entities,
                "entity_count": count,
                "selected_count": len(entity_ids),
                "warning_message": warning_message,
            }
        )

        return context


class BulkOperationProgressView(LoginRequiredMixin, View):
    """Handle bulk operation progress tracking."""

    def get(self, request: HttpRequest) -> HttpResponse:
        """Get progress of a bulk operation."""
        operation_id = request.GET.get("operation_id")

        if not operation_id:
            return JsonResponse({"success": False, "error": _("Operation ID required")}, status=400)

        # For now, return a simple progress response
        # In a real implementation, you might use Redis or database to track progress
        return JsonResponse(
            {
                "success": True,
                "progress": {"completed": 0, "total": 0, "percentage": 0, "status": "pending"},
            }
        )
