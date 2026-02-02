"""Performance optimization mixins for views."""

import json
import logging
import time
from functools import wraps
from typing import Any, Dict, List, Optional

from django.core.cache import cache
from django.db import connection
from django.db.models import Prefetch, QuerySet
from django.http import HttpRequest, HttpResponse
from django.utils.cache import get_cache_key
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_headers

from gift_manager.models import Event, Gift, GiftTag, Person, PersonGroup, Relation

logger = logging.getLogger(__name__)


def log_queries(func):
    """Decorator to log database queries for performance monitoring."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        initial_queries = len(connection.queries)
        start_time = time.time()

        result = func(*args, **kwargs)

        end_time = time.time()
        query_count = len(connection.queries) - initial_queries
        execution_time = (end_time - start_time) * 1000  # Convert to milliseconds

        if query_count > 5 or execution_time > 100:  # Log if > 5 queries or > 100ms
            logger.warning(
                f"Performance warning in {func.__name__}: "
                f"{query_count} queries, {execution_time:.2f}ms"
            )

        return result
    return wrapper


class QueryOptimizationMixin:
    """Mixin to optimize database queries for AJAX endpoints."""

    # Override in subclasses to specify which related fields to prefetch
    prefetch_related_fields: List[str] = []
    select_related_fields: List[str] = []

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
        elif model == Gift:
            return self.optimize_gift_queryset(queryset)
        elif model == Event:
            return self.optimize_event_queryset(queryset)
        elif model == Relation:
            return self.optimize_relation_queryset(queryset)
        elif model == PersonGroup:
            return self.optimize_person_group_queryset(queryset)
        elif model == GiftTag:
            return self.optimize_gift_tag_queryset(queryset)

        return queryset

    def optimize_person_queryset(self, queryset: QuerySet) -> QuerySet:
        """Optimize Person queryset."""
        return queryset.prefetch_related(
            'groups',
            'shared_with',
            Prefetch('gifts', queryset=Gift.objects.select_related('event')),
            Prefetch('events', queryset=Event.objects.prefetch_related('shared_with'))
        )

    def optimize_gift_queryset(self, queryset: QuerySet) -> QuerySet:
        """Optimize Gift queryset."""
        return queryset.select_related('event').prefetch_related(
            'tags',
            'shared_with',
            'persons',
            'groups'
        )

    def optimize_event_queryset(self, queryset: QuerySet) -> QuerySet:
        """Optimize Event queryset."""
        return queryset.prefetch_related(
            'shared_with',
            Prefetch('gifts', queryset=Gift.objects.prefetch_related('tags')),
            'persons',
            'groups'
        )

    def optimize_relation_queryset(self, queryset: QuerySet) -> QuerySet:
        """Optimize Relation queryset."""
        return queryset.select_related('gift', 'event').prefetch_related(
            'persons',
            'groups',
            'shared_with'
        )

    def optimize_person_group_queryset(self, queryset: QuerySet) -> QuerySet:
        """Optimize PersonGroup queryset."""
        return queryset.prefetch_related(
            'persons',
            'shared_with',
            'parent_groups',
            'child_groups'
        )

    def optimize_gift_tag_queryset(self, queryset: QuerySet) -> QuerySet:
        """Optimize GiftTag queryset."""
        return queryset.prefetch_related(
            'shared_with',
            'parent_tags',
            'child_tags',
            Prefetch('gifts', queryset=Gift.objects.select_related('event'))
        )


class CachingMixin:
    """Mixin to add intelligent caching for AJAX responses."""

    # Cache timeout in seconds (default: 5 minutes)
    cache_timeout: int = 300

    # Cache key prefix
    cache_key_prefix: str = "ajax_response"

    # Whether to vary cache by user
    vary_by_user: bool = True

    # Whether to vary cache by query parameters
    vary_by_params: bool = True

    def get_cache_key(self, request: HttpRequest) -> str:
        """Generate cache key for the request."""
        key_parts = [self.cache_key_prefix, request.path]

        if self.vary_by_user and request.user.is_authenticated:
            key_parts.append(f"user_{request.user.id}")

        if self.vary_by_params and request.GET:
            # Sort parameters for consistent cache keys
            params = sorted(request.GET.items())
            param_string = "&".join(f"{k}={v}" for k, v in params)
            key_parts.append(f"params_{hash(param_string)}")

        return ":".join(key_parts)

    def get_cached_response(self, request: HttpRequest) -> Optional[HttpResponse]:
        """Get cached response if available."""
        if not self.should_cache_response(request):
            return None

        cache_key = self.get_cache_key(request)
        cached_data = cache.get(cache_key)

        if cached_data:
            logger.debug(f"Cache hit for key: {cache_key}")
            response = HttpResponse(
                cached_data['content'],
                content_type=cached_data['content_type'],
                status=cached_data['status']
            )

            # Restore headers
            for header, value in cached_data.get('headers', {}).items():
                response[header] = value

            return response

        return None

    def cache_response(self, request: HttpRequest, response: HttpResponse) -> None:
        """Cache the response."""
        if not self.should_cache_response(request) or response.status_code != 200:
            return

        cache_key = self.get_cache_key(request)

        # Prepare data for caching
        cached_data = {
            'content': response.content.decode('utf-8'),
            'content_type': response.get('Content-Type', 'text/html'),
            'status': response.status_code,
            'headers': dict(response.items())
        }

        cache.set(cache_key, cached_data, self.cache_timeout)
        logger.debug(f"Cached response for key: {cache_key}")

    def should_cache_response(self, request: HttpReques

        return True

    def invalidate_cache_pattern(self, pattern: str) -> None:
        """Invalidate cache entries matching pattern."""
        # This would require a more sophisticated cache backend
        # For now, we'll just log the invalidation
        logger.info(f"Cache invalidation requested for pattern: {pattern}")


class AjaxOptimizationMixin(QueryOptimizationMixin, CachingMixin):
    """Combined mixin for AJAX request optimization."""

    @method_decorator(log_queries)
    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """Optimized dispatch with caching and query optimization."""
        # Check for cached response first
        if request.method == 'GET':
            cached_response = self.get_cached_response(request)
            if cached_response:
                return cached_response

        # Process request normally
        response = super().dispatch(request, *args, **kwargs)

        # Cache successful GET responses
        if request.method == 'GET' and response.status_code == 200:
            self.cache_response(request, response)

        return response

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        """Add performance metrics to context."""
        context = super().get_context_data(**kwargs)

        # Add query count for debugging
        if hasattr(self.request, 'user') and self.request.user.is_staff:
            context['_debug_query_count'] = len(connection.queries)

        return context


class BatchOperationMixin:
    """Mixin to optimize batch operations."""

    def perform_batch_operation(self, operation: str, object_ids: List[str]) -> Dict[str, Any]:
        """Perform batch operation with optimization."""
        results = {
            'success': [],
            'errors': [],
            'total': len(object_ids)
        }

        if operation == 'delete':
            results.update(self.batch_delete(object_ids))
        elif operation == 'update':
            results.update(self.batch_update(object_ids))
        else:
            results['errors'].append(f"Unknown operation: {operation}")

        return results

    def batch_delete(self, object_ids: List[str]) -> Dict[str, Any]:
        """Optimized batch delete operation."""
        try:
            # Use bulk delete for efficiency
            queryset = self.get_queryset().filter(pk__in=object_ids)
            deleted_count, _ = queryset.delete()

            return {
                'success': object_ids[:deleted_count],
                'deleted_count': deleted_count
            }
        except Exception as e:
            logger.error(f"Batch delete error: {e}")
            return {'errors': [str(e)]}

    def batch_update(self, object_ids: List[str], update_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """Optimized batch update operation."""
        if not update_data:
            return {'errors': ['No update data provided']}

        try:
            # Use bulk update for efficiency
            queryset = self.get_queryset().filter(pk__in=object_ids)
            updated_count = queryset.update(**update_data)

            return {
                'success': object_ids[:updated_count],
                'updated_count': updated_count
            }
        except Exception as e:
            logger.error(f"Batch update error: {e}")
            return {'errors': [str(e)]}


class ResponseCompressionMixin:
    """Mixin to compress AJAX responses."""

    def finalize_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        """Add compression headers for AJAX responses."""
        if hasattr(super(), 'finalize_response'):
            response = super().finalize_response(request, response)

        # Add compression hint for large responses
        if len(response.content) > 1024:  # > 1KB
            response['Vary'] = 'Accept-Encoding'

        return response


class PerformanceHeadersMixin:
    """Mixin to add performance-related headers."""

    def add_performance_headers(self, response: HttpResponse) -> HttpResponse:
        """Add performance-related headers to response."""
        # Add cache control headers
        if hasattr(self, 'cache_timeout'):
            response['Cache-Control'] = f'max-age={self.cache_timeout}, private'

        # Add ETag for conditional requests
        if hasattr(self, 'get_etag'):
            etag = self.get_etag()
            if etag:
                response['ETag'] = etag

        # Add timing information for debugging
        if hasattr(self.request, 'user') and self.request.user.is_staff:
            query_count = len(connection.queries)
            response['X-Debug-Query-Count'] = str(query_count)

        return response

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """Add performance headers to response."""
        response = super().dispatch(request, *args, **kwargs)
        return self.add_performance_headers(response)


class OptimizedListMixin(AjaxOptimizationMixin, BatchOperationMixin, ResponseCompressionMixin, PerformanceHeadersMixin):
    """Complete optimization mixin for list views."""

    # Pagination settings for performance
    paginate_by = 25

    def get_queryset(self) -> QuerySet:
        """Get optimized queryset for list views."""
        queryset = super().get_queryset()

        # Apply ordering for consistent pagination
        if not queryset.ordered:
            queryset = queryset.order_by('-created_at' if hasattr(queryset.model, 'created_at') else 'pk')

        return queryset

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        """Add optimized context data."""
        context = super().get_context_data(**kwargs)

        # Add pagination info for AJAX requests
        if hasattr(self, 'is_htmx') and self.is_htmx:
            page_obj = context.get('page_obj')
            if page_obj:
                context['pagination_info'] = {
                    'current_page': page_obj.number,
                    'total_pages': page_obj.paginator.num_pages,
                    'has_next': page_obj.has_next(),
                    'has_previous': page_obj.has_previous(),
                    'total_count': page_obj.paginator.count
                }

        return context


class OptimizedDetailMixin(AjaxOptimizationMixin, ResponseCompressionMixin, PerformanceHeadersMixin):
    """Complete optimization mixin for detail views."""

    def get_object(self, queryset: Optional[QuerySet] = None) -> Any:
        """Get optimized object with related data."""
        if queryset is None:
            queryset = self.get_queryset()

        # Apply optimizations before getting object
        obj = super().get_object(queryset)

        return obj


class OptimizedFormMixin(AjaxOptimizationMixin, PerformanceHeadersMixin):
    """Complete optimization mixin for form views."""

    def form_valid(self, form) -> HttpResponse:
        """Handle form validation with cache invalidation."""
        response = super().form_valid(form)

        # Invalidate related cache entries
        if hasattr(self, 'invalidate_cache_pattern'):
            model_name = self.model._meta.model_name
            self.invalidate_cache_pattern(f"*{model_name}*")

        return response
