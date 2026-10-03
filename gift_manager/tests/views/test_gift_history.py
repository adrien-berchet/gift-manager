"""Tests for the recipient gift history and the repeat-gift hint."""

from datetime import date

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gift_manager.models import PermissionLevel
from gift_manager.models import RelationStatus
from gift_manager.permissions import create_or_update_permission
from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import GroupRelationFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import UserFactory


def _status(name: str) -> RelationStatus:
    return RelationStatus.objects.get_or_create(status_en=name, defaults={"status": name})[0]


@pytest.fixture
def user():
    return UserFactory()


@pytest.fixture
def client(user):
    client = Client()
    client.force_login(user)
    return client


def _share(user, obj, level=PermissionLevel.VIEWER):
    create_or_update_permission(user, obj, permission_level=level)


def _plan(user, person, status="Given", event_year=2023, **kwargs):
    event = EventFactory(date=date(event_year, 12, 25)) if event_year else None
    relation = RelationFactory(person=person, status=_status(status), event=event, **kwargs)
    _share(user, relation)
    return relation


def _history_url(person):
    return reverse("gift_manager:person_gift_history", kwargs={"pk": person.person_id})


@pytest.mark.django_db
class TestPersonGiftHistory:
    @pytest.fixture(autouse=True)
    def person(self, user):
        self.person = PersonFactory()
        _share(user, self.person)

    def test_groups_by_year_newest_first(self, client, user):
        _plan(user, self.person, event_year=2021, gift=GiftFactory(name="Old gift"))
        _plan(user, self.person, event_year=2024, gift=GiftFactory(name="New gift"))

        response = client.get(_history_url(self.person))

        assert response.status_code == 200
        years = [group.year for group in response.context["history"]]
        assert years == [2024, 2021]
        content = response.content.decode()
        assert content.index("New gift") < content.index("Old gift")

    @pytest.mark.parametrize("status", ["Idea", "Planned", "Purchased", "Abandoned"])
    def test_only_given_plans_are_history(self, client, user, status):
        _plan(user, self.person, status=status, gift=GiftFactory(name="Not given"))
        _plan(user, self.person, status="Given", gift=GiftFactory(name="Was given"))

        content = client.get(_history_url(self.person)).content.decode()

        assert "Was given" in content
        assert "Not given" not in content

    def test_other_users_plans_are_hidden(self, client, user):
        RelationFactory(
            person=self.person, status=_status("Given"), gift=GiftFactory(name="Secret gift")
        )

        response = client.get(_history_url(self.person))

        assert "Secret gift" not in response.content.decode()

    def test_person_without_access_is_not_found(self, client):
        stranger = PersonFactory()

        assert client.get(_history_url(stranger)).status_code == 404

    def test_anonymous_is_redirected(self):
        assert Client().get(_history_url(self.person)).status_code == 302

    def test_rating_note_and_awaiting_reaction(self, client, user):
        _plan(
            user,
            self.person,
            gift=GiftFactory(name="Rated"),
            reaction_rating=4,
            reaction_note="Loved it",
        )
        _plan(user, self.person, gift=GiftFactory(name="Unrated"))

        content = client.get(_history_url(self.person)).content.decode()

        assert "Loved it" in content
        assert content.count("Awaiting reaction") == 1

    def test_group_plans_show_group_only_when_visible(self, client, user):
        visible_group = PersonGroupFactory(name="Visible family")
        hidden_group = PersonGroupFactory(name="Hidden club")
        self.person.groups.add(visible_group, hidden_group)
        _share(user, visible_group)
        for group, gift_name in ((visible_group, "Family gift"), (hidden_group, "Club gift")):
            relation = GroupRelationFactory(
                group=group, status=_status("Given"), gift=GiftFactory(name=gift_name)
            )
            _share(user, relation)

        content = client.get(_history_url(self.person)).content.decode()

        assert "Family gift" in content
        assert "Visible family" in content
        assert "Club gift" in content
        assert "Hidden club" not in content

    def test_query_count_is_bounded(self, client, user):
        def count_queries():
            with CaptureQueriesContext(connection) as queries:
                assert client.get(_history_url(self.person)).status_code == 200
            return len(queries)

        _plan(user, self.person, gift=GiftFactory())
        baseline = count_queries()
        for year in range(2015, 2025):
            _plan(user, self.person, event_year=year, gift=GiftFactory(), reaction_rating=3)

        assert count_queries() == baseline


@pytest.mark.django_db
class TestGroupGiftHistory:
    def test_lists_plans_targeted_at_the_group(self, client, user):
        group = PersonGroupFactory()
        _share(user, group)
        relation = GroupRelationFactory(
            group=group, status=_status("Given"), gift=GiftFactory(name="Team gift")
        )
        _share(user, relation)

        response = client.get(
            reverse("gift_manager:person_group_gift_history", kwargs={"pk": group.group_id})
        )

        assert response.status_code == 200
        assert "Team gift" in response.content.decode()

    def test_group_without_access_is_not_found(self, client):
        group = PersonGroupFactory()

        response = client.get(
            reverse("gift_manager:person_group_gift_history", kwargs={"pk": group.group_id})
        )

        assert response.status_code == 404


@pytest.mark.django_db
class TestDetailPagesLoadHistory:
    def test_person_detail_points_to_history(self, client, user):
        person = PersonFactory()
        _share(user, person)

        content = client.get(
            reverse("gift_manager:person_detail", kwargs={"pk": person.person_id})
        ).content.decode()

        assert _history_url(person) in content


@pytest.mark.django_db
class TestRepeatGiftHint:
    @pytest.fixture(autouse=True)
    def setup(self, user):
        self.person = PersonFactory()
        _share(user, self.person)
        self.gift = GiftFactory(name="Kayak")
        _share(user, self.gift)

    def hint(self, client, recipient, gift, **extra):
        return client.get(
            reverse("gift_manager:repeat_gift_hint"),
            {"recipient": recipient, "gift": gift.pk, **extra},
        ).content.decode()

    def test_warns_for_same_recipient_and_gift(self, client, user):
        _plan(user, self.person, status="Planned", gift=self.gift)

        content = self.hint(client, f"person:{self.person.person_id}", self.gift)

        assert "data-repeat-gift-hint" in content

    def test_no_warning_for_other_recipient(self, client, user):
        other = PersonFactory()
        _share(user, other)
        _plan(user, self.person, status="Planned", gift=self.gift)

        assert "data-repeat-gift-hint" not in self.hint(
            client, f"person:{other.person_id}", self.gift
        )

    def test_abandoned_plans_do_not_count(self, client, user):
        _plan(user, self.person, status="Abandoned", gift=self.gift)

        content = self.hint(client, f"person:{self.person.person_id}", self.gift)

        assert "data-repeat-gift-hint" not in content

    def test_edited_plan_is_not_a_repeat_of_itself(self, client, user):
        relation = _plan(user, self.person, status="Planned", gift=self.gift)

        content = self.hint(
            client, f"person:{self.person.person_id}", self.gift, relation=relation.relation_id
        )

        assert "data-repeat-gift-hint" not in content

    def test_invalid_input_renders_nothing(self, client):
        response = client.get(
            reverse("gift_manager:repeat_gift_hint"), {"recipient": "bogus", "gift": "x"}
        )

        assert response.status_code == 200
        assert response.content.decode().strip() == ""

    def test_inaccessible_recipient_gets_no_hint(self, client, user):
        stranger = PersonFactory()
        RelationFactory(person=stranger, gift=self.gift, status=_status("Planned"))

        assert "data-repeat-gift-hint" not in self.hint(
            client, f"person:{stranger.person_id}", self.gift
        )

    def test_plan_form_embeds_the_hint_endpoint(self, client):
        response = client.get(reverse("gift_manager:relation_create"))

        assert reverse("gift_manager:repeat_gift_hint") in response.content.decode()

    def test_hint_request_does_not_lock_the_form(self, client):
        """loading-states.js disables every form control during a request from the form."""
        content = client.get(reverse("gift_manager:relation_create")).content.decode()

        assert "data-loading-ignore" in content

    def test_group_recipient_gets_repeat_warning_but_no_suggestions(self, client, user):
        group = PersonGroupFactory()
        _share(user, group)
        relation = GroupRelationFactory(group=group, gift=self.gift, status=_status("Planned"))
        _share(user, relation)

        content = self.hint(client, f"group:{group.group_id}", self.gift)

        assert "data-repeat-gift-hint" in content
        assert "data-interest-suggestions" not in content


@pytest.mark.django_db
class TestGroupDetailSplitsPlans:
    def test_group_panel_shows_each_plan_once(self, client, user):
        group = PersonGroupFactory()
        _share(user, group)
        planned = GroupRelationFactory(
            group=group, status=_status("Planned"), gift=GiftFactory(name="In progress gift")
        )
        given = GroupRelationFactory(
            group=group, status=_status("Given"), gift=GiftFactory(name="Given gift")
        )
        abandoned = GroupRelationFactory(
            group=group, status=_status("Abandoned"), gift=GiftFactory(name="Dropped gift")
        )
        for relation in (planned, given, abandoned):
            _share(user, relation)

        response = client.get(
            reverse("gift_manager:person_group_detail", kwargs={"pk": group.group_id}),
            HTTP_HX_REQUEST="true",
        )

        assert [r.pk for r in response.context["in_progress_relations"]] == [planned.pk]
        assert [r.pk for r in response.context["abandoned_relations"]] == [abandoned.pk]
        assert response.context["given_count"] == 1
        html = response.content.decode()
        assert "In progress gift" in html
        assert "Dropped gift" in html
        assert "Given gift" not in html
        assert (
            reverse("gift_manager:person_group_gift_history", kwargs={"pk": group.group_id}) in html
        )
