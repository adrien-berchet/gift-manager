"""Tests for the reusable offcanvas panel template."""

import pytest
from django.template import Context, Template
from django.test import RequestFactory
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
class TestOffcanvasTemplate:
    """Tests for the reusable offcanvas panel template functionality."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

    def test_offcanvas_base_template_renders(self):
        """Test that the offcanvas base template renders without errors."""
        template = Template(
            "{% load i18n %}"
            "{% include 'gift_manager/includes/offcanvas_base.html' %}"
        )

        request = self.factory.get('/')
        request.user = self.user

        context = Context({'request': request})
        rendered = template.render(context)

        # Check that essential elements are present
        assert 'id="editPanel"' in rendered
        assert 'id="detailPanel"' in rendered
        assert 'offcanvas-end' in rendered
        assert 'offcanvas-panel' in rendered

    def test_offcanvas_has_required_elements(self):
        """Test that the offcanvas template has all required elements for functionality."""
        template = Template(
            "{% load i18n %}"
            "{% include 'gift_manager/includes/offcanvas_base.html' %}"
        )

        request = self.factory.get('/')
        request.user = self.user

        context = Context({'request': request})
        rendered = template.render(context)

        # Check for edit panel elements
        assert 'id="editPanelLabel"' in rendered
        assert 'id="offcanvasContent"' in rendered
        assert 'id="offcanvasLoading"' in rendered
        assert 'id="offcanvasError"' in rendered

        # Check for detail panel elements
        assert 'id="detailPanelLabel"' in rendered
        assert 'id="detailContent"' in rendered
        assert 'id="detailLoading"' in rendered
        assert 'id="detailError"' in rendered

    def test_offcanvas_has_accessibility_features(self):
        """Test that the offcanvas template includes proper accessibility features."""
        template = Template(
            "{% load i18n %}"
            "{% include 'gift_manager/includes/offcanvas_base.html' %}"
        )

        request = self.factory.get('/')
        request.user = self.user

        context = Context({'request': request})
        rendered = template.render(context)

        # Check for accessibility attributes
        assert 'tabindex="-1"' in rendered
        assert 'aria-labelledby=' in rendered
        assert 'aria-label=' in rendered
        assert 'data-bs-keyboard="true"' in rendered

    def test_offcanvas_has_mobile_responsive_classes(self):
        """Test that the offcanvas template includes mobile responsive classes."""
        template = Template(
            "{% load i18n %}"
            "{% include 'gift_manager/includes/offcanvas_base.html' %}"
        )

        request = self.factory.get('/')
        request.user = self.user

        context = Context({'request': request})
        rendered = template.render(context)

        # Check for responsive classes
        assert 'offcanvas-panel' in rendered
        assert 'offcanvas-end' in rendered

    def test_offcanvas_has_loading_and_error_states(self):
        """Test that the offcanvas template includes loading and error state elements."""
        template = Template(
            "{% load i18n %}"
            "{% include 'gift_manager/includes/offcanvas_base.html' %}"
        )

        request = self.factory.get('/')
        request.user = self.user

        context = Context({'request': request})
        rendered = template.render(context)

        # Check for loading states
        assert 'loading-state' in rendered
        assert 'loading-spinner' in rendered

        # Check for error states
        assert 'error-state' in rendered
        assert 'alert-danger' in rendered

        # Check for retry functionality
        assert 'retryOffcanvasLoad' in rendered
        assert 'retryDetailLoad' in rendered

    def test_offcanvas_javascript_functions_defined(self):
        """Test that the offcanvas template defines required JavaScript functions."""
        template = Template(
            "{% load i18n %}"
            "{% include 'gift_manager/includes/offcanvas_base.html' %}"
        )

        request = self.factory.get('/')
        request.user = self.user

        context = Context({'request': request})
        rendered = template.render(context)

        # Check for JavaScript function definitions
        assert 'showOffcanvasLoading' in rendered
        assert 'hideOffcanvasLoading' in rendered
        assert 'showOffcanvasError' in rendered
        assert 'retryOffcanvasLoad' in rendered
        assert 'retryDetailLoad' in rendered

    def test_form_partial_template_renders(self):
        """Test that the form partial template renders correctly."""
        template = Template(
            "{% load i18n %}"
            "{% include 'gift_manager/includes/form_partial.html' with form_action_url='/test/' %}"
        )

        request = self.factory.get('/')
        request.user = self.user

        context = Context({
            'request': request,
            'form': {},  # Mock form object
            'form_action_url': '/test/'
        })
        rendered = template.render(context)

        # Check for form elements
        assert 'offcanvas-form' in rendered
        assert 'panel-form-actions' in rendered
        assert 'hx-post="/test/"' in rendered
        # Just check that the form structure is correct, CSRF token rendering depends on context

    def test_form_partial_has_htmx_integration(self):
        """Test that the form partial template includes proper HTMX integration."""
        template = Template(
            "{% load i18n %}"
            "{% include 'gift_manager/includes/form_partial.html' with form_action_url='/test/' %}"
        )

        request = self.factory.get('/')
        request.user = self.user

        context = Context({
            'request': request,
            'form': {},
            'form_action_url': '/test/'
        })
        rendered = template.render(context)

        # Check for HTMX attributes
        assert 'hx-post=' in rendered
        assert 'hx-target=' in rendered
        assert 'hx-swap=' in rendered
        assert 'hx-indicator=' in rendered
