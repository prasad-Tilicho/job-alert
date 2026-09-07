"""Deleting published Instagram media.

Kept in the package (rather than as a loose script) so the request/response
handling is covered by the same tests as the publishing path.

Deletion is irreversible and Instagram offers no undo, so the caller is expected
to pass explicit media ids - there is deliberately no "delete everything" path.
"""
from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Tuple

import httpx

from jobalert.instagram import GRAPH_BASE, InstagramError, _raise_for_error

log = logging.getLogger(__name__)


def delete_media(client: httpx.Client, media_id: str, access_token: str) -> None:
    """Delete one published media item. Raises :class:`InstagramError` on failure."""
    response = client.request(
        "DELETE",
        f"{GRAPH_BASE}/{media_id}",
        params={"access_token": access_token},
    )
    data = _raise_for_error(response, f"deleting media {media_id}")
    # Meta answers {"success": true}; treat an explicit false as a failure.
    if data.get("success") is False:
        raise InstagramError(f"deleting media {media_id} reported success=false: {data}")


def delete_many(
    client: httpx.Client,
    media_ids: Iterable[str],
    access_token: str,
) -> Tuple[List[str], List[Tuple[str, str]]]:
    """Delete each id, isolating failures. Returns (deleted, [(id, error)])."""
    deleted: List[str] = []
    failed: List[Tuple[str, str]] = []
    for media_id in media_ids:
        try:
            delete_media(client, media_id, access_token)
        except Exception as exc:  # noqa: BLE001 - one bad id must not stop the rest
            log.error("could not delete %s: %s", media_id, exc)
            failed.append((media_id, str(exc)))
            continue
        log.info("deleted media %s", media_id)
        deleted.append(media_id)
    return deleted, failed


def parse_media_ids(raw: str) -> List[str]:
    """Split a comma/space/newline separated list, keeping only plausible ids."""
    tokens = [token.strip() for token in raw.replace(",", " ").split()]
    ids: List[str] = []
    for token in tokens:
        if token.isdigit():
            if token not in ids:
                ids.append(token)
        elif token:
            log.warning("ignoring %r: media ids are numeric", token)
    return ids
