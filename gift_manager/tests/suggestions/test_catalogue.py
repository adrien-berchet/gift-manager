import pytest

from gift_manager.models import PermissionLevel
from gift_manager.suggestions.catalogue import CatalogueStrategy
from gift_manager.suggestions.catalogue import describe_reason
from gift_manager.suggestions.history import build_recipient_history
from gift_manager.suggestions.types import SuggestionContext
from gift_manager.suggestions.types import SuggestionReason
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import GiftTagFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def _context(user, recipient, excluded_gift_ids=frozenset(), blocked_names=frozenset()):
    history = build_recipient_history(user, recipient)
    return SuggestionContext(
        user=user,
        recipient=recipient,
        history=history,
        excluded_gift_ids=excluded_gift_ids,
        blocked_names=blocked_names,
    )


def test_liked_tags_rank_above_disliked_tags(user, share, status):
    person = PersonFactory()
    share(user, person, level=PermissionLevel.VIEWER)

    tag_a = GiftTagFactory(name="Tag A")
    tag_b = GiftTagFactory(name="Tag B")
    for t in (tag_a, tag_b):
        share(user, t, level=PermissionLevel.VIEWER)

    # History: plan with Tag A rated 5 (+2), plan with Tag B rated 2 (-1)
    gift_h1 = GiftFactory(tags=[tag_a])
    gift_h2 = GiftFactory(tags=[tag_b])
    plan_h1 = RelationFactory(
        person=person, gift=gift_h1, status=status("Given"), reaction_rating=5
    )
    plan_h2 = RelationFactory(
        person=person, gift=gift_h2, status=status("Given"), reaction_rating=2
    )
    for obj in (gift_h1, gift_h2, plan_h1, plan_h2):
        share(user, obj, level=PermissionLevel.VIEWER)

    # Candidates:
    # GA (score +2) > GAB (score +2 - 1 = +1) > 0, GB (score -1 < 0) excluded
    ga = GiftFactory(name="GA", tags=[tag_a])
    gab = GiftFactory(name="GAB", tags=[tag_a, tag_b])
    gb = GiftFactory(name="GB", tags=[tag_b])
    for g in (ga, gab, gb):
        share(user, g, level=PermissionLevel.VIEWER)

    ctx = _context(user, person, excluded_gift_ids=frozenset({gift_h1.pk, gift_h2.pk}))
    candidates = CatalogueStrategy().suggest(ctx, limit=10)
    candidate_ids = [c.gift.pk for c in candidates]

    assert candidate_ids == [ga.pk, gab.pk]
    assert gb.pk not in candidate_ids


def test_direct_history_outweighs_group_history(user, share, status):
    group = PersonGroupFactory()
    person = PersonFactory()
    person.groups.add(group)
    for obj in (group, person):
        share(user, obj, level=PermissionLevel.VIEWER)

    tag_a = GiftTagFactory(name="Tag A")
    tag_c = GiftTagFactory(name="Tag C")
    share(user, tag_a, level=PermissionLevel.VIEWER)
    share(user, tag_c, level=PermissionLevel.VIEWER)

    # Same rating 5: direct on tag A (weight 1.0 * 2 = 2.0), group on tag C (weight 0.5 * 2 = 1.0)
    gift_ha = GiftFactory(tags=[tag_a])
    gift_hc = GiftFactory(tags=[tag_c])
    direct_plan = RelationFactory(
        person=person, gift=gift_ha, status=status("Given"), reaction_rating=5
    )
    group_plan = RelationFactory(
        person=None, group=group, gift=gift_hc, status=status("Given"), reaction_rating=5
    )
    for obj in (gift_ha, gift_hc, direct_plan, group_plan):
        share(user, obj, level=PermissionLevel.VIEWER)

    candidate_a = GiftFactory(name="Candidate A", tags=[tag_a])
    candidate_c = GiftFactory(name="Candidate C", tags=[tag_c])
    share(user, candidate_a, level=PermissionLevel.VIEWER)
    share(user, candidate_c, level=PermissionLevel.VIEWER)

    ctx = _context(user, person, excluded_gift_ids=frozenset({gift_ha.pk, gift_hc.pk}))
    candidates = CatalogueStrategy().suggest(ctx, limit=10)
    assert [c.gift.pk for c in candidates] == [candidate_a.pk, candidate_c.pk]


def test_abandoned_plan_tags_are_negative(user, share, status):
    person = PersonFactory()
    share(user, person, level=PermissionLevel.VIEWER)

    tag_abandoned = GiftTagFactory(name="Abandoned Tag")
    share(user, tag_abandoned, level=PermissionLevel.VIEWER)

    gift_h = GiftFactory(tags=[tag_abandoned])
    plan_h = RelationFactory(person=person, gift=gift_h, status=status("Abandoned"))
    share(user, gift_h, level=PermissionLevel.VIEWER)
    share(user, plan_h, level=PermissionLevel.VIEWER)

    candidate = GiftFactory(tags=[tag_abandoned])
    share(user, candidate, level=PermissionLevel.VIEWER)

    ctx = _context(user, person, excluded_gift_ids=frozenset({gift_h.pk}))
    candidates = CatalogueStrategy().suggest(ctx, limit=10)
    assert candidate.pk not in [c.gift.pk for c in candidates]


def test_ancestor_tags_overlap(user, share, status):
    toys_tag = GiftTagFactory(name="Toys")
    lego_tag = GiftTagFactory(name="Lego")
    lego_tag.parent_tags.add(toys_tag)
    share(user, toys_tag, level=PermissionLevel.VIEWER)
    share(user, lego_tag, level=PermissionLevel.VIEWER)

    person = PersonFactory()
    share(user, person, level=PermissionLevel.VIEWER)

    history_gift = GiftFactory(tags=[lego_tag])
    plan = RelationFactory(
        person=person, gift=history_gift, status=status("Given"), reaction_rating=5
    )
    share(user, history_gift, level=PermissionLevel.VIEWER)
    share(user, plan, level=PermissionLevel.VIEWER)

    candidate_toys = GiftFactory(name="Toy Truck", tags=[toys_tag])
    share(user, candidate_toys, level=PermissionLevel.VIEWER)

    ctx = _context(user, person, excluded_gift_ids=frozenset({history_gift.pk}))
    candidates = CatalogueStrategy().suggest(ctx, limit=10)
    assert candidate_toys.pk in [c.gift.pk for c in candidates]


def test_interests_count_as_positive(user, share):
    books_tag = GiftTagFactory(name="Books")
    share(user, books_tag, level=PermissionLevel.VIEWER)

    person = PersonFactory()
    person.interests.add(books_tag)
    share(user, person, level=PermissionLevel.VIEWER)

    candidate_book = GiftFactory(name="Novel", tags=[books_tag])
    share(user, candidate_book, level=PermissionLevel.VIEWER)

    ctx = _context(user, person)
    candidates = CatalogueStrategy().suggest(ctx, limit=10)
    assert len(candidates) == 1
    assert candidates[0].gift.pk == candidate_book.pk
    assert candidates[0].reason.code == "interests"
    assert "Books" in candidates[0].reason.tag_names


def test_excluded_gift_ids_are_never_returned(user, share):
    tag = GiftTagFactory(name="Tag")
    share(user, tag, level=PermissionLevel.VIEWER)

    person = PersonFactory()
    person.interests.add(tag)
    share(user, person, level=PermissionLevel.VIEWER)

    gift = GiftFactory(tags=[tag])
    share(user, gift, level=PermissionLevel.VIEWER)

    ctx = _context(user, person, excluded_gift_ids=frozenset({gift.pk}))
    candidates = CatalogueStrategy().suggest(ctx, limit=10)
    assert candidates == []


def test_shared_gift_from_other_user_is_a_candidate(user, share):
    tag = GiftTagFactory(name="Tag")
    share(user, tag, level=PermissionLevel.VIEWER)

    person = PersonFactory()
    person.interests.add(tag)
    share(user, person, level=PermissionLevel.VIEWER)

    other_user = UserFactory()
    shared_gift = GiftFactory(tags=[tag])
    share(other_user, shared_gift, level=PermissionLevel.OWNER)
    share(user, shared_gift, level=PermissionLevel.VIEWER)

    ctx = _context(user, person)
    candidates = CatalogueStrategy().suggest(ctx, limit=10)
    assert shared_gift.pk in [c.gift.pk for c in candidates]


def test_unshared_gift_is_never_a_candidate(user, share):
    tag = GiftTagFactory(name="Tag")
    share(user, tag, level=PermissionLevel.VIEWER)

    person = PersonFactory()
    person.interests.add(tag)
    share(user, person, level=PermissionLevel.VIEWER)

    other_user = UserFactory()
    unshared_gift = GiftFactory(tags=[tag])
    share(other_user, unshared_gift, level=PermissionLevel.OWNER)

    ctx = _context(user, person)
    candidates = CatalogueStrategy().suggest(ctx, limit=10)
    assert unshared_gift.pk not in [c.gift.pk for c in candidates]


def test_fallback_uses_best_average_rating(user, share, status):
    person = PersonFactory()
    share(user, person, level=PermissionLevel.VIEWER)

    other_person = PersonFactory()
    share(user, other_person, level=PermissionLevel.VIEWER)

    gift_5 = GiftFactory(name="Gift 5")
    gift_4 = GiftFactory(name="Gift 4")
    gift_3 = GiftFactory(name="Gift 3")
    for g in (gift_5, gift_4, gift_3):
        share(user, g, level=PermissionLevel.VIEWER)

    plan_5 = RelationFactory(
        person=other_person, gift=gift_5, status=status("Given"), reaction_rating=5
    )
    plan_4 = RelationFactory(
        person=other_person, gift=gift_4, status=status("Given"), reaction_rating=4
    )
    plan_3 = RelationFactory(
        person=other_person, gift=gift_3, status=status("Given"), reaction_rating=3
    )
    for p in (plan_5, plan_4, plan_3):
        share(user, p, level=PermissionLevel.VIEWER)

    ctx = _context(user, person)
    candidates = CatalogueStrategy().suggest(ctx, limit=10)

    # In fallback mode (no positive tags in profile): score >= 0 and popularity >= 4
    candidate_ids = [c.gift.pk for c in candidates]
    assert candidate_ids == [gift_5.pk, gift_4.pk]
    assert gift_3.pk not in candidate_ids
    assert candidates[0].reason.code == "popular"


def test_hidden_tags_neither_score_nor_appear_in_reason(user, share, status):
    visible_a = GiftTagFactory(name="Visible A")
    hidden_h = GiftTagFactory(name="Hidden H")
    share(user, visible_a, level=PermissionLevel.VIEWER)
    # hidden_h is NOT shared with user

    person = PersonFactory()
    share(user, person, level=PermissionLevel.VIEWER)

    candidate = GiftFactory(tags=[visible_a, hidden_h])
    share(user, candidate, level=PermissionLevel.VIEWER)

    history_gift = GiftFactory(tags=[visible_a, hidden_h])
    share(user, history_gift, level=PermissionLevel.VIEWER)
    plan = RelationFactory(
        person=person, gift=history_gift, status=status("Given"), reaction_rating=4
    )
    share(user, plan, level=PermissionLevel.VIEWER)

    ctx = _context(user, person, excluded_gift_ids=frozenset({history_gift.pk}))
    candidates = CatalogueStrategy().suggest(ctx, limit=10)

    assert len(candidates) == 1
    assert candidates[0].reason.tag_names == ("Visible A",)


def test_ratings_from_plans_not_shared_are_ignored(user, share, status):
    person = PersonFactory()
    share(user, person, level=PermissionLevel.VIEWER)

    tag = GiftTagFactory(name="Tag")
    share(user, tag, level=PermissionLevel.VIEWER)

    other_user = UserFactory()
    other_person = PersonFactory()
    unshared_gift = GiftFactory(tags=[tag])
    unshared_plan = RelationFactory(
        person=other_person, gift=unshared_gift, status=status("Given"), reaction_rating=5
    )
    share(other_user, unshared_plan, level=PermissionLevel.OWNER)

    candidate = GiftFactory(tags=[tag])
    share(user, candidate, level=PermissionLevel.VIEWER)

    ctx = _context(user, person)
    candidates = CatalogueStrategy().suggest(ctx, limit=10)
    # No profile exists for user, popularity for candidate is 0
    assert candidates == []


def test_describe_reason_formats_tags_and_rating():
    reason = SuggestionReason(code="liked_tags", tag_names=("Books", "Maps"), rating=5)
    text = describe_reason(reason, recipient=None)
    assert text == "Shares tags with gifts rated 5/5: Books, Maps"

    reason_no_rating = SuggestionReason(code="liked_tags", tag_names=("Books",), rating=None)
    text_no_rating = describe_reason(reason_no_rating, recipient=None)
    assert text_no_rating == "Shares tags with past favourites: Books"

    reason_interests = SuggestionReason(code="interests", tag_names=("Art",), rating=None)
    text_interests = describe_reason(reason_interests, recipient=None)
    assert text_interests == "Matches their interests: Art"

    reason_related = SuggestionReason(code="related_liked_tags", tag_names=("Games",), rating=4)
    text_related = describe_reason(reason_related, recipient=None)
    assert text_related == "Shares tags with gifts liked by related recipients: Games"

    reason_popular = SuggestionReason(code="popular", tag_names=(), rating=4.8)
    text_popular = describe_reason(reason_popular, recipient=None)
    assert text_popular == "Rated 4.8/5 on average"
