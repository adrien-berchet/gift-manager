"""Reveal and received-gift flow fixes from the 2026-11-12 QA pass."""

import json
from pathlib import Path

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from gift_manager.forms import ReceivedGiftForm
from gift_manager.forms import RelationRevealForm
from gift_manager.models import PermissionLevel
from gift_manager.models import Relation
from gift_manager.models import RelationStatus
from gift_manager.received_gifts import reveal_plan
from gift_manager.services import PermissionService
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import ReceivedGiftFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = PROJECT_ROOT / "gift_manager/static/gift_manager"
TEMPLATE_ROOT = PROJECT_ROOT / "gift_manager/templates/gift_manager"


def _own(user, obj):
    PermissionService.create_or_update_permission(user, obj, permission_level=PermissionLevel.OWNER)
    return obj


def _status(name):
    return RelationStatus.objects.get_or_create(status_en=name, defaults={"status": name})[0]


@pytest.fixture
def owner():
    return UserFactory()


@pytest.fixture
def recipient_person(owner):
    recipient = UserFactory()
    owner.profile.friends.add(recipient.profile)
    return _own(owner, PersonFactory(first_name="Sam", account=recipient))


@pytest.fixture
def given_plan(owner, recipient_person):
    plan = Relation.objects.create(
        gift=_own(owner, GiftFactory(name="Desk Lamp")),
        person=recipient_person,
        status=_status("Given"),
    )
    return _own(owner, plan)


class TestAlreadyRevealedPlan:
    def _reveal_url(self, plan):
        return reverse("gift_manager:relation_reveal", kwargs={"pk": plan.relation_id})

    def _detail_url(self, plan):
        return reverse("gift_manager:relation_detail", kwargs={"pk": plan.relation_id})

    def test_page_redirects_to_the_plan_with_a_message(self, client, owner, given_plan):
        reveal_plan(given_plan, owner)
        client.force_login(owner)

        response = client.get(self._reveal_url(given_plan))

        assert response.status_code == 302
        assert response.url == self._detail_url(given_plan)
        assert [str(m) for m in get_messages(response.wsgi_request)] == [
            "This gift plan was already revealed."
        ]

    def test_panel_shows_the_revealed_plan(self, client, owner, given_plan):
        reveal_plan(given_plan, owner)
        client.force_login(owner)

        response = client.get(self._reveal_url(given_plan), HTTP_HX_REQUEST="true", follow=True)

        assert response.status_code == 200
        content = response.content.decode()
        assert "This gift plan was already revealed." in content
        assert "relation-reveal-form" not in content

    def test_stale_panel_submit_closes_with_a_notice(self, client, owner, given_plan):
        reveal_plan(given_plan, owner)
        client.force_login(owner)

        response = client.post(
            self._reveal_url(given_plan), {"title": "Again"}, HTTP_HX_REQUEST="true"
        )

        assert response.status_code == 200
        triggers = json.loads(response.headers["HX-Trigger"])
        assert triggers["showNotification"]["message"] == "This gift plan was already revealed."
        assert "offcanvas:close" in triggers

    def test_plan_that_cannot_be_revealed_is_still_forbidden(self, client, owner, given_plan):
        given_plan.status = _status("Planned")
        given_plan.save()
        client.force_login(owner)

        assert client.get(self._reveal_url(given_plan)).status_code == 403


class TestRevealOfferedOnCreate:
    def test_creating_a_plan_as_given_offers_the_reveal(self, client, owner, recipient_person):
        gift = _own(owner, GiftFactory(name="Board Game"))
        client.force_login(owner)

        response = client.post(
            reverse("gift_manager:relation_create"),
            {
                "gift": gift.pk,
                "recipient": f"person:{recipient_person.person_id}",
                "status": _status("Given").pk,
            },
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 200
        plan = Relation.objects.get(gift=gift)
        link = json.loads(response.headers["HX-Trigger"])["showNotification"]["link"]
        assert link["url"] == reverse(
            "gift_manager:relation_reveal", kwargs={"pk": plan.relation_id}
        )

    def test_creating_a_planned_plan_offers_no_reveal(self, client, owner, recipient_person):
        gift = _own(owner, GiftFactory(name="Board Game"))
        client.force_login(owner)

        response = client.post(
            reverse("gift_manager:relation_create"),
            {
                "gift": gift.pk,
                "recipient": f"person:{recipient_person.person_id}",
                "status": _status("Planned").pk,
            },
            HTTP_HX_REQUEST="true",
        )

        triggers = json.loads(response.headers.get("HX-Trigger") or "{}")
        assert "link" not in (triggers.get("showNotification") or {})


class TestRevealPanelMarkup:
    def test_summary_card_uses_theme_aware_surface(self, client, owner, given_plan):
        client.force_login(owner)
        url = reverse("gift_manager:relation_reveal", kwargs={"pk": given_plan.relation_id})

        content = client.get(url, HTTP_HX_REQUEST="true").content.decode()

        assert "reveal-snapshot-summary" in content
        assert "bg-body-tertiary" not in content
        styles = (STATIC_ROOT / "css/form-partials.css").read_text(encoding="utf-8")
        assert ".reveal-snapshot-summary" in styles
        assert "var(--surface-background)" in styles
        assert "var(--text-primary)" in styles

    def test_snapshot_fields_are_stacked_in_the_narrow_panel(self):
        fields = (TEMPLATE_ROOT / "includes/forms/relation_reveal_fields.html").read_text(
            encoding="utf-8"
        )

        assert "col-md-6" not in fields


class TestUrlErrors:
    def test_reveal_form_reports_one_error_for_an_unsafe_link(self):
        form = RelationRevealForm({"title": "Lamp", "url": "javascript:alert(1)"})

        assert not form.is_valid()
        assert len(form.errors["url"]) == 1

    def test_reveal_form_still_rejects_a_link_without_host(self):
        form = RelationRevealForm({"title": "Lamp", "url": "ftp://example.com/file"})

        assert not form.is_valid()
        assert len(form.errors["url"]) == 1


class TestFutureDateWarning:
    def test_date_inputs_carry_the_warning_text(self):
        warning = "This date is in the future."

        received_widget = ReceivedGiftForm(user=UserFactory()).fields["received_on"].widget
        reveal_widget = RelationRevealForm().fields["received_on"].widget

        assert received_widget.attrs["data-future-date-warning"] == warning
        assert reveal_widget.attrs["data-future-date-warning"] == warning

    def test_future_date_is_still_accepted(self):
        user = UserFactory()
        form = ReceivedGiftForm(
            {
                "gift_mode": "new",
                "title": "Early present",
                "received_on": "2099-01-01",
                "giver_mode": "other",
                "giver_label": "Aunt Marie",
                "occasion_mode": "other",
            },
            user=user,
        )

        assert form.is_valid(), form.errors

    def test_form_initializer_registers_the_warning(self):
        script = (STATIC_ROOT / "js/form-initializer.js").read_text(encoding="utf-8")

        assert 'FormInitializer.register("futureDateWarning"' in script
        assert "data-future-date-warning" in script


class TestRevealToastStaysOpen:
    def test_link_toasts_do_not_hide_on_their_own(self):
        script = (STATIC_ROOT / "js/app-shell.js").read_text(encoding="utf-8")

        assert "options.persistent = true" in script
        assert "autohide: !options.persistent" in script


@pytest.mark.parametrize("year", ["99999999999", "0", "-5", "10000"])
def test_received_gift_list_ignores_out_of_range_years(client, year):
    user = UserFactory()
    ReceivedGiftFactory(recipient_user=user, title="Kept visible")
    client.force_login(user)

    response = client.get(reverse("gift_manager:received_gift_list"), {"year": year})

    assert response.status_code == 200
    assert "Kept visible" in response.content.decode()
