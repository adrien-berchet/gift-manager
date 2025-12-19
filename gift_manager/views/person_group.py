"""PersonGroup-related views."""

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.urls import reverse_lazy
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.decorators.http import require_POST

from gift_manager.forms import PersonGroupAddMultipleChildGroupsForm
from gift_manager.forms import PersonGroupAddMultiplePersonsForm
from gift_manager.forms import PersonGroupForm
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import Relation
from gift_manager.models import RelationStatus
from gift_manager.services import PermissionLevel
from gift_manager.services import PermissionService
from gift_manager.views.base import BaseCreateView
from gift_manager.views.base import BaseDeleteView
from gift_manager.views.base import BaseDetailView
from gift_manager.views.base import BaseListView
from gift_manager.views.base import BaseUpdateView


class PersonGroupListView(BaseListView):
    model = PersonGroup
    template_name = "gift_manager/person_group_list.html"
    object_type = "Groups"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.column_names = {
            "name": gettext("Group name"),
        }

    def get_queryset(self):
        return (
            PersonGroup.objects.accessible_by(self.request.user)
            .prefetch_related("parent_groups", "child_groups", "person_set")
            .order_by("name")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get all groups as model instances for tree view
        all_groups = list(self.get_queryset())

        # Also provide data as dictionaries for Grid.js view compatibility
        # (Grid.js template expects dictionaries with .get() method)
        context["data"] = [
            {
                "group_id": g.group_id,
                "name": g.name,
            }
            for g in all_groups
        ]

        # Build hierarchical tree data for tree view
        def build_tree_node(group, depth=0, visited=None) -> dict:
            """Recursively build tree nodes with hierarchy information."""
            if visited is None:
                visited = set()

            # Prevent infinite loops
            if group.pk in visited:
                return None
            visited.add(group.pk)

            node = {
                "group": group,
                "group_id": str(group.group_id),
                "name": group.name,
                "depth": depth,
                "member_count": group.person_set.count(),
                "has_children": group.child_groups.exists(),
                "parent_ids": [str(p.group_id) for p in group.parent_groups.all()],
                "children": [],
            }

            # Add children recursively
            for child in group.child_groups.all():
                child_node = build_tree_node(child, depth + 1, visited.copy())
                if child_node:
                    node["children"].append(child_node)

            return node

        # Find root groups (those without parents)
        root_groups = [g for g in all_groups if not g.parent_groups.exists()]

        # Build tree from roots
        tree_data = []
        for root in root_groups:
            tree_node = build_tree_node(root)
            if tree_node:
                tree_data.append(tree_node)

        # Flatten tree for easier rendering
        def flatten_tree(nodes, result=None) -> list:
            """Flatten tree structure for template rendering."""
            if result is None:
                result = []
            for node in nodes:
                result.append(node)
                if node["children"]:
                    flatten_tree(node["children"], result)
            return result

        context["tree_data"] = flatten_tree(tree_data)
        context["has_hierarchy"] = any(
            g.parent_groups.exists() or g.child_groups.exists() for g in all_groups
        )

        return context


class PersonGroupCreateView(BaseCreateView):
    model = PersonGroup
    form_class = PersonGroupForm
    success_url = reverse_lazy("gift_manager:person_groups")
    context_object_name = "group"
    object_type = "Person group"

    def get_form_kwargs(self):
        """Pass the user to the form."""
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class PersonGroupUpdateView(BaseUpdateView):
    model = PersonGroup
    form_class = PersonGroupForm
    pk_name = "group_id"
    context_object_name = "group"
    object_type = "Person group"
    detail_url_name = "person_group_detail"

    def get_form_kwargs(self):
        """Pass the user to the form."""
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


def add_multiple_persons_to_group(request, pk):
    group = get_object_or_404(PersonGroup, group_id=pk)
    if request.method == "POST":
        form = PersonGroupAddMultiplePersonsForm(request.POST, user=request.user, group=group)
        if form.is_valid():
            form.save(group)
            return redirect("gift_manager:person_group_detail", pk=pk)
    else:
        form = PersonGroupAddMultiplePersonsForm(user=request.user, group=group)

    return render(
        request,
        "gift_manager/person_group_add_person_form.html",
        {
            "group": group,
            "form": form,
        },
    )


def add_multiple_child_groups_to_group(request, pk):
    """Add multiple child groups to a parent group."""
    parent_group = get_object_or_404(PersonGroup, group_id=pk)
    if request.method == "POST":
        form = PersonGroupAddMultipleChildGroupsForm(
            request.POST, user=request.user, group=parent_group
        )
        if form.is_valid():
            form.save(parent_group)
            return redirect("gift_manager:person_group_detail", pk=pk)
    else:
        form = PersonGroupAddMultipleChildGroupsForm(user=request.user, group=parent_group)

    return render(
        request,
        "gift_manager/person_group_add_child_groups_form.html",
        {
            "group": parent_group,
            "form": form,
        },
    )


def remove_person_from_group(request, pk, person_id):  # noqa: ARG001
    with transaction.atomic():
        group = get_object_or_404(PersonGroup, group_id=pk)
        person = get_object_or_404(Person, person_id=person_id)
        person.groups.remove(group)
        return redirect("gift_manager:person_group_detail", pk=pk)


class PersonGroupDeleteView(BaseDeleteView):
    model = PersonGroup
    success_url = reverse_lazy("gift_manager:person_groups")
    pk_name = "group_id"
    object_type = "group"


class PersonGroupDetailView(BaseDetailView):
    model = PersonGroup
    template_name = "gift_manager/person_group_detail.html"
    context_object_name = "group"
    pk_name = "group_id"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Hierarchy information
        context["parent_groups"] = self.object.parent_groups.all()
        context["child_groups"] = self.object.get_children()

        # Direct members only
        context["persons"] = (
            Person.objects.accessible_by(self.request.user)
            .filter(groups=self.object)
            .prefetch_related("groups")
            .order_by("family_name", "first_name")
        )

        # All members (including from nested groups)
        nested_member_qs = self.object.get_all_members(include_nested=True)
        context["nested_members"] = (
            nested_member_qs.filter(pk__in=Person.objects.accessible_by(self.request.user))
            .prefetch_related("groups")
            .order_by("family_name", "first_name")
        )

        # Member counts
        context["direct_member_count"] = context["persons"].count()
        context["nested_member_count"] = context["nested_members"].count()

        # Relations/gifts for this group
        context["gifts"] = (
            Relation.objects.accessible_by(self.request.user)
            .filter(group=self.object, gift__isnull=False)
            .select_related("gift", "event", "status")
            .prefetch_related("gift__tags")
            .order_by("status__pk", "gift__name")
        )

        # All gifts (including direct members and nested members)
        # We perform the query on Relation to catch:
        # 1. Gifts to the group itself (self.object)
        # 2. Gifts to any person in the nested members list (nested_member_qs)
        context["nested_gifts"] = (
            Relation.objects.accessible_by(self.request.user)
            .filter(
                Q(group=self.object) | Q(person__in=nested_member_qs),
                gift__isnull=False,
            )
            .select_related("person", "group", "gift", "event", "status")
            .prefetch_related("gift__tags")
            .order_by("status__pk", "gift__name")
        )

        context["relation_statuses"] = RelationStatus.objects.all()

        # Add action buttons
        is_editor = context["is_editor"]
        context["action_buttons"] = [
            {
                "type": "edit",
                "url": reverse(
                    "gift_manager:person_group_edit", kwargs={"pk": self.object.group_id}
                ),
                "label": _("Edit group"),
                "enabled": is_editor,
                "tooltip": _("You do not have permission to edit this object")
                if not is_editor
                else None,
            },
            {
                "type": "delete",
                "url": reverse(
                    "gift_manager:person_group_delete", kwargs={"pk": self.object.group_id}
                ),
                "label": _("Delete group"),
                "enabled": True,
                "tooltip": _(
                    "You do not have permission to delete this object so it will only be "
                    "unshared with you"
                )
                if not is_editor
                else None,
            },
        ]
        return context


class PersonGroupExplorerView(LoginRequiredMixin, View):
    """View for exploring persons by hierarchical groups."""

    template_name = "gift_manager/person_group_explorer.html"

    def get(self, request, *args, **kwargs):
        # Get the selected group (or None for the root level)
        selected_group_id = kwargs.get("pk")

        # Context to be sent to the template
        context = {
            "selected_group": None,
            "root_groups": [],
            "parent_groups": [],
            "child_groups": [],
            "members": [],
            "breadcrumbs": [],
        }

        # Initialize the navigation history in session if it doesn't exist
        if "group_navigation_history" not in request.session:
            request.session["group_navigation_history"] = {}

        navigation_history = request.session["group_navigation_history"]

        # If a group is selected, retrieve it
        if selected_group_id:
            try:
                # Prefetch related groups to optimize hierarchy traversal
                selected_group = get_object_or_404(
                    PersonGroup.objects.prefetch_related("parent_groups", "child_groups"),
                    group_id=selected_group_id,
                )

                # Check if the user has access to this group
                if not selected_group.shared_with.filter(id=request.user.id).exists():
                    messages.error(
                        request,
                        gettext(
                            "You do not have access to this group or this group does not exist."
                        ),
                    )
                    return redirect("gift_manager:person_group_explorer")

                context["selected_group"] = selected_group

                # Get the source/referring group if present in the query string
                referring_group_id = request.GET.get("from_group")
                if referring_group_id:
                    # Store the relationship: current group came from this referring group
                    navigation_history[str(selected_group_id)] = referring_group_id
                    request.session.modified = True

                # Build the breadcrumbs based on navigation history
                breadcrumbs = []
                current_group_id = str(selected_group_id)
                visited = set()  # To prevent infinite loops

                while current_group_id and current_group_id not in visited:
                    visited.add(current_group_id)
                    try:
                        group = PersonGroup.objects.get(group_id=current_group_id)
                        breadcrumbs.insert(0, group)
                        # Move to parent in the navigation history
                        current_group_id = navigation_history.get(current_group_id)
                    except PersonGroup.DoesNotExist:
                        break

                context["breadcrumbs"] = breadcrumbs

                # Get parent groups and child groups
                context["parent_groups"] = (
                    selected_group.parent_groups.filter(Q(shared_with=request.user))
                    .prefetch_related("person_set")
                    .order_by("name")
                )

                context["child_groups"] = (
                    selected_group.child_groups.filter(Q(shared_with=request.user))
                    .prefetch_related("person_set")
                    .order_by("name")
                )

                # Get members in this group (direct members)
                context["members"] = (
                    Person.objects.accessible_by(request.user)
                    .filter(groups=selected_group)
                    .order_by("family_name", "first_name")
                )

            except PersonGroup.DoesNotExist:
                messages.error(
                    request,
                    gettext("This group does not exist or you do not have access to it."),
                )
                return redirect("gift_manager:person_group_explorer")
        else:
            # No group selected: show root level groups
            context["root_groups"] = (
                PersonGroup.objects.accessible_by(request.user)
                .filter(parent_groups__isnull=True)
                .prefetch_related("person_set")
                .order_by("name")
            )

        return render(request, self.template_name, context)


@login_required
@require_POST
def reparent_group(  # noqa: C901, PLR0911, PLR0912 ; pylint: disable=too-many-branches, too-many-return-statements
    request,
) -> JsonResponse:
    """API endpoint for reparenting groups (used by drag-and-drop and bulk operations).

    Accepts JSON payload with:
    - group_id: UUID of the group to reparent
    - parent_ids: List of parent group UUIDs (can be empty for root groups)
    - action: "set" (replace all parents), "add" (add parents), or "remove" (remove parents)

    Returns JSON with:
    - success: boolean
    - message: string
    - errors: list of error messages (if any)
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "message": gettext("Invalid JSON data")}, status=400)

    group_id = data.get("group_id")
    parent_ids = data.get("parent_ids", [])
    action = data.get("action", "set")  # "set", "add", or "remove"

    # Validate required fields
    if not group_id:
        return JsonResponse(
            {"success": False, "message": gettext("group_id is required")}, status=400
        )

    if action not in ["set", "add", "remove"]:
        return JsonResponse(
            {
                "success": False,
                "message": gettext("action must be 'set', 'add', or 'remove'"),
            },
            status=400,
        )

    # Get the group
    try:
        group = PersonGroup.objects.get(group_id=group_id)
    except PersonGroup.DoesNotExist:
        return JsonResponse({"success": False, "message": gettext("Group not found")}, status=404)

    # Check permissions - user must be an editor of the group
    permission = PermissionService.get_permission(group, request.user, "group")
    if permission < PermissionLevel.EDITOR:
        return JsonResponse(
            {
                "success": False,
                "message": gettext("You do not have permission to edit this group"),
            },
            status=403,
        )

    # Get parent groups
    parent_groups = []
    if parent_ids:
        # Fetch all candidate groups in one query
        groups_map = {
            str(k): v
            for k, v in PersonGroup.objects.in_bulk(parent_ids, field_name="group_id").items()
        }

        # Fetch all accessible group IDs in one query
        accessible_group_ids = set(
            PersonGroup.objects.filter(
                group_id__in=parent_ids, shared_with=request.user
            ).values_list("group_id", flat=True)
        )

        for parent_id in parent_ids:
            # Check existence
            if parent_id not in groups_map:
                return JsonResponse(
                    {
                        "success": False,
                        "message": gettext("Parent group not found: %(id)s") % {"id": parent_id},
                    },
                    status=404,
                )

            parent_group = groups_map[parent_id]

            # Check permissions
            # Note: The original code checked shared_with.filter(id=user.id).exists()
            # which means direct shared_with membership is required.
            if parent_group.group_id not in accessible_group_ids:
                return JsonResponse(
                    {
                        "success": False,
                        "message": gettext("You do not have access to parent group: %(name)s")
                        % {"name": parent_group.name},
                    },
                    status=403,
                )

            parent_groups.append(parent_group)

    # Check for cycles before making changes
    errors = [
        gettext("Adding '%(parent)s' as a parent would create a cycle")
        % {"parent": parent_group.name}
        for parent_group in parent_groups
        if group.has_cycle_with(parent_group)
    ]

    if errors:
        return JsonResponse(
            {"success": False, "message": gettext("Cycle detected"), "errors": errors},
            status=400,
        )

    # Perform the reparenting operation
    try:
        with transaction.atomic():
            if action == "set":
                # Replace all parents
                group.parent_groups.set(parent_groups)
                message = gettext("Group parents updated successfully")
            elif action == "add":
                # Add new parents
                for parent_group in parent_groups:
                    group.parent_groups.add(parent_group)
                message = gettext("Parents added successfully")
            elif action == "remove":
                # Remove parents
                for parent_group in parent_groups:
                    group.parent_groups.remove(parent_group)
                message = gettext("Parents removed successfully")
            else:
                message = gettext("Invalid action")

        return JsonResponse(
            {
                "success": True,
                "message": message,
                "group_id": str(group.group_id),
                "parent_ids": [str(p.group_id) for p in group.parent_groups.all()],
            }
        )

    except ValidationError as e:
        return JsonResponse(
            {
                "success": False,
                "message": str(e),
                "errors": e.messages if hasattr(e, "messages") else [str(e)],
            },
            status=400,
        )
    except Exception as e:
        return JsonResponse(
            {
                "success": False,
                "message": gettext("An error occurred: %(error)s") % {"error": str(e)},
            },
            status=500,
        )
