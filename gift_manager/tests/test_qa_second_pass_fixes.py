"""Fixes from the second 2026-11-12 QA pass (N1-N7 in docs/qa)."""

import json
from pathlib import Path

import pytest
from django.urls import reverse
from django.utils import timezone

from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import PermissionLevel
from gift_manager.models import Relation
from gift_manager.models import RelationStatus
from gift_manager.services import PermissionService
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import UserFactory
from gift_manager.tests.factories import WishFactory

pytestmark = pytest.mark.django_db

STATIC_ROOT = Path(__file__).resolve().parents[1] / "static/gift_manager"
LEAVE_LABEL = "Remove my access"


def _grant(user, obj, level=PermissionLevel.OWNER):
    PermissionService.create_or_update_permission(user, obj, permission_level=level)
    return obj


def _status(name):
    return RelationStatus.objects.get_or_create(status_en=name, defaults={"status": name})[0]


@pytest.fixture
def owner():
    return UserFactory()


@pytest.fixture
def viewer():
    return UserFactory()


class TestFutureDateWarningContrast:
    def test_warning_uses_theme_aware_colours(self):
        styles = (STATIC_ROOT / "css/form-partials.css").read_text(encoding="utf-8")
        script = (STATIC_ROOT / "js/form-initializer.js").read_text(encoding="utf-8")

        assert ".future-date-warning {" in styles
        assert '[data-theme="dark"] .future-date-warning' in styles
        assert "text-warning-emphasis" not in script


class TestViewerRemovesTheirAccess:
    """A viewer's Delete becomes "Remove my access" and only drops their own access."""

    @pytest.fixture
    def shared_objects(self, owner, viewer):
        person = _grant(owner, PersonFactory(first_name="Mom"))
        gift = _grant(owner, GiftFactory(name="Novel"))
        event = _grant(owner, Event.objects.create(name="Christmas"))
        group = _grant(owner, PersonGroupFactory(name="Family"))
        plan = _grant(
            owner, Relation.objects.create(person=person, gift=gift, status=_status("Idea"))
        )
        objects = {
            "person": (person, person.person_id),
            "gift": (gift, gift.gift_id),
            "event": (event, event.event_id),
            "person_group": (group, group.group_id),
            "relation": (plan, plan.relation_id),
        }
        for obj, _pk in objects.values():
            _grant(viewer, obj, PermissionLevel.VIEWER)
        return objects

    @pytest.mark.parametrize("kind", ["person", "gift", "event", "person_group", "relation"])
    def test_detail_page_offers_remove_my_access(self, client, viewer, shared_objects, kind):
        _obj, pk = shared_objects[kind]
        client.force_login(viewer)

        response = client.get(reverse(f"gift_manager:{kind}_detail", kwargs={"pk": pk}))

        buttons = [
            b for b in response.context["action_buttons"] if b["type"] in {"delete", "leave"}
        ]
        assert len(buttons) == 1
        delete_url = reverse(f"gift_manager:{kind}_delete", kwargs={"pk": pk})
        assert buttons[0]["type"] == "leave"
        assert buttons[0]["label"] == LEAVE_LABEL
        assert buttons[0]["url"] == f"{delete_url}?intent=leave_access"
        assert f'href="{delete_url}?intent=leave_access"' in response.content.decode()

    def test_owner_of_an_unshared_object_gets_delete(self, client, owner):
        gift = _grant(owner, GiftFactory(name="Mine only"))
        client.force_login(owner)

        response = client.get(reverse("gift_manager:gift_detail", kwargs={"pk": gift.gift_id}))

        [button] = [
            b for b in response.context["action_buttons"] if b["type"] in {"delete", "leave"}
        ]
        assert button["type"] == "delete"
        assert button.get("enabled", True) is True

    def test_sole_owner_of_a_shared_object_cannot_delete_it(self, client, owner, shared_objects):
        _gift, pk = shared_objects["gift"]
        client.force_login(owner)

        response = client.get(reverse("gift_manager:gift_detail", kwargs={"pk": pk}))

        [button] = [
            b for b in response.context["action_buttons"] if b["type"] in {"delete", "leave"}
        ]
        assert button["enabled"] is False
        assert button["tooltip"] == "At least one owner is required."
        delete_url = reverse("gift_manager:gift_delete", kwargs={"pk": pk})
        assert client.get(delete_url).status_code == 403

    def test_editor_of_a_shared_object_removes_their_access(self, client, owner, shared_objects):
        gift, pk = shared_objects["gift"]
        editor = UserFactory()
        _grant(editor, gift, PermissionLevel.EDITOR)
        client.force_login(editor)
        delete_url = reverse("gift_manager:gift_delete", kwargs={"pk": pk})

        response = client.get(reverse("gift_manager:gift_detail", kwargs={"pk": pk}))
        [button] = [
            b for b in response.context["action_buttons"] if b["type"] in {"delete", "leave"}
        ]
        assert button["type"] == "leave"
        # Even without the intent, the confirmation says what the POST does: only unshare
        page = client.get(delete_url).content.decode()
        assert LEAVE_LABEL in page
        assert client.post(delete_url).status_code == 302
        assert type(gift).objects.filter(pk=gift.pk).exists()
        assert PermissionService.get_permission(gift, editor) == PermissionLevel.NONE

    def test_public_tag_cannot_be_deleted_or_left(self, client, owner, viewer):
        from gift_manager.models import GiftTag

        tag = GiftTag.objects.create(name="Everyone", is_public=True)
        _grant(viewer, tag, PermissionLevel.VIEWER)
        client.force_login(viewer)

        response = client.get(reverse("gift_manager:gift_tag_detail", kwargs={"pk": tag.tag_id}))

        assert response.context["delete_mode"] == "none"
        content = response.content.decode()
        assert "intent=leave_access" not in content
        assert f"</i>{LEAVE_LABEL}" not in content.replace("\n", "").replace("  ", "")
        assert "A public tag cannot be deleted or left." in content

    def test_confirmation_page_says_remove_my_access(self, client, viewer, shared_objects):
        person, pk = shared_objects["person"]
        client.force_login(viewer)
        url = reverse("gift_manager:person_delete", kwargs={"pk": pk})

        content = client.get(url, {"intent": "leave_access"}).content.decode()

        assert LEAVE_LABEL in content
        assert "Are you sure you want to delete" not in content
        assert 'name="intent" value="leave_access"' in content

        response = client.post(url, {"intent": "leave_access"})
        assert response.status_code == 302
        assert PermissionService.get_permission(person, viewer) == PermissionLevel.NONE
        assert type(person).objects.filter(pk=person.pk).exists()

    def test_confirmation_modal_says_remove_my_access(self, client, viewer, shared_objects):
        _gift, pk = shared_objects["gift"]
        client.force_login(viewer)
        url = reverse("gift_manager:gift_delete", kwargs={"pk": pk})

        content = client.get(
            url, {"intent": "leave_access"}, HTTP_HX_REQUEST="true"
        ).content.decode()

        assert f'data-confirm-label="{LEAVE_LABEL}"' in content
        assert f'data-confirm-title="{LEAVE_LABEL}"' in content
        assert 'name="intent" value="leave_access"' in content
        assert "This action cannot be undone." not in content
        # The gift's plan is not affected by leaving, so it is not listed
        assert "This will also affect" not in content

    def test_detail_panel_offers_remove_my_access(self, client, viewer, shared_objects):
        _gift, pk = shared_objects["gift"]
        client.force_login(viewer)

        content = client.get(
            reverse("gift_manager:gift_detail", kwargs={"pk": pk}), HTTP_HX_REQUEST="true"
        ).content.decode()

        delete_url = reverse("gift_manager:gift_delete", kwargs={"pk": pk})
        assert f'data-delete-url="{delete_url}?intent=leave_access"' in content
        assert LEAVE_LABEL in content

    def test_global_birthday_offers_neither(self, client, viewer):
        birthday = Event.objects.get_birthday_event()
        client.force_login(viewer)

        response = client.get(
            reverse("gift_manager:event_detail", kwargs={"pk": birthday.event_id})
        )

        [button] = [
            b for b in response.context["action_buttons"] if b["type"] in {"delete", "leave"}
        ]
        assert button["type"] == "delete"
        assert button["enabled"] is False


class TestPlanListsHideEditFromViewers:
    @pytest.mark.parametrize("kind", ["event", "gift"])
    def test_viewer_sees_no_edit_or_delete_for_plans(self, client, owner, viewer, kind):
        gift = _grant(owner, GiftFactory(name="Lamp"))
        event = _grant(owner, Event.objects.create(name="Housewarming"))
        plan = _grant(
            owner,
            Relation.objects.create(
                person=_grant(owner, PersonFactory()),
                gift=gift,
                event=event,
                status=_status("Idea"),
            ),
        )
        _grant(viewer, plan, PermissionLevel.VIEWER)
        target = gift if kind == "gift" else event
        _grant(viewer, target, PermissionLevel.VIEWER)
        pk = target.gift_id if kind == "gift" else target.event_id
        edit_url = reverse("gift_manager:relation_edit", kwargs={"pk": plan.relation_id})
        delete_url = reverse("gift_manager:relation_delete", kwargs={"pk": plan.relation_id})
        detail_url = reverse(f"gift_manager:{kind}_detail", kwargs={"pk": pk})

        client.force_login(viewer)
        viewer_page = client.get(detail_url).content.decode()
        client.force_login(owner)
        owner_page = client.get(detail_url).content.decode()

        leave_link = f'href="{delete_url}?intent=leave_access"'
        assert edit_url not in viewer_page
        assert f'href="{delete_url}"' not in viewer_page
        # The plan stays shared with its owner: the viewer can only remove their own access
        assert leave_link in viewer_page
        assert edit_url in owner_page
        # Its only owner cannot delete it while it is shared, and has no friend to hand it to
        assert f'href="{delete_url}"' not in owner_page
        assert leave_link not in owner_page


class TestPlanLinksFollowPlanRights:
    """Person and group pages show a plan's Edit link only to users who can edit that plan."""

    def test_person_editor_who_only_views_the_plan_gets_no_edit_link(self, client, owner, viewer):
        person = _grant(owner, PersonFactory())
        _grant(viewer, person, PermissionLevel.EDITOR)
        plan = _grant(
            owner,
            Relation.objects.create(person=person, gift=GiftFactory(), status=_status("Idea")),
        )
        _grant(viewer, plan, PermissionLevel.VIEWER)
        edit_url = reverse("gift_manager:relation_edit", kwargs={"pk": plan.relation_id})
        url = reverse("gift_manager:person_detail", kwargs={"pk": person.person_id})

        client.force_login(viewer)
        assert edit_url not in client.get(url).content.decode()
        client.force_login(owner)
        assert edit_url in client.get(url).content.decode()

    def test_group_page_hides_edit_for_plans_the_user_only_views(self, client, owner, viewer):
        group = _grant(owner, PersonGroupFactory(name="Family"))
        _grant(viewer, group, PermissionLevel.VIEWER)
        plan = _grant(
            owner,
            Relation.objects.create(group=group, gift=GiftFactory(), status=_status("Idea")),
        )
        _grant(viewer, plan, PermissionLevel.VIEWER)
        edit_url = reverse("gift_manager:relation_edit", kwargs={"pk": plan.relation_id})
        url = reverse("gift_manager:person_group_detail", kwargs={"pk": group.group_id})
        # The side panel lists the plans (the full page uses permission-aware grids)
        panel = {"HTTP_HX_REQUEST": "true"}

        client.force_login(viewer)
        assert edit_url not in client.get(url, **panel).content.decode()
        client.force_login(owner)
        assert edit_url in client.get(url, **panel).content.decode()


class TestUnassignedGifts:
    @pytest.fixture
    def gifts(self, owner):
        planned = _grant(owner, GiftFactory(name="Planned scarf"))
        idle = _grant(owner, GiftFactory(name="Idle puzzle"))
        _grant(
            owner,
            Relation.objects.create(
                person=_grant(owner, PersonFactory()), gift=planned, status=_status("Idea")
            ),
        )
        return planned, idle

    def test_unassigned_gifts_do_not_need_attention(self, client, owner, gifts):
        client.force_login(owner)

        response = client.get(reverse("gift_manager:home"))

        assert response.context["dashboard_summary"]["unassigned_gifts"] == 1
        assert response.context["dashboard_summary"]["attention"] == 0
        content = response.content.decode()
        assert "dashboard-summary-tile--attention" not in content
        assert f'href="{reverse("gift_manager:gifts")}?unassigned=1"' in content

    def test_gift_list_can_show_only_gifts_not_in_a_plan(self, client, owner, gifts):
        client.force_login(owner)
        url = reverse("gift_manager:gifts")

        everything = client.get(url)
        unassigned = client.get(url, {"unassigned": "1"})

        names = lambda response: {row[1] for row in response.context["grid_data"]}  # noqa: E731
        assert names(everything) == {"Planned scarf", "Idle puzzle"}
        assert names(unassigned) == {"Idle puzzle"}
        assert unassigned.context["show_unassigned"] is True
        content = unassigned.content.decode()
        assert f'href="{url}?unassigned=1"' in content
        assert 'aria-current="page"' in content


class TestGiverWishBadge:
    def test_given_plan_shows_given_instead_of_planned(self, client):
        from gift_manager import wishlist

        wisher, friend = UserFactory(), UserFactory()
        wisher.profile.friends.add(friend.profile)
        wish = WishFactory(wisher=wisher, title="Kettle")
        person = _grant(friend, PersonFactory(account=wisher))
        plan = wishlist.plan_wish(wish, friend, person)
        plan.status = _status("Given")
        plan.status_changed_at = timezone.now()
        plan.save()
        client.force_login(friend)

        response = client.get(
            reverse("gift_manager:person_detail", kwargs={"pk": person.person_id})
        )

        [item] = response.context["friend_wishes"]
        assert item.planned_is_given is True
        content = response.content.decode()
        wish_html = content[content.index(f'id="wish-item-{wish.wish_id}"') :]
        wish_html = wish_html[: wish_html.index("<!-- Actions -->")]
        compact = " ".join(wish_html.split()).replace("> ", ">").replace(" <", "<")
        assert ">Given</a>" in compact
        assert ">Planned</a>" not in compact


def test_person_without_plans_in_progress_says_so(client, owner):
    person = _grant(owner, PersonFactory())
    client.force_login(owner)

    content = client.get(
        reverse("gift_manager:person_detail", kwargs={"pk": person.person_id})
    ).content.decode()

    assert "No gift plans in progress for this person." in content
    assert "No gift plans found for this person." not in content


def test_creating_a_plan_as_given_says_it_was_created(client, owner):
    recipient = UserFactory()
    owner.profile.friends.add(recipient.profile)
    person = _grant(owner, PersonFactory(account=recipient))
    gift = _grant(owner, GiftFactory(name="Board game"))
    client.force_login(owner)

    response = client.post(
        reverse("gift_manager:relation_create"),
        {"gift": gift.pk, "recipient": f"person:{person.person_id}", "status": _status("Given").pk},
        HTTP_HX_REQUEST="true",
    )

    notification = json.loads(response.headers["HX-Trigger"])["showNotification"]
    assert notification["message"] == "Gift plan created."
    assert "link" in notification
    assert Gift.objects.filter(pk=gift.pk).exists()
