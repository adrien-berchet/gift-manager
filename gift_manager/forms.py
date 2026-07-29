from django import forms
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.utils.translation import gettext_lazy

from .email_encoding import decode_email
from .email_encoding import encode_email
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


def build_recipient_choices(
    user,
    *,
    include_persons: bool = True,
    include_groups: bool = True,
) -> list:
    """Build typed recipient choices for person/group backed gift plans."""
    choices = [("", gettext_lazy("Select a recipient"))]

    if not user or not user.is_authenticated:
        return choices

    if include_persons:
        person_choices = [
            (f"person:{person.person_id}", str(person))
            for person in Person.objects.accessible_by(user).order_by("family_name", "first_name")
        ]
        if person_choices:
            choices.append((gettext_lazy("People"), person_choices))

    if include_groups:
        group_choices = [
            (f"group:{group.group_id}", group.name)
            for group in PersonGroup.objects.accessible_by(user).order_by("name")
        ]
        if group_choices:
            choices.append((gettext_lazy("Groups"), group_choices))

    return choices


def apply_recipient_choice(instance: Relation, recipient_value: str, user) -> None:
    """Map a typed recipient value back to the current Relation fields."""
    if not recipient_value:
        raise forms.ValidationError(gettext_lazy("Select a recipient."))

    recipient_type, separator, object_id = recipient_value.partition(":")
    if separator != ":" or not object_id:
        raise forms.ValidationError(gettext_lazy("Choose a valid recipient."))

    if not user or not user.is_authenticated:
        raise forms.ValidationError(gettext_lazy("Choose a valid recipient."))

    try:
        if recipient_type == "person":
            instance.person = Person.objects.accessible_by(user).get(person_id=object_id)
            instance.group = None
            return
        if recipient_type == "group":
            instance.group = PersonGroup.objects.accessible_by(user).get(group_id=object_id)
            instance.person = None
            return
    except (DjangoValidationError, Person.DoesNotExist, PersonGroup.DoesNotExist, ValueError):
        raise forms.ValidationError(gettext_lazy("Choose a valid recipient.")) from None

    raise forms.ValidationError(gettext_lazy("Choose a valid recipient."))


class PersonForm(BaseFormMixin, forms.ModelForm):
    # Use a separate field for the decoded email to display properly in the form
    email_address = forms.EmailField(
        required=False,
        label=gettext_lazy("Email address"),
        error_messages={
            "invalid": gettext_lazy("Enter a valid email address."),
        },
    )

    class Meta:
        model = Person
        fields = ["first_name", "family_name", "email_address", "groups"]
        labels = {
            "first_name": gettext_lazy("First name"),
            "family_name": gettext_lazy("Family name"),
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
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["groups"].required = False
        # Decode the email address for display in the form
        if self.instance and self.instance.pk:
            self.initial["email_address"] = decode_email(self.instance.email_address)

    def save(self, *, commit=True):  # pylint: disable=arguments-differ
        instance = super().save(commit=False)
        # Encode the email address before saving
        email = self.cleaned_data.get("email_address")
        instance.email_address = encode_email(email)
        if commit:
            instance.save()
            self._save_m2m()
        return instance


class PersonGroupForm(BaseFormMixin, forms.ModelForm):
    parent_groups = forms.ModelMultipleChoiceField(
        queryset=PersonGroup.objects.none(),
        required=False,
        widget=forms.SelectMultiple(
            attrs={
                "class": "form-select searchable-select",
                "size": "8",
            }
        ),
        label=gettext_lazy("Parent groups"),
        help_text=gettext_lazy("Hold Ctrl/Cmd to select multiple. Use the search box to filter."),
    )

    persons = forms.ModelMultipleChoiceField(
        queryset=Person.objects.none(),
        required=False,
        widget=forms.SelectMultiple(
            attrs={
                "class": "form-select searchable-select",
                "size": "10",
            }
        ),
        label=gettext_lazy("Members"),
        help_text=gettext_lazy("Hold Ctrl/Cmd to select multiple. Use the search box to filter."),
    )

    child_groups = forms.ModelMultipleChoiceField(
        queryset=PersonGroup.objects.none(),
        required=False,
        widget=forms.SelectMultiple(
            attrs={
                "class": "form-select searchable-select",
                "size": "8",
            }
        ),
        label=gettext_lazy("Child groups"),
        help_text=gettext_lazy("Hold Ctrl/Cmd to select multiple. Use the search box to filter."),
    )

    class Meta:
        model = PersonGroup
        fields = ["name", "parent_groups", "child_groups", "persons"]
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
            available_child_groups = PersonGroup.objects.accessible_by(user)

            # If editing an existing group, exclude self and descendants to prevent cycles
            # for parent_groups field
            if self.instance and self.instance.pk:
                descendants = self.instance.get_descendants()
                descendant_ids = [self.instance.pk] + [d.pk for d in descendants]
                available_groups = available_groups.exclude(pk__in=descendant_ids)

            self.fields["parent_groups"].queryset = available_groups.order_by("name")

            # Logic for child_groups
            # Exclude ancestors (and self) to prevent cycles
            if self.instance and self.instance.pk:
                ancestors = self.instance.get_ancestors()
                ancestor_ids = [self.instance.pk] + [a.pk for a in ancestors]
                available_child_groups = available_child_groups.exclude(pk__in=ancestor_ids)

            self.fields["child_groups"].queryset = available_child_groups.order_by("name")

            # Set initial value if editing
            if self.instance and self.instance.pk:
                self.fields["parent_groups"].initial = self.instance.parent_groups.all()
                self.fields["child_groups"].initial = self.instance.child_groups.all()

            # Show only persons accessible by the user
            self.fields["persons"].queryset = Person.objects.accessible_by(user).order_by(
                "family_name", "first_name"
            )

            # Set initial value if editing
            if self.instance and self.instance.pk:
                self.fields["persons"].initial = self.instance.person_set.all()

    def save(self, *, commit=True):  # pylint: disable=arguments-differ
        """Save the group and update the many-to-many relationships."""
        instance = super().save(commit=commit)

        if commit:
            # Update parent_groups relationship
            if "parent_groups" in self.cleaned_data:
                instance.parent_groups.set(self.cleaned_data["parent_groups"])

            # Update child_groups relationship
            if "child_groups" in self.cleaned_data:
                instance.child_groups.set(self.cleaned_data["child_groups"])

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
                        "Adding '%(parent)s' as a parent would create a cycle in the group "
                        "hierarchy."
                    )
                    % {"parent": parent.name}
                )

        return parent_groups

    def clean(self):
        cleaned_data = super().clean()
        parent_groups = cleaned_data.get("parent_groups", [])
        child_groups = cleaned_data.get("child_groups", [])

        # Check for direct intersection: a group cannot be both a parent and a child
        intersection = set(parent_groups).intersection(set(child_groups))
        if intersection:
            names = ", ".join([g.name for g in intersection])
            raise forms.ValidationError(
                gettext_lazy("The following groups cannot be both parent and child: %(names)s")
                % {"names": names}
            )

        # Check for deep/indirect cycles via new relationships
        # Scenario: Adding Parent P and Child C, where C is already an ancestor of P.
        # This creates G -> C -> ... -> P -> G (Cycle).
        # We need to ensure no selected child is an ancestor of any selected parent.
        children_set = set(child_groups)
        for parent in parent_groups:
            # We can use get_ancestors() which is cached/optimized on the model
            parent_ancestors = set(parent.get_ancestors())
            cycle_children = children_set.intersection(parent_ancestors)

            if cycle_children:
                names = ", ".join([c.name for c in cycle_children])
                raise forms.ValidationError(
                    gettext_lazy(
                        "Cannot add parent '%(parent)s' and child(ren) '%(children)s' "
                        "simultaneously because the child(ren) are ancestors of the parent "
                        "(Cycle: Group -> Child -> ... -> Parent -> Group)."
                    )
                    % {"parent": parent.name, "children": names}
                )

        return cleaned_data

    def clean_child_groups(self):
        """Validate that adding child groups won't create a cycle."""
        child_groups = self.cleaned_data.get("child_groups")

        if not self.instance or not self.instance.pk:
            # For new groups, no cycle check needed
            # (assuming the new group hasn't been saved yet, so it can't be an ancestor of anyone)
            return child_groups

        # Checking if 'self' is an ancestor of the potential child
        # If 'self' IS an ancestor of 'child', then 'child' is a descendant of 'self'.
        # Making 'child' a child of 'self' is fine (it's redundant but not a cycle unless child is
        # also an ancestor).
        # Wait. A cycle is formed if A -> B -> ... -> A.
        # If we make C a child of P (P -> C), we must ensure C is not an ancestor of P.
        # self.instance is P. child is C.
        # We need to check if P (self) is in C.get_descendants() ?? No.
        # We need to check if C is an ancestor of P.
        # P.has_cycle_with(ancestor) checks "if ancestor == self OR self in
        # ancestor.get_ancestors()"
        # Here we are adding children.
        # Cycle if: P -> C implies we cannot have C -> ... -> P.
        # So we check if P is already in C's descendants? No, that means C is an ancestor of P.
        # Essentially, creating P -> C is invalid if C is already an ancestor of P.

        for child in child_groups:
            # Check if 'child' is an ancestor of 'self' (the group we are editing)
            if child in self.instance.get_ancestors():
                raise forms.ValidationError(
                    gettext_lazy(
                        "Adding '%(child)s' as a child would create a cycle in the group "
                        "hierarchy (it is already an ancestor)."
                    )
                    % {"child": child.name}
                )

            # Also self cannot be child of self
            if child == self.instance:
                raise forms.ValidationError(gettext_lazy("A group cannot be a child of itself."))

        return child_groups


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


class PersonGroupAddMultipleChildGroupsForm(forms.Form):
    child_groups = forms.ModelMultipleChoiceField(
        queryset=PersonGroup.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label=gettext_lazy("Child groups"),
        help_text=gettext_lazy("Select groups to add as children of this group"),
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        parent_group = kwargs.pop("group", None)
        super().__init__(*args, **kwargs)

        if user and parent_group:
            # Get all accessible groups
            available_groups = PersonGroup.objects.accessible_by(user)

            # Exclude groups that would create cycles:
            # 1. The parent group itself
            # 2. Current children (already added)
            # 3. All ancestors of the parent (would create cycle)
            exclude_ids = [parent_group.pk]

            # Add current children
            exclude_ids.extend([child.pk for child in parent_group.get_children()])

            # Add ancestors (adding them as children would create a cycle)
            exclude_ids.extend([ancestor.pk for ancestor in parent_group.get_ancestors()])

            available_groups = available_groups.exclude(pk__in=exclude_ids)

            self.fields["child_groups"].queryset = available_groups.order_by("name")

    def save(self, parent_group: PersonGroup):
        """Add all selected groups as children of the parent group."""
        for child in self.cleaned_data["child_groups"]:
            parent_group.child_groups.add(child)
        parent_group.save()


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
        self.user = kwargs.pop("user", None)
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
                queryset = (
                    Person.objects.accessible_by(self.user)
                    if self.user and self.user.is_authenticated
                    else Person.objects.none()
                )
                self.instance.person = queryset.get(person_id=self.person_id)
            except (DjangoValidationError, Person.DoesNotExist):
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
        self.user = kwargs.pop("user", None)
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
                queryset = (
                    PersonGroup.objects.accessible_by(self.user)
                    if self.user and self.user.is_authenticated
                    else PersonGroup.objects.none()
                )
                self.instance.group = queryset.get(group_id=self.group_id)
            except (DjangoValidationError, PersonGroup.DoesNotExist):
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
    recipient = forms.ChoiceField(
        label=gettext_lazy("Recipient"),
        required=True,
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text=gettext_lazy("Choose the person or group this gift plan is for."),
    )

    class Meta:
        model = Relation
        fields = ["recipient", "comment", "event", "status", "due_date"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "comment": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "comment": gettext_lazy("Comment"),
            "event": gettext_lazy("Event"),
            "status": gettext_lazy("Status"),
            "due_date": gettext_lazy("Due date"),
        }

    def __init__(self, *args, **kwargs):
        self.gift_id = kwargs.pop("gift_id", None)
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.fields["recipient"].choices = build_recipient_choices(self.user)
        if self.instance and self.instance.pk:
            self.initial["recipient"] = self.instance.recipient_key
        self.fields["event"].queryset = Event.objects.all()
        self.fields["event"].required = False

    def clean(self):
        """Validate and map the typed recipient choice to person/group fields."""
        cleaned_data = super().clean()
        try:
            apply_recipient_choice(self.instance, cleaned_data.get("recipient"), self.user)
        except forms.ValidationError as exc:
            self.add_error("recipient", exc)

        # Set the gift from the gift_id parameter
        if self.gift_id:
            try:
                queryset = (
                    Gift.objects.accessible_by(self.user)
                    if self.user and self.user.is_authenticated
                    else Gift.objects.none()
                )
                self.instance.gift = queryset.get(gift_id=self.gift_id)
            except (DjangoValidationError, Gift.DoesNotExist):
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
    recipient = forms.ChoiceField(
        label=gettext_lazy("Recipient"),
        required=True,
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text=gettext_lazy("Choose the person or group this gift plan is for."),
    )

    class Meta:
        model = Relation
        fields = [
            "recipient",
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
            "gift": gettext_lazy("Gift"),
            "comment": gettext_lazy("Comment"),
            "event": gettext_lazy("Event"),
            "status": gettext_lazy("Status"),
            "due_date": gettext_lazy("Due date"),
        }

    def __init__(self, *args, **kwargs):
        hide_person = kwargs.pop("hide_person", False)
        hide_group = kwargs.pop("hide_group", False)
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.fields["recipient"].choices = build_recipient_choices(
            self.user,
            include_persons=not hide_person,
            include_groups=not hide_group,
        )
        if self.instance and self.instance.pk:
            self.initial["recipient"] = self.instance.recipient_key

    def clean(self):
        """Validate and map the typed recipient choice to person/group fields."""
        cleaned_data = super().clean()
        try:
            apply_recipient_choice(self.instance, cleaned_data.get("recipient"), self.user)
        except forms.ValidationError as exc:
            self.add_error("recipient", exc)

        return cleaned_data
