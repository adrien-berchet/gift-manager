import pytest

from gift_manager.suggestions.names import normalize_gift_name


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Lego  Technic! ", "lego technic"),
        ("Écharpe en laine", "echarpe en laine"),
        ("Café-crème", "cafe creme"),
        ("Cœur en chocolat", "coeur en chocolat"),
        ("Lætitia", "laetitia"),
        ("Книга", "книга"),
        ("日本語の本", "日本語の本"),
        ("", ""),
    ],
)
def test_normalize_gift_name(raw, expected):
    assert normalize_gift_name(raw) == expected


def test_normalize_gift_name_case_insensitive_and_diacritics():
    assert normalize_gift_name("ÉCHARPE") == normalize_gift_name("echarpe")
