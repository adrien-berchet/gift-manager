from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy

from .models import Event
from .models import Gift
from .models import GiftTag
from .models import Person
from .models import PersonGroup
from .models import Relation


class BaseFormMixin:
    """Mixin to apply CSS classes to form fields."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Apply CSS classes to form fields based on the widget type
        for field in self.fields.values():
            if isinstance(field.widget, (forms.TextInput | forms.EmailInput)):
                field.widget.attrs.update({"class": "form-input-text"})
            elif isinstance(field.widget, forms.Textarea):
                field.widget.attrs.update({"class": "form-textarea"})
            elif isinstance(field.widget, forms.DateInput):
                field.widget.attrs.update({"class": "form-date-input", "type": "date"})


class PersonForm(BaseFormMixin, forms.ModelForm):
    class Meta:
        model = Person
        fields = ["first_name", "family_name", "email_address", "groups"]
        labels = {
            "first_name": gettext_lazy("First name"),
            "family_name": gettext_lazy("Family name"),
            "email_address": gettext_lazy("Email address"),
            "groups": gettext_lazy("Groups"),
        }
        widgets = {
            "first_name": forms.TextInput(attrs={"rows": 1}),
            "family_name": forms.TextInput(attrs={"rows": 1}),
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


class PersonGroupForm(BaseFormMixin, forms.ModelForm):
    parent_groups = forms.ModelMultipleChoiceField(
        queryset=PersonGroup.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label=gettext_lazy("Parent groups"),
        help_text=gettext_lazy("Select parent groups for this group (optional)"),
    )

    persons = forms.ModelMultipleChoiceField(
        queryset=Person.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label=gettext_lazy("Members"),
        help_text=gettext_lazy("Select persons who belong to this group (optional)"),
    )

    class Meta:
        model = PersonGroup
        fields = ["name", "parent_groups", "persons"]
        labels = {
            "name": gettext_lazy("Name"),
        }
        widgets = {
            "name": forms.TextInput(attrs={"rows": 1}),
        }

    def __init__(self, *args, **kwargs):
        # Extract user from kwargs before calling super().__init__
        user = kwargs.pop("user", None)

        super().__init__(*args, **kwargs)
        self.fields["name"].required = False

        if user:
            # Show only groups accessible by the user
            available_groups = PersonGroup.objects.accessible_by(user)

            # If editing an existing group, exclude self and descendants to prevent cycles
            if self.instance and self.instance.pk:
                descendants = self.instance.get_descendants()
                descendant_ids = [self.instance.pk] + [d.pk for d in descendants]
                available_groups = available_groups.exclude(pk__in=descendant_ids)

            self.fields["parent_groups"].queryset = available_groups

            # Set initial value if editing
            if self.instance and self.instance.pk:
                self.fields["parent_groups"].initial = self.instance.parent_groups.all()

            # Show only persons accessible by the user
            self.fields["persons"].queryset = Person.objects.accessible_by(user).order_by(
                "family_name", "first_name"
            )

            # Set initial value if editing
            if self.instance and self.instance.pk:
                self.fields["persons"].initial = self.instance.person_set.all()

    def save(self, commit=True):
        """Save the group and update the many-to-many relationships."""
        instance = super().save(commit=commit)

        if commit:
            # Update parent_groups relationship
            if "parent_groups" in self.cleaned_data:
                instance.parent_groups.set(self.cleaned_data["parent_groups"])

            # Update persons relationship
            if "persons" in self.cleaned_data:
                instance.person_set.set(self.cleaned_data["persons"])

        return instance

    def clean_parent_groups(self):
        """Validate that adding parent groups won't create a cycle."""
        parent_groups = self.cleaned_data.get("parent_groups")

        if not self.instance or not self.instance.pk:
            # For new groups, no cycle check needed
            return parent_groups

        for parent in parent_groups:
            if self.instance.has_cycle_with(parent):
                raise forms.ValidationError(
                    gettext_lazy(
                        "Adding '%(parent)s' as a parent would create a cycle in the group hierarchy."
                    )
                    % {"parent": parent.name}
                )

        return parent_groups


class PersonGroupAddMultiplePersonsForm(forms.Form):
    persons = forms.ModelMultipleChoiceField(
        queryset=Person.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label="Persons",
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)  # Get the user from the kwargs
        group = kwargs.pop("group", None)  # Get the group from the kwargs
        super().__init__(*args, **kwargs)
        # Filter the persons accessible to this user
        if user:
            query = Q(shared_with=user)
            # Filter the persons not in the group if a group is given
            if group:
                query &= ~Q(groups=group)
            self.fields["persons"].queryset = Person.objects.filter(query).order_by(
                "family_name", "first_name"
            )

    def save(self, group: PersonGroup):
        """Add all selected persons to the group."""
        for i in self.cleaned_data["persons"]:
            i.groups.add(group)
            i.save()


class PersonRelationForm(BaseFormMixin, forms.ModelForm):
    class Meta:
        model = Relation
        fields = ["gift", "comment", "event", "status", "due_date"]
        widgets = {
            "comment": forms.Textarea(attrs={"rows": 3}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }
        labels = {
            "gift": gettext_lazy("Gift"),
            "comment": gettext_lazy("Comment"),
            "event": gettext_lazy("Event"),
            "status": gettext_lazy("Status"),
            "due_date": gettext_lazy("Due date"),
        }

    def __init__(self, *args, **kwargs):
        self.person_id = kwargs.pop("person_id", None)
        super().__init__(*args, **kwargs)
        self.fields["event"].queryset = Event.objects.all()
        self.fields["event"].required = False

    def clean(self):
        cleaned_data = super().clean()
        # Ensure that the group is None
        self.instance.group = None

        # Define the person if the person_id is given
        if self.person_id:
            try:
                self.instance.person = Person.objects.get(person_id=self.person_id)
            except Person.DoesNotExist:
                raise forms.ValidationError(
                    gettext_lazy("The specified person does not exist.")
                ) from None

        return cleaned_data


class PersonGroupRelationForm(BaseFormMixin, forms.ModelForm):
    class Meta:
        model = Relation
        fields = ["gift", "comment", "event", "status", "due_date"]
        widgets = {
            "comment": forms.Textarea(attrs={"rows": 3}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }
        labels = {
            "gift": gettext_lazy("Gift"),
            "comment": gettext_lazy("Comment"),
            "event": gettext_lazy("Event"),
            "status": gettext_lazy("Status"),
            "due_date": gettext_lazy("Due date"),
        }

    def __init__(self, *args, **kwargs):
        self.group_id = kwargs.pop("group_id", None)
        super().__init__(*args, **kwargs)
        self.fields["event"].queryset = Event.objects.all()
        self.fields["event"].required = False

    def clean(self):
        cleaned_data = super().clean()
        # Ensure person is None since this is a group relation form
        self.instance.person = None

        # Set the group from the group_id parameter
        if self.group_id:
            try:
                self.instance.group = PersonGroup.objects.get(group_id=self.group_id)
            except PersonGroup.DoesNotExist:
                raise forms.ValidationError(
                    gettext_lazy("The specified person group does not exist.")
                ) from None

        return cleaned_data


class GiftForm(BaseFormMixin, forms.ModelForm):
    class Meta:
        model = Gift
        fields = ["name", "comment", "tags"]
        labels = {
            "name": gettext_lazy("Name"),
            "comment": gettext_lazy("Comment"),
            "tags": gettext_lazy("Tags"),
        }
        widgets = {
            "name": forms.TextInput(attrs={"rows": 1}),
            "comment": forms.Textarea(attrs={"rows": 3}),
        }
        error_messages = {
            "name": {
                "max_length": gettext_lazy("This name is too long."),
            },
            "comment": {
                "max_length": gettext_lazy("This comment is too long."),
            },
        }


class GiftTagForm(BaseFormMixin, forms.ModelForm):
    class Meta:
        model = GiftTag
        fields = ["name", "parent_tags"]
        widgets = {
            "parent_tags": forms.SelectMultiple(attrs={"class": "form-control"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        # If the form is in edit mode, check that the parent tags do not create a cycle
        if self.instance and self.instance.pk:
            for parent in cleaned_data.get("parent_tags", []):
                if self.instance.has_cycle_with(parent):
                    self.add_error(
                        "parent_tags",
                        gettext_lazy(
                            "Adding this parent would create a cycle in the tag hierarchy."
                        ),
                    )
        return cleaned_data


class GiftRelationForm(BaseFormMixin, forms.ModelForm):
    class Meta:
        model = Relation
        fields = ["person", "group", "comment", "event", "status", "due_date"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "comment": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "person": gettext_lazy("Person"),
            "group": gettext_lazy("Group"),
            "comment": gettext_lazy("Comment"),
            "event": gettext_lazy("Event"),
            "status": gettext_lazy("Status"),
            "due_date": gettext_lazy("Due date"),
        }

    def __init__(self, *args, **kwargs):
        self.gift_id = kwargs.pop("gift_id", None)
        super().__init__(*args, **kwargs)
        self.fields["event"].queryset = Event.objects.all()
        self.fields["event"].required = False

    def clean(self):
        cleaned_data = super().clean()
        # Ensure that the group is None
        self.instance.group = None

        # Define the person if the group_id is given
        if self.gift_id:
            try:
                self.instance.gift = Gift.objects.get(gift_id=self.gift_id)
            except Gift.DoesNotExist:
                raise forms.ValidationError(
                    gettext_lazy("The specified gift does not exist.")
                ) from None

        return cleaned_data


class EventForm(BaseFormMixin, forms.ModelForm):
    date_type = forms.ChoiceField(
        label=gettext_lazy("Date type"),
        choices=[
            ("absolute", gettext_lazy("Absolute date")),
            ("recurrence", gettext_lazy("Recurrent")),
        ],
        widget=forms.RadioSelect,
    )

    class Meta:
        model = Event
        fields = ["name", "comment", "date_type", "absolute_date", "recurrence"]
        widgets = {
            "name": forms.TextInput(attrs={"rows": 1}),
            "comment": forms.Textarea(attrs={"rows": 3}),
            "absolute_date": forms.DateInput(attrs={"type": "date"}),
        }
        labels = {
            "name": gettext_lazy("Name"),
            "comment": gettext_lazy("Comment"),
            "date_type": gettext_lazy("Date type"),
            "absolute_date": gettext_lazy("Absolute date"),
            "recurrence": gettext_lazy("Recurrence"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["absolute_date"].required = False
        self.fields["recurrence"].required = False

        if self.instance and self.instance.absolute_date:
            self.fields["date_type"].initial = "absolute"
        elif self.instance and self.instance.recurrence:
            self.fields["date_type"].initial = "recurrence"


class RelationForm(BaseFormMixin, forms.ModelForm):
    class Meta:
        model = Relation
        fields = [
            "person",
            "group",
            "gift",
            "comment",
            "event",
            "status",
            "due_date",
        ]
        widgets = {
            "comment": forms.Textarea(attrs={"rows": 3}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }
        labels = {
            "person": gettext_lazy("Person"),
            "group": gettext_lazy("Group"),
            "gift": gettext_lazy("Gift"),
            "comment": gettext_lazy("Comment"),
            "event": gettext_lazy("Event"),
            "status": gettext_lazy("Status"),
            "due_date": gettext_lazy("Due date"),
        }

    def __init__(self, *args, **kwargs):
        hide_person = kwargs.pop("hide_person", False)
        hide_group = kwargs.pop("hide_group", False)
        super().__init__(*args, **kwargs)
        if hide_person:
            self.fields.pop("person", None)
        if hide_group:
            self.fields.pop("group", None)
