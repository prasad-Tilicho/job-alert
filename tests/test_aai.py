from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from jobalert.models import Category
from jobalert.sources.aai import RECRUITMENT_URL, AaiSource

FIXTURE = (Path(__file__).parent / "fixtures" / "aai_recruitment.html").read_text(encoding="utf-8")
# The fixture's newest notice is dated 07-09-2026.
TODAY = date(2026, 9, 7)


@pytest.fixture
def client():
    with httpx.Client(timeout=5) as c:
        yield c


def fetch(client, html=FIXTURE, today=TODAY):
    respx.get(RECRUITMENT_URL).mock(return_value=httpx.Response(200, text=html))
    return AaiSource().fetch(client, today=today)


class TestAaiSource:
    @respx.mock
    def test_returns_recent_notices_tagged_government(self, client):
        jobs = fetch(client)
        assert jobs
        assert all(job.category is Category.GOVERNMENT for job in jobs)
        assert all(job.org == "Airports Authority of India" for job in jobs)

    @respx.mock
    def test_captures_the_number_of_posts(self, client):
        # The field no other source publishes.
        assert any(job.vacancies for job in fetch(client))

    @respx.mock
    def test_drops_notices_older_than_the_window(self, client):
        # The page keeps 2025 notices alongside current ones; presenting a closed
        # recruitment as open wastes an application.
        jobs = fetch(client)
        assert all(job.posted_at >= date(2026, 7, 24) for job in jobs)
        assert not any(job.posted_at.year == 2025 for job in jobs)

    @respx.mock
    def test_an_older_today_widens_nothing_retroactively(self, client):
        # Same page a year later: everything is stale, so nothing is returned.
        assert fetch(client, today=date(2027, 9, 7)) == []

    @respx.mock
    def test_links_point_at_the_release_page(self, client):
        assert all("/recruitment/release/" in job.apply_url for job in fetch(client))
        assert all(job.apply_url.startswith("https://www.aai.aero/") for job in fetch(client))

    @respx.mock
    def test_ignores_the_header_and_its_sort_links(self, client):
        assert not any("Exam Name" in job.title for job in fetch(client))

    @respx.mock
    def test_skips_results_and_corrigenda(self, client):
        html = (
            '<table><tr><td>RESULT of written exam</td><td>HR</td><td>5</td>'
            '<td>07-09-2026</td><td><a href="/en/recruitment/release/1">x</a></td></tr></table>'
        )
        assert fetch(client, html) == []

    @respx.mock
    def test_sentence_cases_shouted_titles(self, client):
        titles = [job.title for job in fetch(client)]
        assert not any(t.isupper() and len(t) > 12 for t in titles)

    @respx.mock
    def test_an_empty_table_yields_nothing(self, client):
        assert fetch(client, "<table></table>") == []

    @respx.mock
    def test_raises_on_http_error(self, client):
        respx.get(RECRUITMENT_URL).mock(return_value=httpx.Response(500))
        with pytest.raises(httpx.HTTPStatusError):
            AaiSource().fetch(client)
