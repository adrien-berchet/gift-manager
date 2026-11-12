"""Views for received gifts management (personal log)."""

import json
import uuid
from collections import defaultdict
from datetime import MAXYEAR
from datetime import MINYEAR
from typing import Any

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.urls import reverse_lazy
from django.utils import formats
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView
from django.views.generic import UpdateView
from django.views.generic import View

from gift_manager.forms import ReceivedGiftForm
from gift_manager.forms import RelationRevealForm
from gift_manager.forms import person_group_choices
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import ReceivedGift
from gift_manager.models import Relation
from gift_manager.models import Wish
from gift_manager.received_gifts import ShareReactionResult
from gift_manager.received_gifts import annotate_snapshot_givers
from gift_manager.received_gifts import can_reveal_plan
from gift_manager.received_gifts import can_share_reaction
from gift_manager.received_gifts import get_reveal_targets
from gift_manager.received_gifts import linkable_giver_ids
from gift_manager.received_gifts import reveal_plan
from gift_manager.received_gifts import share_reaction_feedback
from gift_manager.received_gifts import user_is_plan_owner
from gift_manager.services import PermissionService
from gift_manager.validators import validate_http_url
from gift_manager.views.base import HTMXResponseMixin
from gift_manager.wishlist import own_received_gifts

User = get_user_model()


def _parse_giver_filter(raw_giver: str) -> tuple[str, Q | None]:
    """Parse ``person:<uuid>``, ``group:<uuid>``, or a bare UUID into a queryset filter."""
    if not raw_giver:
        return "", None
    kind = None
    uuid_part = raw_giver
    if raw_giver.startswith("person:"):
        kind = "person"
        uuid_part = raw_giver.removeprefix("person:")
    elif raw_giver.startswith("group:"):
        kind = "group"
        uuid_part = raw_giver.removeprefix("group:")

    try:
        parsed = uuid.UUID(uuid_part)
    except ValueError:
        return "", None

    if kind == "person":
        return f"person:{parsed}", Q(giver_persons__person_id=parsed)
    if kind == "group":
        return f"group:{parsed}", Q(giver_groups__group_id=parsed)
    return str(parsed), Q(giver_persons__person_id=parsed) | Q(giver_groups__group_id=parsed)


class ReceivedGiftListView(LoginRequiredMixin, View):
    """List received gifts for the authenticated user, grouped by year."""

    template_name = "gift_manager/received_gift_list.html"
    partial_template_name = "gift_manager/includes/received_gift_list_partial.html"

    def get(self, request, *args, **kwargs):
        user = request.user
        queryset = (
            ReceivedGift.objects.for_user(user)
            .prefetch_related("giver_persons", "giver_groups", "giver_accounts")
            .select_related("event", "wish")
        )

        filter_year = request.GET.get("year", "").strip()
        filter_giver_raw = request.GET.get("giver", "").strip()
        filter_occasion = request.GET.get("occasion", "").strip()
        filter_thank_you = request.GET.get("thank_you", "").strip()

        if filter_year:
            try:
                year = int(filter_year)
            except ValueError:
                year = None
            if year is not None and MINYEAR <= year <= MAXYEAR:
                queryset = queryset.filter(received_on__year=year)
            else:
                filter_year = ""

        filter_giver, giver_query = _parse_giver_filter(filter_giver_raw)
        if giver_query is not None:
            queryset = queryset.filter(giver_query).distinct()

        if filter_occasion:
            queryset = queryset.filter(
                Q(occasion_text__icontains=filter_occasion)
                | Q(event__name__icontains=filter_occasion)
            ).distinct()

        if filter_thank_you in {"pending", "0", "false"}:
            filter_thank_you = "pending"
            queryset = queryset.filter(thank_you_sent=False)
        elif filter_thank_you in {"sent", "1", "true"}:
            filter_thank_you = "sent"
            queryset = queryset.filter(thank_you_sent=True)
        else:
            filter_thank_you = ""

        all_user_gifts = ReceivedGift.objects.for_user(user)
        pending_thank_you_count = all_user_gifts.filter(thank_you_sent=False).count()

        # Available years for filter dropdown
        available_years = sorted(
            {d.year for d in all_user_gifts.values_list("received_on", flat=True) if d},
            reverse=True,
        )

        # Available givers (accessible people and groups linked on the user's received gifts)
        giver_person_pks = all_user_gifts.values_list("giver_persons", flat=True).distinct()
        giver_group_pks = all_user_gifts.values_list("giver_groups", flat=True).distinct()
        available_persons = (
            Person.objects.accessible_by(user)
            .filter(pk__in=giver_person_pks)
            .order_by("family_name", "first_name")
        )
        available_groups = (
            PersonGroup.objects.accessible_by(user).filter(pk__in=giver_group_pks).order_by("name")
        )
        available_giver_choices = person_group_choices(available_persons, available_groups)

        # Group gifts by year (newest first)
        by_year = defaultdict(list)
        for item in queryset:
            year = item.received_on.year if item.received_on else None
            by_year[year].append(item)

        grouped_gifts = [
            (year, by_year[year])
            for year in sorted(by_year.keys(), key=lambda y: (y is None, -(y or 0)))
        ]
        listed_gifts = [gift for gifts in by_year.values() for gift in gifts]
        annotate_snapshot_givers(user, listed_gifts)
        linkable_person_ids, linkable_group_ids = linkable_giver_ids(user, listed_gifts)

        context = {
            "grouped_gifts": grouped_gifts,
            "pending_thank_you_count": pending_thank_you_count,
            "available_years": available_years,
            "available_giver_choices": available_giver_choices,
            "filter_year": filter_year,
            "filter_giver": filter_giver,
            "filter_occasion": filter_occasion,
            "filter_thank_you": filter_thank_you,
            "linkable_person_ids": linkable_person_ids,
            "linkable_group_ids": linkable_group_ids,
        }

        if request.headers.get("HX-Request") == "true":
            return render(request, self.partial_template_name, context)
        return render(request, self.template_name, context)


class ReceivedGiftDetailView(LoginRequiredMixin, View):
    """View details of a received gift."""

    template_name = "gift_manager/received_gift_detail.html"
    partial_template_name = "gift_manager/includes/received_gift_detail_partial.html"

    def get(self, request, pk, *args, **kwargs):
        gift = get_object_or_404(
            ReceivedGift.objects.for_user(request.user)
            .prefetch_related("giver_persons", "giver_groups", "giver_accounts")
            .select_related("event", "wish", "source_relation"),
            received_gift_id=pk,
        )

        annotate_snapshot_givers(request.user, [gift])
        linkable_person_ids, linkable_group_ids = linkable_giver_ids(request.user, [gift])
        context = {
            "gift": gift,
            "can_share_reaction": can_share_reaction(gift, request.user),
            "linkable_person_ids": linkable_person_ids,
            "linkable_group_ids": linkable_group_ids,
            "full_page_detail": request.GET.get("surface") == "page",
            # Received gifts are private to their recipient, who can always edit them
            "is_editor": True,
            "action_buttons": [
                {
                    "type": "edit",
                    "url": reverse(
                        "gift_manager:received_gift_edit", kwargs={"pk": gift.received_gift_id}
                    ),
                    "label": _("Edit received gift"),
                },
                {
                    "type": "delete",
                    "url": reverse(
                        "gift_manager:received_gift_delete", kwargs={"pk": gift.received_gift_id}
                    ),
                    "label": _("Delete received gift"),
                },
            ],
        }

        if request.headers.get("HX-Request") == "true":
            return render(request, self.partial_template_name, context)
        return render(request, self.template_name, context)


class _ReceivedGiftHTMXFormMixin(LoginRequiredMixin, HTMXResponseMixin):
    """Shared HTMX/page setup for creating and editing received gifts."""

    model = ReceivedGift
    form_class = ReceivedGiftForm
    template_name = "gift_manager/received_gift_form.html"
    htmx_template_name = "gift_manager/includes/received_gift_form_partial.html"
    success_url = reverse_lazy("gift_manager:received_gift_list")
    close_offcanvas = True
    action_label = ""
    success_message = ""

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["action"] = str(self.action_label)
        context["translated_type"] = gettext("Received Gift")
        context["form_surface"] = "offcanvas" if self.is_htmx else "page"
        context["cancel_url"] = self.success_url
        return context

    def get_success_message(self) -> str:
        return str(self.success_message)

    def form_valid(self, form: ReceivedGiftForm) -> HttpResponse:
        response = super().form_valid(form)
        if not self.is_htmx:
            messages.success(self.request, self.get_success_message())
        return response

    def form_invalid(self, form: ReceivedGiftForm) -> HttpResponse:
        response = super().form_invalid(form)
        if self.is_htmx:
            response["HX-Trigger"] = json.dumps(
                {
                    "showNotification": {
                        "message": gettext("Please correct the errors below."),
                        "type": "error",
                    }
                }
            )
        return response


class ReceivedGiftCreateView(_ReceivedGiftHTMXFormMixin, CreateView):
    """Record a new received gift."""

    action_label = _("Record")
    success_message = _("Received gift recorded successfully.")

    def get_initial(self):
        initial = super().get_initial()
        wish_id = self.request.GET.get("wish")
        if wish_id:
            try:
                wish = (
                    Wish.objects.for_wisher(self.request.user)
                    .filter(is_archived=False)
                    .get(wish_id=wish_id)
                )
                initial["wish"] = wish
                initial["title"] = wish.title
                initial["url"] = wish.url
                initial["description"] = wish.notes
            except (Wish.DoesNotExist, ValidationError):
                pass
        giver_id = self.request.GET.get("giver")
        if giver_id:
            try:
                person = Person.objects.accessible_by(self.request.user).get(person_id=giver_id)
                initial["givers"] = [f"person:{person.person_id}"]
            except (Person.DoesNotExist, ValidationError):
                pass
        return initial

    def form_valid(self, form):
        form.instance.recipient_user = self.request.user
        return super().form_valid(form)


class ReceivedGiftUpdateView(_ReceivedGiftHTMXFormMixin, UpdateView):
    """Edit an existing received gift."""

    action_label = _("Edit")
    success_message = _("Received gift updated successfully.")

    def get_queryset(self):
        return ReceivedGift.objects.for_user(self.request.user)

    def get_object(self, queryset=None):
        if queryset is None:
            queryset = self.get_queryset()
        return get_object_or_404(queryset, received_gift_id=self.kwargs.get("pk"))


class ReceivedGiftDeleteView(LoginRequiredMixin, HTMXResponseMixin, View):
    """Delete a received gift."""

    template_name = "gift_manager/received_gift_confirm_delete.html"
    htmx_template_name = "gift_manager/includes/delete_confirmation_modal.html"

    def get_object(self):
        return get_object_or_404(
            ReceivedGift.objects.for_user(self.request.user).select_related("wish"),
            received_gift_id=self.kwargs.get("pk"),
        )

    def get(self, request, *args, **kwargs):
        gift = self.get_object()
        if self.is_htmx:
            entity_details = [
                gettext("Date received: {date}").format(
                    date=formats.date_format(gift.received_on, "DATE_FORMAT")
                )
            ]
            if gift.wish_id:
                entity_details.append(
                    gettext(
                        "Deleting this received gift will update the fulfilled status on your "
                        "wishlist if no other plans or gifts fulfill it."
                    )
                )
            return render(
                request,
                self.htmx_template_name,
                {
                    "entity_type": gettext("Received Gift"),
                    "entity_name": gift.title,
                    "entity_description": gift.description or None,
                    "entity_icon": "box-open",
                    "entity_details": entity_details,
                    "delete_url": request.path,
                    "related_objects": [],
                },
            )
        return render(request, self.template_name, {"gift": gift})

    def post(self, request, *args, **kwargs):
        gift = self.get_object()
        gift.delete()

        success_message = gettext("Received gift deleted successfully.")

        if self.is_htmx:
            triggers = ["list:update", "modal:close"]
            triggers.append({"showNotification": {"message": success_message, "type": "success"}})
            response = HttpResponse("")
            response["HX-Reswap"] = "none"
            response["HX-Trigger"] = self.build_hx_trigger_header(triggers)
            return response

        messages.success(request, success_message)
        return redirect("gift_manager:received_gift_list")


class ReceivedGiftToggleFulfillsWishView(LoginRequiredMixin, View):
    """Count, or stop counting, a received gift as receiving its wish (from the wish panel)."""

    section_template_name = "gift_manager/includes/wish_received_section.html"

    def post(self, request, pk, *args, **kwargs):
        gift = get_object_or_404(
            ReceivedGift.objects.for_user(request.user)
            .filter(wish__wisher=request.user)
            .select_related("wish"),
            received_gift_id=pk,
        )
        gift.fulfills_wish = not gift.fulfills_wish
        gift.save(update_fields=["fulfills_wish"])  # the post_save signal re-derives the wish

        wish = gift.wish
        if request.headers.get("HX-Request") == "true":
            received_gifts = own_received_gifts(request.user, wish)
            linkable_person_ids, linkable_group_ids = linkable_giver_ids(
                request.user, received_gifts
            )
            context = {
                "wish": wish,
                "received_gifts": received_gifts,
                "linkable_person_ids": linkable_person_ids,
                "linkable_group_ids": linkable_group_ids,
            }
            response = render(request, self.section_template_name, context)
            response["HX-Trigger"] = json.dumps({"list:update": None})
            return response
        return redirect("gift_manager:wish_edit", wish_id=wish.wish_id)


class ReceivedGiftToggleThankYouView(LoginRequiredMixin, View):
    """Toggle thank-you sent flag on a received gift."""

    def post(self, request, pk, *args, **kwargs):
        gift = get_object_or_404(
            ReceivedGift.objects.for_user(request.user),
            received_gift_id=pk,
        )
        gift.thank_you_sent = not gift.thank_you_sent
        gift.save(update_fields=["thank_you_sent"])

        # No toast or flash message: the toggled button already shows the new state
        if request.headers.get("HX-Request") == "true":
            response = HttpResponse("")
            response["HX-Reswap"] = "none"
            response["HX-Trigger"] = json.dumps({"list:update": None})
            return response

        return redirect("gift_manager:received_gift_list")


def reveal_initial_data(relation: Relation) -> dict:
    """Compute prefill values for ``RelationRevealForm`` from ``relation``."""
    raw_url = (relation.url or (relation.gift.url if relation.gift else ""))[:2000]
    if raw_url:
        try:
            validate_http_url(raw_url)
        except ValidationError:
            raw_url = ""

    if relation.status_changed_at:
        initial_date = timezone.localdate(relation.status_changed_at)
    elif relation.due_date:
        initial_date = relation.due_date
    else:
        initial_date = timezone.localdate()

    return {
        "title": (relation.gift.name if relation.gift else "")[:255],
        "url": raw_url,
        "received_on": initial_date,
        "occasion_text": relation.event.name[:100] if relation.event else "",
    }


def build_relation_reveal_context(
    relation: Relation,
    user,
    form: RelationRevealForm,
    *,
    form_surface: str,
) -> dict[str, Any]:
    """Build template context shared by Reveal GET/POST and reaction chaining."""
    targets = get_reveal_targets(relation, user)
    owner_ids = [
        u_id
        for u_id, lvl in PermissionService.get_permission_map(relation).items()
        if lvl == PermissionLevel.OWNER
    ]
    co_owners = list(User.objects.filter(pk__in=owner_ids, is_active=True))
    defaults = reveal_initial_data(relation)
    expand_details = bool(
        form["title"].errors
        or form["received_on"].errors
        or form["occasion_text"].errors
        or form["url"].errors
        or not (str(form["title"].value() or "")).strip()
    )
    return {
        "relation": relation,
        "form": form,
        "preview": defaults,
        "expand_details": expand_details,
        "targets": targets,
        "co_owners": co_owners,
        "action": gettext("Reveal"),
        "translated_type": gettext("Gift Plan"),
        "submit_label": gettext("Reveal now"),
        "form_surface": form_surface,
        "cancel_url": reverse("gift_manager:relation_detail", kwargs={"pk": relation.relation_id}),
    }


def render_relation_reveal_form(
    request,
    relation: Relation,
    form: RelationRevealForm | None = None,
    *,
    form_surface: str = "offcanvas",
) -> HttpResponse:
    """Render the reveal form template for offcanvas or full page."""
    if form is None:
        form = RelationRevealForm(initial=reveal_initial_data(relation))
    template = (
        "gift_manager/includes/relation_reveal_partial.html"
        if form_surface == "offcanvas"
        else "gift_manager/relation_reveal.html"
    )
    return render(
        request,
        template,
        build_relation_reveal_context(relation, request.user, form, form_surface=form_surface),
    )


# Query parameter telling the plan detail that a reveal link pointed to an already revealed plan
ALREADY_REVEALED_PARAM = "already_revealed"


class RelationRevealView(LoginRequiredMixin, HTMXResponseMixin, View):
    """Preview and reveal a Given gift plan to its recipient(s)."""

    template_name = "gift_manager/relation_reveal.html"
    partial_template_name = "gift_manager/includes/relation_reveal_partial.html"

    def get_relation(self, pk):
        return get_object_or_404(
            Relation.objects.accessible_by(self.request.user).select_related(
                "gift", "event", "person", "group"
            ),
            relation_id=pk,
        )

    def already_revealed_response(self, request, relation: Relation) -> HttpResponse:
        """Send a stale reveal link or form back to the plan, which shows it is revealed."""
        message = gettext("This gift plan was already revealed.")
        if self.is_htmx and request.method == "POST":
            response = HttpResponse("")
            response["HX-Reswap"] = "none"
            response["HX-Trigger"] = self.build_hx_trigger_header(
                ["list:update", "offcanvas:close", {"showNotification": {"message": message}}]
            )
            return response
        detail_url = reverse("gift_manager:relation_detail", kwargs={"pk": relation.relation_id})
        if self.is_htmx:
            # The side panel follows the redirect and shows the plan with this notice
            return redirect(f"{detail_url}?{ALREADY_REVEALED_PARAM}=1")
        messages.info(request, message)
        return redirect(detail_url)

    def check_can_reveal(self, request, relation: Relation) -> HttpResponse | None:
        """Return the response for a plan that cannot be revealed, or None when it can."""
        if can_reveal_plan(relation, request.user):
            return None
        if relation.revealed_at is not None and user_is_plan_owner(relation, request.user):
            return self.already_revealed_response(request, relation)
        raise PermissionDenied(gettext("This gift plan cannot be revealed."))

    def get(self, request, pk, *args, **kwargs):
        relation = self.get_relation(pk)
        if (response := self.check_can_reveal(request, relation)) is not None:
            return response

        return render_relation_reveal_form(
            request,
            relation,
            form_surface="offcanvas" if self.is_htmx else "page",
        )

    def post(self, request, pk, *args, **kwargs):
        relation = self.get_relation(pk)
        if (response := self.check_can_reveal(request, relation)) is not None:
            return response

        form = RelationRevealForm(request.POST)
        if not form.is_valid():
            response = render_relation_reveal_form(
                request,
                relation,
                form,
                form_surface="offcanvas" if self.is_htmx else "page",
            )
            if self.is_htmx:
                response.status_code = 422
                response["HX-Trigger"] = json.dumps(
                    {
                        "showNotification": {
                            "message": gettext("Please correct the errors below."),
                            "type": "error",
                        }
                    }
                )
            return response

        created_gifts = reveal_plan(
            relation,
            request.user,
            title=form.cleaned_data["title"],
            url=form.cleaned_data["url"],
            received_on=form.cleaned_data["received_on"],
            occasion_text=form.cleaned_data["occasion_text"],
            giver_note=form.cleaned_data["giver_note"],
        )

        if not created_gifts:
            message = gettext("No eligible recipient friends found to reveal to.")
            msg_type = "warning"
        else:
            message = gettext("Gift plan successfully revealed to recipient!")
            msg_type = "success"

        if self.is_htmx:
            triggers = ["list:update", "offcanvas:close"]
            triggers.append({"showNotification": {"message": message, "type": msg_type}})
            response = HttpResponse("")
            response["HX-Reswap"] = "none"
            response["HX-Trigger"] = self.build_hx_trigger_header(triggers)
            return response

        messages.add_message(
            request, messages.SUCCESS if msg_type == "success" else messages.WARNING, message
        )
        return redirect("gift_manager:relation_detail", pk=relation.relation_id)


class ReceivedGiftShareReactionView(LoginRequiredMixin, HTMXResponseMixin, View):
    """Share recipient reaction feedback back to the giver's plan."""

    def post(self, request, pk, *args, **kwargs):
        gift = get_object_or_404(
            ReceivedGift.objects.for_user(request.user),
            received_gift_id=pk,
        )

        result = share_reaction_feedback(gift, request.user)
        if result is ShareReactionResult.SHARED:
            message = gettext("Reaction feedback shared with the givers.")
            msg_type = "success"
            django_level = messages.SUCCESS
        elif result is ShareReactionResult.NOTHING_NEW:
            message = gettext("The givers already have feedback for this gift.")
            msg_type = "info"
            django_level = messages.INFO
        else:
            message = gettext("Unable to share reaction feedback.")
            msg_type = "warning"
            django_level = messages.WARNING

        if self.is_htmx:
            response = HttpResponse("")
            response["HX-Reswap"] = "none"
            response["HX-Trigger"] = json.dumps(
                {
                    "list:update": None,
                    "showNotification": {"message": message, "type": msg_type},
                }
            )
            return response

        messages.add_message(request, django_level, message)
        return redirect("gift_manager:received_gift_detail", pk=gift.received_gift_id)
