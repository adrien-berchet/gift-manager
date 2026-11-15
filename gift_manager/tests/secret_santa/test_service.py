"""Tests of the Secret Santa service layer."""

import random
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from gift_manager.email_encoding import encode_email
from gift_manager.models import PermissionLevel
from gift_manager.models import PersonGroupPermission
from gift_manager.secret_santa import draw as draw_engine
from gift_manager.secret_santa import service
from gift_manager.secret_santa.models import MAX_PARTICIPANTS
from gift_manager.secret_santa.models import Exchange
from gift_manager.secret_santa.models import ExchangeParticipant
from gift_manager.secret_santa.service import ExchangeError
from gift_manager.tests.factories import ExchangeFactory
from gift_manager.tests.factories import ExchangeParticipantFactory
from gift_manager.tests.factories import ExclusionSetFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def seeded(seed: int) -> random.Random:
    return random.Random(seed)  # noqa: S311 - reproducible tests, not a secret


@pytest.fixture
def organizer():
    return UserFactory(first_name="Olivia", last_name="Organizer")


@pytest.fixture
def exchange(organizer):
    return ExchangeFactory(organizer=organizer)


def add_people(exchange, *names):
    return [
        service.add_participant(exchange, name=name, email=f"{name}@example.com") for name in names
    ]


def pairings(exchange):
    return dict(exchange.participants.values_list("pk", "gives_to_id"))


def test_create_exchange_copies_the_organizer_currency(organizer):
    organizer.profile.currency = "CHF"
    organizer.profile.save()

    exchange = service.create_exchange(
        organizer, name="Family", exchange_date=timezone.localdate(), budget=Decimal(20)
    )

    assert exchange.currency == "CHF"
    assert exchange.status == Exchange.Status.DRAFT
    assert not exchange.participants.exists()


def test_organizer_taking_part_becomes_a_linked_participant(organizer):
    exchange = service.create_exchange(
        organizer, name="Family", exchange_date=timezone.localdate(), organizer_takes_part=True
    )

    participant = exchange.participants.get()
    assert participant.name == "Olivia Organizer"
    assert participant.linked_account == organizer
    assert participant.email == organizer.profile.email


def test_organizer_without_full_name_takes_part_under_their_username():
    organizer = UserFactory(first_name="", last_name="", username="santa_boss")
    exchange = service.create_exchange(
        organizer, name="Office", exchange_date=timezone.localdate(), organizer_takes_part=True
    )
    assert exchange.participants.get().name == "santa_boss"


def test_add_participant_refuses_a_duplicate_name_ignoring_case(exchange):
    service.add_participant(exchange, name="Anna")

    with pytest.raises(ExchangeError, match="same name"):
        service.add_participant(exchange, name="  aNNa ")

    assert exchange.participants.count() == 1


def test_add_participant_without_email(exchange):
    participant = service.add_participant(exchange, name="Ben", email="")
    assert participant.email_address is None


def test_add_participant_refuses_an_empty_name(exchange):
    with pytest.raises(ExchangeError):
        service.add_participant(exchange, name="   ")


def test_add_participant_refuses_the_101st(exchange):
    ExchangeParticipant.objects.bulk_create(
        ExchangeParticipant(exchange=exchange, name=f"P{i}", token=f"token-{i}")
        for i in range(MAX_PARTICIPANTS)
    )

    with pytest.raises(ExchangeError, match="at most 100"):
        service.add_participant(exchange, name="One too many")


def test_import_persons_copies_name_email_and_account_link(exchange, organizer):
    account = UserFactory()
    person = PersonFactory(
        first_name="Chloe",
        family_name="Martin",
        email_address=encode_email("chloe@example.com"),
        account=account,
        owner=organizer,
    )

    assert service.import_persons(exchange, organizer, [person]) == (1, 0)

    participant = exchange.participants.get()
    assert participant.name == "Chloe Martin"
    assert participant.email == "chloe@example.com"
    assert participant.source_person == person
    assert participant.linked_account == account


def test_import_skips_people_already_present(exchange, organizer):
    account = UserFactory()
    person = PersonFactory(first_name="Dan", family_name="One", account=account, owner=organizer)
    same_account = PersonFactory(
        first_name="Daniel", family_name="One", account=account, owner=organizer
    )
    same_name = PersonFactory(first_name="dan", family_name="ONE", owner=organizer)

    result = service.import_persons(exchange, organizer, [person, person, same_account, same_name])

    assert result == (1, 3)
    assert exchange.participants.count() == 1


def test_import_skips_a_typed_participant_with_the_same_name(exchange, organizer):
    service.add_participant(exchange, name="Eve Adams")
    person = PersonFactory(first_name="Eve", family_name="Adams", owner=organizer)

    assert service.import_persons(exchange, organizer, [person]) == (0, 1)


def test_import_ignores_persons_the_organizer_cannot_access(exchange, organizer):
    stranger = PersonFactory()

    assert service.import_persons(exchange, organizer, [stranger]) == (0, 0)
    assert not exchange.participants.exists()


def test_import_refuses_to_go_over_the_limit(exchange, organizer):
    ExchangeParticipant.objects.bulk_create(
        ExchangeParticipant(exchange=exchange, name=f"P{i}", token=f"token-{i}")
        for i in range(MAX_PARTICIPANTS - 1)
    )
    persons = PersonFactory.create_batch(2, owner=organizer)

    with pytest.raises(ExchangeError, match="at most 100"):
        service.import_persons(exchange, organizer, persons)

    assert exchange.participants.count() == MAX_PARTICIPANTS - 1


def test_import_group_includes_nested_members_once(exchange, organizer):
    parent = PersonGroupFactory()
    PersonGroupPermission.objects.create(
        user=organizer,
        group=parent,
        permission_type=PermissionLevel.VIEWER,
        inherit_permissions=True,
    )
    child = PersonGroupFactory()
    child.parent_groups.add(parent)
    in_both = PersonFactory(owner=organizer, groups=[parent, child])
    in_child = PersonFactory(owner=organizer, groups=[child])

    assert service.import_group(exchange, organizer, parent) == (2, 0)
    assert set(exchange.participants.values_list("source_person", flat=True)) == {
        in_both.pk,
        in_child.pk,
    }


def test_import_group_leaves_out_nested_groups_the_organizer_cannot_see(exchange, organizer):
    parent = PersonGroupFactory(shared_with=[organizer])
    hidden_child = PersonGroupFactory()
    hidden_child.parent_groups.add(parent)
    PersonFactory(owner=organizer, groups=[hidden_child])

    assert service.import_group(exchange, organizer, parent) == (0, 0)


def test_import_group_the_organizer_cannot_access_is_refused(exchange, organizer):
    group = PersonGroupFactory()
    PersonFactory(owner=organizer, groups=[group])

    with pytest.raises(ExchangeError):
        service.import_group(exchange, organizer, group)

    assert not exchange.participants.exists()


def test_forbidden_pairs_cover_every_pair_of_a_set_in_both_directions(exchange):
    a, b, c, d = add_people(exchange, "A", "B", "C", "D")
    ExclusionSetFactory(exchange=exchange, participants=[a, b, c])
    ExclusionSetFactory(exchange=exchange, participants=[c, d])

    assert service.forbidden_pairs(exchange) == {
        (a.pk, b.pk),
        (b.pk, a.pk),
        (a.pk, c.pk),
        (c.pk, a.pk),
        (b.pk, c.pk),
        (c.pk, b.pk),
        (c.pk, d.pk),
        (d.pk, c.pk),
    }


def test_exclusion_set_needs_two_participants_of_the_same_exchange(exchange):
    a, b = add_people(exchange, "A", "B")
    foreigner = ExchangeParticipantFactory()

    with pytest.raises(ExchangeError, match="at least two"):
        service.save_exclusion_set(exchange, name="Alone", participants=[a])
    with pytest.raises(ExchangeError, match="at least two"):
        service.save_exclusion_set(exchange, name="Mixed", participants=[a, foreigner])

    exclusion_set = service.save_exclusion_set(exchange, name="Couple", participants=[a, b])
    assert set(exclusion_set.participants.all()) == {a, b}


def test_exclusion_set_can_be_updated_and_deleted(exchange):
    a, b, c = add_people(exchange, "A", "B", "C")
    exclusion_set = service.save_exclusion_set(exchange, name="Couple", participants=[a, b])

    service.save_exclusion_set(
        exchange, name="Trio", participants=[a, b, c], instance=exclusion_set
    )
    exclusion_set.refresh_from_db()
    assert exclusion_set.name == "Trio"
    assert exclusion_set.participants.count() == 3

    service.delete_exclusion_set(exclusion_set)
    assert not exchange.exclusion_sets.exists()


def test_run_draw_assigns_everyone_and_marks_the_exchange_drawn(exchange):
    exchange.no_mutual_draw = True
    exchange.save()
    people = add_people(exchange, "A", "B", "C", "D", "E", "F")
    ExclusionSetFactory(exchange=exchange, participants=people[:2])

    service.run_draw(exchange, rng=seeded(1))

    exchange.refresh_from_db()
    assert exchange.status == Exchange.Status.DRAWN
    assert exchange.drawn_at is not None
    assert draw_engine.is_valid(
        pairings(exchange),
        [p.pk for p in people],
        service.forbidden_pairs(exchange),
        no_mutual=True,
    )


def test_run_draw_with_impossible_exclusions_saves_nothing(exchange):
    people = add_people(exchange, "A", "B", "C", "D", "E")
    ExclusionSetFactory(exchange=exchange, participants=people[:3])

    with pytest.raises(ExchangeError, match="No draw is possible"):
        service.run_draw(exchange)

    exchange.refresh_from_db()
    assert exchange.status == Exchange.Status.DRAFT
    assert not exchange.participants.filter(gives_to__isnull=False).exists()


def test_run_draw_needs_three_participants(exchange):
    add_people(exchange, "A", "B")

    with pytest.raises(ExchangeError, match="At least 3"):
        service.run_draw(exchange)


def test_redraw_replaces_every_pairing_in_one_go(exchange):
    people = add_people(exchange, *"ABCDEFGH")
    service.run_draw(exchange, rng=seeded(1))
    exchange.refresh_from_db()
    first, first_at = pairings(exchange), exchange.drawn_at

    service.run_draw(exchange, rng=seeded(2))

    exchange.refresh_from_db()
    second = pairings(exchange)
    assert second != first
    assert exchange.drawn_at > first_at
    assert draw_engine.is_valid(second, [p.pk for p in people], set(), no_mutual=False)


def test_failed_redraw_keeps_the_previous_pairings(exchange, monkeypatch):
    add_people(exchange, "A", "B", "C", "D")
    service.run_draw(exchange, rng=seeded(1))
    before = pairings(exchange)

    def give_up(*args, **kwargs):
        raise draw_engine.NoDrawPossible(draw_engine.GAVE_UP)

    monkeypatch.setattr(draw_engine, "draw", give_up)
    with pytest.raises(ExchangeError, match="No draw was found"):
        service.run_draw(exchange)

    assert pairings(exchange) == before


def test_participants_and_sets_are_frozen_after_the_draw_except_name_and_email(exchange):
    a, b, c, _d = add_people(exchange, "A", "B", "C", "D")
    exclusion_set = service.save_exclusion_set(exchange, name="Couple", participants=[a, b])
    service.run_draw(exchange, rng=seeded(1))
    frozen = "The draw is done"

    with pytest.raises(ExchangeError, match=frozen):
        service.add_participant(exchange, name="Late")
    with pytest.raises(ExchangeError, match=frozen):
        service.remove_participant(c)
    with pytest.raises(ExchangeError, match=frozen):
        service.save_exclusion_set(exchange, name="Other", participants=[a, c])
    with pytest.raises(ExchangeError, match=frozen):
        service.delete_exclusion_set(exclusion_set)
    with pytest.raises(ExchangeError, match=frozen):
        service.update_exchange(
            exchange,
            name=exchange.name,
            exchange_date=exchange.exchange_date,
            budget=exchange.budget,
            guidelines="",
            no_mutual_draw=True,
        )

    service.update_participant(c, name="Charlie", email="charlie@example.com")
    c.refresh_from_db()
    assert (c.name, c.email) == ("Charlie", "charlie@example.com")
    assert c.gives_to_id is not None


def test_closed_exchange_refuses_every_change(exchange):
    (a,) = add_people(exchange, "A")
    Exchange.objects.filter(pk=exchange.pk).update(status=Exchange.Status.CLOSED)

    with pytest.raises(ExchangeError, match="closed"):
        service.update_participant(a, name="B", email="")
    with pytest.raises(ExchangeError, match="closed"):
        service.run_draw(exchange)
    with pytest.raises(ExchangeError, match="closed"):
        service.add_participant(exchange, name="C")


def test_update_participant_email_clears_the_send_again_cooldown(exchange):
    (a,) = add_people(exchange, "A")
    ExchangeParticipant.objects.filter(pk=a.pk).update(last_emailed_at=timezone.now())
    a.refresh_from_db()
    token = a.token

    service.update_participant(a, name="A", email="A@example.com")
    a.refresh_from_db()
    assert a.last_emailed_at is not None  # same address

    service.update_participant(a, name="A", email="new@example.com")
    a.refresh_from_db()
    assert a.last_emailed_at is None
    assert a.token == token


def test_renaming_to_an_existing_name_is_refused_after_the_draw_too(exchange):
    a, _b, _c = add_people(exchange, "A", "B", "C")
    service.run_draw(exchange, rng=seeded(1))

    with pytest.raises(ExchangeError, match="same name"):
        service.update_participant(a, name="b", email="")


def test_remove_participant_before_the_draw(exchange):
    a, b = add_people(exchange, "A", "B")
    service.save_exclusion_set(exchange, name="Couple", participants=[a, b])

    service.remove_participant(a)

    assert list(exchange.participants.all()) == [b]


def test_regenerate_token(exchange):
    (a,) = add_people(exchange, "A")
    old = a.token

    service.regenerate_token(a)

    assert not ExchangeParticipant.objects.filter(token=old).exists()


def test_delete_exchange_removes_everything(exchange):
    people = add_people(exchange, "A", "B", "C", "D")
    service.save_exclusion_set(exchange, name="Couple", participants=people[:2])
    service.run_draw(exchange, rng=seeded(1))

    service.delete_exchange(exchange)

    assert not Exchange.objects.exists()
    assert not ExchangeParticipant.objects.exists()


def test_organized_by_returns_only_my_exchanges(exchange, organizer):
    ExchangeFactory()

    assert list(service.organized_by(organizer)) == [exchange]


def test_participants_without_pairings_does_not_load_gives_to(exchange):
    add_people(exchange, "A", "B", "C")
    service.run_draw(exchange, rng=seeded(1))

    participants = list(service.participants_without_pairings(exchange))

    assert all("gives_to_id" in p.get_deferred_fields() for p in participants)


def test_declined_participants_are_left_out_of_the_draw(exchange):
    people = add_people(exchange, "A", "B", "C", "D")
    ExchangeParticipant.objects.filter(pk=people[3].pk).update(declined=True)

    service.run_draw(exchange, rng=seeded(1))

    result = pairings(exchange)
    assert result[people[3].pk] is None
    assert people[3].pk not in result.values()
    assert draw_engine.is_valid(
        {k: v for k, v in result.items() if k != people[3].pk},
        [p.pk for p in people[:3]],
        set(),
        no_mutual=False,
    )


def test_too_few_after_declines(exchange):
    people = add_people(exchange, "A", "B", "C")
    ExchangeParticipant.objects.filter(pk=people[0].pk).update(declined=True)

    with pytest.raises(ExchangeError, match="At least 3"):
        service.run_draw(exchange)


def test_declined_member_of_an_exclusion_set_is_ignored(exchange):
    a, b, _c, d, _e = add_people(exchange, "A", "B", "C", "D", "E")
    service.save_exclusion_set(exchange, name="Trio", participants=[a, b, d])
    ExchangeParticipant.objects.filter(pk=d.pk).update(declined=True)

    for seed in range(10):
        service.run_draw(exchange, rng=seeded(seed))
        result = pairings(exchange)
        assert result[d.pk] is None
        assert d.pk not in result.values()
        assert result[a.pk] != b.pk
        assert result[b.pk] != a.pk


def test_put_back_only_before_the_draw(exchange):
    a, _b, _c, d = add_people(exchange, "A", "B", "C", "D")
    ExchangeParticipant.objects.filter(pk=d.pk).update(declined=True)
    d.refresh_from_db()

    service.put_back(d)
    d.refresh_from_db()
    assert not d.declined

    service.run_draw(exchange, rng=seeded(1))
    with pytest.raises(ExchangeError, match="The draw is done"):
        service.put_back(a)


# ---------------------------------------------------------------------------
# Slice 3: starting from a previous exchange
# ---------------------------------------------------------------------------


def copy_of(previous, **kwargs):
    return service.copy_exchange(
        previous,
        previous.organizer,
        name="Next year",
        exchange_date=previous.exchange_date,
        **kwargs,
    )


def test_copy_copies_participants_and_sets(exchange):
    a, b, c, _d = add_people(exchange, "A", "B", "C", "D")
    service.save_exclusion_set(exchange, name="Couple", participants=[a, b])

    copy = copy_of(exchange)

    assert copy.previous_exchange == exchange
    assert copy.no_repeat_draw
    names = dict(copy.participants.values_list("name", "previous_participant__name"))
    assert names == {"A": "A", "B": "B", "C": "C", "D": "D"}
    (copied_set,) = copy.exclusion_sets.all()
    assert copied_set.name == "Couple"
    assert {p.name for p in copied_set.participants.all()} == {"A", "B"}
    new_c = copy.participants.get(name="C")
    assert new_c.token != c.token
    assert new_c.email == c.email


def test_copy_keeps_emails_stopped_and_linked_accounts(exchange, organizer):
    person_account = UserFactory()
    person = PersonFactory(
        first_name="Pat", family_name="", account=person_account, owner=organizer
    )
    service.import_persons(exchange, organizer, [person])
    self_account = UserFactory()
    self_attached = ExchangeParticipantFactory(
        exchange=exchange,
        name="Self",
        linked_account=self_account,
        account_attached_by_participant=True,
        wishlist_confirmed=True,
        emails_stopped=True,
        declined=True,
        note_for_santa="note",
    )
    ExchangeParticipantFactory(exchange=exchange, name="Olivia", linked_account=organizer)

    copy = copy_of(exchange)

    assert copy.participants.get(name="Pat").linked_account == person_account
    assert copy.participants.get(name="Olivia").linked_account == organizer
    new_self = copy.participants.get(name="Self")
    # The participant linked their account themselves: the copy keeps it, so they need not
    # attach it again. Like an imported account, it only shows the exchange once invited or
    # drawn, and nothing of their wishlist is shared until they confirm for this exchange.
    assert new_self.linked_account == self_account
    assert not new_self.account_attached_by_participant
    assert not new_self.wishlist_confirmed
    assert not new_self.shared_wishes.exists()
    assert new_self.emails_stopped
    assert not new_self.declined
    assert new_self.note_for_santa == ""
    assert new_self.previous_participant == self_attached


def test_copy_links_an_account_once_preferring_the_participant_who_attached_it(exchange, organizer):
    # Pat was imported before their person record was linked to an account; since then the
    # record was linked to the account Sam attached to their own participation.
    person = PersonFactory(first_name="Pat", family_name="", owner=organizer)
    service.import_persons(exchange, organizer, [person])
    account = UserFactory()
    person.account = account
    person.save(update_fields=["account"])
    ExchangeParticipantFactory(
        exchange=exchange,
        name="Sam",
        linked_account=account,
        account_attached_by_participant=True,
    )

    copy = copy_of(exchange)

    assert copy.participants.get(name="Sam").linked_account == account
    assert copy.participants.get(name="Pat").linked_account is None


def test_copy_drops_a_set_left_with_one_member(exchange):
    a, b, _c = add_people(exchange, "A", "B", "C")
    service.save_exclusion_set(exchange, name="Couple", participants=[a, b])
    ExchangeParticipant.objects.filter(pk=b.pk).delete()

    assert not copy_of(exchange).exclusion_sets.exists()


def test_no_repeat_forbids_last_years_pairs(exchange):
    add_people(exchange, "A", "B", "C", "D", "E")
    service.run_draw(exchange, rng=seeded(1))
    before = {
        (giver, recipient)
        for giver, recipient in exchange.participants.values_list("name", "gives_to__name")
    }

    copy = copy_of(exchange)
    forbidden, _ = service.draw_rules(copy)
    names = dict(copy.participants.values_list("pk", "name"))
    assert {(names[g], names[r]) for g, r in forbidden} == before

    for seed in range(10):
        service.run_draw(copy, rng=seeded(seed))
        after = set(copy.participants.values_list("name", "gives_to__name"))
        assert not after & before


def test_no_repeat_off_or_without_history_forbids_nothing(exchange):
    add_people(exchange, "A", "B", "C")
    copy = copy_of(exchange)  # the previous exchange was never drawn
    assert service.draw_rules(copy) == (set(), False)

    service.run_draw(exchange, rng=seeded(1))
    assert copy_of(exchange, no_repeat_draw=False).no_repeat_draw is False
    assert service.draw_rules(copy_of(exchange, no_repeat_draw=False))[0] == set()


def test_no_repeat_survives_a_deleted_previous_exchange(exchange):
    add_people(exchange, "A", "B", "C", "D")
    service.run_draw(exchange, rng=seeded(1))
    copy = copy_of(exchange)

    exchange.delete()
    copy.refresh_from_db()

    assert service.draw_rules(copy)[0] == set()
    service.run_draw(copy, rng=seeded(2))


def test_no_repeat_switch_only_changes_before_the_draw(exchange):
    add_people(exchange, "A", "B", "C")
    copy = copy_of(exchange)
    fields = {
        "name": copy.name,
        "exchange_date": copy.exchange_date,
        "budget": None,
        "guidelines": "",
        "no_mutual_draw": False,
    }
    service.update_exchange(copy, no_repeat_draw=False, **fields)
    copy.refresh_from_db()
    assert not copy.no_repeat_draw

    service.run_draw(copy, rng=seeded(1))
    with pytest.raises(ExchangeError, match="The draw is done"):
        service.update_exchange(copy, no_repeat_draw=True, **fields)


# ---------------------------------------------------------------------------
# Slice 3: repairs after the draw
# ---------------------------------------------------------------------------


def drawn_people(exchange, *names, seed=1):
    people = add_people(exchange, *names)
    service.run_draw(exchange, rng=seeded(seed))
    return people


def test_remove_and_repair_changes_one_pairing_and_returns_the_santa(exchange):
    people = drawn_people(exchange, "A", "B", "C", "D", "E")
    before = pairings(exchange)
    removed = people[2]
    santa_pk = next(g for g, r in before.items() if r == removed.pk)
    ExchangeParticipant.objects.update(last_emailed_at=timezone.now())

    changed = service.remove_and_repair(removed)

    after = pairings(exchange)
    assert [p.pk for p in changed] == [santa_pk]
    assert after[santa_pk] == before[removed.pk]
    assert all(after[g] == r for g, r in before.items() if g not in (santa_pk, removed.pk))
    assert ExchangeParticipant.objects.get(pk=santa_pk).last_emailed_at is None
    assert not ExchangeParticipant.objects.filter(pk=removed.pk).exists()


def test_remove_from_a_mutual_pair_is_refused_and_nothing_changes(exchange):
    a, b, c, d, e = add_people(exchange, "A", "B", "C", "D", "E")
    for giver, recipient in ((a, b), (b, a), (c, d), (d, e), (e, c)):
        ExchangeParticipant.objects.filter(pk=giver.pk).update(gives_to=recipient)
    Exchange.objects.filter(pk=exchange.pk).update(status=Exchange.Status.DRAWN)
    before = pairings(exchange)

    with pytest.raises(ExchangeError, match="No repair keeps every rule"):
        service.remove_and_repair(b)

    assert pairings(exchange) == before


def test_remove_below_three_is_refused(exchange):
    people = drawn_people(exchange, "A", "B", "C")
    with pytest.raises(ExchangeError, match="At least 3"):
        service.remove_and_repair(people[0])
    with pytest.raises(ExchangeError, match="At least 3"):
        service.remove_and_redraw(people[0])
    assert exchange.participants.count() == 3


def test_remove_a_declined_participant_after_the_draw(exchange):
    people = add_people(exchange, "A", "B", "C", "D")
    ExchangeParticipant.objects.filter(pk=people[3].pk).update(declined=True)
    service.run_draw(exchange, rng=seeded(1))
    before = pairings(exchange)

    assert service.remove_and_repair(people[3]) == []
    before.pop(people[3].pk)
    assert pairings(exchange) == before


def test_remove_and_redraw_rolls_back_on_failure(exchange, monkeypatch):
    people = drawn_people(exchange, "A", "B", "C", "D")
    before = pairings(exchange)

    def give_up(*args, **kwargs):
        raise draw_engine.NoDrawPossible(draw_engine.GAVE_UP)

    monkeypatch.setattr(draw_engine, "draw", give_up)
    with pytest.raises(ExchangeError):
        service.remove_and_redraw(people[0])

    assert pairings(exchange) == before


def test_remove_and_redraw(exchange):
    people = drawn_people(exchange, "A", "B", "C", "D")
    changed = service.remove_and_redraw(people[0])
    assert len(changed) == 3
    assert draw_engine.is_valid(
        pairings(exchange), [p.pk for p in people[1:]], set(), no_mutual=False
    )


def test_add_and_repair_changes_two_pairings(exchange):
    people = drawn_people(exchange, "A", "B", "C", "D", "E")
    before = pairings(exchange)

    changed = service.add_and_repair(exchange, name="Late", email="late@example.com", rng=seeded(3))

    late = exchange.participants.get(name="Late")
    after = pairings(exchange)
    assert late.pk in {p.pk for p in changed}
    assert len(changed) == 3
    assert sum(after[g] != r for g, r in before.items()) == 2
    assert draw_engine.is_valid(after, [p.pk for p in people] + [late.pk], set(), no_mutual=False)


def test_add_and_repair_puts_back_a_declined_participant(exchange):
    people = add_people(exchange, "A", "B", "C", "D", "E")
    ExchangeParticipant.objects.filter(pk=people[4].pk).update(declined=True)
    service.run_draw(exchange, rng=seeded(1))

    service.add_and_repair(exchange, participant=people[4], rng=seeded(2))

    late = ExchangeParticipant.objects.get(pk=people[4].pk)
    assert not late.declined
    assert late.gives_to_id is not None
    with pytest.raises(ExchangeError, match="already takes part"):
        service.add_and_repair(exchange, participant=people[0])


def test_add_and_repair_joins_the_chosen_sets(exchange):
    a, b, _c, _d, _e = drawn_people(exchange, "A", "B", "C", "D", "E")
    household = ExclusionSetFactory(exchange=exchange, participants=[a, b])
    service.add_and_repair(exchange, name="Late", exclusion_sets=[household], rng=seeded(1))

    late = exchange.participants.get(name="Late")
    assert late in household.participants.all()
    assert late.gives_to_id not in (a.pk, b.pk)
    assert pairings(exchange)[a.pk] != late.pk
    assert pairings(exchange)[b.pk] != late.pk


def test_impossible_insertion_saves_nothing(exchange):
    people = drawn_people(exchange, "A", "B", "C")
    everyone = ExclusionSetFactory(exchange=exchange, participants=people)
    before = pairings(exchange)

    with pytest.raises(ExchangeError, match="Redraw everything instead"):
        service.add_and_repair(exchange, name="Late", exclusion_sets=[everyone])

    assert not exchange.participants.filter(name="Late").exists()
    assert pairings(exchange) == before


def test_add_and_redraw(exchange):
    drawn_people(exchange, "A", "B", "C")
    changed = service.add_and_redraw(exchange, name="Late", rng=seeded(4))
    assert len(changed) == 4
    assert exchange.participants.get(name="Late").gives_to_id is not None


def test_repairs_respect_no_repeat(exchange):
    drawn_people(exchange, "A", "B", "C", "D", "E", "F")
    copy = copy_of(exchange)
    service.run_draw(copy, rng=seeded(2))
    forbidden, _ = service.draw_rules(copy)
    for seed in range(5):
        service.add_and_repair(copy, name=f"Late {seed}", rng=seeded(seed))
        assert not set(pairings(copy).items()) & forbidden


def test_repairs_keep_wishes_and_notes(exchange):
    people = drawn_people(exchange, "A", "B", "C", "D", "E")
    ExchangeParticipant.objects.filter(pk=people[1].pk).update(note_for_santa="Size M")
    service.add_and_repair(exchange, name="Late", rng=seeded(1))
    service.remove_and_repair(exchange.participants.get(name="Late"))
    assert ExchangeParticipant.objects.get(pk=people[1].pk).note_for_santa == "Size M"


def test_repairs_need_a_drawn_exchange(exchange):
    people = add_people(exchange, "A", "B", "C", "D")
    with pytest.raises(ExchangeError, match="not been done"):
        service.remove_and_repair(people[0])
    with pytest.raises(ExchangeError, match="not been done"):
        service.add_and_repair(exchange, name="Late")


def test_copy_skips_a_person_no_longer_shared(exchange, organizer):
    from gift_manager.models import PersonPermission

    account = UserFactory()
    person = PersonFactory(first_name="Pat", family_name="", account=account, owner=organizer)
    service.import_persons(exchange, organizer, [person])
    PersonPermission.objects.filter(person=person, user=organizer).delete()

    copied = copy_of(exchange).participants.get(name="Pat")

    assert copied.source_person is None
    assert copied.linked_account is None


# ---------------------------------------------------------------------------
# Slice 3: closing
# ---------------------------------------------------------------------------


def test_close_only_drawn_and_from_the_date(exchange):
    add_people(exchange, "A", "B", "C")
    with pytest.raises(ExchangeError, match="Only a drawn exchange"):
        service.close_exchange(exchange, reveal=False, today=exchange.exchange_date)

    service.run_draw(exchange, rng=seeded(1))
    with pytest.raises(ExchangeError, match="can be closed from"):
        service.close_exchange(
            exchange, reveal=False, today=exchange.exchange_date - timedelta(days=1)
        )

    service.close_exchange(exchange, reveal=True, today=exchange.exchange_date)
    exchange.refresh_from_db()
    assert exchange.status == Exchange.Status.CLOSED
    assert exchange.pairings_revealed
    assert exchange.closed_at is not None


def test_close_twice_is_refused(exchange):
    add_people(exchange, "A", "B", "C")
    service.run_draw(exchange, rng=seeded(1))
    service.close_exchange(exchange, reveal=False, today=exchange.exchange_date)

    with pytest.raises(ExchangeError, match="closed"):
        service.close_exchange(exchange, reveal=True, today=exchange.exchange_date)
    exchange.refresh_from_db()
    assert not exchange.pairings_revealed


def test_close_keeps_pairings(exchange):
    add_people(exchange, "A", "B", "C")
    service.run_draw(exchange, rng=seeded(1))
    before = pairings(exchange)

    service.close_exchange(exchange, reveal=False, today=exchange.exchange_date)

    assert pairings(exchange) == before
