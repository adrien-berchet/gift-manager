import pytest
from django.db import IntegrityError
from django.db import transaction

from gift_manager.models import GiftSuggestion
from gift_manager.models import GiftSuggestionGeneration
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_requires_exactly_one_recipient(user):
    person = PersonFactory()
    group = PersonGroupFactory()
    gift = GiftFactory()

    # Neither person nor group
    with pytest.raises(IntegrityError), transaction.atomic():
        GiftSuggestion.objects.create(
            user=user,
            source=GiftSuggestion.Source.CATALOGUE,
            gift=gift,
            normalized_name="gift",
        )

    # Both person and group
    with pytest.raises(IntegrityError), transaction.atomic():
        GiftSuggestion.objects.create(
            user=user,
            person=person,
            group=group,
            source=GiftSuggestion.Source.CATALOGUE,
            gift=gift,
            normalized_name="gift",
        )


def test_catalogue_requires_gift(user):
    person = PersonFactory()

    with pytest.raises(IntegrityError), transaction.atomic():
        GiftSuggestion.objects.create(
            user=user,
            person=person,
            source=GiftSuggestion.Source.CATALOGUE,
            gift=None,
            name="Book",
            normalized_name="book",
        )


def test_ai_requires_name(user):
    person = PersonFactory()

    with pytest.raises(IntegrityError), transaction.atomic():
        GiftSuggestion.objects.create(
            user=user,
            person=person,
            source=GiftSuggestion.Source.AI,
            name="",
            normalized_name="",
        )


def test_one_catalogue_row_per_user_recipient_gift(user):
    person = PersonFactory()
    gift = GiftFactory()

    GiftSuggestion.objects.create(
        user=user,
        person=person,
        source=GiftSuggestion.Source.CATALOGUE,
        gift=gift,
        normalized_name="book",
    )

    # Second catalogue row with same user, person, gift raises IntegrityError
    with pytest.raises(IntegrityError), transaction.atomic():
        GiftSuggestion.objects.create(
            user=user,
            person=person,
            source=GiftSuggestion.Source.CATALOGUE,
            gift=gift,
            normalized_name="book",
        )

    # Same gift for another user is fine
    other_user = UserFactory()
    second = GiftSuggestion.objects.create(
        user=other_user,
        person=person,
        source=GiftSuggestion.Source.CATALOGUE,
        gift=gift,
        normalized_name="book",
    )
    assert second.pk is not None


def test_deleting_gift_deletes_its_suggestions(user):
    person = PersonFactory()
    gift = GiftFactory()

    suggestion = GiftSuggestion.objects.create(
        user=user,
        person=person,
        source=GiftSuggestion.Source.CATALOGUE,
        gift=gift,
        normalized_name="book",
    )
    suggestion_id = suggestion.pk
    gift.delete()

    assert not GiftSuggestion.objects.filter(pk=suggestion_id).exists()


def test_generation_requires_one_recipient(user):
    person = PersonFactory()
    group = PersonGroupFactory()

    # Neither
    with pytest.raises(IntegrityError), transaction.atomic():
        GiftSuggestionGeneration.objects.create(user=user)

    # Both
    with pytest.raises(IntegrityError), transaction.atomic():
        GiftSuggestionGeneration.objects.create(user=user, person=person, group=group)

    # One person works
    gen_person = GiftSuggestionGeneration.objects.create(user=user, person=person)
    assert gen_person.pk is not None

    # One group works
    gen_group = GiftSuggestionGeneration.objects.create(user=user, group=group)
    assert gen_group.pk is not None
