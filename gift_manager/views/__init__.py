"""Views module - exports all views for backward compatibility."""

# Common utilities
# Base classes (not typically imported directly, but available if needed)
from .base import BaseCreateView
from .base import BaseDeleteView
from .base import BaseDetailView
from .base import BaseListView
from .base import BaseUpdateView
from .base import CancelToPreviousMixin
from .base import ContextPermissionMixin
from .base import CreatePermissionMixin
from .base import DeleteSharedMixin
from .base import EditPermissionMixin
from .base import FilterByUserMixin
from .base import GetObjectByTokenMixin
from .base import SharedUsersMixin
from .common import get_user
from .common import global_search
from .common import home

# Event views
from .event import EventCreateView
from .event import EventDeleteView
from .event import EventDetailView
from .event import EventListView
from .event import EventUpdateView

# Gift views
from .gift import GiftCreateView
from .gift import GiftDeleteView
from .gift import GiftDetailView
from .gift import GiftListView
from .gift import GiftUpdateView

# GiftTag views
from .gift_tag import GiftTagCreateView
from .gift_tag import GiftTagDeleteView
from .gift_tag import GiftTagDetailView
from .gift_tag import GiftTagExplorerView
from .gift_tag import GiftTagListView
from .gift_tag import GiftTagUpdateView

# Person views
from .person import PersonCreateView
from .person import PersonDeleteView
from .person import PersonDetailView
from .person import PersonListView
from .person import PersonUpdateView

# PersonGroup views
from .person_group import PersonGroupCreateView
from .person_group import PersonGroupDeleteView
from .person_group import PersonGroupDetailView
from .person_group import PersonGroupExplorerView
from .person_group import PersonGroupListView
from .person_group import PersonGroupUpdateView
from .person_group import add_multiple_child_groups_to_group
from .person_group import add_multiple_persons_to_group
from .person_group import remove_person_from_group
from .person_group import reparent_group

# Profile views
from .profile import AcceptInvitationView
from .profile import InvitationExpiredView
from .profile import ProfileDetailView
from .profile import RemoveFriendView
from .profile import SendInvitationView
from .profile import UpdateViewPreferencesView

# Relation views
from .relation import GiftRelationCreateView
from .relation import GiftRelationDeleteView
from .relation import PersonGroupRelationCreateView
from .relation import PersonRelationCreateView
from .relation import RelationCreateView
from .relation import RelationDeleteView
from .relation import RelationDetailView
from .relation import RelationListView
from .relation import RelationStatusDetailView
from .relation import RelationStatusListView
from .relation import RelationUpdateView
from .relation import update_relation_status

# Sharing views
from .sharing import ShareObjectsView

__all__ = [
    "AcceptInvitationView",
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
    "EventCreateView",
    "EventDeleteView",
    "EventDetailView",
    "EventListView",
    "EventUpdateView",
    "FilterByUserMixin",
    "GetObjectByTokenMixin",
    "GiftCreateView",
    "GiftDeleteView",
    "GiftDetailView",
    "GiftListView",
    "GiftRelationCreateView",
    "GiftRelationDeleteView",
    "GiftTagCreateView",
    "GiftTagDeleteView",
    "GiftTagDetailView",
    "GiftTagExplorerView",
    "GiftTagListView",
    "GiftTagUpdateView",
    "GiftUpdateView",
    "InvitationExpiredView",
    "PersonCreateView",
    "PersonDeleteView",
    "PersonDetailView",
    "PersonGroupCreateView",
    "PersonGroupDeleteView",
    "PersonGroupDetailView",
    "PersonGroupExplorerView",
    "PersonGroupListView",
    "PersonGroupRelationCreateView",
    "PersonGroupUpdateView",
    "PersonListView",
    "PersonRelationCreateView",
    "PersonUpdateView",
    "ProfileDetailView",
    "RelationCreateView",
    "RelationDeleteView",
    "RelationDetailView",
    "RelationListView",
    "RelationStatusDetailView",
    "RelationStatusListView",
    "RelationUpdateView",
    "RemoveFriendView",
    "SendInvitationView",
    "ShareObjectsView",
    "SharedUsersMixin",
    "UpdateViewPreferencesView",
    "add_multiple_child_groups_to_group",
    "add_multiple_persons_to_group",
    "get_user",
    "global_search",
    "home",
    "remove_person_from_group",
    "reparent_group",
    "update_relation_status",
]
