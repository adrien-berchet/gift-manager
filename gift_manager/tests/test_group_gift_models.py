from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db import transaction
from django.utils import timezone

from gift_manager.models import Relation
from gift_manager.models import RelationContribution
from gift_manager.models import SplitMode
from gift_manager.tests.factories import RelationContributionFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import UserFactory


@pytest.mark.django_db
class TestRelationGroupGiftFields:
    def test_relation_split_mode_and_is_group_gift_defaults(self):
        relation = RelationFactory()
        relation.refresh_from_db()

        assert relation.is_group_gift is False
        assert relation.split_mode == SplitMode.EQUAL

    def test_invalid_split_mode_is_rejected_by_full_clean(self):
        relation = RelationFactory()
        relation.split_mode = "bogus"

        with pytest.raises(ValidationError) as exc_info:
            relation.full_clean()

        assert "split_mode" in exc_info.value.message_dict


@pytest.mark.django_db
class TestRelationContributionConstraints:
    """DB-level constraints, exercised through bulk_create/update to bypass ``save()``."""

    def test_contribution_requires_name(self):
        relation = RelationFactory()

        with pytest.raises(IntegrityError), transaction.atomic():
            RelationContribution.objects.bulk_create(
                [RelationContribution(relation=relation, user=None, name="")]
            )

    def test_contribution_amount_non_negative(self):
        contribution = RelationContributionFactory()

        with pytest.raises(IntegrityError), transaction.atomic():
            RelationContribution.objects.filter(pk=contribution.pk).update(amount=Decimal("-0.01"))

    def test_contribution_is_paid_requires_paid_at(self):
        contribution = RelationContributionFactory()

        with pytest.raises(IntegrityError), transaction.atomic():
            RelationContribution.objects.filter(pk=contribution.pk).update(
                is_paid=True, paid_at=None
            )

    def test_paid_at_without_is_paid_is_rejected(self):
        contribution = RelationContributionFactory()

        with pytest.raises(IntegrityError), transaction.atomic():
            RelationContribution.objects.filter(pk=contribution.pk).update(
                is_paid=False, paid_at=timezone.now()
            )

    def test_unique_user_contribution_per_plan(self):
        contribution = RelationContributionFactory()

        with pytest.raises(IntegrityError), transaction.atomic():
            RelationContributionFactory(relation=contribution.relation, user=contribution.user)

    def test_same_user_can_contribute_to_different_plans(self):
        user = UserFactory()

        RelationContributionFactory(user=user)
        RelationContributionFactory(user=user)

        assert RelationContribution.objects.filter(user=user).count() == 2

    def test_multiple_external_contributors_allowed(self):
        relation = RelationFactory()

        RelationContributionFactory(relation=relation, user=None, name="Aunt Jo")
        RelationContributionFactory(relation=relation, user=None, name="Uncle Bob")

        assert relation.contributions.count() == 2

    def test_duplicate_user_is_reported_by_full_clean(self):
        contribution = RelationContributionFactory()
        duplicate = RelationContribution(relation=contribution.relation, user=contribution.user)

        with pytest.raises(ValidationError):
            duplicate.full_clean()

    def test_negative_amount_is_rejected_by_full_clean(self):
        contribution = RelationContributionFactory.build(amount=Decimal("-1.00"))

        with pytest.raises(ValidationError) as exc_info:
            contribution.full_clean(exclude=["relation", "user"])

        assert "amount" in exc_info.value.message_dict


@pytest.mark.django_db
class TestRelationContributionBehaviour:
    def test_save_snapshots_user_username_into_name(self):
        user = UserFactory(username="alice")
        contribution = RelationContribution.objects.create(
            relation=RelationFactory(), user=user, name=""
        )

        contribution.refresh_from_db()

        assert contribution.name == "alice"

    def test_save_refreshes_name_while_user_is_linked(self):
        user = UserFactory(username="alice")
        contribution = RelationContributionFactory(user=user)
        user.username = "alice2"
        user.save()

        contribution.save()
        contribution.refresh_from_db()

        assert contribution.name == "alice2"

    def test_save_with_update_fields_persists_refreshed_name(self):
        user = UserFactory(username="alice")
        contribution = RelationContributionFactory(user=user)
        user.username = "alice2"
        user.save()

        contribution.save(update_fields=["amount"])
        contribution.refresh_from_db()

        assert contribution.name == "alice2"

    def test_save_strips_external_name(self):
        contribution = RelationContributionFactory(user=None, name="  Aunt Jo  ")

        contribution.refresh_from_db()

        assert contribution.name == "Aunt Jo"

    def test_clean_rejects_blank_external_name(self):
        contribution = RelationContributionFactory.build(user=None, name="   ")

        with pytest.raises(ValidationError) as exc_info:
            contribution.clean()

        assert "name" in exc_info.value.message_dict

    def test_clean_accepts_user_without_name(self):
        contribution = RelationContributionFactory.build(user=UserFactory(), name="")

        contribution.clean()

    def test_save_rejects_blank_external_name_with_validation_error(self):
        with pytest.raises(ValidationError):
            RelationContributionFactory(user=None, name="   ")

    def test_mark_paid_sets_flag_and_timestamp(self):
        contribution = RelationContributionFactory(amount=Decimal("10.00"))

        contribution.mark_paid()
        contribution.refresh_from_db()

        assert contribution.is_paid is True
        assert contribution.paid_at is not None
        assert contribution.amount == Decimal("10.00")

    def test_mark_paid_freezes_given_amount(self):
        contribution = RelationContributionFactory()

        contribution.mark_paid(amount=Decimal("12.50"))
        contribution.refresh_from_db()

        assert contribution.amount == Decimal("12.50")

    def test_mark_paid_keeps_original_timestamp_when_already_paid(self):
        contribution = RelationContributionFactory(is_paid=True)
        original = contribution.paid_at

        contribution.mark_paid()
        contribution.refresh_from_db()

        assert contribution.paid_at == original

    def test_mark_unpaid_clears_flag_and_timestamp(self):
        contribution = RelationContributionFactory(is_paid=True)

        contribution.mark_unpaid()
        contribution.refresh_from_db()

        assert contribution.is_paid is False
        assert contribution.paid_at is None

    def test_factory_paid_trait_satisfies_constraint(self):
        contribution = RelationContributionFactory(paid=True)

        assert contribution.is_paid is True
        assert contribution.paid_at is not None

    def test_factory_external_trait(self):
        contribution = RelationContributionFactory(external=True)

        assert contribution.user is None
        assert contribution.name

    def test_display_name_and_str_use_live_username(self):
        user = UserFactory(username="alice")
        contribution = RelationContributionFactory(user=user, amount=Decimal("5.00"))

        assert contribution.display_name == "alice"
        assert str(contribution) == "alice (5.00)"

    def test_display_name_for_external_contributor(self):
        contribution = RelationContributionFactory(user=None, name="Aunt Jo")

        assert contribution.display_name == "Aunt Jo"

    def test_default_ordering_is_creation_order(self):
        relation = RelationFactory()
        first = RelationContributionFactory(relation=relation, user=None, name="A")
        second = RelationContributionFactory(relation=relation, user=None, name="B")

        assert list(relation.contributions.all()) == [first, second]


@pytest.mark.django_db
class TestRelationContributionDeletion:
    def test_user_account_deletion_preserves_contribution_row(self):
        user = UserFactory(username="alice")
        contribution = RelationContributionFactory(user=user, is_paid=True)

        user.delete()
        contribution.refresh_from_db()

        assert contribution.user is None
        assert contribution.name == "alice"
        assert contribution.display_name == "alice"
        assert contribution.is_paid is True

    def test_several_deleted_users_can_coexist_on_one_plan(self):
        relation = RelationFactory()
        first_user, second_user = UserFactory(), UserFactory()
        RelationContributionFactory(relation=relation, user=first_user)
        RelationContributionFactory(relation=relation, user=second_user)

        first_user.delete()
        second_user.delete()

        assert relation.contributions.filter(user__isnull=True).count() == 2

    def test_deleting_relation_cascades_to_contributions(self):
        contribution = RelationContributionFactory()
        relation = contribution.relation

        relation.delete()

        assert not RelationContribution.objects.filter(pk=contribution.pk).exists()
        assert not Relation.objects.filter(pk=relation.pk).exists()
