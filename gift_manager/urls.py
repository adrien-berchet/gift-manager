from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path

from . import views

app_name = "gift_manager"

urlpatterns = [
    path("", views.home, name="home"),
    path("api/search/", views.global_search, name="global_search"),
    path("admin/", admin.site.urls),
    path("profile/", views.ProfileDetailView.as_view(), name="profile_detail"),
    path("send-invitation/", views.SendInvitationView.as_view(), name="send_invitation"),
    path(
        "accept-invitation/<uuid:token>/",
        views.AcceptInvitationView.as_view(),
        name="accept_invitation",
    ),
    path(
        "invitation-expired/",
        views.InvitationExpiredView.as_view(),
        name="invitation_expired",
    ),
    path(
        "profile/remove-friend/<int:friend_id>/",
        views.RemoveFriendView.as_view(),
        name="remove_friend",
    ),
    path(
        "profile/update-view-preferences/",
        views.UpdateViewPreferencesView.as_view(),
        name="update_view_preferences",
    ),
    path("persons/", views.PersonListView.as_view(), name="persons"),
    path("persons/create/", views.PersonCreateView.as_view(), name="person_create"),
    path("persons/<uuid:pk>/", views.PersonDetailView.as_view(), name="person_detail"),
    path("persons/<uuid:pk>/edit/", views.PersonUpdateView.as_view(), name="person_edit"),
    path("persons/<uuid:pk>/delete/", views.PersonDeleteView.as_view(), name="person_delete"),
    path(
        "persons/<uuid:pk>/add_relation/",
        views.PersonRelationCreateView.as_view(),
        name="person_relation_create",
    ),
    path("person_groups/", views.PersonGroupListView.as_view(), name="person_groups"),
    path(
        "person_groups/explore/",
        views.PersonGroupExplorerView.as_view(),
        name="person_group_explorer",
    ),
    path(
        "person_groups/explore/<uuid:pk>/",
        views.PersonGroupExplorerView.as_view(),
        name="person_group_explorer_with_group",
    ),
    path(
        "person_groups/create/", views.PersonGroupCreateView.as_view(), name="person_group_create"
    ),
    path(
        "person_groups/<uuid:pk>/",
        views.PersonGroupDetailView.as_view(),
        name="person_group_detail",
    ),
    path(
        "person_groups/<uuid:pk>/edit/",
        views.PersonGroupUpdateView.as_view(),
        name="person_group_edit",
    ),
    path(
        "person_groups/<uuid:pk>/delete/",
        views.PersonGroupDeleteView.as_view(),
        name="person_group_delete",
    ),
    path(
        "person_groups/<uuid:pk>/add_person/",
        views.add_multiple_persons_to_group,
        name="add_person_group_person",
    ),
    path(
        "person_groups/<uuid:pk>/add_child_groups/",
        views.add_multiple_child_groups_to_group,
        name="add_child_groups_to_group",
    ),
    path(
        "person_groups/<uuid:pk>/add_relation/",
        views.PersonGroupRelationCreateView.as_view(),
        name="person_group_relation_create",
    ),
    path(
        "person_groups/<uuid:pk>/remove_person/<uuid:person_id>/",
        views.remove_person_from_group,
        name="remove_person_group_person",
    ),
    path(
        "api/person_groups/reparent/",
        views.reparent_group,
        name="api_reparent_group",
    ),
    path("gifts/", views.GiftListView.as_view(), name="gifts"),
    path("gifts/create/", views.GiftCreateView.as_view(), name="gift_create"),
    path("gifts/<uuid:pk>/", views.GiftDetailView.as_view(), name="gift_detail"),
    path("gifts/<uuid:pk>/edit/", views.GiftUpdateView.as_view(), name="gift_edit"),
    path("gifts/<uuid:pk>/delete/", views.GiftDeleteView.as_view(), name="gift_delete"),
    path(
        "gifts/<uuid:pk>/add_relation/",
        views.GiftRelationCreateView.as_view(),
        name="gift_relation_create",
    ),
    path("gift-tags/", views.GiftTagExplorerView.as_view(), name="gift_tag_explorer"),
    path(
        "gift-tags/<uuid:pk>/",
        views.GiftTagExplorerView.as_view(),
        name="gift_tag_explorer_with_tag",
    ),
    path("gift-tag/create/", views.GiftTagCreateView.as_view(), name="gift_tag_create"),
    path("gift-tag/<uuid:pk>/", views.GiftTagDetailView.as_view(), name="gift_tag_detail"),
    path("gift-tag/<uuid:pk>/edit", views.GiftTagUpdateView.as_view(), name="gift_tag_edit"),
    path("gift-tag/<uuid:pk>/delete", views.GiftTagDeleteView.as_view(), name="gift_tag_delete"),
    path(
        "relations/",
        views.RelationListView.as_view(),
        name="relations",
    ),
    path(
        "relations/create/",
        views.RelationCreateView.as_view(),
        name="relation_create",
    ),
    path(
        "relations/<uuid:pk>/",
        views.RelationDetailView.as_view(),
        name="relation_detail",
    ),
    path(
        "relations/<uuid:pk>/edit/",
        views.RelationUpdateView.as_view(),
        name="relation_edit",
    ),
    path(
        "relations/<uuid:pk>/delete/",
        views.RelationDeleteView.as_view(),
        name="relation_delete",
    ),
    path("events/", views.EventListView.as_view(), name="events"),
    path("events/create/", views.EventCreateView.as_view(), name="event_create"),
    path("events/<uuid:pk>/", views.EventDetailView.as_view(), name="event_detail"),
    path("events/<uuid:pk>/edit/", views.EventUpdateView.as_view(), name="event_edit"),
    path("events/<uuid:pk>/delete/", views.EventDeleteView.as_view(), name="event_delete"),
    path("relation_statuses/", views.RelationStatusListView.as_view(), name="relation_statuses"),
    path(
        "relation_statuses/<int:pk>/",
        views.RelationStatusDetailView.as_view(),
        name="relation_status_detail",
    ),
    path("relation_status_update/", views.update_relation_status, name="relation_status_update"),
    path("share/", views.ShareObjectsView.as_view(), name="share_objects"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
