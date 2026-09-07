"""Cosmetic clean-up of job titles from third-party feeds.

Employers type titles into free-text boxes, so they arrive with stray spacing and
inconsistent dashes that look like rendering bugs once set in 90pt type.

This module only fixes *punctuation and whitespace*. It deliberately never
corrects spelling or rewords anything: the title is the employer's own wording,
and silently editing it would misrepresent the listing.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

_WHITESPACE = re.compile(r"\s+")
# A dash with whitespace on exactly one side is being used as a separator, not as
# a compound hyphen - "Manager- Return" rather than "Full-Stack".
_LOPSIDED_DASH = re.compile(r"(?<=\S)\s+[-–—](?=\S)|(?<=\S)[-–—]\s+(?=\S)")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,;:!?])")
# Only insert a space after a comma when the next character is a letter, so
# decimals and thousands separators are untouched.
_MISSING_SPACE_AFTER_COMMA = re.compile(r"([,;:])(?=[^\s\d])")
_EDGE_SEPARATORS = re.compile(r"^[\s\-–—,;:|/]+|[\s\-–—,;:|/]+$")
_TRAILING_STOP = re.compile(r"(?<![.\d])\.$")


def tidy_title(title: Optional[str]) -> str:
    """Normalise spacing and punctuation in a job title.

    Returns the empty string for blank input.
    """
    if not title:
        return ""

    text = unicodedata.normalize("NFKC", str(title))
    text = _WHITESPACE.sub(" ", text).strip()
    if not text:
        return ""

    text = _LOPSIDED_DASH.sub(" - ", text)
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = _MISSING_SPACE_AFTER_COMMA.sub(r"\1 ", text)
    text = _WHITESPACE.sub(" ", text)
    text = _EDGE_SEPARATORS.sub("", text)
    # A single trailing full stop reads as a typo in a headline; "..." is intentional.
    text = _TRAILING_STOP.sub("", text)
    return text.strip()
