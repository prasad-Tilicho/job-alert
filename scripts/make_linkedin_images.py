#!/usr/bin/env python3
"""Generate a LinkedIn carousel about the project.

Deliberately reuses the poster's own palette and typeface, so the slides look
like they came from the thing they describe.

Usage:  python3 scripts/make_linkedin_images.py [output_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jobalert.poster import theme  # noqa: E402
from jobalert.poster.layout import wrap_text  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "assets" / "fonts"

SIZE = 1080
MARGIN = 88
CONTENT = SIZE - 2 * MARGIN

BG = theme.BACKGROUND
TEXT = theme.TEXT
MUTED = theme.TEXT_MUTED
EMERALD = theme.ACCENTS[list(theme.ACCENTS)[0]]
BLUE = (96, 165, 250)
DARK = theme.TEXT_ON_ACCENT

_cache: dict = {}


def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    key = (weight, size)
    if key not in _cache:
        _cache[key] = ImageFont.truetype(str(FONTS / f"Poppins-{weight}.ttf"), size)
    return _cache[key]


def canvas(accent=EMERALD) -> Image.Image:
    """Dark slide with the poster's soft corner glow and top accent bar."""
    image = Image.new("RGB", (SIZE, SIZE), BG)
    overlay = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.ellipse([SIZE - 420, SIZE - 420, SIZE + 380, SIZE + 380], fill=(*accent, 44))
    draw.ellipse([-320, -340, 340, 320], fill=(*accent, 26))
    overlay = overlay.filter(ImageFilter.GaussianBlur(110))
    image.paste(Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB"), (0, 0))
    ImageDraw.Draw(image).rectangle([0, 0, SIZE, 12], fill=accent)
    return image


def tracked(draw, xy, text, fnt, fill, tracking=3.0) -> None:
    x, y = xy
    for char in text:
        draw.text((x, y), char, font=fnt, fill=fill, anchor="lm")
        x += fnt.getlength(char) + tracking


def block(draw, x, y, text, fnt, fill, width=CONTENT, spacing=1.18) -> float:
    """Draw wrapped text; return the y below it."""
    lines = wrap_text(text, width, fnt.getlength)
    step = fnt.size * spacing
    for index, line in enumerate(lines):
        draw.text((x, y + index * step), line, font=fnt, fill=fill, anchor="la")
    return y + len(lines) * step


def footer(draw, accent=EMERALD) -> None:
    draw.text((MARGIN, SIZE - 62), "@naukri_notice_77", font=font("Bold", 26),
              fill=MUTED, anchor="ls")
    draw.text((SIZE - MARGIN, SIZE - 62), "github.com/prasad-Tilicho/job-alert",
              font=font("Regular", 22), fill=MUTED, anchor="rs")


def slide_hero(dest: Path) -> Path:
    image = canvas()
    draw = ImageDraw.Draw(image)
    tracked(draw, (MARGIN, 150), "SIDE PROJECT", font("Bold", 24), EMERALD, 4.0)
    y = block(draw, MARGIN, 220, "An Instagram account that posts job alerts by itself.",
              font("Bold", 78), TEXT, spacing=1.12)
    y = block(draw, MARGIN, y + 40,
              "Greenfield. Empty repo to production.", font("SemiBold", 40), MUTED)
    y = block(draw, MARGIN, y + 12, "Built with Claude Code.", font("SemiBold", 40), EMERALD)

    box_top = y + 56
    draw.rounded_rectangle([MARGIN, box_top, SIZE - MARGIN, box_top + 150],
                           radius=26, fill=EMERALD)
    draw.text((SIZE / 2, box_top + 58), "\u20b90", font=font("Bold", 72), fill=DARK, anchor="mm")
    tracked(draw, (SIZE / 2 - 150, box_top + 112), "INFRASTRUCTURE COST",
            font("Bold", 22), DARK, 3.5)
    footer(draw)
    return save(image, dest)


def slide_pipeline(dest: Path) -> Path:
    image = canvas(BLUE)
    draw = ImageDraw.Draw(image)
    tracked(draw, (MARGIN, 130), "EVERY 12 HOURS", font("Bold", 24), BLUE, 4.0)
    draw.text((MARGIN, 175), "The pipeline", font=font("Bold", 62), fill=TEXT, anchor="la")

    steps: Sequence[Tuple[str, str]] = (
        ("FETCH", "~420 listings from 7 sources"),
        ("VALIDATE", "drop expired, incomplete, non-HTTPS"),
        ("RANK", "government first, then India, then remote"),
        ("RENDER", "1080x1350 poster, drawn with Pillow"),
        ("COMMIT", "the repo is the image host"),
        ("PUBLISH", "container -> poll -> media_publish"),
    )
    y = 300
    for index, (label, detail) in enumerate(steps):
        dot_x = MARGIN + 16
        draw.ellipse([dot_x - 9, y + 16, dot_x + 9, y + 34], fill=BLUE)
        if index < len(steps) - 1:
            draw.line([(dot_x, y + 38), (dot_x, y + 96)], fill=(48, 62, 92), width=3)
        draw.text((MARGIN + 52, y + 6), label, font=font("Bold", 34), fill=TEXT, anchor="la")
        draw.text((MARGIN + 52, y + 50), detail, font=font("Regular", 26), fill=MUTED, anchor="la")
        y += 104
    footer(draw)
    return save(image, dest)


def slide_finding(dest: Path) -> Path:
    image = canvas()
    draw = ImageDraw.Draw(image)
    tracked(draw, (MARGIN, 130), "THE HARD PART", font("Bold", 24), EMERALD, 4.0)
    y = block(draw, MARGIN, 180, "It was never the API.", font("Bold", 62), TEXT)
    y = block(draw, MARGIN, y + 26,
              "Most Indian government portals publish no machine-readable "
              "vacancies at all. I probed around 40.",
              font("Regular", 32), MUTED, spacing=1.35)

    findings = (
        ("UPSC", "blocked at the CDN edge"),
        ("IBPS", "RSS feed holds only placeholder posts"),
        ("Railways", '"(04/2026) Notification" - no job title'),
        ("DRDO", "102 rows of cutoff marks, not openings"),
    )
    y += 44
    for name, detail in findings:
        draw.rounded_rectangle([MARGIN, y, SIZE - MARGIN, y + 74], radius=14,
                               fill=theme.SURFACE)
        draw.text((MARGIN + 26, y + 37), name, font=font("Bold", 30), fill=TEXT, anchor="lm")
        draw.text((SIZE - MARGIN - 26, y + 37), detail, font=font("Regular", 24),
                  fill=MUTED, anchor="rm")
        y += 88

    draw.rounded_rectangle([MARGIN, y + 14, SIZE - MARGIN, y + 96], radius=16, fill=EMERALD)
    draw.text((SIZE / 2, y + 55),
              "3 worked: SSC, ISRO, Cochin Shipyard",
              font=font("Bold", 30), fill=DARK, anchor="mm")
    footer(draw)
    return save(image, dest)


def slide_output(dest: Path, posters: Sequence[Path]) -> Path:
    image = canvas(BLUE)
    draw = ImageDraw.Draw(image)
    tracked(draw, (MARGIN, 122), "THE OUTPUT", font("Bold", 24), BLUE, 4.0)
    draw.text((MARGIN, 166), "Every poster, drawn in code", font=font("Bold", 52),
              fill=TEXT, anchor="la")

    width, gap = 386, 40
    top = 280
    left = (SIZE - (width * 2 + gap)) // 2
    for index, path in enumerate(posters[:2]):
        shot = Image.open(path).convert("RGB")
        shot = shot.resize((width, int(width * shot.height / shot.width)), Image.LANCZOS)
        x = left + index * (width + gap)
        draw.rounded_rectangle([x - 5, top - 5, x + width + 5, top + shot.height + 5],
                               radius=18, outline=(52, 66, 96), width=3)
        image.paste(shot, (x, top))
    draw.text((SIZE / 2, SIZE - 148), "No templates. No LLM. Deterministic Python.",
              font=font("SemiBold", 30), fill=MUTED, anchor="mm")
    footer(draw)
    return save(image, dest)


def slide_stats(dest: Path) -> Path:
    image = canvas()
    draw = ImageDraw.Draw(image)
    tracked(draw, (MARGIN, 130), "WHERE IT LANDED", font("Bold", 24), EMERALD, 4.0)
    draw.text((MARGIN, 176), "By the numbers", font=font("Bold", 62), fill=TEXT, anchor="la")

    stats = (("340", "tests"), ("94%", "coverage"), ("7", "live sources"),
             ("~420", "jobs per run"), ("10", "posts per day"), ("\u20b90", "running cost"))
    cell_w, cell_h, gap = (CONTENT - 32) // 2, 132, 32
    y = 316
    for index, (value, label) in enumerate(stats):
        col, row = index % 2, index // 2
        x = MARGIN + col * (cell_w + gap)
        top = y + row * (cell_h + 24)
        draw.rounded_rectangle([x, top, x + cell_w, top + cell_h], radius=18,
                               fill=theme.SURFACE)
        draw.text((x + 28, top + 46), value, font=font("Bold", 54), fill=EMERALD, anchor="lm")
        draw.text((x + 28, top + 96), label, font=font("Regular", 26), fill=MUTED, anchor="lm")
    footer(draw)
    return save(image, dest)


def save(image: Image.Image, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest, format="PNG", optimize=True)
    return dest


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "assets" / "linkedin"
    posters = sorted((ROOT / "out").glob("*.jpg"))[:2]
    slides: List[Path] = [
        slide_hero(out / "01-hero.png"),
        slide_pipeline(out / "02-pipeline.png"),
        slide_finding(out / "03-finding.png"),
        slide_stats(out / "05-stats.png"),
    ]
    if len(posters) >= 2:
        slides.insert(3, slide_output(out / "04-output.png", posters))
    for path in slides:
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
