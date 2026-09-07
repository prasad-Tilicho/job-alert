"""Airports Authority of India recruitment notices.

AAI publishes a recruitment table that, unusually, states the number of posts on
offer - the fact job seekers care about most after the deadline.

The table carries no closing date, only the advertisement date, and it keeps
notices from previous years on the same page. Anything older than
:data:`MAX_NOTICE_AGE_DAYS` is dropped rather than presented as current, and the
poster shows the advertisement date so a reader can judge for themselves.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from typing import List, Optional
from urllib.parse import urljoin

import httpx

from jobalert.models import Category, Job

log = logging.getLogger(__name__)

BASE = "https://www.aai.aero/"
RECRUITMENT_URL = urljoin(BASE, "en/careers/recruitment")

SOURCE_NAME = "aai"
ORGANISATION = "Airports Authority of India"
LOCATION = "All India"

# Government application windows run about three to six weeks. Beyond this the
# notice is almost certainly closed, and presenting it as current would waste
# somebody's time.
MAX_NOTICE_AGE_DAYS = 45

_DATE = re.compile(r"(\d{2})-(\d{2})-(\d{4})")
_WHITESPACE = re.compile(r"\s+")
_EXCLUDE = re.compile(r"result|shortlist|answer key|cancell?ed|withdrawn|corrigendum", re.I)


class _TableParser(HTMLParser):
    """Collects each row's cells and its first link."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: List[List[str]] = []
        self.links: List[Optional[str]] = []
        self._cells: List[str] = []
        self._buf: List[str] = []
        self._href: Optional[str] = None
        self._in_row = False
        self._in_cell = False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._in_row, self._cells, self._href = True, [], None
        elif tag in ("td", "th") and self._in_row:
            self._in_cell, self._buf = True, []
        elif tag == "a" and self._in_row and self._href is None:
            href = dict(attrs).get("href")
            # Ignore the header's column-sort links.
            if href and "/recruitment/release/" in href:
                self._href = href

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._in_cell:
            self._cells.append(_WHITESPACE.sub(" ", "".join(self._buf)).strip())
            self._in_cell = False
        elif tag == "tr" and self._in_row:
            self.rows.append(self._cells)
            self.links.append(self._href)
            self._in_row = False

    def handle_data(self, data):
        if self._in_cell:
            self._buf.append(data)


def _parse_date(value: str) -> Optional[date]:
    match = _DATE.search(value or "")
    if not match:
        return None
    day, month, year = match.groups()
    try:
        return datetime(int(year), int(month), int(day)).date()
    except ValueError:
        return None


def _parse_posts(value: str) -> Optional[int]:
    digits = re.sub(r"[^\d]", "", value or "")
    if not digits:
        return None
    try:
        count = int(digits)
    except ValueError:
        return None
    return count if 0 < count < 100000 else None


class AaiSource:
    """Recent AAI recruitment notices."""

    name = SOURCE_NAME

    def __init__(self, max_age_days: int = MAX_NOTICE_AGE_DAYS):
        self._max_age = max_age_days

    def fetch(self, client: httpx.Client, today: Optional[date] = None) -> List[Job]:
        response = client.get(RECRUITMENT_URL, headers={"Accept": "text/html"})
        response.raise_for_status()

        parser = _TableParser()
        parser.feed(response.text)

        cutoff = (today or date.today()) - timedelta(days=self._max_age)
        jobs: List[Job] = []
        for cells, href in zip(parser.rows, parser.links):
            job = self._to_job(cells, href, cutoff)
            if job is not None:
                jobs.append(job)
        return jobs

    def _to_job(self, cells: List[str], href: Optional[str], cutoff: date) -> Optional[Job]:
        # Expected shape: exam name, department, total posts, job post date, ...
        if len(cells) < 4 or not href:
            return None

        title = cells[0].strip()
        if not title or _EXCLUDE.search(title):
            return None

        posted = _parse_date(cells[3])
        if posted is None or posted < cutoff:
            # Stale or undated: never present it as a current opening.
            return None

        if title.upper() == title and len(title) > 12:
            title = title.title()

        return Job(
            source=self.name,
            external_id=href.rstrip("/").rsplit("/", 1)[-1] or None,
            title=title,
            org=ORGANISATION,
            location=LOCATION,
            apply_url=urljoin(BASE, href),
            category=Category.GOVERNMENT,
            vacancies=_parse_posts(cells[2]),
            posted_at=posted,
            source_url=RECRUITMENT_URL,
        )
