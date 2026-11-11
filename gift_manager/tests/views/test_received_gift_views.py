"""Tests for ReceivedGift views (CRUD, list filtering, timeline, privacy)."""

import json
from datetime import date

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from gift_manager.forms import ReceivedGiftForm
from gift_manager.models import PermissionLevel
from gift_manager.models import ReceivedGift
from gift_manager.services import PermissionService
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import ReceivedGiftFactory
from gift_manager.tests.factories import UserFactory
from gift_manager.tests.factories import WishFactory


@pytest.mark.django_db
def test_received_gift_list_view_renders_own_gifts_grouped_by_year(client):
    user = UserFactory()
    client.force_login(user)

    ReceivedGiftFactory(
        recipient_user=user,
        title="Gift 2026",
        received_on=date(2026, 5, 10),
    )
    ReceivedGiftFactory(
        recipient_user=user,
        title="Gift 2025",
        received_on=date(2025, 12, 25),
    )

    url = reverse("gift_manager:received_gift_list")
    response = client.get(url)
    assert response.status_code == 200

    content = response.content.decode()
    assert "Gift 2026" in content
    assert "Gift 2025" in content
    assert "2026" in content
    assert "2025" in content


@pytest.mark.django_db
def test_received_gift_list_view_privacy(client):
    user_a = UserFactory()
    user_b = UserFactory()

    ReceivedGiftFactory(recipient_user=user_a, title="User A Secret Gift")
    ReceivedGiftFactory(recipient_user=user_b, title="User B Secret Gift")

    client.force_login(user_a)
    response = client.get(reverse("gift_manager:received_gift_list"))
    assert response.status_code == 200

    content = response.content.decode()
    assert "User A Secret Gift" in content
    assert "User B Secret Gift" not in content


@pytest.mark.django_db
def test_received_gift_list_filter_by_thank_you_status(client):
    user = UserFactory()
    client.force_login(user)

    ReceivedGiftFactory(
        recipient_user=user,
        title="Pending Gift",
        thank_you_sent=False,
    )
    ReceivedGiftFactory(
        recipient_user=user,
        title="Thanked Gift",
        thank_you_sent=True,
    )

    url = reverse("gift_manager:received_gift_list")

    # Filter pending
    resp_pending = client.get(url, {"thank_you": "pending"})
    assert "Pending Gift" in resp_pending.content.decode()
    assert "Thanked Gift" not in resp_pending.content.decode()

    # Filter sent
    resp_sent = client.get(url, {"thank_you": "sent"})
    assert "Pending Gift" not in resp_sent.content.decode()
    assert "Thanked Gift" in resp_sent.content.decode()


@pytest.mark.django_db
def test_received_gift_detail_view(client):
    user = UserFactory()
    other_user = UserFactory()

    gift = ReceivedGiftFactory(recipient_user=user, title="Detail Gift Test")

    client.force_login(user)
    url = reverse("gift_manager:received_gift_detail", kwargs={"pk": gift.received_gift_id})
    resp = client.get(url)
    assert resp.status_code == 200
    assert "Detail Gift Test" in resp.content.decode()

    # Other user cannot view it
    client.force_login(other_user)
    resp_other = client.get(url)
    assert resp_other.status_code == 404


@pytest.mark.django_db
def test_received_gift_create_view_post_valid(client):
    user = UserFactory()
    client.force_login(user)

    person = PersonFactory(first_name="Grandma", family_name="Rose")
    PermissionService.create_or_update_permission(
        user, person, permission_level=PermissionLevel.OWNER
    )

    url = reverse("gift_manager:received_gift_create")
    data = {
        "title": "Knitted Scarf",
        "received_on": "2026-11-09",
        "giver_mode": "contacts",
        "givers": [f"person:{person.person_id}"],
        "giver_label": "",
        "occasion_mode": "other",
        "occasion_text": "Winter Visit",
        "reaction_rating": "5",
        "reaction_note": "So cozy!",
        "thank_you_sent": "on",
    }
    response = client.post(url, data)
    assert response.status_code == 302
    assert response.url == reverse("gift_manager:received_gift_list")

    gift = ReceivedGift.objects.get(title="Knitted Scarf")
    assert gift.recipient_user == user
    assert gift.reaction_rating == 5
    assert gift.thank_you_sent is True
    assert person in gift.giver_persons.all()


@pytest.mark.django_db
def test_received_gift_create_view_requires_at_least_one_giver(client):
    user = UserFactory()
    client.force_login(user)

    url = reverse("gift_manager:received_gift_create")
    data = {
        "title": "Orphan Gift",
        "received_on": "2026-11-09",
        "giver_label": "",
    }
    response = client.post(url, data)
    assert response.status_code == 200  # Form errors
    assert "Please specify who gave this gift" in response.content.decode()


@pytest.mark.django_db
def test_received_gift_update_view(client):
    user = UserFactory()
    client.force_login(user)

    gift = ReceivedGiftFactory(
        recipient_user=user,
        title="Old Title",
        giver_label="Someone",
    )

    url = reverse("gift_manager:received_gift_edit", kwargs={"pk": gift.received_gift_id})
    response = client.post(
        url,
        {
            "title": "Updated Title",
            "received_on": "2026-11-09",
            "giver_label": "Someone Updated",
            "reaction_rating": "4",
        },
    )
    assert response.status_code == 302
    gift.refresh_from_db()
    assert gift.title == "Updated Title"
    assert gift.reaction_rating == 4


@pytest.mark.django_db
def test_received_gift_delete_view(client):
    user = UserFactory()
    client.force_login(user)

    gift = ReceivedGiftFactory(recipient_user=user, title="To Be Deleted")
    url = reverse("gift_manager:received_gift_delete", kwargs={"pk": gift.received_gift_id})

    # GET confirm
    resp_get = client.get(url)
    assert resp_get.status_code == 200
    assert "To Be Deleted" in resp_get.content.decode()

    # POST delete
    resp_post = client.post(url)
    assert resp_post.status_code == 302
    assert not ReceivedGift.objects.filter(pk=gift.pk).exists()


@pytest.mark.django_db
def test_received_gift_toggle_thank_you(client):
    user = UserFactory()
    client.force_login(user)

    gift = ReceivedGiftFactory(recipient_user=user, thank_you_sent=False)
    url = reverse(
        "gift_manager:received_gift_toggle_thank_you", kwargs={"pk": gift.received_gift_id}
    )

    # Toggle to True
    client.post(url)
    gift.refresh_from_db()
    assert gift.thank_you_sent is True

    # Toggle back to False
    client.post(url)
    gift.refresh_from_db()
    assert gift.thank_you_sent is False


@pytest.mark.django_db
def test_received_gift_toggle_thank_you_htmx_refreshes_list_without_notification(client):
    """The toggled button already shows the result: no toast and no flash message."""
    user = UserFactory()
    client.force_login(user)
    gift = ReceivedGiftFactory(recipient_user=user, thank_you_sent=False)
    url = reverse(
        "gift_manager:received_gift_toggle_thank_you", kwargs={"pk": gift.received_gift_id}
    )

    resp = client.post(url, headers={"HX-Request": "true"})

    assert resp.status_code == 200
    assert json.loads(resp["HX-Trigger"]) == {"list:update": None}
    # Nothing queued for the next full page load either
    list_resp = client.get(reverse("gift_manager:received_gift_list"))
    assert not list(get_messages(list_resp.wsgi_request))


@pytest.mark.django_db
def test_received_gift_toggle_thank_you_without_htmx_redirects_without_message(client):
    user = UserFactory()
    client.force_login(user)
    gift = ReceivedGiftFactory(recipient_user=user, thank_you_sent=False)
    url = reverse(
        "gift_manager:received_gift_toggle_thank_you", kwargs={"pk": gift.received_gift_id}
    )

    resp = client.post(url, follow=True)

    assert resp.redirect_chain[-1][0] == reverse("gift_manager:received_gift_list")
    assert not list(get_messages(resp.wsgi_request))
    gift.refresh_from_db()
    assert gift.thank_you_sent is True


@pytest.mark.django_db
def test_received_gift_list_shows_giver_names_linked_when_accessible(client):
    user = UserFactory()
    client.force_login(user)

    giver = PersonFactory(first_name="Grandma", family_name="Rose")
    PermissionService.create_or_update_permission(
        user, giver, permission_level=PermissionLevel.OWNER
    )
    gift = ReceivedGiftFactory(recipient_user=user, title="Knitted Scarf")
    gift.giver_persons.set([giver])

    content = client.get(reverse("gift_manager:received_gift_list")).content.decode()

    giver_url = reverse("gift_manager:person_detail", kwargs={"pk": giver.person_id})
    assert f'href="{giver_url}"' in content
    assert "Grandma Rose</a>" in content
    # The giver filter lists the giver by name
    assert ">Grandma Rose</option>" in content


@pytest.mark.django_db
def test_received_gift_giver_without_access_is_shown_but_not_linked(client):
    user = UserFactory()
    client.force_login(user)

    giver = PersonFactory(first_name="Former", family_name="Friend")
    gift = ReceivedGiftFactory(recipient_user=user, title="Old Gift")
    gift.giver_persons.set([giver])

    giver_url = reverse("gift_manager:person_detail", kwargs={"pk": giver.person_id})
    for url in (
        reverse("gift_manager:received_gift_list"),
        reverse("gift_manager:received_gift_detail", kwargs={"pk": gift.received_gift_id}),
    ):
        content = client.get(url).content.decode()
        assert "Former Friend" in content
        assert giver_url not in content


@pytest.mark.django_db
def test_received_gift_detail_shows_linked_giver_and_title_without_username(client):
    user = UserFactory(username="owner_login")
    client.force_login(user)

    giver = PersonFactory(first_name="Uncle", family_name="Paul")
    PermissionService.create_or_update_permission(
        user, giver, permission_level=PermissionLevel.OWNER
    )
    gift = ReceivedGiftFactory(recipient_user=user, title="Board Game", description="Fun for all")
    gift.giver_persons.set([giver])

    url = reverse("gift_manager:received_gift_detail", kwargs={"pk": gift.received_gift_id})
    content = client.get(url).content.decode()

    giver_url = reverse("gift_manager:person_detail", kwargs={"pk": giver.person_id})
    assert f'href="{giver_url}"' in content
    assert "Uncle Paul</a>" in content
    assert "owner_login" not in content
    # No leading line break inside the pre-line description block
    assert 'style="white-space: pre-line;">Fun for all' in content


@pytest.mark.django_db
def test_received_gift_detail_page_uses_generic_title_and_action_buttons(client):
    user = UserFactory()
    client.force_login(user)
    gift = ReceivedGiftFactory(recipient_user=user, title="Board Game")

    url = reverse("gift_manager:received_gift_detail", kwargs={"pk": gift.received_gift_id})
    response = client.get(url)
    content = response.content.decode()

    assert "<h1>Received gift details</h1>" in content
    assert 'class="breadcrumb' not in content
    edit_url = reverse("gift_manager:received_gift_edit", kwargs={"pk": gift.received_gift_id})
    assert [b["url"] for b in response.context["action_buttons"]] == [
        edit_url,
        reverse("gift_manager:received_gift_delete", kwargs={"pk": gift.received_gift_id}),
    ]

    # The slide-in panel shows enabled edit/delete buttons for the owner
    panel = client.get(url, HTTP_HX_REQUEST="true").content.decode()
    assert f'data-edit-url="{edit_url}"' in panel
    assert "fa-lock" not in panel


@pytest.mark.django_db
def test_dashboard_has_record_received_gift_quick_action(client):
    user = UserFactory()
    client.force_login(user)

    content = client.get(reverse("gift_manager:home")).content.decode()

    create_url = reverse("gift_manager:received_gift_create")
    assert f'href="{create_url}" class="quick-action-btn" data-action="create"' in content


@pytest.mark.django_db
def test_wish_card_has_mark_as_received_shortcut(client):
    user = UserFactory()
    client.force_login(user)
    wish = WishFactory(wisher=user, title="Headphones")

    content = client.get(reverse("gift_manager:wishlist_list")).content.decode()

    assert f"{reverse('gift_manager:received_gift_create')}?wish={wish.wish_id}" in content


@pytest.mark.django_db
def test_create_form_prefilled_from_wish(client):
    user = UserFactory()
    client.force_login(user)
    wish = WishFactory(wisher=user, title="Headphones", notes="Wireless")

    url = f"{reverse('gift_manager:received_gift_create')}?wish={wish.wish_id}"
    form = client.get(url).context["form"]

    assert form.initial["wish"] == wish
    assert form.initial["title"] == "Headphones"
    assert form.initial["description"] == "Wireless"


@pytest.mark.django_db
def test_person_detail_has_record_received_gift_action(client):
    user = UserFactory()
    client.force_login(user)
    person = PersonFactory(first_name="Grandma", family_name="Rose")
    PermissionService.create_or_update_permission(
        user, person, permission_level=PermissionLevel.OWNER
    )

    response = client.get(reverse("gift_manager:person_detail", kwargs={"pk": person.person_id}))

    expected_url = f"{reverse('gift_manager:received_gift_create')}?giver={person.person_id}"
    button = next(b for b in response.context["action_buttons"] if b["url"] == expected_url)
    assert button["data_action"] == "create"

    form = client.get(expected_url).context["form"]
    assert form.initial["givers"] == [f"person:{person.person_id}"]
    assert form["giver_mode"].value() == "contacts"


@pytest.mark.django_db
def test_received_gift_form_wish_choices_show_title_only_and_widgets_are_styled():
    user = UserFactory(username="owner_login")
    wish = WishFactory(wisher=user, title="Headphones")

    form = ReceivedGiftForm(user=user)

    wish_labels = [label for value, label in form.fields["wish"].choices if value]
    assert wish_labels == ["Headphones"]
    assert form.fields["wish"].label_from_instance(wish) == "Headphones"
    assert "form-input-text" in form.fields["url"].widget.attrs["class"]
    for name in ("event", "wish"):
        assert "form-select" in form.fields[name].widget.attrs["class"], name
    assert "form-check-input" in form.fields["givers"].widget.attrs["class"]


@pytest.mark.django_db
def test_received_gift_form_renders_mode_choices_and_sectioned_givers(client):
    user = UserFactory()
    client.force_login(user)
    person = PersonFactory(first_name="Grandma", family_name="Rose")
    PermissionService.create_or_update_permission(
        user, person, permission_level=PermissionLevel.OWNER
    )
    group = PersonGroupFactory(name="Rose family")
    PermissionService.create_or_update_permission(
        user, group, permission_level=PermissionLevel.OWNER
    )
    WishFactory(wisher=user, title="Headphones")

    content = client.get(reverse("gift_manager:received_gift_create")).content.decode()

    # Giver: radio between known people/groups and a free-text name
    assert 'name="giver_mode" value="contacts"' in content
    assert 'name="giver_mode" value="other"' in content
    assert 'class="guided-panel guided-panel--contacts"' in content
    assert 'class="guided-panel guided-panel--other"' in content
    # One giver selector with a "People" and a "Groups" section
    picker = content[content.index('class="giver-picker"') :]
    assert picker.index("People") < picker.index("Grandma Rose") < picker.index("Groups")
    assert picker.index("Groups") < picker.index("Rose family")
    assert f'value="person:{person.person_id}"' in content
    assert f'value="group:{group.group_id}"' in content
    # Occasion: radio between a known event and a free-text occasion
    assert 'name="occasion_mode" value="event"' in content
    assert 'class="guided-panel guided-panel--event"' in content
    # The wish field is a plain field, not a section of its own
    assert "Fulfill Wishlist Item" not in content
    assert 'name="wish"' in content
    assert "Mark the wish as received" in content


def _panel(content, name):
    start = content.index(f'class="guided-panel guided-panel--{name}"')
    return content[start : content.index('class="guided-panel ', start + 1)]


@pytest.mark.django_db
def test_received_gift_form_chooses_between_a_new_gift_and_a_fulfilled_wish(client):
    user = UserFactory()
    client.force_login(user)
    wish = WishFactory(wisher=user, title="Headphones")
    url = reverse("gift_manager:received_gift_create")

    content = client.get(url).content.decode()

    assert "form-collapsible" not in content
    assert 'name="gift_mode" value="new"' in content
    assert 'name="gift_mode" value="wish"' in content
    new_panel = _panel(content, "new")
    assert 'name="title"' in new_panel
    assert 'name="url"' in new_panel
    assert 'name="wish"' not in new_panel
    wish_panel = _panel(content, "wish")
    assert 'name="wish"' in wish_panel
    # Ticked by default: untick it for wishes received again and again
    assert 'type="checkbox" name="fulfills_wish"' in wish_panel
    checkbox = wish_panel[wish_panel.index('name="fulfills_wish"') :]
    assert " checked" in checkbox[: checkbox.index(">")]
    assert "Mark the wish as received" in wish_panel
    # The title keeps its asterisk, but no HTML "required" (hidden in wish mode)
    title_input = new_panel[new_panel.index('<input type="text" name="title"') :]
    assert " required" not in title_input[: title_input.index(">")]
    assert '<span class="text-danger" aria-hidden="true">*</span>' in new_panel

    # Recording a gift from a wish starts on the wish side
    content = client.get(f"{url}?wish={wish.wish_id}").content.decode()
    assert 'name="gift_mode" value="wish" id="id_gift_mode_1" autocomplete="off" checked' in (
        content
    )
