"""Secret Santa views.

Participant pages are opened by a secret token, without login, as standalone pages like the
guest wishlist. They read only the participant's own pairing and never anything of a linked
account. Organizer pages are behind login and scoped to the exchanges the user organizes.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count
from django.db.models import Prefetch
from django.db.models.functions import Lower
from django.http import Http404
from django.http import HttpResponse
from django.http import HttpResponseBadRequest
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

from gift_manager.secret_santa import emails
from gift_manager.secret_santa import service
from gift_manager.secret_santa.draw import MIN_PARTICIPANTS
from gift_manager.secret_santa.forms import ExchangeForm
from gift_manager.secret_santa.forms import ExclusionSetForm
from gift_manager.secret_santa.forms import ImportForm
from gift_manager.secret_santa.forms import ParticipantForm
from gift_manager.secret_santa.models import MAX_PARTICIPANTS
from gift_manager.secret_santa.models import Exchange
from gift_manager.secret_santa.models import ExchangeParticipant
from gift_manager.secret_santa.models import ExclusionSet
from gift_manager.secret_santa.service import ExchangeError


def _private(response: HttpResponse) -> HttpResponse:
    """Mark a response as private: no cache, no referrer, no indexing."""
    response["Cache-Control"] = "private, no-store"
    response["Referrer-Policy"] = "no-referrer"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


# ---------------------------------------------------------------------------
# Participant pages (no login)
# ---------------------------------------------------------------------------


@require_safe
def secret_santa_participant(request, token):
    """Show a participant the exchange and, once drawn, who they give a gift to."""
    if not token:
        raise Http404
    participant = get_object_or_404(
        ExchangeParticipant.objects.select_related("exchange__organizer__profile"),
        token=token,
        exchange__organizer__is_active=True,
    )
    exchange = participant.exchange
    with translation.override(exchange.organizer.profile.language):
        recipient_name = None
        if exchange.is_drawn and participant.gives_to_id is not None:
            # Only the name of the participant's own recipient; who drew them is never read
            recipient_name = (
                ExchangeParticipant.objects.filter(pk=participant.gives_to_id, exchange=exchange)
                .values_list("name", flat=True)
                .first()
            )
        names = list(
            exchange.participants.order_by(Lower("name"), "pk").values_list("name", flat=True)
        )
        response = render(
            request,
            "gift_manager/secret_santa/participant_page.html",
            {
                "participant": participant,
                "exchange": exchange,
                "organizer_name": emails.organizer_name(exchange),
                "names": names,
                "recipient_name": recipient_name,
            },
        )
    return _private(response)


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
        ExchangeParticipant.objects.defer("gives_to").select_related("exchange"),
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
            and emails.can_send_again(participant, now)
        )
    exclusion_sets = exchange.exclusion_sets.prefetch_related(
        Prefetch(
            "participants",
            queryset=ExchangeParticipant.objects.defer("gives_to").order_by(Lower("name")),
        )
    )
    context = {
        "exchange": exchange,
        "participants": participants,
        "exclusion_sets": exclusion_sets,
        "organizer_takes_part": any(
            participant.linked_account_id == request.user.pk for participant in participants
        ),
        "can_draw": len(participants) >= MIN_PARTICIPANTS,
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
    """Create an exchange, then go to its page."""
    form = ExchangeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        exchange = service.create_exchange(request.user, **form.cleaned_data)
        messages.success(request, gettext("Exchange created. Add the participants."))
        return _to_detail(exchange)
    return render(
        request,
        "gift_manager/secret_santa/exchange_form.html",
        {
            "form": form,
            "exchange": None,
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
        initial={
            "name": exchange.name,
            "exchange_date": exchange.exchange_date,
            "budget": exchange.budget,
            "guidelines": exchange.guidelines,
            "no_mutual_draw": exchange.no_mutual_draw,
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
    reports: list[emails.SendReport] = []
    try:
        with transaction.atomic():
            participants = service.run_draw(exchange)
            # After the commit only: a failed email must never undo the draw
            transaction.on_commit(
                lambda: reports.append(
                    emails.send_assignments(exchange, participants, request.build_absolute_uri)
                )
            )
    except ExchangeError as error:
        messages.error(request, error.message)
        return _to_detail(exchange)
    if redraw:
        messages.success(
            request, gettext("The draw was done again. Everyone has a new assignment.")
        )
    else:
        messages.success(request, gettext("The draw is done."))
    if reports:
        _flash_report(request, reports[0])
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
        exchange.participants.order_by(Lower("name"), "pk").values_list("name", "gives_to__name")
    )
    return _reveal_response(
        request,
        exchange,
        "gift_manager/includes/secret_santa_pairings.html",
        {"pairings": pairings},
    )
