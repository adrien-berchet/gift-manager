from django.apps import AppConfig


class GiftManagerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "gift_manager"

    def ready(self):
        import gift_manager.signals  # noqa: F401, PLC0415
