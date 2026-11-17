"""Secret Santa models: an exchange, its participants and its exclusion sets.

An exchange belongs to its organizer only and never goes through ``PermissionService``.
Participants are not persons of the address book: a participant is a name, an optional email
address and a secret token that opens their personal page.
"""

from __future__ import annotations

import secrets
import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy

from gift_manager.email_encoding import decode_email
from gift_manager.email_encoding import encode_email
from gift_manager.validators import validate_http_url

__all__ = [
    "MAX_EXCHANGE_WISHES",
    "MAX_NOTE_LENGTH",
    "MAX_PARTICIPANTS",
    "Exchange",
    "ExchangeParticipant",
    "ExchangeWish",
    "ExclusionSet",
]

MAX_PARTICIPANTS = 100
# Limits of what a participant may write from their personal page, which needs no login
MAX_EXCHANGE_WISHES = 30
MAX_NOTE_LENGTH = 2000


def new_participant_token() -> str:
    """Return a new secret for a personal link."""
    return secrets.token_urlsafe(32)


class Exchange(models.Model):
    """A Secret Santa exchange organized by one user."""

    class Status(models.TextChoices):
        DRAFT = "draft", gettext_lazy("Draft")
        DRAWN = "drawn", gettext_lazy("Drawn")
        CLOSED = "closed", gettext_lazy("Closed")

    exchange_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    organizer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="organized_exchanges",
    )
    name = models.CharField(gettext_lazy("Name"), max_length=120)
    exchange_date = models.DateField(gettext_lazy("Exchange date"))
    budget = models.DecimalField(
        gettext_lazy("Budget"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    # Copied from the organizer's profile at creation, so the budget keeps its meaning
    currency = models.CharField(max_length=3)
    guidelines = models.TextField(gettext_lazy("Guidelines"), blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    no_mutual_draw = models.BooleanField(
        gettext_lazy("Nobody draws the person who drew them"), default=False
    )
    drawn_at = models.DateTimeField(null=True, blank=True)
    # The exchange this one was started from: its pairings may be avoided
    previous_exchange = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    no_repeat_draw = models.BooleanField(
        gettext_lazy("Nobody draws the same person as in the previous exchange"), default=False
    )
    # Chosen at closing: every participant then sees who gave to whom
    pairings_revealed = models.BooleanField(default=False)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = gettext_lazy("Secret Santa exchange")
        verbose_name_plural = gettext_lazy("Secret Santa exchanges")

    def __str__(self) -> str:
        return str(self.name)

    @property
    def is_draft(self) -> bool:
        return self.status == self.Status.DRAFT

    @property
    def is_drawn(self) -> bool:
        return self.status == self.Status.DRAWN

    @property
    def is_closed(self) -> bool:
        return self.status == self.Status.CLOSED


class ExchangeParticipant(models.Model):
    """A participant of an exchange, reached through their personal secret link."""

    participant_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    exchange = models.ForeignKey(Exchange, on_delete=models.CASCADE, related_name="participants")
    name = models.CharField(gettext_lazy("Name"), max_length=120)
    # Email is stored encoded for privacy - use the email property for decoded access
    email_address = models.TextField(null=True, blank=True)
    token = models.CharField(max_length=64, unique=True, editable=False)
    source_person = models.ForeignKey(
        "gift_manager.Person",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    linked_account = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="exchange_participations",
    )
    # Secret: organizer pages never load it unless the organizer asked to see the pairings
    gives_to = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="drawn_by",
    )
    # The same person in the exchange this one was copied from
    previous_participant = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    emails_stopped = models.BooleanField(default=False)
    last_emailed_at = models.DateTimeField(null=True, blank=True)
    # Said from their personal page, before the draw, that they cannot take part
    declined = models.BooleanField(default=False)
    # When the personal link was first sent before the draw
    invited_at = models.DateTimeField(null=True, blank=True)
    # The participant linked their account themselves (not through an import)
    account_attached_by_participant = models.BooleanField(default=False)
    note_for_santa = models.TextField(blank=True, max_length=MAX_NOTE_LENGTH)
    # The linked account confirmed which real wishes its Santa may see
    wishlist_confirmed = models.BooleanField(default=False)
    shared_wishes = models.ManyToManyField("gift_manager.Wish", blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = gettext_lazy("Secret Santa participant")
        verbose_name_plural = gettext_lazy("Secret Santa participants")
        constraints = [
            models.UniqueConstraint("exchange", Lower("name"), name="ss_participant_unique_name"),
            models.UniqueConstraint(
                fields=["exchange", "source_person"],
                condition=Q(source_person__isnull=False),
                name="ss_participant_unique_source",
            ),
            models.UniqueConstraint(
                fields=["exchange", "linked_account"],
                condition=Q(linked_account__isnull=False),
                name="ss_participant_unique_account",
            ),
        ]

    def __str__(self) -> str:
        return str(self.name)

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = new_participant_token()
        super().save(*args, **kwargs)

    @property
    def email(self) -> str | None:
        """Get the decoded email address."""
        return decode_email(self.email_address)

    def set_email(self, value: str | None) -> None:
        """Set the email address, encoding it for storage."""
        self.email_address = encode_email(value or None)

    def regenerate_token(self) -> str:
        """Create a new secret; the previous personal link stops working."""
        self.token = new_participant_token()
        self.save(update_fields=["token"])
        return self.token


class ExchangeWish(models.Model):
    """A wish written for one exchange only, shown to the participant's Santa."""

    wish_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    participant = models.ForeignKey(
        ExchangeParticipant, on_delete=models.CASCADE, related_name="exchange_wishes"
    )
    title = models.CharField(gettext_lazy("Title"), max_length=200)
    url = models.URLField(
        gettext_lazy("Link"), max_length=2000, blank=True, validators=[validate_http_url]
    )
    price = models.DecimalField(
        gettext_lazy("Price"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name = gettext_lazy("Exchange wish")
        verbose_name_plural = gettext_lazy("Exchange wishes")

    def __str__(self) -> str:
        return str(self.title)


class ExclusionSet(models.Model):
    """A named set of participants who must not draw each other (a couple, a household)."""

    set_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    exchange = models.ForeignKey(Exchange, on_delete=models.CASCADE, related_name="exclusion_sets")
    name = models.CharField(gettext_lazy("Name"), max_length=120)
    participants = models.ManyToManyField(ExchangeParticipant, related_name="exclusion_sets")

    class Meta:
        ordering = ["name", "pk"]
        verbose_name = gettext_lazy("Exclusion set")
        verbose_name_plural = gettext_lazy("Exclusion sets")

    def __str__(self) -> str:
        return str(self.name)
