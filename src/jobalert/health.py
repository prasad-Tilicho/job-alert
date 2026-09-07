"""Tracks whether each source is still working.

Sources are deliberately isolated: one failing site must not cost the whole run.
The cost of that isolation is silence - a parser broken by a site redesign keeps
failing while runs continue to succeed. This module turns that silence into an
alert.

Two distinct faults are tracked, because they need different patience:

* **Errors** are suspicious immediately; a short streak means something is wrong.
* **Zero results** are normal for some sources - SSC genuinely has no live exam
  between cycles - so a source is only flagged for zeroes if it has produced
  jobs before and has since gone quiet for a long stretch.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from jobalert.sources.registry import SourceOutcome

log = logging.getLogger(__name__)

# Consecutive failed runs before a source is called broken.
ERROR_THRESHOLD = 3
# Consecutive empty runs, for a source that has produced jobs before.
ZERO_THRESHOLD = 14

Health = Dict[str, Dict[str, Any]]


def _blank() -> Dict[str, Any]:
    return {
        "last_count": 0,
        "best_count": 0,
        "consecutive_zero": 0,
        "consecutive_error": 0,
        "last_success_at": None,
        "last_error": None,
    }


def update_health(health: Health, outcomes: Iterable[SourceOutcome], now: datetime) -> Health:
    """Return a new health record folding in this run's outcomes."""
    updated: Health = {name: dict(entry) for name, entry in health.items()}

    for outcome in outcomes:
        entry = dict(updated.get(outcome.name) or _blank())
        entry["last_count"] = outcome.count

        if not outcome.ok:
            entry["consecutive_error"] = int(entry.get("consecutive_error", 0)) + 1
            entry["last_error"] = outcome.error
        elif outcome.count == 0:
            entry["consecutive_error"] = 0
            entry["consecutive_zero"] = int(entry.get("consecutive_zero", 0)) + 1
        else:
            entry["consecutive_error"] = 0
            entry["consecutive_zero"] = 0
            entry["best_count"] = max(int(entry.get("best_count", 0)), outcome.count)
            entry["last_success_at"] = now.isoformat()
            entry["last_error"] = None

        updated[outcome.name] = entry
    return updated


def unhealthy_sources(health: Health) -> List[Tuple[str, str]]:
    """Return [(source, reason)] for sources that look broken."""
    problems: List[Tuple[str, str]] = []
    for name, entry in sorted(health.items()):
        errors = int(entry.get("consecutive_error", 0))
        zeroes = int(entry.get("consecutive_zero", 0))
        best = int(entry.get("best_count", 0))

        if errors >= ERROR_THRESHOLD:
            problems.append((name, f"failed {errors} runs in a row: {entry.get('last_error')}"))
        elif best > 0 and zeroes >= ZERO_THRESHOLD:
            problems.append((
                name,
                f"returned 0 jobs for {zeroes} runs in a row after previously "
                f"returning up to {best} - the page has probably changed",
            ))
    return problems


def summarise(outcomes: Sequence[SourceOutcome]) -> str:
    """One-line-per-source summary for the run log."""
    if not outcomes:
        return "no sources configured"
    return "\n".join(
        f"  {o.name:<16}{o.count:>4} jobs" + (f"   ERROR {o.error}" if not o.ok else "")
        for o in outcomes
    )


def load_health(path: Path) -> Health:
    """Read the health file. A missing or corrupt file reads as empty."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        log.error("health file at %s is unreadable (%s); starting fresh", path, exc)
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): dict(v) for k, v in data.items() if isinstance(v, dict)}


def save_health(path: Path, health: Health) -> None:
    """Write the health file atomically."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(health, handle, indent=2, sort_keys=True)
        handle.write("\n")
    tmp.replace(path)
