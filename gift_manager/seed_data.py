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
from datetime import timedelta
from decimal import Decimal

from allauth.account.models import EmailAddress
from django.contrib.auth.models import User
from django.utils import timezone

from gift_manager import account_links
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
from gift_manager.models import Wish
from gift_manager.models import WishPriority
from gift_manager.permissions import create_or_update_permission


@dataclass(frozen=True)
class AccountLinkSeed:
    household: PersonGroup
    alice_record: Person
    self_record: Person


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
    wishes: dict[str, Wish] = field(default_factory=dict)


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

    The dataset contains **36 objects** exercising every model, relationship,
    hierarchy, permission level, encrypted-email and wishlist/preference feature of the application.
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

    # Set Alice's gift preferences and avoid notes
    alice.profile.preferences_notes = "Shoe size 39, favorite color blue, loves green tea."
    alice.profile.avoid_notes = "Peanut allergy, dislikes polyester clothing."
    alice.profile.ai_share_self_profile = True
    alice.profile.save()

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
    # Birthdays relative to today so the dashboard "Upcoming birthdays" section is populated.
    today = timezone.localdate()
    mom_birthday_date = today + timedelta(days=5)
    sister_birthday_date = today + timedelta(days=21)

    mom = Person.objects.create(
        first_name="Mom",
        family_name="Seed",
        email_address=encode_email("mom@example.com"),
        birthday_day=mom_birthday_date.day,
        birthday_month=mom_birthday_date.month,
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
        birthday_day=sister_birthday_date.day,
        birthday_month=sister_birthday_date.month,
        birthday_year=1992,
    )
    sister.groups.add(family)

    best_friend = Person.objects.create(
        first_name="Best Friend",
        family_name="Pal",
        email_address=encode_email("bestfriend@example.com"),
        # Leap-day birthday: celebrated on February 28 in non-leap years.
        birthday_day=29,
        birthday_month=2,
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
    alice.profile.public_interests.add(books)

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
        schedule_type=Event.ScheduleType.RECURRING,
        date=date(2000, 12, 25),
        recurrence="yearly",
    )
    mom_birthday = Event.objects.create(
        name="Mom Birthday",
        comment="Mom's special day",
        schedule_type=Event.ScheduleType.RECURRING,
        date=date(2000, 3, 15),
        recurrence="yearly",
    )
    graduation = Event.objects.create(
        name="Graduation",
        comment="University graduation",
        schedule_type=Event.ScheduleType.ONE_TIME,
        date=date(2026, 6, 15),
    )

    # The global Birthday event is normally provisioned by a migration; make sure it exists
    # (it is wiped by database flushes) so every user deterministically sees it.
    Event.objects.get_birthday_event()

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
        reaction_rating=5,
        reaction_note="Everyone loved it.",
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
    # 11. Wishes (Alice's wishlist)
    # ------------------------------------------------------------------
    teapot = Wish.objects.create(
        wisher=alice,
        title="Ceramic Teapot",
        url="https://example.com/teapot",
        price_hint=Decimal("45.00"),
        priority=WishPriority.MEDIUM,
        notes="Japanese Kyusu teapot, glazed ceramic.",
    )
    fountain_pen = Wish.objects.create(
        wisher=alice,
        title="Fountain Pen",
        url="https://example.com/pen",
        price_hint=Decimal("85.00"),
        priority=WishPriority.HIGH,
        notes="Fine nib, blue or black body.",
    )

    wishes: dict[str, Wish] = {
        "teapot": teapot,
        "fountain_pen": fountain_pen,
    }

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
        wishes=wishes,
    )


def create_account_link_seed(data: SeedData) -> AccountLinkSeed:
    """Create additional seed data for person-account links in development and E2E tests.

    Creates a 'Household' group and two person records owned by ``testuser``:
    - ``alice_record`` linked to ``data.alice``
    - ``self_record`` linked to ``testuser``
    """
    testuser = User.objects.get(username="testuser")

    household = PersonGroup.objects.create(name="Household")
    create_or_update_permission(testuser, household, permission_level=PermissionLevel.OWNER)

    alice_record = Person.objects.create(
        first_name="Alice",
        family_name="Smith",
        email_address=encode_email("alice@example.com"),
    )
    create_or_update_permission(testuser, alice_record, permission_level=PermissionLevel.OWNER)
    alice_record.groups.add(household)
    account_links.link(alice_record, data.alice, actor=testuser)

    self_record = Person.objects.create(
        first_name="Test",
        family_name="User",
        email_address=encode_email("testuser@example.com"),
    )
    create_or_update_permission(testuser, self_record, permission_level=PermissionLevel.OWNER)
    self_record.groups.add(household)
    account_links.link(self_record, testuser, actor=testuser)

    return AccountLinkSeed(
        household=household,
        alice_record=alice_record,
        self_record=self_record,
    )
