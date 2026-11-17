"""Tests of the Secret Santa participant pages (personal page and stop-emails page)."""

import random
import re

import pytest
from django.conf import settings
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import translation

from gift_manager.secret_santa import emails
from gift_manager.secret_santa import service
from gift_manager.secret_santa.models import Exchange
from gift_manager.secret_santa.models import ExchangeParticipant
from gift_manager.secret_santa.models import ExchangeWish
from gift_manager.tests.factories import ExchangeFactory
from gift_manager.tests.factories import ExchangeParticipantFactory
from gift_manager.tests.factories import ExchangeWishFactory
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


def comparable(response):
    """The page without its per-render CSRF token, to compare two renders."""
    return re.sub(
        r'name="csrfmiddlewaretoken" value="[^"]+"', 'name="csrfmiddlewaretoken"', text(response)
    )


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
    assert response["Referrer-Policy"] == "strict-origin"
    assert response["X-Robots-Tag"] == "noindex, nofollow"
    content = text(response)
    assert content.index('<meta name="referrer" content="strict-origin">') < content.index("<link")
    # Only the minimal navbar: no link into the app beyond its brand
    assert content.count("<nav") == 1
    assert "nav-link" not in content


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
    before = comparable(client.get(page(me.token)))
    account = UserFactory(username="carl_account")
    account.profile.preferred_language = "fr"
    account.profile.save()
    WishFactory(wisher=account, title="Secret wish of Carl")
    ExchangeParticipant.objects.filter(pk=me.pk).update(linked_account=account)

    after = comparable(client.get(page(me.token)))

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


# ---------------------------------------------------------------------------
# Slice 2: telling your Santa, declining, attaching an account
# ---------------------------------------------------------------------------


def action(name, participant, *extra):
    return reverse(f"gift_manager:secret_santa_{name}", args=[participant.token, *extra])


def santa_of(participant):
    """The Santa of a participant (tests only: pages never read this)."""
    return ExchangeParticipant.objects.get(gives_to=participant)


def test_wish_add_redirects_and_shows_the_wish(client, exchange):
    me = exchange.participants.get(name="Bob")

    response = client.post(
        action("wish_add", me), {"title": "Puzzle", "url": "https://example.com/p", "price": "15"}
    )

    assert response.status_code == 303
    assert response["Location"] == page(me.token)
    assert response["Referrer-Policy"] == "no-referrer"
    assert "Puzzle" in text(client.get(page(me.token)))


@pytest.mark.parametrize(
    "data",
    [
        {"title": "Bad link", "url": "javascript:alert(1)"},
        {"title": "Negative", "price": "-1"},
        {"title": ""},
        {"title": "x" * 201},
    ],
)
def test_invalid_wishes_are_refused(client, exchange, data):
    me = exchange.participants.get(name="Bob")

    response = client.post(action("wish_add", me), data)

    assert response.status_code == 400
    assert response["Cache-Control"] == "private, no-store"
    assert not me.exchange_wishes.exists()


def test_post_without_csrf_is_refused(exchange):
    from django.test import Client

    me = exchange.participants.get(name="Bob")
    response = Client(enforce_csrf_checks=True).post(action("wish_add", me), {"title": "X"})

    assert response.status_code == 403
    assert not me.exchange_wishes.exists()


def test_actions_need_post_and_a_valid_token(client, exchange):
    me = exchange.participants.get(name="Bob")
    assert client.get(action("wish_add", me)).status_code == 405
    url = reverse("gift_manager:secret_santa_wish_add", args=["bad-token"])
    assert client.post(url, {"title": "X"}).status_code == 404


def test_cannot_delete_the_wish_of_someone_else(client, exchange):
    me = exchange.participants.get(name="Bob")
    other = ExchangeWishFactory(participant=exchange.participants.get(name="Carl"))

    response = client.post(action("wish_delete", me, other.wish_id))

    assert response.status_code == 404
    assert ExchangeWish.objects.filter(pk=other.pk).exists()


def test_note_is_saved_and_too_long_refused(client, exchange):
    me = exchange.participants.get(name="Bob")

    assert client.post(action("note", me), {"note": "Size M"}).status_code == 303
    assert client.post(action("note", me), {"note": "x" * 2001}).status_code == 400
    me.refresh_from_db()
    assert me.note_for_santa == "Size M"


def test_my_santa_sees_my_wishes_and_note_after_the_draw(client, exchange):
    me = exchange.participants.get(name="Bob")
    client.post(action("wish_add", me), {"title": "Puzzle"})
    client.post(action("note", me), {"note": "No chocolate"})
    service.run_draw(exchange, rng=seeded(1))
    santa = santa_of(me)
    someone_else = exchange.participants.exclude(pk__in=[me.pk, santa.pk]).first()

    santa_page = text(client.get(page(santa.token)))
    other_page = text(client.get(page(someone_else.token)))

    assert "Puzzle" in santa_page
    assert "No chocolate" in santa_page
    assert "Puzzle" not in other_page
    assert "No chocolate" not in other_page


def test_wishes_and_note_are_titled_apart(client, exchange):
    me = exchange.participants.get(name="Bob")
    client.post(action("wish_add", me), {"title": "Puzzle"})
    client.post(action("note", me), {"note": "No chocolate"})
    service.run_draw(exchange, rng=seeded(1))

    own_page = text(client.get(page(me.token)))
    santa_page = text(client.get(page(santa_of(me).token)))

    # The writer's card: one titled part for the wishes, another for the note
    wishes_at, note_at = own_page.index("Your wishes"), own_page.index("Your note")
    assert wishes_at < own_page.index("Puzzle") < note_at < own_page.index("No chocolate")
    # The Santa's card: the note has its own title and box, after the wishes
    note_title = santa_page.index("Note from Bob")
    assert santa_page.index("What Bob would like") < santa_page.index("Puzzle") < note_title
    assert (
        note_title
        < santa_page.index("secret-santa-recipient-note")
        < santa_page.index("No chocolate")
    )


def test_blank_note_shows_no_note_part(client, exchange):
    me = exchange.participants.get(name="Bob")
    client.post(action("wish_add", me), {"title": "Puzzle"})
    ExchangeParticipant.objects.filter(pk=me.pk).update(note_for_santa="   ")
    service.run_draw(exchange, rng=seeded(1))

    santa_page = text(client.get(page(santa_of(me).token)))

    assert "Puzzle" in santa_page
    assert "Note from Bob" not in santa_page


def test_wish_and_note_survive_a_redraw(client, exchange):
    me = exchange.participants.get(name="Bob")
    client.post(action("wish_add", me), {"title": "Puzzle"})
    service.run_draw(exchange, rng=seeded(1))
    service.run_draw(exchange, rng=seeded(2))

    assert "Puzzle" in text(client.get(page(santa_of(me).token)))


def test_declined_page_states(client, exchange):
    me = exchange.participants.get(name="Bob")

    assert client.post(action("decline", me)).status_code == 303
    content = text(client.get(page(me.token)))
    assert "You said that you cannot take part." in content
    assert ">Bob<" not in content  # left out of the participant list

    client.post(action("rejoin", me))
    me.refresh_from_db()
    assert not me.declined

    client.post(action("decline", me))
    service.run_draw(exchange, rng=seeded(1))
    content = text(client.get(page(me.token)))
    assert "You do not take part in this exchange." in content
    assert client.post(action("rejoin", me)).status_code == 400


def test_decline_after_the_draw_is_refused(client, drawn_exchange):
    me = drawn_exchange.participants.get(name="Bob")

    response = client.post(action("decline", me))

    assert response.status_code == 400
    me.refresh_from_db()
    assert not me.declined


def test_attach_flow_anonymous_goes_through_login_without_the_token(client, exchange):
    me = exchange.participants.get(name="Bob")
    account = UserFactory(username="bob_account")
    account.set_password("pw-123456")
    account.save()

    start = client.post(action("attach_start", me))
    assert start.status_code == 302
    assert me.token not in start["Location"]
    assert start["Location"].startswith("/accounts/login/")
    assert start["Referrer-Policy"] == "no-referrer"

    client.login(username="bob_account", password="pw-123456")
    confirm_url = reverse("gift_manager:secret_santa_attach_confirm")
    assert me.token not in confirm_url
    confirm_page = client.get(confirm_url)
    assert confirm_page.status_code == 200
    assert "Bob" in text(confirm_page)
    me.refresh_from_db()
    assert me.linked_account is None  # not before the confirmation

    done = client.post(confirm_url)
    assert done.status_code == 303
    me.refresh_from_db()
    assert me.linked_account == account
    assert me.account_attached_by_participant
    assert "secret_santa_attach" not in client.session


def test_attach_with_a_regenerated_token_is_refused(client, exchange):
    me = exchange.participants.get(name="Bob")
    account = UserFactory()
    client.force_login(account)
    client.post(action("attach_start", me))
    service.regenerate_token(me)

    response = client.post(reverse("gift_manager:secret_santa_attach_confirm"))

    assert response.status_code == 400
    me.refresh_from_db()
    assert me.linked_account is None


def test_attach_without_a_pending_request_is_refused(client):
    client.force_login(UserFactory())
    response = client.get(reverse("gift_manager:secret_santa_attach_confirm"))
    assert response.status_code == 400


def test_contested_attach_shows_the_error_and_forgets_the_request(client, exchange):
    me = exchange.participants.get(name="Bob")
    account = UserFactory()
    ExchangeParticipant.objects.filter(exchange=exchange, name="Carl").update(
        linked_account=account
    )
    client.force_login(account)
    client.post(action("attach_start", me))

    response = client.post(reverse("gift_manager:secret_santa_attach_confirm"))

    assert response.status_code == 400
    assert "another participant" in text(response)
    assert "secret_santa_attach" not in client.session


def test_attach_to_a_participation_linked_elsewhere_is_refused_before_confirming(client, exchange):
    me = exchange.participants.get(name="Bob")
    link(me)
    client.force_login(UserFactory())
    client.post(action("attach_start", me))

    confirm_page = client.get(reverse("gift_manager:secret_santa_attach_confirm"))

    page_text = text(confirm_page)
    assert "already linked to another Gift Manager account" in page_text
    assert "If it is yours, log in with that account." in page_text
    assert "Link my account" not in page_text
    assert "secret_santa_attach" not in client.session


def test_attach_of_an_account_used_by_another_participant_is_refused_before_confirming(
    client, exchange
):
    me = exchange.participants.get(name="Bob")
    account = UserFactory()
    ExchangeParticipant.objects.filter(exchange=exchange, name="Carl").update(
        linked_account=account
    )
    client.force_login(account)
    client.post(action("attach_start", me))

    confirm_page = client.get(reverse("gift_manager:secret_santa_attach_confirm"))

    assert "another participant" in text(confirm_page)
    assert "Link my account" not in text(confirm_page)


def link(participant, username="linked_user", **profile):
    account = UserFactory(username=username)
    for key, value in profile.items():
        setattr(account.profile, key, value)
    account.profile.save()
    ExchangeParticipant.objects.filter(pk=participant.pk).update(linked_account=account)
    participant.refresh_from_db()
    return account


def test_linked_page_is_identical_for_anonymous_and_other_accounts(client, exchange):
    me = exchange.participants.get(name="Bob")
    unlinked_page = comparable(client.get(page(me.token)))
    account = link(me, preferred_language="fr")
    WishFactory(wisher=account, title="Secret real wish")
    ExchangeParticipant.objects.filter(pk=me.pk).update(
        wishlist_confirmed=True, account_attached_by_participant=True
    )

    anonymous = comparable(client.get(page(me.token)))
    client.force_login(UserFactory())
    other_account = comparable(client.get(page(me.token)))

    assert anonymous == unlinked_page == other_account
    assert "Secret real wish" not in anonymous
    assert 'lang="en"' in anonymous


def test_linked_viewer_sees_selection_and_own_language(client, exchange):
    me = exchange.participants.get(name="Bob")
    account = link(me, preferred_language="fr")
    WishFactory(wisher=account, title="Real wish")
    client.force_login(account)

    content = text(client.get(page(me.token)))

    assert "Real wish" in content
    assert 'lang="fr"' in content
    assert f"/secret-santa/p/{me.token}/share/" in content


def page_in(language, token):
    with translation.override(language):
        return page(token)


def test_page_has_a_navbar_with_theme_and_language_only(client, exchange):
    me = exchange.participants.get(name="Bob")

    content = text(client.get(page(me.token)))

    navbar = content[content.index('<nav class="navbar') : content.index("</nav>")]
    assert "Gift Manager" in navbar
    assert 'id="theme-toggle"' in navbar
    assert 'name="language"' in navbar
    assert f'name="next" value="{page(me.token)}"' in navbar
    assert "nav-link" not in navbar
    assert "gift_manager/js/theme-toggle.js" in content


def test_language_chosen_in_the_navbar_overrides_the_default(client, exchange):
    me = exchange.participants.get(name="Bob")

    response = client.post(
        reverse("set_language"), {"language": "fr", "next": page_in("en", me.token)}
    )

    assert response.status_code == 302
    assert response["Location"] == page_in("fr", me.token)
    assert 'lang="fr"' in text(client.get(response["Location"]))
    # Back to the organizer's language: the cookie no longer matches the page prefix
    client.cookies.load({settings.LANGUAGE_COOKIE_NAME: "en"})
    assert 'lang="en"' in text(client.get(page_in("en", me.token)))


def test_only_a_chosen_language_overrides_the_default(client, exchange):
    me = exchange.participants.get(name="Bob")
    account = link(me, preferred_language="fr")
    client.force_login(account)

    # A prefix without a matching cookie (the emailed link) keeps the account's language
    assert 'lang="fr"' in text(client.get(page_in("en", me.token)))
    # A cookie for another prefix (set while using the app) does not override it either
    client.cookies.load({settings.LANGUAGE_COOKIE_NAME: "en"})
    assert 'lang="fr"' in text(client.get(page_in("fr", me.token)))
    # A cookie matching the prefix is a choice made on this page
    assert 'lang="en"' in text(client.get(page_in("en", me.token)))


def test_language_switch_after_an_error_returns_to_the_page(client, exchange):
    me = exchange.participants.get(name="Bob")

    content = text(client.post(action("note", me), {"note": "x" * 2001}))

    assert f'name="next" value="{page(me.token)}"' in content


def test_unlink_button_is_last_on_the_page_and_red(client, exchange):
    me = exchange.participants.get(name="Bob")
    detach_url = action("detach", me)
    assert detach_url not in text(client.get(page(me.token)))

    client.force_login(link(me))
    content = text(client.get(page(me.token)))

    unlink = re.search(
        rf'<form method="post" action="{re.escape(detach_url)}"[^>]*>.*?</form>', content, re.DOTALL
    )
    assert unlink is not None
    assert "btn-outline-danger" in unlink.group(0)
    # Below every section and the decline control: only the closing note follows
    after = content[unlink.end() :]
    assert "<section" not in after
    assert "secret-santa-decline" not in after
    assert "gift_manager/images/gift.png" in content[: content.index("</h1>")]


def test_share_and_detach_need_the_linked_account(client, exchange):
    me = exchange.participants.get(name="Bob")
    account = link(me)
    wish = WishFactory(wisher=account)

    assert client.post(action("share", me), {"wishes": [str(wish.wish_id)]}).status_code == 404
    assert client.post(action("detach", me)).status_code == 404
    client.force_login(UserFactory())
    assert client.post(action("share", me), {"wishes": [str(wish.wish_id)]}).status_code == 404
    me.refresh_from_db()
    assert me.linked_account == account
    assert not me.wishlist_confirmed


def test_santa_sees_shared_wishes_after_confirmation_only(client, exchange):
    me = exchange.participants.get(name="Bob")
    account = link(me)
    shared = WishFactory(wisher=account, title="Shared real wish")
    WishFactory(wisher=account, title="Kept private")
    service.run_draw(exchange, rng=seeded(1))
    santa_page = page(santa_of(me).token)
    assert "Shared real wish" not in text(Client().get(santa_page))

    client.force_login(account)
    response = client.post(action("share", me), {"wishes": [str(shared.wish_id)]})
    assert response.status_code == 303

    content = text(Client().get(santa_page))
    assert "Shared real wish" in content
    assert "Kept private" not in content

    client.post(action("detach", me))
    assert "Shared real wish" not in text(Client().get(santa_page))


# ---------------------------------------------------------------------------
# Slice 3: closed exchanges
# ---------------------------------------------------------------------------


def close(exchange, *, reveal):
    Exchange.objects.filter(pk=exchange.pk).update(
        status=Exchange.Status.CLOSED, pairings_revealed=reveal
    )


def test_closed_without_reveal_reads_no_other_pairing(client, drawn_exchange):
    me = drawn_exchange.participants.get(name="Bob")
    close(drawn_exchange, reveal=False)

    with CaptureQueriesContext(connection) as queries:
        content = text(client.get(page(me.token)))

    assert "This exchange is over." in content
    assert "gave to" not in content
    later = [q["sql"] for q in queries.captured_queries[1:]]
    assert all("gives_to" not in sql for sql in later)


def test_closed_with_reveal_lists_everyone_who_took_part(client, drawn_exchange):
    me = drawn_exchange.participants.get(name="Bob")
    close(drawn_exchange, reveal=True)

    content = text(client.get(page(me.token)))

    for participant in drawn_exchange.participants.select_related("gives_to"):
        assert f"{participant.name} gave to {participant.gives_to.name}" in content


def test_closed_page_hides_shared_content_and_refuses_writes(client, drawn_exchange):
    me = drawn_exchange.participants.get(name="Bob")
    santa = santa_of(me)
    client.post(action("wish_add", me), {"title": "Puzzle"})
    close(drawn_exchange, reveal=False)

    assert "Puzzle" not in text(client.get(page(santa.token)))
    assert "Puzzle" not in text(client.get(page(me.token)))
    for name, data in (("wish_add", {"title": "X"}), ("note", {"note": "X"}), ("decline", {})):
        assert client.post(action(name, me), data).status_code == 400
    assert me.exchange_wishes.count() == 1
