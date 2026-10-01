"""Tests for the ``send_gift_digest`` management command."""

from datetime import date
from datetime import timedelta
from io import StringIO
from unittest import mock

import pytest
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from gift_manager.models import Profile
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import RelationStatusFactory
from gift_manager.tests.factories import UserFactory

BASE_URL = "https://gifts.example.com"
MONDAY = date(2026, 9, 28)
TUESDAY = date(2026, 9, 29)


@pytest.fixture(autouse=True)
def site_base_url(settings):
    settings.SITE_BASE_URL = BASE_URL


def run(*args) -> str:
    out = StringIO()
    call_command("send_gift_digest", *args, stdout=out)
    return out.getvalue()


def opt_in(user, frequency=Profile.DIGEST_DAILY, **profile_fields):
    Profile.objects.filter(user=user).update(digest_frequency=frequency, **profile_fields)
    user.refresh_from_db()
    return user


def overdue_plan(user, days=3, **kwargs):
    return RelationFactory(
        due_date=timezone.localdate() - timedelta(days=days),
        status=RelationStatusFactory(status="Planned"),
        shared_with=[user],
        **kwargs,
    )


@pytest.mark.django_db
class TestSelection:
    def test_digest_is_off_by_default(self, user):
        overdue_plan(user)

        run()

        assert mail.outbox == []

    def test_opted_in_user_receives_one_email_with_the_plan(self, user):
        plan = overdue_plan(user)
        opt_in(user)

        output = run()

        assert len(mail.outbox) == 1
        message = mail.outbox[0]
        assert message.to == [user.profile.email]
        assert plan.gift.name in message.body
        assert f"{BASE_URL}/en/relations/{plan.relation_id}/" in message.body
        assert "Sent 1 digest" in output

    def test_multiple_items_still_produce_a_single_email(self, user):
        overdue_plan(user)
        overdue_plan(user, days=9)
        PersonFactory(
            birthday_day=timezone.localdate().day,
            birthday_month=timezone.localdate().month,
            shared_with=[user],
        )
        opt_in(user)

        run()

        assert len(mail.outbox) == 1

    def test_nothing_is_sent_when_no_plan_qualifies(self, user):
        opt_in(user)

        output = run()

        assert mail.outbox == []
        assert "Sent 0 digest" in output

    def test_each_user_only_receives_their_own_data(self, user):
        other = UserFactory()
        mine = overdue_plan(user)
        theirs = overdue_plan(other)
        opt_in(user)
        opt_in(other)

        run()

        bodies = {message.to[0]: message.body for message in mail.outbox}
        assert mine.gift.name in bodies[user.profile.email]
        assert theirs.gift.name not in bodies[user.profile.email]
        assert mine.gift.name not in bodies[other.profile.email]

    def test_inactive_users_are_skipped(self, user):
        overdue_plan(user)
        opt_in(user)
        user.is_active = False
        user.save()

        run()

        assert mail.outbox == []

    def test_users_without_an_email_are_skipped(self, user):
        overdue_plan(user)
        opt_in(user)
        user.email = ""
        user.save()

        run()

        assert mail.outbox == []

    def test_user_option_restricts_the_run(self, user):
        other = UserFactory()
        for account in (user, other):
            overdue_plan(account)
            opt_in(account)

        run("--user", other.username)

        assert [message.to for message in mail.outbox] == [[other.profile.email]]

    def test_dry_run_sends_nothing(self, user):
        overdue_plan(user)
        opt_in(user)

        output = run("--dry-run")

        assert mail.outbox == []
        assert "Would send 1 digest" in output

    def test_a_broken_recipient_does_not_stop_the_others(self, user):
        other = UserFactory()
        for account in (user, other):
            overdue_plan(account)
            opt_in(account)

        real_send = mail.EmailMultiAlternatives.send
        calls = []

        def flaky_send(self, *args, **kwargs):
            calls.append(self.to)
            if len(calls) == 1:
                msg = "smtp down"
                raise OSError(msg)
            return real_send(self, *args, **kwargs)

        with (
            mock.patch.object(mail.EmailMultiAlternatives, "send", flaky_send),
            pytest.raises(CommandError, match="1 digest"),
        ):
            run()

        assert len(mail.outbox) == 1


@pytest.mark.django_db
class TestSentTracking:
    def test_sending_records_the_day(self, user):
        overdue_plan(user)
        opt_in(user)

        run()

        user.profile.refresh_from_db()
        assert user.profile.last_digest_sent_on == timezone.localdate()

    def test_running_again_the_same_day_sends_nothing_more(self, user):
        overdue_plan(user)
        opt_in(user)

        run()
        output = run()

        assert len(mail.outbox) == 1
        assert "1 already sent today" in output
        assert "Sent 0 digest" in output

    def test_a_digest_sent_on_a_previous_day_does_not_block_today(self, user):
        overdue_plan(user)
        opt_in(user, last_digest_sent_on=timezone.localdate() - timedelta(days=1))

        run()

        assert len(mail.outbox) == 1

    def test_rerun_after_a_partial_failure_only_emails_the_failed_user(self, user):
        other = UserFactory()
        for account in (user, other):
            overdue_plan(account)
            opt_in(account)

        real_send = mail.EmailMultiAlternatives.send
        failing = [user.profile.email]

        def flaky_send(self, *args, **kwargs):
            if self.to == failing:
                msg = "smtp down"
                raise OSError(msg)
            return real_send(self, *args, **kwargs)

        with (
            mock.patch.object(mail.EmailMultiAlternatives, "send", flaky_send),
            pytest.raises(CommandError),
        ):
            run()
        assert [message.to for message in mail.outbox] == [[other.profile.email]]
        user.profile.refresh_from_db()
        assert user.profile.last_digest_sent_on is None

        run()

        assert [message.to for message in mail.outbox] == [
            [other.profile.email],
            [user.profile.email],
        ]

    def test_dry_run_does_not_record_anything(self, user):
        overdue_plan(user)
        opt_in(user)

        run("--dry-run")

        user.profile.refresh_from_db()
        assert user.profile.last_digest_sent_on is None

    def test_an_empty_digest_is_not_recorded_so_later_runs_can_still_send(self, user):
        opt_in(user)
        run()
        user.profile.refresh_from_db()
        assert user.profile.last_digest_sent_on is None

        overdue_plan(user)
        run()

        assert len(mail.outbox) == 1

    def test_user_option_also_skips_a_user_already_sent(self, user):
        overdue_plan(user)
        opt_in(user)

        run("--user", user.username)
        run("--user", user.username)

        assert len(mail.outbox) == 1


@pytest.mark.django_db
class TestFrequency:
    def test_weekly_digest_is_sent_on_mondays(self, user):
        overdue_plan(user)
        opt_in(user, Profile.DIGEST_WEEKLY)

        with mock.patch("django.utils.timezone.localdate", return_value=MONDAY):
            run()

        assert len(mail.outbox) == 1

    def test_weekly_digest_is_not_sent_on_other_days(self, user):
        overdue_plan(user)
        opt_in(user, Profile.DIGEST_WEEKLY)

        with mock.patch("django.utils.timezone.localdate", return_value=TUESDAY):
            run()

        assert mail.outbox == []

    def test_include_weekly_ignores_the_weekday(self, user):
        overdue_plan(user)
        opt_in(user, Profile.DIGEST_WEEKLY)

        with mock.patch("django.utils.timezone.localdate", return_value=TUESDAY):
            run("--include-weekly")

        assert len(mail.outbox) == 1

    def test_daily_digest_is_sent_any_day(self, user):
        overdue_plan(user)
        opt_in(user)

        with mock.patch("django.utils.timezone.localdate", return_value=TUESDAY):
            run()

        assert len(mail.outbox) == 1


@pytest.mark.django_db
class TestContent:
    def test_unsubscribe_link_and_headers(self, user):
        overdue_plan(user)
        opt_in(user)

        run()

        message = mail.outbox[0]
        link = message.extra_headers["List-Unsubscribe"].strip("<>")
        assert link.startswith(f"{BASE_URL}/en/digest/unsubscribe/")
        assert message.extra_headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
        assert link in message.body
        assert link in message.alternatives[0].content

    def test_html_alternative_is_attached(self, user):
        plan = overdue_plan(user)
        opt_in(user)

        run()

        html, mimetype = mail.outbox[0].alternatives[0]
        assert mimetype == "text/html"
        assert plan.gift.name in html

    def test_html_alternative_escapes_names_but_text_does_not(self, user):
        evil = "<script>alert(1)</script> & co"
        overdue_plan(user, gift=GiftFactory(name=evil))
        opt_in(user)

        run()

        html = mail.outbox[0].alternatives[0].content
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert evil in mail.outbox[0].body

    def test_email_is_rendered_in_the_language_of_the_profile(self, user):
        overdue_plan(user)
        opt_in(user, preferred_language="fr")

        run()

        message = mail.outbox[0]
        assert "nécessite votre attention" in message.subject
        assert "En retard" in message.body
        # Links follow the language of the recipient too
        assert f"{BASE_URL}/fr/relations/" in message.body

    def test_default_language_is_english(self, user):
        overdue_plan(user)
        opt_in(user)

        run()

        assert "needs your attention" in mail.outbox[0].subject
        assert "Overdue" in mail.outbox[0].body

    def test_language_does_not_leak_to_the_next_recipient(self, user):
        other = UserFactory()
        for account in (user, other):
            overdue_plan(account)
        opt_in(user, preferred_language="fr")
        opt_in(other)

        run()

        subjects = {message.to[0]: message.subject for message in mail.outbox}
        assert "nécessite" in subjects[user.profile.email]
        assert "needs your attention" in subjects[other.profile.email]


@pytest.mark.django_db
def test_command_requires_the_site_base_url(settings, user):
    settings.SITE_BASE_URL = ""
    overdue_plan(user)
    opt_in(user)

    with pytest.raises(CommandError, match="SITE_BASE_URL"):
        run()

    assert mail.outbox == []
