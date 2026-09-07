#!/usr/bin/env python3
"""Generate Instagram profile-picture options in the poster's visual language.

Instagram crops avatars to a circle and renders them as small as 32px, so every
variant keeps its content well inside the inscribed circle and relies on one
high-contrast shape rather than fine detail.

Usage:  python3 scripts/make_avatar.py [output_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "assets" / "fonts"

SIZE = 1080
BG = (12, 16, 27)
EMERALD = (52, 211, 153)
BLUE = (96, 165, 250)
WHITE = (255, 255, 255)
DARK = (10, 14, 24)

SUPERSAMPLE = 2  # draw large, downscale: cheap anti-aliasing for the ring and text


def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / f"Poppins-{weight}.ttf"), size)


def _canvas() -> Image.Image:
    return Image.new("RGB", (SIZE * SUPERSAMPLE, SIZE * SUPERSAMPLE), BG)


def _finish(image: Image.Image, dest: Path) -> Path:
    image = image.resize((SIZE, SIZE), Image.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest, format="PNG", optimize=True)
    return dest


def variant_monogram(dest: Path) -> Path:
    """Accent-filled circle with a dark monogram. Highest contrast when tiny."""
    s = SIZE * SUPERSAMPLE
    image = _canvas()
    draw = ImageDraw.Draw(image)
    draw.ellipse([0, 0, s, s], fill=EMERALD)
    draw.text((s / 2, s / 2 - s * 0.02), "NN", font=font("Bold", int(s * 0.42)),
              fill=DARK, anchor="mm")
    return _finish(image, dest)


def variant_ring(dest: Path) -> Path:
    """Dark circle, accent ring, light monogram. Reads as a brand mark."""
    s = SIZE * SUPERSAMPLE
    image = _canvas()
    draw = ImageDraw.Draw(image)
    draw.ellipse([0, 0, s, s], fill=BG)
    inset, width = s * 0.055, int(s * 0.035)
    draw.ellipse([inset, inset, s - inset, s - inset], outline=EMERALD, width=width)
    draw.text((s / 2, s / 2 - s * 0.055), "NN", font=font("Bold", int(s * 0.34)),
              fill=WHITE, anchor="mm")
    draw.text((s / 2, s / 2 + s * 0.165), "JOB ALERTS", font=font("SemiBold", int(s * 0.072)),
              fill=EMERALD, anchor="mm")
    return _finish(image, dest)


def variant_split(dest: Path) -> Path:
    """Both accent colours, echoing the GOVT/PRIVATE split the posters use."""
    s = SIZE * SUPERSAMPLE
    image = _canvas()
    glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse([-s * 0.15, -s * 0.15, s * 0.75, s * 0.75], fill=(*EMERALD, 190))
    gdraw.ellipse([s * 0.3, s * 0.35, s * 1.2, s * 1.25], fill=(*BLUE, 190))
    glow = glow.filter(ImageFilter.GaussianBlur(s * 0.09))

    circle = Image.new("RGB", (s, s), BG)
    circle.paste(Image.alpha_composite(circle.convert("RGBA"), glow).convert("RGB"), (0, 0))

    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, s, s], fill=255)
    image.paste(circle, (0, 0), mask)

    draw = ImageDraw.Draw(image)
    draw.text((s / 2, s / 2), "NN", font=font("Bold", int(s * 0.40)), fill=DARK, anchor="mm")
    return _finish(image, dest)


def variant_wordmark(dest: Path) -> Path:
    """No monogram - the name stacked. Clearest for anyone who reads the profile."""
    s = SIZE * SUPERSAMPLE
    image = _canvas()
    draw = ImageDraw.Draw(image)
    draw.ellipse([0, 0, s, s], fill=BG)
    inset = s * 0.045
    draw.ellipse([inset, inset, s - inset, s - inset], outline=BLUE, width=int(s * 0.022))
    draw.text((s / 2, s / 2 - s * 0.10), "NAUKRI", font=font("Bold", int(s * 0.20)),
              fill=WHITE, anchor="mm")
    draw.text((s / 2, s / 2 + s * 0.075), "NOTICE", font=font("Bold", int(s * 0.20)),
              fill=BLUE, anchor="mm")
    draw.rounded_rectangle(
        [s * 0.33, s * 0.70, s * 0.67, s * 0.775], radius=s * 0.04, fill=EMERALD
    )
    return _finish(image, dest)


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "assets" / "avatar"
    for name, builder in (
        ("monogram", variant_monogram),
        ("ring", variant_ring),
        ("split", variant_split),
        ("wordmark", variant_wordmark),
    ):
        print(builder(out / f"avatar-{name}.png"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
