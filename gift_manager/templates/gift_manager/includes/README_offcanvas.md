# Reusable Offcanvas Panel Template

This document explains how to use the reusable offcanvas panel template system for the modern UX interface.

## Overview

The offcanvas panel system provides a consistent way to display forms and detailed content in slide-out panels that are:
- **Responsive**: Full-screen on mobile devices (< 768px), side panels on desktop
- **Accessible**: Proper focus management, keyboard navigation, and ARIA attributes
- **HTMX-integrated**: Seamless AJAX loading with loading states and error handling
- **Touch-friendly**: Optimized for mobile interactions

## Files

- `offcanvas_base.html` - Main offcanvas template with two panels (edit and detail)
- `form_partial.html` - Example form template for use within offcanvas panels
- `modern-ux.css` - Enhanced CSS styles for responsive behavior and mobile support

## Usage

### 1. Basic Structure

The template provides two main panels:

```html
<!-- Edit/Create Panel -->
<div id="editPanel" class="offcanvas offcanvas-end offcanvas-panel">
  <!-- Content loaded dynamically -->
</div>

<!-- Detail Panel -->
<div id="detailPanel" class="offcanvas offcanvas-end offcanvas-panel">
  <!-- Content loaded dynamically -->
</div>
```

### 2. Triggering Panels

Use data attributes on buttons to trigger panels:

```html
<!-- Edit button -->
<button data-action="edit"
        data-edit-url="/entities/123/edit/"
        class="btn btn-primary">
  Edit
</button>

<!-- Create button -->
<button data-action="create"
        data-create-url="/entities/create/"
        class="btn btn-success">
  Create
</button>

<!-- Detail button -->
<button data-action="detail"
        data-detail-url="/entities/123/"
        class="btn btn-info">
  View Details
</button>
```

### 3. Form Structure

When creating forms for offcanvas panels, use this structure:

```html
<form method="post"
      hx-post="{{ form_action_url }}"
      hx-target="#offcanvasContent"
      hx-swap="innerHTML"
      class="offcanvas-form">

  {% csrf_token %}

  <!-- Form fields -->
  <div class="form-fields">
    {{ form.as_p }}
  </div>

  <!-- Sticky form actions -->
  <div class="panel-form-actions">
    <button type="button" class="btn btn-secondary" data-bs-dismiss="offcanvas">
      Cancel
    </button>
    <button type="submit" class="btn btn-primary">
      Save
    </button>
  </div>
</form>
```

### 4. Django View Integration

Create HTMX-compatible views:

```python
class PersonEditView(HTMXResponseMixin, UpdateView):
    model = Person
    form_class = PersonForm
    template_name = 'persons/person_form.html'
    htmx_template_name = 'persons/person_form_partial.html'

    def get_success_url(self):
        if self.is_htmx:
            return None  # No redirect for HTMX requests
        return reverse('gift_manager:persons')
```

## Features

### Responsive Behavior

- **Desktop (≥768px)**: 400px wide side panel (480px on large screens ≥1200px)
- **Mobile (<768px)**: Full-screen overlay for better usability
- **Touch-friendly**: 44px minimum touch targets, optimized spacing

### Loading States

The template includes built-in loading and error states:

```javascript
// Show loading state
showOffcanvasLoading('editPanel');

// Hide loading state
hideOffcanvasLoading('editPanel');

// Show error state
showOffcanvasError('Error message', 'editPanel');
```

### Accessibility Features

- **Focus management**: Automatic focus on first form field
- **Keyboard navigation**: Tab trapping within panels
- **ARIA attributes**: Proper labeling and descriptions
- **Screen reader support**: Dynamic content announcements
- **Keyboard shortcuts**: Escape to close, Ctrl+S to save

### Mobile Enhancements

- **Full-screen panels**: Automatic conversion on small screens
- **Touch gestures**: Swipe-friendly interactions
- **Keyboard handling**: Proper positioning when virtual keyboard appears
- **Reduced motion**: Respects user preferences

## CSS Classes

Key CSS classes for customization:

- `.offcanvas-panel` - Base panel class
- `.offcanvas-mobile-fullscreen` - Applied automatically on mobile
- `.panel-form-actions` - Sticky form action buttons
- `.loading-state` - Loading indicator container
- `.error-state` - Error message container

## JavaScript Events

Custom events for integration:

```javascript
// Listen for panel events
document.addEventListener('offcanvas:show', function(e) {
  // Panel is about to show
});

document.addEventListener('offcanvas:retry', function(e) {
  // User clicked retry button
  const panelId = e.detail.panelId;
});
```

## Requirements Satisfied

This implementation satisfies the following requirements:

- **Requirement 2.1**: Edit forms in slide-out panels
- **Requirement 9.2**: Responsive behavior for mobile (full-screen on small screens)
- **Bootstrap 5 Integration**: Uses native Bootstrap offcanvas components
- **HTMX Integration**: Seamless AJAX form loading and submission
- **Progressive Enhancement**: Works without JavaScript (falls back to regular forms)

## Browser Support

- Modern browsers with CSS Grid and Flexbox support
- Bootstrap 5 compatible browsers
- Mobile browsers with touch support
- Screen readers and assistive technologies
