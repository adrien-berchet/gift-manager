"""Gift name normalisation for deduplication and matching."""

import re
import unicodedata

_NON_ALPHANUMERIC = re.compile(r"[^a-zA-Z0-9]+")


def normalize_gift_name(name: str) -> str:
    """Normalize a gift name for comparisons and deduplication.

    Decomposes characters with NFKD, strips combining marks (accents), casefolds,
    replaces runs of non-alphanumeric characters with a single space, and strips
    leading/trailing whitespace.
    """
    if not name:
        return ""
    decomposed = unicodedata.normalize("NFKD", name)
    without_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
    return _NON_ALPHANUMERIC.sub(" ", without_marks.casefold()).strip()
