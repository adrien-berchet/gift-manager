"""Inline editing views for AJAX field updates."""

import json
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.core.exceptions import ValidationError
from django.db import transaction

from gift_manager.models import Person, Gift, Event, PersonGroup, GiftTag, Relation, PermissionLevel
from gift_manager.services import PermissionService
from gift_manager.views.base import GetObjectByTokenMixin


class InlineFieldUpdateView(LoginRequiredMixin, GetObjectByTokenMixin, View):
    """Base view for inline field updates via AJAX."""

    model = None
    allowed_fields = []
    pk_name = None  # Must be set in subclasses

    def get_queryset(self):
        """Return the queryset for the model."""
        return self.model.objects.all()

    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        """Handle inline field update."""
        try:
            # Parse JSON data
            data = json.loads(request.body)
            field_name = data.get('field')
            field_value = data.get('value')
            entity_id = kwargs.get('pk')

            # Validate field is allowed
            if field_name not in self.allowed_fields:
                return JsonResponse({
                    'success': False,
                    'error': f'Field "{field_name}" is not editable inline.'
                }, status=400)

            # Get the object first to check permissions
            obj = self.get_object()

            # Check permissions - user needs at least EDITOR level
            user_permission = PermissionService.get_permission(obj, request.user)
            if user_permission < PermissionLevel.EDITOR:
                return JsonResponse({
                    'success': False,
                    'error': 'You do not have permission to edit this item.'
                }, status=403)

            # Now validate field value (remove null characters and other problematic characters)
            if field_value is not None:
                # Remove null characters and other control characters that can cause database issues
                field_value = ''.join(char for char in str(field_value) if ord(char) >= 32 or char in '\t\n\r')
                field_value = field_value.strip()

            # Check for empty value after cleaning
            if not field_value:
                return JsonResponse({
                    'success': False,
                    'error': 'Field value cannot be empty or contain only invalid characters.'
                }, status=400)

            # Special validation for email fields
            if field_name == 'email_address' and field_value:
                from django.core.validators import validate_email
                from django.core.exceptions import ValidationError as DjangoValidationError
                try:
                    validate_email(field_value)
                except DjangoValidationError:
                    return JsonResponse({
                        'success': False,
                        'error': 'Please enter a valid email address.'
                    }, status=400)

            # Update the field
            with transaction.atomic():
                old_value = getattr(obj, field_name)
                setattr(obj, field_name, field_value)

                try:
                    obj.full_clean()
                    obj.save(update_fields=[field_name])
                except ValidationError as e:
                    # Handle both field-specific and general validation errors
                    if hasattr(e, 'message_dict') and field_name in e.message_dict:
                        error_message = e.message_dict[field_name][0]
                    elif hasattr(e, 'message_dict') and '__all__' in e.message_dict:
                        error_message = e.message_dict['__all__'][0]
                    elif hasattr(e, 'messages') and e.messages:
                        error_message = e.messages[0]
                    else:
                        error_message = 'Invalid value'

                    return JsonResponse({
                        'success': False,
                        'error': str(error_message)
                    }, status=400)

            return JsonResponse({
                'success': True,
                'old_value': old_value,
                'new_value': field_value,
                'message': f'{field_name.replace("_", " ").title()} updated successfully.'
            })

        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data.'
            }, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': 'An error occurred while updating the field.'
            }, status=500)


class PersonInlineUpdateView(InlineFieldUpdateView):
    """Inline editing for Person fields."""
    model = Person
    allowed_fields = ['first_name', 'family_name', 'email_address']
    pk_name = 'person_id'


class GiftInlineUpdateView(InlineFieldUpdateView):
    """Inline editing for Gift fields."""
    model = Gift
    allowed_fields = ['name', 'comment']
    pk_name = 'gift_id'


class EventInlineUpdateView(InlineFieldUpdateView):
    """Inline editing for Event fields."""
    model = Event
    allowed_fields = ['name', 'comment']
    pk_name = 'event_id'


class PersonGroupInlineUpdateView(InlineFieldUpdateView):
    """Inline editing for PersonGroup fields."""
    model = PersonGroup
    allowed_fields = ['name', 'comment']
    pk_name = 'group_id'


class GiftTagInlineUpdateView(InlineFieldUpdateView):
    """Inline editing for GiftTag fields."""
    model = GiftTag
    allowed_fields = ['name']
    pk_name = 'tag_id'


class RelationInlineUpdateView(InlineFieldUpdateView):
    """Inline editing for Relation fields."""
    model = Relation
    allowed_fields = ['comment']
    pk_name = 'relation_id'
