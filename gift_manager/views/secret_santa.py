"""Secret Santa views.

Participant pages are opened by a secret token, without login, as standalone pages like the
guest wishlist. They read only the participant's own pairing and never anything of a linked
account. Organizer pages are behind login and scoped to the exchanges the user organizes.
"""

from __future__ import annotations

from django.db.models.functions import Lower
from django.http import Http404
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import render
from django.utils import translation
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_safe

from gift_manager.secret_santa import emails
from gift_manager.secret_santa.models import ExchangeParticipant


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
