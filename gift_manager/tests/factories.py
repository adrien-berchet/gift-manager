"""Factory Boy factories for creating test data.

This module provides factory classes for creating model instances in tests.
Using factories instead of fixtures provides more flexibility and clearer tests.

Usage:
    from gift_manager.tests.factories import PersonFactory, GiftFactory

    # Create a single instance
    person = PersonFactory()

    # Create with specific attributes
    person = PersonFactory(first_name="John", family_name="Doe")

    # Create multiple instances
    persons = PersonFactory.create_batch(5)

    # Build without saving to database
    person = PersonFactory.build()
"""

from datetime import date
from datetime import timedelta

import factory
from django.contrib.auth.models import User
from factory.django import DjangoModelFactory

from gift_manager.email_encoding import encode_email
from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import GiftTag
from gift_manager.models import Invitation
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import Relation
from gift_manager.models import RelationStatus


class UserFactory(DjangoModelFactory):
    """Factory for creating User instances."""

    class Meta:
        model = User
        skip_postgeneration_save = True

    username = factory.Sequence(lambda n: f"user{n}")
    # Email is stored encoded for privacy
    email = factory.LazyAttribute(lambda obj: encode_email(f"{obj.username}@example.com"))
    password = factory.PostGenerationMethodCall("set_password", "testpass123")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    is_active = True

    @classmethod
    def _after_postgeneration(cls, instance, create, results=None):
        """Save the instance after post-generation hooks."""
        if create:
            instance.save()


class PersonFactory(DjangoModelFactory):
    """Factory for creating Person instances."""

    class Meta:
        model = Person

    first_name = factory.Faker("first_name")
    family_name = factory.Faker("last_name")
    # Email is stored encoded for privacy
    email_address = factory.LazyAttribute(
        lambda obj: encode_email(f"{obj.first_name.lower()}.{obj.family_name.lower()}@example.com")
    )

    @factory.post_generation
    def groups(self, create, extracted, **kwargs):
        """Handle ManyToMany relationship with groups."""
        if not create or not extracted:
            return
        self.groups.add(*extracted)

    @factory.post_generation
    def shared_with(self, create, extracted, **kwargs):
        """Handle ManyToMany relationship with shared_with users."""
        if not create or not extracted:
            return
        for user in extracted:
            from gift_manager.models import PermissionLevel
            from gift_manager.models import PersonPermission

            PersonPermission.objects.create(
                user=user, person=self, permission_type=PermissionLevel.VIEWER
            )


class PersonGroupFactory(DjangoModelFactory):
    """Factory for creating PersonGroup instances."""

    class Meta:
        model = PersonGroup

    name = factory.Sequence(lambda n: f"Group {n}")

    @factory.post_generation
    def shared_with(self, create, extracted, **kwargs):
        """Handle ManyToMany relationship with shared_with users."""
        if not create or not extracted:
            return
        for user in extracted:
            from gift_manager.models import PermissionLevel
            from gift_manager.models import PersonGroupPermission

            PersonGroupPermission.objects.create(
                user=user, group=self, permission_type=PermissionLevel.VIEWER
            )


class GiftTagFactory(DjangoModelFactory):
    """Factory for creating GiftTag instances."""

    class Meta:
        model = GiftTag

    name = factory.Sequence(lambda n: f"Tag {n}")
    is_public = False

    @factory.post_generation
    def parent_tags(self, create, extracted, **kwargs):
        """Handle ManyToMany relationship with parent_tags."""
        if not create or not extracted:
            return
        self.parent_tags.add(*extracted)

    @factory.post_generation
    def shared_with(self, create, extracted, **kwargs):
        """Handle ManyToMany relationship with shared_with users."""
        if not create or not extracted:
            return
        for user in extracted:
            from gift_manager.models import GiftTagPermission
            from gift_manager.models import PermissionLevel

            GiftTagPermission.objects.create(
                user=user, gift_tag=self, permission_type=PermissionLevel.VIEWER
            )


class GiftFactory(DjangoModelFactory):
    """Factory for creating Gift instances."""

    class Meta:
        model = Gift

    name = factory.Sequence(lambda n: f"Gift {n}")
    comment = factory.Faker("sentence")

    @factory.post_generation
    def tags(self, create, extracted, **kwargs):
        """Handle ManyToMany relationship with tags."""
        if not create or not extracted:
            return
        self.tags.add(*extracted)

    @factory.post_generation
    def shared_with(self, create, extracted, **kwargs):
        """Handle ManyToMany relationship with shared_with users."""
        if not create or not extracted:
            return
        for user in extracted:
            from gift_manager.models import GiftPermission
            from gift_manager.models import PermissionLevel

            GiftPermission.objects.create(
                user=user, gift=self, permission_type=PermissionLevel.VIEWER
            )


class EventFactory(DjangoModelFactory):
    """Factory for creating Event instances."""

    class Meta:
        model = Event

    name = factory.Sequence(lambda n: f"Event {n}")
    comment = factory.Faker("sentence")
    usual_date = factory.LazyFunction(lambda: date.today() + timedelta(days=30))
    recurrence = "yearly"

    @factory.post_generation
    def shared_with(self, create, extracted, **kwargs):
        """Handle ManyToMany relationship with shared_with users."""
        if not create or not extracted:
            return
        for user in extracted:
            from gift_manager.models import EventPermission
            from gift_manager.models import PermissionLevel

            EventPermission.objects.create(
                user=user, event=self, permission_type=PermissionLevel.VIEWER
            )


class RelationStatusFactory(DjangoModelFactory):
    """Factory for creating RelationStatus instances."""

    class Meta:
        model = RelationStatus
        django_get_or_create = ("status",)

    status = factory.Iterator(["Idea", "Planned", "Purchased", "Given"])


class RelationFactory(DjangoModelFactory):
    """Factory for creating Relation instances."""

    class Meta:
        model = Relation

    person = factory.SubFactory(PersonFactory)
    group = None
    gift = factory.SubFactory(GiftFactory)
    event = factory.SubFactory(EventFactory)
    status = factory.SubFactory(RelationStatusFactory, status="Idea")
    comment = factory.Faker("sentence")
    due_date = factory.LazyFunction(lambda: date.today() + timedelta(days=30))

    @factory.post_generation
    def shared_with(self, create, extracted, **kwargs):
        """Handle ManyToMany relationship with shared_with users."""
        if not create or not extracted:
            return
        for user in extracted:
            from gift_manager.models import PermissionLevel
            from gift_manager.models import RelationPermission

            RelationPermission.objects.create(
                user=user, relation=self, permission_type=PermissionLevel.VIEWER
            )


class GroupRelationFactory(RelationFactory):
    """Factory for creating Relation instances for groups (not persons)."""

    person = None
    group = factory.SubFactory(PersonGroupFactory)


class InvitationFactory(DjangoModelFactory):
    """Factory for creating Invitation instances."""

    class Meta:
        model = Invitation

    sender = factory.SubFactory(UserFactory)
    # Email is stored encrypted for privacy
    recipient_email = factory.LazyAttribute(
        lambda obj: encode_email(f"recipient{obj.sender.username}@example.com")
    )
    accepted = False
