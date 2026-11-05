import pytest

from gift_manager.models import GiftTag
from gift_manager.models import PermissionLevel
from gift_manager.suggestions.history import build_recipient_history
from gift_manager.suggestions.history import tag_ancestor_map
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import GiftTagFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_tag_ancestor_map_survives_cycle():
    tag_a = GiftTagFactory(name="Tag A")
    tag_b = GiftTagFactory(name="Tag B")

    # Insert a cycle directly in the through table
    through = GiftTag.parent_tags.through
    through.objects.create(from_gifttag_id=tag_a.pk, to_gifttag_id=tag_b.pk)
    through.objects.create(from_gifttag_id=tag_b.pk, to_gifttag_id=tag_a.pk)

    ancestors = tag_ancestor_map({tag_a.pk, tag_b.pk})
    assert ancestors[tag_a.pk] == frozenset({tag_a.pk, tag_b.pk})
    assert ancestors[tag_b.pk] == frozenset({tag_a.pk, tag_b.pk})


def test_person_history_includes_own_and_group_plans(user, share, status):
    parent_group = PersonGroupFactory(name="Grandparents")
    group = PersonGroupFactory(name="Parents")
    group.parent_groups.add(parent_group)

    person = PersonFactory(first_name="Alice")
    person.groups.add(group)

    own_plan = RelationFactory(person=person, gift=GiftFactory(), status=status("Given"))
    group_plan = RelationFactory(
        person=None, group=group, gift=GiftFactory(), status=status("Given")
    )
    parent_plan = RelationFactory(
        person=None, group=parent_group, gift=GiftFactory(), status=status("Given")
    )

    for obj in (
        person,
        group,
        parent_group,
        own_plan,
        group_plan,
        parent_plan,
        own_plan.gift,
        group_plan.gift,
        parent_plan.gift,
    ):
        share(user, obj, level=PermissionLevel.VIEWER)

    history = build_recipient_history(user, person)
    relation_ids = {item.relation_id for item in history.items}

    assert own_plan.pk in relation_ids
    assert group_plan.pk in relation_ids
    assert parent_plan.pk in relation_ids

    items_by_id = {item.relation_id: item for item in history.items}
    assert items_by_id[own_plan.pk].is_direct is True
    assert items_by_id[group_plan.pk].is_direct is False
    assert items_by_id[parent_plan.pk].is_direct is False


def test_group_history_includes_member_and_nested_member_plans(user, share, status):
    parent_group = PersonGroupFactory(name="Family")
    child_group = PersonGroupFactory(name="Kids")
    child_group.parent_groups.add(parent_group)

    member = PersonFactory(first_name="Bob")
    member.groups.add(child_group)

    plan = RelationFactory(person=member, gift=GiftFactory(), status=status("Given"))

    for obj in (parent_group, child_group, member, plan, plan.gift):
        share(user, obj, level=PermissionLevel.VIEWER)

    history = build_recipient_history(user, parent_group)
    assert len(history.items) == 1
    assert history.items[0].relation_id == plan.pk
    assert history.items[0].is_direct is False


def test_plans_not_shared_with_viewer_are_absent(user, share, status):
    person = PersonFactory()
    shared_plan = RelationFactory(person=person, gift=GiftFactory(), status=status("Given"))
    unshared_plan = RelationFactory(person=person, gift=GiftFactory(), status=status("Given"))

    for obj in (person, shared_plan, shared_plan.gift):
        share(user, obj, level=PermissionLevel.VIEWER)

    history = build_recipient_history(user, person)
    relation_ids = {item.relation_id for item in history.items}
    assert shared_plan.pk in relation_ids
    assert unshared_plan.pk not in relation_ids


def test_hidden_surprise_plan_is_not_in_history(user, share, status):
    # Viewer is linked to the person
    person = PersonFactory(account=user)
    owner = UserFactory()

    gift = GiftFactory()
    surprise_plan = RelationFactory(
        person=person, gift=gift, status=status("Purchased"), is_surprise=True
    )
    # Grant owner permission to owner, viewer permission to user
    share(owner, surprise_plan, level=PermissionLevel.OWNER)
    share(user, surprise_plan, level=PermissionLevel.VIEWER)
    share(user, person, level=PermissionLevel.VIEWER)
    share(user, gift, level=PermissionLevel.VIEWER)

    history = build_recipient_history(user, person)
    assert surprise_plan.pk not in {item.relation_id for item in history.items}
    assert gift.pk not in history.planned_gift_ids


def test_planned_gift_ids_skip_abandoned_and_indirect_plans(user, share, status):
    person = PersonFactory()
    group = PersonGroupFactory()
    person.groups.add(group)

    gift_active = GiftFactory()
    gift_abandoned = GiftFactory()
    gift_group = GiftFactory()

    direct_active = RelationFactory(person=person, gift=gift_active, status=status("Idea"))
    direct_abandoned = RelationFactory(
        person=person, gift=gift_abandoned, status=status("Abandoned")
    )
    indirect_active = RelationFactory(
        person=None, group=group, gift=gift_group, status=status("Idea")
    )

    for obj in (
        person,
        group,
        direct_active,
        direct_abandoned,
        indirect_active,
        gift_active,
        gift_abandoned,
        gift_group,
    ):
        share(user, obj, level=PermissionLevel.VIEWER)

    history = build_recipient_history(user, person)
    assert gift_active.pk in history.planned_gift_ids
    assert gift_abandoned.pk not in history.planned_gift_ids
    assert gift_group.pk not in history.planned_gift_ids


def test_rating_and_note_only_when_visible(user, share, status):
    person = PersonFactory()
    gift_idea = GiftFactory()
    gift_given = GiftFactory()

    idea_plan = RelationFactory(
        person=person,
        gift=gift_idea,
        status=status("Idea"),
        reaction_rating=5,
        reaction_note="Great idea",
    )
    given_plan = RelationFactory(
        person=person,
        gift=gift_given,
        status=status("Given"),
        reaction_rating=4,
        reaction_note="Loved it",
    )

    for obj in (person, idea_plan, given_plan, gift_idea, gift_given):
        share(user, obj, level=PermissionLevel.VIEWER)

    history = build_recipient_history(user, person)
    items_by_id = {item.relation_id: item for item in history.items}

    # On Idea plan, reaction cannot be rated, so rating is None and note is empty
    assert items_by_id[idea_plan.pk].rating is None
    assert items_by_id[idea_plan.pk].note == ""

    # On Given plan, rating and note are kept
    assert items_by_id[given_plan.pk].rating == 4
    assert items_by_id[given_plan.pk].note == "Loved it"


def test_tag_ids_include_visible_ancestors_only(user, share, status):
    secret_tag = GiftTagFactory(name="Secret")
    toys_tag = GiftTagFactory(name="Toys")
    lego_tag = GiftTagFactory(name="Lego")

    # Lego -> Toys -> Secret
    lego_tag.parent_tags.add(toys_tag)
    toys_tag.parent_tags.add(secret_tag)

    # Share Lego and Toys with user, but NOT Secret
    share(user, lego_tag, level=PermissionLevel.VIEWER)
    share(user, toys_tag, level=PermissionLevel.VIEWER)

    person = PersonFactory()
    gift = GiftFactory()
    gift.tags.add(lego_tag)
    plan = RelationFactory(person=person, gift=gift, status=status("Given"))

    for obj in (person, gift, plan):
        share(user, obj, level=PermissionLevel.VIEWER)

    history = build_recipient_history(user, person)
    item = history.items[0]
    assert item.tag_ids == frozenset({lego_tag.pk, toys_tag.pk})
    assert secret_tag.pk not in item.tag_ids


def test_interest_tags_only_visible_ones(user, share):
    visible_interest = GiftTagFactory(name="Music")
    hidden_interest = GiftTagFactory(name="Private Interest")
    share(user, visible_interest, level=PermissionLevel.VIEWER)

    person = PersonFactory()
    person.interests.add(visible_interest, hidden_interest)
    share(user, person, level=PermissionLevel.VIEWER)

    history = build_recipient_history(user, person)
    assert visible_interest.pk in history.interest_tag_ids
    assert hidden_interest.pk not in history.interest_tag_ids


def test_query_count_is_bounded(user, share, status, django_assert_max_num_queries):
    person = PersonFactory()
    share(user, person, level=PermissionLevel.VIEWER)

    tags = [GiftTagFactory(name=f"Tag {i}") for i in range(10)]
    for tag in tags:
        share(user, tag, level=PermissionLevel.VIEWER)

    person.interests.add(tags[0], tags[1])

    plans = []
    for i in range(10):
        gift = GiftFactory(name=f"Gift {i}")
        gift.tags.add(tags[i % len(tags)])
        plan = RelationFactory(person=person, gift=gift, status=status("Given"))
        share(user, gift, level=PermissionLevel.VIEWER)
        share(user, plan, level=PermissionLevel.VIEWER)
        plans.append(plan)

    # Max 6 queries:
    with django_assert_max_num_queries(6):
        build_recipient_history(user, person)


def test_history_item_carries_direct_tag_ids_without_ancestors(user, share, status):
    parent_tag = GiftTagFactory(name="Toys")
    child_tag = GiftTagFactory(name="Lego")
    child_tag.parent_tags.add(parent_tag)

    share(user, parent_tag, level=PermissionLevel.VIEWER)
    share(user, child_tag, level=PermissionLevel.VIEWER)

    person = PersonFactory()
    gift = GiftFactory()
    gift.tags.add(child_tag)
    plan = RelationFactory(person=person, gift=gift, status=status("Given"))

    for obj in (person, gift, plan):
        share(user, obj, level=PermissionLevel.VIEWER)

    history = build_recipient_history(user, person)
    item = history.items[0]

    assert item.tag_ids == frozenset({child_tag.pk, parent_tag.pk})
    assert item.direct_tag_ids == frozenset({child_tag.pk})


def test_build_preference_profile_aggregates_three_buckets_with_direct_counts(user, share, status):
    from gift_manager.models import GiftSuggestion
    from gift_manager.suggestions.history import build_preference_profile

    robotics = GiftTagFactory(name="Robotics")
    scifi = GiftTagFactory(name="Sci-Fi")
    horror = GiftTagFactory(name="Horror")

    for tag in (robotics, scifi, horror):
        share(user, tag, level=PermissionLevel.VIEWER)

    person = PersonFactory()
    share(user, person, level=PermissionLevel.VIEWER)

    # 2 plans rated 5★ with Robotics
    for i in range(2):
        g = GiftFactory(name=f"Robo {i}")
        g.tags.add(robotics)
        p = RelationFactory(
            person=person, gift=g, status=status("Given"), reaction_rating=5, reaction_note="Great!"
        )
        share(user, g, level=PermissionLevel.VIEWER)
        share(user, p, level=PermissionLevel.VIEWER)

    # 1 plan rated 1★ with Horror
    g_horror = GiftFactory(name="Spooky Book")
    g_horror.tags.add(horror)
    p_horror = RelationFactory(
        person=person,
        gift=g_horror,
        status=status("Given"),
        reaction_rating=1,
        reaction_note="Hated it",
    )
    share(user, g_horror, level=PermissionLevel.VIEWER)
    share(user, p_horror, level=PermissionLevel.VIEWER)

    # Dismissed suggestion with already_owned_or_practiced (Sci-Fi)
    sugg_owned = GiftSuggestion.objects.create(
        user=user,
        person=person,
        source=GiftSuggestion.Source.AI,
        state=GiftSuggestion.State.DISMISSED,
        dismiss_reason=GiftSuggestion.DismissReason.ALREADY_OWNED_OR_PRACTICED,
        name="Sci-Fi Novel",
    )
    sugg_owned.tags.add(scifi)

    # Dismissed suggestion with dislikes (Horror)
    sugg_disliked = GiftSuggestion.objects.create(
        user=user,
        person=person,
        source=GiftSuggestion.Source.AI,
        state=GiftSuggestion.State.DISMISSED,
        dismiss_reason=GiftSuggestion.DismissReason.DISLIKES,
        name="Horror Movie",
    )
    sugg_disliked.tags.add(horror)

    history = build_recipient_history(user, person)
    visible_tag_ids = {robotics.pk, scifi.pk, horror.pk}
    profile = build_preference_profile(user, history, visible_tag_ids)

    assert profile.liked_tags == (("Robotics", 2),)
    assert profile.owned_tags == (("Sci-Fi", 1),)
    assert profile.disliked_tags == (("Horror", 2),)


def test_build_preference_profile_respects_50_plus_history_and_visibility(user, share, status):
    from gift_manager.suggestions.history import build_preference_profile

    visible_tag = GiftTagFactory(name="Chess")
    hidden_tag = GiftTagFactory(name="Secret Hobby")
    share(user, visible_tag, level=PermissionLevel.VIEWER)
    # hidden_tag is intentionally NOT shared with user

    person = PersonFactory()
    share(user, person, level=PermissionLevel.VIEWER)

    # 55 plans rated 5★
    for i in range(55):
        g = GiftFactory(name=f"Chess Set {i}")
        g.tags.add(visible_tag, hidden_tag)
        p = RelationFactory(
            person=person, gift=g, status=status("Given"), reaction_rating=5, reaction_note="Super"
        )
        share(user, g, level=PermissionLevel.VIEWER)
        share(user, p, level=PermissionLevel.VIEWER)

    history = build_recipient_history(user, person)
    assert len(history.items) == 55

    visible_tag_ids = {visible_tag.pk}
    profile = build_preference_profile(user, history, visible_tag_ids)

    assert profile.liked_tags == (("Chess", 55),)
    assert "Secret Hobby" not in [t[0] for t in profile.liked_tags]
