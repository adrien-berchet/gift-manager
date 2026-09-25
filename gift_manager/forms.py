from collections.abc import Iterator

from django import forms
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.db.models import QuerySet
from django.utils.translation import gettext_lazy

from .email_encoding import decode_email
from .email_encoding import encode_email
from .group_hierarchy_service import GroupHierarchyService
from .models import Event
from .models import Gift
from .models import GiftTag
from .models import Person
from .models import PersonGroup
from .models import Relation
from .statuses import can_rate_status


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
    # Declared (not a Meta field) so ModelForm does not blindly .set() memberships:
    # they are saved through GroupHierarchyService, which checks group authority.
    groups = forms.ModelMultipleChoiceField(
        queryset=PersonGroup.objects.none(),
        required=False,
        label=gettext_lazy("Groups"),
    )

    class Meta:
        model = Person
        fields = ["first_name", "family_name", "email_address"]
        labels = {
            "first_name": gettext_lazy("First name"),
            "family_name": gettext_lazy("Family name"),
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
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.user = None
        if user is not None:
            self.set_user(user)
        # Decode the email address for display in the form
        if self.instance and self.instance.pk:
            self.initial["email_address"] = decode_email(self.instance.email_address)
            self.initial.setdefault("groups", list(self.instance.groups.all()))

    def set_user(self, user) -> None:
        """Bind the acting user: only groups they can edit are offered as choices."""
        self.user = user
        self.fields["groups"].queryset = _editable_by(
            PersonGroup.objects.accessible_by(user), user
        ).order_by("name")

    def _group_changes(self) -> tuple[set, set]:
        """Return (add, remove) groups; groups not offered as choices are left untouched."""
        selected = set(self.cleaned_data.get("groups", []))
        offered = set(self.fields["groups"].queryset)
        current = set(self.instance.groups.all()) if self.instance.pk else set()
        return selected - current, (current & offered) - selected

    def clean(self):
        cleaned_data = super().clean()
        if self.user is not None and not self.errors:
            add, remove = self._group_changes()
            try:
                GroupHierarchyService.check_person_group_changes(
                    self.user,
                    self.instance,
                    add=add,
                    remove=remove,
                    person_is_new=self.instance.pk is None,
                )
            except PermissionDenied as error:
                self.add_error("groups", str(error))
        return cleaned_data

    def save(self, *, commit=True):  # pylint: disable=arguments-differ
        instance = super().save(commit=False)
        # Encode the email address before saving
        email = self.cleaned_data.get("email_address")
        instance.email_address = encode_email(email)
        if commit:
            is_new = instance.pk is None
            with transaction.atomic():
                instance.save()
                if self.user is not None:
                    add, remove = self._group_changes()
                    GroupHierarchyService.change_person_groups(
                        self.user, instance, add=add, remove=remove, person_is_new=is_new
                    )
        return instance


def _denial(check, user, group, add, remove, group_is_new) -> str | None:
    """Return the denial message if check rejects the changes, else None."""
    try:
        check(user, group, add=add, remove=remove, group_is_new=group_is_new)
    except PermissionDenied as error:
        return str(error)
    return None


def _editable_by(queryset, user) -> QuerySet:
    """Restrict a queryset to the objects the user can edit."""
    return queryset.filter(pk__in=GroupHierarchyService.editable_pks(user, queryset))


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
        # Links are declared above and saved by GroupHierarchyService, not by
        # ModelForm's unconditional many-to-many .set()
        fields = ["name"]
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
        self.user = user

        if user:
            # Show only groups the user can edit: linking a group changes who can access it
            available_groups = _editable_by(PersonGroup.objects.accessible_by(user), user)
            available_child_groups = _editable_by(PersonGroup.objects.accessible_by(user), user)

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
            self.fields["persons"].queryset = _editable_by(
                Person.objects.accessible_by(user), user
            ).order_by("family_name", "first_name")

            # Set initial value if editing
            if self.instance and self.instance.pk:
                self.fields["persons"].initial = self.instance.person_set.all()

    def save(self, *, commit=True):  # pylint: disable=arguments-differ
        """Save the group and update the many-to-many relationships."""
        is_new = self.instance.pk is None
        with transaction.atomic():
            instance = super().save(commit=commit)
            if commit and self.user:
                self._save_relationships(instance, is_new=is_new)

        return instance

    def _relationship_changes(self, instance, *, is_new) -> Iterator[tuple]:
        """Yield (field, check, change, add, remove) for each submitted link field.

        Only links whose other end was offered as a choice are touched, so links
        to objects the user cannot edit survive the save.
        """
        for field, related_name, check, change in (
            (
                "parent_groups",
                "parent_groups",
                GroupHierarchyService.check_parent_changes,
                GroupHierarchyService.change_parents,
            ),
            (
                "child_groups",
                "child_groups",
                GroupHierarchyService.check_child_changes,
                GroupHierarchyService.change_children,
            ),
            (
                "persons",
                "person_set",
                GroupHierarchyService.check_member_changes,
                GroupHierarchyService.change_members,
            ),
        ):
            if field not in self.cleaned_data:
                continue
            selected = set(self.cleaned_data[field])
            offered = set(self.fields[field].queryset)
            current = set() if is_new else set(getattr(instance, related_name).all())
            yield field, check, change, selected - current, (current & offered) - selected

    def _check_relationship_permissions(self) -> None:
        """Report unauthorized link changes as form errors instead of failing on save."""
        if not self.user or self.errors:
            return
        is_new = self.instance.pk is None
        for field, check, _change, add, remove in self._relationship_changes(
            self.instance, is_new=is_new
        ):
            error = _denial(check, self.user, self.instance, add, remove, is_new)
            if error:
                self.add_error(field, error)

    def _save_relationships(self, instance, *, is_new) -> None:
        """Apply the submitted links through the authorization-aware service."""
        for _field, _check, change, add, remove in self._relationship_changes(
            instance, is_new=is_new
        ):
            change(self.user, instance, add=add, remove=remove, group_is_new=is_new)

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
        self._check_relationship_permissions()
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
        self.user = user
        # Filter the persons the user can edit
        if user:
            query = Q(shared_with=user)
            # Filter the persons not in the group if a group is given
            if group:
                query &= ~Q(groups=group)
            self.fields["persons"].queryset = _editable_by(
                Person.objects.filter(query), user
            ).order_by("family_name", "first_name")

    def save(self, group: PersonGroup):
        """Add all selected persons to the group."""
        GroupHierarchyService.change_members(self.user, group, add=self.cleaned_data["persons"])


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
        self.user = user
        self.parent_group = parent_group

        if user and parent_group:
            # Get all accessible groups
            available_groups = _editable_by(PersonGroup.objects.accessible_by(user), user)

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

    def clean(self):
        cleaned_data = super().clean()
        children = cleaned_data.get("child_groups")
        if self.user and self.parent_group and children:
            try:
                GroupHierarchyService.check_child_changes(
                    self.user, self.parent_group, add=children
                )
            except PermissionDenied as error:
                self.add_error("child_groups", str(error))
        return cleaned_data

    def save(self, parent_group: PersonGroup):
        """Add all selected groups as children of the parent group."""
        GroupHierarchyService.change_children(
            self.user, parent_group, add=self.cleaned_data["child_groups"]
        )
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

    def _save_m2m(self) -> None:
        """Save tags without dropping the ones the user was never offered.

        Views restrict the ``tags`` choices to the tags the user can access; the
        gift's other tags belong to other users and must survive the edit.
        """
        offered = set(self.fields["tags"].queryset)
        hidden = (set(self.instance.tags.all()) - offered) if self.instance.pk else set()
        super()._save_m2m()
        if hidden:
            self.instance.tags.add(*hidden)


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
    class Meta:
        model = Event
        fields = ["name", "comment", "schedule_type", "date", "recurrence"]
        widgets = {
            "name": forms.TextInput(attrs={"rows": 1}),
            "comment": forms.Textarea(attrs={"rows": 3}),
            "schedule_type": forms.RadioSelect,
            "date": forms.DateInput(attrs={"type": "date"}),
        }
        labels = {
            "name": gettext_lazy("Name"),
            "comment": gettext_lazy("Comment"),
            "schedule_type": gettext_lazy("Schedule"),
            "date": gettext_lazy("Date"),
            "recurrence": gettext_lazy("Recurrence"),
        }
        help_texts = {
            "date": gettext_lazy(
                "Use the event date for one-time events, or the typical date for repeating events."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date"].required = False
        self.fields["recurrence"].required = False

    def clean(self):
        """Validate and normalize event schedule fields."""
        cleaned_data = super().clean()
        schedule_type = cleaned_data.get("schedule_type")
        event_date = cleaned_data.get("date")
        recurrence = cleaned_data.get("recurrence")

        if schedule_type == Event.ScheduleType.UNSCHEDULED:
            cleaned_data["date"] = None
            cleaned_data["recurrence"] = None
            return cleaned_data

        if schedule_type == Event.ScheduleType.ONE_TIME:
            if not event_date:
                self.add_error("date", gettext_lazy("Choose a date."))
            cleaned_data["recurrence"] = None
            return cleaned_data

        if schedule_type == Event.ScheduleType.RECURRING:
            if not event_date:
                self.add_error("date", gettext_lazy("Choose a date."))
            if not recurrence:
                self.add_error("recurrence", gettext_lazy("Choose a recurrence."))
            return cleaned_data

        self.add_error("schedule_type", gettext_lazy("Choose a valid schedule."))
        return cleaned_data


REACTION_RATING_CHOICES = [(rating, str(rating)) for rating in range(1, 6)]
REACTION_FIELD_NAMES = ("reaction_rating", "reaction_note")
REACTION_NOTE_MAX_LENGTH = 1000


def build_reaction_rating_field() -> forms.TypedChoiceField:
    """Return the optional 1-5 rating field shared by the reaction forms."""
    return forms.TypedChoiceField(
        label=gettext_lazy("Rating"),
        choices=REACTION_RATING_CHOICES,
        coerce=int,
        empty_value=None,
        required=False,
        widget=forms.RadioSelect,
    )


def build_reaction_note_field() -> forms.CharField:
    """Return the optional reaction note field shared by the reaction forms."""
    return forms.CharField(
        label=gettext_lazy("Note"),
        required=False,
        max_length=REACTION_NOTE_MAX_LENGTH,
        widget=forms.Textarea(attrs={"rows": 3}),
    )


def _reaction_field_omitted(form, name: str) -> bool:
    """Return whether a reaction field was left out of the submitted data."""
    return form.fields[name].widget.value_omitted_from_data(
        form.data, form.files, form.add_prefix(name)
    )


class RelationReactionForm(BaseFormMixin, forms.ModelForm):
    """Rate how a recipient reacted to (or would have liked) a gift plan."""

    reaction_rating = build_reaction_rating_field()
    reaction_note = build_reaction_note_field()

    class Meta:
        model = Relation
        fields = list(REACTION_FIELD_NAMES)

    def clean(self):
        """Leave stored values untouched for fields the client did not submit."""
        cleaned_data = super().clean()
        for name in REACTION_FIELD_NAMES:
            if _reaction_field_omitted(self, name):
                cleaned_data.pop(name, None)
        return cleaned_data


class RelationForm(BaseFormMixin, forms.ModelForm):
    recipient = forms.ChoiceField(
        label=gettext_lazy("Recipient"),
        required=True,
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text=gettext_lazy("Choose the person or group this gift plan is for."),
    )
    reaction_rating = build_reaction_rating_field()
    reaction_note = build_reaction_note_field()

    class Meta:
        model = Relation
        fields = [
            "recipient",
            "gift",
            "comment",
            "event",
            "status",
            "due_date",
            *REACTION_FIELD_NAMES,
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
        self.rateable_status_ids = {
            str(status.pk) for status in self.fields["status"].queryset if can_rate_status(status)
        }
        self.fields["status"].widget.attrs["data-rateable-statuses"] = ",".join(
            sorted(self.rateable_status_ids)
        )

    @property
    def reaction_section_visible(self) -> bool:
        """Return whether the current status can carry a reaction rating."""
        return str(self["status"].value()) in self.rateable_status_ids

    def clean(self):
        """Validate and map the typed recipient choice to person/group fields."""
        cleaned_data = super().clean()
        try:
            apply_recipient_choice(self.instance, cleaned_data.get("recipient"), self.user)
        except forms.ValidationError as exc:
            self.add_error("recipient", exc)

        self._discard_inapplicable_reaction(cleaned_data)
        return cleaned_data

    def _discard_inapplicable_reaction(self, cleaned_data) -> None:
        """Leave the stored reaction untouched unless it applies to the submitted status."""
        rating_applies = can_rate_status(cleaned_data.get("status"))
        for name in REACTION_FIELD_NAMES:
            if not rating_applies or _reaction_field_omitted(self, name):
                cleaned_data.pop(name, None)
