#!/usr/bin/env python
"""Benchmark and compare AI model and effort combinations for gift suggestions.

This script runs side-by-side evaluations across different model IDs and reasoning
effort levels for the GiftManager AI gift suggestion feature.

Features:
- Tests multiple models and effort levels against a real recipient profile in your database.
- Supports steering filters: occasion, budget, and free-form user hints.
- Flexible database targeting: query any PostgreSQL database, SQLite file, or database URL.
- Dry-run by default: tests prompt, schema adherence, and candidate scoring without
  polluting the database or consuming daily user generation quotas.
- Displays latency, suggestion quality, rationale, tag matching, and avoid-list checks.
- Formats results as rich terminal tables, Markdown, or JSON.

Usage examples:
  # Fast benchmark using defaults (Anthropic haiku & sonnet with low & medium effort)
  python scripts/benchmark_suggestion_models.py

  # Test against a specific recipient by full name, ID, or family name filter
  python scripts/benchmark_suggestion_models.py --recipient "Mailys Dupont"
  python scripts/benchmark_suggestion_models.py --recipient Mailys --family-name Dupont
  python scripts/benchmark_suggestion_models.py --recipient-id 42

  # List available recipients in your database to find IDs and exact names
  python scripts/benchmark_suggestion_models.py --list-recipients
  python scripts/benchmark_suggestion_models.py --list-recipients Mailys

  # Test against a specific database name or port
  python scripts/benchmark_suggestion_models.py --db-name gift_manager_test --db-port 5433

  # Test against a SQLite database file
  python scripts/benchmark_suggestion_models.py --db-sqlite /path/to/test.sqlite3

  # Test specific models and effort levels
  python scripts/benchmark_suggestion_models.py -m claude-haiku-5-5 claude-sonnet-4-6 -e low medium

  # Test with steering parameters
  python scripts/benchmark_suggestion_models.py --occasion "Birthday" --budget "moderate"

  # Dry-run test pipeline with mock AI (no API key needed)
  python scripts/benchmark_suggestion_models.py --mock
"""

from __future__ import annotations

import argparse
import contextlib
import getpass
import json
import logging
import os
import socket
import sys
import time
import urllib.parse
import uuid
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Configure Django environment
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Load root .env file
load_dotenv(BASE_DIR / ".env")

os.environ.setdefault("DJANGO_ENV", "development")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "GiftManager.settings")

# Fallback DB_PORT to 5433 (Docker Compose mapping) if running on host and DB_PORT isn't set
if "DB_PORT" not in os.environ:
    test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    test_sock.settimeout(0.3)
    if test_sock.connect_ex(("127.0.0.1", 5433)) == 0:
        os.environ["DB_PORT"] = "5433"
    test_sock.close()

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.db import connections  # noqa: E402
from django.db.models import CharField  # noqa: E402
from django.db.models import Count  # noqa: E402
from django.db.models import Q  # noqa: E402
from django.db.models import Value  # noqa: E402
from django.db.models.functions import Concat  # noqa: E402
from django.utils import translation  # noqa: E402

from gift_manager.models import Person  # noqa: E402
from gift_manager.models import PersonGroup  # noqa: E402
from gift_manager.suggestions.ai.anthropic_client import AnthropicClient  # noqa: E402
from gift_manager.suggestions.ai.client import AIClient  # noqa: E402
from gift_manager.suggestions.ai.client import AIError  # noqa: E402
from gift_manager.suggestions.ai.openai_client import OpenAIClient  # noqa: E402
from gift_manager.suggestions.ai.strategy import AIStrategy  # noqa: E402
from gift_manager.suggestions.names import normalize_gift_name  # noqa: E402
from gift_manager.suggestions.service import GiftSuggestionService  # noqa: E402

logger = logging.getLogger("suggestion_benchmark")
logger.propagate = False
_log_handler = logging.StreamHandler(sys.stdout)
_log_handler.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(_log_handler)
logger.setLevel(logging.INFO)

# Suppress verbose HTTP network debugging from SDK clients
for _noisy in (
    "anthropic",
    "openai",
    "httpx",
    "httpcore",
    "httpx2",
    "httpcore2",
    "_trace",
    "_base_client",
    "_client",
):
    logging.getLogger(_noisy).setLevel(logging.WARNING)


@dataclass
class BenchmarkIdea:
    name: str
    description: str
    reason: str
    tag_ids: list[int]
    is_avoided: bool


@dataclass
class BenchmarkRunResult:
    model: str
    effort: str
    duration_s: float
    success: bool
    error: str | None
    ideas: list[BenchmarkIdea]
    payload_size_chars: int


class MockBenchmarkClient:
    """Mock client for verifying benchmark pipeline without making network API calls."""

    def __init__(self, model: str, effort: str = "") -> None:
        self.model = model
        self.effort = effort

    def generate(self, *, system: str, payload: dict, schema: dict) -> str:
        _ = (system, schema)
        time.sleep(0.4 if "haiku" in self.model or "mini" in self.model else 0.8)
        interests = payload.get("interests", ["General"])
        occasion = payload.get("occasion", "any occasion")
        first_interest = interests[0] if interests else "Special"

        mock_response = {
            "ideas": [
                {
                    "name": f"{first_interest} Curated Gift Set",
                    "description": (
                        f"A personalized gift set tailored for {occasion} focusing "
                        f"on {first_interest.lower()}."
                    ),
                    "reason": f"Matches recipient interest in {first_interest}.",
                    "tags": interests[:2],
                },
                {
                    "name": f"Handcrafted {first_interest} Accessory",
                    "description": (
                        f"An artisanal item designed for everyday enjoyment during {occasion}."
                    ),
                    "reason": "Complements previous positive gift reactions.",
                    "tags": interests[:1],
                },
                {
                    "name": f"Premium {occasion} Experience Ticket",
                    "description": (
                        f"An immersive experience voucher celebrating {occasion} with loved ones."
                    ),
                    "reason": "Provides a memorable non-physical experience within budget.",
                    "tags": [],
                },
            ]
        }
        return json.dumps(mock_response)


def _apply_url_db_config(db_url: str) -> str:
    parsed = urllib.parse.urlparse(db_url)
    db_cfg = settings.DATABASES["default"]
    if parsed.scheme.startswith("sqlite"):
        db_path = parsed.path.lstrip("/") or ":memory:"
        db_cfg.update(
            {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": db_path,
                "USER": "",
                "PASSWORD": "",
                "HOST": "",
                "PORT": "",
                "OPTIONS": {},
            }
        )
        connections.databases["default"].update(db_cfg)
        return f"SQLite ({db_path})"

    # Parse query parameters (e.g. sslmode, options) into OPTIONS
    options: dict[str, Any] = {}
    query_params = urllib.parse.parse_qs(parsed.query)
    for key, values in query_params.items():
        if values:
            options[key] = values[0]

    hostname = parsed.hostname or "localhost"
    # Neon and other managed serverless cloud databases require SSL
    if "neon.tech" in hostname and "sslmode" not in options:
        options["sslmode"] = "require"

    username = urllib.parse.unquote(parsed.username or "")
    password = urllib.parse.unquote(parsed.password or "")
    db_name = parsed.path.lstrip("/")

    db_cfg.update(
        {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": db_name,
            "USER": username,
            "PASSWORD": password,
            "HOST": hostname,
            "PORT": str(parsed.port or 5432),
            "OPTIONS": options,
        }
    )

    if "neon.tech" in hostname or "pooler" in hostname:
        db_cfg["DISABLE_SERVER_SIDE_CURSORS"] = True

    connections.databases["default"].update(db_cfg)
    port = parsed.port or 5432
    return f"PostgreSQL '{db_name}' on {hostname}:{port}"


def _apply_field_db_config(args: argparse.Namespace) -> str:
    db_cfg = settings.DATABASES["default"]
    if getattr(args, "db_name", None):
        db_cfg["NAME"] = args.db_name
    if getattr(args, "db_host", None):
        db_cfg["HOST"] = args.db_host
    if getattr(args, "db_port", None):
        db_cfg["PORT"] = str(args.db_port)
    if getattr(args, "db_user", None):
        db_cfg["USER"] = args.db_user
    if getattr(args, "prompt_db_password", False) or getattr(args, "db_password", None) == "-":
        db_cfg["PASSWORD"] = getpass.getpass("Enter database password: ")
    elif getattr(args, "db_password", None):
        db_cfg["PASSWORD"] = args.db_password

    host = db_cfg.get("HOST", "localhost")
    sslmode = getattr(args, "db_sslmode", None) or os.environ.get("DB_SSLMODE")
    if sslmode:
        db_cfg.setdefault("OPTIONS", {})["sslmode"] = sslmode
    elif "neon.tech" in host:
        db_cfg.setdefault("OPTIONS", {})["sslmode"] = "require"

    if "neon.tech" in host or "pooler" in host:
        db_cfg["DISABLE_SERVER_SIDE_CURSORS"] = True

    del connections["default"]
    try:
        connections["default"].ensure_connection()
    except Exception:
        is_local_host = host in ("localhost", "127.0.0.1", "")
        if is_local_host and not getattr(args, "db_port", None) and db_cfg.get("PORT") != "5433":
            db_cfg["PORT"] = "5433"
            db_cfg["HOST"] = "127.0.0.1"
            del connections["default"]
            connections["default"].ensure_connection()
        else:
            raise

    engine_name = "PostgreSQL" if "postgresql" in db_cfg.get("ENGINE", "") else "Database"
    port = db_cfg.get("PORT", "5432")
    return f"{engine_name} '{db_cfg.get('NAME')}' on {host}:{port}"


def configure_database(args: argparse.Namespace) -> str:
    """Configure and establish the database connection based on arguments or environment."""
    if getattr(args, "env_file", None):
        env_path = Path(args.env_file).resolve()
        if not env_path.is_file():
            err_msg = f"Specified env file not found: {env_path}"
            raise FileNotFoundError(err_msg)
        load_dotenv(env_path, override=True)

    if getattr(args, "db_sqlite", None):
        sqlite_path = Path(args.db_sqlite).resolve()
        db_cfg = settings.DATABASES["default"]
        db_cfg.update(
            {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": str(sqlite_path),
                "USER": "",
                "PASSWORD": "",
                "HOST": "",
                "PORT": "",
                "OPTIONS": {},
            }
        )
        connections.databases["default"].update(db_cfg)
        del connections["default"]
        connections["default"].ensure_connection()
        return f"SQLite ({sqlite_path})"

    if getattr(args, "db_url", None):
        desc = _apply_url_db_config(args.db_url)
        del connections["default"]
        connections["default"].ensure_connection()
        return desc

    return _apply_field_db_config(args)


def list_database_recipients(
    query: str | None = None,
    user: object | None = None,
) -> None:
    """Print a list of matching recipients in the connected database and exit."""
    qs = (
        Person.objects.annotate(
            full_name=Concat("first_name", Value(" "), "family_name", output_field=CharField()),
            interests_count=Count("interests", distinct=True),
        )
        .select_related("user_link")
        .order_by("first_name", "family_name")
    )

    if user:
        qs = qs.filter(user_link=user)

    if query:
        q = query.strip()
        tokens = q.split()
        if len(tokens) >= 2:
            t1, t2 = tokens[0], " ".join(tokens[1:])
            name_filter = (Q(first_name__icontains=t1) & Q(family_name__icontains=t2)) | (
                Q(first_name__icontains=t2) & Q(family_name__icontains=t1)
            )
        else:
            name_filter = Q(first_name__icontains=q) | Q(family_name__icontains=q)

        qs = qs.filter(name_filter | Q(full_name__icontains=q) | Q(email_address__icontains=q))

    people = list(qs[:50])
    total_count = qs.count()

    if not people:
        filter_msg = f" matching '{query}'" if query else ""
        logger.info("\nNo recipients found in database%s.\n", filter_msg)
        return

    filter_msg = f" matching '{query}'" if query else ""
    logger.info("\nRecipients in database%s (%d total):", filter_msg, total_count)
    hdr_sep = "─" * 100
    logger.info(hdr_sep)
    logger.info(
        "%-6s %-20s %-20s %-28s %-10s %s",
        "ID",
        "First Name",
        "Family Name",
        "Email",
        "Owner",
        "Interests",
    )
    logger.info(hdr_sep)
    for p in people:
        first = (p.first_name or "")[:20]
        family = (p.family_name or "")[:20]
        email = (p.email_address or "-")[:28]
        owner = (p.user_link.username if p.user_link else "-")[:10]
        cnt = getattr(p, "interests_count", 0)
        logger.info(
            "%-6s %-20s %-20s %-28s %-10s %s",
            str(p.pk),
            first,
            family,
            email,
            owner,
            f"{cnt} tag(s)",
        )
    logger.info(hdr_sep)
    if total_count > len(people):
        logger.info(
            "(Showing first %d of %d recipients. "
            "Filter with --list-recipients <QUERY> for specific names.)",
            len(people),
            total_count,
        )
    sample = people[0]
    logger.info("\nTo run a benchmark for one of these recipients, pass:")
    logger.info("  --recipient-id %s", sample.pk)
    if sample.family_name:
        logger.info('  --recipient "%s %s"\n', sample.first_name, sample.family_name)
    else:
        logger.info('  --recipient "%s"\n', sample.first_name)


def list_database_groups(query: str | None = None) -> None:
    """Print a list of matching recipient groups in the connected database and exit."""
    qs = PersonGroup.objects.annotate(members_count=Count("persons", distinct=True)).order_by(
        "name"
    )
    if query:
        qs = qs.filter(name__icontains=query.strip())
    groups = list(qs[:50])
    total_count = qs.count()

    if not groups:
        filter_msg = f" matching '{query}'" if query else ""
        logger.info("\nNo groups found in database%s.\n", filter_msg)
        return

    filter_msg = f" matching '{query}'" if query else ""
    logger.info("\nRecipient Groups in database%s (%d total):", filter_msg, total_count)
    hdr_sep = "─" * 60
    logger.info(hdr_sep)
    logger.info("%-6s %-38s %s", "ID", "Group Name", "Members")
    logger.info(hdr_sep)
    for g in groups:
        name = (g.name or "")[:38]
        cnt = getattr(g, "members_count", 0)
        logger.info("%-6s %-38s %s", str(g.pk), name, f"{cnt} member(s)")
    logger.info(hdr_sep)
    if total_count > len(groups):
        logger.info(
            "(Showing first %d of %d groups. "
            "Filter with --list-groups <QUERY> for specific names.)",
            len(groups),
            total_count,
        )
    sample = groups[0]
    logger.info("\nTo run a benchmark for one of these groups, pass:")
    logger.info("  --group-id %s", sample.pk)
    logger.info('  --group "%s"\n', sample.name)


def _resolve_group(
    group_identifier: str | None,
    group_id: str | None,
) -> PersonGroup:
    """Resolve a PersonGroup by ID or name."""
    if group_id:
        if group_id.isdigit():
            group = PersonGroup.objects.filter(pk=int(group_id)).first()
        else:
            with contextlib.suppress(ValueError):
                group = PersonGroup.objects.filter(group_id=uuid.UUID(group_id)).first()
        if not group:
            err = f"Recipient group with ID '{group_id}' not found in database."
            raise ValueError(err)
        return group

    if group_identifier:
        if group_identifier.isdigit():
            group = PersonGroup.objects.filter(pk=int(group_identifier)).first()
        else:
            group = PersonGroup.objects.filter(name__icontains=group_identifier.strip()).first()
        if not group:
            err = f"Recipient group '{group_identifier}' not found in database."
            raise ValueError(err)
        return group

    err = "No group identifier provided."
    raise ValueError(err)


def _resolve_person_by_id(recipient_id: str) -> Person:
    """Resolve a Person by integer PK or UUID string."""
    target: Person | None = None
    if recipient_id.isdigit():
        target = Person.objects.filter(pk=int(recipient_id)).first()
    else:
        with contextlib.suppress(ValueError):
            target = Person.objects.filter(person_id=uuid.UUID(recipient_id)).first()
    if not target:
        err = f"Recipient with ID '{recipient_id}' not found in database."
        raise ValueError(err)
    return target


def _find_name_candidates(raw_query: str, family_name: str | None) -> list[Person]:
    """Find matching Person candidates by name, tokens, or email."""
    qs = Person.objects.annotate(
        full_name=Concat("first_name", Value(" "), "family_name", output_field=CharField()),
        rev_name=Concat("family_name", Value(" "), "first_name", output_field=CharField()),
    ).select_related("user_link")

    if family_name:
        return list(
            qs.filter(
                first_name__icontains=raw_query,
                family_name__icontains=family_name.strip(),
            )
        )

    exact_candidates = list(
        qs.filter(
            Q(full_name__iexact=raw_query)
            | Q(rev_name__iexact=raw_query)
            | Q(first_name__iexact=raw_query)
            | Q(family_name__iexact=raw_query)
            | Q(email_address__iexact=raw_query)
        )
    )
    if exact_candidates:
        return exact_candidates

    tokens = raw_query.split()
    if len(tokens) >= 2:
        t1, t2 = tokens[0], " ".join(tokens[1:])
        split_matches = list(
            qs.filter(
                (Q(first_name__icontains=t1) & Q(family_name__icontains=t2))
                | (Q(first_name__icontains=t2) & Q(family_name__icontains=t1))
            )
        )
        if split_matches:
            return split_matches

    return list(
        qs.filter(
            Q(full_name__icontains=raw_query)
            | Q(first_name__icontains=raw_query)
            | Q(family_name__icontains=raw_query)
            | Q(email_address__icontains=raw_query)
        )
    )


def _disambiguation_error(
    raw_query: str,
    candidates: list[Person],
    family_name: str | None,
) -> ValueError:
    """Format a clear error listing ambiguous candidates and recommended flags."""
    lines = [f"Multiple recipients ({len(candidates)}) match '{raw_query}':"]
    for c in candidates[:10]:
        owner_str = f", owner: {c.user_link.username}" if c.user_link else ""
        email_str = f", email: {c.email_address}" if c.email_address else ""
        lines.append(f"  • [ID {c.pk}] {c.first_name} {c.family_name}{email_str}{owner_str}")
    if len(candidates) > 10:
        lines.append(f"  ... and {len(candidates) - 10} more.")
    lines.append("\nPlease disambiguate by passing the exact full name or ID:")
    lines.append(f"  --recipient-id {candidates[0].pk}")
    if candidates[0].family_name:
        lines.append(f'  --recipient "{candidates[0].first_name} {candidates[0].family_name}"')
        if not family_name:
            lines.append(f'  --recipient "{raw_query}" --family-name "{candidates[0].family_name}"')
    return ValueError("\n".join(lines))


def _try_resolve_direct_id(raw_query: str) -> Person | None:
    """Attempt resolving Person if raw_query is a numeric ID or UUID."""
    if raw_query.isdigit():
        return _resolve_person_by_id(raw_query)
    if len(raw_query) in (32, 36):
        with contextlib.suppress(ValueError):
            return _resolve_person_by_id(raw_query)
    return None


def resolve_recipient(
    recipient_identifier: str | None = None,
    recipient_id: str | None = None,
    family_name: str | None = None,
    group_identifier: str | None = None,
    group_id: str | None = None,
    user: object | None = None,
) -> Person | PersonGroup:
    """Resolve recipient person or group with intelligent matching and disambiguation."""
    if group_id or group_identifier:
        return _resolve_group(group_identifier, group_id)

    if recipient_id:
        return _resolve_person_by_id(recipient_id)

    raw_query = (recipient_identifier or "").strip()
    if not raw_query and not family_name:
        base_qs = Person.objects.filter(user_link=user) if user else Person.objects.all()
        target = (
            base_qs.filter(interests__isnull=False).distinct().first()
            or base_qs.first()
            or Person.objects.first()
        )
        if not target:
            err = "No recipients found in database."
            raise ValueError(err)
        return target

    if not family_name:
        direct = _try_resolve_direct_id(raw_query)
        if direct:
            return direct

    candidates = _find_name_candidates(raw_query, family_name)
    if not candidates:
        err = (
            f"No recipient found matching '{raw_query}'. "
            "Run with '--list-recipients' to view available recipients in the database."
        )
        raise ValueError(err)

    if len(candidates) == 1:
        return candidates[0]

    if user:
        user_matches = [c for c in candidates if c.user_link_id == getattr(user, "pk", None)]
        if len(user_matches) == 1:
            return user_matches[0]

    raise _disambiguation_error(raw_query, candidates, family_name)


def resolve_subject(
    user_identifier: str | None,
    recipient_identifier: str | None,
    recipient_id: str | None = None,
    family_name: str | None = None,
    group_identifier: str | None = None,
    group_id: str | None = None,
) -> tuple[object, Person | PersonGroup]:
    """Find appropriate user and recipient in database."""
    user_model = get_user_model()
    user = None
    if user_identifier:
        if user_identifier.isdigit():
            user = user_model.objects.filter(pk=int(user_identifier)).first()
        else:
            user = user_model.objects.filter(username__iexact=user_identifier).first()
        if not user:
            err = f"User '{user_identifier}' not found in database."
            raise ValueError(err)

    recipient = resolve_recipient(
        recipient_identifier=recipient_identifier,
        recipient_id=recipient_id,
        family_name=family_name,
        group_identifier=group_identifier,
        group_id=group_id,
        user=user,
    )

    if user is None:
        if isinstance(recipient, Person) and recipient.user_link:
            user = recipient.user_link
        else:
            user = user_model.objects.filter(is_active=True).first()
            if not user:
                err = "No active user found in database."
                raise ValueError(err)

    return user, recipient


def instantiate_client(
    provider: str,
    model: str,
    effort: str,
    api_key: str,
    base_url: str | None,
    timeout: float,
    *,
    max_tokens: int | None = None,
    mock: bool = False,
) -> AIClient:
    """Build the AI client for the benchmark turn."""
    if mock:
        return MockBenchmarkClient(model=model, effort=effort)

    if provider == "anthropic":
        if not api_key:
            err = "Missing Anthropic API key. Set GIFT_SUGGESTIONS_AI_API_KEY or pass --api-key."
            raise ValueError(err)
        effective_max_tokens = max_tokens
        if effective_max_tokens is None:
            effective_max_tokens = 8192 if effort in ("high", "max", "xhigh") else 4096

        effective_timeout = timeout
        if effective_timeout <= 30.0:
            if effort in ("max", "xhigh"):
                effective_timeout = 120.0
            elif effort == "high":
                effective_timeout = 60.0

        return AnthropicClient(
            api_key=api_key,
            model=model,
            timeout=effective_timeout,
            effort=effort,
            max_tokens=effective_max_tokens,
        )

    if provider == "openai":
        if not api_key and not base_url:
            err = "Missing OpenAI API key. Set GIFT_SUGGESTIONS_AI_API_KEY or pass --api-key."
            raise ValueError(err)
        return OpenAIClient(
            api_key=api_key or "unused",
            model=model,
            base_url=base_url or None,
            timeout=timeout,
        )

    err = f"Unsupported provider: {provider}"
    raise ValueError(err)


def run_single_evaluation(
    service: GiftSuggestionService,
    client: AIClient,
    model: str,
    effort: str,
    count: int,
    occasion: str,
    budget: str,
    hint: str,
    *,
    save: bool = False,
) -> BenchmarkRunResult:
    """Run one benchmark test against the suggestions service or strategy."""
    ctx = service._ai_context(occasion=occasion, budget=budget, hint=hint)  # noqa: SLF001
    payload_size = len(json.dumps(ctx.history.items[:50], default=str))

    start_time = time.monotonic()
    try:
        if save:
            service.ai_client = client
            block = service.request_more_ideas(
                count=count, occasion=occasion, budget=budget, hint=hint
            )
            candidate_items = [
                (c.name, c.description, c.reason, list(c.tag_ids)) for c in block.ideas
            ]
        else:
            strategy = AIStrategy(client)
            candidates = strategy.suggest(ctx, limit=count)
            candidate_items = [
                (c.name, c.description, str(c.reason_text or c.reason), list(c.tag_ids))
                for c in candidates
            ]

        duration_s = time.monotonic() - start_time
        blocked_names = set(ctx.blocked_names)
        ideas = []
        for name, desc, reason, tag_ids in candidate_items:
            norm = normalize_gift_name(name)
            is_avoided = norm in blocked_names
            ideas.append(
                BenchmarkIdea(
                    name=name,
                    description=desc,
                    reason=reason,
                    tag_ids=tag_ids,
                    is_avoided=is_avoided,
                )
            )

        return BenchmarkRunResult(
            model=model,
            effort=effort,
            duration_s=duration_s,
            success=True,
            error=None,
            ideas=ideas,
            payload_size_chars=payload_size,
        )

    except (AIError, Exception) as exc:
        duration_s = time.monotonic() - start_time
        return BenchmarkRunResult(
            model=model,
            effort=effort,
            duration_s=duration_s,
            success=False,
            error=str(exc),
            ideas=[],
            payload_size_chars=payload_size,
        )


def print_pretty_report(
    user: object,
    recipient: Person | PersonGroup,
    occasion: str,
    budget: str,
    hint: str,
    results: list[BenchmarkRunResult],
    db_desc: str = "",
    lang: str = "fr",
) -> None:
    """Print colored terminal report of benchmark results."""
    interests: list[str] = []
    if hasattr(recipient, "interests"):
        rel = recipient.interests
        if hasattr(rel, "all"):
            interests = [t.name for t in rel.all()]

    separator = "=" * 78
    username = getattr(user, "username", str(user))
    user_pk = getattr(user, "pk", "")

    logger.info("\n%s", separator)
    logger.info(" 🎁 GIFT MANAGER — AI SUGGESTION BENCHMARK")
    logger.info("%s", separator)
    if db_desc:
        logger.info(" Database:   %s", db_desc)
    logger.info(" User:       %s (ID: %s)", username, user_pk)
    if isinstance(recipient, PersonGroup):
        logger.info(" Recipient:  [Group] %s (ID: %s)", recipient.name, recipient.pk)
    else:
        logger.info(" Recipient:  %s (ID: %s)", recipient, recipient.pk)
    if interests:
        logger.info(" Interests:  %s", ", ".join(interests))
    logger.info(
        " Occasion:   %s | Budget: %s | Lang: %s | Hint: %s",
        occasion or "(None)",
        budget or "(Default)",
        lang,
        hint or "(None)",
    )
    logger.info("-" * 78)

    for res in results:
        effort_str = f" [effort: {res.effort}]" if res.effort else ""
        logger.info("\n▶ Model: %s%s", res.model, effort_str)
        logger.info("  Latency:    %.2fs", res.duration_s)

        if not res.success:
            logger.info("  ❌ FAILED:  %s", res.error)
            continue

        logger.info("  Ideas generated: %d", len(res.ideas))
        for idx, idea in enumerate(res.ideas, 1):
            avoid_flag = " ⚠️ [AVOID LIST VIOLATION]" if idea.is_avoided else ""
            logger.info("    %d. \033[1m%s\033[0m%s", idx, idea.name, avoid_flag)
            logger.info("       Description: %s", idea.description)
            logger.info("       Reason:      %s", idea.reason)

    logger.info("\n%s", separator)
    logger.info(" 📊 SUMMARY COMPARISON TABLE")
    logger.info("%s", separator)
    logger.info(" %-25s | %-8s | %-9s | %-6s | %s", "Model", "Effort", "Latency", "Ideas", "Status")
    logger.info("-" * 78)
    for res in results:
        status = "✅ OK" if res.success else "❌ ERR"
        effort_col = res.effort or "-"
        logger.info(
            " %-25s | %-8s | %6.2fs  | %-6d | %s",
            res.model,
            effort_col,
            res.duration_s,
            len(res.ideas),
            status,
        )
    logger.info("%s\n", separator)


def print_markdown_report(results: list[BenchmarkRunResult]) -> None:
    """Print Markdown formatted table."""
    logger.info("\n### AI Suggestion Benchmark Results\n")
    logger.info("| Model | Effort | Latency | Ideas Count | Status |")
    logger.info("| :--- | :--- | :--- | :--- | :--- |")
    for res in results:
        status = "✅ OK" if res.success else f"❌ Error: {res.error}"
        effort_val = res.effort or "-"
        logger.info(
            "| `%s` | %s | %.2fs | %d | %s |",
            res.model,
            effort_val,
            res.duration_s,
            len(res.ideas),
            status,
        )
    logger.info("")


def _build_argument_parser() -> argparse.ArgumentParser:
    desc = "Benchmark and evaluate AI models and effort combinations for gift suggestions."
    parser = argparse.ArgumentParser(
        description=desc,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-p",
        "--provider",
        choices=["anthropic", "openai"],
        default=getattr(settings, "GIFT_SUGGESTIONS_AI_PROVIDER", "") or "anthropic",
        help="AI provider adapter to evaluate.",
    )
    parser.add_argument(
        "-m",
        "--models",
        nargs="+",
        help="Model IDs to test. Defaults to standard provider models.",
    )
    parser.add_argument(
        "-e",
        "--efforts",
        nargs="+",
        help="Effort levels to test (e.g., low medium high). Relevant for Anthropic.",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="API key for provider. If omitted, uses environment/settings.",
    )
    parser.add_argument(
        "--base-url",
        default=getattr(settings, "GIFT_SUGGESTIONS_AI_BASE_URL", "") or "",
        help="Base URL for OpenAI-compatible endpoints.",
    )
    parser.add_argument(
        "--user",
        help="Username or user ID to test with (defaults to recipient owner or first active user).",
    )
    parser.add_argument(
        "--recipient",
        help=(
            'Recipient name, email, or ID (e.g. "Mailys Dupont", "Mailys", or 42). '
            "Defaults to person with most interests/history."
        ),
    )
    parser.add_argument(
        "--recipient-id",
        help="Exact recipient database ID (integer or UUID) to target directly.",
    )
    parser.add_argument(
        "--family-name",
        help=(
            "Family name to filter or disambiguate identical first names "
            '(e.g. --recipient "Mailys" --family-name "Dupont").'
        ),
    )
    parser.add_argument(
        "--group",
        help="Target a recipient PersonGroup by name or ID instead of an individual Person.",
    )
    parser.add_argument(
        "--group-id",
        help="Target a recipient PersonGroup by exact database ID.",
    )
    parser.add_argument(
        "--list-recipients",
        nargs="?",
        const="",
        default=None,
        metavar="QUERY",
        help=(
            "List matching recipients in database and exit "
            "(e.g. --list-recipients or --list-recipients Mailys)."
        ),
    )
    parser.add_argument(
        "--list-groups",
        nargs="?",
        const="",
        default=None,
        metavar="QUERY",
        help="List matching recipient groups in database and exit.",
    )
    parser.add_argument(
        "-c",
        "--count",
        type=int,
        default=3,
        help="Number of suggestions requested per run (1 to 5).",
    )
    parser.add_argument(
        "--occasion",
        default="Birthday",
        help="Steering parameter: occasion filter.",
    )
    parser.add_argument(
        "--lang",
        "--language",
        dest="lang",
        default="fr",
        choices=["fr", "en"],
        help="Language for generated suggestions (default: fr).",
    )
    parser.add_argument(
        "--budget",
        default="moderate",
        help="Steering parameter: budget tier (e.g. modest, moderate, luxury).",
    )
    parser.add_argument(
        "--hint",
        default="",
        help="Steering parameter: free-form user hint.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Request timeout in seconds (default: 60.0, auto-scales to 120s for max effort).",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Maximum completion tokens (default: 4096, auto-scales to 8192 for high/max effort).",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Persist generated ideas into database (default: False / dry-run).",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock AI client (fast offline dry-run test without API keys).",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Output summary as Markdown table.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw results as JSON.",
    )

    db_group = parser.add_argument_group("Database options")
    db_group.add_argument(
        "--db-name",
        help="Target database name to query (overrides DB_NAME).",
    )
    db_group.add_argument(
        "--db-host",
        help="Target database host (overrides DB_HOST, e.g. localhost, 127.0.0.1).",
    )
    db_group.add_argument(
        "--db-port",
        help="Target database port (overrides DB_PORT, e.g. 5432, 5433).",
    )
    db_group.add_argument(
        "--db-user",
        help="Target database user (overrides DB_USER).",
    )
    db_group.add_argument(
        "--db-password",
        help="Target database password (overrides DB_PASSWORD).",
    )
    db_group.add_argument(
        "--prompt-db-password",
        action="store_true",
        help="Prompt securely for the database password in terminal without echoing.",
    )
    db_group.add_argument(
        "--db-sslmode",
        choices=["disable", "allow", "prefer", "require", "verify-ca", "verify-full"],
        help="SSL mode for PostgreSQL (e.g. require for Neon/AWS).",
    )
    db_group.add_argument(
        "--db-url",
        help="Target database connection URL (e.g. postgresql://user:pass@host:5432/dbname).",
    )
    db_group.add_argument(
        "--db-sqlite",
        help="Path to an existing SQLite database file to evaluate against.",
    )
    db_group.add_argument(
        "--env-file",
        help="Path to an alternative .env file containing database & AI credentials.",
    )
    return parser


def _handle_discovery_modes(args: argparse.Namespace) -> bool:
    """Handle --list-recipients or --list-groups discovery actions."""
    if args.list_recipients is not None:
        user = None
        if args.user:
            user_model = get_user_model()
            user = (
                user_model.objects.filter(pk=int(args.user)).first()
                if args.user.isdigit()
                else user_model.objects.filter(username__iexact=args.user).first()
            )
        list_database_recipients(args.list_recipients, user=user)
        return True

    if args.list_groups is not None:
        list_database_groups(args.list_groups)
        return True

    return False


def _resolve_api_key(args: argparse.Namespace) -> str:
    """Resolve active AI provider API key from args, settings, or env."""
    if args.api_key:
        return args.api_key
    setting_key = getattr(settings, "GIFT_SUGGESTIONS_AI_API_KEY", "")
    if setting_key:
        return setting_key
    env_var = "ANTHROPIC_API_KEY" if args.provider == "anthropic" else "OPENAI_API_KEY"
    return os.environ.get(env_var, "")


ANTHROPIC_MODEL_ALIASES: dict[str, str] = {
    "haiku": "claude-haiku-5-5",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6",
    "haiku-5-5": "claude-haiku-5-5",
    "sonnet-4-6": "claude-sonnet-4-6",
    "sonnet-5-5": "claude-sonnet-5-5",
    "opus-4-6": "claude-opus-4-6",
    "opus-5-5": "claude-opus-5-5",
}

OPENAI_MODEL_ALIASES: dict[str, str] = {
    "4o": "gpt-4o",
    "4o-mini": "gpt-4o-mini",
    "gpt4o": "gpt-4o",
    "gpt4o-mini": "gpt-4o-mini",
    "o1": "o1",
    "o3-mini": "o3-mini",
}


def _resolve_model_name(model: str, provider: str) -> str:
    """Resolve common short aliases to full provider model IDs."""
    cleaned = model.strip().lower()
    if provider == "anthropic":
        return ANTHROPIC_MODEL_ALIASES.get(cleaned, model)
    if provider == "openai":
        return OPENAI_MODEL_ALIASES.get(cleaned, model)
    return model


def _resolve_models_and_efforts(
    args: argparse.Namespace,
) -> tuple[list[str], list[str]]:
    """Determine models and effort levels matrix from CLI arguments."""
    if args.provider == "anthropic":
        raw_models = args.models or ["claude-haiku-5-5", "claude-sonnet-4-6"]
        efforts = args.efforts or ["low", "medium"]
    else:
        raw_models = args.models or ["gpt-4o-mini", "gpt-4o"]
        efforts = args.efforts or [""]
    models = [_resolve_model_name(m, args.provider) for m in raw_models]
    return models, efforts


def _extract_error_detail(exc: Exception) -> str:
    """Extract descriptive error message from upstream client exception."""
    cause = getattr(exc, "__cause__", None)
    if cause:
        if "timeout" in type(cause).__name__.lower() or "timeout" in str(cause).lower():
            return f"{exc} (Request timed out. Increase timeout with --timeout <seconds>)"
        body = getattr(cause, "body", None)
        if isinstance(body, dict):
            inner = body.get("error")
            if isinstance(inner, dict) and "message" in inner:
                return f"{exc} ({inner['message']})"
            if isinstance(inner, str):
                return f"{exc} ({inner})"
        msg = getattr(cause, "message", None)
        if msg:
            return f"{exc} ({msg})"
    return str(exc)


def _run_benchmark_turn(
    service: GiftSuggestionService,
    args: argparse.Namespace,
    model: str,
    effort: str,
    api_key: str,
) -> BenchmarkRunResult:
    """Execute a single model and effort combination evaluation."""
    try:
        client = instantiate_client(
            provider=args.provider,
            model=model,
            effort=effort,
            api_key=api_key,
            base_url=args.base_url,
            timeout=args.timeout,
            max_tokens=getattr(args, "max_tokens", None),
            mock=args.mock,
        )
        result = run_single_evaluation(
            service=service,
            client=client,
            model=model,
            effort=effort,
            count=args.count,
            occasion=args.occasion,
            budget=args.budget,
            hint=args.hint,
            save=args.save,
        )
    except Exception as exc:
        err_detail = _extract_error_detail(exc)
        if not args.json:
            sys.stdout.write(f" ✗ Error: {err_detail}\n")
        return BenchmarkRunResult(
            model=model,
            effort=effort,
            duration_s=0.0,
            success=False,
            error=err_detail,
            ideas=[],
            payload_size_chars=0,
        )
    else:
        if not args.json:
            status_icon = "✓" if result.success else "✗"
            sys.stdout.write(f" {status_icon} ({result.duration_s:.2f}s)\n")
        return result


def main() -> None:
    parser = _build_argument_parser()
    args = parser.parse_args()

    try:
        db_desc = configure_database(args)
    except Exception as exc:
        logger.info("\n❌ Database Connection Error: %s\n", exc)
        sys.exit(1)

    if _handle_discovery_modes(args):
        return

    translation.activate(args.lang)

    try:
        user, recipient = resolve_subject(
            user_identifier=args.user,
            recipient_identifier=args.recipient,
            recipient_id=args.recipient_id,
            family_name=args.family_name,
            group_identifier=args.group,
            group_id=args.group_id,
        )
    except ValueError as exc:
        logger.info("\n❌ %s\n", exc)
        sys.exit(1)

    api_key = _resolve_api_key(args)
    models, efforts = _resolve_models_and_efforts(args)
    service = GiftSuggestionService(user, recipient)

    test_matrix = [(m, e) for m in models for e in efforts]
    results: list[BenchmarkRunResult] = []

    if not args.json:
        logger.info("Starting benchmark across %d configuration(s)...", len(test_matrix))

    for model, effort in test_matrix:
        effort_label = f" (effort: {effort})" if effort else ""
        if not args.json:
            sys.stdout.write(f"  • Testing {model}{effort_label}...")
            sys.stdout.flush()

        results.append(
            _run_benchmark_turn(
                service=service,
                args=args,
                model=model,
                effort=effort,
                api_key=api_key,
            )
        )

    if args.json:
        logger.info(json.dumps([asdict(r) for r in results], indent=2))
    elif args.markdown:
        print_markdown_report(results)
    else:
        print_pretty_report(
            user=user,
            recipient=recipient,
            occasion=args.occasion,
            budget=args.budget,
            hint=args.hint,
            results=results,
            db_desc=db_desc,
            lang=args.lang,
        )


if __name__ == "__main__":
    main()
