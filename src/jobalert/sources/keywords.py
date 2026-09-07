"""Heuristic for telling a government posting apart from a private one.

Deliberately conservative: a false GOVERNMENT tag is worse than a missed one,
because the poster's category pill is a factual claim about the employer.
"""
from __future__ import annotations

from jobalert.dedupe import normalize_text

GOVERNMENT_MARKERS = (
    "government of",
    "govt of",
    "ministry of",
    "department of",
    "public sector",
    "recruitment board",
    "selection commission",
    "staff selection",
    "public service commission",
    "sarkari",
    "municipal corporation",
    "state bank",
    "reserve bank",
    "indian army",
    "indian navy",
    "indian air force",
    "railway",
    "psu ",
    "ongc",
    "bhel",
    "drdo",
    "isro",
    "upsc",
    "ssc ",
    "ibps",
    "nabard",
    "aiims",
)


def looks_governmental(*fields: str) -> bool:
    """True when any field contains a recognised government-employer marker."""
    haystack = " ".join(normalize_text(field) for field in fields if field)
    # Pad so markers with a trailing space (e.g. "ssc ") can match at the end.
    haystack = f" {haystack} "
    return any(marker in haystack for marker in GOVERNMENT_MARKERS)
