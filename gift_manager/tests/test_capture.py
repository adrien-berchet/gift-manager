"""Tests for the browser bookmarklet: captured values, landing page and prefilled forms."""

from decimal import Decimal
from urllib.parse import parse_qs
from urllib.parse import unquote
from urllib.parse import urlsplit

import pytest
from django.urls import reverse

from gift_manager.capture import build_bookmarklet
from gift_manager.capture import clean_capture
from gift_manager.capture import target_urls
from gift_manager.models import Gift
from gift_manager.models import Wish
from gift_manager.tests.factories import PersonFactory

PRODUCT = {
    "title": "Red scarf",
    "url": "https://shop.example/scarf?ref=1",
    "price": "24.50",
    "currency": "EUR",
    "notes": "A warm scarf",
}


class TestCleanCapture:
    def test_keeps_valid_values(self):
        capture = clean_capture(PRODUCT, "EUR")

        assert capture.title == "Red scarf"
        assert capture.url == "https://shop.example/scarf?ref=1"
        assert capture.price == Decimal("24.50")
        assert capture.notes == "A warm scarf"
        assert not capture.is_empty

    @pytest.mark.parametrize(
        "url",
        [
            "javascript:alert(1)",
            "data:text/html,x",
            "shop.example/scarf",
            "//shop.example/scarf",
            "ftp://shop.example/scarf",
            "https://shop.example@evil.example/",
            "https://",
            "https://shop.example/" + "a" * 2000,
        ],
    )
    def test_drops_unusable_url(self, url):
        capture = clean_capture({**PRODUCT, "url": url}, "EUR")

        assert capture.url == ""
        assert capture.title == "Red scarf"

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("24,99", Decimal("24.99")),
            ("1,299.00", Decimal("1299.00")),
            ("1.299,00", Decimal("1299.00")),
            ("1.234.567,89", Decimal("1234567.89")),
            ("1,234,567", Decimal("1234567.00")),
            ("1 299,50", Decimal("1299.50")),
            (" 1 299,5 ", Decimal("1299.50")),
            ("24.999", Decimal("25.00")),
            ("0", Decimal("0.00")),
        ],
    )
    def test_normalizes_price(self, raw, expected):
        assert clean_capture({**PRODUCT, "price": raw}, "EUR").price == expected

    @pytest.mark.parametrize(
        "raw", ["", "abc", "-5", "NaN", "Infinity", "1e400", "100000000", "1,299", "1.2.3"]
    )
    def test_drops_unusable_price(self, raw):
        assert clean_capture({**PRODUCT, "price": raw}, "EUR").price is None

    def test_price_kept_when_currency_matches_whatever_the_case(self):
        assert clean_capture({**PRODUCT, "currency": " eur "}, "EUR").price == Decimal("24.50")

    @pytest.mark.parametrize("currency", ["USD", "", "€"])
    def test_price_dropped_when_currency_differs_or_is_unknown(self, currency):
        capture = clean_capture({**PRODUCT, "currency": currency}, "EUR")

        assert capture.price is None
        assert capture.title == "Red scarf"

    def test_long_values_are_truncated_not_dropped(self):
        capture = clean_capture({"title": "t" * 400, "notes": "n" * 400}, "EUR")

        assert capture.title == "t" * 255
        assert capture.notes == "n" * 150

    def test_empty_capture(self):
        assert clean_capture({}, "EUR").is_empty

    def test_target_urls_omit_empty_values(self):
        targets = target_urls(clean_capture({"title": "Red scarf"}, "EUR"))

        assert parse_qs(urlsplit(targets["wish"]).query) == {"title": ["Red scarf"]}
        assert parse_qs(urlsplit(targets["gift"]).query) == {"name": ["Red scarf"]}
        assert parse_qs(urlsplit(targets["plan"]).query) == {"new_gift-name": ["Red scarf"]}


class TestBookmarklet:
    def test_is_a_single_void_javascript_url(self):
        href = build_bookmarklet("https://gifts.example/en/capture/")

        assert href.startswith("javascript:void")
        assert "\n" not in href
        assert '"https://gifts.example/en/capture/"' in unquote(href)

    def test_capture_url_cannot_break_out_of_the_script(self):
        source = unquote(build_bookmarklet('https://x.example/"+alert(1)+"'))

        assert '"https://x.example/\\"+alert(1)+\\""' in source


@pytest.mark.django_db
class TestCaptureView:
    @pytest.fixture
    def url(self):
        return reverse("gift_manager:capture")

    def test_requires_login_and_keeps_the_captured_values(self, client, url):
        response = client.get(url, PRODUCT)

        assert response.status_code == 302
        next_url = parse_qs(urlsplit(response["Location"]).query)["next"][0]
        assert parse_qs(urlsplit(next_url).query)["title"] == ["Red scarf"]

    def test_shows_the_product_and_the_three_targets(self, authenticated_client, url):
        response = authenticated_client.get(url, PRODUCT)
        content = response.content.decode()

        assert response.status_code == 200
        assert response["Referrer-Policy"] == "same-origin"
        assert "Red scarf" in content
        targets = response.context["targets"]
        assert parse_qs(urlsplit(targets["wish"]).query) == {
            "title": ["Red scarf"],
            "url": ["https://shop.example/scarf?ref=1"],
            "price_hint": ["24.50"],
            "notes": ["A warm scarf"],
        }
        assert parse_qs(urlsplit(targets["plan"]).query) == {
            "new_gift-name": ["Red scarf"],
            "new_gift-url": ["https://shop.example/scarf?ref=1"],
            "new_gift-price": ["24.50"],
        }
        for name in ("wish", "plan", "gift"):
            assert f'data-capture-target="{name}"' in content

    def test_price_in_another_currency_is_left_out(self, authenticated_client, url):
        response = authenticated_client.get(url, {**PRODUCT, "currency": "USD"})

        assert response.context["capture"].price is None
        assert "price" not in response.context["targets"]["gift"]

    def test_invalid_values_never_fail(self, authenticated_client, url):
        response = authenticated_client.get(
            url, {"title": "<script>alert(1)</script>", "url": "javascript:alert(1)", "price": "x"}
        )
        content = response.content.decode()

        assert response.status_code == 200
        assert "<script>alert(1)</script>" not in content
        assert "javascript:alert(1)" not in content

    def test_nothing_captured(self, authenticated_client, url):
        response = authenticated_client.get(url)

        assert response.status_code == 200
        assert "capture-empty" in response.content.decode()

    def test_get_changes_nothing(self, authenticated_client, url):
        authenticated_client.get(url, PRODUCT)

        assert not Wish.objects.exists()
        assert not Gift.objects.exists()

    def test_profile_offers_the_bookmarklet(self, authenticated_client, url):
        response = authenticated_client.get(reverse("gift_manager:profile_detail"))

        href = response.context["bookmarklet_url"]
        assert f'"http://testserver{url}"' in unquote(href)
        assert "bookmarklet-link" in response.content.decode()


@pytest.mark.django_db
class TestPrefilledForms:
    def test_wish_form_is_prefilled(self, authenticated_client):
        response = authenticated_client.get(
            reverse("gift_manager:wish_create"),
            {
                "title": "Red scarf",
                "url": "https://shop.example/scarf",
                "price_hint": "24.50",
                "notes": "A warm scarf",
            },
        )

        initial = response.context["form"].initial
        assert initial["title"] == "Red scarf"
        assert initial["url"] == "https://shop.example/scarf"
        assert initial["price_hint"] == "24.50"
        assert initial["notes"] == "A warm scarf"

    def test_prefilled_wish_can_be_saved(self, authenticated_client, user):
        response = authenticated_client.post(
            reverse("gift_manager:wish_create"),
            {
                "title": "Red scarf",
                "url": "https://shop.example/scarf",
                "price_hint": "24.50",
                "priority": "2",
                "notes": "",
            },
        )

        assert response.status_code == 302
        wish = Wish.objects.get(wisher=user)
        assert wish.price_hint == Decimal("24.50")

    def test_gift_form_is_prefilled(self, authenticated_client):
        response = authenticated_client.get(
            reverse("gift_manager:gift_create"),
            {"name": "Red scarf", "url": "https://shop.example/scarf", "price": "24.50"},
        )

        initial = response.context["form"].initial
        assert initial["name"] == "Red scarf"
        assert initial["url"] == "https://shop.example/scarf"
        assert initial["price"] == "24.50"

    def test_guided_flow_carries_the_gift_through_the_recipient_step(
        self, authenticated_client, user
    ):
        url = reverse("gift_manager:relation_guided_create")
        person = PersonFactory(shared_with=[user])
        prefill = {
            "new_gift-name": "Red scarf",
            "new_gift-url": "https://shop.example/scarf",
            "new_gift-price": "24.50",
        }

        first = authenticated_client.get(url, {**prefill, "recipient": "ignored"})
        content = first.content.decode()
        carried = dict(first.context["carried"])

        assert carried == {**prefill, "gift_mode": "new"}
        assert 'name="new_gift-name" value="Red scarf"' in content

        second = authenticated_client.post(
            url,
            {
                "step": 1,
                "nav": "next",
                "recipient_mode": "existing",
                "recipient": f"person:{person.person_id}",
                **carried,
            },
        )
        gift_step = second.context["step_form"]

        assert gift_step.mode == "new"
        assert gift_step.new_form.initial["name"] == "Red scarf"
        assert gift_step.new_form.initial["url"] == "https://shop.example/scarf"
        assert gift_step.new_form.initial["price"] == "24.50"

    def test_guided_flow_opened_on_the_gift_step_shows_the_gift(self, authenticated_client):
        response = authenticated_client.get(
            reverse("gift_manager:relation_guided_create"),
            {"step": 2, "new_gift-name": "Red scarf", "new_gift-price": "24.50"},
        )
        gift_step = response.context["step_form"]

        assert gift_step.mode == "new"
        assert gift_step.new_form.initial["name"] == "Red scarf"
        assert gift_step.new_form.initial["price"] == "24.50"

    def test_guided_flow_without_prefill_carries_nothing(self, authenticated_client):
        response = authenticated_client.get(reverse("gift_manager:relation_guided_create"))

        assert response.context["carried"] == []
