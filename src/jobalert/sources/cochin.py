"""Cochin Shipyard Limited - a Government of India public sector undertaking.

CSL publishes current openings as a plain HTML table with the one field most
government portals omit: a real closing date. Titles are prefixed with
"Vacancy Notification - " boilerplate, which is stripped so the poster shows the
role rather than the paperwork.
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

BASE = "https://cochinshipyard.in/"
CAREERS_URL = urljoin(BASE, "careers")

SOURCE_NAME = "cochin"
ORGANISATION = "Cochin Shipyard Limited"

_DATE = re.compile(r"(\d{2})-(\d{2})-(\d{4})")
_WHITESPACE = re.compile(r"\s+")
# Paperwork wording that says nothing about the role itself.
_BOILERPLATE = re.compile(
    r"^\s*(vacancy\s+notification|notification)\s*(for|-|:)?\s*"
    r"(engagement\s+of|selection\s+(to\s+the\s+post\s+of|of))?\s*",
    re.I,
)


class _TableParser(HTMLParser):
    """Collects each row's cell texts plus the first link in the row."""

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


def _parse_date(value: str) -> Optional[date]:
    match = _DATE.search(value or "")
    if not match:
        return None
    day, month, year = match.groups()
    try:
        return datetime(int(year), int(month), int(day)).date()
    except ValueError:
        return None


def _clean_title(raw: str) -> str:
    """Strip notification boilerplate so the role leads."""
    title = _BOILERPLATE.sub("", (raw or "").strip()).strip(" -:")
    # Some rows are shouted in full caps; sentence-case reads better at 90pt.
    if title and title.upper() == title and len(title) > 12:
        title = title.title()
    return title


class CochinShipyardSource:
    """Current openings at Cochin Shipyard and its units."""

    name = SOURCE_NAME

    def fetch(self, client: httpx.Client) -> List[Job]:
        response = client.get(CAREERS_URL, headers={"Accept": "text/html"})
        response.raise_for_status()

        parser = _TableParser()
        parser.feed(response.text)

        jobs: List[Job] = []
        for cells, href in zip(parser.rows, parser.links):
            job = self._to_job(cells, href)
            if job is not None:
                jobs.append(job)
        return jobs

    def _to_job(self, cells: List[str], href: Optional[str]) -> Optional[Job]:
        # Expected shape: serial, post, last date, location, read-more.
        if len(cells) < 4:
            return None
        last_date = _parse_date(cells[2])
        if last_date is None:
            # Also skips the header row, which has no date.
            return None

        title = _clean_title(cells[1])
        if not title or not href:
            log.info("cochin: skipping row without a title or link: %s", cells[:3])
            return None

        location = cells[3].strip() or "India"
        return Job(
            source=self.name,
            external_id=href.rstrip("/").rsplit("/", 1)[-1] or None,
            title=title,
            org=ORGANISATION,
            location=location,
            apply_url=urljoin(BASE, href),
            category=Category.GOVERNMENT,
            salary=None,
            last_date=last_date,
            source_url=CAREERS_URL,
        )
