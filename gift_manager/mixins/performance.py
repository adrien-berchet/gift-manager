"""Performance optimization mixins for views."""

import logging
from typing import Any

from django.db.models import Prefetch
from django.db.models import QuerySet

from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import GiftTag
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import Relation

logger = logging.getLogger(__name__)


class QueryOptimizationMixin:
    """Mixin to optimize database queries for AJAX endpoints."""

    # Override in subclasses to specify which related fields to prefetch
    prefetch_related_fields: list[str] = []
    select_related_fields: list[str] = []

    def get_queryset(self) -> QuerySet:
        """Optimize queryset with prefetch_related and select_related."""
        queryset = super().get_queryset()

        # Apply select_related for foreign key relationships
        if self.select_related_fields:
            queryset = queryset.select_related(*self.select_related_fields)

        # Apply prefetch_related for many-to-many and reverse foreign key relationships
        if self.prefetch_related_fields:
            queryset = queryset.prefetch_related(*self.prefetch_related_fields)

        # Apply model-specific optimizations
        queryset = self.optimize_model_queryset(queryset)

        return queryset

    def optimize_model_queryset(self, queryset: QuerySet) -> QuerySet:
        """Apply model-specific query optimizations."""
        model = queryset.model

        if model == Person:
            return self.optimize_person_queryset(queryset)
        if model == Gift:
            return self.optimize_gift_queryset(queryset)
        if model == Event:
            return self.optimize_event_queryset(queryset)
        if model == Relation:
            return self.optimize_relation_queryset(queryset)
        if model == PersonGroup:
            return self.optimize_person_group_queryset(queryset)
        if model == GiftTag:
            return self.optimize_gift_tag_queryset(queryset)

        return queryset

    def optimize_person_queryset(self, queryset: QuerySet) -> QuerySet:
        """Optimize Person queryset."""
        return queryset.prefetch_related(
            "groups",
            "shared_with",
            Prefetch("persons", queryset=Relation.objects.select_related("gift", "event")),
        )

    def optimize_gift_queryset(self, queryset: QuerySet) -> QuerySet:
        """Optimize Gift queryset."""
        return queryset.select_related("event").prefetch_related(
            "tags", "shared_with", "persons", "groups"
        )

    def optimize_event_queryset(self, queryset: QuerySet) -> QuerySet:
        """Optimize Event queryset."""
        return queryset.prefetch_related(
            "shared_with",
            Prefetch("gifts", queryset=Gift.objects.prefetch_related("tags")),
            "persons",
            "groups",
        )

    def optimize_relation_queryset(self, queryset: QuerySet) -> QuerySet:
        """Optimize Relation queryset."""
        return queryset.select_related("gift", "event").prefetch_related(
            "persons", "groups", "shared_with"
        )

    def optimize_person_group_queryset(self, queryset: QuerySet) -> QuerySet:
        """Optimize PersonGroup queryset."""
        return queryset.prefetch_related("persons", "shared_with", "parent_groups", "child_groups")

    def optimize_gift_tag_queryset(self, queryset: QuerySet) -> QuerySet:
        """Optimize GiftTag queryset."""
        return queryset.prefetch_related(
            "shared_with",
            "parent_tags",
            "child_tags",
            Prefetch("gifts", queryset=Gift.objects.select_related("event")),
        )


class BatchOperationMixin:
    """Mixin to optimize batch operations."""

    def perform_batch_operation(self, operation: str, object_ids: list[str]) -> dict[str, Any]:
        """Perform batch operation with optimization."""
        results = {"success": [], "errors": [], "total": len(object_ids)}

        if operation == "delete":
            results.update(self.batch_delete(object_ids))
        elif operation == "update":
            results.update(self.batch_update(object_ids))
        else:
            results["errors"].append(f"Unknown operation: {operation}")

        return results

    def batch_delete(self, object_ids: list[str]) -> dict[str, Any]:
        """Optimized batch delete operation."""
        try:
            # Use bulk delete for efficiency
            queryset = self.get_queryset().filter(pk__in=object_ids)
            deleted_count, _ = queryset.delete()

            return {"success": object_ids[:deleted_count], "deleted_count": deleted_count}
        except Exception as e:
            logger.error(f"Batch delete error: {e}")
            return {"errors": [str(e)]}

    def batch_update(
        self, object_ids: list[str], update_data: dict[str, Any] = None
    ) -> dict[str, Any]:
        """Optimized batch update operation."""
        if not update_data:
            return {"errors": ["No update data provided"]}

        try:
            # Use bulk update for efficiency
            queryset = self.get_queryset().filter(pk__in=object_ids)
            updated_count = queryset.update(**update_data)

            return {"success": object_ids[:updated_count], "updated_count": updated_count}
        except Exception as e:
            logger.error(f"Batch update error: {e}")
            return {"errors": [str(e)]}
