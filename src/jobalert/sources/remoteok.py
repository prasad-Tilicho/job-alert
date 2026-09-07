"""RemoteOK public JSON feed.

The first element of the response is a legal notice rather than a job; RemoteOK
asks for a link back and attribution, which :mod:`jobalert.caption` provides.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from jobalert.models import Category, Job

log = logging.getLogger(__name__)

API_URL = "https://remoteok.com/api"
SOURCE_NAME = "remoteok"
ATTRIBUTION = "RemoteOK"


class RemoteOkSource:
    """Fetches the RemoteOK feed."""

    name = SOURCE_NAME

    def fetch(self, client: httpx.Client) -> List[Job]:
        response = client.get(API_URL, headers={"Accept": "application/json"})
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list):
            return []
        # Row 0 is RemoteOK's legal notice, not a posting.
        jobs = (self._to_job(row) for row in rows if isinstance(row, dict) and "legal" not in row)
        return [job for job in jobs if job is not None]

    def _to_job(self, row: Dict[str, Any]) -> Optional[Job]:
        title = (row.get("position") or "").strip()
        org = (row.get("company") or "").strip()
        url = (row.get("apply_url") or row.get("url") or "").strip()
        location = (row.get("location") or "").strip()
        if not (title and org and url and location):
            log.info("remoteok: skipping incomplete row id=%s", row.get("id"))
            return None

        return Job(
            source=self.name,
            external_id=str(row.get("id")) if row.get("id") else None,
            title=title,
            org=org,
            location=location,
            apply_url=url,
            category=Category.PRIVATE,
            salary=_format_usd(row.get("salary_min"), row.get("salary_max")),
            posted_at=_epoch_to_date(row.get("epoch")),
            source_url="https://remoteok.com/",
        )


def _format_usd(minimum: Optional[int], maximum: Optional[int]) -> Optional[str]:
    if not minimum or not maximum:
        return None
    return f"${minimum:,.0f} - ${maximum:,.0f} per year"


def _epoch_to_date(epoch: Optional[int]):
    if not epoch:
        return None
    try:
        return datetime.fromtimestamp(int(epoch), tz=timezone.utc).date()
    except (ValueError, OSError, OverflowError, TypeError):
        return None
