"""Employees' State Insurance Corporation - hospital and medical recruitment.

ESIC runs hospitals and medical colleges across India and recruits constantly,
mostly for teaching faculty, senior residents and specialists.

Its recruitment table mixes openings with results, shortlists, corrigenda and
addenda under one heading, so a row must match an inclusion phrase *and* clear an
exclusion list. A closing date is shown when the table states one and simply
omitted when it does not - many ESIC posts are walk-in interviews with a date
rather than an application deadline.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from html.parser import HTMLParser
from typing import List, Optional
from urllib.parse import urljoin

import httpx

from jobalert.models import Category, Job

log = logging.getLogger(__name__)

BASE = "https://www.esic.gov.in/"
LISTING_URL = urljoin(BASE, "recruitments")
PAGE_URL = urljoin(BASE, "recruitments/index/page:{page}")
DEFAULT_PAGES = 3

SOURCE_NAME = "esic"
ORGANISATION = "Employees' State Insurance Corporation"

_WHITESPACE = re.compile(r"\s+")
_ISO_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
# "- PDF size:(1.67 MB) ." trails many subject lines.
_PDF_NOISE = re.compile(r"\s*-?\s*PDF\s*size\s*:?\s*\([^)]*\)\s*\.?\s*$", re.I)
_LEADING_NOISE = re.compile(r"^\s*(regarding\s+uploading|regarding)\s+", re.I)

_INCLUDE = re.compile(
    r"walk[\s-]*in|recruitment|advertisement|vacanc|engagement|appointment|empanelment",
    re.I,
)
_EXCLUDE = re.compile(
    r"result|shortlist|short-list|merit list|corrigendum|addendum|answer key"
    r"|cancell|withdrawn|provisional|selected candidates|postpone",
    re.I,
)


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
            self._href = dict(attrs).get("href")

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


def _parse_iso(value: str) -> Optional[date]:
    """Pull a YYYY-MM-DD out of cells like 'Interview (2026-09-18)' or 'Others'."""
    match = _ISO_DATE.search(value or "")
    if not match:
        return None
    year, month, day = match.groups()
    try:
        return datetime(int(year), int(month), int(day)).date()
    except ValueError:
        return None


def clean_subject(subject: str) -> str:
    """Strip attachment noise and soften shouted lines."""
    title = _PDF_NOISE.sub("", (subject or "").strip())
    title = _LEADING_NOISE.sub("", title).strip(" -–:.")
    if title and title.upper() == title and len(title) > 12:
        title = title.title()
    return title


class EsicSource:
    """Open recruitments across ESIC hospitals and medical colleges."""

    name = SOURCE_NAME

    def __init__(self, pages: int = DEFAULT_PAGES):
        self._pages = max(1, pages)

    def fetch(self, client: httpx.Client) -> List[Job]:
        jobs: List[Job] = []
        for page in range(1, self._pages + 1):
            url = LISTING_URL if page == 1 else PAGE_URL.format(page=page)
            if page == 1:
                response = client.get(url, headers={"Accept": "text/html"})
                response.raise_for_status()
            else:
                # Later pages are a bonus; losing one must not cost us page 1.
                try:
                    response = client.get(url, headers={"Accept": "text/html"})
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    log.warning("esic: page %d unavailable (%s)", page, exc)
                    continue

            parser = _TableParser()
            parser.feed(response.text)
            for cells, href in zip(parser.rows, parser.links):
                job = self._to_job(cells, href)
                if job is not None:
                    jobs.append(job)
        return jobs

    def _to_job(self, cells: List[str], href: Optional[str]) -> Optional[Job]:
        # Expected shape: serial, office, subject, publish date, last date, ref.
        if len(cells) < 5:
            return None

        subject = cells[2]
        if not _INCLUDE.search(subject) or _EXCLUDE.search(subject):
            return None

        title = clean_subject(subject)
        if not title or not href:
            return None

        office = cells[1].strip() or "India"
        reference = cells[5].strip() if len(cells) > 5 else ""

        return Job(
            source=self.name,
            # The console reference is stable; the attachment path is not.
            external_id=reference.replace("/", "-") or None,
            title=title,
            org=ORGANISATION,
            location=office,
            apply_url=urljoin(BASE, href),
            category=Category.GOVERNMENT,
            # Shown when the table states one; many rows are walk-ins with none.
            last_date=_parse_iso(cells[4]),
            posted_at=_parse_iso(cells[3]),
            source_url=LISTING_URL,
        )
