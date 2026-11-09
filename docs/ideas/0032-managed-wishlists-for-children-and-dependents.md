# Idea: Managed Wishlists For Children And Dependents

## Status

Proposed

## Summary

Enable parents and guardians to manage wishlists on behalf of children and other dependents who do not have their own user accounts. Today, `Wish` rows are tied directly to a registered `User` account (`wisher=user`). While parents can create `Person` records for their children, they cannot publish a wishlist for those records that family members (grandparents, aunts, uncles) can see and claim against.

This idea anchors wishes to a `Person` record when managed by a guardian, while explicitly resolving the "parent-giver visibility conflict": unlike adult self-managed wishlists where claims are hidden from the wisher to keep gifts a surprise, a guardian managing a child's list is usually also a primary gift buyer who needs to see what others have claimed to coordinate purchases and avoid duplicate gifts.

## Motivation

A major use case for universal wishlist apps like GiftList is managing gift requests for children during birthdays and holidays. Parents frequently get asked by relatives: "What does the little one want this year?"

In Gift Manager, `Person` records represent recipients, and permissions allow sharing those records among friends and family groups. However, the wishlist system introduced in `0028` only supports wishes belonging to a `User`. Because children do not have email addresses or login accounts, parents cannot create a shared wishlist for them.

Crucially, child wishlists present two distinct architectural requirements:
1. **Query Isolation:** `Wish` queries must prevent child wishes from leaking onto the parent's personal wishlist or to friends who do not have access to the child's record.
2. **Claim Visibility:** On an adult wishlist, the wisher must never see who claimed their wishes (`WishListView` defers claims). For a child's list, however, the managing parent coordinates gifts with extended family. If claims are hidden from the parent, the parent cannot know what grandma already bought. If claims are visible to everyone, there is no surprise for the parent, but the child remains surprised. The system needs an explicit, intuitive rule for claim visibility on managed dependent lists.

## User Value

- Parents collect and share gift wishes for their kids in one place without repeating them across family group chats.
- Relatives (grandparents, godparents, friends) see accurate wishlists for children they buy gifts for.
- Clear coordination: parents and relatives avoid buying duplicate toys or clothes.
- Preserves surprise for the child while giving parents the visibility needed to manage family gifting.

## Possible Scope

- Allow a `Wish` to be associated with an owned `Person` record (for example, an optional `person` foreign key on `Wish`).
- Query separation in `WishQuerySet` (`gift_manager/models.py:1376-1394`):
  - Update `for_wisher()` to require `person__isnull=True`, preventing child wishes from appearing on the parent's personal wishlist.
  - Update `visible_to_friend()` to require `person__isnull=True`, preventing child wishes from being visible to parent friends who do not share the child's record.
  - Add `for_person(person, viewer)` governed strictly by permissions on that `Person` record.
- Management permissions: only users with `OWNER` permission on the `Person` record can add, edit, or archive wishes for that person.
- Visibility for relatives:
  - Because `Person` records in Gift Manager are private per user, relatives only see the child's wishlist if the parent shares their `Person` record with them (via `PersonPermission` direct sharing or a shared family `PersonGroup`). The UI should explain this and guide sharing when creating a dependent wishlist.
  - Users with shared access to the `Person` record view the wishlist on the person's detail page (`gift_manager/templates/gift_manager/person_detail.html`).
- Claim visibility policy:
  - Givers (relatives/friends) see wish claims as normal.
  - The managing parent/guardian can view claims on the child's wishlist (unlike their own personal wishlist) so they can coordinate purchases.
  - An optional per-wish or per-person toggle ("Keep claims secret from me") for parents who want to be surprised by what relatives choose.
- Converting child wishes into gift plans: givers can claim a child's wish and turn it into a private surprise `Relation` plan, matching adult wish planning under `0028`.

## Out Of Scope

- Minor user accounts, youth logins, or child authentication.
- Multi-guardian co-ownership permissions beyond existing `PersonPermission` levels.
- Public sharing without an account (covered separately in `0033`).

## Implementation Notes For AI Agent

- Data model:
  - Inspect `Wish` in `gift_manager/models.py`. Currently, `wisher = models.ForeignKey(User, on_delete=models.CASCADE, related_name="wishes")`.
  - Add an optional `person = models.ForeignKey("Person", null=True, blank=True, on_delete=models.CASCADE, related_name="managed_wishes")`. A wish is either personal (`person is None`, belonging to `wisher`) or managed (`person` set, created by `wisher` who owns `person`).
  - Validation: require `person.account IS NULL` (a record linked to an account is that user's own wishlist, never a managed one), and that `wisher` has `OWNER` rights on `person`.
- Visibility and queries:
  - Update `WishQuerySet.for_wisher` (`gift_manager/models.py:1379`): filter `wisher=user, person__isnull=True, is_deleted_by_wisher=False`.
  - Update `WishQuerySet.visible_to_friend` (`gift_manager/models.py:1385`): filter `wisher=wisher_user, person__isnull=True`.
  - Implement `WishQuerySet.for_person(person, viewer)`: checks `PermissionService.get_effective_permission(person, viewer) >= PermissionLevel.VIEWER`. If `viewer` is the manager (owner), only defer claims if surprise mode is enabled. If `viewer` is a giver, show active wishes with claims visible.
- UI & Integration:
  - Add a "Wishlist" tab or section to `gift_manager/templates/gift_manager/person_detail.html` alongside history and notes.
  - Managers see an "Add wish" button that opens `WishForm` pre-set with `person`.
  - Givers see the list with "Claim" and "Plan" action buttons, served by `WishClaimToggleView` and `WishPlanView` in `gift_manager/views/wishlist.py`. These views cannot be reused as-is: they gate access with `Wish.objects.visible_to_friend(request.user, person.account)` (`gift_manager/views/wishlist.py:317`, `:332`, `:383`), and a dependent has no `account`. Add a branch for managed wishes that checks access through `for_person(person, request.user)` instead.
- Claim release:
  - Personal-wish claims are released on unfriending (`_is_friend_of_wisher` in `gift_manager/wishlist.py:215`, `:238`). Friendship is irrelevant for managed wishes: their claims must instead be released when the claimer loses access to the `Person` (direct unshare, removal from the sharing `PersonGroup`, or loss of the group permission), reusing the same release path.
- Tests:
  - Verify query isolation: `for_wisher` never returns dependent wishes; `visible_to_friend` never exposes dependent wishes to non-shared friends.
  - Verify permission boundaries: only person owners can edit child wishes; viewers with shared person access can view and claim.
  - Verify that claims by friends update correctly and convert to `Relation` plans without breaking `hidden_surprises_for`.
  - Verify that a claimer who loses access to the `Person` has their claim released, and that unfriending the guardian alone does not release it while access to the `Person` remains.

Recommended starting context:

- `docs/ai/architecture.md`
- `docs/ideas/implemented/0028-wishlists-and-collaborative-gift-giving.md`
- `gift_manager/models.py`
- `gift_manager/wishlist.py`
- `gift_manager/views/wishlist.py`

## Acceptance Criteria

- An owner of a `Person` record without an account link can create, edit, archive, and delete wishes for that person.
- `WishQuerySet.for_wisher` and `visible_to_friend` strictly exclude dependent wishes (`person__isnull=True`).
- Users who have shared access to that `Person` can view the wishlist on the person's detail page.
- Users with access to the `Person` can claim a dependent's wish and convert it into a gift plan (`Relation`), without being friends with the guardian.
- By default, the managing guardian can see claim statuses on the dependent's wishes to coordinate family gifting without duplicates.
- Deleting the `Person` record respects existing cascade and orphan-purging rules (`purge_if_orphaned`).
- When a claimer loses access to the `Person` (unshared directly or through a group), their claims on that person's wishes are released.
- Tests cover query isolation, owner management, viewer claiming, and claim visibility rules.

## Dependencies Or Related Ideas

- Builds on `0028` (Wishlists And Collaborative Gift Giving) and `0006` (Recipient Notes And Interests).
- Can be combined with `0031` (Bookmarklet) to quickly add items to a child's list.
- Can be viewed via `0033` (Read-Only Guest Wishlist Links) if public sharing is enabled.

## Open Questions

- What happens when a child eventually creates their own user account and is linked via `Person.account`: should existing managed wishes migrate to the new account, be archived, or offer a prompt during linking?
- Should co-parents (e.g. two users with `EDITOR` access to the same child `Person`) both be allowed to manage the wishlist, or strictly the `OWNER`?
- Should the default for guardians be "claims visible" (coordination-first) with an opt-in "surprise me" toggle, or vice versa?
