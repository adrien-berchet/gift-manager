"""Guards against user-facing text and formats that bypass the French translation."""

import ast
import re
from pathlib import Path

import pytest
from django.conf import settings
from django.template.loader import render_to_string
from django.test import Client
from django.utils import translation
from django.utils.translation import override
from django.utils.translation import trans_real

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_ROOT = PROJECT_ROOT / "gift_manager/templates"


@pytest.fixture(autouse=True)
def _restore_active_language():
    """Requests to /fr/ activate French and nothing resets it; do not leak into later tests."""
    yield
    translation.activate(settings.LANGUAGE_CODE)


# Format names that follow the active locale (Django's DATE_FORMAT family)
LOCALE_DATE_FORMAT = re.compile(r"^[A-Z][A-Z_]*_FORMAT$")


def test_templates_do_not_hardcode_english_date_formats():
    offenders = [
        f"{path.relative_to(TEMPLATE_ROOT)}: {match.group(0)}"
        for path in TEMPLATE_ROOT.rglob("*.html")
        for match in re.finditer(r'\|date:"([^"]*)"', path.read_text(encoding="utf-8"))
        if not LOCALE_DATE_FORMAT.match(match.group(1))
    ]
    assert offenders == [], "Use DATE_FORMAT / SHORT_DATE_FORMAT so dates follow the locale"


@pytest.mark.django_db
def test_base_template_follows_the_active_language():
    english = Client().get("/en/").content.decode()
    french = Client().get("/fr/").content.decode()

    assert '<html lang="en">' in english
    assert '<html lang="fr">' in french
    assert 'aria-label="Toggle dark mode"' in english
    assert 'aria-label="Basculer le mode sombre"' in french
    # Labels handed to the static scripts are translated too
    assert "loading: 'Chargement...'" in french
    assert "deleting: 'Suppression...'" in french
    assert "fieldRequired: 'Ce champ est obligatoire'" in french


def test_script_labels_in_base_template_have_french_translations():
    """Every msgid passed to the JS config must be translated, not silently English."""
    base = (TEMPLATE_ROOT / "gift_manager/base.html").read_text(encoding="utf-8")
    msgids = set(re.findall(r'\{% trans "([^"]+)" as t %\}', base))
    assert len(msgids) > 20  # the i18n and uiTranslations objects

    # Look entries up in the catalog: some words (e.g. "Tags") are legitimately identical
    catalog = trans_real.translation("fr")._catalog
    untranslated = sorted(m for m in msgids if not catalog.get(m))
    assert untranslated == []


@pytest.mark.django_db
def test_delete_confirmation_details_are_translated(monkeypatch):
    from gift_manager.views.base import DeleteConfirmationMixin

    class FakeObject:
        date_summary = "Chaque année"
        is_scheduled = True

    class Probe(DeleteConfirmationMixin):
        object = FakeObject()

    with override("fr"):
        assert Probe().get_entity_details() == ["Planification : Chaque année"]
    with override("en"):
        assert Probe().get_entity_details() == ["Schedule: Chaque année"]


def test_allauth_layout_sets_language_attribute():
    with override("fr"):
        html = render_to_string("allauth/layouts/base.html", {})
    assert '<html lang="fr"' in html


def _catalog_entries():
    """Msgid -> True for every French catalog entry that has a translation."""
    return {msgid for msgid, msgstr in trans_real.translation("fr")._catalog.items() if msgstr}


def test_every_template_and_python_string_has_a_french_translation():
    """Catch strings added without updating locale/fr (they would silently render in English)."""
    translated = _catalog_entries()
    trans_tag = re.compile(r"""\{%\s*trans\s+(?:"([^"]*)"|'([^']*)')""")
    used = {}
    for path in TEMPLATE_ROOT.rglob("*.html"):
        for match in trans_tag.finditer(path.read_text(encoding="utf-8")):
            msgid = match.group(1) if match.group(1) is not None else match.group(2)
            if msgid:
                used.setdefault(msgid, path.relative_to(PROJECT_ROOT).as_posix())

    packages = [PROJECT_ROOT / "gift_manager", PROJECT_ROOT / "GiftManager"]
    for package in packages:
        for path in package.rglob("*.py"):
            if {"tests", "migrations"} & set(path.parts):
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                func = node.func
                name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
                first = node.args[0]
                if (
                    name in {"gettext", "gettext_lazy", "_"}
                    and isinstance(first, ast.Constant)
                    and isinstance(first.value, str)
                ):
                    used.setdefault(
                        first.value, f"{path.relative_to(PROJECT_ROOT).as_posix()}:{node.lineno}"
                    )

    missing = sorted(
        f"{where}: {msgid}" for msgid, where in used.items() if msgid not in translated
    )
    assert missing == [], "Add these strings to locale/fr/LC_MESSAGES/django.po and compile it"


@pytest.mark.django_db
def test_dashboard_renders_in_french(client, user):
    client.force_login(user)
    french = client.get("/fr/").content.decode()

    for expected in ("Prochaines actions", "Bibliothèque", "Tableau de bord"):
        assert expected in french
    for english in ("Next actions", ">Library<", "Dashboard summary"):
        assert english not in french
