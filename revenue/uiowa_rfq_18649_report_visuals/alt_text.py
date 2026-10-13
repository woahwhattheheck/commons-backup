"""Plain-text alternatives, generated from the same data that draws the figure.

Why generation rather than a hand-written caption: a hand-written alt text is
correct on the day it is written and wrong the first time the data changes.
Every function here reads the same `Matrix` the figure reads, so the two cannot
disagree. figures.py calls these to fill each SVG's <desc>, which means the
accessible description and the picture are produced from one source.

Two rules the text keeps that a careless summary would lose:
  * Never say "not assessed" in a way that implies a poor result. The phrasing
    is always about the review's evidence, not the group's performance.
  * Never state an average band or a score. Counts only.

Also produces the TABLE templates -- Markdown and plain text -- carrying the
same glyph + label redundancy as the charts, so the report's tabular version is
not a second-class citizen.

Python 3 standard library only.
"""

from __future__ import annotations

import palette

FICTION_PREFIX = "SYNTHETIC EXAMPLE - not a University finding."


def _cell_phrase(cell) -> str:
    if cell is None:
        return "no record supplied"
    b = cell.band
    if b.key == "UNASSESSED":
        return "not assessed (outside the agreed scope for this group)"
    if b.key == "INSUFFICIENT_EVIDENCE":
        return (f"insufficient evidence ({cell.evidence_total} items collected, "
                f"not enough to support a rating)")
    if b.key == "NOT_APPLICABLE":
        return ("not applicable (this practice does not apply to how this group "
                "operates; nothing is missing)")
    if b.key == "CONTRADICTORY":
        readings = "; ".join(f"{r['source']} says {r['says']}" for r in cell.conflict)
        return (f"sources disagree, no single rating is supportable - {readings}. "
                f"Both readings are kept unreconciled")
    return f"{b.label.lower()} ({cell.evidence_total} evidence items)"


def matrix_alt(matrix) -> str:
    t = matrix.totals()
    lines = [
        f"{matrix.disclaimer}",
        f"Assessment matrix: {len(matrix.group_ids)} groups by {len(matrix.area_ids)} "
        f"assessment areas, {t['cells_expected']} cells.",
        f"{t['rated']} cells carry a rating; {t['insufficient_evidence']} had insufficient "
        f"evidence; {t['not_assessed']} were not assessed; {t['not_applicable']} do not apply "
        f"to that group; {t['contradictory']} have sources that disagree"
        + (f"; {t['cells_missing']} have no record supplied." if t["cells_missing"] else "."),
        "Unrated cells describe the evidence available to this review, not the performance "
        "of the group, and are excluded from every count of ratings.",
    ]
    for gid in matrix.group_ids:
        parts = []
        for aid in matrix.area_ids:
            parts.append(f"{matrix.area_label(aid)}: {_cell_phrase(matrix.cell(gid, aid))}")
        lines.append(f"{matrix.group_label(gid)} ({gid}) - " + "; ".join(parts) + ".")
    return " ".join(lines)


def cross_group_alt(matrix) -> str:
    lines = [
        matrix.disclaimer,
        "Comparison across groups. Each assessment area is a column; each rating is a "
        "horizontal lane, strongest at the top. Two further lanes sit below a dividing rule: "
        "insufficient evidence, and not assessed. Those two are not lower ratings - they are "
        "statements about the evidence this review holds.",
    ]
    for aid in matrix.area_ids:
        by_band: dict[str, list[str]] = {}
        for gid in matrix.group_ids:
            cell = matrix.cell(gid, aid)
            key = cell.band_key if cell is not None else "NO_RECORD"
            by_band.setdefault(key, []).append(gid)
        parts = []
        for key in palette.BAND_ORDER + ("NO_RECORD",):
            if key in by_band:
                label = ("no record supplied" if key == "NO_RECORD"
                         else palette.BANDS[key].label)
                parts.append(f"{label}: {', '.join(by_band[key])}")
        lines.append(f"{matrix.area_label(aid)} - " + "; ".join(parts) + ".")
    ctx = [f"{gid} is {matrix.group_context(gid)}" for gid in matrix.group_ids
           if matrix.group_context(gid)]
    if ctx:
        lines.append("Group context: " + "; ".join(ctx)
                     + ". Groups differ in size, funding and service model; read a difference "
                       "as a prompt for a question, not as a ranking.")
    return " ".join(lines)


def evidence_alt(matrix) -> str:
    lines = [
        matrix.disclaimer,
        "Evidence behind each group, as a stacked bar of items collected by kind: "
        + ", ".join(k["label"].lower() for k in palette.EVIDENCE_KINDS) + ".",
    ]
    for gid in matrix.group_ids:
        s = matrix.summarize_group(gid)
        bits = []
        for k in palette.EVIDENCE_KEYS:
            label = palette.evidence_kind(k)["label"].lower()
            if not s.recorded.get(k):
                bits.append(f"{label} not recorded")      # an omission
            else:
                bits.append(f"{label} {s.evidence[k]}")   # a count, including zero
        breakdown = ", ".join(bits)
        lines.append(f"{s.label} ({gid}): {s.evidence_total} items - {breakdown}. "
                     f"{s.coverage_sentence}")
    lines.append("A longer bar means the area is better evidenced, not that the group performs "
                 "better. A count of zero is a recorded measurement and is shown as a zero "
                 "token; a kind nobody recorded is shown as not recorded and is never added "
                 "to a total as if it were zero. Areas not assessed contribute no evidence.")
    return " ".join(lines)


def roadmap_alt(matrix) -> str:
    lines = [matrix.disclaimer,
             "Phased roadmap in three planning horizons: "
             + ", ".join(f"phase {p['badge']} {p['label']}" for p in palette.PHASES) + "."]
    if not matrix.roadmap:
        lines.append("No roadmap items supplied.")
        return " ".join(lines)
    for p in palette.PHASES:
        items = [i for i in matrix.roadmap if i["phase"] == p["key"]]
        if not items:
            lines.append(f"Phase {p['badge']} ({p['label']}): no items.")
            continue
        described = []
        for item in items:
            bits = [f"{item['id']} {item['title']}, from {item['recommendation']}"]
            bits.append(f"effort {item['effort']}" if item.get("effort")
                        else "effort not estimated")
            deps = item.get("depends_on") or []
            if deps:
                bits.append("after " + ", ".join(deps))
            described.append("; ".join(bits))
        lines.append(f"Phase {p['badge']} ({p['label']}): " + ". ".join(described) + ".")
    lines.append("Phase windows are planning horizons, not commitments. Items with no effort "
                 "estimate are marked as such and not scheduled by guesswork.")
    return " ".join(lines)


def states_alt() -> str:
    """Text alternative for the comparison fixture. Takes no data by design."""
    lines = ["SYNTHETIC REFERENCE FIXTURE - defines the visual vocabulary only. No University "
             "data appears in this figure.",
             "Every state the report can show, with what it means and how it is counted. No "
             "two states differ only by colour.",
             "Ratings, counted as ratings: "
             + "; ".join(f"{palette.BANDS[k].label} (mark {palette.BANDS[k].glyph}, "
                         f"{palette.BANDS[k].texture} fill, solid border)"
                         for k in palette.ORDINAL_KEYS) + ".",
             "Not ratings, each excluded from every rating count: "
             + "; ".join(f"{palette.BANDS[k].label} (mark {palette.BANDS[k].glyph}, "
                         f"{palette.BANDS[k].texture} fill, {palette.BANDS[k].border} border) - "
                         f"{palette.BANDS[k].meaning}"
                         for k in palette.NON_RATING_KEYS) + ".",
             "No record supplied: the input carried no row for this cell. Shown as an empty "
             "dashed outline, excluded from counts, and reported as a hole in the input.",
             "Values: measured zero is a real count of zero, shown with a solid border because "
             "it is a value we have, and counted as the value 0. Not recorded means no count "
             "was supplied, shown with a dashed border, excluded from totals and never summed "
             "as if it were zero.",
             "Border language: solid means a value we have, dashed means a value we do not "
             "have, double means more than one value with both kept. None of the unrated "
             "states is a low score."]
    return " ".join(lines)


ALT_BUILDERS = {
    "matrix": matrix_alt,
    "cross-group": cross_group_alt,
    "evidence-coverage": evidence_alt,
    "roadmap": roadmap_alt,
    "states": lambda _matrix=None: states_alt(),
}


# --------------------------------------------------------------------------
# Table templates. Same redundancy contract: glyph + written label, never a
# colour swatch on its own, and never a number standing in for a band.
# --------------------------------------------------------------------------
def matrix_markdown(matrix) -> str:
    out = [f"### {matrix.title}: assessment matrix", "", f"*{matrix.disclaimer}*", ""]
    header = "| Group | " + " | ".join(matrix.area_label(a) for a in matrix.area_ids) + " |"
    out.append(header)
    out.append("|---" * (len(matrix.area_ids) + 1) + "|")
    for gid in matrix.group_ids:
        cells = []
        for aid in matrix.area_ids:
            cell = matrix.cell(gid, aid)
            if cell is None:
                cells.append("`??` No record supplied")
                continue
            b = cell.band
            cells.append(f"{b.glyph} **{b.label}**")
        out.append(f"| **{gid}** {matrix.group_label(gid)} | " + " | ".join(cells) + " |")
    out += ["", "**Key**", ""]
    out.append("| Mark | Band | What it means |")
    out.append("|---|---|---|")
    for key in palette.ORDINAL_KEYS:
        b = palette.BANDS[key]
        out.append(f"| {b.glyph} | **{b.label}** | {b.meaning} |")
    out.append("| | | *Below: not ratings.* |")
    for key in palette.NON_RATING_KEYS:
        b = palette.BANDS[key]
        out.append(f"| {b.glyph} | **{b.label}** | {b.meaning} |")
    out += ["", "Unrated cells describe the evidence available to this review, not the "
                "performance of the group. They are excluded from every count of ratings.", ""]
    return "\n".join(out)


def coverage_markdown(matrix) -> str:
    out = [f"### {matrix.title}: evidence coverage", "", f"*{matrix.disclaimer}*", ""]
    out.append("| Group | " + " | ".join(k["label"] for k in palette.EVIDENCE_KINDS)
               + " | Total | Coverage |")
    out.append("|---" * (len(palette.EVIDENCE_KINDS) + 3) + "|")
    for gid in matrix.group_ids:
        s = matrix.summarize_group(gid)
        # A kind nobody counted prints as words. A blank cell or a `0` here is
        # the table version of the bug this whole lane exists to fix: it tells
        # the reader a measurement was taken when none was.
        counts = " | ".join(
            (str(s.evidence[k]) if s.recorded.get(k) else "_not recorded_")
            + (f" ({s.missing_counts[k]} area(s) uncounted)"
               if s.recorded.get(k) and s.missing_counts.get(k) else "")
            for k in palette.EVIDENCE_KEYS)
        out.append(f"| **{gid}** {s.label} | {counts} | **{s.evidence_total}** | "
                   f"{s.coverage_sentence} |")
    out += ["", "A larger total means the area is better evidenced, not that the group "
                "performs better. A `0` is a recorded count; *not recorded* means no count "
                "was supplied and is never added to a total as a zero.", ""]
    return "\n".join(out)


def roadmap_markdown(matrix) -> str:
    out = [f"### {matrix.title}: phased roadmap", "", f"*{matrix.disclaimer}*", ""]
    out.append("| Phase | Window | Item | From | Effort | Prerequisite |")
    out.append("|---|---|---|---|---|---|")
    for p in palette.PHASES:
        for item in [i for i in matrix.roadmap if i["phase"] == p["key"]]:
            effort = item.get("effort") or "_not estimated_"
            deps = ", ".join(item.get("depends_on") or []) or "-"
            out.append(f"| {p['badge']} | {p['label']} | **{item['id']}** {item['title']} "
                       f"| {item['recommendation']} | {effort} | {deps} |")
    out += ["", "Phase windows are planning horizons, not commitments. Items with no effort "
                "estimate are shown as *not estimated* and are never given a guessed value.", ""]
    return "\n".join(out)


def alt_text_bundle(matrix) -> str:
    """One document carrying the text alternative for every figure."""
    out = [f"# {matrix.title} - text alternatives for every figure", "",
           f"{matrix.disclaimer}", "",
           "Each block below is the exact text embedded in the matching SVG's <desc> "
           "element. A reader using a screen reader, a plain-text export or a printed "
           "black-and-white copy receives the same content as a reader seeing colour.", ""]
    titles = {
        "matrix": "Figure 1 - Assessment matrix",
        "cross-group": "Figure 2 - Comparison across groups",
        "evidence-coverage": "Figure 3 - Evidence behind each group",
        "roadmap": "Figure 4 - Phased roadmap",
    }
    for key in ("matrix", "cross-group", "evidence-coverage", "roadmap"):
        out += [f"## {titles[key]}", "", ALT_BUILDERS[key](matrix), ""]
    out += ["## Tables", "", matrix_markdown(matrix), "", coverage_markdown(matrix), "",
            roadmap_markdown(matrix), ""]
    return "\n".join(out)
