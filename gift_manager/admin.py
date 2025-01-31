from django.contrib import admin

# from .models import PersonsGroupRelation
from .models import Event
from .models import EventPermission
from .models import Gift
from .models import GiftPermission
from .models import GiftTag
from .models import GiftTagPermission
from .models import Person
from .models import PersonGroup
from .models import PersonGroupPermission
from .models import PersonPermission
from .models import Relation
from .models import RelationPermission
from .models import RelationStatus

admin.site.register(Person)
admin.site.register(PersonPermission)
admin.site.register(PersonGroup)
admin.site.register(PersonGroupPermission)
# admin.site.register(PersonsGroupRelation)
admin.site.register(GiftTag)
admin.site.register(GiftTagPermission)
admin.site.register(Gift)
admin.site.register(GiftPermission)
admin.site.register(Event)
admin.site.register(EventPermission)
admin.site.register(RelationStatus)
admin.site.register(Relation)
admin.site.register(RelationPermission)
