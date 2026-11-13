# QA Scenarios

Journeys to test in browser QA passes. Each lists the accounts it needs (seed data: alice and
bob are ordinary users, testuser is a superuser) and what to check. Add a journey whenever a
feature ships or a pass finds a gap.

## Gift plans

- **Create and edit** (any user): create a plan from the dashboard side panel, then from a
  person page; edit it to Given. Check the lists and counters update without a reload, the
  dropdowns are styled, and the "Reveal to recipient" toast stays until closed when the
  recipient is a friend with an account.
- **Quick actions** (any user): mark a card Given; the reaction prompt offers "Save & reveal".
  Undo the action.
- **New gift from the plan form** (any user): create a plan with "Or a new gift" filled and
  no gift chosen; the gift appears on the Gifts page, owned by the user. Choosing a gift and
  naming one is refused; sharing the new plan with a friend shares the new gift.
- **Given plan** (any user): a plan marked Given shows "Given on" on its card and its page
  instead of "No date", no "I'll take this" button, and no Surprise badge once revealed.
- **Viewer rights** (alice shares a plan with bob as viewer): bob sees no Edit or Delete links
  for it in person, group, event and gift pages.

## Reveal and received gifts

- **Reveal to a friend** (testuser → alice, friends): Given plan, reveal from the card, the
  toast, the plan page and the gift history; then alice sees it in her received gifts with the
  right title, link, date, occasion and note. A second reveal is refused; an old reveal link
  opens the plan with "This gift plan was already revealed."
- **Co-owned plan** (testuser and bob own it; alice is friends with testuser only): alice sees
  testuser by name or as her contact and bob only as "and 1 other".
- **Reaction** (alice): rate and annotate the received gift, share it; the giver's plan gets
  the rating and note.
- **Wish fulfilled** (testuser plans alice's wish, gives and reveals it): alice's wish is
  received; when she turns off "Mark the wish as received", testuser sees it Available again
  and can plan it.
- **Manual entry** (alice): record a gift with contacts, a free-text giver, an event or a
  free-text occasion; a future date shows a warning but saves.
- Check the reveal panel and received-gift screens in dark mode and at 390 px.

## Sharing and deleting

- **Viewer leaves** (alice shares Mom with bob as viewer): bob's Delete reads "Remove my
  access" on the page, the side panel and the edit form; after confirming, alice still owns Mom.
- **Only owner hands over** (alice owns Mom, shares it with bob, they are friends): "Hand over
  and remove my access" asks for the new owner (editors first); bob becomes owner. Without a
  friend to hand over to, the button is disabled with the reason.
- **Row menus** (alice shares Mom with bob as viewer): in the People grid, bob's row menu
  holds only "Remove my access"; confirming removes the row and alice still owns Mom. The
  only owner of a shared object with no friend to hand it to sees a disabled Delete with
  the reason. The group tree view, the status page grid and the plan lists of gift and
  event pages offer no Edit or Delete the user may not use.
- **Global Birthday event**: nobody, superuser included, can edit or delete it (page, grid,
  edit URL, Django admin).

## Dashboard and lists

- "Needs attention" is highlighted only when its count is not 0; "Awaiting reaction" has its
  own section.
- "Unassigned gifts" opens the Gifts page in "Not in a plan yet"; planning one of them removes
  it from that view.
- Group member counts match on the recipients page and the group explorer.
- The Recipients page lists the user's own person with "This is you" and no "New Gift Plan";
  its count matches the dashboard's Recipients tile.
- The Statuses page gives the number of the user's plans per status; a status badge on a
  card or a detail page opens that status's plans.
- The filter panel of a grid is fully translated in French and offers no "checkbox" sort.
- Ctrl+K then typing at once: no character is lost.

## Profile and wishlist

- The profile's active wish count leaves out received wishes.
- The delete-account and deactivate-account pages cancel back to the profile.

## Everywhere

- French pages show no English text on changed screens.
- Light and dark themes are readable (contrast at least 4.5:1 for text).
- No horizontal scrolling at 390 px.
