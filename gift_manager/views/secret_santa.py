"""Secret Santa views.

Participant pages are opened by a secret token, without login, as standalone pages like the
guest wishlist. They read only the participant's own pairing and never anything of a linked
account. Organizer pages are behind login and scoped to the exchanges the user organizes.
"""

from __future__ import annotations

import hashlib
import hmac
from functools import wraps
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count
from django.db.models import Prefetch
from django.db.models.functions import Lower
from django.http import Http404
from django.http import HttpResponse
from django.http import HttpResponseBadRequest
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils import translation
from django.utils.decorators import method_decorator
from django.utils.translation import gettext
from django.utils.translation import ngettext
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.views.decorators.http import require_POST
from django.views.decorators.http import require_safe

from gift_manager.secret_santa import access
from gift_manager.secret_santa import emails
from gift_manager.secret_santa import participation
from gift_manager.secret_santa import planning
from gift_manager.secret_santa import service
from gift_manager.secret_santa.draw import MIN_PARTICIPANTS
from gift_manager.secret_santa.forms import ExchangeForm
from gift_manager.secret_santa.forms import ExchangeWishForm
from gift_manager.secret_santa.forms import ExclusionSetForm
from gift_manager.secret_santa.forms import ImportForm
from gift_manager.secret_santa.forms import LatecomerForm
from gift_manager.secret_santa.forms import NoteForm
from gift_manager.secret_santa.forms import ParticipantForm
from gift_manager.secret_santa.forms import SharedWishesForm
from gift_manager.secret_santa.models import MAX_EXCHANGE_WISHES
from gift_manager.secret_santa.models import MAX_PARTICIPANTS
from gift_manager.secret_santa.models import Exchange
from gift_manager.secret_santa.models import ExchangeParticipant
from gift_manager.secret_santa.models import ExchangeWish
from gift_manager.secret_santa.models import ExclusionSet
from gift_manager.secret_santa.service import ExchangeError

if TYPE_CHECKING:
    from collections.abc import Callable


# The personal page holds forms: with "no-referrer", browsers send "Origin: null" on their POST
# and the CSRF check refuses them. "strict-origin" never sends the path (where the secret token
# is) to anyone, only the site's origin, so the token does not leak either.
PERSONAL_PAGE_REFERRER_POLICY = "strict-origin"


def _private(response: HttpResponse, *, referrer_policy: str = "no-referrer") -> HttpResponse:
    """Mark a response as private: no cache, no referrer path, no indexing."""
    response["Cache-Control"] = "private, no-store"
    response["Referrer-Policy"] = referrer_policy
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


# ---------------------------------------------------------------------------
# Participant pages (no login)
# ---------------------------------------------------------------------------


ATTACH_SESSION_KEY = "secret_santa_attach"


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _participant_by_token(token: str) -> ExchangeParticipant:
    """Return the participant of a personal link, or 404."""
    if not token:
        raise Http404
    return get_object_or_404(
        ExchangeParticipant.objects.select_related(
            "exchange__organizer__profile", "linked_account__profile"
        ),
        token=token,
        exchange__organizer__is_active=True,
    )


def _page_url(participant: ExchangeParticipant) -> str:
    return reverse("gift_manager:secret_santa_participant", args=[participant.token])


def _see_other(url: str) -> HttpResponse:
    """Redirect after a POST of the personal page, without leaking it anywhere."""
    response = HttpResponseRedirect(url)
    response.status_code = 303
    return _private(response)


def _render_page(
    request,
    participant: ExchangeParticipant,
    *,
    status: int = 200,
    error: str | None = None,
    wish_form: ExchangeWishForm | None = None,
    note_form: NoteForm | None = None,
) -> HttpResponse:
    """Render the personal page.

    Only a visitor logged in as the linked account sees anything of that account (its real
    wishes, the link itself, its language); everyone else gets the same page whether the
    participant is linked or not.
    """
    exchange = participant.exchange
    linked_viewer = access.viewer_is_linked(participant, request.user)
    language = (
        request.user.profile.language if linked_viewer else exchange.organizer.profile.language
    )
    with translation.override(language):
        context = {
            "participant": participant,
            "exchange": exchange,
            "organizer_name": emails.organizer_name(exchange),
            "names": list(
                service.taking_part(exchange)
                .order_by(Lower("name"), "pk")
                .values_list("name", flat=True)
            ),
            "recipient": access.recipient_view(participant),
            "own_wishes": list(participant.exchange_wishes.all()),
            "wish_form": wish_form or ExchangeWishForm(),
            "note_form": note_form or NoteForm(initial={"note": participant.note_for_santa}),
            "linked_viewer": linked_viewer,
            "error": error,
            "max_wishes": MAX_EXCHANGE_WISHES,
        }
        if linked_viewer:
            context["shareable_wishes"] = participation.shareable_wishes(participant)
            context["account_currency"] = request.user.profile.currency
        context["referrer_policy"] = PERSONAL_PAGE_REFERRER_POLICY
        response = render(
            request, "gift_manager/secret_santa/participant_page.html", context, status=status
        )
    return _private(response, referrer_policy=PERSONAL_PAGE_REFERRER_POLICY)


@require_safe
def secret_santa_participant(request, token):
    """Show a participant the exchange, what they share and, once drawn, who they drew."""
    return _render_page(request, _participant_by_token(token))


def _participant_action(action: Callable) -> Callable:
    """Wrap a POST of the personal page: 404 for a bad link, errors shown on the page."""

    @wraps(action)
    @require_POST
    def view(request, token, *args, **kwargs) -> HttpResponse:
        participant = _participant_by_token(token)
        try:
            result = action(request, participant, *args, **kwargs)
        except ExchangeError as error:
            return _render_page(request, participant, status=400, error=error.message)
        return result or _see_other(_page_url(participant))

    return view


@_participant_action
def secret_santa_wish_add(request, participant):
    form = ExchangeWishForm(request.POST)
    if not form.is_valid():
        return _render_page(request, participant, status=400, wish_form=form)
    participation.add_exchange_wish(participant, **form.cleaned_data)
    return None


@_participant_action
def secret_santa_wish_delete(request, participant, wish_id):  # noqa: ARG001
    try:
        participation.delete_exchange_wish(participant, wish_id)
    except ExchangeWish.DoesNotExist:
        raise Http404 from None


@_participant_action
def secret_santa_note(request, participant):
    form = NoteForm(request.POST)
    if not form.is_valid():
        return _render_page(request, participant, status=400, note_form=form)
    participation.save_note(participant, form.cleaned_data["note"])
    return None


@_participant_action
def secret_santa_decline(request, participant):  # noqa: ARG001
    participation.decline(participant)


@_participant_action
def secret_santa_rejoin(request, participant):  # noqa: ARG001
    participation.rejoin(participant)


@_participant_action
def secret_santa_attach_start(request, participant):
    """Remember the participant in the session, then confirm once logged in.

    Neither the login URL nor the confirmation URL carries the token.
    """
    if participant.exchange.is_closed:
        raise ExchangeError(gettext("This exchange is closed."))
    request.session[ATTACH_SESSION_KEY] = {
        "participant": participant.pk,
        "token_hash": _token_hash(participant.token),
    }
    target = reverse("gift_manager:secret_santa_attach_confirm")
    if request.user.is_authenticated:
        return _private(redirect(target))
    return _private(redirect_to_login(target))


@_participant_action
def secret_santa_detach(request, participant):
    if not access.viewer_is_linked(participant, request.user):
        raise Http404
    participation.detach_account(participant, request.user)


@_participant_action
def secret_santa_share(request, participant):
    if not access.viewer_is_linked(participant, request.user):
        raise Http404
    choices = [
        (str(wish.wish_id), wish.title) for wish, _ in participation.shareable_wishes(participant)
    ]
    form = SharedWishesForm(request.POST, choices=choices)
    if not form.is_valid():
        raise ExchangeError(gettext("Choose among your active wishes."))
    participation.save_shared_wishes(participant, request.user, form.cleaned_data["wishes"])


def _pending_attachment(request) -> ExchangeParticipant | None:
    """Return the participant remembered by the attach flow, if its link is still valid."""
    data = request.session.get(ATTACH_SESSION_KEY)
    if not isinstance(data, dict):
        return None
    participant = (
        ExchangeParticipant.objects.select_related("exchange__organizer__profile")
        .defer("gives_to", "note_for_santa")
        .filter(pk=data.get("participant"), exchange__organizer__is_active=True)
        .first()
    )
    if participant is None or not hmac.compare_digest(
        _token_hash(participant.token), str(data.get("token_hash", ""))
    ):
        return None
    return participant


@login_required
@require_http_methods(["GET", "POST"])
def secret_santa_attach_confirm(request):
    """Ask the logged-in participant to confirm the link to their account."""
    template = "gift_manager/secret_santa/attach_confirm.html"
    participant = _pending_attachment(request)
    if participant is None:
        request.session.pop(ATTACH_SESSION_KEY, None)
        return _private(
            render(request, template, {"expired": True}, status=400),
            referrer_policy=PERSONAL_PAGE_REFERRER_POLICY,
        )
    if request.method == "POST":
        try:
            participation.attach_account(participant, request.user)
        except ExchangeError as error:
            request.session.pop(ATTACH_SESSION_KEY, None)
            return _private(
                render(
                    request,
                    template,
                    {"participant": participant, "error": error.message},
                    status=400,
                ),
                referrer_policy=PERSONAL_PAGE_REFERRER_POLICY,
            )
        request.session.pop(ATTACH_SESSION_KEY, None)
        return _see_other(_page_url(participant))
    # The form of this page posts: see PERSONAL_PAGE_REFERRER_POLICY
    return _private(
        render(request, template, {"participant": participant}),
        referrer_policy=PERSONAL_PAGE_REFERRER_POLICY,
    )


@method_decorator(csrf_exempt, name="dispatch")
class SecretSantaStopEmailsView(View):
    """Stop the emails of one exchange from the signed link of an email.

    GET only asks for confirmation (mail scanners follow links); POST stops the emails. The
    POST is exempt from CSRF so a mail client can do an RFC 8058 one-click unsubscribe; the
    signed token is the only credential and only allows turning the emails off.
    """

    template_name = "gift_manager/secret_santa/stop_emails.html"

    def _participant(self, token) -> ExchangeParticipant | None:
        participant_id = emails.read_stop_token(token)
        if participant_id is None:
            return None
        return (
            ExchangeParticipant.objects.select_related("exchange__organizer__profile")
            .defer("gives_to")
            .filter(pk=participant_id)
            .first()
        )

    def _render(self, request, participant, *, done: bool) -> HttpResponse:
        context = {
            "valid": participant is not None,
            "done": done,
            "exchange_name": participant.exchange.name if participant else "",
        }
        status = 200 if participant else 400
        if participant is None:
            return _private(render(request, self.template_name, context, status=status))
        with translation.override(participant.exchange.organizer.profile.language):
            return _private(render(request, self.template_name, context, status=status))

    def get(self, request, token, *args, **kwargs):
        return self._render(request, self._participant(token), done=False)

    def post(self, request, token, *args, **kwargs):
        participant = self._participant(token)
        if participant is not None and not participant.emails_stopped:
            ExchangeParticipant.objects.filter(pk=participant.pk).update(emails_stopped=True)
        return self._render(request, participant, done=participant is not None)


# ---------------------------------------------------------------------------
# Organizer pages (login, scoped to the exchanges the user organizes)
# ---------------------------------------------------------------------------


def _get_exchange(request, exchange_id) -> Exchange:
    """Return an exchange the user organizes, or 404 (never 403)."""
    return get_object_or_404(
        service.organized_by(request.user).select_related("organizer__profile"),
        exchange_id=exchange_id,
    )


def _get_participant(exchange: Exchange, participant_id) -> ExchangeParticipant:
    """Return a participant of this exchange, without who they drew."""
    return get_object_or_404(
        ExchangeParticipant.objects.defer("gives_to", "note_for_santa").select_related("exchange"),
        exchange=exchange,
        participant_id=participant_id,
    )


def _to_detail(exchange: Exchange) -> HttpResponse:
    return redirect("gift_manager:secret_santa_detail", exchange_id=exchange.exchange_id)


def _form_error(request, form) -> None:
    """Flash the first error of an invalid form."""
    for errors in form.errors.values():
        for error in errors:
            messages.error(request, error)
            return


def _is_htmx(request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _names(participants) -> str:
    return ", ".join(participant.name for participant in participants)


def _flash_report(request, report: emails.SendReport) -> None:
    """Tell the organizer what happened to the emails, naming who was not reached."""
    if report.sent:
        count = len(report.sent)
        messages.success(
            request,
            ngettext("%(count)d email sent.", "%(count)d emails sent.", count) % {"count": count},
        )
    unreached = report.no_email + report.stopped
    if unreached:
        messages.info(
            request,
            gettext("No email for %(names)s: hand out their personal link.")
            % {"names": _names(unreached)},
        )
    if report.failed:
        messages.error(
            request,
            gettext("The email could not be sent to %(names)s. Use Send again or Show link.")
            % {"names": _names(report.failed)},
        )
    if report.over_limit:
        messages.error(
            request,
            gettext(
                "The email limit is reached: nothing was sent to %(names)s. Try again tomorrow "
                "or hand out their personal link."
            )
            % {"names": _names(report.over_limit)},
        )


def _detail_context(request, exchange: Exchange, **extra) -> dict:
    participants = list(service.participants_without_pairings(exchange))
    now = timezone.now()
    for participant in participants:
        participant.can_send_again = (
            bool(participant.email_address)
            and not participant.emails_stopped
            and not participant.declined
            and (exchange.is_drawn or participant.invited_at is not None)
            and emails.can_send_again(participant, now)
        )
    exclusion_sets = exchange.exclusion_sets.prefetch_related(
        Prefetch(
            "participants",
            queryset=ExchangeParticipant.objects.defer("gives_to", "note_for_santa").order_by(
                Lower("name")
            ),
        )
    )
    context = {
        "exchange": exchange,
        "participants": participants,
        "exclusion_sets": exclusion_sets,
        "organizer_takes_part": any(
            participant.linked_account_id == request.user.pk for participant in participants
        ),
        "can_draw": sum(not p.declined for p in participants) >= MIN_PARTICIPANTS,
        "uninvited_count": sum(
            1 for p in participants if not p.declined and p.invited_at is None and p.email_address
        ),
        "min_participants": MIN_PARTICIPANTS,
        "max_participants": MAX_PARTICIPANTS,
        "participant_form": ParticipantForm(),
        "import_form": ImportForm(user=request.user),
        "set_form": ExclusionSetForm(exchange=exchange),
    }
    context.update(extra)
    return context


@login_required
@require_safe
def secret_santa_list(request):
    """List the exchanges the user organizes."""
    exchanges = service.organized_by(request.user).annotate(participant_count=Count("participants"))
    return render(request, "gift_manager/secret_santa/exchange_list.html", {"exchanges": exchanges})


@login_required
@require_http_methods(["GET", "POST"])
def secret_santa_create(request):
    """Create an exchange, or start one from a previous exchange (``?from=<uuid>``)."""
    previous = None
    source = request.GET.get("from")
    if source:
        try:
            previous = service.organized_by(request.user).get(exchange_id=source)
        except (Exchange.DoesNotExist, ValidationError):
            raise Http404 from None
    initial = {}
    if previous is not None:
        initial = {
            "name": previous.name,
            "budget": previous.budget,
            "guidelines": previous.guidelines,
            "no_mutual_draw": previous.no_mutual_draw,
            "no_repeat_draw": True,
        }
    form = ExchangeForm(request.POST or None, initial=initial, has_previous=previous is not None)
    if request.method == "POST" and form.is_valid():
        if previous is not None:
            exchange = service.copy_exchange(previous, request.user, **form.cleaned_data)
            messages.success(request, gettext("Exchange created from the previous one."))
        else:
            exchange = service.create_exchange(request.user, **form.cleaned_data)
            messages.success(request, gettext("Exchange created. Add the participants."))
        return _to_detail(exchange)
    return render(
        request,
        "gift_manager/secret_santa/exchange_form.html",
        {
            "form": form,
            "exchange": None,
            "previous": previous,
            "currency_label": request.user.profile.currency,
            "cancel_url": reverse("gift_manager:secret_santa_list"),
        },
    )


@login_required
@require_safe
def secret_santa_detail(request, exchange_id):
    """Show the participants, the exclusion sets and the actions; never a pairing."""
    exchange = _get_exchange(request, exchange_id)
    return render(
        request,
        "gift_manager/secret_santa/exchange_detail.html",
        _detail_context(request, exchange),
    )


@login_required
@require_http_methods(["GET", "POST"])
def secret_santa_edit(request, exchange_id):
    """Edit the exchange; the mutual-draw switch only changes before the draw."""
    exchange = _get_exchange(request, exchange_id)
    if exchange.is_closed:
        messages.error(request, gettext("This exchange is closed."))
        return _to_detail(exchange)
    form = ExchangeForm(
        request.POST or None,
        creating=False,
        switch_locked=not exchange.is_draft,
        has_previous=exchange.previous_exchange_id is not None,
        initial={
            "name": exchange.name,
            "exchange_date": exchange.exchange_date,
            "budget": exchange.budget,
            "guidelines": exchange.guidelines,
            "no_mutual_draw": exchange.no_mutual_draw,
            "no_repeat_draw": exchange.no_repeat_draw,
        },
    )
    if request.method == "POST" and form.is_valid():
        try:
            service.update_exchange(exchange, **form.cleaned_data)
        except ExchangeError as error:
            messages.error(request, error.message)
        else:
            messages.success(request, gettext("Exchange updated."))
        return _to_detail(exchange)
    return render(
        request,
        "gift_manager/secret_santa/exchange_form.html",
        {
            "form": form,
            "exchange": exchange,
            "currency_label": exchange.currency,
            "cancel_url": _to_detail(exchange).url,
        },
    )


@login_required
@require_POST
def secret_santa_delete(request, exchange_id):
    exchange = _get_exchange(request, exchange_id)
    service.delete_exchange(exchange)
    messages.success(request, gettext("Exchange deleted."))
    return redirect("gift_manager:secret_santa_list")


@login_required
@require_POST
def secret_santa_participant_add(request, exchange_id):
    exchange = _get_exchange(request, exchange_id)
    form = ParticipantForm(request.POST)
    if not form.is_valid():
        _form_error(request, form)
        return _to_detail(exchange)
    try:
        participant = service.add_participant(
            exchange, name=form.cleaned_data["name"], email=form.cleaned_data["email"]
        )
    except ExchangeError as error:
        messages.error(request, error.message)
    else:
        messages.success(request, gettext("%(name)s added.") % {"name": participant.name})
    return _to_detail(exchange)


@login_required
@require_POST
def secret_santa_participant_import(request, exchange_id):
    exchange = _get_exchange(request, exchange_id)
    form = ImportForm(request.POST, user=request.user)
    if not form.is_valid():
        _form_error(request, form)
        return _to_detail(exchange)
    added = skipped = 0
    try:
        with transaction.atomic():
            if form.cleaned_data["group"]:
                result = service.import_group(exchange, request.user, form.cleaned_data["group"])
                added, skipped = added + result[0], skipped + result[1]
            if form.cleaned_data["persons"]:
                result = service.import_persons(
                    exchange, request.user, form.cleaned_data["persons"]
                )
                added, skipped = added + result[0], skipped + result[1]
    except ExchangeError as error:
        messages.error(request, error.message)
    else:
        messages.success(
            request,
            gettext("%(added)d added, %(skipped)d already there.")
            % {"added": added, "skipped": skipped},
        )
    return _to_detail(exchange)


@login_required
@require_POST
def secret_santa_participant_edit(request, exchange_id, participant_id):
    exchange = _get_exchange(request, exchange_id)
    participant = _get_participant(exchange, participant_id)
    form = ParticipantForm(request.POST)
    if not form.is_valid():
        _form_error(request, form)
        return _to_detail(exchange)
    try:
        service.update_participant(
            participant, name=form.cleaned_data["name"], email=form.cleaned_data["email"]
        )
    except ExchangeError as error:
        messages.error(request, error.message)
    else:
        messages.success(request, gettext("%(name)s updated.") % {"name": participant.name})
    return _to_detail(exchange)


@login_required
@require_POST
def secret_santa_participant_remove(request, exchange_id, participant_id):
    exchange = _get_exchange(request, exchange_id)
    participant = _get_participant(exchange, participant_id)
    try:
        service.remove_participant(participant)
    except ExchangeError as error:
        messages.error(request, error.message)
    else:
        messages.success(request, gettext("%(name)s removed.") % {"name": participant.name})
    return _to_detail(exchange)


@login_required
@require_POST
def secret_santa_set_save(request, exchange_id):
    exchange = _get_exchange(request, exchange_id)
    form = ExclusionSetForm(request.POST, exchange=exchange)
    if not form.is_valid():
        _form_error(request, form)
        return _to_detail(exchange)
    instance = None
    if form.cleaned_data["set_id"]:
        instance = get_object_or_404(
            ExclusionSet, exchange=exchange, set_id=form.cleaned_data["set_id"]
        )
    try:
        service.save_exclusion_set(
            exchange,
            name=form.cleaned_data["name"],
            participants=form.cleaned_data["participants"],
            instance=instance,
        )
    except ExchangeError as error:
        messages.error(request, error.message)
    else:
        messages.success(request, gettext("Exclusion set saved."))
    return _to_detail(exchange)


@login_required
@require_POST
def secret_santa_set_delete(request, exchange_id, set_id):
    exchange = _get_exchange(request, exchange_id)
    exclusion_set = get_object_or_404(ExclusionSet, exchange=exchange, set_id=set_id)
    try:
        service.delete_exclusion_set(exclusion_set)
    except ExchangeError as error:
        messages.error(request, error.message)
    else:
        messages.success(request, gettext("Exclusion set deleted."))
    return _to_detail(exchange)


@login_required
@require_POST
def secret_santa_draw(request, exchange_id):
    """Draw (or redraw), then email every participant their personal link."""
    exchange = _get_exchange(request, exchange_id)
    redraw = exchange.is_drawn
    if _change_and_email(request, exchange, lambda: service.run_draw(exchange)):
        if redraw:
            message = gettext("The draw was done again. Everyone has a new assignment.")
        else:
            message = gettext("The draw is done.")
        messages.success(request, message)
    return _to_detail(exchange)


def _change_and_email(request, exchange: Exchange, operation: Callable) -> bool:
    """Run a change of the pairings, then email the participants it returns.

    The emails are sent after the commit only: a failed email must never undo the change.
    Returns False (with the error flashed) when the change was refused.
    """
    reports: list[emails.SendReport] = []
    try:
        with transaction.atomic():
            changed = operation()
            transaction.on_commit(
                lambda: reports.append(
                    emails.send_assignments(exchange, changed, request.build_absolute_uri)
                )
            )
    except ExchangeError as error:
        messages.error(request, error.message)
        return False
    if reports:
        _flash_report(request, reports[0])
    return True


@login_required
@require_POST
def secret_santa_remove_repair(request, exchange_id, participant_id):
    """After the draw, remove a participant; only their Santa gets a new assignment."""
    exchange = _get_exchange(request, exchange_id)
    participant = _get_participant(exchange, participant_id)
    if _change_and_email(request, exchange, lambda: service.remove_and_repair(participant)):
        messages.success(
            request,
            gettext("%(name)s removed. Their Santa has a new assignment.")
            % {"name": participant.name},
        )
    return _to_detail(exchange)


@login_required
@require_POST
def secret_santa_remove_redraw(request, exchange_id, participant_id):
    """After the draw, remove a participant and redraw everything."""
    exchange = _get_exchange(request, exchange_id)
    participant = _get_participant(exchange, participant_id)
    if _change_and_email(request, exchange, lambda: service.remove_and_redraw(participant)):
        messages.success(
            request,
            gettext("%(name)s removed. Everyone has a new assignment.")
            % {"name": participant.name},
        )
    return _to_detail(exchange)


@login_required
@require_POST
def secret_santa_add_latecomer(request, exchange_id):
    """After the draw, bring in a latecomer (new, or a participant who had declined)."""
    exchange = _get_exchange(request, exchange_id)
    form = LatecomerForm(request.POST, exchange=exchange)
    if not form.is_valid():
        _form_error(request, form)
        return _to_detail(exchange)
    data = form.cleaned_data
    participant = data["participant"]
    arguments = {
        "participant": participant,
        "name": data["name"],
        "email": data["email"],
        "exclusion_sets": data["sets"],
    }
    redraw = data["mode"] == LatecomerForm.REDRAW
    operation = service.add_and_redraw if redraw else service.add_and_repair
    if _change_and_email(request, exchange, lambda: operation(exchange, **arguments)):
        name = participant.name if participant else data["name"]
        if redraw:
            message = gettext("%(name)s added. Everyone has a new assignment.")
        else:
            message = gettext("%(name)s added. Two Santas and %(name)s have a new assignment.")
        messages.success(request, message % {"name": name})
    return _to_detail(exchange)


@login_required
@require_POST
def secret_santa_invite(request, exchange_id):
    """Before the draw, send their personal link to the participants not invited yet."""
    exchange = _get_exchange(request, exchange_id)
    try:
        report = emails.send_invitations(exchange, request.build_absolute_uri)
    except ExchangeError as error:
        messages.error(request, error.message)
    else:
        if report.sent or report.failed or report.over_limit:
            _flash_report(request, report)
        else:
            messages.info(request, gettext("Everyone with an email address has their link."))
    return _to_detail(exchange)


@login_required
@require_POST
def secret_santa_put_back(request, exchange_id, participant_id):
    """Before the draw, count again a participant who had said they cannot take part."""
    exchange = _get_exchange(request, exchange_id)
    participant = _get_participant(exchange, participant_id)
    try:
        service.put_back(participant)
    except ExchangeError as error:
        messages.error(request, error.message)
    else:
        messages.success(
            request, gettext("%(name)s takes part again.") % {"name": participant.name}
        )
    return _to_detail(exchange)


@login_required
@require_POST
def secret_santa_send_again(request, exchange_id, participant_id):
    exchange = _get_exchange(request, exchange_id)
    participant = _get_participant(exchange, participant_id)
    try:
        report = emails.send_again(participant, request.build_absolute_uri)
    except ExchangeError as error:
        messages.error(request, error.message)
    else:
        _flash_report(request, report)
    return _to_detail(exchange)


def _reveal_response(request, exchange: Exchange, template: str, context: dict) -> HttpResponse:
    """Answer a reveal with its partial (HTMX) or inside the detail page, never cached."""
    if _is_htmx(request):
        response = render(request, template, context)
    else:
        response = render(
            request,
            "gift_manager/secret_santa/exchange_detail.html",
            _detail_context(request, exchange, revealed_template=template, **context),
        )
    response["Cache-Control"] = "private, no-store"
    return response


@login_required
@require_POST
def secret_santa_show_link(request, exchange_id, participant_id):
    """Show one participant's personal link, after the organizer confirmed the warning."""
    if request.POST.get("confirm") != "1":
        return HttpResponseBadRequest()
    exchange = _get_exchange(request, exchange_id)
    participant = _get_participant(exchange, participant_id)
    participant.exchange = exchange
    return _reveal_response(
        request,
        exchange,
        "gift_manager/includes/secret_santa_revealed_link.html",
        {
            "revealed_participant": participant,
            "revealed_url": request.build_absolute_uri(emails.participant_path(participant)),
        },
    )


@login_required
@require_POST
def secret_santa_regenerate_link(request, exchange_id, participant_id):
    exchange = _get_exchange(request, exchange_id)
    participant = _get_participant(exchange, participant_id)
    try:
        service.regenerate_token(participant)
    except ExchangeError as error:
        messages.error(request, error.message)
    else:
        messages.success(
            request,
            gettext("%(name)s has a new personal link. The old one no longer works.")
            % {"name": participant.name},
        )
    return _to_detail(exchange)


@login_required
@require_POST
def secret_santa_pairings(request, exchange_id):
    """Show who everyone drew, after the organizer confirmed the warning."""
    if request.POST.get("confirm") != "1":
        return HttpResponseBadRequest()
    exchange = _get_exchange(request, exchange_id)
    if exchange.is_draft:
        messages.error(request, gettext("The draw has not been done yet."))
        return _to_detail(exchange)
    pairings = list(
        service.taking_part(exchange)
        .order_by(Lower("name"), "pk")
        .values_list("name", "gives_to__name")
    )
    return _reveal_response(
        request,
        exchange,
        "gift_manager/includes/secret_santa_pairings.html",
        {"pairings": pairings},
    )


@login_required
@require_safe
def secret_santa_plan_gift(request, participant_id):
    """Open the guided plan for the recipient of the user's own participation."""
    santa = get_object_or_404(
        ExchangeParticipant.objects.select_related("exchange").defer("note_for_santa"),
        participant_id=participant_id,
        linked_account=request.user,
        declined=False,
        gives_to__isnull=False,
        exchange__status=Exchange.Status.DRAWN,
        exchange__organizer__is_active=True,
    )
    query = urlencode(planning.plan_prefill(santa, request.user))
    return redirect(f"{reverse('gift_manager:relation_guided_create')}?{query}")
