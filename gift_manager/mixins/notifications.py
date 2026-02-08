"""Notification mixins for Django views
Provides server-side integration with client-side notification system
Requirements: 8.4, 4.4
"""

import json

from django.contrib import messages
from django.http import HttpResponse
from django.http import JsonResponse
from django.utils.translation import gettext as _


class NotificationMixin:
    """Mixin to add notification support to Django views.
    Integrates with the client-side notification system.
    """

    def add_success_notification(self, message, title=None):
        """Add a success notification."""
        return self._add_notification(message, "success", title)

    def add_error_notification(self, message, title=None):
        """Add an error notification."""
        return self._add_notification(message, "danger", title)

    def add_warning_notification(self, message, title=None):
        """Add a warning notification."""
        return self._add_notification(message, "warning", title)

    def add_info_notification(self, message, title=None):
        """Add an info notification."""
        return self._add_notification(message, "info", title)

    def _add_notification(self, message, type, title=None):
        """Internal method to add notification."""
        if hasattr(self, "request") and self.request:
            # For HTMX requests, add to response headers
            if self.request.headers.get("HX-Request"):
                return {"type": type, "message": message, "title": title}
            # For regular requests, use Django messages
            getattr(messages, type)(self.request, message)
        return None


class HTMXNotificationMixin(NotificationMixin):
    """Enhanced mixin for HTMX requests with notification support."""

    def get_success_response(self, message=None, title=None, trigger_events=None, **kwargs):
        """Create a success response with notification for HTMX requests."""
        response_data = {}

        if message:
            response_data["notification"] = {"type": "success", "message": message, "title": title}

        # Add any additional data
        response_data.update(kwargs)

        # Create response
        if self.request.headers.get("HX-Request"):
            response = HttpResponse(status=200)

            # Add notification headers
            if message:
                response["X-Success-Message"] = message
                if title:
                    response["X-Success-Title"] = title

            # Add trigger events
            triggers = []
            if trigger_events:
                if isinstance(trigger_events, str):
                    triggers.append(trigger_events)
                else:
                    triggers.extend(trigger_events)

            # Always trigger list update for CRUD operations
            if hasattr(self, "model") and self.model:
                triggers.append("list:update")

            if triggers:
                response["HX-Trigger"] = json.dumps(dict.fromkeys(triggers, True))

            return response
        # For non-HTMX requests, add message and redirect
        if message:
            messages.success(self.request, message)
        return super().get_success_url() if hasattr(super(), "get_success_url") else "/"

    def get_error_response(self, message, title=None, status=400, **kwargs):
        """Create an error response with notification for HTMX requests."""
        response_data = {"error": message}
        response_data.update(kwargs)

        if self.request.headers.get("HX-Request"):
            response = HttpResponse(status=status)
            response["X-Error-Message"] = message
            response["X-Error-Type"] = "error"
            if title:
                response["X-Error-Title"] = title
            return response
        messages.error(self.request, message)
        return JsonResponse(response_data, status=status)


class CRUDNotificationMixin(HTMXNotificationMixin):
    """Mixin for CRUD operations with automatic notifications."""

    def form_valid(self, form):
        """Override form_valid to add success notification."""
        response = super().form_valid(form)

        # Generate success message based on the action
        if hasattr(self, "success_message") and self.success_message:
            message = self.success_message
        else:
            # Auto-generate message based on view type
            action = self._get_action_name()
            model_name = self._get_model_name()
            message = self._get_default_success_message(action, model_name)

        if self.request.headers.get("HX-Request"):
            return self.get_success_response(message)
        messages.success(self.request, message)
        return response

    def form_invalid(self, form):
        """Override form_invalid to add error notification."""
        response = super().form_invalid(form)

        # Generate error message
        error_count = sum(len(errors) for errors in form.errors.values())
        if error_count == 1:
            # Single error - show specific message
            field_name, field_errors = next(iter(form.errors.items()))
            message = f"{field_name}: {field_errors[0]}"
        else:
            # Multiple errors - show count
            message = _("Please correct {count} error{s} in the form.").format(
                count=error_count, s="s" if error_count > 1 else ""
            )

        if self.request.headers.get("HX-Request"):
            response["X-Error-Message"] = message
            response["X-Error-Type"] = "validation"
        else:
            messages.error(self.request, message)

        return response

    def delete(self, request, *args, **kwargs):
        """Override delete to add success notification."""
        obj = self.get_object()
        model_name = self._get_model_name()
        obj_name = str(obj)

        response = super().delete(request, *args, **kwargs)

        message = _("{model} '{name}' has been deleted successfully.").format(
            model=model_name, name=obj_name
        )

        if request.headers.get("HX-Request"):
            return self.get_success_response(message, trigger_events=["list:update", "modal:close"])
        messages.success(request, message)
        return response

    def _get_action_name(self):
        """Get the action name based on the view class."""
        class_name = self.__class__.__name__.lower()
        if "create" in class_name:
            return "created"
        if "update" in class_name or "edit" in class_name:
            return "updated"
        if "delete" in class_name:
            return "deleted"
        return "saved"

    def _get_model_name(self):
        """Get the model name for messages."""
        if hasattr(self, "model") and self.model:
            return self.model._meta.verbose_name.title()
        return "Item"

    def _get_default_success_message(self, action, model_name):
        """Generate default success message."""
        messages = {
            "created": _("{model} has been created successfully."),
            "updated": _("{model} has been updated successfully."),
            "deleted": _("{model} has been deleted successfully."),
            "saved": _("{model} has been saved successfully."),
        }

        template = messages.get(action, messages["saved"])
        return template.format(model=model_name)


class BulkOperationNotificationMixin:
    """Mixin for bulk operations with progress notifications."""

    def perform_bulk_operation(self, queryset, operation, progress_callback=None):
        """Perform bulk operation with progress tracking.

        Args:
            queryset: QuerySet to operate on
            operation: Function to call for each object
            progress_callback: Optional callback for progress updates
        """
        total = queryset.count()
        processed = 0
        errors = []

        for obj in queryset:
            try:
                operation(obj)
                processed += 1

                if progress_callback:
                    progress = int((processed / total) * 100)
                    progress_callback(progress, f"Processed {processed} of {total} items")

            except Exception as e:
                errors.append(f"{obj}: {e!s}")

        return {
            "total": total,
            "processed": processed,
            "errors": errors,
            "success": len(errors) == 0,
        }

    def get_bulk_success_message(self, result, operation_name):
        """Generate success message for bulk operations."""
        if result["success"]:
            return _("{count} items {operation} successfully.").format(
                count=result["processed"], operation=operation_name
            )
        return _(
            "{processed} of {total} items {operation} successfully. {errors} errors occurred."
        ).format(
            processed=result["processed"],
            total=result["total"],
            operation=operation_name,
            errors=len(result["errors"]),
        )


class ValidationNotificationMixin:
    """Mixin to handle validation errors with detailed notifications."""

    def add_form_error_notification(self, form):
        """Add notification for form validation errors."""
        errors = []

        # Collect all form errors
        for field, field_errors in form.errors.items():
            if field == "__all__":
                errors.extend(field_errors)
            else:
                field_label = form.fields[field].label or field.replace("_", " ").title()
                for error in field_errors:
                    errors.append(f"{field_label}: {error}")

        if errors:
            if len(errors) == 1:
                message = errors[0]
            else:
                message = _("Please correct the following errors:\n• ") + "\n• ".join(errors)

            return self.add_error_notification(message, _("Validation Error"))

        return None

    def add_field_error_notification(self, field_name, error_message):
        """Add notification for specific field error."""
        message = f"{field_name.replace('_', ' ').title()}: {error_message}"
        return self.add_error_notification(message, _("Validation Error"))


# Convenience function for standalone use
def add_htmx_notification(response, message, notification_type="success", title=None):
    """Add notification headers to an HTMX response.

    Args:
        response: HttpResponse object
        message: Notification message
        notification_type: Type of notification (success, error, warning, info)
        title: Optional notification title
    """
    if notification_type == "success":
        response["X-Success-Message"] = message
        if title:
            response["X-Success-Title"] = title
    else:
        response["X-Error-Message"] = message
        response["X-Error-Type"] = notification_type
        if title:
            response["X-Error-Title"] = title

    return response
