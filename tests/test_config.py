import pytest

from jobalert.config import ConfigError, load_config

FULL_ENV = {
    "IG_USER_ID": "17841400000000000",
    "IG_ACCESS_TOKEN": "IGQVJ...token",
    "ADZUNA_APP_ID": "abc123",
    "ADZUNA_APP_KEY": "def456",
    "GITHUB_REPOSITORY": "prasad/job-alert",
    "IG_HANDLE": "@dailyjobalerts",
}


class TestLoadConfig:
    def test_reads_a_complete_environment(self):
        config = load_config(FULL_ENV)
        assert config.ig_user_id == "17841400000000000"
        assert config.adzuna_app_id == "abc123"
        assert config.repo == "prasad/job-alert"
        assert config.handle == "@dailyjobalerts"

    def test_reports_every_missing_variable_at_once(self):
        # Failing one at a time would mean six CI runs to find six problems.
        with pytest.raises(ConfigError) as excinfo:
            load_config({})
        message = str(excinfo.value)
        assert "IG_USER_ID" in message
        assert "IG_ACCESS_TOKEN" in message
        assert "GITHUB_REPOSITORY" in message

    def test_dry_run_does_not_require_instagram_credentials(self):
        config = load_config({"GITHUB_REPOSITORY": "a/b"}, require_instagram=False)
        assert config.ig_access_token == ""

    def test_adzuna_is_optional_so_a_run_still_works_without_it(self):
        env = {k: v for k, v in FULL_ENV.items() if not k.startswith("ADZUNA")}
        config = load_config(env)
        assert config.adzuna_app_id == ""

    def test_paused_is_parsed_from_common_truthy_spellings(self):
        for value in ("true", "TRUE", "1", "yes"):
            assert load_config({**FULL_ENV, "PAUSED": value}).paused is True
        for value in ("false", "0", "no", ""):
            assert load_config({**FULL_ENV, "PAUSED": value}).paused is False

    def test_max_posts_per_run_has_a_safe_default_and_upper_bound(self):
        assert load_config(FULL_ENV).max_posts_per_run == 3
        assert load_config({**FULL_ENV, "MAX_POSTS_PER_RUN": "2"}).max_posts_per_run == 2
        # A typo like 300 must not spam followers or burn the API quota.
        assert load_config({**FULL_ENV, "MAX_POSTS_PER_RUN": "300"}).max_posts_per_run == 10

    def test_invalid_max_posts_falls_back_to_the_default(self):
        assert load_config({**FULL_ENV, "MAX_POSTS_PER_RUN": "abc"}).max_posts_per_run == 3

    def test_raw_image_url_is_pinned_to_a_commit_sha(self):
        config = load_config(FULL_ENV)
        url = config.raw_url("deadbeef", "out/abc123.jpg")
        assert url == "https://raw.githubusercontent.com/prasad/job-alert/deadbeef/out/abc123.jpg"
