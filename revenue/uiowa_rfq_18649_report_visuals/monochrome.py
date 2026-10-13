"""Remove hue from report SVG paint without rewriting evidence or references.

The package emits hex paint in SVG presentation attributes. Only those actual
attributes are converted; visible text, descriptions, source metadata, element
IDs and local fragment references retain their bytes. The original luminance
calculation and separation report are unchanged.

This converter intentionally rejects unsupported paint syntax, stylesheets and
DTD declarations rather than claiming a complete monochrome export for content
it did not inspect. It is not a universal simulation of printers or vision.
Python 3 standard library only. No network or external entity resolution.
"""
from __future__ import annotations

import re
from xml.parsers import expat

import contrast

_HEX = re.compile(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?\Z")
_PAINT = frozenset(("fill", "stroke", "color", "stop-color", "flood-color",
                    "lighting-color", "solid-color"))
_ATTR = re.compile(rb'''(?<!\S)([A-Za-z_][\w.:-]*)\s*=\s*(["'])(.*?)\2''', re.S)
_LOCAL_PAINT = re.compile(r"url\(\s*#[A-Za-z_][\w:.-]*\s*\)\Z")


class UnsupportedPaint(ValueError):
    """The SVG uses paint this report-specific converter cannot certify."""


def _colour(value: str) -> str | None:
    value = value.strip()
    if _HEX.fullmatch(value):
        return value
    if value.lower() in ("black", "white"):
        return "#000000" if value.lower() == "black" else "#FFFFFF"
    if value in ("none", "currentColor", "inherit") or _LOCAL_PAINT.fullmatch(value):
        return None
    raise UnsupportedPaint(f"unsupported SVG paint {value!r}; use hex presentation attributes")


def _paint_spans(svg_text: str) -> tuple[bytes, list[tuple[int, int, str]]]:
    """Find colour value spans in parsed start tags, never in arbitrary text.

    Expat supplies UTF-8 byte offsets and skips comments/CDATA for this handler.
    The lexical scan is confined to each validated start tag and retains every
    byte outside the changed paint values. It is not a document-wide colour
    substitution. Malformed XML and DTDs fail before any output is produced.
    """
    if not isinstance(svg_text, str):
        raise TypeError("SVG source must be a string")
    raw = svg_text.encode("utf-8")
    parser = expat.ParserCreate(encoding="utf-8")
    spans: list[tuple[int, int, str]] = []
    root_seen = False

    def start(name, attrs):
        nonlocal root_seen
        if not root_seen:
            if name.rsplit(":", 1)[-1] != "svg":
                raise ValueError("expected an SVG document")
            root_seen = True
        if name.rsplit(":", 1)[-1] == "style" or attrs.get("style", "").strip():
            raise UnsupportedPaint("stylesheets and inline CSS are not supported; use presentation attributes")
        begin = parser.CurrentByteIndex
        end = begin
        quote = 0
        while end < len(raw):
            value = raw[end]
            if quote:
                if value == quote:
                    quote = 0
            elif value in (34, 39):
                quote = value
            elif value == 62:
                break
            end += 1
        for match in _ATTR.finditer(raw, begin, end):
            attribute = match.group(1).decode("ascii")
            if attribute not in _PAINT:
                continue
            colour = _colour(attrs[attribute])
            if colour is not None:
                spans.append((match.start(3), match.end(3), colour))

    def reject_doctype(*args):
        raise UnsupportedPaint("DTD declarations are not supported")

    def instruction(target, data):
        if target.lower() == "xml-stylesheet":
            raise UnsupportedPaint("external stylesheets are not supported")

    parser.StartElementHandler = start
    parser.StartDoctypeDeclHandler = reject_doctype
    parser.ProcessingInstructionHandler = instruction
    parser.Parse(raw, True)
    return raw, spans


def to_monochrome(svg_text: str) -> str:
    """Convert supported paint values; preserve all non-paint source bytes."""
    raw, spans = _paint_spans(svg_text)
    pieces = []
    last = 0
    for start, end, colour in spans:
        pieces.extend((raw[last:start], contrast.to_grayscale(colour).encode("ascii")))
        last = end
    pieces.append(raw[last:])
    return b"".join(pieces).decode("utf-8")


def colours_in(svg_text: str) -> list[str]:
    """Distinct supported paint colours, excluding text and fragment IDs."""
    _, spans = _paint_spans(svg_text)
    seen: list[str] = []
    for _, _, colour in spans:
        value = contrast.to_hex(contrast.parse_hex(colour))
        if value not in seen:
            seen.append(value)
    return seen


def is_monochrome(svg_text: str) -> bool:
    """Whether supported paint has no hue; unsupported formats raise."""
    for value in colours_in(svg_text):
        r, g, b = contrast.parse_hex(value)
        if not (r == g == b):
            return False
    return True


def separation_report(fills: dict) -> list[tuple[str, str, float]]:
    """Pairwise monochrome separation for a set of named fills.

    Returned sorted worst-first, because the interesting number is always the
    closest pair, not the average.
    """
    names = list(fills)
    rows: list[tuple[str, str, float]] = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            rows.append((a, b, contrast.grayscale_contrast(fills[a], fills[b])))
    rows.sort(key=lambda row: row[2])
    return rows
