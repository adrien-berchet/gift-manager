import pytest
from django.contrib.auth.models import User

from gift_manager.forms import PersonGroupForm
from gift_manager.models import PersonGroup
from gift_manager.permissions import PermissionLevel
from gift_manager.permissions import create_or_update_permission


@pytest.fixture
def group_setup(db):
    user = User.objects.create_user(username="testuser", password="password")

    # Create hierarchy: G1 -> G2 -> G3
    g1 = PersonGroup.objects.create(name="Group 1")
    g2 = PersonGroup.objects.create(name="Group 2")
    g3 = PersonGroup.objects.create(name="Group 3")
    g4 = PersonGroup.objects.create(name="Group 4 (Independent)")

    g2.parent_groups.add(g1)
    g3.parent_groups.add(g2)

    # Grant permissions
    create_or_update_permission(user, g1, permission_level=PermissionLevel.EDITOR)
    create_or_update_permission(user, g2, permission_level=PermissionLevel.EDITOR)
    create_or_update_permission(user, g3, permission_level=PermissionLevel.EDITOR)
    create_or_update_permission(user, g4, permission_level=PermissionLevel.EDITOR)

    return {
        "user": user,
        "g1": g1,
        "g2": g2,
        "g3": g3,
        "g4": g4,
    }


@pytest.mark.django_db
def test_form_fields_exist(group_setup):
    user = group_setup["user"]
    g2 = group_setup["g2"]
    form = PersonGroupForm(instance=g2, user=user)
    assert "child_groups" in form.fields
    assert "parent_groups" in form.fields


@pytest.mark.django_db
def test_queryset_excludes_ancestors_for_child_groups(group_setup):
    """When editing G2, available child groups should NOT include parent groups."""
    user = group_setup["user"]
    g1 = group_setup["g1"]
    g2 = group_setup["g2"]
    g3 = group_setup["g3"]
    g4 = group_setup["g4"]

    form = PersonGroupForm(instance=g2, user=user)
    queryset = form.fields["child_groups"].queryset

    assert g4 in queryset
    assert g3 in queryset  # G3 is already a child, should be in queryset to be pre-selected or kept
    assert g1 not in queryset  # G1 is ancestor, cannot be child (cycle G1->G2->G1)
    assert g2 not in queryset  # Self cannot be child


@pytest.mark.django_db
def test_save_updates_child_groups(group_setup):
    """Test adding a child group via the form."""
    user = group_setup["user"]
    g1 = group_setup["g1"]
    g2 = group_setup["g2"]
    g3 = group_setup["g3"]
    g4 = group_setup["g4"]

    # G2 currently has G3 as child. Let's add G4 as child of G2.
    data = {
        "name": "Group 2 Updated",
        "parent_groups": [g1.pk],
        "child_groups": [g3.pk, g4.pk],
        "persons": [],
    }
    form = PersonGroupForm(data=data, instance=g2, user=user)
    assert form.is_valid(), form.errors
    form.save()

    g2.refresh_from_db()
    assert g4 in g2.child_groups.all()
    assert g3 in g2.child_groups.all()
    # Check G4 parents
    assert g2 in g4.parent_groups.all()


@pytest.mark.django_db
def test_cycle_validation_if_queryset_bypassed(group_setup):
    """Force a cycle in data and check validation."""
    user = group_setup["user"]
    g1 = group_setup["g1"]
    g2 = group_setup["g2"]

    # Try to make G1 a child of G2 (G1 is already parent of G2, so cycle)
    # Bypassing queryset restriction by submitting ID directly
    data = {
        "name": "Group 2",
        "parent_groups": [g1.pk],
        "child_groups": [g1.pk],  # This should fail
    }
    form = PersonGroupForm(data=data, instance=g2, user=user)
    # We need to artificially allow G1 in the field's queryset for the form to even validate
    # the choice presence, otherwise it's just an "Select a valid choice" error.
    # But we want to test the `clean_child_groups` logic explicitly.
    # Use a form initialized without user (no filtering) or override queryset after init.

    # Override filtering for test purposes
    form.fields["child_groups"].queryset = PersonGroup.objects.all()

    assert not form.is_valid()
    assert "child_groups" in form.errors
    assert "create a cycle" in form.errors["child_groups"][0]


@pytest.mark.django_db
def test_cannot_be_both_parent_and_child(group_setup):
    """Test that a group cannot be selected as both parent and child."""
    user = group_setup["user"]
    g2 = group_setup["g2"]
    g4 = group_setup["g4"]

    # Try to set G4 as both parent and child of G2
    data = {
        "name": "Group 2",
        "parent_groups": [g4.pk],
        "child_groups": [g4.pk],
        "persons": [],
    }
    form = PersonGroupForm(data=data, instance=g2, user=user)

    assert not form.is_valid()
    # The error is a non-field error (raised in clean()), so it should be in __all__
    assert "__all__" in form.errors
    assert "cannot be both parent and child" in form.errors["__all__"][0]
    assert g4.name in form.errors["__all__"][0]


@pytest.mark.django_db
def test_check_deep_cycle_simultaneous_add(group_setup):
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
    user = group_setup["user"]
    g1 = group_setup["g1"]
    g2 = group_setup["g2"]
    g4 = group_setup["g4"]

    # Ensure hierarchy is as expected
    assert g1 in g2.get_ancestors()

    data = {
        "name": "Group 4",
        "parent_groups": [g2.pk],  # Parent is G2
        "child_groups": [g1.pk],  # Child is G1 (Ancestor of G2)
        "persons": [],
    }
    form = PersonGroupForm(data=data, instance=g4, user=user)

    assert not form.is_valid()
    assert "__all__" in form.errors
    error_msg = form.errors["__all__"][0]
    assert "Cycle: Group -> Child -> ... -> Parent -> Group" in error_msg
    assert g2.name in error_msg
    assert g1.name in error_msg
