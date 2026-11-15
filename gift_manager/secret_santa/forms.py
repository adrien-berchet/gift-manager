"""Forms of the Secret Santa organizer pages."""

from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy

from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.secret_santa.models import ExchangeParticipant


class ExchangeForm(forms.Form):
    """Create or edit an exchange; ``organizer_takes_part`` only exists at creation."""

    name = forms.CharField(
        label=gettext_lazy("Name"),
        max_length=120,
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "off"}),
    )
    exchange_date = forms.DateField(
        label=gettext_lazy("Exchange date"),
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
    )
    budget = forms.DecimalField(
        label=gettext_lazy("Budget"),
        required=False,
        min_value=0,
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
    )
    guidelines = forms.CharField(
        label=gettext_lazy("Guidelines"),
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        help_text=gettext_lazy("Shown on the personal page of every participant."),
    )
    no_mutual_draw = forms.BooleanField(
        label=gettext_lazy("Nobody draws the person who drew them"),
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    organizer_takes_part = forms.BooleanField(
        label=gettext_lazy("I take part in the draw"),
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def __init__(self, *args, creating: bool = True, switch_locked: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        if not creating:
            del self.fields["organizer_takes_part"]
        if switch_locked:
            self.fields["no_mutual_draw"].disabled = True
            self.fields["no_mutual_draw"].help_text = gettext_lazy(
                "This rule can only change before the draw."
            )


class ParticipantForm(forms.Form):
    """A typed participant: a name and an optional email address."""

    name = forms.CharField(
        label=gettext_lazy("Name"),
        max_length=120,
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "off"}),
    )
    email = forms.EmailField(
        label=gettext_lazy("Email"),
        required=False,
        widget=forms.EmailInput(attrs={"class": "form-control", "autocomplete": "off"}),
    )


class ExclusionSetForm(forms.Form):
    """A named set of participants who must not draw each other."""

    set_id = forms.UUIDField(required=False, widget=forms.HiddenInput)
    name = forms.CharField(
        label=gettext_lazy("Name"),
        max_length=120,
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "off"}),
    )
    participants = forms.ModelMultipleChoiceField(
        label=gettext_lazy("Participants"),
        queryset=ExchangeParticipant.objects.none(),
        to_field_name="participant_id",
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
    )

    def __init__(self, *args, exchange, **kwargs):
        super().__init__(*args, **kwargs)
        # Pairings are never loaded by organizer pages
        self.fields["participants"].queryset = exchange.participants.defer("gives_to").order_by(
            "name"
        )


class ImportForm(forms.Form):
    """Import a whole group and/or some persons of the organizer's address book."""

    group = forms.ModelChoiceField(
        label=gettext_lazy("A group"),
        queryset=PersonGroup.objects.none(),
        to_field_name="group_id",
        required=False,
        empty_label=gettext_lazy("No group"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    persons = forms.ModelMultipleChoiceField(
        label=gettext_lazy("Persons"),
        queryset=Person.objects.none(),
        to_field_name="person_id",
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": 6}),
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["group"].queryset = PersonGroup.objects.accessible_by(user).order_by("name")
        self.fields["persons"].queryset = Person.objects.accessible_by(user).order_by(
            "first_name", "family_name"
        )

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("group") and not cleaned.get("persons"):
            raise forms.ValidationError(gettext_lazy("Choose a group or some persons."))
        return cleaned
