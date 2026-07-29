#!/usr/bin/env python
"""Identify and clean up duplicate UUIDs in the database.

This script detects records with duplicate UUIDs and merges them carefully while
preserving existing relations and permissions.
"""

import logging
import os
import sys
from collections import defaultdict
from pathlib import Path

import django
from django.db import transaction

# Setup Django
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "GiftManager.settings")
django.setup()

from gift_manager.models import Event  # noqa: E402
from gift_manager.models import Gift  # noqa: E402
from gift_manager.models import GiftTag  # noqa: E402
from gift_manager.models import Person  # noqa: E402
from gift_manager.models import PersonGroup  # noqa: E402
from gift_manager.models import Relation  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def find_duplicates(model, uuid_field):
    """Find duplicates for a given model."""
    all_objects = model.objects.all()
    uuid_to_objects = defaultdict(list)

    for obj in all_objects:
        uuid_value = getattr(obj, uuid_field)
        uuid_to_objects[uuid_value].append(obj)

    return {uuid_val: objs for uuid_val, objs in uuid_to_objects.items() if len(objs) > 1}


def merge_persons(duplicates):
    """Merge duplicate people."""
    logger.info("\n=== Processing %s duplicate Person records ===", len(duplicates))

    for uuid_val, persons in duplicates.items():
        logger.info("\nUUID: %s - %s duplicates found", uuid_val, len(persons))

        # Sort by ID, keeping the oldest record first.
        sorted_persons = sorted(persons, key=lambda p: p.id)
        keeper = sorted_persons[0]
        to_delete = sorted_persons[1:]

        logger.info("  Keep: ID=%s, Name=%s", keeper.id, keeper)

        with transaction.atomic():
            for duplicate in to_delete:
                logger.info("  Delete: ID=%s, Name=%s", duplicate.id, duplicate)

                # Migrate permissions.
                for perm in duplicate.personpermission_set.all():
                    # Check whether the keeper already has a permission for this user.
                    existing = keeper.personpermission_set.filter(user=perm.user).first()
                    if existing:
                        # Keep the highest permission level.
                        if perm.permission_type > existing.permission_type:
                            existing.permission_type = perm.permission_type
                            existing.save()
                    else:
                        perm.person = keeper
                        perm.save()

                # Migrate gift relations.
                for relation in duplicate.persons.all():
                    # Check whether this gift relation already exists.
                    existing = keeper.persons.filter(gift=relation.gift).first()
                    if not existing:
                        relation.person = keeper
                        relation.save()

                # Migrate groups.
                for group in duplicate.groups.all():
                    if not keeper.groups.filter(id=group.id).exists():
                        keeper.groups.add(group)

                # Migrate user_link if needed.
                if duplicate.user_link and not keeper.user_link:
                    keeper.user_link = duplicate.user_link
                    keeper.save()

                # Delete the duplicate.
                duplicate.delete()


def report_generic_duplicates(duplicates, name):
    """Report duplicate objects that require a manual merge."""
    logger.info("\n=== Processing %s duplicate %s records ===", len(duplicates), name)

    for uuid_val, objects in duplicates.items():
        logger.info("\nUUID: %s - %s duplicates found", uuid_val, len(objects))

        # Sort by ID, keeping the oldest record first.
        sorted_objects = sorted(objects, key=lambda o: o.id)
        keeper = sorted_objects[0]
        to_delete = sorted_objects[1:]

        logger.info("  Keep: ID=%s, %s", keeper.id, keeper)
        logger.info("  Automatic merge is not supported for %s.", name)
        for duplicate in to_delete:
            logger.info("  Manual merge required: ID=%s, %s", duplicate.id, duplicate)


def main():
    """Run the duplicate UUID cleanup."""
    logger.info("=" * 60)
    logger.info("Searching for duplicate UUIDs in the database")
    logger.info("=" * 60)

    models_to_check = [
        (Person, "person_id", "Person"),
        (PersonGroup, "group_id", "PersonGroup"),
        (GiftTag, "tag_id", "GiftTag"),
        (Gift, "gift_id", "Gift"),
        (Event, "event_id", "Event"),
        (Relation, "relation_id", "Relation"),
    ]

    has_duplicates = False

    for model, uuid_field, name in models_to_check:
        duplicates = find_duplicates(model, uuid_field)
        if duplicates:
            has_duplicates = True
            if model == Person:
                merge_persons(duplicates)
            else:
                report_generic_duplicates(duplicates, name)

    if not has_duplicates:
        logger.info("\nNo duplicates found!")
    else:
        logger.info("\n%s", "=" * 60)
        logger.info("Cleanup complete!")
        logger.info("=" * 60)


if __name__ == "__main__":
    main()
