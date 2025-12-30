# CLAUDE.md - AI Assistant Guide for Gift Manager

This document provides comprehensive guidance for AI assistants working on the Gift Manager codebase. Last updated: 2025-12-30

## Table of Contents

1. [Project Overview](#project-overview)
2. [Repository Structure](#repository-structure)
3. [Tech Stack](#tech-stack)
4. [Development Workflow](#development-workflow)
5. [Code Conventions](#code-conventions)
6. [Testing Guidelines](#testing-guidelines)
7. [Architecture Patterns](#architecture-patterns)
8. [Database & Models](#database--models)
9. [Permission System](#permission-system)
10. [Frontend Guidelines](#frontend-guidelines)
11. [Internationalization](#internationalization)
12. [Common Tasks](#common-tasks)
13. [Important Gotchas](#important-gotchas)

## Project Overview

Gift Manager is a Django 5.1 web application for managing gifts, persons, events, and their relationships with a sophisticated permission and sharing system.

**Key Features:**
- Multi-user gift tracking with granular permissions (NONE, VIEWER, EDITOR, OWNER)
- Hierarchical person groups and gift tags with cascade permissions
- Event management with recurrence support
- Email encryption for privacy (Fernet symmetric encryption)
- Internationalization (English, French)
- Modern responsive UI with Grid.js tables and HTMX

**Tech Stack Snapshot:**
- Django 5.1.x + PostgreSQL 15
- django-allauth for authentication
- WhiteNoise for static files
- Bootstrap 5 + Grid.js + HTMX
- pytest + Playwright for testing
- Docker + Gunicorn/Uvicorn for deployment

## Repository Structure

```
gift-manager/
├── GiftManager/              # Django project configuration
│   ├── settings/            # Environment-specific settings
│   │   ├── base.py          # Base configuration
│   │   ├── development.py   # Development overrides
│   │   ├── production.py    # Production overrides
│   │   └── testing.py       # Testing overrides
│   ├── urls.py             # Root URL configuration
│   ├── views.py            # Project-level views (account management)
│   ├── wsgi.py / asgi.py   # WSGI/ASGI applications
│
├── gift_manager/            # Main Django application
│   ├── models.py            # Database models (1100+ lines)
│   ├── forms.py             # Django forms
│   ├── services.py          # Business logic (PermissionService)
│   ├── permissions.py       # Permission facade
│   ├── adapters.py          # Custom allauth adapter
│   ├── email_encoding.py    # Email encryption utilities
│   ├── translation.py       # Model translation config
│   ├── views/               # Views organized by domain
│   │   ├── base.py          # Base classes and mixins
│   │   ├── person.py        # Person CRUD views
│   │   ├── gift.py          # Gift CRUD views
│   │   ├── event.py         # Event CRUD views
│   │   ├── person_group.py  # Group views with hierarchy
│   │   ├── gift_tag.py      # Tag views with hierarchy
│   │   ├── relation.py      # Relation CRUD views
│   │   ├── profile.py       # User profile and invitations
│   │   ├── sharing.py       # Permission sharing views
│   │   └── common.py        # Home, search views
│   ├── templates/           # HTML templates
│   │   ├── gift_manager/    # App-specific templates
│   │   ├── allauth/         # Authentication templates
│   │   └── account/         # Account management templates
│   ├── static/              # Static assets (CSS, JS, images)
│   ├── migrations/          # Database migrations (22 total)
│   ├── tests/               # Test suite
│   │   ├── conftest.py      # pytest fixtures
│   │   ├── factories.py     # Factory Boy factories
│   │   ├── test_*.py        # Test modules
│   │   ├── views/           # View tests
│   │   └── forms/           # Form tests
│   ├── templatetags/        # Custom template tags
│   └── urls.py             # App URL configuration
│
├── locale/                  # i18n translations
│   └── fr/LC_MESSAGES/      # French translations
├── staticfiles/             # Collected static files
├── .github/workflows/       # CI/CD (GitHub Actions)
├── pyproject.toml          # Dependencies and tool config
├── docker-compose.yml      # Development Docker setup
└── Dockerfile              # Production Docker image
```

## Tech Stack

### Backend
- **Django 5.1.x** - Web framework
- **PostgreSQL 15** - Primary database (JSONB features required)
- **django-allauth 0.61+** - Authentication and email verification
- **cryptography 42.0+** - Email encryption (Fernet)
- **django-modeltranslation 0.18+** - Model field translation
- **django-redis 5+** - Caching backend
- **Gunicorn/Uvicorn** - Application servers
- **WhiteNoise 6.6+** - Static file serving

### Frontend
- **Bootstrap 5** - CSS framework
- **Grid.js** - Modern table library (replaced DataTables)
- **HTMX** - Dynamic HTML updates
- **Vanilla JavaScript** - Minimal dependencies

### Testing
- **pytest 8+** - Test framework
- **pytest-django 4+** - Django integration
- **pytest-playwright 0.7+** - Browser automation
- **factory-boy 3.3+** - Test data generation
- **faker 24+** - Fake data

### Code Quality
- **ruff 0.3+** - Fast linter and formatter
- **isort** - Import sorting (black profile)
- **flake8** - Code style checking
- **pydocstyle** - Docstring validation
- **codespell** - Spelling checker
- **pre-commit 3+** - Git hook automation
- **mypy** - Type checking (optional)

## Development Workflow

### Setting Up Development Environment

1. **Clone and install dependencies:**
   ```bash
   git clone <repository>
   cd gift-manager
   pip install -e ".[dev]"
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

3. **Run with Docker Compose (recommended):**
   ```bash
   docker-compose up
   ```

4. **Or run locally:**
   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   python manage.py runserver
   ```

### Pre-commit Hooks

**IMPORTANT:** All commits must pass pre-commit checks. Install hooks:
```bash
pre-commit install
```

**Hooks run on commit:**
- `ruff` - Linting and formatting
- `isort` - Import sorting
- `flake8` - Code style
- `pydocstyle` - Docstring validation
- `codespell` - Spell checking
- `commitlint` - Commit message validation
- Standard hooks (trailing whitespace, end-of-file, merge conflicts)

**Manual execution:**
```bash
pre-commit run --all-files
```

### Commit Message Convention

**Follow Conventional Commits:**
```
Type(scope): Subject in sentence case

Body (optional)

Footer (optional)
```

**Valid types:**
- `Feat` - New feature
- `Fix` - Bug fix
- `Docs` - Documentation changes
- `Style` - Code style changes (formatting)
- `Refactor` - Code refactoring
- `Perf` - Performance improvements
- `Test` - Test additions/changes
- `Build` - Build system changes
- `CI` - CI/CD changes
- `Chore` - Maintenance tasks
- `Revert` - Revert previous commit
- `Release` - Release commits
- `Deprecate` - Deprecation notices

**Examples:**
```
Feat(gifts): Add tag filtering to gift list view
Fix(permissions): Resolve cascade permission inheritance bug
Docs: Update API documentation for permission service
Refactor(models): Optimize QuerySet for person groups
Test(views): Add missing tests for gift detail view
```

**Enforcement:**
- Max length: 100 characters
- commitlint pre-commit hook validates format
- CI pipeline checks commit messages

### CI/CD Pipeline

**GitHub Actions Workflow** (`.github/workflows/ci.yml`)

**Triggers:**
- Push to `main`, `develop` branches
- Pull requests to `main`, `develop`

**Test Matrix:**
- Python 3.10, 3.11, 3.12
- PostgreSQL 15

**Pipeline Steps:**
1. Install dependencies from `pyproject.toml`
2. Run database migrations
3. Execute test suite with coverage
4. Upload coverage to Codecov (Python 3.12 only)
5. Security scans: Bandit, pip-audit
6. Build package verification

## Code Conventions

### Python Style

**Line Length:** 100 characters (ruff, isort, flake8)

**Formatting:**
- Black-compatible (ruff format)
- Google-style docstrings
- Single-line imports (isort force-single-line)

**Import Order:**
1. Standard library
2. Third-party packages
3. Django imports
4. Local application imports

Example:
```python
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models

from .email_encoding import encode_email
from .permissions import PermissionLevel
```

### Naming Conventions

**Models:**
- Singular nouns: `Person`, `Gift`, `Event`
- Descriptive names: `PersonGroup`, `GiftTag`, `RelationStatus`
- Permission models: `<Model>Permission` (e.g., `GiftPermission`)

**Views:**
- Class-based views: `<Model><Action>View` (e.g., `GiftListView`, `PersonUpdateView`)
- Mixins: `<Purpose>Mixin` (e.g., `FilterByUserMixin`, `PermissionRequiredMixin`)

**QuerySets/Managers:**
- QuerySet: `<Model>QuerySet` (e.g., `PersonQuerySet`)
- Manager: `<Model>Manager` (e.g., `PersonManager`)

**URLs:**
- Kebab-case: `person-list`, `gift-tag-detail`, `share-objects`
- RESTful conventions: `<resource>-<action>`

**Template Names:**
- Snake_case: `person_list.html`, `gift_detail.html`, `edit_form.html`

### Database Conventions

**Field Names:**
- Primary keys: `<model>_id` (UUID, e.g., `person_id`, `gift_id`)
- Foreign keys: `<model>` (e.g., `person`, `gift`, `event`)
- Boolean fields: `is_<attribute>` (e.g., `is_public`, `is_expired`)
- Dates: `<purpose>_date` (e.g., `creation_date`, `due_date`, `usual_date`)

**Meta Options:**
- Always set `verbose_name` and `verbose_name_plural` with `gettext_lazy()`
- Use `unique_together` for composite unique constraints
- Add `ordering` for default sort order when appropriate

**Indexes:**
- Add `db_index=True` for frequently queried fields
- Composite indexes for common filter combinations

## Testing Guidelines

### Test Organization

**Location:** `/home/user/gift-manager/gift_manager/tests/`

**Structure:**
```
tests/
├── conftest.py              # pytest fixtures
├── factories.py             # Factory Boy factories
├── test_models.py          # Model tests
├── test_permissions.py     # Permission system tests
├── test_email_encoding.py  # Email encryption tests
├── test_frontend.py        # Playwright e2e tests
├── test_nested_groups.py   # Group hierarchy tests
├── views/                  # View-specific tests
│   ├── test_base.py
│   ├── test_person_group_detail.py
│   ├── test_gift_detail.py
│   └── ...
└── forms/                  # Form-specific tests
    └── test_person_group_form_child_groups.py
```

### Running Tests

**Full test suite:**
```bash
pytest
```

**With coverage:**
```bash
pytest --cov=gift_manager --cov-report=html
```

**Specific test file:**
```bash
pytest gift_manager/tests/test_permissions.py
```

**Exclude slow/frontend tests:**
```bash
pytest -m "not slow and not frontend"
```

**Frontend tests only:**
```bash
pytest -m frontend
```

### Writing Tests

**Use factories for test data:**
```python
from gift_manager.tests.factories import PersonFactory, GiftFactory

def test_gift_creation():
    person = PersonFactory()
    gift = GiftFactory(name="Test Gift")
    assert gift.name == "Test Gift"
```

**Use fixtures for common setups:**
```python
@pytest.fixture
def authenticated_user(client, user_factory):
    user = user_factory()
    client.force_login(user)
    return user
```

**Test permissions thoroughly:**
```python
def test_gift_access_with_viewer_permission(client, user, gift):
    from gift_manager.permissions import PermissionService, PermissionLevel

    PermissionService.create_or_update_permission(
        gift, user, PermissionLevel.VIEWER
    )

    response = client.get(f"/gifts/{gift.gift_id}/")
    assert response.status_code == 200
```

**Frontend tests with Playwright:**
```python
@pytest.mark.frontend
def test_gift_list_displays_correctly(page, live_server, authenticated_user):
    page.goto(f"{live_server.url}/gifts/")
    assert page.locator("h1").inner_text() == "Gifts"
```

### Test Database

**Settings:** `GiftManager.settings.testing`

**Database:**
- PostgreSQL recommended for full compatibility
- SQLite fallback for quick local testing (limitations on JSONB)
- Test database created automatically: `test_<DB_NAME>`

**Migrations:**
- Automatically applied before tests
- Use `--reuse-db` to speed up repeated test runs

## Architecture Patterns

### Service Layer Pattern

**Purpose:** Encapsulate complex business logic separate from views/models

**Implementation:** `gift_manager/services.py`

**Key Service:** `PermissionService`
- Static methods for permission operations
- Handles cascade inheritance for hierarchical groups
- Abstracts permission complexity from views

**Usage Example:**
```python
from gift_manager.permissions import PermissionService, PermissionLevel

# Get user's permission level on an object
permission = PermissionService.get_permission(gift, user)

# Check if user has editor access
if permission >= PermissionLevel.EDITOR:
    # Allow editing

# Create or update permission
PermissionService.create_or_update_permission(
    gift, user, PermissionLevel.VIEWER
)

# Delete permission
PermissionService.delete_permission(gift, user)
```

### Facade Pattern

**Purpose:** Provide simplified interface to PermissionService

**Implementation:** `gift_manager/permissions.py`

**Exports:**
- `PermissionLevel` constants
- `PermissionService` methods
- Convenient one-import access

**Usage:**
```python
from gift_manager.permissions import PermissionService, PermissionLevel

# Everything needed is in one import
```

### QuerySet/Manager Pattern

**Purpose:** Encapsulate complex queries in reusable methods

**Implementation:** Custom managers and querysets

**Example:**
```python
# In models.py
class PersonQuerySet(models.QuerySet):
    def accessible_by(self, user):
        return self.filter(Q(user_link=user) | Q(shared_with=user))

    def with_groups_annotated(self):
        return self.annotate(
            groups_info=JSONBAgg(...)  # JSONB annotation for Grid.js
        )

class PersonManager(models.Manager):
    def get_queryset(self):
        return PersonQuerySet(self.model, using=self._db)

    def accessible_by(self, user):
        return self.get_queryset().accessible_by(user)

    def for_list_display(self, user):
        return (
            self.accessible_by(user)
            .with_groups_annotated()
            .values(...)
        )

# Usage in views
persons = Person.objects.for_list_display(request.user)
```

### Class-Based View Hierarchy

**Base Classes:** `gift_manager/views/base.py`

**Structure:**
```python
# Base view classes
class BaseListView(LoginRequiredMixin, FilterByUserMixin, ListView)
class BaseDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView)
class BaseCreateView(LoginRequiredMixin, CreateView)
class BaseUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView)
class BaseDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView)

# Mixins
class FilterByUserMixin:  # Filter queryset by user access
class PermissionRequiredMixin:  # Check permission level
class ContextPermissionMixin:  # Add permission to template context
```

**Usage in domain views:**
```python
from .base import BaseListView, BaseDetailView, BaseUpdateView

class GiftListView(BaseListView):
    model = Gift
    template_name = "gift_manager/gift_list.html"

class GiftDetailView(BaseDetailView):
    model = Gift
    permission_required = PermissionLevel.VIEWER

class GiftUpdateView(BaseUpdateView):
    model = Gift
    form_class = GiftForm
    permission_required = PermissionLevel.EDITOR
```

### Hierarchical Data Pattern

**Models with Hierarchy:** `PersonGroup`, `GiftTag`

**Key Methods:**
- `get_children()` - Direct children
- `get_descendants()` - All descendants recursively
- `get_ancestors()` - All parents up to root
- `get_primary_ancestors_path()` - Specific path for breadcrumbs
- `has_cycle_with(potential_parent)` - Cycle detection
- `clear_hierarchy_cache()` - Cache invalidation

**Optimization:**
- Single query fetches all groups/tags
- Traversal done in-memory (no N+1 queries)
- Results cached for 1 hour (Redis)
- Signal handlers clear cache on changes

**Example:**
```python
# Get all descendant groups
child_groups = group.get_descendants()

# Get all persons in group and descendants
all_members = group.get_all_members(include_nested=True)

# Check if adding parent would create cycle
if group.has_cycle_with(potential_parent):
    raise ValidationError("Cycle detected")
```

## Database & Models

### Core Models

**User Management:**
- `Profile` - Extends User with view preferences, friend list
- `Invitation` - Token-based invitations with expiration

**Primary Entities:**
- `Person` - Individual with optional email, groups membership
- `PersonGroup` - Hierarchical groups with parent_groups
- `Gift` - Gift with tags, comments
- `GiftTag` - Hierarchical tags with parent_tags
- `Event` - Events with dates, recurrence
- `Relation` - Links person/group to gift with status, event

**Permission Models:**
- `PersonPermission`, `PersonGroupPermission`
- `GiftPermission`, `GiftTagPermission`
- `EventPermission`, `RelationPermission`

**Supporting Models:**
- `RelationStatus` - Predefined statuses (Idea, Ordered, Wrapped, etc.)

### Model Features

**UUID Primary Keys:**
All primary models use UUID for primary keys:
```python
person_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
```

**Email Encryption:**
Email fields use Fernet symmetric encryption:
```python
# In model
email_address = models.TextField(...)  # Stores encrypted value

# Property for access
@property
def email(self) -> str | None:
    return decode_email(self.email_address)

def set_email(self, value: str | None) -> None:
    self.email_address = encode_email(value)
```

**Translatable Fields:**
Using django-modeltranslation:
```python
# models.py
class RelationStatus(models.Model):
    status = models.TextField(unique=True)

# translation.py
from modeltranslation.translator import register, TranslationOptions

@register(RelationStatus)
class RelationStatusTranslationOptions(TranslationOptions):
    fields = ('status',)

# Creates: status_en, status_fr database fields
```

**JSONB Annotations:**
For efficient Grid.js data fetching:
```python
persons = Person.objects.annotate(
    groups_info=JSONBAgg(
        Func(
            Value("id"), F("groups__group_id"),
            Value("name"), F("groups__name"),
            function="jsonb_build_object",
        ),
        filter=Q(groups__group_id__isnull=False),
        distinct=True,
    )
).values("person_id", "first_name", "family_name", "groups_info")
```

### Database Migrations

**Location:** `gift_manager/migrations/`

**Creating Migrations:**
```bash
# After model changes
python manage.py makemigrations

# With description
python manage.py makemigrations --name add_field_to_person
```

**Applying Migrations:**
```bash
# Apply all pending
python manage.py migrate

# Apply specific migration
python manage.py migrate gift_manager 0022

# Show migration status
python manage.py showmigrations
```

**Migration Best Practices:**
1. **Always review generated migrations** before committing
2. **Test migrations on copy of production data** for complex changes
3. **Provide data migrations** for transforming existing data
4. **Add indexes** for new fields that will be queried frequently
5. **Use reversible operations** when possible (provide `reverse_code` for RunPython)

**Data Migration Example:**
```python
# In migration file
from django.db import migrations

def encode_existing_emails(apps, schema_editor):
    Person = apps.get_model('gift_manager', 'Person')
    for person in Person.objects.all():
        if person.email_address:
            person.email_address = encode_email(person.email_address)
            person.save()

class Migration(migrations.Migration):
    dependencies = [...]

    operations = [
        migrations.RunPython(encode_existing_emails, reverse_code=migrations.RunPython.noop),
    ]
```

## Permission System

### Permission Levels

**Hierarchy:**
```python
NONE = 0       # No access (default)
VIEWER = 10    # Read-only access
EDITOR = 20    # Read and modify
OWNER = 30     # Full control (delete, share)
```

**Usage:**
```python
from gift_manager.permissions import PermissionLevel

# Check permission level
if permission >= PermissionLevel.EDITOR:
    # Allow editing
```

### Shareable Models

All primary models are shareable:
- Person
- PersonGroup (with cascade inheritance)
- Gift
- GiftTag
- Event
- Relation

### Permission Through Tables

**Structure:**
```python
class GiftPermission(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    gift = models.ForeignKey(Gift, on_delete=models.CASCADE)
    permission_type = models.IntegerField(
        choices=PermissionLevel.CHOICES,
        default=PermissionLevel.VIEWER
    )

    class Meta:
        unique_together = ("user", "gift")
```

**Special: PersonGroupPermission**
```python
class PersonGroupPermission(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    group = models.ForeignKey(PersonGroup, on_delete=models.CASCADE)
    permission_type = models.IntegerField(...)
    inherit_permissions = models.BooleanField(
        default=False,
        help_text="If true, this permission level cascades to all child groups"
    )
```

### Cascade Inheritance

**Concept:** Permissions on parent groups can cascade to child groups

**Implementation:**
```python
def get_effective_permission_for_group(group, user):
    """
    Get effective permission considering cascade inheritance.
    Checks group and all ancestors for inherited permissions.
    Returns highest permission level found.
    """
    # Direct permission on group
    direct_perm = get_permission(group, user)

    # Check ancestors for inherited permissions
    ancestors = group.get_ancestors()
    inherited_perms = [
        pgp.permission_type
        for ancestor in ancestors
        for pgp in PersonGroupPermission.objects.filter(
            group=ancestor, user=user, inherit_permissions=True
        )
    ]

    # Return highest permission
    return max([direct_perm, *inherited_perms], default=PermissionLevel.NONE)
```

### Permission Service

**Location:** `gift_manager/services.py`

**Key Methods:**

```python
# Get permission level
permission = PermissionService.get_permission(obj, user)

# Get effective permission (considers inheritance for groups)
permission = PermissionService.get_effective_permission_for_group(group, user)

# Get formatted label
label = PermissionService.get_permission_label(obj, user)  # "editor", "viewer", etc.

# Create or update permission
PermissionService.create_or_update_permission(
    obj, user, PermissionLevel.EDITOR
)

# Delete permission
PermissionService.delete_permission(obj, user)

# Get model class from string
model_class = PermissionService.get_model_class("gift")

# Get all users with access
users = PermissionService.get_users_with_permission(obj)
```

**Checking Permissions in Views:**
```python
class GiftUpdateView(BaseUpdateView):
    model = Gift
    permission_required = PermissionLevel.EDITOR

    # BaseUpdateView checks permission automatically
```

**Checking Permissions Manually:**
```python
from gift_manager.permissions import PermissionService, PermissionLevel

permission = PermissionService.get_permission(gift, request.user)
if permission < PermissionLevel.EDITOR:
    return HttpResponseForbidden("You don't have permission to edit this gift")
```

## Frontend Guidelines

### Template Structure

**Base Template:** `gift_manager/templates/base.html`
- Navigation bar with user menu
- Sidebar with main navigation
- Theme toggle (light/dark mode)
- Message display area
- Content block

**Common Templates:**
- `<model>_list.html` - List views with Grid.js tables
- `<model>_detail.html` - Detail views with related objects
- `edit_form.html` - Shared form template
- `<model>_explorer.html` - Hierarchical tree views
- `share_objects.html` - Permission sharing interface

**Template Inheritance:**
```django
{% extends "base.html" %}

{% block title %}Gift List{% endblock %}

{% block content %}
  <h1>Gifts</h1>
  <div id="grid-container"></div>
{% endblock %}

{% block extra_js %}
  <script src="{% static 'gift_manager/grid-utils.js' %}"></script>
{% endblock %}
```

### Grid.js Integration

**Purpose:** Modern, lightweight table library for list views

**Initialization:**
```javascript
// In template
<div id="grid-container"></div>

<script>
  const grid = new gridjs.Grid({
    columns: [
      { id: 'name', name: 'Name' },
      { id: 'comment', name: 'Comment' },
      {
        id: 'actions',
        name: 'Actions',
        formatter: (cell, row) => {
          return gridjs.html(`
            <a href="/gifts/${row.cells[0].data}/edit">Edit</a>
            <a href="/gifts/${row.cells[0].data}/delete">Delete</a>
          `);
        }
      }
    ],
    server: {
      url: '/api/gifts/',
      then: data => data.results,
      total: data => data.count
    },
    pagination: {
      limit: 20,
      server: {
        url: (prev, page, limit) => `${prev}?page=${page + 1}&limit=${limit}`
      }
    },
    search: {
      server: {
        url: (prev, keyword) => `${prev}?search=${keyword}`
      }
    },
    sort: true
  }).render(document.getElementById('grid-container'));
</script>
```

**Best Practices:**
1. Use server-side pagination for large datasets
2. Leverage JSONB annotations for related data (groups_info, tags_info)
3. Format actions column with proper permissions check
4. Add custom CSS for consistent styling

### HTMX Usage

**Purpose:** Dynamic HTML updates without full page reloads

**Common Patterns:**

**Inline editing:**
```html
<div hx-get="/gifts/{{ gift.gift_id }}/edit/"
     hx-target="#edit-form"
     hx-swap="innerHTML">
  Click to edit
</div>
<div id="edit-form"></div>
```

**Form submission:**
```html
<form hx-post="/gifts/create/"
      hx-target="#gift-list"
      hx-swap="beforeend">
  <!-- Form fields -->
  <button type="submit">Create Gift</button>
</form>
```

**Permission row updates:**
```html
<div hx-post="/share/{{ object_type }}/{{ object_id }}/"
     hx-target="#permission-rows"
     hx-swap="innerHTML">
  <!-- Permission form -->
</div>
```

### Static Files

**Location:** `gift_manager/static/`

**Key Files:**
- `gift_manager/main.css` - Main stylesheet with Grid.js styling
- `gift_manager/theme.css` - Theme and dark mode styles
- `gift_manager/custom-dropdowns.css` - Custom dropdown styling
- `gift_manager/grid-utils.js` - Grid.js initialization helpers
- `gift_manager/ui-enhancements.js` - Interactive UI features
- `gift_manager/filter-panel.js` - Advanced filtering
- `gift_manager/notifications.js` - User notifications

**Loading Static Files:**
```django
{% load static %}
<link rel="stylesheet" href="{% static 'gift_manager/main.css' %}">
<script src="{% static 'gift_manager/grid-utils.js' %}"></script>
```

**Collecting Static Files (Production):**
```bash
python manage.py collectstatic --noinput
```

### Dark Mode Support

**Implementation:**
- Theme toggle in navigation bar
- CSS variables for colors in `theme.css`
- User preference stored in localStorage
- Server-side rendering respects user preference

**CSS Variables:**
```css
:root {
  --primary-color: #007bff;
  --background-color: #ffffff;
  --text-color: #212529;
}

[data-theme="dark"] {
  --background-color: #1a1a1a;
  --text-color: #e0e0e0;
}
```

## Internationalization

### Supported Languages

- **English (en)** - Default
- **French (fr)** - Fully translated

### Translation Workflow

**1. Mark strings for translation:**

**In Python code:**
```python
from django.utils.translation import gettext_lazy

class Person(models.Model):
    class Meta:
        verbose_name = gettext_lazy("Person")
        verbose_name_plural = gettext_lazy("Persons")
```

**In templates:**
```django
{% load i18n %}
{% trans "Hello World" %}

{% blocktrans with name=person.name %}
  Welcome, {{ name }}!
{% endblocktrans %}
```

**2. Extract translatable strings:**
```bash
# For app
python manage.py makemessages -l fr

# For JavaScript
python manage.py makemessages -d djangojs -l fr
```

**3. Translate in .po files:**
Edit `locale/fr/LC_MESSAGES/django.po`:
```po
msgid "Person"
msgstr "Personne"

msgid "Persons"
msgstr "Personnes"
```

**4. Compile translations:**
```bash
python manage.py compilemessages
```

### Model Translation

**Configuration:** `gift_manager/translation.py`

**Example:**
```python
from modeltranslation.translator import register, TranslationOptions
from .models import RelationStatus

@register(RelationStatus)
class RelationStatusTranslationOptions(TranslationOptions):
    fields = ('status',)
```

**Result:**
- Database fields: `status`, `status_en`, `status_fr`
- Automatic language switching based on user preference

### URL Internationalization

**Root URLs with i18n patterns:**
```python
from django.conf.urls.i18n import i18n_patterns

urlpatterns = i18n_patterns(
    path('', include('gift_manager.urls')),
    path('admin/', admin.site.urls),
)
```

**URL structure:**
- English: `/en/gifts/`
- French: `/fr/gifts/`

## Common Tasks

### Adding a New Model

1. **Define model in `models.py`:**
   ```python
   class NewModel(models.Model):
       model_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
       name = models.TextField()
       creation_date = models.DateTimeField(auto_now_add=True)
       shared_with = models.ManyToManyField(
           User, through="NewModelPermission",
           related_name="%(app_label)s_%(class)s_shared_with"
       )

       class Meta:
           verbose_name = gettext_lazy("New Model")
           verbose_name_plural = gettext_lazy("New Models")
   ```

2. **Create permission model:**
   ```python
   class NewModelPermission(models.Model):
       user = models.ForeignKey(User, on_delete=models.CASCADE)
       new_model = models.ForeignKey(NewModel, on_delete=models.CASCADE)
       permission_type = models.IntegerField(
           choices=PermissionLevel.CHOICES,
           default=PermissionLevel.VIEWER
       )

       class Meta:
           unique_together = ("user", "new_model")
   ```

3. **Create and apply migrations:**
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```

4. **Create forms in `forms.py`:**
   ```python
   class NewModelForm(forms.ModelForm):
       class Meta:
           model = NewModel
           fields = ['name']
   ```

5. **Create views in `views/new_model.py`:**
   ```python
   from .base import BaseListView, BaseDetailView, BaseCreateView

   class NewModelListView(BaseListView):
       model = NewModel
       template_name = "gift_manager/new_model_list.html"
   ```

6. **Add URLs in `urls.py`:**
   ```python
   path('new-models/', views.NewModelListView.as_view(), name='new_model_list'),
   ```

7. **Create templates:**
   - `templates/gift_manager/new_model_list.html`
   - `templates/gift_manager/new_model_detail.html`
   - `templates/gift_manager/new_model_form.html`

8. **Add tests:**
   - `tests/test_new_model.py`
   - `tests/views/test_new_model_views.py`

### Adding Permission Support to PermissionService

**Update `services.py`:**
```python
class PermissionService:
    @staticmethod
    def get_permission(obj, user):
        # Add case for new model
        if isinstance(obj, NewModel):
            try:
                perm = NewModelPermission.objects.get(new_model=obj, user=user)
                return perm.permission_type
            except NewModelPermission.DoesNotExist:
                return PermissionLevel.NONE
        # ... existing cases
```

### Creating a Data Migration

**Generate empty migration:**
```bash
python manage.py makemigrations --empty gift_manager --name populate_default_statuses
```

**Edit migration file:**
```python
from django.db import migrations

def create_default_statuses(apps, schema_editor):
    RelationStatus = apps.get_model('gift_manager', 'RelationStatus')
    statuses = ['Idea', 'Ordered', 'Wrapped', 'Given']
    for status_name in statuses:
        RelationStatus.objects.get_or_create(status_en=status_name)

def reverse_statuses(apps, schema_editor):
    RelationStatus = apps.get_model('gift_manager', 'RelationStatus')
    RelationStatus.objects.all().delete()

class Migration(migrations.Migration):
    dependencies = [
        ('gift_manager', '0021_previous_migration'),
    ]

    operations = [
        migrations.RunPython(create_default_statuses, reverse_code=reverse_statuses),
    ]
```

### Adding a New Translation

**Extract strings:**
```bash
python manage.py makemessages -l es  # Spanish
```

**Edit `.po` file:**
```po
# locale/es/LC_MESSAGES/django.po
msgid "Gift"
msgstr "Regalo"
```

**Compile:**
```bash
python manage.py compilemessages
```

**Add to settings:**
```python
# GiftManager/settings/base.py
LANGUAGES = [
    ('en', gettext_lazy('English')),
    ('fr', gettext_lazy('French')),
    ('es', gettext_lazy('Spanish')),  # Add new language
]
```

### Running Specific Tests

**Single test file:**
```bash
pytest gift_manager/tests/test_permissions.py
```

**Single test class:**
```bash
pytest gift_manager/tests/test_permissions.py::TestPermissionService
```

**Single test method:**
```bash
pytest gift_manager/tests/test_permissions.py::TestPermissionService::test_get_permission
```

**With keyword filter:**
```bash
pytest -k "permission"
```

**Verbose output:**
```bash
pytest -v
```

**Stop on first failure:**
```bash
pytest -x
```

**Debugging with pdb:**
```bash
pytest --pdb
```

## Important Gotchas

### 1. PostgreSQL Required for JSONB

**Issue:** SQLite doesn't support JSONB aggregations used in Grid.js queries

**Solution:**
- Use PostgreSQL for development and testing when working with Grid.js features
- SQLite acceptable for quick model tests only

### 2. Email Encryption Key

**Issue:** Missing `EMAIL_ENCRYPTION_KEY` causes Fernet errors

**Solution:**
```bash
# Generate key
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'

# Add to .env
EMAIL_ENCRYPTION_KEY=<generated_key>
```

**Never commit encryption keys to version control!**

### 3. Hierarchical Cache Invalidation

**Issue:** Changes to group/tag hierarchy not reflected immediately

**Solution:**
- Cache is automatically invalidated via signal handlers
- For manual invalidation: `obj.clear_hierarchy_cache()`
- Cache TTL: 1 hour

### 4. Cascade Permission Inheritance

**Issue:** Child groups not inheriting permissions as expected

**Solution:**
- Ensure `inherit_permissions=True` on parent group permission
- Use `PermissionService.get_effective_permission_for_group()` (not `get_permission()`)
- Check for cycles in group hierarchy

### 5. Migration Dependencies

**Issue:** Migrations fail due to missing dependencies

**Solution:**
- Always review generated migrations for dependencies
- Ensure migrations are applied in order
- Check for custom `RunPython` operations that require specific state

### 6. Static Files in Production

**Issue:** Static files not loading in production

**Solution:**
```bash
# Collect static files before deployment
python manage.py collectstatic --noinput

# Ensure STATIC_ROOT is configured
# WhiteNoise handles serving automatically
```

### 7. Translation Fallbacks

**Issue:** Missing translations showing raw msgid strings

**Solution:**
- Always provide English translations (default)
- Run `compilemessages` after editing `.po` files
- Check for `fuzzy` entries in `.po` files (remove or fix)

### 8. Testing with Playwright

**Issue:** Browser tests failing in CI

**Solution:**
- Install Playwright browsers: `playwright install`
- Use `--headed` flag for debugging locally
- Ensure `live_server` fixture is used for URLs
- Check viewport size and async operations

### 9. Permission Through Table Unique Constraints

**Issue:** IntegrityError when creating duplicate permissions

**Solution:**
- Use `get_or_create()` or `update_or_create()`
- Use `PermissionService.create_or_update_permission()` (handles this)

### 10. Model Translation Field Access

**Issue:** Accessing `status` vs `status_en` vs `status_fr` confusion

**Solution:**
- Use `status` field - modeltranslation handles language switching
- Direct field access: `obj.status_en`, `obj.status_fr`
- In migrations: Use language-specific fields (`status_en`)

---

## Quick Reference

### Environment Variables

**Required:**
- `DJANGO_SECRET_KEY` - Django secret key
- `EMAIL_ENCRYPTION_KEY` - Fernet key for email encryption
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` - Database
- `ALLOWED_HOSTS` - Comma-separated domains
- `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` - SMTP

**Optional:**
- `REDIS_URL` - Redis connection string
- `SENTRY_DSN` - Sentry error tracking
- `DEBUG` - Debug mode (default: False)
- `LOG_LEVEL` - Logging level

### Common Commands

```bash
# Development
python manage.py runserver
python manage.py migrate
python manage.py createsuperuser
python manage.py makemigrations

# Testing
pytest
pytest --cov=gift_manager
pytest -m "not slow and not frontend"

# Translations
python manage.py makemessages -l fr
python manage.py compilemessages

# Static files
python manage.py collectstatic --noinput

# Code quality
pre-commit run --all-files
ruff check .
ruff format .

# Docker
docker-compose up
docker-compose exec web python manage.py migrate
```

### File Paths Reference

- **Models:** `gift_manager/models.py`
- **Views:** `gift_manager/views/<domain>.py`
- **Forms:** `gift_manager/forms.py`
- **URLs:** `gift_manager/urls.py`
- **Templates:** `gift_manager/templates/gift_manager/`
- **Static:** `gift_manager/static/gift_manager/`
- **Tests:** `gift_manager/tests/`
- **Migrations:** `gift_manager/migrations/`
- **Settings:** `GiftManager/settings/<env>.py`

---

**Document Version:** 1.0
**Last Updated:** 2025-12-30
**Maintainer:** AI Assistant (Claude Code)

For questions or updates to this document, create an issue or pull request.
