"""Gift name normalisation for deduplication and matching."""

import re
import unicodedata

_NON_ALPHANUMERIC = re.compile(r"[^\w]+", re.UNICODE)


def normalize_gift_name(name: str) -> str:
    """Normalize a gift name for comparisons and deduplication.

    Expands common ligatures (œ -> oe, æ -> ae), decomposes characters with NFKD,
    strips combining marks (accents), casefolds, replaces runs of non-word
    characters with a single space, and strips leading/trailing whitespace.
    """
    if not name:
        return ""
    expanded = name.replace("œ", "oe").replace("Œ", "oe").replace("æ", "ae").replace("Æ", "ae")
    decomposed = unicodedata.normalize("NFKD", expanded)
    without_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
    return _NON_ALPHANUMERIC.sub(" ", without_marks.casefold()).strip()
