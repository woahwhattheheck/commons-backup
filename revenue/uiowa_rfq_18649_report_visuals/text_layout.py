"""Content-sized SVG text without character truncation.

The layout deliberately budgets a full em for an ordinary code point (two
for East Asian wide/fullwidth characters). This is conservative for the
package's Helvetica/Arial/sans-serif stack; it is not a claim about every
installed font. Browser measurement and visual inspection remain necessary.
Only line breaks are introduced. No source words are shortened or discarded.
"""
from __future__ import annotations

import html
import math
import unicodedata

FONT_FAMILY = "Helvetica Neue, Helvetica, Arial, sans-serif"
LEADING = 1.4


def _positive(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a finite positive number")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite positive number")
    return float(value)


def _units(char: str) -> int:
    if char == "\t":
        return 8
    if unicodedata.combining(char) or char in ("\u200d", "\ufe0f"):
        return 0
    return 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1


def wrap_text(value: str, width: float, size: float) -> tuple[str, ...]:
    """Return complete lines, retaining spaces and splitting only as needed.

    Newlines are represented by actual line breaks. Other whitespace is kept
    in the line text. Long uninterrupted identifiers are broken across lines,
    without an ellipsis or invented hyphen. The exact original remains on the
    enclosing group for comparison, and all its characters remain visible.
    """
    if not isinstance(value, str):
        raise TypeError("text must be a string")
    width = _positive(width, "width")
    size = _positive(size, "size")
    if width < size:
        raise ValueError("text column is narrower than one ordinary character")
    capacity = int(width // size)
    result: list[str] = []
    # Normalize newline spelling only. Deliberately do not strip the text.
    for paragraph in value.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if not paragraph:
            result.append("")
            continue
        remaining = paragraph
        while remaining:
            used = 0
            end = 0
            boundary = 0
            for i, char in enumerate(remaining):
                units = _units(char)
                if end and used + units > capacity:
                    break
                if not end and units > capacity:
                    raise ValueError("text column is narrower than one wide character")
                used += units
                end = i + 1
                if char.isspace():
                    boundary = end
            if end == len(remaining):
                result.append(remaining)
                break
            # Keep a whole word when a preceding whitespace boundary exists.
            cut = boundary if boundary and remaining[:boundary].strip() else end
            result.append(remaining[:cut])
            remaining = remaining[cut:]
    return tuple(result)


def text_height(value: str, width: float, size: float) -> float:
    return len(wrap_text(value, width, size)) * size * LEADING


def _attr(value: object) -> str:
    return (html.escape(str(value), quote=True).replace("\n", "&#10;")
            .replace("\r", "&#13;").replace("\t", "&#9;"))


def text_block(x: float, y: float, value: str, width: float, size: float,
               fill: str, weight: str | None = None) -> tuple[str, float]:
    """SVG markup plus bottom coordinate; x/y identify the top-left corner."""
    lines = wrap_text(value, width, size)
    attrs = (f'data-text-layout="full" data-source-text="{_attr(value)}" '
             f'data-layout-x="{x:g}" data-layout-y="{y:g}" '
             f'data-layout-width="{width:g}" '
             f'data-layout-height="{len(lines) * size * LEADING:g}"')
    parts = [f"<g {attrs}>"]
    for index, line in enumerate(lines):
        baseline = y + size + index * size * LEADING
        bold = f' font-weight="{_attr(weight)}"' if weight else ""
        parts.append(
            f'<text x="{x:g}" y="{baseline:g}" font-size="{size:g}" '
            f'fill="{_attr(fill)}" font-family="{_attr(FONT_FAMILY)}"{bold} '
            f'xml:space="preserve">{html.escape(line, quote=False)}</text>')
    parts.append("</g>")
    return "".join(parts), y + len(lines) * size * LEADING


def add_text(fig, x: float, y: float, value: str, width: float, size: float,
             fill: str, weight: str | None = None) -> float:
    markup, bottom = text_block(x, y, value, width, size, fill, weight)
    fig.add(markup)
    return bottom
