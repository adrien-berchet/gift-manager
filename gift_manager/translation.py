from modeltranslation.translator import register, TranslationOptions
from .models import RelationStatus

@register(RelationStatus)
class RelationStatusTranslationOptions(TranslationOptions):
    fields = ('status',)
