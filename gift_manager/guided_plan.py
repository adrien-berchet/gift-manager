"""Step forms and helpers of the guided gift plan creation flow.

The guided flow collects a gift plan in three steps (recipient, gift, occasion). Each step has a
small form that validates only its own fields. The final save re-validates every step, creates the
inline gift and event if requested, and hands the assembled data to ``RelationForm`` so the plan
matches one created with the full form.
"""

from django import forms
from django.utils.translation import gettext_lazy

from gift_manager.forms import BaseFormMixin
from gift_manager.forms import EventForm
from gift_manager.forms import GiftForm
from gift_manager.forms import RelationForm
from gift_manager.forms import build_recipient_choices
from gift_manager.forms import resolve_recipient_choice
from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import PermissionLevel
from gift_manager.models import RelationStatus
from gift_manager.services import PermissionService

GUIDED_STEPS = ("recipient", "gift", "occasion")

DEFAULT_STATUS_NAME = "Idea"


class _GuidedStepForm(BaseFormMixin, forms.Form):
    """Base class of the step forms: a plain form that knows the creating user."""

    def __init__(self, data=None, *, user, **kwargs):
        self.user = user
        super().__init__(data, **kwargs)


class GuidedRecipientForm(_GuidedStepForm):
    """Step 1: the person or group the gift plan is for."""

    recipient = forms.ChoiceField(
        label=gettext_lazy("Recipient"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, data=None, *, user, **kwargs):
        super().__init__(data, user=user, **kwargs)
        self.fields["recipient"].choices = build_recipient_choices(user)

    def clean_recipient(self) -> str:
        value = self.cleaned_data["recipient"]
        resolve_recipient_choice(value, self.user)
        return value


class GuidedGiftForm(_GuidedStepForm):
    """Step 2: an existing gift, or the name of a new one."""

    gift = forms.ModelChoiceField(
        label=gettext_lazy("Gift"),
        queryset=Gift.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    new_gift_name = forms.CharField(
        label=gettext_lazy("Or create a new gift"),
        required=False,
        widget=forms.TextInput(attrs={"placeholder": gettext_lazy("Gift name")}),
    )

    def __init__(self, data=None, *, user, **kwargs):
        super().__init__(data, user=user, **kwargs)
        self.fields["gift"].queryset = Gift.objects.accessible_by(user).order_by("name")

    def clean(self):
        cleaned_data = super().clean()
        gift = cleaned_data.get("gift")
        name = cleaned_data.get("new_gift_name")
        if "gift" in self.errors:
            return cleaned_data
        if gift and name:
            self.add_error(
                "new_gift_name",
                gettext_lazy("Choose an existing gift or enter a new one, not both."),
            )
        elif not gift and not name:
            self.add_error("gift", gettext_lazy("Choose a gift or enter a new gift name."))
        return cleaned_data


class GuidedOccasionForm(_GuidedStepForm):
    """Step 3: the event (existing or new), the due date and optional notes."""

    event = forms.ModelChoiceField(
        label=gettext_lazy("Event"),
        queryset=Event.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    new_event_name = forms.CharField(
        label=gettext_lazy("Or create a new event"),
        required=False,
        widget=forms.TextInput(attrs={"placeholder": gettext_lazy("Event name")}),
    )
    new_event_date = forms.DateField(
        label=gettext_lazy("New event date"),
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    due_date = forms.DateField(
        label=gettext_lazy("Due date"),
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    comment = forms.CharField(
        label=gettext_lazy("Notes"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, data=None, *, user, **kwargs):
        super().__init__(data, user=user, **kwargs)
        self.fields["event"].queryset = Event.objects.accessible_by(user).order_by("name")

    def clean(self):
        cleaned_data = super().clean()
        if self.errors:
            return cleaned_data
        event = cleaned_data.get("event")
        name = cleaned_data.get("new_event_name")
        new_date = cleaned_data.get("new_event_date")
        if event and (name or new_date):
            self.add_error(
                "new_event_name",
                gettext_lazy("Choose an existing event or enter a new one, not both."),
            )
        elif name and not new_date:
            self.add_error("new_event_date", gettext_lazy("Choose a date."))
        elif new_date and not name:
            self.add_error("new_event_name", gettext_lazy("Enter a name for the new event."))
        elif not cleaned_data.get("due_date"):
            cleaned_data["due_date"] = event.next_occurrence() if event else new_date
        return cleaned_data


STEP_FORMS = {
    "recipient": GuidedRecipientForm,
    "gift": GuidedGiftForm,
    "occasion": GuidedOccasionForm,
}


def _save_owned(form: forms.ModelForm, user, object_attr: str) -> Gift | Event:
    """Save a validated model form, owned by ``user`` (mirrors ``BaseCreateView.form_valid``)."""
    if not form.is_valid():
        raise forms.ValidationError(
            [message for errors in form.errors.values() for message in errors]
        )
    instance = form.save(commit=False)
    if hasattr(instance, "user_link"):
        instance.user_link = user
    instance.save()
    form.save_m2m()
    PermissionService.create_or_update_permission(
        user, instance, permission_level=PermissionLevel.OWNER, object_attr=object_attr
    )
    return instance


def create_inline_objects(user, gift_form, occasion_form) -> tuple[Gift, Event | None]:
    """Return the chosen or newly created gift and event of validated step forms.

    New objects are validated with the regular forms and owned by ``user``. Call it inside the
    caller's transaction so that nothing is left behind when the plan itself is rejected.
    """
    gift = gift_form.cleaned_data["gift"]
    if gift is None:
        gift = _save_owned(
            GiftForm({"name": gift_form.cleaned_data["new_gift_name"]}), user, "gift"
        )

    event = occasion_form.cleaned_data["event"]
    new_event_name = occasion_form.cleaned_data["new_event_name"]
    if event is None and new_event_name:
        event_form = EventForm(
            {
                "name": new_event_name,
                "schedule_type": Event.ScheduleType.ONE_TIME,
                "date": occasion_form.cleaned_data["new_event_date"].isoformat(),
            }
        )
        event = _save_owned(event_form, user, "event")
    return gift, event


def build_relation_data(user, recipient_form, occasion_form, gift, event) -> dict:
    """Return the POST-like data ``RelationForm`` needs to create the guided plan.

    The status is ``Idea`` and ``is_surprise`` starts as it does in the full form for the recipient.
    """
    recipient = recipient_form.cleaned_data["recipient"]
    due_date = occasion_form.cleaned_data["due_date"]
    default_form = RelationForm(initial={"recipient": recipient}, user=user)
    return {
        "recipient": recipient,
        "gift": gift.pk,
        "event": event.pk if event else "",
        "due_date": due_date.isoformat() if due_date else "",
        "comment": occasion_form.cleaned_data["comment"],
        "status": RelationStatus.objects.get(status_en=DEFAULT_STATUS_NAME).pk,
        "is_surprise": bool(default_form.initial.get("is_surprise")),
    }
