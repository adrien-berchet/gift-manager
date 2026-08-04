"""Tests for the ``seed_data`` management command."""

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError

from gift_manager.models import Gift
from gift_manager.models import Person
from gift_manager.models import PersonGroup


@pytest.mark.django_db
class TestSeedDataCommand:
    """Tests for ``python manage.py seed_data``."""

    def test_creates_data_on_clean_db(self):
        """The command succeeds on a clean database."""
        call_command("seed_data")
        assert User.objects.filter(username="alice").exists()
        assert User.objects.filter(username="bob").exists()
        assert Person.objects.count() >= 5
        assert Gift.objects.count() >= 4

    def test_refuses_on_populated_db(self):
        """The command raises ``CommandError`` when seed users already exist."""
        call_command("seed_data")
        with pytest.raises(CommandError, match=r"alice.*bob.*already exist"):
            call_command("seed_data")

    def test_refuses_when_persons_exist(self):
        """The command raises ``CommandError`` when persons already exist."""
        Person.objects.create(first_name="Someone", family_name="Else")
        with pytest.raises(CommandError, match="already contains"):
            call_command("seed_data")

    def test_flush_clears_and_recreates(self):
        """``--flush`` deletes existing data and re-seeds successfully."""
        call_command("seed_data")
        assert Person.objects.count() >= 5

        # Flush and re-create
        call_command("seed_data", flush=True)
        assert User.objects.filter(username="alice").exists()
        assert Person.objects.count() >= 5

    def test_flush_preserves_superusers(self):
        """``--flush`` does not delete superuser accounts."""
        superuser = User.objects.create_superuser(
            username="admin",
            password="admin_password",
            email="admin@example.com",
        )

        call_command("seed_data")
        call_command("seed_data", flush=True)

        assert User.objects.filter(pk=superuser.pk).exists()
        # Seed users are re-created
        assert User.objects.filter(username="alice").exists()

    def test_flush_on_empty_db(self):
        """``--flush`` works even on an already-empty database."""
        call_command("seed_data", flush=True)
        assert User.objects.filter(username="alice").exists()
        assert PersonGroup.objects.count() >= 3
