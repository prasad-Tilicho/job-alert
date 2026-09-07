"""Core domain types.

Every type here is frozen: jobs flow through fetch -> validate -> render -> publish
without any stage mutating what an earlier stage produced.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from jobalert.dedupe import make_job_id
from jobalert.titles import tidy_title


class Category(enum.Enum):
    """Which bucket a posting falls into. Drives the poster's accent colour."""

    GOVERNMENT = "GOVT"
    PRIVATE = "PRIVATE"

    @property
    def label(self) -> str:
        """Short text shown in the poster's category pill."""
        return self.value


@dataclass(frozen=True)
class Job:
    """A single job posting, normalised across every source."""

    source: str
    title: str
    org: str
    location: str
    apply_url: str
    category: Category = Category.PRIVATE
    external_id: Optional[str] = None
    salary: Optional[str] = None
    # True when the source predicted the salary rather than the employer stating
    # it. Such figures are shown, but always labelled as estimates.
    salary_is_estimated: bool = False
    last_date: Optional[date] = None
    posted_at: Optional[date] = None
    source_url: Optional[str] = None
    _job_id: str = field(default="", init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        # Titles are normalised here rather than in each source, so a source added
        # later cannot forget to do it. Only spacing and punctuation are touched -
        # see :mod:`jobalert.titles`.
        object.__setattr__(self, "title", tidy_title(self.title))
        # Computed once at construction so the id is stable for the object's lifetime.
        object.__setattr__(
            self,
            "_job_id",
            make_job_id(self.source, external_id=self.external_id, apply_url=self.apply_url),
        )

    @property
    def job_id(self) -> str:
        """Stable identity used for deduplication and as the poster filename."""
        return self._job_id
