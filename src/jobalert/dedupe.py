"""Stable job identity and the record of what has already been published.

The posted-state file is the single thing standing between a parser bug and the
same job being posted to real followers twice, so it is deliberately boring:
plain JSON, tolerant of corruption, pruned but never silently emptied.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

log = logging.getLogger(__name__)

JOB_ID_LEN = 16
DEFAULT_KEEP_DAYS = 180
_WHITESPACE = re.compile(r"\s+")
_TRACKING_PREFIXES = ("utm_",)
_TRACKING_PARAMS = frozenset({"gclid", "fbclid", "mc_cid", "mc_eid", "source", "src"})


def normalize_text(value: Optional[str]) -> str:
    """Fold text to a comparable form: NFKC, collapsed whitespace, casefolded."""
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value)
    return _WHITESPACE.sub(" ", normalized).strip().casefold()


def canonical_url(url: str) -> str:
    """Reduce a URL to the form two sources would agree on for the same posting.

    Drops the fragment and tracking parameters, lowercases the host (but not the
    path, which is case-sensitive on most servers), and sorts the query.
    """
    parts = urlsplit(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_PARAMS
        and not key.lower().startswith(_TRACKING_PREFIXES)
    ]
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(sorted(query)), ""))


def make_job_id(
    source: str,
    external_id: Optional[str] = None,
    apply_url: Optional[str] = None,
) -> str:
    """Derive a stable id for a posting.

    Prefers the source's own id, which survives the source rewriting its URLs;
    falls back to the canonical apply URL.
    """
    key = normalize_text(external_id) or (canonical_url(apply_url) if apply_url else "")
    if not key:
        raise ValueError(f"cannot identify a job from source {source!r} with no id and no url")
    digest = hashlib.sha256(f"{normalize_text(source)}|{key}".encode("utf-8"))
    return digest.hexdigest()[:JOB_ID_LEN]


def load_posted(path: Path) -> Dict[str, str]:
    """Read the posted-state file. A missing or corrupt file reads as empty."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        # Never crash the run over this, but make the damage loud in the logs:
        # an empty read means previously-posted jobs become eligible again.
        log.error("posted-state file at %s is unreadable (%s); treating as empty", path, exc)
        return {}
    if not isinstance(data, dict):
        log.error("posted-state file at %s is not an object; treating as empty", path)
        return {}
    return {str(k): str(v) for k, v in data.items()}


def save_posted(path: Path, posted: Dict[str, str]) -> None:
    """Write the posted-state file atomically so an interrupted run cannot truncate it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(posted, handle, indent=2, sort_keys=True)
        handle.write("\n")
    tmp.replace(path)


def mark_posted(posted: Dict[str, str], job_id: str, when: datetime) -> Dict[str, str]:
    """Return a new mapping with ``job_id`` recorded. Does not mutate the input."""
    return {**posted, job_id: when.isoformat()}


def filter_unposted(jobs: Iterable["object"], posted: Dict[str, str]) -> List["object"]:
    """Drop jobs already published, and collapse duplicates inside this batch."""
    seen = set(posted)
    fresh: List[object] = []
    for job in jobs:
        job_id = job.job_id  # type: ignore[attr-defined]
        if job_id in seen:
            continue
        seen.add(job_id)
        fresh.append(job)
    return fresh


def prune_posted(
    posted: Dict[str, str],
    now: datetime,
    keep_days: int = DEFAULT_KEEP_DAYS,
) -> Dict[str, str]:
    """Drop entries older than ``keep_days`` so the state file stays small.

    Entries with an unparseable timestamp are kept: we would rather carry a stale
    row forever than re-post a job because its date was written badly.
    """
    cutoff = now - timedelta(days=keep_days)
    kept = {}
    for job_id, stamp in posted.items():
        try:
            when = datetime.fromisoformat(stamp)
        except (ValueError, TypeError):
            kept[job_id] = stamp
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when >= cutoff:
            kept[job_id] = stamp
    return kept
