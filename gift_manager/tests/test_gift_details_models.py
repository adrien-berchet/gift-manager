from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db import transaction

from gift_manager.models import Profile
from gift_manager.statuses import is_purchased_status
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import RelationStatusFactory
from gift_manager.tests.factories import UserFactory
from gift_manager.validators import validate_http_url


@pytest.mark.parametrize("value", ["http://example.com", "https://example.com/a?b=1"])
def test_validate_http_url_accepts_http_and_https(value):
    validate_http_url(value)


@pytest.mark.parametrize(
    "value",
    ["javascript:alert(1)", "data:text/html,x", "ftp://a.b", "example.com", "https://"],
)
def test_validate_http_url_rejects_unsafe_schemes(value):
    with pytest.raises(ValidationError):
        validate_http_url(value)


@pytest.mark.django_db
class TestEffectiveValues:
    def test_effective_price_prefers_plan_override(self):
        relation = RelationFactory(gift=GiftFactory(price=Decimal("10")), price=Decimal("5"))
        assert relation.effective_price == Decimal("5")

    def test_effective_price_falls_back_to_gift(self):
        relation = RelationFactory(gift=GiftFactory(price=Decimal("10")), price=None)
        assert relation.effective_price == Decimal("10")

    def test_effective_price_none_when_both_missing(self):
        relation = RelationFactory(gift=GiftFactory(price=None), price=None)
        assert relation.effective_price is None

    def test_zero_plan_price_is_an_override(self):
        relation = RelationFactory(gift=GiftFactory(price=Decimal("10")), price=Decimal("0"))
        assert relation.effective_price == Decimal("0")

    def test_effective_url_falls_back_to_gift(self):
        relation = RelationFactory(gift=GiftFactory(url="https://gift.example"), url="")
        assert relation.effective_url == "https://gift.example"

    def test_effective_url_prefers_plan_override(self):
        relation = RelationFactory(
            gift=GiftFactory(url="https://gift.example"), url="https://plan.example"
        )
        assert relation.effective_url == "https://plan.example"


@pytest.mark.django_db
class TestPriceConstraint:
    def test_negative_gift_price_violates_constraint(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            GiftFactory(price=Decimal("-1"))

    def test_negative_relation_price_violates_constraint(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            RelationFactory(price=Decimal("-1"))


@pytest.mark.django_db
def test_profile_currency_defaults_to_eur():
    profile = Profile.objects.get(user=UserFactory())
    assert profile.currency == "EUR"


@pytest.mark.django_db
def test_is_purchased_status():
    assert is_purchased_status(RelationStatusFactory(status="Purchased"))
    assert not is_purchased_status(RelationStatusFactory(status="Idea"))
    assert not is_purchased_status(None)
