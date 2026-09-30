"""Views for person birthdays: forms, detail page, dashboard section and plan shortcut."""

import re
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from django.utils import translation

from gift_manager.forms import RelationForm
from gift_manager.models import Event
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.services import PermissionService
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def client_user(client, user):
    client.force_login(user)
    return client


def _grant(user, person, level):
    PermissionService.create_or_update_permission(user, person, permission_level=level)


def _person_with_birthday_in(days, *, user, level=PermissionLevel.VIEWER, **kwargs):
    """Create a person whose birthday is ``days`` days from today, visible to user."""
    target = timezone.localdate() + timedelta(days=days)
    person = PersonFactory(birthday_day=target.day, birthday_month=target.month, **kwargs)
    _grant(user, person, level)
    return person


class TestPersonForms:
    def test_create_with_birthday(self, client_user, user):
        response = client_user.post(
            reverse("gift_manager:person_create"),
            {
                "first_name": "Anna",
                "birthday_day": "14",
                "birthday_month": "7",
                "birthday_year": "1990",
            },
        )

        assert response.status_code == 302
        person = Person.objects.get(first_name="Anna")
        assert (person.birthday_day, person.birthday_month, person.birthday_year) == (14, 7, 1990)

    def test_create_with_birthday_without_year(self, client_user):
        client_user.post(
            reverse("gift_manager:person_create"),
            {"first_name": "Anna", "birthday_day": "14", "birthday_month": "7"},
        )

        person = Person.objects.get(first_name="Anna")
        assert (person.birthday_day, person.birthday_month, person.birthday_year) == (14, 7, None)

    def test_create_without_birthday_still_works(self, client_user):
        response = client_user.post(reverse("gift_manager:person_create"), {"first_name": "Anna"})

        assert response.status_code == 302
        assert Person.objects.get(first_name="Anna").has_birthday is False

    def test_leap_day_without_year_is_accepted(self, client_user):
        client_user.post(
            reverse("gift_manager:person_create"),
            {"first_name": "Leap", "birthday_day": "29", "birthday_month": "2"},
        )

        assert Person.objects.get(first_name="Leap").has_birthday is True

    @pytest.mark.parametrize(
        "data",
        [
            {"birthday_day": "30", "birthday_month": "2"},
            {"birthday_day": "29", "birthday_month": "2", "birthday_year": "2001"},
            {"birthday_day": "5"},
            {"birthday_month": "5"},
            {"birthday_year": "1990"},
            {"birthday_day": "32", "birthday_month": "1"},
        ],
    )
    def test_invalid_birthday_is_rejected(self, client_user, data):
        response = client_user.post(
            reverse("gift_manager:person_create"), {"first_name": "Bad", **data}
        )

        assert response.status_code == 200
        assert not Person.objects.filter(first_name="Bad").exists()
        form = response.context["form"]
        assert any(name.startswith("birthday_") for name in form.errors)

    def test_edit_and_clear_birthday(self, client_user, user):
        person = PersonFactory(birthday_day=1, birthday_month=1, birthday_year=1980)
        _grant(user, person, PermissionLevel.EDITOR)
        url = reverse("gift_manager:person_edit", kwargs={"pk": person.person_id})

        client_user.post(
            url,
            {"first_name": person.first_name, "birthday_day": "2", "birthday_month": "3"},
        )
        person.refresh_from_db()
        assert (person.birthday_day, person.birthday_month, person.birthday_year) == (2, 3, None)

        client_user.post(url, {"first_name": person.first_name})
        person.refresh_from_db()
        assert person.has_birthday is False
        assert person.birthday_year is None

    def test_edit_form_shows_current_birthday_on_page_and_offcanvas(self, client_user, user):
        person = PersonFactory(birthday_day=14, birthday_month=7, birthday_year=1990)
        _grant(user, person, PermissionLevel.EDITOR)
        url = reverse("gift_manager:person_edit", kwargs={"pk": person.person_id})

        for extra in ({}, {"HTTP_HX_REQUEST": "true"}):
            content = client_user.get(url, **extra).content.decode()
            assert 'name="birthday_day"' in content
            assert 'name="birthday_month"' in content
            assert 'name="birthday_year"' in content
            assert '<option value="14" selected>' in content
            assert '<option value="7" selected>' in content
            assert '<option value="1990" selected>' in content

    def test_viewer_cannot_edit_the_birthday(self, client_user, user):
        person = PersonFactory(birthday_day=1, birthday_month=1)
        _grant(user, person, PermissionLevel.VIEWER)

        response = client_user.post(
            reverse("gift_manager:person_edit", kwargs={"pk": person.person_id}),
            {"first_name": person.first_name, "birthday_day": "9", "birthday_month": "9"},
        )

        assert response.status_code in (302, 403)
        person.refresh_from_db()
        assert (person.birthday_day, person.birthday_month) == (1, 1)


class TestPersonDetail:
    def test_viewer_sees_the_birthday(self, client_user, user):
        person = PersonFactory(birthday_day=14, birthday_month=7)
        _grant(user, person, PermissionLevel.VIEWER)

        response = client_user.get(
            reverse("gift_manager:person_detail", kwargs={"pk": person.person_id})
        )

        assert response.status_code == 200
        assert "July 14" in response.content.decode()

    def test_birth_year_is_shown_when_known(self, client_user, user):
        person = PersonFactory(birthday_day=14, birthday_month=7, birthday_year=1990)
        _grant(user, person, PermissionLevel.VIEWER)

        response = client_user.get(
            reverse("gift_manager:person_detail", kwargs={"pk": person.person_id})
        )

        assert "July 14, 1990" in response.content.decode()

    def test_person_without_access_is_not_found(self, client_user):
        person = PersonFactory(birthday_day=14, birthday_month=7)

        response = client_user.get(
            reverse("gift_manager:person_detail", kwargs={"pk": person.person_id})
        )

        assert response.status_code == 404
        assert "July 14" not in response.content.decode()


class TestDashboardBirthdays:
    def test_section_lists_upcoming_birthdays(self, client_user, user):
        person = _person_with_birthday_in(3, user=user, first_name="Anna", family_name="Smith")

        response = client_user.get(reverse("gift_manager:home"))

        assert [item["person"] for item in response.context["upcoming_birthdays"]] == [person]
        content = response.content.decode()
        assert "Upcoming birthdays" in content
        assert "Anna Smith" in content
        assert "In 3 days" in content
        assert "No gift plan yet" in content
        assert f"birthday_for={person.person_id}" in content

    def test_section_sits_between_needs_attention_and_library(self, client_user, user):
        _person_with_birthday_in(3, user=user)

        content = client_user.get(reverse("gift_manager:home")).content.decode()

        assert (
            content.index("Needs attention")
            < content.index("Upcoming birthdays")
            < content.index("Library")
        )

    def test_section_is_absent_without_upcoming_birthdays(self, client_user, user):
        _person_with_birthday_in(90, user=user)
        PersonFactory(birthday_day=None, birthday_month=None)

        response = client_user.get(reverse("gift_manager:home"))

        assert response.context["upcoming_birthdays"] == []
        assert "Upcoming birthdays" not in response.content.decode()

    def test_inaccessible_person_never_appears(self, client_user, user):
        target = timezone.localdate() + timedelta(days=2)
        PersonFactory(
            first_name="Secret",
            family_name="Person",
            birthday_day=target.day,
            birthday_month=target.month,
        )

        response = client_user.get(reverse("gift_manager:home"))

        assert response.context["upcoming_birthdays"] == []
        assert "Secret Person" not in response.content.decode()

    def test_person_shared_with_another_user_only_is_hidden(self, client_user, user):
        other = UserFactory()
        _person_with_birthday_in(2, user=other, first_name="Private")

        response = client_user.get(reverse("gift_manager:home"))

        assert "Private" not in response.content.decode()

    def test_today_and_tomorrow_labels(self, client_user, user):
        _person_with_birthday_in(0, user=user, first_name="Todd")
        _person_with_birthday_in(1, user=user, first_name="Tina")

        content = client_user.get(reverse("gift_manager:home")).content.decode()

        assert "Today" in content
        assert "Tomorrow" in content

    def test_anonymous_visitor_sees_no_birthdays(self, client):
        response = client.get(reverse("gift_manager:home"))

        assert response.status_code == 200
        assert "upcoming_birthdays" not in response.context


class TestBirthdayPlanShortcut:
    def test_prefills_recipient_event_and_due_date(self, client_user, user):
        person = _person_with_birthday_in(10, user=user)

        response = client_user.get(
            reverse("gift_manager:relation_create"), {"birthday_for": str(person.person_id)}
        )

        assert response.status_code == 200
        initial = response.context["form"].initial
        assert initial["recipient"] == f"person:{person.person_id}"
        assert initial["event"] == Event.objects.get_birthday_event().pk
        assert initial["due_date"] == person.next_birthday()
        assert initial["due_date"] == timezone.localdate() + timedelta(days=10)

    def test_prefilled_fields_are_rendered_in_the_offcanvas(self, client_user, user):
        person = _person_with_birthday_in(10, user=user)
        birthday_event = Event.objects.get_birthday_event()

        response = client_user.get(
            reverse("gift_manager:relation_create"),
            {"birthday_for": str(person.person_id)},
            HTTP_HX_REQUEST="true",
        )

        content = response.content.decode()
        assert f'value="person:{person.person_id}" selected' in content
        assert f'value="{birthday_event.pk}" selected' in content
        assert person.next_birthday().isoformat() in content

    def test_birthday_event_is_offered_to_any_user(self, client_user, user):
        person = _person_with_birthday_in(10, user=user)

        response = client_user.get(
            reverse("gift_manager:relation_create"), {"birthday_for": str(person.person_id)}
        )

        queryset = response.context["form"].fields["event"].queryset
        assert Event.objects.get_birthday_event() in queryset

    def test_does_not_create_events_per_person(self, client_user, user):
        people = [_person_with_birthday_in(day, user=user) for day in (3, 4, 5)]
        before = Event.objects.count()

        for person in people:
            client_user.get(
                reverse("gift_manager:relation_create"), {"birthday_for": str(person.person_id)}
            )

        assert Event.objects.count() == before

    def test_inaccessible_person_is_ignored(self, client_user):
        target = timezone.localdate() + timedelta(days=5)
        person = PersonFactory(birthday_day=target.day, birthday_month=target.month)

        response = client_user.get(
            reverse("gift_manager:relation_create"), {"birthday_for": str(person.person_id)}
        )

        assert response.status_code == 200
        initial = response.context["form"].initial
        assert "recipient" not in initial
        assert "due_date" not in initial

    def test_person_without_birthday_is_ignored(self, client_user, user):
        person = PersonFactory()
        _grant(user, person, PermissionLevel.VIEWER)

        response = client_user.get(
            reverse("gift_manager:relation_create"), {"birthday_for": str(person.person_id)}
        )

        assert "recipient" not in response.context["form"].initial

    @pytest.mark.parametrize("value", ["", "not-a-uuid", "12345"])
    def test_invalid_value_is_ignored(self, client_user, value):
        response = client_user.get(reverse("gift_manager:relation_create"), {"birthday_for": value})

        assert response.status_code == 200
        assert "recipient" not in response.context["form"].initial

    def test_plain_create_form_is_unchanged(self, client_user):
        response = client_user.get(reverse("gift_manager:relation_create"))

        assert response.status_code == 200
        assert "recipient" not in response.context["form"].initial

    def test_prefilled_due_date_renders_in_french_for_a_date_input(self, user):
        person = _person_with_birthday_in(10, user=user)

        with translation.override("fr"):
            form = RelationForm(
                user=user,
                initial={
                    "recipient": f"person:{person.person_id}",
                    "due_date": person.next_birthday(),
                },
            )
            html = str(form["due_date"])

        # <input type="date"> only accepts ISO values, not the French dd/mm/yyyy format
        assert f'value="{person.next_birthday().isoformat()}"' in html


class TestGlobalBirthdayEventAccess:
    """A regular user sees the global Birthday event but can only read it."""

    @pytest.fixture
    def birthday_event(self):
        return Event.objects.get_birthday_event()

    def _url(self, name, event):
        return reverse(f"gift_manager:{name}", kwargs={"pk": event.event_id})

    def test_event_list_shows_it_to_every_user(self, client_user, birthday_event):
        response = client_user.get(reverse("gift_manager:events"), {"no_js": "1"})

        detail_urls = [
            row["actions"][0]["url"] for row in response.context["fallback_table_data"]["rows"]
        ]
        assert self._url("event_detail", birthday_event) in detail_urls

    def test_detail_page_is_read_only(self, client_user, birthday_event):
        response = client_user.get(self._url("event_detail", birthday_event))

        assert response.status_code == 200
        buttons = {button["type"]: button for button in response.context["action_buttons"]}
        assert buttons["edit"]["enabled"] is False
        assert buttons["delete"]["enabled"] is False

    def test_dashboard_counts_the_global_event(self, client_user):
        response = client_user.get(reverse("gift_manager:home"))

        assert response.context["stats"]["events"] >= 1

    def test_regular_user_cannot_edit_it(self, client_user, birthday_event):
        url = self._url("event_edit", birthday_event)

        assert client_user.get(url).status_code == 403
        response = client_user.post(url, {"name": "Renamed", "schedule_type": "unscheduled"})

        assert response.status_code == 403
        birthday_event.refresh_from_db()
        assert birthday_event.name == "Birthday"

    def test_regular_user_cannot_delete_it(self, client_user, birthday_event):
        url = self._url("event_delete", birthday_event)

        assert client_user.get(url).status_code == 403
        assert client_user.post(url).status_code == 403
        assert Event.objects.filter(pk=birthday_event.pk).exists()

    def test_regular_user_cannot_leave_it(self, client_user, birthday_event):
        url = self._url("event_delete", birthday_event)

        assert client_user.get(url, {"intent": "leave_access"}).status_code == 403
        assert client_user.post(url, {"intent": "leave_access"}).status_code == 403

    def test_superuser_can_still_manage_it(self, client, birthday_event):
        admin = UserFactory(is_superuser=True)
        client.force_login(admin)

        response = client.get(self._url("event_edit", birthday_event))

        assert response.status_code == 200

    def test_share_page_does_not_offer_it(self, client_user, birthday_event):
        response = client_user.get(reverse("gift_manager:share_objects"))

        assert response.status_code == 200
        assert birthday_event not in response.context["events"]
        assert birthday_event.event_id.hex not in response.content.decode().replace("-", "")

    def test_share_page_preselection_ignores_it(self, client_user, birthday_event):
        response = client_user.get(
            reverse("gift_manager:share_objects"),
            {"entity_type": "event", "ids": str(birthday_event.event_id)},
        )

        assert response.context["preselected"]["events"] == []


class TestBirthdaySelectors:
    """The birthday is three selects on one row, ordered like dates in the active locale."""

    @staticmethod
    def _select_names(html):
        return re.findall(r'<select name="(birthday_\w+)"', html)

    def test_three_selects_share_one_row(self, client_user):
        html = client_user.get(reverse("gift_manager:person_create")).content.decode()

        fieldset = html[html.index("<fieldset") : html.index("</fieldset>")]
        assert len(re.findall(r'<div class="birthday-row">', fieldset)) == 1
        assert len(self._select_names(fieldset)) == 3
        assert 'type="number"' not in fieldset

    def test_day_first_in_french_month_first_in_english(self, user):
        from gift_manager.forms import PersonForm

        with translation.override("fr"):
            assert [f.name for f in PersonForm().birthday_fields] == [
                "birthday_day",
                "birthday_month",
                "birthday_year",
            ]
        with translation.override("en"):
            assert [f.name for f in PersonForm().birthday_fields] == [
                "birthday_month",
                "birthday_day",
                "birthday_year",
            ]

    def test_empty_birthday_selects_the_placeholders(self, user):
        from gift_manager.forms import PersonForm

        html = str(PersonForm()["birthday_day"])

        assert '<option value="" selected>Day</option>' in html
        assert '<option value="31">31</option>' in html
        assert '<option value="32">' not in html

    def test_year_select_shows_a_short_placeholder_and_keeps_the_optional_label(self, user):
        from gift_manager.forms import PersonForm

        form = PersonForm()

        assert '<option value="" selected>Year</option>' in str(form["birthday_year"])
        assert str(form.fields["birthday_year"].label) == "Year (optional)"

    def test_year_placeholder_is_translated(self, user):
        from gift_manager.forms import PersonForm

        with translation.override("fr"):
            assert '<option value="" selected>Année</option>' in str(PersonForm()["birthday_year"])

    def test_year_choices_run_from_this_year_back_to_1900(self, user):
        from gift_manager.forms import PersonForm

        years = [value for value, _ in PersonForm().fields["birthday_year"].choices if value != ""]

        assert years[0] == timezone.localdate().year
        assert years[-1] == 1900
        assert years == sorted(years, reverse=True)

    def test_stored_year_outside_the_range_is_kept_when_editing(self, user):
        from gift_manager.forms import PersonForm

        person = PersonFactory(birthday_day=3, birthday_month=4, birthday_year=1850)

        form = PersonForm(instance=person)

        assert 1850 in [value for value, _ in form.fields["birthday_year"].choices]
        assert '<option value="1850" selected>' in str(form["birthday_year"])

    @pytest.mark.parametrize(
        "data",
        [
            {"birthday_day": "32", "birthday_month": "1"},
            {"birthday_day": "1", "birthday_month": "13"},
        ],
    )
    def test_forged_out_of_range_values_are_rejected(self, client_user, data):
        response = client_user.post(
            reverse("gift_manager:person_create"), {"first_name": "Forged", **data}
        )

        assert response.status_code == 200
        assert not Person.objects.filter(first_name="Forged").exists()

    def test_future_year_is_rejected_even_if_forged(self, client_user):
        response = client_user.post(
            reverse("gift_manager:person_create"),
            {
                "first_name": "Future",
                "birthday_day": "1",
                "birthday_month": "1",
                "birthday_year": str(timezone.localdate().year + 1),
            },
        )

        assert response.status_code == 200
        assert "birthday_year" in response.context["form"].errors

    def test_errors_are_shown_under_the_row(self, client_user):
        response = client_user.post(
            reverse("gift_manager:person_create"),
            {"first_name": "Bad", "birthday_day": "30", "birthday_month": "2"},
        )

        content = response.content.decode()
        assert "Enter a valid date." in content
        assert content.index("</fieldset>") > content.index("Enter a valid date.")
