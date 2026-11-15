"""Secret Santa draw engine: pure functions, no database and no Django.

A draw assigns every participant (a giver) exactly one other participant (a recipient) so that
everyone also receives exactly once, nobody draws themselves, no forbidden (giver, recipient)
pair is used and, when ``no_mutual`` is set, nobody draws the person who drew them.

The search first checks that a draw can exist at all (a perfect matching between givers and
allowed recipients), so most impossible exclusions are reported at once. It then backtracks,
always on the giver with the fewest remaining choices, with candidates in random order, and
abandons a branch as soon as a giver has no choice left or a recipient can no longer be drawn.
Every tried candidate counts as one step; past ``max_steps`` the search gives up, so a request
never hangs on a pathological case.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Collection
    from collections.abc import Iterable
    from collections.abc import Mapping
    from collections.abc import Sequence

MIN_PARTICIPANTS = 3
DEFAULT_MAX_STEPS = 20_000  # about two seconds in the worst case for 100 people


TOO_FEW = "too_few"
IMPOSSIBLE = "impossible"
GAVE_UP = "gave_up"


class NoDrawPossible(Exception):  # noqa: N818 - the name reads as the outcome
    """No draw was produced. ``reason`` is "too_few", "impossible" or "gave_up"."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def draw(
    participants: Sequence[int] | Iterable[int],
    forbidden: Collection[tuple[int, int]] = (),
    *,
    no_mutual: bool = False,
    rng: random.Random | None = None,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> dict[int, int]:
    """Return a draw as a mapping giver -> recipient, or raise ``NoDrawPossible``.

    ``forbidden`` holds ordered (giver, recipient) pairs; pairs naming someone who is not a
    participant are ignored. ``rng`` defaults to ``random.SystemRandom()``.
    """
    people = list(dict.fromkeys(participants))
    if len(people) < MIN_PARTICIPANTS:
        raise NoDrawPossible(TOO_FEW)
    forbidden_pairs = set(forbidden)
    allowed = {
        giver: {
            recipient
            for recipient in people
            if recipient != giver and (giver, recipient) not in forbidden_pairs
        }
        for giver in people
    }
    if not _has_perfect_matching(people, allowed):
        raise NoDrawPossible(IMPOSSIBLE)

    search = _Search(people, allowed, no_mutual=no_mutual, rng=rng or random.SystemRandom())
    result = search.run(max_steps)
    if result is None:
        raise NoDrawPossible(IMPOSSIBLE)
    return result


def is_valid(
    assignment: Mapping[int, int],
    participants: Iterable[int],
    forbidden: Collection[tuple[int, int]],
    *,
    no_mutual: bool,
) -> bool:
    """Return whether ``assignment`` is a complete draw that respects every rule."""
    people = set(participants)
    if set(assignment) != people or sorted(assignment.values()) != sorted(people):
        return False
    forbidden_pairs = set(forbidden)
    for giver, recipient in assignment.items():
        if giver == recipient or (giver, recipient) in forbidden_pairs:
            return False
        if no_mutual and assignment[recipient] == giver:
            return False
    return True


def _has_perfect_matching(people: list[int], allowed: Mapping[int, set[int]]) -> bool:
    """Return whether every giver can get a distinct allowed recipient (augmenting paths)."""
    giver_of: dict[int, int] = {}

    def augment(giver: int, seen: set[int]) -> bool:
        for recipient in allowed[giver]:
            if recipient in seen:
                continue
            seen.add(recipient)
            if recipient not in giver_of or augment(giver_of[recipient], seen):
                giver_of[recipient] = giver
                return True
        return False

    return all(augment(giver, set()) for giver in people)


class _Search:
    """Backtracking over the edges (unassigned giver -> recipient not yet drawn)."""

    def __init__(self, people, allowed, *, no_mutual: bool, rng: random.Random):
        self.no_mutual = no_mutual
        self.rng = rng
        # Ties between equally constrained givers are broken by this random order
        self.order = list(people)
        rng.shuffle(self.order)
        self.candidates = {giver: set(allowed[giver]) for giver in people}
        self.givers = {recipient: set() for recipient in people}
        for giver, recipients in allowed.items():
            for recipient in recipients:
                self.givers[recipient].add(giver)
        self.unassigned = set(people)
        self.drawn: set[int] = set()
        self.assignment: dict[int, int] = {}
        self.steps = 0
        self.max_steps = 0

    def run(self, max_steps: int) -> dict[int, int] | None:
        self.max_steps = max_steps
        return dict(self.assignment) if self._extend() else None

    def _extend(self) -> bool:
        if not self.unassigned:
            return True
        giver = min(
            (giver for giver in self.order if giver in self.unassigned),
            key=lambda giver: len(self.candidates[giver]),
        )
        choices = sorted(self.candidates[giver])
        self.rng.shuffle(choices)
        for recipient in choices:
            self.steps += 1
            if self.steps > self.max_steps:
                raise NoDrawPossible(GAVE_UP)
            alive, removed = self._assign(giver, recipient)
            if alive and self._extend():
                return True
            self._undo(giver, removed)
        return False

    def _remove(self, giver: int, recipient: int, removed: list[tuple[int, int]]) -> None:
        self.candidates[giver].discard(recipient)
        self.givers[recipient].discard(giver)
        removed.append((giver, recipient))

    def _assign(self, giver: int, recipient: int) -> tuple[bool, list[tuple[int, int]]]:
        """Assign, remove the edges this rules out, and report whether the branch can live."""
        removed: list[tuple[int, int]] = []
        self.unassigned.discard(giver)
        self.drawn.add(recipient)
        self.assignment[giver] = recipient
        alive = True
        # The giver is done: none of its other recipients can count on it any more
        for other in list(self.candidates[giver]):
            self._remove(giver, other, removed)
            if other != recipient and not self.givers[other]:
                alive = False
        # The recipient is taken: nobody else can draw them
        for other in list(self.givers[recipient]):
            self._remove(other, recipient, removed)
            if not self.candidates[other]:
                alive = False
        # Nobody draws the person who drew them
        if self.no_mutual and giver in self.candidates[recipient]:
            self._remove(recipient, giver, removed)
            if not self.candidates[recipient] or (
                giver not in self.drawn and not self.givers[giver]
            ):
                alive = False
        return alive, removed

    def _undo(self, giver: int, removed: list[tuple[int, int]]) -> None:
        for edge_giver, edge_recipient in removed:
            self.candidates[edge_giver].add(edge_recipient)
            self.givers[edge_recipient].add(edge_giver)
        self.drawn.discard(self.assignment.pop(giver))
        self.unassigned.add(giver)


def _breaks_a_rule(
    pairs: Iterable[tuple[int, int]],
    assignment: Mapping[int, int],
    forbidden: Collection[tuple[int, int]],
    *,
    no_mutual: bool,
) -> bool:
    """Return whether one of the new ``pairs`` breaks a rule within ``assignment``."""
    for giver, recipient in pairs:
        if giver == recipient or (giver, recipient) in forbidden:
            return True
        if no_mutual and assignment.get(recipient) == giver:
            return True
    return False


def repair_removal(
    assignment: Mapping[int, int],
    removed: int,
    forbidden: Collection[tuple[int, int]] = (),
    *,
    no_mutual: bool = False,
) -> dict[int, int]:
    """Remove ``removed``: whoever drew them now gives to the person they had drawn.

    Only that one pairing changes. Raises ``NoDrawPossible`` when fewer than
    ``MIN_PARTICIPANTS`` would remain or when the new pairing breaks a rule, which includes
    removing someone from a mutual pair (their Santa would draw themselves).
    """
    if len(assignment) - 1 < MIN_PARTICIPANTS:
        raise NoDrawPossible(TOO_FEW)
    santa = next((giver for giver, recipient in assignment.items() if recipient == removed), None)
    if santa is None or removed not in assignment:
        raise NoDrawPossible(IMPOSSIBLE)
    result = {giver: recipient for giver, recipient in assignment.items() if giver != removed}
    result[santa] = assignment[removed]
    if _breaks_a_rule([(santa, result[santa])], result, set(forbidden), no_mutual=no_mutual):
        raise NoDrawPossible(IMPOSSIBLE)
    return result


def repair_insertion(
    assignment: Mapping[int, int],
    newcomer: int,
    forbidden: Collection[tuple[int, int]] = (),
    *,
    no_mutual: bool = False,
    rng: random.Random | None = None,
) -> tuple[dict[int, int], set[int]]:
    """Insert ``newcomer`` by changing two pairings, so that nobody can deduce their recipient.

    If A gave to B and C gave to D, then A gives to the newcomer, the newcomer gives to D and C
    gives to B. The choice of (A, C) is random among every choice that keeps all the rules.
    Returns the new assignment and the participants whose recipient changed (A, C and the
    newcomer). Raises ``NoDrawPossible`` when no choice keeps every rule.
    """
    forbidden_pairs = set(forbidden)
    givers = sorted(assignment)
    choices = []
    for first in givers:
        former = assignment[first]
        for second in givers:
            if second in (first, former):
                continue
            result = dict(assignment)
            result[first] = newcomer
            result[newcomer] = assignment[second]
            result[second] = former
            new_pairs = [(first, newcomer), (newcomer, assignment[second]), (second, former)]
            if not _breaks_a_rule(new_pairs, result, forbidden_pairs, no_mutual=no_mutual):
                choices.append((first, second))
    if not choices:
        raise NoDrawPossible(IMPOSSIBLE)
    first, second = (rng or random.SystemRandom()).choice(choices)
    result = dict(assignment)
    result[first] = newcomer
    result[newcomer] = assignment[second]
    result[second] = assignment[first]
    return result, {first, second, newcomer}
