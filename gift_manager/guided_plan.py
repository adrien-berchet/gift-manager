"""Step forms and helpers of the guided gift plan creation flow.

The guided flow collects a gift plan in three steps (recipient, gift, occasion). Each step form
offers an existing object or a new one. A new object is the object's own model form
(``PersonForm``, ``GiftForm``, ``EventForm``) embedded as a prefixed sub-form, validated only when
its identifying field is filled. The final save re-validates every step, creates the new objects,
and hands the assembled data to ``RelationForm`` so the plan matches one created with the full
form.
"""

from typing import NamedTuple

from django import forms
from django.utils.translation import gettext_lazy

from gift_manager.forms import BaseFormMixin
from gift_manager.forms import EventForm
from gift_manager.forms import GiftForm
from gift_manager.forms import PersonForm
from gift_manager.forms import RelationForm
from gift_manager.forms import build_recipient_choices
from gift_manager.forms import resolve_recipient_choice
from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import GiftTag
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import RelationStatus
from gift_manager.services import PermissionService

GUIDED_STEPS = ("recipient", "gift", "occasion")

DEFAULT_STATUS_NAME = "Idea"

PLAN_FIELD_NAMES = ("due_date", "comment", "status", "url", "price")


class _GuidedStepForm(BaseFormMixin, forms.Form):
    """Base class of the step forms: a plain form that knows the creating user."""

    def __init__(self, data=None, *, user, **kwargs):
        self.user = user
        super().__init__(data, **kwargs)


class _NewObjectStepForm(_GuidedStepForm):
    """A step offering an existing object (the chooser field) or a new one (``new_form``).

    ``new_form`` is bound to the posted data only when the new object is requested, i.e. when its
    identifying field is filled; otherwise it is unbound, prefilled with whatever was typed, and
    never validated. ``initial_values`` prefills an unbound step (own fields and ``new_form``)
    from previously posted values.
    """

    chooser_name: str
    new_form_class: type[forms.ModelForm]
    new_prefix: str
    identifying_field: str
    visible_new_fields: tuple[str, ...]
    new_defaults: dict = {}
    choose_message = None
    both_message = None

    def __init__(self, data=None, *, user, initial_values=None, **kwargs):
        super().__init__(data, user=user, **kwargs)
        values = data if data is not None else initial_values
        self.new_requested = data is not None and bool(
            (data.get(f"{self.new_prefix}-{self.identifying_field}") or "").strip()
        )
        self.new_form = self._build_new_form(data, values)
        if data is None and values is not None:
            self._prefill(self, values, prefix="")

    def _new_form_kwargs(self) -> dict:
        return {}

    def _configure_new_form(self, form: forms.ModelForm) -> None:
        """Hook: scope the sub-form's choices to what the user can access."""

    def _build_new_form(self, data, values) -> forms.ModelForm:
        if self.new_requested:
            form = self.new_form_class(data, prefix=self.new_prefix, **self._new_form_kwargs())
            self._configure_new_form(form)
            return form
        form = self.new_form_class(prefix=self.new_prefix, **self._new_form_kwargs())
        self._configure_new_form(form)
        form.initial.update(self.new_defaults)
        if values is not None:
            self._prefill(form, values, prefix=self.new_prefix)
        return form

    @staticmethod
    def _prefill(form, values, *, prefix: str) -> None:
        """Copy the posted ``values`` of ``form``'s fields into its initial data."""
        for name, field in form.fields.items():
            key = f"{prefix}-{name}" if prefix else name
            if key in values:
                form.initial[name] = field.widget.value_from_datadict(values, {}, key)

    def input_names(self) -> list[str]:
        """Return every input name of the step (own fields, then the prefixed sub-form's)."""
        return [*self.fields, *(self.new_form.add_prefix(name) for name in self.new_form.fields)]

    def new_visible_fields(self) -> list:
        return [self.new_form[name] for name in self.visible_new_fields]

    def new_detail_fields(self) -> list:
        return [
            self.new_form[name]
            for name in self.new_form.fields
            if name not in self.visible_new_fields
        ]

    @property
    def details_open(self) -> bool:
        """Whether "More details" should start open: it has errors or non-default values."""
        if self.new_requested and self.new_form.errors:
            return True
        return any(
            bound.value() not in (None, "", [], ())
            and bound.value() != self.new_defaults.get(bound.name)
            for bound in self.new_detail_fields()
        )

    def clean(self) -> dict:
        cleaned_data = super().clean()
        if self.chooser_name in self.errors:
            return cleaned_data
        existing = cleaned_data.get(self.chooser_name)
        if existing and self.new_requested:
            self.add_error(self.chooser_name, self.both_message)
        elif not existing and not self.new_requested and self.choose_message:
            self.add_error(self.chooser_name, self.choose_message)
        return cleaned_data

    def is_valid(self) -> bool:
        step_valid = super().is_valid()
        new_valid = not self.new_requested or self.new_form.is_valid()
        return step_valid and new_valid


class GuidedRecipientForm(_NewObjectStepForm):
    """Step 1: an existing person or group, or a new person."""

    chooser_name = "recipient"
    new_form_class = PersonForm
    new_prefix = "new_person"
    identifying_field = "first_name"
    visible_new_fields = ("first_name",)
    choose_message = gettext_lazy("Choose a recipient or enter the first name of a new person.")
    both_message = gettext_lazy("Choose an existing recipient or enter a new person, not both.")

    recipient = forms.ChoiceField(
        label=gettext_lazy("Recipient"),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, data=None, *, user, **kwargs):
        super().__init__(data, user=user, **kwargs)
        self.fields["recipient"].choices = build_recipient_choices(user)

    def _new_form_kwargs(self) -> dict:
        return {"user": self.user}

    def clean_recipient(self) -> str:
        value = self.cleaned_data["recipient"]
        if value:
            resolve_recipient_choice(value, self.user)
        return value


class GuidedGiftForm(_NewObjectStepForm):
    """Step 2: an existing gift, or a new one."""

    chooser_name = "gift"
    new_form_class = GiftForm
    new_prefix = "new_gift"
    identifying_field = "name"
    visible_new_fields = ("name",)
    choose_message = gettext_lazy("Choose a gift or enter a new gift name.")
    both_message = gettext_lazy("Choose an existing gift or enter a new one, not both.")

    gift = forms.ModelChoiceField(
        label=gettext_lazy("Gift"),
        queryset=Gift.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, data=None, *, user, **kwargs):
        super().__init__(data, user=user, **kwargs)
        self.fields["gift"].queryset = Gift.objects.accessible_by(user).order_by("name")

    def _configure_new_form(self, form: forms.ModelForm) -> None:
        form.fields["tags"].queryset = GiftTag.objects.accessible_by(self.user).order_by("name")


class GuidedOccasionForm(_NewObjectStepForm):
    """Step 3: the event (existing or new), the due date and the plan's own details."""

    chooser_name = "event"
    new_form_class = EventForm
    new_prefix = "new_event"
    identifying_field = "name"
    visible_new_fields = ("name", "date")
    new_defaults = {"schedule_type": Event.ScheduleType.ONE_TIME}
    both_message = gettext_lazy("Choose an existing event or enter a new one, not both.")

    event = forms.ModelChoiceField(
        label=gettext_lazy("Event"),
        queryset=Event.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, data=None, *, user, recipient_value: str = "", **kwargs):
        super().__init__(data, user=user, **kwargs)
        self.fields["event"].queryset = Event.objects.accessible_by(user).order_by("name")
        plan_form = RelationForm(initial={"recipient": recipient_value}, user=user)
        for name in PLAN_FIELD_NAMES:
            self.fields[name] = plan_form.fields[name]
        status = self.fields["status"]
        status.empty_label = None
        idea = RelationStatus.objects.filter(status_en=DEFAULT_STATUS_NAME).first()
        status.initial = idea.pk if idea else None
        self.fields["is_surprise"] = forms.TypedChoiceField(
            label=gettext_lazy("Surprise"),
            choices=[("false", gettext_lazy("No")), ("true", gettext_lazy("Yes"))],
            coerce=lambda value: value == "true",
            empty_value=False,
            required=False,
            initial="true" if plan_form.initial.get("is_surprise") else "false",
        )
        if data is None and kwargs.get("initial_values") is not None:
            self._prefill(self, kwargs["initial_values"], prefix="")

    def clean(self) -> dict:
        cleaned_data = super().clean()
        if self.errors or cleaned_data.get("due_date"):
            return cleaned_data
        event = cleaned_data.get("event")
        if event:
            cleaned_data["due_date"] = event.next_occurrence()
        elif self.new_requested and self.new_form.is_valid():
            new_event = self.new_form.instance
            cleaned_data["due_date"] = (
                new_event.next_occurrence() or self.new_form.cleaned_data.get("date")
            )
        return cleaned_data


STEP_FORMS = {
    "recipient": GuidedRecipientForm,
    "gift": GuidedGiftForm,
    "occasion": GuidedOccasionForm,
}


class InlineObjects(NamedTuple):
    """The recipient, gift and event of a guided plan, chosen or newly created."""

    recipient_value: str
    gift: Gift
    event: Event | None


def _save_owned(form: forms.ModelForm, user, object_attr: str) -> Person | Gift | Event:
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


def create_inline_objects(user, recipient_form, gift_form, occasion_form) -> InlineObjects:
    """Return the chosen or newly created recipient, gift and event of validated step forms.

    New objects come from the steps' ``new_form`` sub-forms and are owned by ``user``. Call it
    inside the caller's transaction so that nothing is left behind when the plan is rejected.
    """
    if recipient_form.new_requested:
        person = _save_owned(recipient_form.new_form, user, "person")
        recipient_value = f"person:{person.person_id}"
    else:
        recipient_value = recipient_form.cleaned_data["recipient"]

    if gift_form.new_requested:
        gift = _save_owned(gift_form.new_form, user, "gift")
    else:
        gift = gift_form.cleaned_data["gift"]

    if occasion_form.new_requested:
        event = _save_owned(occasion_form.new_form, user, "event")
    else:
        event = occasion_form.cleaned_data["event"]
    return InlineObjects(recipient_value, gift, event)


def build_relation_data(user, inline: InlineObjects, occasion_form) -> dict:  # noqa: ARG001
    """Return the POST-like data ``RelationForm`` needs to create the guided plan."""
    cleaned = occasion_form.cleaned_data
    due_date = cleaned["due_date"]
    return {
        "recipient": inline.recipient_value,
        "gift": inline.gift.pk,
        "event": inline.event.pk if inline.event else "",
        "due_date": due_date.isoformat() if due_date else "",
        "comment": cleaned["comment"],
        "status": cleaned["status"].pk,
        "url": cleaned["url"],
        "price": cleaned["price"],
        "is_surprise": bool(cleaned["is_surprise"]),
    }
