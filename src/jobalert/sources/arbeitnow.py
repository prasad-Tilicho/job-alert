"""Arbeitnow job board API. Free, no key, European and remote roles."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from jobalert.models import Category, Job

log = logging.getLogger(__name__)

API_URL = "https://www.arbeitnow.com/api/job-board-api"
SOURCE_NAME = "arbeitnow"
ATTRIBUTION = "Arbeitnow"


class ArbeitnowSource:
    """Fetches the first page of the Arbeitnow board."""

    name = SOURCE_NAME

    def fetch(self, client: httpx.Client) -> List[Job]:
        response = client.get(API_URL)
        response.raise_for_status()
        rows = response.json().get("data") or []
        return [job for job in (self._to_job(row) for row in rows) if job is not None]

    def _to_job(self, row: Dict[str, Any]) -> Optional[Job]:
        title = (row.get("title") or "").strip()
        org = (row.get("company_name") or "").strip()
        url = (row.get("url") or "").strip()
        location = (row.get("location") or "").strip()
        if not (title and org and url and location):
            log.info("arbeitnow: skipping incomplete row slug=%s", row.get("slug"))
            return None

        if row.get("remote"):
            location = f"{location} (Remote)"

        return Job(
            source=self.name,
            external_id=row.get("slug"),
            title=title,
            org=org,
            location=location,
            apply_url=url,
            category=Category.PRIVATE,
            posted_at=_epoch_to_date(row.get("created_at")),
            source_url="https://www.arbeitnow.com/",
        )


def _epoch_to_date(epoch: Optional[int]):
    if not epoch:
        return None
    try:
        return datetime.fromtimestamp(int(epoch), tz=timezone.utc).date()
    except (ValueError, OSError, OverflowError, TypeError):
        return None
