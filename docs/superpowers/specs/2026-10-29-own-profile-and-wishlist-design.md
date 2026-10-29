# Own Profile And Wishlist - Design

Implements Project B of [docs/ideas/0028-wishlists-and-collaborative-gift-giving.md](docs/ideas/0028-wishlists-and-collaborative-gift-giving.md).

## Context

In Gift Manager, a `Person` record is historically a giver's private address book entry. While givers can record private notes and tags for their recipients, the recipient has had no way to express their own interests, clothing/shoe sizes, dislikes/allergies ("please avoid"), or specific gift wishes. Givers often have to repeatedly ask recipients for ideas or guess.

With Project A completed, the system now reliably knows which `Person` record represents which user account through `Person.account`. Project B builds directly upon this foundation to introduce user-authored **Profile Preferences** and **Wishlists**, while maintaining strict privacy boundaries so givers can coordinate and surprise the wisher.

---

## Goals

1. **User-Authored Profile Preferences:**
   - Registered users can specify their own public interests (global tags), clothing/shoe sizes, general preferences, and a "please avoid" list (allergies, disliked formats).
2. **Wishlist Management:**
   - Registered users can create, edit, prioritize, archive, and delete items on their personal wishlist (with title, URL, price hint, notes, and priority).
3. **Giver Visibility & Shared View:**
   - Confirmed friends viewing any `Person` record linked to that friend (`person.account == friend_user`) can view the friend's self-declared preferences and active wishlist items.
4. **Strict Surprise & Privacy Boundary:**
   - The wisher **never** sees who claimed or planned a gift from their wishlist, nor any giver coordination comments or status updates.
   - Friends can claim a wish or seamlessly create a gift plan (`Relation`) linked to it.
5. **AI & Catalogue Suggestion Enhancement:**
   - Incorporate the recipient's self-declared interests, sizes, "please avoid" guidelines, and open wishlist items into the suggestion engines when generating gift ideas for a linked record.

---

## Decisions (agreed with the user)

| Topic | Decision |
|---|---|
| **Wishlist Model** | Dedicated `Wish` model owned by the wisher (`User`), rather than reusing `Relation`. Reusing `Relation` would create risk of surprise leaks because `Relation` carries giver-centric visibility rules. |
| **Privacy Boundary** | The wisher sees their own wishes and preferences, but **never** sees claim statuses, claimer identities, or fulfilling `Relation` plans. Givers see claims and fulfillment status among co-givers. |
| **State Invariant** | Everything the wisher views, renders, and performs operates identically whether a wish is claimed or unclaimed. Tested through direct response equality assertions. |
| **Plan Linking & Surprise Enforcement** | A friend can click "Plan this gift" on a wish. This creates or links a `Relation` pointing to `Relation.wish`. `plan_wish` **forces `is_surprise = True`** when `person.account == wish.wisher`. The created `Gift` is private to givers and never shared with the wisher. |
| **Single Claim Rule** | One friend may claim or plan a wish at a time to prevent duplicate purchases. If Carol claimed a wish, Bob cannot plan or claim it until Carol releases her claim. |
| **Claim Lifecycle on Archiving / Deletion** | If the wisher archives or deletes a wish that a friend has already claimed, the claim is **not** dropped. The wish is flagged `archived_by_wisher = True`, and the claimer sees a notice (*"The wisher removed or archived this wish"*), preventing broken plans or duplicate purchases. |
| **Claim Lifecycle on Plan Deletion** | If a fulfilling `Relation` is deleted or cancelled, its claim on `Wish` is automatically released. |
| **Claimer Identity** | If friend Carol views Alice's wish claimed by Bob: Carol sees *"Claimed by @bob"* if Carol and Bob are friends; Carol sees *"Claimed by a friend"* if Carol is not friends with Bob. |
| **Public Interests & Tag Visibility** | `Profile.public_interests` is restricted to global public tags (`GiftTag.is_public=True`). This avoids leaking private tag names or violating per-user tag permissions. Freeform interest text is captured in `preferences_notes`. |
| **Profile Preferences** | Added to `Profile`: `preferences_notes` (sizes, colors, brands), `avoid_notes` ("no physical books", allergies), and `public_interests` (M2M `GiftTag` where `is_public=True`). |
| **AI Suggestion Consent** | Toggle `Profile.ai_share_self_profile` (**default: False**, opt-in, matching `ai_share_person_notes`). When enabled, friends requesting AI suggestions for a person linked to that account feed scrubbed tags, avoid notes, and unclaimed wishes into the prompt. |
| **Access Control** | Only **confirmed friends** (`user.profile.friends`) have access to a user's wishlist and profile preferences. Unlinked users or non-friends cannot view them. |
| **Unfriending** | Unfriending automatically releases claims held by the former friend on the wisher's wishes. Historical plans retain `Relation.wish` or set it to `NULL`. |

---

## Non-goals

- Group gift cost-splitting, contribution tally, and tracking who owes what (deferred to **Project C: Group gifts**).
- Automated price tracking or web scraping of third-party product URLs.
- Public/unauthenticated guest wishlist links for non-registered users.
- Giver-only discussion directly on unclaimed wishes (giver discussion happens via [gift_manager/models.py](gift_manager/models.py) once a plan is initiated).
- Secret Santa draws or automated assignments.

---

## Data Model (Migration)

### 1. New Model: `Wish`

Following repository conventions (integer `id` primary key, unique UUID `wish_id`, `condition` parameter in `CheckConstraint`, `max_length=2000` URLs with validation, `MinValueValidator`, and `gettext_lazy`):

```python
class WishPriority(models.IntegerChoices):
    LOW = 1, gettext_lazy("Nice to have")
    MEDIUM = 2, gettext_lazy("Would love")
    HIGH = 3, gettext_lazy("Must have")


class WishQuerySet(models.QuerySet):
    """QuerySet for Wish model with explicit visibility filters."""

    def for_wisher(self, user):
        """Return active and archived wishes belonging to the wisher."""
        if not user or not user.is_authenticated:
            return self.none()
        return self.filter(wisher=user)

    def visible_to_friend(self, friend_user, wisher_user):
        """Return active wishes of a friend, visible only to confirmed friends."""
        if not friend_user or not friend_user.is_authenticated:
            return self.none()
        if not friend_user.profile.friends.filter(user=wisher_user).exists():
            return self.none()
        return self.filter(wisher=wisher_user, is_archived=False)


class Wish(models.Model):
    wish_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    wisher = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="wishes"
    )
    title = models.CharField(gettext_lazy("Title"), max_length=255)
    url = models.URLField(
        gettext_lazy("Link"),
        max_length=2000,
        blank=True,
        default="",
        validators=[validate_http_url],
    )
    price_hint = models.DecimalField(
        gettext_lazy("Price hint"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=gettext_lazy("Expected or typical price in your profile currency."),
    )
    notes = models.TextField(
        gettext_lazy("Notes"),
        blank=True,
        help_text=gettext_lazy("Sizes, colors, specifications."),
    )
    priority = models.IntegerField(
        gettext_lazy("Priority"),
        choices=WishPriority.choices,
        default=WishPriority.MEDIUM,
    )
    is_archived = models.BooleanField(
        gettext_lazy("Archived"),
        default=False,
        help_text=gettext_lazy("Archived wishes are hidden from friends unless claimed."),
    )
    is_fulfilled = models.BooleanField(
        gettext_lazy("Fulfilled"),
        default=False,
        help_text=gettext_lazy("Marked as fulfilled once given or received."),
    )
    claimed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="claimed_wishes",
    )
    claimed_at = models.DateTimeField(null=True, blank=True)
    wisher_updated_at = models.DateTimeField(
        auto_now=True,
        help_text=gettext_lazy("Tracks when wisher last modified the wish."),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = WishQuerySet.as_manager()

    class Meta:
        ordering = ["-priority", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(claimed_by__isnull=True) | models.Q(claimed_at__isnull=False),
                name="wish_claimed_by_requires_claimed_at",
            ),
            models.CheckConstraint(
                condition=models.Q(price_hint__isnull=True) | models.Q(price_hint__gte=0),
                name="wish_price_hint_non_negative",
            ),
        ]

    def is_updated_after_claim(self) -> bool:
        """Return whether the wisher modified this wish after it was claimed."""
        return bool(self.claimed_at and self.wisher_updated_at and self.wisher_updated_at > self.claimed_at)
```

### 2. Additions to `Profile`

```python
# Self-authored recipient preferences
preferences_notes = models.TextField(
    gettext_lazy("Sizes and preferences"),
    blank=True,
    help_text=gettext_lazy("Clothing size, shoe size, favorite colors, preferred brands."),
)
avoid_notes = models.TextField(
    gettext_lazy("Things to avoid"),
    blank=True,
    help_text=gettext_lazy("Allergies, formats to avoid (e.g. no physical books), dislikes."),
)
public_interests = models.ManyToManyField(
    "GiftTag",
    blank=True,
    limit_choices_to={"is_public": True},
    related_name="interested_profiles",
    help_text=gettext_lazy("Global public tags describing topics and hobbies you enjoy."),
)
ai_share_self_profile = models.BooleanField(
    gettext_lazy("Allow friends' AI suggestions to consider your preferences"),
    default=False,
)
```

### 3. Additions to `Relation` (Gift Plan)

```python
wish = models.ForeignKey(
    "Wish",
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
    related_name="fulfilling_plans",
    help_text=gettext_lazy("The wish this gift plan fulfills."),
)
```

#### Validation on `Relation`:
In `Relation.clean()`:
```python
if self.wish_id is not None:
    if self.group_id is not None:
        raise ValidationError(gettext_lazy("A gift plan fulfilling a wish must target a person, not a group."))
    if not self.person or self.person.account_id != self.wish.wisher_id:
        raise ValidationError(gettext_lazy("The recipient person must represent the wisher of this wish."))
```

---

## Privacy and Visibility Boundary

```
+---------------------------------------------------------------------------------------+
| VISIBILITY & SIDE-CHANNEL BOUNDARY MATRIX                                             |
+------------------------------------+--------------------+-----------------------------+
| Entity / Surface                   | Wisher Sees        | Friends / Givers See        |
+------------------------------------+--------------------+-----------------------------+
| Wish list items & details          | YES (editable)     | YES (read-only)             |
| Profile preferences & avoid        | YES (editable)     | YES (read-only)             |
| Wish claimed status                | NO (always hidden) | YES ("Claimed by @bob")     |
| Claimer identity                   | NO                 | YES (or "Claimed by friend")|
| Wisher modified after claim badge  | NO                 | YES                         |
| Fulfilling plans (Relations)       | NO (hidden)        | YES (standard plan rules)   |
| Created Gift record                | NO (hidden)        | YES (standard gift rules)   |
| Giver comments on plans            | NO                 | YES (standard plan rules)   |
| Direct response HTML / form state  | IDENTICAL whether  | Distinct based on claim     |
|                                    | claimed or not     |                             |
+------------------------------------+--------------------+-----------------------------+
```

### Strict Invariant & Test Verification
The wisher must experience **identical** page rendering, error codes, and form responses regardless of whether a wish is unclaimed, claimed, or attached to an active plan:
- Test pattern: instantiate a wish for Alice, capture `client.get('/profile/wishlist/')` and `client.get(edit_url)`; have Bob claim it and plan it; replay Alice's requests and assert the rendered output matches character-for-character.

---

## Service: `gift_manager/wishlist.py`

Encapsulates all business rules for wish creation, claims, and plan synchronization:

- `get_wisher_wishes(wisher: User, include_archived: bool = False) -> QuerySet[Wish]`:
  Uses `Wish.objects.for_wisher(wisher)`.
- `get_friend_visible_wishes(wisher: User, friend: User) -> QuerySet[Wish]`:
  Validates friendship via `PermissionService.users_are_friends(wisher, friend)`. Uses `Wish.objects.visible_to_friend(friend, wisher)`.
- `claim_wish(wish: Wish, friend: User) -> Wish`:
  - Atomic transaction with `PermissionService.lock_object(wish)`.
  - Verifies friendship between `friend` and `wish.wisher`.
  - Rejects if `friend == wish.wisher` (`PermissionDenied("You cannot claim your own wish.")`).
  - Rejects if `wish.claimed_by` is set to another user (`ValidationError("This wish has already been claimed by another friend.")`).
  - If already claimed by `friend`, no-op.
  - Sets `claimed_by = friend`, `claimed_at = timezone.now()`.
- `release_wish_claim(wish: Wish, actor: User) -> Wish`:
  - Allowed only for the `claimed_by` user or a superuser.
  - Clears `claimed_by = None`, `claimed_at = None`.
- `plan_wish(wish: Wish, friend: User, person: Person, event=None) -> Relation`:
  - Validates `person.account == wish.wisher`.
  - Claims the wish for `friend` (or verifies existing claim by `friend`).
  - Creates `Gift(name=wish.title, url=wish.url, comment=wish.notes)` owned by `friend`.
  - Creates `Relation(person=person, gift=gift, event=event, wish=wish, is_surprise=True)` owned by `friend`.
- `sync_wish_on_plan_change(relation: Relation) -> None`:
  - If plan is deleted or marked `CANCELLED`, automatically releases the wish claim if no other active plans fulfill it.
  - If plan is marked `GIVEN`, marks `wish.is_fulfilled = True`.
- `release_claims_after_unfriending(user: User, former_friend: User) -> None`:
  - Unfriending hook: releases any claims held by either user on the other's wishes.

---

## UI and Workflows

### 1. Wisher's Interface (`/profile/` and `/profile/wishlist/`)
- **"My Preferences" Section on Profile:**
  - Form to update `preferences_notes` (sizes/colors), `avoid_notes` (allergies/dislikes), `public_interests` (select2 / multi-select of public tags), and `ai_share_self_profile`.
- **"My Wishlist" Section / Sub-page:**
  - Clean list of current wishes showing Title, Link, Price hint, Priority badge, Notes.
  - Offcanvas / modal form (`WishForm`: `title`, `url`, `price_hint`, `notes`, `priority`).
  - Quick action buttons: Edit, Archive, Delete.

### 2. Giver's Interface (On Linked `Person` Detail Page)
- When viewing a person whose `person.account` is set to a friend:
  - Add a dedicated **"Wishlist & Preferences"** tab/card on the person detail page.
  - Displays:
    - **Self-Declared Preferences:** Sizes, colors, preferred brands.
    - **Things to Avoid:** Highlighted caution box (allergies, dislikes).
    - **Public Interests:** Public tag pills chosen by the friend.
    - **Wishlist Items:**
      - Items ordered by priority (Must have, Would love, Nice to have).
      - Claim status pill:
        - "Available" (green/secondary).
        - "Claimed by you" (info).
        - "Claimed by @bob" (or "Claimed by a friend" if viewer is not friends with Bob).
        - "Modified after claim" badge if wisher edited details after it was reserved.
      - Actions:
        - **"Claim" / "Release claim"**: Direct 1-click HTMX toggle.
        - **"Plan this gift"**: Opens guided plan creation pre-filled with the wish details and recipient, creating a surprise `Relation`.

---

## AI & Catalogue Suggestions Integration

### 1. AI Suggestion Prompt ([gift_manager/suggestions/ai/prompt.py](gift_manager/suggestions/ai/prompt.py))
When building recipient info for a person where `person.account` is linked:
1. Check `recipient.account.profile.ai_share_self_profile`.
2. If enabled (`True`):
   - **Interests:** Merge `recipient.account.profile.public_interests` names with the person record's tags.
   - **Avoidances:** Append scrubbed `recipient.account.profile.avoid_notes` (`scrub_text(avoid_notes, terms)`) to avoid guidelines.
   - **Sizes & Preferences:** Include scrubbed `preferences_notes` in recipient notes context.
   - **Active Wishes:** Pass active **unclaimed and unfulfilled** wish titles (`scrub_text(wish.title, terms)`) as strong positive inspiration.

### 2. Catalogue Suggestions ([gift_manager/suggestions/catalogue.py](gift_manager/suggestions/catalogue.py))
When matching gifts by tag/interest, incorporate the wisher's `public_interests` as candidate match tags.

---

## Testing Strategy

1. **Unit & Service Tests (`gift_manager/tests/test_wishlist_service.py`):**
   - Wisher can create/edit/archive/delete wishes.
   - Wisher can never claim their own wish.
   - Non-friends cannot view or claim a wish.
   - Friends can claim and release claims.
   - Double-claim by two friends raises domain refusal.
   - Claimer identity respects mutual friendship (masked if not mutual friends).
   - Unfriending releases claims across both users.
   - Archiving by wisher preserves claim and sets `archived_by_wisher`.
2. **Side-Channel Invariant Tests (`gift_manager/tests/views/test_wishlist_privacy.py`):**
   - Assert wisher response HTML, headers, and form state are strictly equal between an unclaimed wish and a claimed/planned wish.
   - Assert `Relation.wish` enforces `is_surprise = True`.
   - Assert created `Gift` is not shared with the wisher.
3. **View & UI Tests (`gift_manager/tests/views/test_wishlist_views.py`):**
   - Friend sees claim badges and can claim/release via HTMX.
   - Planning a wish associates `Relation.wish` and enforces person account validation.
4. **AI & Catalogue Suggestion Tests (`gift_manager/tests/test_suggestions_wishlist.py`):**
   - Verify self-profile interests and avoid notes are included in AI prompt when `ai_share_self_profile = True`.
   - Verify prompt strictly omits self-profile when `ai_share_self_profile = False` (default).
   - Verify claimed wishes are never suggested.
5. **End-to-End Tests (`gift_manager/tests/e2e/test_wishlist_e2e.py`):**
   - Alice creates a wish on her profile.
   - Bob views Alice's linked person, sees the wish, claims it, and converts it into a surprise plan.
   - Verify Alice's view shows the wish without showing Bob's claim or plan.
