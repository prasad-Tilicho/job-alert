from datetime import datetime, timezone

import pytest

from jobalert.dedupe import (
    canonical_url,
    filter_unposted,
    load_posted,
    make_job_id,
    mark_posted,
    normalize_text,
    prune_posted,
    save_posted,
)
from tests.factories import make_job


class TestNormalizeText:
    def test_collapses_whitespace_and_casefolds(self):
        assert normalize_text("  Senior   Data\tEngineer \n") == "senior data engineer"

    def test_unicode_is_nfkc_normalized(self):
        # Fullwidth characters must fold to their ASCII equivalents.
        assert normalize_text("ＡＢＣ") == "abc"

    def test_none_and_empty_become_empty_string(self):
        assert normalize_text(None) == ""
        assert normalize_text("   ") == ""


class TestCanonicalUrl:
    def test_drops_fragment_and_tracking_params(self):
        url = "https://Example.COM/jobs/42?utm_source=x&utm_medium=y&ref=1#apply"
        assert canonical_url(url) == "https://example.com/jobs/42?ref=1"

    def test_strips_trailing_slash_and_lowercases_host_only(self):
        # Path case is significant on most servers, host case is not.
        assert canonical_url("https://Example.com/Jobs/Abc/") == "https://example.com/Jobs/Abc"

    def test_keeps_meaningful_query_params_sorted(self):
        assert canonical_url("https://e.com/j?b=2&a=1") == "https://e.com/j?a=1&b=2"


class TestMakeJobId:
    def test_is_stable_across_calls(self):
        assert make_job_id("adzuna", external_id="123") == make_job_id("adzuna", external_id="123")

    def test_differs_by_source(self):
        assert make_job_id("adzuna", external_id="1") != make_job_id("remoteok", external_id="1")

    def test_external_id_takes_precedence_over_url(self):
        a = make_job_id("adzuna", external_id="1", apply_url="https://a.com/x")
        b = make_job_id("adzuna", external_id="1", apply_url="https://b.com/y")
        assert a == b

    def test_falls_back_to_canonical_url_when_no_external_id(self):
        a = make_job_id("s", apply_url="https://e.com/j?utm_source=x")
        b = make_job_id("s", apply_url="https://E.com/j/")
        assert a == b

    def test_requires_at_least_one_identifier(self):
        with pytest.raises(ValueError):
            make_job_id("adzuna")

    def test_is_short_hex(self):
        job_id = make_job_id("adzuna", external_id="1")
        assert len(job_id) == 16
        assert all(c in "0123456789abcdef" for c in job_id)


class TestPostedStore:
    def test_load_returns_empty_mapping_when_file_missing(self, tmp_path):
        assert load_posted(tmp_path / "nope.json") == {}

    def test_save_then_load_roundtrips(self, tmp_path):
        path = tmp_path / "posted.json"
        now = datetime(2026, 9, 7, tzinfo=timezone.utc)
        save_posted(path, {"abc": now.isoformat()})
        assert load_posted(path) == {"abc": now.isoformat()}

    def test_load_tolerates_corrupt_file(self, tmp_path):
        path = tmp_path / "posted.json"
        path.write_text("{not json", encoding="utf-8")
        assert load_posted(path) == {}

    def test_mark_posted_does_not_mutate_input(self):
        original = {"a": "2026-01-01T00:00:00+00:00"}
        updated = mark_posted(original, "b", datetime(2026, 9, 7, tzinfo=timezone.utc))
        assert original == {"a": "2026-01-01T00:00:00+00:00"}
        assert set(updated) == {"a", "b"}

    def test_filter_unposted_removes_known_ids(self):
        seen = make_job(source="adzuna", external_id="1")
        fresh = make_job(source="adzuna", external_id="2")
        posted = {seen.job_id: "2026-01-01T00:00:00+00:00"}
        assert filter_unposted([seen, fresh], posted) == [fresh]

    def test_filter_unposted_drops_duplicates_within_one_batch(self):
        a = make_job(source="adzuna", external_id="1")
        b = make_job(source="adzuna", external_id="1", title="Different title, same posting")
        assert filter_unposted([a, b], {}) == [a]

    def test_prune_drops_entries_older_than_cutoff(self):
        now = datetime(2026, 9, 7, tzinfo=timezone.utc)
        mapping = {
            "old": "2025-01-01T00:00:00+00:00",
            "recent": "2026-09-01T00:00:00+00:00",
            "corrupt": "not-a-date",
        }
        pruned = prune_posted(mapping, now=now, keep_days=180)
        assert set(pruned) == {"recent", "corrupt"}
