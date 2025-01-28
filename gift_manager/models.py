import datetime
import uuid

from django.contrib import admin
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User

PERMISSION_CHOICES = [
    ('editor', 'Editor'),
    ('viewer', 'Viewer'),
]

class Person(models.Model):
    """
    Model for a person.
    """
    person_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    first_name = models.TextField(unique=False, null=False)
    family_name = models.TextField(unique=False, null=True)
    email_address = models.EmailField(unique=False, null=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    groups = models.ManyToManyField("PersonGroup", secondary=group_relations, backref="persons")
    shared_with = models.ManyToManyField(User, through='PersonPermission', related_name='shared_persons')
    user_link = models.ForeignKey(User, on_delete=models.SET_NULL, related_name='persons', null=True)

    def __str__(self):
        return (self.first_name + " " + self.family_name).strip()


class PersonPermission(models.Model):
    """
    Model for permissions on a person.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    person = models.ForeignKey(Person, on_delete=models.CASCADE)
    permission_type = models.CharField(max_length=6, choices=PERMISSION_CHOICES)

    class Meta:
        unique_together = ('user', 'person')


class PersonGroup(models.Model):
    """
    Model for a group of persons.
    """
    group_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    group_name = models.TextField(unique=False, null=False)
    creation_date = models.DateTimeField(auto_now_add=True)
    shared_with = models.ManyToManyField(User, through='GroupPermission', related_name='shared_groups')


class PersonGroupPermission(models.Model):
    """
    Model for permissions on a group.
"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    group = models.ForeignKey(PersonGroup, on_delete=models.CASCADE)
    permission_type = models.CharField(max_length=6, choices=PERMISSION_CHOICES)

    class Meta:
        unique_together = ('user', 'group')


class PersonsGroupRelation(models.Model):
    """
    Relation between a person and a group.
    """
    person = models.ForeignKey(Person, on_delete=models.CASCADE)
    group = models.ForeignKey(PersonGroup, on_delete=models.CASCADE)
    creation_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('person', 'group')


class GiftTag(models.Model):
    """
    Model for a gift tag.
    """
    tag_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tag_name = models.TextField(unique=False, null=False)
    parent_tag = models.ForeignKey("GiftTag", on_delete=models.CASCADE, null=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    shared_with = models.ManyToManyField(User, through='GiftTagPermission', related_name='shared_gift_tags')


class GiftTagPermission(models.Model):
    """
    Model for permissions on a gift tag.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    gift_tag = models.ForeignKey(GiftTag, on_delete=models.CASCADE)
    permission_type = models.CharField(max_length=6, choices=PERMISSION_CHOICES)

    class Meta:
        unique_together = ('user', 'gift_tag')


class Gift(models.Model):
    """
    Model for a gift.
    """
    gift_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.TextField(unique=False, null=False)
    comment = models.TextField(unique=False, null=True)
    tags = models.ManyToManyField(GiftTag, related_name="gifts")
    creation_date = models.DateTimeField(auto_now_add=True)
    shared_with = models.ManyToManyField(User, through='GiftPermission', related_name='shared_gifts')


class GiftPermission(models.Model):
    """
    Model for permissions on a gift.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    gift = models.ForeignKey(Gift, on_delete=models.CASCADE)
    permission_type = models.CharField(max_length=6, choices=PERMISSION_CHOICES)

    class Meta:
        unique_together = ('user', 'gift')


class Event(models.Model):
    """
    Model for an event.
    """
    event_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.TextField(unique=False, null=False)
    comment = models.TextField(unique=False, null=True)
    usual_date = models.DateField(unique=False, null=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    shared_with = models.ManyToManyField(User, through='EventPermission', related_name='shared_events')


class EventPermission(models.Model):
    """
    Model for permissions on an event.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    permission_type = models.CharField(max_length=6, choices=PERMISSION_CHOICES)

    class Meta:
        unique_together = ('user', 'event')


class RelationStatus(models.Model):
    """
    Model for a relation status.
    """
    status = models.TextField(unique=True, null=False)


class Relation(models.Model):
    """
    Model for a relation.
    """
    relation_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="related_person")
    gift = models.ForeignKey(Gift, on_delete=models.CASCADE, related_name="related_gift")
    status = models.ForeignKey(RelationStatus, on_delete=models.CASCADE)  # Add default value after the status model is created
    due_date = models.DateField(unique=False, null=True)
    comment = models.TextField(unique=False, null=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    shared_with = models.ManyToManyField(User, through='RelationPermission', related_name='shared_relations')


class RelationPermission(models.Model):
    """
    Model for permissions on a relation.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    relation = models.ForeignKey(Relation, on_delete=models.CASCADE)
    permission_type = models.CharField(max_length=6, choices=PERMISSION_CHOICES)

    class Meta:
        unique_together = ('user', 'relation')
