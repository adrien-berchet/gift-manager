"""Deterministic seed data for integration tests and development.

Provides a ``create_seed_data()`` function that populates a small, consistent
dataset covering all model relationships, permissions, hierarchies and
encrypted emails.  Callable from both pytest fixtures and the
``seed_data`` management command.

Design decisions
~~~~~~~~~~~~~~~~
* **Direct ORM calls** - no factories / Faker so the dataset is fully
  deterministic and readable.
* **Returns a frozen ``SeedData`` dataclass** - type-safe, immutable,
  IDE-friendly attribute access (``data.alice``, ``data.persons["mom"]``).
* **UUIDs auto-generated** - tests reference objects via the dataclass,
  never by UUID.
* **Not idempotent** - assumes a clean database.  Pytest provides per-test
  isolation; the management command has a ``--flush`` flag.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from datetime import date

from allauth.account.models import EmailAddress
from django.contrib.auth.models import User

from gift_manager.email_encoding import encode_email
from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import GiftTag
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import PersonGroupPermission
from gift_manager.models import Relation
from gift_manager.models import RelationStatus
from gift_manager.permissions import create_or_update_permission


@dataclass(frozen=True)
class SeedData:
    """Container for all seed-data objects.

    Every attribute is populated by :func:`create_seed_data`.
    """

    alice: User
    bob: User
    statuses: dict[str, RelationStatus] = field(default_factory=dict)
    groups: dict[str, PersonGroup] = field(default_factory=dict)
    persons: dict[str, Person] = field(default_factory=dict)
    tags: dict[str, GiftTag] = field(default_factory=dict)
    gifts: dict[str, Gift] = field(default_factory=dict)
    events: dict[str, Event] = field(default_factory=dict)
    relations: list[Relation] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _grant_owner_all(user: User, objects: list) -> None:
    """Assign OWNER permission on every object in *objects* to *user*."""
    for obj in objects:
        create_or_update_permission(user, obj, permission_level=PermissionLevel.OWNER)


# ---------------------------------------------------------------------------
# Main entry-point
# ---------------------------------------------------------------------------


def create_seed_data() -> SeedData:  # noqa: PLR0915
    """Create a deterministic seed dataset and return a :class:`SeedData` instance.

    The dataset contains **34 objects** exercising every model, relationship,
    hierarchy, permission level and encrypted-email feature of the application.
    """
    # ------------------------------------------------------------------
    # 1. Users
    # ------------------------------------------------------------------
    alice = User.objects.create_user(
        username="alice",
        password="alice_password",
        email=encode_email("alice@example.com"),
        first_name="Alice",
        last_name="Seed",
    )
    bob = User.objects.create_user(
        username="bob",
        password="bob_password",
        email=encode_email("bob@example.com"),
        first_name="Bob",
        last_name="Seed",
    )

    # Ensure a superuser exists (skip if already present).
    if not User.objects.filter(username="testuser").exists():
        testuser = User.objects.create_superuser(
            username="testuser",
            password="testpass123",
            email=encode_email("testuser@example.com"),
        )
    else:
        testuser = User.objects.get(username="testuser")

    # Make testuser friends with alice and bob.
    testuser.profile.friends.add(alice.profile, bob.profile)

    # Mark all user emails as verified for allauth.
    for user_obj, plain_email in [
        (alice, "alice@example.com"),
        (bob, "bob@example.com"),
        (testuser, "testuser@example.com"),
    ]:
        EmailAddress.objects.get_or_create(
            user=user_obj,
            email=plain_email,
            defaults={"verified": True, "primary": True},
        )

    # ------------------------------------------------------------------
    # 2. Relation statuses (with fr translations)
    # ------------------------------------------------------------------
    statuses: dict[str, RelationStatus] = {}
    for status_en, status_fr in [
        ("Idea", "Idée"),
        ("Planned", "Planifié"),
        ("Purchased", "Acheté"),
        ("Abandoned", "Abandonné"),
        ("Given", "Offert"),
    ]:
        obj = (
            RelationStatus.objects.filter(status_en=status_en).first()
            or RelationStatus.objects.filter(status=status_en).first()
            or RelationStatus()
        )
        # Also set the base ``status`` field to the English value so that
        # look-ups via ``RelationStatus.objects.get(status=…)`` work
        # regardless of the active language.
        obj.status_en = status_en
        obj.status_fr = status_fr
        obj.status = status_en
        obj.save()
        statuses[status_en.lower()] = obj

    # ------------------------------------------------------------------
    # 3. Person groups (with hierarchy)
    # ------------------------------------------------------------------
    family = PersonGroup.objects.create(name="Family")
    close_family = PersonGroup.objects.create(name="Close Family")
    close_family.parent_groups.add(family)  # Close Family → child of Family
    friends = PersonGroup.objects.create(name="Friends")

    groups: dict[str, PersonGroup] = {
        "family": family,
        "close_family": close_family,
        "friends": friends,
    }

    # ------------------------------------------------------------------
    # 4. Persons (+ group memberships + encrypted emails)
    # ------------------------------------------------------------------
    mom = Person.objects.create(
        first_name="Mom",
        family_name="Seed",
        email_address=encode_email("mom@example.com"),
    )
    mom.groups.add(family, close_family)

    dad = Person.objects.create(
        first_name="Dad",
        family_name="Seed",
        email_address=encode_email("dad@example.com"),
    )
    dad.groups.add(family, close_family)

    sister = Person.objects.create(
        first_name="Sister",
        family_name="Seed",
        email_address=encode_email("sister@example.com"),
    )
    sister.groups.add(family)

    best_friend = Person.objects.create(
        first_name="Best Friend",
        family_name="Pal",
        email_address=encode_email("bestfriend@example.com"),
    )
    best_friend.groups.add(friends)

    colleague = Person.objects.create(
        first_name="Colleague",
        family_name="Work",
        # No email - intentionally left blank.
    )

    persons: dict[str, Person] = {
        "mom": mom,
        "dad": dad,
        "sister": sister,
        "best_friend": best_friend,
        "colleague": colleague,
    }

    # ------------------------------------------------------------------
    # 5. Gift tags (with hierarchy)
    # ------------------------------------------------------------------
    electronics = GiftTag.objects.create(name="Electronics")
    gadgets = GiftTag.objects.create(name="Gadgets")
    gadgets.parent_tags.add(electronics)  # Gadgets → child of Electronics
    books = GiftTag.objects.create(name="Books", is_public=True)

    tags: dict[str, GiftTag] = {
        "electronics": electronics,
        "gadgets": gadgets,
        "books": books,
    }

    # ------------------------------------------------------------------
    # 6. Gifts (+ tag M2M)
    # ------------------------------------------------------------------
    smartphone = Gift.objects.create(name="Smartphone", comment="Latest model")
    smartphone.tags.add(electronics, gadgets)

    novel = Gift.objects.create(name="Novel", comment="Classic literature")
    novel.tags.add(books)

    watch = Gift.objects.create(name="Watch", comment="Luxury brand")
    watch.tags.add(gadgets)

    scarf = Gift.objects.create(name="Scarf", comment="Hand-knitted")
    # No tags for scarf - intentionally left empty.

    gifts: dict[str, Gift] = {
        "smartphone": smartphone,
        "novel": novel,
        "watch": watch,
        "scarf": scarf,
    }

    # ------------------------------------------------------------------
    # 7. Events
    # ------------------------------------------------------------------
    christmas = Event.objects.create(
        name="Christmas",
        comment="Annual holiday",
        usual_date=date(2000, 12, 25),
        recurrence="yearly",
    )
    mom_birthday = Event.objects.create(
        name="Mom Birthday",
        comment="Mom's special day",
        usual_date=date(2000, 3, 15),
        recurrence="yearly",
    )
    graduation = Event.objects.create(
        name="Graduation",
        comment="University graduation",
        absolute_date=date(2026, 6, 15),
    )

    events: dict[str, Event] = {
        "christmas": christmas,
        "mom_birthday": mom_birthday,
        "graduation": graduation,
    }

    # ------------------------------------------------------------------
    # 8. Relations
    # ------------------------------------------------------------------
    relation_0 = Relation.objects.create(
        person=mom,
        gift=smartphone,
        event=christmas,
        status=statuses["idea"],
    )
    relation_1 = Relation.objects.create(
        person=dad,
        gift=novel,
        event=mom_birthday,
        status=statuses["planned"],
    )
    relation_2 = Relation.objects.create(
        person=best_friend,
        gift=watch,
        event=graduation,
        status=statuses["purchased"],
    )
    # Group relation - person is None, group is set.
    relation_3 = Relation.objects.create(
        group=family,
        gift=scarf,
        event=christmas,
        status=statuses["given"],
    )

    relations: list[Relation] = [relation_0, relation_1, relation_2, relation_3]

    # ------------------------------------------------------------------
    # 9. Permissions - alice OWNER on everything
    # ------------------------------------------------------------------
    all_objects: list = [
        *groups.values(),
        *persons.values(),
        *tags.values(),
        *gifts.values(),
        *events.values(),
        *relations,
    ]
    _grant_owner_all(alice, all_objects)

    # Set inherit_permissions on alice's Family group permission.
    PersonGroupPermission.objects.filter(user=alice, group=family).update(
        inherit_permissions=True,
    )

    # ------------------------------------------------------------------
    # 10. Permissions - bob mixed access (see permission matrix)
    # ------------------------------------------------------------------
    # Groups
    create_or_update_permission(bob, family, permission_level=PermissionLevel.VIEWER)
    # close_family: NONE (no permission row)
    create_or_update_permission(bob, friends, permission_level=PermissionLevel.EDITOR)

    # Persons
    create_or_update_permission(bob, mom, permission_level=PermissionLevel.VIEWER)
    create_or_update_permission(bob, dad, permission_level=PermissionLevel.VIEWER)
    # sister: NONE
    create_or_update_permission(bob, best_friend, permission_level=PermissionLevel.EDITOR)
    # colleague: NONE

    # Tags
    create_or_update_permission(bob, electronics, permission_level=PermissionLevel.VIEWER)
    # gadgets: NONE
    create_or_update_permission(bob, books, permission_level=PermissionLevel.EDITOR)

    # Gifts
    create_or_update_permission(bob, smartphone, permission_level=PermissionLevel.VIEWER)
    create_or_update_permission(bob, novel, permission_level=PermissionLevel.VIEWER)
    create_or_update_permission(bob, watch, permission_level=PermissionLevel.EDITOR)
    # scarf: NONE

    # Events
    create_or_update_permission(bob, christmas, permission_level=PermissionLevel.VIEWER)
    # mom_birthday: NONE
    create_or_update_permission(bob, graduation, permission_level=PermissionLevel.EDITOR)

    # Relations
    create_or_update_permission(bob, relation_0, permission_level=PermissionLevel.VIEWER)
    # relation_1: NONE
    create_or_update_permission(bob, relation_2, permission_level=PermissionLevel.EDITOR)
    # relation_3: NONE

    # ------------------------------------------------------------------
    # Done - return frozen dataclass
    # ------------------------------------------------------------------
    return SeedData(
        alice=alice,
        bob=bob,
        statuses=statuses,
        groups=groups,
        persons=persons,
        tags=tags,
        gifts=gifts,
        events=events,
        relations=relations,
    )
