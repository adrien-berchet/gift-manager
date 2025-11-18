"""Views module - exports all views for backward compatibility."""

# Common utilities
from .common import get_user, home

# Base classes (not typically imported directly, but available if needed)
from .base import (
    BaseCreateView,
    BaseDeleteView,
    BaseDetailView,
    BaseListView,
    BaseUpdateView,
    CancelToPreviousMixin,
    ContextPermissionMixin,
    CreatePermissionMixin,
    DeleteSharedMixin,
    EditPermissionMixin,
    FilterByUserMixin,
    GetObjectByTokenMixin,
    SharedUsersMixin,
)

# Profile views
from .profile import (
    AcceptInvitationView,
    InvitationExpiredView,
    ProfileDetailView,
    RemoveFriendView,
    SendInvitationView,
)

# Person views
from .person import (
    PersonCreateView,
    PersonDeleteView,
    PersonDetailView,
    PersonListView,
    PersonUpdateView,
)

# PersonGroup views
from .person_group import (
    PersonGroupCreateView,
    PersonGroupDeleteView,
    PersonGroupDetailView,
    PersonGroupListView,
    PersonGroupUpdateView,
    add_multiple_persons_to_group,
    remove_person_from_group,
)

# Gift views
from .gift import (
    GiftCreateView,
    GiftDeleteView,
    GiftDetailView,
    GiftListView,
    GiftUpdateView,
)

# Event views
from .event import (
    EventCreateView,
    EventDeleteView,
    EventDetailView,
    EventListView,
    EventUpdateView,
)

# Relation views
from .relation import (
    GiftRelationCreateView,
    GiftRelationDeleteView,
    PersonGroupRelationCreateView,
    PersonRelationCreateView,
    RelationCreateView,
    RelationDeleteView,
    RelationDetailView,
    RelationListView,
    RelationStatusDetailView,
    RelationStatusListView,
    RelationUpdateView,
    update_relation_status,
)

# Sharing views
from .sharing import ShareObjectsView

# GiftTag views
from .gift_tag import (
    GiftTagCreateView,
    GiftTagDeleteView,
    GiftTagDetailView,
    GiftTagExplorerView,
    GiftTagListView,
    GiftTagUpdateView,
)

__all__ = [
    # Common utilities
    "get_user",
    "home",
    # Base classes
    "BaseCreateView",
    "BaseDeleteView",
    "BaseDetailView",
    "BaseListView",
    "BaseUpdateView",
    "CancelToPreviousMixin",
    "ContextPermissionMixin",
    "CreatePermissionMixin",
    "DeleteSharedMixin",
    "EditPermissionMixin",
    "FilterByUserMixin",
    "GetObjectByTokenMixin",
    "SharedUsersMixin",
    # Profile views
    "AcceptInvitationView",
    "InvitationExpiredView",
    "ProfileDetailView",
    "RemoveFriendView",
    "SendInvitationView",
    # Person views
    "PersonCreateView",
    "PersonDeleteView",
    "PersonDetailView",
    "PersonListView",
    "PersonUpdateView",
    # PersonGroup views
    "PersonGroupCreateView",
    "PersonGroupDeleteView",
    "PersonGroupDetailView",
    "PersonGroupListView",
    "PersonGroupUpdateView",
    "add_multiple_persons_to_group",
    "remove_person_from_group",
    # Gift views
    "GiftCreateView",
    "GiftDeleteView",
    "GiftDetailView",
    "GiftListView",
    "GiftUpdateView",
    # Event views
    "EventCreateView",
    "EventDeleteView",
    "EventDetailView",
    "EventListView",
    "EventUpdateView",
    # Relation views
    "GiftRelationCreateView",
    "GiftRelationDeleteView",
    "PersonGroupRelationCreateView",
    "PersonRelationCreateView",
    "RelationCreateView",
    "RelationDeleteView",
    "RelationDetailView",
    "RelationListView",
    "RelationStatusDetailView",
    "RelationStatusListView",
    "RelationUpdateView",
    "update_relation_status",
    # Sharing views
    "ShareObjectsView",
    # GiftTag views
    "GiftTagCreateView",
    "GiftTagDeleteView",
    "GiftTagDetailView",
    "GiftTagExplorerView",
    "GiftTagListView",
    "GiftTagUpdateView",
]
