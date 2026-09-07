import json
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from jobalert.models import Category
from jobalert.sources.ssc import ALL_EXAMS_URL, LIVE_EXAMS_URL, SscSource

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def client():
    with httpx.Client(timeout=5) as c:
        yield c


def mock_ssc(live=None, all_exams=None):
    respx.get(LIVE_EXAMS_URL).mock(
        return_value=httpx.Response(200, json=live or fixture("ssc_live.json"))
    )
    respx.get(ALL_EXAMS_URL).mock(
        return_value=httpx.Response(200, json=all_exams or fixture("ssc_all.json"))
    )


class TestSscSource:
    @respx.mock
    def test_every_exam_is_tagged_as_government(self, client):
        mock_ssc()
        jobs = SscSource().fetch(client)
        assert jobs
        assert all(job.category is Category.GOVERNMENT for job in jobs)
        assert all(job.org == "Staff Selection Commission" for job in jobs)

    @respx.mock
    def test_carries_the_real_application_deadline(self, client):
        # This is the whole point of the source: an authoritative closing date.
        mock_ssc()
        job = {j.external_id: j for j in SscSource().fetch(client)}["kuy5m41umlgmfbf0"]
        assert job.last_date == date(2026, 9, 22)
        assert job.posted_at == date(2026, 9, 2)

    @respx.mock
    def test_uses_the_exam_description_as_the_title(self, client):
        mock_ssc()
        job = {j.external_id: j for j in SscSource().fetch(client)}["kuy5m41umlgmfbf0"]
        assert job.title == "Junior Engineer Examination, 2026"

    @respx.mock
    def test_links_to_the_matching_application_form(self, client):
        mock_ssc()
        jobs = {j.external_id: j for j in SscSource().fetch(client)}
        assert jobs["kuy5m41umlgmfbf0"].apply_url == "https://ssc.gov.in/ApplicationForm/jemecform"
        assert jobs["closed1"].apply_url == "https://ssc.gov.in/ApplicationForm/cglform"

    @respx.mock
    def test_falls_back_to_the_notice_board_when_no_form_is_known(self, client):
        mock_ssc(all_exams={"data": []})
        job = SscSource().fetch(client)[0]
        assert job.apply_url == "https://ssc.gov.in/notice-board"

    @respx.mock
    def test_skips_inactive_exams(self, client):
        mock_ssc()
        assert "inactive1" not in {j.external_id for j in SscSource().fetch(client)}

    @respx.mock
    def test_skips_exams_with_no_closing_date(self, client):
        # Without a deadline the listing cannot tell anyone when to apply by.
        mock_ssc()
        assert "nodate1" not in {j.external_id for j in SscSource().fetch(client)}

    @respx.mock
    def test_is_nationwide(self, client):
        mock_ssc()
        assert SscSource().fetch(client)[0].location == "All India"

    @respx.mock
    def test_never_claims_a_salary_it_does_not_know(self, client):
        mock_ssc()
        assert all(job.salary is None for job in SscSource().fetch(client))

    @respx.mock
    def test_raises_on_http_error_so_the_registry_can_isolate_it(self, client):
        respx.get(LIVE_EXAMS_URL).mock(return_value=httpx.Response(503))
        respx.get(ALL_EXAMS_URL).mock(return_value=httpx.Response(200, json={"data": []}))
        with pytest.raises(httpx.HTTPStatusError):
            SscSource().fetch(client)

    @respx.mock
    def test_a_missing_exam_catalogue_does_not_lose_the_listings(self, client):
        # The catalogue only supplies the form URL; losing it must not lose jobs.
        respx.get(LIVE_EXAMS_URL).mock(
            return_value=httpx.Response(200, json=fixture("ssc_live.json"))
        )
        respx.get(ALL_EXAMS_URL).mock(return_value=httpx.Response(500))
        assert SscSource().fetch(client)


class TestEligibilityFields:
    @respx.mock
    def test_publishes_the_age_limit_it_does_have(self, client):
        # SSC publishes no pay figure, so eligibility is the useful fact here.
        mock_ssc()
        job = {j.external_id: j for j in SscSource().fetch(client)}["kuy5m41umlgmfbf0"]
        assert job.age_limit == "18 - 32 years"

    @respx.mock
    def test_publishes_the_application_fee(self, client):
        mock_ssc()
        job = {j.external_id: j for j in SscSource().fetch(client)}["kuy5m41umlgmfbf0"]
        assert job.application_fee == "Rs 100"

    def test_age_formats_cope_with_a_missing_bound(self):
        from jobalert.sources.ssc import _age_limit

        assert _age_limit({"minAge": 18, "maxAge": 32}) == "18 - 32 years"
        assert _age_limit({"maxAge": 30}) == "Up to 30 years"
        assert _age_limit({"minAge": 21}) == "21 years and above"
        assert _age_limit({}) is None

    def test_a_zero_or_missing_fee_is_handled(self):
        from jobalert.sources.ssc import _fee

        assert _fee({"fee": 100}) == "Rs 100"
        assert _fee({"fee": 0}) == "Rs 0"
        assert _fee({}) is None
        assert _fee({"fee": "abc"}) is None
