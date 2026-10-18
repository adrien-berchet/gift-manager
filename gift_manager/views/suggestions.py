"""Views for recipient gift plan suggestions."""

import dataclasses
import uuid

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET
from django.views.decorators.http import require_POST

from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.suggestions.catalogue import describe_reason
from gift_manager.suggestions.service import GiftSuggestionService
from gift_manager.views.base import HTMXResponseMixin

SUGGESTIONS_SECTION_TEMPLATE = "gift_manager/includes/gift_suggestions_section.html"
CATALOGUE_ITEMS_TEMPLATE = "gift_manager/includes/gift_suggestions_catalogue_items.html"


def suggestions_url_for(recipient: Person | PersonGroup) -> str:
    """Return the base suggestions URL for a recipient."""
    if isinstance(recipient, Person):
        return reverse("gift_manager:person_suggestions", kwargs={"pk": recipient.person_id})
    return reverse("gift_manager:person_group_suggestions", kwargs={"pk": recipient.group_id})


def _get_recipient_or_404(user, pk: uuid.UUID, *, is_person: bool) -> Person | PersonGroup:
    if is_person:
        return get_object_or_404(Person.objects.accessible_by(user), person_id=pk)
    return get_object_or_404(PersonGroup.objects.accessible_by(user), group_id=pk)


def _render_suggestions(request, recipient: Person | PersonGroup) -> HttpResponse:
    raw_offset = request.GET.get("offset", 0)
    try:
        offset = int(raw_offset)
        offset = max(offset, 0)
    except (ValueError, TypeError):
        offset = 0

    surface = request.GET.get("surface", "")
    service = GiftSuggestionService(request.user, recipient)
    page = service.catalogue_page(offset=offset)

    candidates = [
        dataclasses.replace(c, reason_text=describe_reason(c.reason, recipient))
        for c in page.candidates
    ]

    context = {
        "recipient": recipient,
        "is_person": isinstance(recipient, Person),
        "candidates": candidates,
        "next_offset": page.next_offset,
        "suggestions_url": suggestions_url_for(recipient),
        "surface": surface,
        "ai_enabled": service.ai_enabled,
    }

    if offset > 0:
        return render(request, CATALOGUE_ITEMS_TEMPLATE, context)
    return render(request, SUGGESTIONS_SECTION_TEMPLATE, context)


def _handle_accept(request, recipient: Person | PersonGroup) -> HttpResponse:
    gift_raw = request.POST.get("gift")
    if not gift_raw:
        raise Http404
    try:
        gift_uuid = uuid.UUID(gift_raw)
    except (ValueError, TypeError):
        raise Http404 from None

    service = GiftSuggestionService(request.user, recipient)
    service.accept_gift(gift_uuid)

    surface = request.POST.get("surface", "")
    is_htmx = getattr(request, "htmx", False) or request.headers.get("HX-Request") == "true"
    if not is_htmx:
        if isinstance(recipient, Person):
            return redirect("gift_manager:person_detail", pk=recipient.person_id)
        return redirect("gift_manager:person_group_detail", pk=recipient.group_id)

    if surface == "page":
        response = HttpResponse(status=204)
        response["HX-Refresh"] = "true"
        return response

    response = _render_suggestions(request, recipient)
    response["HX-Trigger"] = HTMXResponseMixin.build_hx_trigger_header(["list:update"])
    return response


def _handle_dismiss(request, recipient: Person | PersonGroup) -> HttpResponse:
    gift_raw = request.POST.get("gift")
    if not gift_raw:
        raise Http404
    try:
        gift_uuid = uuid.UUID(gift_raw)
    except (ValueError, TypeError):
        raise Http404 from None

    service = GiftSuggestionService(request.user, recipient)
    service.dismiss_gift(gift_uuid)

    is_htmx = getattr(request, "htmx", False) or request.headers.get("HX-Request") == "true"
    if not is_htmx:
        if isinstance(recipient, Person):
            return redirect("gift_manager:person_detail", pk=recipient.person_id)
        return redirect("gift_manager:person_group_detail", pk=recipient.group_id)

    return _render_suggestions(request, recipient)


@login_required
@require_GET
def person_suggestions(request, pk: uuid.UUID) -> HttpResponse:
    """Return catalogue and AI suggestions for a person."""
    recipient = _get_recipient_or_404(request.user, pk, is_person=True)
    return _render_suggestions(request, recipient)


@login_required
@require_POST
def person_suggestion_accept(request, pk: uuid.UUID) -> HttpResponse:
    """Accept a suggestion for a person and create an Idea plan."""
    recipient = _get_recipient_or_404(request.user, pk, is_person=True)
    return _handle_accept(request, recipient)


@login_required
@require_POST
def person_suggestion_dismiss(request, pk: uuid.UUID) -> HttpResponse:
    """Dismiss a suggestion for a person."""
    recipient = _get_recipient_or_404(request.user, pk, is_person=True)
    return _handle_dismiss(request, recipient)


@login_required
@require_GET
def person_group_suggestions(request, pk: uuid.UUID) -> HttpResponse:
    """Return catalogue and AI suggestions for a group."""
    recipient = _get_recipient_or_404(request.user, pk, is_person=False)
    return _render_suggestions(request, recipient)


@login_required
@require_POST
def person_group_suggestion_accept(request, pk: uuid.UUID) -> HttpResponse:
    """Accept a suggestion for a group and create an Idea plan."""
    recipient = _get_recipient_or_404(request.user, pk, is_person=False)
    return _handle_accept(request, recipient)


@login_required
@require_POST
def person_group_suggestion_dismiss(request, pk: uuid.UUID) -> HttpResponse:
    """Dismiss a suggestion for a group."""
    recipient = _get_recipient_or_404(request.user, pk, is_person=False)
    return _handle_dismiss(request, recipient)
