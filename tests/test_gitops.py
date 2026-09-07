import subprocess
from pathlib import Path

import pytest

from jobalert.gitops import GitError, commit, has_staged_changes, head_sha, run_git, stage


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    (tmp_path / "seed.txt").write_text("seed", encoding="utf-8")
    stage(["seed.txt"], cwd=tmp_path)
    commit("chore: seed", cwd=tmp_path)
    return tmp_path


class TestRunGit:
    def test_returns_stdout(self, repo):
        assert "main" in run_git(["branch", "--show-current"], cwd=repo)

    def test_raises_with_the_git_error_text(self, repo):
        with pytest.raises(GitError, match="not-a-command"):
            run_git(["not-a-command"], cwd=repo)


class TestStageAndCommit:
    def test_commits_new_files_and_returns_the_sha(self, repo):
        (repo / "out").mkdir()
        (repo / "out" / "a.jpg").write_bytes(b"jpeg")
        stage(["out"], cwd=repo)
        sha = commit("feat: add poster", cwd=repo)
        assert sha is not None
        assert len(sha) == 40
        assert sha == head_sha(cwd=repo)

    def test_commit_is_a_no_op_when_nothing_changed(self, repo):
        # A run that publishes nothing must not create an empty commit.
        assert commit("chore: nothing", cwd=repo) is None

    def test_has_staged_changes_reflects_the_index(self, repo):
        assert has_staged_changes(cwd=repo) is False
        (repo / "new.txt").write_text("x", encoding="utf-8")
        stage(["new.txt"], cwd=repo)
        assert has_staged_changes(cwd=repo) is True

    def test_staging_a_missing_path_is_ignored(self, repo):
        # out/ may legitimately not exist on a run that rendered nothing.
        stage(["does-not-exist"], cwd=repo)
        assert has_staged_changes(cwd=repo) is False

    def test_commit_does_not_depend_on_global_git_identity(self, repo):
        (repo / "b.txt").write_text("b", encoding="utf-8")
        stage(["b.txt"], cwd=repo)
        sha = commit("chore: b", cwd=repo, author_name="Job Alert Bot")
        author = run_git(["show", "-s", "--format=%an", sha], cwd=repo)
        assert author == "Job Alert Bot"


class TestGitRepoOps:
    def test_save_commits_without_pushing_when_disabled(self, repo):
        from jobalert.publish import GitRepoOps

        ops = GitRepoOps(repo, push_enabled=False)
        (repo / "out").mkdir()
        (repo / "out" / "a.jpg").write_bytes(b"x")
        sha = ops.save(["out"], "chore: poster")
        assert sha == ops.head_sha()

    def test_save_returns_none_when_there_is_nothing_to_commit(self, repo):
        from jobalert.publish import GitRepoOps

        assert GitRepoOps(repo, push_enabled=False).save(["out"], "chore: nothing") is None
