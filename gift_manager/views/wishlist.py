"""Views for wisher personal wishlist management."""

import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponse
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.template.loader import render_to_string
from django.urls import reverse
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext
from django.views.generic import CreateView
from django.views.generic import UpdateView
from django.views.generic import View

from gift_manager import wishlist
from gift_manager.forms import WishForm
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import Relation
from gift_manager.models import Wish
from gift_manager.services import PermissionService
from gift_manager.statuses import is_abandoned_status
from gift_manager.views.base import HTMXResponseMixin


class WishListView(LoginRequiredMixin, View):
    """List wisher's personal wishes with strict privacy boundary."""

    template_name = "gift_manager/wishlist_list.html"
    partial_template_name = "gift_manager/includes/wishlist_body_partial.html"

    def get(self, request, *args, **kwargs):
        # Strict privacy invariant: defer columns related to claim/plan state
        # so template evaluation cannot access or trigger queries on them.
        wishes = Wish.objects.for_wisher(request.user).defer(
            "claimed_by", "claimed_at", "is_fulfilled"
        )
        active_wishes = list(wishes.filter(is_archived=False))
        archived_wishes = list(wishes.filter(is_archived=True))

        context = {
            "active_wishes": active_wishes,
            "archived_wishes": archived_wishes,
        }

        if request.headers.get("HX-Request") == "true":
            return render(request, self.partial_template_name, context)
        return render(request, self.template_name, context)


class WishCreateView(LoginRequiredMixin, HTMXResponseMixin, CreateView):
    """Add a new wish to wisher's personal wishlist."""

    model = Wish
    form_class = WishForm
    template_name = "gift_manager/wish_form.html"
    htmx_template_name = "gift_manager/includes/wish_form_partial.html"
    success_url = reverse_lazy("gift_manager:wishlist_list")
    close_offcanvas = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["action"] = gettext("Add")
        context["translated_type"] = gettext("Wish")
        context["form_surface"] = "offcanvas" if self.is_htmx else "page"
        context["cancel_url"] = self.success_url
        return context

    def form_valid(self, form):
        form.instance.wisher = self.request.user
        form.instance.wisher_updated_at = timezone.now()
        self.object = form.save()

        success_message = self.get_success_message()
        messages.success(self.request, success_message)

        if self.is_htmx:
            triggers = ["list:update"]
            if getattr(self, "close_offcanvas", False):
                triggers.append("offcanvas:close")
            if success_message:
                triggers.append(
                    {"showNotification": {"message": success_message, "type": "success"}}
                )
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

    def get_success_message(self):
        return gettext("Wish added successfully.")


class WishUpdateView(LoginRequiredMixin, HTMXResponseMixin, UpdateView):
    """Edit an existing wish on wisher's personal wishlist."""

    model = Wish
    form_class = WishForm
    template_name = "gift_manager/wish_form.html"
    htmx_template_name = "gift_manager/includes/wish_form_partial.html"
    success_url = reverse_lazy("gift_manager:wishlist_list")
    close_offcanvas = True

    def get_queryset(self):
        return Wish.objects.for_wisher(self.request.user)

    def get_object(self, queryset=None):
        if queryset is None:
            queryset = self.get_queryset()
        wish_id = self.kwargs.get("wish_id")
        return get_object_or_404(queryset, wish_id=wish_id)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["action"] = gettext("Edit")
        context["translated_type"] = gettext("Wish")
        context["form_surface"] = "offcanvas" if self.is_htmx else "page"
        context["cancel_url"] = self.success_url
        return context

    def form_valid(self, form):
        with transaction.atomic():
            # Prevent concurrent friend claim from being overwritten
            Wish.objects.select_for_update().get(pk=self.object.pk)
            self.object = form.save(commit=False)
            self.object.wisher_updated_at = timezone.now()
            fields_to_update = set(form.changed_data) | {"wisher_updated_at"}
            self.object.save(update_fields=fields_to_update)

        success_message = self.get_success_message()
        messages.success(self.request, success_message)

        if self.is_htmx:
            triggers = ["list:update"]
            if getattr(self, "close_offcanvas", False):
                triggers.append("offcanvas:close")
            if success_message:
                triggers.append(
                    {"showNotification": {"message": success_message, "type": "success"}}
                )
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

    def get_success_message(self):
        return gettext("Wish updated successfully.")


class WishArchiveView(LoginRequiredMixin, View):
    """Toggle the archived status of a personal wish."""

    def post(self, request, wish_id, *args, **kwargs):
        with transaction.atomic():
            wish = get_object_or_404(
                Wish.objects.select_for_update().for_wisher(request.user),
                wish_id=wish_id,
            )
            wish.is_archived = not wish.is_archived
            wish.save(update_fields=["is_archived"])

        msg = gettext("Wish archived.") if wish.is_archived else gettext("Wish unarchived.")

        if request.headers.get("HX-Request") == "true":
            response = HttpResponse("")
            response["HX-Reswap"] = "none"
            response["HX-Trigger"] = json.dumps(
                {
                    "list:update": {},
                    "showNotification": {"message": str(msg), "type": "success"},
                }
            )
            return response

        messages.success(request, msg)
        return redirect("gift_manager:wishlist_list")


class WishDeleteView(LoginRequiredMixin, View):
    """Delete a personal wish (or archive it if claimed/planned)."""

    def post(self, request, wish_id, *args, **kwargs):
        wish = get_object_or_404(
            Wish.objects.for_wisher(request.user),
            wish_id=wish_id,
        )
        wishlist.delete_wish(wish, request.user)
        msg = gettext("Wish removed.")

        if request.headers.get("HX-Request") == "true":
            response = HttpResponse("")
            response["HX-Reswap"] = "none"
            response["HX-Trigger"] = json.dumps(
                {
                    "list:update": {},
                    "showNotification": {"message": str(msg), "type": "success"},
                }
            )
            return response

        messages.success(request, msg)
        return redirect("gift_manager:wishlist_list")


def annotate_wish_for_giver(wish, viewer, person, viewer_friend_ids=None):
    """Attach giver-specific view properties to a wish instance."""
    if viewer_friend_ids is None:
        viewer_friend_ids = set(viewer.profile.friends.values_list("user_id", flat=True))
    wish.claimer_label = wishlist.format_claimer_label(wish, viewer, viewer_friend_ids)
    wish.is_claimed_by_viewer = wish.claimed_by_id == viewer.id
    wish.modified_after_claim = wish.is_updated_after_claim()

    active_plans = Relation.objects.filter(
        wish=wish,
        person=person,
        relationpermission__user=viewer,
        relationpermission__permission_type=PermissionLevel.OWNER,
    ).select_related("status")
    active_plan = next((p for p in active_plans if not is_abandoned_status(p.status)), None)
    wish.planned_relation = active_plan
    wish.is_planned_by_viewer = active_plan is not None
    return wish


class WishClaimToggleView(LoginRequiredMixin, View):
    """Toggle reservation/claim on a friend's wish."""

    @staticmethod
    def _execute_toggle(wish, user) -> tuple[Wish | None, str | None, str | None]:
        try:
            if wish.claimed_by_id == user.id:
                return (
                    wishlist.release_wish_claim(wish, user),
                    gettext("Wish claim released."),
                    None,
                )
            return wishlist.claim_wish(wish, user), gettext("Wish claimed."), None
        except ValidationError as exc:
            msg = exc.message if hasattr(exc, "message") else str(exc)
            return None, None, msg

    @staticmethod
    def _render_deleted_response(
        request, person, is_htmx, error_message, success_message
    ) -> HttpResponse:
        if is_htmx:
            response = HttpResponse("")
            msg = error_message or success_message
            msg_type = "error" if error_message else "success"
            response["HX-Trigger"] = json.dumps(
                {"showNotification": {"message": str(msg), "type": msg_type}}
            )
            return response
        if error_message:
            messages.error(request, error_message)
        elif success_message:
            messages.success(request, success_message)
        return redirect("gift_manager:person_detail", pk=person.person_id)

    def post(self, request, person_id, wish_id, *args, **kwargs):
        person = get_object_or_404(Person, person_id=person_id)
        if (
            PermissionService.get_effective_permission(person, request.user)
            < PermissionLevel.VIEWER
        ):
            raise PermissionDenied(gettext("You do not have permission to view this person."))

        if not person.account_id or not PermissionService.users_are_friends(
            request.user, person.account
        ):
            raise PermissionDenied(
                gettext("You can only view and claim wishes of confirmed friends.")
            )

        wish = get_object_or_404(
            Wish.objects.visible_to_friend(request.user, person.account),
            wish_id=wish_id,
        )

        is_htmx = request.headers.get("HX-Request") == "true"
        is_editor = (
            PermissionService.get_effective_permission(person, request.user)
            >= PermissionLevel.EDITOR
        )

        toggled_wish, success_message, error_message = self._execute_toggle(wish, request.user)
        if toggled_wish is not None:
            wish = toggled_wish
        else:
            wish = get_object_or_404(
                Wish.objects.visible_to_friend(request.user, person.account),
                wish_id=wish_id,
            )

        if wish.is_deleted_by_wisher and wish.claimed_by_id is None:
            return self._render_deleted_response(
                request, person, is_htmx, error_message, success_message
            )

        annotate_wish_for_giver(wish, request.user, person)

        if is_htmx:
            content = render_to_string(
                "gift_manager/includes/person_wish_item_partial.html",
                {"wish": wish, "person": person, "is_editor": is_editor},
                request=request,
            )
            response = HttpResponse(content)
            trigger_msg = error_message or success_message
            trigger_type = "error" if error_message else "success"
            response["HX-Trigger"] = json.dumps(
                {"showNotification": {"message": str(trigger_msg), "type": trigger_type}}
            )
            return response

        if error_message:
            messages.error(request, error_message)
        elif success_message:
            messages.success(request, success_message)
        return redirect("gift_manager:person_detail", pk=person.person_id)


class WishPlanView(LoginRequiredMixin, View):
    """Plan a gift fulfilling a friend's wish."""

    def post(self, request, person_id, wish_id, *args, **kwargs):
        person = get_object_or_404(Person, person_id=person_id)
        if (
            PermissionService.get_effective_permission(person, request.user)
            < PermissionLevel.EDITOR
        ):
            raise PermissionDenied(
                gettext("You need edit rights on this person to plan a gift for them.")
            )

        if not person.account_id or not PermissionService.users_are_friends(
            request.user, person.account
        ):
            raise PermissionDenied(gettext("You can only plan gifts for confirmed friends."))

        wish = get_object_or_404(
            Wish.objects.visible_to_friend(request.user, person.account),
            wish_id=wish_id,
        )

        already_existed = wishlist.get_active_plan_for_wish(wish, request.user, person) is not None

        try:
            wishlist.plan_wish(wish, request.user, person)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
            detail_url = reverse("gift_manager:person_detail", kwargs={"pk": person.person_id})
            if request.headers.get("HX-Request") == "true":
                response = HttpResponse("")
                response["HX-Redirect"] = detail_url
                return response
            return redirect(detail_url)

        if already_existed:
            messages.info(request, gettext("Gift plan already exists for this wish."))
        else:
            messages.success(request, gettext("Gift plan created from wish."))

        detail_url = reverse("gift_manager:person_detail", kwargs={"pk": person.person_id})
        if request.headers.get("HX-Request") == "true":
            response = HttpResponse("")
            response["HX-Redirect"] = detail_url
            return response
        return redirect(detail_url)
