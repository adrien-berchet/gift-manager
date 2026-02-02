"""Progressive enhancement mixins for Django views."""

import logging
from typing import Any, Dict

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers

logger = logging.getLogger(__name__)


class ProgressiveEnhancementMixin:
    """Mixin to handle progressive enhancement in views."""

    # Template names for different modes
    fallback_template_name = None
    no_js_template_name = None

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """Detect request type and set appropriate flags."""
        # Detect if JavaScript is disabled
        self.no_js = request.GET.get('no_js') == '1' or request.POST.get('no_js') == '1'

        # Detect if this is a fallback request
        self.is_fallback = self.no_js or not self.supports_enhanced_features(request)

        # Store original HTMX flag
        self.is_htmx = getattr(self, 'is_htmx', request.headers.get('HX-Request') == 'true')

        # Override HTMX flag if in fallback mode
        if self.is_fallback:
            self.is_htmx = False

        return super().dispatch(request, *args, **kwargs)

    def supports_enhanced_features(self, request: HttpRequest) -> bool:
        """Check if the request supports enhanced features."""
        # Check for modern browser capabilities
        user_agent = request.META.get('HTTP_USER_AGENT', '').lower()

        # Basic checks for very old browsers
        old_browsers = [
            'msie 6', 'msie 7', 'msie 8',  # Old IE versions
            'opera/9',  # Old Opera
            'firefox/3',  # Very old Firefox
        ]

        for old_browser in old_browsers:
            if old_browser in user_agent:
                return False

        # Check for JavaScript support indicators
        if 'javascript' in request.META.get('HTTP_ACCEPT', ''):
            return True

        # Default to supporting enhanced features
        return True

    def get_template_names(self) -> list:
        """Return appropriate template based on request type."""
        templates = []

        # Add no-JS template if available and needed
        if self.no_js and self.no_js_template_name:
            templates.append(self.no_js_template_name)

        # Add fallback template if available and needed
        if self.is_fallback and self.fallback_template_name:
            templates.append(self.fallback_template_name)

        # Add HTMX template if available and appropriate
        if self.is_htmx and hasattr(self, 'htmx_template_name') and self.htmx_template_name:
            templates.append(self.htmx_template_name)

        # Add default templates
        templates.extend(super().get_template_names())

        return templates

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        """Add progressive enhancement context."""
        con
r(self, 'object') and self.object:
            model_name = self.object._meta.model_name
            pk = getattr(self.object, self.object._meta.pk.name)

            try:
                fallback_urls.update({
                    'edit': reverse(f'gift_manager:{model_name}_edit', kwargs={'pk': pk}) + '?no_js=1',
                    'delete': reverse(f'gift_manager:{model_name}_delete', kwargs={'pk': pk}) + '?no_js=1',
                    'detail': reverse(f'gift_manager:{model_name}_detail', kwargs={'pk': pk}),
                })
            except Exception:
                # Fallback URL generation failed, continue without them
                pass

        return fallback_urls

    def form_valid(self, form) -> HttpResponse:
        """Handle form validation with progressive enhancement."""
        response = super().form_valid(form)

        # For non-AJAX requests, always redirect to avoid re-submission
        if not self.is_htmx or self.is_fallback:
            if hasattr(response, 'status_code') and response.status_code == 200:
                # Convert to redirect
                success_url = self.get_success_url()
                return redirect(success_url)

        return response

    def form_invalid(self, form) -> HttpResponse:
        """Handle form validation errors with progressive enhancement."""
        response = super().form_invalid(form)

        # For fallback mode, ensure errors are clearly displayed
        if self.is_fallback:
            context = self.get_context_data(form=form)
            context['form_errors'] = form.errors
            context['non_field_errors'] = form.non_field_errors()

            return self.render_to_response(context)

        return response


class NoJSRedirectMixin:
    """Mixin to handle redirects for non-JavaScript requests."""

    def get_success_url(self) -> str:
        """Get success URL, adding no_js parameter if needed."""
        success_url = super().get_success_url()

        if getattr(self, 'no_js', False):
            separator = '&' if '?' in success_url else '?'
            success_url += f'{separator}no_js=1'

        return success_url


class FallbackFormMixin:
    """Mixin to provide fallback form handling."""

    def get_form_kwargs(self) -> Dict[str, Any]:
        """Add fallback-specific form kwargs."""
        kwargs = super().get_form_kwargs()

        # Add fallback flag to form
        if getattr(self, 'is_fallback', False):
            kwargs['fallback_mode'] = True

        return kwargs

    def get_form_class(self):
        """Return appropriate form class for fallback mode."""
        form_class = super().get_form_class()

        # Use simplified form for fallback mode if available
        if getattr(self, 'is_fallback', False) and hasattr(self, 'fallback_form_class'):
            return self.fallback_form_class

        return form_class


class AccessibleErrorMixin:
    """Mixin to provide accessible error handling."""

    def form_invalid(self, form) -> HttpResponse:
        """Provide accessible error messages."""
        response = super().form_invalid(form)

        # Add structured error information for screen readers
        if isinstance(response, TemplateResponse):
            context = response.context_data
            context['accessible_errors'] = self.get_accessible_errors(form)

        return response

    def get_accessible_errors(self, form) -> Dict[str, Any]:
        """Get structured error information for accessibility."""
        accessible_errors = {
            'has_errors': form.errors or form.non_field_errors(),
            'error_count': len(form.errors) + len(form.non_field_errors()),
            'field_errors': {},
            'non_field_errors': list(form.non_field_errors()),
        }

        # Structure field errors with labels
        for field_name, errors in form.errors.items():
            field = form.fields.get(field_name)
            field_label = field.label if field else field_name.replace('_', ' ').title()

            accessible_errors['field_errors'][field_name] = {
                'label': field_label,
                'errors': list(errors),
                'error_id': f'{field_name}_errors',
            }

        return accessible_errors


class FallbackListMixin:
    """Mixin to provide fallback list functionality."""

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        """Add fallback list context."""
        context = super().get_context_data(**kwargs)

        if getattr(self, 'is_fallback', False):
            # Provide simple pagination for fallback mode
            context['simple_pagination'] = True

            # Add fallback table data
            context['fallback_table_data'] = self.get_fallback_table_data()

        return context

    def get_fallback_table_data(self) -> Dict[str, Any]:
        """Get data for fallback table rendering."""
        queryset = self.get_queryset()

        # Get column information
        columns = self.get_fallback_columns()

        # Prepare table data
        table_data = {
            'columns': columns,
            'rows': [],
        }

        for obj in queryset:
            row = {}
            for column in columns:
                field_name = column['field']
                if hasattr(obj, field_name):
                    value = getattr(obj, field_name)
                    row[field_name] = self.format_fallback_value(value, column)
                else:
                    row[field_name] = ''

            # Add action URLs
            row['actions'] = self.get_fallback_actions(obj)
            table_data['rows'].append(row)

        return table_data

    def get_fallback_columns(self) -> list:
        """Get column definitions for fallback table."""
        # Override in subclasses to define columns
        return [
            {'field': 'id', 'label': 'ID', 'type': 'text'},
            {'field': '__str__', 'label': 'Name', 'type': 'text'},
        ]

    def format_fallback_value(self, value: Any, column: Dict[str, Any]) -> str:
        """Format value for fallback table display."""
        if value is None:
            return ''

        column_type = column.get('type', 'text')

        if column_type == 'date' and hasattr(value, 'strftime'):
            return value.strftime('%Y-%m-%d')
        elif column_type == 'datetime' and hasattr(value, 'strftime'):
            return value.strftime('%Y-%m-%d %H:%M')
        elif column_type == 'boolean':
            return 'Yes' if value else 'No'
        else:
            return str(value)

    def get_fallback_actions(self, obj) -> list:
        """Get action links for fallback table."""
        actions = []
        model_name = obj._meta.model_name
        pk = getattr(obj, obj._meta.pk.name)

        try:
            actions.extend([
                {
                    'label': 'View',
                    'url': reverse(f'gift_manager:{model_name}_detail', kwargs={'pk': pk}),
                    'class': 'btn btn-sm btn-outline-primary',
                },
                {
                    'label': 'Edit',
                    'url': reverse(f'gift_manager:{model_name}_edit', kwargs={'pk': pk}) + '?no_js=1',
                    'class': 'btn btn-sm btn-outline-warning',
                },
                {
                    'label': 'Delete',
                    'url': reverse(f'gift_manager:{model_name}_delete', kwargs={'pk': pk}) + '?no_js=1',
                    'class': 'btn btn-sm btn-outline-danger',
                },
            ])
        except Exception:
            # URL generation failed, provide basic actions
            pass

        return actions


class ComprehensiveProgressiveEnhancementMixin(
    ProgressiveEnhancementMixin,
    NoJSRedirectMixin,
    FallbackFormMixin,
    AccessibleErrorMixin
):
    """Complete progressive enhancement mixin combining all features."""

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        """Add comprehensive progressive enhancement context."""
        context = super().get_context_data(**kwargs)

        # Add browser capability information
        context['browser_capabilities'] = self.get_browser_capabilities()

        # Add fallback instructions
        if self.is_fallback:
            context['fallback_instructions'] = self.get_fallback_instructions()

        return context

    def get_browser_capabilities(self) -> Dict[str, bool]:
        """Detect browser capabilities."""
        request = self.request
        user_agent = request.META.get('HTTP_USER_AGENT', '').lower()

        capabilities = {
            'javascript': not self.no_js,
            'css3': 'webkit' in user_agent or 'gecko' in user_agent or 'trident' in user_agent,
            'ajax': not self.is_fallback,
            'modern_browser': self.supports_enhanced_features(request),
        }

        return capabilities

    def get_fallback_instructions(self) -> Dict[str, str]:
        """Get instructions for fallback mode."""
        return {
            'title': 'Simplified Mode Active',
            'message': 'The application is running in compatibility mode. All features are available but may require page refreshes.',
            'help_text': 'Enable JavaScript in your browser for the best experience.',
        }


@method_decorator(vary_on_headers('User-Agent'), name='dispatch')
class ProgressiveEnhancementListMixin(ComprehensiveProgressiveEnhancementMixin, FallbackListMixin):
    """Complete progressive enhancement mixin for list views."""
    pass


@method_decorator(vary_on_headers('User-Agent'), name='dispatch')
class ProgressiveEnhancementFormMixin(ComprehensiveProgressiveEnhancementMixin):
    """Complete progressive enhancement mixin for form views."""
    pass
