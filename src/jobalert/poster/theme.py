"""Every visual constant for the poster lives here.

Keeping the palette and metrics in one module means restyling the account is a
single-file change, and nothing downstream carries a magic number.
"""
from __future__ import annotations

from typing import Dict, Tuple

from jobalert.models import Category

RGB = Tuple[int, int, int]

# 1080x1350 is 4:5, the tallest ratio Instagram shows uncropped in the feed -
# the most screen real estate a single image can occupy.
CANVAS: Tuple[int, int] = (1080, 1350)
MARGIN = 80
CONTENT_WIDTH = CANVAS[0] - 2 * MARGIN

BACKGROUND: RGB = (12, 16, 27)
SURFACE: RGB = (22, 29, 45)
TEXT: RGB = (255, 255, 255)
TEXT_MUTED: RGB = (141, 156, 180)
TEXT_ON_ACCENT: RGB = (10, 14, 24)

ACCENTS: Dict[Category, RGB] = {
    Category.GOVERNMENT: (52, 211, 153),  # emerald
    Category.PRIVATE: (96, 165, 250),  # blue
}

ACCENT_BAR_HEIGHT = 14
GLOW_BLUR = 110
PILL_HEIGHT = 56
PILL_RADIUS = 28
PILL_PADDING_X = 30
STRIP_HEIGHT = 118
STRIP_RADIUS = 24
DIVIDER_COLOR: RGB = (38, 48, 70)

# Font sizes the title is allowed to take, largest that fits wins.
TITLE_SIZES = range(46, 99, 2)
TITLE_MAX_LINES = 4
TITLE_LINE_SPACING = 1.16

ORG_SIZES = range(28, 47, 2)
ORG_MAX_LINES = 2
ORG_LINE_SPACING = 1.22

LABEL_SIZE = 21
LABEL_TRACKING = 3.0
VALUE_SIZE = 34
VALUE_MAX_LINES = 2
META_LINE_SPACING = 1.25

PILL_TEXT_SIZE = 26
DATE_TEXT_SIZE = 26
STRIP_TEXT_SIZE = 40
FOOTER_SIZE = 30
FOOTER_NOTE_SIZE = 22
BIO_NOTE_SIZE = 25

GAP_SM = 16
GAP_MD = 30
GAP_LG = 52

HEADER_TOP = 78
TITLE_TOP = 236
FOOTER_BOTTOM_INSET = 62


def accent_for(category: Category) -> RGB:
    """Accent colour for a category, falling back to the private-sector blue."""
    return ACCENTS.get(category, ACCENTS[Category.PRIVATE])
