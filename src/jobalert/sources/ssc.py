"""Staff Selection Commission - the official all-India recruitment body.

SSC's website is an Angular app backed by a public JSON API, so this reads that
API directly rather than scraping rendered HTML. Exam notices are Government of
India works, and the API needs no key.

This is the highest-value source in the project: unlike the commercial job APIs,
SSC publishes an authoritative *application closing date*, which is the single
most useful fact for anyone deciding whether to apply.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import httpx

from jobalert.models import Category, Job

log = logging.getLogger(__name__)

BASE = "https://ssc.gov.in"
LIVE_EXAMS_URL = f"{BASE}/api/admin/5.1/liveExams"
ALL_EXAMS_URL = f"{BASE}/api/admin/5.1/allExams"
NOTICE_BOARD = f"{BASE}/notice-board"

SOURCE_NAME = "ssc"
ORGANISATION = "Staff Selection Commission"
# SSC exams are conducted nationwide rather than at a single posting location.
LOCATION = "All India"


def _age_limit(row: Dict[str, Any]) -> Optional[str]:
    """Format SSC's min/max age, tolerating either bound being absent."""
    low, high = row.get("minAge"), row.get("maxAge")
    if low and high:
        return f"{int(low)} - {int(high)} years"
    if high:
        return f"Up to {int(high)} years"
    if low:
        return f"{int(low)} years and above"
    return None


def _fee(row: Dict[str, Any]) -> Optional[str]:
    """Base application fee. Category exemptions are set out in the notification."""
    fee = row.get("fee")
    try:
        return f"Rs {int(fee)}" if fee is not None and int(fee) >= 0 else None
    except (TypeError, ValueError):
        return None


def _parse_date(value: Optional[str]) -> Optional[date]:
    """Parse SSC's mix of plain dates and UTC timestamps."""
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


class SscSource:
    """Live SSC examinations with an open application window."""

    name = SOURCE_NAME

    def fetch(self, client: httpx.Client) -> List[Job]:
        response = client.get(LIVE_EXAMS_URL, headers={"Accept": "application/json"})
        response.raise_for_status()
        live = response.json().get("data") or []

        forms = self._application_forms(client)
        jobs = (self._to_job(row, forms) for row in live)
        return [job for job in jobs if job is not None]

    def _application_forms(self, client: httpx.Client) -> Dict[str, str]:
        """Map exam code -> application form path.

        Only used to deep-link the apply button, so a failure here degrades to the
        notice board rather than costing us the listings.
        """
        try:
            response = client.get(ALL_EXAMS_URL, headers={"Accept": "application/json"})
            response.raise_for_status()
            rows = response.json().get("data") or []
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("ssc: exam catalogue unavailable (%s); linking to the notice board", exc)
            return {}

        forms: Dict[str, str] = {}
        for row in rows:
            code, url = row.get("examCode"), row.get("navigationUrl")
            if code and url:
                forms.setdefault(str(code), str(url))
        return forms

    def _to_job(self, row: Dict[str, Any], forms: Dict[str, str]) -> Optional[Job]:
        if not row.get("isActive"):
            return None

        last_date = _parse_date(row.get("applicationEndDate"))
        if last_date is None:
            # An SSC listing with no closing date cannot tell anyone when to apply.
            log.info("ssc: skipping %s with no application end date", row.get("examCode"))
            return None

        title = (row.get("examDescription") or row.get("examName") or "").strip()
        code = str(row.get("examCode") or "").strip()
        if not title:
            title = f"{code} Examination {row.get('examYear') or ''}".strip()
        if not title:
            return None

        path = forms.get(code)
        apply_url = f"{BASE}{path}" if path and path.startswith("/") else NOTICE_BOARD

        return Job(
            source=self.name,
            external_id=str(row.get("id")) if row.get("id") else None,
            title=title,
            org=ORGANISATION,
            location=LOCATION,
            apply_url=apply_url,
            category=Category.GOVERNMENT,
            # SSC publishes no pay figure here; the notification PDF carries it.
            salary=None,
            age_limit=_age_limit(row),
            application_fee=_fee(row),
            last_date=last_date,
            posted_at=_parse_date(row.get("applicationStartDate")),
            source_url=NOTICE_BOARD,
        )
