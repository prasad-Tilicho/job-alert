#!/usr/bin/env python3
"""Refresh the Instagram long-lived token and store it back as a repo secret.

Instagram's long-lived tokens last 60 days and cannot be revived once they lapse,
so this runs weekly. The new token is written straight back into the repository
secret the publishing workflow reads, which is why it needs a PAT with
``Secrets: write`` - GITHUB_TOKEN cannot write secrets.

The token is never printed: it goes from Instagram into a sealed box and then to
the GitHub API, so it cannot leak into workflow logs.
"""
from __future__ import annotations

import os
import sys
from base64 import b64encode

import httpx
from nacl import encoding, public

from jobalert.instagram import InstagramError, refresh_access_token

SECRET_NAME = "IG_ACCESS_TOKEN"
GITHUB_API = "https://api.github.com"
API_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def seal(public_key_b64: str, secret_value: str) -> str:
    """Encrypt a secret with the repository's public key, as GitHub requires."""
    key = public.PublicKey(public_key_b64.encode("utf-8"), encoding.Base64Encoder())
    sealed = public.SealedBox(key).encrypt(secret_value.encode("utf-8"))
    return b64encode(sealed).decode("utf-8")


def store_secret(client: httpx.Client, repo: str, pat: str, name: str, value: str) -> None:
    auth = {**API_HEADERS, "Authorization": f"Bearer {pat}"}

    key_response = client.get(f"{GITHUB_API}/repos/{repo}/actions/secrets/public-key", headers=auth)
    key_response.raise_for_status()
    key = key_response.json()

    put_response = client.put(
        f"{GITHUB_API}/repos/{repo}/actions/secrets/{name}",
        headers=auth,
        json={"encrypted_value": seal(key["key"], value), "key_id": key["key_id"]},
    )
    put_response.raise_for_status()


def main() -> int:
    token = (os.environ.get("IG_ACCESS_TOKEN") or "").strip()
    pat = (os.environ.get("GH_PAT") or "").strip()
    repo = (os.environ.get("GITHUB_REPOSITORY") or "").strip()

    missing = [
        name
        for name, value in (("IG_ACCESS_TOKEN", token), ("GH_PAT", pat), ("GITHUB_REPOSITORY", repo))
        if not value
    ]
    if missing:
        print(f"missing environment variable(s): {', '.join(missing)}", file=sys.stderr)
        return 2

    with httpx.Client(timeout=30) as client:
        try:
            new_token, expires_in = refresh_access_token(client, token)
        except InstagramError as exc:
            print(f"token refresh failed: {exc}", file=sys.stderr)
            print(
                "If the token has already lapsed it cannot be refreshed - generate a new "
                "long-lived token in the Meta app dashboard and update the secret by hand.",
                file=sys.stderr,
            )
            return 1

        store_secret(client, repo, pat, SECRET_NAME, new_token)

    print(f"{SECRET_NAME} refreshed; valid for about {expires_in // 86400} more days")
    return 0


if __name__ == "__main__":
    sys.exit(main())
