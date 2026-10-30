# Group Gifts And Contribution Tally - Design

Implements Project C of [docs/ideas/0028-wishlists-and-collaborative-gift-giving.md](docs/ideas/0028-wishlists-and-collaborative-gift-giving.md).

## Context

In Gift Manager, a gift plan (`Relation`) connects a recipient (person or group) with a gift and an optional occasion. Coordination features (Project 0007) currently allow collaborators to claim a plan (`claimed_by`, designating who buys the gift) and leave discussion comments.

However, when friends, family, or colleagues decide to buy a gift together (e.g. chipping in for an expensive item, a wedding registry gift, or a group birthday present):
- One person typically purchases the gift (the **buyer** / claimer).
- Multiple people agree to contribute (**participants / contributors**).
- There is currently no way to record who is participating, how the cost is split, who has paid their share to the buyer, and who still owes money.
- Users are forced to maintain external spreadsheets or chat tallies outside the app.

Project C adds collaborative buying and contribution tracking directly to gift plans without handling real money or collecting payment credentials.

> [!NOTE]
> **Terminology distinction:**
> - **Recipient Group (`PersonGroup`):** A group of people who *receive* a gift (e.g., "The Johnsons", "The Team").
> - **Group Gift / Collaborative Gift:** A gift plan where multiple *givers* chip in together to fund the gift for the recipient.

---

## Goals

1. **Collaborative Gifting on Plans:**
   - Any shared gift plan can be organized as a collaborative group gift with multiple contributors.
2. **Participant Management:**
   - Add and remove contributors.
   - Contributors can be registered collaborators on the plan (`user: ForeignKey(User, null=True)`) or external individuals without accounts (free-text snapshot `name: CharField`).
   - When a registered user is selected, their name is always snapshotted into `name` so the ledger remains fully intact and queryable even if their user account is deleted later.
3. **Flexible Cost Splitting:**
   - **Equal split (default):** Total gift cost is divided among contributors. Remainder cents from uneven splits are distributed by 1 cent each over the first $r$ contributors. Stored shares are derived at read time, avoiding stale data when price or participant counts change.
   - **Paid share freeze:** Once a contributor pays, their paid amount is frozen. Any subsequent price changes or contributor count changes rebalance only across the remaining unpaid contributors (`remaining_price = max(0, total_price - sum_frozen)`). If total frozen payments exceed a reduced price, the UI clearly displays an "Overfunded by $X" state.
   - **Custom split:** Individual contributors can have custom, fixed share amounts (e.g. a couple counting double, or someone contributing a specific amount). Custom shares equal to 0 cannot be marked as paid.
   - Clear indicators for custom mode: displays allocated vs. total amount (e.g. "$75 of $100 allocated").
4. **Payment Status Tracking:**
   - Each contributor's share can be marked as **Paid** or **Unpaid**.
   - The buyer (`Relation.claimed_by`) is automatically recognized as paid at read time (since they paid the shop), and their row's toggle is disabled.
   - A share marked paid requires and tracks a timestamp (`paid_at`).
5. **Per-Plan Balance & Tally Summary:**
   - Clear summary card showing:
     - Total price and currency (derived from the plan owner's currency so all collaborators see consistent units).
     - Buyer (who made the purchase or is buying it). When no buyer is assigned, payments are described as "Pledged to group fund".
     - Breakdown per contributor: share amount, paid/unpaid status badge, and toggle action.
     - Progress bar and tally: Total collected, total remaining, and amount owed to the buyer from other contributors.
6. **Strict Anti-Spoiler & Universal Recipient Privacy Boundary:**
   - **Universal Recipient Privacy:** A user who is the recipient of a gift plan can **never** see the group gift section, contributor breakdown, or financial tally for their own gift—whether the plan is marked surprise or not, and whether it was generated from a wish or created directly. For group recipients, owners of the plan are exempt since they act as co-givers.
   - No group gift or contribution data is ever rendered in calendar feeds (.ics), email digests, or AI suggestion prompts for any user.

---

## Decisions (incorporating peer review consensus)

| Topic | Decision |
|---|---|
| **Model Architecture** | `RelationContribution` model linked to `Relation` (`related_name="contributions"`). Normalized and isolated from core plan queries. |
| **Account Deletion Safety** | `RelationContribution.user` is `SET_NULL`, and `name` always stores a snapshot of the contributor's display name at creation/save time. If the account is deleted, the historical ledger is preserved without `IntegrityError`. |
| **Buyer Role & State** | The buyer is the user holding `Relation.claimed_by`. Buyer status is **derived at read time**, not stored as a mutable static flag. If `claimed_by` changes or is released, the tally updates automatically. When no one has claimed the plan, payments are "pledged" to the group pool. The buyer's paid toggle is disabled. |
| **Equal Split Derivation & Paid Freeze** | In `EQUAL` split mode, unpaid shares are computed dynamically at read time via `calculate_equal_shares(remaining_price, unpaid_count)` where `remaining_price = max(0, total_price - sum_frozen)`. When a contributor's share is paid, `amount` is frozen at that paid value. Unmarking paid resets `amount` to `0.00` and `paid_at` to `None`. |
| **Penny Rounding** | In `EQUAL` split mode, integer cents $C$ and contributor count $N$ use `divmod(C, N)`: base cents $b = C // N$, remainder $r = C \% N$. The first $r$ contributors receive $b + 1$ cents; the remaining $N - r$ receive $b$ cents. Sum of shares strictly equals the total price. Tested with Hypothesis (prices capped to 2 decimal places). |
| **Custom Split Allocations** | In `CUSTOM` mode, explicit amounts are stored on each contribution. If the sum of custom shares does not equal the plan price, the UI displays "Allocated $X of $Y" (under-allocated or over-allocated) without blocking saves. Switching from custom to equal requires confirmation. |
| **Universal Recipient Boundary** | A centralized guard `_require_group_gift_access` reuses `plan_coordination.require_level(relation, user, minimum_level)` to enforce surprise visibility, and rejects access with the generic `PermissionDenied("You do not have permission to do this on this gift plan.")` for any recipient user (`is_recipient_of_plan(relation, user)`). The group gift section renders nothing for recipients. |
| **Group Recipient Owner Exemption** | For group recipients (`relation.group`), plan owners (`PermissionLevel.OWNER`) who happen to be group members can access group gifts because they are organizing/funding the gift. For individual persons (`relation.person`), the recipient account is **strictly blocked** under all circumstances. |
| **Recipient & Group Link Robustness** | When building contributor rows, any contributor row matching `is_recipient_of_plan(relation, user)` is automatically treated as an external snapshot contributor (`user=None`), preventing stale or newly linked recipient accounts from being exposed as active user contributors on their own gifts. |
| **Permissions** | Plan **Editors and Owners** (`PermissionLevel.EDITOR`) can enable/disable group gifts, add/remove contributors, change split mode, and edit custom amounts. Both **Editors/Owners** AND the **Buyer** (`relation.claimed_by`) can toggle paid/unpaid status. Group gift operations reject plans where `is_group_gift` is false. |
| **Safety on Removal & Disable** | `disable_group_gift` and `remove_contributor` refuse to delete rows if `is_paid = True` (`ValidationError("Cannot remove a contributor or disable a group gift with recorded payments; unmark payment first.")`). `disable_group_gift` preserves contribution records by default. |
| **Concurrency Protection** | Every service function acquiring or mutating group gift state locks the relation with `PermissionService.lock_object(relation)` inside `transaction.atomic()` before re-fetching rows. Tested on PostgreSQL with concurrent requests. |
| **Plan Lifecycle** | When a plan is marked `Given`, payment collection remains active. When a plan is `Abandoned`, the UI adapts to show paid amounts as "funds to be settled/returned". Plan duplication (`duplicate_initial`) and plan repeat do not copy contribution ledgers. |
| **Feeds, Digests, & Prompts** | Group gift and contribution details are excluded from all calendar feeds, email reminder digests, and AI suggestion prompts for all users. |
| **Non-Goals (Out-of-Scope)** | No real money handling, credit card forms, bank accounts, or external payment gateways. |

---

## Non-goals

- Real payment processing, escrow, or credit card collection.
- In-app money transfers or bank integrations.
- Public guest links for unauthenticated participants.
- Automated payment reminder emails or push notifications.

---

## Data Model

### 1. `RelationContribution`

```python
class RelationContribution(models.Model):
    """A financial contribution toward the cost of a collaborative gift plan."""

    relation = models.ForeignKey(
        "Relation",
        on_delete=models.CASCADE,
        related_name="contributions",
    )
    user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gift_contributions",
        help_text=gettext_lazy("Registered user participating in this group gift."),
    )
    name = models.CharField(
        max_length=150,
        help_text=gettext_lazy("Snapshot name of the contributor or external contributor label."),
    )
    amount = models.DecimalField(
        gettext_lazy("Share amount"),
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=gettext_lazy("Stored share amount in custom mode, or frozen paid amount in equal mode."),
    )
    is_paid = models.BooleanField(
        gettext_lazy("Paid"),
        default=False,
        help_text=gettext_lazy("Whether this contributor has paid their share to the buyer."),
    )
    paid_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=gettext_lazy("When this share was marked as paid."),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gte=0),
                name="contribution_amount_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(is_paid=False, paid_at__isnull=True)
                | models.Q(is_paid=True, paid_at__isnull=False),
                name="contribution_is_paid_requires_paid_at",
            ),
            models.CheckConstraint(
                condition=~models.Q(name=""),
                name="contribution_requires_name",
            ),
            models.UniqueConstraint(
                fields=["relation", "user"],
                condition=models.Q(user__isnull=False),
                name="unique_user_contribution_per_plan",
            ),
        ]

    def save(self, *args, **kwargs):
        # Always maintain name as a snapshot of user display name if user is set
        if self.user and not self.name:
            self.name = self.user.username
        super().save(*args, **kwargs)

    @property
    def display_name(self) -> str:
        """Return the formatted contributor name."""
        if self.user:
            return self.user.username
        return self.name
```

### 2. Additions to `Relation`

```python
class SplitMode(models.TextChoices):
    EQUAL = "equal", gettext_lazy("Equal split")
    CUSTOM = "custom", gettext_lazy("Custom amounts")


is_group_gift = models.BooleanField(
    gettext_lazy("Group gift"),
    default=False,
    help_text=gettext_lazy("Whether this gift plan is funded collaboratively by multiple contributors."),
)
split_mode = models.CharField(
    max_length=20,
    choices=SplitMode.choices,
    default=SplitMode.EQUAL,
    help_text=gettext_lazy("How the total gift cost is divided among contributors."),
)
```

---

## Service Layer: `gift_manager/group_gifts.py`

### 1. Pure Calculation Functions
```python
def calculate_equal_shares(total_price: Decimal | None, contributor_count: int) -> list[Decimal]:
    """Divide total_price into contributor_count shares, spreading remainder cents by 1 cent each.

    Returns empty list if contributor_count <= 0.
    Returns list of 0.00 if total_price is None or <= 0.
    Sum of shares strictly equals round(total_price, 2).
    """
    if contributor_count <= 0:
        return []
    if total_price is None or total_price <= 0:
        return [Decimal("0.00")] * contributor_count

    total_cents = int(round(total_price * 100))
    base_cents, remainder_cents = divmod(total_cents, contributor_count)

    shares: list[Decimal] = []
    for i in range(contributor_count):
        cents = base_cents + (1 if i < remainder_cents else 0)
        shares.append(Decimal(cents) / Decimal(100))
    return shares
```

### 2. Access and Recipient Guard Helper
```python
def is_recipient_of_plan(relation: Relation, user: User) -> bool:
    """Return whether user is the recipient of the plan.

    For a person recipient, true if person.account == user.
    For a group recipient, true if user is a member UNLESS user is an OWNER of the plan.
    """
    if not user or not user.is_authenticated:
        return False
    if relation.person_id and relation.person.account_id == user.pk:
        return True
    if relation.group_id:
        is_member = relation.group.get_all_members(include_nested=True).filter(account=user).exists()
        if is_member:
            level = PermissionService.get_effective_permission(relation, user)
            return level < PermissionLevel.OWNER
    return False


def _require_group_gift_access(relation: Relation, user: User, minimum_level: int = PermissionLevel.VIEWER) -> int:
    """Validate user permission and assert user is not the recipient of the plan.

    Reuses plan_coordination.require_level to enforce hidden surprises.
    Raises PermissionDenied (HTTP 403) with generic message on failure.
    """
    from gift_manager.plan_coordination import require_level

    level = require_level(relation, user, minimum_level)
    if is_recipient_of_plan(relation, user):
        raise PermissionDenied(gettext("You do not have permission to do this on this gift plan."))
    return level
```

### 3. Financial Summary Data Class & Formulas
```python
@dataclass(frozen=True)
class ContributorRow:
    contribution: RelationContribution
    display_name: str
    share_amount: Decimal
    is_buyer: bool
    is_paid: bool
    paid_at: datetime | None
    can_toggle_paid: bool
    can_remove: bool


@dataclass(frozen=True)
class GroupGiftSummary:
    is_group_gift: bool
    split_mode: str
    total_price: Decimal | None
    currency: str
    buyer: User | None
    contributor_count: int
    rows: list[ContributorRow]
    total_allocated: Decimal
    total_collected: Decimal
    total_remaining: Decimal
    owed_to_buyer: Decimal
    is_fully_paid: bool
    is_overfunded: bool
    can_manage: bool
```

**Financial Formulas:**
- `total_price`: `relation.effective_price or Decimal("0.00")`
- `total_allocated`: `sum(row.share_amount for row in rows)`
- `total_collected`: `sum(row.share_amount for row in rows if row.is_paid)`
- `total_remaining`: `max(Decimal("0.00"), total_price - total_collected)`
- `is_overfunded`: `total_collected > total_price`
- `owed_to_buyer`: `sum(row.share_amount for row in rows if not row.is_buyer and not row.is_paid)` if `buyer` else `Decimal("0.00")`
- `is_fully_paid`: `total_collected >= total_price and total_price > 0`
- `currency`: Derived from the first plan owner's `profile.currency` (via `PermissionService.get_permission_map`) to guarantee uniform currency symbols across all collaborators.

### 4. Operations (Enclosed in `transaction.atomic()` with Row Locks)
- `enable_group_gift(relation: Relation, actor: User, split_mode: str = SplitMode.EQUAL) -> Relation`:
  - Requires `_require_group_gift_access(relation, actor, PermissionLevel.EDITOR)`.
  - Sets `is_group_gift = True` and `split_mode = split_mode`.
  - If `relation.claimed_by` is set, uses `get_or_create` to ensure the buyer is a contributor without duplicate constraint violations.
- `disable_group_gift(relation: Relation, actor: User) -> Relation`:
  - Requires `_require_group_gift_access(relation, actor, PermissionLevel.EDITOR)`.
  - If any contribution has `is_paid = True`, raises `ValidationError(gettext("Cannot disable a group gift with recorded payments."))`.
  - Preserves contribution records and sets `is_group_gift = False`.
- `set_split_mode(relation: Relation, actor: User, split_mode: str) -> Relation`:
  - Requires `_require_group_gift_access(relation, actor, PermissionLevel.EDITOR)`.
  - Validates `relation.is_group_gift is True`.
  - When switching from `EQUAL` to `CUSTOM`, freezes current dynamic shares into `amount`.
  - When switching from `CUSTOM` to `EQUAL`, resets un-paid `amount` to `0.00` so dynamic equal shares take over.
- `add_contributor(relation: Relation, actor: User, user: User | None = None, name: str = "", amount: Decimal = Decimal("0.00")) -> RelationContribution`:
  - Requires `_require_group_gift_access(relation, actor, PermissionLevel.EDITOR)`.
  - Validates `relation.is_group_gift is True`.
  - Name is stripped of whitespace. Validate length between 1 and 150 characters.
  - If `user` is provided:
    - Validates `not is_recipient_of_plan(relation, user)`.
    - Validates `PermissionService.get_effective_permission(relation, user) >= PermissionLevel.VIEWER`.
    - Snapshots `user.username` into `name`.
  - Else: validates `bool(name)`.
  - Creates and returns `RelationContribution`.
- `remove_contributor(contribution: RelationContribution, actor: User) -> None`:
  - Requires `_require_group_gift_access(contribution.relation, actor, PermissionLevel.EDITOR)`.
  - Validates `contribution.relation.is_group_gift is True`.
  - Rejects removing the buyer if the plan is currently claimed (`ValidationError(gettext("Cannot remove the designated buyer from contributors."))`).
  - Rejects removing any contributor with `is_paid = True` (`ValidationError(gettext("Cannot remove a contributor with a recorded payment; unmark payment first."))`).
  - Deletes contribution.
- `toggle_contribution_paid(contribution: RelationContribution, actor: User) -> RelationContribution`:
  - Requires `_require_group_gift_access(contribution.relation, actor, PermissionLevel.VIEWER)`.
  - Validates `contribution.relation.is_group_gift is True`.
  - Actor must be either an Editor/Owner (`PermissionLevel.EDITOR`) or the buyer (`contribution.relation.claimed_by`).
  - If contributor is the buyer (`contribution.user_id == relation.claimed_by_id`), raises `ValidationError(gettext("The buyer's share is settled by definition."))`.
  - If in Custom mode and `amount <= 0`, raises `ValidationError(gettext("Cannot mark a zero-amount share as paid."))`.
  - If in Equal mode and derived share `<= 0`, raises `ValidationError(gettext("Cannot mark a zero-amount share as paid."))`.
  - Toggles `is_paid`. If True, sets `paid_at = timezone.now()` and freezes `amount` at the current share. If False, clears `paid_at = None` and resets `amount = 0.00` in Equal mode.
- `update_contribution_amount(contribution: RelationContribution, actor: User, amount: Decimal) -> RelationContribution`:
  - Requires `_require_group_gift_access(contribution.relation, actor, PermissionLevel.EDITOR)`.
  - Validates `contribution.relation.is_group_gift is True`.
  - Validates `contribution.relation.split_mode == SplitMode.CUSTOM`.
  - Validates `amount >= 0`.
  - Updates `amount`.

---

## UI and Workflows

### 1. Dedicated Template Partial: `gift_manager/templates/gift_manager/includes/relation_group_gift_partial.html`
- Included in `relation_detail.html`:
  - If `is_recipient_of_plan(relation, request.user)`: entire partial renders **nothing**.
  - If `not relation.is_group_gift`:
    - Shows an **"Organize as a group gift"** button for editors (prompting to set `Relation.price` first if price is missing).
  - If `relation.is_group_gift`:
    - **Header & Balance Bar:**
      - Total price & currency (plan owner currency).
      - Split mode badge with 1-click toggle between Equal and Custom.
      - Progress bar (`role="progressbar"`, accessible label) displaying collected vs remaining amount.
      - In Custom mode: alert if under-allocated or over-allocated.
      - If overfunded: warning banner with excess amount.
    - **Contributors List / Cards (Mobile-friendly):**
      - Contributor name (with buyer badge if `claimed_by`).
      - Share amount (in Custom mode: inline edit input).
      - Paid status badge (`Paid` green / `Unpaid` orange).
      - Actions:
        - 1-click HTMX toggle `Mark as paid` / `Mark as unpaid` (disabled on buyer).
        - Remove contributor (`x` button for editors, disabled on buyer if claimed or if paid).
    - **Add Contributor Form:**
      - Selector: select from plan collaborators or type external contributor name.
      - In Custom mode: initial amount input.
      - "Add contributor" button.

### 2. HTMX Endpoints in `gift_manager/views/group_gifts.py`:
- `POST relations/<uuid:pk>/group-gift/toggle/` (`relation_group_gift_toggle`): enable/disable.
- `POST relations/<uuid:pk>/group-gift/mode/` (`relation_group_gift_mode`): switch split mode.
- `POST relations/<uuid:pk>/group-gift/contributors/add/` (`relation_group_gift_contributor_add`).
- `POST relations/<uuid:pk>/group-gift/contributors/<int:contribution_id>/remove/` (`relation_group_gift_contributor_remove`).
- `POST relations/<uuid:pk>/group-gift/contributors/<int:contribution_id>/toggle-paid/` (`relation_group_gift_contributor_toggle_paid`).
- `POST relations/<uuid:pk>/group-gift/contributors/<int:contribution_id>/amount/` (`relation_group_gift_contributor_amount`).

All endpoints return `relation_group_gift_partial.html` on HTMX requests, and redirect to `relation_detail` for standard POST requests.

---

## Privacy and Side-Channel Boundary

```
+---------------------------------------------------------------------------------------+
| GROUP GIFT PRIVACY MATRIX                                                             |
+------------------------------------+--------------------+-----------------------------+
| Surface                            | Recipient / Wisher | Givers / Collaborators      |
+------------------------------------+--------------------+-----------------------------+
| Group gift partial & tally         | ALWAYS HIDDEN      | FULL ACCESS                 |
| Contribution HTMX endpoints        | HTTP 403 Forbidden | Processed normally          |
| Surprise plan (`is_surprise=True`) | Plan hidden        | Standard access             |
| Non-surprise plan                  | Sees gift info only| Sees gift & group gift tally|
| Calendar feed & email digests      | EXCLUDED           | EXCLUDED                    |
| AI suggestions & Catalogue         | EXCLUDED           | EXCLUDED                    |
+------------------------------------+--------------------+-----------------------------+
```

---

## Test Strategy

1. **Model & Constraint Tests (`gift_manager/tests/test_group_gift_models.py`):**
   - Non-negative amount constraint.
   - Requires name constraint (empty and whitespace-only rejected).
   - `is_paid` requires `paid_at` constraint.
   - Unique user per relation constraint.
   - User account deletion: deleting user preserves contribution row with snapshot name without IntegrityError.
2. **Service & Mathematics Tests (`gift_manager/tests/test_group_gift_service.py`):**
   - Pure penny rounding: tests across various totals and counts (e.g. $100 / 3 -> 33.34, 33.33, 33.33; $0.07 / 4 -> 0.02, 0.02, 0.02, 0.01).
   - Hypothesis property test asserting `sum(calculate_equal_shares(p, n)) == p` across arbitrary positive Decimals (rounded to 2 decimal places) and counts.
   - Zero count, zero price, and None price edge cases.
   - Concurrency locking with `PermissionService.lock_object` tested on PostgreSQL with concurrent additions.
   - Buyer change: buyer role dynamically follows `claimed_by`.
   - Freeze paid shares in equal mode; rebalancing remaining unpaid shares.
   - Price drops below sum of frozen payments (overfunded state).
   - Owner-exemption matrix: owner member allowed on group recipient; non-owner member blocked; person recipient blocked even if plan owner.
   - Buyer & editor payment toggle permissions; refusing to toggle buyer row.
   - Refusing disable and removal while payments are recorded.
   - State guards: operations reject when `is_group_gift` is False.
3. **Privacy, Feeds & Digests Tests (`gift_manager/tests/views/test_group_gift_privacy.py`):**
   - Universal recipient privacy: recipient user gets HTTP 403 when hitting any group gift endpoint.
   - Recipient never sees group gift markup in `relation_detail` HTML across surprise and non-surprise plans.
   - Calendar feed (.ics) contains no contribution or group gift text for any user.
   - Email digest contains no contribution or group gift text for any user.
   - AI suggestion prompt generation contains no contribution or group gift text.
   - Dynamic recipient protection converts active recipient contributor rows to external snapshots (`user = None`).
4. **View & HTMX Tests (`gift_manager/tests/views/test_group_gift_views.py`):**
   - Enable, add contributor, remove contributor, toggle paid.
   - Custom split mode and amount updating.
   - Form error handling, validation, and plain POST fallback.
5. **End-to-End Tests (`gift_manager/tests/e2e/test_group_gift_e2e.py`):**
   - Collaborative scenario 1 (Surprise plan):
     - Alice creates a surprise plan for Bob, sets price $90, and claims it (buyer).
     - Alice organizes plan as group gift, adds Carol (collaborator) and Uncle Dave (external name).
     - Equal split derives $30.00 each.
     - Alice marks Carol as paid once Carol pays her.
     - Progress shows $60 / $90 collected (Alice + Carol), Dave owes $30.
     - Bob logs in and verifies no group gift or financial details appear on his views.
   - Collaborative scenario 2 (Non-surprise shared plan):
     - Alice creates a non-surprise plan for Bob and shares it with Bob and Carol.
     - Alice organizes as group gift with Carol.
     - Bob views the plan, sees the gift information, but group gift / tally section is strictly absent.
6. **Localization:**
   - Full French translations in `locale/fr/LC_MESSAGES/django.po` compiled with `compilemessages`.
