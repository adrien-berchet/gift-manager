import pytest
from django.urls import reverse

from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import UserFactory


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("url_name", "factory", "factory_kwargs", "expected_text"),
    [
        (
            "persons",
            PersonFactory,
            {"first_name": "Ada", "family_name": "Lovelace"},
            "Ada",
        ),
        ("gifts", GiftFactory, {"name": "Warm socks"}, "Warm socks"),
        ("events", EventFactory, {"name": "Birthday dinner"}, "Birthday dinner"),
    ],
)
def test_list_views_render_explicit_fallback_mode(
    client,
    url_name,
    factory,
    factory_kwargs,
    expected_text,
):
    user = UserFactory()
    factory(shared_with=[user], **factory_kwargs)
    client.force_login(user)

    response = client.get(reverse(f"gift_manager:{url_name}"), {"no_js": "1"})

    assert response.status_code == 200
    assert response.context["is_fallback"] is True
    assert response.context["fallback_table_data"]["rows"]

    content = response.content.decode("utf-8")
    assert "Compatibility Mode" in content
    assert "fallback-mode.css" in content
    assert "progressive-enhancement.css" not in content
    assert "progressive-enhancement.js" not in content
    assert "fallback-table" in content
    assert expected_text in content
