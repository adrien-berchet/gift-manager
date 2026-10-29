"""Views for wisher personal wishlist management."""

import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpResponse
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext
from django.views.generic import CreateView
from django.views.generic import UpdateView
from django.views.generic import View

from gift_manager import wishlist
from gift_manager.forms import WishForm
from gift_manager.models import Wish
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
