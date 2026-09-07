"""Pure text-layout helpers.

These take a ``measure`` callable rather than a Pillow font so the fiddly
wrapping and size-fitting logic can be unit tested without loading a typeface.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, List, Sequence, Tuple

Measure = Callable[[str], float]

ELLIPSIS = "..."
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class FittedText:
    """The chosen font size and the lines produced at that size."""

    size: int
    lines: List[str]
    truncated: bool


def _break_long_word(word: str, max_width: float, measure: Measure) -> List[str]:
    """Split a word that cannot fit on one line, one character at a time.

    Always consumes at least one character per chunk, so a max_width smaller than
    a single glyph cannot loop forever.
    """
    chunks: List[str] = []
    current = ""
    for char in word:
        candidate = current + char
        if current and measure(candidate) > max_width:
            chunks.append(current)
            current = char
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def wrap_text(text: str, max_width: float, measure: Measure) -> List[str]:
    """Greedily wrap ``text`` so no line exceeds ``max_width``."""
    normalized = _WHITESPACE.sub(" ", (text or "").strip())
    if not normalized:
        return []

    lines: List[str] = []
    current = ""
    for word in normalized.split(" "):
        candidate = f"{current} {word}" if current else word
        if not current or measure(candidate) <= max_width:
            if measure(candidate) <= max_width or not current:
                current = candidate
                if measure(current) > max_width:
                    # A single word wider than the line: break it up.
                    pieces = _break_long_word(current, max_width, measure)
                    lines.extend(pieces[:-1])
                    current = pieces[-1]
                continue
        lines.append(current)
        if measure(word) > max_width:
            pieces = _break_long_word(word, max_width, measure)
            lines.extend(pieces[:-1])
            current = pieces[-1]
        else:
            current = word
    if current:
        lines.append(current)
    return lines


def _truncate(lines: Sequence[str], max_lines: int) -> Tuple[List[str], bool]:
    if len(lines) <= max_lines:
        return list(lines), False
    kept = list(lines[:max_lines])
    last = kept[-1].rstrip()
    kept[-1] = (last[: -len(ELLIPSIS)].rstrip() + ELLIPSIS) if len(last) > len(ELLIPSIS) else last + ELLIPSIS
    return kept, True


def fit_text(
    text: str,
    max_width: float,
    max_lines: int,
    sizes: Sequence[int],
    measure_for: Callable[[int], Measure],
) -> FittedText:
    """Pick the largest size in ``sizes`` whose wrapped text fits ``max_lines``.

    "Fits" is monotonic in font size, so this binary searches rather than trying
    every size. When even the smallest size overflows, the text is truncated with
    an ellipsis instead of spilling off the poster.
    """
    sizes = sorted(sizes)
    if not sizes:
        raise ValueError("fit_text requires at least one candidate size")

    def fits(size: int) -> bool:
        return len(wrap_text(text, max_width, measure_for(size))) <= max_lines

    low, high = 0, len(sizes) - 1
    best = -1
    while low <= high:
        mid = (low + high) // 2
        if fits(sizes[mid]):
            best = mid
            low = mid + 1
        else:
            high = mid - 1

    if best >= 0:
        size = sizes[best]
        return FittedText(size=size, lines=wrap_text(text, max_width, measure_for(size)), truncated=False)

    size = sizes[0]
    lines, truncated = _truncate(wrap_text(text, max_width, measure_for(size)), max_lines)
    return FittedText(size=size, lines=lines, truncated=truncated)


def block_height(line_count: int, size: int, spacing: float) -> int:
    """Pixel height of a wrapped block of ``line_count`` lines."""
    if line_count <= 0:
        return 0
    return int(round(size * spacing * line_count))
