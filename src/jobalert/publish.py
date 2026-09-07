"""Run orchestration: fetch, filter, render, commit, publish, record.

Ordering is load-bearing. Instagram fetches the poster from a public URL, so the
image must be committed and pushed *before* the media container is created; the
posted-state file is committed *after* publishing, so a crash mid-run leaves jobs
eligible to retry rather than silently marked as done.
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import httpx

from jobalert.archive import append_published, load_archive, save_archive
from jobalert.caption import build_caption
from jobalert.config import Config, ConfigError, load_config
from jobalert.dedupe import filter_unposted, load_posted, mark_posted, prune_posted, save_posted
from jobalert.gitops import commit, head_sha, push, stage
from jobalert.instagram import InstagramClient
from jobalert.models import Category, Job
from jobalert.poster.render import PosterRenderer
from jobalert.site import render_site
from jobalert.sources.registry import build_sources, fetch_all

log = logging.getLogger(__name__)

HTTP_TIMEOUT = 30.0
USER_AGENT = "jobalert/0.1 (+https://github.com/)"
OUT_DIR_NAME = "out"
STATE_DIR_NAME = "state"
SITE_DIR_NAME = "docs"


@dataclass(frozen=True)
class RunResult:
    """What a single run did, for logging and for the workflow summary."""

    fetched: int = 0
    rejected: int = 0
    selected: int = 0
    published: List[str] = field(default_factory=list)
    failed: List[Tuple[str, str]] = field(default_factory=list)
    skipped_paused: bool = False


INDIA_SOURCES = frozenset({"adzuna"})  # Adzuna is queried against its India endpoint.
INDIA_MARKERS = ("india",)
# Only these count as genuinely global remote. "Leipzig (Remote)" does not: it is
# a German-language, German-timezone role that happens to allow working from home.
GLOBAL_REMOTE = frozenset({"remote", "worldwide", "anywhere", "global", "remote worldwide"})
_REMOTE_QUALIFIER = re.compile(r"[()\[\]]|\bremote\b|\bonly\b|[,/-]")


def is_global_remote(location: str) -> bool:
    """True when a location says "anywhere", not "this city, from home"."""
    cleaned = " ".join(_REMOTE_QUALIFIER.sub(" ", location.casefold()).split())
    return cleaned in GLOBAL_REMOTE or (not cleaned and "remote" in location.casefold())


def relevance_tier(job: Job) -> int:
    """Lower is better. Decides which jobs are worth one of the day's few slots.

    The account is India-facing, so a locally-advertised European role is the
    least useful thing it can post - the keyless sources return plenty of those,
    and without this they crowd out everything else purely by arrival order.
    """
    if job.category is Category.GOVERNMENT:
        return 0
    location = job.location.casefold()
    if job.source in INDIA_SOURCES or any(marker in location for marker in INDIA_MARKERS):
        return 1
    if is_global_remote(job.location):
        return 2
    return 3


def select_jobs(jobs: Sequence[Job], limit: int) -> List[Job]:
    """Rank and cap the jobs to publish this run.

    Government postings lead because they are the account's reason to exist and
    are the scarcest; then India-relevant, then remote, then the rest. Ties break
    on recency, and finally on job id so the order is reproducible across runs.
    """
    def rank(job: Job):
        recency = -job.posted_at.toordinal() if job.posted_at else 0
        return (relevance_tier(job), recency, job.job_id)

    return sorted(jobs, key=rank)[:limit]


class GitRepoOps:
    """Commits and pushes the repository, which is also the poster's web host."""

    def __init__(self, root: Path, push_enabled: bool = True):
        self._root = Path(root)
        self._push = push_enabled

    def save(self, paths: Sequence[str], message: str) -> Optional[str]:
        stage(paths, cwd=self._root)
        sha = commit(message, cwd=self._root)
        if sha and self._push:
            push(cwd=self._root)
        return sha

    def head_sha(self) -> str:
        return head_sha(cwd=self._root)


def run(
    config: Config,
    today: date,
    jobs: Sequence[Job],
    renderer,
    publisher,
    repo,
    dry_run: bool = False,
) -> RunResult:
    """Execute one publishing run over already-fetched ``jobs``."""
    from jobalert.validate import partition_valid  # local import keeps the module graph flat

    if config.paused:
        log.warning("PAUSED is set; publishing nothing this run")
        return RunResult(fetched=len(jobs), skipped_paused=True)

    valid, rejected = partition_valid(jobs, today=today)
    for job, reason in rejected:
        log.info("rejected %s (%s): %s", job.job_id, reason, job.title[:80])

    posted = load_posted(config.state_path)
    fresh = filter_unposted(valid, posted)
    selected = select_jobs(fresh, limit=config.max_posts_per_run)
    log.info(
        "fetched=%d valid=%d fresh=%d selected=%d", len(jobs), len(valid), len(fresh), len(selected)
    )

    if not selected:
        return RunResult(fetched=len(jobs), rejected=len(rejected))

    rendered: List[Tuple[Job, Path, str]] = []
    for job in selected:
        dest = config.out_dir / f"{job.job_id}.jpg"
        renderer.render(job, dest, today=today)
        rendered.append((job, dest, build_caption(job, handle=config.handle, today=today)))

    if dry_run:
        for job, dest, caption in rendered:
            print(f"\n--- {dest} ---\n{caption}\n")
        log.info("dry run: %d poster(s) rendered, nothing published", len(rendered))
        return RunResult(fetched=len(jobs), rejected=len(rejected), selected=len(selected))

    # Posters must be live on raw.githubusercontent.com before Instagram is asked
    # to fetch them, so this commit happens before any publish call.
    sha = repo.save([OUT_DIR_NAME], f"chore: add {len(rendered)} poster(s)") or repo.head_sha()

    published: List[str] = []
    failed: List[Tuple[str, str]] = []
    archive = load_archive(config.archive_path)
    now = datetime.now(timezone.utc)
    for job, dest, caption in rendered:
        image_url = config.raw_url(sha, f"{OUT_DIR_NAME}/{dest.name}")
        try:
            media_id = publisher.publish_photo(image_url, caption)
        except Exception as exc:  # noqa: BLE001 - one bad post must not sink the run
            log.error("publishing %s failed: %s: %s", job.job_id, type(exc).__name__, exc)
            failed.append((job.job_id, str(exc)))
            continue
        log.info("published %s as media %s", job.job_id, media_id)
        published.append(job.job_id)
        # Recorded only on success, so a failure stays eligible for the next run.
        posted = mark_posted(posted, job.job_id, now)
        archive = append_published(archive, job, now)

    if published:
        save_posted(config.state_path, prune_posted(posted, now=now))
        save_archive(config.archive_path, archive)
        # The landing page is what "link in bio" points at, so it is regenerated
        # in the same commit as the state that produced it.
        render_site(archive, handle=config.handle, dest=config.site_path, generated_at=now)
        repo.save(
            [STATE_DIR_NAME, SITE_DIR_NAME],
            f"chore: record {len(published)} published job(s)",
        )

    return RunResult(
        fetched=len(jobs),
        rejected=len(rejected),
        selected=len(selected),
        published=published,
        failed=failed,
    )


def _fetch_jobs(config: Config) -> List[Job]:
    with httpx.Client(
        timeout=HTTP_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    ) as client:
        return fetch_all(build_sources(config), client)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Publish job posters to Instagram.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="render posters and print captions without publishing or committing",
    )
    parser.add_argument("--limit", type=int, default=None, help="override MAX_POSTS_PER_RUN")
    parser.add_argument("--no-push", action="store_true", help="commit locally without pushing")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    try:
        config = load_config(require_instagram=not args.dry_run)
    except ConfigError as exc:
        log.error("%s", exc)
        return 2

    if args.limit is not None:
        from dataclasses import replace

        config = replace(config, max_posts_per_run=max(1, args.limit))

    jobs = _fetch_jobs(config)

    renderer = PosterRenderer(fonts_dir=config.fonts_dir, handle=config.handle)
    with httpx.Client(timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
        publisher = InstagramClient(client, config.ig_user_id, config.ig_access_token)
        result = run(
            config,
            today=date.today(),
            jobs=jobs,
            renderer=renderer,
            publisher=publisher,
            repo=GitRepoOps(config.root, push_enabled=not args.no_push),
            dry_run=args.dry_run,
        )

    log.info(
        "done: fetched=%d rejected=%d published=%d failed=%d",
        result.fetched,
        result.rejected,
        len(result.published),
        len(result.failed),
    )
    return 1 if result.failed and not result.published else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
