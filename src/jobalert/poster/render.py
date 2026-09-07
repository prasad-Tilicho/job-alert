"""Composes the Instagram poster with Pillow.

The layout is anchored from both ends: the header and title flow down from the
top, the footer and deadline strip are pinned to the bottom, and the optional
metadata rows fill whatever is left. That way a four-line title can never push
the deadline off the canvas.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from jobalert.attribution import label_for
from jobalert.models import Job
from jobalert.poster import theme
from jobalert.poster.layout import Measure, block_height, fit_text, wrap_text

CANVAS = theme.CANVAS
JPEG_QUALITY = 88

FONT_FILES = {
    "bold": "Poppins-Bold.ttf",
    "semibold": "Poppins-SemiBold.ttf",
    "regular": "Poppins-Regular.ttf",
}


def _format_date(value: date) -> str:
    return value.strftime("%d %b %Y").upper()


class FontSet:
    """Loads and caches the bundled typefaces.

    CI runners have no system fonts, so the TTFs are committed under assets/fonts
    and a missing one must fail at construction rather than mid-render.
    """

    def __init__(self, fonts_dir: Path):
        self._dir = Path(fonts_dir)
        missing = [name for name in FONT_FILES.values() if not (self._dir / name).is_file()]
        if missing:
            raise FileNotFoundError(
                f"missing font file(s) in {self._dir}: {', '.join(sorted(missing))}"
            )
        self._cache: Dict[Tuple[str, int], ImageFont.FreeTypeFont] = {}

    def get(self, weight: str, size: int) -> ImageFont.FreeTypeFont:
        key = (weight, int(size))
        if key not in self._cache:
            self._cache[key] = ImageFont.truetype(str(self._dir / FONT_FILES[weight]), int(size))
        return self._cache[key]

    def measure_for(self, weight: str) -> Callable[[int], Measure]:
        """Return a size -> measure factory, as :func:`fit_text` expects."""

        def factory(size: int) -> Measure:
            font = self.get(weight, size)
            return lambda text: font.getlength(text)

        return factory


def _tracked_width(text: str, font: ImageFont.FreeTypeFont, tracking: float) -> float:
    if not text:
        return 0.0
    return sum(font.getlength(ch) for ch in text) + tracking * (len(text) - 1)


def _draw_tracked(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[float, float],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill,
    tracking: float,
) -> None:
    """Draw letter-spaced text. Pillow has no tracking, so glyphs go one by one."""
    x, y = xy
    for char in text:
        draw.text((x, y), char, font=font, fill=fill, anchor="lm")
        x += font.getlength(char) + tracking


def _draw_lines(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    lines: Sequence[str],
    font: ImageFont.FreeTypeFont,
    fill,
    spacing: float,
) -> float:
    """Draw a wrapped block top-down and return the y just below it."""
    step = font.size * spacing
    for index, line in enumerate(lines):
        draw.text((x, y + index * step), line, font=font, fill=fill, anchor="la")
    return y + len(lines) * step


class PosterRenderer:
    """Renders job posters. Construct once and reuse; fonts are cached."""

    def __init__(self, fonts_dir: Path, handle: str):
        self._fonts = FontSet(fonts_dir)
        self._handle = handle

    def render(self, job: Job, dest: Path, today: date) -> Path:
        """Write the poster for ``job`` to ``dest`` as a JPEG and return the path."""
        width, height = CANVAS
        accent = theme.accent_for(job.category)

        image = Image.new("RGB", CANVAS, theme.BACKGROUND)
        self._draw_backdrop(image, accent)
        draw = ImageDraw.Draw(image)

        draw.rectangle([0, 0, width, theme.ACCENT_BAR_HEIGHT], fill=accent)
        self._draw_header(draw, job, accent, today)

        cursor = self._draw_title_and_org(draw, job, accent)

        # Bottom-anchored elements are placed first so the flexible middle section
        # knows exactly how much room it has.
        footer_y = height - theme.FOOTER_BOTTOM_INSET
        self._draw_footer(draw, job, footer_y)

        # The strip is always drawn, so every poster has the same silhouette and no
        # post is left with a dead band where a deadline would have been.
        strip_bottom = footer_y - theme.FOOTER_SIZE - theme.GAP_LG
        strip_top = strip_bottom - theme.STRIP_HEIGHT
        self._draw_action_strip(draw, job, strip_top, strip_bottom, accent)
        content_limit = strip_top - theme.GAP_LG

        self._draw_details(draw, job, top_limit=cursor, bottom_limit=content_limit)

        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        image.save(dest, format="JPEG", quality=JPEG_QUALITY, optimize=True, subsampling=0)
        return dest

    # -- sections -------------------------------------------------------------

    def _draw_backdrop(self, image: Image.Image, accent) -> None:
        """Two blurred accent glows, so the poster is not a flat slab.

        The blur matters: an unblurred ellipse at low alpha still shows a hard
        edge that reads as a rendering artefact behind the title.
        """
        overlay = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        cx, cy, r = CANVAS[0] + 40, CANVAS[1] + 10, 520
        odraw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*accent, 46))
        odraw.ellipse([-320, -360, 380, 340], fill=(*accent, 30))
        overlay = overlay.filter(ImageFilter.GaussianBlur(theme.GLOW_BLUR))
        image.paste(Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB"), (0, 0))

    def _draw_header(self, draw: ImageDraw.ImageDraw, job: Job, accent, today: date) -> None:
        pill_font = self._fonts.get("bold", theme.PILL_TEXT_SIZE)
        label = job.category.label
        text_width = _tracked_width(label, pill_font, theme.LABEL_TRACKING)
        pill_width = text_width + 2 * theme.PILL_PADDING_X
        top = theme.HEADER_TOP
        bottom = top + theme.PILL_HEIGHT
        draw.rounded_rectangle(
            [theme.MARGIN, top, theme.MARGIN + pill_width, bottom],
            radius=theme.PILL_RADIUS,
            fill=accent,
        )
        _draw_tracked(
            draw,
            (theme.MARGIN + theme.PILL_PADDING_X, (top + bottom) / 2),
            label,
            pill_font,
            theme.TEXT_ON_ACCENT,
            theme.LABEL_TRACKING,
        )

        stamp = _format_date(job.posted_at or today)
        draw.text(
            (CANVAS[0] - theme.MARGIN, (top + bottom) / 2),
            stamp,
            font=self._fonts.get("semibold", theme.DATE_TEXT_SIZE),
            fill=theme.TEXT_MUTED,
            anchor="rm",
        )

    def _draw_title_and_org(self, draw: ImageDraw.ImageDraw, job: Job, accent) -> float:
        title = fit_text(
            job.title,
            max_width=theme.CONTENT_WIDTH,
            max_lines=theme.TITLE_MAX_LINES,
            sizes=theme.TITLE_SIZES,
            measure_for=self._fonts.measure_for("bold"),
        )
        cursor = _draw_lines(
            draw,
            theme.MARGIN,
            theme.TITLE_TOP,
            title.lines,
            self._fonts.get("bold", title.size),
            theme.TEXT,
            theme.TITLE_LINE_SPACING,
        )

        org = fit_text(
            job.org,
            max_width=theme.CONTENT_WIDTH,
            max_lines=theme.ORG_MAX_LINES,
            sizes=theme.ORG_SIZES,
            measure_for=self._fonts.measure_for("semibold"),
        )
        cursor += theme.GAP_SM
        return _draw_lines(
            draw,
            theme.MARGIN,
            cursor,
            org.lines,
            self._fonts.get("semibold", org.size),
            accent,
            theme.ORG_LINE_SPACING,
        )

    def _meta_rows(self, job: Job) -> List[Tuple[str, List[str], int]]:
        """Label, wrapped value lines, and pixel height for each detail row."""
        value_font = self._fonts.get("regular", theme.VALUE_SIZE)
        pairs = [("LOCATION", job.location)]
        if job.salary:
            pairs.append(("SALARY", job.salary))

        rows: List[Tuple[str, List[str], int]] = []
        for label, value in pairs:
            lines = wrap_text(value, theme.CONTENT_WIDTH, value_font.getlength)[: theme.VALUE_MAX_LINES]
            height = theme.LABEL_SIZE + theme.GAP_SM + block_height(
                len(lines), theme.VALUE_SIZE, theme.META_LINE_SPACING
            )
            rows.append((label, lines, height))
        return rows

    def _draw_details(
        self,
        draw: ImageDraw.ImageDraw,
        job: Job,
        top_limit: float,
        bottom_limit: float,
    ) -> None:
        """Draw the divider and detail rows as one block, anchored to the bottom.

        Anchoring downwards keeps a short title from leaving a dead zone in the
        lower half of the poster. When the title is long enough that the block
        would collide with it, the block falls back to flowing from the top.
        """
        rows = self._meta_rows(job)
        total = sum(height for _, _, height in rows) + theme.GAP_MD * (len(rows) - 1)

        meta_top = bottom_limit - total
        divider_y = meta_top - theme.GAP_MD
        floor = top_limit + theme.GAP_MD
        if divider_y < floor:
            divider_y = floor
            meta_top = divider_y + theme.GAP_MD

        draw.line(
            [(theme.MARGIN, divider_y), (CANVAS[0] - theme.MARGIN, divider_y)],
            fill=theme.DIVIDER_COLOR,
            width=2,
        )

        label_font = self._fonts.get("bold", theme.LABEL_SIZE)
        value_font = self._fonts.get("regular", theme.VALUE_SIZE)
        cursor = meta_top
        for label, lines, height in rows:
            if cursor + height > bottom_limit + 1:
                # Out of room: omit the row rather than overlap the deadline strip.
                break
            _draw_tracked(
                draw,
                (theme.MARGIN, cursor + theme.LABEL_SIZE / 2),
                label,
                label_font,
                theme.TEXT_MUTED,
                theme.LABEL_TRACKING,
            )
            cursor += theme.LABEL_SIZE + theme.GAP_SM
            cursor = _draw_lines(
                draw, theme.MARGIN, cursor, lines, value_font, theme.TEXT, theme.META_LINE_SPACING
            )
            cursor += theme.GAP_MD

    def _draw_action_strip(
        self,
        draw: ImageDraw.ImageDraw,
        job: Job,
        top: float,
        bottom: float,
        accent,
    ) -> None:
        """The accent bar above the footer: a deadline when known, else a CTA.

        A job with no published closing date gets "APPLY NOW / LINK IN BIO" rather
        than an invented date - the strip must never state something we do not know.
        """
        if job.last_date is not None:
            label, value = "APPLY BY", _format_date(job.last_date)
        else:
            label, value = "APPLY NOW", "LINK IN BIO"

        draw.rounded_rectangle(
            [theme.MARGIN, top, CANVAS[0] - theme.MARGIN, bottom],
            radius=theme.STRIP_RADIUS,
            fill=accent,
        )
        middle = (top + bottom) / 2
        _draw_tracked(
            draw,
            (theme.MARGIN + theme.PILL_PADDING_X, middle),
            label,
            self._fonts.get("bold", theme.LABEL_SIZE),
            theme.TEXT_ON_ACCENT,
            theme.LABEL_TRACKING,
        )
        draw.text(
            (CANVAS[0] - theme.MARGIN - theme.PILL_PADDING_X, middle),
            value,
            font=self._fonts.get("bold", theme.STRIP_TEXT_SIZE),
            fill=theme.TEXT_ON_ACCENT,
            anchor="rm",
        )

    def _draw_footer(self, draw: ImageDraw.ImageDraw, job: Job, baseline: float) -> None:
        draw.text(
            (theme.MARGIN, baseline),
            self._handle,
            font=self._fonts.get("bold", theme.FOOTER_SIZE),
            fill=theme.TEXT,
            anchor="ls",
        )
        draw.text(
            (CANVAS[0] - theme.MARGIN, baseline),
            f"Source: {label_for(job.source)}",
            font=self._fonts.get("regular", theme.FOOTER_NOTE_SIZE),
            fill=theme.TEXT_MUTED,
            anchor="rs",
        )
