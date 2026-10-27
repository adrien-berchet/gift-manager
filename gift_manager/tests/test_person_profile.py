"""Tests for person profile promotion domain helpers."""

from datetime import date
from unittest.mock import patch

import pytest

from gift_manager.models import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.person_profile import append_person_provenance_note
from gift_manager.person_profile import promote_tags_to_person_interests
from gift_manager.person_profile import promotion_target
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import GiftTagFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import UserFactory


def share(user, obj, level=PermissionLevel.EDITOR):
    return create_or_update_permission(user, obj, permission_level=level)


@pytest.mark.django_db
def test_promotion_target_guards_surprise_plans(user):
    person = PersonFactory()
    share(user, person, level=PermissionLevel.EDITOR)
    gift = GiftFactory()
    share(user, gift, level=PermissionLevel.EDITOR)

    # Normal relation
    normal_rel = RelationFactory(person=person, gift=gift, is_surprise=False)
    share(user, normal_rel, level=PermissionLevel.EDITOR)
    assert promotion_target(user, normal_rel) == person

    # Surprise relation must never promote to person profile
    surprise_rel = RelationFactory(person=person, gift=gift, is_surprise=True)
    share(user, surprise_rel, level=PermissionLevel.EDITOR)
    assert promotion_target(user, surprise_rel) is None


@pytest.mark.django_db
def test_promotion_target_guards_groups_and_viewer_permissions(user):
    group = PersonGroupFactory()
    share(user, group, level=PermissionLevel.OWNER)
    # Target is a group -> None
    assert promotion_target(user, group) is None

    person = PersonFactory()
    # Read-only viewer permissions on person -> None
    share(user, person, level=PermissionLevel.VIEWER)
    assert promotion_target(user, person) is None

    # Relation for group -> None
    gift = GiftFactory()
    share(user, gift, level=PermissionLevel.EDITOR)
    rel_group = RelationFactory(group=group, person=None, gift=gift)
    share(user, rel_group, level=PermissionLevel.EDITOR)
    assert promotion_target(user, rel_group) is None


@pytest.mark.django_db
def test_promotion_target_returns_person_when_editor(user):
    person = PersonFactory()
    share(user, person, level=PermissionLevel.EDITOR)
    assert promotion_target(user, person) == person

    owner = UserFactory()
    owned_person = PersonFactory()
    share(owner, owned_person, level=PermissionLevel.OWNER)
    assert promotion_target(owner, owned_person) == owned_person


@pytest.mark.django_db
def test_append_person_provenance_note_formats_and_deduplicates():
    person = PersonFactory(notes="Initial notes about preferences.")
    today = date(2026, 10, 22)

    # First append succeeds
    success1 = append_person_provenance_note(
        person,
        source_label="Suggestion",
        item_name="  Coffee Grinder \n manual  ",
        text="A déjà un modèle similaire chez lui.",
        today=today,
    )
    assert success1 is True
    person.refresh_from_db()
    expected = (
        "Initial notes about preferences.\n"
        "[2026-10-22 - Suggestion: Coffee Grinder manual]: A déjà un modèle similaire chez lui."
    )
    assert person.notes == expected

    # Re-saving same note (e.g. repeated reaction save) deduplicates and does not append twice
    success2 = append_person_provenance_note(
        person,
        source_label="Suggestion",
        item_name="Coffee Grinder manual",
        text="A déjà un modèle similaire chez lui.",
        today=date(2026, 10, 23),  # Even with different date, signature matches
    )
    assert success2 is False
    person.refresh_from_db()
    assert person.notes.count("Coffee Grinder manual") == 1

    # Empty text returns False
    assert (
        append_person_provenance_note(
            person,
            source_label="Suggestion",
            item_name="Something",
            text="   ",
        )
        is False
    )


@pytest.mark.django_db
def test_append_person_provenance_note_uses_select_for_update():
    person = PersonFactory(notes="")

    with patch("gift_manager.person_profile.Person.objects.select_for_update") as mock_sfu:
        mock_sfu.return_value.get.return_value = person
        with patch.object(person, "save") as mock_save:
            res = append_person_provenance_note(
                person,
                source_label="Gift idea",
                item_name="Book",
                text="Loved it",
                today=date(2026, 10, 22),
            )
            assert res is True
            mock_sfu.assert_called_once()
            mock_save.assert_called_once_with(update_fields=["notes"])


@pytest.mark.django_db
def test_promote_tags_to_person_interests_skips_ancestors_and_limits(user):
    parent = GiftTagFactory(name="Literature")
    child = GiftTagFactory(name="Sci-Fi novels")
    child.parent_tags.add(parent)
    unrelated = GiftTagFactory(name="Woodworking")
    unshared = GiftTagFactory(name="Secret tag")

    for tag in (parent, child, unrelated):
        share(user, tag, level=PermissionLevel.VIEWER)

    person = PersonFactory()
    share(user, person, level=PermissionLevel.EDITOR)

    # Existing interest is child "Sci-Fi novels"
    person.interests.add(child)

    # If we promote parent "Literature", it should be skipped because child is already present!
    # "Secret tag" is unshared, so it should be skipped.
    # "Woodworking" should be added.
    tags_to_promote = [parent, child, unrelated, unshared]
    added_names = promote_tags_to_person_interests(person, tags_to_promote, user)

    assert added_names == ["Woodworking"]
    assert set(person.interests.values_list("name", flat=True)) == {"Sci-Fi novels", "Woodworking"}

    # Test limit of 5 tags
    new_tags = [GiftTagFactory(name=f"Hobby {i}") for i in range(10)]
    for t in new_tags:
        share(user, t, level=PermissionLevel.VIEWER)

    added_batch = promote_tags_to_person_interests(person, new_tags, user)
    assert len(added_batch) == 5
