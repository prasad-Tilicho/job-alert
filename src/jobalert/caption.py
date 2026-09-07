"""Builds the Instagram caption for a job.

Two hard constraints shape this module: Instagram allows 2,200 characters and 30
hashtags, and it does not linkify anything in a caption - hence "link in bio".
Source attribution is mandatory under Adzuna's and RemoteOK's terms, so it is
assembled last and never dropped by truncation.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import List

from jobalert.attribution import label_for
from jobalert.models import Category, Job

MAX_CAPTION_LEN = 2200
MAX_HASHTAGS = 30
ELLIPSIS = "..."

_NON_ALNUM = re.compile(r"[^a-z0-9]+")

BASE_TAGS = ("jobs", "jobalert", "hiring", "jobsearch", "career", "vacancy", "nowhiring")
GOVERNMENT_TAGS = ("governmentjobs", "govtjobs", "sarkarinaukri", "sarkarijob", "govtjobalert")
PRIVATE_TAGS = ("privatejobs", "corporatejobs", "techjobs", "freshersjobs")

# Location words that make useless hashtags on their own.
_LOCATION_STOPWORDS = frozenset({"india", "remote", "worldwide", "anywhere", "multiple", "locations", "across"})


def _slug(value: str) -> str:
    """Fold to bare ASCII letters and digits.

    Decomposing first matters: without it "Dusseldorf" spelled with an umlaut
    loses the vowel entirely and yields "#dsseldorfjobs".
    """
    decomposed = unicodedata.normalize("NFKD", value.strip().casefold())
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _NON_ALNUM.sub("", stripped)


def hashtags_for(job: Job) -> List[str]:
    """Build a de-duplicated, limit-respecting hashtag list for a job."""
    category_tags = GOVERNMENT_TAGS if job.category is Category.GOVERNMENT else PRIVATE_TAGS

    location_tags: List[str] = []
    for part in re.split(r"[,/()\-]", job.location):
        slug = _slug(part)
        if slug and slug not in _LOCATION_STOPWORDS and len(slug) > 2:
            location_tags.append(f"{slug}jobs")

    ordered: List[str] = []
    for tag in list(category_tags) + location_tags + list(BASE_TAGS):
        candidate = f"#{_slug(tag)}"
        if candidate != "#" and candidate not in ordered:
            ordered.append(candidate)
    return ordered[:MAX_HASHTAGS]


def _format_date(value: date) -> str:
    return value.strftime("%d %b %Y")


def build_caption(job: Job, handle: str, today: date) -> str:
    """Compose the full caption, truncating the headline before anything else.

    The tail (call to action, attribution, hashtags) is reserved first, so a very
    long job title can never push the required attribution out of the caption.
    """
    icon = "\U0001f3db️" if job.category is Category.GOVERNMENT else "\U0001f4bc"

    details = [f"\U0001f4cd Location: {job.location.strip()}"]
    if job.salary:
        label = "Salary (estimated)" if job.salary_is_estimated else "Salary"
        details.append(f"\U0001f4b0 {label}: {job.salary.strip()}")
    if job.age_limit:
        details.append(f"\U0001f9d1 Age limit: {job.age_limit.strip()}")
    if job.application_fee:
        details.append(f"\U0001f9fe Fee: {job.application_fee.strip()}")
    if job.last_date is not None:
        details.append(f"\U0001f5d3️ Apply by: {_format_date(job.last_date)}")

    tail_parts = [
        f"\U0001f449 Full details and apply link in bio {handle}",
        "",
        f"Source: {label_for(job.source)}",
        "",
        " ".join(hashtags_for(job)),
    ]
    tail = "\n".join(tail_parts)

    head = f"{icon} {job.title.strip()}\n{job.org.strip()}"
    body = "\n".join([head, "", "\n".join(details), "", tail])

    if len(body) <= MAX_CAPTION_LEN:
        return body

    # Shrink only the headline; everything below it is either factual or required.
    overflow = len(body) - MAX_CAPTION_LEN + len(ELLIPSIS)
    trimmed_title = job.title.strip()[: max(0, len(job.title.strip()) - overflow)].rstrip()
    head = f"{icon} {trimmed_title}{ELLIPSIS}\n{job.org.strip()}"
    body = "\n".join([head, "", "\n".join(details), "", tail])
    return body[:MAX_CAPTION_LEN]
