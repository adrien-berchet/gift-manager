from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path

from . import views

app_name = "gift_manager"

urlpatterns = [
    path("", views.home, name="home"),
    path("admin/", admin.site.urls),
    path("persons/", views.PersonListView.as_view(), name="persons"),
    path("persons/create/", views.PersonCreateView.as_view(), name="person_create"),
    path("persons/<uuid:pk>/", views.PersonDetailView.as_view(), name="person_detail"),
    path("persons/<uuid:pk>/edit/", views.PersonUpdateView.as_view(), name="person_edit"),
    path("persons/<uuid:pk>/delete/", views.PersonDeleteView.as_view(), name="person_delete"),
    path(
        "persons/<uuid:pk>/add_relation/",
        views.PersonRelationCreateView.as_view(),
        name="add_person_relation",
    ),
    path("person_groups/", views.PersonGroupListView.as_view(), name="person_groups"),
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
        "person_groups/<uuid:pk>/add_relation/",
        views.PersonGroupRelationCreateView.as_view(),
        name="add_person_group_relation",
    ),
    path(
        "person_groups/<uuid:pk>/remove_person/<uuid:person_id>/",
        views.remove_person_from_group,
        name="remove_person_group_person",
    ),
    path("gifts/", views.GiftListView.as_view(), name="gifts"),
    path("gifts/create/", views.GiftCreateView.as_view(), name="gift_create"),
    path("gifts/<uuid:pk>/", views.GiftDetailView.as_view(), name="gift_detail"),
    path("gifts/<uuid:pk>/edit/", views.GiftUpdateView.as_view(), name="gift_edit"),
    path("gifts/<uuid:pk>/delete/", views.GiftDeleteView.as_view(), name="gift_delete"),
    path(
        "gifts/<uuid:pk>/add_relation/",
        views.GiftRelationCreateView.as_view(),
        name="add_gift_relation",
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
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
