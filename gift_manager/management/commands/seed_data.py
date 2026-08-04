"""Management command to populate the database with deterministic seed data.

Usage::

    # Seed a clean database
    python manage.py seed_data

    # Flush existing data first, then seed
    python manage.py seed_data --flush
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import GiftTag
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import Relation
from gift_manager.models import RelationStatus


class Command(BaseCommand):
    help = "Populate the database with deterministic seed data for development and testing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            default=False,
            help=(
                "Delete all gift_manager data and non-superuser users "
                "before seeding.  Superusers are preserved."
            ),
        )

    def handle(self, *args, **options):
        if options["flush"]:
            self._flush()
        else:
            self._check_clean_db()

        from gift_manager.seed_data import create_seed_data  # noqa: PLC0415

        data = create_seed_data()
        self._print_summary(data)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_clean_db(self) -> None:
        """Raise ``CommandError`` if the database already contains data."""
        if User.objects.filter(username__in=["alice", "bob"]).exists():
            msg = (
                "Users 'alice' and/or 'bob' already exist.  "
                "Use --flush to delete existing data before seeding."
            )
            raise CommandError(msg)
        if Person.objects.exists() or Gift.objects.exists():
            msg = (
                "The database already contains persons or gifts.  "
                "Use --flush to delete existing data before seeding."
            )
            raise CommandError(msg)

    def _flush(self) -> None:
        """Delete all gift_manager data and non-superuser users."""
        self.stdout.write("Flushing existing data...")

        # Delete in reverse-dependency order to avoid FK constraint errors.
        Relation.objects.all().delete()
        Event.objects.all().delete()
        Gift.objects.all().delete()
        GiftTag.objects.all().delete()
        Person.objects.all().delete()
        PersonGroup.objects.all().delete()
        RelationStatus.objects.all().delete()

        # Delete non-superuser users (preserve superusers).
        User.objects.filter(is_superuser=False).delete()

        self.stdout.write(self.style.SUCCESS("  Flushed."))

    def _print_summary(self, data) -> None:
        """Print a summary of created objects."""
        self.stdout.write(self.style.SUCCESS("\nSeed data created successfully!\n"))
        self.stdout.write(f"  Users:            {2}  (alice, bob + testuser superuser)")
        self.stdout.write(f"  Relation statuses: {len(data.statuses)}")
        self.stdout.write(f"  Person groups:     {len(data.groups)}")
        self.stdout.write(f"  Persons:           {len(data.persons)}")
        self.stdout.write(f"  Gift tags:         {len(data.tags)}")
        self.stdout.write(f"  Gifts:             {len(data.gifts)}")
        self.stdout.write(f"  Events:            {len(data.events)}")
        self.stdout.write(f"  Relations:         {len(data.relations)}")
        self.stdout.write("")
        self.stdout.write("  Login as:  alice / alice_password   |   bob / bob_password")
        self.stdout.write("  Admin:     testuser / testpass123")
