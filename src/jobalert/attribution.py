"""Human-readable source names.

Adzuna and RemoteOK both require attribution in their terms, so this is shared by
the poster footer and the caption rather than duplicated in each.
"""
from __future__ import annotations

from typing import Dict

SOURCE_LABELS: Dict[str, str] = {
    "adzuna": "Adzuna",
    "arbeitnow": "Arbeitnow",
    "remoteok": "RemoteOK",
    "ssc": "SSC",
    "isro": "ISRO",
    "cochin": "Cochin Shipyard",
    "aai": "AAI",
}


def label_for(source: str) -> str:
    """Display name for a source key, falling back to a title-cased key."""
    return SOURCE_LABELS.get(source.strip().casefold(), source.strip().title())
