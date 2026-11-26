"""Contact import pages: upload a contacts file, preview the contacts, import the selected ones.

The uploaded file is never stored: the parsed contact records wait in the session (one pending
import per session, under a random id) until the user confirms or cancels.
"""

import time
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import get_language
from django.utils.translation import gettext
from django.views import View
from django.views.decorators.http import require_POST
from django.views.generic import FormView

from gift_manager.contact_import_forms import ContactImportConfirmForm
from gift_manager.contact_import_forms import ContactUploadForm
from gift_manager.contact_import_service import find_duplicates
from gift_manager.contact_import_service import import_contacts
from gift_manager.models import Person

SESSION_KEY = "contact_import"
# A pending import older than this is forgotten: contact details stay in the session only
# while the user goes through the preview.
PENDING_IMPORT_TTL_SECONDS = 60 * 60


def _people_view_url() -> str:
    return reverse("gift_manager:recipients") + "?view=people"


def _pending_import(request, import_id: str) -> dict | None:
    """Return the session's pending import when ``import_id`` names it."""
    pending = request.session.get(SESSION_KEY)
    if not isinstance(pending, dict):
        return None
    if time.time() - pending.get("created", 0) > PENDING_IMPORT_TTL_SECONDS:
        del request.session[SESSION_KEY]
        return None
    if pending.get("id") == import_id:
        return pending
    return None


def _expired(request) -> HttpResponseRedirect:
    messages.warning(
        request, gettext("This import is no longer available. Upload your contacts file again.")
    )
    return redirect("gift_manager:contact_import")


def _birthday_display(bday: list | None) -> str:
    if not bday:
        return ""
    day, month, year = bday
    return Person(birthday_day=day, birthday_month=month, birthday_year=year).birthday_display


class ContactImportUploadView(LoginRequiredMixin, FormView):
    """Upload a contacts file, parse it and continue to the preview."""

    template_name = "gift_manager/contact_import_upload.html"
    form_class = ContactUploadForm
    login_url = "/accounts/login/"

    def get_form_kwargs(self) -> dict:
        kwargs = super().get_form_kwargs()
        # Ambiguous slash dates are day first in French exports, month first otherwise
        kwargs["day_first"] = (get_language() or "").startswith("fr")
        return kwargs

    def get_context_data(self, **kwargs) -> dict:
        context = super().get_context_data(**kwargs)
        context["cancel_url"] = _people_view_url()
        return context

    def form_valid(self, form):
        import_id = uuid.uuid4().hex
        # A new upload replaces any pending one, which bounds what the session holds
        self.request.session[SESSION_KEY] = {
            "id": import_id,
            "contacts": form.result.contacts,
            "skipped": form.result.skipped,
            "created": time.time(),
        }
        return redirect("gift_manager:contact_import_preview", import_id=import_id)


class ContactImportPreviewView(LoginRequiredMixin, View):
    """Show the parsed contacts (GET) and import the selected ones (POST)."""

    template_name = "gift_manager/contact_import_preview.html"
    login_url = "/accounts/login/"

    def get(self, request, import_id):
        pending = _pending_import(request, import_id)
        if pending is None:
            return _expired(request)
        duplicates = find_duplicates(request.user, pending["contacts"])
        selected = {index for index, kind in enumerate(duplicates) if kind is None}
        form = ContactImportConfirmForm(user=request.user, contact_count=len(pending["contacts"]))
        return self._render(request, import_id, pending, form, duplicates, selected)

    def post(self, request, import_id):
        pending = _pending_import(request, import_id)
        if pending is None:
            return _expired(request)
        contacts = pending["contacts"]
        form = ContactImportConfirmForm(
            request.POST, user=request.user, contact_count=len(contacts)
        )
        if form.is_valid():
            indexes = form.cleaned_data["selected"]
            try:
                people = import_contacts(
                    request.user, contacts, indexes, group=form.cleaned_data["group"]
                )
            except PermissionDenied as error:
                form.add_error("group", str(error))
            except ValidationError:
                # Never show or log the error itself: it may quote contact details
                form.add_error(
                    None,
                    gettext("Some contacts could not be imported. Nothing was imported."),
                )
            else:
                del request.session[SESSION_KEY]
                not_imported = len(contacts) - len(people) + pending["skipped"]
                messages.success(
                    request,
                    gettext("Contacts imported: %(imported)d. Not imported: %(not_imported)d.")
                    % {"imported": len(people), "not_imported": not_imported},
                )
                return redirect(_people_view_url())
        duplicates = find_duplicates(request.user, contacts)
        selected = set()
        for value in request.POST.getlist("selected"):
            if value.isdigit():
                selected.add(int(value))
        return self._render(request, import_id, pending, form, duplicates, selected)

    def _render(self, request, import_id, pending, form, duplicates, selected) -> HttpResponse:
        rows = [
            {
                "index": index,
                "given": contact["given"],
                "family": contact["family"],
                "email": contact["emails"][0] if contact["emails"] else "",
                "birthday": _birthday_display(contact["bday"]),
                "invalid_birthday": contact["invalid_birthday"],
                "duplicate": duplicate,
                "checked": index in selected,
            }
            for index, (contact, duplicate) in enumerate(
                zip(pending["contacts"], duplicates, strict=True)
            )
        ]
        context = {
            "import_id": import_id,
            "form": form,
            "rows": rows,
            "skipped": pending["skipped"],
            "selected_count": sum(1 for row in rows if row["checked"]),
            "cancel_url": reverse("gift_manager:contact_import_cancel", args=[import_id]),
        }
        return render(request, self.template_name, context)


@login_required(login_url="/accounts/login/")
@require_POST
def contact_import_cancel(request, import_id):
    """Forget a pending import and go back to the people view."""
    if _pending_import(request, import_id) is not None:
        del request.session[SESSION_KEY]
    return redirect(_people_view_url())
