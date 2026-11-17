"""Getting-started checklist steps, worked out from the data a user owns.

Shared objects never tick a step: the checklist teaches by doing, so only what the user
created (``PermissionLevel.OWNER``) counts.
"""

from dataclasses import dataclass

from django.urls import reverse
from django.utils.translation import gettext

from gift_manager.models import Gift
from gift_manager.models import Invitation
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import Relation
from gift_manager.models import RelationStatus
from gift_manager.models import Wish
from gift_manager.statuses import is_given_status
from gift_manager.statuses import is_purchased_status


@dataclass(frozen=True)
class GettingStartedStep:
    """One checklist step."""

    key: str
    label: str
    done: bool
    action_url: str
    help_url: str
    optional: bool
    guided_url: str | None = None


@dataclass(frozen=True)
class GettingStarted:
    """The checklist of one user."""

    steps: tuple[GettingStartedStep, ...]

    @property
    def core_steps(self) -> tuple[GettingStartedStep, ...]:
        return tuple(step for step in self.steps if not step.optional)

    @property
    def optional_steps(self) -> tuple[GettingStartedStep, ...]:
        return tuple(step for step in self.steps if step.optional)

    @property
    def core_done_count(self) -> int:
        return sum(1 for step in self.core_steps if step.done)

    @property
    def all_done(self) -> bool:
        return all(step.done for step in self.steps)


def _help_url(topic: str, anchor: str | None = None) -> str:
    url = reverse("gift_manager:help_topic", args=[topic])
    return f"{url}#{anchor}" if anchor else url


def _progress_status_ids() -> list:
    return [
        status.pk
        for status in RelationStatus.objects.all()
        if is_purchased_status(status) or is_given_status(status)
    ]


def compute_getting_started(user) -> GettingStarted:
    """Return the checklist of ``user``, each step ticked from data they own."""
    owned_plans = Relation.objects.owned_by(user)
    steps = (
        GettingStartedStep(
            key="recipient",
            label=gettext("Add a recipient"),
            done=Person.objects.owned_by(user).exists()
            or PersonGroup.objects.owned_by(user).exists(),
            action_url=reverse("gift_manager:person_create"),
            help_url=_help_url("how-it-works", "recipients"),
            optional=False,
        ),
        GettingStartedStep(
            key="gift",
            label=gettext("Add a gift idea"),
            done=Gift.objects.owned_by(user).exists(),
            action_url=reverse("gift_manager:gift_create"),
            help_url=_help_url("how-it-works", "gifts"),
            optional=False,
        ),
        GettingStartedStep(
            key="plan",
            label=gettext("Create your first gift plan"),
            done=owned_plans.exists(),
            action_url=reverse("gift_manager:relation_create"),
            help_url=_help_url("how-it-works", "gift-plans"),
            optional=False,
            guided_url=reverse("gift_manager:relation_guided_create"),
        ),
        GettingStartedStep(
            key="progress",
            label=gettext("Move a plan to Purchased or Given"),
            done=owned_plans.filter(status_id__in=_progress_status_ids()).exists(),
            action_url=reverse("gift_manager:relations"),
            help_url=_help_url("how-it-works", "statuses"),
            optional=False,
        ),
        GettingStartedStep(
            key="wish",
            label=gettext("Add something to your wishlist"),
            # for_wisher leaves out wishes the user deleted; archived ones still count.
            done=Wish.objects.for_wisher(user).exists(),
            action_url=reverse("gift_manager:wish_create"),
            help_url=_help_url("wishlist"),
            optional=True,
        ),
        GettingStartedStep(
            key="friend",
            label=gettext("Connect with a friend"),
            done=user.profile.friends.exists() or Invitation.objects.filter(sender=user).exists(),
            action_url=reverse("gift_manager:send_invitation"),
            help_url=_help_url("friends-and-sharing"),
            optional=True,
        ),
    )
    return GettingStarted(steps=steps)
