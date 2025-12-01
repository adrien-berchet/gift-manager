import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import classproperty
from django.utils.translation import gettext_lazy

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


class UserPermissionManager(models.Manager):
    """Base manager for models with user permissions."""

    def accessible_by(self, user):
        """Return all objects accessible by a user."""
        return self.filter(Q(shared_with=user))


class PersonManager(UserPermissionManager):
    """Manager for Person model with additional query methods."""

    def with_groups_annotated(self):
        """Return persons with groups information annotated for Grid.js."""
        from django.contrib.postgres.aggregates import JSONBAgg
        from django.db.models import F, Func, Value

        return self.annotate(
            groups_info=JSONBAgg(
                Func(
                    Value("id"),
                    F("groups__group_id"),
                    Value("name"),
                    F("groups__name"),
                    function="jsonb_build_object",
                ),
                filter=Q(groups__group_id__isnull=False),
                distinct=True,
            )
        )

    def with_complete_name(self):
        """Return persons with complete_name annotation (family_name + first_name)."""
        from django.db.models import TextField, Value
        from django.db.models.functions import Concat

        return self.annotate(
            complete_name=Concat(
                "family_name", Value(" "), "first_name", output_field=TextField()
            )
        )

    def for_list_display(self, user):
        """Return queryset optimized for list display with all necessary annotations."""
        return (
            self.accessible_by(user)
            .with_groups_annotated()
            .values("person_id", "first_name", "family_name", "email_address", "groups_info")
        )


class GiftManager(UserPermissionManager):
    """Manager for Gift model with additional query methods."""

    def with_tags_annotated(self):
        """Return gifts with tags information annotated for Grid.js."""
        from django.contrib.postgres.aggregates import JSONBAgg
        from django.db.models import F, Func, Value

        return self.annotate(
            tags_info=JSONBAgg(
                Func(
                    Value("id"),
                    F("tags__tag_id"),
                    Value("name"),
                    F("tags__name"),
                    function="jsonb_build_object",
                ),
                filter=Q(tags__tag_id__isnull=False),
                distinct=True,
            )
        )

    def for_list_display(self, user):
        """Return queryset optimized for list display with all necessary annotations."""
        return (
            self.accessible_by(user)
            .with_tags_annotated()
            .values("gift_id", "name", "comment", "tags_info")
        )


class EventManager(UserPermissionManager):
    """Manager for Event model with additional query methods."""

    def for_list_display(self, user):
        """Return queryset optimized for list display."""
        return self.accessible_by(user).values("event_id", "name", "comment", "usual_date")


class RelationManager(UserPermissionManager):
    """Manager for Relation model with additional query methods."""

    def with_related_objects(self):
        """Return relations with all related objects selected."""
        return self.select_related("person", "group", "gift", "event", "status")

    def with_related_object_name(self):
        """Return relations with related_object annotation (person or group name)."""
        from django.db.models import TextField, Value
        from django.db.models.functions import Coalesce, Concat, NullIf

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
                "event__event_id",
                "status",
                "due_date",
            )
        )


class Profile(models.Model):
    """Model for a user profile."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    friends = models.ManyToManyField("self", symmetrical=True, blank=True)

    def __str__(self):
        return f"{gettext_lazy('Profile of')} {self.user.username}"

    def get_absolute_url(self) -> str:
        return reverse("gift_manager:profile_detail")


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):  # noqa: ARG001
    if created:  # pragma: no branch
        Profile.objects.create(user=instance)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def save_user_profile(sender, instance, **kwargs):  # noqa: ARG001
    if hasattr(instance, "profile"):
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
    recipient_email = models.EmailField()
    accepted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return (
            f"{gettext_lazy('Invitation from')} {self.sender} "
            f"{gettext_lazy('to')} {self.recipient_email}"
        )

    def is_expired(self):
        """Check if the invitation has expired."""
        if not hasattr(settings, "INVITATION_EXPIRY_DAYS"):
            return False  # If not configured, invitations don't expire

        expiry_days = getattr(settings, "INVITATION_EXPIRY_DAYS", 7)
        expiry_date = self.created_at + timedelta(days=expiry_days)
        return timezone.now() > expiry_date


class Person(models.Model):
    """Model for a person."""

    person_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    first_name = models.TextField(unique=False, null=False)
    family_name = models.TextField(unique=False, null=True, blank=True)
    email_address = models.EmailField(unique=False, null=True, blank=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    groups = models.ManyToManyField("PersonGroup", blank=True)
    shared_with = models.ManyToManyField(
        User, through="PersonPermission", related_name="%(app_label)s_%(class)s_shared_with"
    )
    user_link = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="%(app_label)s_%(class)s_user",
        null=True,
        blank=True,
    )

    # Custom manager
    objects = PersonManager()

    class Meta:
        verbose_name = gettext_lazy("Person")
        verbose_name_plural = gettext_lazy("Persons")

    def __str__(self) -> str:
        return (self.first_name + " " + (self.family_name or "")).strip()


class PersonPermission(models.Model):
    """Model for permissions on a person."""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    person = models.ForeignKey(Person, on_delete=models.CASCADE)
    permission_type = models.IntegerField(
        choices=PermissionLevel.CHOICES, default=PermissionLevel.VIEWER
    )

    class Meta:
        unique_together = ("user", "person")

    def __str__(self):
        return f"{self.user} - {self.person} -> {PermissionLevel.get_label(self.permission_type)}"

    @classproperty
    def filter_name(self):
        return "person"


class PersonGroup(models.Model):
    """Model for a group of persons."""

    group_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.TextField(unique=False, null=False)
    creation_date = models.DateTimeField(auto_now_add=True)
    shared_with = models.ManyToManyField(
        User, through="PersonGroupPermission", related_name="%(app_label)s_%(class)s_shared_with"
    )

    # Custom manager
    objects = UserPermissionManager()  # PersonGroup uses basic manager

    class Meta:
        verbose_name = gettext_lazy("Person group")
        verbose_name_plural = gettext_lazy("Person groups")

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("gift_manager:person_group_edit", kwargs={"pk": self.pk})


class PersonGroupPermission(models.Model):
    """Model for permissions on a group."""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    group = models.ForeignKey(PersonGroup, on_delete=models.CASCADE)
    permission_type = models.IntegerField(
        choices=PermissionLevel.CHOICES, default=PermissionLevel.VIEWER
    )

    class Meta:
        unique_together = ("user", "group")

    def __str__(self):
        return f"{self.user} - {self.group} -> {PermissionLevel.get_label(self.permission_type)}"

    @classproperty
    def filter_name(self):
        return "group"


class GiftTagManager(models.Manager):
    def accessible_by(self, user):
        """Return all tags accessible by a user."""
        return self.filter(Q(is_public=True) | Q(shared_with=user))

    def root_tags_for_user(self, user):
        """Return all root tags accessible by a user."""
        return self.accessible_by(user).filter(parent_tags__isnull=True)

    def children_for_user(self, parent_tag, user):
        """Return all children tags of a tag accessible by a user."""
        return self.accessible_by(user).filter(parent_tags=parent_tag)

    def with_prefetched_relations(self):
        """
        Return queryset with prefetched parent_tags and child_tags.

        Use this method when you need to traverse the hierarchy to avoid N+1 queries.
        """
        return self.prefetch_related('parent_tags', 'child_tags')


class GiftTag(models.Model):
    """Model for a gift tag."""

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
        return self.name

    def get_children(self):
        """Returns all direct child tags."""
        return self.child_tags.all()

    def get_descendants(self, use_cache=True):
        """
        Returns all descendant tags (recursively).

        Optimized to fetch all descendants in a single query using prefetch_related,
        then traverse the hierarchy in memory to avoid N+1 queries.

        Args:
            use_cache: If True, use cached results when available (default: True)
        """
        # Check cache first
        cache_key = f'gifttag_descendants_{self.pk}'
        if use_cache:
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                return cached_result

        # Fetch all potentially needed tags upfront to avoid multiple queries
        # We'll prefetch child_tags for efficient traversal
        all_tags = {self.pk: self}
        descendants = set()
        to_process = list(self.child_tags.prefetch_related('child_tags').all())
        processed_ids = {self.pk}

        # Build cache of all tags we'll need
        for tag in to_process:
            all_tags[tag.pk] = tag

        while to_process:
            current = to_process.pop(0)
            if current.pk in processed_ids:
                continue

            processed_ids.add(current.pk)
            descendants.add(current)

            # Get children from prefetched data
            children = list(current.child_tags.all())
            for child in children:
                if child.pk not in processed_ids:
                    if child.pk not in all_tags:
                        all_tags[child.pk] = child
                        # Prefetch for next level
                        child = GiftTag.objects.prefetch_related('child_tags').get(pk=child.pk)
                    to_process.append(child)

        result = list(descendants)

        # Cache the result for 1 hour
        if use_cache:
            cache.set(cache_key, result, 3600)

        return result

    def get_ancestors(self, use_cache=True):
        """
        Returns all parent tags (up to the root).

        Optimized to fetch all ancestors in a single query using prefetch_related,
        then traverse the hierarchy in memory to avoid N+1 queries.

        Args:
            use_cache: If True, use cached results when available (default: True)
        """
        # Check cache first
        cache_key = f'gifttag_ancestors_{self.pk}'
        if use_cache:
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                return cached_result

        # Fetch all potentially needed tags upfront to avoid multiple queries
        all_tags = {self.pk: self}
        ancestors = set()
        to_process = list(self.parent_tags.prefetch_related('parent_tags').all())
        processed_ids = {self.pk}

        # Build cache of all tags we'll need
        for tag in to_process:
            all_tags[tag.pk] = tag

        while to_process:
            current = to_process.pop(0)
            if current.pk in processed_ids:
                continue

            processed_ids.add(current.pk)
            ancestors.add(current)

            # Get parents from prefetched data
            parents = list(current.parent_tags.all())
            for parent in parents:
                if parent.pk not in processed_ids:
                    if parent.pk not in all_tags:
                        all_tags[parent.pk] = parent
                        # Prefetch for next level
                        parent = GiftTag.objects.prefetch_related('parent_tags').get(pk=parent.pk)
                    to_process.append(parent)

        result = list(ancestors)

        # Cache the result for 1 hour
        if use_cache:
            cache.set(cache_key, result, 3600)

        return result

    def get_primary_ancestors_path(self):
        """
        Returns a specific path of ancestors (for breadcrumbs).

        Optimized to prefetch parent_tags to avoid N+1 queries.
        """
        # Arbitrarily choosing the first parent at each level
        ancestors = []
        current = self
        visited = {self.pk}

        # Prefetch parent_tags for the initial tag
        if not hasattr(self, '_prefetched_objects_cache'):
            current = GiftTag.objects.prefetch_related('parent_tags').get(pk=self.pk)

        while True:
            parents = list(current.parent_tags.all())
            if not parents:
                break

            # Take the first parent that doesn't create a cycle
            next_parent = None
            for parent in parents:
                if parent.pk not in visited:
                    next_parent = parent
                    visited.add(parent.pk)
                    break

            if not next_parent:
                break

            ancestors.append(next_parent)
            # Prefetch for next iteration
            current = GiftTag.objects.prefetch_related('parent_tags').get(pk=next_parent.pk)

        ancestors.reverse()
        return ancestors

    def has_cycle_with(self, potential_parent):
        """Checks if adding a parent would create a cycle."""
        if potential_parent == self:
            return True

        # Check if we are already an ancestor of the potential parent
        return self in potential_parent.get_ancestors()

    def get_all_gifts(self):
        """Returns all gifts associated with this tag and its descendants."""
        tags = [self, *self.get_descendants()]
        return Gift.objects.filter(tags__in=tags).distinct()

    def clear_hierarchy_cache(self):
        """Clear cached hierarchy data for this tag and related tags."""
        # Clear cache for this tag
        cache.delete(f'gifttag_descendants_{self.pk}')
        cache.delete(f'gifttag_ancestors_{self.pk}')

        # Clear cache for all ancestors (since their descendants changed)
        for ancestor in self.get_ancestors(use_cache=False):
            cache.delete(f'gifttag_descendants_{ancestor.pk}')

        # Clear cache for all descendants (since their ancestors changed)
        for descendant in self.get_descendants(use_cache=False):
            cache.delete(f'gifttag_ancestors_{descendant.pk}')

    def clean(self):
        """Custom validation to avoid cycles."""
        if self.pk:
            for parent in self.parent_tags.all():
                if self.has_cycle_with(parent):
                    raise ValidationError(
                        gettext_lazy(
                            "Adding this parent would create a cycle in the tag hierarchy."
                        )
                    )


class GiftTagPermission(models.Model):
    """Model for permissions on a gift tag."""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    gift_tag = models.ForeignKey(GiftTag, on_delete=models.CASCADE)
    permission_type = models.IntegerField(
        choices=PermissionLevel.CHOICES, default=PermissionLevel.VIEWER
    )

    class Meta:
        unique_together = ("user", "gift_tag")

    def __str__(self) -> str:
        return f"{self.user} - {self.gift_tag} -> {PermissionLevel.get_label(self.permission_type)}"

    @classproperty
    def filter_name(self):
        return "gift_tag"


class Gift(models.Model):
    """Model for a gift."""

    gift_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.TextField(unique=False, null=False)
    comment = models.TextField(unique=False, null=True, blank=True)
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

    def __str__(self) -> str:
        return self.name


class GiftPermission(models.Model):
    """Model for permissions on a gift."""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    gift = models.ForeignKey(Gift, on_delete=models.CASCADE)
    permission_type = models.IntegerField(
        choices=PermissionLevel.CHOICES, default=PermissionLevel.VIEWER
    )

    class Meta:
        unique_together = ("user", "gift")

    def __str__(self):
        return f"{self.user} - {self.gift} -> {PermissionLevel.get_label(self.permission_type)}"

    @classproperty
    def filter_name(self):
        return "gift"


class Event(models.Model):
    """Model for an event."""

    event_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.TextField(unique=False, null=False)
    comment = models.TextField(unique=False, null=True, blank=True)
    usual_date = models.DateField(unique=False, null=True, blank=True)
    absolute_date = models.DateField(unique=False, null=True, blank=True)
    recurrence = models.CharField(
        max_length=20,
        choices=[
            ("daily", "Daily"),
            ("weekly", "Weekly"),
            ("monthly", "Monthly"),
            ("yearly", "Yearly"),
        ],
        null=True,
        blank=True,
    )
    creation_date = models.DateTimeField(auto_now_add=True)
    shared_with = models.ManyToManyField(
        User, through="EventPermission", related_name="%(app_label)s_%(class)s_shared_with"
    )

    # Custom manager
    objects = EventManager()

    class Meta:
        verbose_name = gettext_lazy("Event")
        verbose_name_plural = gettext_lazy("Events")

    def __str__(self) -> str:
        return self.name


class EventPermission(models.Model):
    """Model for permissions on an event."""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    permission_type = models.IntegerField(
        choices=PermissionLevel.CHOICES, default=PermissionLevel.VIEWER
    )

    class Meta:
        unique_together = ("user", "event")

    def __str__(self):
        return f"{self.user} - {self.event} -> {PermissionLevel.get_label(self.permission_type)}"

    @classproperty
    def filter_name(self):
        return "event"


class RelationStatus(models.Model):
    """Model for a relation status."""

    status = models.TextField(unique=True, null=False)

    class Meta:
        verbose_name = gettext_lazy("Relation Status")
        verbose_name_plural = gettext_lazy("Relation Statuses")

    def __str__(self) -> str:
        return self.status


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
        on_delete=models.CASCADE,
        default="Idea",
    )
    due_date = models.DateField(unique=False, null=True, blank=True)
    comment = models.TextField(unique=False, null=True, blank=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    shared_with = models.ManyToManyField(
        User, through="RelationPermission", related_name="shared_relations"
    )

    # Custom manager
    objects = RelationManager()

    class Meta:
        verbose_name = gettext_lazy("Relation")
        verbose_name_plural = gettext_lazy("Relations")

    def __str__(self) -> str:
        return f"{self.person} - {self.gift} ({self.status})"

    def save(self, *args, **kwargs):
        """Override save to ensure validation."""
        self.clean()
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("gift_manager:person_edit", kwargs={"pk": self.pk})

    def clean(self):
        """Ensure that at least person or group is set."""
        if (self.person is None) == (self.group is None):
            raise ValidationError(
                gettext_lazy("Either a person or a group must be specified but not both.")
            )


class RelationPermission(models.Model):
    """Model for permissions on a relation."""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    relation = models.ForeignKey(Relation, on_delete=models.CASCADE)
    permission_type = models.IntegerField(
        choices=PermissionLevel.CHOICES, default=PermissionLevel.VIEWER
    )

    class Meta:
        unique_together = ("user", "relation")

    def __str__(self):
        return f"{self.user} - {self.relation} -> {PermissionLevel.get_label(self.permission_type)}"

    @classproperty
    def filter_name(self):
        return "relation"


# Signal handlers for GiftTag cache invalidation
@receiver(post_save, sender=GiftTag)
def clear_gifttag_cache_on_save(sender, instance, **kwargs):
    """Clear hierarchy cache when a GiftTag is saved."""
    instance.clear_hierarchy_cache()


@receiver(models.signals.m2m_changed, sender=GiftTag.parent_tags.through)
def clear_gifttag_cache_on_parent_change(sender, instance, action, **kwargs):
    """Clear hierarchy cache when parent_tags relationship changes."""
    if action in ['post_add', 'post_remove', 'post_clear']:
        instance.clear_hierarchy_cache()
