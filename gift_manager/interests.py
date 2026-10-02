"""Match a person's interests (gift tags) against the gifts the viewer can use."""

from django.db.models import Count

from gift_manager.models import Gift
from gift_manager.models import GiftTag
from gift_manager.models import Person

SUGGESTION_LIMIT = 8


def gifts_matching_interests(user, person: Person, limit: int = SUGGESTION_LIMIT) -> list[Gift]:
    """Return the viewer's gifts sharing tags with the person's interests, best match first.

    Only tags the viewer can access count on either side, and gifts that already have a
    plan for the person are left out.
    """
    interest_ids = list(
        person.interests.filter(
            pk__in=GiftTag.objects.accessible_by(user).values("pk")
        ).values_list("pk", flat=True)
    )
    if not interest_ids:
        return []
    return list(
        Gift.objects.accessible_by(user)
        .filter(tags__in=interest_ids)
        .exclude(gifts__person=person)
        .annotate(matching_tags=Count("tags", distinct=True))
        .order_by("-matching_tags", "name")[:limit]
    )
