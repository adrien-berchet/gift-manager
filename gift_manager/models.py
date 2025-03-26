import uuid

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.functional import classproperty
from django.utils.translation import gettext_lazy

_PERMISSION_LEVEL_DICT = {"none": 0, "viewer": 10, "editor": 20, "owner": 30}
_PERMISSION_LABEL_DICT = {
    0: gettext_lazy("none"),
    10: gettext_lazy("viewer"),
    20: gettext_lazy("editor"),
    30: gettext_lazy("owner"),
}


class PermissionLevel:
    NONE = _PERMISSION_LEVEL_DICT["none"]
    VIEWER = _PERMISSION_LEVEL_DICT["viewer"]
    EDITOR = _PERMISSION_LEVEL_DICT["editor"]
    OWNER = _PERMISSION_LEVEL_DICT["owner"]

    CHOICES = [
        (NONE, _PERMISSION_LABEL_DICT[NONE]),
        (VIEWER, _PERMISSION_LABEL_DICT[VIEWER]),
        (EDITOR, _PERMISSION_LABEL_DICT[EDITOR]),
        (OWNER, _PERMISSION_LABEL_DICT[OWNER]),
    ]

    @classmethod
    def get_label(cls, permission_level, case="lower") -> str:
        """Get the label of a permission level."""
        label = _PERMISSION_LABEL_DICT.get(permission_level, "none")
        if case == "upper":
            return label.upper()
        if case == "title":
            return label.title()
        return label


class UserPermissionManager(models.Manager):
    def accessible_by(self, user):
        """Return all objects accessible by a user."""
        return self.filter(Q(shared_with=user))


class Profile(models.Model):
    """Model for a user profile."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    friends = models.ManyToManyField("self", symmetrical=True, blank=True)

    def __str__(self):
        return f"{gettext_lazy('Profile of')} {self.user.username}"


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):  # noqa: ARG001
    if created:  # pragma: no branch
        Profile.objects.create(user=instance)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def save_user_profile(sender, instance, **kwargs):  # noqa: ARG001
    if hasattr(instance, "profile"):
        instance.profile.save()
    else:  # pragma: no branch
        Profile.objects.create(user=instance)


class Invitation(models.Model):
    """Model for an invitation."""

    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="%(app_label)s_%(class)s_invitations_sent",
        on_delete=models.CASCADE,
    )
    recipient_email = models.EmailField()
    accepted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return (
            f"{gettext_lazy('Invitation from')} {self.sender} "
            f"{gettext_lazy('to')} {self.recipient_email}"
        )


class Person(models.Model):
    """Model for a person."""

    person_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    first_name = models.TextField(unique=False, null=False)
    family_name = models.TextField(unique=False, null=True, blank=True)
    email_address = models.EmailField(unique=False, null=True, blank=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    groups = models.ManyToManyField("PersonGroup", blank=True)
    shared_with = models.ManyToManyField(
        User, through="PersonPermission", related_name="%(app_label)s_%(class)s_shared_with"
    )
    user_link = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="%(app_label)s_%(class)s_user",
        null=True,
        blank=True,
    )

    # Custom manager
    objects = UserPermissionManager()

    class Meta:
        verbose_name = gettext_lazy("Person")
        verbose_name_plural = gettext_lazy("Persons")

    def __str__(self):
        return (self.first_name + " " + (self.family_name or "")).strip()


class PersonPermission(models.Model):
    """Model for permissions on a person."""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    person = models.ForeignKey(Person, on_delete=models.CASCADE)
    permission_type = models.IntegerField(
        choices=PermissionLevel.CHOICES, default=PermissionLevel.VIEWER
    )

    class Meta:
        unique_together = ("user", "person")

    def __str__(self):
        return f"{self.user} - {self.person} -> {PermissionLevel.get_label(self.permission_type)}"

    @classproperty
    def filter_name(self):
        return "person"


class PersonGroup(models.Model):
    """Model for a group of persons."""

    group_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.TextField(unique=False, null=False)
    creation_date = models.DateTimeField(auto_now_add=True)
    shared_with = models.ManyToManyField(
        User, through="PersonGroupPermission", related_name="%(app_label)s_%(class)s_shared_with"
    )

    # Custom manager
    objects = UserPermissionManager()

    class Meta:
        verbose_name = gettext_lazy("Person group")
        verbose_name_plural = gettext_lazy("¨Person groups")

    def __str__(self):
        return self.name


class PersonGroupPermission(models.Model):
    """Model for permissions on a group."""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    group = models.ForeignKey(PersonGroup, on_delete=models.CASCADE)
    permission_type = models.IntegerField(
        choices=PermissionLevel.CHOICES, default=PermissionLevel.VIEWER
    )

    class Meta:
        unique_together = ("user", "group")

    def __str__(self):
        return f"{self.user} - {self.group} -> {PermissionLevel.get_label(self.permission_type)}"

    @classproperty
    def filter_name(self):
        return "group"


class GiftTagManager(models.Manager):
    def accessible_by(self, user):
        """Return all tags accessible by a user."""
        return self.filter(Q(is_public=True) | Q(shared_with=user))

    def root_tags_for_user(self, user):
        """Return all root tags accessible by a user."""
        return self.accessible_by(user).filter(parent_tags__isnull=True)

    def children_for_user(self, parent_tag, user):
        """Return all children tags of a tag accessible by a user."""
        return self.accessible_by(user).filter(parent_tags=parent_tag)


class GiftTag(models.Model):
    """Model for a gift tag."""

    tag_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.TextField(unique=False, null=False)
    parent_tags = models.ManyToManyField(
        "self", symmetrical=False, related_name="child_tags", blank=True
    )
    creation_date = models.DateTimeField(auto_now_add=True)
    is_public = models.BooleanField(default=False, help_text="If true, this tag is public.")
    shared_with = models.ManyToManyField(
        User, through="GiftTagPermission", related_name="%(app_label)s_%(class)s_shared_with"
    )

    # Custom manager
    objects = GiftTagManager()

    def __str__(self):
        return self.name

    def get_children(self):
        """Returns all direct child tags."""
        return self.child_tags.all()

    def get_descendants(self):
        """Returns all descendant tags (recursively)."""
        descendants = set()
        to_process = list(self.get_children())
        processed_ids = set()

        while to_process:
            current = to_process.pop(0)
            if current.pk in processed_ids:
                continue

            processed_ids.add(current.pk)
            descendants.add(current)
            to_process.extend(
                [child for child in current.get_children() if child.pk not in processed_ids]
            )

        return list(descendants)

    def get_ancestors(self):
        """Returns all parent tags (up to the root)."""
        ancestors = set()
        to_process = list(self.parent_tags.all())
        processed_ids = set()

        while to_process:
            current = to_process.pop(0)
            if current.pk in processed_ids:
                continue

            processed_ids.add(current.pk)
            ancestors.add(current)
            to_process.extend(
                [parent for parent in current.parent_tags.all() if parent.pk not in processed_ids]
            )

        return list(ancestors)

    def get_primary_ancestors_path(self):
        """Returns a specific path of ancestors (for breadcrumbs)."""
        # Arbitrarily choosing the first parent at each level
        ancestors = []
        current = self
        visited = {self.pk}

        while True:
            parents = current.parent_tags.all()
            if not parents:
                break

            # Take the first parent that doesn't create a cycle
            next_parent = None
            for parent in parents:
                if parent.pk not in visited:
                    next_parent = parent
                    visited.add(parent.pk)
                    break

            if not next_parent:
                break

            ancestors.append(next_parent)
            current = next_parent

        ancestors.reverse()
        return ancestors

    def has_cycle_with(self, potential_parent):
        """Checks if adding a parent would create a cycle."""
        if potential_parent == self:
            return True

        # Check if we are already an ancestor of the potential parent
        return self in potential_parent.get_ancestors()

    def get_all_gifts(self):
        """Returns all gifts associated with this tag and its descendants."""
        tags = [self, *self.get_descendants()]
        return Gift.objects.filter(tags__in=tags).distinct()

    def clean(self):
        """Custom validation to avoid cycles."""
        if self.pk:
            for parent in self.parent_tags.all():
                if self.has_cycle_with(parent):
                    raise ValidationError(
                        gettext_lazy(
                            "Adding this parent would create a cycle in the tag hierarchy."
                        )
                    )


class GiftTagPermission(models.Model):
    """Model for permissions on a gift tag."""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    gift_tag = models.ForeignKey(GiftTag, on_delete=models.CASCADE)
    permission_type = models.IntegerField(
        choices=PermissionLevel.CHOICES, default=PermissionLevel.VIEWER
    )

    class Meta:
        unique_together = ("user", "gift_tag")

    def __str__(self):
        return f"{self.user} - {self.gift_tag} -> {PermissionLevel.get_label(self.permission_type)}"

    @classproperty
    def filter_name(self):
        return "gift_tag"


class Gift(models.Model):
    """Model for a gift."""

    gift_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.TextField(unique=False, null=False)
    comment = models.TextField(unique=False, null=True, blank=True)
    tags = models.ManyToManyField(GiftTag, related_name="gifts", blank=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    shared_with = models.ManyToManyField(
        User, through="GiftPermission", related_name="%(app_label)s_%(class)s_shared_with"
    )

    # Custom manager
    objects = UserPermissionManager()

    class Meta:
        verbose_name = gettext_lazy("Gift")
        verbose_name_plural = gettext_lazy("Gifts")

    def __str__(self):
        return self.name


class GiftPermission(models.Model):
    """Model for permissions on a gift."""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    gift = models.ForeignKey(Gift, on_delete=models.CASCADE)
    permission_type = models.IntegerField(
        choices=PermissionLevel.CHOICES, default=PermissionLevel.VIEWER
    )

    class Meta:
        unique_together = ("user", "gift")

    def __str__(self):
        return f"{self.user} - {self.gift} -> {PermissionLevel.get_label(self.permission_type)}"

    @classproperty
    def filter_name(self):
        return "gift"


class Event(models.Model):
    """Model for an event."""

    event_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.TextField(unique=False, null=False)
    comment = models.TextField(unique=False, null=True, blank=True)
    usual_date = models.DateField(unique=False, null=True, blank=True)
    absolute_date = models.DateField(unique=False, null=True, blank=True)
    recurrence = models.CharField(
        max_length=20,
        choices=[
            ("daily", "Daily"),
            ("weekly", "Weekly"),
            ("monthly", "Monthly"),
            ("yearly", "Yearly"),
        ],
        null=True,
        blank=True,
    )
    creation_date = models.DateTimeField(auto_now_add=True)
    shared_with = models.ManyToManyField(
        User, through="EventPermission", related_name="%(app_label)s_%(class)s_shared_with"
    )

    # Custom manager
    objects = UserPermissionManager()

    class Meta:
        verbose_name = gettext_lazy("Event")
        verbose_name_plural = gettext_lazy("Events")

    def __str__(self):
        return self.name


class EventPermission(models.Model):
    """Model for permissions on an event."""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    permission_type = models.IntegerField(
        choices=PermissionLevel.CHOICES, default=PermissionLevel.VIEWER
    )

    class Meta:
        unique_together = ("user", "event")

    def __str__(self):
        return f"{self.user} - {self.event} -> {PermissionLevel.get_label(self.permission_type)}"

    @classproperty
    def filter_name(self):
        return "event"


class RelationStatus(models.Model):
    """Model for a relation status."""

    status = models.TextField(unique=True, null=False)

    class Meta:
        verbose_name = gettext_lazy("Relation Status")
        verbose_name_plural = gettext_lazy("Relation Statuses")

    def __str__(self):
        return self.status


class Relation(models.Model):
    """Model for a relation between a person and a gift."""

    relation_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    person = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name="persons", null=True, blank=True
    )
    group = models.ForeignKey(
        PersonGroup, on_delete=models.CASCADE, related_name="groups", null=True, blank=True
    )
    gift = models.ForeignKey(Gift, on_delete=models.CASCADE, related_name="gifts")
    event = models.ForeignKey(
        Event, on_delete=models.SET_NULL, related_name="relations", null=True, blank=True
    )
    status = models.ForeignKey(
        RelationStatus,
        on_delete=models.CASCADE,
        default="Idea",
    )
    due_date = models.DateField(unique=False, null=True, blank=True)
    comment = models.TextField(unique=False, null=True, blank=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    shared_with = models.ManyToManyField(
        User, through="RelationPermission", related_name="shared_relations"
    )

    # Custom manager
    objects = UserPermissionManager()

    class Meta:
        verbose_name = gettext_lazy("Relation")
        verbose_name_plural = gettext_lazy("Relations")

    def __str__(self):
        return f"{self.person} - {self.gift} ({self.status})"

    def save(self, *args, **kwargs):
        """Override save to ensure validation."""
        self.clean()
        super().save(*args, **kwargs)

    def clean(self):
        """Ensure that at least person or group is set."""
        if (self.person is None) == (self.group is None):
            raise ValidationError(
                gettext_lazy("Either a person or a group must be specified but not both.")
            )


class RelationPermission(models.Model):
    """Model for permissions on a relation."""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    relation = models.ForeignKey(Relation, on_delete=models.CASCADE)
    permission_type = models.IntegerField(
        choices=PermissionLevel.CHOICES, default=PermissionLevel.VIEWER
    )

    class Meta:
        unique_together = ("user", "relation")

    def __str__(self):
        return f"{self.user} - {self.relation} -> {PermissionLevel.get_label(self.permission_type)}"

    @classproperty
    def filter_name(self):
        return "relation"
