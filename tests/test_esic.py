from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from jobalert.models import Category
from jobalert.sources.esic import LISTING_URL, PAGE_URL, EsicSource, clean_subject

FIXTURE = (Path(__file__).parent / "fixtures" / "esic_page1.html").read_text(encoding="utf-8")
EMPTY = "<html><body><table></table></body></html>"


@pytest.fixture
def client():
    with httpx.Client(timeout=5) as c:
        yield c


def mock_pages(page1=FIXTURE, others=EMPTY):
    respx.get(LISTING_URL).mock(return_value=httpx.Response(200, text=page1))
    for page in (2, 3):
        respx.get(PAGE_URL.format(page=page)).mock(return_value=httpx.Response(200, text=others))


class TestEsicSource:
    @respx.mock
    def test_returns_openings_tagged_government(self, client):
        mock_pages()
        jobs = EsicSource().fetch(client)
        assert jobs
        assert all(job.category is Category.GOVERNMENT for job in jobs)
        assert all(job.org == "Employees' State Insurance Corporation" for job in jobs)

    @respx.mock
    def test_excludes_results_shortlists_and_corrigenda(self, client):
        mock_pages()
        titles = " ".join(job.title.lower() for job in EsicSource().fetch(client))
        for phrase in ("result", "shortlist", "corrigendum", "addendum"):
            assert phrase not in titles

    @respx.mock
    def test_keeps_walk_in_interviews_which_are_real_openings(self, client):
        mock_pages()
        assert any("walk" in job.title.lower() for job in EsicSource().fetch(client))

    @respx.mock
    def test_a_row_without_a_date_is_still_published(self, client):
        # ESIC often files a recruitment under "Others" with no date. The opening
        # is still real, so it is kept and simply carries no deadline.
        row = (
            '<table><tr><td>1</td><td>Recruitment Branch</td>'
            '<td><a href="/attachments/x.pdf">RECRUITMENT OF ASSISTANT PROFESSORS IN ESIC</a></td>'
            '<td>2026-09-05</td><td>Others</td><td>12500/2026</td></tr></table>'
        )
        mock_pages(page1=row)
        jobs = EsicSource().fetch(client)
        assert len(jobs) == 1
        assert jobs[0].last_date is None
        assert jobs[0].posted_at == date(2026, 9, 5)

    @respx.mock
    def test_a_deadline_is_used_when_the_table_states_one(self, client):
        mock_pages()
        assert any(job.last_date is not None for job in EsicSource().fetch(client))

    @respx.mock
    def test_reads_the_interview_date_as_the_closing_date(self, client):
        mock_pages()
        assert date(2026, 9, 18) in {j.last_date for j in EsicSource().fetch(client)}

    @respx.mock
    def test_keeps_the_hospital_as_the_location(self, client):
        mock_pages()
        assert any("Indore" in job.location for job in EsicSource().fetch(client))

    @respx.mock
    def test_follows_pagination(self, client):
        respx.get(LISTING_URL).mock(return_value=httpx.Response(200, text=FIXTURE))
        for page in (2, 3):
            respx.get(PAGE_URL.format(page=page)).mock(
                return_value=httpx.Response(200, text=FIXTURE)
            )
        one_page = len(EsicSource(pages=1).fetch(client))
        three_pages = len(EsicSource(pages=3).fetch(client))
        assert three_pages == one_page * 3

    @respx.mock
    def test_a_failing_later_page_does_not_lose_the_first(self, client):
        respx.get(LISTING_URL).mock(return_value=httpx.Response(200, text=FIXTURE))
        respx.get(PAGE_URL.format(page=2)).mock(return_value=httpx.Response(500))
        respx.get(PAGE_URL.format(page=3)).mock(return_value=httpx.Response(200, text=EMPTY))
        assert EsicSource().fetch(client)

    @respx.mock
    def test_a_failing_first_page_raises_for_the_registry(self, client):
        respx.get(LISTING_URL).mock(return_value=httpx.Response(503))
        with pytest.raises(httpx.HTTPStatusError):
            EsicSource().fetch(client)

    @respx.mock
    def test_links_are_absolute(self, client):
        mock_pages()
        assert all(job.apply_url.startswith("https://www.esic.gov.in/")
                   for job in EsicSource().fetch(client))


class TestCleanSubject:
    def test_strips_the_pdf_size_suffix(self):
        assert clean_subject("walk in interview MO Ayurvedic- PDF size:(1.67 MB) .") == (
            "walk in interview MO Ayurvedic"
        )

    def test_softens_shouted_subjects(self):
        result = clean_subject("RECRUITMENT OF ASSISTANT PROFESSORS IN ESIC")
        assert result != result.upper()
        assert "Assistant Professors" in result

    def test_drops_regarding_uploading_preamble(self):
        assert clean_subject(
            "Regarding Uploading Advertisement No: 12 of 2026 for Recruitment of Professor"
        ).startswith("Advertisement No")

    def test_leaves_an_ordinary_subject_alone(self):
        subject = "Walk-in-interview for Recruitment of Teaching Faculty"
        assert clean_subject(subject) == subject


class TestRowsWithoutLinks:
    @respx.mock
    def test_a_row_with_nothing_to_apply_to_is_dropped(self, client):
        # No link means no way to act on the listing.
        row = (
            "<table><tr><td>1</td><td>Office</td>"
            "<td>Recruitment of Nurses</td><td>2026-09-05</td>"
            "<td>Others</td><td>1/2026</td></tr></table>"
        )
        mock_pages(page1=row)
        assert EsicSource().fetch(client) == []
