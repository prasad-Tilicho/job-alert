from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from jobalert.models import Category
from jobalert.sources.cochin import CAREERS_URL, CochinShipyardSource, _clean_title

FIXTURE = (Path(__file__).parent / "fixtures" / "cochin_careers.html").read_text(encoding="utf-8")


@pytest.fixture
def client():
    with httpx.Client(timeout=5) as c:
        yield c


def fetch(client, html=FIXTURE):
    respx.get(CAREERS_URL).mock(return_value=httpx.Response(200, text=html))
    return CochinShipyardSource().fetch(client)


class TestCochinShipyardSource:
    @respx.mock
    def test_reads_every_opening(self, client):
        jobs = fetch(client)
        assert len(jobs) >= 5
        assert all(job.org == "Cochin Shipyard Limited" for job in jobs)

    @respx.mock
    def test_is_tagged_government_as_a_public_sector_undertaking(self, client):
        assert all(job.category is Category.GOVERNMENT for job in fetch(client))

    @respx.mock
    def test_carries_the_real_closing_date(self, client):
        # The field almost every other government portal omits.
        assert all(job.last_date is not None for job in fetch(client))
        assert date(2026, 9, 14) in {job.last_date for job in fetch(client)}

    @respx.mock
    def test_keeps_the_unit_location(self, client):
        assert {"CSL (KOCHI)", "CANSRU (ANDAMAN)"} & {job.location for job in fetch(client)}

    @respx.mock
    def test_links_are_absolute(self, client):
        assert all(job.apply_url.startswith("https://cochinshipyard.in/") for job in fetch(client))

    @respx.mock
    def test_skips_the_header_row(self, client):
        assert not any("Name of the post" in job.title for job in fetch(client))

    @respx.mock
    def test_an_empty_table_yields_nothing(self, client):
        assert fetch(client, "<table></table>") == []

    @respx.mock
    def test_raises_on_http_error(self, client):
        respx.get(CAREERS_URL).mock(return_value=httpx.Response(502))
        with pytest.raises(httpx.HTTPStatusError):
            CochinShipyardSource().fetch(client)


class TestCleanTitle:
    def test_strips_vacancy_notification_boilerplate(self):
        assert _clean_title("Vacancy Notification - Ship Draftsman Trainees for CSL") == (
            "Ship Draftsman Trainees for CSL"
        )

    def test_strips_selection_to_the_post_of(self):
        assert _clean_title(
            "Vacancy Notification - Selection to the post of Guarantee Engineer"
        ) == "Guarantee Engineer"

    def test_strips_engagement_of(self):
        assert _clean_title("Notification for Engagement of Interns").startswith("Interns")

    def test_sentence_cases_shouted_titles(self):
        result = _clean_title("NOTIFICATION FOR ENGAGEMENT OF ITI TRADE APPRENTICES")
        assert result != result.upper()
        assert "Iti Trade Apprentices" in result

    def test_leaves_an_ordinary_title_alone(self):
        assert _clean_title("Chief Executive Officer (CEO) for ISTC") == (
            "Chief Executive Officer (CEO) for ISTC"
        )
