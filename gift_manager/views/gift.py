"""Gift-related views."""

from django.contrib.postgres.aggregates import JSONBAgg
from django.db.models import Case
from django.db.models import F
from django.db.models import Func
from django.db.models import IntegerField
from django.db.models import Q
from django.db.models import Value
from django.db.models import When
from django.urls import reverse_lazy
from django.utils.translation import gettext

from gift_manager.forms import GiftForm
from gift_manager.models import Gift
from gift_manager.models import GiftTag
from gift_manager.models import Relation
from gift_manager.models import RelationStatus
from gift_manager.views.base import BaseCreateView
from gift_manager.views.base import BaseDeleteView
from gift_manager.views.base import BaseDetailView
from gift_manager.views.base import BaseListView
from gift_manager.views.base import BaseUpdateView


class GiftListView(BaseListView):
    model = Gift
    template_name = "gift_manager/gift_list.html"
    object_type = "Gifts"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.column_names = {
            "name": gettext("Gift name"),
            "comment": gettext("Comment"),
            "tags": gettext("Tags"),
        }

    def get_queryset(self):
        """Return Gifts for the current user or shared with the user."""
        return (
            Gift.objects.accessible_by(self.request.user)
            .annotate(
                tags_info=JSONBAgg(
                    Func(
                        Value("id"),
                        F("tags__tag_id"),
                        Value("name"),
                        F("tags__name"),
                        function="jsonb_build_object",
                    ),
                    filter=Q(tags__tag_id__isnull=False),
                    distinct=True,
                ),
            )
            .values("gift_id", "name", "comment", "tags_info")
        )


class GiftCreateView(BaseCreateView):
    model = Gift
    form_class = GiftForm
    success_url = reverse_lazy("gift_manager:gifts")
    context_object_name = "gift"
    object_type = "Gift"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["tags"].queryset = GiftTag.objects.accessible_by(self.request.user).order_by(
            "name"
        )
        return form


class GiftUpdateView(BaseUpdateView):
    model = Gift
    form_class = GiftForm
    pk_name = "gift_id"
    context_object_name = "gift"
    object_type = "Gift"
    detail_url_name = "gift_detail"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["tags"].queryset = GiftTag.objects.accessible_by(self.request.user).order_by(
            "name"
        )
        return form


class GiftDeleteView(BaseDeleteView):
    model = Gift
    success_url = reverse_lazy("gift_manager:gifts")
    pk_name = "gift_id"
    object_type = "gift"


class GiftDetailView(BaseDetailView):
    model = Gift
    template_name = "gift_manager/gift_detail.html"
    context_object_name = "gift"
    pk_name = "gift_id"

    def get_context_data(self, **kwargs) -> dict:
        context = super().get_context_data(**kwargs)
        context["relations"] = (
            Relation.objects.accessible_by(self.request.user)
            .filter(gift=self.object)
            .select_related("status", "person", "group", "event")
            .annotate(
                status_order=Case(
                    When(status__status__iexact="idea", then=Value(0)),
                    When(status__status__iexact="to buy", then=Value(1)),
                    When(status__status__iexact="bought", then=Value(2)),
                    When(status__status__iexact="given", then=Value(3)),
                    default=Value(99),
                    output_field=IntegerField(),
                )
            )
            .order_by("status_order", "status__status")
        )
        context["relation_statuses"] = RelationStatus.objects.all()
        context["shared_with"] = self.object.shared_with.exclude(id=self.request.user.id)
        return context
