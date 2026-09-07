"""Instagram content-publishing client.

Uses the Instagram API with Instagram Login (graph.instagram.com), which talks to
a professional account directly and needs no linked Facebook Page.

Publishing is deliberately three steps - create a container, wait for Instagram
to fetch the image, then publish - because Instagram downloads the image from our
URL asynchronously and publishing early fails.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, Optional, Tuple

import httpx

log = logging.getLogger(__name__)

API_VERSION = "v23.0"
GRAPH_ROOT = "https://graph.instagram.com"
GRAPH_BASE = f"{GRAPH_ROOT}/{API_VERSION}"

DEFAULT_POLL_ATTEMPTS = 20
DEFAULT_POLL_INTERVAL = 3.0
TERMINAL_ERROR_STATUSES = frozenset({"ERROR", "EXPIRED"})


class InstagramError(RuntimeError):
    """Raised when Instagram rejects a request or a container never publishes."""


def _payload(response: httpx.Response) -> Dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        data = {}
    return data if isinstance(data, dict) else {}


def _raise_for_error(response: httpx.Response, action: str) -> Dict[str, Any]:
    """Turn a Graph API error into an InstagramError carrying Meta's own message."""
    data = _payload(response)
    if response.status_code >= 400:
        message = (data.get("error") or {}).get("message") or response.text[:200]
        raise InstagramError(f"{action} failed ({response.status_code}): {message}")
    return data


class InstagramClient:
    """Publishes single-image posts to one Instagram professional account."""

    def __init__(
        self,
        client: httpx.Client,
        user_id: str,
        access_token: str,
        sleep: Optional[Callable[[float], None]] = None,
    ):
        self._client = client
        self._user_id = user_id
        self._token = access_token
        self._sleep = sleep or time.sleep

    def create_container(self, image_url: str, caption: str) -> str:
        """Ask Instagram to stage a post. Returns the creation id."""
        response = self._client.post(
            f"{GRAPH_BASE}/{self._user_id}/media",
            data={"image_url": image_url, "caption": caption, "access_token": self._token},
        )
        data = _raise_for_error(response, "creating media container")
        creation_id = data.get("id")
        if not creation_id:
            raise InstagramError(f"creating media container returned no id: {data}")
        return str(creation_id)

    def wait_for_container(
        self,
        creation_id: str,
        attempts: int = DEFAULT_POLL_ATTEMPTS,
        interval: float = DEFAULT_POLL_INTERVAL,
    ) -> None:
        """Block until Instagram has fetched the image, or raise.

        Instagram downloads the image from our public URL in the background; a
        container is only publishable once its status reaches FINISHED.
        """
        for attempt in range(attempts):
            response = self._client.get(
                f"{GRAPH_BASE}/{creation_id}",
                params={"fields": "status_code,status", "access_token": self._token},
            )
            data = _raise_for_error(response, "checking container status")
            status = str(data.get("status_code") or "").upper()
            if status == "FINISHED":
                return
            if status in TERMINAL_ERROR_STATUSES:
                raise InstagramError(
                    f"container {creation_id} reported {status}: {data.get('status') or 'no detail'}"
                )
            log.info("container %s is %s (attempt %d/%d)", creation_id, status, attempt + 1, attempts)
            self._sleep(interval)
        raise InstagramError(f"container {creation_id} never finished after {attempts} checks")

    def publish_container(self, creation_id: str) -> str:
        """Publish a finished container. Returns the published media id."""
        response = self._client.post(
            f"{GRAPH_BASE}/{self._user_id}/media_publish",
            data={"creation_id": creation_id, "access_token": self._token},
        )
        data = _raise_for_error(response, "publishing media")
        media_id = data.get("id")
        if not media_id:
            raise InstagramError(f"publishing media returned no id: {data}")
        return str(media_id)

    def publish_photo(
        self,
        image_url: str,
        caption: str,
        attempts: int = DEFAULT_POLL_ATTEMPTS,
        interval: float = DEFAULT_POLL_INTERVAL,
    ) -> str:
        """Run the full create -> wait -> publish sequence."""
        creation_id = self.create_container(image_url, caption)
        self.wait_for_container(creation_id, attempts=attempts, interval=interval)
        return self.publish_container(creation_id)


def refresh_access_token(client: httpx.Client, access_token: str) -> Tuple[str, int]:
    """Extend a long-lived token by another 60 days.

    Tokens must be at least 24 hours old to refresh and cannot be revived once
    they lapse, which is why the refresh workflow runs weekly rather than monthly.
    """
    response = client.get(
        f"{GRAPH_ROOT}/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": access_token},
    )
    data = _raise_for_error(response, "refreshing access token")
    token = data.get("access_token")
    if not token:
        raise InstagramError(f"token refresh returned no token: {data}")
    return str(token), int(data.get("expires_in") or 0)
