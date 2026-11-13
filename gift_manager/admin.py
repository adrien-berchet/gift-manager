from django.contrib import admin

from .models import Event
from .models import EventPermission
from .models import Gift
from .models import GiftPermission
from .models import GiftSuggestion
from .models import GiftSuggestionGeneration
from .models import GiftTag
from .models import GiftTagPermission
from .models import Invitation
from .models import Person
from .models import PersonGroup
from .models import PersonGroupPermission
from .models import PersonPermission
from .models import Profile
from .models import ReceivedGift
from .models import Relation
from .models import RelationPermission
from .models import RelationStatus

admin.site.register(Person)
admin.site.register(PersonPermission)
admin.site.register(PersonGroup)
admin.site.register(PersonGroupPermission)
admin.site.register(Profile)
admin.site.register(Invitation)
admin.site.register(GiftTag)
admin.site.register(GiftTagPermission)
admin.site.register(Gift)
admin.site.register(GiftPermission)
admin.site.register(GiftSuggestion)
admin.site.register(GiftSuggestionGeneration)
admin.site.register(EventPermission)
admin.site.register(RelationStatus)
admin.site.register(Relation)
admin.site.register(RelationPermission)


@admin.register(ReceivedGift)
class ReceivedGiftAdmin(admin.ModelAdmin):
    list_display = ("title", "recipient_user", "received_on", "thank_you_sent")
    list_filter = ("thank_you_sent", "received_on")
    search_fields = ("title", "recipient_user__username")
    readonly_fields = [
        "received_gift_id",
        "recipient_user",
        "title",
        "description",
        "url",
        "received_on",
        "event",
        "occasion_text",
        "giver_label",
        "reaction_rating",
        "reaction_note",
        "reaction_shared_at",
        "thank_you_sent",
        "wish",
        "source_relation",
        "source_givers_text",
        "giver_note",
        "created_at",
        "updated_at",
    ]

    def has_add_permission(self, _request):
        return False

    def has_change_permission(self, _request, _obj=None):
        return False


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    """Events; the global Birthday event is shared by every account and stays read-only."""

    def has_change_permission(self, request, obj=None):
        if obj is not None and obj.is_global:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_global:
            return False
        return super().has_delete_permission(request, obj)
