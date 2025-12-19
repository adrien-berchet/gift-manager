from django.contrib.auth.models import User
from django.test import TestCase

from gift_manager.forms import PersonGroupForm
from gift_manager.models import PersonGroup
from gift_manager.permissions import PermissionLevel
from gift_manager.permissions import create_or_update_permission


class PersonGroupFormChildGroupsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="password")

        # Create hierarchy: G1 -> G2 -> G3
        self.g1 = PersonGroup.objects.create(name="Group 1")
        self.g2 = PersonGroup.objects.create(name="Group 2")
        self.g3 = PersonGroup.objects.create(name="Group 3")
        self.g4 = PersonGroup.objects.create(name="Group 4 (Independent)")

        self.g2.parent_groups.add(self.g1)
        self.g3.parent_groups.add(self.g2)

        # Grant permissions
        create_or_update_permission(self.user, self.g1, permission_level=PermissionLevel.EDITOR)
        create_or_update_permission(self.user, self.g2, permission_level=PermissionLevel.EDITOR)
        create_or_update_permission(self.user, self.g3, permission_level=PermissionLevel.EDITOR)
        create_or_update_permission(self.user, self.g4, permission_level=PermissionLevel.EDITOR)

    def test_form_fields_exist(self):
        form = PersonGroupForm(instance=self.g2, user=self.user)
        assert "child_groups" in form.fields
        assert "parent_groups" in form.fields

    def test_queryset_excludes_ancestors_for_child_groups(self):
        """When editing G2, available child groups should NOT include parent groups."""
        form = PersonGroupForm(instance=self.g2, user=self.user)
        queryset = form.fields["child_groups"].queryset

        assert self.g4 in queryset
        assert (
            self.g3 in queryset
        )  # G3 is already a child, should be in queryset to be pre-selected or kept
        assert self.g1 not in queryset  # G1 is ancestor, cannot be child (cycle G1->G2->G1)
        assert self.g2 not in queryset  # Self cannot be child

    def test_save_updates_child_groups(self):
        """Test adding a child group via the form."""
        # G2 currently has G3 as child. Let's add G4 as child of G2.
        data = {
            "name": "Group 2 Updated",
            "parent_groups": [self.g1.pk],
            "child_groups": [self.g3.pk, self.g4.pk],
            "persons": [],
        }
        form = PersonGroupForm(data=data, instance=self.g2, user=self.user)
        assert form.is_valid(), form.errors
        form.save()

        self.g2.refresh_from_db()
        assert self.g4 in self.g2.child_groups.all()
        assert self.g3 in self.g2.child_groups.all()
        # Check G4 parents
        assert self.g2 in self.g4.parent_groups.all()

    def test_cycle_validation_if_queryset_bypassed(self):
        """Force a cycle in data and check validation."""
        # Try to make G1 a child of G2 (G1 is already parent of G2, so cycle)
        # Bypassing queryset restriction by submitting ID directly
        data = {
            "name": "Group 2",
            "parent_groups": [self.g1.pk],
            "child_groups": [self.g1.pk],  # This should fail
        }
        form = PersonGroupForm(data=data, instance=self.g2, user=self.user)
        # We need to artificially allow G1 in the field's queryset for the form to even validate
        # the choice presence, otherwise it's just an "Select a valid choice" error.
        # But we want to test the `clean_child_groups` logic explicitly.
        # Use a form initialized without user (no filtering) or override queryset after init.

        # Override filtering for test purposes
        form.fields["child_groups"].queryset = PersonGroup.objects.all()

        assert not form.is_valid()
        assert "child_groups" in form.errors
        assert "create a cycle" in form.errors["child_groups"][0]

    def test_cannot_be_both_parent_and_child(self):
        """Test that a group cannot be selected as both parent and child."""
        # Try to set G4 as both parent and child of G2
        data = {
            "name": "Group 2",
            "parent_groups": [self.g4.pk],
            "child_groups": [self.g4.pk],
            "persons": [],
        }
        form = PersonGroupForm(data=data, instance=self.g2, user=self.user)

        assert not form.is_valid()
        # The error is a non-field error (raised in clean()), so it should be in __all__
        assert "__all__" in form.errors
        assert "cannot be both parent and child" in form.errors["__all__"][0]
        assert self.g4.name in form.errors["__all__"][0]

    def test_check_deep_cycle_simultaneous_add(self):
        """Test prevention of indirect cycles when adding parent and child simultaneously.

        Scenario:
        G1 -> G2 -> G3.
        We edit G4 (Independent).
        We set G2 as Parent of G4.
        We set G1 as Child of G4.
        Result if allowed: G4 -> G1 -> G2 -> G4 (Cycle).
        Here G1 (proposed child) is an ancestor of G2 (proposed parent).

        Note: G1 is ancestor of G2.
        """
        # Ensure hierarchy is as expected
        assert self.g1 in self.g2.get_ancestors()

        data = {
            "name": "Group 4",
            "parent_groups": [self.g2.pk],  # Parent is G2
            "child_groups": [self.g1.pk],  # Child is G1 (Ancestor of G2)
            "persons": [],
        }
        form = PersonGroupForm(data=data, instance=self.g4, user=self.user)

        assert not form.is_valid()
        assert "__all__" in form.errors
        error_msg = form.errors["__all__"][0]
        assert "Cycle: Group -> Child -> ... -> Parent -> Group" in error_msg
        assert self.g2.name in error_msg
        assert self.g1.name in error_msg
