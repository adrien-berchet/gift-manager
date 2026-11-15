"""Tests of the Secret Santa organizer pages."""

import random
import uuid

import pytest
from django.core import mail
from django.core.cache import cache
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gift_manager.secret_santa import service
from gift_manager.secret_santa.models import Exchange
from gift_manager.secret_santa.models import ExchangeParticipant
from gift_manager.secret_santa.models import ExclusionSet
from gift_manager.tests.factories import ExchangeFactory
from gift_manager.tests.factories import ExchangeParticipantFactory
from gift_manager.tests.factories import ExclusionSetFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_quota():
    cache.clear()
    yield
    cache.clear()


def seeded(seed):
    return random.Random(seed)  # noqa: S311 - reproducible test


@pytest.fixture
def exchange(user):
    exchange = ExchangeFactory(organizer=user, name="Family 2026")
    for name in ("Anna", "Bob", "Carl", "Dora"):
        ExchangeParticipantFactory(exchange=exchange, name=name)
    return exchange


@pytest.fixture
def drawn_exchange(exchange):
    service.run_draw(exchange, rng=seeded(1))
    return exchange


@pytest.fixture
def other_client():
    other = UserFactory()
    client = Client()
    client.force_login(other)
    return client


def url(name, exchange, *extra):
    return reverse(f"gift_manager:{name}", args=[exchange.exchange_id, *extra])


def organizer_urls(exchange):
    participant = exchange.participants.first()
    exclusion_set = ExclusionSetFactory(
        exchange=exchange, participants=list(exchange.participants.all()[:2])
    )
    pid = participant.participant_id
    return [
        ("get", url("secret_santa_detail", exchange)),
        ("get", url("secret_santa_edit", exchange)),
        ("post", url("secret_santa_delete", exchange)),
        ("post", url("secret_santa_participant_add", exchange)),
        ("post", url("secret_santa_participant_import", exchange)),
        ("post", url("secret_santa_participant_edit", exchange, pid)),
        ("post", url("secret_santa_participant_remove", exchange, pid)),
        ("post", url("secret_santa_send_again", exchange, pid)),
        ("post", url("secret_santa_show_link", exchange, pid)),
        ("post", url("secret_santa_regenerate_link", exchange, pid)),
        ("post", url("secret_santa_set_save", exchange)),
        ("post", url("secret_santa_set_delete", exchange, exclusion_set.set_id)),
        ("post", url("secret_santa_draw", exchange)),
        ("post", url("secret_santa_pairings", exchange)),
    ]


def messages_of(response):
    return [str(message) for message in response.context["messages"]]


def test_every_organizer_url_requires_login(client, exchange):
    urls = [
        *organizer_urls(exchange),
        ("get", reverse("gift_manager:secret_santa_list")),
        ("get", reverse("gift_manager:secret_santa_create")),
    ]
    for method, target in urls:
        response = getattr(client, method)(target, {"confirm": "1"})
        assert response.status_code == 302, target
        assert "/login/" in response["Location"]


def test_another_user_gets_404_on_every_organizer_url(other_client, exchange):
    for method, target in organizer_urls(exchange):
        response = getattr(other_client, method)(target, {"confirm": "1"})
        assert response.status_code == 404, target
    assert Exchange.objects.filter(pk=exchange.pk).exists()


def test_a_participant_or_set_of_another_exchange_is_404(authenticated_client, exchange, user):
    mine_too = ExchangeFactory(organizer=user)
    foreign = ExchangeParticipantFactory(exchange=mine_too)
    foreign_set = ExclusionSetFactory(exchange=mine_too)

    for name in ("secret_santa_participant_edit", "secret_santa_show_link"):
        response = authenticated_client.post(
            url(name, exchange, foreign.participant_id), {"confirm": "1", "name": "X"}
        )
        assert response.status_code == 404
    response = authenticated_client.post(
        url("secret_santa_set_delete", exchange, foreign_set.set_id)
    )
    assert response.status_code == 404
    response = authenticated_client.post(
        url("secret_santa_set_save", exchange),
        {"set_id": str(foreign_set.set_id), "name": "X", "participants": []},
    )
    assert ExclusionSet.objects.filter(pk=foreign_set.pk, exchange=mine_too).exists()


def test_list_shows_only_my_exchanges(authenticated_client, exchange):
    ExchangeFactory(name="Not mine")

    content = authenticated_client.get(reverse("gift_manager:secret_santa_list")).content.decode()

    assert "Family 2026" in content
    assert "Not mine" not in content


def test_create_exchange_and_take_part(authenticated_client, user):
    response = authenticated_client.post(
        reverse("gift_manager:secret_santa_create"),
        {
            "name": "Office",
            "exchange_date": "2026-12-20",
            "budget": "15",
            "guidelines": "Be nice",
            "organizer_takes_part": "on",
        },
    )

    exchange = Exchange.objects.get(name="Office")
    assert response.status_code == 302
    assert response["Location"] == url("secret_santa_detail", exchange)
    assert exchange.organizer == user
    assert exchange.participants.get().linked_account == user


def test_create_form_shows_errors(authenticated_client):
    response = authenticated_client.post(reverse("gift_manager:secret_santa_create"), {})
    assert response.status_code == 200
    assert not Exchange.objects.exists()


def test_edit_exchange(authenticated_client, exchange):
    response = authenticated_client.post(
        url("secret_santa_edit", exchange),
        {"name": "Renamed", "exchange_date": "2026-12-24", "no_mutual_draw": "on"},
    )
    assert response.status_code == 302
    exchange.refresh_from_db()
    assert exchange.name == "Renamed"
    assert exchange.no_mutual_draw


def test_mutual_switch_is_locked_after_the_draw(authenticated_client, drawn_exchange):
    authenticated_client.post(
        url("secret_santa_edit", drawn_exchange),
        {"name": "Renamed", "exchange_date": "2026-12-24", "no_mutual_draw": "on"},
    )
    drawn_exchange.refresh_from_db()
    assert drawn_exchange.name == "Renamed"
    assert not drawn_exchange.no_mutual_draw


def test_add_edit_remove_participant(authenticated_client, exchange):
    authenticated_client.post(
        url("secret_santa_participant_add", exchange), {"name": "Eve", "email": "eve@example.com"}
    )
    eve = exchange.participants.get(name="Eve")
    assert eve.email == "eve@example.com"

    authenticated_client.post(
        url("secret_santa_participant_edit", exchange, eve.participant_id),
        {"name": "Evelyn", "email": ""},
    )
    eve.refresh_from_db()
    assert (eve.name, eve.email) == ("Evelyn", None)

    authenticated_client.post(url("secret_santa_participant_remove", exchange, eve.participant_id))
    assert not exchange.participants.filter(pk=eve.pk).exists()


def test_duplicate_name_shows_an_error_and_saves_nothing(authenticated_client, exchange):
    response = authenticated_client.post(
        url("secret_santa_participant_add", exchange), {"name": "anna"}, follow=True
    )

    assert "Two participants cannot have the same name." in messages_of(response)
    assert exchange.participants.count() == 4


def test_invalid_email_is_refused(authenticated_client, exchange):
    response = authenticated_client.post(
        url("secret_santa_participant_add", exchange),
        {"name": "Eve", "email": "not-an-email"},
        follow=True,
    )
    assert messages_of(response)
    assert not exchange.participants.filter(name="Eve").exists()


def test_import_group_and_persons_reports_added_and_skipped(authenticated_client, exchange, user):
    group = PersonGroupFactory(shared_with=[user])
    in_group = PersonFactory(first_name="Gina", family_name="G", owner=user, groups=[group])
    alone = PersonFactory(first_name="Hugo", family_name="H", owner=user)
    already = PersonFactory(first_name="Anna", family_name="", owner=user, groups=[group])

    response = authenticated_client.post(
        url("secret_santa_participant_import", exchange),
        {"group": str(group.group_id), "persons": [str(alone.person_id), str(in_group.person_id)]},
        follow=True,
    )

    assert "2 added, 2 already there." in messages_of(response)
    assert set(exchange.participants.values_list("name", flat=True)) == {
        "Anna",
        "Bob",
        "Carl",
        "Dora",
        "Gina G",
        "Hugo H",
    }
    assert not exchange.participants.filter(source_person=already).exists()


def test_import_refuses_a_group_of_another_user(authenticated_client, exchange):
    group = PersonGroupFactory()
    PersonFactory(groups=[group])

    response = authenticated_client.post(
        url("secret_santa_participant_import", exchange),
        {"group": str(group.group_id)},
        follow=True,
    )

    assert messages_of(response)
    assert exchange.participants.count() == 4


def test_exclusion_set_with_participants_of_another_exchange_is_refused(
    authenticated_client, exchange
):
    anna = exchange.participants.get(name="Anna")
    foreigner = ExchangeParticipantFactory()

    authenticated_client.post(
        url("secret_santa_set_save", exchange),
        {
            "name": "Mixed",
            "participants": [str(anna.participant_id), str(foreigner.participant_id)],
        },
    )

    assert not exchange.exclusion_sets.exists()


def test_exclusion_set_create_edit_delete(authenticated_client, exchange):
    anna, bob, carl = (exchange.participants.get(name=n) for n in ("Anna", "Bob", "Carl"))
    authenticated_client.post(
        url("secret_santa_set_save", exchange),
        {"name": "Couple", "participants": [str(anna.participant_id), str(bob.participant_id)]},
    )
    exclusion_set = exchange.exclusion_sets.get()

    authenticated_client.post(
        url("secret_santa_set_save", exchange),
        {
            "set_id": str(exclusion_set.set_id),
            "name": "Trio",
            "participants": [str(p.participant_id) for p in (anna, bob, carl)],
        },
    )
    exclusion_set.refresh_from_db()
    assert exclusion_set.name == "Trio"
    assert exclusion_set.participants.count() == 3

    authenticated_client.post(url("secret_santa_set_delete", exchange, exclusion_set.set_id))
    assert not exchange.exclusion_sets.exists()


def test_draw_sends_emails_after_commit_and_reports(
    authenticated_client, exchange, django_capture_on_commit_callbacks
):
    ExchangeParticipant.objects.filter(exchange=exchange, name="Dora").update(email_address=None)

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = authenticated_client.post(url("secret_santa_draw", exchange))

    assert response.status_code == 302
    assert len(callbacks) == 1
    exchange.refresh_from_db()
    assert exchange.status == Exchange.Status.DRAWN
    assert len(mail.outbox) == 3
    assert not exchange.participants.filter(gives_to__isnull=True).exists()


def test_draw_flashes_what_happened_to_the_emails(authenticated_client, exchange, monkeypatch):
    # Run the after-commit callbacks at once, as a request without an outer transaction would
    monkeypatch.setattr("django.db.transaction.on_commit", lambda func, *a, **k: func())
    ExchangeParticipant.objects.filter(exchange=exchange, name="Dora").update(email_address=None)

    response = authenticated_client.post(url("secret_santa_draw", exchange), follow=True)

    found = messages_of(response)
    assert "The draw is done." in found
    assert "3 emails sent." in found
    assert "No email for Dora: hand out their personal link." in found


def test_impossible_draw_shows_the_message_and_stays_draft(authenticated_client, exchange):
    ExclusionSetFactory(exchange=exchange, participants=list(exchange.participants.all()[:3]))

    response = authenticated_client.post(url("secret_santa_draw", exchange), follow=True)

    assert "No draw is possible with these exclusions." in messages_of(response)
    exchange.refresh_from_db()
    assert exchange.status == Exchange.Status.DRAFT
    assert not mail.outbox


def test_detail_page_never_contains_a_pairing(authenticated_client, drawn_exchange):
    ExclusionSetFactory(
        exchange=drawn_exchange, participants=list(drawn_exchange.participants.all()[:2])
    )
    detail_url = url("secret_santa_detail", drawn_exchange)

    with CaptureQueriesContext(connection) as queries:
        response = authenticated_client.get(detail_url)

    content = response.content.decode()
    assert response.status_code == 200
    assert "gives to" not in content
    for participant in drawn_exchange.participants.select_related("gives_to"):
        assert f"{participant.name} gives to" not in content
    exchange_queries = [
        q["sql"] for q in queries.captured_queries if "secret" in q["sql"] or "exchange" in q["sql"]
    ]
    assert exchange_queries
    assert all("gives_to_id" not in sql for sql in exchange_queries)


def test_show_link_needs_confirmation_and_post(authenticated_client, drawn_exchange):
    participant = drawn_exchange.participants.first()
    target = url("secret_santa_show_link", drawn_exchange, participant.participant_id)

    assert authenticated_client.get(target).status_code == 405
    assert authenticated_client.post(target).status_code == 400


def test_show_link_returns_the_link_uncached(authenticated_client, drawn_exchange):
    participant = drawn_exchange.participants.first()
    target = url("secret_santa_show_link", drawn_exchange, participant.participant_id)

    partial = authenticated_client.post(target, {"confirm": "1"}, HTTP_HX_REQUEST="true")
    page = authenticated_client.post(target, {"confirm": "1"})

    assert participant.token in partial.content.decode()
    assert "<nav" not in partial.content.decode()
    assert partial["Cache-Control"] == "private, no-store"
    assert participant.token in page.content.decode()
    assert "<nav" in page.content.decode()
    assert page["Cache-Control"] == "private, no-store"


def test_pairings_need_confirmation_and_list_everyone(authenticated_client, drawn_exchange):
    target = url("secret_santa_pairings", drawn_exchange)
    assert authenticated_client.get(target).status_code == 405
    assert authenticated_client.post(target).status_code == 400

    content = authenticated_client.post(
        target, {"confirm": "1"}, HTTP_HX_REQUEST="true"
    ).content.decode()

    for participant in drawn_exchange.participants.select_related("gives_to"):
        assert f"{participant.name} gives to {participant.gives_to.name}" in content


def test_pairings_warning_is_stronger_when_the_organizer_takes_part(
    authenticated_client, drawn_exchange, user
):
    detail_url = url("secret_santa_detail", drawn_exchange)
    assert "secret-santa-self-warning" not in authenticated_client.get(detail_url).content.decode()

    ExchangeParticipant.objects.filter(exchange=drawn_exchange, name="Anna").update(
        linked_account=user
    )
    assert "secret-santa-self-warning" in authenticated_client.get(detail_url).content.decode()


def test_regenerate_link_kills_the_old_one(authenticated_client, client, drawn_exchange):
    participant = drawn_exchange.participants.first()
    old = participant.token

    authenticated_client.post(
        url("secret_santa_regenerate_link", drawn_exchange, participant.participant_id)
    )

    participant.refresh_from_db()
    page = "gift_manager:secret_santa_participant"
    assert Client().get(reverse(page, args=[old])).status_code == 404
    assert Client().get(reverse(page, args=[participant.token])).status_code == 200


def test_send_again_and_its_cooldown(authenticated_client, drawn_exchange):
    participant = drawn_exchange.participants.first()
    target = url("secret_santa_send_again", drawn_exchange, participant.participant_id)

    first = authenticated_client.post(target, follow=True)
    second = authenticated_client.post(target, follow=True)

    assert "1 email sent." in messages_of(first)
    assert "Wait a few minutes before sending this email again." in messages_of(second)
    assert len(mail.outbox) == 1


def test_redraw_changes_assignments_and_resends(authenticated_client, drawn_exchange, monkeypatch):
    monkeypatch.setattr("django.db.transaction.on_commit", lambda func, *a, **k: func())
    drawn_at = Exchange.objects.get(pk=drawn_exchange.pk).drawn_at

    response = authenticated_client.post(url("secret_santa_draw", drawn_exchange), follow=True)

    assert "The draw was done again. Everyone has a new assignment." in messages_of(response)
    assert len(mail.outbox) == 4
    assert Exchange.objects.get(pk=drawn_exchange.pk).drawn_at > drawn_at


def test_participants_cannot_be_added_after_the_draw_but_can_be_renamed(
    authenticated_client, drawn_exchange
):
    response = authenticated_client.post(
        url("secret_santa_participant_add", drawn_exchange), {"name": "Late"}, follow=True
    )
    assert any("The draw is done" in m for m in messages_of(response))
    assert not drawn_exchange.participants.filter(name="Late").exists()

    anna = drawn_exchange.participants.get(name="Anna")
    authenticated_client.post(
        url("secret_santa_participant_edit", drawn_exchange, anna.participant_id),
        {"name": "Annabelle", "email": "annabelle@example.com"},
    )
    anna.refresh_from_db()
    assert anna.name == "Annabelle"


def test_delete_exchange(authenticated_client, exchange):
    response = authenticated_client.post(url("secret_santa_delete", exchange))

    assert response.status_code == 302
    assert response["Location"] == reverse("gift_manager:secret_santa_list")
    assert not Exchange.objects.exists()


def test_more_menu_links_to_secret_santa(authenticated_client):
    content = authenticated_client.get(reverse("gift_manager:home")).content.decode()
    assert reverse("gift_manager:secret_santa_list") in content


def test_unknown_exchange_is_404(authenticated_client):
    response = authenticated_client.get(
        reverse("gift_manager:secret_santa_detail", args=[uuid.uuid4()])
    )
    assert response.status_code == 404


def test_invite_and_put_back_urls_are_scoped(other_client, exchange):
    participant = exchange.participants.first()
    assert other_client.post(url("secret_santa_invite", exchange)).status_code == 404
    response = other_client.post(url("secret_santa_put_back", exchange, participant.participant_id))
    assert response.status_code == 404


def test_invite_sends_the_personal_links(authenticated_client, exchange):
    response = authenticated_client.post(url("secret_santa_invite", exchange), follow=True)

    assert "4 emails sent." in messages_of(response)
    assert len(mail.outbox) == 4
    assert "Invited" in response.content.decode()
    again = authenticated_client.post(url("secret_santa_invite", exchange), follow=True)
    assert "Everyone with an email address has their link." in messages_of(again)


def test_declined_participant_is_shown_and_can_be_put_back(authenticated_client, exchange):
    dora = exchange.participants.get(name="Dora")
    ExchangeParticipant.objects.filter(pk=dora.pk).update(declined=True)

    content = authenticated_client.get(url("secret_santa_detail", exchange)).content.decode()
    assert "secret-santa-declined" in content
    assert url("secret_santa_put_back", exchange, dora.participant_id) in content

    authenticated_client.post(url("secret_santa_put_back", exchange, dora.participant_id))
    dora.refresh_from_db()
    assert not dora.declined


def test_draw_button_counts_non_declined(authenticated_client, exchange):
    ExchangeParticipant.objects.filter(exchange=exchange, name__in=["Carl", "Dora"]).update(
        declined=True
    )
    content = authenticated_client.get(url("secret_santa_detail", exchange)).content.decode()
    assert "secret-santa-draw-button" not in content


def test_pairings_leave_out_declined(authenticated_client, exchange):
    ExchangeParticipant.objects.filter(exchange=exchange, name="Dora").update(declined=True)
    service.run_draw(exchange, rng=seeded(1))

    content = authenticated_client.post(
        url("secret_santa_pairings", exchange), {"confirm": "1"}, HTTP_HX_REQUEST="true"
    ).content.decode()

    assert content.count('class="secret-santa-pairing"') == 3
    assert "Dora gives to" not in content


def test_create_from_a_previous_exchange(authenticated_client, exchange):
    target = reverse("gift_manager:secret_santa_create") + f"?from={exchange.exchange_id}"
    page = authenticated_client.get(target).content.decode()
    assert 'name="no_repeat_draw"' in page
    assert "Family 2026" in page

    response = authenticated_client.post(
        target, {"name": "Family 2027", "exchange_date": "2027-12-24", "no_repeat_draw": "on"}
    )

    copy = Exchange.objects.get(name="Family 2027")
    assert response["Location"] == url("secret_santa_detail", copy)
    assert copy.previous_exchange == exchange
    assert copy.no_repeat_draw
    assert copy.participants.count() == 4


def test_create_from_an_exchange_of_another_user_is_404(authenticated_client):
    foreign = ExchangeFactory()
    target = reverse("gift_manager:secret_santa_create") + f"?from={foreign.exchange_id}"
    assert authenticated_client.get(target).status_code == 404
    assert (
        authenticated_client.get(
            reverse("gift_manager:secret_santa_create") + "?from=x"
        ).status_code
        == 404
    )
