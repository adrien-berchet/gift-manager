"""Tests of the Secret Santa draw engine (pure functions, no database)."""

import random
import time

import pytest
from hypothesis import given
from hypothesis import settings
from hypothesis import strategies as st

from gift_manager.secret_santa.draw import MIN_PARTICIPANTS
from gift_manager.secret_santa.draw import NoDrawPossible
from gift_manager.secret_santa.draw import draw
from gift_manager.secret_santa.draw import is_valid


def seeded(seed: int) -> random.Random:
    """Return a reproducible generator; draws in production use ``SystemRandom``."""
    return random.Random(seed)  # noqa: S311 - reproducible tests, not a secret


def test_result_is_a_permutation_without_self_draw():
    result = draw(range(10), rng=seeded(1))
    assert sorted(result) == sorted(result.values()) == list(range(10))
    assert all(giver != recipient for giver, recipient in result.items())


def test_forbidden_pairs_are_respected():
    forbidden = {(0, 1), (1, 0), (2, 3)}
    for seed in range(50):
        result = draw(range(6), forbidden, rng=seeded(seed))
        assert not any((giver, recipient) in forbidden for giver, recipient in result.items())


def test_no_mutual_draw():
    for seed in range(50):
        result = draw(range(5), no_mutual=True, rng=seeded(seed))
        assert all(result[result[giver]] != giver for giver in result)


@pytest.mark.parametrize("count", [0, 1, 2])
def test_too_few_participants(count):
    assert count < MIN_PARTICIPANTS
    with pytest.raises(NoDrawPossible) as error:
        draw(range(count))
    assert error.value.reason == "too_few"


def test_set_larger_than_half_is_impossible_and_fast():
    members = range(60)  # 31 people who must not draw each other
    forbidden = {(a, b) for a in range(31) for b in range(31) if a != b}
    start = time.monotonic()
    with pytest.raises(NoDrawPossible) as error:
        draw(members, forbidden)
    assert error.value.reason == "impossible"
    assert time.monotonic() - start < 1


def test_three_people_with_no_mutual_is_a_cycle():
    result = draw([1, 2, 3], no_mutual=True, rng=seeded(3))
    assert result[result[result[1]]] == 1


def test_three_people_one_couple_no_mutual_is_impossible():
    # 1 and 2 exclude each other: both must give to 3, impossible
    with pytest.raises(NoDrawPossible) as error:
        draw([1, 2, 3], {(1, 2), (2, 1)}, no_mutual=True)
    assert error.value.reason == "impossible"


def test_impossible_only_because_of_no_mutual_is_reported():
    # Without the switch 1 <-> 2 and 3 <-> 4 is the only draw; with it, nothing is left
    forbidden = {(1, 3), (1, 4), (2, 3), (2, 4), (3, 1), (3, 2), (4, 1), (4, 2)}
    assert draw([1, 2, 3, 4], forbidden) == {1: 2, 2: 1, 3: 4, 4: 3}
    with pytest.raises(NoDrawPossible) as error:
        draw([1, 2, 3, 4], forbidden, no_mutual=True)
    assert error.value.reason == "impossible"


def test_hundred_participants_with_households_is_fast():
    households = [range(i, i + 4) for i in range(0, 100, 4)]
    forbidden = {(a, b) for h in households for a in h for b in h if a != b}
    start = time.monotonic()
    result = draw(range(100), forbidden, no_mutual=True, rng=seeded(7))
    assert time.monotonic() - start < 2
    assert is_valid(result, range(100), forbidden, no_mutual=True)


def test_hundred_participants_with_a_dense_impossible_set_is_fast():
    forbidden = {(a, b) for a in range(51) for b in range(51) if a != b}
    start = time.monotonic()
    with pytest.raises(NoDrawPossible) as error:
        draw(range(100), forbidden, no_mutual=True)
    assert error.value.reason == "impossible"
    assert time.monotonic() - start < 1


def test_exactly_half_in_one_set_is_possible():
    forbidden = {(a, b) for a in range(5) for b in range(5) if a != b}
    for seed in range(20):
        result = draw(range(10), forbidden, no_mutual=True, rng=seeded(seed))
        assert is_valid(result, range(10), forbidden, no_mutual=True)


def test_step_budget_gives_up_cleanly():
    with pytest.raises(NoDrawPossible) as error:
        draw(range(30), no_mutual=True, max_steps=0)
    assert error.value.reason == "gave_up"


def test_different_seeds_give_different_draws():
    draws = {tuple(sorted(draw(range(8), rng=seeded(s)).items())) for s in range(20)}
    assert len(draws) > 1


def test_default_rng_works():
    assert is_valid(draw(range(5)), range(5), (), no_mutual=False)


def test_forbidden_pairs_outside_the_participants_are_ignored():
    result = draw([1, 2, 3], {(1, 99), (99, 1)}, rng=seeded(0))
    assert is_valid(result, [1, 2, 3], set(), no_mutual=False)


@pytest.mark.parametrize(
    "assignment",
    [
        {1: 2, 2: 3},  # someone missing
        {1: 1, 2: 3, 3: 2},  # self draw
        {1: 2, 2: 2, 3: 1},  # two givers for one recipient
        {1: 2, 2: 3, 3: 1, 4: 1},  # unknown giver
    ],
)
def test_is_valid_rejects_broken_assignments(assignment):
    assert not is_valid(assignment, [1, 2, 3], set(), no_mutual=False)


def test_is_valid_checks_forbidden_and_mutual():
    assert not is_valid({1: 2, 2: 3, 3: 1}, [1, 2, 3], {(1, 2)}, no_mutual=False)
    assert not is_valid({1: 2, 2: 1, 3: 4, 4: 3}, [1, 2, 3, 4], set(), no_mutual=True)
    assert is_valid({1: 2, 2: 1, 3: 4, 4: 3}, [1, 2, 3, 4], set(), no_mutual=False)


@settings(max_examples=60, deadline=None)
@given(
    data=st.data(),
    count=st.integers(min_value=3, max_value=25),
    no_mutual=st.booleans(),
)
def test_any_result_is_valid(data, count, no_mutual):
    participants = list(range(count))
    pairs = [(a, b) for a in participants for b in participants if a != b]
    forbidden = set(data.draw(st.lists(st.sampled_from(pairs), max_size=count * 3)))
    reason = None
    try:
        result = draw(participants, forbidden, no_mutual=no_mutual, rng=seeded(0))
    except NoDrawPossible as error:
        reason = error.reason
    if reason is not None:
        assert reason in {"impossible", "gave_up"}
    else:
        assert is_valid(result, participants, forbidden, no_mutual=no_mutual)
