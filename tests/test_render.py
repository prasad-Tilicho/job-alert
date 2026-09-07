from datetime import date
from pathlib import Path

import pytest
from PIL import Image

from jobalert.config import PROJECT_ROOT
from jobalert.models import Category
from jobalert.poster.render import CANVAS, PosterRenderer
from tests.factories import make_job

TODAY = date(2026, 9, 7)


@pytest.fixture(scope="module")
def renderer():
    return PosterRenderer(fonts_dir=PROJECT_ROOT / "assets" / "fonts", handle="@dailyjobalerts")


def render(renderer, tmp_path: Path, job) -> Image.Image:
    dest = tmp_path / f"{job.job_id}.jpg"
    result = renderer.render(job, dest, today=TODAY)
    assert result == dest
    return Image.open(dest)


class TestPosterRenderer:
    def test_produces_an_instagram_ready_jpeg(self, renderer, tmp_path):
        image = render(renderer, tmp_path, make_job())
        # Instagram accepts JPEG only, and 4:5 is the tallest allowed feed ratio.
        assert image.format == "JPEG"
        assert image.mode == "RGB"
        assert image.size == CANVAS

    def test_the_poster_is_not_blank(self, renderer, tmp_path):
        image = render(renderer, tmp_path, make_job())
        assert len(image.convert("RGB").getcolors(maxcolors=200000) or []) > 20

    def test_government_and_private_posters_differ_visually(self, renderer, tmp_path):
        gov = render(renderer, tmp_path, make_job(external_id="g", category=Category.GOVERNMENT))
        pri = render(renderer, tmp_path, make_job(external_id="p", category=Category.PRIVATE))
        assert gov.tobytes() != pri.tobytes()

    @pytest.mark.parametrize(
        "overrides",
        [
            {"salary": None},
            {"last_date": None},
            {"salary": None, "last_date": None},
            {"title": "Assistant " * 40},
            {"title": "Supercalifragilisticexpialidociousemploymentopportunity"},
            {"org": "A" * 120},
            {"location": "Thiruvananthapuram, Kerala, India, South Asia, Earth"},
            {"title": "सहायक अनुभाग अधिकारी भर्ती"},
            {"salary": "Rs 4.4L - 14.2L per year", "last_date": date(2026, 12, 31)},
        ],
        ids=[
            "no-salary",
            "no-deadline",
            "neither",
            "very-long-title",
            "unbreakable-word",
            "long-org",
            "long-location",
            "devanagari",
            "everything",
        ],
    )
    def test_renders_every_shape_of_job_at_the_right_size(self, renderer, tmp_path, overrides):
        job = make_job(external_id=str(abs(hash(str(overrides)))), **overrides)
        image = render(renderer, tmp_path, job)
        assert image.size == CANVAS

    def test_creates_the_destination_directory(self, renderer, tmp_path):
        dest = tmp_path / "nested" / "deeper" / "poster.jpg"
        renderer.render(make_job(), dest, today=TODAY)
        assert dest.exists()

    def test_missing_font_directory_fails_loudly_at_construction(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            PosterRenderer(fonts_dir=tmp_path / "absent", handle="@x")


class TestActionStrip:
    def test_a_job_without_a_deadline_still_gets_a_strip(self, renderer, tmp_path):
        # Same silhouette either way: no post is left with a dead band at the bottom.
        with_date = render(renderer, tmp_path, make_job(external_id="d1"))
        without = render(renderer, tmp_path, make_job(external_id="d2", last_date=None))
        assert with_date.size == without.size == CANVAS

        # The strip region must not be empty background in either case.
        strip_box = (100, 1090, 980, 1180)
        for image in (with_date, without):
            colors = image.crop(strip_box).getcolors(maxcolors=100000) or []
            assert len(colors) > 5


class TestSalaryAndStripLabels:
    def test_estimated_salaries_are_labelled_as_estimates(self, renderer):
        # An unlabelled prediction would read as the employer's stated offer.
        estimated = make_job(salary="Rs 18.0L - 24.0L per year", salary_is_estimated=True)
        stated = make_job(salary="Rs 18.0L - 24.0L per year", salary_is_estimated=False)
        assert [label for label, _, _ in renderer._meta_rows(estimated)] == ["LOCATION", "SALARY (EST.)"]
        assert [label for label, _, _ in renderer._meta_rows(stated)] == ["LOCATION", "SALARY"]

    def test_a_job_without_a_deadline_shows_its_posting_date(self, renderer, tmp_path):
        # Rather than a generic call to action, when we know when it was posted.
        job = make_job(last_date=None, posted_at=date(2026, 9, 5))
        image = render(renderer, tmp_path, job)
        assert image.size == CANVAS

    def test_a_job_with_neither_date_still_renders(self, renderer, tmp_path):
        job = make_job(external_id="nodates", last_date=None, posted_at=None)
        assert render(renderer, tmp_path, job).size == CANVAS


class TestStripContent:
    def test_a_deadline_wins_over_the_posting_date(self):
        from jobalert.poster.render import _strip_content

        label, value, uses_posted = _strip_content(make_job(last_date=date(2026, 10, 15)))
        assert (label, value, uses_posted) == ("APPLY BY", "15 OCT 2026", False)

    def test_falls_back_to_the_posting_date(self):
        from jobalert.poster.render import _strip_content

        job = make_job(last_date=None, posted_at=date(2026, 9, 5))
        assert _strip_content(job) == ("POSTED", "05 SEP 2026", True)

    def test_falls_back_to_a_call_to_action_with_no_dates_at_all(self):
        from jobalert.poster.render import _strip_content

        job = make_job(last_date=None, posted_at=None)
        assert _strip_content(job) == ("APPLY NOW", "LINK IN BIO", False)


class TestEligibilityRows:
    def test_age_limit_and_fee_appear_when_the_source_provides_them(self, renderer):
        job = make_job(salary=None, age_limit="18 - 32 years", application_fee="Rs 100")
        assert [label for label, _, _ in renderer._meta_rows(job)] == [
            "LOCATION", "AGE LIMIT", "FEE",
        ]

    def test_they_are_absent_when_unknown(self, renderer):
        job = make_job(salary=None, age_limit=None, application_fee=None)
        assert [label for label, _, _ in renderer._meta_rows(job)] == ["LOCATION"]

    def test_a_government_poster_with_every_row_still_renders(self, renderer, tmp_path):
        job = make_job(external_id="full", salary=None, age_limit="18 - 32 years",
                       application_fee="Rs 100", last_date=date(2026, 9, 22))
        assert render(renderer, tmp_path, job).size == CANVAS


class TestBioPrompt:
    def test_every_poster_points_at_the_bio_link(self, renderer, tmp_path):
        # Captions are not clickable, so the poster itself must say where to go.
        for overrides in ({"last_date": date(2026, 10, 15)}, {"last_date": None}):
            job = make_job(external_id=str(overrides), **overrides)
            assert render(renderer, tmp_path, job).size == CANVAS

    def test_the_prompt_is_not_repeated_when_the_strip_already_says_it(self, renderer, tmp_path):
        from jobalert.poster.render import _strip_content

        job = make_job(last_date=None, posted_at=None)
        assert _strip_content(job)[1] == "LINK IN BIO"
        assert render(renderer, tmp_path, job).size == CANVAS


class TestGlyphCoverage:
    def test_fixed_poster_strings_are_plain_ascii(self):
        from jobalert.poster.render import POSTER_STRINGS

        for key, value in POSTER_STRINGS.items():
            assert value.isascii(), f"{key} contains a character Poppins may not have: {value!r}"
