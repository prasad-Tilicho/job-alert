import httpx
import pytest
import respx

from jobalert.instagram import GRAPH_BASE, InstagramClient, InstagramError, refresh_access_token

USER_ID = "17841400000000000"
TOKEN = "IGQV-token"
IMAGE_URL = "https://raw.githubusercontent.com/u/r/sha/out/a.jpg"


@pytest.fixture
def client():
    with httpx.Client(timeout=5) as c:
        yield c


@pytest.fixture
def ig(client):
    # sleep is injected so polling tests do not actually wait.
    return InstagramClient(client, user_id=USER_ID, access_token=TOKEN, sleep=lambda _: None)


class TestCreateContainer:
    @respx.mock
    def test_posts_the_image_url_and_caption(self, ig):
        route = respx.post(f"{GRAPH_BASE}/{USER_ID}/media").mock(
            return_value=httpx.Response(200, json={"id": "1789"})
        )
        assert ig.create_container(IMAGE_URL, "hello") == "1789"
        sent = dict(httpx.QueryParams(route.calls[0].request.content.decode()))
        assert sent["image_url"] == IMAGE_URL
        assert sent["caption"] == "hello"
        assert sent["access_token"] == TOKEN

    @respx.mock
    def test_raises_when_instagram_rejects_the_container(self, ig):
        respx.post(f"{GRAPH_BASE}/{USER_ID}/media").mock(
            return_value=httpx.Response(400, json={"error": {"message": "bad image"}})
        )
        with pytest.raises(InstagramError, match="bad image"):
            ig.create_container(IMAGE_URL, "hello")

    @respx.mock
    def test_raises_when_the_response_has_no_id(self, ig):
        respx.post(f"{GRAPH_BASE}/{USER_ID}/media").mock(return_value=httpx.Response(200, json={}))
        with pytest.raises(InstagramError):
            ig.create_container(IMAGE_URL, "hello")


class TestWaitForContainer:
    @respx.mock
    def test_polls_until_the_container_is_finished(self, ig):
        respx.get(f"{GRAPH_BASE}/1789").mock(
            side_effect=[
                httpx.Response(200, json={"status_code": "IN_PROGRESS"}),
                httpx.Response(200, json={"status_code": "IN_PROGRESS"}),
                httpx.Response(200, json={"status_code": "FINISHED"}),
            ]
        )
        ig.wait_for_container("1789")

    @respx.mock
    def test_raises_immediately_on_an_error_status(self, ig):
        respx.get(f"{GRAPH_BASE}/1789").mock(
            return_value=httpx.Response(200, json={"status_code": "ERROR", "status": "download failed"})
        )
        with pytest.raises(InstagramError, match="ERROR"):
            ig.wait_for_container("1789")

    @respx.mock
    def test_gives_up_after_the_attempt_budget(self, ig):
        respx.get(f"{GRAPH_BASE}/1789").mock(
            return_value=httpx.Response(200, json={"status_code": "IN_PROGRESS"})
        )
        with pytest.raises(InstagramError, match="never finished"):
            ig.wait_for_container("1789", attempts=3)


class TestPublish:
    @respx.mock
    def test_publishes_the_container_and_returns_the_media_id(self, ig):
        route = respx.post(f"{GRAPH_BASE}/{USER_ID}/media_publish").mock(
            return_value=httpx.Response(200, json={"id": "media-42"})
        )
        assert ig.publish_container("1789") == "media-42"
        sent = dict(httpx.QueryParams(route.calls[0].request.content.decode()))
        assert sent["creation_id"] == "1789"

    @respx.mock
    def test_publish_photo_runs_create_poll_publish_in_order(self, ig):
        calls = []
        respx.post(f"{GRAPH_BASE}/{USER_ID}/media").mock(
            side_effect=lambda request: calls.append("create") or httpx.Response(200, json={"id": "c1"})
        )
        respx.get(f"{GRAPH_BASE}/c1").mock(
            side_effect=lambda request: calls.append("poll")
            or httpx.Response(200, json={"status_code": "FINISHED"})
        )
        respx.post(f"{GRAPH_BASE}/{USER_ID}/media_publish").mock(
            side_effect=lambda request: calls.append("publish")
            or httpx.Response(200, json={"id": "m1"})
        )
        assert ig.publish_photo(IMAGE_URL, "caption") == "m1"
        assert calls == ["create", "poll", "publish"]

    @respx.mock
    def test_a_container_that_errors_never_reaches_publish(self, ig):
        respx.post(f"{GRAPH_BASE}/{USER_ID}/media").mock(
            return_value=httpx.Response(200, json={"id": "c1"})
        )
        respx.get(f"{GRAPH_BASE}/c1").mock(
            return_value=httpx.Response(200, json={"status_code": "ERROR"})
        )
        publish = respx.post(f"{GRAPH_BASE}/{USER_ID}/media_publish").mock(
            return_value=httpx.Response(200, json={"id": "m1"})
        )
        with pytest.raises(InstagramError):
            ig.publish_photo(IMAGE_URL, "caption")
        assert not publish.called


class TestRefreshAccessToken:
    @respx.mock
    def test_returns_the_new_token_and_lifetime(self, client):
        respx.get("https://graph.instagram.com/refresh_access_token").mock(
            return_value=httpx.Response(200, json={"access_token": "new-token", "expires_in": 5183944})
        )
        token, expires_in = refresh_access_token(client, "old-token")
        assert token == "new-token"
        assert expires_in == 5183944

    @respx.mock
    def test_raises_when_the_token_is_already_dead(self, client):
        respx.get("https://graph.instagram.com/refresh_access_token").mock(
            return_value=httpx.Response(400, json={"error": {"message": "Session expired"}})
        )
        with pytest.raises(InstagramError, match="Session expired"):
            refresh_access_token(client, "old-token")
