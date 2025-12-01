from unittest.mock import Mock
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User

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


@patch("gift_manager.views.common.render")
def test_home_view(mock_render):
    """Test that home view renders correct template."""
    # Arrange
    mock_request = Mock()

    # Act
    result = home(mock_request)

    # Assert
    mock_render.assert_called_once_with(mock_request, "gift_manager/home.html")
    assert result == mock_render.return_value
