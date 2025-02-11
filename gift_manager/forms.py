from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy

from .models import Event
from .models import Gift
from .models import Person
from .models import PersonGroup
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


class PersonGroupForm(forms.ModelForm):
    class Meta:
        model = PersonGroup
        fields = ["name", "shared_with"]
        labels = {
            "name": gettext_lazy("Name"),
            "shared_with": gettext_lazy("Shared With"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].required = False
        self.fields["shared_with"].required = False


class PersonGroupAddMultiplePersonsForm(forms.Form):
    persons = forms.ModelMultipleChoiceField(
        queryset=Person.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label="Persons",
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)  # Get the user from the kwargs
        super().__init__(*args, **kwargs)
        # Filter the persons accessible to this user
        if user:
            self.fields["persons"].queryset = Person.objects.filter(Q(shared_with=user))

    def save(self, group: PersonGroup):
        """Add all selected persons to the group."""
        for i in self.cleaned_data["persons"]:
            i.groups.add(group)
            i.save()


class PersonRelationForm(forms.ModelForm):
    class Meta:
        model = Relation
        fields = ["gift", "status", "due_date", "event", "shared_with"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["event"].queryset = Event.objects.all()
        self.fields["event"].required = False


class PersonGroupRelationForm(forms.ModelForm):
    class Meta:
        model = Relation
        fields = ["gift", "status", "due_date", "event", "shared_with"]
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
        fields = ["person", "group", "status", "due_date", "shared_with"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        person = cleaned_data.get("person")
        group = cleaned_data.get("group")

        if person and group:
            self.add_error("group", gettext_lazy("You can not select both a person and a group."))
        elif not person and not group:
            raise forms.ValidationError(gettext_lazy("You must select one person or one group."))

        return cleaned_data


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


class RelationForm(forms.ModelForm):
    class Meta:
        model = Relation
        fields = ["person", "group", "gift", "status", "due_date", "shared_with"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        person = cleaned_data.get("person")
        group = cleaned_data.get("group")

        if person and group:
            self.add_error("group", gettext_lazy("You can not select both a person and a group."))
        elif not person and not group:
            raise forms.ValidationError(gettext_lazy("You must select one person or one group."))

        return cleaned_data
