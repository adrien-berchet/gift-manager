"""Tests for the gift plan reaction prompt, endpoint and edit form section."""

import json

import pytest
from django.test import Client
from django.urls import reverse

from gift_manager.forms import RelationForm
from gift_manager.models import PermissionLevel
from gift_manager.models import RelationStatus
from gift_manager.permissions import create_or_update_permission
from gift_manager.tests.factories import GroupRelationFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import UserFactory


def _status(name: str) -> RelationStatus:
    return RelationStatus.objects.get_or_create(status_en=name, defaults={"status": name})[0]


def _reaction_url(relation) -> str:
    return reverse("gift_manager:relation_reaction", kwargs={"pk": relation.relation_id})


@pytest.mark.django_db
class TestRelationReactionView:
    @pytest.fixture(autouse=True)
    def setup(self, settings):
        settings.USE_I18N = False
        self.user = UserFactory()
        self.client = Client()
        self.client.force_login(self.user)

    def make_relation(self, status_name="Given", *, level=PermissionLevel.EDITOR, **kwargs):
        relation = RelationFactory(status=_status(status_name), **kwargs)
        if level is not None:
            create_or_update_permission(self.user, relation, permission_level=level)
        return relation

    def test_get_given_relation_renders_form(self):
        relation = self.make_relation("Given")

        response = self.client.get(_reaction_url(relation), HTTP_HX_REQUEST="true")

        assert response.status_code == 200
        content = response.content.decode()
        assert "Their reaction" in content
        assert 'name="reaction_rating"' in content
        assert 'name="reaction_note"' in content
        assert 'data-form-type="relation-reaction"' in content

    def test_get_abandoned_relation_uses_estimate_wording(self):
        relation = self.make_relation("Abandoned")

        response = self.client.get(_reaction_url(relation), HTTP_HX_REQUEST="true")

        assert response.status_code == 200
        assert "How much would they have liked it?" in response.content.decode()

    def test_get_group_relation_works(self):
        relation = GroupRelationFactory(status=_status("Given"))
        create_or_update_permission(self.user, relation, permission_level=PermissionLevel.EDITOR)

        response = self.client.get(_reaction_url(relation), HTTP_HX_REQUEST="true")

        assert response.status_code == 200

    @pytest.mark.parametrize("status_name", ["Idea", "Planned", "Purchased"])
    def test_non_terminal_relation_is_rejected(self, status_name):
        relation = self.make_relation(status_name)

        get_response = self.client.get(_reaction_url(relation), HTTP_HX_REQUEST="true")
        post_response = self.client.post(
            _reaction_url(relation), {"reaction_rating": "4"}, HTTP_HX_REQUEST="true"
        )

        assert get_response.status_code == 400
        assert post_response.status_code == 400
        relation.refresh_from_db()
        assert relation.reaction_rating is None

    def test_viewer_cannot_open_or_save(self):
        relation = self.make_relation("Given", level=PermissionLevel.VIEWER)

        get_response = self.client.get(_reaction_url(relation), HTTP_HX_REQUEST="true")
        post_response = self.client.post(
            _reaction_url(relation), {"reaction_rating": "4"}, HTTP_HX_REQUEST="true"
        )

        assert get_response.status_code == 403
        assert post_response.status_code == 403
        relation.refresh_from_db()
        assert relation.reaction_rating is None

    def test_inaccessible_relation_is_not_found(self):
        relation = self.make_relation("Given", level=None)

        response = self.client.get(_reaction_url(relation), HTTP_HX_REQUEST="true")

        assert response.status_code == 404

    def test_login_is_required(self):
        relation = self.make_relation("Given")

        response = Client().get(_reaction_url(relation))

        assert response.status_code == 302

    def test_post_saves_rating_and_note_and_refreshes(self):
        relation = self.make_relation("Given")

        response = self.client.post(
            _reaction_url(relation),
            {"reaction_rating": "5", "reaction_note": "  Loved it  "},
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 200
        assert response["HX-Reswap"] == "none"
        triggers = json.loads(response["HX-Trigger"])
        assert "list:update" in triggers
        assert "offcanvas:close" in triggers
        assert triggers["showNotification"]["type"] == "success"
        relation.refresh_from_db()
        assert relation.reaction_rating == 5
        assert relation.reaction_note == "Loved it"

    def test_post_abandoned_relation_saves_estimate(self):
        relation = self.make_relation("Abandoned")

        response = self.client.post(
            _reaction_url(relation),
            {"reaction_rating": "1", "reaction_note": "Too expensive"},
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 200
        relation.refresh_from_db()
        assert relation.reaction_rating == 1
        assert relation.reaction_note == "Too expensive"

    def test_post_empty_rating_clears_existing_reaction(self):
        relation = self.make_relation("Given", reaction_rating=3, reaction_note="ok")

        response = self.client.post(
            _reaction_url(relation),
            {"reaction_rating": "", "reaction_note": ""},
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 200
        relation.refresh_from_db()
        assert relation.reaction_rating is None
        assert not relation.reaction_note

    @pytest.mark.parametrize("rating", ["0", "6", "abc"])
    def test_post_invalid_rating_returns_form_errors(self, rating):
        relation = self.make_relation("Given")

        response = self.client.post(
            _reaction_url(relation), {"reaction_rating": rating}, HTTP_HX_REQUEST="true"
        )

        assert response.status_code == 422
        relation.refresh_from_db()
        assert relation.reaction_rating is None

    def test_inline_post_saves_without_closing_panels_and_keeps_note(self):
        relation = self.make_relation("Given", reaction_note="Keep me")

        response = self.client.post(
            _reaction_url(relation),
            {"reaction_rating": "4", "inline": "1"},
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 200
        triggers = json.loads(response["HX-Trigger"])
        assert "list:update" in triggers
        assert "offcanvas:close" not in triggers
        relation.refresh_from_db()
        assert relation.reaction_rating == 4
        assert relation.reaction_note == "Keep me"

    def test_inline_post_never_overwrites_existing_rating(self):
        relation = self.make_relation("Given", reaction_rating=5, reaction_note="Loved")

        response = self.client.post(
            _reaction_url(relation),
            {"reaction_rating": "1", "inline": "1"},
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 409
        relation.refresh_from_db()
        assert relation.reaction_rating == 5
        assert relation.reaction_note == "Loved"

    def test_panel_post_overwrites_existing_rating(self):
        relation = self.make_relation("Given", reaction_rating=5)

        response = self.client.post(
            _reaction_url(relation), {"reaction_rating": "2"}, HTTP_HX_REQUEST="true"
        )

        assert response.status_code == 200
        relation.refresh_from_db()
        assert relation.reaction_rating == 2

    def test_post_omitting_note_keeps_stored_note(self):
        relation = self.make_relation("Given", reaction_note="Keep me")

        self.client.post(_reaction_url(relation), {"reaction_rating": "3"}, HTTP_HX_REQUEST="true")

        relation.refresh_from_db()
        assert relation.reaction_note == "Keep me"

    def test_inline_post_requires_edit_permission(self):
        relation = self.make_relation("Given", level=PermissionLevel.VIEWER)

        response = self.client.post(
            _reaction_url(relation),
            {"reaction_rating": "4", "inline": "1"},
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 403
        relation.refresh_from_db()
        assert relation.reaction_rating is None

    def test_post_too_long_note_is_rejected(self):
        relation = self.make_relation("Given")

        response = self.client.post(
            _reaction_url(relation),
            {"reaction_rating": "3", "reaction_note": "x" * 1001},
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 422
        relation.refresh_from_db()
        assert relation.reaction_rating is None

    def test_get_is_prefilled_with_existing_reaction(self):
        relation = self.make_relation("Given", reaction_rating=4, reaction_note="Nice")

        response = self.client.get(_reaction_url(relation), HTTP_HX_REQUEST="true")

        content = response.content.decode()
        assert "Nice" in content
        assert 'value="4" checked' in content or 'checked value="4"' in content


@pytest.mark.django_db
class TestReactionPromptAfterQuickAction:
    @pytest.fixture(autouse=True)
    def setup(self, settings):
        settings.USE_I18N = False
        self.user = UserFactory()
        self.client = Client()
        self.client.force_login(self.user)
        for name in ("Idea", "Planned", "Purchased", "Given", "Abandoned"):
            _status(name)

    def _post_action(self, relation, action):
        return self.client.post(
            reverse("gift_manager:relation_quick_action", kwargs={"pk": relation.relation_id}),
            {"action": action},
            HTTP_HX_REQUEST="true",
        )

    def _make(self, status_name, **kwargs):
        relation = RelationFactory(status=_status(status_name), **kwargs)
        create_or_update_permission(self.user, relation, permission_level=PermissionLevel.EDITOR)
        return relation

    def test_given_action_asks_for_a_reaction(self):
        from datetime import timedelta

        from django.utils import timezone

        relation = self._make("Planned", due_date=timezone.localdate() + timedelta(days=2))

        response = self._post_action(relation, "given")

        triggers = json.loads(response["HX-Trigger"])
        assert triggers["reaction:prompt"]["url"] == _reaction_url(relation)
        assert "list:update" in triggers

    def test_abandon_action_asks_for_a_reaction(self):
        relation = self._make("Idea", due_date=None, event=None)

        response = self._post_action(relation, "abandoned")

        triggers = json.loads(response["HX-Trigger"])
        assert triggers["reaction:prompt"]["url"] == _reaction_url(relation)

    def test_purchased_action_does_not_prompt(self):
        from datetime import timedelta

        from django.utils import timezone

        relation = self._make("Planned", due_date=timezone.localdate() + timedelta(days=2))

        response = self._post_action(relation, "purchased")

        assert "reaction:prompt" not in json.loads(response["HX-Trigger"])


@pytest.mark.django_db
class TestRelationFormReactionSection:
    def _form(self, relation, user, **data):
        payload = {
            "recipient": relation.recipient_key,
            "gift": relation.gift_id,
            "comment": "c",
            "event": relation.event_id or "",
            "status": relation.status_id,
            "due_date": "",
            **data,
        }
        return RelationForm(data=payload, instance=relation, user=user)

    @pytest.fixture
    def owner(self):
        return UserFactory()

    def _make(self, owner, status_name, **kwargs):
        relation = RelationFactory(status=_status(status_name), **kwargs)
        create_or_update_permission(owner, relation, permission_level=PermissionLevel.OWNER)
        for related in (relation.person, relation.gift, relation.event):
            if related is not None:
                create_or_update_permission(owner, related, permission_level=PermissionLevel.OWNER)
        return relation

    @pytest.mark.parametrize("status_name", ["Given", "Abandoned"])
    def test_rating_saved_for_terminal_status(self, owner, status_name):
        relation = self._make(owner, status_name)
        form = self._form(relation, owner, reaction_rating="4", reaction_note="Nice")

        assert form.is_valid(), form.errors
        saved = form.save()

        saved.refresh_from_db()
        assert saved.reaction_rating == 4
        assert saved.reaction_note == "Nice"

    def test_rating_is_ignored_for_non_terminal_status(self, owner):
        relation = self._make(owner, "Planned")
        form = self._form(relation, owner, reaction_rating="4", reaction_note="Nice")

        assert form.is_valid(), form.errors
        saved = form.save()

        saved.refresh_from_db()
        assert saved.reaction_rating is None
        assert not saved.reaction_note

    def test_stored_rating_survives_edit_while_status_is_not_terminal(self, owner):
        relation = self._make(owner, "Planned", reaction_rating=4, reaction_note="Nice")
        form = self._form(relation, owner)

        assert form.is_valid(), form.errors
        saved = form.save()

        saved.refresh_from_db()
        assert saved.reaction_rating == 4
        assert saved.reaction_note == "Nice"

    def test_changing_status_to_given_and_rating_in_one_edit(self, owner):
        relation = self._make(owner, "Planned")
        form = self._form(
            relation, owner, status=_status("Given").pk, reaction_rating="5", reaction_note=""
        )

        assert form.is_valid(), form.errors
        saved = form.save()

        saved.refresh_from_db()
        assert saved.reaction_rating == 5

    def test_out_of_range_rating_is_invalid(self, owner):
        relation = self._make(owner, "Given")
        form = self._form(relation, owner, reaction_rating="9")

        assert not form.is_valid()
        assert "reaction_rating" in form.errors


@pytest.mark.django_db
class TestReactionDashboardGroup:
    @pytest.fixture(autouse=True)
    def setup(self, settings):
        settings.USE_I18N = False
        self.user = UserFactory()
        self.client = Client()
        self.client.force_login(self.user)

    def _make(self, status_name="Given", *, level=PermissionLevel.OWNER, **kwargs):
        relation = RelationFactory(status=_status(status_name), **kwargs)
        create_or_update_permission(self.user, relation, permission_level=level)
        return relation

    def _group(self):
        response = self.client.get(reverse("gift_manager:home"))
        assert response.status_code == 200
        groups = {g["key"]: g for g in response.context["dashboard_action_groups"]}
        return groups.get("reaction"), response

    def test_recently_given_unrated_plan_is_listed(self):
        relation = self._make()

        group, response = self._group()

        assert group is not None
        assert [card["relation"].pk for card in group["items"]] == [relation.pk]
        assert group["label"] == "Awaiting reaction"
        assert response.context["dashboard_summary"]["reaction"] == 1
        assert _reaction_url(relation) in response.content.decode()

    def test_card_has_inline_stars_and_no_rate_button(self):
        relation = self._make()

        group, response = self._group()

        assert group["items"][0]["quick_actions"] == []
        assert group["items"][0]["can_rate_inline"] is True
        html = response.content.decode()
        assert "data-rating-inline" in html
        assert f'hx-post="{_reaction_url(relation)}"' in html
        assert 'name="inline"' in html
        assert 'data-action="quick-rate"' not in html

    def test_rated_plan_is_not_listed(self):
        self._make(reaction_rating=3)

        group, _ = self._group()

        assert group is None

    def test_abandoned_plan_is_never_listed(self):
        self._make("Abandoned")

        group, _ = self._group()

        assert group is None

    def test_viewer_does_not_see_plan(self):
        self._make(level=PermissionLevel.VIEWER)

        group, _ = self._group()

        assert group is None

    def test_old_given_plan_leaves_the_group(self):
        from datetime import timedelta

        from django.utils import timezone

        relation = self._make()
        type(relation).objects.filter(pk=relation.pk).update(
            status_changed_at=timezone.now() - timedelta(days=45)
        )

        group, _ = self._group()

        assert group is None

    def test_plan_without_timestamp_falls_back_to_due_date(self):
        from datetime import timedelta

        from django.utils import timezone

        recent = self._make(due_date=timezone.localdate() - timedelta(days=3))
        old = self._make(due_date=timezone.localdate() - timedelta(days=90))
        no_date = self._make(due_date=None)
        type(recent).objects.filter(pk__in=[recent.pk, old.pk, no_date.pk]).update(
            status_changed_at=None
        )

        group, _ = self._group()

        assert [card["relation"].pk for card in group["items"]] == [recent.pk]

    def test_reaction_group_does_not_count_as_needing_attention(self):
        self._make()

        _, response = self._group()

        assert response.context["dashboard_summary"]["attention"] == 0


@pytest.mark.django_db
class TestReactionDisplay:
    @pytest.fixture(autouse=True)
    def setup(self, settings):
        settings.USE_I18N = False
        self.user = UserFactory()
        self.client = Client()
        self.client.force_login(self.user)

    def _make(self, status_name, **kwargs):
        relation = RelationFactory(status=_status(status_name), **kwargs)
        create_or_update_permission(self.user, relation, permission_level=PermissionLevel.OWNER)
        return relation

    def test_detail_shows_reaction_with_status_wording(self):
        given = self._make("Given", reaction_rating=4, reaction_note="Big smile")
        abandoned = self._make("Abandoned", reaction_rating=2, reaction_note="Too pricey")

        given_html = self.client.get(
            reverse("gift_manager:relation_detail", kwargs={"pk": given.relation_id}),
            HTTP_HX_REQUEST="true",
        ).content.decode()
        abandoned_html = self.client.get(
            reverse("gift_manager:relation_detail", kwargs={"pk": abandoned.relation_id}),
            HTTP_HX_REQUEST="true",
        ).content.decode()

        assert "Their reaction" in given_html
        assert "Big smile" in given_html
        assert "4 out of 5" in given_html
        assert "How much they would have liked it" in abandoned_html
        assert "Too pricey" in abandoned_html

    def test_detail_hides_reaction_when_status_is_not_terminal(self):
        relation = self._make("Planned", reaction_rating=4, reaction_note="Hidden note")

        html = self.client.get(
            reverse("gift_manager:relation_detail", kwargs={"pk": relation.relation_id}),
            HTTP_HX_REQUEST="true",
        ).content.decode()

        assert "Hidden note" not in html

    def test_person_detail_lists_given_and_abandoned_reactions(self):
        from gift_manager.tests.factories import PersonFactory

        person = PersonFactory()
        create_or_update_permission(self.user, person, permission_level=PermissionLevel.OWNER)
        self._make("Given", person=person, reaction_rating=2)
        loved = self._make("Given", person=person, reaction_rating=5)
        abandoned = self._make("Abandoned", person=person, reaction_rating=1, reaction_note="Nope")
        self._make("Given", person=person)

        response = self.client.get(
            reverse("gift_manager:person_detail", kwargs={"pk": person.person_id}),
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 200
        assert [r.pk for r in response.context["given_reactions"]][0] == loved.pk
        assert len(response.context["given_reactions"]) == 2
        assert [r.pk for r in response.context["abandoned_reactions"]] == [abandoned.pk]
        html = response.content.decode()
        assert 'data-reaction-list="given"' in html
        assert 'data-reaction-list="abandoned"' in html
        assert "Abandoned ideas" in html
        assert "Nope" in html

    def test_person_detail_includes_group_plan_reactions_flagged_as_group(self):
        from gift_manager.tests.factories import PersonFactory
        from gift_manager.tests.factories import PersonGroupFactory

        person = PersonFactory()
        group = PersonGroupFactory()
        person.groups.add(group)
        create_or_update_permission(self.user, person, permission_level=PermissionLevel.OWNER)
        relation = GroupRelationFactory(group=group, status=_status("Given"), reaction_rating=4)
        create_or_update_permission(self.user, relation, permission_level=PermissionLevel.OWNER)

        response = self.client.get(
            reverse("gift_manager:person_detail", kwargs={"pk": person.person_id}),
            HTTP_HX_REQUEST="true",
        )

        assert [r.pk for r in response.context["given_reactions"]] == [relation.pk]
        assert group.name in response.content.decode()

    def test_person_detail_without_reactions_has_no_history_section(self):
        from gift_manager.tests.factories import PersonFactory

        person = PersonFactory()
        create_or_update_permission(self.user, person, permission_level=PermissionLevel.OWNER)
        self._make("Given", person=person)

        response = self.client.get(
            reverse("gift_manager:person_detail", kwargs={"pk": person.person_id}),
            HTTP_HX_REQUEST="true",
        )

        assert "reaction-history" not in response.content.decode()

    def test_edit_form_shows_reaction_section_for_given_only(self):
        given = self._make("Given", reaction_rating=3)
        planned = self._make("Planned")

        given_html = self.client.get(
            reverse("gift_manager:relation_edit", kwargs={"pk": given.relation_id}),
            HTTP_HX_REQUEST="true",
        ).content.decode()
        planned_html = self.client.get(
            reverse("gift_manager:relation_edit", kwargs={"pk": planned.relation_id}),
            HTTP_HX_REQUEST="true",
        ).content.decode()

        assert "data-reaction-fields hidden" not in given_html
        assert "data-reaction-fields" in given_html
        assert "data-reaction-fields hidden" in planned_html
        assert "data-rateable-statuses" in given_html


@pytest.mark.django_db
class TestReactionOnCards:
    """Inline stars on unrated cards, read-only stars plus edit link on rated ones."""

    @pytest.fixture(autouse=True)
    def setup(self, settings):
        settings.USE_I18N = False
        self.user = UserFactory()
        self.client = Client()
        self.client.force_login(self.user)

    def _make(self, status_name, *, level=PermissionLevel.OWNER, **kwargs):
        relation = RelationFactory(status=_status(status_name), **kwargs)
        create_or_update_permission(self.user, relation, permission_level=level)
        return relation

    def _workspace_html(self):
        response = self.client.get(reverse("gift_manager:relations"))
        assert response.status_code == 200
        return response.content.decode()

    @pytest.mark.parametrize("status_name", ["Given", "Abandoned"])
    def test_unrated_terminal_card_has_inline_stars(self, status_name):
        relation = self._make(status_name)

        html = self._workspace_html()

        assert "data-rating-inline" in html
        assert f'hx-post="{_reaction_url(relation)}"' in html
        # Outlined stars keep unrated cards visibly different from rated (solid) ones.
        assert 'class="far fa-star"' in html

    def test_abandoned_inline_stars_use_estimate_wording(self):
        self._make("Abandoned")

        assert "How much would they have liked it?" in self._workspace_html()

    def test_rated_card_is_read_only_with_edit_link(self):
        relation = self._make("Given", reaction_rating=4)

        html = self._workspace_html()

        assert "data-rating-inline" not in html
        assert "4 out of 5" in html
        assert 'aria-label="Edit reaction"' in html
        assert f'data-edit-url="{_reaction_url(relation)}"' in html

    def test_viewer_sees_stars_without_controls(self):
        self._make("Given", level=PermissionLevel.VIEWER, reaction_rating=4)
        self._make("Given", level=PermissionLevel.VIEWER)

        html = self._workspace_html()

        assert "4 out of 5" in html
        assert "data-rating-inline" not in html
        assert 'aria-label="Edit reaction"' not in html

    @pytest.mark.parametrize("status_name", ["Idea", "Planned", "Purchased"])
    def test_non_terminal_card_has_no_rating_controls(self, status_name):
        self._make(status_name)

        html = self._workspace_html()

        assert "data-rating-inline" not in html
        assert 'aria-label="Edit reaction"' not in html
