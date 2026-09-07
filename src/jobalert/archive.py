"""Record of what has been published, with enough detail to rebuild the site.

``state/posted.json`` answers "have we posted this?" and nothing more. The landing
page needs the job itself - title, employer, apply link - so published jobs are
also appended here, newest first and capped.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Sequence

from jobalert.models import Job

log = logging.getLogger(__name__)

ARCHIVE_LIMIT = 200

Record = Dict[str, Any]


def load_archive(path: Path) -> List[Record]:
    """Read the archive. A missing or corrupt file reads as empty."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        log.error("archive at %s is unreadable (%s); treating as empty", path, exc)
        return []
    if not isinstance(data, list):
        log.error("archive at %s is not a list; treating as empty", path)
        return []
    return [record for record in data if isinstance(record, dict)]


def save_archive(path: Path, records: Sequence[Record]) -> None:
    """Write the archive atomically."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(list(records), handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    tmp.replace(path)


def to_record(job: Job, when: datetime) -> Record:
    """Flatten a job into the JSON shape the site generator consumes."""
    return {
        "job_id": job.job_id,
        "external_id": job.external_id,
        "title": job.title,
        "org": job.org,
        "location": job.location,
        "apply_url": job.apply_url,
        "category": job.category.name,
        "salary": job.salary,
        "salary_is_estimated": job.salary_is_estimated,
        "age_limit": job.age_limit,
        "application_fee": job.application_fee,
        "description": job.description,
        "start_date": job.start_date.isoformat() if job.start_date else None,
        "last_date": job.last_date.isoformat() if job.last_date else None,
        "source": job.source,
        "published_at": when.isoformat(),
    }


def append_published(archive: Sequence[Record], job: Job, when: datetime) -> List[Record]:
    """Return a new archive with ``job`` at the front, capped to the newest entries."""
    record = to_record(job, when)
    kept = [existing for existing in archive if existing.get("job_id") != record["job_id"]]
    return [record, *kept][:ARCHIVE_LIMIT]
