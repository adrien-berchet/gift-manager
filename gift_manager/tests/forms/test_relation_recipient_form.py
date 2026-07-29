import pytest
from django.urls import reverse

from gift_manager.forms import GiftRelationForm
from gift_manager.forms import RelationForm
from gift_manager.models import Relation
from gift_manager.permissions import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import RelationStatusFactory
from gift_manager.tests.factories import UserFactory


def relation_form_data(*, recipient, gift, status, **overrides):
    data = {
        "recipient": recipient,
        "gift": str(gift.pk),
        "comment": "Maybe for the next occasion",
        "event": "",
        "status": str(status.pk),
        "due_date": "",
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_relation_form_maps_person_recipient_to_person_field():
    user = UserFactory()
    person = PersonFactory(first_name="Ada", family_name="Lovelace", shared_with=[user])
    gift = GiftFactory()
    status = RelationStatusFactory(status="Idea")

    form = RelationForm(
        data=relation_form_data(
            recipient=f"person:{person.person_id}",
            gift=gift,
            status=status,
        ),
        user=user,
    )

    assert form.is_valid(), form.errors
    assert form.instance.person == person
    assert form.instance.group is None


@pytest.mark.django_db
def test_relation_form_maps_group_recipient_to_group_field():
    user = UserFactory()
    group = PersonGroupFactory(name="Family", shared_with=[user])
    gift = GiftFactory()
    status = RelationStatusFactory(status="Idea")

    form = RelationForm(
        data=relation_form_data(
            recipient=f"group:{group.group_id}",
            gift=gift,
            status=status,
        ),
        user=user,
    )

    assert form.is_valid(), form.errors
    assert form.instance.person is None
    assert form.instance.group == group


@pytest.mark.django_db
def test_gift_relation_form_uses_single_recipient_control_for_groups():
    user = UserFactory()
    group = PersonGroupFactory(name="Friends", shared_with=[user])
    gift = GiftFactory(shared_with=[user])
    status = RelationStatusFactory(status="Idea")

    form = GiftRelationForm(
        data={
            "recipient": f"group:{group.group_id}",
            "comment": "",
            "event": "",
            "status": str(status.pk),
            "due_date": "",
        },
        gift_id=gift.gift_id,
        user=user,
    )

    assert form.is_valid(), form.errors
    assert form.instance.gift == gift
    assert form.instance.person is None
    assert form.instance.group == group


@pytest.mark.django_db
def test_gift_relation_create_rejects_inaccessible_url_gift(client):
    user = UserFactory()
    client.force_login(user)
    person = PersonFactory(first_name="Ada", family_name="Lovelace", shared_with=[user])
    private_gift = GiftFactory(name="Private gift")
    status = RelationStatusFactory(status="Idea")

    response = client.post(
        reverse("gift_manager:gift_relation_create", kwargs={"pk": private_gift.gift_id}),
        {
            "recipient": f"person:{person.person_id}",
            "comment": "",
            "event": "",
            "status": str(status.pk),
            "due_date": "",
        },
    )

    assert response.status_code == 200
    assert not Relation.objects.filter(gift=private_gift).exists()
    assert "The specified gift does not exist." in response.content.decode("utf-8")


@pytest.mark.django_db
def test_relation_form_rejects_inaccessible_recipient():
    user = UserFactory()
    private_person = PersonFactory(first_name="Private", family_name="Person")
    gift = GiftFactory()
    status = RelationStatusFactory(status="Idea")

    form = RelationForm(
        data=relation_form_data(
            recipient=f"person:{private_person.person_id}",
            gift=gift,
            status=status,
        ),
        user=user,
    )

    assert not form.is_valid()
    assert "recipient" in form.errors


@pytest.mark.django_db
def test_relation_form_initializes_from_existing_recipient_key():
    user = UserFactory()
    group = PersonGroupFactory(name="Book Club", shared_with=[user])
    relation = RelationFactory(person=None, group=group)
    create_or_update_permission(user, relation, permission_level=PermissionLevel.OWNER)

    form = RelationForm(instance=relation, user=user)

    assert form.initial["recipient"] == f"group:{group.group_id}"
