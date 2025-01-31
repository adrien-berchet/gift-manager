from modeltranslation.translator import TranslationOptions
from modeltranslation.translator import register

from .models import RelationStatus


@register(RelationStatus)
class RelationStatusTranslationOptions(TranslationOptions):
    fields = ("status",)
