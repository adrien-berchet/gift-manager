from unittest.mock import Mock
from unittest.mock import patch

# from venv import create
# import attr
import pytest
from django.contrib.auth.models import User

from gift_manager.models import EventPermission
from gift_manager.models import GiftPermission
from gift_manager.models import Person
from gift_manager.models import PersonGroupPermission
from gift_manager.models import PersonPermission
from gift_manager.models import RelationPermission
from gift_manager.permissions import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.permissions import delete_permission
from gift_manager.permissions import get_permission
from gift_manager.permissions import get_permission_label
from gift_manager.permissions import get_permission_model


class TestPermissionLevel:
    """Tests for the PermissionLevel class."""

    @pytest.mark.parametrize(
        ("permission_level", "case", "expected"),
        [
            (PermissionLevel.NONE, "lower", "none"),
            (PermissionLevel.VIEWER, "lower", "viewer"),
            (PermissionLevel.EDITOR, "lower", "editor"),
            (PermissionLevel.OWNER, "lower", "owner"),
            (PermissionLevel.NONE, "upper", "NONE"),
            (PermissionLevel.VIEWER, "upper", "VIEWER"),
            (PermissionLevel.EDITOR, "upper", "EDITOR"),
            (PermissionLevel.OWNER, "upper", "OWNER"),
            (PermissionLevel.NONE, "title", "None"),
            (PermissionLevel.VIEWER, "title", "Viewer"),
            (PermissionLevel.EDITOR, "title", "Editor"),
            (PermissionLevel.OWNER, "title", "Owner"),
        ],
    )
    def test_get_label(self, permission_level, case, expected):
        """Test that permission levels are correctly translated with proper case."""
        assert PermissionLevel.get_label(permission_level, case) == expected

    def test_invalid_permission_level(self):
        """Test that invalid permission levels return the default 'none'."""
        assert PermissionLevel.get_label(999) == "none"


class TestGetPermissionModel:
    """Tests for the get_permission_model function."""

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        ("db_obj", "expected_permission_model"),
        [
            ("Person", PersonPermission),
            ("PersonGroup", PersonGroupPermission),
            ("Gift", GiftPermission),
            ("Event", EventPermission),
            ("Relation", RelationPermission),
        ],
        indirect=["db_obj"],
    )
    def test_get_permission_model(self, db_obj, expected_permission_model):
        """Test that the correct permission model is returned for various objects."""
        result = get_permission_model(db_obj)
        assert result == expected_permission_model

    def test_get_permission_model_unknown_class(self):
        """Test that None is returned for an unknown class."""

        class UnknownClass:
            pass

        obj = Mock(spec=["__class__"])
        obj.__class__ = UnknownClass

        with pytest.raises(TypeError, match="Could not determine the model of the object"):
            get_permission_model(obj)


class TestGetPermission:
    """Tests for the get_permission function."""

    def test_get_permission_mock(self):
        """Test that get_permission returns correct permission type."""
        # Arrange
        mock_obj = Mock()
        mock_user = Mock(spec=User)
        filter_name = "object_name"

        # Configure the mock relationship
        mock_through = Mock()
        mock_permission = Mock()
        mock_permission.permission_type = PermissionLevel.EDITOR
        mock_through.objects.filter.return_value.first.return_value = mock_permission
        mock_obj.shared_with.through = mock_through

        # Act
        result = get_permission(mock_obj, mock_user, filter_name)

        # Assert
        mock_through.objects.filter.assert_called_once_with(
            user=mock_user, **{filter_name: mock_obj}
        )
        assert result == PermissionLevel.EDITOR

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        "db_obj",
        [
            ("Person"),
            ("PersonGroup"),
            ("Gift"),
            ("Event"),
            ("Relation"),
        ],
        indirect=True,
    )
    def test_get_permission_model(self, db_obj):
        """Test that get_permission_label returns correct permission."""
        result = get_permission_model(db_obj)
        assert result == db_obj.shared_with.through

    @pytest.mark.parametrize(
        ("permission_level"),
        [
            (PermissionLevel.VIEWER),
            (PermissionLevel.EDITOR),
            (PermissionLevel.OWNER),
        ],
    )
    @pytest.mark.django_db
    def test_get_permission(self, permission_level, person, user):
        """Test that get_permission_label returns correct permission."""
        result = get_permission(person, user, "person")
        assert result == PermissionLevel.NONE

        create_or_update_permission(user, person, permission_level=permission_level)
        result = get_permission(person, user, "person")
        assert result == permission_level

    def test_get_permission_no_permission(self):
        """Test that get_permission returns NONE when no permission exists."""
        # Arrange
        mock_obj = Mock()
        mock_user = Mock(spec=User)
        filter_name = "object_name"

        # Configure the mock to return None (no permission)
        mock_through = Mock()
        mock_through.objects.filter.return_value.first.return_value = None
        mock_obj.shared_with.through = mock_through

        # Act
        result = get_permission(mock_obj, mock_user, filter_name)

        # Assert
        mock_through.objects.filter.assert_called_once_with(
            user=mock_user, **{filter_name: mock_obj}
        )
        assert result == PermissionLevel.NONE

    @pytest.mark.parametrize(
        ("permission_level", "case", "expected"),
        [
            (PermissionLevel.NONE, "lower", "none"),
            (PermissionLevel.VIEWER, "lower", "viewer"),
            (PermissionLevel.EDITOR, "lower", "editor"),
            (PermissionLevel.OWNER, "lower", "owner"),
            (PermissionLevel.NONE, "upper", "NONE"),
            (PermissionLevel.VIEWER, "upper", "VIEWER"),
            (PermissionLevel.EDITOR, "upper", "EDITOR"),
            (PermissionLevel.OWNER, "upper", "OWNER"),
            (PermissionLevel.NONE, "title", "None"),
            (PermissionLevel.VIEWER, "title", "Viewer"),
            (PermissionLevel.EDITOR, "title", "Editor"),
            (PermissionLevel.OWNER, "title", "Owner"),
        ],
    )
    @patch("gift_manager.services.PermissionService.get_permission")
    def test_get_permission_label(self, mock_get_permission, permission_level, case, expected):
        """Test that get_permission_label returns correct label."""
        # Arrange
        mock_obj = Mock()
        mock_user = Mock(spec=User)
        filter_name = "object_name"

        # Configure the mock to return the expected permission
        mock_get_permission.return_value = permission_level

        result = get_permission_label(mock_obj, mock_user, filter_name, case=case)

        # Assert
        mock_get_permission.assert_called_once_with(mock_obj, mock_user, filter_name)
        assert result == expected


class TestCreateOrUpdatePermission:
    """Tests for the create_or_update_permission function."""

    @pytest.fixture
    def mock_user(self):
        return Mock(spec=["id"])

    @pytest.fixture
    def mock_obj(self):
        obj = Mock(spec=["__class__", "shared_with"])
        obj.__class__ = Person
        obj.__class__.__name__ = "Person"
        obj.shared_with = Mock()
        obj.shared_with.all = Mock(return_value=[])
        return obj

    def test_create_permission_success(self, mock_user, mock_obj):
        """Test successfully creating a new permission."""
        # Setup
        mock_permission = Mock()

        with (
            patch(
                "gift_manager.services.PermissionService.get_permission_model",
                return_value=PersonPermission,
            ),
            patch.object(
                PersonPermission.objects, "get_or_create", return_value=(mock_permission, True)
            ) as mock_get_or_create,
        ):
            # Execute
            result = create_or_update_permission(mock_user, mock_obj)

            # Verify
            mock_get_or_create.assert_called_once_with(
                user=mock_user,
                person=mock_obj,
                defaults={"permission_type": PermissionLevel.VIEWER},
            )
            mock_obj.shared_with.add.assert_called_once_with(mock_user)
            assert result == mock_permission

    def test_update_permission_success(self, mock_user, mock_obj):
        """Test successfully updating an existing permission."""
        # Setup
        mock_permission = Mock(spec=["permission_type", "save"])
        mock_permission.permission_type = PermissionLevel.VIEWER

        with (
            patch(
                "gift_manager.services.PermissionService.get_permission_model",
                return_value=PersonPermission,
            ),
            patch.object(
                PersonPermission.objects, "get_or_create", return_value=(mock_permission, False)
            ) as mock_get_or_create,
        ):
            # Execute
            result = create_or_update_permission(
                mock_user, mock_obj, permission_level=PermissionLevel.EDITOR
            )

            # Verify
            mock_get_or_create.assert_called_once_with(
                user=mock_user,
                person=mock_obj,
                defaults={"permission_type": PermissionLevel.EDITOR},
            )
            assert mock_permission.permission_type == PermissionLevel.EDITOR
            mock_permission.save.assert_called_once()
            mock_obj.shared_with.add.assert_called_once_with(mock_user)
            assert result == mock_permission

    def test_create_permission_rejects_invalid_level(self, mock_user, mock_obj):
        """Test permission rows cannot be created with unsupported levels."""
        with pytest.raises(ValueError, match="Invalid permission value"):
            create_or_update_permission(mock_user, mock_obj, permission_level=999)

    def test_no_permission_level_change(self, mock_user, mock_obj):
        """Test that permission isn't updated when level is unchanged."""
        # Setup
        mock_permission = Mock(spec=["permission_type", "save"])
        mock_permission.permission_type = PermissionLevel.EDITOR

        with (
            patch(
                "gift_manager.services.PermissionService.get_permission_model",
                return_value=PersonPermission,
            ),
            patch.object(
                PersonPermission.objects, "get_or_create", return_value=(mock_permission, False)
            ) as mock_get_or_create,
        ):
            # Execute
            result = create_or_update_permission(
                mock_user, mock_obj, permission_level=PermissionLevel.EDITOR
            )

            # Verify
            mock_get_or_create.assert_called_once()
            mock_permission.save.assert_not_called()
            mock_obj.shared_with.add.assert_called_once_with(mock_user)
            assert result == mock_permission

    def test_custom_object_attr(self, mock_user, mock_obj):
        """Test using custom object attribute name."""
        # Setup
        mock_permission = Mock(spec=["permission_type", "save"])

        with (
            patch(
                "gift_manager.services.PermissionService.get_permission_model",
                return_value=PersonPermission,
            ),
            patch.object(
                PersonPermission.objects, "get_or_create", return_value=(mock_permission, True)
            ) as mock_get_or_create,
        ):
            # Execute
            result = create_or_update_permission(mock_user, mock_obj, object_attr="custom_attr")

            # Verify
            mock_get_or_create.assert_called_once_with(
                user=mock_user,
                custom_attr=mock_obj,
                defaults={"permission_type": PermissionLevel.VIEWER},
            )
            assert result == mock_permission

    def test_create_permission_no_model(self, mock_user, mock_obj):
        """Test that ValueError is raised when no permission model is found."""
        # Setup and execution
        with (
            patch(
                "gift_manager.services.PermissionService.get_permission_model", return_value=None
            ),
            pytest.raises(
                ValueError, match="Could not determine permission model for this object type"
            ),
        ):
            # Execute
            create_or_update_permission(mock_user, mock_obj)

    def test_user_already_in_shared_with(self, mock_user, mock_obj):
        """Test that shared_with.add isn't called if user is already in shared_with."""
        # Setup
        mock_permission = Mock()
        mock_obj.shared_with.all.return_value = [mock_user]

        with (
            patch(
                "gift_manager.services.PermissionService.get_permission_model",
                return_value=PersonPermission,
            ),
            patch.object(
                PersonPermission.objects, "get_or_create", return_value=(mock_permission, True)
            ),
        ):
            # Execute
            result = create_or_update_permission(mock_user, mock_obj)

            # Verify
            mock_obj.shared_with.add.assert_not_called()
            assert result == mock_permission

    def test_object_without_shared_with(self, mock_user):
        """Test creating permission for object without shared_with attribute."""
        # Setup
        mock_obj_no_sharing = Mock(spec=["__class__"])
        mock_obj_no_sharing.__class__ = Person
        mock_obj_no_sharing.__class__.__name__ = "Person"
        mock_permission = Mock()

        with (
            patch(
                "gift_manager.services.PermissionService.get_permission_model",
                return_value=PersonPermission,
            ),
            patch.object(
                PersonPermission.objects, "get_or_create", return_value=(mock_permission, True)
            ),
        ):
            # Execute
            result = create_or_update_permission(mock_user, mock_obj_no_sharing)

            # Verify
            assert result == mock_permission
            # No error is raised despite lack of shared_with


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
            patch(
                "gift_manager.services.PermissionService.get_permission_model",
                return_value=PersonPermission,
            ),
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
            patch(
                "gift_manager.services.PermissionService.get_permission_model",
                return_value=PersonPermission,
            ),
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
        # Setup and execution
        with (
            patch(
                "gift_manager.services.PermissionService.get_permission_model", return_value=None
            ),
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
            patch(
                "gift_manager.services.PermissionService.get_permission_model",
                return_value=PersonPermission,
            ),
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
            patch(
                "gift_manager.services.PermissionService.get_permission_model",
                return_value=PersonPermission,
            ),
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
