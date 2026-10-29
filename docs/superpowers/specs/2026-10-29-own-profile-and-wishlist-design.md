# Own Profile And Wishlist - Design

Implements Project B of `docs/ideas/0028-wishlists-and-collaborative-gift-giving.md`.

## Context

In Gift Manager, a `Person` record is historically a giver's private contact entry. While givers can record private notes and tags for their recipients, the recipient had no way to express their own interests, clothing/shoe sizes, dislikes/allergies, or specific gift wishes. Givers often have to repeatedly ask recipients for ideas or guess.

With Project A completed, the system now reliably knows which `Person` record represents which user account through `Person.account`. Project B builds directly upon this foundation to introduce user-authored **Profile Preferences** and **Wishlists**, while maintaining strict privacy boundaries so givers can coordinate and surprise the wisher.

---

## Goals

1. **User-Authored Profile Preferences:**
   - Registered users can specify their own public interests (tags), clothing/shoe sizes, general preferences, and a "please avoid" list (allergies, disliked formats).
2. **Wishlist Management:**
   - Registered users can create, edit, prioritize, archive, and delete items on their personal wishlist (with title, URL, price hint, notes, and priority).
3. **Giver Visibility & Shared View:**
   - Confirmed friends viewing any `Person` record linked to that friend (`person.account == friend_user`) can view the friend's self-declared preferences and active wishlist items.
4. **Strict Surprise & Privacy Boundary:**
   - The wisher **never** sees who claimed or planned a gift from their wishlist, nor any giver coordination comments or status updates.
   - Friends can claim a wish or seamlessly create a gift plan (`Relation`) linked to it.
5. **AI Suggestion Enhancement:**
   - Incorporate the recipient's self-declared interests, sizes, "please avoid" guidelines, and open wishlist items into the AI suggestion prompt when generating gift ideas for a linked record.

---

## Decisions (agreed with the user)

| Topic | Decision |
|---|---|
| **Wishlist Model** | Dedicated `Wish` model owned by the wisher (`User`), rather than reusing `Relation`. Reusing `Relation` would create risk of surprise leaks because `Relation` carries giver-centric visibility rules. |
| **Privacy Boundary** | The wisher sees their own wishes and preferences, but **never** sees claim statuses, claimer identities, or fulfilling `Relation` plans. Givers see claims and fulfillment status among co-givers. |
| **Plan Linking** | A friend can click "Plan this gift" on a wish. This creates or links a `Relation` pointing to `Relation.wish`. Existing plan coordination, budget tracking, and status workflows work automatically. |
| **Direct Claims on Wishes** | A friend can claim a wish directly (without creating a full event plan immediately) to reserve it and avoid duplicate purchases by other friends. |
| **Profile Preferences** | Added to `Profile`: `preferences_notes` (sizes, colors, brands), `avoid_notes` ("no physical books", allergies), and `public_interests` (M2M `GiftTag`). |
| **AI Suggestion Consent** | Toggle `Profile.ai_share_self_profile` (default: True). When enabled, friends requesting AI suggestions for a person linked to that account feed the wisher's self-declared tags, avoid notes, and wishlist items into the prompt. |
| **Access Control** | Only **confirmed friends** (`user.profile.friends`) have access to a user's wishlist and profile preferences. Unlinked users or non-friends cannot view them. |
| **Own Record View** | On a user's own `Person` record (`person.account == request.user`), a prominent banner links directly to their profile to manage their wishlist and preferences. |

---

## Non-goals

- Group gift cost-splitting, contribution tally, and tracking who owes what (deferred to **Project C: Group gifts**).
- Automated price tracking or web scraping of third-party product URLs.
- Public/unauthenticated guest wishlist links for non-registered users.
- Secret Santa draws or automated assignments.

---

## Data Model (Migration)

### 1. New Model: `Wish`

```python
class WishPriority(models.IntegerChoices):
    LOW = 1, _("Nice to have")
    MEDIUM = 2, _("Would love")
    HIGH = 3, _("Must have")


class Wish(models.Model):
    wish_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wisher = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="wishes"
    )
    title = models.CharField(_("Title"), max_length=255)
    url = models.URLField(_("Link"), blank=True)
    price_hint = models.DecimalField(
        _("Price hint"), max_digits=10, decimal_places=2, null=True, blank=True
    )
    notes = models.TextField(_("Notes"), blank=True, help_text=_("Sizes, colors, specifications"))
    priority = models.IntegerField(
        _("Priority"), choices=WishPriority.choices, default=WishPriority.MEDIUM
    )
    is_archived = models.BooleanField(
        _("Archived"), default=False, help_text=_("Archived wishes are hidden from friends")
    )
    claimed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="claimed_wishes",
    )
    claimed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-priority", "-created_at"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(claimed_by__isnull=True) | models.Q(claimed_at__isnull=False),
                name="wish_claimed_by_requires_claimed_at",
            )
        ]
```

### 2. Additions to `Profile`

```python
# Self-authored recipient preferences
preferences_notes = models.TextField(
    _("Sizes and preferences"),
    blank=True,
    help_text=_("Clothing size, shoe size, favorite colors, preferred brands."),
)
avoid_notes = models.TextField(
    _("Things to avoid"),
    blank=True,
    help_text=_("Allergies, formats to avoid (e.g. no physical books), dislikes."),
)
public_interests = models.ManyToManyField(
    "GiftTag",
    blank=True,
    related_name="interested_profiles",
    help_text=_("Interests and themes you enjoy."),
)
ai_share_self_profile = models.BooleanField(
    _("Allow friends' AI suggestions to consider your preferences"),
    default=True,
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
    help_text=_("The wish this gift plan fulfills."),
)
```

---

## Privacy and Visibility Boundary

```
+-------------------------------------------------------------------------------+
| VISIBILITY MATRIX                                                             |
+------------------------------+--------------------+---------------------------+
| Entity                       | Wisher Sees        | Friends / Givers See      |
+------------------------------+--------------------+---------------------------+
| Wish list items & details    | YES (editable)     | YES (read-only)           |
| Profile preferences & avoid  | YES (editable)     | YES (read-only)           |
| Wish claimed status          | NO (always hidden) | YES ("Claimed by @bob")   |
| Claimer identity             | NO                 | YES                       |
| Fulfilling plans (Relations) | NO (hidden)        | YES (standard plan rules) |
| Giver comments on plans      | NO                 | YES (standard plan rules) |
+------------------------------+--------------------+---------------------------+
```

### Visibility Rules in QuerySets & Views

1. **Wisher's Own View:**
   - Reaches wishes through `request.user.wishes.all()`.
   - Serializers and context processors **never** pass `claimed_by` or `fulfilling_plans` to templates rendered for the wisher.
2. **Friends' View:**
   - Accessible only when `PermissionService.users_are_friends(request.user, wisher)`.
   - Active wishes (`is_archived=False`) are returned.
   - For friends, `claimed_by` and `fulfilling_plans` are surfaced so friends don't duplicate purchases.
3. **Former Friends:**
   - Unfriending (`RemoveFriendView`) automatically releases any claims the former friend holds on the wisher's wishes (`wish.claimed_by == former_friend`), just as it severs relation access.

---

## Service: `gift_manager/wishlist.py`

Encapsulates all business logic for wishes and claims:

- `get_wisher_wishes(wisher: User, include_archived: bool = False) -> QuerySet[Wish]`
- `get_friend_visible_wishes(wisher: User, friend: User) -> QuerySet[Wish]`: Verifies friendship; raises `PermissionDenied` if not friends.
- `claim_wish(wish: Wish, friend: User) -> Wish`:
  - Atomic transaction with `select_for_update()`.
  - Verifies friendship between `friend` and `wish.wisher`.
  - Rejects if `friend == wish.wisher` (wisher cannot claim their own wish).
  - Rejects if already claimed by another user.
  - Sets `claimed_by = friend`, `claimed_at = timezone.now()`.
- `release_wish_claim(wish: Wish, actor: User) -> Wish`:
  - Allowed for the claimer or the wisher (if archiving).
  - Clears `claimed_by` and `claimed_at`.
- `plan_wish(wish: Wish, friend: User, person: Person, ...) -> Relation`:
  - Creates a `Relation` where `relation.wish = wish`, `relation.person = person`.
  - Automatically claims the wish for `friend` if not already claimed.
- `release_claims_after_unfriending(user: User, former_friend: User) -> None`:
  - Releases any claims `user` holds on `former_friend`'s wishes, and vice-versa.

---

## UI and Workflows

### 1. Wisher's Interface (Profile Page `/profile/`)
- **"My Preferences" Card:**
  - Form to update `preferences_notes` (sizes/colors), `avoid_notes` (allergies/dislikes), `public_interests` (tags select), and `ai_share_self_profile`.
- **"My Wishlist" Tab/Card:**
  - Clean list of current wishes showing Title, Link, Price, Priority badge, Notes.
  - "Add a wish" modal or offcanvas form (`WishForm`: title, url, price_hint, notes, priority).
  - Quick action buttons: Edit, Archive, Delete.

### 2. Giver's Interface (On Linked `Person` Detail Page)
- When viewing a person whose `person.account` is set to a friend:
  - Add a dedicated **"Wishlist & Preferences"** tab/card on the person detail page.
  - Displays:
    - **Self-Declared Preferences:** Sizes, colors, preferred brands.
    - **Things to Avoid:** Highlighted caution/info box (allergies, dislikes).
    - **Shared Interests:** Tags chosen by the friend.
    - **Wishlist Items:**
      - Items ordered by priority (High, Medium, Low).
      - Claim status: "Claimed by you", "Claimed by @bob", or "Available".
      - Actions:
        - **"Claim" / "Release claim"**: Direct 1-click toggle.
        - **"Plan this gift"**: Opens guided plan creation pre-filled with the wish details and recipient.

---

## AI Suggestions Integration

In [`gift_manager/suggestions/ai/prompt.py`](file:///home/adrien/Work/Perso/GiftManager/gift_manager/suggestions/ai/prompt.py):

When building recipient info for a person where `person.account` is linked:
1. Check `recipient.account.profile.ai_share_self_profile`.
2. If enabled:
   - **Interests:** Merge `recipient.account.profile.public_interests` with the person record's tags.
   - **Avoidances:** Append `recipient.account.profile.avoid_notes` to the scrubbed avoid guidelines.
   - **Sizes & Preferences:** Include windowed `preferences_notes` in the recipient notes context.
   - **Active Wishes:** Pass active unfulfilled wish titles as strong guidance (e.g. *"Recipient has explicitly wished for: [Titles]"*).

---

## Testing Strategy

1. **Unit & Service Tests (`gift_manager/tests/test_wishlist_service.py`):**
   - Wisher can create/edit/archive/delete wishes.
   - Wisher can never claim their own wish.
   - Non-friends cannot view or claim a wish.
   - Friends can claim and release claims.
   - Double-claim raises domain refusal.
   - Unfriending releases claims across both users.
2. **View & Security Tests (`gift_manager/tests/views/test_wishlist_views.py`):**
   - Assert wisher response context never contains `claimed_by`.
   - Assert friend sees claim badges and can claim via HTMX.
   - Assert planning a wish associates `Relation.wish`.
3. **AI Suggestion Tests (`gift_manager/tests/test_suggestions_wishlist.py`):**
   - Verify self-profile interests and avoid notes are properly included in the AI prompt when enabled.
   - Verify prompt respects `ai_share_self_profile = False`.
4. **End-to-End Tests (`gift_manager/tests/e2e/test_wishlist_e2e.py`):**
   - Alice creates a wish on her profile.
   - Bob views Alice's linked person, sees the wish, claims it, and converts it into a surprise plan.
   - Verify Alice's view shows the wish without showing Bob's claim or plan.
