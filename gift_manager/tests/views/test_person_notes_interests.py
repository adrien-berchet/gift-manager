"""Tests for person notes, interests and interest-based gift suggestions."""

import pytest
from django.test import Client
from django.urls import reverse

from gift_manager.forms import PersonForm
from gift_manager.interests import gifts_matching_interests
from gift_manager.models import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import GiftTagFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import UserFactory


def _share(user, obj, level=PermissionLevel.EDITOR):
    create_or_update_permission(user, obj, permission_level=level)


@pytest.fixture
def user():
    return UserFactory()


@pytest.fixture
def client(user):
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def person(user):
    person = PersonFactory()
    _share(user, person)
    return person


def _form(user, person=None, **data):
    payload = {"first_name": "Anna", "family_name": "Smith", **data}
    return PersonForm(payload, instance=person, user=user)


@pytest.mark.django_db
class TestPersonForm:
    def test_notes_and_interests_are_saved(self, user):
        tag = GiftTagFactory(name="Kayaking", shared_with=[user])

        form = _form(user, notes="Allergic to nuts", interests=[tag.pk])

        assert form.is_valid(), form.errors
        saved = form.save()
        assert saved.notes == "Allergic to nuts"
        assert list(saved.interests.all()) == [tag]

    def test_overlong_notes_are_rejected(self, user):
        form = _form(user, notes="x" * 5001)

        assert not form.is_valid()
        assert "notes" in form.errors

    def test_inaccessible_tags_are_rejected(self, user):
        tag = GiftTagFactory(name="Not mine")

        form = _form(user, interests=[tag.pk])

        assert not form.is_valid()
        assert "interests" in form.errors

    def test_hidden_interests_survive_an_edit(self, user, person):
        hidden = GiftTagFactory(name="Hidden")
        visible = GiftTagFactory(name="Visible", shared_with=[user])
        person.interests.add(hidden, visible)

        form = _form(user, person, interests=[])

        assert form.is_valid(), form.errors
        form.save()
        assert list(person.interests.all()) == [hidden]

    def test_both_form_variants_render_the_fields(self, client, person):
        url = reverse("gift_manager:person_edit", kwargs={"pk": person.person_id})

        for extra in ({}, {"HTTP_HX_REQUEST": "true"}):
            content = client.get(url, **extra).content.decode()
            assert 'name="notes"' in content
            assert 'name="interests"' in content


@pytest.mark.django_db
class TestPersonDetail:
    def detail(self, client, person):
        return client.get(
            reverse("gift_manager:person_detail", kwargs={"pk": person.person_id})
        ).content.decode()

    def test_notes_and_visible_interests_are_shown(self, client, user, person):
        person.notes = "Prefers books"
        person.save()
        person.interests.add(
            GiftTagFactory(name="Hiking", shared_with=[user]), GiftTagFactory(name="Secret tag")
        )

        content = self.detail(client, person)

        assert "Prefers books" in content
        assert "Hiking" in content
        assert "Secret tag" not in content

    def test_notes_are_not_readable_without_access(self, client):
        person = PersonFactory(notes="Private note")

        response = client.get(
            reverse("gift_manager:person_detail", kwargs={"pk": person.person_id})
        )

        assert response.status_code in (403, 404)
        assert "Private note" not in response.content.decode()


@pytest.mark.django_db
class TestInterestMatching:
    @pytest.fixture(autouse=True)
    def setup(self, user, person):
        self.user = user
        self.person = person
        self.tag = GiftTagFactory(name="Outdoor", shared_with=[user])
        person.interests.add(self.tag)

    def test_orders_by_shared_tags(self):
        other_tag = GiftTagFactory(name="Water", shared_with=[self.user])
        self.person.interests.add(other_tag)
        one = GiftFactory(name="Tent", tags=[self.tag], shared_with=[self.user])
        two = GiftFactory(name="Kayak", tags=[self.tag, other_tag], shared_with=[self.user])
        GiftFactory(name="Unrelated", shared_with=[self.user])

        assert gifts_matching_interests(self.user, self.person) == [two, one]

    def test_skips_gifts_already_planned_for_the_person(self):
        gift = GiftFactory(name="Tent", tags=[self.tag], shared_with=[self.user])
        RelationFactory(person=self.person, gift=gift, shared_with=[self.user])

        assert gifts_matching_interests(self.user, self.person) == []

    def test_ignores_gifts_the_user_cannot_access(self):
        GiftFactory(name="Hidden gift", tags=[self.tag])

        assert gifts_matching_interests(self.user, self.person) == []

    def test_hint_endpoint_lists_matching_gifts(self, client):
        gift = GiftFactory(name="Tent", tags=[self.tag], shared_with=[self.user])

        content = client.get(
            reverse("gift_manager:repeat_gift_hint"),
            {"recipient": f"person:{self.person.person_id}"},
        ).content.decode()

        assert "data-interest-suggestions" in content
        assert f'data-suggest-gift="{gift.pk}"' in content

    def test_plans_hidden_from_the_viewer_do_not_exclude_a_gift(self):
        gift = GiftFactory(name="Tent", tags=[self.tag], shared_with=[self.user])
        RelationFactory(person=self.person, gift=gift)  # not shared with the viewer

        assert gifts_matching_interests(self.user, self.person) == [gift]

    def test_inaccessible_interest_tags_do_not_match(self):
        secret = GiftTagFactory(name="Secret")
        self.person.interests.set([secret])
        GiftFactory(name="Hidden match", tags=[secret], shared_with=[self.user])

        assert gifts_matching_interests(self.user, self.person) == []
