from unittest.mock import Mock
from unittest.mock import patch

import pytest

from gift_manager.models import Person
from gift_manager.models import PersonPermission
from gift_manager.permissions import PermissionLevel
from gift_manager.permissions import delete_permission


class TestDeletePermission:
    @pytest.fixture
    def mock_user(self):
        return Mock(spec=["id"])

    @pytest.fixture
    def mock_obj(self):
        obj = Mock(spec=["__class__", "shared_with"])
        obj.__class__ = Person
        obj.shared_with = Mock()
        obj.shared_with.all = Mock(return_value=[])
        return obj

    @pytest.fixture
    def mock_permission_obj(self):
        return Mock(spec=["delete", "permission_type"])

    def test_delete_permission_success(self, mock_user, mock_obj, mock_permission_obj):
        # Setup
        mock_obj.shared_with.all.return_value = [mock_user]

        with (
            patch("gift_manager.permissions.get_permission_model", return_value=PersonPermission),
            patch.object(
                PersonPermission.objects, "get", return_value=mock_permission_obj
            ) as mock_get,
        ):
            # Execute
            result = delete_permission(mock_user, mock_obj)

            # Verify
            mock_get.assert_called_once()
            mock_permission_obj.delete.assert_called_once()
            mock_obj.shared_with.remove.assert_called_once_with(mock_user)
            assert result is True

    def test_delete_permission_not_exist(self, mock_user, mock_obj):
        # Setup
        with (
            patch("gift_manager.permissions.get_permission_model", return_value=PersonPermission),
            patch.object(
                PersonPermission.objects, "get", side_effect=PersonPermission.DoesNotExist()
            ) as mock_get,
        ):
            # Execute
            result = delete_permission(mock_user, mock_obj)

            # Verify
            mock_get.assert_called_once()
            assert result is False
            mock_obj.shared_with.remove.assert_not_called()

    def test_delete_permission_no_model(self, mock_user, mock_obj):
        # Setup et exécution
        with (
            patch("gift_manager.permissions.get_permission_model", return_value=None),
            pytest.raises(
                ValueError, match="Could not determine permission model for this object type"
            ),
        ):
            delete_permission(mock_user, mock_obj)

    def test_delete_permission_no_shared_with(self, mock_user, mock_permission_obj):
        # Setup - object without shared_with attribute
        mock_obj_no_sharing = Mock(spec=["__class__"])
        mock_obj_no_sharing.__class__ = Person

        with (
            patch("gift_manager.permissions.get_permission_model", return_value=PersonPermission),
            patch.object(
                PersonPermission.objects, "get", return_value=mock_permission_obj
            ) as mock_get,
        ):
            # Execute
            result = delete_permission(mock_user, mock_obj_no_sharing)

            # Verify
            mock_get.assert_called_once()
            mock_permission_obj.delete.assert_called_once()
            assert result is True

    def test_delete_permission_user_not_in_shared_with(
        self, mock_user, mock_obj, mock_permission_obj
    ):
        # Setup - user not in shared_with
        other_user = Mock()
        mock_obj.shared_with.all.return_value = [other_user]

        with (
            patch("gift_manager.permissions.get_permission_model", return_value=PersonPermission),
            patch.object(
                PersonPermission.objects, "get", return_value=mock_permission_obj
            ) as mock_get,
        ):
            # Execute
            result = delete_permission(mock_user, mock_obj)

            # Verify
            mock_get.assert_called_once()
            mock_permission_obj.delete.assert_called_once()
            mock_obj.shared_with.remove.assert_not_called()
            assert result is True


@pytest.mark.parametrize(
    ("permission_level", "expected_label"),
    [
        (PermissionLevel.VIEWER, "Viewer"),
        (PermissionLevel.EDITOR, "Editor"),
        (PermissionLevel.OWNER, "Owner"),
    ],
)
def test_permission_labels(permission_level, expected_label):
    assert PermissionLevel.get_label(permission_level, case="title") == expected_label
