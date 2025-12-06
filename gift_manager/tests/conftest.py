"""Pytest configuration and fixtures for Gift Manager tests.

This module provides pytest fixtures for testing. It uses factory_boy for
creating test data, which provides more flexibility than static fixtures.

Usage:
    def test_something(user, person, gift):
        # user, person, gift are already created
        assert person.first_name is not None
"""

from datetime import date

import pytest
from django.contrib.auth.models import User
from django.test import Client

from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import GiftTag
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import Relation
from gift_manager.models import RelationStatus

# Import factories for convenient access
from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import GiftTagFactory
from gift_manager.tests.factories import GroupRelationFactory
from gift_manager.tests.factories import InvitationFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import RelationStatusFactory
from gift_manager.tests.factories import UserFactory


# =============================================================================
# User Fixtures
# =============================================================================


@pytest.fixture
def username():
    """Create a test username."""
    return "testuser"


@pytest.fixture
def userpassword():
    """Create a test user password."""
    return "password123"


@pytest.fixture
def user_email():
    """Create a test user email."""
    return "user@example.com"


@pytest.fixture
def user(username, userpassword, user_email):
    """Create a test user."""
    return User.objects.create_user(username=username, password=userpassword, email=user_email)


@pytest.fixture
def user_factory():
    """Return the UserFactory for creating users in tests."""
    return UserFactory


@pytest.fixture
def authenticated_client(user, userpassword):
    """Return an authenticated test client."""
    client = Client()
    client.login(username=user.username, password=userpassword)
    return client


# =============================================================================
# Person Fixtures
# =============================================================================


@pytest.fixture
def person_first_name():
    """Create a test person first name."""
    return "John"


@pytest.fixture
def person_family_name():
    """Create a test person family name."""
    return "Doe"


@pytest.fixture
def person(person_first_name, person_family_name):
    """Create a test person."""
    return Person.objects.create(first_name=person_first_name, family_name=person_family_name)


@pytest.fixture
def person_factory():
    """Return the PersonFactory for creating persons in tests."""
    return PersonFactory


# =============================================================================
# Group Fixtures
# =============================================================================


@pytest.fixture
def group_name():
    """Create a test person group name."""
    return "Family"


@pytest.fixture
def group(group_name):
    """Create a test person group."""
    return PersonGroup.objects.create(name=group_name)


@pytest.fixture
def group_factory():
    """Return the PersonGroupFactory for creating groups in tests."""
    return PersonGroupFactory


# =============================================================================
# Gift Fixtures
# =============================================================================


@pytest.fixture
def gift_tag_name():
    """Create a test gift tag name."""
    return "Electronics"


@pytest.fixture
def gift_tag(gift_tag_name):
    """Create a test gift tag."""
    return GiftTag.objects.create(name=gift_tag_name)


@pytest.fixture
def gift_tag_factory():
    """Return the GiftTagFactory for creating gift tags in tests."""
    return GiftTagFactory


@pytest.fixture
def gift_name():
    """Create a test gift name."""
    return "Smartphone"


@pytest.fixture
def gift_comment():
    """Create a test gift comment."""
    return "Latest model"


@pytest.fixture
def gift(gift_name, gift_comment):
    """Create a test gift."""
    return Gift.objects.create(name=gift_name, comment=gift_comment)


@pytest.fixture
def gift_factory():
    """Return the GiftFactory for creating gifts in tests."""
    return GiftFactory


# =============================================================================
# Event Fixtures
# =============================================================================


@pytest.fixture
def event_name():
    """Create a test event name."""
    return "Birthday"


@pytest.fixture
def event_comment():
    """Create a test event comment."""
    return "Annual celebration"


@pytest.fixture
def event_usual_date():
    """Create a test event usual date."""
    return date(2000, 5, 15)


@pytest.fixture
def event_recurrence():
    """Create a test event recurrence."""
    return "yearly"


@pytest.fixture
def event(event_name, event_comment, event_usual_date, event_recurrence):
    """Create a test event."""
    return Event.objects.create(
        name=event_name,
        comment=event_comment,
        usual_date=event_usual_date,
        recurrence=event_recurrence,
    )


@pytest.fixture
def event_factory():
    """Return the EventFactory for creating events in tests."""
    return EventFactory


# =============================================================================
# Relation Fixtures
# =============================================================================


@pytest.fixture
def status():
    """Create a test relation status."""
    return RelationStatus.objects.create(status="Idea")


@pytest.fixture
def status_factory():
    """Return the RelationStatusFactory for creating statuses in tests."""
    return RelationStatusFactory


@pytest.fixture
def person_relation(person, gift, status):
    """Create a test relation for a person."""
    return Relation.objects.create(person=person, gift=gift, status=status)


@pytest.fixture
def group_relation(group, gift, status):
    """Create a test relation for a group."""
    return Relation.objects.create(group=group, gift=gift, status=status)


@pytest.fixture
def relation_factory():
    """Return the RelationFactory for creating relations in tests."""
    return RelationFactory


@pytest.fixture
def group_relation_factory():
    """Return the GroupRelationFactory for creating group relations in tests."""
    return GroupRelationFactory


# =============================================================================
# Invitation Fixtures
# =============================================================================


@pytest.fixture
def invitation_factory():
    """Return the InvitationFactory for creating invitations in tests."""
    return InvitationFactory


# =============================================================================
# Parametrized Fixtures
# =============================================================================


@pytest.fixture
def db_obj(request, person, gift, event, group, person_relation):
    """Return a database object based on the request parameter.

    Usage:
        @pytest.mark.parametrize("db_obj", ["person", "gift"], indirect=True)
        def test_something(db_obj):
            ...
    """
    if isinstance(request.param, (list | tuple)):
        obj_type = str(request.param[0]).lower()
    else:
        obj_type = str(request.param).lower()
    return {
        "person": person,
        "gift": gift,
        "event": event,
        "persongroup": group,
        "relation": person_relation,
    }[obj_type]
