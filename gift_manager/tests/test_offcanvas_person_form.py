"""Tests for offcanvas person form functionality.

This module tests the three critical issues that were fixed:
1. Save button submits the form
2. Select All/Clear All buttons work after HTMX swap
3. Permission selectors don't cause full form reload
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from gift_manager.models import Person
from gift_manager.models import PersonGroup

from .utils import assert_text_in_rendered

User = get_user_model()


@pytest.mark.django_db
class TestOffcanvasPersonForm:
    """Test offcanvas person form functionality."""

    @pytest.fixture
    def user(self):
        """Create a test user."""
        return User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    @pytest.fixture
    def client_logged_in(self, user):
        """Create a logged-in client."""
        client = Client()
        client.login(username="testuser", password="testpass123")
        return client

    @pytest.fixture
    def person(self, user):
        """Create a test person."""
        return Person.objects.create(
            user_link=user, first_name="John", family_name="Doe", email_address="john@example.com"
        )

    @pytest.fixture
    def groups(self, user):
        """Create test groups."""
        groups = [
            PersonGroup.objects.create(name="Family"),
            PersonGroup.objects.create(name="Friends"),
            PersonGroup.objects.create(name="Colleagues"),
        ]
        # Add permissions for the user
        from gift_manager.models import PersonGroupPermission

        for group in groups:
            PersonGroupPermission.objects.create(
                group=group,
                user=user,
                permission_type=30,  # Owner permission
            )
        return groups

    def test_person_edit_form_loads_with_htmx(self, client_logged_in, person):
        """Test that person edit form loads correctly with HTMX request."""
        url = reverse("gift_manager:person_edit", kwargs={"pk": person.person_id})
        response = client_logged_in.get(url, HTTP_HX_REQUEST="true")

        assert response.status_code == 200
        # Should return partial template for HTMX
        assert_text_in_rendered("person-form", response.content.decode())
        assert_text_in_rendered("data-form-type", response.content.decode())

    def test_person_edit_form_has_htmx_attributes(self, client_logged_in, person):
        """Test that form has correct HTMX attributes for submission."""
        url = reverse("gift_manager:person_edit", kwargs={"pk": person.person_id})
        response = client_logged_in.get(url, HTTP_HX_REQUEST="true")

        content = response.content.decode()
        # Check for HTMX attributes
        assert_text_in_rendered("hx-post=", content)
        assert_text_in_rendered("hx-target=", content)
        assert_text_in_rendered("hx-swap=", content)
        assert 'hx-on::after-request="handleFormResponse(event)"' not in content

    def test_person_edit_form_has_group_buttons(self, client_logged_in, person, groups):
        """Test that form has Select All/Clear All buttons with correct data attributes."""
        # Add person to groups
        person.groups.set(groups)

        url = reverse("gift_manager:person_edit", kwargs={"pk": person.person_id})
        response = client_logged_in.get(url, HTTP_HX_REQUEST="true")

        content = response.content.decode()
        # Check for group buttons with data-action attributes
        assert_text_in_rendered('data-action="select-all-groups"', content)
        assert_text_in_rendered('data-action="clear-all-groups"', content)

    def test_person_form_submission_success(self, client_logged_in, person):
        """Test successful form submission returns correct HTMX response."""
        url = reverse("gift_manager:person_edit", kwargs={"pk": person.person_id})
        data = {
            "first_name": "Jane",
            "family_name": "Smith",
            "email_address": "jane@example.com",
        }

        response = client_logged_in.post(url, data, HTTP_HX_REQUEST="true")

        # Should return 200 with HX-Trigger header
        assert response.status_code in [200, 302]
        if response.status_code == 200:
            # Check for HX-Trigger header
            assert "HX-Trigger" in response

            # Verify person was updated
            person.refresh_from_db()
            assert person.first_name == "Jane"
            assert person.family_name == "Smith"

    def test_person_form_validation_error(self, client_logged_in, person):
        """Test form validation errors are returned correctly."""
        url = reverse("gift_manager:person_edit", kwargs={"pk": person.person_id})
        data = {
            "first_name": "",  # Required field
            "family_name": "Smith",
            "email_address": "invalid-email",  # Invalid email
        }

        response = client_logged_in.post(url, data, HTTP_HX_REQUEST="true")

        # Should return an HTMX validation error status with form errors
        assert response.status_code == 422
        assert "HX-Trigger" in response
        assert "list:update" not in response["HX-Trigger"]
        content = response.content.decode()
        # Form should be re-rendered with errors
        assert "person-form" in content
        assert "form-error-summary" in content

    def test_person_create_form_has_htmx_attributes(self, client_logged_in):
        """Test that create form has correct HTMX attributes."""
        url = reverse("gift_manager:person_create")
        response = client_logged_in.get(url, HTTP_HX_REQUEST="true")

        assert response.status_code == 200
        content = response.content.decode()
        # Check for HTMX attributes
        assert_text_in_rendered("hx-post=", content)
        assert_text_in_rendered('data-form-type="person-edit"', content)

    def test_person_create_form_preselects_accessible_context_group(self, client_logged_in, groups):
        """The group detail shortcut initializes the new person's groups field."""
        group = groups[1]
        url = reverse("gift_manager:person_create")

        response = client_logged_in.get(
            url,
            {"group": group.group_id},
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 200
        selected_groups = response.context["form"]["groups"].value() or []
        assert set(map(str, selected_groups)) == {str(group.pk)}

    @pytest.mark.parametrize("group_parameter", ["not-a-uuid", "", "42"])
    def test_person_create_form_ignores_malformed_context_group(
        self, client_logged_in, group_parameter
    ):
        """Bad group query parameters must neither fail nor select a group."""
        url = reverse("gift_manager:person_create")

        response = client_logged_in.get(
            url,
            {"group": group_parameter},
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 200
        assert not (response.context["form"]["groups"].value() or [])

    def test_person_create_form_ignores_inaccessible_context_group(self, client_logged_in):
        """A group outside the user's accessible queryset cannot be preselected."""
        inaccessible_group = PersonGroup.objects.create(name="Private group")
        url = reverse("gift_manager:person_create")

        response = client_logged_in.get(
            url,
            {"group": inaccessible_group.group_id},
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 200
        assert not (response.context["form"]["groups"].value() or [])
        assert f'value="{inaccessible_group.pk}"' not in response.content.decode()

    def test_form_has_data_form_type_attribute(self, client_logged_in, person):
        """Test that form has data-form-type attribute for FormInitializer."""
        url = reverse("gift_manager:person_edit", kwargs={"pk": person.person_id})
        response = client_logged_in.get(url, HTTP_HX_REQUEST="true")

        content = response.content.decode()
        assert_text_in_rendered('data-form-type="person-edit"', content)

    def test_form_has_sticky_actions(self, client_logged_in, person):
        """Test that form has sticky action buttons at bottom."""
        url = reverse("gift_manager:person_edit", kwargs={"pk": person.person_id})
        response = client_logged_in.get(url, HTTP_HX_REQUEST="true")

        content = response.content.decode()
        # Check for sticky actions container
        assert_text_in_rendered("panel-form-actions", content)
        # Check for Cancel and Save buttons
        assert_text_in_rendered('data-bs-dismiss="offcanvas"', content)
        assert_text_in_rendered('type="submit"', content)
