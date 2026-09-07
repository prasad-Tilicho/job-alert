"""Adzuna job search API (India).

Free tier is roughly 1,000 calls a month, which is ample for a couple of runs a
day. Adzuna's terms require attribution, which :mod:`jobalert.caption` adds.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from jobalert.models import Category, Job
from jobalert.sources.keywords import looks_governmental
from jobalert.summarise import summarise

log = logging.getLogger(__name__)

BASE_URL = "https://api.adzuna.com/v1/api/jobs"
COUNTRY = "in"
SOURCE_NAME = "adzuna"
ATTRIBUTION = "Adzuna"


def _format_inr(minimum: Optional[float], maximum: Optional[float]) -> Optional[str]:
    """Render an annual INR range in lakhs, the unit Indian listings actually use."""
    if not minimum or not maximum:
        return None
    return f"Rs {minimum / 100000:.1f}L - {maximum / 100000:.1f}L per year"


def _parse_date(value: Optional[str]):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


class AdzunaSource:
    """Fetches recent Indian listings from Adzuna."""

    name = SOURCE_NAME

    def __init__(self, app_id: str, app_key: str, results_per_page: int = 30, max_days_old: int = 7):
        self._app_id = app_id
        self._app_key = app_key
        self._results_per_page = results_per_page
        self._max_days_old = max_days_old

    def fetch(self, client: httpx.Client) -> List[Job]:
        response = client.get(
            f"{BASE_URL}/{COUNTRY}/search/1",
            params={
                "app_id": self._app_id,
                "app_key": self._app_key,
                "results_per_page": self._results_per_page,
                "max_days_old": self._max_days_old,
                "sort_by": "date",
                "content-type": "application/json",
            },
        )
        response.raise_for_status()
        results = response.json().get("results") or []
        return [job for job in (self._to_job(row) for row in results) if job is not None]

    def _to_job(self, row: Dict[str, Any]) -> Optional[Job]:
        org = (row.get("company") or {}).get("display_name") or ""
        location = (row.get("location") or {}).get("display_name") or ""
        apply_url = row.get("redirect_url") or ""
        title = row.get("title") or ""
        if not (org and location and apply_url and title):
            log.info("adzuna: skipping incomplete row id=%s", row.get("id"))
            return None

        # Adzuna predicts most salaries. Dropping them left nearly every Indian
        # poster with no pay information at all, so they are shown but flagged -
        # a labelled estimate informs without asserting the employer's offer.
        salary = _format_inr(row.get("salary_min"), row.get("salary_max"))
        estimated = str(row.get("salary_is_predicted", "1")) != "0"

        category_label = (row.get("category") or {}).get("label") or ""
        is_gov = looks_governmental(org, title, category_label)

        return Job(
            source=self.name,
            external_id=str(row.get("id")) if row.get("id") else None,
            title=title.strip(),
            org=org.strip(),
            location=location.strip(),
            apply_url=apply_url.strip(),
            category=Category.GOVERNMENT if is_gov else Category.PRIVATE,
            salary=salary,
            salary_is_estimated=bool(salary) and estimated,
            description=summarise(row.get("description")),
            posted_at=_parse_date(row.get("created")),
            source_url="https://www.adzuna.in/",
        )
