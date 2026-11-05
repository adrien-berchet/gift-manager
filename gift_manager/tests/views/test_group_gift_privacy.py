"""Privacy boundary and side-channel invariant tests for group gifts.

Verifies that no side channel leaks group gift tallies, contributor names, or amounts
to recipients, external feeds, email digests, or AI suggestion prompts.
"""

from __future__ import annotations

import ast
from datetime import date
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.utils import timezone

from gift_manager import account_links
from gift_manager import group_gifts
from gift_manager.calendar_feed import build_calendar
from gift_manager.digest_sending import _build_message
from gift_manager.models import PermissionLevel
from gift_manager.models import RelationContribution
from gift_manager.models import SplitMode
from gift_manager.reminders import build_digest
from gift_manager.services import PermissionService
from gift_manager.suggestions.ai.prompt import build_ai_payload
from gift_manager.suggestions.history import build_recipient_history
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import GroupRelationFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

SENTINEL_CONTRIBUTOR = "ZqxContributor"
SENTINEL_AMOUNT = Decimal("1234.56")
SENTINEL_AMOUNT_STRS = ["1234.56", "1,234.56", "1234,56"]


def _befriend(first, second):
    first.profile.friends.add(second.profile)


def _grant(obj, user, level=PermissionLevel.OWNER, attr=None):
    PermissionService.create_or_update_permission(
        user, obj, permission_level=level, object_attr=attr
    )


# --- 1. Service-Level Recipient 403 Tests -----------------------------------------------------


@pytest.mark.parametrize("recipient_kind", ["person", "group", "nested_group"])
@pytest.mark.parametrize("is_surprise", [False, True])
def test_recipient_gets_403_on_all_group_gift_service_calls(recipient_kind, is_surprise):
    """Recipient user calling any group gift service function gets generic PermissionDenied."""
    owner = UserFactory(username="plan_owner")
    recipient = UserFactory(username="plan_recipient")
    collaborator = UserFactory(username="plan_collab")
    _befriend(owner, recipient)
    _befriend(owner, collaborator)

    if recipient_kind == "person":
        person = PersonFactory(account=recipient)
        _grant(person, owner, PermissionLevel.OWNER)
        relation = RelationFactory(
            person=person,
            group=None,
            price=Decimal("100.00"),
            is_surprise=is_surprise,
            is_group_gift=True,
            split_mode=SplitMode.EQUAL,
        )
    elif recipient_kind == "group":
        group = PersonGroupFactory()
        _grant(group, owner, PermissionLevel.OWNER)
        recip_person = PersonFactory(account=recipient)
        recip_person.groups.add(group)
        relation = GroupRelationFactory(
            group=group,
            price=Decimal("100.00"),
            is_surprise=is_surprise,
            is_group_gift=True,
            split_mode=SplitMode.EQUAL,
        )
    else:  # nested_group
        parent_group = PersonGroupFactory()
        _grant(parent_group, owner, PermissionLevel.OWNER)
        child_group = PersonGroupFactory()
        _grant(child_group, owner, PermissionLevel.OWNER)
        child_group.parent_groups.add(parent_group)
        recip_person = PersonFactory(account=recipient)
        recip_person.groups.add(child_group)
        relation = GroupRelationFactory(
            group=parent_group,
            price=Decimal("100.00"),
            is_surprise=is_surprise,
            is_group_gift=True,
            split_mode=SplitMode.EQUAL,
        )

    _grant(relation, owner, PermissionLevel.OWNER, "relation")
    _grant(relation, collaborator, PermissionLevel.EDITOR, "relation")
    if not is_surprise:
        _grant(relation, recipient, PermissionLevel.VIEWER, "relation")

    contrib = RelationContribution.objects.create(
        relation=relation,
        user=collaborator,
        name=collaborator.username,
        amount=Decimal("50.00"),
        is_paid=False,
    )

    err_msg = "You do not have permission to do this on this gift plan."

    # 1. enable_group_gift
    with pytest.raises(PermissionDenied, match=err_msg):
        group_gifts.enable_group_gift(relation, recipient)

    # 2. disable_group_gift
    with pytest.raises(PermissionDenied, match=err_msg):
        group_gifts.disable_group_gift(relation, recipient)

    # 3. set_split_mode
    with pytest.raises(PermissionDenied, match=err_msg):
        group_gifts.set_split_mode(relation, recipient, SplitMode.CUSTOM)

    # 4. add_contributor
    with pytest.raises(PermissionDenied, match=err_msg):
        group_gifts.add_contributor(relation, recipient, name="Someone")

    # 5. remove_contributor
    with pytest.raises(PermissionDenied, match=err_msg):
        group_gifts.remove_contributor(contrib, recipient)

    # 6. toggle_contribution_paid
    with pytest.raises(PermissionDenied, match=err_msg):
        group_gifts.toggle_contribution_paid(contrib, recipient)

    # 7. update_contribution_amount
    with pytest.raises(PermissionDenied, match=err_msg):
        group_gifts.update_contribution_amount(contrib, recipient, Decimal("20.00"))

    # 8. get_group_gift_summary
    with pytest.raises(PermissionDenied, match=err_msg):
        group_gifts.get_group_gift_summary(relation, recipient)


def test_group_member_owner_positive_control():
    """A member of a recipient group who is an OWNER of the plan is not treated as recipient."""
    owner_member = UserFactory(username="owner_member")
    group = PersonGroupFactory()
    _grant(group, owner_member, PermissionLevel.OWNER)
    member_person = PersonFactory(account=owner_member)
    member_person.groups.add(group)

    relation = GroupRelationFactory(
        group=group,
        price=Decimal("100.00"),
        is_group_gift=True,
        split_mode=SplitMode.EQUAL,
    )
    _grant(relation, owner_member, PermissionLevel.OWNER, "relation")

    # Assert get_group_gift_summary succeeds for owner_member
    summary = group_gifts.get_group_gift_summary(relation, viewer=owner_member)
    assert summary.is_group_gift is True
    assert summary.can_manage is True


# --- 2. Future Task 4 View Endpoints with Strict xfail ---------------------------------------


@pytest.mark.parametrize(
    "url_name,kwargs_builder",
    [
        (
            "gift_manager:relation_group_gift_toggle",
            lambda rel, _c: {"pk": rel.relation_id},
        ),
        (
            "gift_manager:relation_group_gift_mode",
            lambda rel, _c: {"pk": rel.relation_id},
        ),
        (
            "gift_manager:relation_group_gift_contributor_add",
            lambda rel, _c: {"pk": rel.relation_id},
        ),
        (
            "gift_manager:relation_group_gift_contributor_remove",
            lambda rel, c: {"pk": rel.relation_id, "contribution_id": c.pk},
        ),
        (
            "gift_manager:relation_group_gift_contributor_toggle_paid",
            lambda rel, c: {"pk": rel.relation_id, "contribution_id": c.pk},
        ),
        (
            "gift_manager:relation_group_gift_contributor_amount",
            lambda rel, c: {"pk": rel.relation_id, "contribution_id": c.pk},
        ),
    ],
)
def test_future_group_gift_endpoints_return_403_for_recipient(client, url_name, kwargs_builder):
    """All 6 group gift endpoints return HTTP 403 when called by the recipient."""
    owner = UserFactory()
    recipient = UserFactory()
    _befriend(owner, recipient)

    person = PersonFactory(account=recipient)
    _grant(person, owner, PermissionLevel.OWNER)

    relation = RelationFactory(
        person=person,
        group=None,
        price=Decimal("100.00"),
        is_surprise=False,
        is_group_gift=True,
    )
    _grant(relation, owner, PermissionLevel.OWNER, "relation")
    _grant(relation, recipient, PermissionLevel.VIEWER, "relation")

    contrib = RelationContribution.objects.create(
        relation=relation,
        name="External Contributor",
        amount=Decimal("50.00"),
    )

    url = reverse(url_name, kwargs=kwargs_builder(relation, contrib))

    client.force_login(recipient)
    response = client.post(url, data={})
    assert response.status_code == 403

    # Nonexistent contribution ID still returns 403 (no 404 leakage for recipient)
    kw = kwargs_builder(relation, contrib)
    if "contribution_id" in kw:
        bad_kw = dict(kw)
        bad_kw["contribution_id"] = 999999
        url_bad = reverse(url_name, kwargs=bad_kw)
        res_bad = client.post(url_bad, data={})
        assert res_bad.status_code == 403


# --- 3. Existing View Surfaces & Markup Privacy -----------------------------------------------


def test_recipient_never_sees_group_gift_markup_on_surprise_or_non_surprise_plan(client):
    """Recipient rendering relation_detail never receives group gift markup, table, or sentinels."""
    owner = UserFactory(username="giver_owner")
    recipient = UserFactory(username="recipient_user")
    collaborator = UserFactory(username="giver_collab")
    _befriend(owner, recipient)
    _befriend(owner, collaborator)

    person = PersonFactory(account=recipient)
    _grant(person, owner, PermissionLevel.OWNER)

    # 1. Surprise plan: 404 for recipient, 200 for collaborator
    surprise_plan = RelationFactory(
        person=person,
        group=None,
        gift=GiftFactory(name="Surprise Drone"),
        price=Decimal("50.00"),
        is_surprise=True,
        is_group_gift=True,
        split_mode=SplitMode.EQUAL,
    )
    _grant(surprise_plan, owner, PermissionLevel.OWNER, "relation")
    _grant(surprise_plan, collaborator, PermissionLevel.EDITOR, "relation")
    RelationContribution.objects.create(
        relation=surprise_plan,
        name=SENTINEL_CONTRIBUTOR,
        amount=SENTINEL_AMOUNT,
        is_paid=True,
        paid_at=timezone.now(),
    )

    client.force_login(recipient)
    surprise_url = reverse("gift_manager:relation_detail", kwargs={"pk": surprise_plan.relation_id})
    res_surprise_recip = client.get(surprise_url)
    assert res_surprise_recip.status_code == 404

    client.force_login(collaborator)
    res_surprise_collab = client.get(surprise_url)
    assert res_surprise_collab.status_code == 200

    # 2. Non-surprise shared plan: 200 for recipient, but strictly NO group gift data
    non_surprise_plan = RelationFactory(
        person=person,
        group=None,
        gift=GiftFactory(name="Shared Bicycle"),
        price=Decimal("50.00"),
        is_surprise=False,
        is_group_gift=True,
        split_mode=SplitMode.EQUAL,
    )
    _grant(non_surprise_plan, owner, PermissionLevel.OWNER, "relation")
    _grant(non_surprise_plan, recipient, PermissionLevel.VIEWER, "relation")
    _grant(non_surprise_plan, collaborator, PermissionLevel.EDITOR, "relation")
    RelationContribution.objects.create(
        relation=non_surprise_plan,
        name=SENTINEL_CONTRIBUTOR,
        amount=SENTINEL_AMOUNT,
        is_paid=True,
        paid_at=timezone.now(),
    )

    client.force_login(recipient)
    non_surprise_url = reverse(
        "gift_manager:relation_detail", kwargs={"pk": non_surprise_plan.relation_id}
    )
    res_non_surprise_recip = client.get(non_surprise_url)
    assert res_non_surprise_recip.status_code == 200

    html = res_non_surprise_recip.content.decode("utf-8")
    assert SENTINEL_CONTRIBUTOR not in html
    for amt_str in SENTINEL_AMOUNT_STRS:
        assert amt_str not in html

    # Group gift markup indicators must be absent for recipient
    assert "relation_group_gift" not in html
    assert "group-gift-card" not in html
    assert "contribution-tally" not in html

    # Context check: group_gift key should either be absent or None
    if hasattr(res_non_surprise_recip, "context") and res_non_surprise_recip.context is not None:
        for ctx in res_non_surprise_recip.context:
            assert ctx.get("group_gift") is None


# --- 4. Feeds and Digests Exclusion -----------------------------------------------------------


def test_calendar_feed_excludes_group_gift_data():
    """Private .ics calendar feed excludes all group gift data for recipient and collaborators."""
    owner = UserFactory()
    recipient = UserFactory()
    collaborator = UserFactory()
    _befriend(owner, recipient)
    _befriend(owner, collaborator)

    person = PersonFactory(account=recipient)
    _grant(person, owner, PermissionLevel.OWNER)

    plan = RelationFactory(
        person=person,
        group=None,
        gift=GiftFactory(name="Calendar Special Gift"),
        due_date=date.today() + timedelta(days=5),
        price=Decimal("50.00"),
        is_surprise=False,
        is_group_gift=True,
    )
    _grant(plan, owner, PermissionLevel.OWNER, "relation")
    _grant(plan, recipient, PermissionLevel.VIEWER, "relation")
    _grant(plan, collaborator, PermissionLevel.EDITOR, "relation")

    RelationContribution.objects.create(
        relation=plan,
        name=SENTINEL_CONTRIBUTOR,
        amount=SENTINEL_AMOUNT,
        is_paid=True,
        paid_at=timezone.now(),
    )

    # Positive control: collaborator feed contains the gift plan
    collab_feed = build_calendar(collaborator)
    assert plan.gift.name in collab_feed

    # Sensitive group gift data must not appear in collaborator feed
    assert SENTINEL_CONTRIBUTOR not in collab_feed
    for amt_str in SENTINEL_AMOUNT_STRS:
        assert amt_str not in collab_feed
    assert "group-gift" not in collab_feed
    assert "Group gift" not in collab_feed

    # Recipient feed
    recip_feed = build_calendar(recipient)
    assert plan.gift.name in recip_feed
    assert SENTINEL_CONTRIBUTOR not in recip_feed
    for amt_str in SENTINEL_AMOUNT_STRS:
        assert amt_str not in recip_feed


def test_email_digest_excludes_group_gift_data(settings):
    """Email reminder digest excludes all group gift data in repr and rendered templates."""
    settings.SITE_BASE_URL = "https://gifts.example.com"

    owner = UserFactory()
    collaborator = UserFactory()
    _befriend(owner, collaborator)

    person = PersonFactory()
    _grant(person, owner, PermissionLevel.OWNER)

    plan = RelationFactory(
        person=person,
        gift=GiftFactory(name="Digest Watch"),
        due_date=date.today() + timedelta(days=2),
        price=Decimal("50.00"),
        is_group_gift=True,
    )
    _grant(plan, owner, PermissionLevel.OWNER, "relation")
    _grant(plan, collaborator, PermissionLevel.EDITOR, "relation")

    RelationContribution.objects.create(
        relation=plan,
        name=SENTINEL_CONTRIBUTOR,
        amount=SENTINEL_AMOUNT,
        is_paid=True,
        paid_at=timezone.now(),
    )

    digest = build_digest(collaborator, today=date.today(), lookahead_days=7)
    digest_repr = repr(digest)

    # Positive control: plan appears in digest
    assert plan.gift.name in digest_repr

    # Negative check on digest object
    assert SENTINEL_CONTRIBUTOR not in digest_repr
    for amt_str in SENTINEL_AMOUNT_STRS:
        assert amt_str not in digest_repr

    # Rendered email message via digest_sending
    message = _build_message(collaborator, digest, collaborator.email)
    body_text = message.body
    body_html = message.alternatives[0][0]

    # Positive control: plan appears in rendered email
    assert plan.gift.name in body_text
    assert plan.gift.name in body_html

    # Negative checks in rendered email templates
    assert SENTINEL_CONTRIBUTOR not in body_text
    assert SENTINEL_CONTRIBUTOR not in body_html
    for amt_str in SENTINEL_AMOUNT_STRS:
        assert amt_str not in body_text
        assert amt_str not in body_html


def test_ai_prompt_excludes_group_gift_data():
    """AI suggestion prompt payload contains no group gift text or contributor names."""
    owner = UserFactory()
    recipient = UserFactory()
    _befriend(owner, recipient)

    person = PersonFactory(account=recipient)
    _grant(person, owner, PermissionLevel.OWNER)

    plan = RelationFactory(
        person=person,
        gift=GiftFactory(name="AI Robot Toy"),
        price=Decimal("50.00"),
        is_group_gift=True,
    )
    _grant(plan, owner, PermissionLevel.OWNER, "relation")

    RelationContribution.objects.create(
        relation=plan,
        name=SENTINEL_CONTRIBUTOR,
        amount=SENTINEL_AMOUNT,
        is_paid=True,
        paid_at=timezone.now(),
    )

    history = build_recipient_history(owner, person)
    payload = build_ai_payload(
        history,
        viewer=owner,
        available_tag_names=["Jeux"],
        avoid_names=[],
        count=3,
        language="en",
    )

    payload_str = str(payload)

    # Positive control: gift appears in history
    assert plan.gift.name in payload_str

    # Sensitive group gift data must not appear in AI payload
    assert SENTINEL_CONTRIBUTOR not in payload_str
    assert "ZqxContributor" not in payload_str
    for amt_str in SENTINEL_AMOUNT_STRS:
        assert amt_str not in payload_str
    assert "group_gift" not in payload_str
    assert "contribution" not in payload_str


def test_group_gift_code_isolation():
    """Verify calendar, reminders, and AI modules never import group gifts or contributions."""
    guarded_files = [
        Path("gift_manager/calendar_feed.py"),
        Path("gift_manager/reminders.py"),
        Path("gift_manager/digest_sending.py"),
        Path("gift_manager/suggestions/ai/prompt.py"),
    ]

    for file_path in guarded_files:
        assert file_path.exists(), f"Guarded module {file_path} must exist"
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "group_gift" not in alias.name, f"{file_path} imports {alias.name}"
                    assert "RelationContribution" not in alias.name, (
                        f"{file_path} imports {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert "group_gift" not in mod, f"{file_path} imports from {mod}"
                for alias in node.names:
                    assert alias.name != "RelationContribution", (
                        f"{file_path} imports RelationContribution"
                    )

    template_files = [
        Path("gift_manager/templates/gift_manager/email/digest.txt"),
        Path("gift_manager/templates/gift_manager/email/digest.html"),
    ]
    for tmpl_path in template_files:
        assert tmpl_path.exists(), f"Guarded template {tmpl_path} must exist"
        content = tmpl_path.read_text(encoding="utf-8").lower()
        assert "contribution" not in content, f"{tmpl_path} mentions contribution"
        assert "group_gift" not in content, f"{tmpl_path} mentions group_gift"


# --- 5. Dynamic Recipient Protection on Account Link -----------------------------------------


def test_link_converts_contributions_to_external_snapshots():
    """Linking person to account converts existing contributions on that person's plans to snapshots."""
    owner = UserFactory()
    bob = UserFactory(username="bob")
    carol = UserFactory(username="carol")
    _befriend(owner, bob)
    _befriend(owner, carol)

    # Person 1 (unlinked initially)
    p1 = PersonFactory(first_name="Bobby", account=None)
    _grant(p1, owner, PermissionLevel.OWNER)

    # Person 2 (different person, unlinked initially)
    p2 = PersonFactory(first_name="Other", account=None)
    _grant(p2, owner, PermissionLevel.OWNER)

    # Plan 1 for Person 1
    rel1 = RelationFactory(person=p1, group=None, price=Decimal("100.00"), is_group_gift=True)
    _grant(rel1, owner, PermissionLevel.OWNER, "relation")

    # Plan 2 for Person 2
    rel2 = RelationFactory(person=p2, group=None, price=Decimal("100.00"), is_group_gift=True)
    _grant(rel2, owner, PermissionLevel.OWNER, "relation")

    # Contributor 1 on rel1 held by bob (to become recipient of p1)
    c1 = RelationContribution.objects.create(
        relation=rel1,
        user=bob,
        name="bob",
        amount=Decimal("40.00"),
        is_paid=True,
        paid_at=timezone.now(),
    )

    # Control 1 on rel1 held by carol
    c2 = RelationContribution.objects.create(
        relation=rel1,
        user=carol,
        name="carol",
        amount=Decimal("60.00"),
        is_paid=False,
    )

    # Control 2 on rel2 held by bob
    c3 = RelationContribution.objects.create(
        relation=rel2,
        user=bob,
        name="bob",
        amount=Decimal("50.00"),
        is_paid=False,
    )

    # Link p1 to bob
    account_links.link(p1, bob, actor=owner)
    p1.refresh_from_db()
    assert p1.account == bob

    # c1 must now be an external snapshot: user=None, name/amount/is_paid preserved
    c1.refresh_from_db()
    assert c1.user is None
    assert c1.name == "bob"
    assert c1.amount == Decimal("40.00")
    assert c1.is_paid is True

    # Controls must remain completely untouched
    c2.refresh_from_db()
    assert c2.user == carol
    assert c2.amount == Decimal("60.00")

    c3.refresh_from_db()
    assert c3.user == bob
    assert c3.amount == Decimal("50.00")


def test_unlink_does_not_restore_contribution_user_links():
    """Unlinking person leaves previously converted contributions as snapshots (user=None)."""
    owner = UserFactory()
    bob = UserFactory(username="bob")
    _befriend(owner, bob)

    person = PersonFactory(account=None)
    _grant(person, owner, PermissionLevel.OWNER)

    relation = RelationFactory(person=person, is_group_gift=True)
    _grant(relation, owner, PermissionLevel.OWNER, "relation")

    contrib = RelationContribution.objects.create(
        relation=relation,
        user=bob,
        name="bob",
        amount=Decimal("25.00"),
    )

    # Link converts to snapshot
    account_links.link(person, bob, actor=owner)
    contrib.refresh_from_db()
    assert contrib.user is None

    # Unlink leaves snapshot as user=None
    account_links.unlink(person, actor=owner)
    person.refresh_from_db()
    assert person.account is None

    contrib.refresh_from_db()
    assert contrib.user is None
    assert contrib.name == "bob"


def test_group_recipient_dynamic_masking_in_summary():
    """get_group_gift_summary masks user name to snapshot and resets is_buyer for recipient rows."""
    alice = UserFactory(username="alice")
    bob = UserFactory(username="bob")
    carol = UserFactory(username="carol")
    _befriend(alice, bob)
    _befriend(alice, carol)

    group = PersonGroupFactory()
    _grant(group, alice, PermissionLevel.OWNER)

    # Bob is member of group
    bob_person = PersonFactory(account=bob)
    bob_person.groups.add(group)

    relation = GroupRelationFactory(
        group=group,
        price=Decimal("100.00"),
        claimed_by=bob,  # Bob claimed plan, but is a non-owner member of recipient group
        claimed_at=timezone.now(),
        is_group_gift=True,
        split_mode=SplitMode.EQUAL,
    )
    _grant(relation, alice, PermissionLevel.OWNER, "relation")
    _grant(relation, carol, PermissionLevel.EDITOR, "relation")
    # Bob has VIEWER, not OWNER
    _grant(relation, bob, PermissionLevel.VIEWER, "relation")

    # Contributor row for Bob with distinctive snapshot name in DB
    contrib_bob = RelationContribution.objects.create(
        relation=relation,
        user=bob,
        name="bob",
        amount=Decimal("50.00"),
    )
    RelationContribution.objects.filter(pk=contrib_bob.pk).update(name="BobSnapshotName")
    contrib_bob.refresh_from_db()

    # Contributor row for Carol (collaborator, not recipient)
    contrib_carol = RelationContribution.objects.create(
        relation=relation,
        user=carol,
        name="CarolSnapshotName",
        amount=Decimal("50.00"),
    )

    # Alice (plan owner) views group gift summary
    summary = group_gifts.get_group_gift_summary(relation, viewer=alice)
    rows_by_id = {r.contribution.pk: r for r in summary.rows}

    # Bob's row is masked because Bob is a recipient of the plan
    bob_row = rows_by_id[contrib_bob.pk]
    assert bob_row.display_name == "BobSnapshotName"
    assert bob_row.is_buyer is False

    # Carol's row is normal
    carol_row = rows_by_id[contrib_carol.pk]
    assert carol_row.display_name == carol.username
    assert carol_row.is_buyer is False
