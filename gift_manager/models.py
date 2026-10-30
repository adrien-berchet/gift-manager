# pylint: disable=too-many-lines
from __future__ import annotations

import calendar
import secrets
import uuid
from datetime import date as date_class
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.postgres.aggregates import JSONBAgg
from django.core.exceptions import EmptyResultSet
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.core.validators import MinValueValidator
from django.db import IntegrityError
from django.db import connection
from django.db import models
from django.db import transaction
from django.db.models import Exists
from django.db.models import F
from django.db.models import Func
from django.db.models import OuterRef
from django.db.models import Q
from django.db.models import TextField
from django.db.models import Value
from django.db.models.expressions import RawSQL
from django.db.models.functions import Coalesce
from django.db.models.functions import Concat
from django.db.models.functions import NullIf
from django.db.models.query_utils import DeferredAttribute
from django.db.models.signals import post_delete
from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.urls import reverse
from django.utils import formats
from django.utils import timezone
from django.utils.functional import classproperty
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy

from .email_encoding import decode_email
from .email_encoding import encode_email
from .statuses import can_rate_status
from .validators import validate_http_url

_PERMISSION_LEVEL_DICT = {"none": 0, "viewer": 10, "editor": 20, "owner": 30}
_PERMISSION_LABEL_DICT = {
    0: gettext_lazy("none"),
    10: gettext_lazy("viewer"),
    20: gettext_lazy("editor"),
    30: gettext_lazy("owner"),
}


class PermissionLevel:
    NONE = _PERMISSION_LEVEL_DICT["none"]
    VIEWER = _PERMISSION_LEVEL_DICT["viewer"]
    EDITOR = _PERMISSION_LEVEL_DICT["editor"]
    OWNER = _PERMISSION_LEVEL_DICT["owner"]

    CHOICES = [
        (NONE, _PERMISSION_LABEL_DICT[NONE]),
        (VIEWER, _PERMISSION_LABEL_DICT[VIEWER]),
        (EDITOR, _PERMISSION_LABEL_DICT[EDITOR]),
        (OWNER, _PERMISSION_LABEL_DICT[OWNER]),
    ]

    @classmethod
    def get_label(cls, permission_level, case="lower") -> str:
        """Get the label of a permission level."""
        label = _PERMISSION_LABEL_DICT.get(permission_level, "none")
        if case == "upper":
            return label.upper()
        if case == "title":
            return label.title()
        return label


class BaseObjectPermission(models.Model):
    """Abstract base model for object-level permissions."""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    permission_type = models.IntegerField(
        choices=PermissionLevel.CHOICES, default=PermissionLevel.VIEWER
    )

    class Meta:
        abstract = True

    def __str__(self):
        target = getattr(self, self.filter_name)
        return f"{self.user} - {target} -> {PermissionLevel.get_label(self.permission_type)}"


def date_in_year(year: int, month: int, day: int) -> date_class:
    """Return the date of a yearly occurrence in a given year.

    A day that does not exist in that year (February 29 in a non-leap year) is clamped
    to the last day of the month.
    """
    return date_class(year, month, min(day, calendar.monthrange(year, month)[1]))


def next_yearly_occurrence(month: int, day: int, today: date_class) -> date_class:
    """Return the first occurrence of a month/day that is on or after today."""
    candidate = date_in_year(today.year, month, day)
    if candidate >= today:
        return candidate
    return date_in_year(today.year + 1, month, day)


class UserPermissionQuerySet(models.QuerySet):
    """Base QuerySet for models with user permissions."""

    def accessible_by(self, user):
        """Return all objects accessible by a user (shared with the user)."""
        return self.filter(Q(shared_with=user))


class PersonQuerySet(UserPermissionQuerySet):
    """QuerySet for Person model with additional query methods."""

    def with_groups_annotated(self, user=None):
        """Return persons with groups information annotated for Grid.js.

        When a user is given, only the groups that user can access are included.
        """
        from django.db import connection

        # Use database-specific aggregation
        if connection.vendor == "postgresql":
            group_filter = Q(groups__group_id__isnull=False)
            if user is not None:
                group_filter &= Q(
                    groups__pk__in=PersonGroup.objects.accessible_by(user).values("pk")
                )
            return self.annotate(
                groups_info=JSONBAgg(
                    Func(
                        Value("id"),
                        F("groups__group_id"),
                        Value("name"),
                        F("groups__name"),
                        function="jsonb_build_object",
                    ),
                    filter=group_filter,
                    distinct=True,
                )
            )
        # For SQLite and other databases, use a simpler approach
        return self.prefetch_related("groups")

    def with_complete_name(self):
        """Return persons with complete_name annotation (family_name + first_name)."""
        return self.annotate(
            complete_name=Concat("family_name", Value(" "), "first_name", output_field=TextField())
        )

    def for_list_display(self, user):
        """Return queryset optimized for list display with all necessary annotations."""
        return (
            self.accessible_by(user)
            .with_groups_annotated(user)
            .values("person_id", "first_name", "family_name", "email_address", "groups_info")
        )


class PersonManager(models.Manager.from_queryset(PersonQuerySet)):
    """Manager for Person model with additional query methods."""


class GiftQuerySet(UserPermissionQuerySet):
    """QuerySet for Gift model with additional query methods."""

    def with_tags_annotated(self, user=None):
        """Return gifts with tags information annotated for Grid.js.

        When a user is given, only the tags that user can access are included.
        """
        from django.db import connection

        # Use database-specific aggregation
        if connection.vendor == "postgresql":
            tag_filter = Q(tags__tag_id__isnull=False)
            if user is not None:
                tag_filter &= Q(tags__pk__in=GiftTag.objects.accessible_by(user).values("pk"))
            return self.annotate(
                tags_info=JSONBAgg(
                    Func(
                        Value("id"),
                        F("tags__tag_id"),
                        Value("name"),
                        F("tags__name"),
                        function="jsonb_build_object",
                    ),
                    filter=tag_filter,
                    distinct=True,
                )
            )
        # For SQLite and other databases, use a simpler approach
        return self.prefetch_related("tags")

    def for_list_display(self, user):
        """Return queryset optimized for list display with all necessary annotations."""
        return (
            self.accessible_by(user)
            .with_tags_annotated(user)
            .values("gift_id", "name", "comment", "tags_info")
        )


class GiftManager(models.Manager.from_queryset(GiftQuerySet)):
    """Manager for Gift model with additional query methods."""


class EventQuerySet(UserPermissionQuerySet):
    """QuerySet for Event model: global events are visible to every user."""

    def accessible_by(self, user):
        """Return all events accessible by a user (global or shared with the user)."""
        return self.filter(Q(is_global=True) | Q(shared_with=user)).distinct()

    def for_list_display(self, user):
        """Return queryset optimized for list display."""
        return self.accessible_by(user).only(
            "event_id",
            "name",
            "comment",
            "schedule_type",
            "date",
            "recurrence",
            "is_global",
            "is_birthday",
        )


class EventManager(models.Manager.from_queryset(EventQuerySet)):
    """Manager for Event model with additional query methods."""

    def get_birthday_event(self):
        """Return the global Birthday event, creating it when it is missing.

        The event is normally provisioned by a migration. It is unscheduled on purpose:
        the date of a birthday gift plan is the next birthday of its recipient, which is
        computed from the person, so no event row is needed per person or per year.
        """
        event = self.filter(is_birthday=True).first()
        if event is None:
            try:
                with transaction.atomic():
                    event = self.create(
                        name=self.model.BIRTHDAY_EVENT_NAME,
                        schedule_type=self.model.ScheduleType.UNSCHEDULED,
                        is_global=True,
                        is_birthday=True,
                    )
            except IntegrityError:
                # A concurrent request created it first: the unique constraint allows one
                event = self.get(is_birthday=True)
        return event


def recipient_groups_for(user, excluding_person: Person | None = None) -> RawSQL:
    """Return a subquery of the pks of the groups that ``user`` is a recipient of.

    These are the groups of each person linked to ``user`` (``Person.account``) plus all of
    their ancestor groups: a member of a nested group is a member of its parents. It is a
    recursive query embedded in the caller's statement, so reading plans costs no extra query
    whatever the depth of the hierarchy.
    """
    memberships = Person.groups.through.objects.filter(person__account=user)
    if excluding_person is not None:
        memberships = memberships.exclude(person=excluding_person)
    return PersonGroup.hierarchy_subquery(
        memberships.values("persongroup_id"), ancestors=True, include_start=True
    )


class RelationQuerySet(UserPermissionQuerySet):
    """QuerySet for Relation model with additional query methods."""

    def hidden_surprises_for(self, user, excluding_person: Person | None = None):
        """Return the surprise plans ``user`` must never see, shared with them or not.

        A surprise plan is hidden from its recipient: the person linked to ``user`` or a member
        of the targeted group (nested groups included). A user who owns the plan is exempt.
        """
        owns_plan = RelationPermission.objects.filter(
            relation=OuterRef("pk"), user=user, permission_type=PermissionLevel.OWNER
        )
        person_filter = Q(person__account=user)
        if excluding_person is not None:
            person_filter &= ~Q(person=excluding_person)
        return (
            self.filter(is_surprise=True)
            .filter(
                person_filter
                | Q(group_id__in=recipient_groups_for(user, excluding_person=excluding_person))
            )
            .exclude(Exists(owns_plan))
        )

    def accessible_by(self, user):
        """Return the plans shared with ``user``, except the surprises addressed to them."""
        hidden = self.model.objects.hidden_surprises_for(user).values("pk")
        return super().accessible_by(user).exclude(pk__in=hidden)

    def with_related_objects(self):
        """Return relations with all related objects selected."""
        return self.select_related("person", "group", "gift", "event", "status")

    def with_related_object_name(self):
        """Return relations with related_object annotation (person or group name)."""
        return self.annotate(
            related_object=Coalesce(
                NullIf(
                    Concat(
                        "person__first_name",
                        Value(" "),
                        "person__family_name",
                        output_field=TextField(),
                    ),
                    Value(" "),
                ),
                "group__name",
                output_field=TextField(),
            )
        )

    def for_list_display(self, user):
        """Return queryset optimized for list display with all annotations."""
        return (
            self.accessible_by(user)
            .with_related_object_name()
            .values(
                "relation_id",
                "gift__name",
                "gift__gift_id",
                "comment",
                "related_object",
                "person__person_id",
                "group__group_id",
                "event__name",
                "event__is_birthday",
                "event__event_id",
                "status",
                "due_date",
            )
        )


class RelationManager(models.Manager.from_queryset(RelationQuerySet)):
    """Manager for Relation model with additional query methods."""


class Profile(models.Model):
    """Model for a user profile."""

    # View preference choices
    VIEW_LIST = "list"
    VIEW_CARD = "card"
    VIEW_CHOICES = [
        (VIEW_LIST, gettext_lazy("List")),
        (VIEW_CARD, gettext_lazy("Card")),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    friends = models.ManyToManyField("self", symmetrical=True, blank=True)

    # Set when the user deactivates their own account. Only such accounts may reactivate
    # themselves with their password; any other inactive account (e.g. disabled by an
    # administrator) needs an administrator to reactivate it.
    self_deactivated_at = models.DateTimeField(null=True, blank=True, editable=False)

    # View preferences for list pages
    default_view_desktop = models.CharField(
        max_length=10,
        choices=VIEW_CHOICES,
        default=VIEW_LIST,
        verbose_name=gettext_lazy("Default view for desktop"),
        help_text=gettext_lazy("Default view mode for desktop/large screens"),
    )
    default_view_mobile = models.CharField(
        max_length=10,
        choices=VIEW_CHOICES,
        default=VIEW_CARD,
        verbose_name=gettext_lazy("Default view for mobile"),
        help_text=gettext_lazy("Default view mode for mobile/small screens"),
    )

    # Reminders: the digest email is opt-in and rendered in ``preferred_language``
    DIGEST_OFF = "off"
    DIGEST_WEEKLY = "weekly"
    DIGEST_DAILY = "daily"
    DIGEST_FREQUENCY_CHOICES = [
        (DIGEST_OFF, gettext_lazy("Off")),
        (DIGEST_WEEKLY, gettext_lazy("Weekly (Mondays)")),
        (DIGEST_DAILY, gettext_lazy("Daily")),
    ]
    DIGEST_LOOKAHEAD_CHOICES = [
        (7, gettext_lazy("1 week")),
        (14, gettext_lazy("2 weeks")),
        (30, gettext_lazy("30 days")),
    ]

    CURRENCY_CHOICES = [
        ("EUR", "EUR (€)"),
        ("USD", "USD ($)"),
        ("GBP", "GBP (£)"),
        ("CHF", "CHF"),
        ("CAD", "CAD ($)"),
    ]

    currency = models.CharField(
        max_length=3,
        choices=CURRENCY_CHOICES,
        default="EUR",
        verbose_name=gettext_lazy("Currency"),
    )
    preferred_language = models.CharField(
        max_length=10,
        blank=True,
        choices=settings.LANGUAGES,
        verbose_name=gettext_lazy("Language"),
        help_text=gettext_lazy("Language of the emails and of the calendar feed"),
    )
    digest_frequency = models.CharField(
        max_length=10,
        choices=DIGEST_FREQUENCY_CHOICES,
        default=DIGEST_OFF,
        verbose_name=gettext_lazy("Reminder emails"),
    )
    digest_lookahead_days = models.PositiveSmallIntegerField(
        choices=DIGEST_LOOKAHEAD_CHOICES,
        default=14,
        verbose_name=gettext_lazy("Look ahead"),
    )
    # Day of the last digest email actually sent; lets a re-run of the command skip the users
    # who already got theirs (e.g. after a partial failure)
    last_digest_sent_on = models.DateField(null=True, blank=True, editable=False)
    # Secret of the private calendar feed URL; null while the feed is disabled
    calendar_token = models.CharField(
        max_length=64, unique=True, null=True, blank=True, editable=False
    )
    ai_share_person_notes = models.BooleanField(
        default=False,
        verbose_name=gettext_lazy("Share recipient notes with AI"),
        help_text=gettext_lazy(
            "Allow recipient notes (sizes, preferences, allergies) to be anonymised and shared "
            "with the AI suggestion provider to improve gift idea relevance."
        ),
    )
    preferences_notes = models.TextField(
        gettext_lazy("Sizes and preferences"),
        blank=True,
        help_text=gettext_lazy("Clothing size, shoe size, favorite colors, preferred brands."),
    )
    avoid_notes = models.TextField(
        gettext_lazy("Things to avoid"),
        blank=True,
        help_text=gettext_lazy("Allergies, formats to avoid (e.g. no physical books), dislikes."),
    )
    public_interests = models.ManyToManyField(
        "GiftTag",
        blank=True,
        limit_choices_to={"is_public": True},
        related_name="interested_profiles",
        help_text=gettext_lazy("Global public tags describing topics and hobbies you enjoy."),
    )
    ai_share_self_profile = models.BooleanField(
        default=False,
        verbose_name=gettext_lazy("Allow friends' AI suggestions to consider your preferences"),
    )

    def __str__(self):
        label = gettext_lazy("Profile of")
        return f"{label} {self.user.username}"

    def get_absolute_url(self) -> str:
        return reverse("gift_manager:profile_detail")

    @property
    def email(self) -> str | None:
        """Get the decoded user email address."""
        return decode_email(self.user.email)

    def set_user_email(self, value: str | None) -> None:
        """Set the user email address, encoding it for storage."""
        self.user.email = encode_email(value)
        self.user.save()

    @property
    def language(self) -> str:
        """Return the language used for emails and the calendar feed."""
        supported = {code for code, _ in settings.LANGUAGES}
        if self.preferred_language in supported:
            return self.preferred_language
        return settings.LANGUAGE_CODE

    def regenerate_calendar_token(self) -> str:
        """Create a new calendar feed secret; the previous feed URL stops working."""
        self.calendar_token = secrets.token_urlsafe(32)
        self.save(update_fields=["calendar_token"])
        return self.calendar_token

    def clear_calendar_token(self) -> None:
        """Disable the calendar feed."""
        self.calendar_token = None
        self.save(update_fields=["calendar_token"])


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    if created:  # pragma: no branch
        Profile.objects.create(user=instance)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, "profile"):
        if instance.is_active and instance.profile.self_deactivated_at is not None:
            # Reactivated by any path (e.g. the admin): a later deactivation is not the user's own
            instance.profile.self_deactivated_at = None
        instance.profile.save()
    else:  # pragma: no branch
        Profile.objects.create(user=instance)


class Invitation(models.Model):
    """Model for an invitation."""

    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="%(app_label)s_%(class)s_invitations_sent",
        on_delete=models.CASCADE,
    )
    person = models.ForeignKey(
        "Person",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invitations",
    )
    # Email is stored encoded for privacy - use email property for decoded access
    recipient_email = models.TextField()
    accepted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        prefix = gettext_lazy("Invitation from")
        to_label = gettext_lazy("to")
        return f"{prefix} {self.sender} {to_label} {self.email}"

    @property
    def email(self) -> str | None:
        """Get the decoded recipient email address."""
        return decode_email(self.recipient_email)

    def set_email(self, value: str | None) -> None:
        """Set the recipient email address, encoding it for storage."""
        self.recipient_email = encode_email(value)

    @property
    def expires_at(self):
        """Return the expiry datetime, or None when invitations do not expire."""
        expiry_days = getattr(settings, "INVITATION_EXPIRY_DAYS", None)
        if expiry_days is None or self.created_at is None:
            return None
        return self.created_at + timedelta(days=expiry_days)

    def is_expired(self):
        """Check if the invitation has expired."""
        expires_at = self.expires_at
        if expires_at is None:
            return False  # If not configured, invitations don't expire
        return timezone.now() > expires_at


class Person(models.Model):
    """Model for a person."""

    person_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    first_name = models.TextField(unique=False, null=False)
    family_name = models.TextField(unique=False, null=True, blank=True)
    # Email is stored encoded for privacy - use email property for decoded access
    email_address = models.TextField(unique=False, null=True, blank=True)
    # Birthday: day and month go together, the year is optional. Stored as separate
    # columns so a birthday without a year needs no placeholder year.
    birthday_day = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
    )
    birthday_month = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
    )
    birthday_year = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(9999)],
    )
    # Free-text notes (sizes, allergies, things to avoid). Shared with everyone who can
    # see the person, like the rest of the person's data. Never log their content.
    notes = models.TextField(null=True, blank=True)
    # Interests reuse the gift tags, so they can be matched against a gift's tags directly.
    interests = models.ManyToManyField("GiftTag", related_name="interested_persons", blank=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    groups = models.ManyToManyField("PersonGroup", blank=True)
    shared_with = models.ManyToManyField(
        User, through="PersonPermission", related_name="%(app_label)s_%(class)s_shared_with"
    )
    account = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="linked_persons",
    )
    link_suggestion_dismissed_account = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    # Custom manager
    objects = PersonManager()

    class Meta:
        verbose_name = gettext_lazy("Person")
        verbose_name_plural = gettext_lazy("Persons")
        constraints = [
            models.CheckConstraint(
                condition=(
                    # The isnull terms matter: a comparison with NULL is NULL, which a SQL
                    # CHECK accepts, so a day without a month would otherwise slip through
                    Q(
                        birthday_day__isnull=False,
                        birthday_month__isnull=False,
                        birthday_day__gte=1,
                        birthday_day__lte=31,
                        birthday_month__gte=1,
                        birthday_month__lte=12,
                    )
                    | Q(
                        birthday_day__isnull=True,
                        birthday_month__isnull=True,
                        birthday_year__isnull=True,
                    )
                ),
                name="person_birthday_valid_day_and_month",
            ),
        ]

    def __str__(self) -> str:
        return (self.first_name + " " + (self.family_name or "")).strip()

    @property
    def has_birthday(self) -> bool:
        """Return True when a birthday (day and month) is recorded."""
        return self.birthday_day is not None and self.birthday_month is not None

    @property
    def birthday_display(self) -> str:
        """Return the birthday formatted for the active locale (year only when known)."""
        if not self.has_birthday:
            return ""
        if self.birthday_year is None:
            # Year 2000 is a leap year, so February 29 is representable
            return formats.date_format(
                date_in_year(2000, self.birthday_month, self.birthday_day), "MONTH_DAY_FORMAT"
            )
        return formats.date_format(
            date_in_year(self.birthday_year, self.birthday_month, self.birthday_day), "DATE_FORMAT"
        )

    def next_birthday(self, today: date_class | None = None) -> date_class | None:
        """Return the next birthday on or after today, or None without a birthday.

        The birthday is computed, never stored as an Event. A February 29 birthday
        falls on February 28 in non-leap years.
        """
        if not self.has_birthday:
            return None
        return next_yearly_occurrence(
            self.birthday_month, self.birthday_day, today or timezone.localdate()
        )

    def clean(self):
        """Validate that the birthday is a real calendar day (February 29 needs no year)."""
        super().clean()
        if self.birthday_month is None and self.birthday_day is None:
            if self.birthday_year is not None:
                raise ValidationError(
                    {"birthday_year": gettext_lazy("Enter a day and a month for the birthday.")}
                )
            return
        if self.birthday_month is None or self.birthday_day is None:
            raise ValidationError(
                {"birthday_day": gettext_lazy("Enter both the day and the month.")}
            )
        if not (1 <= self.birthday_month <= 12 and 1 <= self.birthday_day <= 31):
            return  # the field validators already report out-of-range values
        if self.birthday_year is not None and self.birthday_year > timezone.localdate().year:
            raise ValidationError(
                {"birthday_year": gettext_lazy("Enter a year that is not in the future.")}
            )
        # Year 2000 is a leap year: February 29 stays valid without a year.
        year = self.birthday_year or 2000
        if self.birthday_day > calendar.monthrange(year, self.birthday_month)[1]:
            raise ValidationError({"birthday_day": gettext_lazy("Enter a valid date.")})

    @property
    def email(self) -> str | None:
        """Get the decoded email address."""
        return decode_email(self.email_address)

    def set_email(self, value: str | None) -> None:
        """Set the email address, encoding it for storage."""
        self.email_address = encode_email(value)


class PersonPermission(BaseObjectPermission):
    """Model for permissions on a person."""

    person = models.ForeignKey(Person, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("user", "person")

    @classproperty
    def filter_name(self):
        return "person"


class PersonGroupQuerySet(UserPermissionQuerySet):
    """QuerySet for PersonGroup model with hierarchy query methods."""

    def accessible_by(self, user):
        """Return groups accessible directly or through inherited parent permissions."""
        if not user or not user.is_authenticated:
            return self.none()

        # The descendants of the groups shared with a cascading permission, resolved in the
        # same statement so the live hierarchy is used whatever its depth
        cascading_groups = PersonGroupPermission.objects.filter(
            user=user, inherit_permissions=True
        ).values("group_id")
        inherited_groups = self.model.hierarchy_subquery(cascading_groups)

        return self.filter(Q(shared_with=user) | Q(pk__in=inherited_groups)).distinct()

    def root_groups_for_user(self, user):
        """Return all root groups (without parents) accessible by a user."""
        return self.accessible_by(user).filter(parent_groups__isnull=True)

    def children_for_user(self, parent_group, user):
        """Return all children groups of a group accessible by a user."""
        return self.accessible_by(user).filter(parent_groups=parent_group)

    def with_prefetched_relations(self):
        """Return queryset with prefetched parent_groups and child_groups.

        Use this method when you need to traverse the hierarchy to avoid N+1 queries.
        """
        return self.prefetch_related("parent_groups", "child_groups")


class PersonGroupManager(models.Manager.from_queryset(PersonGroupQuerySet)):
    """Manager for PersonGroup model with hierarchy query methods."""


class HierarchicalDAGMixin:
    """Mixin for models structured as a directed acyclic graph (DAG).

    Provides recursive queries for descendants and ancestors, path-to-root and cycle
    detection. The hierarchy is always read from the database, so nothing goes stale.
    """

    parent_rel_name = None
    child_rel_name = None
    cycle_error_message = None

    @classmethod
    def _get_parent_rel_name(cls) -> str:
        if not cls.parent_rel_name:
            msg = f"{cls.__name__} must define 'parent_rel_name'."
            raise NotImplementedError(msg)
        return cls.parent_rel_name

    @classmethod
    def _get_child_rel_name(cls) -> str:
        if not cls.child_rel_name:
            msg = f"{cls.__name__} must define 'child_rel_name'."
            raise NotImplementedError(msg)
        return cls.child_rel_name

    @classmethod
    def _get_cycle_error_message(cls) -> str:
        if not cls.cycle_error_message:
            msg = f"{cls.__name__} must define 'cycle_error_message'."
            raise NotImplementedError(msg)
        return cls.cycle_error_message

    @classmethod
    def hierarchy_subquery(cls, start, *, ancestors=False, include_start=False) -> RawSQL:
        """Return a subquery of the pks reachable from ``start`` in the hierarchy.

        ``start`` is a queryset of the pks to start from (``.values(...)`` on one column), or an
        iterable of nodes of this model (an empty one reaches nothing). The result holds their
        descendants, or their ancestors when ``ancestors`` is True, and the starting pks
        themselves when ``include_start`` is True. It is a recursive query embedded
        in the caller's statement, so it costs no extra query whatever the depth; ``UNION``
        drops the rows already found, so a cycle stored in the database cannot loop. On such a
        cycle the descendants (or ancestors) of a node include the node itself.
        """
        manager = cls._default_manager
        if not isinstance(start, models.QuerySet):
            start = manager.filter(pk__in=[node.pk for node in start]).values("pk")
        if not start.query.is_sliced:
            start = start.order_by()
        if len(start.query.values_select) != 1:
            msg = "The start of a hierarchy subquery must select exactly one column."
            raise ValueError(msg)
        quote = connection.ops.quote_name
        field = cls._meta.get_field(cls._get_parent_rel_name())
        child_fk = quote(field.m2m_column_name())
        parent_fk = quote(field.m2m_reverse_name())
        from_fk, to_fk = (child_fk, parent_fk) if ancestors else (parent_fk, child_fk)
        edges = quote(field.m2m_db_table())
        # The compiled start query keeps its values as parameters (S608 below)
        try:
            start_sql, start_params = start.query.sql_with_params()
        except EmptyResultSet:
            # Django compiles no SQL for a start known to be empty: use a valid empty one
            empty = manager.filter(pk__isnull=True).values("pk")
            start_sql, start_params = empty.query.sql_with_params()
        if include_start:
            anchor = f"SELECT start_nodes.* FROM ({start_sql}) AS start_nodes"  # noqa: S608
        else:
            anchor = (
                f"SELECT edge.{to_fk} FROM {edges} AS edge "  # noqa: S608
                f"WHERE edge.{from_fk} IN ({start_sql})"
            )
        sql = f"""
            WITH RECURSIVE hierarchy_nodes(node_id) AS (
                {anchor}
                UNION
                SELECT edge.{to_fk}
                FROM {edges} AS edge
                JOIN hierarchy_nodes ON edge.{from_fk} = hierarchy_nodes.node_id
            )
            SELECT node_id FROM hierarchy_nodes
        """  # noqa: S608 - identifiers come from model metadata, values are parameters
        return RawSQL(sql, start_params)  # noqa: S611 - see the comment on ``sql``

    def get_children(self):
        """Returns all direct child objects."""
        return getattr(self, self._get_child_rel_name()).all()

    def get_descendants(self) -> list:
        """Returns all descendant objects (recursively), in a single query."""
        return self._get_hierarchy_nodes(ancestors=False)

    def get_ancestors(self) -> list:
        """Returns all parent objects (up to the root), in a single query."""
        return self._get_hierarchy_nodes(ancestors=True)

    def _get_hierarchy_nodes(self, *, ancestors: bool) -> list:
        manager = type(self)._default_manager  # noqa: SLF001
        nodes = self.hierarchy_subquery([self], ancestors=ancestors)
        # A cycle stored in the database would bring the node back
        return list(manager.filter(pk__in=nodes).exclude(pk=self.pk))

    def get_primary_ancestors_path(self, within=None) -> list:
        """Returns a specific path of ancestors (for breadcrumbs).

        Follows parents step-by-step from child to root, avoiding full-table scans. When
        ``within`` (a queryset of this model, e.g. the ones a user can access) is given, the
        ancestors outside it are left out of the path.
        """
        parent_rel_name = self._get_parent_rel_name()
        ancestors = []
        current = self
        visited = {self.pk}

        while True:
            parents = list(getattr(current, parent_rel_name).all())
            if not parents:
                break

            next_parent = None
            for parent in parents:
                if parent.pk not in visited:
                    next_parent = parent
                    visited.add(parent.pk)
                    break

            if not next_parent:
                break

            ancestors.append(next_parent)
            current = next_parent

        ancestors.reverse()
        if within is None or not ancestors:
            return ancestors
        kept = set(
            within.filter(pk__in=[node.pk for node in ancestors]).values_list("pk", flat=True)
        )
        return [node for node in ancestors if node.pk in kept]

    def has_cycle_with(self, potential_parent):
        """Checks if adding a parent would create a cycle."""
        if potential_parent == self:
            return True
        return self in potential_parent.get_ancestors()

    def clean(self):
        """Custom validation to avoid cycles."""
        super().clean()
        if self.pk:
            parent_rel = getattr(self, self._get_parent_rel_name())
            cycle_error = self._get_cycle_error_message()
            for parent in parent_rel.all():
                if self.has_cycle_with(parent):
                    raise ValidationError(cycle_error)


class PersonGroup(HierarchicalDAGMixin, models.Model):
    """Model for a group of persons."""

    parent_rel_name = "parent_groups"
    child_rel_name = "child_groups"
    cycle_error_message = gettext_lazy(
        "Adding this parent would create a cycle in the group hierarchy."
    )

    group_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.TextField(unique=False, null=False)
    parent_groups = models.ManyToManyField(
        "self", symmetrical=False, related_name="child_groups", blank=True
    )
    creation_date = models.DateTimeField(auto_now_add=True)
    shared_with = models.ManyToManyField(
        User, through="PersonGroupPermission", related_name="%(app_label)s_%(class)s_shared_with"
    )

    # Custom manager
    objects = PersonGroupManager()

    class Meta:
        verbose_name = gettext_lazy("Person group")
        verbose_name_plural = gettext_lazy("Person groups")

    def __str__(self) -> str:
        return f"{self.name}"

    def get_absolute_url(self) -> str:
        return reverse("gift_manager:person_group_edit", kwargs={"pk": self.pk})

    def get_all_members(self, include_nested=False):
        """Returns all persons in this group.

        Args:
            include_nested: If True, also include members from all descendant groups

        Returns:
            QuerySet of Person objects
        """
        if not include_nested:
            return self.person_set.all()

        # The live hierarchy, like the surprise hiding that relies on it
        descendants = self.hierarchy_subquery([self], include_start=True)
        return Person.objects.filter(groups__in=descendants).distinct()


class PersonGroupPermission(BaseObjectPermission):
    """Model for permissions on a group."""

    group = models.ForeignKey(PersonGroup, on_delete=models.CASCADE)
    inherit_permissions = models.BooleanField(
        default=False,
        help_text="If true, this permission level cascades to all child groups",
    )

    class Meta:
        unique_together = ("user", "group")

    @classproperty
    def filter_name(self):
        return "group"


class GiftTagQuerySet(UserPermissionQuerySet):
    """QuerySet for GiftTag model with hierarchy query methods."""

    def accessible_by(self, user):
        """Return all tags accessible by a user."""
        return self.filter(Q(is_public=True) | Q(shared_with=user)).distinct()

    def root_tags_for_user(self, user):
        """Return all root tags accessible by a user."""
        return self.accessible_by(user).filter(parent_tags__isnull=True)

    def children_for_user(self, parent_tag, user):
        """Return all children tags of a tag accessible by a user."""
        return self.accessible_by(user).filter(parent_tags=parent_tag)

    def with_prefetched_relations(self):
        """Return queryset with prefetched parent_tags and child_tags.

        Use this method when you need to traverse the hierarchy to avoid N+1 queries.
        """
        return self.prefetch_related("parent_tags", "child_tags")


class GiftTagManager(models.Manager.from_queryset(GiftTagQuerySet)):
    """Manager for GiftTag model with hierarchy query methods."""


class GiftTag(HierarchicalDAGMixin, models.Model):
    """Model for a gift tag."""

    parent_rel_name = "parent_tags"
    child_rel_name = "child_tags"
    cycle_error_message = gettext_lazy(
        "Adding this parent would create a cycle in the tag hierarchy."
    )

    tag_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.TextField(unique=False, null=False, db_index=True)
    parent_tags = models.ManyToManyField(
        "self", symmetrical=False, related_name="child_tags", blank=True
    )
    creation_date = models.DateTimeField(auto_now_add=True)
    is_public = models.BooleanField(default=False, help_text="If true, this tag is public.")
    shared_with = models.ManyToManyField(
        User, through="GiftTagPermission", related_name="%(app_label)s_%(class)s_shared_with"
    )

    # Custom manager
    objects = GiftTagManager()

    def __str__(self):
        return f"{self.name}"

    def get_all_gifts(self, user=None):
        """Returns gifts associated with this tag and descendants, optionally user-filtered."""
        tags = GiftTag.objects.filter(pk__in=self.hierarchy_subquery([self], include_start=True))
        if user is None:
            return Gift.objects.filter(tags__in=tags).distinct()

        accessible_tags = GiftTag.objects.accessible_by(user)
        if not accessible_tags.filter(pk=self.pk).exists():
            return Gift.objects.none()

        tags = tags.filter(pk__in=accessible_tags.values("pk"))
        return Gift.objects.accessible_by(user).filter(tags__in=tags).distinct()


class GiftTagPermission(BaseObjectPermission):
    """Model for permissions on a gift tag."""

    gift_tag = models.ForeignKey(GiftTag, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("user", "gift_tag")

    @classproperty
    def filter_name(self):
        return "gift_tag"


class Gift(models.Model):
    """Model for a gift."""

    gift_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.TextField(unique=False, null=False)
    comment = models.TextField(unique=False, null=True, blank=True)
    url = models.URLField(
        max_length=2000,
        blank=True,
        default="",
        validators=[validate_http_url],
        verbose_name=gettext_lazy("Link"),
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        verbose_name=gettext_lazy("Estimated price"),
    )
    tags = models.ManyToManyField(GiftTag, related_name="gifts", blank=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    shared_with = models.ManyToManyField(
        User, through="GiftPermission", related_name="%(app_label)s_%(class)s_shared_with"
    )

    # Custom manager
    objects = GiftManager()

    class Meta:
        verbose_name = gettext_lazy("Gift")
        verbose_name_plural = gettext_lazy("Gifts")
        constraints = [
            models.CheckConstraint(
                condition=Q(price__isnull=True) | Q(price__gte=0),
                name="gift_price_non_negative",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name}"


class GiftPermission(BaseObjectPermission):
    """Model for permissions on a gift."""

    gift = models.ForeignKey(Gift, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("user", "gift")

    @classproperty
    def filter_name(self):
        return "gift"


class EventNameDescriptor(DeferredAttribute):
    """Return the name in the active language for the global Birthday event.

    The stored name stays the canonical English one: only reading it translates, and saving
    writes the stored value back (see ``EventNameField``), so a translation never reaches the
    database. Other events keep the name their user typed.
    """

    def __get__(self, instance, cls=None):
        value = super().__get__(instance, cls)
        if instance is not None and instance.__dict__.get("is_birthday"):
            return gettext("Birthday")
        return value

    def __set__(self, instance, value):
        # Defining __set__ makes this a data descriptor, so it also wins over the instance
        # dictionary on reads; the stored value still lives in that dictionary.
        instance.__dict__[self.field.attname] = value


class EventNameField(models.TextField):
    """Event name that reads translated for the global Birthday event."""

    descriptor_class = EventNameDescriptor

    def deconstruct(self):
        # A plain TextField as far as migrations are concerned: no schema or state change
        name, _path, args, kwargs = super().deconstruct()
        return name, "django.db.models.TextField", args, kwargs

    def pre_save(self, model_instance, add):
        stored = model_instance.__dict__.get(self.attname)
        return stored if stored is not None else super().pre_save(model_instance, add)

    def value_from_object(self, obj):
        stored = obj.__dict__.get(self.attname)
        return stored if stored is not None else super().value_from_object(obj)


def birthday_event_name_q(query: str, prefix: str = "") -> Q:
    """Return a filter matching the global Birthday event when the query fits its translated name.

    Its stored name is English, so a search typed in the user's language (for example
    "anniv") would otherwise miss it. ``prefix`` reaches it through a relation (``"event__"``).
    """
    if query.strip() and query.strip().lower() in gettext("Birthday").lower():
        return Q(**{f"{prefix}is_birthday": True})
    return Q()


class Event(models.Model):
    """Model for an event."""

    class ScheduleType(models.TextChoices):
        UNSCHEDULED = "unscheduled", gettext_lazy("No date yet")
        ONE_TIME = "one_time", gettext_lazy("One-time")
        RECURRING = "recurring", gettext_lazy("Repeating")

    RECURRENCE_CHOICES = [
        ("daily", gettext_lazy("Daily")),
        ("weekly", gettext_lazy("Weekly")),
        ("monthly", gettext_lazy("Monthly")),
        ("yearly", gettext_lazy("Yearly")),
    ]

    # Stored name of the global Birthday event; it reads translated (see EventNameDescriptor)
    BIRTHDAY_EVENT_NAME = "Birthday"

    event_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = EventNameField(unique=False, null=False)
    comment = models.TextField(unique=False, null=True, blank=True)
    schedule_type = models.CharField(
        max_length=20,
        choices=ScheduleType.choices,
        default=ScheduleType.UNSCHEDULED,
    )
    date = models.DateField(unique=False, null=True, blank=True)
    recurrence = models.CharField(
        max_length=20,
        choices=RECURRENCE_CHOICES,
        null=True,
        blank=True,
    )
    creation_date = models.DateTimeField(auto_now_add=True)
    # Global events are visible (read-only) to every user; only superusers can change them.
    is_global = models.BooleanField(default=False, editable=False)
    # Marks the global event used for birthday gift plans (the name is user-visible).
    is_birthday = models.BooleanField(default=False, editable=False)
    shared_with = models.ManyToManyField(
        User, through="EventPermission", related_name="%(app_label)s_%(class)s_shared_with"
    )

    # Custom manager
    objects = EventManager()

    class Meta:
        verbose_name = gettext_lazy("Event")
        verbose_name_plural = gettext_lazy("Events")
        constraints = [
            models.UniqueConstraint(
                fields=["is_birthday"],
                condition=Q(is_birthday=True),
                name="event_single_birthday_event",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name}"

    @property
    def is_scheduled(self) -> bool:
        return self.schedule_type != self.ScheduleType.UNSCHEDULED and self.date is not None

    @property
    def is_recurring(self) -> bool:
        return self.schedule_type == self.ScheduleType.RECURRING and bool(self.recurrence)

    @property
    def date_summary(self) -> str:
        if not self.is_scheduled:
            if self.is_birthday:
                # No date of its own: gift plans take the recipient's next birthday
                return gettext("Repeats yearly, on the recipient's birthday")
            return gettext("No date yet")

        formatted_date = formats.date_format(self.date, "DATE_FORMAT")
        if self.is_recurring:
            return gettext("Repeats %(recurrence)s from %(date)s") % {
                "recurrence": self.recurrence_sentence_label,
                "date": formatted_date,
            }
        return formatted_date

    @property
    def recurrence_sentence_label(self) -> str:
        """Return the recurrence label in the grammar used by date summaries."""
        labels = {
            "daily": gettext("daily"),
            "weekly": gettext("weekly"),
            "monthly": gettext("monthly"),
            "yearly": gettext("yearly"),
        }
        return labels.get(self.recurrence, self.get_recurrence_display().lower())

    def clean(self):
        """Keep the schedule fields consistent with the selected schedule type."""
        super().clean()
        errors = {}

        if self.schedule_type == self.ScheduleType.UNSCHEDULED:
            if self.date is not None:
                errors["date"] = gettext_lazy("Leave the date empty for unscheduled events.")
            if self.recurrence:
                errors["recurrence"] = gettext_lazy(
                    "Leave the recurrence empty for unscheduled events."
                )
        elif self.schedule_type == self.ScheduleType.ONE_TIME:
            if self.date is None:
                errors["date"] = gettext_lazy("Choose a date.")
            if self.recurrence:
                errors["recurrence"] = gettext_lazy("One-time events cannot have a recurrence.")
        elif self.schedule_type == self.ScheduleType.RECURRING:
            if self.date is None:
                errors["date"] = gettext_lazy("Choose a date.")
            if not self.recurrence:
                errors["recurrence"] = gettext_lazy("Choose a recurrence.")
        else:
            errors["schedule_type"] = gettext_lazy("Choose a valid schedule.")

        if errors:
            raise ValidationError(errors)

    def next_occurrence(self, today=None):
        """Return the next occurrence date for scheduled events."""
        if not self.is_scheduled:
            return None

        today = today or timezone.localdate()
        if self.schedule_type == self.ScheduleType.ONE_TIME:
            return self.date if self.date >= today else None

        if self.date >= today:
            return self.date

        recurrence_handlers = {
            "daily": self._next_daily_occurrence,
            "weekly": self._next_weekly_occurrence,
            "monthly": self._next_monthly_occurrence,
            "yearly": self._next_yearly_occurrence,
        }
        handler = recurrence_handlers.get(self.recurrence)
        return handler(today) if handler else None

    def _next_daily_occurrence(self, today: date_class) -> date_class:
        return today

    def _next_weekly_occurrence(self, today: date_class) -> date_class:
        days_until_next = (7 - ((today - self.date).days % 7)) % 7
        return today + timedelta(days=days_until_next)

    def _next_monthly_occurrence(self, today: date_class) -> date_class:
        day = min(self.date.day, calendar.monthrange(today.year, today.month)[1])
        candidate = date_class(today.year, today.month, day)
        if candidate >= today:
            return candidate

        year = today.year + (today.month // 12)
        month = 1 if today.month == 12 else today.month + 1
        day = min(self.date.day, calendar.monthrange(year, month)[1])
        return date_class(year, month, day)

    def _next_yearly_occurrence(self, today: date_class) -> date_class:
        return next_yearly_occurrence(self.date.month, self.date.day, today)


class EventPermission(BaseObjectPermission):
    """Model for permissions on an event."""

    event = models.ForeignKey(Event, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("user", "event")

    @classproperty
    def filter_name(self):
        return "event"


class WishPriority(models.IntegerChoices):
    LOW = 1, gettext_lazy("Nice to have")
    MEDIUM = 2, gettext_lazy("Would love")
    HIGH = 3, gettext_lazy("Must have")


class WishQuerySet(models.QuerySet):
    """QuerySet for Wish model with explicit visibility filters."""

    def for_wisher(self, user):
        """Return active and archived wishes belonging to the wisher."""
        if not user or not user.is_authenticated:
            return self.none()
        return self.filter(wisher=user)

    def visible_to_friend(self, friend_user, wisher_user):
        """Return active wishes of a friend, visible only to confirmed friends."""
        if not friend_user or not friend_user.is_authenticated:
            return self.none()
        if not Profile.objects.filter(user=friend_user, friends__user=wisher_user).exists():
            return self.none()
        return self.filter(wisher=wisher_user).filter(
            Q(is_archived=False) | Q(claimed_by=friend_user)
        )


class Wish(models.Model):
    """A personal wish authored by a user, visible to confirmed friends."""

    wish_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    wisher = models.ForeignKey(User, on_delete=models.CASCADE, related_name="wishes")
    title = models.CharField(gettext_lazy("Title"), max_length=255)
    url = models.URLField(
        gettext_lazy("Link"),
        max_length=2000,
        blank=True,
        default="",
        validators=[validate_http_url],
    )
    price_hint = models.DecimalField(
        gettext_lazy("Price hint"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=gettext_lazy("Expected or typical price in your profile currency."),
    )
    notes = models.TextField(
        gettext_lazy("Notes"),
        blank=True,
        help_text=gettext_lazy("Sizes, colors, specifications."),
    )
    priority = models.IntegerField(
        gettext_lazy("Priority"),
        choices=WishPriority.choices,
        default=WishPriority.MEDIUM,
    )
    is_archived = models.BooleanField(
        gettext_lazy("Archived"),
        default=False,
        help_text=gettext_lazy("Archived wishes are hidden from friends unless claimed."),
    )
    is_fulfilled = models.BooleanField(
        gettext_lazy("Fulfilled"),
        default=False,
        help_text=gettext_lazy("Marked as fulfilled once given or received."),
    )
    claimed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="claimed_wishes",
    )
    claimed_at = models.DateTimeField(null=True, blank=True)
    wisher_updated_at = models.DateTimeField(
        default=timezone.now,
        help_text=gettext_lazy("Tracks when wisher last modified the wish."),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = WishQuerySet.as_manager()

    class Meta:
        verbose_name = gettext_lazy("Wish")
        verbose_name_plural = gettext_lazy("Wishes")
        ordering = ["-priority", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(claimed_by__isnull=True) | models.Q(claimed_at__isnull=False),
                name="wish_claimed_by_requires_claimed_at",
            ),
            models.CheckConstraint(
                condition=models.Q(price_hint__isnull=True) | models.Q(price_hint__gte=0),
                name="wish_price_hint_non_negative",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.wisher.username})"

    def is_updated_after_claim(self) -> bool:
        """Return whether the wisher modified this wish after it was claimed."""
        return bool(
            self.claimed_by_id
            and self.claimed_at
            and self.wisher_updated_at
            and self.wisher_updated_at > self.claimed_at
        )


class SplitMode(models.TextChoices):
    """How the cost of a group gift is divided among its contributors."""

    EQUAL = "equal", gettext_lazy("Equal split")
    CUSTOM = "custom", gettext_lazy("Custom amounts")


class RelationStatus(models.Model):
    """Model for a relation status."""

    DEFAULT_STATUS = "Idea"

    status = models.TextField(unique=True, null=False)

    class Meta:
        verbose_name = gettext_lazy("Relation Status")
        verbose_name_plural = gettext_lazy("Relation Statuses")

    def __str__(self) -> str:
        return f"{self.status}"

    @classmethod
    def get_default_pk(cls):
        """Get or create the default status and return its primary key.

        This is used as the default for the Relation.status ForeignKey.
        Using a callable that returns a PK avoids migration issues.
        """
        # Use status_en to avoid issues with modeltranslation when the site is in another language
        status, _ = cls.objects.get_or_create(status_en=cls.DEFAULT_STATUS)
        return status.pk


_STATUS_NOT_LOADED = object()


class Relation(models.Model):
    """Model for a relation between a person and a gift."""

    relation_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    person = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name="persons", null=True, blank=True
    )
    group = models.ForeignKey(
        PersonGroup, on_delete=models.CASCADE, related_name="groups", null=True, blank=True
    )
    gift = models.ForeignKey(Gift, on_delete=models.CASCADE, related_name="gifts")
    event = models.ForeignKey(
        Event, on_delete=models.SET_NULL, related_name="relations", null=True, blank=True
    )
    status = models.ForeignKey(
        RelationStatus,
        on_delete=models.PROTECT,
        default=RelationStatus.get_default_pk,
    )
    due_date = models.DateField(unique=False, null=True, blank=True)
    comment = models.TextField(unique=False, null=True, blank=True)
    # Optional overrides of the gift's link and price for this plan
    url = models.URLField(
        max_length=2000,
        blank=True,
        default="",
        validators=[validate_http_url],
        verbose_name=gettext_lazy("Link"),
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        verbose_name=gettext_lazy("Estimated price"),
    )
    creation_date = models.DateTimeField(auto_now_add=True)
    status_changed_at = models.DateTimeField(null=True, blank=True, editable=False)
    reaction_rating = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    reaction_note = models.TextField(null=True, blank=True)
    shared_with = models.ManyToManyField(
        User, through="RelationPermission", related_name="shared_relations"
    )
    # Hides the plan from its recipient when the recipient is also a user of the app
    is_surprise = models.BooleanField(default=False)
    # The collaborator who is buying the gift. ``claimed_at`` can outlive ``claimed_by``
    # when the claimer's account is deleted, so only ``claimed_by`` tells if it is claimed.
    claimed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="claimed_relations",
    )
    claimed_at = models.DateTimeField(null=True, blank=True)
    wish = models.ForeignKey(
        "Wish",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="fulfilling_plans",
        help_text=gettext_lazy("The wish this gift plan fulfills."),
    )
    is_group_gift = models.BooleanField(
        gettext_lazy("Group gift"),
        default=False,
        help_text=gettext_lazy(
            "Whether this gift plan is funded collaboratively by multiple contributors."
        ),
    )
    split_mode = models.CharField(
        max_length=20,
        choices=SplitMode.choices,
        default=SplitMode.EQUAL,
        help_text=gettext_lazy("How the total gift cost is divided among contributors."),
    )

    # Custom manager
    objects = RelationManager()

    class Meta:
        verbose_name = gettext_lazy("Relation")
        verbose_name_plural = gettext_lazy("Relations")
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(person__isnull=False, group__isnull=True)
                    | Q(person__isnull=True, group__isnull=False)
                ),
                name="relation_exactly_one_recipient",
            ),
            models.CheckConstraint(
                condition=Q(reaction_rating__isnull=True)
                | Q(reaction_rating__gte=1, reaction_rating__lte=5),
                name="relation_reaction_rating_range",
            ),
            models.CheckConstraint(
                condition=Q(price__isnull=True) | Q(price__gte=0),
                name="relation_price_non_negative",
            ),
            models.CheckConstraint(
                condition=Q(claimed_by__isnull=True) | Q(claimed_at__isnull=False),
                name="relation_claimed_by_requires_claimed_at",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.recipient_name} - {self.gift} ({self.status})"

    def save(self, *args, **kwargs):
        """Override save method.

        Note: Validation is handled at the form level to avoid recursion issues
        when updating existing instances.
        """
        if self._status_has_changed():
            self.status_changed_at = timezone.now()
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                kwargs["update_fields"] = {*update_fields, "status_changed_at"}
        super().save(*args, **kwargs)
        self._loaded_status_id = self.status_id

    def get_absolute_url(self) -> str:
        return reverse("gift_manager:relation_detail", kwargs={"pk": self.relation_id})

    @property
    def is_claimed(self) -> bool:
        """Return whether a collaborator has claimed this gift plan."""
        return self.claimed_by_id is not None

    @property
    def effective_url(self) -> str:
        """Return the plan's link, falling back to the gift's."""
        return self.url or self.gift.url

    @property
    def effective_price(self):
        """Return the plan's price, falling back to the gift's (``None`` when neither is set)."""
        return self.price if self.price is not None else self.gift.price

    def clean(self):
        """Ensure that exactly one of person or group is set.

        This is primarily used for form validation. For model-level validation,
        forms should call this explicitly.
        """
        super().clean()
        if (self.person is None) == (self.group is None):
            raise ValidationError(
                gettext_lazy("Choose exactly one recipient: a person or a group.")
            )
        if self.wish_id is not None:
            if self.group_id is not None:
                raise ValidationError(
                    gettext_lazy("A gift plan fulfilling a wish must target a person, not a group.")
                )
            if self.person_id is None or self.person.account_id != self.wish.wisher_id:
                raise ValidationError(
                    gettext_lazy("The recipient person must represent the wisher of this wish.")
                )

    @classmethod
    def from_db(cls, db, field_names, values):
        """Remember the loaded status so ``save`` can detect status changes."""
        instance = super().from_db(db, field_names, values)
        instance._loaded_status_id = instance.__dict__.get(  # noqa: SLF001
            "status_id", _STATUS_NOT_LOADED
        )
        return instance

    def refresh_from_db(self, using=None, fields=None, from_queryset=None):
        """Re-sync the remembered status when the status is reloaded."""
        super().refresh_from_db(using=using, fields=fields, from_queryset=from_queryset)
        if fields is None or {"status", "status_id"} & set(fields):
            self._loaded_status_id = self.__dict__.get("status_id", _STATUS_NOT_LOADED)

    def _status_has_changed(self) -> bool:
        """Return whether the status differs from the value loaded from the database."""
        if self._state.adding:
            return self.status_changed_at is None
        loaded_status_id = getattr(self, "_loaded_status_id", _STATUS_NOT_LOADED)
        return loaded_status_id is not _STATUS_NOT_LOADED and loaded_status_id != self.status_id

    @property
    def has_visible_reaction(self) -> bool:
        """Return whether a reaction rating exists and applies to the current status."""
        return self.reaction_rating is not None and can_rate_status(self.status)

    @property
    def recipient(self) -> Person | PersonGroup | None:
        """Return the person or group targeted by this gift plan."""
        return self.person or self.group

    @property
    def recipient_name(self) -> str:
        """Return the display name for the gift plan recipient."""
        recipient = self.recipient
        return str(recipient) if recipient else ""

    @property
    def recipient_type(self) -> str:
        """Return the stable recipient type identifier."""
        if self.person_id is not None:
            return "person"
        if self.group_id is not None:
            return "group"
        return ""

    @property
    def recipient_type_label(self) -> str:
        """Return the user-facing recipient type."""
        if self.person_id is not None:
            return gettext_lazy("Person")
        if self.group_id is not None:
            return gettext_lazy("Group")
        return ""

    @property
    def recipient_key(self) -> str:
        """Return a typed recipient key for forms and UI state."""
        if self.person_id is not None:
            return f"person:{self.person.person_id}"
        if self.group_id is not None:
            return f"group:{self.group.group_id}"
        return ""

    @property
    def recipient_url(self) -> str:
        """Return the recipient detail URL."""
        if self.person_id is not None:
            return reverse("gift_manager:person_detail", kwargs={"pk": self.person.person_id})
        if self.group_id is not None:
            return reverse("gift_manager:person_group_detail", kwargs={"pk": self.group.group_id})
        return ""

    @property
    def is_group_targeted(self) -> bool:
        """Return whether this gift plan targets a group directly."""
        return self.group_id is not None


class RelationContribution(models.Model):
    """One contributor's share of a group gift plan.

    ``amount`` is the share in custom mode, or the frozen paid amount in equal mode.
    ``user`` is cleared when the account is deleted; ``name`` keeps the label so the
    buyer's tally survives.
    """

    relation = models.ForeignKey(
        "Relation",
        on_delete=models.CASCADE,
        related_name="contributions",
    )
    user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gift_contributions",
        help_text=gettext_lazy("Registered user participating in this group gift."),
    )
    name = models.CharField(
        max_length=150,
        help_text=gettext_lazy("Snapshot name of the contributor or external contributor label."),
    )
    amount = models.DecimalField(
        gettext_lazy("Share amount"),
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=gettext_lazy(
            "Stored share amount in custom mode, or frozen paid amount in equal mode."
        ),
    )
    is_paid = models.BooleanField(
        gettext_lazy("Paid"),
        default=False,
        help_text=gettext_lazy("Whether this contributor has paid their share to the buyer."),
    )
    paid_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=gettext_lazy("When this share was marked as paid."),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gte=0),
                name="contribution_amount_non_negative",
            ),
            models.CheckConstraint(
                condition=Q(is_paid=False, paid_at__isnull=True)
                | Q(is_paid=True, paid_at__isnull=False),
                name="contribution_is_paid_requires_paid_at",
            ),
            models.CheckConstraint(
                condition=~Q(name=""),
                name="contribution_requires_name",
            ),
            models.UniqueConstraint(
                fields=["relation", "user"],
                condition=Q(user__isnull=False),
                name="unique_user_contribution_per_plan",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.display_name} ({self.amount})"

    def save(self, *args, **kwargs):
        """Keep ``name`` in sync with the linked user and reject blank external names."""
        if self.user_id is not None:
            self.name = self.user.username
        else:
            self.name = (self.name or "").strip()
            if not self.name:
                raise ValidationError({"name": gettext_lazy("A contributor name is required.")})
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = {*update_fields, "name"}
        super().save(*args, **kwargs)

    @property
    def display_name(self) -> str:
        """Return the live username while the account exists, else the stored name."""
        if self.user_id is not None:
            return self.user.username
        return self.name

    def clean(self):
        """Require a non-blank name for contributors without an account."""
        super().clean()
        self.name = (self.name or "").strip()
        if self.user_id is None and not self.name:
            raise ValidationError({"name": gettext_lazy("A contributor name is required.")})

    def mark_paid(self, amount: Decimal | None = None) -> None:
        """Mark the share as paid, optionally freezing the paid ``amount``."""
        fields = {"is_paid", "paid_at"}
        if not self.is_paid or self.paid_at is None:
            self.paid_at = timezone.now()
        self.is_paid = True
        if amount is not None:
            self.amount = amount
            fields.add("amount")
        self.save(update_fields=fields)

    def mark_unpaid(self) -> None:
        """Clear the paid state and its timestamp."""
        self.is_paid = False
        self.paid_at = None
        self.save(update_fields=["is_paid", "paid_at"])


class RelationPermission(BaseObjectPermission):
    """Model for permissions on a relation."""

    relation = models.ForeignKey(Relation, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("user", "relation")

    @classproperty
    def filter_name(self):
        return "relation"


class RelationComment(models.Model):
    """A short comment left by a collaborator on a gift plan."""

    relation = models.ForeignKey(Relation, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="relation_comments"
    )
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "pk")

    def __str__(self) -> str:
        return f"{self.author} on {self.relation_id}: {str(self.text)[:30]}"


class GiftSuggestionGeneration(models.Model):
    """An AI suggestion generation run for a recipient, used for rate limits and audit."""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="gift_suggestion_generations"
    )
    person = models.ForeignKey(
        Person, on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    group = models.ForeignKey(
        PersonGroup, on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    succeeded = models.BooleanField(default=False)
    idea_count = models.PositiveSmallIntegerField(default=0)
    prompt_version = models.PositiveSmallIntegerField(default=1)
    model = models.CharField(max_length=100, blank=True, default="")
    duration_ms = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        verbose_name = gettext_lazy("Gift suggestion generation")
        verbose_name_plural = gettext_lazy("Gift suggestion generations")
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(person__isnull=False, group__isnull=True)
                    | Q(person__isnull=True, group__isnull=False)
                ),
                name="gift_suggestion_generation_one_recipient",
            ),
        ]

    def __str__(self) -> str:
        recipient = self.person or self.group
        return f"{self.user} - {recipient} at {self.created_at}"


class GiftSuggestion(models.Model):
    """A suggested gift for a recipient (from catalogue scoring or an AI provider)."""

    class Source(models.TextChoices):
        CATALOGUE = "catalogue", gettext_lazy("Catalogue")
        AI = "ai", gettext_lazy("AI")

    class State(models.TextChoices):
        PENDING = "pending", gettext_lazy("Pending")
        ACCEPTED = "accepted", gettext_lazy("Accepted")
        DISMISSED = "dismissed", gettext_lazy("Dismissed")

    class DismissReason(models.TextChoices):
        ALREADY_OWNED_OR_PRACTICED = (
            "already_owned_or_practiced",
            gettext_lazy("Already owned or practiced"),
        )
        DISLIKES = "dislikes", gettext_lazy("Not their taste")
        TOO_EXPENSIVE = "too_expensive", gettext_lazy("Too expensive")
        CUSTOM = "custom", gettext_lazy("Other reason")

    DISMISS_COMMENT_MAX_LENGTH = 120

    suggestion_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="gift_suggestions")
    person = models.ForeignKey(
        Person, on_delete=models.CASCADE, null=True, blank=True, related_name="gift_suggestions"
    )
    group = models.ForeignKey(
        PersonGroup,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="gift_suggestions",
    )
    source = models.CharField(max_length=10, choices=Source.choices)
    state = models.CharField(max_length=10, choices=State.choices, default=State.PENDING)
    dismiss_reason = models.CharField(
        max_length=40,
        choices=DismissReason.choices,
        blank=True,
        default="",
    )
    dismiss_comment = models.CharField(
        max_length=DISMISS_COMMENT_MAX_LENGTH, blank=True, default=""
    )
    gift = models.ForeignKey(
        Gift, on_delete=models.CASCADE, null=True, blank=True, related_name="suggestions"
    )
    generation = models.ForeignKey(
        GiftSuggestionGeneration,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="ideas",
    )
    name = models.TextField(blank=True, default="")
    description = models.TextField(blank=True, default="")
    reason = models.TextField(blank=True, default="")
    tags = models.ManyToManyField(GiftTag, blank=True, related_name="+")
    normalized_name = models.TextField(db_index=True)
    score = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "pk")
        verbose_name = gettext_lazy("Gift suggestion")
        verbose_name_plural = gettext_lazy("Gift suggestions")
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(person__isnull=False, group__isnull=True)
                    | Q(person__isnull=True, group__isnull=False)
                ),
                name="gift_suggestion_one_recipient",
            ),
            models.CheckConstraint(
                condition=Q(source="ai") | Q(gift__isnull=False),
                name="gift_suggestion_catalogue_has_gift",
            ),
            models.CheckConstraint(
                condition=Q(source="catalogue") | ~Q(name=""),
                name="gift_suggestion_ai_has_name",
            ),
            models.UniqueConstraint(
                fields=["user", "person", "gift"],
                condition=Q(source="catalogue", person__isnull=False),
                name="gift_suggestion_unique_catalogue_person",
            ),
            models.UniqueConstraint(
                fields=["user", "group", "gift"],
                condition=Q(source="catalogue", group__isnull=False),
                name="gift_suggestion_unique_catalogue_group",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "person", "state"], name="gift_sugg_user_person_idx"),
            models.Index(fields=["user", "group", "state"], name="gift_sugg_user_group_idx"),
        ]

    def __str__(self) -> str:
        gift_or_name = self.gift.name if self.gift_id is not None else self.name
        return f"{self.user} - {self.recipient}: {gift_or_name} ({self.source}/{self.state})"

    @property
    def recipient(self) -> Person | PersonGroup | None:
        if self.person_id is not None:
            return self.person
        if self.group_id is not None:
            return self.group
        return None


@receiver(post_delete, sender=RelationPermission)
def release_claim_when_access_is_removed(sender, instance, **kwargs):
    """Release the claim a user holds on a plan once they lose access to it."""
    Relation.objects.filter(pk=instance.relation_id, claimed_by_id=instance.user_id).update(
        claimed_by=None, claimed_at=None
    )


@receiver(post_save, sender=Relation)
def release_claim_of_hidden_recipient(sender, instance, created, **kwargs):
    """Release the claim when its holder can no longer see the plan.

    That happens when the plan becomes a surprise for them (the flag is ticked or the recipient
    changes), so a plan is never stuck on a claimer who cannot even open it.
    """
    if created or not instance.is_surprise or instance.claimed_by_id is None:
        return
    claimer = instance.claimed_by
    if Relation.objects.hidden_surprises_for(claimer).filter(pk=instance.pk).exists():
        Relation.objects.filter(pk=instance.pk).update(claimed_by=None, claimed_at=None)
        instance.claimed_by = None
        instance.claimed_at = None


@receiver(pre_delete, sender=Relation)
def remember_wish_owners_before_plan_deletion(sender, instance, **kwargs):
    """Snapshot the plan's owners: their permissions may be gone by ``post_delete``."""
    if instance.wish_id is not None:
        instance._wish_owner_ids = set(  # noqa: SLF001
            RelationPermission.objects.filter(
                relation_id=instance.pk, permission_type=PermissionLevel.OWNER
            ).values_list("user_id", flat=True)
        )


@receiver(post_save, sender=Relation)
def sync_wish_after_plan_save(sender, instance, **kwargs):
    """Keep the wish's claim and fulfilled flag in line with the plan that fulfils it."""
    if instance.wish_id is not None:
        from gift_manager import wishlist

        wishlist.sync_wish_on_plan_change(instance)


@receiver(post_delete, sender=Relation)
def sync_wish_after_plan_deletion(sender, instance, **kwargs):
    """Release the wish's claim when its last active fulfilling plan is deleted."""
    if instance.wish_id is not None:
        from gift_manager import wishlist

        wishlist.sync_wish_on_plan_change(instance, is_deleted=True)
