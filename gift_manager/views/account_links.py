"""Views for linking person records to user accounts."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views import View

from gift_manager import account_links
from gift_manager.account_links import LinkRefused
from gift_manager.account_links import link_choices
from gift_manager.account_links import revealed_surprise_count
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.services import PermissionService


class PersonLinkAccountView(LoginRequiredMixin, View):
    """Form and action for linking a person record to an account or unlinking it."""

    def _get_person(self, request, pk) -> Person:
        person = get_object_or_404(Person.objects.accessible_by(request.user), person_id=pk)
        if (
            PermissionService.get_effective_permission(person, request.user)
            < PermissionLevel.EDITOR
        ):
            raise PermissionDenied(_("You do not have permission to edit this person."))
        return person

    def get(self, request, pk):
        person = self._get_person(request, pk)
        choices = link_choices(person, request.user)
        selected_account_id = str(person.account_id) if person.account_id else ""
        context = {
            "person": person,
            "choices": choices,
            "selected_account_id": selected_account_id,
            "confirm_required": False,
            "confirm_account_id": "",
            "confirmation_message": "",
            "error_message": "",
        }
        is_htmx = request.headers.get("HX-Request") == "true"
        template_name = (
            "gift_manager/includes/person_link_form_partial.html"
            if is_htmx
            else "gift_manager/person_link_account.html"
        )
        return render(request, template_name, context)

    def post(self, request, pk):
        person = self._get_person(request, pk)
        is_htmx = request.headers.get("HX-Request") == "true"
        template_name = (
            "gift_manager/includes/person_link_form_partial.html"
            if is_htmx
            else "gift_manager/person_link_account.html"
        )

        if "account" not in request.POST:
            choices = link_choices(person, request.user)
            context = {
                "person": person,
                "choices": choices,
                "selected_account_id": str(person.account_id) if person.account_id else "",
                "error_message": _("Please select who this person is."),
                "confirm_required": False,
                "confirm_account_id": "",
                "confirmation_message": "",
            }
            return render(request, template_name, context, status=400)

        account_val = request.POST["account"]
        target_user = None
        if account_val != "":
            try:
                target_user = User.objects.get(pk=int(account_val))
            except (ValueError, User.DoesNotExist):
                choices = link_choices(person, request.user)
                context = {
                    "person": person,
                    "choices": choices,
                    "selected_account_id": account_val,
                    "error_message": _("Invalid account selection."),
                    "confirm_required": False,
                    "confirm_account_id": "",
                    "confirmation_message": "",
                }
                return render(request, template_name, context, status=400)

        try:
            with transaction.atomic():
                PermissionService.lock_object(person)
                person.refresh_from_db(fields=["account"])
                target_id = target_user.id if target_user else None

                if person.account_id and target_id != person.account_id:
                    count = revealed_surprise_count(person)
                    confirmed = request.POST.get("confirm") == "1" and request.POST.get(
                        "confirm_account", str(person.account_id)
                    ) == str(person.account_id)
                    if count > 0 and not confirmed:
                        account_username = person.account.username
                        warning_msg = ngettext(
                            "%(count)d surprise plan shared with %(username)s "
                            "would become visible to them.",
                            "%(count)d surprise plans shared with %(username)s "
                            "would become visible to them.",
                            count,
                        ) % {"count": count, "username": account_username}
                        choices = link_choices(person, request.user)
                        context = {
                            "person": person,
                            "choices": choices,
                            "selected_account_id": account_val,
                            "confirm_required": True,
                            "confirm_account_id": str(person.account_id),
                            "confirmation_message": warning_msg,
                            "error_message": "",
                        }
                        return render(request, template_name, context, status=200)

                if target_user is None:
                    account_links.unlink(person, request.user)
                    messages.success(request, _("Link removed."))
                else:
                    account_links.link(person, target_user, request.user)
                    messages.success(
                        request,
                        _("Linked to %(username)s.") % {"username": target_user.username},
                    )

        except LinkRefused as exc:
            choices = link_choices(person, request.user)
            context = {
                "person": person,
                "choices": choices,
                "selected_account_id": account_val,
                "error_message": exc.message if hasattr(exc, "message") else str(exc),
                "confirm_required": False,
                "confirm_account_id": "",
                "confirmation_message": "",
            }
            return render(request, template_name, context, status=400)

        success_url = reverse("gift_manager:person_detail", kwargs={"pk": person.person_id})
        if is_htmx:
            response = HttpResponse(status=204)
            response["HX-Redirect"] = success_url
            return response
        return redirect(success_url)
