from datetime import date

from jobalert.validate import MAX_TITLE_LEN, partition_valid, rejection_reason
from tests.factories import make_job

TODAY = date(2026, 9, 7)


class TestRejectionReason:
    def test_accepts_a_well_formed_job(self):
        assert rejection_reason(make_job(), today=TODAY) is None

    def test_rejects_blank_title(self):
        assert rejection_reason(make_job(title="   "), today=TODAY) == "missing title"

    def test_rejects_title_without_letters(self):
        assert rejection_reason(make_job(title="--- 123 ---"), today=TODAY) == "title has no letters"

    def test_rejects_overlong_title(self):
        job = make_job(title="a" * (MAX_TITLE_LEN + 1))
        assert rejection_reason(job, today=TODAY) == "title too long"

    def test_rejects_missing_organisation(self):
        assert rejection_reason(make_job(org=""), today=TODAY) == "missing organisation"

    def test_rejects_missing_location(self):
        assert rejection_reason(make_job(location=""), today=TODAY) == "missing location"

    def test_rejects_non_https_apply_url(self):
        job = make_job(apply_url="http://example.com/job")
        assert rejection_reason(job, today=TODAY) == "apply url is not https"

    def test_rejects_malformed_apply_url(self):
        assert rejection_reason(make_job(apply_url="not a url"), today=TODAY) == "apply url is not https"

    def test_rejects_expired_deadline(self):
        job = make_job(last_date=date(2026, 9, 6))
        assert rejection_reason(job, today=TODAY) == "deadline has passed"

    def test_accepts_deadline_of_today(self):
        assert rejection_reason(make_job(last_date=TODAY), today=TODAY) is None

    def test_accepts_absent_deadline(self):
        assert rejection_reason(make_job(last_date=None), today=TODAY) is None

    def test_rejects_implausibly_distant_deadline(self):
        job = make_job(last_date=date(2030, 1, 1))
        assert rejection_reason(job, today=TODAY) == "deadline is implausibly far away"


class TestPartitionValid:
    def test_splits_and_reports_reasons(self):
        good = make_job(external_id="1")
        bad = make_job(external_id="2", title="")
        valid, rejected = partition_valid([good, bad], today=TODAY)
        assert valid == [good]
        assert rejected == [(bad, "missing title")]

    def test_preserves_input_order_of_valid_jobs(self):
        jobs = [make_job(external_id=str(i)) for i in range(5)]
        valid, rejected = partition_valid(jobs, today=TODAY)
        assert valid == jobs
        assert rejected == []
