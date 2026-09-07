"""ISRO / Department of Space recruitment notices.

ISRO publishes vacancies as a plain HTML table on its careers page, so this reads
that page with the standard library's HTML parser.

The page mixes three kinds of entry - open vacancies, selection results, and
interview schedules - under one heading. Publishing a "Selection Panel" notice as
a job opening would actively mislead someone, so entries must match an inclusion
phrase *and* clear an exclusion list; anything ambiguous is dropped.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from html.parser import HTMLParser
from typing import List, Optional, Tuple
from urllib.parse import urljoin

import httpx

from jobalert.models import Category, Job

log = logging.getLogger(__name__)

BASE = "https://www.isro.gov.in/"
CAREERS_URL = urljoin(BASE, "Careers.html")

SOURCE_NAME = "isro"
ORGANISATION = "ISRO - Department of Space"
LOCATION = "All India"

# An entry must look like an open vacancy ...
_INCLUDE = re.compile(r"inviting applications?|recruitment to the posts?", re.I)
# ... and must not be an amendment, a result, or a schedule.
_EXCLUDE = re.compile(
    r"corrigendum|selection panel|schedule of interview|result|shortlist"
    r"|answer key|postponed|cancelled|withdrawn|addendum",
    re.I,
)
_POST_NAME = re.compile(r"(?:to|for)\s+the\s+posts?\s+of\s+(.+)$", re.I)
_ADVT_PREFIX = re.compile(r"^(?:advt\.?|advertisement)\s*no\.?[^-]*?(?:-|dated[^-]*-)\s*", re.I)
_DATED = re.compile(r"dated\.?\s*(\d{2})[-./](\d{2})[-./](\d{4})", re.I)
_TRAILING_NOISE = re.compile(r"\s*read\s+more\s*$", re.I)
_WHITESPACE = re.compile(r"\s+")


class _RowParser(HTMLParser):
    """Collects (text, first href) for every table row."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: List[Tuple[str, Optional[str]]] = []
        self._text: List[str] = []
        self._href: Optional[str] = None
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._depth, self._text, self._href = 1, [], None
        elif tag == "a" and self._depth and self._href is None:
            self._href = dict(attrs).get("href")

    def handle_endtag(self, tag):
        if tag == "tr" and self._depth:
            text = _WHITESPACE.sub(" ", "".join(self._text)).strip()
            if text:
                self.rows.append((text, self._href))
            self._depth = 0

    def handle_data(self, data):
        if self._depth:
            self._text.append(data)


def _parse_dated(text: str) -> Optional[date]:
    match = _DATED.search(text)
    if not match:
        return None
    day, month, year = match.groups()
    try:
        return datetime(int(year), int(month), int(day)).date()
    except ValueError:
        return None


def _title_from(text: str) -> str:
    """Reduce a notice line to the role being advertised."""
    cleaned = _TRAILING_NOISE.sub("", text).strip()
    match = _POST_NAME.search(cleaned)
    if match:
        return match.group(1).strip(" .,-")
    return _ADVT_PREFIX.sub("", cleaned).strip(" .,-")


class IsroSource:
    """Open vacancies from the ISRO careers page."""

    name = SOURCE_NAME

    def fetch(self, client: httpx.Client) -> List[Job]:
        response = client.get(CAREERS_URL, headers={"Accept": "text/html"})
        response.raise_for_status()

        parser = _RowParser()
        parser.feed(response.text)

        jobs = (self._to_job(text, href) for text, href in parser.rows)
        return [job for job in jobs if job is not None]

    def _to_job(self, text: str, href: Optional[str]) -> Optional[Job]:
        if not _INCLUDE.search(text) or _EXCLUDE.search(text):
            return None
        if not href:
            log.info("isro: skipping row with no link: %s", text[:60])
            return None

        title = _title_from(text)
        if not title:
            return None

        return Job(
            source=self.name,
            # The notice URL is the only stable identifier ISRO exposes.
            external_id=None,
            title=title,
            org=ORGANISATION,
            location=LOCATION,
            apply_url=urljoin(BASE, href),
            category=Category.GOVERNMENT,
            salary=None,
            # Closing dates live inside the linked notice, not in this table.
            last_date=None,
            posted_at=_parse_dated(text),
            source_url=CAREERS_URL,
        )
