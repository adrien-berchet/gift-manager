# New User Guidance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Explain Gift Manager's concepts and features to new users through public Help pages
and a dismissible, data-driven "Getting started" checklist on the dashboard.

**Architecture:** A static topic registry (`gift_manager/help_topics.py`) drives two
server-rendered views under `/help/`. Each topic's content is a translated template. A small
module (`gift_manager/getting_started.py`) works out the checklist steps from data the user owns,
using a new `owned_by(user)` queryset helper. The dashboard renders the card unless
`Profile.getting_started_hidden_at` is set. Plain POST views hide the card and show it again.
Empty states and existing intro lines link to the matching Help topic.

**Tech Stack:** Django 5.1 templates and class-based views, Bootstrap, PostgreSQL, pytest
(+ factories), Playwright e2e.

**Spec:** `docs/superpowers/specs/2026-11-17-new-user-guidance-design.md`

## Global Constraints

- No new production dependency; no Markdown library; no screenshots in Help pages.
- Core flows (Help pages, hide, show again) work as plain links and form POSTs, without custom
  JavaScript.
- Every new user-facing string is translated into French. Run
  `python manage.py makemessages -l fr` **without** `--no-location`, fill in
  `locale/fr/LC_MESSAGES/django.po`, then run `python manage.py compilemessages`.
  `gift_manager/tests/test_locale_coverage.py::test_every_template_and_python_string_has_a_french_translation`
  must pass at the end of every task.
- Use the product vocabulary: gift plan, recipient, gift, event, status. Never "relation".
- Help pages are public (no login). Hide and show-again require login.
- Checklist steps count only objects the user **owns** (`PermissionLevel.OWNER`), never ones
  that are only shared with them.
- Nothing hides the card automatically; only an explicit Hide sets
  `Profile.getting_started_hidden_at`.
- Give each concept the Font Awesome icon the app already uses for it: the navbar icon where
  there is one, otherwise the icon on the Profile page (wishlist, bookmarklet).
- Use PostgreSQL for tests (`tox run -e py311 -- …`). Don't run `tox -e py311` and `tox -e e2e`
  at the same time, because they share the test database.
- Lint: `tox -e lint` needs Python 3.10, which may be missing. If so, run
  `git status --short | awk '{print $2}' | xargs pre-commit run --files`.

## Review Focus

1. **Unknown or odd Help slug** (`/help/nope/`, `/help/../base/`): returns 404. The topic
   template is always taken from the registry, never built from the URL. → Task 2 test.
2. **Only shared data:** a user whose recipients, gifts and plans were all shared by a friend
   sees steps 1 to 4 unticked. → Task 3 test.
3. **Plan statuses under the French locale:** Purchased/Given detection still works when the
   active language is `fr`, because it goes through the `status_en` slug helpers. → Task 3 test.
4. **Logged-out POST to hide or show:** redirects to login and changes nothing. A repeated hide
   or show leaves the state unchanged and still redirects. → Task 4 test.
5. **Filtered gift list:** `?unassigned=1` with gifts that all have plans still shows the grid
   and its own empty result, not the "no gifts yet" empty state. That state depends on whether
   any gift is accessible, not on the filter. → Task 5 test.

---

### Task 1: `owned_by(user)` queryset helper

**Files:**
- Modify: `gift_manager/models.py:117-122` (`UserPermissionQuerySet`)
- Test: `gift_manager/tests/models/test_owned_by.py` (create)

**Interfaces:**
- Produces: `UserPermissionQuerySet.owned_by(user) -> QuerySet`, available as
  `Person.objects.owned_by(user)`, `PersonGroup.objects…`, `Gift.objects…`,
  `Relation.objects…`. It returns the objects on which `user` has a permission row whose
  `permission_type == PermissionLevel.OWNER`.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.django_db
class TestOwnedBy:
    def test_returns_owned_person_only(self, user_factory):
        alice, bob = user_factory(), user_factory()
        owned = PersonFactory(owner=alice)
        shared = PersonFactory(owner=bob, shared_with=[alice])  # VIEWER for alice
        assert list(Person.objects.owned_by(alice)) == [owned]
        assert shared not in Person.objects.owned_by(alice)

    @pytest.mark.parametrize("level", [PermissionLevel.VIEWER, PermissionLevel.EDITOR])
    def test_non_owner_levels_excluded(self, user_factory, level): ...
        # gift with create_or_update_permission(alice, gift, permission_level=level)
        # -> not in Gift.objects.owned_by(alice)

    def test_works_for_groups_gifts_and_plans(self, user_factory): ...
        # one owned PersonGroup, Gift, Relation each
        # (create_or_update_permission(alice, obj, permission_level=PermissionLevel.OWNER))
        # -> each appears in its model's owned_by(alice)
```

`create_or_update_permission(user, obj, *, permission_level=PermissionLevel.VIEWER,
object_attr=None)` lives in `gift_manager/permissions.py`. `permission_level` is keyword-only.
`Person`, `PersonGroup`, `Gift` and `Relation` managers are all built with
`models.Manager.from_queryset(<X>QuerySet)` on subclasses of `UserPermissionQuerySet`, so the
method is available on all four.

- [ ] **Step 2: Run the tests and check that they fail**

Run: `tox run -e py311 -- gift_manager/tests/models/test_owned_by.py`
Expected: FAIL with `AttributeError: … has no attribute 'owned_by'`.

- [ ] **Step 3: Implement `owned_by(self, user)` on `UserPermissionQuerySet`**

Filter through the `shared_with` through-model, using
`self.model._meta.get_field("shared_with").remote_field.through` and its FK to `self.model`.
Keep it to a single query: a `pk__in` subquery on through rows with `user=user,
permission_type=PermissionLevel.OWNER`. Don't use a join on `shared_with` with a second filter,
because it would combine conditions from different rows.

- [ ] **Step 4: Run the tests and check that they pass**

Run: `tox run -e py311 -- gift_manager/tests/models/test_owned_by.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gift_manager/models.py gift_manager/tests/models/test_owned_by.py
git commit -m "Feat: Add an owned_by queryset helper for permissioned models"
```

---

### Task 2: Public Help section

**Files:**
- Create: `gift_manager/help_topics.py`
- Create: `gift_manager/views/help.py`
- Modify: `gift_manager/views/__init__.py` (export the two views)
- Modify: `gift_manager/urls.py` (two routes)
- Create: `gift_manager/templates/gift_manager/help/index.html`
- Create: `gift_manager/templates/gift_manager/help/topic.html`
- Create: `gift_manager/templates/gift_manager/help/topics/{how-it-works,wishlist,friends-and-sharing,secret-santa,received-gifts,quick-capture,reminders}.html`
- Modify: `gift_manager/templates/gift_manager/base.html:~166` (Help link in the navbar utilities, before Profile, for all users)
- Modify: `gift_manager/templates/gift_manager/home.html:~224-240` (logged-out welcome page links to `how-it-works`)
- Create (if needed): `gift_manager/static/gift_manager/css/help.css`
- Test: `gift_manager/tests/test_help_pages.py` (create)
- Modify: `locale/fr/LC_MESSAGES/django.po`

**Interfaces:**
- Produces, in `gift_manager/help_topics.py`:
  - `HelpTopic(NamedTuple)` with fields `slug: str`, `title: str` (lazy), `summary: str`
    (lazy), `icon: str` (Font Awesome classes), `template: str`.
  - `HELP_TOPICS: tuple[HelpTopic, ...]`, in display order:

    | slug | title | icon |
    |---|---|---|
    | `how-it-works` | How Gift Manager works | `fas fa-hand-holding-heart` |
    | `wishlist` | Wishlist and guest links | `fas fa-gift` |
    | `friends-and-sharing` | Friends and sharing | `fas fa-share-alt` |
    | `secret-santa` | Secret Santa | `fas fa-hat-wizard` |
    | `received-gifts` | Received gifts | `fas fa-box-open` |
    | `quick-capture` | Quick capture (bookmarklet) | `fas fa-bookmark` |
    | `reminders` | Reminders and calendar feed | `fas fa-calendar-alt` |

  - `get_help_topic(slug: str) -> HelpTopic | None`.
  - `CORE_SECTION_IDS = ("gift-plans", "recipients", "gifts", "occasions", "statuses",
    "suggestions", "typical-workflow")`: the anchor `id`s on the `how-it-works` page, linked
    to by Task 3.
- Produces URL names: `gift_manager:help_index` → `help/`;
  `gift_manager:help_topic` → `help/<slug:topic>/`.
- Produces context: `HelpIndexView` gives `topics` (the registry) and `getting_started_hidden`
  (always `False` in this task; Task 4 fills it in). `HelpTopicView` gives `topic` and `topics`.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.django_db
class TestHelpPages:
    def test_index_is_public_and_lists_every_topic(self, client):
        response = client.get(reverse("gift_manager:help_index"))
        assert response.status_code == 200
        for topic in HELP_TOPICS:
            assert reverse("gift_manager:help_topic", args=[topic.slug]) in response.content.decode()

    @pytest.mark.parametrize("slug", [t.slug for t in HELP_TOPICS])
    def test_every_topic_renders_logged_out(self, client, slug): ...  # 200, contains str(topic.title)

    def test_topic_renders_logged_in(self, authenticated_client): ...  # how-it-works 200

    @pytest.mark.parametrize("slug", ["nope", "base", "topics"])
    def test_unknown_topic_is_404(self, client, slug): ...

    def test_core_page_has_every_section_anchor(self, client):
        html = client.get(reverse("gift_manager:help_topic", args=["how-it-works"])).content.decode()
        for section_id in CORE_SECTION_IDS:
            assert f'id="{section_id}"' in html

    def test_navbar_has_help_link_for_everyone(self, client, authenticated_client): ...
        # GET home logged out and logged in: href of help_index present in both

    def test_welcome_page_links_to_core_topic(self, client): ...
```

- [ ] **Step 2: Run the tests and check that they fail**

Run: `tox run -e py311 -- gift_manager/tests/test_help_pages.py`
Expected: FAIL with `NoReverseMatch` / `ImportError`.

- [ ] **Step 3: Implement the registry, views, URLs and templates**

- `HelpIndexView(TemplateView)` and `HelpTopicView(TemplateView)` live in
  `views/help.py`, with no login mixin. `HelpTopicView` raises `Http404` when
  `get_help_topic(kwargs["topic"])` is `None`.
- `topic.html` extends `base.html`, shows the title, then `{% include topic.template %}`, then a
  small "Other topics" list. Use the Bootstrap card and section styles of existing pages.
- **Topic content.** Keep it short and task-oriented, in `{% trans %}` / `{% blocktrans %}`.
  Each feature page answers three things: what it's for, when to use it, and how to start, with
  a link to the page where you do it. `how-it-works` has one `<section id="…">` per
  `CORE_SECTION_IDS` entry:
  - gift plans connect a recipient, a gift, usually an occasion, and a status;
  - recipients are people and groups, and a plan for a group is different from a plan for each
    member;
  - gifts are a catalogue of ideas, reusable across plans;
  - occasions are events and birthdays;
  - statuses run Idea → Planned → Purchased → Given, with Abandoned as the way out;
  - suggestions from the catalogue and from AI on the recipient page;
  - a typical workflow from first plan to Given.
- **Navbar Help link.** The utilities list (`ul.navbar-utilities`, `base.html:145`) sits inside
  `#navbarSupportedContent`, so on phones it is reached through the navbar toggler. Add an
  `<li class="nav-item">` link to `help_index`
  (`fas fa-circle-question`, label "Help") before the Profile item. Mark it active with the
  existing pattern `{% if 'help_' in request.resolver_match.url_name %}`. No other URL name
  contains `help_`.
- **Phone layout of the utilities.** On phones, `.navbar-utilities` is a 2-column grid whose last
  item spans both columns (`gift_manager/static/gift_manager/css/base-layout.css:272-283`). One
  more item would leave a half-empty row for a regular logged-in user (search, theme, Help,
  Profile, language, then Sign Out across both columns). Add a phone-only rule in the same media
  block that makes the Help item span both columns as well. Check the menu at 390 px wide, both
  logged in and logged out. `test_phone_layout.py` runs in Task 6.

- [ ] **Step 4: Run the tests and check that they pass**

Run: `tox run -e py311 -- gift_manager/tests/test_help_pages.py`
Expected: PASS.

- [ ] **Step 5: Translate**

Run `python manage.py makemessages -l fr`, fill in every new `msgid`, then run
`python manage.py compilemessages`.
Run: `tox run -e py311 -- gift_manager/tests/test_locale_coverage.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add gift_manager/help_topics.py gift_manager/views/help.py gift_manager/views/__init__.py \
  gift_manager/urls.py gift_manager/templates/gift_manager/help gift_manager/templates/gift_manager/base.html \
  gift_manager/templates/gift_manager/home.html gift_manager/static/gift_manager/css \
  gift_manager/tests/test_help_pages.py locale/fr/LC_MESSAGES
git commit -m "Feat: Add public Help pages explaining concepts and features"
```

---

### Task 3: Getting-started step computation

**Files:**
- Create: `gift_manager/getting_started.py`
- Test: `gift_manager/tests/test_getting_started.py` (create)
- Modify: `locale/fr/LC_MESSAGES/django.po`

**Interfaces:**
- Consumes: `owned_by(user)` (Task 1); `gift_manager:help_topic` and `CORE_SECTION_IDS`
  (Task 2); `is_purchased_status` / `is_given_status` from `gift_manager/statuses.py`.
- Produces:

```python
@dataclass(frozen=True)
class GettingStartedStep:
    key: str            # "recipient" | "gift" | "plan" | "progress" | "wish" | "friend"
    label: str
    done: bool
    action_url: str
    help_url: str
    optional: bool
    guided_url: str | None = None

@dataclass(frozen=True)
class GettingStarted:
    steps: tuple[GettingStartedStep, ...]
    @property
    def core_steps(self) -> tuple[GettingStartedStep, ...]: ...
    @property
    def optional_steps(self) -> tuple[GettingStartedStep, ...]: ...
    @property
    def core_done_count(self) -> int: ...
    @property
    def all_done(self) -> bool: ...   # every step, optional ones included

def compute_getting_started(user) -> GettingStarted
```

Step table. The labels are copy, and the help URLs use Task 2's anchors:

| key | label | done when | action_url | help_url | optional |
|---|---|---|---|---|---|
| recipient | Add a recipient | `Person.objects.owned_by(u)` or `PersonGroup.objects.owned_by(u)` exists | `person_create` | `how-it-works#recipients` | no |
| gift | Add a gift idea | `Gift.objects.owned_by(u)` exists | `gift_create` | `how-it-works#gifts` | no |
| plan | Create your first gift plan | `Relation.objects.owned_by(u)` exists | `relation_create` (+ `guided_url` = `relation_guided_create`) | `how-it-works#gift-plans` | no |
| progress | Move a plan to Purchased or Given | owned plan with `status_id` in the progress status ids | `relations` | `how-it-works#statuses` | no |
| wish | Add something to your wishlist | `Wish.objects.for_wisher(u).filter(is_deleted_by_wisher=False)` exists (archived wishes count, soft-deleted ones don't) | `wish_create` | `wishlist` | yes |
| friend | Connect with a friend | `u.profile.friends` exists or `Invitation.objects.filter(sender=u)` exists | `send_invitation` | `friends-and-sharing` | yes |

Progress status ids: `[s.pk for s in RelationStatus.objects.all() if is_purchased_status(s) or
is_given_status(s)]`. The status table is tiny, and the helpers already handle translation.
That's one small extra query on top of one `exists()` per step; the design doc says the same.

Add to the test list: `test_soft_deleted_wish_does_not_tick_wish_step` (a wish with
`is_deleted_by_wisher=True` → not done) and `test_archived_wish_ticks_wish_step`.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.django_db
class TestComputeGettingStarted:
    def test_empty_account_has_nothing_done(self, user):
        gs = compute_getting_started(user)
        assert [s.key for s in gs.steps] == ["recipient", "gift", "plan", "progress", "wish", "friend"]
        assert [s.optional for s in gs.steps] == [False] * 4 + [True] * 2
        assert gs.core_done_count == 0 and not gs.all_done

    def test_owned_group_counts_as_recipient(self, user): ...
    def test_owned_gift_ticks_gift_step(self, user): ...
    def test_owned_plan_ticks_plan_step_but_not_progress_when_idea(self, user): ...
    @pytest.mark.parametrize("status", ["Purchased", "Given"])
    def test_purchased_or_given_plan_ticks_progress(self, user, status): ...
    def test_progress_detected_under_french_locale(self, user): ...      # with translation.override("fr")
    def test_shared_only_objects_tick_nothing(self, user, user_factory): ...
        # friend owns person, gift, Given plan; all shared with `user` as VIEWER/EDITOR
        # -> steps recipient/gift/plan/progress all done == False
    def test_wish_ticks_wish_step(self, user): ...
    def test_friend_or_sent_invitation_ticks_friend_step(self, user, user_factory): ...  # two cases
    def test_all_done_when_every_step_done(self, user, user_factory): ...
    def test_plan_step_offers_guided_url(self, user):
        plan = next(s for s in compute_getting_started(user).steps if s.key == "plan")
        assert plan.guided_url == reverse("gift_manager:relation_guided_create")
```

- [ ] **Step 2: Run the tests and check that they fail**

Run: `tox run -e py311 -- gift_manager/tests/test_getting_started.py`
Expected: FAIL with `ModuleNotFoundError: gift_manager.getting_started`.

- [ ] **Step 3: Implement `compute_getting_started(user) -> GettingStarted`**

Use the table above. Each check is a single `.exists()` query. Labels use `gettext`.

- [ ] **Step 4: Run the tests and check that they pass**

Run: `tox run -e py311 -- gift_manager/tests/test_getting_started.py`
Expected: PASS.

- [ ] **Step 5: Translate the labels and check locale coverage** (same commands as Task 2,
  Step 5).

- [ ] **Step 6: Commit**

```bash
git add gift_manager/getting_started.py gift_manager/tests/test_getting_started.py locale/fr/LC_MESSAGES
git commit -m "Feat: Compute getting-started steps from the user's own data"
```

---

### Task 4: Dashboard card, hide and show again

**Files:**
- Modify: `gift_manager/models.py:397+` (`Profile`: new field)
- Create: `gift_manager/migrations/0052_profile_getting_started_hidden_at.py` (via `makemigrations`)
- Modify: `gift_manager/views/profile.py` (two views, next to `UpdateViewPreferencesView`)
- Modify: `gift_manager/views/__init__.py`, `gift_manager/urls.py`
- Modify: `gift_manager/views/common.py:98+` (`home` context)
- Create: `gift_manager/templates/gift_manager/includes/getting_started_card.html`
- Modify: `gift_manager/templates/gift_manager/home.html`. Include the card as the **first child
  of `#dashboard-live`** (`home.html:33`), before the "Needs attention" section. That puts it
  below the topbar (the `<h1>` "Next actions" and its buttons) and inside the block that HTMX
  refreshes through `hx-select="#dashboard-live"`. After a create in the offcanvas, the ticks
  update without a reload. Step action links use `data-action="create"`, like the dashboard's
  other create buttons, so they open in the offcanvas. The "progress" step's link goes to the
  gift plans list, so it gets no `data-action`. The "What's this?" links are plain links.
- Modify: `gift_manager/views/help.py` and `help/index.html` (show-again form)
- Modify: `gift_manager/static/gift_manager/css/dashboard.css`
- Test: `gift_manager/tests/test_getting_started_card.py` (create)
- Modify: `locale/fr/LC_MESSAGES/django.po`

**Interfaces:**
- Consumes: `compute_getting_started(user) -> GettingStarted` (Task 3); `HelpIndexView`
  (Task 2).
- Produces:
  - `Profile.getting_started_hidden_at = models.DateTimeField(null=True, blank=True,
    editable=False)`.
  - `HideGettingStartedView(LoginRequiredMixin, View)`, POST only. It sets the field to
    `timezone.now()` only if it is null, then redirects to `gift_manager:home`. URL name
    `gift_manager:getting_started_hide`, path `getting-started/hide/`.
  - `ShowGettingStartedView(LoginRequiredMixin, View)`, POST only. It sets the field to `None`,
    then redirects to `gift_manager:home`. URL name `gift_manager:getting_started_show`, path
    `getting-started/show/`.
  - The `home` context gets `getting_started`: a `GettingStarted`, or `None` when the field is
    set.
  - The `HelpIndexView` context gets `getting_started_hidden: bool`, which is true only for an
    authenticated user whose field is set.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.django_db
class TestGettingStartedCard:
    def test_new_user_sees_card(self, authenticated_client):
        html = authenticated_client.get(reverse("gift_manager:home")).content.decode()
        assert 'id="getting-started"' in html
        assert reverse("gift_manager:getting_started_hide") in html

    def test_card_shows_all_set_state_when_everything_done(self, authenticated_client, user, ...): ...
        # every step done -> card still present, contains the "You're all set" copy, still has Hide

    def test_hide_removes_card_and_redirects_home(self, authenticated_client, user): ...
    def test_hidden_card_stays_hidden_when_data_changes(self, authenticated_client, user): ...
        # hide, then delete the user's only wish -> card still absent
    def test_repeated_hide_keeps_first_timestamp(self, authenticated_client, user): ...
    def test_help_index_offers_show_again_only_when_hidden(self, authenticated_client, user, client): ...
        # visible -> no show form; hidden -> form posting to getting_started_show; logged out -> no form
    def test_show_again_restores_card(self, authenticated_client, user): ...
    @pytest.mark.parametrize("name", ["getting_started_hide", "getting_started_show"])
    def test_logged_out_post_redirects_to_login(self, client, name): ...
    @pytest.mark.parametrize("name", ["getting_started_hide", "getting_started_show"])
    def test_get_is_not_allowed(self, authenticated_client, name):  # 405
        ...
    def test_card_links_each_step_to_help(self, authenticated_client): ...
        # every step.help_url appears in the card HTML
```

- [ ] **Step 2: Run the tests and check that they fail**

Run: `tox run -e py311 -- gift_manager/tests/test_getting_started_card.py`
Expected: FAIL (`NoReverseMatch` / missing `id="getting-started"`).

- [ ] **Step 3: Add the field and generate the migration**

Run: `python manage.py makemigrations gift_manager --name profile_getting_started_hidden_at`
Expected: a single `AddField` on `profile`. Read the migration before going on.

- [ ] **Step 4: Implement the views, URLs, `home` context and the Help index context**

Use `http_method_names = ["post"]` for the two views. They need CSRF, so use plain `<form
method="post">` buttons.

- [ ] **Step 5: Implement `includes/getting_started_card.html` and its styles**

- **Layout:** a `<section id="getting-started" aria-labelledby="getting-started-heading">`.
  The heading reads "Getting started". Next to it is the `core_done_count`/4 counter and the
  Hide form button.
- **Core steps:** listed first. "Explore more" comes after them as a small subheading, followed
  by the optional steps.
- **Each step** shows a check icon (`fas fa-circle-check`) or an empty circle (`far fa-circle`).
  An unfinished step links its label to `action_url`. The plan step also has a "Guided" link to
  `guided_url`. Every step has a "What's this?" link to `help_url`.
- **When `all_done`:** show the line "You're all set. You can hide this checklist; it stays
  available from Help." above the list.
- Match the dashboard's existing section and card styling in `dashboard.css`, for light and
  dark themes and phone widths.

- [ ] **Step 6: Run the tests and check that they pass**

Run: `tox run -e py311 -- gift_manager/tests/test_getting_started_card.py gift_manager/tests/test_help_pages.py gift_manager/tests/test_migrations.py`
Expected: PASS.

- [ ] **Step 7: Translate and check locale coverage** (same commands as Task 2, Step 5).

- [ ] **Step 8: Commit**

```bash
git add gift_manager/models.py gift_manager/migrations/0052_profile_getting_started_hidden_at.py \
  gift_manager/views gift_manager/urls.py gift_manager/templates/gift_manager \
  gift_manager/static/gift_manager/css/dashboard.css gift_manager/tests/test_getting_started_card.py \
  locale/fr/LC_MESSAGES
git commit -m "Feat: Show a dismissible getting-started checklist on the dashboard"
```

---

### Task 5: "Learn more" links, gifts empty state, AGENTS.md rule

**Files:**
- Create: `gift_manager/templates/gift_manager/includes/help_learn_more.html`
- Modify (empty states):
  - `relation_list.html:~151` → topic `how-it-works#gift-plans`
  - `recipient_list.html:~226` → `how-it-works#recipients`
  - `secret_santa/exchange_list.html:~39` → `secret-santa`
  - Wishlist and received gifts: **no link in the empty state**. Their intro line, which shows on
    every full-page render, already carries it, and a second identical link would be noise.
- Modify (existing intro lines):
  - `wishlist_list.html:~28` → `wishlist`
  - `received_gift_list.html:~27` → `received-gifts`
  - `profile_detail.html` wishlist (~198), bookmarklet (~215) and received gifts (~231) blurbs →
    `wishlist`, `quick-capture`, `received-gifts`
  - `share_objects.html:~29` → `friends-and-sharing`
- Modify: `gift_manager/views/gift.py:99-110` (`GiftListView.get_context_data`) and
  `gift_list.html:18-55` (server-rendered empty state)
- Modify: `AGENTS.md` (Frontend Notes rule)
- Test: `gift_manager/tests/test_help_links.py` (create)
- Modify (existing tests that load `/gifts/` for a user with no accessible gift and assert on
  the grid; give the user an accessible gift in their setup, without changing what they assert):
  - `gift_manager/tests/views/test_advanced_list_tools.py:7,17-40`
  - `gift_manager/tests/test_quick_action_buttons.py:46-58`: the `GiftFactory()` there is not
    shared with the user.
  - `gift_manager/tests/views/test_ux_review_small_fixes.py:51-62`
- Modify: `locale/fr/LC_MESSAGES/django.po`

**Interfaces:**
- Consumes: `gift_manager:help_topic` (Task 2).
- Produces:
  - `includes/help_learn_more.html` takes `topic` (slug) and an optional `anchor`. It renders
    `<a class="help-learn-more" href="{% url 'gift_manager:help_topic' topic %}{% if anchor %}#{{ anchor }}{% endif %}">`
    containing the icon `fas fa-circle-question` and the text "Learn more".
  - `GiftListView` context gets `has_gifts: bool`, equal to
    `Gift.objects.accessible_by(user).exists()`. It ignores `?unassigned=1` and other filters.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.django_db
class TestHelpLinks:
    @pytest.mark.parametrize(("url_name", "href"), [
        ("relations", "/help/how-it-works/#gift-plans"),
        ("recipients", "/help/how-it-works/#recipients"),
        ("wishlist_list", "/help/wishlist/"),
        ("received_gift_list", "/help/received-gifts/"),
        ("secret_santa_list", "/help/secret-santa/"),
        ("share_objects", "/help/friends-and-sharing/"),
        ("profile_detail", "/help/quick-capture/"),
    ])
    def test_page_links_to_its_help_topic(self, authenticated_client, url_name, href): ...
        # build href with reverse(); assert it is in the page HTML for an empty account

    def test_gift_list_shows_empty_state_without_gifts(self, authenticated_client):
        html = authenticated_client.get(reverse("gift_manager:gifts")).content.decode()
        assert 'id="gift-grid"' not in html
        assert reverse("gift_manager:gift_create") in html
        assert reverse("gift_manager:help_topic", args=["how-it-works"]) + "#gifts" in html

    def test_gift_list_shows_grid_with_gifts(self, authenticated_client, user): ...
    def test_unassigned_filter_with_no_match_keeps_grid(self, authenticated_client, user): ...
        # user owns a gift used by a plan; GET ?unassigned=1 -> 'id="gift-grid"' present
    def test_wishlist_has_a_single_learn_more_when_empty(self, authenticated_client):
        html = authenticated_client.get(reverse("gift_manager:wishlist_list")).content.decode()
        assert html.count(reverse("gift_manager:help_topic", args=["wishlist"])) == 1
```

- [ ] **Step 2: Run the tests and check that they fail**

Run: `tox run -e py311 -- gift_manager/tests/test_help_links.py`
Expected: FAIL.

- [ ] **Step 3: Add the include and the links**

In each empty state, put the include after the existing text or buttons. On each intro line,
append it inline after the sentence.

- [ ] **Step 4: Gifts empty state**

When `not has_gifts`, render a `gift-plan-empty-state` block in place of the advanced-list
tools, `#gift-grid` and the grid scripts. It contains:
- the icon `fas fa-gift` and the heading "No gifts yet.";
- the line "Keep your gift ideas here and reuse them in your gift plans.";
- a "New gift" button to `gift_create` with `data-action="create"`;
- the Learn more link (`how-it-works`, anchor `gifts`).

The no-JS fallback template is unchanged.

- [ ] **Step 5: Update the AGENTS.md rule**

Replace the bullet "Do not put feature explanations or keyboard shortcut documentation into
the UI unless the user asks." with:
"Full feature explanations live in the Help section (`gift_manager/help_topics.py`) and the
getting-started checklist; a page may keep one short intro line linking to its Help topic. Do
not add keyboard shortcut documentation to the UI unless the user asks."

- [ ] **Step 6: Run the tests and check that they pass**

Run: `tox run -e py311 -- gift_manager/tests/test_help_links.py gift_manager/tests/test_grid_actions.py gift_manager/tests/views/test_advanced_list_tools.py gift_manager/tests/test_quick_action_buttons.py gift_manager/tests/views/test_ux_review_small_fixes.py`
Expected: PASS. Then run `rg -l "reverse\(\"gift_manager:gifts\"\)|'/gifts/'|\"/gifts/\"" gift_manager/tests`
and run every non-e2e file it lists. Any other test that expects the grid for a user with no
gifts gets the same setup fix. The e2e list-template test runs in Task 6.

- [ ] **Step 7: Translate and check locale coverage** (same commands as Task 2, Step 5).

- [ ] **Step 8: Commit**

```bash
git add AGENTS.md gift_manager/templates/gift_manager gift_manager/views/gift.py \
  gift_manager/tests/test_help_links.py locale/fr/LC_MESSAGES
git commit -m "Feat: Link empty states and intro lines to their Help topic"
```

---

### Task 6: End-to-end check, desktop and phone

**Files:**
- Create: `gift_manager/tests/e2e/test_getting_started_e2e.py`

**Interfaces:**
- Consumes: everything above; the e2e fixtures `live_server`, `page` and `seed_data_e2e`
  (`gift_manager/tests/e2e/conftest.py`); the login helper pattern from
  `gift_manager/tests/e2e/test_dashboard_layout.py`.

- [ ] **Step 1: Write the e2e test**

```python
@pytest.mark.django_db(transaction=True)
@pytest.mark.frontend
@pytest.mark.e2e
class TestGettingStartedJourney:
    @pytest.mark.parametrize("viewport", [{"width": 1280, "height": 900}, {"width": 390, "height": 844}])
    def test_new_user_hides_and_restores_checklist(self, page, live_server, seed_data_e2e, viewport):
        # create a fresh user (User.objects.create_user; the Profile comes from the post_save signal), log in
        # 1. dashboard shows #getting-started with "Add a recipient" unticked
        # 2. click the recipient step's "What's this?" -> URL ends with /help/how-it-works/#recipients,
        #    section #recipients visible
        # 3. back to dashboard, click Hide -> #getting-started has count 0
        # 4. open Help from the navbar (on phone: through the navbar toggler) -> click the show-again button
        # 5. lands on dashboard, #getting-started visible again
        # 6. no horizontal scroll: page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
```

- [ ] **Step 2: Run it**

Run: `tox run -e e2e -- gift_manager/tests/e2e/test_getting_started_e2e.py`
Expected: PASS for both viewports. If it fails, fix the template or CSS from the earlier task,
not the test's expectations.

- [ ] **Step 3: Run the related existing e2e tests**

Run: `tox run -e e2e -- gift_manager/tests/e2e/test_dashboard_layout.py gift_manager/tests/e2e/test_phone_layout.py gift_manager/tests/e2e/test_list_templates.py`
Pay attention to the dashboard live-refresh tests in `test_dashboard_layout.py` (around lines 491
and 616-679), because the card now sits inside `#dashboard-live`.
Expected: PASS. The card must not break the dashboard layout tests. If one asserts a
first-viewport layout that the card now pushes down, have the test hide the card in its setup
(set `getting_started_hidden_at` on the user's profile), not change the card.

- [ ] **Step 4: Lint and commit**

Run the lint fallback from Global Constraints on the changed files. Expected: no failures.

```bash
git add gift_manager/tests/e2e/test_getting_started_e2e.py gift_manager/tests/e2e
git commit -m "Test: Cover the getting-started checklist journey on desktop and phone"
```
