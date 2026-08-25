"""Regression tests for GiftTag UUID authorization boundaries."""

import json
import uuid

import pytest
from django.test import override_settings
from django.urls import reverse

from gift_manager.models import Gift
from gift_manager.models import GiftTag
from gift_manager.permissions import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.permissions import get_permission
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import UserFactory


@pytest.mark.django_db
@override_settings(USE_I18N=False)
def test_private_gift_tag_edit_get_and_post_are_inaccessible_by_uuid(authenticated_client, user):
    """A guessed private tag UUID must not expose or mutate the edit form."""
    private_tag = GiftTag.objects.create(name="Secret Tag")
    url = reverse("gift_manager:gift_tag_edit", kwargs={"pk": private_tag.tag_id})

    get_response = authenticated_client.get(url)
    post_response = authenticated_client.post(
        url,
        {
            "name": "Renamed by Stranger",
            "parent_tags": [],
        },
    )

    private_tag.refresh_from_db()
    assert get_response.status_code == 404
    assert post_response.status_code == 404
    assert private_tag.name == "Secret Tag"
    assert get_permission(private_tag, user) == PermissionLevel.NONE


@pytest.mark.django_db
@override_settings(USE_I18N=False)
def test_private_gift_tag_permission_update_does_not_share_by_uuid(authenticated_client, user):
    """Permission HTMX posts must resolve tag access before mutating shares."""
    friend = UserFactory(username="friend", email="friend@example.com")
    user.profile.friends.add(friend.profile)
    private_tag = GiftTag.objects.create(name="Secret Tag")
    url = reverse("gift_manager:gift_tag_edit", kwargs={"pk": private_tag.tag_id})

    response = authenticated_client.post(
        url,
        {
            "user_id": str(friend.id),
            "permission": str(PermissionLevel.VIEWER),
        },
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 404
    assert get_permission(private_tag, friend) == PermissionLevel.NONE
    assert private_tag.shared_with.count() == 0


@pytest.mark.django_db
@override_settings(USE_I18N=False)
def test_public_gift_tag_without_permission_cannot_be_edited_by_uuid(
    authenticated_client,
    user,
):
    """Public visibility alone must not grant edit permission."""
    public_tag = GiftTag.objects.create(name="Public Tag", is_public=True)
    url = reverse("gift_manager:gift_tag_edit", kwargs={"pk": public_tag.tag_id})

    get_response = authenticated_client.get(url)
    post_response = authenticated_client.post(
        url,
        {
            "name": "Renamed Public Tag",
            "parent_tags": [],
        },
    )

    public_tag.refresh_from_db()
    assert get_response.status_code == 403
    assert post_response.status_code == 403
    assert public_tag.name == "Public Tag"
    assert get_permission(public_tag, user) == PermissionLevel.NONE


@pytest.mark.django_db
@override_settings(USE_I18N=False)
def test_private_gift_tag_delete_is_inaccessible_by_uuid(authenticated_client):
    """A guessed private tag UUID must not open confirmation or delete the tag."""
    private_tag = GiftTag.objects.create(name="Secret Tag")
    url = reverse("gift_manager:gift_tag_delete", kwargs={"pk": private_tag.tag_id})

    get_response = authenticated_client.get(url)
    post_response = authenticated_client.post(url)

    assert get_response.status_code == 404
    assert post_response.status_code == 404
    assert GiftTag.objects.filter(pk=private_tag.pk, name="Secret Tag").exists()


@pytest.mark.django_db
@override_settings(USE_I18N=False)
def test_public_gift_tag_without_permission_cannot_be_deleted_by_uuid(
    authenticated_client,
    user,
):
    """Public tags are readable but not deletable without explicit permission."""
    public_tag = GiftTag.objects.create(name="Public Tag", is_public=True)
    url = reverse("gift_manager:gift_tag_delete", kwargs={"pk": public_tag.tag_id})

    get_response = authenticated_client.get(url)
    post_response = authenticated_client.post(url)

    assert get_response.status_code == 403
    assert post_response.status_code == 403
    assert GiftTag.objects.filter(pk=public_tag.pk, name="Public Tag").exists()
    assert get_permission(public_tag, user) == PermissionLevel.NONE


@pytest.mark.django_db
@override_settings(USE_I18N=False)
def test_explicit_editor_can_delete_unshared_gift_tag(authenticated_client, user):
    """Editor permission remains sufficient for the existing hard-delete flow."""
    tag = GiftTag.objects.create(name="Editable Tag")
    create_or_update_permission(user, tag, permission_level=PermissionLevel.EDITOR)
    url = reverse("gift_manager:gift_tag_delete", kwargs={"pk": tag.tag_id})

    response = authenticated_client.post(url)

    assert response.status_code == 302
    assert not GiftTag.objects.filter(pk=tag.pk).exists()


@pytest.mark.django_db
@override_settings(USE_I18N=False)
def test_gift_create_rejects_forged_private_tag_choice(authenticated_client):
    """Gift forms must reject private tag primary keys outside the filtered queryset."""
    private_tag = GiftTag.objects.create(name="Secret Tag")

    response = authenticated_client.post(
        reverse("gift_manager:gift_create"),
        {
            "name": "Forged Tagged Gift",
            "comment": "",
            "tags": [str(private_tag.pk)],
        },
    )

    assert response.status_code == 200
    assert "tags" in response.context["form"].errors
    assert not Gift.objects.filter(name="Forged Tagged Gift").exists()


@pytest.mark.django_db
@override_settings(USE_I18N=False)
def test_gift_update_rejects_forged_private_tag_choice(authenticated_client, user):
    """Gift edit forms must not accept inaccessible tag IDs on POST."""
    gift = Gift.objects.create(name="Owned Gift", comment="")
    private_tag = GiftTag.objects.create(name="Secret Tag")
    create_or_update_permission(user, gift, permission_level=PermissionLevel.OWNER)
    url = reverse("gift_manager:gift_edit", kwargs={"pk": gift.gift_id})

    response = authenticated_client.post(
        url,
        {
            "name": "Owned Gift",
            "comment": "",
            "tags": [str(private_tag.pk)],
        },
    )

    gift.refresh_from_db()
    assert response.status_code == 200
    assert "tags" in response.context["form"].errors
    assert gift.tags.count() == 0


@pytest.mark.django_db
@override_settings(USE_I18N=False)
def test_gift_tag_detail_usage_stats_exclude_inaccessible_descendant_gifts(
    authenticated_client,
    user,
):
    """Tag hierarchy usage stats must not count inaccessible gifts under hidden child tags."""
    parent_tag = GiftTag.objects.create(name="Public Tag", is_public=True)
    hidden_child = GiftTag.objects.create(name="Hidden Child")
    hidden_child.parent_tags.add(parent_tag)
    inaccessible_gift = GiftFactory(name="Private tagged gift")
    inaccessible_gift.tags.add(hidden_child)

    response = authenticated_client.get(
        reverse("gift_manager:gift_tag_detail", kwargs={"pk": parent_tag.tag_id})
    )

    assert response.status_code == 200
    assert response.context["usage_stats"]["direct_gifts"] == 0
    assert response.context["usage_stats"]["total_gifts"] == 0
    assert response.context["usage_stats"]["child_tags"] == 0


@pytest.mark.django_db
@override_settings(USE_I18N=False)
def test_gift_tag_detail_deduplicates_public_parent_with_multiple_permissions(
    authenticated_client,
    user,
):
    """A public parent tag must appear once regardless of its permission rows."""
    friend = UserFactory(username="friend", email="friend@example.com")
    parent_tag = GiftTag.objects.create(name="Public Parent", is_public=True)
    child_tag = GiftTag.objects.create(name="Public Child", is_public=True)
    child_tag.parent_tags.add(parent_tag)
    create_or_update_permission(user, parent_tag, permission_level=PermissionLevel.OWNER)
    create_or_update_permission(friend, parent_tag, permission_level=PermissionLevel.VIEWER)

    response = authenticated_client.get(
        reverse("gift_manager:gift_tag_detail", kwargs={"pk": child_tag.tag_id})
    )

    assert response.status_code == 200
    assert list(response.context["parent_tags"]) == [parent_tag]


@pytest.mark.django_db
@override_settings(USE_I18N=False)
def test_gift_tag_create_rejects_forged_private_parent_tag_choice(authenticated_client):
    """Tag forms must reject private parent tag IDs outside the filtered queryset."""
    private_parent = GiftTag.objects.create(name="Secret Parent")

    response = authenticated_client.post(
        reverse("gift_manager:gift_tag_create"),
        {
            "name": "Forged Child",
            "parent_tags": [str(private_parent.pk)],
        },
    )

    assert response.status_code == 200
    assert "parent_tags" in response.context["form"].errors
    assert not GiftTag.objects.filter(name="Forged Child").exists()


@pytest.mark.django_db
@override_settings(USE_I18N=False)
def test_gift_tag_update_rejects_forged_private_parent_tag_choice(
    authenticated_client,
    user,
):
    """Tag edit forms must not accept inaccessible parent tag IDs on POST."""
    tag = GiftTag.objects.create(name="Owned Tag")
    private_parent = GiftTag.objects.create(name="Secret Parent")
    create_or_update_permission(user, tag, permission_level=PermissionLevel.OWNER)
    url = reverse("gift_manager:gift_tag_edit", kwargs={"pk": tag.tag_id})

    response = authenticated_client.post(
        url,
        {
            "name": "Owned Tag",
            "parent_tags": [str(private_parent.pk)],
        },
    )

    tag.refresh_from_db()
    assert response.status_code == 200
    assert "parent_tags" in response.context["form"].errors
    assert tag.parent_tags.count() == 0


@pytest.mark.django_db
@override_settings(USE_I18N=False)
def test_explorer_does_not_store_or_render_private_from_tag(authenticated_client):
    """Forged breadcrumb referrers must not leak private tag names."""
    private_parent = GiftTag.objects.create(name="Secret Parent")
    public_child = GiftTag.objects.create(name="Public Child", is_public=True)
    public_child.parent_tags.add(private_parent)
    url = reverse("gift_manager:gift_tag_explorer_with_tag", kwargs={"pk": public_child.tag_id})

    response = authenticated_client.get(f"{url}?from_tag={private_parent.tag_id}")

    assert response.status_code == 200
    assert b"Secret Parent" not in response.content
    assert str(public_child.tag_id) not in authenticated_client.session.get(
        "tag_navigation_history",
        {},
    )


@pytest.mark.django_db
@override_settings(USE_I18N=False)
def test_explorer_deduplicates_public_related_tags_with_multiple_permissions(
    authenticated_client,
    user,
):
    """Public parent and child tags must each appear once in explorer context."""
    friend = UserFactory(username="friend", email="friend@example.com")
    parent_tag = GiftTag.objects.create(name="Public Parent", is_public=True)
    selected_tag = GiftTag.objects.create(name="Public Selected", is_public=True)
    child_tag = GiftTag.objects.create(name="Public Child", is_public=True)
    selected_tag.parent_tags.add(parent_tag)
    child_tag.parent_tags.add(selected_tag)
    for related_tag in (parent_tag, child_tag):
        create_or_update_permission(user, related_tag, permission_level=PermissionLevel.OWNER)
        create_or_update_permission(friend, related_tag, permission_level=PermissionLevel.VIEWER)

    response = authenticated_client.get(
        reverse("gift_manager:gift_tag_explorer_with_tag", kwargs={"pk": selected_tag.tag_id})
    )

    assert response.status_code == 200
    assert list(response.context["parent_tags"]) == [parent_tag]
    assert list(response.context["child_tags"]) == [child_tag]


@pytest.mark.django_db
@override_settings(USE_I18N=False)
def test_explorer_prunes_private_from_tag_already_in_session(authenticated_client):
    """Previously stored private breadcrumb references must not keep leaking attempts alive."""
    private_parent = GiftTag.objects.create(name="Secret Parent")
    public_child = GiftTag.objects.create(name="Public Child", is_public=True)
    public_child.parent_tags.add(private_parent)
    session = authenticated_client.session
    session["tag_navigation_history"] = {
        str(public_child.tag_id): str(private_parent.tag_id),
    }
    session.save()

    response = authenticated_client.get(
        reverse("gift_manager:gift_tag_explorer_with_tag", kwargs={"pk": public_child.tag_id})
    )

    assert response.status_code == 200
    assert b"Secret Parent" not in response.content
    assert str(public_child.tag_id) not in authenticated_client.session.get(
        "tag_navigation_history",
        {},
    )


@pytest.mark.django_db
@override_settings(USE_I18N=False)
def test_detail_hides_private_ancestors_and_inaccessible_descendant_gift_counts(
    authenticated_client,
    user,
):
    """Public tag detail stats and breadcrumbs must only use accessible tags/gifts."""
    private_parent = GiftTag.objects.create(name="Secret Parent")
    public_child = GiftTag.objects.create(name="Public Child", is_public=True)
    private_descendant = GiftTag.objects.create(name="Secret Descendant")
    public_child.parent_tags.add(private_parent)
    private_descendant.parent_tags.add(public_child)

    visible_gift = Gift.objects.create(name="Visible Gift", comment="")
    hidden_gift = Gift.objects.create(name="Hidden Gift", comment="")
    visible_gift.tags.add(public_child)
    hidden_gift.tags.add(private_descendant)
    create_or_update_permission(user, visible_gift, permission_level=PermissionLevel.OWNER)

    response = authenticated_client.get(
        reverse("gift_manager:gift_tag_detail", kwargs={"pk": public_child.tag_id})
    )

    assert response.status_code == 200
    assert b"Secret Parent" not in response.content
    assert b"Secret Descendant" not in response.content
    assert b"Hidden Gift" not in response.content
    assert response.context["ancestors_path"] == []
    assert response.context["usage_stats"]["direct_gifts"] == 1
    assert response.context["usage_stats"]["total_gifts"] == 1


@pytest.mark.django_db
@override_settings(USE_I18N=False)
def test_inline_gift_tag_update_private_uuid_returns_not_found(authenticated_client):
    """Inline edits must not update or expose inaccessible private tags."""
    private_tag = GiftTag.objects.create(name="Secret Tag")
    url = reverse("gift_manager:gift_tag_inline_update", kwargs={"pk": private_tag.tag_id})

    response = authenticated_client.post(
        url,
        data=json.dumps({"field": "name", "value": "Renamed"}),
        content_type="application/json",
    )

    private_tag.refresh_from_db()
    assert response.status_code == 404
    assert response.json()["success"] is False
    assert private_tag.name == "Secret Tag"


@pytest.mark.django_db
@override_settings(USE_I18N=False)
def test_inline_gift_tag_update_public_without_permission_is_denied(authenticated_client):
    """Public visibility must not be enough for inline editing."""
    public_tag = GiftTag.objects.create(name="Public Tag", is_public=True)
    url = reverse("gift_manager:gift_tag_inline_update", kwargs={"pk": public_tag.tag_id})

    response = authenticated_client.post(
        url,
        data=json.dumps({"field": "name", "value": "Renamed"}),
        content_type="application/json",
    )

    public_tag.refresh_from_db()
    assert response.status_code == 403
    assert response.json()["success"] is False
    assert public_tag.name == "Public Tag"


@pytest.mark.django_db
@override_settings(USE_I18N=False)
def test_inline_gift_tag_update_missing_uuid_returns_not_found(authenticated_client):
    """Missing inline UUIDs should not fall through to a generic server error."""
    url = reverse("gift_manager:gift_tag_inline_update", kwargs={"pk": uuid.uuid4()})

    response = authenticated_client.post(
        url,
        data=json.dumps({"field": "name", "value": "Renamed"}),
        content_type="application/json",
    )

    assert response.status_code == 404
    assert response.json()["success"] is False
