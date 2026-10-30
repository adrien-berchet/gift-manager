"""Tests for group gift view endpoints, forms, and HTMX partial rendering."""

from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from gift_manager.forms import GroupGiftContributorForm
from gift_manager.forms import GroupGiftCustomAmountForm
from gift_manager.models import PermissionLevel
from gift_manager.models import Relation
from gift_manager.models import RelationContribution
from gift_manager.models import SplitMode
from gift_manager.services import PermissionService
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

HX = {"HTTP_HX_REQUEST": "true"}


def _befriend(first: User, second: User) -> None:
    first.profile.friends.add(second.profile)


def _share(obj, user: User, level: int = PermissionLevel.OWNER, attr: str | None = None) -> None:
    PermissionService.create_or_update_permission(
        user, obj, permission_level=level, object_attr=attr
    )


@pytest.fixture
def owner() -> User:
    return UserFactory(username="plan_owner")


@pytest.fixture
def editor(owner) -> User:
    user = UserFactory(username="plan_editor")
    _befriend(owner, user)
    return user


@pytest.fixture
def viewer(owner) -> User:
    user = UserFactory(username="plan_viewer")
    _befriend(owner, user)
    return user


@pytest.fixture
def recipient(owner) -> User:
    user = UserFactory(username="plan_recipient")
    _befriend(owner, user)
    return user


@pytest.fixture
def relation(owner, editor, viewer, recipient) -> Relation:
    person = PersonFactory(account=recipient)
    _share(person, owner, PermissionLevel.OWNER)

    rel = RelationFactory(
        person=person,
        group=None,
        price=Decimal("120.00"),
        is_surprise=False,
        is_group_gift=False,
        split_mode=SplitMode.EQUAL,
    )
    _share(rel, owner, PermissionLevel.OWNER, "relation")
    _share(rel, editor, PermissionLevel.EDITOR, "relation")
    _share(rel, viewer, PermissionLevel.VIEWER, "relation")
    _share(rel, recipient, PermissionLevel.VIEWER, "relation")
    return rel


# --- Form Tests --------------------------------------------------------------------------------


def test_contributor_form_validation(relation, editor, recipient):
    # Neither user nor name -> error
    form = GroupGiftContributorForm(data={}, relation=relation)
    assert not form.is_valid()

    # Both user and name -> error
    form = GroupGiftContributorForm(
        data={"user": editor.pk, "name": "Uncle Bob"}, relation=relation
    )
    assert not form.is_valid()

    # Valid with user
    form = GroupGiftContributorForm(data={"user": editor.pk}, relation=relation)
    assert form.is_valid()
    assert form.cleaned_data["user"] == editor

    # Valid with name
    form = GroupGiftContributorForm(data={"name": "Uncle Bob"}, relation=relation)
    assert form.is_valid()
    assert form.cleaned_data["name"] == "Uncle Bob"

    # Recipient rejected
    form = GroupGiftContributorForm(data={"user": recipient.pk}, relation=relation)
    assert not form.is_valid()


def test_custom_amount_form_validation():
    # Valid positive amount
    form = GroupGiftCustomAmountForm(data={"amount": "45.50"})
    assert form.is_valid()
    assert form.cleaned_data["amount"] == Decimal("45.50")

    # Negative amount -> error
    form = GroupGiftCustomAmountForm(data={"amount": "-10.00"})
    assert not form.is_valid()


# --- View Endpoint Tests -----------------------------------------------------------------------


def test_enable_disable_group_gift_htmx_and_redirect(client, relation, editor):
    client.force_login(editor)
    toggle_url = reverse(
        "gift_manager:relation_group_gift_toggle", kwargs={"pk": relation.relation_id}
    )

    # Enable via HTMX
    res = client.post(toggle_url, data={"action": "enable"}, **HX)
    assert res.status_code == 200
    content = res.content.decode()
    assert 'id="relation-group-gift"' in content
    assert "<html" not in content
    relation.refresh_from_db()
    assert relation.is_group_gift is True

    # Disable via plain POST -> 302 redirect
    res = client.post(toggle_url, data={"action": "disable"})
    assert res.status_code == 302
    assert res.url.endswith("#relation-group-gift")
    relation.refresh_from_db()
    assert relation.is_group_gift is False


def test_switch_split_mode_htmx(client, relation, editor):
    relation.is_group_gift = True
    relation.save()
    client.force_login(editor)
    mode_url = reverse("gift_manager:relation_group_gift_mode", kwargs={"pk": relation.relation_id})

    # Switch to custom
    res = client.post(mode_url, data={"split_mode": "custom"}, **HX)
    assert res.status_code == 200
    relation.refresh_from_db()
    assert relation.split_mode == SplitMode.CUSTOM

    # Invalid mode -> 422
    res = client.post(mode_url, data={"split_mode": "invalid_mode"}, **HX)
    assert res.status_code == 422


def test_add_contributor_user_and_external(client, relation, editor):
    relation.is_group_gift = True
    relation.save()
    client.force_login(editor)
    add_url = reverse(
        "gift_manager:relation_group_gift_contributor_add", kwargs={"pk": relation.relation_id}
    )

    # Add collaborator
    res = client.post(add_url, data={"user": editor.pk}, **HX)
    assert res.status_code == 200
    assert relation.contributions.filter(user=editor).exists()

    # Add external person
    res = client.post(add_url, data={"name": "Aunt Sarah"}, **HX)
    assert res.status_code == 200
    assert relation.contributions.filter(name="Aunt Sarah").exists()

    # Invalid add (both user and name) -> 422
    res = client.post(add_url, data={"user": editor.pk, "name": "Duplicate"}, **HX)
    assert res.status_code == 422


def test_remove_contributor_htmx(client, relation, editor):
    relation.is_group_gift = True
    relation.save()
    contrib = RelationContribution.objects.create(
        relation=relation, name="Removable", amount=Decimal("10.00")
    )
    client.force_login(editor)
    remove_url = reverse(
        "gift_manager:relation_group_gift_contributor_remove",
        kwargs={"pk": relation.relation_id, "contribution_id": contrib.pk},
    )

    # First remove -> 200
    res = client.post(remove_url, **HX)
    assert res.status_code == 200
    assert not RelationContribution.objects.filter(pk=contrib.pk).exists()

    # Second remove -> idempotent 200
    res2 = client.post(remove_url, **HX)
    assert res2.status_code == 200


def test_toggle_paid_htmx(client, relation, editor):
    relation.is_group_gift = True
    relation.save()
    contrib = RelationContribution.objects.create(
        relation=relation, name="Payer", amount=Decimal("60.00")
    )
    client.force_login(editor)
    toggle_url = reverse(
        "gift_manager:relation_group_gift_contributor_toggle_paid",
        kwargs={"pk": relation.relation_id, "contribution_id": contrib.pk},
    )

    # Mark paid
    res = client.post(toggle_url, **HX)
    assert res.status_code == 200
    contrib.refresh_from_db()
    assert contrib.is_paid is True
    assert contrib.paid_at is not None

    # Mark unpaid
    res = client.post(toggle_url, **HX)
    assert res.status_code == 200
    contrib.refresh_from_db()
    assert contrib.is_paid is False


def test_update_custom_amount_htmx(client, relation, editor):
    relation.is_group_gift = True
    relation.split_mode = SplitMode.CUSTOM
    relation.save()
    contrib = RelationContribution.objects.create(
        relation=relation, name="Custom Contributor", amount=Decimal("30.00")
    )
    client.force_login(editor)
    amount_url = reverse(
        "gift_manager:relation_group_gift_contributor_amount",
        kwargs={"pk": relation.relation_id, "contribution_id": contrib.pk},
    )

    res = client.post(amount_url, data={"amount": "55.00"}, **HX)
    assert res.status_code == 200
    contrib.refresh_from_db()
    assert contrib.amount == Decimal("55.00")

    # Negative amount -> 422
    res_bad = client.post(amount_url, data={"amount": "-5.00"}, **HX)
    assert res_bad.status_code == 422


def test_plan_detail_renders_group_gift_card_for_collaborators(client, relation, editor):
    relation.is_group_gift = True
    relation.save()
    RelationContribution.objects.create(
        relation=relation,
        name="Uncle Dave",
        amount=Decimal("40.00"),
        is_paid=True,
        paid_at=timezone.now(),
    )
    client.force_login(editor)
    detail_url = reverse("gift_manager:relation_detail", kwargs={"pk": relation.relation_id})

    res = client.get(detail_url)
    assert res.status_code == 200
    content = res.content.decode()
    assert 'id="relation-group-gift"' in content
    assert "Uncle Dave" in content
    assert "progressbar" in content


def test_permissions_and_methods(client, relation, viewer):
    toggle_url = reverse(
        "gift_manager:relation_group_gift_toggle", kwargs={"pk": relation.relation_id}
    )

    # GET -> 405 Method Not Allowed
    client.force_login(viewer)
    res_get = client.get(toggle_url)
    assert res_get.status_code == 405

    # Viewer cannot toggle (needs editor) -> 403
    res_viewer = client.post(toggle_url, data={"action": "enable"})
    assert res_viewer.status_code == 403

    # Anonymous -> 302 to login
    client.logout()
    res_anon = client.post(toggle_url, data={"action": "enable"})
    assert res_anon.status_code == 302
    assert "/login" in res_anon.url or "/accounts/login" in res_anon.url
