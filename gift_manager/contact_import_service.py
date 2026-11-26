"""Contact import: duplicate detection and creation of people from parsed contact records.

Records come from ``gift_manager.contact_import`` (see its docstring for their shape). Contact
details are third-party personal data: never log them.
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from gift_manager.group_hierarchy_service import GroupHierarchyService
from gift_manager.invitations import normalize_email
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.services import PermissionService
from gift_manager.suggestions.names import normalize_gift_name

# Possible duplicate kinds: a person the user owns, or one only shared with them
OWNED = "owned"
SHARED = "shared"

_BIRTHDAY_FIELDS = ("birthday_day", "birthday_month", "birthday_year")


def _name_key(first_name: str | None, family_name: str | None) -> tuple[str, str]:
    """Case-, accent- and ligature-insensitive key of a first and family name."""
    return normalize_gift_name(first_name or ""), normalize_gift_name(family_name or "")


def _email_key(email: str | None) -> str:
    if not email:
        return ""
    try:
        return normalize_email(email)
    except ValidationError:
        return email.strip().casefold()


def _stronger(current: str | None, kind: str) -> str:
    return OWNED if OWNED in {current, kind} else kind


def find_duplicates(user, contacts: list[dict]) -> list[str | None]:
    """Return, per contact, ``OWNED``, ``SHARED`` or None.

    A contact is a possible duplicate of a person the user can access (owned or shared) with
    the same first email (emails are encrypted, so they are compared decoded, in Python) or
    the same first and family name. A match on an owned person wins. Two queries in total.
    """
    people = Person.objects.accessible_by(user).only(
        "pk", "first_name", "family_name", "email_address"
    )
    owned_pks = set(Person.objects.owned_by(user).values_list("pk", flat=True))
    by_email: dict[str, str] = {}
    by_name: dict[tuple[str, str], str] = {}
    for person in people:
        kind = OWNED if person.pk in owned_pks else SHARED
        if email := _email_key(person.email):
            by_email[email] = _stronger(by_email.get(email), kind)
        name = _name_key(person.first_name, person.family_name)
        if name[0]:
            by_name[name] = _stronger(by_name.get(name), kind)

    duplicates = []
    for contact in contacts:
        kinds = {by_name.get(_name_key(contact["given"], contact["family"]))}
        if contact["emails"]:
            kinds.add(by_email.get(contact["emails"][0]))
        duplicates.append(OWNED if OWNED in kinds else SHARED if SHARED in kinds else None)
    return duplicates


def _build_person(contact: dict) -> Person:
    """Return an unsaved, validated person for a contact record."""
    person = Person(first_name=contact["given"], family_name=contact["family"] or None)
    if contact["emails"]:
        person.set_email(contact["emails"][0])
    if contact["bday"]:
        person.birthday_day, person.birthday_month, person.birthday_year = contact["bday"]
    # Same rules as the person form; uniqueness and the birthday check constraint are left to
    # the database (one query per person otherwise), and Person.clean() is stricter anyway.
    try:
        person.full_clean(validate_unique=False, validate_constraints=False)
    except ValidationError as error:
        if not set(error.message_dict) <= set(_BIRTHDAY_FIELDS):
            raise
        for field in _BIRTHDAY_FIELDS:
            setattr(person, field, None)
        person.full_clean(validate_unique=False, validate_constraints=False)
    return person


def import_contacts(
    user, contacts: list[dict], indexes: list[int], group: PersonGroup | None = None
) -> list[Person]:
    """Create one person per selected contact, owned by ``user``, in one transaction.

    When ``group`` is given, the new people are added to it; ``PermissionDenied`` is raised
    (and nothing is created) unless ``user`` may edit that group.
    """
    people = [_build_person(contacts[index]) for index in sorted(set(indexes))]
    with transaction.atomic():
        Person.objects.bulk_create(people)
        PermissionService.grant_owner_to_new_objects(user, people)
        if group is not None:
            GroupHierarchyService.change_members(user, group, add=people, members_are_new=True)
    return people
