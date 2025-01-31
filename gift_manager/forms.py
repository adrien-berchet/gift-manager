from django import forms
from django.utils.translation import gettext_lazy

from .models import Event
from .models import Gift
from .models import Person
from .models import Relation


class PersonForm(forms.ModelForm):
    class Meta:
        model = Person
        fields = ["first_name", "family_name", "email_address", "groups", "shared_with"]
        labels = {
            "first_name": gettext_lazy("First Name"),
            "family_name": gettext_lazy("Family Name"),
            "email_address": gettext_lazy("Email Address"),
            "groups": gettext_lazy("Groups"),
            "shared_with": gettext_lazy("Shared With"),
        }
        error_messages = {
            "first_name": {
                "max_length": gettext_lazy("This first name is too long."),
            },
            "family_name": {
                "max_length": gettext_lazy("This family name is too long."),
            },
            "email_address": {
                "invalid": gettext_lazy("Enter a valid email address."),
            },
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["groups"].required = False
        self.fields["shared_with"].required = False


class PersonRelationForm(forms.ModelForm):
    class Meta:
        model = Relation
        fields = ["gift", "status", "due_date", "event"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["event"].queryset = Event.objects.all()
        self.fields["event"].required = False


class GiftForm(forms.ModelForm):
    class Meta:
        model = Gift
        fields = ["name", "comment", "tags", "shared_with"]
        labels = {
            "name": gettext_lazy("Name"),
            "comment": gettext_lazy("Comment"),
            "tags": gettext_lazy("Tags"),
            "shared_with": gettext_lazy("Shared With"),
        }
        error_messages = {
            "name": {
                "max_length": gettext_lazy("This name is too long."),
            },
            "comment": {
                "max_length": gettext_lazy("This comment is too long."),
            },
        }


class GiftRelationForm(forms.ModelForm):
    class Meta:
        model = Relation
        fields = ["person", "status", "due_date"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }


class EventForm(forms.ModelForm):
    date_type = forms.ChoiceField(
        label=gettext_lazy("Date Type"),
        choices=[
            ("absolute", gettext_lazy("Absolute Date")),
            ("recurrence", gettext_lazy("Recurrent")),
        ],
        widget=forms.RadioSelect,
    )

    class Meta:
        model = Event
        fields = ["name", "comment", "date_type", "absolute_date", "recurrence", "shared_with"]
        widgets = {
            "absolute_date": forms.DateInput(attrs={"type": "date"}),
        }
        labels = {
            "name": gettext_lazy("Name"),
            "comment": gettext_lazy("Comment"),
            "date_type": gettext_lazy("Date Type"),
            "absolute_date": gettext_lazy("Absolute Date"),
            "recurrence": gettext_lazy("Recurrence"),
            "shared_with": gettext_lazy("Shared With"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["absolute_date"].required = False
        self.fields["recurrence"].required = False

        if self.instance and self.instance.absolute_date:
            self.fields["date_type"].initial = "absolute"
        elif self.instance and self.instance.recurrence:
            self.fields["date_type"].initial = "recurrence"
