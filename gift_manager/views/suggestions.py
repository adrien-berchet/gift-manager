"""Views for recipient gift plan suggestions."""

import dataclasses
import uuid

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.http import HttpResponse
from django.http import HttpResponseBadRequest
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET
from django.views.decorators.http import require_POST

from gift_manager.models import GiftSuggestion
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.person_profile import append_person_provenance_note
from gift_manager.person_profile import promote_tags_to_person_interests
from gift_manager.person_profile import promotion_target
from gift_manager.suggestions.catalogue import describe_reason
from gift_manager.suggestions.occasions import derive_default_occasion
from gift_manager.suggestions.occasions import get_upcoming_occasions
from gift_manager.suggestions.service import AI_BATCH_SIZE
from gift_manager.suggestions.service import GiftSuggestionService
from gift_manager.suggestions.service import normalize_dismiss_input
from gift_manager.views.base import HTMXResponseMixin

SUGGESTIONS_SECTION_TEMPLATE = "gift_manager/includes/gift_suggestions_section.html"
CATALOGUE_ITEMS_TEMPLATE = "gift_manager/includes/gift_suggestions_catalogue_items.html"
AI_BLOCK_TEMPLATE = "gift_manager/includes/gift_suggestions_ai_block.html"
DISMISSED_PANEL_TEMPLATE = "gift_manager/includes/gift_suggestions_dismissed_panel.html"


def suggestions_url_for(recipient: Person | PersonGroup) -> str:
    """Return the base suggestions URL for a recipient."""
    if isinstance(recipient, Person):
        return reverse("gift_manager:person_suggestions", kwargs={"pk": recipient.person_id})
    return reverse("gift_manager:person_group_suggestions", kwargs={"pk": recipient.group_id})


def ideas_url_for(recipient: Person | PersonGroup) -> str:
    """Return the ideas URL for a recipient."""
    if isinstance(recipient, Person):
        return reverse("gift_manager:person_suggestion_ideas", kwargs={"pk": recipient.person_id})
    return reverse("gift_manager:person_group_suggestion_ideas", kwargs={"pk": recipient.group_id})


def dismissed_url_for(recipient: Person | PersonGroup) -> str:
    """Return the dismissed suggestions URL for a recipient."""
    if isinstance(recipient, Person):
        return reverse(
            "gift_manager:person_suggestions_dismissed", kwargs={"pk": recipient.person_id}
        )
    return reverse(
        "gift_manager:person_group_suggestions_dismissed", kwargs={"pk": recipient.group_id}
    )


def restore_url_for(recipient: Person | PersonGroup) -> str:
    """Return the restore suggestion URL for a recipient."""
    if isinstance(recipient, Person):
        return reverse("gift_manager:person_suggestion_restore", kwargs={"pk": recipient.person_id})
    return reverse(
        "gift_manager:person_group_suggestion_restore", kwargs={"pk": recipient.group_id}
    )


def purge_url_for(recipient: Person | PersonGroup) -> str:
    """Return the purge suggestion URL for a recipient."""
    if isinstance(recipient, Person):
        return reverse("gift_manager:person_suggestion_purge", kwargs={"pk": recipient.person_id})
    return reverse("gift_manager:person_group_suggestion_purge", kwargs={"pk": recipient.group_id})


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
        "ideas_url": ideas_url_for(recipient) if service.ai_enabled else "",
        "dismissed_url": dismissed_url_for(recipient),
        "dismissed_count": service.dismissed_count(),
        "surface": surface,
        "ai_enabled": service.ai_enabled,
        "can_promote_to_profile": promotion_target(request.user, recipient) is not None,
    }

    if offset > 0:
        return render(request, CATALOGUE_ITEMS_TEMPLATE, context)
    return render(request, SUGGESTIONS_SECTION_TEMPLATE, context)


def _render_ai_block(
    request,
    recipient: Person | PersonGroup,
    block,
    occasion: str | None = None,
    budget: str = "",
    hint: str = "",
    upcoming_occasions=None,
) -> HttpResponse:
    surface = request.GET.get("surface") or request.POST.get("surface", "")
    if upcoming_occasions is None:
        upcoming_occasions = get_upcoming_occasions(request.user, recipient)

    valid_occasion_names = {occ["name"] for occ in upcoming_occasions}
    if occasion is None:
        selected_occasion = derive_default_occasion(upcoming_occasions)
    elif occasion in valid_occasion_names:
        selected_occasion = occasion
    else:
        selected_occasion = ""

    currency_code = getattr(getattr(request.user, "profile", None), "currency", "EUR") or "EUR"
    currency_symbol = {"EUR": "€", "USD": "$", "GBP": "£"}.get(currency_code, currency_code)

    context = {
        "recipient": recipient,
        "is_person": isinstance(recipient, Person),
        "block": block,
        "ideas_url": ideas_url_for(recipient),
        "surface": surface,
        "upcoming_occasions": upcoming_occasions,
        "selected_occasion": selected_occasion,
        "selected_budget": budget,
        "current_hint": hint,
        "currency_symbol": currency_symbol,
        "can_promote_to_profile": promotion_target(request.user, recipient) is not None,
    }
    return render(request, AI_BLOCK_TEMPLATE, context)


def _handle_ideas(request, recipient: Person | PersonGroup) -> HttpResponse:
    service = GiftSuggestionService(request.user, recipient)
    if request.method == "POST":
        count_raw = request.POST.get("count")
        occasion_raw = (request.POST.get("occasion") or "").strip()
        budget_raw = (request.POST.get("budget") or "").strip()
        hint = (request.POST.get("hint") or "").strip()[:120]

        upcoming_occasions = get_upcoming_occasions(request.user, recipient)
        valid_occasion_names = {occ["name"] for occ in upcoming_occasions}
        occasion = occasion_raw if occasion_raw in valid_occasion_names else ""
        budget = budget_raw if budget_raw in {"under_30", "30_75", "over_75"} else ""

        count = AI_BATCH_SIZE
        if count_raw is not None:
            try:
                count = max(1, min(int(count_raw), 5))
            except (ValueError, TypeError):
                count = AI_BATCH_SIZE
        block = service.request_more_ideas(count=count, occasion=occasion, budget=budget, hint=hint)
        return _render_ai_block(
            request,
            recipient,
            block,
            occasion=occasion,
            budget=budget,
            hint=hint,
            upcoming_occasions=upcoming_occasions,
        )
    if request.method == "GET":
        block = service.ai_block()
        return _render_ai_block(request, recipient, block)
    return HttpResponseNotAllowed(["GET", "POST"])


def _handle_accept(request, recipient: Person | PersonGroup) -> HttpResponse:
    gift_raw = request.POST.get("gift")
    sugg_raw = request.POST.get("suggestion")

    if (gift_raw and sugg_raw) or (not gift_raw and not sugg_raw):
        return HttpResponseBadRequest(_("Provide either gift or suggestion."))

    service = GiftSuggestionService(request.user, recipient)

    if gift_raw:
        try:
            gift_uuid = uuid.UUID(gift_raw)
        except (ValueError, TypeError):
            raise Http404 from None
        service.accept_gift(gift_uuid)
    else:
        try:
            sugg_uuid = uuid.UUID(sugg_raw)
        except (ValueError, TypeError):
            raise Http404 from None
        service.accept_suggestion(sugg_uuid)

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


def _promote_dismissal_to_profile(
    user,
    recipient: Person | PersonGroup,
    suggestion: GiftSuggestion,
    reason: str,
    comment: str,
) -> bool:
    target_person = promotion_target(user, recipient)
    if not target_person:
        return False

    item_name = (
        suggestion.gift.name if (suggestion.gift_id and suggestion.gift) else suggestion.name
    )
    tags = (
        suggestion.gift.tags.all()
        if (suggestion.gift_id and suggestion.gift)
        else suggestion.tags.all()
    )

    note_text = comment
    if not note_text and reason == GiftSuggestion.DismissReason.ALREADY_OWNED_OR_PRACTICED:
        note_text = _("Already owned or practiced")

    promoted = False
    if note_text and append_person_provenance_note(
        target_person,
        source_label=_("Suggestion"),
        item_name=item_name,
        text=note_text,
    ):
        promoted = True

    if reason == GiftSuggestion.DismissReason.ALREADY_OWNED_OR_PRACTICED:
        added_tags = promote_tags_to_person_interests(target_person, tags, user)
        if added_tags:
            promoted = True

    return promoted


def _handle_dismiss(request, recipient: Person | PersonGroup) -> HttpResponse:
    gift_raw = request.POST.get("gift")
    sugg_raw = request.POST.get("suggestion")

    if (gift_raw and sugg_raw) or (not gift_raw and not sugg_raw):
        return HttpResponseBadRequest(_("Provide either gift or suggestion."))

    service = GiftSuggestionService(request.user, recipient)
    reason, comment = normalize_dismiss_input(
        request.POST.get("reason", ""), request.POST.get("comment", "")
    )

    if gift_raw:
        try:
            gift_uuid = uuid.UUID(gift_raw)
        except (ValueError, TypeError):
            raise Http404 from None
        suggestion = service.dismiss_gift(gift_uuid, reason=reason, comment=comment)
    else:
        try:
            sugg_uuid = uuid.UUID(sugg_raw)
        except (ValueError, TypeError):
            raise Http404 from None
        suggestion = service.dismiss_suggestion(sugg_uuid, reason=reason, comment=comment)

    promoted = False
    if request.POST.get("promote_to_profile") == "1":
        promoted = _promote_dismissal_to_profile(
            request.user, recipient, suggestion, reason, comment
        )

    is_htmx = getattr(request, "htmx", False) or request.headers.get("HX-Request") == "true"
    if not is_htmx:
        if isinstance(recipient, Person):
            return redirect("gift_manager:person_detail", pk=recipient.person_id)
        return redirect("gift_manager:person_group_detail", pk=recipient.group_id)

    response = _render_suggestions(request, recipient)
    if promoted:
        response["HX-Trigger"] = HTMXResponseMixin.build_hx_trigger_header(
            [
                {
                    "showNotification": {
                        "message": _("Preference remembered in recipient's profile."),
                        "type": "info",
                    }
                }
            ]
        )
    return response


def _render_dismissed_panel(request, recipient: Person | PersonGroup) -> HttpResponse:
    service = GiftSuggestionService(request.user, recipient)
    items = service.dismissed_suggestions()
    context = {
        "recipient": recipient,
        "is_person": isinstance(recipient, Person),
        "items": items,
        "restore_url": restore_url_for(recipient),
        "purge_url": purge_url_for(recipient),
    }
    return render(request, DISMISSED_PANEL_TEMPLATE, context)


def _handle_restore(request, recipient: Person | PersonGroup) -> HttpResponse:
    gift_raw = request.POST.get("gift")
    sugg_raw = request.POST.get("suggestion")

    if (gift_raw and sugg_raw) or (not gift_raw and not sugg_raw):
        return HttpResponseBadRequest(_("Provide either gift or suggestion."))

    service = GiftSuggestionService(request.user, recipient)

    if gift_raw:
        try:
            gift_uuid = uuid.UUID(gift_raw)
        except (ValueError, TypeError):
            raise Http404 from None
        service.restore_gift(gift_uuid)
    else:
        try:
            sugg_uuid = uuid.UUID(sugg_raw)
        except (ValueError, TypeError):
            raise Http404 from None
        service.restore_suggestion(sugg_uuid)

    is_htmx = getattr(request, "htmx", False) or request.headers.get("HX-Request") == "true"
    if not is_htmx:
        if isinstance(recipient, Person):
            return redirect("gift_manager:person_detail", pk=recipient.person_id)
        return redirect("gift_manager:person_group_detail", pk=recipient.group_id)

    response = _render_dismissed_panel(request, recipient)
    response["HX-Trigger"] = HTMXResponseMixin.build_hx_trigger_header(["suggestions:refresh"])
    return response


def _handle_purge(request, recipient: Person | PersonGroup) -> HttpResponse:
    gift_raw = request.POST.get("gift")
    sugg_raw = request.POST.get("suggestion")

    if (gift_raw and sugg_raw) or (not gift_raw and not sugg_raw):
        return HttpResponseBadRequest(_("Provide either gift or suggestion."))

    service = GiftSuggestionService(request.user, recipient)

    if gift_raw:
        try:
            gift_uuid = uuid.UUID(gift_raw)
        except (ValueError, TypeError):
            raise Http404 from None
        service.purge_gift(gift_uuid)
    else:
        try:
            sugg_uuid = uuid.UUID(sugg_raw)
        except (ValueError, TypeError):
            raise Http404 from None
        service.purge_suggestion(sugg_uuid)

    is_htmx = getattr(request, "htmx", False) or request.headers.get("HX-Request") == "true"
    if not is_htmx:
        if isinstance(recipient, Person):
            return redirect("gift_manager:person_detail", pk=recipient.person_id)
        return redirect("gift_manager:person_group_detail", pk=recipient.group_id)

    response = _render_dismissed_panel(request, recipient)
    response["HX-Trigger"] = HTMXResponseMixin.build_hx_trigger_header(["suggestions:refresh"])
    return response


@login_required
@require_GET
def person_suggestions(request, pk: uuid.UUID) -> HttpResponse:
    """Return catalogue and AI suggestions for a person."""
    recipient = _get_recipient_or_404(request.user, pk, is_person=True)
    return _render_suggestions(request, recipient)


@login_required
def person_suggestion_ideas(request, pk: uuid.UUID) -> HttpResponse:
    """Return or generate AI ideas for a person."""
    recipient = _get_recipient_or_404(request.user, pk, is_person=True)
    return _handle_ideas(request, recipient)


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
def person_suggestions_dismissed(request, pk: uuid.UUID) -> HttpResponse:
    """Return the list of dismissed suggestions for a person."""
    recipient = _get_recipient_or_404(request.user, pk, is_person=True)
    return _render_dismissed_panel(request, recipient)


@login_required
@require_POST
def person_suggestion_restore(request, pk: uuid.UUID) -> HttpResponse:
    """Restore a dismissed suggestion for a person."""
    recipient = _get_recipient_or_404(request.user, pk, is_person=True)
    return _handle_restore(request, recipient)


@login_required
@require_POST
def person_suggestion_purge(request, pk: uuid.UUID) -> HttpResponse:
    """Permanently delete a dismissed suggestion record for a person."""
    recipient = _get_recipient_or_404(request.user, pk, is_person=True)
    return _handle_purge(request, recipient)


@login_required
@require_GET
def person_group_suggestions(request, pk: uuid.UUID) -> HttpResponse:
    """Return catalogue and AI suggestions for a group."""
    recipient = _get_recipient_or_404(request.user, pk, is_person=False)
    return _render_suggestions(request, recipient)


@login_required
def person_group_suggestion_ideas(request, pk: uuid.UUID) -> HttpResponse:
    """Return or generate AI ideas for a group."""
    recipient = _get_recipient_or_404(request.user, pk, is_person=False)
    return _handle_ideas(request, recipient)


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


@login_required
@require_GET
def person_group_suggestions_dismissed(request, pk: uuid.UUID) -> HttpResponse:
    """Return the list of dismissed suggestions for a group."""
    recipient = _get_recipient_or_404(request.user, pk, is_person=False)
    return _render_dismissed_panel(request, recipient)


@login_required
@require_POST
def person_group_suggestion_restore(request, pk: uuid.UUID) -> HttpResponse:
    """Restore a dismissed suggestion for a group."""
    recipient = _get_recipient_or_404(request.user, pk, is_person=False)
    return _handle_restore(request, recipient)


@login_required
@require_POST
def person_group_suggestion_purge(request, pk: uuid.UUID) -> HttpResponse:
    """Permanently delete a dismissed suggestion record for a group."""
    recipient = _get_recipient_or_404(request.user, pk, is_person=False)
    return _handle_purge(request, recipient)
