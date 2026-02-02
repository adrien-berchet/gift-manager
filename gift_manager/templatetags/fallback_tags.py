"""Template tags for progressive enhancement fallbacks."""

from django import template

register = template.Library()


@register.filter
def lookup(dictionary, key):
    """Look up a key in a dictionary."""
    if isinstance(dictionary, dict):
        return dictionary.get(key, '')

    # Handle object attribute lookup
    if hasattr(dictionary, key):
        return getattr(dictionary, key)

    return ''


@register.filter
def add_no_js(url):
    """Add no_js=1 parameter to URL."""
    if not url:
        return url

    separator = '&' if '?' in url else '?'
    return f"{url}{separator}no_js=1"


@register.inclusion_tag('gift_manager/fallback/includes/fallback_actions.html')
def fallback_actions(object, object_type):
    """Render fallback action buttons for an object."""
    return {
        'object': object,
        'object_type': object_type,
    }


@register.inclusion_tag('gift_manager/fallback/includes/fallback_pagination.html')
def fallback_pagination(page_obj, request):
    """Render fallback pagination."""
    return {
        'page_obj': page_obj,
        'request': request,
    }


@register.simple_tag
def fallback_url(view_name, *args, **kwargs):
    """Generate URL with no_js parameter."""
    from django.urls import reverse

    url = reverse(view_name, args=args, kwargs=kwargs)
    separator = '&' if '?' in url else '?'
    return f"{url}{separator}no_js=1"


@register.filter
def is_fallback_mode(request):
    """Check if request is in fallback mode."""
    return (
        request.GET.get('no_js') == '1' or
        request.POST.get('no_js') == '1' or
        not request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest'
    )


@register.inclusion_tag('gift_manager/fallback/includes/browser_notice.html')
def browser_compatibility_notice(request):
    """Show browser compatibility notice if needed."""
    user_agent = request.META.get('HTTP_USER_AGENT', '').lower()

    # Check for very old browsers
    old_browsers = [
        ('Internet Explorer 8', 'msie 8'),
        ('Internet Explorer 9', 'msie 9'),
        ('Internet Explorer 10', 'msie 10'),
    ]

    detected_browser = None
    for browser_name, browser_string in old_browsers:
        if browser_string in user_agent:
            detected_browser = browser_name
            break

    return {
        'show_notice': detected_browser is not None,
        'browser_name': detected_browser,
        'is_fallback': is_fallback_mode(request),
    }


@register.filter
def supports_feature(request, feature):
    """Check if browser supports a specific feature."""
    user_agent = request.META.get('HTTP_USER_AGENT', '').lower()

    feature_support = {
        'css3': not any(old in user_agent for old in ['msie 6', 'msie 7', 'msie 8']),
        'javascript': request.GET.get('no_js') != '1',
        'ajax': 'xmlhttprequest' in request.META.get('HTTP_ACCEPT', '').lower(),
        'modern': not any(old in user_agent for old in ['msie', 'opera/9', 'firefox/3']),
    }

    return feature_support.get(feature, True)


@register.simple_tag(takes_context=True)
def fallback_form_action(context, form_action=None):
    """Generate form action URL for fallback mode."""
    request = context['request']

    if form_action:
        url = form_action
    else:
        url = request.path

    # Add no_js parameter if not already present
    if 'no_js=1' not in url:
        separator = '&' if '?' in url else '?'
        url += f"{separator}no_js=1"

    return url


@register.inclusion_tag('gift_manager/fallback/includes/fallback_search.html')
def fallback_search_form(request, placeholder="Search..."):
    """Render fallback search form."""
    return {
        'request': request,
        'placeholder': placeholder,
        'search_value': request.GET.get('search', ''),
    }
