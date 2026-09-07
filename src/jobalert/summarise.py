"""Turns a source's job description into a short plain-text summary.

Descriptions arrive as HTML fragments of wildly varying length. Captions are
capped at 2,200 characters and nobody reads a wall of text on Instagram, so this
strips markup and keeps the opening couple of sentences.
"""
from __future__ import annotations

import html
import re
import unicodedata
from typing import Optional

MAX_SUMMARY_LEN = 240
ELLIPSIS = "..."

_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")
# Boilerplate that adds nothing on a poster caption.
_BOILERPLATE = re.compile(
    r"^\s*(job\s+description|description|about\s+the\s+role|overview)\s*[:\-]\s*", re.I
)


def summarise(description: Optional[str], limit: int = MAX_SUMMARY_LEN) -> Optional[str]:
    """Return a short plain-text summary, or None when there is nothing useful."""
    if not description:
        return None

    text = html.unescape(_TAG.sub(" ", str(description)))
    text = unicodedata.normalize("NFKC", text)
    text = _WHITESPACE.sub(" ", text).strip()
    text = _BOILERPLATE.sub("", text).strip()
    if len(text) < 30:
        # Too short to say anything; better to omit the line entirely.
        return None

    if len(text) <= limit:
        return text

    # Prefer cutting at a sentence end, then a word, before hard-truncating.
    window = text[: limit + 1]
    sentence_end = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
    if sentence_end >= limit // 2:
        return window[: sentence_end + 1].strip()
    space = window.rfind(" ")
    cut = space if space >= limit // 2 else limit
    return text[:cut].rstrip(" ,;:-") + ELLIPSIS
