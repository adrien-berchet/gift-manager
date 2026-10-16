# pylint: disable=redefined-outer-name
import pytest
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext

from gift_manager.models import GiftTag
from gift_manager.models import HierarchicalDAGMixin
from gift_manager.models import PermissionLevel
from gift_manager.models import PersonGroup
from gift_manager.models import PersonGroupPermission
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import UserFactory


class TestHierarchicalDAGMixinConfiguration:
    """Tests that HierarchicalDAGMixin raises NotImplementedError when configuration is missing."""

    def test_unconfigured_mixin_raises_not_implemented(self):
        class IncompleteDAG(HierarchicalDAGMixin):
            pk = 1

        obj = IncompleteDAG()

        with pytest.raises(NotImplementedError, match="must define 'parent_rel_name'"):
            obj._get_parent_rel_name()

        with pytest.raises(NotImplementedError, match="must define 'child_rel_name'"):
            obj._get_child_rel_name()

        with pytest.raises(NotImplementedError, match="must define 'cycle_error_message'"):
            obj._get_cycle_error_message()


@pytest.mark.django_db
class TestHierarchyQueryCounts:
    """Tests verifying that hierarchy traversals execute bounded queries without full-table scans."""

    @staticmethod
    def _chain(factory, parent_rel_name, depth):
        """Create a chain root -> ... -> leaf of ``depth + 1`` nodes, plus unrelated nodes."""
        nodes = [factory(name="Node 0")]
        for level in range(1, depth + 1):
            node = factory(name=f"Node {level}")
            getattr(node, parent_rel_name).add(nodes[-1])
            nodes.append(node)
        for i in range(10):
            factory(name=f"Unrelated {i}")
        return nodes

    @pytest.mark.parametrize(
        ("factory", "parent_rel_name"),
        [
            (PersonGroupFactory, "parent_groups"),
            (lambda name: GiftTag.objects.create(name=name), "parent_tags"),
        ],
        ids=["group", "tag"],
    )
    @pytest.mark.parametrize("depth", [1, 4])
    def test_descendants_use_one_recursive_query(
        self, django_assert_num_queries, factory, parent_rel_name, depth
    ):
        """get_descendants runs one recursive query whatever the depth."""
        nodes = self._chain(factory, parent_rel_name, depth)

        with django_assert_num_queries(1) as captured:
            descendants = nodes[0].get_descendants()

        assert set(descendants) == set(nodes[1:])
        assert "WITH RECURSIVE" in captured.captured_queries[0]["sql"]

    @pytest.mark.parametrize(
        ("factory", "parent_rel_name"),
        [
            (PersonGroupFactory, "parent_groups"),
            (lambda name: GiftTag.objects.create(name=name), "parent_tags"),
        ],
        ids=["group", "tag"],
    )
    @pytest.mark.parametrize("depth", [1, 4])
    def test_ancestors_use_one_recursive_query(
        self, django_assert_num_queries, factory, parent_rel_name, depth
    ):
        """get_ancestors runs one recursive query whatever the depth."""
        nodes = self._chain(factory, parent_rel_name, depth)

        with django_assert_num_queries(1) as captured:
            ancestors = nodes[-1].get_ancestors()

        assert set(ancestors) == set(nodes[:-1])
        assert "WITH RECURSIVE" in captured.captured_queries[0]["sql"]

    def test_traversal_terminates_on_existing_cycle(self):
        """A cycle already stored in the database does not loop and never returns the node."""
        first = PersonGroupFactory(name="First")
        second = PersonGroupFactory(name="Second")
        # Bypass the model validation to simulate legacy data
        second.parent_groups.add(first)
        first.parent_groups.add(second)

        assert first.get_descendants() == [second]
        assert first.get_ancestors() == [second]

    def test_diamond_hierarchy_returns_each_node_once(self):
        """A node reachable through several parents is returned once."""
        root = PersonGroupFactory(name="Root")
        left = PersonGroupFactory(name="Left")
        right = PersonGroupFactory(name="Right")
        bottom = PersonGroupFactory(name="Bottom")
        left.parent_groups.add(root)
        right.parent_groups.add(root)
        bottom.parent_groups.add(left, right)

        descendants = root.get_descendants()
        ancestors = bottom.get_ancestors()

        assert sorted(g.pk for g in descendants) == sorted([left.pk, right.pk, bottom.pk])
        assert sorted(g.pk for g in ancestors) == sorted([root.pk, left.pk, right.pk])

    def test_accessible_by_with_cascading_permission_uses_one_query(
        self, user, django_assert_num_queries
    ):
        """Cascading group permissions resolve inside a single query, at any depth."""
        nodes = self._chain(PersonGroupFactory, "parent_groups", 4)
        PersonGroupPermission.objects.create(
            user=user,
            group=nodes[1],
            permission_type=PermissionLevel.VIEWER,
            inherit_permissions=True,
        )

        with django_assert_num_queries(1):
            accessible = set(PersonGroup.objects.accessible_by(user))

        assert accessible == set(nodes[1:])

    def test_accessible_by_follows_hierarchy_changes_made_without_signals(self, user):
        """Access granted through a cascading permission follows the live hierarchy."""
        parent = PersonGroupFactory(name="Parent")
        child = PersonGroupFactory(name="Child")
        child.parent_groups.add(parent)
        PersonGroupPermission.objects.create(
            user=user,
            group=parent,
            permission_type=PermissionLevel.VIEWER,
            inherit_permissions=True,
        )
        assert child in PersonGroup.objects.accessible_by(user)

        # Detach the child with a queryset delete, which sends no m2m_changed signal
        PersonGroup.parent_groups.through.objects.filter(from_persongroup=child).delete()

        assert child not in PersonGroup.objects.accessible_by(user)

    def test_person_group_primary_ancestors_path_query_count(self, django_assert_num_queries):
        """get_primary_ancestors_path steps along parent relations without table scans."""
        root = PersonGroupFactory(name="Root")
        mid = PersonGroupFactory(name="Mid")
        leaf = PersonGroupFactory(name="Leaf")
        mid.parent_groups.add(root)
        leaf.parent_groups.add(mid)

        for i in range(10):
            PersonGroupFactory(name=f"Unrelated {i}")

        # Step 1: leaf -> mid (1 query)
        # Step 2: mid -> root (1 query)
        # Step 3: root -> no parent (1 query)
        with django_assert_num_queries(3) as captured:
            path = leaf.get_primary_ancestors_path()
        assert path == [root, mid]
        for query in captured.captured_queries:
            assert "WHERE" in query["sql"]
            assert "parent_groups" in query["sql"]

    def test_gift_tag_primary_ancestors_path_query_count(self, django_assert_num_queries):
        """GiftTag.get_primary_ancestors_path steps along parent relations without table scans."""
        root = GiftTag.objects.create(name="Root")
        mid = GiftTag.objects.create(name="Mid")
        leaf = GiftTag.objects.create(name="Leaf")
        mid.parent_tags.add(root)
        leaf.parent_tags.add(mid)

        for i in range(10):
            GiftTag.objects.create(name=f"Unrelated {i}")

        with django_assert_num_queries(3) as captured:
            path = leaf.get_primary_ancestors_path()
        assert path == [root, mid]
        for query in captured.captured_queries:
            assert "WHERE" in query["sql"]
            assert "parent_tags" in query["sql"]

    def test_accessible_by_ignores_non_cascading_and_other_users_permissions(self, user):
        """Only the user's own cascading permissions open the descendants."""
        other_user = UserFactory()
        nodes = self._chain(PersonGroupFactory, "parent_groups", 2)
        PersonGroupPermission.objects.create(
            user=user,
            group=nodes[0],
            permission_type=PermissionLevel.VIEWER,
            inherit_permissions=False,
        )
        PersonGroupPermission.objects.create(
            user=other_user,
            group=nodes[0],
            permission_type=PermissionLevel.OWNER,
            inherit_permissions=True,
        )

        assert set(PersonGroup.objects.accessible_by(user)) == {nodes[0]}
        assert set(PersonGroup.objects.accessible_by(other_user)) == set(nodes)

    def test_accessible_by_terminates_on_existing_cycle(self, user):
        """A cycle stored in the database does not break cascading permissions."""
        first = PersonGroupFactory(name="First")
        second = PersonGroupFactory(name="Second")
        second.parent_groups.add(first)
        first.parent_groups.add(second)
        PersonGroupPermission.objects.create(
            user=user,
            group=first,
            permission_type=PermissionLevel.VIEWER,
            inherit_permissions=True,
        )

        assert set(PersonGroup.objects.accessible_by(user)) == {first, second}

    def test_hierarchy_subquery_requires_a_single_column(self):
        """The start of a hierarchy subquery must select exactly one column."""
        with pytest.raises(ValueError, match="exactly one column"):
            PersonGroup.hierarchy_subquery(PersonGroup.objects.all())
        with pytest.raises(ValueError, match="exactly one column"):
            PersonGroup.hierarchy_subquery(PersonGroup.objects.values("pk", "name"))


HIERARCHY_MODELS = [
    pytest.param(PersonGroupFactory, "parent_groups", id="group"),
    pytest.param(lambda: GiftTag.objects.create(name="Tag"), "parent_tags", id="tag"),
]


@pytest.mark.django_db
class TestHierarchyIsNotCached:
    """The hierarchy is always read from the database: no cache to keep in sync."""

    @pytest.mark.parametrize(("factory", "parent_rel_name"), HIERARCHY_MODELS)
    def test_results_are_not_stored_in_the_cache(self, factory, parent_rel_name):
        parent, child = factory(), factory()
        getattr(child, parent_rel_name).add(parent)

        assert parent.get_descendants() == [child]
        assert child.get_ancestors() == [parent]

        model_name = parent._meta.model_name
        assert cache.get(f"{model_name}_descendants_{parent.pk}") is None
        assert cache.get(f"{model_name}_ancestors_{child.pk}") is None

    @pytest.mark.parametrize(("factory", "parent_rel_name"), HIERARCHY_MODELS)
    def test_changes_made_without_signals_are_seen(self, factory, parent_rel_name):
        parent, child = factory(), factory()
        edges = getattr(child, parent_rel_name)
        edges.add(parent)
        assert parent.get_descendants() == [child]

        # A queryset delete on the link table sends no m2m_changed signal
        edges.through.objects.all().delete()

        assert parent.get_descendants() == []
        assert child.get_ancestors() == []

    @pytest.mark.parametrize(("factory", "parent_rel_name"), HIERARCHY_MODELS)
    def test_saving_a_node_runs_no_hierarchy_query(
        self, django_assert_num_queries, factory, parent_rel_name
    ):
        parent, child = factory(), factory()
        getattr(child, parent_rel_name).add(parent)

        with django_assert_num_queries(1):
            child.save()

    @pytest.mark.parametrize(("factory", "parent_rel_name"), HIERARCHY_MODELS)
    def test_linking_nodes_only_touches_the_link_table(self, factory, parent_rel_name):
        parent, child = factory(), factory()
        edges = getattr(child, parent_rel_name)

        with CaptureQueriesContext(connection) as captured:
            edges.add(parent)
            edges.remove(parent)

        link_table = edges.through._meta.db_table
        assert all(link_table in query["sql"] for query in captured.captured_queries)


@pytest.mark.django_db
class TestPrimaryAncestorsPathWithin:
    """The breadcrumb path can be limited to the ancestors inside a queryset."""

    @pytest.mark.parametrize(("factory", "parent_rel_name"), HIERARCHY_MODELS)
    def test_ancestors_outside_the_queryset_are_left_out_in_order(
        self, django_assert_num_queries, factory, parent_rel_name
    ):
        root, hidden, parent, node = factory(), factory(), factory(), factory()
        getattr(hidden, parent_rel_name).add(root)
        getattr(parent, parent_rel_name).add(hidden)
        getattr(node, parent_rel_name).add(parent)
        within = type(node).objects.exclude(pk=hidden.pk)

        assert node.get_primary_ancestors_path() == [root, hidden, parent]
        # One query per level walked (3 parents and the root's empty parents), one to filter
        with django_assert_num_queries(5):
            path = node.get_primary_ancestors_path(within=within)
        assert path == [root, parent]

    def test_root_path_needs_no_filter_query(self, django_assert_num_queries):
        root = PersonGroupFactory()

        with django_assert_num_queries(1):
            assert root.get_primary_ancestors_path(within=PersonGroup.objects.all()) == []
