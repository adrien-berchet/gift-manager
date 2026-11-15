"""The "Plan a gift" shortcut of a Santa with an account: what the guided plan starts from.

Only what the Santa can already see is preselected: the person the organizer imported the
recipient from, when the Santa may edit that person; otherwise a person the Santa owns that is
linked to the recipient's account; otherwise a new person named after the recipient. A new
person is never linked to the recipient's account.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.secret_santa.models import ExchangeParticipant
from gift_manager.services import PermissionService

if TYPE_CHECKING:
    from django.contrib.auth.models import User


def plan_prefill(santa: ExchangeParticipant, user: User) -> dict[str, str]:
    """Return the query-string values of the guided plan for ``santa``'s recipient."""
    recipient = (
        ExchangeParticipant.objects.filter(pk=santa.gives_to_id, exchange_id=santa.exchange_id)
        .only("name", "source_person_id", "linked_account_id")
        .get()
    )
    if recipient.source_person_id is not None:
        person = Person.objects.filter(pk=recipient.source_person_id).first()
        if (
            person is not None
            and PermissionService.get_effective_permission(person, user) >= PermissionLevel.EDITOR
        ):
            return {"recipient": f"person:{person.person_id}"}
    if recipient.linked_account_id is not None:
        owned = (
            Person.objects.filter(
                account_id=recipient.linked_account_id,
                personpermission__user=user,
                personpermission__permission_type=PermissionLevel.OWNER,
            )
            .order_by("pk")
            .first()
        )
        if owned is not None:
            return {"recipient": f"person:{owned.person_id}"}
    first_name, _, family_name = recipient.name.partition(" ")
    prefill = {"new_person-first_name": first_name}
    if family_name.strip():
        prefill["new_person-family_name"] = family_name.strip()
    return prefill
