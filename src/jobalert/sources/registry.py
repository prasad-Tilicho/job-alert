"""Assembles the enabled sources and fetches from all of them."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional, Sequence

import httpx

from jobalert.models import Job
from jobalert.sources.adzuna import AdzunaSource
from jobalert.sources.arbeitnow import ArbeitnowSource
from jobalert.sources.base import JobSource
from jobalert.sources.aai import AaiSource
from jobalert.sources.cochin import CochinShipyardSource
from jobalert.sources.esic import EsicSource
from jobalert.sources.isro import IsroSource
from jobalert.sources.remoteok import RemoteOkSource
from jobalert.sources.ssc import SscSource

if TYPE_CHECKING:  # pragma: no cover
    from jobalert.config import Config

log = logging.getLogger(__name__)

# Keywords for the public-sector pass: state-owned banks, insurers and PSUs.
PUBLIC_SECTOR_KEYWORDS = (
    "bank recruitment probationary officer clerk government public sector "
    "undertaking railway defence PSU nationalised"
)


def build_sources(config: "Config") -> List[JobSource]:
    """Return every source the current configuration can actually use."""
    # SSC first: it is the only source publishing authoritative government
    # notifications with a real application deadline, and it needs no key.
    sources: List[JobSource] = [SscSource(), IsroSource(), CochinShipyardSource()]

    # AAI and ESIC serve fine from an Indian residential network but refuse the
    # TCP connection from GitHub's runners, so enabling them there only produces
    # a permanent health alert. Set ENABLE_GEO_RESTRICTED=true when running from
    # a network they accept - a self-hosted runner, or locally.
    if config.enable_geo_restricted:
        sources.extend([AaiSource(), EsicSource()])
    else:
        log.info("geo-restricted sources (aai, esic) disabled; set ENABLE_GEO_RESTRICTED=true to use them")
    if config.adzuna_app_id and config.adzuna_app_key:
        sources.append(AdzunaSource(app_id=config.adzuna_app_id, app_key=config.adzuna_app_key))
        # Banks and PSUs advertise through Adzuna but rarely make the plain
        # recency query, so a second keyword-filtered pass surfaces them.
        sources.append(
            AdzunaSource(
                app_id=config.adzuna_app_id,
                app_key=config.adzuna_app_key,
                what_or=PUBLIC_SECTOR_KEYWORDS,
                max_days_old=21,
                name="adzuna-public",
            )
        )
    else:
        log.warning("adzuna credentials missing; skipping the only India-focused source")
    sources.append(ArbeitnowSource())
    sources.append(RemoteOkSource())
    return sources


@dataclass(frozen=True)
class SourceOutcome:
    """What one source did on one run."""

    name: str
    count: int
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class FetchResult:
    """Everything fetched, plus a per-source record for health tracking."""

    jobs: List[Job]
    outcomes: List[SourceOutcome]


def fetch_with_outcomes(sources: Sequence[JobSource], client: httpx.Client) -> FetchResult:
    """Fetch from every source, isolating failures and recording what each did.

    One unreachable API must never cost us the whole run, so each source is
    wrapped individually. That isolation is also why the outcomes matter: a
    broken source would otherwise fail silently for weeks.
    """
    collected: List[Job] = []
    outcomes: List[SourceOutcome] = []
    for source in sources:
        try:
            jobs = source.fetch(client)
        except Exception as exc:  # noqa: BLE001 - deliberately broad: isolate one bad source
            log.error("source %s failed: %s: %s", source.name, type(exc).__name__, exc)
            outcomes.append(
                SourceOutcome(name=source.name, count=0, error=f"{type(exc).__name__}: {exc}")
            )
            continue
        log.info("source %s returned %d jobs", source.name, len(jobs))
        outcomes.append(SourceOutcome(name=source.name, count=len(jobs)))
        collected.extend(jobs)
    return FetchResult(jobs=collected, outcomes=outcomes)


def fetch_all(sources: Sequence[JobSource], client: httpx.Client) -> List[Job]:
    """Fetch from every source, isolating failures."""
    return fetch_with_outcomes(sources, client).jobs
