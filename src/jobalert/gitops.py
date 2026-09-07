"""Thin wrapper over the git CLI.

The repository doubles as the image host: a poster is only reachable by Instagram
once it is committed and pushed, so committing is part of the publish pipeline
rather than a housekeeping afterthought.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import List, Optional, Sequence

log = logging.getLogger(__name__)

DEFAULT_AUTHOR_NAME = "job-alert-bot"
DEFAULT_AUTHOR_EMAIL = "job-alert-bot@users.noreply.github.com"


class GitError(RuntimeError):
    """Raised when a git command fails."""


def run_git(args: Sequence[str], cwd: Path) -> str:
    """Run a git command in ``cwd`` and return its trimmed stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout.strip()


def stage(paths: Sequence[str], cwd: Path) -> None:
    """Stage paths that exist. A path that was never created is not an error."""
    existing: List[str] = [p for p in paths if (Path(cwd) / p).exists()]
    if not existing:
        return
    run_git(["add", "--", *existing], cwd=cwd)


def has_staged_changes(cwd: Path) -> bool:
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    return result.returncode == 1


def commit(
    message: str,
    cwd: Path,
    author_name: str = DEFAULT_AUTHOR_NAME,
    author_email: str = DEFAULT_AUTHOR_EMAIL,
) -> Optional[str]:
    """Commit staged changes, returning the new sha, or None if there were none.

    Identity is passed per-command rather than written to git config so the
    runner's (or the developer's) own settings are left untouched.
    """
    if not has_staged_changes(cwd=cwd):
        log.info("nothing staged; skipping commit")
        return None
    run_git(
        [
            "-c", f"user.name={author_name}",
            "-c", f"user.email={author_email}",
            "commit", "-m", message, "--no-verify",
        ],
        cwd=cwd,
    )
    return head_sha(cwd=cwd)


def push(cwd: Path, remote: str = "origin", branch: Optional[str] = None) -> None:
    """Push the current branch."""
    branch = branch or run_git(["branch", "--show-current"], cwd=cwd)
    run_git(["push", remote, f"HEAD:{branch}"], cwd=cwd)


def head_sha(cwd: Path) -> str:
    return run_git(["rev-parse", "HEAD"], cwd=cwd)
