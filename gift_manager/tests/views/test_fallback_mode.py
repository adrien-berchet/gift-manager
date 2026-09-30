import pytest
from django.urls import reverse

from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import GiftTagFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory
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


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("url_name", "factory", "detail_name", "uuid_field"),
    [
        ("persons", PersonFactory, "person", "person_id"),
        ("gifts", GiftFactory, "gift", "gift_id"),
        ("events", EventFactory, "event", "event_id"),
    ],
)
def test_fallback_list_actions_use_public_uuids(client, url_name, factory, detail_name, uuid_field):
    """GM-AUD-008: no-JS row actions must point at the UUID routes."""
    user = UserFactory()
    obj = factory(shared_with=[user])
    client.force_login(user)

    response = client.get(reverse(f"gift_manager:{url_name}"), {"no_js": "1"})

    (row,) = response.context["fallback_table_data"]["rows"]
    kwargs = {"pk": getattr(obj, uuid_field)}
    assert [action["url"] for action in row["actions"]] == [
        reverse(f"gift_manager:{detail_name}_detail", kwargs=kwargs),
        reverse(f"gift_manager:{detail_name}_edit", kwargs=kwargs) + "?no_js=1",
        reverse(f"gift_manager:{detail_name}_delete", kwargs=kwargs) + "?no_js=1",
    ]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("factory", "route_prefix", "uuid_field"),
    [
        (PersonFactory, "person", "person_id"),
        (GiftFactory, "gift", "gift_id"),
        (EventFactory, "event", "event_id"),
        (PersonGroupFactory, "person_group", "group_id"),
        (GiftTagFactory, "gift_tag", "tag_id"),
        (RelationFactory, "relation", "relation_id"),
    ],
)
def test_fallback_actions_resolve_for_every_uuid_model(factory, route_prefix, uuid_field):
    """Instances and values() rows of every UUID-routed model yield resolvable URLs."""
    from gift_manager.mixins.fallback_mode import FallbackModeListMixin

    obj = factory()
    view = FallbackModeListMixin()
    view.model = type(obj)
    expected = reverse(
        f"gift_manager:{route_prefix}_detail", kwargs={"pk": getattr(obj, uuid_field)}
    )

    from_instance = view.get_fallback_actions(obj)
    from_row = view.get_fallback_actions({uuid_field: getattr(obj, uuid_field)})

    assert from_instance[0]["url"] == expected
    assert from_row[0]["url"] == expected
    assert [a["label"] for a in from_row] == ["View", "Edit", "Delete"]


@pytest.mark.django_db
def test_fallback_actions_for_unrouted_models_are_empty():
    from gift_manager.mixins.fallback_mode import FallbackModeListMixin

    user = UserFactory()
    view = FallbackModeListMixin()
    view.model = type(user)

    assert view.get_fallback_actions(user) == []
    assert view.get_fallback_actions({"id": user.pk}) == []
