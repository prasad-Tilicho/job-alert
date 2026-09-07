from datetime import date, datetime, timezone

from jobalert.archive import ARCHIVE_LIMIT, append_published, load_archive, save_archive
from tests.factories import make_job

WHEN = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


class TestLoadArchive:
    def test_missing_file_reads_as_empty(self, tmp_path):
        assert load_archive(tmp_path / "nope.json") == []

    def test_corrupt_file_reads_as_empty(self, tmp_path):
        path = tmp_path / "published.json"
        path.write_text("[[[", encoding="utf-8")
        assert load_archive(path) == []

    def test_roundtrips(self, tmp_path):
        path = tmp_path / "published.json"
        records = append_published([], make_job(), WHEN)
        save_archive(path, records)
        assert load_archive(path) == records


class TestAppendPublished:
    def test_captures_the_fields_the_landing_page_needs(self):
        job = make_job()
        record = append_published([], job, WHEN)[0]
        assert record["job_id"] == job.job_id
        assert record["title"] == job.title
        assert record["org"] == job.org
        assert record["location"] == job.location
        assert record["apply_url"] == job.apply_url
        assert record["category"] == "GOVERNMENT"
        assert record["salary"] == job.salary
        assert record["last_date"] == "2026-10-15"
        assert record["published_at"] == WHEN.isoformat()

    def test_does_not_mutate_the_existing_archive(self):
        original = append_published([], make_job(external_id="1"), WHEN)
        append_published(original, make_job(external_id="2"), WHEN)
        assert len(original) == 1

    def test_newest_entries_come_first(self):
        records = append_published([], make_job(external_id="1"), WHEN)
        records = append_published(records, make_job(external_id="2"), WHEN)
        assert records[0]["external_id"] == "2"

    def test_republishing_the_same_job_replaces_rather_than_duplicates(self):
        job = make_job()
        records = append_published(append_published([], job, WHEN), job, WHEN)
        assert len(records) == 1

    def test_is_capped_so_the_page_and_repo_stay_small(self):
        records = []
        for index in range(ARCHIVE_LIMIT + 25):
            records = append_published(records, make_job(external_id=str(index)), WHEN)
        assert len(records) == ARCHIVE_LIMIT
        # The cap must drop the oldest, never the newest.
        assert records[0]["external_id"] == str(ARCHIVE_LIMIT + 24)

    def test_absent_optional_fields_serialise_as_null(self):
        record = append_published([], make_job(salary=None, last_date=None), WHEN)[0]
        assert record["salary"] is None
        assert record["last_date"] is None


class TestArchiveCapturesEveryPosterField:
    def test_eligibility_dates_and_description_survive_the_round_trip(self, tmp_path):
        from datetime import date as _date

        job = make_job(age_limit="18 - 32 years", application_fee="Rs 100",
                       start_date=_date(2026, 9, 2), description="Applications invited.")
        record = append_published([], job, WHEN)[0]
        assert record["age_limit"] == "18 - 32 years"
        assert record["application_fee"] == "Rs 100"
        assert record["start_date"] == "2026-09-02"
        assert record["description"] == "Applications invited."

    def test_a_job_missing_them_records_nulls_not_missing_keys(self, tmp_path):
        # A missing key breaks anything reading the archive positionally.
        record = append_published([], make_job(), WHEN)[0]
        for key in ("age_limit", "application_fee", "description", "start_date"):
            assert key in record
