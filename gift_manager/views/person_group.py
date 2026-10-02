"""PersonGroup-related views."""

import json
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Prefetch
from django.db.models import Q
from django.http import HttpResponse
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.urls import reverse_lazy
from django.utils.html import format_html
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.decorators.http import require_http_methods
from django.views.decorators.http import require_POST

from gift_manager.forms import PersonGroupAddMultipleChildGroupsForm
from gift_manager.forms import PersonGroupAddMultiplePersonsForm
from gift_manager.forms import PersonGroupForm
from gift_manager.group_hierarchy_service import GroupHierarchyService
from gift_manager.mixins.permissions import PermissionContextMixin
from gift_manager.mixins.permissions import PermissionUpdateMixin
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


class PersonGroupListView(PermissionContextMixin, BaseListView):
    model = PersonGroup
    template_name = "gift_manager/person_group_list.html"
    object_type = "Groups"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.column_names = get_person_group_grid_column_names()

    def get_queryset(self):
        return get_person_group_grid_queryset(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            get_person_group_management_context(self.request.user, include_permissions=False)
        )
        return context


def get_person_group_grid_column_names():
    """Return translated column labels for the group management grid."""
    return {
        "name": gettext("Group name"),
    }


def _accessible_members_prefetch(user, member_queryset=None) -> Prefetch:
    """Prefetch the members a user can access into ``group.accessible_members``.

    Member counts must be computed from this list: ``group.person_set`` also contains
    persons the user cannot see.
    """
    if member_queryset is None:
        member_queryset = Person.objects.accessible_by(user)
    return Prefetch("person_set", queryset=member_queryset, to_attr="accessible_members")


def get_person_group_grid_queryset(user, member_queryset=None):
    """Return groups prepared for the shared management grid and tree view."""
    return (
        PersonGroup.objects.accessible_by(user)
        .prefetch_related(
            "parent_groups",
            "child_groups",
            _accessible_members_prefetch(user, member_queryset),
        )
        .order_by("name")
    )


def get_person_group_management_context(
    user, *, include_permissions=True, member_queryset=None
) -> dict:
    """Build the shared person-group management context."""
    all_groups = list(get_person_group_grid_queryset(user, member_queryset=member_queryset))
    accessible_group_ids = {group.pk for group in all_groups}
    tree_data = _build_person_group_tree_data(all_groups, accessible_group_ids)
    has_hierarchy = any(
        any(parent.pk in accessible_group_ids for parent in group.parent_groups.all())
        or any(child.pk in accessible_group_ids for child in group.child_groups.all())
        for group in all_groups
    )

    context = {
        "column_names": get_person_group_grid_column_names(),
        "data": [{"group_id": group.group_id, "name": group.name} for group in all_groups],
        "tree_data": tree_data,
        "has_hierarchy": has_hierarchy,
    }

    if include_permissions:
        permissions = {
            str(group.group_id): PermissionService.get_effective_permission(group, user)
            for group in all_groups
        }
        context["user_permissions_json"] = json.dumps(permissions)

    return context


def _build_person_group_tree_data(all_groups, accessible_group_ids) -> list[dict]:
    """Build flattened tree data for accessible groups."""

    def build_tree_node(group, depth=0, visited=None) -> dict | None:
        if visited is None:
            visited = set()

        if group.pk in visited:
            return None
        visited.add(group.pk)

        prefetched_members = _get_prefetched_group_members(group)
        prefetched_parents = [
            parent for parent in group.parent_groups.all() if parent.pk in accessible_group_ids
        ]
        prefetched_children = [
            child for child in group.child_groups.all() if child.pk in accessible_group_ids
        ]

        node = {
            "group": group,
            "group_id": str(group.group_id),
            "name": group.name,
            "depth": depth,
            "member_count": len(prefetched_members),
            "has_children": len(prefetched_children) > 0,
            "parent_ids": [str(parent.group_id) for parent in prefetched_parents],
            "children": [],
        }

        for child in prefetched_children:
            child_node = build_tree_node(child, depth + 1, visited.copy())
            if child_node:
                node["children"].append(child_node)

        return node

    def flatten_tree(nodes, result=None) -> list:
        if result is None:
            result = []
        for node in nodes:
            result.append(node)
            if node["children"]:
                flatten_tree(node["children"], result)
        return result

    root_groups = [
        group
        for group in all_groups
        if not any(parent.pk in accessible_group_ids for parent in group.parent_groups.all())
    ]

    tree_data = []
    for root in root_groups:
        tree_node = build_tree_node(root)
        if tree_node:
            tree_data.append(tree_node)

    return flatten_tree(tree_data)


def _get_prefetched_group_members(group) -> list[Person]:
    prefetched_members = getattr(group, "accessible_members", None)
    if prefetched_members is not None:
        return prefetched_members
    return list(group.person_set.all())


class PersonGroupCreateView(BaseCreateView):
    model = PersonGroup
    form_class = PersonGroupForm
    success_url = reverse_lazy("gift_manager:person_groups")
    context_object_name = "group"
    object_type = "Person group"
    htmx_template_name = "gift_manager/includes/person_group_form_partial.html"
    form_fields_template = "gift_manager/includes/forms/person_group_fields.html"
    form_css_class = "person-group-form"
    form_type = "person_group"

    def get_form_kwargs(self):
        """Pass the user to the form."""
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class PersonGroupUpdateView(PermissionUpdateMixin, BaseUpdateView):
    model = PersonGroup
    form_class = PersonGroupForm
    pk_name = "group_id"
    context_object_name = "group"
    object_type = "Person group"
    detail_url_name = "person_group_detail"
    htmx_template_name = "gift_manager/includes/person_group_form_partial.html"
    form_fields_template = "gift_manager/includes/forms/person_group_fields.html"
    form_css_class = "person-group-form"
    form_type = "person_group"

    def get_form_kwargs(self):
        """Pass the user to the form."""
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def post(self, request, *args, **kwargs):
        """Check editor permission before processing the form."""
        self.object = self.get_object()
        permission = PermissionService.get_effective_permission(self.object, request.user)
        if permission < PermissionLevel.EDITOR:
            messages.error(request, _("You do not have permission to edit this group"))
            return redirect("gift_manager:person_group_detail", pk=self.object.group_id)
        return super().post(request, *args, **kwargs)


def _check_editor_permission(
    request,
    group: PersonGroup,
) -> bool:
    """Check if the user has permission to modify the group.

    Args:
        request: The HTTP request object.
        group: The PersonGroup instance.

    Returns:
        bool: True if the user has permission to modify the group, False otherwise.
    """
    permission = PermissionService.get_effective_permission(group, request.user)
    if permission < PermissionLevel.EDITOR:
        messages.error(request, _("You do not have permission to edit this group"))
        return False
    return True


@login_required
def add_multiple_persons_to_group(request, pk):
    group = get_object_or_404(PersonGroup, group_id=pk)

    # Permission: require at least Editor on the group
    if not _check_editor_permission(request, group):
        return redirect("gift_manager:person_group_detail", pk=pk)

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


@login_required
def add_multiple_child_groups_to_group(request, pk):
    """Add multiple child groups to a parent group."""
    parent_group = get_object_or_404(PersonGroup, group_id=pk)

    # Permission: require at least Editor on the group
    if not _check_editor_permission(request, parent_group):
        return redirect("gift_manager:person_group_detail", pk=pk)

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


def _htmx_notification_response(
    message: str, *, level: str, status: int = 200, list_update: bool = False
) -> HttpResponse:
    """Return an empty HTMX response that closes the modal and shows a notification."""
    events = {"modal:close": {}, "showNotification": {"message": message, "type": level}}
    if list_update:
        events["list:update"] = {}
    response = HttpResponse("", status=status)
    response["HX-Trigger"] = json.dumps(events)
    return response


def _group_edit_denied_response(request, *, is_htmx: bool, redirect_url: str) -> HttpResponse:
    """Answer a group membership change attempted without editor permission."""
    denied_message = gettext("You do not have permission to edit this group")
    if is_htmx and request.method == "GET":
        # Shown in the confirmation modal body, without a form to submit
        return HttpResponse(
            format_html('<div class="alert alert-danger mb-0">{}</div>', denied_message),
            status=403,
        )
    if is_htmx:
        return _htmx_notification_response(denied_message, level="error", status=403)
    messages.error(request, denied_message)
    return redirect(redirect_url)


@login_required
@require_http_methods(["GET", "POST"])
def remove_person_from_group(request, pk, person_id):
    """Remove a person from a group.

    GET only renders a confirmation (a modal body for HTMX, a full page otherwise);
    the membership is changed by the POST that the confirmation submits.
    """
    is_htmx = request.headers.get("HX-Request") == "true"
    detail_url = reverse("gift_manager:person_group_detail", kwargs={"pk": pk})

    with transaction.atomic():
        group = get_object_or_404(PersonGroup.objects.accessible_by(request.user), group_id=pk)

        # Permission: require at least Editor on the group
        if PermissionService.get_effective_permission(group, request.user) < PermissionLevel.EDITOR:
            return _group_edit_denied_response(request, is_htmx=is_htmx, redirect_url=detail_url)

        person = get_object_or_404(Person.objects.accessible_by(request.user), person_id=person_id)

        if request.method == "GET":
            template_name = (
                "gift_manager/includes/person_group_remove_person_confirmation.html"
                if is_htmx
                else "gift_manager/person_group_remove_person_confirm.html"
            )
            return render(
                request,
                template_name,
                {
                    "group": group,
                    "person": person,
                    "remove_url": request.path,
                    "cancel_url": detail_url,
                },
            )

        try:
            GroupHierarchyService.change_members(request.user, group, remove=[person])
        except PermissionDenied as error:
            if is_htmx:
                return _htmx_notification_response(str(error), level="error", status=403)
            messages.error(request, str(error))
            return redirect(detail_url)

    success_message = gettext("Person removed from group")
    if is_htmx:
        # The detail page refreshes its membership section (counts and grids) on list:update
        return _htmx_notification_response(success_message, level="success", list_update=True)
    messages.success(request, success_message)
    return redirect(detail_url)


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
    htmx_template_name = "gift_manager/includes/person_group_detail_partial.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        accessible_groups = PersonGroup.objects.accessible_by(self.request.user)
        accessible_group_ids = set(accessible_groups.values_list("pk", flat=True))
        accessible_descendants = [
            group for group in self.object.get_descendants() if group.pk in accessible_group_ids
        ]
        accessible_nested_groups = [self.object, *accessible_descendants]
        accessible_people = Person.objects.accessible_by(self.request.user)

        # Hierarchy information
        context["parent_groups"] = accessible_groups.filter(child_groups=self.object).order_by(
            "name"
        )
        context["child_groups"] = accessible_groups.filter(parent_groups=self.object).order_by(
            "name"
        )
        context["ancestors_path"] = [
            group
            for group in self.object.get_primary_ancestors_path()
            if group.pk in accessible_group_ids
        ]

        # Direct members only
        context["members"] = (
            accessible_people.filter(groups=self.object)
            .prefetch_related("groups")
            .order_by("family_name", "first_name")
        )

        # All members (including from nested groups)
        nested_member_qs = accessible_people.filter(groups__in=accessible_nested_groups).distinct()
        context["nested_members"] = nested_member_qs.prefetch_related("groups").order_by(
            "family_name", "first_name"
        )

        # Relations/gifts for this group
        context["relations"] = (
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
                Q(group__in=accessible_nested_groups) | Q(person__in=nested_member_qs),
                gift__isnull=False,
            )
            .select_related("person", "group", "gift", "event", "status")
            .prefetch_related("gift__tags")
            .order_by("status__pk", "gift__name")
        )

        context["relation_statuses"] = RelationStatus.objects.all()
        context["gift_history_url"] = reverse(
            "gift_manager:person_group_gift_history", kwargs={"pk": self.object.group_id}
        )

        # Member counts
        context["direct_member_count"] = context["members"].count()
        context["nested_member_count"] = context["nested_members"].count()
        context["gift_count"] = context["relations"].count()
        context["nested_gift_count"] = context["nested_gifts"].count()

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
        accessible_groups = PersonGroup.objects.accessible_by(request.user)

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
                selected_group = accessible_groups.prefetch_related(
                    "parent_groups", "child_groups"
                ).get(group_id=selected_group_id)

                context["selected_group"] = selected_group

                # Get the source/referring group if present in the query string
                referring_group_id = request.GET.get("from_group")
                if referring_group_id:
                    # Store the relationship: current group came from this referring group
                    navigation_history[str(selected_group_id)] = referring_group_id
                    request.session.modified = True

                # Build the breadcrumbs based on navigation history
                # First, collect all group IDs we need from the navigation path
                breadcrumb_ids = []
                current_group_id = str(selected_group_id)
                visited = set()  # To prevent infinite loops

                while current_group_id and current_group_id not in visited:
                    visited.add(current_group_id)
                    breadcrumb_ids.append(current_group_id)
                    current_group_id = navigation_history.get(current_group_id)

                # Batch fetch all groups in ONE query instead of N queries
                groups_by_id = {
                    str(g.group_id): g
                    for g in accessible_groups.filter(group_id__in=breadcrumb_ids)
                }

                # Build breadcrumbs in correct order (reversed, since we collected child-first)
                breadcrumbs = [
                    groups_by_id[gid] for gid in reversed(breadcrumb_ids) if gid in groups_by_id
                ]

                context["breadcrumbs"] = breadcrumbs

                # Get parent groups and child groups
                context["parent_groups"] = (
                    accessible_groups.filter(child_groups=selected_group)
                    .prefetch_related(_accessible_members_prefetch(request.user))
                    .order_by("name")
                )

                context["child_groups"] = (
                    accessible_groups.filter(parent_groups=selected_group)
                    .prefetch_related(_accessible_members_prefetch(request.user))
                    .order_by("name")
                )

                # Get members in this group (direct members)
                context["members"] = (
                    Person.objects.accessible_by(request.user)
                    .filter(groups=selected_group)
                    .order_by("family_name", "first_name")
                )

            except (PersonGroup.DoesNotExist, ValidationError, ValueError):
                messages.error(
                    request,
                    gettext("This group does not exist or you do not have access to it."),
                )
                return redirect("gift_manager:person_group_explorer")
        else:
            # No group selected: show root level groups
            all_accessible_groups = list(
                accessible_groups.prefetch_related(
                    "parent_groups", _accessible_members_prefetch(request.user)
                ).order_by("name")
            )
            accessible_group_ids = {group.pk for group in all_accessible_groups}
            context["root_groups"] = [
                group
                for group in all_accessible_groups
                if not any(
                    parent.pk in accessible_group_ids for parent in group.parent_groups.all()
                )
            ]

        return render(request, self.template_name, context)


def _json_error(message: str, status: int) -> JsonResponse:
    return JsonResponse({"success": False, "message": message}, status=status)


def _parse_group_uuid(value) -> uuid.UUID | None:
    """Return the UUID given as a string, or None when the value is not a valid UUID."""
    if not isinstance(value, str):
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def _parse_reparent_payload(request) -> tuple[uuid.UUID, list[uuid.UUID], str] | JsonResponse:
    """Validate the reparent JSON body; return (group id, parent ids, action) or an error."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict):
        return _json_error(gettext("Invalid JSON data"), 400)

    group_id = data.get("group_id")
    parent_ids = data.get("parent_ids", [])
    action = data.get("action", "set")  # "set", "add", or "remove"

    if not group_id:
        return _json_error(gettext("group_id is required"), 400)
    if action not in ["set", "add", "remove"]:
        return _json_error(gettext("action must be 'set', 'add', or 'remove'"), 400)

    group_uuid = _parse_group_uuid(group_id)
    if group_uuid is None:
        return _json_error(gettext("Invalid group identifier"), 400)

    parent_uuids = (
        [_parse_group_uuid(parent_id) for parent_id in parent_ids]
        if isinstance(parent_ids, list)
        else [None]
    )
    if None in parent_uuids:
        return _json_error(gettext("Invalid parent group identifier"), 400)

    # Keep the requested order but ignore duplicates
    return group_uuid, list(dict.fromkeys(parent_uuids)), action


@login_required
@require_POST
def reparent_group(  # noqa: PLR0911 ; pylint: disable=too-many-return-statements
    request,
) -> JsonResponse:
    """API endpoint for reparenting groups (used by drag-and-drop and bulk operations).

    Accepts JSON payload with:
    - group_id: UUID of the group to reparent
    - parent_ids: List of parent group UUIDs (can be empty for root groups)
    - action: "set" (replace all parents), "add" (add parents), or "remove" (remove parents)

    Unknown groups and groups the user cannot access get the same 404 answer, so the
    endpoint does not reveal whether a group exists or what it is called.

    Returns JSON with:
    - success: boolean
    - message: string
    - errors: list of error messages (if any)
    """
    payload = _parse_reparent_payload(request)
    if isinstance(payload, JsonResponse):
        return payload
    group_id, parent_ids, action = payload

    accessible_groups = PersonGroup.objects.accessible_by(request.user)

    # Get the group
    try:
        group = accessible_groups.get(group_id=group_id)
    except PersonGroup.DoesNotExist:
        return _json_error(gettext("Group not found"), 404)

    # Check permissions - user must be an editor of the group
    permission = PermissionService.get_effective_permission(group, request.user)
    if permission < PermissionLevel.EDITOR:
        return _json_error(gettext("You do not have permission to edit this group"), 403)

    # Get parent groups: only groups the user can access are candidates
    parents_by_id = {
        parent.group_id: parent for parent in accessible_groups.filter(group_id__in=parent_ids)
    }
    missing_ids = [parent_id for parent_id in parent_ids if parent_id not in parents_by_id]
    if missing_ids:
        return _json_error(gettext("Parent group not found: %(id)s") % {"id": missing_ids[0]}, 404)
    parent_groups = [parents_by_id[parent_id] for parent_id in parent_ids]

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
                # Parents the user cannot edit were never offered: keep them
                current = set(group.parent_groups.all())
                selected = set(parent_groups)
                removable = current - selected
                editable_pks = GroupHierarchyService.editable_pks(request.user, removable)
                GroupHierarchyService.change_parents(
                    request.user,
                    group,
                    add=selected - current,
                    remove={parent for parent in removable if parent.pk in editable_pks},
                )
                message = gettext("Group parents updated successfully")
            elif action == "add":
                # Add new parents
                GroupHierarchyService.change_parents(request.user, group, add=parent_groups)
                message = gettext("Parents added successfully")
            elif action == "remove":
                # Remove parents
                GroupHierarchyService.change_parents(request.user, group, remove=parent_groups)
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

    except PermissionDenied as e:
        return JsonResponse({"success": False, "message": str(e)}, status=403)
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
