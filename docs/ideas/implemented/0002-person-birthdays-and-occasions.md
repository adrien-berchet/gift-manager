# Idea: Person Birthdays And Personal Occasions

## Status

Implemented

## Summary

Let users record a birthday (and optionally other yearly occasions) on a
person, and surface those dates proactively. The dashboard lists people whose
occasion is coming up and offers a one-click "Create a gift plan for Anna's
birthday" action that pre-fills the recipient, the occasion and the due date.

## Motivation

`Person` currently stores only a name, email and groups, and `Event` is a
standalone object with no link to a person. The dashboard's "recipients with
upcoming occasions" section only shows recipients that already have a gift plan
attached to an event. A user who has not yet created a plan for an upcoming
birthday gets no signal at all, which is the exact situation the app should
prevent.

## User Value

- Users are reminded of birthdays without creating an event by hand per person
  and per year.
- Starting a gift plan for an upcoming occasion takes one click.
- The dashboard answers "who do I need to think about soon?" even for people
  with no plan yet.

## Possible Scope

- Optional `birthday` field on `Person` (day and month required, year
  optional), editable in the person form and shown on the detail page.
- A helper that computes the next occurrence of a birthday, reusing the
  approach of `Event.next_occurrence`.
- Dashboard section "Upcoming birthdays" listing people with a birthday in the
  next N days and whether a gift plan already exists for that occasion.
- A create-gift-plan shortcut that pre-fills recipient, due date and an
  occasion event.
- Decide and implement how the occasion maps to an `Event` (auto-created
  yearly recurring event per person, or a virtual occasion).

## Out Of Scope

- Email or push reminders (see the reminders idea).
- Importing birthdays from contacts or external calendars.
- Occasions for groups.
- Age calculation or age-based suggestions.

## Implementation Notes For AI Agent

- `Person` model and its manager: `gift_manager/models.py`; any new field needs
  a migration, form updates in `gift_manager/forms.py` and
  `gift_manager/templates/gift_manager/includes/forms/person_fields.html`.
- Person detail: `gift_manager/templates/gift_manager/includes/person_detail_partial.html`.
- Dashboard data: `home` and the action-group helpers in
  `gift_manager/views/common.py`; template `gift_manager/templates/gift_manager/home.html`.
- Card shortcuts follow the pattern in `gift_manager/gift_plan_actions.py` and
  `gift_manager/gift_plan_cards.py`.
- Respect `PermissionService` and the `accessible_by(user)` managers; do not
  expose birthdays of people the user cannot access.
- Keep translations current (`python manage.py makemessages -l fr`).

Recommended starting context:

- `docs/ai/architecture.md`
- `docs/ai/testing.md`
- `gift_manager/models.py`, `gift_manager/views/common.py`

## Acceptance Criteria

- A user can set, edit and clear a person's birthday in both the offcanvas and
  the full-page forms.
- The dashboard lists accessible people with a birthday in the upcoming window,
  ordered by next occurrence, including leap-day birthdays.
- The shortcut opens the gift-plan form with recipient, due date and occasion
  pre-filled.
- People the user cannot access never appear.
- Model, view and permission tests cover the new behaviour; `tox run -e lint`
  passes.

## Dependencies Or Related Ideas

- Feeds the reminders idea (`0003`).
- Complements the recipient profile notes idea (`0006`).

## Decisions

- **Visibility:** the birthday is shared with everyone who can view the person
  (`Person.objects.accessible_by(user)`); only editors can change it.
- **Occasions are computed, not stored:** birthdays never create `Event` rows per
  person or per year. `Person.next_birthday()` derives the next occurrence (February 29
  falls on February 28 in non-leap years) and `gift_manager/birthdays.py` builds the
  dashboard list from it.
- **One global Birthday event:** gift plans created from a birthday point at a single
  global event (`Event.is_global` and `Event.is_birthday`, created by migration `0032`,
  `Event.objects.get_birthday_event()`). It is unscheduled: the plan's due date is the
  recipient's next birthday. Every user can view it; only superusers can change it. Global
  events are visible through `EventQuerySet.accessible_by` and get a VIEWER floor in
  `PermissionService.get_effective_permission`; `SharingService.needs_cascade_grant`
  keeps plan sharing from requiring ownership of a global event. Other celebrations
  (Christmas, ...) are still ordinary user-created events; more global events would only
  need the `is_global` flag.
- **Window:** fixed 30 days (`UPCOMING_BIRTHDAYS_DAYS`), not configurable.
- **Plan coverage:** a birthday counts as covered by a live (not abandoned) plan for the
  person that the user can see, due up to 60 days before the birthday (early or overdue)
  or on it, and that uses the Birthday event or is due exactly on the birthday. Plans
  without a due date, or addressed to a group the person belongs to, are not counted.
  Uncovered birthdays show a "No gift plan yet" warning and the shortcut
  (`relation_create?birthday_for=<person_id>`).
- **Known limits:** the Birthday event name is not translated (`Event.name` is a plain
  field), a superuser can rename or delete it (plans then lose their event and a new one is
  created on next use), and birthdays are stored in plain text, unlike emails, because their
  visibility is exactly the person's.
