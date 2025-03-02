import uuid

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.translation import gettext_lazy


class PermissionLevel:
    NONE = 0
    VIEWER = 10
    EDITOR = 20
    OWNER = 30

    CHOICES = [(NONE, "none"), (VIEWER, "viewer"), (EDITOR, "editor"), (OWNER, "owner")]

    CHOICES_DICT = {"none": NONE, "viewer": VIEWER, "editor": EDITOR, "owner": OWNER}


class Profile(models.Model):
    """Model for a user profile."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    friends = models.ManyToManyField("self", symmetrical=True, blank=True)

    def __str__(self):
        return f"{gettext_lazy('Profile of')} {self.user.username}"


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):  # noqa: ARG001
    if created:
        Profile.objects.create(user=instance)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def save_user_profile(sender, instance, **kwargs):  # noqa: ARG001
    if hasattr(instance, "profile"):
        instance.profile.save()
    else:
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

    class Meta:
        verbose_name = gettext_lazy("Person")
        verbose_name_plural = gettext_lazy("Persons")

    def __str__(self):
        return (self.first_name + " " + self.family_name).strip()


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
        return f"{self.user} - {self.group} -> {self.permission_type}"


class GiftTag(models.Model):
    """Model for a gift tag."""

    tag_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.TextField(unique=False, null=False)
    parent_tag = models.ForeignKey("GiftTag", on_delete=models.CASCADE, null=True, blank=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    shared_with = models.ManyToManyField(
        User, through="GiftTagPermission", related_name="%(app_label)s_%(class)s_shared_with"
    )

    def __str__(self):
        return self.name


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
    permission_type = models.IntegerField(
        choices=PermissionLevel.CHOICES, default=PermissionLevel.VIEWER
    )

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
    permission_type = models.IntegerField(
        choices=PermissionLevel.CHOICES, default=PermissionLevel.VIEWER
    )

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

    class Meta:
        verbose_name = gettext_lazy("Relation")
        verbose_name_plural = gettext_lazy("Relations")

    def __str__(self):
        return f"{self.person} - {self.gift} ({self.status})"


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
        return f"{self.user} - {self.relation} -> {self.permission_type}"
