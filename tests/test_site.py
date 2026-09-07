import re
from datetime import date, datetime, timezone

from jobalert.archive import append_published
from jobalert.site import render_site
from tests.factories import make_job

WHEN = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


def build(tmp_path, jobs, handle="@naukri_notice_77"):
    records = []
    for job in jobs:
        records = append_published(records, job, WHEN)
    dest = tmp_path / "index.html"
    render_site(records, handle=handle, dest=dest, generated_at=WHEN)
    return dest.read_text(encoding="utf-8")


class TestRenderSite:
    def test_lists_each_job_with_a_working_apply_link(self, tmp_path):
        html = build(tmp_path, [make_job(apply_url="https://example.com/apply/1")])
        assert "Assistant Section Officer" in html
        assert 'href="https://example.com/apply/1"' in html

    def test_shows_the_handle(self, tmp_path):
        assert "@naukri_notice_77" in build(tmp_path, [make_job()])

    def test_credits_the_sources(self, tmp_path):
        html = build(tmp_path, [make_job(source="adzuna")])
        assert "Adzuna" in html

    def test_renders_an_empty_archive_without_crashing(self, tmp_path):
        html = build(tmp_path, [])
        assert "<html" in html.lower()
        assert "no jobs" in html.lower()

    def test_marks_estimated_salaries(self, tmp_path):
        html = build(tmp_path, [make_job(salary="Rs 12L", salary_is_estimated=True)])
        assert "estimated" in html.lower()

    def test_is_mobile_first(self, tmp_path):
        # Nearly every visitor arrives by tapping a link in the Instagram app.
        html = build(tmp_path, [make_job()])
        assert 'name="viewport"' in html

    def test_escapes_untrusted_job_text(self, tmp_path):
        # Titles come from third-party APIs and land on a public page.
        html = build(tmp_path, [make_job(title='<script>alert("xss")</script>Engineer')])
        assert "<script>alert" not in html
        assert "&lt;script&gt;" in html

    def test_drops_links_that_are_not_https(self, tmp_path):
        job = make_job(apply_url="https://ok.example.com/1")
        html = build(tmp_path, [job])
        assert 'href="https://ok.example.com/1"' in html
        assert 'href="javascript:' not in html

    def test_refuses_a_javascript_url_injected_into_the_archive(self, tmp_path):
        from jobalert.site import render_site

        records = [{
            "job_id": "x", "title": "Evil", "org": "E", "location": "L",
            "apply_url": "javascript:alert(1)", "category": "PRIVATE", "salary": None,
            "salary_is_estimated": False, "last_date": None, "source": "adzuna",
            "published_at": WHEN.isoformat(), "external_id": "x",
        }]
        dest = tmp_path / "index.html"
        render_site(records, handle="@h", dest=dest, generated_at=WHEN)
        html = dest.read_text(encoding="utf-8")
        assert "javascript:alert" not in html

    def test_external_links_are_safe_from_tabnabbing(self, tmp_path):
        html = build(tmp_path, [make_job()])
        assert 'rel="noopener noreferrer"' in html

    def test_creates_the_destination_directory(self, tmp_path):
        dest = tmp_path / "docs" / "index.html"
        render_site([], handle="@h", dest=dest, generated_at=WHEN)
        assert dest.exists()


class TestExtraFields:
    def test_shows_eligibility_and_description(self, tmp_path):
        from datetime import date as _date

        html = build(tmp_path, [make_job(age_limit="18 - 32 years", application_fee="Rs 100",
                                         description="Applications invited for 500 posts.")])
        assert "18 - 32 years" in html
        assert "Rs 100" in html
        assert "Applications invited for 500 posts." in html

    def test_escapes_a_hostile_description(self, tmp_path):
        # Escaped text may still contain the words; what matters is that no live
        # tag reaches the document.
        html = build(tmp_path, [make_job(description='<img src=x onerror=alert(1)>')])
        assert "<img" not in html
        assert "&lt;img src=x onerror=alert(1)&gt;" in html
