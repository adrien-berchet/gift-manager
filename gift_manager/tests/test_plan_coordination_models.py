"""Model tests for plan coordination: claim, surprise flag and comments."""

import pytest
from django.db import IntegrityError
from django.db import transaction
from django.utils import timezone

from gift_manager.models import PermissionLevel
from gift_manager.models import RelationComment
from gift_manager.services import PermissionService
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def _share(relation, user, level=PermissionLevel.VIEWER):
    PermissionService.create_or_update_permission(
        user, relation, permission_level=level, object_attr="relation"
    )


def test_defaults():
    relation = RelationFactory()

    assert relation.is_surprise is False
    assert relation.claimed_by is None
    assert relation.claimed_at is None
    assert relation.is_claimed is False


def test_claimed_by_requires_claimed_at():
    relation = RelationFactory()
    relation.claimed_by = UserFactory()
    relation.claimed_at = None

    with pytest.raises(IntegrityError), transaction.atomic():
        relation.save()


def test_deleting_claimer_unclaims_without_error():
    claimer = UserFactory()
    relation = RelationFactory()
    relation.claimed_by = claimer
    relation.claimed_at = timezone.now()
    relation.save()

    claimer.delete()
    relation.refresh_from_db()

    assert relation.claimed_by is None
    assert relation.is_claimed is False


def test_unsharing_releases_the_claim_of_that_user_only():
    claimer, other = UserFactory(), UserFactory()
    relation = RelationFactory()
    _share(relation, claimer)
    _share(relation, other)
    relation.claimed_by = claimer
    relation.claimed_at = timezone.now()
    relation.save()

    PermissionService.delete_permission(other, relation)
    relation.refresh_from_db()
    assert relation.claimed_by == claimer

    PermissionService.delete_permission(claimer, relation)
    relation.refresh_from_db()
    assert relation.claimed_by is None
    assert relation.claimed_at is None


def test_comments_are_ordered_oldest_first():
    relation = RelationFactory()
    author = UserFactory()
    first = RelationComment.objects.create(relation=relation, author=author, text="first")
    second = RelationComment.objects.create(relation=relation, author=author, text="second")

    assert list(relation.comments.all()) == [first, second]


def test_deleting_the_relation_deletes_its_comments():
    relation = RelationFactory()
    RelationComment.objects.create(relation=relation, author=UserFactory(), text="hi")

    relation.delete()

    assert RelationComment.objects.count() == 0


def test_deleting_the_author_keeps_the_comment():
    relation = RelationFactory()
    author = UserFactory()
    comment = RelationComment.objects.create(relation=relation, author=author, text="hi")

    author.delete()
    comment.refresh_from_db()

    assert comment.author is None
