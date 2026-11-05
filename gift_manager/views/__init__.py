"""Views module - exports all views for backward compatibility."""

# Common utilities
# Base classes (not typically imported directly, but available if needed)
from .account_links import FriendLinkPersonView
from .account_links import PersonDismissLinkSuggestionView
from .account_links import PersonLinkAccountView
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
from .group_gifts import relation_group_gift_contributor_add
from .group_gifts import relation_group_gift_contributor_amount
from .group_gifts import relation_group_gift_contributor_remove
from .group_gifts import relation_group_gift_contributor_toggle_paid
from .group_gifts import relation_group_gift_mode
from .group_gifts import relation_group_gift_toggle
from .i18n import set_language
from .i18n import translate_url_safe

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
from .plan_coordination import relation_claim
from .plan_coordination import relation_comment_add
from .plan_coordination import relation_comment_delete
from .plan_coordination import relation_release

# Profile views
from .profile import AcceptInvitationView
from .profile import CancelInvitationView
from .profile import ConfirmRemoveFriendView
from .profile import InvitationExpiredView
from .profile import ProfileDetailView
from .profile import RemoveFriendView
from .profile import SendInvitationView
from .profile import UpdateProfilePreferencesView
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
from .relation import relation_quick_action_undo
from .relation import relation_reaction
from .relation import surprise_default_hint
from .relation import update_relation_status
from .relation_guided import RelationGuidedCreateView

# Reminder views
from .reminders import DigestUnsubscribeView
from .reminders import DisableCalendarFeedView
from .reminders import RegenerateCalendarFeedView
from .reminders import UpdateReminderPreferencesView
from .reminders import calendar_feed

# Sharing views
from .sharing import ShareObjectsView

# Suggestions views
from .suggestions import dismissed_url_for
from .suggestions import ideas_url_for
from .suggestions import person_group_suggestion_accept
from .suggestions import person_group_suggestion_dismiss
from .suggestions import person_group_suggestion_ideas
from .suggestions import person_group_suggestion_purge
from .suggestions import person_group_suggestion_restore
from .suggestions import person_group_suggestions
from .suggestions import person_group_suggestions_dismissed
from .suggestions import person_suggestion_accept
from .suggestions import person_suggestion_dismiss
from .suggestions import person_suggestion_ideas
from .suggestions import person_suggestion_purge
from .suggestions import person_suggestion_restore
from .suggestions import person_suggestions
from .suggestions import person_suggestions_dismissed
from .suggestions import purge_url_for
from .suggestions import restore_url_for
from .suggestions import suggestions_url_for

# Wishlist views
from .wishlist import WishArchiveView
from .wishlist import WishClaimToggleView
from .wishlist import WishCreateView
from .wishlist import WishDeleteView
from .wishlist import WishListView
from .wishlist import WishPlanView
from .wishlist import WishUpdateView

__all__ = [
    "AcceptInvitationView",
    "BaseCreateView",
    "BaseDeleteView",
    "BaseDetailView",
    "BaseListView",
    "BaseUpdateView",
    "CancelInvitationView",
    "CancelToPreviousMixin",
    "ConfirmRemoveFriendView",
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
    "FriendLinkPersonView",
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
    "PersonDismissLinkSuggestionView",
    "PersonGroupCreateView",
    "PersonGroupDeleteView",
    "PersonGroupDetailView",
    "PersonGroupExplorerView",
    "PersonGroupListView",
    "PersonGroupRelationCreateView",
    "PersonGroupUpdateView",
    "PersonLinkAccountView",
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
    "RelationGuidedCreateView",
    "RelationListView",
    "RelationStatusDetailView",
    "RelationStatusListView",
    "RelationUpdateView",
    "RemoveFriendView",
    "SendInvitationView",
    "ShareObjectsView",
    "SharedUsersMixin",
    "UpdateProfilePreferencesView",
    "UpdateReminderPreferencesView",
    "UpdateViewPreferencesView",
    "WishArchiveView",
    "WishClaimToggleView",
    "WishCreateView",
    "WishDeleteView",
    "WishListView",
    "WishPlanView",
    "WishUpdateView",
    "add_multiple_child_groups_to_group",
    "add_multiple_persons_to_group",
    "calendar_feed",
    "dismissed_url_for",
    "event_plan_again",
    "get_user",
    "global_search",
    "home",
    "ideas_url_for",
    "person_gift_history",
    "person_group_gift_history",
    "person_group_suggestion_accept",
    "person_group_suggestion_dismiss",
    "person_group_suggestion_ideas",
    "person_group_suggestion_purge",
    "person_group_suggestion_restore",
    "person_group_suggestions",
    "person_group_suggestions_dismissed",
    "person_suggestion_accept",
    "person_suggestion_dismiss",
    "person_suggestion_ideas",
    "person_suggestion_purge",
    "person_suggestion_restore",
    "person_suggestions",
    "person_suggestions_dismissed",
    "purge_url_for",
    "relation_claim",
    "relation_comment_add",
    "relation_comment_delete",
    "relation_group_gift_contributor_add",
    "relation_group_gift_contributor_amount",
    "relation_group_gift_contributor_remove",
    "relation_group_gift_contributor_toggle_paid",
    "relation_group_gift_mode",
    "relation_group_gift_toggle",
    "relation_quick_action",
    "relation_quick_action_undo",
    "relation_reaction",
    "relation_release",
    "remove_person_from_group",
    "reparent_group",
    "repeat_gift_hint",
    "restore_url_for",
    "set_language",
    "suggestions_url_for",
    "surprise_default_hint",
    "translate_url_safe",
    "update_relation_status",
]
