"""Scope-change impact calculator.

Added scope is priced separately from correction of an in-scope defect.
Missing quantities/rates and onsite/travel holds fail closed. Required
checks use raise, never assert (python -O safe).
"""

from __future__ import annotations

import json
import os

try:
    from .catalog import (
        AUTHORITY,
        BASELINE,
        CHANGE_TYPES,
        IN_SCOPE_CORRECTION,
    )
except ImportError:
    from catalog import (
        AUTHORITY,
        BASELINE,
        CHANGE_TYPES,
        IN_SCOPE_CORRECTION,
    )

SCHEMA = "uiowa-133-scope-change/1"
MAX_LINE_QTY = 20
MAX_FILE_BYTES = 200_000

ERROR, WARN, INFO = "ERROR", "WARN", "INFO"


class ScopeError(Exception):
    """Worksheet cannot be priced without inventing an input."""


def load_worksheet(path):
    st = os.stat(path)
    if st.st_size > MAX_FILE_BYTES:
        raise ScopeError("worksheet %r exceeds %d bytes" % (path, MAX_FILE_BYTES))
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ScopeError("worksheet must be a JSON object")
    if data.get("schema") != SCHEMA:
        raise ScopeError("unsupported schema %r" % (data.get("schema"),))
    if not isinstance(data.get("lines"), list):
        raise ScopeError("worksheet.lines must be a list")
    return data


def _int_qty(raw, line_id):
    if raw is None:
        raise ScopeError("line %s is missing quantity" % line_id)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ScopeError("line %s quantity must be a JSON integer" % line_id)
    if raw < 0 or raw > MAX_LINE_QTY:
        raise ScopeError("line %s quantity %r is out of bounds" % (line_id, raw))
    return raw


def quote(worksheet):
    issues = []
    lines_out = []
    incremental_hours = 0
    incremental_usd = 0
    hold_usd = False

    if worksheet.get("baseline_workshare_usd") not in (None, BASELINE["workshare_base_usd"]):
        issues.append(
            {
                "severity": ERROR,
                "code": "BASELINE_MISMATCH",
                "detail": "worksheet baseline %r is not the pinned $%d workshare"
                % (worksheet.get("baseline_workshare_usd"), BASELINE["workshare_base_usd"]),
            }
        )

    seen = set()
    for i, line in enumerate(worksheet.get("lines") or []):
        if not isinstance(line, dict):
            raise ScopeError("lines[%d] must be an object" % i)
        lid = line.get("id") or ("LINE-%d" % (i + 1))
        if lid in seen:
            raise ScopeError("duplicate line id %r" % lid)
        seen.add(lid)
        kind = line.get("type")
        qty = _int_qty(line.get("quantity"), lid)
        class_ = line.get("class") or "added_scope"

        if class_ == IN_SCOPE_CORRECTION:
            if qty:
                issues.append(
                    {
                        "severity": INFO,
                        "code": "CORRECTION_NOT_PRICED",
                        "detail": "line %s is an in-scope defect correction; incremental fee stays $0"
                        % lid,
                        "ref": lid,
                    }
                )
            lines_out.append(
                {
                    "id": lid,
                    "type": kind,
                    "class": class_,
                    "quantity": qty,
                    "hours": 0,
                    "usd": 0,
                    "status": "IN_SCOPE_NO_INCREMENT",
                    "note": "Correction of an in-scope defect is not additional scope.",
                }
            )
            continue

        if class_ != "added_scope":
            raise ScopeError("line %s has unknown class %r" % (lid, class_))
        if kind not in CHANGE_TYPES:
            raise ScopeError("line %s has unknown change type %r" % (lid, kind))
        spec = CHANGE_TYPES[kind]
        hours = spec["hours"] * qty
        usd = spec["usd"]
        status = "PRICED_PROPOSED"
        note = spec["label"]
        if spec["travel"]:
            usd = None
            status = "HOLD_TRAVEL_UNAUTHORIZED"
            note = (
                "Onsite/travel is excluded from the $24,000 base. This assembler "
                "does not invent travel spend or authorization."
            )
            hold_usd = True
            issues.append(
                {
                    "severity": WARN,
                    "code": "ONSITE_TRAVEL_HOLD",
                    "detail": "line %s requests onsite days; travel remains unauthorized"
                    % lid,
                    "ref": lid,
                }
            )
        elif usd is None:
            hold_usd = True
            status = "HOLD_MISSING_RATE"
            issues.append(
                {
                    "severity": ERROR,
                    "code": "MISSING_RATE",
                    "detail": "line %s has no proposed rate" % lid,
                    "ref": lid,
                }
            )
        else:
            usd = usd * qty
            if spec["option"] and qty > 1:
                issues.append(
                    {
                        "severity": WARN,
                        "code": "READOUT_QTY_GT_ONE",
                        "detail": "line %s additional_readout qty=%d; only the first $4,000 option is pinned"
                        % (lid, qty),
                        "ref": lid,
                    }
                )
        incremental_hours += hours
        if isinstance(usd, int):
            incremental_usd += usd
        lines_out.append(
            {
                "id": lid,
                "type": kind,
                "class": class_,
                "quantity": qty,
                "hours": hours,
                "usd": usd,
                "status": status,
                "note": note,
            }
        )

    baseline_usd = BASELINE["workshare_base_usd"]
    option_usd = BASELINE["workshare_option_usd"]
    total = None if hold_usd else baseline_usd + incremental_usd
    result = {
        "schema": SCHEMA,
        "baseline": dict(BASELINE),
        "authority": dict(AUTHORITY),
        "lines": lines_out,
        "totals": {
            "baseline_usd": baseline_usd,
            "incremental_hours": incremental_hours,
            "incremental_usd": None if hold_usd else incremental_usd,
            "optional_readout_usd": option_usd,
            "quoted_total_usd": total,
            "status": "HOLD_MISSING_INPUTS" if hold_usd else "PROPOSED_NOT_ACCEPTED",
        },
        "issues": issues,
        "notes": [
            "$%d is TJLabs subcontract workshare, not the prime all-inclusive bid fee."
            % baseline_usd,
            "Added scope is priced separately from in-scope defect correction.",
            "Travel/onsite is excluded from base and is never auto-authorized.",
            "This quote is not an invoice, payment, submission, or schedule.",
        ],
    }
    result["baseline"]["milestone_split"] = list(BASELINE["milestone_split"])
    result["baseline"]["milestone_amounts_usd"] = list(BASELINE["milestone_amounts_usd"])
    result["baseline"]["groups"] = list(BASELINE["groups"])
    result["baseline"]["dimensions"] = list(BASELINE["dimensions"])
    result["baseline"]["horizon_weeks"] = list(BASELINE["horizon_weeks"])
    return result


def render_worksheet(result):
    t = result["totals"]
    lines = [
        "# RFQ 18649 scope-change quotation (PROPOSED / NOT ACCEPTED)",
        "",
        "Baseline TJLabs subcontract workshare: **$%s** (not the prime bid fee)."
        % "{:,}".format(t["baseline_usd"]),
        "Incremental hours: **%s**." % t["incremental_hours"],
        "Incremental USD: **%s**."
        % (
            "HOLD"
            if t["incremental_usd"] is None
            else "$" + "{:,}".format(t["incremental_usd"])
        ),
        "Quoted total: **%s**."
        % (
            "HOLD"
            if t["quoted_total_usd"] is None
            else "$" + "{:,}".format(t["quoted_total_usd"])
        ),
        "Status: **%s**." % t["status"],
        "",
        "| ID | Type | Class | Qty | Hours | USD | Status |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for ln in result["lines"]:
        usd = "HOLD" if ln["usd"] is None else ln["usd"]
        lines.append(
            "| %s | %s | %s | %s | %s | %s | %s |"
            % (
                ln["id"],
                ln["type"] or "",
                ln["class"],
                ln["quantity"],
                ln["hours"],
                usd,
                ln["status"],
            )
        )
    lines += ["", "## Notes", ""]
    for n in result["notes"]:
        lines.append("- %s" % n)
    if result["issues"]:
        lines += ["", "## Issues", ""]
        for i in result["issues"]:
            lines.append("- **%s** `%s` %s" % (i["severity"], i["code"], i["detail"]))
    return "\n".join(lines) + "\n"
