from datetime import datetime, timezone

from jobalert.health import (
    ERROR_THRESHOLD,
    ZERO_THRESHOLD,
    load_health,
    save_health,
    summarise,
    unhealthy_sources,
    update_health,
)
from jobalert.sources.registry import SourceOutcome

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


def ok(name, count):
    return SourceOutcome(name=name, count=count, error=None)


def err(name, message="boom"):
    return SourceOutcome(name=name, count=0, error=message)


def repeat(outcome, times, health=None):
    health = health or {}
    for _ in range(times):
        health = update_health(health, [outcome], now=NOW)
    return health


class TestUpdateHealth:
    def test_records_a_successful_fetch(self):
        health = update_health({}, [ok("ssc", 5)], now=NOW)
        assert health["ssc"]["last_count"] == 5
        assert health["ssc"]["consecutive_error"] == 0
        assert health["ssc"]["consecutive_zero"] == 0
        assert health["ssc"]["best_count"] == 5

    def test_does_not_mutate_the_input(self):
        original = update_health({}, [ok("ssc", 5)], now=NOW)
        update_health(original, [ok("ssc", 0)], now=NOW)
        assert original["ssc"]["last_count"] == 5

    def test_remembers_the_best_count_a_source_has_managed(self):
        health = update_health({}, [ok("isro", 10)], now=NOW)
        health = update_health(health, [ok("isro", 3)], now=NOW)
        assert health["isro"]["best_count"] == 10

    def test_counts_consecutive_zero_runs(self):
        health = repeat(ok("ssc", 0), 3)
        assert health["ssc"]["consecutive_zero"] == 3

    def test_a_successful_fetch_resets_the_streaks(self):
        health = repeat(err("esic"), 5)
        health = update_health(health, [ok("esic", 4)], now=NOW)
        assert health["esic"]["consecutive_error"] == 0
        assert health["esic"]["consecutive_zero"] == 0

    def test_tracks_when_a_source_last_produced_anything(self):
        health = update_health({}, [ok("aai", 2)], now=NOW)
        assert health["aai"]["last_success_at"] == NOW.isoformat()
        later = update_health(health, [err("aai")], now=NOW)
        assert later["aai"]["last_success_at"] == NOW.isoformat()

    def test_sources_are_tracked_independently(self):
        health = update_health({}, [ok("ssc", 1), err("esic")], now=NOW)
        assert health["ssc"]["consecutive_error"] == 0
        assert health["esic"]["consecutive_error"] == 1


class TestUnhealthySources:
    def test_a_healthy_run_reports_nothing(self):
        assert unhealthy_sources(update_health({}, [ok("ssc", 3)], now=NOW)) == []

    def test_repeated_errors_are_flagged(self):
        health = repeat(err("esic", "503"), ERROR_THRESHOLD)
        flagged = dict(unhealthy_sources(health))
        assert "esic" in flagged
        assert "503" in flagged["esic"]

    def test_a_single_error_is_not_flagged(self):
        # Transient failures are normal; only a streak means something is broken.
        assert unhealthy_sources(repeat(err("esic"), ERROR_THRESHOLD - 1)) == []

    def test_a_source_that_stops_returning_results_is_flagged(self):
        health = update_health({}, [ok("esic", 15)], now=NOW)
        health = repeat(ok("esic", 0), ZERO_THRESHOLD, health)
        flagged = dict(unhealthy_sources(health))
        assert "esic" in flagged
        assert "0 jobs" in flagged["esic"]

    def test_a_source_that_never_produced_anything_is_not_flagged_for_zeroes(self):
        # SSC legitimately has no live exam between cycles; that is not a fault.
        assert unhealthy_sources(repeat(ok("ssc", 0), ZERO_THRESHOLD * 2)) == []

    def test_a_brief_quiet_spell_is_not_flagged(self):
        health = update_health({}, [ok("ssc", 1)], now=NOW)
        assert unhealthy_sources(repeat(ok("ssc", 0), ZERO_THRESHOLD - 1, health)) == []


class TestPersistence:
    def test_missing_file_reads_as_empty(self, tmp_path):
        assert load_health(tmp_path / "nope.json") == {}

    def test_corrupt_file_reads_as_empty(self, tmp_path):
        path = tmp_path / "health.json"
        path.write_text("{oops", encoding="utf-8")
        assert load_health(path) == {}

    def test_roundtrips(self, tmp_path):
        path = tmp_path / "health.json"
        health = update_health({}, [ok("ssc", 2)], now=NOW)
        save_health(path, health)
        assert load_health(path) == health


class TestSummarise:
    def test_lists_each_source_and_its_count(self):
        text = summarise([ok("ssc", 1), ok("isro", 10), err("esic", "timeout")])
        assert "ssc" in text and "1" in text
        assert "isro" in text and "10" in text
        assert "esic" in text and "timeout" in text

    def test_handles_an_empty_run(self):
        assert summarise([]) == "no sources configured"
