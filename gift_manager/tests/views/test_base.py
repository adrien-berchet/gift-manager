from unittest.mock import Mock
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.test import override_settings
from django.urls import reverse

from gift_manager.models import Gift
from gift_manager.models import Person
from gift_manager.permissions import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.permissions import get_permission
from gift_manager.views import FilterByUserMixin
from gift_manager.views import GetObjectByTokenMixin


class TestFilterByUserMixin:
    """Tests for FilterByUserMixin."""

    def test_get_queryset(self):
        """Test queryset is filtered by current user."""
        # Arrange
        mixin = FilterByUserMixin()
        mixin.model = Mock()
        mixin.request = Mock()
        mixin.request.user = Mock(spec=User)

        mock_queryset = Mock()
        mixin.model.objects.filter.return_value = mock_queryset

        # Act
        result = mixin.get_queryset()

        # Assert
        mixin.model.objects.filter.assert_called_once()
        assert result == mock_queryset


class TestGetObjectByTokenMixin:
    """Tests for GetObjectByTokenMixin."""

    def test_get_object_success(self):
        """Test getting object by token successfully."""
        # Arrange
        mixin = GetObjectByTokenMixin()
        mixin.pk_name = "test_id"
        mixin.get_queryset = Mock(return_value=Mock())
        mixin.kwargs = {"pk": "123"}

        with patch(
            "gift_manager.views.base.get_object_or_404", return_value="found_object"
        ) as mock_get:
            # Act
            result = mixin.get_object()

            # Assert
            mock_get.assert_called_once_with(mixin.get_queryset.return_value, test_id="123")
            assert result == "found_object"

    def test_get_object_missing_pk(self):
        """Test error when pk is missing."""
        # Arrange
        mixin = GetObjectByTokenMixin()
        mixin.get_queryset = Mock(return_value=Mock())


@pytest.mark.django_db
class TestBaseCreateView:
    """Tests for BaseCreateView."""

    @pytest.fixture(autouse=True)
    def setup(self, user):
        """Setup test fixtures."""
        self.user = user
        self.client = Client()
        self.client.force_login(user)

    @override_settings(USE_I18N=False)
    def test_gift_create_view_with_shared_permissions(self):
        """Test creating an object with sharing permissions."""
        # Create a friend user
        friend = User.objects.create_user(
            username="testfriend", email="friend@example.com", password="password123"
        )
        # Add the friend to the user's profile
        self.user.profile.friends.add(friend.profile)

        # Create gift with sharing
        url = reverse("gift_manager:gift_create")
        data = {
            "name": "Test Shared Gift",
            "comment": "Gift with sharing",
            "share_with_" + str(friend.id): PermissionLevel.VIEWER,
        }

        # Act
        response = self.client.post(url, data)

        # Assert
        assert response.status_code == 302  # Redirect after success

        # Check that gift was created
        gift = Gift.objects.get(name="Test Shared Gift")
        assert gift is not None

        # Check that sharing was created
        permissions = get_permission(gift, friend)
        assert permissions == PermissionLevel.VIEWER


@pytest.mark.django_db
class TestEditPermissionMixin:
    """Tests for EditPermissionMixin."""

    @pytest.fixture(autouse=True)
    def setup(self, user, userpassword, person):
        """Setup test fixtures."""
        self.user = user
        self.person = person

        # Create a friend
        self.friend = User.objects.create_user(
            username="testfriend", email="friend@example.com", password=userpassword
        )

        # Add the friend to the user's profile
        self.user.profile.friends.add(self.friend.profile)

        # Create a permission for the person
        create_or_update_permission(self.user, self.person, permission_level=PermissionLevel.OWNER)

        self.client = Client()
        self.client.force_login(user)


@pytest.mark.django_db
class TestDeleteSharedMixin:
    """Tests for DeleteSharedMixin."""

    @pytest.fixture(autouse=True)
    def setup(self, user, userpassword):
        """Setup test fixtures."""
        self.user = user
        self.client = Client()
        self.client.force_login(user)

        # Create another user
        self.other_user = User.objects.create_user(
            username="otheruser", email="other@example.com", password=userpassword
        )

        # Create a test person shared with both users
        self.person = Person.objects.create(
            first_name="Shared",
            family_name="Person",
        )
        create_or_update_permission(user, self.person, permission_level=PermissionLevel.OWNER)
        create_or_update_permission(
            self.other_user, self.person, permission_level=PermissionLevel.VIEWER
        )

        # Create a test person shared only with current user
        self.person_not_shared = Person.objects.create(
            first_name="Not",
            family_name="Shared",
        )
        create_or_update_permission(
            user, self.person_not_shared, permission_level=PermissionLevel.OWNER
        )

    @override_settings(USE_I18N=False)
    def test_delete_shared_object(self):
        """Test deleting an object shared with other users."""
        url = reverse("gift_manager:person_delete", kwargs={"pk": self.person.person_id})

        # Act
        response = self.client.post(url)

        # Assert
        assert response.status_code == 302  # Redirect after action

        # The person should still exist (only sharing is removed)
        self.person.refresh_from_db()

        # Current user should not have access anymore
        assert get_permission(self.person, self.user) == PermissionLevel.NONE

        # Other user should still have access
        assert get_permission(self.person, self.other_user) == PermissionLevel.VIEWER

    @override_settings(USE_I18N=False)
    def test_delete_non_shared_object(self):
        """Test deleting an object not shared with other users."""
        url = reverse("gift_manager:person_delete", kwargs={"pk": self.person_not_shared.person_id})

        # Act
        response = self.client.post(url)

        # Assert
        assert response.status_code == 302  # Redirect after action

        # The person should be completely deleted
        with pytest.raises(Person.DoesNotExist):
            self.person_not_shared.refresh_from_db()
