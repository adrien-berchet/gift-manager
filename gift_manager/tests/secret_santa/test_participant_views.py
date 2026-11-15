"""Tests of the Secret Santa participant pages (personal page and stop-emails page)."""

import random

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gift_manager.secret_santa import emails
from gift_manager.secret_santa import service
from gift_manager.secret_santa.models import Exchange
from gift_manager.secret_santa.models import ExchangeParticipant
from gift_manager.tests.factories import ExchangeFactory
from gift_manager.tests.factories import ExchangeParticipantFactory
from gift_manager.tests.factories import UserFactory
from gift_manager.tests.factories import WishFactory

pytestmark = pytest.mark.django_db


def page(token):
    return reverse("gift_manager:secret_santa_participant", args=[token])


def seeded(seed):
    return random.Random(seed)  # noqa: S311 - reproducible test


@pytest.fixture
def exchange():
    exchange = ExchangeFactory(name="Family 2026", guidelines="No socks\nPlease")
    for name in ("Zoe", "anna", "Bob", "Carl"):
        ExchangeParticipantFactory(exchange=exchange, name=name)
    return exchange


@pytest.fixture
def drawn_exchange(exchange):
    service.run_draw(exchange, rng=seeded(1))
    return exchange


def text(response):
    return response.content.decode()


def test_page_before_the_draw(client, exchange):
    me = exchange.participants.get(name="Bob")

    response = client.get(page(me.token))

    assert response.status_code == 200
    content = text(response)
    assert "Family 2026" in content
    assert "The draw has not been done yet." in content
    assert "You give a gift to" not in content
    # Alphabetical, ignoring case
    positions = [content.index(f">{name}<") for name in ("anna", "Bob", "Carl", "Zoe")]
    assert positions == sorted(positions)
    assert "No socks<br>Please" in content
    assert "30.00" in content


def test_page_after_the_draw_shows_only_my_recipient(client, drawn_exchange):
    me = ExchangeParticipant.objects.select_related("gives_to").get(
        exchange=drawn_exchange, name="Bob"
    )

    content = text(client.get(page(me.token)))

    assert f"You give a gift to: <strong>{me.gives_to.name}</strong>" in content
    assert "gives to" not in content
    assert content.count("You give a gift to") == 1


def test_page_never_reads_who_drew_me(client, drawn_exchange):
    me = drawn_exchange.participants.get(name="Bob")

    with CaptureQueriesContext(connection) as queries:
        client.get(page(me.token))

    for query in queries.captured_queries:
        sql = query["sql"]
        assert f'"gives_to_id" = {me.pk}' not in sql
        assert "drawn_by" not in sql
    # The names of the other participants are read without their pairings
    names_query = [q["sql"] for q in queries.captured_queries if "LOWER" in q["sql"].upper()]
    assert names_query
    assert all("gives_to_id" not in sql for sql in names_query)


def test_page_after_a_redraw_shows_the_new_recipient(client, drawn_exchange):
    me = drawn_exchange.participants.get(name="Bob")
    for seed in range(2, 40):
        service.run_draw(drawn_exchange, rng=seeded(seed))
        me.refresh_from_db()
        recipient = ExchangeParticipant.objects.get(pk=me.gives_to_id)
        assert f"<strong>{recipient.name}</strong>" in text(client.get(page(me.token)))


def test_guidelines_are_escaped(client, exchange):
    Exchange.objects.filter(pk=exchange.pk).update(guidelines="<script>alert(1)</script>")
    me = exchange.participants.first()

    content = text(client.get(page(me.token)))

    assert "<script>alert(1)</script>" not in content
    assert "&lt;script&gt;" in content


def test_headers_and_meta(client, exchange):
    me = exchange.participants.first()

    response = client.get(page(me.token))

    assert response["Cache-Control"] == "private, no-store"
    assert response["Referrer-Policy"] == "no-referrer"
    assert response["X-Robots-Tag"] == "noindex, nofollow"
    content = text(response)
    assert content.index('<meta name="referrer" content="no-referrer">') < content.index("<link")
    assert "<nav" not in content


def test_unknown_token_and_inactive_organizer_are_404(client, exchange):
    assert client.get(page("not-a-token")).status_code == 404

    me = exchange.participants.first()
    exchange.organizer.is_active = False
    exchange.organizer.save()
    assert client.get(page(me.token)).status_code == 404


def test_token_of_a_deleted_exchange_is_404(client, exchange):
    token = exchange.participants.first().token
    exchange.delete()
    assert client.get(page(token)).status_code == 404


def test_regenerated_token_kills_the_old_link(client, exchange):
    me = exchange.participants.first()
    old = me.token
    service.regenerate_token(me)

    assert client.get(page(old)).status_code == 404
    assert client.get(page(me.token)).status_code == 200


def test_page_is_read_only(client, exchange):
    me = exchange.participants.first()
    assert client.post(page(me.token)).status_code == 405


def test_page_uses_the_organizer_language(client, exchange):
    exchange.organizer.profile.preferred_language = "fr"
    exchange.organizer.profile.save()
    me = exchange.participants.first()

    content = text(client.get(page(me.token)))  # an /en/ URL

    assert "pas encore eu lieu" in content
    assert 'lang="fr"' in content


def test_linked_participant_page_shows_nothing_of_the_account(client, drawn_exchange):
    me = drawn_exchange.participants.get(name="Carl")
    before = text(client.get(page(me.token)))
    account = UserFactory(username="carl_account")
    account.profile.preferred_language = "fr"
    account.profile.save()
    WishFactory(wisher=account, title="Secret wish of Carl")
    ExchangeParticipant.objects.filter(pk=me.pk).update(linked_account=account)

    after = text(client.get(page(me.token)))

    assert after == before
    assert "Secret wish of Carl" not in after


def test_closed_exchange_page_hides_the_assignment(client, drawn_exchange):
    Exchange.objects.filter(pk=drawn_exchange.pk).update(status=Exchange.Status.CLOSED)
    me = ExchangeParticipant.objects.select_related("gives_to").get(
        exchange=drawn_exchange, name="Bob"
    )

    content = text(client.get(page(me.token)))

    assert "This exchange is over." in content
    assert f"<strong>{me.gives_to.name}</strong>" not in content


def test_stop_emails_get_asks_and_post_stops(client, exchange):
    me = exchange.participants.first()
    url = reverse("gift_manager:secret_santa_stop_emails", args=[emails.make_stop_token(me)])

    response = client.get(url)
    assert response.status_code == 200
    assert "Do you want to stop receiving emails" in text(response)
    assert response["Cache-Control"] == "private, no-store"
    me.refresh_from_db()
    assert not me.emails_stopped

    response = client.post(url)
    assert response.status_code == 200
    assert "You will no longer receive emails" in text(response)
    assert response["Referrer-Policy"] == "no-referrer"
    me.refresh_from_db()
    assert me.emails_stopped


def test_stop_emails_post_works_without_csrf(exchange):
    from django.test import Client

    me = exchange.participants.first()
    url = reverse("gift_manager:secret_santa_stop_emails", args=[emails.make_stop_token(me)])

    response = Client(enforce_csrf_checks=True).post(url)

    assert response.status_code == 200
    me.refresh_from_db()
    assert me.emails_stopped


def test_stop_emails_with_a_bad_token_is_400(client):
    url = reverse("gift_manager:secret_santa_stop_emails", args=["bad-token"])

    for response in (client.get(url), client.post(url)):
        assert response.status_code == 400
        assert "This link is not valid." in text(response)
        assert response["X-Robots-Tag"] == "noindex, nofollow"
