"""A small hand-written SVG writer. No plotting library, by design.

Two reasons this is written out by hand instead of driving matplotlib:
  * Dependency: this package must run on a locked-down machine with the
    standard library and nothing else.
  * Accountability: every glyph, hatch stroke, <title>, <desc> and
    aria attribute in the output is something this package put there
    deliberately and can therefore assert in a test. Nothing accessible is
    left to a library's defaults.

Accessibility mechanics handled here:
  * <svg role="img"> with aria-labelledby pointing at a real <title> and
    <desc>, so assistive technology announces the figure rather than skipping
    an anonymous image.
  * A <desc> that is generated from the same data as the drawing, so the text
    alternative cannot drift away from the picture.
  * Textures declared as <pattern> defs, so the texture channel survives being
    rendered anywhere, including as a plain image.

Python 3 standard library only.
"""

from __future__ import annotations

import math

_TEXT_ESCAPES = (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"))
_ATTR_ESCAPES = _TEXT_ESCAPES + (('"', "&quot;"), ("'", "&apos;"))


def esc_text(value) -> str:
    s = str(value)
    for a, b in _TEXT_ESCAPES:
        s = s.replace(a, b)
    return s


def esc_attr(value) -> str:
    s = str(value)
    for a, b in _ATTR_ESCAPES:
        s = s.replace(a, b)
    return s


def _num(v) -> str:
    """Trim float noise so output is stable and diffable across machines."""
    if isinstance(v, float):
        if v == int(v):
            return str(int(v))
        return f"{v:.3f}".rstrip("0").rstrip(".")
    return str(v)


def attrs(**kwargs) -> str:
    parts = []
    for key, value in kwargs.items():
        if value is None:
            continue
        # single trailing underscore escapes a Python keyword (class_ -> class);
        # every remaining underscore is an SVG/ARIA hyphen (aria_labelledby ->
        # aria-labelledby). Getting this wrong emits aria:labelledby, which
        # assistive technology ignores -- the figure then announces as nothing.
        name = key.rstrip("_").replace("_", "-")
        parts.append(f'{name}="{esc_attr(_num(value))}"')
    return " ".join(parts)


# --------------------------------------------------------------------------
# Primitives
# --------------------------------------------------------------------------
def rect(x, y, w, h, **kw) -> str:
    return f"<rect {attrs(x=x, y=y, width=w, height=h, **kw)}/>"


def line(x1, y1, x2, y2, **kw) -> str:
    return f"<line {attrs(x1=x1, y1=y1, x2=x2, y2=y2, **kw)}/>"


def circle(cx, cy, r, **kw) -> str:
    return f"<circle {attrs(cx=cx, cy=cy, r=r, **kw)}/>"


def polygon(points, **kw) -> str:
    pts = " ".join(f"{_num(x)},{_num(y)}" for x, y in points)
    return f'<polygon points="{pts}" {attrs(**kw)}/>'


def path(d, **kw) -> str:
    return f'<path d="{esc_attr(d)}" {attrs(**kw)}/>'


def text(x, y, content, size=12, fill="#1A1A1A", anchor="start", weight=None,
         family=None, **kw) -> str:
    family = family or "Helvetica Neue, Helvetica, Arial, sans-serif"
    return (
        f"<text {attrs(x=x, y=y, font_size=size, fill=fill, text_anchor=anchor, font_weight=weight, font_family=family, **kw)}>"
        f"{esc_text(content)}</text>"
    )


def group(body, **kw) -> str:
    inner = "".join(body) if isinstance(body, (list, tuple)) else body
    a = attrs(**kw)
    return f"<g {a}>{inner}</g>" if a else f"<g>{inner}</g>"


# --------------------------------------------------------------------------
# Marks. Drawn as real geometry rather than font glyphs: a text glyph depends
# on the reader having a font that covers it, and a printed report should not.
# --------------------------------------------------------------------------
def mark(shape: str, cx: float, cy: float, size: float, fill: str,
         stroke: str | None = None, stroke_width: float = 1.2) -> str:
    """Draw one categorical mark. `size` is the full width of the mark."""
    r = size / 2.0
    stroke = stroke or fill

    if shape == "circle":
        return circle(cx, cy, r, fill=fill, stroke=stroke, stroke_width=stroke_width)
    if shape == "triangle_up":
        return polygon([(cx, cy - r), (cx + r, cy + r * 0.85), (cx - r, cy + r * 0.85)],
                       fill=fill, stroke=stroke, stroke_width=stroke_width,
                       stroke_linejoin="round")
    if shape == "triangle_down":
        return polygon([(cx, cy + r), (cx + r, cy - r * 0.85), (cx - r, cy - r * 0.85)],
                       fill=fill, stroke=stroke, stroke_width=stroke_width,
                       stroke_linejoin="round")
    if shape == "diamond":
        return polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)],
                       fill=fill, stroke=stroke, stroke_width=stroke_width,
                       stroke_linejoin="round")
    if shape == "square":
        return rect(cx - r, cy - r, size, size, fill=fill, stroke=stroke,
                    stroke_width=stroke_width)
    if shape == "bullseye":
        # Open ring plus a centre dot: reads as "something is here but we cannot
        # place it", visibly different from the solid circle used for a rating.
        return (circle(cx, cy, r, fill="none", stroke=stroke, stroke_width=stroke_width * 1.6)
                + circle(cx, cy, max(1.0, r * 0.3), fill=stroke))
    if shape == "dash":
        # Deliberately off-scale looking: a flat bar, no area, no position on a
        # ramp. Nothing about it suggests "low".
        return rect(cx - r, cy - max(1.2, r * 0.26), size, max(2.4, r * 0.52),
                    fill=stroke, stroke="none", rx=1)
    if shape == "slash_circle":
        # The international "does not apply" mark. Semantically distinct from
        # "we do not know": this cell was never a question for this group.
        return (circle(cx, cy, r, fill="none", stroke=stroke, stroke_width=stroke_width * 1.6)
                + line(cx - r * 0.7, cy + r * 0.7, cx + r * 0.7, cy - r * 0.7,
                       stroke=stroke, stroke_width=stroke_width * 1.6))
    if shape == "opposed":
        # Two triangles pointing at each other: two readings of the same thing,
        # both retained. Reads as a conflict, not as an absence.
        return (polygon([(cx - r, cy - r), (cx - r, cy + r), (cx - r * 0.15, cy)],
                        fill=fill, stroke=stroke, stroke_width=stroke_width)
                + polygon([(cx + r, cy - r), (cx + r, cy + r), (cx + r * 0.15, cy)],
                          fill=fill, stroke=stroke, stroke_width=stroke_width))
    if shape in ("pentagon", "hexagon"):
        n = 5 if shape == "pentagon" else 6
        start = -math.pi / 2
        pts = [(cx + r * math.cos(start + 2 * math.pi * i / n),
                cy + r * math.sin(start + 2 * math.pi * i / n)) for i in range(n)]
        return polygon(pts, fill=fill, stroke=stroke, stroke_width=stroke_width,
                       stroke_linejoin="round")
    raise ValueError(f"unknown mark shape {shape!r}")


KNOWN_SHAPES = ("circle", "triangle_up", "triangle_down", "diamond", "square",
                "bullseye", "dash", "pentagon", "hexagon", "slash_circle", "opposed")


# --------------------------------------------------------------------------
# Textures
# --------------------------------------------------------------------------
KNOWN_TEXTURES = ("solid", "lines_horizontal", "dots", "diagonal_45",
                  "diagonal_135", "crosshatch", "checker", "split_diagonal")


def pattern_def(pid: str, texture: str, fill: str, ink: str, weight: float = 1.2) -> str:
    """One <pattern>: the band's fill, with its texture struck over it."""
    if texture == "solid":
        return (f'<pattern {attrs(id=pid, width=8, height=8, patternUnits="userSpaceOnUse")}>'
                f'{rect(0, 0, 8, 8, fill=fill)}</pattern>')
    if texture == "lines_horizontal":
        body = rect(0, 0, 8, 8, fill=fill) + line(0, 4, 8, 4, stroke=ink, stroke_width=weight)
    elif texture == "dots":
        body = (rect(0, 0, 8, 8, fill=fill)
                + circle(2, 2, weight, fill=ink) + circle(6, 6, weight, fill=ink))
    elif texture == "diagonal_45":
        body = (rect(0, 0, 8, 8, fill=fill)
                + path("M0,8 L8,0", stroke=ink, stroke_width=weight)
                + path("M-2,2 L2,-2", stroke=ink, stroke_width=weight)
                + path("M6,10 L10,6", stroke=ink, stroke_width=weight))
    elif texture == "diagonal_135":
        # Opposite lean and wider spacing than diagonal_45 on purpose: two
        # hatches at the same angle read as the same texture at a distance.
        body = (rect(0, 0, 8, 8, fill=fill)
                + path("M0,0 L8,8", stroke=ink, stroke_width=weight))
    elif texture == "checker":
        body = (rect(0, 0, 8, 8, fill=fill)
                + rect(0, 0, 4, 4, fill=ink) + rect(4, 4, 4, 4, fill=ink))
    elif texture == "split_diagonal":
        # Bold alternating bands, not fine hatching: this state must stay loud
        # when the figure is scaled down or exported to monochrome, because a
        # conflict in the evidence is the most informative cell on the page.
        body = (rect(0, 0, 8, 8, fill=fill)
                + polygon([(0, 8), (8, 0), (8, 4), (4, 8)], fill=ink)
                + polygon([(0, 0), (4, 0), (0, 4)], fill=ink))
    elif texture == "crosshatch":
        body = (rect(0, 0, 8, 8, fill=fill)
                + path("M0,8 L8,0", stroke=ink, stroke_width=weight * 0.9)
                + path("M0,0 L8,8", stroke=ink, stroke_width=weight * 0.9))
    else:
        raise ValueError(f"unknown texture {texture!r}")
    return (f'<pattern {attrs(id=pid, width=8, height=8, patternUnits="userSpaceOnUse")}>'
            f"{body}</pattern>")


ARROW_MARKER_ID = "dependency-arrow"


def arrow_marker(colour: str) -> str:
    return (f'<marker {attrs(id=ARROW_MARKER_ID, viewBox="0 0 10 10", refX=9, refY=5, markerWidth=7, markerHeight=7, orient="auto-start-reverse")}>'
            f'{path("M0,0 L10,5 L0,10 z", fill=colour)}</marker>')


# --------------------------------------------------------------------------
# Document
# --------------------------------------------------------------------------
def bordered_rect(x, y, w, h, fill, stroke, weight, style="solid", rx=3) -> str:
    """One box with a border whose STYLE carries meaning.

        solid   a value we have
        dashed  a value we do not have
        double  more than one value, both retained

    The style is a channel in its own right: it survives monochrome export and
    it survives a reader who cannot resolve the fill texture at small sizes.
    """
    if style == "solid":
        return rect(x, y, w, h, fill=fill, stroke=stroke, stroke_width=weight, rx=rx)
    if style == "dashed":
        return rect(x, y, w, h, fill=fill, stroke=stroke, stroke_width=weight,
                    stroke_dasharray="5 3", rx=rx)
    if style == "double":
        inset = max(2.5, weight * 2)
        return (rect(x, y, w, h, fill=fill, stroke=stroke, stroke_width=weight, rx=rx)
                + rect(x + inset, y + inset, w - 2 * inset, h - 2 * inset, fill="none",
                       stroke=stroke, stroke_width=max(0.9, weight * 0.7),
                       rx=max(1, rx - 1)))
    raise ValueError(f"unknown border style {style!r}")


KNOWN_BORDERS = ("solid", "dashed", "double")


class Figure:
    """An SVG document that always carries its own text alternative."""

    def __init__(self, width: int, height: int, title: str, description: str,
                 background: str = "#FFFFFF", slug: str = "figure") -> None:
        self.width = width
        self.height = height
        self.title = title
        self.description = description
        self.background = background
        self.slug = slug
        self._defs: list[str] = []
        self._def_ids: set[str] = set()
        self._body: list[str] = []

    def add(self, markup: str) -> None:
        self._body.append(markup)

    def add_all(self, markup_list) -> None:
        self._body.extend(markup_list)

    def add_def(self, def_id: str, markup: str) -> str:
        """Register a def once. Returns the id, so callers can url(#id) it."""
        if def_id not in self._def_ids:
            self._def_ids.add(def_id)
            self._defs.append(markup)
        return def_id

    def texture_fill(self, key: str, texture: str, fill: str, ink: str,
                     weight: float = 1.2) -> str:
        """Register the pattern for one band/kind and return its paint value."""
        if texture == "solid":
            return fill  # no pattern needed; keeps the output smaller and simpler
        pid = f"{self.slug}-tex-{key}"
        self.add_def(pid, pattern_def(pid, texture, fill, ink, weight))
        return f"url(#{pid})"

    def render(self) -> str:
        tid = f"{self.slug}-title"
        did = f"{self.slug}-desc"
        head = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'{attrs(width=self.width, height=self.height, viewBox=f"0 0 {self.width} {self.height}", role="img", aria_labelledby=f"{tid} {did}")}>'
        )
        parts = [
            head,
            f'<title id="{tid}">{esc_text(self.title)}</title>',
            f'<desc id="{did}">{esc_text(self.description)}</desc>',
        ]
        if self._defs:
            parts.append("<defs>" + "".join(self._defs) + "</defs>")
        parts.append(rect(0, 0, self.width, self.height, fill=self.background))
        parts.extend(self._body)
        parts.append("</svg>")
        return "\n".join(parts) + "\n"
