"""A new gift plan may name a gift that does not exist yet: the plan creates it (Q2)."""

import pytest
from django.urls import reverse

from gift_manager.forms import GiftRelationForm
from gift_manager.forms import PersonRelationForm
from gift_manager.forms import RelationForm
from gift_manager.models import Gift
from gift_manager.models import PermissionLevel
from gift_manager.models import Relation
from gift_manager.services import PermissionService
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import RelationStatusFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(client):
    user = UserFactory(username="giver")
    client.force_login(user)
    return user


@pytest.fixture
def person(user):
    person = PersonFactory(first_name="Ada", family_name="Lovelace")
    PermissionService.create_or_update_permission(
        user, person, permission_level=PermissionLevel.OWNER
    )
    return person


@pytest.fixture
def status():
    return RelationStatusFactory(status="Idea")


def _data(person, status, **extra):
    return {"recipient": f"person:{person.person_id}", "status": status.pk, **extra}


class TestRelationForm:
    def test_a_new_gift_name_creates_the_gift_owned_by_the_user(self, user, person, status):
        form = RelationForm(_data(person, status, new_gift_name="  Telescope "), user=user)

        assert form.is_valid(), form.errors
        plan = form.save()

        gift = Gift.objects.get(name="Telescope")
        assert plan.gift == gift
        assert PermissionService.get_permission(gift, user) == PermissionLevel.OWNER

    def test_an_existing_gift_still_works_and_creates_nothing(self, user, person, status):
        gift = GiftFactory(name="Book", shared_with=[user])

        form = RelationForm(_data(person, status, gift=gift.pk), user=user)

        assert form.is_valid(), form.errors
        assert form.save().gift == gift
        assert Gift.objects.count() == 1

    def test_a_gift_is_required_one_way_or_the_other(self, user, person, status):
        form = RelationForm(_data(person, status, new_gift_name="   "), user=user)

        assert not form.is_valid()
        assert form.errors["gift"] == ["Choose a gift or name a new one."]

    def test_choosing_a_gift_and_naming_a_new_one_is_refused(self, user, person, status):
        gift = GiftFactory(name="Book", shared_with=[user])

        form = RelationForm(
            _data(person, status, gift=gift.pk, new_gift_name="Telescope"), user=user
        )

        assert not form.is_valid()
        assert form.errors["new_gift_name"] == [
            "Choose an existing gift or name a new one, not both."
        ]
        assert not Gift.objects.filter(name="Telescope").exists()

    def test_an_invalid_plan_creates_no_gift(self, user):
        form = RelationForm(
            {
                "recipient": "person:00000000-0000-0000-0000-000000000000",
                "new_gift_name": "Telescope",
            },
            user=user,
        )

        assert not form.is_valid()
        assert not Gift.objects.exists()

    def test_editing_a_plan_does_not_offer_a_new_gift(self, user, person, status):
        plan = RelationFactory(
            person=person, gift=GiftFactory(shared_with=[user]), status=status, shared_with=[user]
        )

        form = RelationForm(instance=plan, user=user)

        assert "new_gift_name" not in form.fields
        assert form.fields["gift"].required

    def test_forms_bound_to_a_recipient_offer_it_too(self, user, person, status):
        form = PersonRelationForm(
            {"status": status.pk, "new_gift_name": "Telescope"},
            user=user,
            person_id=person.person_id,
        )

        assert form.is_valid(), form.errors
        assert form.save().gift.name == "Telescope"

    def test_a_plan_created_from_a_gift_keeps_that_gift(self, user):
        assert "new_gift_name" not in GiftRelationForm(user=user).fields


class TestCreateView:
    def test_page_offers_to_name_a_new_gift(self, client, user, person, status):
        content = client.get(reverse("gift_manager:relation_create")).content.decode()

        assert 'name="new_gift_name"' in content

    def test_post_creates_the_plan_and_its_gift(self, client, user, person, status):
        response = client.post(
            reverse("gift_manager:relation_create"),
            _data(person, status, new_gift_name="Telescope"),
        )

        assert response.status_code == 302, response.content.decode()[:500]
        plan = Relation.objects.get()
        assert plan.gift.name == "Telescope"
        assert plan.person == person
        assert PermissionService.get_permission(plan.gift, user) == PermissionLevel.OWNER

    def test_sharing_the_plan_shares_its_new_gift(self, client, user, person, status):
        friend = UserFactory(username="friend")
        user.profile.friends.add(friend.profile)

        response = client.post(
            reverse("gift_manager:relation_create"),
            _data(
                person,
                status,
                new_gift_name="Telescope",
                **{f"share_with_{friend.pk}": PermissionLevel.VIEWER},
            ),
        )

        assert response.status_code == 302, response.content.decode()[:500]
        gift = Gift.objects.get(name="Telescope")
        assert PermissionService.get_permission(gift, friend) == PermissionLevel.VIEWER

    def test_person_page_form_creates_the_gift(self, client, user, person, status):
        url = reverse("gift_manager:person_relation_create", kwargs={"pk": person.person_id})
        assert 'name="new_gift_name"' in client.get(url).content.decode()

        response = client.post(url, {"status": status.pk, "new_gift_name": "Telescope"})

        assert response.status_code == 302, response.content.decode()[:500]
        assert Relation.objects.get().gift.name == "Telescope"

    def test_edit_page_has_no_new_gift_field(self, client, user, person, status):
        plan = RelationFactory(
            person=person, gift=GiftFactory(shared_with=[user]), status=status, shared_with=[user]
        )
        PermissionService.create_or_update_permission(
            user, plan, permission_level=PermissionLevel.OWNER
        )

        content = client.get(
            reverse("gift_manager:relation_edit", kwargs={"pk": plan.relation_id})
        ).content.decode()

        assert 'name="new_gift_name"' not in content
