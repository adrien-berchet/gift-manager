"""Tests for the contact import service: duplicate detection and person creation."""

import pytest
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.test.utils import CaptureQueriesContext

from gift_manager.contact_import_service import OWNED
from gift_manager.contact_import_service import SHARED
from gift_manager.contact_import_service import find_duplicates
from gift_manager.contact_import_service import import_contacts
from gift_manager.email_encoding import encode_email
from gift_manager.group_hierarchy_service import GroupHierarchyService
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import PersonPermission
from gift_manager.permissions import create_or_update_permission
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import UserFactory


def _contact(given, family="", emails=(), bday=None):
    return {
        "given": given,
        "family": family,
        "emails": list(emails),
        "bday": bday,
        "invalid_birthday": False,
    }


def _person(user, level=PermissionLevel.OWNER, **kwargs):
    email = kwargs.pop("email", None)
    person = PersonFactory(email_address=encode_email(email) if email else None, **kwargs)
    create_or_update_permission(user, person, permission_level=level)
    return person


@pytest.mark.django_db
class TestFindDuplicates:
    """Contacts matching a person the user can access are flagged."""

    def test_email_match_on_owned_person(self, user):
        _person(user, first_name="Other", family_name="Name", email="Ana@Example.com")

        assert find_duplicates(user, [_contact("Ana", "Silva", ["ana@example.com"])]) == [OWNED]

    def test_name_match_ignores_case_and_accents(self, user):
        _person(user, first_name="Élodie", family_name="Lefèvre")

        assert find_duplicates(user, [_contact("elodie", "LEFEVRE")]) == [OWNED]

    def test_ligatures_are_expanded(self, user):
        _person(user, first_name="Noël", family_name="Cœur")

        assert find_duplicates(user, [_contact("Noel", "Coeur")]) == [OWNED]

    def test_shared_person(self, user):
        _person(user, level=PermissionLevel.VIEWER, first_name="Ana", family_name="Silva")

        assert find_duplicates(user, [_contact("Ana", "Silva")]) == [SHARED]

    def test_owned_wins_over_shared(self, user):
        _person(user, level=PermissionLevel.EDITOR, first_name="Ana", family_name="Silva")
        _person(user, first_name="Someone", family_name="Else", email="ana@example.com")

        assert find_duplicates(user, [_contact("Ana", "Silva", ["ana@example.com"])]) == [OWNED]

    def test_people_of_other_users_are_ignored(self, user):
        _person(UserFactory(), first_name="Ana", family_name="Silva", email="ana@example.com")

        assert find_duplicates(user, [_contact("Ana", "Silva", ["ana@example.com"])]) == [None]

    def test_only_the_first_email_counts(self, user):
        _person(user, first_name="Other", family_name="Name", email="second@example.com")

        contact = _contact("Ana", "Silva", ["first@example.com", "second@example.com"])
        assert find_duplicates(user, [contact]) == [None]

    def test_first_name_alone_must_match_family_name_too(self, user):
        _person(user, first_name="Ana", family_name="Silva")

        assert find_duplicates(user, [_contact("Ana")]) == [None]

    def test_person_without_family_name(self, user):
        _person(user, first_name="Sarah", family_name=None)

        assert find_duplicates(user, [_contact("Sarah")]) == [OWNED]

    def test_constant_number_of_queries(self, user):
        for index in range(5):
            _person(user, first_name=f"P{index}", family_name="X", email=f"p{index}@example.com")
        contacts = [_contact(f"C{index}", "Y", [f"c{index}@example.com"]) for index in range(50)]

        with CaptureQueriesContext(connection) as queries:
            find_duplicates(user, contacts)

        assert len(queries) <= 2


@pytest.mark.django_db
class TestImportContacts:
    """Selected contacts become people owned by the importing user."""

    def test_creates_owned_people(self, user):
        contacts = [
            _contact("Ana", "Silva", ["ana@example.com", "ana2@example.com"], [12, 4, 1990]),
            _contact("Okafor", "", [], [1, 12, None]),
        ]

        people = import_contacts(user, contacts, [0, 1])

        assert len(people) == 2
        ana = Person.objects.get(first_name="Ana")
        assert ana.family_name == "Silva"
        assert ana.email == "ana@example.com"
        assert (ana.birthday_day, ana.birthday_month, ana.birthday_year) == (12, 4, 1990)
        okafor = Person.objects.get(first_name="Okafor")
        assert okafor.family_name is None
        assert okafor.email is None
        assert (okafor.birthday_day, okafor.birthday_month, okafor.birthday_year) == (1, 12, None)
        permissions = PersonPermission.objects.filter(person__in=people)
        assert {(p.user_id, p.permission_type) for p in permissions} == {
            (user.pk, PermissionLevel.OWNER)
        }
        assert set(Person.objects.owned_by(user)) == set(people)

    def test_only_selected_contacts_are_created(self, user):
        contacts = [_contact("A"), _contact("B"), _contact("C")]

        import_contacts(user, contacts, [2, 0])

        assert sorted(Person.objects.values_list("first_name", flat=True)) == ["A", "C"]

    def test_imported_people_are_private(self, user):
        other = UserFactory()

        import_contacts(user, [_contact("Ana")], [0])

        assert not Person.objects.accessible_by(other).exists()

    def test_adds_to_an_editable_group(self, user):
        group = PersonGroupFactory()
        create_or_update_permission(user, group, permission_level=PermissionLevel.EDITOR)

        people = import_contacts(user, [_contact("A"), _contact("B")], [0, 1], group=group)

        assert set(group.person_set.all()) == set(people)

    def test_refuses_a_group_the_user_cannot_edit(self, user):
        group = PersonGroupFactory()
        create_or_update_permission(user, group, permission_level=PermissionLevel.VIEWER)

        with pytest.raises(PermissionDenied):
            import_contacts(user, [_contact("A")], [0], group=group)

        assert not Person.objects.exists()

    def test_invalid_birthday_is_dropped(self, user):
        import_contacts(user, [_contact("A", bday=[30, 2, 1990])], [0])

        person = Person.objects.get()
        assert person.birthday_day is None
        assert person.birthday_month is None

    def test_reimport_with_default_selection_creates_nothing(self, user):
        contacts = [_contact("Ana", "Silva", ["ana@example.com"]), _contact("Bob")]
        import_contacts(user, contacts, [0, 1])

        duplicates = find_duplicates(user, contacts)
        default_selection = [index for index, kind in enumerate(duplicates) if kind is None]

        assert default_selection == []
        assert Person.objects.count() == 2

    def test_thousand_contacts_in_few_queries(self, user):
        group = PersonGroupFactory()
        create_or_update_permission(user, group, permission_level=PermissionLevel.OWNER)
        contacts = [_contact(f"P{i}", "X", [f"p{i}@example.com"]) for i in range(1000)]

        with CaptureQueriesContext(connection) as queries:
            people = import_contacts(user, contacts, list(range(1000)), group=group)

        assert len(people) == 1000
        assert group.person_set.count() == 1000
        assert len(queries) < 30


@pytest.mark.django_db
class TestChangeMembersOfNewPeople:
    """members_are_new skips the per-person edit check but still checks the group."""

    def test_group_is_checked_once(self, user):
        group = PersonGroupFactory()
        create_or_update_permission(user, group, permission_level=PermissionLevel.EDITOR)
        people = [PersonFactory() for _ in range(5)]

        with CaptureQueriesContext(connection) as queries:
            GroupHierarchyService.change_members(user, group, add=people, members_are_new=True)

        assert group.person_set.count() == 5
        assert len(queries) < 10

    def test_existing_members_still_need_edit_rights(self, user):
        group = PersonGroupFactory()
        create_or_update_permission(user, group, permission_level=PermissionLevel.EDITOR)
        person = PersonFactory()

        with pytest.raises(PermissionDenied):
            GroupHierarchyService.change_members(user, group, add=[person])
