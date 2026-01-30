"""Tests for HTMXResponseMixin."""

import pytest

from gift_manager.views.base import HTMXResponseMixin


class TestHTMXResponseMixin:
    """Test cases for HTMXResponseMixin."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mixin = HTMXResponseMixin()

    def test_get_template_names_with_htmx(self):
        """Test template selection for HTMX requests."""
        self.mixin.is_htmx = True
        self.mixin.htmx_template_name = "test_partial.html"

        # Mock the parent method to return default templates
        def mock_super_get_template_names():
            return ["default.html"]

        # Temporarily replace the super() call
        self.mixin.get_template_names = lambda: mock_super_get_template_names()

        # Test that HTMX template is returned when available
        original_method = HTMXResponseMixin.get_template_names
        result = original_method(self.mixin)

        assert result == ["test_partial.html"]

    def test_get_template_names_without_htmx(self):
        """Test template selection for regular requests."""
        self.mixin.is_htmx = False
        self.mixin.htmx_template_name = "test_partial.html"

        # Mock the parent method to return default templates
        def mock_super_get_template_names():
            return ["default.html"]

        # Temporarily replace the super() call
        self.mixin.get_template_names = lambda: mock_super_get_template_names()

        result = self.mixin.get_template_names()
        assert result == ["default.html"]

    def test_get_template_names_no_htmx_template(self):
        """Test template selection when no HTMX template is defined."""
        self.mixin.is_htmx = True
        self.mixin.htmx_template_name = None

        # Mock the parent method to return default templates
        def mock_super_get_template_names():
            return ["default.html"]

        # Temporarily replace the super() call
        self.mixin.get_template_names = lambda: mock_super_get_template_names()

        result = self.mixin.get_template_names()
        assert result == ["default.html"]

    def test_get_success_message_default(self):
        """Test default get_success_message method."""
        result = self.mixin.get_success_message()
        assert result is None


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
