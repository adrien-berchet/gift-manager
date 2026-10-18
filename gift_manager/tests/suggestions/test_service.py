import pytest
from django.http import Http404

from gift_manager.models import GiftSuggestion
from gift_manager.models import PermissionLevel
from gift_manager.models import Relation
from gift_manager.models import RelationPermission
from gift_manager.statuses import is_idea_status
from gift_manager.suggestions.service import GiftSuggestionService
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import GiftTagFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_first_page_has_five_without_ai_and_next_offset(user, share):
    tag = GiftTagFactory(name="Tag")
    share(user, tag, level=PermissionLevel.VIEWER)

    person = PersonFactory()
    person.interests.add(tag)
    share(user, person, level=PermissionLevel.VIEWER)

    gifts = [GiftFactory(name=f"Gift {i}", tags=[tag]) for i in range(7)]
    for g in gifts:
        share(user, g, level=PermissionLevel.VIEWER)

    service = GiftSuggestionService(user, person)
    assert not service.ai_enabled

    page1 = service.catalogue_page(offset=0)
    assert len(page1.candidates) == 5
    assert page1.next_offset == 5

    page2 = service.catalogue_page(offset=5)
    assert len(page2.candidates) == 2
    assert page2.next_offset is None


def test_first_page_has_three_when_ai_enabled(user, share):
    tag = GiftTagFactory(name="Tag")
    share(user, tag, level=PermissionLevel.VIEWER)

    person = PersonFactory()
    person.interests.add(tag)
    share(user, person, level=PermissionLevel.VIEWER)

    gifts = [GiftFactory(name=f"Gift {i}", tags=[tag]) for i in range(7)]
    for g in gifts:
        share(user, g, level=PermissionLevel.VIEWER)

    service = GiftSuggestionService(user, person, ai_client=object())
    assert service.ai_enabled

    page1 = service.catalogue_page(offset=0)
    assert len(page1.candidates) == 3
    assert page1.next_offset == 3


def test_gift_planned_for_recipient_is_excluded(user, share, status):
    tag = GiftTagFactory(name="Tag")
    share(user, tag, level=PermissionLevel.VIEWER)

    person = PersonFactory()
    person.interests.add(tag)
    share(user, person, level=PermissionLevel.VIEWER)

    gift1 = GiftFactory(name="Planned Gift", tags=[tag])
    gift2 = GiftFactory(name="Unplanned Gift", tags=[tag])
    for g in (gift1, gift2):
        share(user, g, level=PermissionLevel.VIEWER)

    plan = RelationFactory(person=person, gift=gift1, status=status("Given"))
    share(user, plan, level=PermissionLevel.VIEWER)

    service = GiftSuggestionService(user, person)
    page = service.catalogue_page(offset=0)
    candidate_ids = [c.gift.pk for c in page.candidates]

    assert gift1.pk not in candidate_ids
    assert gift2.pk in candidate_ids


def test_gift_with_only_abandoned_plan_is_not_excluded(user, share, status):
    tag_pos = GiftTagFactory(name="Positive Tag")
    share(user, tag_pos, level=PermissionLevel.VIEWER)

    person = PersonFactory()
    share(user, person, level=PermissionLevel.VIEWER)

    # Past history gift rated 5 (+2) on tag_pos
    h_gift = GiftFactory(tags=[tag_pos])
    share(user, h_gift, level=PermissionLevel.VIEWER)
    h_plan = RelationFactory(person=person, gift=h_gift, status=status("Given"), reaction_rating=5)
    share(user, h_plan, level=PermissionLevel.VIEWER)

    # Gift has an abandoned plan (-1) on tag_pos -> net score +1 > 0
    gift = GiftFactory(name="Gift", tags=[tag_pos])
    share(user, gift, level=PermissionLevel.VIEWER)

    plan = RelationFactory(person=person, gift=gift, status=status("Abandoned"))
    share(user, plan, level=PermissionLevel.VIEWER)

    service = GiftSuggestionService(user, person)
    page = service.catalogue_page(offset=0)
    candidate_ids = [c.gift.pk for c in page.candidates]

    assert gift.pk in candidate_ids


def test_accept_gift_creates_idea_plan_owned_by_user(user, share):
    tag = GiftTagFactory(name="Tag")
    share(user, tag, level=PermissionLevel.VIEWER)

    person = PersonFactory()
    person.interests.add(tag)
    share(user, person, level=PermissionLevel.VIEWER)

    gift = GiftFactory(name="Nice Gift", tags=[tag])
    share(user, gift, level=PermissionLevel.VIEWER)

    service = GiftSuggestionService(user, person)
    relation = service.accept_gift(gift.gift_id)

    assert is_idea_status(relation.status)
    assert relation.person == person
    assert relation.group is None
    assert relation.gift == gift

    # Owner permission granted to user and no one else
    permissions = list(RelationPermission.objects.filter(relation=relation))
    assert len(permissions) == 1
    assert permissions[0].user == user
    assert permissions[0].permission_type == PermissionLevel.OWNER

    # Suggestion row upserted to accepted
    row = GiftSuggestion.objects.get(user=user, person=person, gift=gift)
    assert row.state == GiftSuggestion.State.ACCEPTED
    assert row.source == GiftSuggestion.Source.CATALOGUE

    # Gift no longer in catalogue_page
    page = service.catalogue_page(offset=0)
    assert gift.pk not in [c.gift.pk for c in page.candidates]


def test_accept_gift_for_group_recipient(user, share):
    tag = GiftTagFactory(name="Tag")
    share(user, tag, level=PermissionLevel.VIEWER)

    group = PersonGroupFactory()
    share(user, group, level=PermissionLevel.VIEWER)

    # Add a member with interest so group has suggestions
    member = PersonFactory()
    member.groups.add(group)
    member.interests.add(tag)
    share(user, member, level=PermissionLevel.VIEWER)

    gift = GiftFactory(name="Board Game", tags=[tag])
    share(user, gift, level=PermissionLevel.VIEWER)

    service = GiftSuggestionService(user, group)
    relation = service.accept_gift(gift.gift_id)

    assert relation.person is None
    assert relation.group == group
    assert relation.gift == gift
    assert is_idea_status(relation.status)

    row = GiftSuggestion.objects.get(user=user, group=group, gift=gift)
    assert row.state == GiftSuggestion.State.ACCEPTED


def test_accept_sets_default_surprise(user, share):
    tag = GiftTagFactory(name="Tag")
    share(user, tag, level=PermissionLevel.VIEWER)

    other_user = UserFactory()
    person = PersonFactory(user_link=other_user)
    person.interests.add(tag)
    share(user, person, level=PermissionLevel.VIEWER)

    gift = GiftFactory(tags=[tag])
    share(user, gift, level=PermissionLevel.VIEWER)

    service = GiftSuggestionService(user, person)
    relation = service.accept_gift(gift.gift_id)

    assert relation.is_surprise is True


def test_accept_twice_creates_one_plan(user, share):
    tag = GiftTagFactory(name="Tag")
    share(user, tag, level=PermissionLevel.VIEWER)

    person = PersonFactory()
    person.interests.add(tag)
    share(user, person, level=PermissionLevel.VIEWER)

    gift = GiftFactory(tags=[tag])
    share(user, gift, level=PermissionLevel.VIEWER)

    service = GiftSuggestionService(user, person)
    rel1 = service.accept_gift(gift.gift_id)
    rel2 = service.accept_gift(gift.gift_id)

    assert rel1.pk == rel2.pk
    assert Relation.objects.filter(person=person, gift=gift).count() == 1


def test_accept_inaccessible_gift_is_404(user, share):
    person = PersonFactory()
    share(user, person, level=PermissionLevel.VIEWER)

    other_user = UserFactory()
    unshared_gift = GiftFactory()
    share(other_user, unshared_gift, level=PermissionLevel.OWNER)

    service = GiftSuggestionService(user, person)
    with pytest.raises(Http404):
        service.accept_gift(unshared_gift.gift_id)


def test_dismiss_inaccessible_gift_is_404(user, share):
    person = PersonFactory()
    share(user, person, level=PermissionLevel.VIEWER)

    other_user = UserFactory()
    unshared_gift = GiftFactory()
    share(other_user, unshared_gift, level=PermissionLevel.OWNER)

    service = GiftSuggestionService(user, person)
    with pytest.raises(Http404):
        service.dismiss_gift(unshared_gift.gift_id)


def test_dismissed_gift_never_returns(user, share, status):
    tag = GiftTagFactory(name="Tag")
    share(user, tag, level=PermissionLevel.VIEWER)

    person = PersonFactory()
    share(user, person, level=PermissionLevel.VIEWER)

    other_person = PersonFactory()
    share(user, other_person, level=PermissionLevel.VIEWER)

    # 2 popular gifts so fallback mode works initially
    gift1 = GiftFactory(name="Gift 1", tags=[tag])
    gift2 = GiftFactory(name="Gift 2", tags=[tag])
    for g in (gift1, gift2):
        share(user, g, level=PermissionLevel.VIEWER)

    p1 = RelationFactory(person=other_person, gift=gift1, status=status("Given"), reaction_rating=5)
    p2 = RelationFactory(person=other_person, gift=gift2, status=status("Given"), reaction_rating=4)
    for p in (p1, p2):
        share(user, p, level=PermissionLevel.VIEWER)

    service = GiftSuggestionService(user, person)
    service.dismiss_gift(gift1.gift_id)

    # Dismissed gift is absent
    page = service.catalogue_page(offset=0)
    assert gift1.pk not in [c.gift.pk for c in page.candidates]

    # Even if new history makes tag a top match, it remains absent
    plan_new = RelationFactory(person=person, gift=gift2, status=status("Given"), reaction_rating=5)
    share(user, plan_new, level=PermissionLevel.VIEWER)

    page_after = service.catalogue_page(offset=0)
    assert gift1.pk not in [c.gift.pk for c in page_after.candidates]

    # Another user can still get gift1
    other_user = UserFactory()
    share(other_user, person, level=PermissionLevel.VIEWER)
    share(other_user, other_person, level=PermissionLevel.VIEWER)
    share(other_user, gift1, level=PermissionLevel.VIEWER)
    share(other_user, tag, level=PermissionLevel.VIEWER)
    share(other_user, p1, level=PermissionLevel.VIEWER)
    other_service = GiftSuggestionService(other_user, person)
    other_page = other_service.catalogue_page(offset=0)
    assert gift1.pk in [c.gift.pk for c in other_page.candidates]
