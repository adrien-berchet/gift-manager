"""Forms of the contact import: the file upload and the preview confirmation."""

import logging

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy

from gift_manager.contact_import import MAX_FILE_BYTES
from gift_manager.contact_import import TOO_LARGE
from gift_manager.contact_import import UNREADABLE
from gift_manager.contact_import import ContactImportError
from gift_manager.contact_import import ParseResult
from gift_manager.contact_import import parse_contacts
from gift_manager.group_hierarchy_service import GroupHierarchyService
from gift_manager.models import PersonGroup

logger = logging.getLogger(__name__)


class ContactUploadForm(forms.Form):
    """Upload one contacts file; a valid form holds the parsed contacts in ``result``."""

    file = forms.FileField(
        label=gettext_lazy("Contacts file"),
        help_text=gettext_lazy("A vCard (.vcf) or CSV (.csv) file, up to 2 MB."),
        widget=forms.ClearableFileInput(
            attrs={"accept": ".vcf,.vcard,.csv,text/vcard,text/x-vcard,text/csv"}
        ),
    )

    def __init__(self, *args, day_first: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.day_first = day_first
        self.result: ParseResult | None = None

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if upload.size > MAX_FILE_BYTES:
            raise ValidationError(ContactImportError(TOO_LARGE).message, code=TOO_LARGE)
        data = upload.read(MAX_FILE_BYTES + 1)
        try:
            self.result = parse_contacts(data, upload.name or "", day_first=self.day_first)
        except ContactImportError as error:
            raise ValidationError(error.message, code=error.code) from None
        except Exception as error:
            # Never let the file's content reach logs or error reports (frame locals,
            # exception messages): keep only the exception type.
            logger.error("Contact import: the file could not be parsed (%s)", type(error).__name__)  # noqa: TRY400
            raise ValidationError(ContactImportError(UNREADABLE).message, code=UNREADABLE) from None
        return upload


class _IndexesField(forms.Field):
    """A list of contact indexes, each in ``range(count)``; posted as repeated values."""

    widget = forms.SelectMultiple
    default_error_messages = {
        "required": gettext_lazy("Select at least one contact to import."),
        "invalid": gettext_lazy("This selection is not valid. Reload the page and try again."),
    }

    def __init__(self, *, count: int = 0, **kwargs):
        super().__init__(**kwargs)
        self.count = count

    def to_python(self, value) -> list[int]:
        if not value:
            return []
        try:
            indexes = {int(item) for item in value}
        except (TypeError, ValueError):
            raise ValidationError(self.error_messages["invalid"], code="invalid") from None
        if any(not 0 <= index < self.count for index in indexes):
            raise ValidationError(self.error_messages["invalid"], code="invalid")
        return sorted(indexes)


def editable_groups(user):
    """Return the groups ``user`` may add people to (the person form's rule)."""
    accessible = PersonGroup.objects.accessible_by(user)
    return accessible.filter(pk__in=GroupHierarchyService.editable_pks(user, accessible))


class ContactImportConfirmForm(forms.Form):
    """The contacts selected in the preview, and an optional group to add them to."""

    selected = _IndexesField(label=gettext_lazy("Contacts"))
    group = forms.ModelChoiceField(
        queryset=PersonGroup.objects.none(),
        required=False,
        label=gettext_lazy("Add the imported people to a group (optional)"),
        empty_label=gettext_lazy("No group"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, user, contact_count: int, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["selected"].count = contact_count
        self.fields["group"].queryset = editable_groups(user).order_by("name")
