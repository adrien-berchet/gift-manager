from decimal import Decimal

import pytest
from django.urls import reverse

from gift_manager.tests.factories import GiftFactory


@pytest.mark.django_db
def test_gift_list_exposes_link_and_price_columns(authenticated_client, user):
    GiftFactory(
        name="Scarf",
        url="https://shop.example.com/scarf",
        price=Decimal("12.50"),
        shared_with=[user],
    )
    GiftFactory(name="Bare gift", url="", price=None, shared_with=[user])

    response = authenticated_client.get(reverse("gift_manager:gifts"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "id: 'url'" in content
    assert "id: 'price'" in content
    # Rows carry the raw URL and an unlocalized price, empty strings when unset.
    assert "https://shop.example.com/scarf" in content
    assert '"12.50"' in content
    assert "row.cells[6].data" in content  # gift id follows the new columns


@pytest.mark.django_db
def test_gift_list_hides_unsafe_urls(authenticated_client, user):
    GiftFactory(name="Odd gift", url="", price=None, shared_with=[user])
    # Bypass model validation to simulate legacy data with a non-http link.
    from gift_manager.models import Gift

    Gift.objects.filter(name="Odd gift").update(url="javascript:alert(1)")

    response = authenticated_client.get(reverse("gift_manager:gifts"))

    assert "javascript:alert(1)" not in response.content.decode()
