"""Test helpers for building Job instances without repeating every field."""
from datetime import date

from jobalert.models import Category, Job

_DEFAULTS = dict(
    source="adzuna",
    external_id="1234567",
    title="Assistant Section Officer",
    org="Staff Selection Commission",
    location="New Delhi, India",
    apply_url="https://example.com/jobs/1234567",
    category=Category.GOVERNMENT,
    salary="Rs 44,900 - 1,42,400 per month",
    last_date=date(2026, 10, 15),
    posted_at=date(2026, 9, 1),
)


def make_job(**overrides) -> Job:
    return Job(**{**_DEFAULTS, **overrides})
