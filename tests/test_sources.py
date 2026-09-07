import json
from pathlib import Path

import httpx
import pytest
import respx

from jobalert.models import Category
from jobalert.sources.adzuna import AdzunaSource
from jobalert.sources.arbeitnow import ArbeitnowSource
from jobalert.sources.registry import fetch_all
from jobalert.sources.remoteok import RemoteOkSource

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def client():
    with httpx.Client(timeout=5) as c:
        yield c


class TestAdzunaSource:
    @respx.mock
    def test_maps_fields_and_skips_unusable_rows(self, client):
        respx.get(url__startswith="https://api.adzuna.com/v1/api/jobs/in/search/").mock(
            return_value=httpx.Response(200, json=fixture("adzuna.json"))
        )
        jobs = AdzunaSource(app_id="id", app_key="key").fetch(client)

        # The row with no company is dropped at the source; it could never render.
        assert len(jobs) == 3
        first = jobs[0]
        assert first.title == "Junior Engineer (Civil) - Recruitment 2026"
        assert first.org == "Staff Selection Commission"
        assert first.location == "New Delhi, Delhi"
        assert first.external_id == "4567890123"
        assert first.apply_url.startswith("https://www.adzuna.in/land/ad/4567890123")

    @respx.mock
    def test_tags_government_employers(self, client):
        respx.get(url__startswith="https://api.adzuna.com").mock(
            return_value=httpx.Response(200, json=fixture("adzuna.json"))
        )
        jobs = {j.external_id: j for j in AdzunaSource(app_id="id", app_key="key").fetch(client)}
        assert jobs["4567890123"].category is Category.GOVERNMENT
        assert jobs["4567890125"].category is Category.GOVERNMENT
        assert jobs["4567890124"].category is Category.PRIVATE

    @respx.mock
    def test_shows_real_salaries_but_never_predicted_ones(self, client):
        respx.get(url__startswith="https://api.adzuna.com").mock(
            return_value=httpx.Response(200, json=fixture("adzuna.json"))
        )
        jobs = {j.external_id: j for j in AdzunaSource(app_id="id", app_key="key").fetch(client)}
        assert jobs["4567890123"].salary == "Rs 4.4L - 14.2L per year"
        # salary_is_predicted == "1": Adzuna guessed it, so we must not state it as fact.
        assert jobs["4567890124"].salary is None
        assert jobs["4567890125"].salary is None

    @respx.mock
    def test_sends_credentials_and_india_country_path(self, client):
        route = respx.get(url__startswith="https://api.adzuna.com").mock(
            return_value=httpx.Response(200, json={"results": []})
        )
        AdzunaSource(app_id="the-id", app_key="the-key").fetch(client)
        request = route.calls[0].request
        assert "/jobs/in/search/1" in str(request.url)
        assert request.url.params["app_id"] == "the-id"
        assert request.url.params["app_key"] == "the-key"

    @respx.mock
    def test_raises_on_http_error(self, client):
        respx.get(url__startswith="https://api.adzuna.com").mock(
            return_value=httpx.Response(401, json={"error": "bad key"})
        )
        with pytest.raises(httpx.HTTPStatusError):
            AdzunaSource(app_id="id", app_key="key").fetch(client)


class TestArbeitnowSource:
    @respx.mock
    def test_maps_fields_and_drops_rows_without_a_url(self, client):
        respx.get(url__startswith="https://www.arbeitnow.com/api/job-board-api").mock(
            return_value=httpx.Response(200, json=fixture("arbeitnow.json"))
        )
        jobs = ArbeitnowSource().fetch(client)
        assert len(jobs) == 1
        assert jobs[0].title == "Senior Python Engineer"
        assert jobs[0].org == "Beispiel GmbH"
        assert jobs[0].external_id == "senior-python-engineer-berlin-123456"
        assert jobs[0].category is Category.PRIVATE

    @respx.mock
    def test_marks_remote_roles_in_the_location(self, client):
        respx.get(url__startswith="https://www.arbeitnow.com").mock(
            return_value=httpx.Response(200, json=fixture("arbeitnow.json"))
        )
        assert ArbeitnowSource().fetch(client)[0].location == "Berlin (Remote)"


class TestRemoteOkSource:
    @respx.mock
    def test_skips_the_legal_notice_row_and_incomplete_rows(self, client):
        respx.get(url__startswith="https://remoteok.com/api").mock(
            return_value=httpx.Response(200, json=fixture("remoteok.json"))
        )
        jobs = RemoteOkSource().fetch(client)
        assert len(jobs) == 1
        assert jobs[0].title == "Full Stack Developer"
        assert jobs[0].org == "Acme Remote"
        assert jobs[0].salary == "$60,000 - $90,000 per year"


class TestFetchAll:
    def test_one_failing_source_does_not_stop_the_others(self, client):
        class Boom:
            name = "boom"

            def fetch(self, client):
                raise httpx.ConnectError("down")

        class Fine:
            name = "fine"

            def fetch(self, client):
                from tests.factories import make_job

                return [make_job(source="fine", external_id="1")]

        jobs = fetch_all([Boom(), Fine()], client)
        assert [j.source for j in jobs] == ["fine"]

    def test_returns_empty_list_when_every_source_fails(self, client):
        class Boom:
            name = "boom"

            def fetch(self, client):
                raise ValueError("nope")

        assert fetch_all([Boom()], client) == []


class TestBuildSources:
    def test_includes_adzuna_only_when_credentials_are_present(self, tmp_path):
        from jobalert.config import Config
        from jobalert.sources.registry import build_sources

        with_keys = build_sources(Config(repo="a/b", adzuna_app_id="x", adzuna_app_key="y"))
        without = build_sources(Config(repo="a/b"))
        assert "adzuna" in [s.name for s in with_keys]
        assert "adzuna" not in [s.name for s in without]

    def test_keyless_sources_are_always_available(self):
        from jobalert.config import Config
        from jobalert.sources.registry import build_sources

        names = [s.name for s in build_sources(Config(repo="a/b"))]
        assert {"arbeitnow", "remoteok"} <= set(names)
