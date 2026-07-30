"""GiftTag-related views."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Prefetch
from django.db.models import Q
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils.translation import gettext
from django.views.generic import View

from gift_manager.forms import GiftTagForm
from gift_manager.mixins.permissions import PermissionUpdateMixin
from gift_manager.models import Gift
from gift_manager.models import GiftTag
from gift_manager.views.base import BaseCreateView
from gift_manager.views.base import BaseDeleteView
from gift_manager.views.base import BaseDetailView
from gift_manager.views.base import BaseListView
from gift_manager.views.base import BaseUpdateView


class GiftTagExplorerView(LoginRequiredMixin, View):
    """View for exploring gifts by hierarchical tags."""

    template_name = "gift_manager/gift_tag_explorer.html"

    def _get_accessible_related_referring_tag(
        self,
        user,
        selected_tag,
        referring_tag_id,
    ) -> GiftTag | None:
        """Return an accessible breadcrumb referrer when it is related to selected_tag."""
        try:
            referring_tag = GiftTag.objects.accessible_by(user).get(tag_id=referring_tag_id)
        except (DjangoValidationError, GiftTag.DoesNotExist, ValueError):
            return None

        is_parent = selected_tag.parent_tags.filter(pk=referring_tag.pk).exists()
        is_child = selected_tag.child_tags.filter(pk=referring_tag.pk).exists()
        if not is_parent and not is_child:
            return None

        return referring_tag

    def get(self, request, *args, **kwargs):
        # Get the selected tag (or None for the root level)
        selected_tag_id = kwargs.get("pk")
        accessible_tags = GiftTag.objects.accessible_by(request.user).prefetch_related(
            "parent_tags", "child_tags"
        )

        # Context to be sent to the template
        context = {
            "selected_tag": None,
            "root_tags": [],
            "parent_tags": [],
            "child_tags": [],
            "gifts": [],
            "breadcrumbs": [],
        }

        # Initialize the navigation history in session if it doesn't exist
        if "tag_navigation_history" not in request.session:
            request.session["tag_navigation_history"] = {}

        navigation_history = request.session["tag_navigation_history"]

        # If a tag is selected, retrieve it
        if selected_tag_id:
            try:
                # Prefetch related tags to optimize hierarchy traversal
                selected_tag = accessible_tags.get(tag_id=selected_tag_id)

                context["selected_tag"] = selected_tag

                # Get the source/referring tag if present in the query string
                referring_tag_id = request.GET.get("from_tag")
                if referring_tag_id:
                    referring_tag = self._get_accessible_related_referring_tag(
                        request.user,
                        selected_tag,
                        referring_tag_id,
                    )
                    current_tag_key = str(selected_tag_id)
                    if referring_tag:
                        # Store the relationship: current tag came from this referring tag
                        navigation_history[current_tag_key] = str(referring_tag.tag_id)
                        request.session.modified = True
                    elif current_tag_key in navigation_history:
                        navigation_history.pop(current_tag_key, None)
                        request.session.modified = True

                # Build the breadcrumbs based on navigation history
                breadcrumbs = []
                current_tag_id = str(selected_tag_id)
                visited = set()  # To prevent infinite loops

                while current_tag_id and current_tag_id not in visited:
                    visited.add(current_tag_id)
                    try:
                        tag = accessible_tags.get(tag_id=current_tag_id)
                        breadcrumbs.insert(0, tag)
                        # Move to parent in the navigation history
                        current_tag_id = navigation_history.get(current_tag_id)
                    except (DjangoValidationError, GiftTag.DoesNotExist, ValueError):
                        for tag_key, previous_tag_id in list(navigation_history.items()):
                            if current_tag_id in (tag_key, previous_tag_id):
                                navigation_history.pop(tag_key, None)
                        request.session.modified = True
                        break

                context["breadcrumbs"] = breadcrumbs

                # Rest of your existing code...
                # Get parent tags, child tags, gifts, etc.
                context["parent_tags"] = selected_tag.parent_tags.filter(
                    Q(is_public=True) | Q(shared_with=request.user)
                ).order_by("name")

                context["child_tags"] = selected_tag.child_tags.filter(
                    Q(is_public=True) | Q(shared_with=request.user)
                ).order_by("name")

                # Get the gifts associated with the selected tag
                accessible_tag_ids = set(
                    GiftTag.objects.accessible_by(request.user).values_list("pk", flat=True)
                )
                descendants = [
                    tag for tag in selected_tag.get_descendants() if tag.pk in accessible_tag_ids
                ]
                all_tags_ids = [selected_tag.pk] + [tag.pk for tag in descendants]
                context["gifts"] = (
                    Gift.objects.accessible_by(request.user)
                    .filter(Q(tags__in=all_tags_ids))
                    .prefetch_related(
                        Prefetch(
                            "tags",
                            queryset=GiftTag.objects.accessible_by(request.user).order_by("name"),
                        )
                    )
                    .distinct()
                    .order_by("name")
                )

            except (DjangoValidationError, GiftTag.DoesNotExist, ValueError):
                messages.error(
                    request,
                    gettext("You do not have access to this tag or this tag does not exist."),
                )
                return redirect("gift_manager:gift_tag_explorer")
        else:
            # If no tag is selected, show all root tags and reset navigation history
            navigation_history.clear()
            request.session.modified = True

            # Your existing code for root tags
            context["root_tags"] = (
                GiftTag.objects.accessible_by(request.user)
                .filter(Q(parent_tags__isnull=True))
                .distinct()
                .order_by("name")
            )

            # Show all untagged gifts accessible to the user
            context["gifts"] = (
                Gift.objects.accessible_by(request.user)
                .filter(Q(tags__isnull=True))
                .order_by("name")
            )

        return render(request, self.template_name, context)


class GiftTagListView(BaseListView):
    model = GiftTag
    template_name = "gift_manager/gift_tag_list.html"
    object_type = "Gift Tags"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.column_names = {
            "name": gettext("Tag name"),
            "parent_tag__name": gettext("Parent tag"),
        }

    def get_queryset(self):
        return GiftTag.objects.accessible_by(self.request.user).values(
            "tag_id", "name", "parent_tag__name"
        )


class GiftTagCreateView(BaseCreateView):
    model = GiftTag
    form_class = GiftTagForm
    success_url = reverse_lazy("gift_manager:gift_tag_explorer")
    context_object_name = "gift_tag"
    object_type = "Gift Tag"
    htmx_template_name = "gift_manager/includes/gift_tag_form_partial.html"
    form_fields_template = "gift_manager/includes/forms/gift_tag_fields.html"
    form_css_class = "gift-tag-form"
    form_type = "gift_tag"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["parent_tags"].queryset = GiftTag.objects.accessible_by(
            self.request.user
        ).order_by("name")
        return form


class GiftTagUpdateView(PermissionUpdateMixin, BaseUpdateView):
    model = GiftTag
    fields = ["name", "parent_tags"]
    pk_name = "tag_id"
    context_object_name = "gift_tag"
    object_type = "Gift tag"
    detail_url_name = "gift_tag_detail"
    htmx_template_name = "gift_manager/includes/gift_tag_form_partial.html"
    form_fields_template = "gift_manager/includes/forms/gift_tag_fields.html"
    form_css_class = "gift-tag-form"
    form_type = "gift_tag"

    def get_queryset(self):
        """Optimize queryset with prefetched relations."""
        return GiftTag.objects.accessible_by(self.request.user).prefetch_related(
            "parent_tags", "child_tags"
        )

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        current_tag = self.get_object()
        # get_descendants() is now cached and optimized
        descendants = current_tag.get_descendants()
        excluded_ids = [current_tag.pk] + [tag.pk for tag in descendants]
        form.fields["parent_tags"].queryset = (
            GiftTag.objects.accessible_by(self.request.user)
            .exclude(pk__in=excluded_ids)
            .order_by("name")
        )
        return form


class GiftTagDeleteView(BaseDeleteView):
    model = GiftTag
    success_url = reverse_lazy("gift_manager:gift_tag_explorer")
    pk_name = "tag_id"
    object_type = "gift_tag"


class GiftTagDetailView(BaseDetailView):
    model = GiftTag
    template_name = "gift_manager/gift_tag_detail.html"
    context_object_name = "gift_tag"
    pk_name = "tag_id"
    htmx_template_name = "gift_manager/includes/gift_tag_detail_partial.html"

    def get_queryset(self):
        """Optimize queryset with prefetched relations."""
        return self.model.objects.accessible_by(self.request.user).prefetch_related(
            "parent_tags", "child_tags"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["gifts"] = (
            Gift.objects.accessible_by(self.request.user).filter(tags=self.object).order_by("name")
        )
        context["parent_tags"] = self.object.parent_tags.filter(
            Q(is_public=True) | Q(shared_with=self.request.user)
        ).order_by("name")
        context["child_tags"] = (
            GiftTag.objects.accessible_by(self.request.user)
            .filter(parent_tags=self.object)
            .order_by("name")
        )
        # get_ancestors() is now cached and optimized
        accessible_tag_ids = set(
            GiftTag.objects.accessible_by(self.request.user).values_list("pk", flat=True)
        )
        context["ancestors_path"] = [
            tag for tag in self.object.get_primary_ancestors_path() if tag.pk in accessible_tag_ids
        ]

        # Usage statistics
        direct_gifts_count = context["gifts"].count()
        total_gifts_count = self.object.get_all_gifts(self.request.user).count()
        child_tags_count = context["child_tags"].count()

        context["usage_stats"] = {
            "direct_gifts": direct_gifts_count,
            "total_gifts": total_gifts_count,
            "child_tags": child_tags_count,
        }

        return context
