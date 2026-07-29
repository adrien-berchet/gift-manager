"""Tests for quick action buttons in list views."""

import pytest
from django.test import Client
from django.urls import reverse

from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import UserFactory


@pytest.mark.django_db
class TestQuickActionButtons:
    """Test quick action buttons in list views."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        self.user = UserFactory()
        self.client = Client()
        self.client.force_login(self.user)

    def test_person_list_contains_action_buttons(self):
        """Test that person list contains quick action buttons."""
        PersonFactory()

        url = reverse("gift_manager:persons")
        response = self.client.get(url)

        assert response.status_code == 200
        content = response.content.decode()

        # Check that the action buttons configuration includes all expected actions
        assert "'give'" in content
        assert "'details'" in content
        assert "'edit'" in content
        assert "'delete'" in content
        assert "'share'" in content

        # Check that the actions array includes all buttons
        assert "['give', 'details', 'edit', 'delete', 'share']" in content

    def test_gift_list_contains_action_buttons(self):
        """Test that gift list contains quick action buttons."""
        GiftFactory()

        url = reverse("gift_manager:gifts")
        response = self.client.get(url)

        assert response.status_code == 200
        content = response.content.decode()

        # Check that the action buttons configuration includes all expected actions
        assert "'give'" in content
        assert "'details'" in content
        assert "'edit'" in content
        assert "'delete'" in content
        assert "'share'" in content

        # Check that the actions array includes all buttons
        assert "['give', 'details', 'edit', 'delete', 'share']" in content

    def test_event_list_contains_action_buttons(self):
        """Test that event list contains quick action buttons."""
        EventFactory()

        url = reverse("gift_manager:events")
        response = self.client.get(url)

        assert response.status_code == 200
        content = response.content.decode()

        # Check that the action buttons configuration includes expected actions
        assert "'details'" in content
        assert "'edit'" in content
        assert "'delete'" in content
        assert "'share'" in content

        # Check that the actions array includes all buttons (no 'give' for events)
        assert "['details', 'edit', 'delete', 'share']" in content

    def test_relation_list_contains_action_buttons(self):
        """Test that relation list contains quick action buttons."""
        RelationFactory()

        url = reverse("gift_manager:relations")
        response = self.client.get(url)

        assert response.status_code == 200
        content = response.content.decode()

        # Check that the action buttons configuration includes expected actions
        assert "'details'" in content
        assert "'edit'" in content
        assert "'delete'" in content
        assert "'share'" in content

        # Check that the actions array includes all buttons
        assert "['details', 'edit', 'delete', 'share']" in content

    def test_person_group_list_contains_action_buttons(self):
        """Test that person group list contains quick action buttons."""
        PersonGroupFactory()

        url = reverse("gift_manager:person_groups")
        response = self.client.get(url)

        assert response.status_code == 200
        content = response.content.decode()

        # Check that the action buttons configuration includes all expected actions
        assert "'give'" in content
        assert "'details'" in content
        assert "'edit'" in content
        assert "'delete'" in content
        assert "'share'" in content

        # Check that the actions array includes all buttons
        assert "['give', 'details', 'edit', 'delete', 'share']" in content

    def test_action_buttons_width_increased(self):
        """Test that action column width accommodates labeled action buttons."""
        url = reverse("gift_manager:persons")
        response = self.client.get(url)

        assert response.status_code == 200
        content = response.content.decode()

        assert "width: '360px'" in content

    def test_share_button_points_to_share_objects_url(self):
        """Test that share buttons point to the correct share URL."""
        url = reverse("gift_manager:persons")
        response = self.client.get(url)

        assert response.status_code == 200
        content = response.content.decode()

        # Check that share button uses the share_objects URL
        share_url = reverse("gift_manager:share_objects")
        assert f'share: () => "{share_url}"' in content
