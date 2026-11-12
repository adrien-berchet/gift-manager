"""The wisher's "Received" state on the wishlist, derived only from their own received gifts."""

from datetime import date

import pytest
from django.urls import reverse

from gift_manager import wishlist
from gift_manager.models import PermissionLevel
from gift_manager.models import ReceivedGift
from gift_manager.services import PermissionService
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationStatusFactory
from gift_manager.tests.factories import UserFactory
from gift_manager.tests.factories import WishFactory


@pytest.fixture
def user():
    return UserFactory()


def _receive(user, wish, received_on, *, fulfills=True, title=None):
    return ReceivedGift.objects.create(
        recipient_user=user,
        title=title or wish.title,
        giver_label="Aunt Marie",
        wish=wish,
        received_on=received_on,
        fulfills_wish=fulfills,
    )


def _section(content, marker):
    start = content.index(marker)
    end = content.find("</details>", start)
    return content[start : end if end != -1 else None]


@pytest.mark.django_db
class TestOwnReceipts:
    def test_latest_counting_and_latest_overall_gift_per_wish(self, user):
        wish = WishFactory(wisher=user)
        _receive(user, wish, date(2025, 1, 1))
        counting = _receive(user, wish, date(2025, 6, 1))
        latest = _receive(user, wish, date(2026, 1, 1), fulfills=False)
        other = WishFactory(wisher=user)

        receipts = wishlist.own_receipts(user, [wish, other])

        assert receipts[wish.pk].received_gift == counting
        assert receipts[wish.pk].last_gift == latest
        assert other.pk not in receipts

    def test_only_the_users_own_received_gifts_count(self, user):
        wish = WishFactory(wisher=user)
        _receive(UserFactory(), wish, date(2026, 1, 1))

        assert wishlist.own_receipts(user, [wish]) == {}


@pytest.mark.django_db
class TestWishlistPage:
    url = reverse("gift_manager:wishlist_list")

    def test_received_wish_moves_to_its_own_section_with_a_badge(self, client, user):
        received = WishFactory(wisher=user, title="Espresso Machine")
        WishFactory(wisher=user, title="Board Game")
        gift = _receive(user, received, date(2026, 11, 2))
        client.force_login(user)

        content = client.get(self.url).content.decode()

        active = content[: content.index("received-wishes-section")]
        assert "Board Game" in active
        assert "Espresso Machine" not in active
        section = _section(content, "received-wishes-section")
        assert "Received wishes (1)" in section
        assert "Espresso Machine" in section
        assert "Received on Nov. 2, 2026" in section
        detail_url = reverse("gift_manager:received_gift_detail", args=[gift.received_gift_id])
        assert f'href="{detail_url}"' in section

    def test_repeatable_wish_stays_active_with_its_last_reception(self, client, user):
        wish = WishFactory(wisher=user, title="Dark Chocolate")
        _receive(user, wish, date(2026, 10, 5), fulfills=False)
        client.force_login(user)

        content = client.get(self.url).content.decode()

        assert "received-wishes-section" not in content
        assert "Dark Chocolate" in content
        assert "Last received on Oct. 5, 2026" in content

    def test_archived_received_wish_stays_archived(self, client, user):
        wish = WishFactory(wisher=user, title="Old Lamp", is_archived=True)
        _receive(user, wish, date(2026, 1, 3))
        client.force_login(user)

        content = client.get(self.url).content.decode()

        assert "received-wishes-section" not in content
        assert "Old Lamp" in _section(content, "archived-wishes-section")

    def test_a_friends_given_plan_is_never_shown_as_received(self, client, user):
        """Anti-spoiler: only gifts the wisher recorded mark a wish received on their list."""
        wish = WishFactory(wisher=user, title="Secret Telescope")
        friend = UserFactory()
        user.profile.friends.add(friend.profile)
        friend.profile.friends.add(user.profile)
        wisher_person = PersonFactory(account=user)
        PermissionService.create_or_update_permission(
            friend, wisher_person, permission_level=PermissionLevel.OWNER
        )
        plan = wishlist.plan_wish(wish, friend, wisher_person)
        plan.status = RelationStatusFactory(status="Given")
        plan.save()
        wishlist.sync_wish_on_plan_change(plan)
        wish.refresh_from_db()
        assert wish.is_fulfilled is True
        client.force_login(user)

        content = client.get(self.url).content.decode()

        assert "received-wishes-section" not in content
        assert "Received on" not in content

    def test_receipts_cost_a_constant_number_of_queries(
        self, client, user, django_assert_max_num_queries
    ):
        for index in range(5):
            _receive(user, WishFactory(wisher=user), date(2026, 1, index + 1))
        client.force_login(user)
        client.get(self.url)  # warm session/profile caches

        with django_assert_max_num_queries(12):
            client.get(self.url)
        for index in range(5):
            _receive(user, WishFactory(wisher=user), date(2026, 2, index + 1))
        with django_assert_max_num_queries(12):
            client.get(self.url)


@pytest.mark.django_db
class TestWishPanel:
    def test_edit_panel_lists_received_gifts_and_offers_to_record_one(self, client, user):
        wish = WishFactory(wisher=user, title="Chocolate")
        counted = _receive(user, wish, date(2026, 3, 1))
        not_counted = _receive(user, wish, date(2026, 9, 1), fulfills=False)
        client.force_login(user)

        content = client.get(reverse("gift_manager:wish_edit", args=[wish.wish_id])).content
        content = content.decode()

        block = content[content.index('class="wish-received') :]
        assert "March 1, 2026" in block
        assert "Sept. 1, 2026" in block
        assert f"{reverse('gift_manager:received_gift_create')}?wish={wish.wish_id}" in block
        toggle = reverse(
            "gift_manager:received_gift_toggle_fulfills_wish", args=[counted.received_gift_id]
        )
        assert f'action="{toggle}"' in content
        assert "Don&#x27;t count as received" in block or "Don't count as received" in block
        assert "Count as received" in block
        assert str(not_counted.received_gift_id) in content

    def test_panel_says_not_received_yet(self, client, user):
        wish = WishFactory(wisher=user)
        client.force_login(user)

        content = client.get(reverse("gift_manager:wish_edit", args=[wish.wish_id])).content

        assert "Not received yet." in content.decode()

    def test_create_panel_has_no_received_block(self, client, user):
        client.force_login(user)

        content = client.get(reverse("gift_manager:wish_create")).content.decode()

        assert 'class="wish-received' not in content


@pytest.mark.django_db
class TestToggleFulfillsWish:
    def _url(self, gift):
        return reverse(
            "gift_manager:received_gift_toggle_fulfills_wish", args=[gift.received_gift_id]
        )

    def test_htmx_toggle_updates_the_wish_and_returns_the_block(self, client, user):
        wish = WishFactory(wisher=user, title="Chocolate")
        gift = _receive(user, wish, date(2026, 3, 1))
        client.force_login(user)

        response = client.post(self._url(gift), headers={"HX-Request": "true"})

        assert response.status_code == 200
        assert "list:update" in response["HX-Trigger"]
        assert 'class="wish-received' in response.content.decode()
        gift.refresh_from_db()
        wish.refresh_from_db()
        assert gift.fulfills_wish is False
        assert wish.is_fulfilled is False

        client.post(self._url(gift), headers={"HX-Request": "true"})
        wish.refresh_from_db()
        assert wish.is_fulfilled is True

    def test_without_htmx_redirects_to_the_wish(self, client, user):
        wish = WishFactory(wisher=user)
        gift = _receive(user, wish, date(2026, 3, 1))
        client.force_login(user)

        response = client.post(self._url(gift))

        assert response.status_code == 302
        assert response.url == reverse("gift_manager:wish_edit", args=[wish.wish_id])

    def test_other_users_gift_is_not_found(self, client, user):
        gift = _receive(UserFactory(), WishFactory(), date(2026, 3, 1))
        client.force_login(user)

        assert client.post(self._url(gift)).status_code == 404
        gift.refresh_from_db()
        assert gift.fulfills_wish is True

    def test_gift_without_wish_is_not_found(self, client, user):
        gift = ReceivedGift.objects.create(recipient_user=user, title="Scarf", giver_label="A")
        client.force_login(user)

        assert client.post(self._url(gift)).status_code == 404


@pytest.mark.django_db
class TestSoftDeletedWishAndLinkableGivers:
    def test_soft_delete_wish_unlinks_received_gifts_and_recomputes_fulfilled(self, user):
        friend = UserFactory()
        user.profile.friends.add(friend.profile)
        wish = WishFactory(wisher=user, title="Stand Mixer")
        wish.claimed_by = friend
        wish.claimed_at = wish.created_at
        wish.save(update_fields=["claimed_by", "claimed_at"])

        gift = _receive(user, wish, date(2026, 4, 1))
        wish.refresh_from_db()
        assert wish.is_fulfilled is True

        wishlist.delete_wish(wish, user)
        wish.refresh_from_db()
        gift.refresh_from_db()
        assert wish.is_deleted_by_wisher is True
        assert wish.is_fulfilled is False
        assert gift.wish is None
        assert gift.title == "Stand Mixer"

    def test_wish_edit_renders_accessible_person_link_and_plain_inaccessible_group(
        self, client, user
    ):
        wish = WishFactory(wisher=user, title="Board Game")
        accessible_person = PersonFactory(first_name="Clara")
        inaccessible_group = PersonGroupFactory(name="Hidden Club")
        PermissionService.create_or_update_permission(
            user, accessible_person, permission_level=PermissionLevel.OWNER
        )
        gift = ReceivedGift.objects.create(
            recipient_user=user,
            title="Board Game",
            wish=wish,
            received_on=date(2026, 5, 1),
            fulfills_wish=True,
        )
        gift.giver_persons.add(accessible_person)
        gift.giver_groups.add(inaccessible_group)

        client.force_login(user)
        response = client.get(reverse("gift_manager:wish_edit", args=[wish.wish_id]))
        assert response.status_code == 200
        html = response.content.decode()
        assert reverse("gift_manager:person_detail", args=[accessible_person.person_id]) in html
        assert "Hidden Club" in html
        group_url = reverse("gift_manager:person_group_detail", args=[inaccessible_group.group_id])
        assert group_url not in html
