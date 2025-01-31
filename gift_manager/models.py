import uuid

from django.contrib.auth.models import User
from django.db import models
from django.utils.translation import gettext_lazy

PERMISSION_CHOICES = [
    ("editor", "Editor"),
    ("viewer", "Viewer"),
]


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
        User, on_delete=models.SET_NULL, related_name="persons", null=True, blank=True
    )

    class Meta:
        verbose_name = gettext_lazy("Person")
        verbose_name_plural = gettext_lazy("Persons")

    def __str__(self):
        return (self.first_name + " " + self.family_name).strip()


class PersonPermission(models.Model):
    """Model for permissions on a person."""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    person = models.ForeignKey(Person, on_delete=models.CASCADE)
    permission_type = models.CharField(max_length=6, choices=PERMISSION_CHOICES)

    class Meta:
        unique_together = ("user", "person")

    def __str__(self):
        return f"{self.user} - {self.person} -> {self.permission_type}"


class PersonGroup(models.Model):
    """Model for a group of persons."""

    group_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.TextField(unique=False, null=False)
    creation_date = models.DateTimeField(auto_now_add=True)
    shared_with = models.ManyToManyField(
        User, through="PersonGroupPermission", related_name="%(app_label)s_%(class)s_shared_with"
    )

    class Meta:
        verbose_name = gettext_lazy("Group")
        verbose_name_plural = gettext_lazy("Groups")

    def __str__(self):
        return self.name


class PersonGroupPermission(models.Model):
    """Model for permissions on a group."""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    group = models.ForeignKey(PersonGroup, on_delete=models.CASCADE)
    permission_type = models.CharField(max_length=6, choices=PERMISSION_CHOICES)

    class Meta:
        unique_together = ("user", "group")

    def __str__(self):
        return f"{self.user} - {self.group} -> {self.permission_type}"


class GiftTag(models.Model):
    """Model for a gift tag."""

    tag_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.TextField(unique=False, null=False)
    parent_tag = models.ForeignKey("GiftTag", on_delete=models.CASCADE, null=True, blank=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    shared_with = models.ManyToManyField(
        User, through="GiftTagPermission", related_name="shared_gift_tags"
    )

    def __str__(self):
        return self.name


class GiftTagPermission(models.Model):
    """Model for permissions on a gift tag."""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    gift_tag = models.ForeignKey(GiftTag, on_delete=models.CASCADE)
    permission_type = models.CharField(max_length=6, choices=PERMISSION_CHOICES)

    class Meta:
        unique_together = ("user", "gift_tag")

    def __str__(self):
        return f"{self.user} - {self.gift_tag} -> {self.permission_type}"


class Gift(models.Model):
    """Model for a gift."""

    gift_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.TextField(unique=False, null=False)
    comment = models.TextField(unique=False, null=True, blank=True)
    tags = models.ManyToManyField(GiftTag, related_name="gifts")
    creation_date = models.DateTimeField(auto_now_add=True)
    shared_with = models.ManyToManyField(
        User, through="GiftPermission", related_name="%(app_label)s_%(class)s_shared_with"
    )

    class Meta:
        verbose_name = gettext_lazy("Gift")
        verbose_name_plural = gettext_lazy("Gifts")

    def __str__(self):
        return self.name


class GiftPermission(models.Model):
    """Model for permissions on a gift."""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    gift = models.ForeignKey(Gift, on_delete=models.CASCADE)
    permission_type = models.CharField(max_length=6, choices=PERMISSION_CHOICES)

    class Meta:
        unique_together = ("user", "gift")

    def __str__(self):
        return f"{self.user} - {self.gift} -> {self.permission_type}"


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

    class Meta:
        verbose_name = gettext_lazy("Event")
        verbose_name_plural = gettext_lazy("Events")

    def __str__(self):
        return self.name


class EventPermission(models.Model):
    """Model for permissions on an event."""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    permission_type = models.CharField(max_length=6, choices=PERMISSION_CHOICES)

    class Meta:
        unique_together = ("user", "event")

    def __str__(self):
        return f"{self.user} - {self.event} -> {self.permission_type}"


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
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="persons")
    gift = models.ForeignKey(Gift, on_delete=models.CASCADE, related_name="gifts")
    event = models.ForeignKey(
        Event, on_delete=models.SET_NULL, related_name="relations", null=True, blank=True
    )
    status = models.ForeignKey(
        RelationStatus, on_delete=models.CASCADE
    )  # Add default value after the status model is created and populated
    due_date = models.DateField(unique=False, null=True, blank=True)
    comment = models.TextField(unique=False, null=True, blank=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    shared_with = models.ManyToManyField(
        User, through="RelationPermission", related_name="shared_relations"
    )

    class Meta:
        verbose_name = gettext_lazy("Relation")
        verbose_name_plural = gettext_lazy("Relations")

    def __str__(self):
        return f"{self.person} - {self.gift} ({self.status})"


class RelationPermission(models.Model):
    """Model for permissions on a relation."""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    relation = models.ForeignKey(Relation, on_delete=models.CASCADE)
    permission_type = models.CharField(max_length=6, choices=PERMISSION_CHOICES)

    class Meta:
        unique_together = ("user", "relation")

    def __str__(self):
        return f"{self.user} - {self.relation} -> {self.permission_type}"
