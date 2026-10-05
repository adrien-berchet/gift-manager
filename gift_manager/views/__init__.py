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
from .event import event_plan_again

# Gift views
from .gift import GiftCreateView
from .gift import GiftDeleteView
from .gift import GiftDetailView
from .gift import GiftListView
from .gift import GiftUpdateView

# GiftTag views
from .gift_history import person_gift_history
from .gift_history import person_group_gift_history
from .gift_history import repeat_gift_hint
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

# Recipient views
from .recipient import RecipientListView

# Relation views
from .relation import GiftRelationCreateView
from .relation import GiftRelationDeleteView
from .relation import PersonGroupRelationCreateView
from .relation import PersonRelationCreateView
from .relation import RelationAdvancedListView
from .relation import RelationCreateView
from .relation import RelationDeleteView
from .relation import RelationDetailView
from .relation import RelationListView
from .relation import RelationStatusDetailView
from .relation import RelationStatusListView
from .relation import RelationUpdateView
from .relation import relation_quick_action
from .relation import relation_reaction
from .relation import update_relation_status

# Reminder views
from .reminders import DigestUnsubscribeView
from .reminders import DisableCalendarFeedView
from .reminders import RegenerateCalendarFeedView
from .reminders import UpdateReminderPreferencesView
from .reminders import calendar_feed

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
    "DigestUnsubscribeView",
    "DisableCalendarFeedView",
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
    "RecipientListView",
    "RegenerateCalendarFeedView",
    "RelationAdvancedListView",
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
    "UpdateReminderPreferencesView",
    "UpdateViewPreferencesView",
    "add_multiple_child_groups_to_group",
    "add_multiple_persons_to_group",
    "calendar_feed",
    "event_plan_again",
    "get_user",
    "global_search",
    "home",
    "person_gift_history",
    "person_group_gift_history",
    "relation_quick_action",
    "relation_reaction",
    "remove_person_from_group",
    "reparent_group",
    "repeat_gift_hint",
    "update_relation_status",
]
