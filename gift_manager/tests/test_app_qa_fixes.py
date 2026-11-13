"""Application fixes from the 2026-11-12 QA pass (outside the reveal and received-gift flows)."""

import json
from datetime import timedelta
from pathlib import Path
from unittest import mock

import pytest
from django.contrib import admin
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from gift_manager.admin import EventAdmin
from gift_manager.forms import RelationForm
from gift_manager.models import Event
from gift_manager.models import PermissionLevel
from gift_manager.models import Relation
from gift_manager.services import PermissionService
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import ReceivedGiftFactory
from gift_manager.tests.factories import RelationStatusFactory
from gift_manager.tests.factories import UserFactory
from gift_manager.tests.factories import WishFactory

pytestmark = pytest.mark.django_db

TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "templates/gift_manager"


def _own(user, obj):
    PermissionService.create_or_update_permission(user, obj, permission_level=PermissionLevel.OWNER)
    return obj


class TestGlobalBirthdayEventIsReadOnly:
    """Nobody, superusers included, can change the Birthday event shared by every user."""

    @pytest.fixture
    def superuser(self):
        return UserFactory(is_superuser=True, is_staff=True)

    @pytest.fixture
    def birthday(self):
        return Event.objects.get_birthday_event()

    def test_superuser_only_gets_viewer_access(self, superuser, birthday):
        assert PermissionService.get_effective_permission(birthday, superuser) == (
            PermissionLevel.VIEWER
        )

    def test_superuser_keeps_owner_access_to_other_objects(self, superuser):
        event = Event.objects.create(name="Garden party")

        assert PermissionService.get_effective_permission(event, superuser) == (
            PermissionLevel.OWNER
        )

    def test_superuser_cannot_edit_or_delete_it(self, client, superuser, birthday):
        client.force_login(superuser)
        edit_url = reverse("gift_manager:event_edit", kwargs={"pk": birthday.event_id})
        delete_url = reverse("gift_manager:event_delete", kwargs={"pk": birthday.event_id})

        assert client.post(edit_url, {"name": "Renamed"}).status_code == 403
        assert client.post(delete_url).status_code == 403
        birthday.refresh_from_db()
        assert birthday.name == "Birthday"

    def test_superuser_cannot_bulk_delete_or_inline_edit_it(self, client, superuser, birthday):
        client.force_login(superuser)

        client.post(
            reverse("gift_manager:bulk_operations"),
            json.dumps(
                {
                    "action": "bulk_delete",
                    "entity_type": "event",
                    "entity_ids": [str(birthday.event_id)],
                }
            ),
            content_type="application/json",
        )
        inline = client.post(
            reverse("gift_manager:event_inline_update", kwargs={"pk": birthday.event_id}),
            json.dumps({"field": "name", "value": "Renamed"}),
            content_type="application/json",
        )

        assert inline.status_code == 403
        birthday.refresh_from_db()
        assert birthday.name == "Birthday"

    def test_admin_refuses_to_change_or_delete_it(self, rf, superuser, birthday):
        model_admin = EventAdmin(Event, admin.site)
        request = rf.get("/")
        request.user = superuser
        regular = Event.objects.create(name="Garden party")

        assert model_admin.has_change_permission(request, birthday) is False
        assert model_admin.has_delete_permission(request, birthday) is False
        assert model_admin.has_change_permission(request, regular) is True
        assert model_admin.has_change_permission(request) is True

    def test_detail_page_renders_a_disabled_delete_button(self, client, superuser, birthday):
        client.force_login(superuser)
        delete_url = reverse("gift_manager:event_delete", kwargs={"pk": birthday.event_id})

        content = client.get(
            reverse("gift_manager:event_detail", kwargs={"pk": birthday.event_id})
        ).content.decode()

        assert f'href="{delete_url}"' not in content

    def test_superuser_list_and_detail_offer_no_edit(self, client, superuser, birthday):
        client.force_login(superuser)

        listing = client.get(reverse("gift_manager:events"))
        assert listing.context["user_permissions"][str(birthday.event_id)] == (
            PermissionLevel.VIEWER
        )
        detail = client.get(reverse("gift_manager:event_detail", kwargs={"pk": birthday.event_id}))
        buttons = {button["type"]: button for button in detail.context["action_buttons"]}
        assert buttons["edit"]["enabled"] is False
        assert buttons["delete"]["enabled"] is False


class TestDetailPagesRefreshAfterPanelEdits:
    @pytest.mark.parametrize(
        ("page", "url_name"),
        [
            ("person_detail.html", "gift_manager:person_detail"),
            ("gift_detail.html", "gift_manager:gift_detail"),
            ("event_detail.html", "gift_manager:event_detail"),
        ],
    )
    def test_detail_page_shell_reloads_on_list_update(self, page, url_name):
        template = (TEMPLATE_ROOT / page).read_text(encoding="utf-8")

        # Inline star ratings only refresh the gift history, not the whole page
        assert (
            "hx-trigger=\"list:update[!detail || detail.source !== 'inline_reaction'] from:body\""
            in template
        )
        # Lazy panels inside the shell must not inherit its target and swap the whole page
        assert 'hx-disinherit="*"' in template
        assert f"{{% url '{url_name}' pk=object." in template
        assert "?surface=page" in template

    def test_page_surface_renders_the_full_page_layout_fragment(self, client):
        user = UserFactory()
        person = _own(user, PersonFactory(first_name="Robin"))
        client.force_login(user)
        url = reverse("gift_manager:person_detail", kwargs={"pk": person.person_id})

        response = client.get(f"{url}?surface=page", HTTP_HX_REQUEST="true")

        assert response.status_code == 200
        assert response.context["full_page_detail"] is True
        content = response.content.decode()
        assert "<html" not in content
        # The shell re-creates the history section: it only listens to inline ratings itself
        assert "load, list:update[detail && detail.source === 'inline_reaction'] from:body" in (
            content
        )

    def test_detail_modal_history_still_refreshes_on_every_list_update(self, client):
        user = UserFactory()
        person = _own(user, PersonFactory(first_name="Robin"))
        client.force_login(user)
        url = reverse("gift_manager:person_detail", kwargs={"pk": person.person_id})

        content = client.get(url, HTTP_HX_REQUEST="true").content.decode()

        assert 'hx-trigger="load, list:update from:body"' in content

    def test_page_shell_keeps_the_back_link(self, client):
        user = UserFactory()
        person = _own(user, PersonFactory(first_name="Robin"))
        client.force_login(user)
        url = reverse("gift_manager:person_detail", kwargs={"pk": person.person_id})

        content = client.get(url, {"back": "/en/recipients/"}).content.decode()

        assert "?surface=page&amp;back=/en/recipients/" in content


class TestDashboard:
    @pytest.fixture
    def user(self, client):
        user = UserFactory()
        client.force_login(user)
        return user

    def _awaiting_reaction_plan(self, user):
        plan = Relation.objects.create(
            gift=GiftFactory(name="Thanked Scarf"),
            person=_own(user, PersonFactory()),
            status=RelationStatusFactory(status="Given"),
            due_date=timezone.localdate(),
        )
        return _own(user, plan)

    def test_attention_tile_is_highlighted_only_when_something_needs_attention(self, client, user):
        content = client.get(reverse("gift_manager:home")).content.decode()
        assert "dashboard-summary-tile--attention" not in content

        plan = Relation.objects.create(
            gift=GiftFactory(name="Late Lamp"),
            person=_own(user, PersonFactory()),
            status=RelationStatusFactory(status="Planned"),
            due_date=timezone.localdate() - timedelta(days=2),
        )
        _own(user, plan)

        content = client.get(reverse("gift_manager:home")).content.decode()
        assert "dashboard-summary-tile--attention" in content

    def test_awaiting_reaction_has_its_own_section(self, client, user):
        self._awaiting_reaction_plan(user)

        response = client.get(reverse("gift_manager:home"))

        content = response.content.decode()
        assert response.context["dashboard_summary"]["attention"] == 0
        assert response.context["dashboard_attention_groups"] == []
        assert response.context["dashboard_reaction_group"]["key"] == "reaction"
        assert 'id="dashboard-reaction-heading"' in content
        assert "No gift plans need attention." in content
        reaction_section = content[content.index('id="dashboard-reaction-heading"') :]
        assert "Thanked Scarf" in reaction_section
        needs_attention = content[
            content.index('id="next-action-heading"') : content.index(
                'id="dashboard-reaction-heading"'
            )
        ]
        assert "Thanked Scarf" not in needs_attention


class TestRecipientMemberCounts:
    def test_own_person_counts_as_a_group_member_everywhere(self, client):
        user = UserFactory()
        group = _own(user, PersonGroupFactory(name="Household"))
        me = _own(user, PersonFactory(first_name="Me", account=user))
        partner = _own(user, PersonFactory(first_name="Partner"))
        me.groups.add(group)
        partner.groups.add(group)
        client.force_login(user)

        content = client.get(reverse("gift_manager:recipients")).content.decode()
        assert "2 members" in content
        assert "1 member<" not in content

        groups_view = client.get(reverse("gift_manager:recipients"), {"view": "groups"})
        [row] = groups_view.context["person_group_grid_data"]
        assert row["member_count"] == 2


class TestProfileActiveWishCount:
    def test_received_wishes_are_not_counted_as_active(self, client):
        user = UserFactory()
        WishFactory(wisher=user, title="Still wanted")
        received = WishFactory(wisher=user, title="Already received")
        repeatable = WishFactory(wisher=user, title="Coffee beans")
        WishFactory(wisher=user, title="Archived", is_archived=True)
        ReceivedGiftFactory(recipient_user=user, wish=received, fulfills_wish=True)
        ReceivedGiftFactory(recipient_user=user, wish=repeatable, fulfills_wish=False)
        client.force_login(user)

        response = client.get(reverse("gift_manager:profile_detail"))

        assert response.context["active_wishes_count"] == 2

    def test_a_friends_given_plan_does_not_change_the_count(self, client):
        user = UserFactory()
        wish = WishFactory(wisher=user)
        wish.is_fulfilled = True  # set by a friend's given plan, invisible to the wisher
        wish.save(update_fields=["is_fulfilled"])
        client.force_login(user)

        response = client.get(reverse("gift_manager:profile_detail"))

        assert response.context["active_wishes_count"] == 1


class TestAccountPagesCancelLink:
    @pytest.mark.parametrize("url_name", ["delete_account", "deactivate_account"])
    def test_cancel_goes_back_to_the_profile_without_referer(self, client, url_name):
        client.force_login(UserFactory())

        response = client.get(reverse(url_name))

        assert response.context["cancel_url"] == reverse("gift_manager:profile_detail")

    @pytest.mark.parametrize("url_name", ["delete_account", "deactivate_account"])
    def test_cancel_returns_to_a_same_site_referer(self, client, url_name):
        client.force_login(UserFactory())
        referer = "http://testserver" + reverse("gift_manager:wishlist_list")

        response = client.get(reverse(url_name), HTTP_REFERER=referer)

        assert response.context["cancel_url"] == referer

    def test_cancel_ignores_an_external_referer(self, client):
        client.force_login(UserFactory())

        response = client.get(reverse("delete_account"), HTTP_REFERER="https://evil.example/")

        assert response.context["cancel_url"] == reverse("gift_manager:profile_detail")


def test_delete_logging_does_not_record_request_headers(client):
    user = UserFactory()
    gift = _own(user, GiftFactory(name="Old mug"))
    client.force_login(user)

    with mock.patch("gift_manager.views.base.logger") as logger:
        client.post(reverse("gift_manager:gift_delete", kwargs={"pk": gift.gift_id}))

    logged = " ".join(str(call) for call in logger.mock_calls)
    assert "sessionid" not in logged
    assert "Cookie" not in logged


def test_gift_plan_form_selects_use_the_bootstrap_select_style():
    form = RelationForm(user=UserFactory())

    for name in ("gift", "event", "status"):
        assert "form-select" in form.fields[name].widget.attrs.get("class", ""), name


@pytest.mark.parametrize("button_type", ["edit", "delete"])
def test_action_buttons_are_only_disabled_when_explicitly_disabled(button_type):
    url = f"/en/things/1/{button_type}/"

    enabled = render_to_string(
        "gift_manager/includes/action_buttons.html",
        {"buttons": [{"type": button_type, "url": url}]},
    )
    disabled = render_to_string(
        "gift_manager/includes/action_buttons.html",
        {"buttons": [{"type": button_type, "url": url, "enabled": False}]},
    )

    assert f'href="{url}"' in enabled
    assert f'href="{url}"' not in disabled
    assert "disabled" in disabled
