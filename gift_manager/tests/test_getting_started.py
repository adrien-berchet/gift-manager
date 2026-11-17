"""Tests for the getting-started step computation."""

import pytest
from django.urls import reverse
from django.utils import translation

from gift_manager.getting_started import compute_getting_started
from gift_manager.models import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import InvitationFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import RelationStatusFactory
from gift_manager.tests.factories import WishFactory


def _step(user, key):
    return next(step for step in compute_getting_started(user).steps if step.key == key)


def _own(user, obj):
    create_or_update_permission(user, obj, permission_level=PermissionLevel.OWNER)
    return obj


@pytest.mark.django_db
class TestComputeGettingStarted:
    """Steps tick from data the user owns."""

    def test_empty_account_has_nothing_done(self, user):
        """A new account has every step unticked, core steps first."""
        getting_started = compute_getting_started(user)

        assert [s.key for s in getting_started.steps] == [
            "recipient",
            "gift",
            "plan",
            "progress",
            "wish",
            "friend",
        ]
        assert [s.optional for s in getting_started.steps] == [False] * 4 + [True] * 2
        assert not any(s.done for s in getting_started.steps)
        assert getting_started.core_done_count == 0
        assert not getting_started.all_done
        assert [s.key for s in getting_started.core_steps] == ["recipient", "gift", "plan", "progress"]
        assert [s.key for s in getting_started.optional_steps] == ["wish", "friend"]

    def test_owned_person_counts_as_recipient(self, user):
        """An owned person ticks the recipient step."""
        PersonFactory(owner=user)

        assert _step(user, "recipient").done

    def test_owned_group_counts_as_recipient(self, user):
        """An owned group ticks the recipient step."""
        _own(user, PersonGroupFactory())

        assert _step(user, "recipient").done

    def test_owned_gift_ticks_gift_step(self, user):
        """An owned gift ticks the gift step."""
        _own(user, GiftFactory())

        assert _step(user, "gift").done
        assert compute_getting_started(user).core_done_count == 1

    def test_owned_plan_ticks_plan_step_but_not_progress_when_idea(self, user):
        """An owned plan at Idea ticks the plan step only."""
        _own(user, RelationFactory(status=RelationStatusFactory(status="Idea")))

        assert _step(user, "plan").done
        assert not _step(user, "progress").done

    @pytest.mark.parametrize("status", ["Purchased", "Given"])
    def test_purchased_or_given_plan_ticks_progress(self, user, status):
        """A plan moved to Purchased or Given ticks the progress step."""
        _own(user, RelationFactory(status=RelationStatusFactory(status=status)))

        assert _step(user, "progress").done

    def test_planned_plan_does_not_tick_progress(self, user):
        """Planned is not far enough."""
        _own(user, RelationFactory(status=RelationStatusFactory(status="Planned")))

        assert not _step(user, "progress").done

    def test_progress_detected_under_french_locale(self, user):
        """Detection goes through the English status slug, not the active language."""
        given = RelationStatusFactory(status="Given")
        given.status_fr = "Offert"
        given.save()
        _own(user, RelationFactory(status=given))

        with translation.override("fr"):
            assert _step(user, "progress").done

    def test_shared_only_objects_tick_nothing(self, user, user_factory):
        """Objects a friend owns and shares with the user do not tick any core step."""
        friend = user_factory()
        person = PersonFactory(owner=friend)
        gift = GiftFactory()
        plan = RelationFactory(
            person=person, gift=gift, status=RelationStatusFactory(status="Given")
        )
        for obj in (gift, plan):
            _own(friend, obj)
        create_or_update_permission(user, person, permission_level=PermissionLevel.VIEWER)
        create_or_update_permission(user, gift, permission_level=PermissionLevel.EDITOR)
        create_or_update_permission(user, plan, permission_level=PermissionLevel.EDITOR)

        getting_started = compute_getting_started(user)

        assert [s.done for s in getting_started.core_steps] == [False] * 4

    def test_wish_ticks_wish_step(self, user):
        """A wish by the user ticks the wish step."""
        WishFactory(wisher=user)

        assert _step(user, "wish").done

    def test_archived_wish_ticks_wish_step(self, user):
        """An archived wish still counts."""
        WishFactory(wisher=user, is_archived=True)

        assert _step(user, "wish").done

    def test_soft_deleted_wish_does_not_tick_wish_step(self, user):
        """A wish the user deleted does not count."""
        WishFactory(wisher=user, is_deleted_by_wisher=True)

        assert not _step(user, "wish").done

    def test_another_users_wish_does_not_tick_wish_step(self, user, user_factory):
        """Only the user's own wishes count."""
        WishFactory(wisher=user_factory())

        assert not _step(user, "wish").done

    def test_friend_ticks_friend_step(self, user, user_factory):
        """A confirmed friend ticks the friend step."""
        user.profile.friends.add(user_factory().profile)

        assert _step(user, "friend").done

    def test_sent_invitation_ticks_friend_step(self, user, user_factory):
        """A sent invitation ticks the friend step; a received one does not."""
        other = user_factory()
        InvitationFactory(sender=other)
        assert not _step(user, "friend").done

        InvitationFactory(sender=user)
        assert _step(user, "friend").done

    def test_all_done_when_every_step_done(self, user, user_factory):
        """Every step done, optional ones included, makes all_done true."""
        PersonFactory(owner=user)
        _own(user, GiftFactory())
        _own(user, RelationFactory(status=RelationStatusFactory(status="Given")))
        WishFactory(wisher=user)
        user.profile.friends.add(user_factory().profile)

        getting_started = compute_getting_started(user)

        assert getting_started.core_done_count == 4
        assert getting_started.all_done

    def test_core_done_but_optional_missing_is_not_all_done(self, user):
        """Optional steps are part of all_done."""
        PersonFactory(owner=user)
        _own(user, GiftFactory())
        _own(user, RelationFactory(status=RelationStatusFactory(status="Given")))

        getting_started = compute_getting_started(user)

        assert getting_started.core_done_count == 4
        assert not getting_started.all_done

    def test_plan_step_offers_guided_url(self, user):
        """The plan step links to the guided flow as well."""
        plan = _step(user, "plan")

        assert plan.action_url == reverse("gift_manager:relation_create")
        assert plan.guided_url == reverse("gift_manager:relation_guided_create")

    def test_steps_link_to_actions_and_help(self, user):
        """Each step has its action URL and its Help URL."""
        steps = {s.key: s for s in compute_getting_started(user).steps}
        core = reverse("gift_manager:help_topic", args=["how-it-works"])

        assert steps["recipient"].action_url == reverse("gift_manager:person_create")
        assert steps["recipient"].help_url == f"{core}#recipients"
        assert steps["gift"].action_url == reverse("gift_manager:gift_create")
        assert steps["gift"].help_url == f"{core}#gifts"
        assert steps["plan"].help_url == f"{core}#gift-plans"
        assert steps["progress"].action_url == reverse("gift_manager:relations")
        assert steps["progress"].help_url == f"{core}#statuses"
        assert steps["wish"].action_url == reverse("gift_manager:wish_create")
        assert steps["wish"].help_url == reverse("gift_manager:help_topic", args=["wishlist"])
        assert steps["friend"].action_url == reverse("gift_manager:send_invitation")
        assert steps["friend"].help_url == reverse(
            "gift_manager:help_topic", args=["friends-and-sharing"]
        )
        assert all(s.guided_url is None for s in steps.values() if s.key != "plan")
