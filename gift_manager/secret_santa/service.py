"""Secret Santa business rules: create and edit exchanges, import participants, draw.

Every change locks the exchange row, so two requests of the organizer (a double click, two
tabs) cannot interleave a draw with an edit of the participants. Errors meant for the
organizer are raised as ``ExchangeError`` with a translated message; nothing is saved then.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import IntegrityError
from django.db import transaction
from django.db.models.functions import Lower
from django.utils import formats
from django.utils import timezone
from django.utils.translation import gettext

from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.secret_santa import draw as draw_engine
from gift_manager.secret_santa.models import MAX_PARTICIPANTS
from gift_manager.secret_santa.models import Exchange
from gift_manager.secret_santa.models import ExchangeParticipant
from gift_manager.secret_santa.models import ExclusionSet

if TYPE_CHECKING:
    import random
    from collections.abc import Iterable
    from datetime import date
    from decimal import Decimal

    from django.contrib.auth.models import User
    from django.db.models import QuerySet


class ExchangeError(Exception):
    """A refused change; ``message`` is translated and meant for the organizer."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _too_many() -> ExchangeError:
    return ExchangeError(
        gettext("An exchange can have at most %(count)d participants.")
        % {"count": MAX_PARTICIPANTS}
    )


def _duplicate_name() -> ExchangeError:
    return ExchangeError(gettext("Two participants cannot have the same name."))


def _draw_messages() -> dict[str, str]:
    return {
        draw_engine.TOO_FEW: gettext("At least %(count)d participants are needed.")
        % {"count": draw_engine.MIN_PARTICIPANTS},
        draw_engine.IMPOSSIBLE: gettext("No draw is possible with these exclusions."),
        draw_engine.GAVE_UP: gettext("No draw was found. Try again or relax the exclusions."),
    }


def _lock(exchange: Exchange) -> Exchange:
    """Lock the exchange row for the current transaction and return its fresh state."""
    locked = Exchange.objects.select_for_update().get(pk=exchange.pk)
    exchange.status = locked.status
    return locked


def _check_open(exchange: Exchange) -> None:
    if exchange.status == Exchange.Status.CLOSED:
        raise ExchangeError(gettext("This exchange is closed."))


def lock_open(exchange: Exchange) -> Exchange:
    """Lock the exchange row (inside a transaction) and refuse a closed exchange."""
    locked = _lock(exchange)
    _check_open(locked)
    return locked


def _check_draft(exchange: Exchange) -> None:
    _check_open(exchange)
    if exchange.status != Exchange.Status.DRAFT:
        raise ExchangeError(
            gettext("The draw is done. Redraw to change the participants or the exclusions.")
        )


def _clean_name(name: str) -> str:
    # One line of single spaces: names go into email subjects and must not break headers
    name = " ".join((name or "").split())
    if not name:
        raise ExchangeError(gettext("Enter a name."))
    return name[: ExchangeParticipant._meta.get_field("name").max_length]  # noqa: SLF001


def _name_taken(exchange: Exchange, name: str, *, exclude_pk: int | None = None) -> bool:
    participants = exchange.participants.annotate(lower_name=Lower("name")).filter(
        lower_name=name.lower()
    )
    if exclude_pk is not None:
        participants = participants.exclude(pk=exclude_pk)
    return participants.exists()


def organized_by(user: User) -> QuerySet[Exchange]:
    """Return the exchanges the user organizes; no other user ever sees them."""
    if not user or not user.is_authenticated:
        return Exchange.objects.none()
    return Exchange.objects.filter(organizer=user)


def create_exchange(
    organizer: User,
    *,
    name: str,
    exchange_date: date,
    budget: Decimal | None = None,
    guidelines: str = "",
    no_mutual_draw: bool = False,
    organizer_takes_part: bool = False,
) -> Exchange:
    """Create an exchange in the organizer's currency, with the organizer taking part or not."""
    with transaction.atomic():
        exchange = Exchange.objects.create(
            organizer=organizer,
            name=name,
            exchange_date=exchange_date,
            budget=budget,
            currency=organizer.profile.currency,
            guidelines=guidelines,
            no_mutual_draw=no_mutual_draw,
        )
        if organizer_takes_part:
            participant = ExchangeParticipant(
                exchange=exchange,
                name=_clean_name(organizer.get_full_name().strip() or organizer.username),
                linked_account=organizer,
            )
            participant.set_email(organizer.profile.email)
            participant.save()
    return exchange


def update_exchange(
    exchange: Exchange,
    *,
    name: str,
    exchange_date: date,
    budget: Decimal | None,
    guidelines: str,
    no_mutual_draw: bool,
    no_repeat_draw: bool | None = None,
) -> Exchange:
    """Edit the exchange; the rules of the draw only change before the draw."""
    with transaction.atomic():
        locked = _lock(exchange)
        _check_open(locked)
        if no_repeat_draw is None or locked.previous_exchange_id is None:
            no_repeat_draw = locked.no_repeat_draw
        if (no_mutual_draw, no_repeat_draw) != (locked.no_mutual_draw, locked.no_repeat_draw):
            _check_draft(locked)
        locked.name = name
        locked.exchange_date = exchange_date
        locked.budget = budget
        locked.guidelines = guidelines
        locked.no_mutual_draw = no_mutual_draw
        locked.no_repeat_draw = no_repeat_draw
        locked.save(
            update_fields=[
                "name",
                "exchange_date",
                "budget",
                "guidelines",
                "no_mutual_draw",
                "no_repeat_draw",
            ]
        )
    return locked


def copy_exchange(
    previous: Exchange,
    organizer: User,
    *,
    name: str,
    exchange_date: date,
    budget: Decimal | None = None,
    guidelines: str = "",
    no_mutual_draw: bool = False,
    no_repeat_draw: bool = True,
) -> Exchange:
    """Start a new exchange from ``previous``: same participants and exclusion sets.

    An account link is kept only when it comes from the participant's source person or is the
    organizer taking part; a link the participant attached themselves is not copied. Declines,
    invitations, wishes, notes and wishlist selections start afresh, with new personal links.
    """
    with transaction.atomic():
        exchange = Exchange.objects.create(
            organizer=organizer,
            name=name,
            exchange_date=exchange_date,
            budget=budget,
            currency=organizer.profile.currency,
            guidelines=guidelines,
            no_mutual_draw=no_mutual_draw,
            no_repeat_draw=no_repeat_draw,
            previous_exchange=previous,
        )
        # The address book may have changed since: only persons still shared are kept
        accessible = set(Person.objects.accessible_by(organizer).values_list("pk", flat=True))
        olds = list(
            previous.participants.select_related("source_person").defer(
                "gives_to", "note_for_santa"
            )
        )
        used_accounts = (
            {organizer.pk} if any(old.linked_account_id == organizer.pk for old in olds) else set()
        )
        copies = {}
        for old in olds:
            source = old.source_person if old.source_person_id in accessible else None
            account_id = None
            if old.linked_account_id == organizer.pk:
                account_id = organizer.pk
            elif source is not None and source.account_id not in (None, *used_accounts):
                account_id = source.account_id
                used_accounts.add(account_id)
            copies[old.pk] = ExchangeParticipant.objects.create(
                exchange=exchange,
                name=old.name,
                email_address=old.email_address,
                source_person=source,
                linked_account_id=account_id,
                previous_participant=old,
                emails_stopped=old.emails_stopped,
            )
        for old_set in previous.exclusion_sets.prefetch_related("participants"):
            members = [copies[p.pk] for p in old_set.participants.all() if p.pk in copies]
            if len(members) >= 2:
                new_set = ExclusionSet.objects.create(exchange=exchange, name=old_set.name)
                new_set.participants.set(members)
    return exchange


def _new_participant(locked: Exchange, name: str, email: str) -> ExchangeParticipant:
    """Create a typed participant in a locked exchange, within the limits."""
    name = _clean_name(name)
    if locked.participants.count() >= MAX_PARTICIPANTS:
        raise _too_many()
    if _name_taken(locked, name):
        raise _duplicate_name()
    participant = ExchangeParticipant(exchange=locked, name=name)
    participant.set_email((email or "").strip() or None)
    try:
        with transaction.atomic():
            participant.save()
    except IntegrityError as error:
        raise _duplicate_name() from error
    return participant


def add_participant(exchange: Exchange, *, name: str, email: str = "") -> ExchangeParticipant:
    """Add a typed participant before the draw."""
    _clean_name(name)
    with transaction.atomic():
        locked = _lock(exchange)
        _check_draft(locked)
        return _new_participant(locked, name, email)


def import_persons(
    exchange: Exchange, organizer: User, persons: Iterable[Person]
) -> tuple[int, int]:
    """Import persons of the organizer's address book; return (added, skipped).

    Only the persons the organizer can access are used. A person already present (same
    person record, same linked account or same name ignoring case) is skipped, so nobody
    can end up twice in the draw.
    """
    wanted = [person.pk for person in persons]
    with transaction.atomic():
        locked = _lock(exchange)
        _check_draft(locked)
        accessible = {
            person.pk: person
            for person in Person.objects.accessible_by(organizer)
            .filter(pk__in=wanted)
            .select_related("account")
        }
        existing = list(locked.participants.values_list("source_person_id", "linked_account_id"))
        sources = {source for source, _ in existing if source is not None}
        accounts = {account for _, account in existing if account is not None}
        names = {name.lower() for name in locked.participants.values_list("name", flat=True)}

        to_add: list[ExchangeParticipant] = []
        skipped = 0
        for pk in wanted:
            person = accessible.get(pk)
            if person is None:
                continue
            name = " ".join(str(person).split())[:120]
            if (
                not name
                or person.pk in sources
                or (person.account_id is not None and person.account_id in accounts)
                or name.lower() in names
            ):
                skipped += 1
                continue
            participant = ExchangeParticipant(
                exchange=locked,
                name=name,
                source_person=person,
                linked_account_id=person.account_id,
            )
            participant.set_email(person.email)
            to_add.append(participant)
            sources.add(person.pk)
            names.add(name.lower())
            if person.account_id is not None:
                accounts.add(person.account_id)

        if locked.participants.count() + len(to_add) > MAX_PARTICIPANTS:
            raise _too_many()
        for participant in to_add:
            participant.save()
    return len(to_add), skipped


def import_group(exchange: Exchange, organizer: User, group: PersonGroup) -> tuple[int, int]:
    """Import the direct and nested members of a group the organizer can access."""
    accessible_groups = PersonGroup.objects.accessible_by(organizer)
    if not accessible_groups.filter(pk=group.pk).exists():
        raise ExchangeError(gettext("This group was not found."))
    # Nested groups the organizer cannot see are left out, like their members
    groups = accessible_groups.filter(
        pk__in=PersonGroup.hierarchy_subquery([group], include_start=True)
    ).values("pk")
    members = (
        Person.objects.filter(groups__in=groups)
        .distinct()
        .order_by("first_name", "family_name", "pk")
    )
    return import_persons(exchange, organizer, members)


def update_participant(
    participant: ExchangeParticipant, *, name: str, email: str
) -> ExchangeParticipant:
    """Change a participant's name and email, before or after the draw.

    A new email address resets the "Send again" cooldown. The token is kept.
    """
    name = _clean_name(name)
    email = (email or "").strip() or None
    with transaction.atomic():
        locked = _lock(participant.exchange)
        _check_open(locked)
        if _name_taken(locked, name, exclude_pk=participant.pk):
            raise _duplicate_name()
        fresh = ExchangeParticipant.objects.defer("gives_to").get(pk=participant.pk)
        fields = ["name"]
        fresh.name = name
        if email != fresh.email:
            fresh.set_email(email)
            fresh.last_emailed_at = None
            fields += ["email_address", "last_emailed_at"]
        try:
            with transaction.atomic():
                fresh.save(update_fields=fields)
        except IntegrityError as error:
            raise _duplicate_name() from error
    participant.name = fresh.name
    participant.email_address = fresh.email_address
    participant.last_emailed_at = fresh.last_emailed_at
    return participant


def remove_participant(participant: ExchangeParticipant) -> None:
    """Remove a participant before the draw (also from their exclusion sets)."""
    with transaction.atomic():
        locked = _lock(participant.exchange)
        _check_draft(locked)
        ExchangeParticipant.objects.filter(pk=participant.pk).delete()


def regenerate_token(participant: ExchangeParticipant) -> str:
    """Give a participant a new personal link; the old one answers 404 from now on."""
    with transaction.atomic():
        locked = _lock(participant.exchange)
        _check_open(locked)
        return participant.regenerate_token()


def save_exclusion_set(
    exchange: Exchange,
    *,
    name: str,
    participants: Iterable[ExchangeParticipant],
    instance: ExclusionSet | None = None,
) -> ExclusionSet:
    """Create or update an exclusion set of at least two participants of this exchange."""
    members = {participant.pk: participant for participant in participants}
    name = " ".join((name or "").split())
    if not name:
        raise ExchangeError(gettext("Enter a name."))
    with transaction.atomic():
        locked = _lock(exchange)
        _check_draft(locked)
        if instance is not None and instance.exchange_id != locked.pk:
            raise ExchangeError(gettext("This exclusion set was not found."))
        valid = set(locked.participants.filter(pk__in=list(members)).values_list("pk", flat=True))
        if len(members) < 2 or valid != set(members):
            raise ExchangeError(
                gettext("An exclusion set needs at least two participants of this exchange.")
            )
        exclusion_set = instance or ExclusionSet(exchange=locked)
        exclusion_set.name = name[:120]
        exclusion_set.save()
        exclusion_set.participants.set(list(valid))
    return exclusion_set


def delete_exclusion_set(exclusion_set: ExclusionSet) -> None:
    """Delete an exclusion set before the draw."""
    with transaction.atomic():
        locked = _lock(exclusion_set.exchange)
        _check_draft(locked)
        ExclusionSet.objects.filter(pk=exclusion_set.pk).delete()


def forbidden_pairs(exchange: Exchange) -> set[tuple[int, int]]:
    """Return every ordered pair of two distinct members of one exclusion set."""
    members: dict[int, list[int]] = {}
    through = ExclusionSet.participants.through.objects.filter(exclusionset__exchange=exchange)
    for set_pk, participant_pk in through.values_list("exclusionset_id", "exchangeparticipant_id"):
        members.setdefault(set_pk, []).append(participant_pk)
    return {
        (giver, recipient)
        for group in members.values()
        for giver in group
        for recipient in group
        if giver != recipient
    }


def previous_pairs(exchange: Exchange) -> set[tuple[int, int]]:
    """Return the pairs (p, q) of this exchange whose people were paired in the previous one."""
    if not exchange.no_repeat_draw or exchange.previous_exchange_id is None:
        return set()
    copies = dict(
        exchange.participants.filter(
            previous_participant__exchange_id=exchange.previous_exchange_id
        ).values_list("previous_participant_id", "pk")
    )
    before = ExchangeParticipant.objects.filter(
        pk__in=list(copies), gives_to_id__in=list(copies), declined=False
    ).values_list("pk", "gives_to_id")
    return {(copies[giver], copies[recipient]) for giver, recipient in before}


def draw_rules(exchange: Exchange) -> tuple[set[tuple[int, int]], bool]:
    """Return every active rule of the exchange: forbidden pairs and the mutual-draw switch.

    Draws and repairs use this one place, so a repair is checked against the same rules.
    """
    return forbidden_pairs(exchange) | previous_pairs(exchange), exchange.no_mutual_draw


def run_draw(exchange: Exchange, *, rng: random.Random | None = None) -> list[ExchangeParticipant]:
    """Draw (or redraw) every pairing in one transaction; nothing changes on failure."""
    with transaction.atomic():
        locked = _lock(exchange)
        _check_open(locked)
        # Participants who said they cannot take part are left out of the draw
        participants = list(taking_part(locked).defer("gives_to").order_by("pk"))
        forbidden, no_mutual = draw_rules(locked)
        try:
            result = draw_engine.draw(
                [participant.pk for participant in participants],
                forbidden,
                no_mutual=no_mutual,
                rng=rng,
            )
        except draw_engine.NoDrawPossible as error:
            raise ExchangeError(_draw_messages()[error.reason]) from error
        for participant in participants:
            participant.gives_to_id = result[participant.pk]
            # Only an email sent for this draw counts as sent (and starts the cooldown)
            participant.last_emailed_at = None
        ExchangeParticipant.objects.bulk_update(participants, ["gives_to", "last_emailed_at"])
        locked.participants.filter(declined=True).update(gives_to=None)
        locked.status = Exchange.Status.DRAWN
        locked.drawn_at = timezone.now()
        locked.save(update_fields=["status", "drawn_at"])
    exchange.status = locked.status
    exchange.drawn_at = locked.drawn_at
    return participants


def taking_part(exchange: Exchange) -> QuerySet[ExchangeParticipant]:
    """Return the participants who did not decline."""
    return exchange.participants.filter(declined=False)


def put_back(participant: ExchangeParticipant) -> None:
    """Before the draw, count again a participant who had said they cannot take part."""
    with transaction.atomic():
        locked = _lock(participant.exchange)
        _check_draft(locked)
        ExchangeParticipant.objects.filter(pk=participant.pk).update(declined=False)
    participant.declined = False


def delete_exchange(exchange: Exchange) -> None:
    """Delete an exchange with its participants, pairings and exclusion sets."""
    exchange.delete()


def participants_without_pairings(exchange: Exchange) -> QuerySet[ExchangeParticipant]:
    """Return the participants for organizer pages, never loading who they drew.

    Their note for their Santa is not loaded either: it is meant for the Santa only.
    """
    return exchange.participants.defer("gives_to", "note_for_santa").order_by(Lower("name"), "pk")


# ---------------------------------------------------------------------------
# After the draw: removing or adding someone without starting over
# ---------------------------------------------------------------------------


def _repair_error(error: draw_engine.NoDrawPossible) -> ExchangeError:
    if error.reason == draw_engine.TOO_FEW:
        return ExchangeError(_draw_messages()[draw_engine.TOO_FEW])
    return ExchangeError(gettext("No repair keeps every rule. Redraw everything instead."))


def _lock_drawn(exchange: Exchange) -> Exchange:
    locked = lock_open(exchange)
    if locked.status != Exchange.Status.DRAWN:
        raise ExchangeError(gettext("The draw has not been done yet."))
    return locked


def _assignment(locked: Exchange) -> dict[int, int]:
    return dict(taking_part(locked).filter(gives_to__isnull=False).values_list("pk", "gives_to_id"))


def _save_repair(assignment: dict[int, int], changed: set[int]) -> list[ExchangeParticipant]:
    """Save the new recipients of ``changed``; only an email for the new pairing counts."""
    participants = list(
        ExchangeParticipant.objects.filter(pk__in=changed).defer("gives_to", "note_for_santa")
    )
    for participant in participants:
        participant.gives_to_id = assignment[participant.pk]
        participant.last_emailed_at = None
    ExchangeParticipant.objects.bulk_update(participants, ["gives_to", "last_emailed_at"])
    return participants


def _fresh(locked: Exchange, participant: ExchangeParticipant) -> ExchangeParticipant:
    return locked.participants.select_for_update().get(pk=participant.pk)


def remove_and_repair(participant: ExchangeParticipant) -> list[ExchangeParticipant]:
    """Remove a participant: whoever had drawn them now gives to the person they had drawn.

    Returns the participants to email: that one Santa (nobody for a participant who had
    declined and was left out of the draw).
    """
    with transaction.atomic():
        locked = _lock_drawn(participant.exchange)
        fresh = _fresh(locked, participant)
        assignment = _assignment(locked)
        if fresh.pk not in assignment:
            fresh.delete()
            return []
        forbidden, no_mutual = draw_rules(locked)
        try:
            repaired = draw_engine.repair_removal(
                assignment, fresh.pk, forbidden, no_mutual=no_mutual
            )
        except draw_engine.NoDrawPossible as error:
            raise _repair_error(error) from error
        santa = next(giver for giver, recipient in assignment.items() if recipient == fresh.pk)
        fresh.delete()
        return _save_repair(repaired, {santa})


def remove_and_redraw(participant: ExchangeParticipant) -> list[ExchangeParticipant]:
    """Remove a participant and redraw everything, as one operation (nothing on failure)."""
    with transaction.atomic():
        locked = _lock_drawn(participant.exchange)
        _fresh(locked, participant).delete()
        return run_draw(locked)


def _join(
    locked: Exchange,
    *,
    participant: ExchangeParticipant | None,
    name: str,
    email: str,
    exclusion_sets: Iterable[ExclusionSet],
) -> ExchangeParticipant:
    """Bring a latecomer in: a new participant, or one who had declined, put back."""
    if participant is not None:
        newcomer = _fresh(locked, participant)
        if not newcomer.declined:
            raise ExchangeError(gettext("This participant already takes part."))
        ExchangeParticipant.objects.filter(pk=newcomer.pk).update(declined=False)
        newcomer.declined = False
    else:
        newcomer = _new_participant(locked, name, email)
    for exclusion_set in exclusion_sets:
        if exclusion_set.exchange_id != locked.pk:
            raise ExchangeError(gettext("This exclusion set was not found."))
        exclusion_set.participants.add(newcomer)
    return newcomer


def add_and_repair(
    exchange: Exchange,
    *,
    participant: ExchangeParticipant | None = None,
    name: str = "",
    email: str = "",
    exclusion_sets: Iterable[ExclusionSet] = (),
    rng: random.Random | None = None,
) -> list[ExchangeParticipant]:
    """Insert a latecomer by changing two pairings; return the three participants to email."""
    with transaction.atomic():
        locked = _lock_drawn(exchange)
        newcomer = _join(
            locked, participant=participant, name=name, email=email, exclusion_sets=exclusion_sets
        )
        forbidden, no_mutual = draw_rules(locked)
        try:
            repaired, changed = draw_engine.repair_insertion(
                _assignment(locked), newcomer.pk, forbidden, no_mutual=no_mutual, rng=rng
            )
        except draw_engine.NoDrawPossible as error:
            raise _repair_error(error) from error
        return _save_repair(repaired, changed)


def add_and_redraw(
    exchange: Exchange,
    *,
    participant: ExchangeParticipant | None = None,
    name: str = "",
    email: str = "",
    exclusion_sets: Iterable[ExclusionSet] = (),
    rng: random.Random | None = None,
) -> list[ExchangeParticipant]:
    """Bring a latecomer in and redraw everything, as one operation (nothing on failure)."""
    with transaction.atomic():
        locked = _lock_drawn(exchange)
        _join(
            locked, participant=participant, name=name, email=email, exclusion_sets=exclusion_sets
        )
        return run_draw(locked, rng=rng)


def close_exchange(exchange: Exchange, *, reveal: bool, today: date | None = None) -> None:
    """Close a drawn exchange, from its date on; when ``reveal``, everyone sees the pairings.

    Closing is final. The pairings are kept, so a later exchange can avoid repeating them.
    """
    with transaction.atomic():
        locked = lock_open(exchange)
        if locked.status != Exchange.Status.DRAWN:
            raise ExchangeError(gettext("Only a drawn exchange can be closed."))
        if (today or timezone.localdate()) < locked.exchange_date:
            raise ExchangeError(
                gettext("The exchange can be closed from %(date)s.")
                % {"date": formats.date_format(locked.exchange_date, "DATE_FORMAT")}
            )
        locked.status = Exchange.Status.CLOSED
        locked.closed_at = timezone.now()
        locked.pairings_revealed = reveal
        locked.save(update_fields=["status", "closed_at", "pairings_revealed"])
    exchange.status = locked.status
    exchange.closed_at = locked.closed_at
    exchange.pairings_revealed = locked.pairings_revealed
