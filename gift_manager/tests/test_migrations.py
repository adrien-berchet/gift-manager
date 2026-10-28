from datetime import date
from importlib import import_module

import pytest
from django.apps import apps
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from gift_manager.models import RelationStatus


@pytest.mark.django_db
class TestNormalizeAbandonedStatusSpellingMigration:
    """Regression tests for the abandoned-status data repair migration."""

    @staticmethod
    def _run_migration():
        migration = import_module(
            "gift_manager.migrations.0025_normalize_abandoned_status_spelling"
        )
        migration.normalize_abandoned_status_spelling(apps, None)

    def test_renames_existing_typo_status(self):
        typo_status = RelationStatus.objects.get(status_en="Abandoned")
        typo_status.status = "Abandonned"
        typo_status.status_en = "Abandonned"
        typo_status.save()

        self._run_migration()

        typo_status.refresh_from_db()
        assert typo_status.status == "Abandoned"
        assert typo_status.status_en == "Abandoned"
        assert typo_status.status_fr == "Abandonné"

    def test_keeps_existing_canonical_status(self):
        status = RelationStatus.objects.get(status_en="Abandoned")

        self._run_migration()

        status.refresh_from_db()
        assert status.status == "Abandoned"
        assert status.status_en == "Abandoned"
        assert status.status_fr == "Abandonné"
        assert RelationStatus.objects.filter(status="Abandoned").count() == 1

    def test_merges_typo_duplicate_and_repoints_relations(self, relation_factory):
        canonical = RelationStatus.objects.get(status_en="Abandoned")
        typo_status = RelationStatus.objects.create(
            status="Abandonned",
            status_en="Abandonned",
            status_fr="Legacy abandoned",
        )
        canonical_relation = relation_factory(status=canonical)
        typo_relation = relation_factory(status=typo_status)

        self._run_migration()

        canonical_relation.refresh_from_db()
        typo_relation.refresh_from_db()
        assert canonical_relation.status_id == canonical.pk
        assert typo_relation.status_id == canonical.pk
        assert not RelationStatus.objects.filter(status="Abandonned").exists()
        assert not RelationStatus.objects.filter(status_en="Abandonned").exists()
        assert RelationStatus.objects.filter(status="Abandoned").count() == 1


@pytest.mark.django_db(transaction=True)
class TestEventScheduleModelMigration:
    """Regression tests for the event schedule data migration."""

    migrate_from = [("gift_manager", "0026_relation_exactly_one_recipient_constraint")]
    migrate_to = [("gift_manager", "0027_event_schedule_model")]

    def test_maps_legacy_event_dates_to_schedule_contract(self):
        executor = MigrationExecutor(connection)
        leaf_nodes = executor.loader.graph.leaf_nodes()

        try:
            executor.migrate(self.migrate_from)
            old_apps = executor.loader.project_state(self.migrate_from).apps
            legacy_event = old_apps.get_model("gift_manager", "Event")

            legacy_event.objects.create(
                name="Graduation",
                usual_date=date(2026, 6, 1),
                absolute_date=date(2026, 6, 20),
                recurrence="yearly",
            )
            legacy_event.objects.create(
                name="Birthday",
                usual_date=date(2000, 5, 15),
                recurrence="yearly",
            )
            legacy_event.objects.create(
                name="Visit",
                usual_date=date(2026, 8, 2),
            )
            legacy_event.objects.create(name="Someday")

            executor = MigrationExecutor(connection)
            executor.migrate(self.migrate_to)
            new_apps = executor.loader.project_state(self.migrate_to).apps
            Event = new_apps.get_model("gift_manager", "Event")

            schedules = {
                event.name: (event.schedule_type, event.date, event.recurrence)
                for event in Event.objects.order_by("name")
            }

            assert schedules == {
                "Birthday": ("recurring", date(2000, 5, 15), "yearly"),
                "Graduation": ("one_time", date(2026, 6, 20), None),
                "Someday": ("unscheduled", None, None),
                "Visit": ("one_time", date(2026, 8, 2), None),
            }
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(leaf_nodes)


ARCHIVE_TABLE = "gift_manager_relation_0026_archive"


def _archive_rows():
    if ARCHIVE_TABLE not in connection.introspection.table_names():
        return []
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT comment, reason FROM {ARCHIVE_TABLE} ORDER BY comment")  # noqa: S608
        return cursor.fetchall()


@pytest.mark.django_db(transaction=True)
class TestRelationRecipientCleanupMigration:
    """GM-AUD-010: dirty legacy relations are archived, not silently discarded."""

    before = [("gift_manager", "0025_normalize_abandoned_status_spelling")]
    after = [("gift_manager", "0026_relation_exactly_one_recipient_constraint")]

    def _migrate_across_0026(self, comments):
        """Seed relations before 0026, migrate, and report what survived and was archived."""
        executor = MigrationExecutor(connection)
        leaf_nodes = executor.loader.graph.leaf_nodes()
        try:
            executor.migrate(self.before)
            old_apps = executor.loader.project_state(self.before).apps
            self._seed(old_apps, comments)

            executor = MigrationExecutor(connection)
            executor.migrate(self.after)
            new_apps = executor.loader.project_state(self.after).apps
            relation = new_apps.get_model("gift_manager", "Relation")
            surviving = {
                r.comment: (r.person_id is not None, r.group_id is not None)
                for r in relation.objects.all()
            }
            return surviving, _archive_rows()
        finally:
            with connection.cursor() as cursor:
                cursor.execute(f"DROP TABLE IF EXISTS {ARCHIVE_TABLE}")
            executor = MigrationExecutor(connection)
            executor.migrate(leaf_nodes)

    @staticmethod
    def _seed(old_apps, comments):
        gift = old_apps.get_model("gift_manager", "Gift").objects.create(name="Gift")
        person = old_apps.get_model("gift_manager", "Person").objects.create(first_name="Ada")
        group = old_apps.get_model("gift_manager", "PersonGroup").objects.create(name="Family")
        status_model = old_apps.get_model("gift_manager", "RelationStatus")
        status = status_model.objects.first() or status_model.objects.create(status="Idea")
        relation = old_apps.get_model("gift_manager", "Relation")

        if "clean" in comments:
            relation.objects.create(gift=gift, person=person, status=status, comment="clean")
        if "both" in comments:
            relation.objects.create(
                gift=gift, person=person, group=group, status=status, comment="both"
            )
        if "neither" in comments:
            relation.objects.create(gift=gift, status=status, comment="neither")

    def test_dirty_rows_are_archived_with_their_reason_and_then_repaired(self):
        surviving, archived = self._migrate_across_0026({"clean", "both", "neither"})

        assert surviving == {"clean": (True, False), "both": (True, False)}
        assert [
            (comment, "both" in reason or "no recipient" in reason) for comment, reason in archived
        ] == [
            ("both", True),
            ("neither", True),
        ]
        reasons = dict(archived)
        assert reasons["both"] != reasons["neither"]

    def test_clean_data_creates_no_archive(self):
        surviving, archived = self._migrate_across_0026({"clean"})

        assert surviving == {"clean": (True, False)}
        assert archived == []


@pytest.mark.django_db(transaction=True)
class TestPersonAccountLinkMigration:
    """Regression tests for the Person.user_link -> Person.account migration."""

    migrate_from = [("gift_manager", "0040_giftsuggestion_dismiss_comment_and_more")]
    migrate_to = [("gift_manager", "0041_person_account_link")]

    def _migrate_and_get_apps(self, seed_fn):
        """Helper to run pre-0041 seed, execute 0041 migration, and return new_apps."""
        executor = MigrationExecutor(connection)
        leaf_nodes = executor.loader.graph.leaf_nodes()
        try:
            executor.migrate(self.migrate_from)
            old_apps = executor.loader.project_state(self.migrate_from).apps
            seed_data = seed_fn(old_apps)

            executor = MigrationExecutor(connection)
            executor.migrate(self.migrate_to)
            new_apps = executor.loader.project_state(self.migrate_to).apps
            return new_apps, seed_data
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(leaf_nodes)

    def test_backfills_missing_owner_permission(self):
        def seed(old_apps):
            User = old_apps.get_model("auth", "User")
            Person = old_apps.get_model("gift_manager", "Person")
            u = User.objects.create(username="linked_user")
            p = Person.objects.create(first_name="Alice", user_link=u)
            return u.id, p.id

        new_apps, (user_id, person_id) = self._migrate_and_get_apps(seed)
        PersonPermission = new_apps.get_model("gift_manager", "PersonPermission")
        perms = PersonPermission.objects.filter(person_id=person_id, user_id=user_id)
        assert perms.count() == 1
        assert perms.first().permission_type == 30

    def test_does_not_duplicate_existing_owner_permission(self):
        def seed(old_apps):
            User = old_apps.get_model("auth", "User")
            Person = old_apps.get_model("gift_manager", "Person")
            PersonPermission = old_apps.get_model("gift_manager", "PersonPermission")
            u = User.objects.create(username="linked_user")
            p = Person.objects.create(first_name="Alice", user_link=u)
            PersonPermission.objects.create(person=p, user=u, permission_type=30)
            return u.id, p.id

        new_apps, (user_id, person_id) = self._migrate_and_get_apps(seed)
        PersonPermission = new_apps.get_model("gift_manager", "PersonPermission")
        perms = PersonPermission.objects.filter(person_id=person_id, user_id=user_id)
        assert perms.count() == 1
        assert perms.first().permission_type == 30

    @pytest.mark.parametrize("initial_level", [10, 20])
    def test_upgrades_existing_non_owner_permission(self, initial_level):
        def seed(old_apps):
            User = old_apps.get_model("auth", "User")
            Person = old_apps.get_model("gift_manager", "Person")
            PersonPermission = old_apps.get_model("gift_manager", "PersonPermission")
            u = User.objects.create(username=f"linked_user_{initial_level}")
            p = Person.objects.create(first_name="Alice", user_link=u)
            PersonPermission.objects.create(person=p, user=u, permission_type=initial_level)
            return u.id, p.id

        new_apps, (user_id, person_id) = self._migrate_and_get_apps(seed)
        PersonPermission = new_apps.get_model("gift_manager", "PersonPermission")
        perms = PersonPermission.objects.filter(person_id=person_id, user_id=user_id)
        assert perms.count() == 1
        assert perms.first().permission_type == 30

    def test_preserves_other_users_permissions(self):
        def seed(old_apps):
            User = old_apps.get_model("auth", "User")
            Person = old_apps.get_model("gift_manager", "Person")
            PersonPermission = old_apps.get_model("gift_manager", "PersonPermission")
            creator = User.objects.create(username="creator")
            linked = User.objects.create(username="linked")
            viewer = User.objects.create(username="viewer")
            p = Person.objects.create(first_name="Alice", user_link=linked)
            PersonPermission.objects.create(person=p, user=creator, permission_type=30)
            PersonPermission.objects.create(person=p, user=viewer, permission_type=10)
            return creator.id, linked.id, viewer.id, p.id

        new_apps, (creator_id, linked_id, viewer_id, person_id) = self._migrate_and_get_apps(seed)
        PersonPermission = new_apps.get_model("gift_manager", "PersonPermission")
        assert (
            PersonPermission.objects.get(person_id=person_id, user_id=creator_id).permission_type
            == 30
        )
        assert (
            PersonPermission.objects.get(person_id=person_id, user_id=linked_id).permission_type
            == 30
        )
        assert (
            PersonPermission.objects.get(person_id=person_id, user_id=viewer_id).permission_type
            == 10
        )

    def test_same_user_linked_on_multiple_persons(self):
        def seed(old_apps):
            User = old_apps.get_model("auth", "User")
            Person = old_apps.get_model("gift_manager", "Person")
            u = User.objects.create(username="linked_multi")
            p1 = Person.objects.create(first_name="Alice", user_link=u)
            p2 = Person.objects.create(first_name="Bob", user_link=u)
            return u.id, p1.id, p2.id

        new_apps, (user_id, p1_id, p2_id) = self._migrate_and_get_apps(seed)
        PersonPermission = new_apps.get_model("gift_manager", "PersonPermission")
        assert PersonPermission.objects.get(person_id=p1_id, user_id=user_id).permission_type == 30
        assert PersonPermission.objects.get(person_id=p2_id, user_id=user_id).permission_type == 30

    def test_unlinked_person_gets_no_permission_created(self):
        def seed(old_apps):
            Person = old_apps.get_model("gift_manager", "Person")
            p = Person.objects.create(first_name="Unlinked", user_link=None)
            return p.id

        new_apps, person_id = self._migrate_and_get_apps(seed)
        PersonPermission = new_apps.get_model("gift_manager", "PersonPermission")
        assert PersonPermission.objects.filter(person_id=person_id).count() == 0

    def test_clears_every_account(self):
        def seed(old_apps):
            User = old_apps.get_model("auth", "User")
            Person = old_apps.get_model("gift_manager", "Person")
            u1 = User.objects.create(username="u1")
            u2 = User.objects.create(username="u2")
            p1 = Person.objects.create(first_name="Alice", user_link=u1)
            p2 = Person.objects.create(first_name="Bob", user_link=u2)
            p3 = Person.objects.create(first_name="Charlie", user_link=None)
            return [p1.id, p2.id, p3.id]

        new_apps, person_ids = self._migrate_and_get_apps(seed)
        Person = new_apps.get_model("gift_manager", "Person")
        for person_id in person_ids:
            p = Person.objects.get(id=person_id)
            assert p.account_id is None

    def test_new_columns_exist_and_are_null(self):
        def seed(old_apps):
            User = old_apps.get_model("auth", "User")
            Person = old_apps.get_model("gift_manager", "Person")
            Invitation = old_apps.get_model("gift_manager", "Invitation")
            u = User.objects.create(username="sender")
            p = Person.objects.create(first_name="Alice")
            inv = Invitation.objects.create(sender=u, recipient_email="encoded_email")
            return p.id, inv.id

        new_apps, (person_id, inv_id) = self._migrate_and_get_apps(seed)
        Person = new_apps.get_model("gift_manager", "Person")
        Invitation = new_apps.get_model("gift_manager", "Invitation")
        p = Person.objects.get(id=person_id)
        inv = Invitation.objects.get(id=inv_id)
        assert hasattr(p, "link_suggestion_dismissed_account_id")
        assert p.link_suggestion_dismissed_account_id is None
        assert hasattr(inv, "person_id")
        assert inv.person_id is None


@pytest.mark.django_db
def test_deleting_linked_account_keeps_the_person(user_factory, person_factory):
    account = user_factory()
    person = person_factory(account=account)
    person_id = person.id
    account.delete()
    person.refresh_from_db()
    assert person.account is None
    from gift_manager.models import Person

    assert Person.objects.filter(id=person_id).exists()
