"""Markdown / JSON / CSV renderers for the cash-flow pack."""

from __future__ import annotations

import csv
import io
import json
from decimal import Decimal

try:
    from .canonical import COMMERCIAL_BLOB, SCHEMA
    from .engine import prime_university_register, project_all
    from .formulas import weekly_formula_sheet
    from .invoices import invoice_drafts
except ImportError:
    from canonical import COMMERCIAL_BLOB, SCHEMA
    from engine import prime_university_register, project_all
    from formulas import weekly_formula_sheet
    from invoices import invoice_drafts


def _money(value):
    if value is None:
        return "UNKNOWN"
    if isinstance(value, Decimal):
        return "$" + "{:,.2f}".format(value)
    return str(value)


def _jsonable(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    return obj


def dashboard_markdown(workbook, projections):
    lines = [
        "# RFQ 18649 TJLabs cash-flow dashboard (PROPOSED / NOT ACCEPTED)",
        "",
        "Pinned COMMERCIAL.md blob `%s`." % COMMERCIAL_BLOB,
        "Relative weeks only. Events, invoices, and cash receipts are distinct.",
        "Optional $4,000 readout is excluded from base unless separately enabled.",
        "Prime-to-University amounts never fund this model.",
        "",
        "| Scenario | Trough (pre-receipt) | Peak funding before opening | Incremental need after opening | Closing |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, p in projections.items():
        lines.append(
            "| %s | %s (w%s) | %s | %s | %s |"
            % (
                name,
                _money(p["trough"]["pre_receipt_cash"]),
                p["trough"]["week"],
                _money(p["funding"]["peak_funding_before_opening_liquidity"]),
                _money(p["funding"]["incremental_need_after_opening_liquidity"]),
                _money(p["totals"]["closing_cash_usd"]),
            )
        )
    a = workbook["assumptions"]
    lines += [
        "",
        "## Assumptions",
        "",
        "- Opening liquidity: %s" % _money(Decimal(str(a["opening_liquidity_usd"]))),
        "- Weekly cash cost (weeks 0-%d): %s"
        % (a["cash_cost_weeks"] - 1, _money(Decimal(str(a["cash_cost_usd_per_week"])))),
        "- Weekly imputed effort (noncash): %s"
        % _money(Decimal(str(a["imputed_effort_usd_per_week"]))),
        "- Base receipts: $9,600 + $9,600 + $4,800 = $24,000",
        "- Optional readout enabled: %s" % a["optional_readout_enabled"],
        "",
        "## Notes",
        "",
        "- $24,000 is TJLabs subcontract workshare, not the prime bid fee.",
        "- Hypothetical milestone dates are relative weeks, not a schedule commitment.",
        "- This pack is not an invoice, payment request, or revenue event.",
        "",
    ]
    return "\n".join(lines)


def weekly_csv(projection):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "week",
            "cash_cost",
            "imputed_effort_noncash",
            "invoices_issued",
            "receipts",
            "pre_receipt_cash",
            "closing_cash",
            "events",
            "invoice_ids",
            "cash_ids",
            "D_pre_formula",
            "E_close_formula",
        ]
    )
    sheet = weekly_formula_sheet(projection)
    for row, frow in zip(projection["weekly"], sheet["rows"]):
        w.writerow(
            [
                row["week"],
                row["cash_cost"],
                row["imputed_effort_noncash"],
                row["invoices_issued"],
                row["receipts"],
                row["pre_receipt_cash"],
                row["closing_cash"],
                ";".join(row["events"]),
                ";".join(row["invoice_ids"]),
                ";".join(row["cash_ids"]),
                frow["D_pre_receipt_formula"],
                frow["E_closing_formula"],
            ]
        )
    return buf.getvalue()


def invoices_markdown(projection):
    lines = [
        "# Invoice description drafts — scenario `%s`" % projection["scenario"],
        "",
        "These are planning drafts. `live_invoice` is false.",
        "",
        "| ID | Milestone | Amount | Event week | Invoice week | Cash week | In base |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for d in invoice_drafts(projection):
        lines.append(
            "| %s | %s | %s | %s | %s | %s | %s |"
            % (
                d["id"],
                d["milestone"],
                d["amount_usd"],
                d["event_week"],
                d["invoice_week"],
                d["cash_week"],
                d["in_base"],
            )
        )
        lines.append("")
        lines.append(d["description"])
        lines.append("")
    return "\n".join(lines)


def pack(workbook):
    projections = project_all(workbook)
    return {
        "schema": SCHEMA,
        "commercial_blob": COMMERCIAL_BLOB,
        "projections": _jsonable(projections),
        "prime_university_register": prime_university_register(workbook),
        "invoices": {name: invoice_drafts(p) for name, p in projections.items()},
        "formulas": {name: _jsonable(weekly_formula_sheet(p)) for name, p in projections.items()},
        "dashboard_md": dashboard_markdown(workbook, projections),
    }
