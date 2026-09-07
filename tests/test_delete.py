import httpx
import pytest
import respx

from jobalert.delete import delete_many, delete_media, parse_media_ids
from jobalert.instagram import GRAPH_BASE, InstagramError

TOKEN = "IGQV-token"


@pytest.fixture
def client():
    with httpx.Client(timeout=5) as c:
        yield c


class TestParseMediaIds:
    def test_accepts_commas_spaces_and_newlines(self):
        assert parse_media_ids("111, 222\n333  444") == ["111", "222", "333", "444"]

    def test_drops_duplicates_preserving_order(self):
        assert parse_media_ids("111 222 111") == ["111", "222"]

    def test_ignores_anything_that_is_not_a_media_id(self):
        # Pasting a post URL is the obvious mistake; it must not become an id.
        assert parse_media_ids("https://instagram.com/p/abc 999") == ["999"]

    def test_empty_input_yields_nothing(self):
        assert parse_media_ids("   ") == []


class TestDeleteMedia:
    @respx.mock
    def test_issues_a_delete_with_the_token(self, client):
        route = respx.delete(f"{GRAPH_BASE}/123").mock(
            return_value=httpx.Response(200, json={"success": True})
        )
        delete_media(client, "123", TOKEN)
        assert route.calls[0].request.url.params["access_token"] == TOKEN

    @respx.mock
    def test_raises_with_metas_message(self, client):
        respx.delete(f"{GRAPH_BASE}/123").mock(
            return_value=httpx.Response(400, json={"error": {"message": "Unsupported request"}})
        )
        with pytest.raises(InstagramError, match="Unsupported request"):
            delete_media(client, "123", TOKEN)

    @respx.mock
    def test_treats_an_explicit_failure_as_an_error(self, client):
        respx.delete(f"{GRAPH_BASE}/123").mock(
            return_value=httpx.Response(200, json={"success": False})
        )
        with pytest.raises(InstagramError):
            delete_media(client, "123", TOKEN)


class TestDeleteMany:
    @respx.mock
    def test_one_failure_does_not_stop_the_others(self, client):
        respx.delete(f"{GRAPH_BASE}/111").mock(return_value=httpx.Response(200, json={"success": True}))
        respx.delete(f"{GRAPH_BASE}/222").mock(
            return_value=httpx.Response(400, json={"error": {"message": "nope"}})
        )
        respx.delete(f"{GRAPH_BASE}/333").mock(return_value=httpx.Response(200, json={"success": True}))

        deleted, failed = delete_many(client, ["111", "222", "333"], TOKEN)
        assert deleted == ["111", "333"]
        assert [i for i, _ in failed] == ["222"]

    @respx.mock
    def test_reports_nothing_for_an_empty_list(self, client):
        assert delete_many(client, [], TOKEN) == ([], [])
