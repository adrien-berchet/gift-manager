from datetime import timedelta
from unittest.mock import Mock
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from gift_manager.models import GiftTagPermission
from gift_manager.models import PermissionLevel
from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import GiftTagFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import RelationStatusFactory
from gift_manager.views import get_user
from gift_manager.views import home


@pytest.mark.django_db
class TestGetUser:
    """Tests for get_user."""

    def test_user_not_found(self):
        """Test that get_user raises `User.DoesNotExist` when user is not found."""
        # Act / Assert
        with pytest.raises(User.DoesNotExist):
            get_user("123")

    def test_user_found(self, user, username):
        """Test that get_user returns the proper User object."""
        # Act / Assert
        retrieved_user = get_user(user.id)
        assert retrieved_user == (user, username)

    def test_user_found_return_id(self, user, username):
        """Test that get_user returns the proper User object and its ID."""
        # Act / Assert
        retrieved_user = get_user(user.id, return_id=True)
        assert retrieved_user == (user, username, user.id)


@pytest.mark.django_db
@patch("gift_manager.views.common.render")
def test_home_view(mock_render, user):
    """Test that home view renders correct template."""
    # Arrange
    mock_request = Mock()
    mock_request.user = user

    # Act
    result = home(mock_request)

    # Assert
    mock_render.assert_called_once()
    assert mock_render.call_args[0][0] == mock_request
    assert mock_render.call_args[0][1] == "gift_manager/home.html"
    assert result == mock_render.return_value


@pytest.mark.django_db
class TestHomeDashboard:
    """Tests for the action-oriented authenticated dashboard."""

    @pytest.fixture(autouse=True)
    def setup_user(self, client, user):
        self.client = client
        self.user = user
        self.client.force_login(user)

    def test_dashboard_prioritizes_action_groups_and_filters_private_plans(self):
        today = timezone.localdate()
        idea = RelationStatusFactory(status="Idea")
        planned = RelationStatusFactory(status="Planned")
        abandoned = RelationStatusFactory(status="Abandoned")
        completed = RelationStatusFactory(status="Given")
        stale_event = EventFactory(
            name="Winter party",
            usual_date=today + timedelta(days=60),
            recurrence="yearly",
            shared_with=[self.user],
        )

        RelationFactory(
            gift=GiftFactory(name="Overdue scarf"),
            status=idea,
            due_date=today - timedelta(days=1),
            shared_with=[self.user],
        )
        RelationFactory(
            gift=GiftFactory(name="Soon puzzle"),
            status=idea,
            due_date=today + timedelta(days=3),
            shared_with=[self.user],
        )
        RelationFactory(
            gift=GiftFactory(name="Missing date"),
            event=None,
            status=planned,
            due_date=None,
            shared_with=[self.user],
        )
        RelationFactory(
            gift=GiftFactory(name="Someday telescope"),
            event=None,
            status=idea,
            due_date=None,
            shared_with=[self.user],
        )
        RelationFactory(
            gift=GiftFactory(name="Rejected gadget"),
            status=abandoned,
            due_date=today - timedelta(days=5),
            shared_with=[self.user],
        )
        stale_plan = RelationFactory(
            gift=GiftFactory(name="Old idea"),
            event=stale_event,
            status=idea,
            due_date=today + timedelta(days=70),
            shared_with=[self.user],
        )
        stale_plan.__class__.objects.filter(pk=stale_plan.pk).update(
            creation_date=timezone.now() - timedelta(days=45)
        )
        RelationFactory(
            gift=GiftFactory(name="Already done"),
            status=completed,
            due_date=today - timedelta(days=2),
            shared_with=[self.user],
        )
        RelationFactory(
            gift=GiftFactory(name="Private plan"),
            status=idea,
            due_date=today - timedelta(days=2),
        )

        response = self.client.get(reverse("gift_manager:home"))

        assert response.status_code == 200
        groups = response.context["dashboard_action_groups"]
        assert [group["key"] for group in groups] == [
            "overdue",
            "upcoming",
            "incomplete",
            "stale",
        ]
        assert response.context["dashboard_summary"]["overdue"] == 1
        assert response.context["dashboard_summary"]["upcoming"] == 1
        assert response.context["dashboard_summary"]["incomplete"] == 1
        assert response.context["dashboard_summary"]["stale"] == 1

        content = response.content.decode()
        groups_by_key = {group["key"]: group for group in groups}
        assert groups_by_key["upcoming"]["is_paginated"] is True
        assert groups_by_key["upcoming"]["display_items"] == groups_by_key["upcoming"]["items"]
        assert groups_by_key["incomplete"]["is_paginated"] is True
        assert groups_by_key["incomplete"]["display_items"] == groups_by_key["incomplete"]["items"]
        assert "Overdue scarf" in content
        assert "Soon puzzle" in content
        assert "Missing date" in content
        assert "Someday telescope" not in content
        assert "Rejected gadget" not in content
        assert "Old idea" in content
        assert "Already done" not in content
        assert "Private plan" not in content
        assert (
            "dashboard-action-item dashboard-action-item--incomplete dashboard-action-item--compact"
        ) in content
        assert (
            "dashboard-action-item dashboard-action-item--upcoming dashboard-action-item--compact"
        ) in content
        assert (
            "dashboard-action-list dashboard-action-list--responsive "
            "dashboard-action-list--paginated"
        ) in content
        assert "dashboard-action-list--scrollable" not in content
        assert "data-dashboard-action-paginated" in content
        assert "data-dashboard-pagination" in content
        assert 'id="dashboard-live"' in content
        assert "data-list-container" in content
        assert 'hx-trigger="refresh"' in content
        assert 'hx-select="#dashboard-live"' in content
        assert (
            "dashboard-action-item dashboard-action-item--stale dashboard-action-item--compact"
        ) not in content
        assert content.index("Next actions") < content.index('class="stats-grid"')

    def test_dashboard_paginated_action_groups_render_all_items(self):
        today = timezone.localdate()
        planned = RelationStatusFactory(status="Planned")

        for index in range(5):
            RelationFactory(
                gift=GiftFactory(name=f"Due soon paginated item {index}"),
                status=planned,
                due_date=today + timedelta(days=index + 1),
                shared_with=[self.user],
            )
            RelationFactory(
                gift=GiftFactory(name=f"Needs details paginated item {index}"),
                event=None,
                status=planned,
                due_date=None,
                shared_with=[self.user],
            )

        response = self.client.get(reverse("gift_manager:home"))

        assert response.status_code == 200
        groups_by_key = {
            group["key"]: group for group in response.context["dashboard_action_groups"]
        }
        assert len(groups_by_key["upcoming"]["display_items"]) == 5
        assert len(groups_by_key["incomplete"]["display_items"]) == 5

        content = response.content.decode()
        assert "Due soon paginated item 4" in content
        assert "Needs details paginated item 4" in content

    def test_dashboard_surfaces_unassigned_gifts_and_upcoming_occasion_recipients(self):
        today = timezone.localdate()
        idea = RelationStatusFactory(status="Idea")
        unassigned_gift = GiftFactory(name="Loose puzzle", shared_with=[self.user])
        assigned_gift = GiftFactory(name="Assigned candle", shared_with=[self.user])
        event = EventFactory(
            name="Birthday",
            usual_date=today + timedelta(days=5),
            recurrence="yearly",
            shared_with=[self.user],
        )
        person = PersonFactory(
            first_name="Ada",
            family_name="Lovelace",
            shared_with=[self.user],
        )
        RelationFactory(
            person=person,
            gift=assigned_gift,
            event=event,
            status=idea,
            due_date=today + timedelta(days=4),
            shared_with=[self.user],
        )

        response = self.client.get(reverse("gift_manager:home"))

        assert response.status_code == 200
        assert list(response.context["unassigned_gifts"]) == [unassigned_gift]
        occasion_items = response.context["upcoming_occasion_recipients"]
        assert len(occasion_items) == 1
        assert occasion_items[0]["event"] == event
        assert occasion_items[0]["relation"].recipient_name == "Ada Lovelace"

        content = response.content.decode()
        assert "Loose puzzle" in content
        assert "Assigned candle" in content
        assert "Ada Lovelace" in content
        assert "Birthday" in content
        assert "Plan" in content

    def test_empty_dashboard_keeps_create_actions_before_secondary_counts(self):
        response = self.client.get(reverse("gift_manager:home"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "No gift plans need attention." in content
        assert "Create a gift plan" in content
        assert "Add a gift" in content
        assert content.index("Needs attention") < content.index("Library")
        assert content.index("Library") < content.index('class="stats-grid"')


@pytest.mark.django_db
class TestGlobalSearchView:
    """Tests for global_search view.

    Note: These tests may fail with 404 errors if the gift_manager URLs are wrapped
    in i18n_patterns without proper language prefix handling in tests. If tests fail,
    ensure the test client is properly configured to handle internationalized URLs.
    """

    @pytest.fixture(autouse=True)
    def setup_user(self, user):
        """Create a test user and authenticate the client."""
        self.user = user
        self.client = Client()
        self.client.force_login(self.user)

    def test_search_finds_gifts(self):
        """Test that search finds gifts by name."""
        # Arrange
        gift = GiftFactory(name="Awesome Book", shared_with=[self.user])
        url = reverse("gift_manager:global_search")

        # Act
        response = self.client.get(url, {"q": "book"})

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) > 0

        gift_results = [r for r in data["results"] if r["type"] == "gift"]
        assert len(gift_results) == 1
        assert gift_results[0]["title"] == "Awesome Book"
        assert gift_results[0]["icon"] == "fa-gift"
        assert f"/gifts/{gift.gift_id}/" in gift_results[0]["url"]

    def test_search_finds_gifts_by_comment(self):
        """Test that search finds gifts by comment."""
        # Arrange
        GiftFactory(
            name="Generic Gift", comment="This is a special vintage item", shared_with=[self.user]
        )
        url = reverse("gift_manager:global_search")

        # Act
        response = self.client.get(url, {"q": "vintage"})

        # Assert
        assert response.status_code == 200
        data = response.json()

        gift_results = [r for r in data["results"] if r["type"] == "gift"]
        assert len(gift_results) == 1
        assert gift_results[0]["title"] == "Generic Gift"

    def test_search_finds_persons(self):
        """Test that search finds persons by first name."""
        # Arrange
        person = PersonFactory(first_name="John", family_name="Doe", shared_with=[self.user])
        url = reverse("gift_manager:global_search")

        # Act
        response = self.client.get(url, {"q": "john"})

        # Assert
        assert response.status_code == 200
        data = response.json()

        person_results = [
            r for r in data["results"] if r["type"] == "recipient" and r["subtitle"] == "Person"
        ]
        assert len(person_results) == 1
        assert person_results[0]["icon"] == "fa-user"
        assert f"/persons/{person.person_id}/" in person_results[0]["url"]

    def test_search_finds_persons_by_family_name(self):
        """Test that search finds persons by family name."""
        # Arrange
        PersonFactory(first_name="Jane", family_name="Smith", shared_with=[self.user])
        url = reverse("gift_manager:global_search")

        # Act
        response = self.client.get(url, {"q": "smith"})

        # Assert
        assert response.status_code == 200
        data = response.json()

        person_results = [
            r for r in data["results"] if r["type"] == "recipient" and r["subtitle"] == "Person"
        ]
        assert len(person_results) == 1

    def test_search_finds_person_groups(self):
        """Test that search finds person groups by name."""
        # Arrange
        group = PersonGroupFactory(name="Family Friends", shared_with=[self.user])
        url = reverse("gift_manager:global_search")

        # Act
        response = self.client.get(url, {"q": "family"})

        # Assert
        assert response.status_code == 200
        data = response.json()

        group_results = [
            r for r in data["results"] if r["type"] == "recipient" and r["subtitle"] == "Group"
        ]
        assert len(group_results) == 1
        assert group_results[0]["title"] == "Family Friends"
        assert group_results[0]["icon"] == "fa-layer-group"
        assert f"/person_groups/{group.group_id}/" in group_results[0]["url"]

    def test_search_finds_events(self):
        """Test that search finds events by name."""
        # Arrange
        event = EventFactory(name="Birthday Party", shared_with=[self.user])
        url = reverse("gift_manager:global_search")

        # Act
        response = self.client.get(url, {"q": "birthday"})

        # Assert
        assert response.status_code == 200
        data = response.json()

        event_results = [r for r in data["results"] if r["type"] == "event"]
        assert len(event_results) == 1
        assert event_results[0]["title"] == "Birthday Party"
        assert event_results[0]["icon"] == "fa-calendar-alt"
        assert f"/events/{event.event_id}/" in event_results[0]["url"]

    def test_search_finds_tags(self):
        """Test that search finds tags by name."""
        # Arrange
        # Note: Tags don't use shared_with pattern in the current implementation
        # They're created and queried directly
        tag = GiftTagFactory(name="Electronics")
        GiftTagPermission.objects.create(
            user=self.user, gift_tag=tag, permission_type=PermissionLevel.OWNER
        )
        url = reverse("gift_manager:global_search")

        # Act
        response = self.client.get(url, {"q": "electronics"})

        # Assert
        assert response.status_code == 200
        data = response.json()

        tag_results = [r for r in data["results"] if r["type"] == "tag"]
        assert len(tag_results) == 1
        assert tag_results[0]["title"] == "Electronics"
        assert tag_results[0]["icon"] == "fa-tag"
        assert f"/gift-tag/{tag.tag_id}/" in tag_results[0]["url"]

    def test_search_case_insensitive(self):
        """Test that search is case-insensitive."""
        # Arrange
        GiftFactory(name="Awesome Book", shared_with=[self.user])
        url = reverse("gift_manager:global_search")

        # Act
        response = self.client.get(url, {"q": "AWESOME"})

        # Assert
        assert response.status_code == 200
        data = response.json()

        gift_results = [r for r in data["results"] if r["type"] == "gift"]
        assert len(gift_results) == 1

    def test_search_respects_permissions(self):
        """Test that search only returns accessible items."""
        # Arrange
        # Create another user and their gift
        other_user = User.objects.create_user(
            username="otheruser", email="other@example.com", password="testpass123"
        )
        GiftFactory(name="Private Gift", shared_with=[other_user])

        # Create a gift accessible to current user
        GiftFactory(name="My Gift", shared_with=[self.user])

        url = reverse("gift_manager:global_search")

        # Act
        response = self.client.get(url, {"q": "gift"})

        # Assert
        assert response.status_code == 200
        data = response.json()

        gift_results = [r for r in data["results"] if r["type"] == "gift"]
        # Should only find "My Gift", not "Private Gift"
        assert len(gift_results) == 1
        assert gift_results[0]["title"] == "My Gift"

    def test_search_limits_results_per_category(self):
        """Test that search limits results to max_per_category."""
        # Arrange
        # Create 7 gifts with "test" in the name
        for i in range(7):
            GiftFactory(name=f"Test Gift {i}", shared_with=[self.user])

        url = reverse("gift_manager:global_search")

        # Act
        response = self.client.get(url, {"q": "test"})

        # Assert
        assert response.status_code == 200
        data = response.json()

        gift_results = [r for r in data["results"] if r["type"] == "gift"]
        # Should be limited to 5 per category
        assert len(gift_results) == 5

    def test_search_truncates_long_subtitles(self):
        """Test that long gift comments are truncated in subtitles."""
        # Arrange
        long_comment = "a" * 100  # 100 characters
        GiftFactory(name="Test Gift", comment=long_comment, shared_with=[self.user])
        url = reverse("gift_manager:global_search")

        # Act
        response = self.client.get(url, {"q": "test"})

        # Assert
        assert response.status_code == 200
        data = response.json()

        gift_results = [r for r in data["results"] if r["type"] == "gift"]
        assert len(gift_results) == 1
        # Subtitle should be truncated to 50 chars + "..."
        assert len(gift_results[0]["subtitle"]) == 53
        assert gift_results[0]["subtitle"].endswith("...")

    def test_search_returns_multiple_types(self):
        """Test that search can return results from multiple types."""
        # Arrange
        GiftFactory(name="Party Supplies", shared_with=[self.user])
        EventFactory(name="Birthday Party", shared_with=[self.user])
        PersonFactory(first_name="Party", family_name="Planner", shared_with=[self.user])

        url = reverse("gift_manager:global_search")

        # Act
        response = self.client.get(url, {"q": "party"})

        # Assert
        assert response.status_code == 200
        data = response.json()

        # Should have results from multiple types
        types_found = {r["type"] for r in data["results"]}
        assert "gift" in types_found
        assert "event" in types_found
        assert "recipient" in types_found
