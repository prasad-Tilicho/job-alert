"""Configuration, loaded from the environment and validated at startup.

Everything the run needs is resolved and checked in one place before any network
call happens, so a missing secret fails in the first second of a CI run with a
message naming every variable that is absent - not on the fifth step with a 400.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

DEFAULT_MAX_POSTS_PER_RUN = 3
MAX_POSTS_CEILING = 10
RAW_BASE = "https://raw.githubusercontent.com"
_TRUTHY = frozenset({"1", "true", "yes", "on"})

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ConfigError(RuntimeError):
    """Raised when the environment cannot support a run."""


@dataclass(frozen=True)
class Config:
    """Resolved settings for a single run."""

    repo: str
    ig_user_id: str = ""
    ig_access_token: str = ""
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    handle: str = "@jobalerts"
    max_posts_per_run: int = DEFAULT_MAX_POSTS_PER_RUN
    paused: bool = False
    # Some Indian government sites refuse connections from datacentre IPs. They
    # work from a residential Indian network but time out on GitHub's runners,
    # so they are opt-in rather than silently broken.
    enable_geo_restricted: bool = False
    root: Path = PROJECT_ROOT

    @property
    def out_dir(self) -> Path:
        """Where rendered posters land. Committed, and therefore publicly served."""
        return self.root / "out"

    @property
    def state_path(self) -> Path:
        return self.root / "state" / "posted.json"

    @property
    def archive_path(self) -> Path:
        """Published jobs with enough detail to rebuild the landing page."""
        return self.root / "state" / "published.json"

    @property
    def site_path(self) -> Path:
        """The page the Instagram bio links to, served by GitHub Pages from /docs."""
        return self.root / "docs" / "index.html"

    @property
    def health_path(self) -> Path:
        """Per-source liveness, so a silently broken parser becomes visible."""
        return self.root / "state" / "health.json"

    @property
    def fonts_dir(self) -> Path:
        return self.root / "assets" / "fonts"

    def raw_url(self, commit_sha: str, repo_relative_path: str) -> str:
        """Public URL for a committed file, pinned to a commit.

        Instagram fetches the image server-side, so it must be reachable without
        auth. Pinning to the SHA rather than a branch makes the URL immutable, so
        a later push cannot change what a published post points at.
        """
        return f"{RAW_BASE}/{self.repo}/{commit_sha}/{repo_relative_path}"


def _clean(env: Mapping[str, str], key: str) -> str:
    return (env.get(key) or "").strip()


def _parse_bool(value: str) -> bool:
    return value.strip().casefold() in _TRUTHY


def _parse_max_posts(value: str) -> int:
    """Clamp to a sane range; a typo here would spam followers."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MAX_POSTS_PER_RUN
    if parsed < 1:
        return DEFAULT_MAX_POSTS_PER_RUN
    return min(parsed, MAX_POSTS_CEILING)


def load_config(
    env: Optional[Mapping[str, str]] = None,
    require_instagram: bool = True,
    root: Optional[Path] = None,
) -> Config:
    """Build a :class:`Config`, raising :class:`ConfigError` listing all problems.

    ``require_instagram`` is False for dry runs, which render posters locally and
    never talk to Instagram.
    """
    env = os.environ if env is None else env

    required = ["GITHUB_REPOSITORY"]
    if require_instagram:
        required += ["IG_USER_ID", "IG_ACCESS_TOKEN"]

    missing = [key for key in required if not _clean(env, key)]
    if missing:
        raise ConfigError(
            "missing required environment variable(s): "
            + ", ".join(sorted(missing))
            + ". Set them as repository secrets."
        )

    raw_max = _clean(env, "MAX_POSTS_PER_RUN")
    return Config(
        repo=_clean(env, "GITHUB_REPOSITORY"),
        ig_user_id=_clean(env, "IG_USER_ID"),
        ig_access_token=_clean(env, "IG_ACCESS_TOKEN"),
        adzuna_app_id=_clean(env, "ADZUNA_APP_ID"),
        adzuna_app_key=_clean(env, "ADZUNA_APP_KEY"),
        handle=_clean(env, "IG_HANDLE") or "@jobalerts",
        max_posts_per_run=_parse_max_posts(raw_max) if raw_max else DEFAULT_MAX_POSTS_PER_RUN,
        paused=_parse_bool(_clean(env, "PAUSED")),
        enable_geo_restricted=_parse_bool(_clean(env, "ENABLE_GEO_RESTRICTED")),
        root=root or PROJECT_ROOT,
    )
