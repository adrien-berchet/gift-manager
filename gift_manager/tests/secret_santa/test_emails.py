"""Tests of the Secret Santa emails."""

import random
from datetime import timedelta

import pytest
from django.core import mail
from django.core.cache import cache
from django.utils import timezone

from gift_manager.secret_santa import emails
from gift_manager.secret_santa import service
from gift_manager.secret_santa.emails import send_assignments
from gift_manager.secret_santa.models import ExchangeParticipant
from gift_manager.secret_santa.service import ExchangeError
from gift_manager.tests.factories import ExchangeFactory
from gift_manager.tests.factories import ExchangeParticipantFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def build(path):
    return f"https://gifts.example.com{path}"


@pytest.fixture(autouse=True)
def _clear_quota():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def exchange():
    organizer = UserFactory(first_name="Olivia", last_name="Organizer")
    return ExchangeFactory(
        organizer=organizer, name="Family 2026", guidelines="SECRET-GUIDELINES no socks"
    )


def drawn(exchange, count=3):
    people = [
        ExchangeParticipantFactory(exchange=exchange, name=f"Person {i}") for i in range(count)
    ]
    service.run_draw(exchange, rng=random.Random(1))  # noqa: S311 - reproducible test
    return people


def test_one_email_per_participant_with_an_address(exchange):
    people = drawn(exchange)
    ExchangeParticipant.objects.filter(pk=people[0].pk).update(email_address=None)

    report = send_assignments(exchange, people, build)

    assert len(mail.outbox) == 2
    assert report.no_email == [people[0]]
    assert sorted(p.pk for p in report.sent) == sorted(p.pk for p in people[1:])
    assert all(
        p.last_emailed_at is not None
        for p in ExchangeParticipant.objects.filter(pk__in=[p.pk for p in people[1:]])
    )


def test_email_names_the_participant_and_holds_the_personal_and_stop_links(exchange):
    people = drawn(exchange)
    me = people[1]

    send_assignments(exchange, [me], build)

    (message,) = mail.outbox
    assert message.to == [me.email]
    assert me.name in message.subject
    assert "Family 2026" in message.subject
    assert message.body.startswith(f"Hello {me.name},")
    assert "Olivia Organizer" in message.body
    assert f"https://gifts.example.com/en/secret-santa/p/{me.token}/" in message.body
    stop_link = build(emails.stop_path(me))
    assert stop_link in message.body
    assert message.extra_headers["List-Unsubscribe"] == f"<{stop_link}>"
    assert message.extra_headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    html = message.alternatives[0][0]
    assert me.token in html


def test_email_never_contains_the_guidelines_nor_the_recipient_name(exchange):
    people = drawn(exchange)
    me = ExchangeParticipant.objects.select_related("gives_to").get(pk=people[0].pk)

    send_assignments(exchange, [me], build)

    (message,) = mail.outbox
    content = message.subject + message.body + message.alternatives[0][0]
    assert "SECRET-GUIDELINES" not in content
    assert me.gives_to.name not in content


def test_stopped_participants_get_nothing(exchange):
    people = drawn(exchange)
    ExchangeParticipant.objects.filter(pk=people[0].pk).update(emails_stopped=True)

    report = send_assignments(exchange, people, build)

    assert len(mail.outbox) == 2
    assert report.stopped == [people[0]]


class FlakyConnection:
    """A mail connection that refuses one address."""

    def __init__(self, bad_address):
        self.bad_address = bad_address
        self.sent = []

    def open(self):
        return True

    def close(self):
        pass

    def send_messages(self, messages):
        for message in messages:
            if self.bad_address in message.to:
                error = "mailbox unavailable"
                raise OSError(error)
            self.sent.append(message)
        return len(messages)


def test_one_failing_recipient_does_not_stop_the_others(exchange, monkeypatch):
    people = drawn(exchange)
    connection = FlakyConnection(people[1].email)
    monkeypatch.setattr(emails, "get_connection", lambda: connection)

    report = send_assignments(exchange, people, build)

    assert report.failed == [people[1]]
    assert len(report.sent) == 2
    assert len(connection.sent) == 2
    assert ExchangeParticipant.objects.get(pk=people[1].pk).last_emailed_at is None


def test_mail_server_down_reports_everyone_as_failed(exchange, monkeypatch):
    people = drawn(exchange)

    class DownConnection(FlakyConnection):
        def open(self):
            raise ConnectionRefusedError

    monkeypatch.setattr(emails, "get_connection", lambda: DownConnection(""))

    report = send_assignments(exchange, people, build)

    assert len(report.failed) == 3
    assert report.sent == []


def test_quota_stops_sending_and_reports_the_rest(exchange, settings):
    settings.SECRET_SANTA_EMAIL_LIMIT = 2
    people = drawn(exchange, count=5)

    report = send_assignments(exchange, people, build)

    assert len(report.sent) == 2
    assert len(report.over_limit) == 3
    assert len(mail.outbox) == 2


def test_quota_is_per_organizer(exchange, settings):
    settings.SECRET_SANTA_EMAIL_LIMIT = 3
    people = drawn(exchange)
    other = ExchangeFactory()
    other_people = drawn(other)

    assert len(send_assignments(exchange, people, build).sent) == 3
    assert len(send_assignments(other, other_people, build).sent) == 3
    assert len(send_assignments(exchange, people, build).over_limit) == 3


def test_send_again_respects_the_cooldown(exchange):
    people = drawn(exchange)
    me = people[0]
    send_assignments(exchange, [me], build)
    me.refresh_from_db()

    assert not emails.can_send_again(me)
    with pytest.raises(ExchangeError, match="Wait a few minutes"):
        emails.send_again(me, build)

    later = timezone.now() + timedelta(minutes=6)
    assert emails.can_send_again(me, now=later)
    ExchangeParticipant.objects.filter(pk=me.pk).update(
        last_emailed_at=timezone.now() - timedelta(minutes=6)
    )
    me.refresh_from_db()
    assert len(emails.send_again(me, build).sent) == 1


def test_send_again_is_allowed_after_an_email_change(exchange):
    people = drawn(exchange)
    me = people[0]
    send_assignments(exchange, [me], build)
    me.refresh_from_db()

    service.update_participant(me, name=me.name, email="new@example.com")

    report = emails.send_again(me, build)
    assert len(report.sent) == 1
    assert mail.outbox[-1].to == ["new@example.com"]


def test_send_again_refuses_a_draft_exchange(exchange):
    me = ExchangeParticipantFactory(exchange=exchange)

    with pytest.raises(ExchangeError):
        emails.send_again(me, build)


def test_send_again_counts_in_the_quota(exchange, settings):
    settings.SECRET_SANTA_EMAIL_LIMIT = 3
    people = drawn(exchange)
    send_assignments(exchange, people, build)
    ExchangeParticipant.objects.update(last_emailed_at=None)
    me = ExchangeParticipant.objects.get(pk=people[0].pk)

    assert emails.send_again(me, build).over_limit == [me]


def test_linked_participant_gets_their_own_language(exchange):
    people = drawn(exchange)
    account = UserFactory()
    account.profile.preferred_language = "fr"
    account.profile.save()
    ExchangeParticipant.objects.filter(pk=people[0].pk).update(linked_account=account)

    send_assignments(exchange, [people[0]], build)

    (message,) = mail.outbox
    assert message.subject.startswith("Père Noël secret")
    assert message.body.startswith("Bonjour")
    # The link keeps the organizer's language
    assert "/en/secret-santa/p/" in message.body


def test_unlinked_participant_gets_the_organizer_language(exchange):
    exchange.organizer.profile.preferred_language = "fr"
    exchange.organizer.profile.save()
    people = drawn(exchange)

    send_assignments(exchange, [people[0]], build)

    (message,) = mail.outbox
    assert message.body.startswith("Bonjour")
    assert "/fr/secret-santa/p/" in message.body


def test_stop_token_round_trip_and_tampering(exchange):
    participant = ExchangeParticipantFactory(exchange=exchange)
    token = emails.make_stop_token(participant)

    assert emails.read_stop_token(token) == participant.pk
    assert emails.read_stop_token("x") is None
    assert emails.read_stop_token(token[:-2] + "zz") is None


def test_personal_path_uses_the_organizer_language_prefix(exchange):
    participant = ExchangeParticipantFactory(exchange=exchange)
    assert emails.participant_path(participant) == f"/en/secret-santa/p/{participant.token}/"

    exchange.organizer.profile.preferred_language = "fr"
    exchange.organizer.profile.save()
    participant.exchange.organizer.profile.refresh_from_db()
    assert emails.participant_path(participant) == f"/fr/secret-santa/p/{participant.token}/"


def test_a_redraw_resets_the_email_state_of_whoever_was_not_reached(exchange, monkeypatch):
    people = drawn(exchange)
    send_assignments(exchange, people, build)
    service.run_draw(exchange, rng=random.Random(2))  # noqa: S311 - reproducible test
    connection = FlakyConnection(people[0].email)
    monkeypatch.setattr(emails, "get_connection", lambda: connection)

    report = send_assignments(exchange, people, build)

    assert report.failed == [people[0]]
    unreached = ExchangeParticipant.objects.get(pk=people[0].pk)
    assert unreached.last_emailed_at is None
    assert emails.can_send_again(unreached)


def test_invitations_go_to_non_declined_not_yet_invited(exchange):
    people = [ExchangeParticipantFactory(exchange=exchange, name=f"P{i}") for i in range(4)]
    ExchangeParticipant.objects.filter(pk=people[0].pk).update(declined=True)
    ExchangeParticipant.objects.filter(pk=people[1].pk).update(email_address=None)

    report = emails.send_invitations(exchange, build)

    assert sorted(p.pk for p in report.sent) == sorted(p.pk for p in people[2:])
    assert report.no_email == [people[1]]
    assert len(mail.outbox) == 2
    assert ExchangeParticipant.objects.filter(invited_at__isnull=False).count() == 2
    assert not emails.send_invitations(exchange, build).sent
    assert len(mail.outbox) == 2


def test_invitation_content(exchange):
    me = ExchangeParticipantFactory(exchange=exchange, name="Chloe")

    emails.send_invitations(exchange, build)

    (message,) = mail.outbox
    assert message.subject == 'Secret Santa "Family 2026": your page, Chloe'
    assert message.body.startswith("Hello Chloe,")
    assert "Olivia Organizer invites you" in message.body
    assert me.token in message.body
    assert "SECRET-GUIDELINES" not in message.body + message.alternatives[0][0]
    assert "List-Unsubscribe" in message.extra_headers


def test_invitations_refused_after_the_draw(exchange):
    drawn(exchange)
    with pytest.raises(ExchangeError):
        emails.send_invitations(exchange, build)


def test_send_again_in_draft_resends_the_invitation_only_when_invited(exchange):
    me = ExchangeParticipantFactory(exchange=exchange)
    with pytest.raises(ExchangeError, match="invitations first"):
        emails.send_again(me, build)

    emails.send_invitations(exchange, build)
    ExchangeParticipant.objects.update(last_emailed_at=None)
    me.refresh_from_db()
    emails.send_again(me, build)

    assert len(mail.outbox) == 2
    assert "your page" in mail.outbox[-1].subject


def test_send_again_refuses_a_declined_participant(exchange):
    me = ExchangeParticipantFactory(exchange=exchange, declined=True)
    with pytest.raises(ExchangeError, match="does not take part"):
        emails.send_again(me, build)


def test_redraw_never_emails_declined(exchange):
    people = drawn(exchange, count=4)
    ExchangeParticipant.objects.filter(pk=people[0].pk).update(declined=True)

    report = send_assignments(exchange, people, build)

    assert people[0] not in report.sent
    assert len(mail.outbox) == 3
