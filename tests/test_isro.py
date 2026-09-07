from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from jobalert.models import Category
from jobalert.sources.isro import CAREERS_URL, IsroSource

FIXTURE = (Path(__file__).parent / "fixtures" / "isro_careers.html").read_text(encoding="utf-8")


@pytest.fixture
def client():
    with httpx.Client(timeout=5) as c:
        yield c


def fetch(client, html=FIXTURE):
    respx.get(CAREERS_URL).mock(return_value=httpx.Response(200, text=html))
    return IsroSource().fetch(client)


class TestIsroSource:
    @respx.mock
    def test_returns_only_open_vacancies(self, client):
        jobs = fetch(client)
        assert jobs
        assert all(job.category is Category.GOVERNMENT for job in jobs)

    @respx.mock
    def test_never_publishes_a_corrigendum_as_a_vacancy(self, client):
        # These say "Recruitment to the post of" but amend an existing notice.
        assert not any("corrigendum" in job.title.lower() for job in fetch(client))

    @respx.mock
    def test_never_publishes_results_or_interview_schedules(self, client):
        titles = " ".join(job.title.lower() for job in fetch(client))
        for phrase in ("selection panel", "schedule of interview"):
            assert phrase not in titles

    @respx.mock
    def test_reduces_a_notice_line_to_the_role(self, client):
        # The raw line is "Advt No. ... dated 27-08-2026 - Inviting applications
        # for the post of Scientist/Engineer 'SC'".
        titles = [job.title for job in fetch(client)]
        assert any(t.startswith("Scientist/Engineer") for t in titles)
        assert not any(t.lower().startswith("advt") for t in titles)

    @respx.mock
    def test_reads_the_advertisement_date(self, client):
        assert any(job.posted_at == date(2026, 8, 27) for job in fetch(client))

    @respx.mock
    def test_links_are_absolute(self, client):
        assert all(job.apply_url.startswith("https://www.isro.gov.in/") for job in fetch(client))

    @respx.mock
    def test_claims_no_deadline_it_cannot_see(self, client):
        # Closing dates are inside the linked PDF, not on the listing page.
        assert all(job.last_date is None for job in fetch(client))

    @respx.mock
    def test_rows_without_a_link_are_skipped(self, client):
        html = "<table><tr><td>Inviting applications for the post of Engineer</td></tr></table>"
        assert fetch(client, html) == []

    @respx.mock
    def test_an_empty_page_yields_nothing_rather_than_raising(self, client):
        assert fetch(client, "<html><body></body></html>") == []

    @respx.mock
    def test_raises_on_http_error(self, client):
        respx.get(CAREERS_URL).mock(return_value=httpx.Response(503))
        with pytest.raises(httpx.HTTPStatusError):
            IsroSource().fetch(client)
