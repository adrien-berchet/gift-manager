"""Inline editing views for AJAX field updates."""

import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404
from django.http import JsonResponse
from django.views import View

from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import GiftTag
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import Relation
from gift_manager.services import PermissionService
from gift_manager.views.base import GetObjectByTokenMixin


class InlineFieldUpdateView(LoginRequiredMixin, GetObjectByTokenMixin, View):
    """Base view for inline field updates via AJAX."""

    model = None
    allowed_fields = []
    pk_name = None  # Must be set in subclasses

    def get_queryset(self):
        """Return the queryset for the model."""
        if hasattr(self.model.objects, "accessible_by"):
            return self.model.objects.accessible_by(self.request.user)
        msg = f"{self.model.__name__} does not expose accessible_by() for inline editing."
        raise AttributeError(msg)

    def post(self, request, *args, **kwargs):
        """Handle inline field update."""
        if request.content_type != "application/json":
            return JsonResponse(
                {"success": False, "error": "Inline updates require JSON data."},
                status=415,
            )

        try:
            # Parse JSON data
            data = json.loads(request.body)
            field_name = data.get("field")
            field_value = data.get("value")

            # Get the object first to avoid leaking field-schema details for private UUIDs
            obj = self.get_object()

            # Check permissions - user needs at least EDITOR level
            user_permission = PermissionService.get_effective_permission(obj, request.user)
            if user_permission < PermissionLevel.EDITOR:
                return JsonResponse(
                    {"success": False, "error": "You do not have permission to edit this item."},
                    status=403,
                )

            # Validate field is allowed
            if field_name not in self.allowed_fields:
                return JsonResponse(
                    {"success": False, "error": f'Field "{field_name}" is not editable inline.'},
                    status=400,
                )

            # Now validate field value (remove null characters and other problematic characters)
            if field_value is not None:
                # Remove null characters and other control characters that can cause database issues
                field_value = "".join(
                    char for char in str(field_value) if ord(char) >= 32 or char in "\t\n\r"
                )
                field_value = field_value.strip()

            # Check for empty value after cleaning
            if not field_value:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Field value cannot be empty or contain only invalid characters.",
                    },
                    status=400,
                )

            # Special validation for email fields
            if field_name == "email_address" and field_value:
                from django.core.exceptions import ValidationError as DjangoValidationError
                from django.core.validators import validate_email

                try:
                    validate_email(field_value)
                except DjangoValidationError:
                    return JsonResponse(
                        {"success": False, "error": "Please enter a valid email address."},
                        status=400,
                    )

            # Update the field
            with transaction.atomic():
                old_value = getattr(obj, field_name)
                setattr(obj, field_name, field_value)

                try:
                    obj.full_clean()
                    obj.save(update_fields=[field_name])
                except ValidationError as e:
                    # Handle both field-specific and general validation errors
                    if hasattr(e, "message_dict") and field_name in e.message_dict:
                        error_message = e.message_dict[field_name][0]
                    elif hasattr(e, "message_dict") and "__all__" in e.message_dict:
                        error_message = e.message_dict["__all__"][0]
                    elif hasattr(e, "messages") and e.messages:
                        error_message = e.messages[0]
                    else:
                        error_message = "Invalid value"

                    return JsonResponse({"success": False, "error": str(error_message)}, status=400)

            return JsonResponse(
                {
                    "success": True,
                    "old_value": old_value,
                    "new_value": field_value,
                    "message": f"{field_name.replace('_', ' ').title()} updated successfully.",
                }
            )

        except json.JSONDecodeError:
            return JsonResponse({"success": False, "error": "Invalid JSON data."}, status=400)
        except Http404:
            return JsonResponse({"success": False, "error": "Item not found."}, status=404)
        except Exception:
            return JsonResponse(
                {"success": False, "error": "An error occurred while updating the field."},
                status=500,
            )


class PersonInlineUpdateView(InlineFieldUpdateView):
    """Inline editing for Person fields."""

    model = Person
    allowed_fields = ["first_name", "family_name", "email_address"]
    pk_name = "person_id"


class GiftInlineUpdateView(InlineFieldUpdateView):
    """Inline editing for Gift fields."""

    model = Gift
    allowed_fields = ["name", "comment"]
    pk_name = "gift_id"


class EventInlineUpdateView(InlineFieldUpdateView):
    """Inline editing for Event fields."""

    model = Event
    allowed_fields = ["name", "comment"]
    pk_name = "event_id"


class PersonGroupInlineUpdateView(InlineFieldUpdateView):
    """Inline editing for PersonGroup fields."""

    model = PersonGroup
    allowed_fields = ["name", "comment"]
    pk_name = "group_id"


class GiftTagInlineUpdateView(InlineFieldUpdateView):
    """Inline editing for GiftTag fields."""

    model = GiftTag
    allowed_fields = ["name"]
    pk_name = "tag_id"


class RelationInlineUpdateView(InlineFieldUpdateView):
    """Inline editing for Relation fields."""

    model = Relation
    allowed_fields = ["comment"]
    pk_name = "relation_id"
