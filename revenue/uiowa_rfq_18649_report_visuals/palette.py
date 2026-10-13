"""The report's visual vocabulary, and the rules that keep it readable.

DESIGN CONTRACT -- every one of these is asserted in test_report_visuals.py:

 1. NO MEANING LIVES IN COLOUR ALONE. Each assessment band carries four
    independent channels: a fill colour, a drawn SHAPE, a fill TEXTURE, and a
    written LABEL. Remove any one (colour-blind reader, monochrome printer,
    low-resolution projector that flattens fine hatching, screen reader that
    sees only text) and the remaining channels still say which band it is.

 2. AN UNASSESSED CELL IS NOT A LOW RATING. This is the requirement the whole
    module is built around. "Gap" is a finding about the group. "Not assessed"
    is a statement about OUR evidence, and "Insufficient evidence" is a third,
    different thing again. So the two non-rating states are pulled OFF the
    ordinal scale entirely (`rank is None`), given a dashed border no rating
    ever uses, given their own shapes and textures, and -- measured, not
    asserted -- kept at least 3:1 apart from every rating fill AFTER the colour
    is stripped out. They are excluded from every count of ratings.

 3. GROUP IDENTITY NEVER RIDES ON COLOUR. Measured fact, not a guess: the three
    group colours below land within 1.03:1 -- 1.15:1 of each other in
    grayscale, i.e. indistinguishable on a monochrome print. They are kept
    because they help a sighted reader scan, and they are treated as decorative.
    Group identity is carried by a distinct SHAPE and by the group's code
    printed next to every mark. `GROUP_COLOUR_IS_DECORATIVE` records this so
    nobody later promotes it to load-bearing by accident.

 4. NO PRECISE INSTITUTIONAL SCORES. Bands are named ordinal categories, never
    numbers. `rank` exists to order lanes on an axis; it is deliberately not
    exported to any label, table cell or alt text, and nothing in this package
    averages it. A "3.25 out of 5" for a university department would be a
    made-up precision this evidence cannot support.

Python 3 standard library only.
"""

from __future__ import annotations

import contrast

# --------------------------------------------------------------------------
# Themes. Fills are shared across themes (both backgrounds were measured);
# only page furniture and stroke weights change.
# --------------------------------------------------------------------------
THEMES = {
    "print": {
        "background": "#FFFFFF",
        "ink": "#1A1A1A",
        "muted": "#4A4A45",
        "rule": "#6B6B66",
        # Print loses fine hatching, so strokes are heavier here.
        "hatch_weight": 1.4,
        "border_weight": 1.6,
    },
    "screen": {
        "background": "#FAFAF8",
        "ink": "#1F2124",
        "muted": "#55554F",
        "rule": "#6B6B66",
        "hatch_weight": 1.0,
        "border_weight": 1.3,
    },
}
DEFAULT_THEME = "print"


class Band:
    """One assessment band and every channel that encodes it."""

    __slots__ = ("key", "rank", "label", "glyph", "shape", "texture", "border",
                 "fill", "ink", "texture_ink", "border_ink", "meaning")

    def __init__(self, key, rank, label, glyph, shape, texture, border,
                 fill, ink, texture_ink, border_ink, meaning):
        self.key = key
        self.rank = rank
        self.label = label
        self.glyph = glyph
        self.shape = shape
        self.texture = texture
        self.border = border
        self.fill = fill
        self.ink = ink
        self.texture_ink = texture_ink
        self.border_ink = border_ink
        self.meaning = meaning

    @property
    def on_scale(self) -> bool:
        """True for a rating, False for 'we cannot or did not rate this'."""
        return self.rank is not None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Band {self.key} rank={self.rank}>"


# Ordinal ratings. rank orders lanes on a chart axis and NOTHING else.
# Non-ordinal states carry rank=None so arithmetic on them raises rather than
# quietly producing a number.
BANDS: dict[str, Band] = {
    "STRENGTH": Band(
        "STRENGTH", 4, "Strength", "▲", "triangle_up", "solid", "solid",
        "#10505E", "#FFFFFF", "#FFFFFF", "#0A3A45",
        "Evidence from more than one source shows the practice working consistently.",
    ),
    "ESTABLISHED": Band(
        "ESTABLISHED", 3, "Established", "●", "circle", "lines_horizontal", "solid",
        "#2F6A93", "#FFFFFF", "#FFFFFF", "#1E4A68",
        "The practice is in place and evidenced, with named exceptions.",
    ),
    "DEVELOPING": Band(
        "DEVELOPING", 2, "Developing", "◆", "diamond", "dots", "solid",
        "#8F6510", "#FFFFFF", "#FFFFFF", "#63460B",
        "The practice exists but is applied inconsistently across the evidence seen.",
    ),
    "GAP": Band(
        "GAP", 1, "Gap", "▼", "triangle_down", "diagonal_45", "solid",
        "#9C3016", "#FFFFFF", "#FFFFFF", "#6D220F",
        "Evidence shows the practice is absent or not working where it is needed.",
    ),
    # ---- below this line: NOT ratings. Different question, different answer. ----
    "INSUFFICIENT_EVIDENCE": Band(
        "INSUFFICIENT_EVIDENCE", None, "Insufficient evidence", "◎", "bullseye",
        "crosshatch", "dashed",
        "#D8D8D4", "#1A1A1A", "#5E5E5A", "#5E5E5A",
        "We looked in this area and what we received did not support any rating.",
    ),
    "UNASSESSED": Band(
        "UNASSESSED", None, "Not assessed", "—", "dash", "diagonal_135", "dashed",
        "#EFEFEC", "#1A1A1A", "#7A7A74", "#6B6B66",
        "This area was outside the agreed scope for this group. It is not a rating.",
    ),
    "NOT_APPLICABLE": Band(
        # Different question from "not assessed". This one is a fact about the
        # GROUP's context -- the practice does not apply to them -- not a fact
        # about our evidence. Collapsing the two tells a reader we failed to
        # look at something that was never there to look at.
        "NOT_APPLICABLE", None, "Not applicable", "⊘", "slash_circle", "checker", "dashed",
        "#E4E4DE", "#1A1A1A", "#7A7A73", "#5F5F59",
        "This practice does not apply to how this group operates. Nothing is missing.",
    ),
    "CONTRADICTORY": Band(
        # The most informative cell on the page and the easiest to lose.
        # Averaging it invents a confident middle value; dropping it produces
        # silence. It gets the loudest texture and the only double border.
        "CONTRADICTORY", None, "Sources disagree", "≠", "opposed", "split_diagonal", "double",
        "#EDE4D2", "#1A1A1A", "#6B4F16", "#6B4F16",
        "Two or more sources give different answers. Both readings are kept, unreconciled.",
    ),
}

ORDINAL_KEYS = ("STRENGTH", "ESTABLISHED", "DEVELOPING", "GAP")
# Everything here answers a DIFFERENT question from "how good is this?".
# None of them may be ranked, counted or averaged as a low rating.
NON_RATING_KEYS = ("INSUFFICIENT_EVIDENCE", "UNASSESSED", "NOT_APPLICABLE",
                   "CONTRADICTORY")
BAND_ORDER = ORDINAL_KEYS + NON_RATING_KEYS


def band(key: str) -> Band:
    """Look up a band, refusing to guess. An unknown band must never silently
    become a default -- that is how an absent input turns into a fake rating."""
    try:
        return BANDS[key]
    except KeyError:
        raise KeyError(
            f"unknown assessment band {key!r}; known bands: {', '.join(BAND_ORDER)}"
        ) from None


# --------------------------------------------------------------------------
# Groups. Shape + printed code carry identity; colour is decorative.
# --------------------------------------------------------------------------
GROUP_COLOUR_IS_DECORATIVE = True
GROUP_SHAPES = ("square", "pentagon", "hexagon")
GROUP_COLOURS = ("#1F4E79", "#7A3E8F", "#1F6B4B")


def group_style(index: int) -> dict:
    """Cycle the group vocabulary. Shape first, colour second."""
    return {
        "shape": GROUP_SHAPES[index % len(GROUP_SHAPES)],
        "colour": GROUP_COLOURS[index % len(GROUP_COLOURS)],
    }


# --------------------------------------------------------------------------
# Evidence kinds (the coverage chart) and roadmap phases. Same rule: texture
# and label do the work, colour assists.
# --------------------------------------------------------------------------
EVIDENCE_KINDS = (
    {"key": "documents", "label": "Documents reviewed", "short": "Doc",
     "texture": "solid", "fill": "#2F6A93", "ink": "#FFFFFF"},
    {"key": "interviews", "label": "Interviews", "short": "Int",
     "texture": "dots", "fill": "#8F6510", "ink": "#FFFFFF"},
    {"key": "system_records", "label": "System records", "short": "Sys",
     "texture": "diagonal_45", "fill": "#10505E", "ink": "#FFFFFF"},
    {"key": "observed", "label": "Observed artifacts", "short": "Obs",
     "texture": "crosshatch", "fill": "#1F6B4B", "ink": "#FFFFFF"},
)
EVIDENCE_KEYS = tuple(k["key"] for k in EVIDENCE_KINDS)


def evidence_kind(key: str) -> dict:
    for k in EVIDENCE_KINDS:
        if k["key"] == key:
            return k
    raise KeyError(f"unknown evidence kind {key!r}; known: {', '.join(EVIDENCE_KEYS)}")


# --------------------------------------------------------------------------
# Value states, for counts rather than bands.
#
# The distinction this exists for: a measured ZERO is a real finding ("zero
# unresolved items") and often a good one. If zero draws as an empty bar it is
# indistinguishable from "we never recorded this", and a strength is silently
# filed as a hole. So zero gets a visible token with a SOLID border -- the same
# border language the ratings use, because it is a value we have -- and an
# unrecorded count gets a dashed one.
# --------------------------------------------------------------------------
NOT_RECORDED = "NOT_RECORDED"

VALUE_STATES = {
    "MEASURED_ZERO": {
        "label": "0", "long_label": "Measured zero", "border": "solid",
        "fill": "#FFFFFF", "ink": "#1A1A1A", "border_ink": "#1A1A1A",
        "meaning": "A real count of zero. This is a value, not a missing entry.",
    },
    "NOT_RECORDED": {
        "label": "not recorded", "long_label": "Not recorded", "border": "dashed",
        "fill": "#EFEFEC", "ink": "#1A1A1A", "border_ink": "#6B6B66",
        "meaning": "No count was supplied for this kind. It is not zero.",
    },
}


PHASES = (
    {"key": "P1", "label": "0-90 days", "badge": "1", "texture": "solid",
     "fill": "#10505E", "ink": "#FFFFFF"},
    {"key": "P2", "label": "90-180 days", "badge": "2", "texture": "lines_horizontal",
     "fill": "#2F6A93", "ink": "#FFFFFF"},
    {"key": "P3", "label": "180+ days", "badge": "3", "texture": "dots",
     "fill": "#8F6510", "ink": "#FFFFFF"},
)
PHASE_KEYS = tuple(p["key"] for p in PHASES)

# An estimate we do not have. Drawn with the same not-a-rating vocabulary as an
# unassessed cell: dashed edge, neutral fill, spelled out. Never a zero-length
# bar (invisible) and never a guessed length (a lie).
UNKNOWN_EFFORT = {
    "label": "Effort not estimated",
    "texture": "diagonal_135",
    "fill": "#EFEFEC",
    "ink": "#1A1A1A",
    "border_ink": "#6B6B66",
}


def phase(key: str) -> dict:
    for p in PHASES:
        if p["key"] == key:
            return p
    raise KeyError(f"unknown roadmap phase {key!r}; known: {', '.join(PHASE_KEYS)}")


# --------------------------------------------------------------------------
# The audit. Everything above is measured here; the test suite runs this and
# fails on any FAIL row, so a bad colour cannot reach a reader.
# --------------------------------------------------------------------------
def audit_palette(theme_name: str = DEFAULT_THEME) -> list[contrast.CheckResult]:
    theme = THEMES[theme_name]
    bg = theme["background"]
    out: list[contrast.CheckResult] = []

    out.append(contrast.check(f"{theme_name}: body text", "text", theme["ink"], bg,
                              contrast.TEXT_MIN))
    out.append(contrast.check(f"{theme_name}: secondary text", "text", theme["muted"], bg,
                              contrast.TEXT_MIN))
    out.append(contrast.check(f"{theme_name}: axis rule", "graphical", theme["rule"], bg,
                              contrast.GRAPHICAL_MIN))

    for key in BAND_ORDER:
        b = BANDS[key]
        # Text written on the swatch itself.
        out.append(contrast.check(f"{key}: label on fill", "text", b.ink, b.fill,
                                  contrast.TEXT_MIN))
        # The texture strokes must be visible on their own fill, or the texture
        # channel silently disappears and we are back to colour-only.
        out.append(contrast.check(f"{key}: texture on fill", "graphical", b.texture_ink,
                                  b.fill, contrast.GRAPHICAL_MIN))
        # The border must be visible against the page. This is what keeps a
        # near-white "not assessed" cell from reading as a printing error.
        out.append(contrast.check(f"{key}: border on page", "graphical", b.border_ink, bg,
                                  contrast.GRAPHICAL_MIN))

    # THE load-bearing requirement: after colour is removed, every not-a-rating
    # state stays clearly apart from every rating.
    for nr in NON_RATING_KEYS:
        for rating in ORDINAL_KEYS:
            out.append(contrast.check_grayscale(
                f"{nr} vs {rating} (no colour)", BANDS[nr].fill, BANDS[rating].fill))

    # The conflict stripe must survive monochrome, or the loudest state on the
    # page goes quiet exactly where it matters most.
    contra = BANDS["CONTRADICTORY"]
    out.append(contrast.check_grayscale("CONTRADICTORY: stripe vs its own fill",
                                        contra.texture_ink, contra.fill,
                                        contrast.GRAPHICAL_MIN))

    for state in VALUE_STATES.values():
        out.append(contrast.check(f"value/{state['long_label']}: text on token", "text",
                                  state["ink"], state["fill"], contrast.TEXT_MIN))
        out.append(contrast.check(f"value/{state['long_label']}: border on page", "graphical",
                                  state["border_ink"], bg, contrast.GRAPHICAL_MIN))

    for kind in EVIDENCE_KINDS:
        out.append(contrast.check(f"evidence/{kind['key']}: count on segment", "text",
                                  kind["ink"], kind["fill"], contrast.TEXT_MIN))
        out.append(contrast.check(f"evidence/{kind['key']}: segment on page", "graphical",
                                  kind["fill"], bg, contrast.GRAPHICAL_MIN))

    for p in PHASES:
        out.append(contrast.check(f"phase/{p['key']}: badge text", "text", p["ink"],
                                  p["fill"], contrast.TEXT_MIN))

    for i, colour in enumerate(GROUP_COLOURS):
        out.append(contrast.check(f"group[{i}] mark on page", "graphical", colour, bg,
                                  contrast.GRAPHICAL_MIN))

    return out


def failures(theme_name: str = DEFAULT_THEME) -> list[contrast.CheckResult]:
    return [r for r in audit_palette(theme_name) if not r.ok]
