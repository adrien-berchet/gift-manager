"""Claim, release and comment actions on a gift plan.

Every endpoint looks the plan up through ``Relation.objects.accessible_by``, so a user who cannot
see a plan (a stranger, or the recipient of a surprise) gets a 404, never a 403. HTMX requests get
the refreshed coordination fragment; other requests are redirected to the plan, with a message
when the action was refused.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.utils.translation import gettext
from django.views.decorators.http import require_POST

from gift_manager import plan_coordination
from gift_manager.models import Relation
from gift_manager.models import RelationComment

COORDINATION_TEMPLATE = "gift_manager/includes/relation_coordination_partial.html"


def _plan_or_404(request, pk) -> Relation:
    return get_object_or_404(Relation.objects.accessible_by(request.user), relation_id=pk)


def _respond(
    request, relation, *, status=200, error="", comment_text=""
) -> HttpResponse | HttpResponseRedirect:
    """Return the refreshed fragment (HTMX) or redirect to the plan (anything else)."""
    if request.headers.get("HX-Request") != "true":
        if error:
            messages.error(request, error)
        return redirect(relation.get_absolute_url())
    relation = Relation.objects.select_related("claimed_by").get(pk=relation.pk)
    return render(
        request,
        COORDINATION_TEMPLATE,
        {
            "relation": relation,
            "coordination": plan_coordination.coordination_context(relation, request.user),
            "error": error,
            "comment_text": comment_text,
        },
        status=status,
    )


@login_required
@require_POST
def relation_claim(request, pk):
    """Claim the plan for the requesting user."""
    relation = _plan_or_404(request, pk)
    try:
        plan_coordination.claim(relation, request.user)
    except plan_coordination.AlreadyClaimed as exc:
        error = gettext("%(name)s has already claimed this gift plan.") % {
            "name": exc.claimed_by.username if exc.claimed_by else gettext("Someone")
        }
        return _respond(request, relation, status=409, error=error)
    return _respond(request, relation)


@login_required
@require_POST
def relation_release(request, pk):
    """Release the claim on the plan (its claimer or an owner)."""
    relation = _plan_or_404(request, pk)
    plan_coordination.release(relation, request.user)
    return _respond(request, relation)


@login_required
@require_POST
def relation_comment_add(request, pk):
    """Add a comment from the requesting user to the plan."""
    relation = _plan_or_404(request, pk)
    text = request.POST.get("text", "")
    try:
        plan_coordination.add_comment(relation, request.user, text)
    except ValidationError as exc:
        return _respond(
            request, relation, status=422, error=" ".join(exc.messages), comment_text=text
        )
    return _respond(request, relation)


@login_required
@require_POST
def relation_comment_delete(request, pk, comment_id):
    """Delete a comment of the plan (its author or an owner)."""
    relation = _plan_or_404(request, pk)
    comment = get_object_or_404(RelationComment, pk=comment_id, relation=relation)
    plan_coordination.delete_comment(comment, request.user)
    return _respond(request, relation)
