"""Display of the link, price and currency of gifts and gift plans."""

from decimal import Decimal

import pytest
from django.template import Context
from django.template import Template
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.urls import reverse
from django.utils import translation

from gift_manager.gift_plan_cards import build_gift_plan_card
from gift_manager.permissions import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.templatetags.custom_filters import format_price
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import WishFactory
from gift_manager.views.base import DeleteConfirmationMixin

pytestmark = pytest.mark.django_db

LINK_ATTRS = 'rel="noopener noreferrer nofollow"'


def _render_filter(value, currency):
    template = Template("{% load custom_filters %}{{ value|format_price:currency }}")
    return template.render(Context({"value": value, "currency": currency}))


@pytest.fixture
def client(authenticated_client):
    return authenticated_client


def _share(user, *objects):
    for obj in objects:
        create_or_update_permission(user, obj, permission_level=PermissionLevel.OWNER)


def _render_card(user, relation):
    request = RequestFactory().get("/")
    request.user = user
    card = build_gift_plan_card(relation, urgency_key="upcoming", permission=PermissionLevel.OWNER)
    return render_to_string(
        "gift_manager/includes/gift_plan_card.html", {"card": card, "request": request}
    )


class TestFormatPrice:
    def test_none_is_empty(self):
        assert _render_filter(None, "EUR") == ""

    def test_uses_two_decimals_and_currency(self):
        rendered = _render_filter(Decimal("12.5"), "EUR")
        assert "12.50" in rendered or "12,50" in rendered
        assert "EUR" in rendered or "€" in rendered

    def test_zero_is_displayed(self):
        assert "0" in _render_filter(Decimal(0), "USD")

    @pytest.mark.parametrize(
        ("currency", "english", "french"),
        [
            ("EUR", "€1,234.50", "1\u00a0234,50\u00a0€"),
            ("USD", "$1,234.50", "1\u00a0234,50\u00a0$"),
            ("GBP", "£1,234.50", "1\u00a0234,50\u00a0£"),
            ("CAD", "CA$1,234.50", "1\u00a0234,50\u00a0CA$"),
            ("CHF", "CHF\u00a01,234.50", "1\u00a0234,50\u00a0CHF"),
            ("XYZ", "XYZ\u00a01,234.50", "1\u00a0234,50\u00a0XYZ"),
        ],
    )
    def test_follows_the_convention_of_the_active_language(self, currency, english, french):
        with translation.override("en"):
            assert format_price(Decimal("1234.5"), currency) == english
        with translation.override("fr"):
            assert format_price(Decimal("1234.5"), currency) == french

    def test_negative_amount_keeps_its_sign_first(self):
        with translation.override("en"):
            assert format_price(Decimal(-3), "EUR") == "-€3.00"


class TestSamePriceEverywhere:
    """The gifts list, details, cards, budgets and wishes all show one format per language."""

    @pytest.mark.parametrize(("language", "expected"), [("en", "€24.50"), ("fr", "24,50\u00a0€")])
    def test_same_amount_renders_identically(self, client, user, language, expected):
        price = Decimal("24.50")
        relation = RelationFactory(price=price)
        relation.gift.price = price
        relation.gift.save()
        _share(user, relation, relation.gift, relation.person)
        wish = WishFactory(wisher=user, price_hint=price)

        with translation.override(language):
            gift_list = client.get(reverse("gift_manager:gifts"))
            gift_detail = client.get(
                reverse("gift_manager:gift_detail", kwargs={"pk": relation.gift.gift_id})
            )
            plan_detail = client.get(
                reverse("gift_manager:relation_detail", kwargs={"pk": relation.relation_id})
            )
            person_detail = client.get(
                reverse("gift_manager:person_detail", kwargs={"pk": relation.person.person_id})
            )
            wishlist = client.get(reverse("gift_manager:wishlist_list"))
            card = _render_card(user, relation)

        rows = gift_list.context["grid_data"]
        assert [(row[4], row[11]) for row in rows] == [("24.50", expected)]
        for response in (gift_detail, plan_detail, person_detail, wishlist):
            assert response.status_code == 200
            assert expected in response.content.decode(), response.request["PATH_INFO"]
        assert expected in card
        assert wish.title in wishlist.content.decode()

    def test_gifts_list_shows_the_server_formatted_price(self, client):
        content = client.get(reverse("gift_manager:gifts")).content.decode()
        assert "Intl.NumberFormat" not in content
        assert "row.cells[11].data" in content

    def test_gift_without_price_has_an_empty_display(self, client, user):
        gift = GiftFactory(price=None)
        _share(user, gift)
        rows = client.get(reverse("gift_manager:gifts")).context["grid_data"]
        assert [(row[4], row[11]) for row in rows] == [("", "")]

    @pytest.mark.parametrize(
        ("language", "collected", "total"),
        [("en", "€10.00", "€40.00"), ("fr", "10,00\u00a0€", "40,00\u00a0€")],
    )
    def test_group_gift_amounts_use_the_shared_format(self, language, collected, total):
        group_gift = {
            "currency": "EUR",
            "total_collected": Decimal(10),
            "total_price": Decimal(40),
            "owed_to_buyer": Decimal(30),
            "percent_collected": 25,
            "rows": [],
        }
        with translation.override(language):
            content = render_to_string(
                "gift_manager/includes/relation_group_gift_partial.html",
                {"group_gift": group_gift, "relation": RelationFactory(is_group_gift=True)},
            )
        assert f"{collected} /" in content
        assert total in content
        assert "EUR" not in content
        assert f'aria-valuetext="{collected} ' in content


class TestGiftDetail:
    def test_shows_link_and_price(self, client, user):
        gift = GiftFactory(url="https://shop.example/x", price=Decimal(20))
        _share(user, gift)
        content = client.get(
            reverse("gift_manager:gift_detail", kwargs={"pk": gift.gift_id})
        ).content.decode()
        assert 'href="https://shop.example/x"' in content
        assert LINK_ATTRS in content
        assert 'target="_blank"' in content
        assert "20.00" in content or "20,00" in content

    def test_hides_block_when_empty(self, client, user):
        gift = GiftFactory(url="", price=None)
        _share(user, gift)
        content = client.get(
            reverse("gift_manager:gift_detail", kwargs={"pk": gift.gift_id})
        ).content.decode()
        assert "link-price-display" not in content


class TestPlanCard:
    def test_shows_effective_price_from_gift_when_no_override(self, user):
        relation = RelationFactory(gift=GiftFactory(price=Decimal(30)), price=None)
        assert "30.00" in _render_card(user, relation) or "30,00" in _render_card(user, relation)

    def test_shows_override(self, user):
        relation = RelationFactory(
            gift=GiftFactory(price=Decimal(30), url="https://gift.example"),
            price=Decimal(25),
            url="https://plan.example",
        )
        rendered = _render_card(user, relation)
        assert "25.00" in rendered or "25,00" in rendered
        assert "30.00" not in rendered
        assert 'href="https://plan.example"' in rendered
        assert LINK_ATTRS in rendered

    def test_shows_the_link_host_next_to_the_link(self, user):
        relation = RelationFactory(gift=GiftFactory(url="https://shop.example/a/b?c=1"))
        rendered = _render_card(user, relation)
        # The compact card shows the host as the link text instead of "Open link (host)"
        assert 'link-price-display__host">shop.example<' in rendered
        assert "Open link" not in rendered

    def test_hides_block_when_empty(self, user):
        relation = RelationFactory(gift=GiftFactory(price=None, url=""), price=None, url="")
        assert "link-price-display" not in _render_card(user, relation)


class TestRelationDetail:
    def test_shows_link_price(self, client, user):
        relation = RelationFactory(price=Decimal(9), url="https://plan.example")
        _share(user, relation, relation.gift, relation.person)
        content = client.get(
            reverse("gift_manager:relation_detail", kwargs={"pk": relation.relation_id})
        ).content.decode()
        assert 'href="https://plan.example"' in content
        assert LINK_ATTRS in content
        assert "9.00" in content or "9,00" in content


class TestCurrencyPreference:
    def test_currency_saved_via_preferences_form(self, client, user):
        response = client.post(
            reverse("gift_manager:update_reminder_preferences"),
            {
                "preferred_language": "",
                "digest_frequency": "off",
                "digest_lookahead_days": "14",
                "currency": "USD",
            },
        )
        assert response.status_code == 302
        user.profile.refresh_from_db()
        assert user.profile.currency == "USD"

    def test_currency_is_optional_in_the_form(self, client, user):
        user.profile.currency = "GBP"
        user.profile.save()
        client.post(
            reverse("gift_manager:update_reminder_preferences"),
            {"preferred_language": "", "digest_frequency": "off", "digest_lookahead_days": "14"},
        )
        user.profile.refresh_from_db()
        assert user.profile.currency == "GBP"

    def test_profile_page_shows_currency_select(self, client):
        content = client.get(reverse("gift_manager:profile_detail")).content.decode()
        assert 'name="currency"' in content


def test_delete_confirmation_details_include_formatted_price(rf, user):
    class _View(DeleteConfirmationMixin):
        object_type = "Gift"

    view = _View()
    view.request = rf.get("/")
    view.request.user = user
    view.object = GiftFactory(price=Decimal(15))
    details = view.get_entity_details()
    joined = " ".join(details)
    assert "15" in joined
    assert "$" not in joined
