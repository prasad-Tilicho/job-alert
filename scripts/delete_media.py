#!/usr/bin/env python3
"""Delete published Instagram posts by media id.

Run by the "Delete Instagram posts" workflow, where IG_ACCESS_TOKEN is available.
Deletion is irreversible, so ids must be listed explicitly - there is no
"delete everything" option.

Env:
  IG_ACCESS_TOKEN  required
  MEDIA_IDS        comma/space separated media ids
  CONFIRM          must equal DELETE
"""
from __future__ import annotations

import logging
import os
import sys

import httpx

from jobalert.delete import delete_many, parse_media_ids

CONFIRM_PHRASE = "DELETE"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    token = (os.environ.get("IG_ACCESS_TOKEN") or "").strip()
    raw_ids = os.environ.get("MEDIA_IDS") or ""
    confirm = (os.environ.get("CONFIRM") or "").strip()

    if not token:
        print("IG_ACCESS_TOKEN is not set", file=sys.stderr)
        return 2
    if confirm != CONFIRM_PHRASE:
        print(f"refusing to delete: CONFIRM must be exactly {CONFIRM_PHRASE!r}", file=sys.stderr)
        return 2

    media_ids = parse_media_ids(raw_ids)
    if not media_ids:
        print("no valid media ids given (they are numeric, e.g. 18020946674927238)", file=sys.stderr)
        return 2

    print(f"Deleting {len(media_ids)} post(s): {', '.join(media_ids)}")
    with httpx.Client(timeout=30, headers={"User-Agent": "jobalert/0.1"}) as client:
        deleted, failed = delete_many(client, media_ids, token)

    for media_id in deleted:
        print(f"  deleted {media_id}")
    for media_id, error in failed:
        print(f"  FAILED  {media_id}: {error}")

    if failed and not deleted:
        print(
            "\nNothing was deleted. If every id reports 'Unsupported request', this app's\n"
            "Instagram Login permissions do not cover deletion - remove the posts in the\n"
            "Instagram app instead.",
            file=sys.stderr,
        )
    print(f"\n{len(deleted)} deleted, {len(failed)} failed.")
    print("Note: state/posted.json is unchanged, so deleted jobs will not be reposted.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
