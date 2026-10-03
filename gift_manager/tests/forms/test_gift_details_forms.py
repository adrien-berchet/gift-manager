"""Link and price fields of the gift and gift plan forms."""

import re
from decimal import Decimal

import pytest
from django.urls import reverse

from gift_manager.forms import GiftForm
from gift_manager.forms import GiftRelationForm
from gift_manager.forms import PersonGroupRelationForm
from gift_manager.forms import PersonRelationForm
from gift_manager.forms import RelationForm
from gift_manager.permissions import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

HOSTILE_URLS = ["javascript:alert(1)", "data:text/html,x", "ftp://a.b"]
DETAILS_OPEN = re.compile(r"<details[^>]*\sopen[\s>]")
RELATION_FORMS = [PersonRelationForm, PersonGroupRelationForm, GiftRelationForm, RelationForm]


def _gift_data(**overrides):
    return {"name": "Book", "comment": "", **overrides}


def test_gift_form_accepts_url_and_price():
    form = GiftForm(_gift_data(url="https://shop.example/book", price="12.50"))
    assert form.is_valid(), form.errors
    gift = form.save()
    assert gift.url == "https://shop.example/book"
    assert gift.price == Decimal("12.50")


@pytest.mark.parametrize("url", HOSTILE_URLS)
def test_gift_form_rejects_unsafe_url(url):
    form = GiftForm(_gift_data(url=url))
    assert not form.is_valid()
    assert "url" in form.errors


@pytest.mark.parametrize("price", ["-1", "12.345", "abc"])
def test_gift_form_rejects_invalid_price(price):
    form = GiftForm(_gift_data(price=price))
    assert not form.is_valid()
    assert "price" in form.errors


def test_gift_form_normalizes_scheme_less_url_to_http():
    # Django's URLField prepends http://, which is still a safe http(s) URL
    form = GiftForm(_gift_data(url="example.com"))
    assert form.is_valid(), form.errors
    assert form.save().url == "http://example.com"


def test_gift_form_accepts_zero_price():
    form = GiftForm(_gift_data(price="0"))
    assert form.is_valid(), form.errors
    assert form.save().price == Decimal(0)


def test_gift_form_blank_url_and_price_are_valid():
    form = GiftForm(_gift_data(url="", price=""))
    assert form.is_valid(), form.errors
    gift = form.save()
    assert gift.url == ""
    assert gift.price is None


@pytest.mark.parametrize("form_class", RELATION_FORMS)
def test_relation_forms_expose_url_and_price(form_class):
    form = form_class(user=UserFactory())
    assert "url" in form.fields
    assert "price" in form.fields


@pytest.mark.parametrize("url", HOSTILE_URLS)
def test_relation_form_rejects_unsafe_url(url):
    user = UserFactory()
    relation = RelationFactory()
    form = RelationForm(
        {
            "recipient": relation.recipient_key,
            "gift": relation.gift.pk,
            "status": relation.status.pk,
            "url": url,
        },
        instance=relation,
        user=user,
    )
    assert not form.is_valid()
    assert "url" in form.errors


def test_relation_form_clearing_override_reverts_to_gift():
    gift = GiftFactory(price=Decimal(10), url="https://gift.example")
    relation = RelationFactory(gift=gift, price=Decimal(5), url="https://plan.example")
    user = UserFactory()
    form = RelationForm(
        {
            "recipient": relation.recipient_key,
            "gift": gift.pk,
            "status": relation.status.pk,
            "price": "",
            "url": "",
        },
        instance=relation,
        user=user,
    )
    # The recipient and gift are not accessible to this user: only the override fields matter
    form.is_valid()
    assert "price" not in form.errors
    assert "url" not in form.errors
    assert form.cleaned_data["price"] is None
    assert form.cleaned_data["url"] == ""


def test_relation_form_uses_gift_values_as_placeholder():
    gift = GiftFactory(price=Decimal("10.00"), url="https://gift.example")
    relation = RelationFactory(gift=gift)
    form = RelationForm(instance=relation, user=UserFactory())
    assert form.fields["price"].widget.attrs["placeholder"] == "10.00"
    assert form.fields["url"].widget.attrs["placeholder"] == "https://gift.example"


def test_gift_relation_form_uses_gift_values_as_placeholder():
    user = UserFactory()
    gift = GiftFactory(price=Decimal("7.00"), shared_with=[user])
    form = GiftRelationForm(user=user, gift_id=gift.gift_id)
    assert form.fields["price"].widget.attrs["placeholder"] == "7.00"


class TestCollapsedSection:
    @pytest.fixture
    def client(self, authenticated_client):
        return authenticated_client

    def test_section_closed_when_empty(self, client):
        response = client.get(reverse("gift_manager:gift_create"))
        content = response.content.decode()
        assert "<details" in content
        assert not DETAILS_OPEN.search(content)
        assert 'name="url"' in content
        assert 'name="price"' in content

    def test_section_open_when_value_set(self, client, user):
        gift = GiftFactory(price=Decimal(3), shared_with=[user])
        # An owner permission is required to edit
        from gift_manager.models import GiftPermission
        from gift_manager.models import PermissionLevel

        GiftPermission.objects.filter(gift=gift, user=user).update(
            permission_type=PermissionLevel.OWNER
        )
        response = client.get(reverse("gift_manager:gift_edit", kwargs={"pk": gift.gift_id}))
        assert DETAILS_OPEN.search(response.content.decode())

    def test_section_open_when_plan_override_is_zero(self, client, user):
        relation = RelationFactory(price=Decimal(0))
        for obj in (relation, relation.gift, relation.person):
            create_or_update_permission(user, obj, permission_level=PermissionLevel.OWNER)
        response = client.get(
            reverse("gift_manager:relation_edit", kwargs={"pk": relation.relation_id})
        )
        assert DETAILS_OPEN.search(response.content.decode())

    def test_section_open_on_error(self, client):
        response = client.post(
            reverse("gift_manager:gift_create"), {"name": "x", "url": "javascript:alert(1)"}
        )
        content = response.content.decode()
        assert DETAILS_OPEN.search(content)
        assert "Enter a valid" in content


class TestCurrencyOnForms:
    @pytest.fixture
    def client(self, authenticated_client):
        return authenticated_client

    def test_gift_form_shows_the_user_currency(self, client, user):
        user.profile.currency = "USD"
        user.profile.save()
        content = client.get(reverse("gift_manager:gift_create")).content.decode()
        assert re.search(r'class="input-group-text"[^>]*>\s*USD\s*<', content)

    def test_gift_form_defaults_to_eur(self, client):
        content = client.get(reverse("gift_manager:gift_create")).content.decode()
        assert re.search(r'class="input-group-text"[^>]*>\s*EUR\s*<', content)

    def test_plan_form_shows_the_user_currency(self, client, user):
        user.profile.currency = "GBP"
        user.profile.save()
        content = client.get(reverse("gift_manager:relation_create")).content.decode()
        assert re.search(r'class="input-group-text"[^>]*>\s*GBP\s*<', content)
