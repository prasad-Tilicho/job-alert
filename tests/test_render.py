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
        assert list(gov.getdata()) != list(pri.getdata())

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
