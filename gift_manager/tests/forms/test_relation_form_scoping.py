"""Relation forms scope their own choices to the user (GM-AUD-018)."""

import pytest

from gift_manager.forms import GiftRelationForm
from gift_manager.forms import PersonGroupRelationForm
from gift_manager.forms import PersonRelationForm
from gift_manager.forms import RelationForm
from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

FORMS_WITH_EVENT_ONLY = [PersonRelationForm, PersonGroupRelationForm, GiftRelationForm]
FORMS_WITH_EVENT_AND_GIFT = [RelationForm]


@pytest.fixture
def user():
    return UserFactory()


@pytest.fixture
def events(user):
    return EventFactory(shared_with=[user]), EventFactory()


@pytest.fixture
def gifts(user):
    return GiftFactory(shared_with=[user]), GiftFactory()


@pytest.mark.parametrize("form_class", FORMS_WITH_EVENT_ONLY + FORMS_WITH_EVENT_AND_GIFT)
def test_event_choices_are_limited_to_accessible_events(form_class, user, events):
    mine, someone_elses = events

    form = form_class(user=user)

    assert set(form.fields["event"].queryset) == {mine}
    assert someone_elses not in form.fields["event"].queryset


@pytest.mark.parametrize("form_class", FORMS_WITH_EVENT_ONLY + FORMS_WITH_EVENT_AND_GIFT)
def test_event_choices_are_empty_without_a_user(form_class, events):
    form = form_class()

    assert not form.fields["event"].queryset.exists()


@pytest.mark.parametrize("form_class", FORMS_WITH_EVENT_AND_GIFT)
def test_gift_choices_are_limited_to_accessible_gifts(form_class, user, gifts):
    mine, someone_elses = gifts

    form = form_class(user=user)

    assert set(form.fields["gift"].queryset) == {mine}
    assert someone_elses not in form.fields["gift"].queryset


@pytest.mark.parametrize("form_class", FORMS_WITH_EVENT_AND_GIFT)
def test_gift_choices_are_empty_without_a_user(form_class, gifts):
    assert not form_class().fields["gift"].queryset.exists()


@pytest.mark.parametrize("form_class", FORMS_WITH_EVENT_ONLY)
def test_gift_choices_are_limited_when_the_form_exposes_a_gift(form_class, user, gifts):
    mine, someone_elses = gifts
    form = form_class(user=user)

    if "gift" in form.fields:
        assert set(form.fields["gift"].queryset) == {mine}


def test_forged_event_id_is_rejected_by_the_form(user, events):
    _mine, someone_elses = events

    form = PersonRelationForm(data={"event": someone_elses.pk}, user=user)

    assert not form.is_valid()
    assert "event" in form.errors
