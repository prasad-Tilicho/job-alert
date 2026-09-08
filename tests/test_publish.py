from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import List, Optional, Sequence

import pytest

from jobalert.config import Config
from jobalert.dedupe import load_posted
from jobalert.models import Category
from jobalert.publish import RunResult, run, select_jobs
from tests.factories import make_job

TODAY = date(2026, 9, 7)


class FakeRenderer:
    def __init__(self):
        self.rendered: List[str] = []

    def render(self, job, dest: Path, today: date) -> Path:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"jpeg-bytes")
        self.rendered.append(job.job_id)
        return dest


class FakePublisher:
    def __init__(self, fail_on: Sequence[str] = ()):
        self.calls: List[tuple] = []
        self._fail_on = set(fail_on)

    def publish_photo(self, image_url: str, caption: str) -> str:
        self.calls.append((image_url, caption))
        for token in self._fail_on:
            if token in image_url:
                raise RuntimeError("instagram said no")
        return f"media-{len(self.calls)}"


class FakeRepo:
    def __init__(self, sha: str = "a" * 40):
        self._sha = sha
        self.saves: List[tuple] = []

    def save(self, paths: Sequence[str], message: str) -> Optional[str]:
        self.saves.append((tuple(paths), message))
        return self._sha

    def head_sha(self) -> str:
        return self._sha


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(
        repo="prasad/job-alert",
        ig_user_id="123",
        ig_access_token="tok",
        handle="@dailyjobalerts",
        max_posts_per_run=3,
        root=tmp_path,
    )


def do_run(config, jobs, renderer=None, publisher=None, repo=None, dry_run=False) -> RunResult:
    return run(
        config,
        today=TODAY,
        jobs=jobs,
        renderer=renderer or FakeRenderer(),
        publisher=publisher or FakePublisher(),
        repo=repo or FakeRepo(),
        dry_run=dry_run,
    )


class TestSelectJobs:
    def test_government_jobs_come_first(self):
        private = make_job(external_id="p", category=Category.PRIVATE)
        gov = make_job(external_id="g", category=Category.GOVERNMENT)
        assert select_jobs([private, gov], limit=2) == [gov, private]

    def test_newer_postings_beat_older_ones_within_a_category(self):
        old = make_job(external_id="o", posted_at=date(2026, 8, 1))
        new = make_job(external_id="n", posted_at=date(2026, 9, 5))
        assert select_jobs([old, new], limit=2) == [new, old]

    def test_applies_the_limit(self):
        jobs = [make_job(external_id=str(i)) for i in range(10)]
        assert len(select_jobs(jobs, limit=3)) == 3

    def test_is_deterministic_for_equally_ranked_jobs(self):
        jobs = [make_job(external_id=str(i), posted_at=None) for i in range(5)]
        assert select_jobs(jobs, limit=5) == select_jobs(list(reversed(jobs)), limit=5)


class TestRun:
    def test_paused_configuration_publishes_nothing(self, config):
        publisher = FakePublisher()
        result = do_run(replace(config, paused=True), [make_job()], publisher=publisher)
        assert result.skipped_paused is True
        assert publisher.calls == []

    def test_publishes_and_records_state(self, config):
        publisher = FakePublisher()
        result = do_run(config, [make_job(external_id="1")], publisher=publisher)
        assert len(result.published) == 1
        assert len(publisher.calls) == 1
        assert load_posted(config.state_path)

    def test_builds_the_image_url_from_the_pushed_commit(self, config):
        publisher = FakePublisher()
        job = make_job(external_id="1")
        do_run(config, [job], publisher=publisher, repo=FakeRepo(sha="deadbeef"))
        image_url, _ = publisher.calls[0]
        assert image_url == (
            f"https://raw.githubusercontent.com/prasad/job-alert/deadbeef/out/{job.job_id}.jpg"
        )

    def test_commits_posters_before_publishing_and_state_after(self, config):
        repo = FakeRepo()
        do_run(config, [make_job(external_id="1")], repo=repo)
        assert len(repo.saves) == 2
        assert "out" in repo.saves[0][0]
        assert "state" in repo.saves[1][0]

    def test_invalid_jobs_never_reach_instagram(self, config):
        publisher = FakePublisher()
        result = do_run(config, [make_job(external_id="1", last_date=date(2020, 1, 1))], publisher=publisher)
        assert publisher.calls == []
        assert result.published == []
        assert result.rejected == 1

    def test_already_posted_jobs_are_skipped(self, config):
        job = make_job(external_id="1")
        do_run(config, [job])
        publisher = FakePublisher()
        result = do_run(config, [job], publisher=publisher)
        # The single most important guarantee: a re-run must post nothing.
        assert publisher.calls == []
        assert result.published == []

    def test_respects_max_posts_per_run(self, config):
        publisher = FakePublisher()
        jobs = [make_job(external_id=str(i)) for i in range(10)]
        do_run(config, jobs, publisher=publisher)
        assert len(publisher.calls) == config.max_posts_per_run

    def test_a_failed_publish_is_not_recorded_and_does_not_stop_the_rest(self, config):
        jobs = [make_job(external_id="1"), make_job(external_id="2")]
        failing_id = jobs[0].job_id
        publisher = FakePublisher(fail_on=[failing_id])
        result = do_run(config, jobs, publisher=publisher)

        assert failing_id in [job_id for job_id, _ in result.failed]
        assert jobs[1].job_id in result.published
        # A job that failed must stay eligible for the next run.
        assert failing_id not in load_posted(config.state_path)

    def test_dry_run_renders_but_never_publishes_or_commits(self, config):
        publisher, repo, renderer = FakePublisher(), FakeRepo(), FakeRenderer()
        result = do_run(config, [make_job()], renderer=renderer, publisher=publisher, repo=repo, dry_run=True)
        assert renderer.rendered
        assert publisher.calls == []
        assert repo.saves == []
        assert result.published == []
        assert load_posted(config.state_path) == {}

    def test_an_empty_fetch_is_a_clean_no_op(self, config):
        result = do_run(config, [])
        assert result.published == []
        assert result.fetched == 0


class TestRelevanceTier:
    def test_government_outranks_everything(self):
        from jobalert.publish import relevance_tier

        assert relevance_tier(make_job(category=Category.GOVERNMENT, location="Berlin")) == 0

    def test_india_outranks_remote_which_outranks_a_local_foreign_role(self):
        from jobalert.publish import relevance_tier

        india = make_job(source="arbeitnow", category=Category.PRIVATE, location="Pune, India")
        remote = make_job(source="remoteok", category=Category.PRIVATE, location="Worldwide")
        foreign = make_job(source="arbeitnow", category=Category.PRIVATE, location="Düsseldorf")
        assert relevance_tier(india) < relevance_tier(remote) < relevance_tier(foreign)

    def test_adzuna_counts_as_india_because_of_its_country_endpoint(self):
        from jobalert.publish import relevance_tier

        job = make_job(source="adzuna", category=Category.PRIVATE, location="Bengaluru, Karnataka")
        assert relevance_tier(job) == 1

    def test_selection_prefers_an_india_role_over_a_newer_foreign_one(self):
        india = make_job(
            external_id="i", source="arbeitnow", category=Category.PRIVATE,
            location="Pune, India", posted_at=date(2026, 8, 1),
        )
        foreign = make_job(
            external_id="f", source="arbeitnow", category=Category.PRIVATE,
            location="Berlin", posted_at=date(2026, 9, 6),
        )
        assert select_jobs([foreign, india], limit=1) == [india]


class TestIsGlobalRemote:
    @pytest.mark.parametrize("location", ["Remote", "Worldwide", "Anywhere", "remote worldwide", "Global"])
    def test_recognises_genuinely_global_remote(self, location):
        from jobalert.publish import is_global_remote

        assert is_global_remote(location) is True

    @pytest.mark.parametrize("location", ["Leipzig (Remote)", "Berlin", "Pune, India", "London - Remote only"])
    def test_a_city_qualified_role_is_not_global_remote(self, location):
        from jobalert.publish import is_global_remote

        assert is_global_remote(location) is False

    def test_a_city_remote_role_ranks_below_a_truly_remote_one(self):
        from jobalert.publish import relevance_tier

        city_remote = make_job(source="arbeitnow", category=Category.PRIVATE, location="Leipzig (Remote)")
        worldwide = make_job(source="remoteok", category=Category.PRIVATE, location="Worldwide")
        assert relevance_tier(worldwide) < relevance_tier(city_remote)

    def test_a_second_run_over_the_same_feed_never_repeats_a_post(self, config):
        # With more candidates than slots, a re-run should move on to the next
        # batch rather than either repeating itself or stalling.
        jobs = [make_job(external_id=str(i)) for i in range(10)]
        first = do_run(config, jobs)
        second = do_run(config, jobs)
        assert len(first.published) == len(second.published) == config.max_posts_per_run
        assert set(first.published).isdisjoint(second.published)

    def test_runs_stop_publishing_once_the_feed_is_exhausted(self, config):
        jobs = [make_job(external_id=str(i)) for i in range(3)]
        do_run(config, jobs)
        publisher = FakePublisher()
        assert do_run(config, jobs, publisher=publisher).published == []
        assert publisher.calls == []

    def test_publishing_updates_the_archive_and_landing_page(self, config):
        from jobalert.archive import load_archive

        job = make_job(external_id="1")
        do_run(config, [job])

        archive = load_archive(config.archive_path)
        assert [record["job_id"] for record in archive] == [job.job_id]

        page = config.site_path.read_text(encoding="utf-8")
        assert job.title in page
        assert job.apply_url in page

    def test_the_landing_page_is_committed_with_the_state(self, config):
        repo = FakeRepo()
        do_run(config, [make_job()], repo=repo)
        state_commit_paths = repo.saves[1][0]
        assert "state" in state_commit_paths
        assert "docs" in state_commit_paths

    def test_a_failed_publish_leaves_the_archive_untouched(self, config):
        from jobalert.archive import load_archive

        job = make_job(external_id="1")
        do_run(config, [job], publisher=FakePublisher(fail_on=[job.job_id]))
        assert load_archive(config.archive_path) == []


class TestHealthTracking:
    def _outcomes(self, *pairs):
        from jobalert.sources.registry import SourceOutcome

        return [SourceOutcome(name=n, count=c, error=e) for n, c, e in pairs]

    def test_records_health_for_every_source(self, config):
        from jobalert.health import load_health

        run(config, today=TODAY, jobs=[make_job()], renderer=FakeRenderer(),
            publisher=FakePublisher(), repo=FakeRepo(),
            outcomes=self._outcomes(("ssc", 1, None), ("esic", 0, "boom")))
        health = load_health(config.health_path)
        assert health["ssc"]["last_count"] == 1
        assert health["esic"]["consecutive_error"] == 1

    def test_health_is_recorded_even_when_nothing_is_published(self, config):
        from jobalert.health import load_health

        # A run that publishes nothing is exactly when a broken source matters.
        result = run(config, today=TODAY, jobs=[], renderer=FakeRenderer(),
                     publisher=FakePublisher(), repo=FakeRepo(),
                     outcomes=self._outcomes(("isro", 0, "timeout")))
        assert result.published == []
        assert load_health(config.health_path)["isro"]["consecutive_error"] == 1

    def test_a_broken_source_is_reported_on_the_result(self, config):
        from jobalert.sources.registry import SourceOutcome

        repo = FakeRepo()
        for _ in range(3):
            result = run(config, today=TODAY, jobs=[], renderer=FakeRenderer(),
                         publisher=FakePublisher(), repo=repo,
                         outcomes=[SourceOutcome(name="esic", count=0, error="503")])
        assert [name for name, _ in result.unhealthy] == ["esic"]

    def test_a_dry_run_records_no_health(self, config):
        from jobalert.health import load_health

        run(config, today=TODAY, jobs=[make_job()], renderer=FakeRenderer(),
            publisher=FakePublisher(), repo=FakeRepo(), dry_run=True,
            outcomes=self._outcomes(("ssc", 1, None)))
        assert load_health(config.health_path) == {}

    def test_a_paused_run_records_no_health(self, config):
        from dataclasses import replace as _replace

        from jobalert.health import load_health

        run(_replace(config, paused=True), today=TODAY, jobs=[make_job()],
            renderer=FakeRenderer(), publisher=FakePublisher(), repo=FakeRepo(),
            outcomes=self._outcomes(("ssc", 1, None)))
        assert load_health(config.health_path) == {}

    def test_publishing_still_happens_when_a_source_is_unhealthy(self, config):
        # The alert must never cost the posts that did work.
        from jobalert.sources.registry import SourceOutcome

        repo, publisher = FakeRepo(), FakePublisher()
        for _ in range(3):
            result = run(config, today=TODAY, jobs=[make_job(external_id=str(_))],
                         renderer=FakeRenderer(), publisher=publisher, repo=repo,
                         outcomes=[SourceOutcome(name="esic", count=0, error="503")])
        assert result.published
        assert result.unhealthy


class TestAlternatingSelection:
    def _mixed(self, gov_count, private_count):
        gov = [make_job(external_id=f"g{i}", category=Category.GOVERNMENT) for i in range(gov_count)]
        pri = [make_job(external_id=f"p{i}", category=Category.PRIVATE) for i in range(private_count)]
        return gov + pri

    def test_alternates_government_and_private(self):
        picked = select_jobs(self._mixed(5, 5), limit=6)
        assert [j.category for j in picked] == [
            Category.GOVERNMENT, Category.PRIVATE,
            Category.GOVERNMENT, Category.PRIVATE,
            Category.GOVERNMENT, Category.PRIVATE,
        ]

    def test_leads_with_government(self):
        assert select_jobs(self._mixed(3, 3), limit=1)[0].category is Category.GOVERNMENT

    def test_falls_back_when_private_runs_out(self):
        # Government dominates the feed; a short private pool must not cap the run.
        picked = select_jobs(self._mixed(5, 1), limit=5)
        assert len(picked) == 5
        assert sum(1 for j in picked if j.category is Category.PRIVATE) == 1

    def test_falls_back_when_government_runs_out(self):
        picked = select_jobs(self._mixed(1, 5), limit=5)
        assert len(picked) == 5
        assert picked[0].category is Category.GOVERNMENT

    def test_respects_the_limit(self):
        assert len(select_jobs(self._mixed(20, 20), limit=5)) == 5

    def test_returns_everything_when_the_limit_exceeds_supply(self):
        assert len(select_jobs(self._mixed(2, 1), limit=10)) == 3

    def test_is_reproducible(self):
        jobs = self._mixed(6, 6)
        assert select_jobs(jobs, limit=6) == select_jobs(list(reversed(jobs)), limit=6)

    def test_still_prefers_india_within_the_private_side(self):
        # Adzuna is queried against its India endpoint, so an Adzuna job counts as
        # India whatever its location says; the foreign job needs another source.
        india = make_job(external_id="i", category=Category.PRIVATE, location="Pune, India")
        foreign = make_job(external_id="f", source="arbeitnow", category=Category.PRIVATE,
                           location="Berlin")
        gov = make_job(external_id="g", category=Category.GOVERNMENT)
        picked = select_jobs([foreign, india, gov], limit=2)
        assert picked[1] is india

    def test_an_empty_pool_yields_nothing(self):
        assert select_jobs([], limit=5) == []
