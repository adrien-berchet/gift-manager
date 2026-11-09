# Idea: Read-Only Guest Wishlist Links

## Status

Proposed

## Summary

Allow users to generate a private, unguessable share link for their personal wishlist or a managed dependent's wishlist. Non-registered friends, distant relatives, or grandparents can open the link in any web browser to view what gifts the recipient wants without creating an account or logging in.

To prevent spam, trolling, and state management problems inherent in anonymous claiming (such as anonymous users maliciously marking everything claimed, or being unable to undo a mistaken claim), guest links are strictly read-only. Crucially, to prevent the list owner from using their own public link in an incognito window to discover which items have been claimed or bought (which would undermine the surprise protections in `WishListView`), the guest page renders all active wishes uniformly with zero claim or fulfillment indicators. Visitors who want to coordinate, claim an item, or split expenses are prompted to sign up or log in, then connect with the list owner.

## Motivation

A common friction point in private family apps is the "grandparent hurdle": extended family members who only buy one gift a year do not want to register an account, set a password, verify their email, and learn a new application just to see what a grandchild or friend wants for Christmas.

GiftList overcomes this by making public links the default. In Gift Manager, however, access is strictly governed by `PermissionService` between mutual friends. Opening up full anonymous claiming would introduce serious risks: rate-limiting headaches, spam claims, lack of accountability, and no clean way for an anonymous guest to edit or cancel a claim later.

A read-only tokenized guest link solves the sharing friction safely. Relatives get instant access to view titles, links, price hints, and notes, while state-changing coordination remains safely protected behind registered accounts.

## User Value

- Users easily share their wishlist (or a child's wishlist) via WhatsApp, SMS, or email with anyone.
- Relatives view what to buy without account creation, app downloads, or passwords.
- List owners maintain complete control: links can be revoked or regenerated at any time.
- Preserves surprise protection: because the public view displays no claim state, the owner cannot use it to snoop on their own surprises.
- Prevents database vandalism and spam: read-only access eliminates anonymous claim abuse.

## Possible Scope

- A dedicated sharing model (e.g. `WishlistShare`) supporting both personal and dependent wishlists:
  - Fields: `token` (`CharField(max_length=64, unique=True)`), `user` (nullable FK for personal wishlists), `person` (nullable FK for dependent wishlists), `is_active` (`BooleanField`), `created_at`.
  - Generates unguessable 192-bit cryptographic tokens via `secrets.token_urlsafe(24)`.
  - At most one active share per list: regenerating deactivates (or replaces) the previous share instead of adding another active link.
- Who can share:
  - A personal wishlist: only its owner (`share.user == request.user`).
  - A dependent's wishlist: only a user with `OWNER` permission on that `Person`, matching the management rule of `0032`.
- UI controls:
  - A toggle in the wishlist UI: "Enable public share link" with an instant "Copy link" button (`/wishes/share/<token>/`).
  - An option to revoke or regenerate the link immediately.
- A dedicated, clean read-only guest template:
  - Renders active wishes (title, notes, price hint, external shop link) styled with Bootstrap.
  - Hides internal platform navigation, headers, edit actions, and claim buttons.
  - Displays all active wishes uniformly without showing whether an item is claimed or fulfilled.
  - Displays a subtle banner: "Want to reserve gifts and coordinate with the family? Sign up or log in, then ask [owner] to add you as a friend." linking to `account_signup` and `account_login`. The invitation flow cannot be used here: an invitation is sent by an existing user to an email address, so a guest cannot start it alone.
- Security headers:
  - `Referrer-Policy: no-referrer` (and `rel="noreferrer"` on all external links) to prevent leaking the secret token in HTTP referrers to external retailers.
  - `Cache-Control: private, no-store` so that revoking a link takes effect immediately without stale cache hits on Vercel's CDN.
  - `X-Robots-Tag: noindex, nofollow` to prevent search engine indexing.

## Out Of Scope

- Anonymous claiming or reservations without an account (explicitly excluded due to spam, undoability, and data integrity risks).
- Claim or fulfillment indicators on the guest page (excluded to prevent surprise leaks to the list owner).
- Custom domain vanity URLs.

## Implementation Notes For AI Agent

- Data model:
  - Create a model `WishlistShare` with `token = models.CharField(max_length=64, unique=True)`, `user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE)`, `person = models.ForeignKey(Person, null=True, blank=True, on_delete=models.CASCADE)`, `is_active = models.BooleanField(default=True)`.
  - Add a check constraint ensuring exactly one of `user` or `person` is populated.
  - Add two conditional unique constraints, `UniqueConstraint(fields=["user"], condition=Q(is_active=True, user__isnull=False))` and the same for `person`, so a list never has two active links.
  - Note that `unique=True` on `token` automatically creates a database index; `db_index=True` is redundant.
- View & URLs:
  - Create a public view (e.g. `GuestWishlistView` in `gift_manager/views/wishlist.py`) mapped to `path("wishes/share/<str:token>/", ...)`.
  - The view inherits from `View` (not `LoginRequiredMixin`).
  - Look up the active share: `share = get_object_or_404(WishlistShare, token=token, is_active=True)`.
  - Query active wishes correctly:
    - If `share.user`: `Wish.objects.filter(wisher=share.user, person__isnull=True, is_archived=False, is_deleted_by_wisher=False).order_by("-priority", "-created_at")`.
    - If `share.person`: `Wish.objects.filter(person=share.person, is_archived=False, is_deleted_by_wisher=False).order_by("-priority", "-created_at")`.
  - Response headers: set `response["Referrer-Policy"] = "no-referrer"`, `response["Cache-Control"] = "private, no-store"`, and `response["X-Robots-Tag"] = "noindex, nofollow"`.
- Template:
  - Create `gift_manager/templates/gift_manager/wishlist_guest.html` extending a minimal shell (or a distraction-free version of `base.html` without app navigation).
  - External shop links must include `rel="noopener noreferrer"`.

Recommended starting context:

- `docs/ai/architecture.md`
- `gift_manager/models.py`
- `gift_manager/views/wishlist.py`
- `gift_manager/templates/gift_manager/`

## Acceptance Criteria

- A user can enable guest sharing and copy their unique wishlist share URL for their personal list, or for a dependent's list when they have `OWNER` permission on that `Person`; other users cannot create or manage that share.
- Regenerating a link leaves exactly one active share for the list.
- An unauthenticated visitor accessing the valid URL sees the list of wishes with external links and details.
- The guest view renders all active wishes uniformly without showing whether an item is claimed or fulfilled, preventing surprise leaks.
- Soft-deleted wishes (`is_deleted_by_wisher=True`) and archived wishes never appear.
- External product links include `rel="noreferrer"` and the page sends `Referrer-Policy: no-referrer`.
- The response sets `Cache-Control: private, no-store` so revocation works immediately on Vercel.
- Disabling the share link or regenerating the token immediately causes subsequent requests to the old URL to return 404.
- Guest views are strictly read-only and return `X-Robots-Tag: noindex, nofollow`.
- Unit tests verify token generation, access with valid/invalid tokens, toggle state, header security, and 404 behavior.

## Dependencies Or Related Ideas

- Builds on `0028` (Wishlists And Collaborative Gift Giving).
- Complements `0032` (Managed Wishlists For Children And Dependents).

## Open Questions

- Should guest links support an optional expiration date (for example, auto-disabling 30 days after creation or after an event date)?
