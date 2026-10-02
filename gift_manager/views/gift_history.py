"""Gift history and repeat-gift hint views (HTMX partials)."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import render
from django.views.decorators.http import require_GET

from gift_manager.forms import resolve_recipient_choice
from gift_manager.gift_history import build_gift_history
from gift_manager.gift_history import find_repeat_gift_plans
from gift_manager.gift_history import group_history_queryset
from gift_manager.gift_history import person_history_queryset
from gift_manager.interests import gifts_matching_interests
from gift_manager.metadata_visibility import VisibleMetadata
from gift_manager.models import Gift
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import Relation

HISTORY_TEMPLATE = "gift_manager/includes/gift_history_partial.html"
REPEAT_HINT_TEMPLATE = "gift_manager/includes/repeat_gift_hint.html"


def _render_history(request, relations) -> HttpResponse:
    visible_group_ids = VisibleMetadata.for_request(request).group_ids
    return render(
        request,
        HISTORY_TEMPLATE,
        {"history": build_gift_history(relations, visible_group_ids)},
    )


@login_required
@require_GET
def person_gift_history(request, pk):
    """Return the gift history of a person the user can access."""
    person = get_object_or_404(
        Person.objects.accessible_by(request.user).prefetch_related("groups"), person_id=pk
    )
    return _render_history(request, person_history_queryset(request.user, person))


@login_required
@require_GET
def person_group_gift_history(request, pk):
    """Return the gift history of a group the user can access."""
    group = get_object_or_404(PersonGroup.objects.accessible_by(request.user), group_id=pk)
    return _render_history(request, group_history_queryset(request.user, group))


@login_required
@require_GET
def repeat_gift_hint(request):
    """Return non-blocking hints for the plan form's recipient and gift.

    Two hints share one request: gifts matching the recipient's interests, and a warning
    when the chosen gift is already planned for the same recipient.
    """
    user = request.user
    context = {"repeats": [], "suggestions": []}
    try:
        person, group = resolve_recipient_choice(request.GET.get("recipient", ""), user)
    except ValidationError:
        return render(request, REPEAT_HINT_TEMPLATE, context)

    if person is not None:
        context["suggestions"] = gifts_matching_interests(user, person)

    try:
        gift = Gift.objects.accessible_by(user).get(pk=int(request.GET.get("gift", "")))
        edited = None
        if request.GET.get("relation"):
            edited = Relation.objects.accessible_by(user).get(relation_id=request.GET["relation"])
    except (ValidationError, ValueError, Gift.DoesNotExist, Relation.DoesNotExist):
        return render(request, REPEAT_HINT_TEMPLATE, context)

    context["gift"] = gift
    context["repeats"] = find_repeat_gift_plans(
        user, person=person, group=group, gift=gift, exclude=edited
    )
    return render(request, REPEAT_HINT_TEMPLATE, context)
