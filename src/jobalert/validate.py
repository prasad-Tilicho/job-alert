"""Quality gate applied before anything reaches Instagram.

Publishing is fully automatic, so this module is the only thing between a bad
parse and a wrong deadline shown to real followers. It errs towards dropping.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable, List, Optional, Tuple
from urllib.parse import urlsplit

from jobalert.models import Job

MAX_TITLE_LEN = 200
MAX_DEADLINE_HORIZON = timedelta(days=365)


def _has_letters(value: str) -> bool:
    return any(ch.isalpha() for ch in value)


def rejection_reason(job: Job, today: date) -> Optional[str]:
    """Return why ``job`` must not be published, or None if it is publishable."""
    title = job.title.strip()
    if not title:
        return "missing title"
    if len(title) > MAX_TITLE_LEN:
        return "title too long"
    if not _has_letters(title):
        return "title has no letters"
    if not job.org.strip():
        return "missing organisation"
    if not job.location.strip():
        return "missing location"

    parts = urlsplit(job.apply_url.strip())
    if parts.scheme != "https" or not parts.netloc:
        return "apply url is not https"

    if job.last_date is not None:
        if job.last_date < today:
            return "deadline has passed"
        if job.last_date > today + MAX_DEADLINE_HORIZON:
            return "deadline is implausibly far away"
    return None


def partition_valid(
    jobs: Iterable[Job],
    today: date,
) -> Tuple[List[Job], List[Tuple[Job, str]]]:
    """Split jobs into (publishable, [(rejected, reason)]) preserving input order."""
    valid: List[Job] = []
    rejected: List[Tuple[Job, str]] = []
    for job in jobs:
        reason = rejection_reason(job, today=today)
        if reason is None:
            valid.append(job)
        else:
            rejected.append((job, reason))
    return valid, rejected
