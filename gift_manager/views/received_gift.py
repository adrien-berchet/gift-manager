"""Views for received gifts management (personal log)."""

import contextlib
import json
from collections import defaultdict
from datetime import date

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView
from django.views.generic import UpdateView
from django.views.generic import View

from gift_manager.forms import ReceivedGiftForm
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import ReceivedGift
from gift_manager.models import Relation
from gift_manager.models import Wish
from gift_manager.received_gifts import can_reveal_plan
from gift_manager.received_gifts import get_reveal_targets
from gift_manager.received_gifts import reveal_plan
from gift_manager.received_gifts import share_reaction_feedback
from gift_manager.services import PermissionService
from gift_manager.statuses import is_given_status
from gift_manager.views.base import HTMXResponseMixin
from gift_manager.wishlist import own_received_gifts

User = get_user_model()


def _linkable_giver_ids(user: User, gifts: list[ReceivedGift]) -> tuple[set[int], set[int]]:
    """Return the giver person and group pks the user can still open.

    Givers are always displayed by name, but only linked to their detail page
    while the user has access to them (sharing may have been revoked since).
    """
    person_pks = {person.pk for gift in gifts for person in gift.giver_persons.all()}
    group_pks = {group.pk for gift in gifts for group in gift.giver_groups.all()}
    linkable_person_ids = set(
        Person.objects.accessible_by(user).filter(pk__in=person_pks).values_list("pk", flat=True)
    )
    linkable_group_ids = set(
        PersonGroup.objects.accessible_by(user)
        .filter(pk__in=group_pks)
        .values_list("pk", flat=True)
    )
    return linkable_person_ids, linkable_group_ids


class ReceivedGiftListView(LoginRequiredMixin, View):
    """List received gifts for the authenticated user, grouped by year."""

    template_name = "gift_manager/received_gift_list.html"
    partial_template_name = "gift_manager/includes/received_gift_list_partial.html"

    def get(self, request, *args, **kwargs):
        user = request.user
        queryset = (
            ReceivedGift.objects.for_user(user)
            .prefetch_related("giver_persons", "giver_groups")
            .select_related("event", "wish")
        )

        filter_year = request.GET.get("year", "").strip()
        filter_giver = request.GET.get("giver", "").strip()
        filter_occasion = request.GET.get("occasion", "").strip()
        filter_thank_you = request.GET.get("thank_you", "").strip()

        if filter_year:
            try:
                queryset = queryset.filter(received_on__year=int(filter_year))
            except ValueError:
                filter_year = ""

        if filter_giver:
            # Match person id or group id
            queryset = queryset.filter(giver_persons__person_id=filter_giver) | queryset.filter(
                giver_groups__group_id=filter_giver
            )
            queryset = queryset.distinct()

        if filter_occasion:
            queryset = queryset.filter(event__event_id=filter_occasion) | queryset.filter(
                occasion_text__icontains=filter_occasion
            )
            queryset = queryset.distinct()

        if filter_thank_you in {"pending", "0", "false"}:
            queryset = queryset.filter(thank_you_sent=False)
        elif filter_thank_you in {"sent", "1", "true"}:
            queryset = queryset.filter(thank_you_sent=True)

        all_user_gifts = ReceivedGift.objects.for_user(user)
        total_count = all_user_gifts.count()
        pending_thank_you_count = all_user_gifts.filter(thank_you_sent=False).count()

        # Available years for filter dropdown
        available_years = sorted(
            {d.year for d in all_user_gifts.values_list("received_on", flat=True) if d},
            reverse=True,
        )

        # Available givers
        giver_person_pks = all_user_gifts.values_list("giver_persons", flat=True).distinct()
        available_givers = (
            Person.objects.accessible_by(user)
            .filter(pk__in=giver_person_pks)
            .order_by("family_name", "first_name")
        )

        # Group gifts by year (newest first)
        by_year = defaultdict(list)
        for item in queryset:
            year = item.received_on.year if item.received_on else None
            by_year[year].append(item)

        grouped_gifts = [
            (year, by_year[year])
            for year in sorted(by_year.keys(), key=lambda y: (y is None, -(y or 0)))
        ]
        linkable_person_ids, linkable_group_ids = _linkable_giver_ids(
            user, [gift for gifts in by_year.values() for gift in gifts]
        )

        context = {
            "grouped_gifts": grouped_gifts,
            "total_count": total_count,
            "filtered_count": queryset.count(),
            "pending_thank_you_count": pending_thank_you_count,
            "available_years": available_years,
            "available_givers": available_givers,
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
            .prefetch_related("giver_persons", "giver_groups")
            .select_related("event", "wish", "source_relation"),
            received_gift_id=pk,
        )

        can_share_reaction = False
        if gift.source_relation is not None and is_given_status(gift.source_relation.status):
            owner_ids = set(
                gift.source_relation.relationpermission_set.filter(
                    permission_type=PermissionLevel.OWNER
                ).values_list("user_id", flat=True)
            )
            # Must be friends with at least one owner
            user_friend_ids = set(request.user.profile.friends.values_list("user_id", flat=True))
            if owner_ids & user_friend_ids:
                can_share_reaction = True

        linkable_person_ids, linkable_group_ids = _linkable_giver_ids(request.user, [gift])
        context = {
            "gift": gift,
            "can_share_reaction": can_share_reaction,
            "linkable_person_ids": linkable_person_ids,
            "linkable_group_ids": linkable_group_ids,
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


class ReceivedGiftCreateView(LoginRequiredMixin, HTMXResponseMixin, CreateView):
    """Record a new received gift."""

    model = ReceivedGift
    form_class = ReceivedGiftForm
    template_name = "gift_manager/received_gift_form.html"
    htmx_template_name = "gift_manager/includes/received_gift_form_partial.html"
    success_url = reverse_lazy("gift_manager:received_gift_list")
    close_offcanvas = True

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        wish_id = self.request.GET.get("wish")
        if wish_id:
            try:
                wish = Wish.objects.for_wisher(self.request.user).get(wish_id=wish_id)
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["action"] = gettext("Record")
        context["translated_type"] = gettext("Received Gift")
        context["form_surface"] = "offcanvas" if self.is_htmx else "page"
        context["cancel_url"] = self.success_url
        return context

    def form_valid(self, form):
        form.instance.recipient_user = self.request.user
        self.object = form.save()

        success_message = gettext("Received gift recorded successfully.")
        messages.success(self.request, success_message)

        if self.is_htmx:
            triggers = ["list:update"]
            if getattr(self, "close_offcanvas", False):
                triggers.append("offcanvas:close")
            triggers.append({"showNotification": {"message": success_message, "type": "success"}})
            response = HttpResponse("")
            response["HX-Reswap"] = "none"
            response["HX-Trigger"] = self.build_hx_trigger_header(triggers)
            return response

        return HttpResponseRedirect(self.get_success_url())

    def form_invalid(self, form):
        response = super().form_invalid(form)
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


class ReceivedGiftUpdateView(LoginRequiredMixin, HTMXResponseMixin, UpdateView):
    """Edit an existing received gift."""

    model = ReceivedGift
    form_class = ReceivedGiftForm
    template_name = "gift_manager/received_gift_form.html"
    htmx_template_name = "gift_manager/includes/received_gift_form_partial.html"
    success_url = reverse_lazy("gift_manager:received_gift_list")
    close_offcanvas = True

    def get_queryset(self):
        return ReceivedGift.objects.for_user(self.request.user)

    def get_object(self, queryset=None):
        if queryset is None:
            queryset = self.get_queryset()
        return get_object_or_404(queryset, received_gift_id=self.kwargs.get("pk"))

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["action"] = gettext("Edit")
        context["translated_type"] = gettext("Received Gift")
        context["form_surface"] = "offcanvas" if self.is_htmx else "page"
        context["cancel_url"] = self.success_url
        return context

    def form_valid(self, form):
        self.object = form.save()
        success_message = gettext("Received gift updated successfully.")
        messages.success(self.request, success_message)

        if self.is_htmx:
            triggers = ["list:update"]
            if getattr(self, "close_offcanvas", False):
                triggers.append("offcanvas:close")
            triggers.append({"showNotification": {"message": success_message, "type": "success"}})
            response = HttpResponse("")
            response["HX-Reswap"] = "none"
            response["HX-Trigger"] = self.build_hx_trigger_header(triggers)
            return response

        return HttpResponseRedirect(self.get_success_url())

    def form_invalid(self, form):
        response = super().form_invalid(form)
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


class ReceivedGiftDeleteView(LoginRequiredMixin, HTMXResponseMixin, View):
    """Delete a received gift."""

    template_name = "gift_manager/received_gift_confirm_delete.html"

    def get_object(self):
        return get_object_or_404(
            ReceivedGift.objects.for_user(self.request.user),
            received_gift_id=self.kwargs.get("pk"),
        )

    def get(self, request, *args, **kwargs):
        gift = self.get_object()
        return render(request, self.template_name, {"gift": gift})

    def post(self, request, *args, **kwargs):
        gift = self.get_object()
        gift.delete()

        success_message = gettext("Received gift deleted successfully.")
        messages.success(request, success_message)

        if request.headers.get("HX-Request") == "true":
            triggers = ["list:update", "modal:close"]
            triggers.append({"showNotification": {"message": success_message, "type": "success"}})
            response = HttpResponse("")
            response["HX-Reswap"] = "none"
            response["HX-Trigger"] = self.build_hx_trigger_header(triggers)
            return response

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
            context = {
                "wish": wish,
                "received_gifts": own_received_gifts(request.user, wish),
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

    def get(self, request, pk, *args, **kwargs):
        relation = self.get_relation(pk)
        if not can_reveal_plan(relation, request.user):
            return HttpResponse(
                gettext("This gift plan cannot be revealed."),
                status=403,
            )

        targets = get_reveal_targets(relation, request.user)
        owner_ids = [
            u_id
            for u_id, lvl in PermissionService.get_permission_map(relation).items()
            if lvl == PermissionLevel.OWNER
        ]
        co_owners = list(User.objects.filter(pk__in=owner_ids, is_active=True))

        initial_title = relation.gift.name if relation.gift else ""
        initial_url = relation.url or (relation.gift.url if relation.gift else "")
        if relation.status_changed_at:
            initial_date = timezone.localdate(relation.status_changed_at)
        elif relation.due_date:
            initial_date = relation.due_date
        else:
            initial_date = timezone.localdate()

        initial_occasion = relation.event.name[:100] if relation.event else ""

        context = {
            "relation": relation,
            "targets": targets,
            "co_owners": co_owners,
            "initial_title": initial_title,
            "initial_url": initial_url,
            "initial_date": initial_date.isoformat(),
            "initial_occasion": initial_occasion,
        }
        template = (
            self.partial_template_name
            if request.headers.get("HX-Request") == "true"
            else self.template_name
        )
        return render(request, template, context)

    def post(self, request, pk, *args, **kwargs):
        relation = self.get_relation(pk)
        if not can_reveal_plan(relation, request.user):
            return HttpResponse(
                gettext("This gift plan cannot be revealed."),
                status=403,
            )

        title = request.POST.get("title", "").strip()
        url = request.POST.get("url", "").strip()
        date_str = request.POST.get("received_on", "").strip()
        occasion_text = request.POST.get("occasion_text", "").strip()
        giver_note = request.POST.get("giver_note", "").strip()

        received_on = None
        if date_str:
            with contextlib.suppress(ValueError):
                received_on = date.fromisoformat(date_str)

        created_gifts = reveal_plan(
            relation,
            request.user,
            title=title,
            url=url,
            received_on=received_on,
            occasion_text=occasion_text,
            giver_note=giver_note,
        )

        if not created_gifts:
            message = gettext("No eligible recipient friends found to reveal to.")
            msg_type = "warning"
        else:
            message = gettext("Gift plan successfully revealed to recipient!")
            msg_type = "success"

        messages.add_message(
            request, messages.SUCCESS if msg_type == "success" else messages.WARNING, message
        )

        if request.headers.get("HX-Request") == "true":
            triggers = ["list:update", "modal:close", "card:update"]
            triggers.append({"showNotification": {"message": message, "type": msg_type}})
            response = HttpResponse("")
            response["HX-Reswap"] = "none"
            response["HX-Trigger"] = self.build_hx_trigger_header(triggers)
            return response

        return redirect("gift_manager:relation_detail", pk=relation.relation_id)


class ReceivedGiftShareReactionView(LoginRequiredMixin, HTMXResponseMixin, View):
    """Share recipient reaction feedback back to the giver's plan."""

    def post(self, request, pk, *args, **kwargs):
        gift = get_object_or_404(
            ReceivedGift.objects.for_user(request.user),
            received_gift_id=pk,
        )

        success = share_reaction_feedback(gift, request.user)
        if success:
            message = gettext("Reaction feedback shared with the givers.")
            msg_type = "success"
        else:
            message = gettext("Unable to share reaction feedback.")
            msg_type = "warning"

        if request.headers.get("HX-Request") == "true":
            response = HttpResponse("")
            response["HX-Reswap"] = "none"
            response["HX-Trigger"] = json.dumps(
                {
                    "list:update": None,
                    "modal:close": None,
                    "showNotification": {"message": message, "type": msg_type},
                }
            )
            return response

        return redirect("gift_manager:received_gift_detail", pk=gift.received_gift_id)
