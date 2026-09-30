"""Authorization-aware mutations of group hierarchy and group membership.

Attaching a group under a parent with inheritable permissions changes who can
access it, so hierarchy and membership edges are only mutated through this
service. Every edge requires editor access on both of its ends, and edges that
would expand inherited access require ownership of the attached group.
"""

from collections.abc import Iterable

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils.translation import gettext

from gift_manager.models import PermissionLevel
from gift_manager.models import PersonGroup
from gift_manager.models import PersonGroupPermission
from gift_manager.services import PermissionService


class GroupHierarchyService:
    """Service enforcing write authority on group hierarchy and membership edges."""

    @staticmethod
    def _level(obj, actor) -> int:
        return PermissionService.get_effective_permission(obj, actor)

    @classmethod
    def editable_pks(cls, actor, objs: Iterable) -> set[int]:
        """Return the primary keys of the objects the actor can edit.

        Resolved with a constant number of queries, whatever the number of objects.
        """
        objs = list(objs)
        if not objs:
            return set()
        if actor.is_superuser:
            return {obj.pk for obj in objs}
        if all(isinstance(obj, PersonGroup) for obj in objs):
            return cls._editable_group_pks(actor, objs)
        if any(isinstance(obj, PersonGroup) for obj in objs):
            return {obj.pk for obj in objs if cls._level(obj, actor) >= PermissionLevel.EDITOR}
        return cls._editable_object_pks(actor, objs)

    @staticmethod
    def _editable_group_pks(actor, groups: list[PersonGroup]) -> set[int]:
        pks = {group.pk for group in groups}
        grants = PersonGroupPermission.objects.filter(
            user=actor, permission_type__gte=PermissionLevel.EDITOR
        ).select_related("group")
        editable = set()
        for grant in grants:
            if grant.group_id in pks:
                editable.add(grant.group_id)
            if grant.inherit_permissions:
                editable.update(d.pk for d in grant.group.get_descendants() if d.pk in pks)
        return editable

    @classmethod
    def _editable_object_pks(cls, actor, objs: list) -> set[int]:
        """Editable objects with a permission model (persons, ...), owner via user_link."""
        model = PermissionService.get_permission_model(objs[0])
        attr = PermissionService._get_permission_object_attr(objs[0], model)  # noqa: SLF001
        editable = set(
            model.objects.filter(
                user=actor,
                permission_type__gte=PermissionLevel.EDITOR,
                **{f"{attr}__in": objs},
            ).values_list(f"{attr}_id", flat=True)
        )
        editable.update(obj.pk for obj in objs if getattr(obj, "user_link_id", None) == actor.id)
        return editable

    @classmethod
    def _assert_can_edit(cls, actor, obj, *, is_new: bool = False) -> None:
        if is_new or cls._level(obj, actor) >= PermissionLevel.EDITOR:
            return
        raise PermissionDenied(
            gettext("You do not have permission to edit '%(name)s'.") % {"name": str(obj)}
        )

    @classmethod
    def _expanded_groups(
        cls, parent: PersonGroup, child: PersonGroup, *, child_is_new: bool
    ) -> list[PersonGroup]:
        """Return child and descendants whose access grows if child joins parent."""
        if child_is_new:
            return []
        grants = list(
            PersonGroupPermission.objects.filter(
                group__in=[parent, *parent.get_ancestors(use_cache=False)],
                inherit_permissions=True,
            ).select_related("user")
        )
        grants = [grant for grant in grants if not grant.user.is_superuser]
        if not grants:
            return []
        affected = [child, *child.get_descendants(use_cache=False)]
        return [
            group
            for group in affected
            if any(grant.permission_type > cls._level(group, grant.user) for grant in grants)
        ]

    @classmethod
    def assert_can_link(
        cls,
        actor,
        parent: PersonGroup,
        child: PersonGroup,
        *,
        parent_is_new: bool = False,
        child_is_new: bool = False,
    ) -> None:
        """Validate that actor may attach child under parent."""
        cls._assert_can_edit(actor, parent, is_new=parent_is_new)
        cls._assert_can_edit(actor, child, is_new=child_is_new)
        for group in cls._expanded_groups(parent, child, child_is_new=child_is_new):
            if cls._level(group, actor) < PermissionLevel.OWNER:
                raise PermissionDenied(
                    gettext(
                        "Attaching '%(child)s' under '%(parent)s' would share it with other "
                        "users; only an owner can do this."
                    )
                    % {"child": str(group), "parent": str(parent)}
                )

    @classmethod
    def assert_can_unlink(
        cls,
        actor,
        parent: PersonGroup,
        child: PersonGroup,
        *,
        parent_is_new: bool = False,
        child_is_new: bool = False,
    ) -> None:
        """Validate that actor may detach child from parent."""
        cls._assert_can_edit(actor, parent, is_new=parent_is_new)
        cls._assert_can_edit(actor, child, is_new=child_is_new)

    @classmethod
    def assert_can_change_member(
        cls,
        actor,
        group: PersonGroup,
        person,
        *,
        group_is_new: bool = False,
        person_is_new: bool = False,
    ) -> None:
        """Validate that actor may add or remove person in group."""
        cls._assert_can_edit(actor, group, is_new=group_is_new)
        cls._assert_can_edit(actor, person, is_new=person_is_new)

    @classmethod
    def check_parent_changes(
        cls, actor, group: PersonGroup, *, add=(), remove=(), group_is_new: bool = False
    ) -> None:
        """Raise PermissionDenied unless actor may apply these parent changes."""
        for parent in add:
            cls.assert_can_link(actor, parent, group, child_is_new=group_is_new)
        for parent in remove:
            cls.assert_can_unlink(actor, parent, group, child_is_new=group_is_new)

    @classmethod
    def check_child_changes(
        cls, actor, group: PersonGroup, *, add=(), remove=(), group_is_new: bool = False
    ) -> None:
        """Raise PermissionDenied unless actor may apply these child changes."""
        for child in add:
            cls.assert_can_link(actor, group, child, parent_is_new=group_is_new)
        for child in remove:
            cls.assert_can_unlink(actor, group, child, parent_is_new=group_is_new)

    @classmethod
    def check_member_changes(
        cls, actor, group: PersonGroup, *, add=(), remove=(), group_is_new: bool = False
    ) -> None:
        """Raise PermissionDenied unless actor may apply these membership changes."""
        for person in [*add, *remove]:
            cls.assert_can_change_member(actor, group, person, group_is_new=group_is_new)

    @classmethod
    def check_person_group_changes(
        cls, actor, person, *, add=(), remove=(), person_is_new: bool = False
    ) -> None:
        """Raise PermissionDenied unless actor may add/remove person in these groups."""
        for group in [*add, *remove]:
            cls.assert_can_change_member(actor, group, person, person_is_new=person_is_new)

    @classmethod
    def change_parents(
        cls, actor, group: PersonGroup, *, add=(), remove=(), group_is_new: bool = False
    ) -> None:
        """Attach or detach parents of group, all or nothing."""
        add, remove = list(add), list(remove)
        with transaction.atomic():
            cls.check_parent_changes(
                actor, group, add=add, remove=remove, group_is_new=group_is_new
            )
            group.parent_groups.add(*add)
            group.parent_groups.remove(*remove)

    @classmethod
    def change_children(
        cls, actor, group: PersonGroup, *, add=(), remove=(), group_is_new: bool = False
    ) -> None:
        """Attach or detach children of group, all or nothing."""
        add, remove = list(add), list(remove)
        with transaction.atomic():
            cls.check_child_changes(actor, group, add=add, remove=remove, group_is_new=group_is_new)
            group.child_groups.add(*add)
            group.child_groups.remove(*remove)

    @classmethod
    def change_members(
        cls, actor, group: PersonGroup, *, add=(), remove=(), group_is_new: bool = False
    ) -> None:
        """Add or remove persons in group, all or nothing."""
        add, remove = list(add), list(remove)
        with transaction.atomic():
            cls.check_member_changes(
                actor, group, add=add, remove=remove, group_is_new=group_is_new
            )
            group.person_set.add(*add)
            group.person_set.remove(*remove)

    @classmethod
    def change_person_groups(
        cls, actor, person, *, add=(), remove=(), person_is_new: bool = False
    ) -> None:
        """Add person to or remove person from groups, all or nothing."""
        add, remove = list(add), list(remove)
        with transaction.atomic():
            cls.check_person_group_changes(
                actor, person, add=add, remove=remove, person_is_new=person_is_new
            )
            person.groups.add(*add)
            person.groups.remove(*remove)
