"""Group gift views and HTMX endpoints."""

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.utils.translation import gettext
from django.views.decorators.http import require_POST

from gift_manager import group_gifts
from gift_manager.forms import GroupGiftContributorForm
from gift_manager.forms import GroupGiftCustomAmountForm
from gift_manager.models import Relation
from gift_manager.models import RelationContribution
from gift_manager.models import SplitMode
from gift_manager.plan_coordination import is_recipient_of_plan

GROUP_GIFT_PARTIAL = "gift_manager/includes/relation_group_gift_partial.html"


def _plan_or_404(request, pk) -> Relation:
    """Retrieve relation or raise 404/403 with strict recipient privacy."""
    relation = get_object_or_404(
        Relation.objects.accessible_by(request.user).select_related(
            "person", "group", "claimed_by"
        ),
        relation_id=pk,
    )
    if is_recipient_of_plan(relation, request.user):
        raise PermissionDenied(gettext("You do not have permission to do this on this gift plan."))
    return relation


def _render_group_gift_response(
    request,
    relation: Relation,
    *,
    status: int = 200,
    error: str = "",
    contributor_form: GroupGiftContributorForm | None = None,
    error_contribution_id: int | None = None,
) -> HttpResponse | HttpResponseRedirect:
    """Render the HTMX partial or redirect to relation detail for standard POST."""
    if request.headers.get("HX-Request") != "true":
        if error:
            messages.error(request, error)
        return redirect(f"{relation.get_absolute_url()}#relation-group-gift")

    summary = group_gifts.get_group_gift_summary(relation, request.user)
    if contributor_form is None and summary.can_manage:
        contributor_form = GroupGiftContributorForm(relation=relation)

    return render(
        request,
        GROUP_GIFT_PARTIAL,
        {
            "relation": relation,
            "group_gift": summary,
            "contributor_form": contributor_form,
            "error": error,
            "error_contribution_id": error_contribution_id,
        },
        status=status,
    )


@login_required
@require_POST
def relation_group_gift_toggle(request, pk):
    """Enable or disable group gifting on a gift plan."""
    relation = _plan_or_404(request, pk)
    action = request.POST.get("action")
    try:
        if action == "disable" or (action is None and relation.is_group_gift):
            group_gifts.disable_group_gift(relation, request.user)
        else:
            group_gifts.enable_group_gift(relation, request.user)
    except ValidationError as exc:
        return _render_group_gift_response(
            request, relation, status=422, error=" ".join(exc.messages)
        )
    return _render_group_gift_response(request, relation)


@login_required
@require_POST
def relation_group_gift_mode(request, pk):
    """Switch split mode between EQUAL and CUSTOM."""
    relation = _plan_or_404(request, pk)
    target_mode = request.POST.get("split_mode")
    if not target_mode:
        target_mode = (
            SplitMode.CUSTOM if relation.split_mode == SplitMode.EQUAL else SplitMode.EQUAL
        )
    if target_mode not in SplitMode.values:
        return _render_group_gift_response(
            request, relation, status=422, error=gettext("Invalid split mode.")
        )
    try:
        group_gifts.set_split_mode(relation, request.user, target_mode)
    except ValidationError as exc:
        return _render_group_gift_response(
            request, relation, status=422, error=" ".join(exc.messages)
        )
    return _render_group_gift_response(request, relation)


@login_required
@require_POST
def relation_group_gift_contributor_add(request, pk):
    """Add a contributor (plan collaborator or external individual)."""
    relation = _plan_or_404(request, pk)
    form = GroupGiftContributorForm(request.POST, relation=relation)
    if not form.is_valid():
        error = (
            form.non_field_errors()[0]
            if form.non_field_errors()
            else " ".join([f"{errs[0]}" for f, errs in form.errors.items()])
        )
        return _render_group_gift_response(
            request, relation, status=422, error=error, contributor_form=form
        )
    try:
        group_gifts.add_contributor(
            relation,
            request.user,
            user=form.cleaned_data.get("user"),
            name=form.cleaned_data.get("name") or "",
            amount=form.cleaned_data.get("amount") or Decimal("0.00"),
        )
    except ValidationError as exc:
        return _render_group_gift_response(
            request, relation, status=422, error=" ".join(exc.messages), contributor_form=form
        )
    return _render_group_gift_response(request, relation)


@login_required
@require_POST
def relation_group_gift_contributor_remove(request, pk, contribution_id):
    """Remove a contributor from the group gift."""
    relation = _plan_or_404(request, pk)
    contrib = RelationContribution.objects.filter(pk=contribution_id, relation=relation).first()
    if contrib is None:
        # Idempotent removal
        return _render_group_gift_response(request, relation)
    try:
        group_gifts.remove_contributor(contrib, request.user)
    except ValidationError as exc:
        return _render_group_gift_response(
            request, relation, status=422, error=" ".join(exc.messages)
        )
    return _render_group_gift_response(request, relation)


@login_required
@require_POST
def relation_group_gift_contributor_toggle_paid(request, pk, contribution_id):
    """Toggle a contributor's paid status."""
    relation = _plan_or_404(request, pk)
    contrib = get_object_or_404(RelationContribution, pk=contribution_id, relation=relation)
    try:
        group_gifts.toggle_contribution_paid(contrib, request.user)
    except ValidationError as exc:
        return _render_group_gift_response(
            request,
            relation,
            status=422,
            error=" ".join(exc.messages),
            error_contribution_id=contribution_id,
        )
    return _render_group_gift_response(request, relation)


@login_required
@require_POST
def relation_group_gift_contributor_amount(request, pk, contribution_id):
    """Update custom contribution share amount."""
    relation = _plan_or_404(request, pk)
    contrib = get_object_or_404(RelationContribution, pk=contribution_id, relation=relation)
    form = GroupGiftCustomAmountForm(request.POST)
    if not form.is_valid():
        error = " ".join([f"{errs[0]}" for f, errs in form.errors.items()])
        return _render_group_gift_response(
            request,
            relation,
            status=422,
            error=error,
            error_contribution_id=contribution_id,
        )
    try:
        group_gifts.update_contribution_amount(contrib, request.user, form.cleaned_data["amount"])
    except ValidationError as exc:
        return _render_group_gift_response(
            request,
            relation,
            status=422,
            error=" ".join(exc.messages),
            error_contribution_id=contribution_id,
        )
    return _render_group_gift_response(request, relation)
