#!/usr/bin/env python3
"""Diagnose and obtain a 60-day Instagram access token.

Runs three checks in order so a failure points at one cause instead of several:

  1. Is the token valid at all?  (GET /me)
  2. Can it be exchanged?       (short-lived -> long-lived)
  3. Is it already long-lived?  (refresh instead of exchange)

Values are read with getpass and sent in the request body/query only, so nothing
reaches your shell history.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from getpass import getpass
from typing import Any, Dict, Tuple

GRAPH = "https://graph.instagram.com"
TIMEOUT = 30


def call(path: str, params: Dict[str, str]) -> Tuple[int, Dict[str, Any]]:
    url = f"{GRAPH}/{path}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": "jobalert-setup/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        try:
            return exc.code, json.loads(body)
        except ValueError:
            return exc.code, {"error": {"message": body[:300]}}
    except urllib.error.URLError as exc:
        sys.exit(f"Network error reaching Instagram: {exc.reason}")


def message_of(payload: Dict[str, Any]) -> str:
    return (payload.get("error") or {}).get("message") or json.dumps(payload)[:300]


def report_success(token: str, expires_in: int, how: str) -> None:
    print(f"\nSUCCESS via {how} - valid for about {int(expires_in) // 86400} days.\n")
    print("Add this as the IG_ACCESS_TOKEN repository secret:\n")
    print(token)
    print("\n  gh secret set IG_ACCESS_TOKEN --repo prasad-Tilicho/job-alert")


def main() -> int:
    print("Instagram token diagnostic\n")
    app_secret = "".join(getpass("Instagram app secret: ").split())
    token = "".join(getpass("Access token: ").split())
    print(f"\napp secret: {len(app_secret)} chars (expected 32)")
    print(f"token:      {len(token)} chars\n")

    # --- 1. Is the token valid at all? ------------------------------------
    print("[1/3] Checking whether the token works ...")
    status, me = call("me", {"fields": "id,username,account_type", "access_token": token})
    if status != 200:
        print(f"      FAILED: {message_of(me)}\n")
        print("The token itself is not valid. Most likely causes:\n")
        print("  * It was copied incompletely - the dashboard box scrolls, so it is")
        print("    easy to grab only the visible part. Select all of it.")
        print("  * The Instagram Tester invite was never accepted. Check")
        print("    Instagram -> Settings -> Apps and websites -> Tester invites.")
        print("  * The token was revoked by an app-secret reset. Generate a new one.")
        return 1

    print(f"      OK - account @{me.get('username')} (id {me.get('id')},"
          f" {me.get('account_type')})")
    print(f"\n      Confirm this id matches your IG_USER_ID secret: {me.get('id')}\n")

    # --- 2. Exchange (works only on short-lived tokens) --------------------
    print("[2/3] Trying short-lived -> long-lived exchange ...")
    status, data = call(
        "access_token",
        {
            "grant_type": "ig_exchange_token",
            "client_secret": app_secret,
            "access_token": token,
        },
    )
    if status == 200 and "access_token" in data:
        report_success(data["access_token"], data.get("expires_in", 0), "exchange")
        return 0
    exchange_error = message_of(data)
    print(f"      not exchangeable: {exchange_error}")

    # --- 3. Maybe it is already long-lived --------------------------------
    print("\n[3/3] Trying refresh (works if the token is already long-lived) ...")
    status, data = call(
        "refresh_access_token",
        {"grant_type": "ig_refresh_token", "access_token": token},
    )
    if status == 200 and "access_token" in data:
        print("\n      The dashboard already gave you a LONG-LIVED token, which is why")
        print("      the exchange refused it. No exchange was needed.")
        report_success(data["access_token"], data.get("expires_in", 0), "refresh")
        return 0

    print(f"      refresh failed: {message_of(data)}\n")
    if "client secret" in exchange_error.lower():
        print("The app secret is wrong. Copy it from Use cases -> API setup with")
        print("Instagram login (NOT App settings -> Basic).")
    else:
        print("The token is valid for reading but neither exchangeable nor refreshable.")
        print("This usually means it is a long-lived token less than 24 hours old -")
        print("refresh requires 24h. In that case the token you already hold IS the")
        print("60-day one: store it directly as IG_ACCESS_TOKEN.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
