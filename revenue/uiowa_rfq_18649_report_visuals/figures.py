"""Reusable, content-sized report figures.

Preserves the original report visual vocabulary, palette, data model, text
alternatives and five public figure entry points. Text now wraps into measured
layout budgets; rows, cards, legends and the canvas grow with their contents.
Original package authors retain the visual design and assessment semantics.
Full-text layout repair: ZZ-COPPERFINCH-82D6; discovery: OP5-CONTROL.
Python 3 standard library only.
"""
from __future__ import annotations

import math

import alt_text
import palette
import svg
from text_layout import add_text, text_height

FONT_TITLE = 17
FONT_SUB = 12
FONT_BODY = 11.5
FONT_SMALL = 10.5
MARGIN = 24


def _theme(theme_name: str) -> dict:
    try:
        return palette.THEMES[theme_name]
    except KeyError:
        raise KeyError(
            f"unknown theme {theme_name!r}; known: {', '.join(palette.THEMES)}"
        ) from None


def _text(fig, th, x, y, value, width, size=FONT_BODY, *, muted=False, bold=False):
    return add_text(fig, x, y, value, width, size,
                    th["muted"] if muted else th["ink"], "bold" if bold else None)


def _header(fig, th, title, subtitle, x=MARGIN, y=MARGIN):
    width = fig.width - 2 * MARGIN
    y = _text(fig, th, x, y, title, width, FONT_TITLE, bold=True) + 7
    if subtitle:
        y = _text(fig, th, x, y, subtitle, width, FONT_SUB, muted=True) + 10
    return y


def _finish(fig, bottom):
    fig.height = max(1, math.ceil(bottom + MARGIN))
    return fig


def _band_paint(fig, th, band):
    return fig.texture_fill(band.key, band.texture, band.fill, band.texture_ink,
                            th["hatch_weight"])


def _band_swatch(fig, th, band, x, y, w=26, h=16):
    paint = _band_paint(fig, th, band)
    return [svg.bordered_rect(x, y, w, h, paint, band.border_ink,
                               th["border_weight"], band.border, rx=2),
            svg.mark(band.shape, x + w + 13, y + h / 2, 11,
                     band.fill if band.on_scale else "none", band.border_ink, 1.3)]


def _legend(fig, th, x, y, width, keys=palette.BAND_ORDER):
    y = _text(fig, th, x, y, "How to read this", width, bold=True) + 8
    label_width = 175
    meaning_x = x + 54 + label_width + 16
    meaning_width = width - (meaning_x - x)
    for key in keys:
        band = palette.BANDS[key]
        if key == palette.NON_RATING_KEYS[0]:
            fig.add(svg.line(x, y + 2, x + width, y + 2, stroke=th["rule"],
                             stroke_width=1, stroke_dasharray="3 3"))
            y = _text(fig, th, x, y + 10, "Below this line: not ratings.",
                      width, FONT_SMALL, muted=True, bold=True) + 8
        fig.add_all(_band_swatch(fig, th, band, x, y + 2))
        a = _text(fig, th, x + 54, y, band.label, label_width, bold=True)
        b = _text(fig, th, meaning_x, y, band.meaning, meaning_width,
                  FONT_SMALL, muted=True)
        y = max(y + 18, a, b) + 9
    return y


def _new(matrix, th, width, suffix, description, slug):
    return svg.Figure(int(width), 1, f"{matrix.title} - {suffix}", description,
                      th["background"], slug=slug)


def _intro(fig, matrix, th, suffix):
    return _header(fig, th, f"{matrix.title}: {suffix}",
                   f"{matrix.subtitle}  |  {matrix.disclaimer}") + 6


def _cell_lines(cell):
    if cell is None:
        return ["no record supplied"]
    if cell.conflict:
        # Every reading, including a third or later source, survives intact.
        return [f"{reading['source']}: {reading['says']}" for reading in cell.conflict]
    return [f"{cell.evidence_total} evidence items" if cell.evidence_collected
            else "no evidence collected"]


def matrix_figure(matrix, theme_name=palette.DEFAULT_THEME):
    th = _theme(theme_name)
    row_head, col_w = 180, 180
    grid_w = row_head + col_w * len(matrix.area_ids)
    fig = _new(matrix, th, 2 * MARGIN + max(grid_w, 760), "assessment matrix",
               alt_text.matrix_alt(matrix), "matrix")
    x0 = MARGIN
    top = _intro(fig, matrix, th, "assessment matrix")
    header_bottom = top
    for column, aid in enumerate(matrix.area_ids):
        x = x0 + row_head + column * col_w + 10
        bottom = _text(fig, th, x, top, matrix.area_label(aid), col_w - 20, bold=True)
        header_bottom = max(header_bottom,
                            _text(fig, th, x, bottom + 4, aid, col_w - 20,
                                  FONT_SMALL, muted=True))
    y = header_bottom + 14
    fig.add(svg.line(x0, y - 5, x0 + grid_w, y - 5, stroke=th["rule"], stroke_width=1.2))
    for gid in matrix.group_ids:
        context = matrix.group_context(gid)
        label_h = text_height(matrix.group_label(gid), row_head - 20, FONT_BODY)
        label_h += 5 + text_height(gid, row_head - 20, FONT_SMALL)
        if context:
            label_h += 5 + text_height(context, row_head - 20, FONT_SMALL)
        row_h = max(84, label_h + 20)
        for aid in matrix.area_ids:
            cell = matrix.cell(gid, aid)
            body_h = sum(text_height(value, col_w - 32, FONT_SMALL) + 5
                         for value in _cell_lines(cell))
            band_h = text_height(cell.band.label, col_w - 50, FONT_BODY) if cell else 0
            row_h = max(row_h, 24 + band_h + body_h + 12)
        bottom = _text(fig, th, x0, y + 8, matrix.group_label(gid), row_head - 20,
                       bold=True)
        bottom = _text(fig, th, x0, bottom + 5, gid, row_head - 20, FONT_SMALL, muted=True)
        if context:
            _text(fig, th, x0, bottom + 5, context, row_head - 20, FONT_SMALL, muted=True)
        for column, aid in enumerate(matrix.area_ids):
            cx = x0 + row_head + column * col_w
            cell = matrix.cell(gid, aid)
            if cell is None:
                fig.add(svg.rect(cx + 4, y + 4, col_w - 12, row_h - 12, fill="none",
                                 stroke=th["rule"], stroke_width=1.2,
                                 stroke_dasharray="2 4", rx=3))
                _text(fig, th, cx + 14, y + 14, "no record supplied", col_w - 32,
                      FONT_SMALL, muted=True)
                continue
            band = cell.band
            fig.add(svg.bordered_rect(cx + 4, y + 4, col_w - 12, row_h - 12,
                                      _band_paint(fig, th, band), band.border_ink,
                                      th["border_weight"], band.border, rx=3))
            fig.add(svg.mark(band.shape, cx + 22, y + 23, 14,
                             band.fill if band.on_scale else "none", band.ink, 1.4))
            by = add_text(fig, cx + 38, y + 12, band.label, col_w - 50,
                          FONT_BODY, band.ink, "bold") + 6
            for value in _cell_lines(cell):
                by = add_text(fig, cx + 14, by, value, col_w - 32,
                              FONT_SMALL, band.ink) + 5
        y += row_h
    totals = matrix.totals()
    tails = [("insufficient_evidence", "had insufficient evidence"),
             ("not_assessed", "were not assessed"),
             ("not_applicable", "do not apply to that group"),
             ("contradictory", "have sources that disagree"),
             ("cells_missing", "had no record supplied")]
    tail = "; ".join(f"{totals[key]} {label}" for key, label in tails if totals[key])
    caption = f"{totals['rated']} of {totals['cells_expected']} cells carry a rating."
    if tail:
        caption += " " + tail + "."
    width = fig.width - 2 * MARGIN
    y = _text(fig, th, x0, y + 12, caption, width) + 14
    y = _legend(fig, th, x0, y, width)
    y = _text(fig, th, x0, y + 6,
              "Unrated cells describe the evidence available to this review, not the "
              "performance of the group. They are excluded from every count of ratings.",
              width, FONT_SMALL, muted=True)
    return _finish(fig, y)


def cross_group_figure(matrix, theme_name=palette.DEFAULT_THEME):
    th = _theme(theme_name)
    left, col_w = 210, 180
    grid_w = left + col_w * len(matrix.area_ids)
    fig = _new(matrix, th, 2 * MARGIN + max(grid_w, 760), "comparison across groups",
               alt_text.cross_group_alt(matrix), "cross")
    x0 = MARGIN
    y = _intro(fig, matrix, th, "comparison across groups")
    head_bottom = y
    for column, aid in enumerate(matrix.area_ids):
        head_bottom = max(head_bottom, _text(fig, th, x0 + left + column * col_w + 8,
                                             y, matrix.area_label(aid), col_w - 16,
                                             bold=True))
    y = head_bottom + 12
    slot_w = col_w / (len(matrix.group_ids) + 1)
    code_w = max(1, slot_w - 8)
    code_h = max([text_height(gid, code_w, FONT_SMALL) for gid in matrix.group_ids] + [0])
    lane_h = max(62, 30 + code_h,
                 max(text_height(palette.BANDS[key].label, left - 58, FONT_BODY)
                     for key in palette.BAND_ORDER) + 16)
    lane_y = {}

    def lane(top, band):
        fig.add_all(_band_swatch(fig, th, band, x0, top + 8, 22, 15))
        _text(fig, th, x0 + 48, top + 6, band.label, left - 58, bold=True)
        fig.add(svg.line(x0 + left, top + lane_h, x0 + grid_w, top + lane_h,
                         stroke=th["rule"], stroke_width=0.6, stroke_dasharray="2 4"))
        lane_y[band.key] = top

    for key in palette.ORDINAL_KEYS:
        lane(y, palette.BANDS[key])
        y += lane_h
    fig.add(svg.line(x0, y + 8, x0 + grid_w, y + 8, stroke=th["ink"], stroke_width=2))
    y = _text(fig, th, x0, y + 18,
              "Off the rating scale - these are statements about the evidence, not lower ratings",
              grid_w, FONT_SMALL, bold=True) + 12
    fig.add(svg.rect(x0, y, grid_w, lane_h * len(palette.NON_RATING_KEYS),
                     fill=palette.BANDS["UNASSESSED"].fill, stroke="none", opacity=0.45))
    for key in palette.NON_RATING_KEYS:
        lane(y, palette.BANDS[key])
        y += lane_h
    for gi, gid in enumerate(matrix.group_ids):
        style = palette.group_style(gi)
        for column, aid in enumerate(matrix.area_ids):
            cell = matrix.cell(gid, aid)
            if cell is None:
                continue
            cx = x0 + left + column * col_w + slot_w * (gi + 1)
            top = lane_y[cell.band.key]
            fig.add(svg.mark(style["shape"], cx, top + 14, 13,
                             style["colour"], style["colour"], 1.2))
            _text(fig, th, cx - code_w / 2, top + 26, gid, code_w, FONT_SMALL, bold=True)
    width = fig.width - 2 * MARGIN
    y = _text(fig, th, x0, y + 20,
              "Groups (shape and printed code identify the group; colour is a secondary cue only)",
              width, bold=True) + 12
    for gi, gid in enumerate(matrix.group_ids):
        style = palette.group_style(gi)
        summary = matrix.summarize_group(gid)
        fig.add(svg.mark(style["shape"], x0 + 8, y + 8, 13,
                         style["colour"], style["colour"], 1.2))
        y = _text(fig, th, x0 + 26, y, f"{gid} - {summary.label}", width - 26,
                  bold=True) + 4
        if summary.context:
            y = _text(fig, th, x0 + 26, y, summary.context, width - 26,
                      FONT_SMALL, muted=True) + 4
        y += 8
    y = _text(fig, th, x0, y + 4,
              "Groups differ in size, funding and service model. Read a difference as a "
              "prompt for a question, not as a ranking.", width, FONT_SMALL, muted=True)
    return _finish(fig, y)


def evidence_coverage_figure(matrix, theme_name=palette.DEFAULT_THEME):
    th = _theme(theme_name)
    left, plot_w, right, bar_h = 195, 420, 150, 30
    fig = _new(matrix, th, 2 * MARGIN + left + plot_w + right,
               "evidence behind each group", alt_text.evidence_alt(matrix), "evidence")
    x0 = MARGIN
    width = fig.width - 2 * MARGIN
    y = _intro(fig, matrix, th, "evidence behind each rating")
    y = _text(fig, th, x0, y,
              "Evidence items collected (each segment labelled with its count)",
              width, bold=True) + 18
    summaries = [matrix.summarize_group(gid) for gid in matrix.group_ids]
    scale = plot_w / max([summary.evidence_total for summary in summaries] + [1])
    kind_w = plot_w / len(palette.EVIDENCE_KINDS)
    for summary in summaries:
        top = y
        label_bottom = _text(fig, th, x0, top,
                             f"{summary.group} - {summary.label}", left - 18, bold=True)
        bx = x0 + left
        if summary.evidence_total == 0:
            fig.add(svg.rect(bx, top, plot_w, bar_h, fill=palette.BANDS["UNASSESSED"].fill,
                             stroke=palette.BANDS["UNASSESSED"].border_ink,
                             stroke_width=th["border_weight"], stroke_dasharray="5 3", rx=2))
            _text(fig, th, bx + 10, top + 5, "no evidence collected", plot_w - 20,
                  FONT_SMALL)
        else:
            for kind in palette.EVIDENCE_KINDS:
                count = summary.evidence[kind["key"]]
                if not count:
                    continue
                seg_w = count * scale
                paint = fig.texture_fill(f"ev-{kind['key']}", kind["texture"],
                                         kind["fill"], kind["ink"], th["hatch_weight"])
                fig.add(svg.rect(bx, top, seg_w, bar_h, fill=paint,
                                 stroke=th["background"], stroke_width=1.2))
                label = f"{kind['short']} {count}"
                if (seg_w - 10 >= FONT_SMALL and
                        text_height(label, seg_w - 10, FONT_SMALL) <= FONT_SMALL * 1.4):
                    add_text(fig, bx + 5, top + 7, label, seg_w - 10,
                             FONT_SMALL, kind["ink"], "bold")
                bx += seg_w
        total_bottom = _text(fig, th, x0 + left + plot_w + 14, top,
                             f"{summary.evidence_total} items", right - 14, bold=True)
        # Zero/missing tokens live below the quantitative bar. They must not
        # increase its length or push a positive segment into the total column.
        token_y = max(top + bar_h + 8, total_bottom + 6)
        tokens_bottom = token_y
        for index, kind in enumerate(palette.EVIDENCE_KINDS):
            count = summary.evidence[kind["key"]]
            tx = x0 + left + index * kind_w
            if count:
                label = f"{kind['short']} {count}"
                tokens_bottom = max(tokens_bottom,
                                    _text(fig, th, tx + 4, token_y + 5, label,
                                          kind_w - 12, FONT_SMALL))
            else:
                state = palette.VALUE_STATES["MEASURED_ZERO" if summary.recorded.get(kind["key"])
                                             else "NOT_RECORDED"]
                label = f"{kind['short']} {state['label']}"
                height = text_height(label, kind_w - 20, FONT_SMALL) + 10
                fig.add(svg.bordered_rect(tx + 2, token_y, kind_w - 8, height,
                                          state["fill"], state["border_ink"],
                                          th["border_weight"], state["border"], rx=2))
                bottom = add_text(fig, tx + 8, token_y + 5, label, kind_w - 20,
                                  FONT_SMALL, state["ink"])
                tokens_bottom = max(tokens_bottom, bottom + 5)
        y = _text(fig, th, x0 + left, tokens_bottom + 8, summary.coverage_sentence,
                  plot_w + right, FONT_SMALL, muted=True)
        y = max(y, label_bottom) + 24
    y = _text(fig, th, x0, y, "Evidence kinds", width, bold=True) + 10
    for kind in palette.EVIDENCE_KINDS:
        paint = fig.texture_fill(f"ev-{kind['key']}", kind["texture"], kind["fill"],
                                 kind["ink"], th["hatch_weight"])
        fig.add(svg.rect(x0, y + 2, 26, 15, fill=paint, stroke=th["rule"], stroke_width=1, rx=2))
        y = max(y + 17, _text(fig, th, x0 + 36, y,
                              f"{kind['short']} - {kind['label']}", width - 36)) + 9
    y = _text(fig, th, x0, y + 8,
              "A longer bar means the area is better evidenced, not that the group performs "
              "better. Areas not assessed contribute no evidence and are not shown as zero.",
              width, FONT_SMALL, muted=True)
    return _finish(fig, y)


def roadmap_figure(matrix, theme_name=palette.DEFAULT_THEME):
    th = _theme(theme_name)
    col_w, gap = 250, 22
    width = 2 * MARGIN + col_w * len(palette.PHASES) + gap * (len(palette.PHASES) - 1)
    fig = _new(matrix, th, width, "phased roadmap", alt_text.roadmap_alt(matrix), "roadmap")
    fig.add_def(svg.ARROW_MARKER_ID, svg.arrow_marker(th["ink"]))
    x0 = MARGIN
    top = _intro(fig, matrix, th, "phased roadmap")
    by_phase = {phase["key"]: [] for phase in palette.PHASES}
    for item in matrix.roadmap:
        by_phase[item["phase"]].append(item)
    header_h = max(text_height(f"Phase {phase['badge']}: {phase['label']}",
                              col_w - 45, FONT_BODY) for phase in palette.PHASES) + 18
    cards = {}
    centres = {}
    last_bottom = top + header_h
    for pi, phase in enumerate(palette.PHASES):
        px = x0 + pi * (col_w + gap)
        paint = fig.texture_fill(f"ph-{phase['key']}", phase["texture"], phase["fill"],
                                 phase["ink"], th["hatch_weight"])
        fig.add(svg.rect(px, top, col_w, header_h, fill=paint, stroke=phase["fill"],
                         stroke_width=th["border_weight"], rx=3))
        fig.add(svg.circle(px + 17, top + 17, 10, fill=phase["ink"]))
        fig.add(svg.text(px + 17, top + 21, phase["badge"], size=FONT_BODY,
                         fill=phase["fill"], anchor="middle", weight="bold"))
        add_text(fig, px + 34, top + 8, f"Phase {phase['badge']}: {phase['label']}",
                 col_w - 45, FONT_BODY, phase["ink"], "bold")
        cy = top + header_h + 14
        for item in by_phase[phase["key"]]:
            fields = [(item["title"], FONT_BODY),
                      (f"from {item['recommendation']}", FONT_SMALL),
                      (f"Effort: {item['effort']}" if item.get("effort")
                       else palette.UNKNOWN_EFFORT["label"], FONT_SMALL)]
            dependencies = item.get("depends_on", []) or []
            if dependencies:
                fields.append(("after " + ", ".join(dependencies), FONT_SMALL))
            id_h = text_height(item["id"], col_w - 52, FONT_BODY)
            height = 20 + id_h + 8 + sum(text_height(value, col_w - 32, size) + 9
                                         for value, size in fields)
            height = max(110, height)
            cards[item["id"]] = (px, cy, height, fields, id_h)
            centres[item["id"]] = (px + col_w / 2, cy + height / 2)
            cy += height + 16
        last_bottom = max(last_bottom, cy)
    for item in matrix.roadmap:
        for dependency in item.get("depends_on", []) or []:
            if dependency not in centres:
                continue
            x1, y1 = centres[dependency]
            x2, y2 = centres[item["id"]]
            fig.add(svg.path(f"M{x1},{y1} C{(x1+x2)/2},{y1} {(x1+x2)/2},{y2} {x2},{y2}",
                             fill="none", stroke=th["ink"], stroke_width=1.4,
                             marker_end=f"url(#{svg.ARROW_MARKER_ID})", opacity=0.75))
    for item in matrix.roadmap:
        px, py, height, fields, id_h = cards[item["id"]]
        phase = palette.phase(item["phase"])
        fig.add(svg.rect(px, py, col_w, height, fill=th["background"],
                         stroke=phase["fill"], stroke_width=th["border_weight"], rx=4))
        fig.add(svg.rect(px, py, 5, height, fill=phase["fill"], stroke="none"))
        fig.add(svg.circle(px + 22, py + 18, 9, fill=phase["fill"]))
        fig.add(svg.text(px + 22, py + 22, phase["badge"], size=FONT_SMALL,
                         fill=phase["ink"], anchor="middle", weight="bold"))
        cy = _text(fig, th, px + 38, py + 10, item["id"], col_w - 52, bold=True) + 10
        for index, (value, size) in enumerate(fields):
            if index == 2 and not item.get("effort"):
                unknown = palette.UNKNOWN_EFFORT
                paint = fig.texture_fill("unknown-effort", unknown["texture"], unknown["fill"],
                                         palette.BANDS["UNASSESSED"].texture_ink,
                                         th["hatch_weight"])
                text_h = text_height(value, col_w - 32, size)
                fig.add(svg.rect(px + 10, cy - 3, col_w - 20, text_h + 6, fill=paint,
                                 stroke=unknown["border_ink"], stroke_width=1.2,
                                 stroke_dasharray="4 3", rx=2))
                cy = add_text(fig, px + 16, cy, value, col_w - 32, size, unknown["ink"]) + 9
            else:
                cy = _text(fig, th, px + 16, cy, value, col_w - 32, size,
                           muted=index in (1, 3)) + 9
    y = _text(fig, th, x0, last_bottom + 8,
              "Arrows show prerequisites. Each card also names its prerequisite in words, "
              "so the sequence survives being read without the arrows.",
              width - 2 * MARGIN, FONT_SMALL, muted=True) + 8
    y = _text(fig, th, x0, y,
              "Phase windows are planning horizons, not commitments. Items with no effort "
              "estimate are marked as such and not scheduled by guesswork.",
              width - 2 * MARGIN, FONT_SMALL, muted=True)
    return _finish(fig, y)


STATE_ROWS = (
    ("band", "STRENGTH", "counted as a rating"),
    ("band", "ESTABLISHED", "counted as a rating"),
    ("band", "DEVELOPING", "counted as a rating"),
    ("band", "GAP", "counted as a rating"),
    ("band", "INSUFFICIENT_EVIDENCE", "excluded from every rating count"),
    ("band", "UNASSESSED", "excluded from every rating count"),
    ("band", "NOT_APPLICABLE", "excluded; not a gap in our evidence"),
    ("band", "CONTRADICTORY", "excluded; both readings kept on the page"),
    ("absent", "NO_RECORD", "excluded; reported as a hole in the input"),
    ("value", "MEASURED_ZERO", "counted as the value 0"),
    ("value", "NOT_RECORDED", "excluded from totals; never summed as 0"),
)


def states_figure(matrix=None, theme_name=palette.DEFAULT_THEME):
    th = _theme(theme_name)
    width = 1050
    fig = svg.Figure(width, 1, "Report visuals: every state, side by side",
                     alt_text.states_alt(), th["background"], slug="states")
    x0 = MARGIN
    label_x, label_w = 190, 180
    mean_x, mean_w = 390, 350
    count_x, count_w = 766, 260
    y = _header(fig, th, "Every state the report can show",
                "SYNTHETIC REFERENCE FIXTURE - defines the visual vocabulary only. No "
                "University data appears in this figure. Colour is never the only "
                "difference between two rows.") + 10
    heading_bottom = y
    for header, hx, hw in (("Swatch", x0, 100), ("Mark", 145, 40),
                           ("Name", label_x, label_w), ("What it means", mean_x, mean_w),
                           ("How it is counted", count_x, count_w)):
        heading_bottom = max(heading_bottom,
                             _text(fig, th, hx, y, header, hw, FONT_SMALL,
                                   muted=True, bold=True))
    y = heading_bottom + 10
    fig.add(svg.line(x0, y, width - MARGIN, y, stroke=th["rule"], stroke_width=1.2))
    y += 8
    for kind, key, counting in STATE_ROWS:
        if kind == "band":
            band = palette.BANDS[key]
            name = band.label
            meaning = band.meaning + (" Not a rating." if not band.on_scale else "")
        elif kind == "value":
            state = palette.VALUE_STATES[key]
            name, meaning = state["long_label"], state["meaning"]
        else:
            name = "No record supplied"
            meaning = "The input carried no row for this cell. Not a rating."
        row_h = max(40, text_height(name, label_w, FONT_BODY) + 16,
                    text_height(meaning, mean_w, FONT_SMALL) + 16,
                    text_height(counting, count_w, FONT_SMALL) + 16)
        sw_y = y + (row_h - 22) / 2
        if kind == "band":
            fig.add(svg.bordered_rect(x0, sw_y, 106, 22, _band_paint(fig, th, band),
                                      band.border_ink, th["border_weight"], band.border, rx=2))
            fig.add(svg.mark(band.shape, 156, y + row_h / 2, 13,
                             band.fill if band.on_scale else "none", band.border_ink, 1.4))
        elif kind == "value":
            token_h = text_height(state["label"], 90, FONT_SMALL) + 8
            fig.add(svg.bordered_rect(x0, y + 5, 106, token_h, state["fill"],
                                      state["border_ink"], th["border_weight"], state["border"], rx=2))
            add_text(fig, x0 + 8, y + 9, state["label"], 90, FONT_SMALL, state["ink"], "bold")
            row_h = max(row_h, token_h + 14)
        else:
            fig.add(svg.rect(x0, sw_y, 106, 22, fill="none", stroke=th["rule"],
                             stroke_width=1.2, stroke_dasharray="2 4", rx=2))
            _text(fig, th, x0 + 8, sw_y + 3, "(empty)", 90, FONT_SMALL, muted=True)
        _text(fig, th, label_x, y + 7, name, label_w, bold=True)
        _text(fig, th, mean_x, y + 7, meaning, mean_w, FONT_SMALL, muted=True)
        _text(fig, th, count_x, y + 7, counting, count_w, FONT_SMALL)
        y += row_h
        fig.add(svg.line(label_x, y, width - MARGIN, y, stroke=th["rule"], stroke_width=0.5))
    y = _text(fig, th, x0, y + 14,
              "Each row differs from every other in shape, texture, border style and wording, "
              "not only in colour. Open the .mono.svg copy to confirm: the colour is genuinely "
              "removed there, not simulated.", width - 2 * MARGIN, FONT_SMALL, muted=True) + 8
    y = _text(fig, th, x0, y,
              "Solid border: a value we have. Dashed: a value we do not have. Double: more "
              "than one value, both kept. None of the unrated states is a low score.",
              width - 2 * MARGIN, FONT_SMALL, muted=True)
    return _finish(fig, y)


FIGURES = {"matrix": matrix_figure, "cross-group": cross_group_figure,
           "evidence-coverage": evidence_coverage_figure, "roadmap": roadmap_figure,
           "states": states_figure}
