"""Calendar and dashboard renderers for UIOWA-002."""

from __future__ import annotations

import json
from decimal import Decimal

try:
    from .canonical import COMMERCIAL_BLOB, INTERVIEW_SESSIONS, SCHEMA, TASKS
    from .engine import schedule
except ImportError:
    from canonical import COMMERCIAL_BLOB, INTERVIEW_SESSIONS, SCHEMA, TASKS
    from engine import schedule


def _jsonable(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    return obj


def calendar_markdown(result):
    horizon = result["horizon_weeks"]
    lines = [
        "# RFQ 18649 staffing calendar (PROPOSED / NOT ACCEPTED)",
        "",
        "Horizon: **%s weeks**. Interview sessions: **%s** (ESS/RIS/IAM × 4 dimensions)."
        % (horizon, INTERVIEW_SESSIONS),
        "Participant headcount: **%s** (does not imply one interview per person)."
        % result["participant_count"],
        "TJLabs location: **%s**. Travel: **%s**. Onsite is a subset, not additive."
        % (result["specialist_location"], result["travel"]),
        "",
        "| Week | Specialist hours | Prime hours | Specialist tasks |",
        "|---:|---:|---:|---|",
    ]
    for w in range(horizon):
        tasks = []
        for name in TASKS:
            qty = result["specialist"]["rows"][name]["weekly"][w]
            if qty:
                tasks.append("%s %s" % (name, qty))
        lines.append(
            "| %s | %s | %s | %s |"
            % (
                w,
                result["specialist"]["weekly_total"][w],
                result["prime"]["weekly_total"][w],
                ", ".join(tasks) or "—",
            )
        )
    lines += [
        "",
        "Specialist peak: **%s** h/week (capacity %s)."
        % (result["specialist"]["peak_hours"], result["specialist"]["capacity_per_week"]),
        "Prime peak: **%s** h/week (capacity %s)."
        % (result["prime"]["peak_hours"], result["prime"]["capacity_per_week"]),
        "Specialist productive hours: **%s** (base pin 160.00). Onsite subset: **%s**."
        % (
            result["specialist"]["productive_hours"],
            result["specialist"]["onsite_subset_hours"],
        ),
        "",
        "Pinned COMMERCIAL.md blob `%s`." % COMMERCIAL_BLOB,
        "Assumptions only — not committed staffing, interviews, or travel.",
        "",
    ]
    return "\n".join(lines)


def formula_sheet(result):
    """Weekly specialist total = sum of task columns. Independent of engine totals."""
    rows = []
    for w in range(result["horizon_weeks"]):
        parts = ["%s%d" % (name[:3], w) for name in TASKS]
        rows.append(
            {
                "week": w,
                "formula": "+".join(parts),
                "engine_total": result["specialist"]["weekly_total"][w],
                "cells": {
                    ("%s%d" % (name[:3], w)): result["specialist"]["rows"][name]["weekly"][w]
                    for name in TASKS
                },
            }
        )
    return rows


def eval_formula_sheet(rows):
    out = []
    for row in rows:
        env = dict(row["cells"])
        total = Decimal("0.00")
        for token in row["formula"].split("+"):
            total += env[token]
        out.append(total.quantize(Decimal("0.01")))
    return out


def pack(workbook):
    result = schedule(workbook)
    return {
        "schema": SCHEMA,
        "commercial_blob": COMMERCIAL_BLOB,
        "result": _jsonable(result),
        "calendar_md": calendar_markdown(result),
        "formulas": _jsonable(formula_sheet(result)),
    }
