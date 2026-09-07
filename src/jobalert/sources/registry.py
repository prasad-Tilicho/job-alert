"""Assembles the enabled sources and fetches from all of them."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Sequence

import httpx

from jobalert.models import Job
from jobalert.sources.adzuna import AdzunaSource
from jobalert.sources.arbeitnow import ArbeitnowSource
from jobalert.sources.base import JobSource
from jobalert.sources.remoteok import RemoteOkSource
from jobalert.sources.ssc import SscSource

if TYPE_CHECKING:  # pragma: no cover
    from jobalert.config import Config

log = logging.getLogger(__name__)


def build_sources(config: "Config") -> List[JobSource]:
    """Return every source the current configuration can actually use."""
    # SSC first: it is the only source publishing authoritative government
    # notifications with a real application deadline, and it needs no key.
    sources: List[JobSource] = [SscSource()]
    if config.adzuna_app_id and config.adzuna_app_key:
        sources.append(AdzunaSource(app_id=config.adzuna_app_id, app_key=config.adzuna_app_key))
    else:
        log.warning("adzuna credentials missing; skipping the only India-focused source")
    sources.append(ArbeitnowSource())
    sources.append(RemoteOkSource())
    return sources


def fetch_all(sources: Sequence[JobSource], client: httpx.Client) -> List[Job]:
    """Fetch from every source, isolating failures.

    One unreachable API must never cost us the whole run, so each source is
    wrapped individually and a failure is logged and skipped.
    """
    collected: List[Job] = []
    for source in sources:
        try:
            jobs = source.fetch(client)
        except Exception as exc:  # noqa: BLE001 - deliberately broad: isolate one bad source
            log.error("source %s failed: %s: %s", source.name, type(exc).__name__, exc)
            continue
        log.info("source %s returned %d jobs", source.name, len(jobs))
        collected.extend(jobs)
    return collected
