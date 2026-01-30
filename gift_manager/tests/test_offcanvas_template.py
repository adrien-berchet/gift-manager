"""Tests for the reusable offcanvas panel template."""

import pytest
from django.contrib.auth import get_user_model
from django.template import Context
from django.template import Template
from django.test import RequestFactory

from .utils import text_in_rendered

User = get_user_model()


@pytest.mark.django_db
class TestOffcanvasTemplate:
    """Tests for the reusable offcanvas panel template functionality."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_offcanvas_base_template_renders(self):
        """Test that the offcanvas base template renders without errors."""
        template = Template(
            "{% load i18n %}{% include 'gift_manager/includes/offcanvas_base.html' %}"
        )

        request = self.factory.get("/")
        request.user = self.user

        context = Context({"request": request})
        rendered = template.render(context)

        # Check that essential elements are present
        assert text_in_rendered('id="editPanel"', rendered)
        assert text_in_rendered('id="detailPanel"', rendered)
        assert text_in_rendered("offcanvas-end", rendered)
        assert text_in_rendered("offcanvas-panel", rendered)

    def test_offcanvas_has_required_elements(self):
        """Test that the offcanvas template has all required elements for functionality."""
        template = Template(
            "{% load i18n %}{% include 'gift_manager/includes/offcanvas_base.html' %}"
        )

        request = self.factory.get("/")
        request.user = self.user

        context = Context({"request": request})
        rendered = template.render(context)

        # Check for edit panel elements
        assert text_in_rendered('id="editPanelLabel"', rendered)
        assert text_in_rendered('id="offcanvasContent"', rendered)
        assert text_in_rendered('id="offcanvasLoading"', rendered)
        assert text_in_rendered('id="offcanvasError"', rendered)

        # Check for detail panel elements
        assert text_in_rendered('id="detailPanelLabel"', rendered)
        assert text_in_rendered('id="detailContent"', rendered)
        assert text_in_rendered('id="detailLoading"', rendered)
        assert text_in_rendered('id="detailError"', rendered)

    def test_offcanvas_has_accessibility_features(self):
        """Test that the offcanvas template includes proper accessibility features."""
        template = Template(
            "{% load i18n %}{% include 'gift_manager/includes/offcanvas_base.html' %}"
        )

        request = self.factory.get("/")
        request.user = self.user

        context = Context({"request": request})
        rendered = template.render(context)

        # Check for accessibility attributes
        assert text_in_rendered('tabindex="-1"', rendered)
        assert text_in_rendered("aria-labelledby=", rendered)
        assert text_in_rendered("aria-label=", rendered)
        assert text_in_rendered('data-bs-keyboard="true"', rendered)

    def test_offcanvas_has_mobile_responsive_classes(self):
        """Test that the offcanvas template includes mobile responsive classes."""
        template = Template(
            "{% load i18n %}{% include 'gift_manager/includes/offcanvas_base.html' %}"
        )

        request = self.factory.get("/")
        request.user = self.user

        context = Context({"request": request})
        rendered = template.render(context)

        # Check for responsive classes
        assert text_in_rendered("offcanvas-panel", rendered)
        assert text_in_rendered("offcanvas-end", rendered)

    def test_offcanvas_has_loading_and_error_states(self):
        """Test that the offcanvas template includes loading and error state elements."""
        template = Template(
            "{% load i18n %}{% include 'gift_manager/includes/offcanvas_base.html' %}"
        )

        request = self.factory.get("/")
        request.user = self.user

        context = Context({"request": request})
        rendered = template.render(context)

        # Check for loading states
        assert text_in_rendered("loading-state", rendered)
        assert text_in_rendered("loading-spinner", rendered)

        # Check for error states
        assert text_in_rendered("error-state", rendered)
        assert text_in_rendered("alert-danger", rendered)

        # Check for retry functionality
        assert text_in_rendered("retryOffcanvasLoad", rendered)
        assert text_in_rendered("retryDetailLoad", rendered)

    def test_offcanvas_javascript_functions_defined(self):
        """Test that the offcanvas template defines required JavaScript functions."""
        template = Template(
            "{% load i18n %}{% include 'gift_manager/includes/offcanvas_base.html' %}"
        )

        request = self.factory.get("/")
        request.user = self.user

        context = Context({"request": request})
        rendered = template.render(context)

        # Check for JavaScript function definitions
        assert text_in_rendered("showOffcanvasLoading", rendered)
        assert text_in_rendered("hideOffcanvasLoading", rendered)
        assert text_in_rendered("showOffcanvasError", rendered)
        assert text_in_rendered("retryOffcanvasLoad", rendered)
        assert text_in_rendered("retryDetailLoad", rendered)

    def test_form_partial_template_renders(self):
        """Test that the form partial template renders correctly."""
        template = Template(
            "{% load i18n %}"
            "{% include 'gift_manager/includes/form_partial.html' with form_action_url='/test/' %}"
        )

        request = self.factory.get("/")
        request.user = self.user

        context = Context(
            {
                "request": request,
                "form": {},  # Mock form object
                "form_action_url": "/test/",
            }
        )
        rendered = template.render(context)

        # Check for form elements
        assert text_in_rendered("offcanvas-form", rendered)
        assert text_in_rendered("panel-form-actions", rendered)
        assert text_in_rendered('hx-post="/test/"', rendered)
        # Just check that the form structure is correct, CSRF token rendering depends on context

    def test_form_partial_has_htmx_integration(self):
        """Test that the form partial template includes proper HTMX integration."""
        template = Template(
            "{% load i18n %}"
            "{% include 'gift_manager/includes/form_partial.html' with form_action_url='/test/' %}"
        )

        request = self.factory.get("/")
        request.user = self.user

        context = Context({"request": request, "form": {}, "form_action_url": "/test/"})
        rendered = template.render(context)

        # Check for HTMX attributes
        assert text_in_rendered("hx-post=", rendered)
        assert text_in_rendered("hx-target=", rendered)
        assert text_in_rendered("hx-swap=", rendered)
        assert text_in_rendered("hx-indicator=", rendered)
