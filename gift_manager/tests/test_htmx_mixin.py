"""Tests for HTMXResponseMixin."""

import pytest

from gift_manager.views.base import HTMXResponseMixin


class TemplateParent:
    """Parent view stand-in with the default template behavior."""

    def get_template_names(self):
        """Return default template names."""
        return ["default.html"]


class HTMXTestView(HTMXResponseMixin, TemplateParent):
    """Concrete test view that exercises HTMXResponseMixin.super()."""


class TestHTMXResponseMixin:
    """Test cases for HTMXResponseMixin."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mixin = HTMXTestView()

    def test_get_template_names_with_htmx(self):
        """Test template selection for HTMX requests."""
        self.mixin.is_htmx = True
        self.mixin.htmx_template_name = "test_partial.html"

        result = self.mixin.get_template_names()

        assert result == ["test_partial.html"]

    def test_get_template_names_without_htmx(self):
        """Test template selection for regular requests."""
        self.mixin.is_htmx = False
        self.mixin.htmx_template_name = "test_partial.html"

        result = self.mixin.get_template_names()
        assert result == ["default.html"]

    def test_get_template_names_no_htmx_template(self):
        """Test template selection when no HTMX template is defined."""
        self.mixin.is_htmx = True
        self.mixin.htmx_template_name = None

        result = self.mixin.get_template_names()
        assert result == ["default.html"]

    def test_get_success_message_default(self):
        """Test default get_success_message method."""
        assert self.mixin.get_success_message() is None


@pytest.mark.django_db
class TestHTMXMixinIntegration:
    """Integration tests for HTMX mixin functionality."""

    def test_mixin_attributes(self):
        """Test that mixin has the expected attributes."""
        mixin = HTMXResponseMixin()

        # Test default attribute values
        assert hasattr(mixin, "htmx_template_name")
        assert hasattr(mixin, "close_modal")
        assert hasattr(mixin, "close_offcanvas")

        # Test that get_success_message method exists
        assert callable(getattr(mixin, "get_success_message", None))

    def test_mixin_can_be_subclassed(self):
        """Test that the mixin can be properly subclassed."""

        class TestMixin(HTMXResponseMixin):
            htmx_template_name = "test.html"
            close_modal = True

            def get_success_message(self):
                return "Test success"

        mixin = TestMixin()
        assert mixin.htmx_template_name == "test.html"
        assert mixin.close_modal is True
        assert mixin.get_success_message() == "Test success"
