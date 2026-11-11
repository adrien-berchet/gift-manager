"""Migration 0046 turns the single giver group into a many-to-many without losing data."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("gift_manager", "0045_relation_revealed_at_receivedgift")]
AFTER = [("gift_manager", "0046_receivedgift_giver_groups")]


def _migrate(targets):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(targets)
    return executor.loader.project_state(targets).apps


@pytest.mark.django_db(transaction=True)
def test_giver_group_is_copied_to_giver_groups_and_back():
    apps = _migrate(BEFORE)
    User = apps.get_model("auth", "User")
    PersonGroup = apps.get_model("gift_manager", "PersonGroup")
    ReceivedGift = apps.get_model("gift_manager", "ReceivedGift")
    user = User.objects.create(username="migrated")
    family = PersonGroup.objects.create(name="Family")
    with_group = ReceivedGift.objects.create(
        recipient_user=user, title="Board Game", giver_group=family
    )
    without_group = ReceivedGift.objects.create(
        recipient_user=user, title="Scarf", giver_label="Aunt Marie"
    )

    apps = _migrate(AFTER)
    ReceivedGift = apps.get_model("gift_manager", "ReceivedGift")
    assert list(
        ReceivedGift.objects.get(pk=with_group.pk).giver_groups.values_list("name", flat=True)
    ) == ["Family"]
    assert not ReceivedGift.objects.get(pk=without_group.pk).giver_groups.exists()

    apps = _migrate(BEFORE)
    ReceivedGift = apps.get_model("gift_manager", "ReceivedGift")
    assert ReceivedGift.objects.get(pk=with_group.pk).giver_group_id == family.pk
    assert ReceivedGift.objects.get(pk=without_group.pk).giver_group_id is None

    _migrate(AFTER)
