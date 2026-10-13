"""Exact-decimal weekly cash-flow engine.

Events, invoices, and cash receipts are distinct. Prime-to-University
planning amounts never fund the TJLabs model. Imputed effort is noncash.
"""

from __future__ import annotations

from decimal import Decimal

try:
    from .canonical import AUTHORITY, BASE_TOTAL, OPTIONAL_READOUT, ROLES, SCENARIOS
    from .workbook import CashflowError, D
except ImportError:
    from canonical import AUTHORITY, BASE_TOTAL, OPTIONAL_READOUT, ROLES, SCENARIOS
    from workbook import CashflowError, D

ZERO = Decimal("0.00")
CENT = Decimal("0.01")


def _week_money(horizon):
    return [ZERO for _ in range(horizon)]


def _lag_for(scenario, assumptions):
    if scenario == "delayed_collection":
        return assumptions["collection_lag_delayed_weeks"]
    return assumptions["collection_lag_prompt_weeks"]


def _final_event_week(scenario, assumptions):
    if scenario == "extended_final_review":
        return assumptions["extended_final_event_week"]
    return assumptions["final_event_week"]


def milestone_calendar(assumptions, scenario):
    """Return event/invoice/cash weeks for the three base milestones + optional."""
    lag = _lag_for(scenario, assumptions)
    final_event = _final_event_week(scenario, assumptions)
    kickoff_event = assumptions["kickoff_event_week"]
    draft_event = assumptions["draft_event_week"]
    rows = [
        {
            "id": "kickoff",
            "amount": D(assumptions["base_milestones"][0]["amount"], "kickoff"),
            "event_week": kickoff_event,
            "invoice_week": kickoff_event + assumptions.get("kickoff_invoice_offset_weeks", 0),
            "event": "written_authorization",
        },
        {
            "id": "draft",
            "amount": D(assumptions["base_milestones"][1]["amount"], "draft"),
            "event_week": draft_event,
            "invoice_week": draft_event + assumptions.get("draft_invoice_offset_weeks", 0),
            "event": "draft_delivery",
        },
        {
            "id": "final",
            "amount": D(assumptions["base_milestones"][2]["amount"], "final"),
            "event_week": final_event,
            "invoice_week": final_event + assumptions.get("final_invoice_offset_weeks", 0),
            "event": "written_final_acceptance",
        },
    ]
    for row in rows:
        row["cash_week"] = row["invoice_week"] + lag
        row["in_base"] = True
    if assumptions["optional_readout_enabled"]:
        opt_event = assumptions["optional_event_week"]
        rows.append(
            {
                "id": "optional_readout",
                "amount": OPTIONAL_READOUT,
                "event_week": opt_event,
                "invoice_week": opt_event,
                "cash_week": opt_event + lag,
                "event": "separate_written_authorization",
                "in_base": False,
            }
        )
    return rows


def project_scenario(workbook, scenario):
    if scenario not in SCENARIOS:
        raise CashflowError("unknown scenario %r" % scenario)
    a = workbook["assumptions"]
    horizon = a["horizon_weeks"]
    opening = D(a["opening_liquidity_usd"], "opening_liquidity_usd")
    cost = D(a["cash_cost_usd_per_week"], "cash_cost_usd_per_week")
    imputed = D(a["imputed_effort_usd_per_week"], "imputed_effort_usd_per_week")
    cost_weeks = a["cash_cost_weeks"]
    imputed_weeks = a["imputed_weeks"]
    miles = milestone_calendar(a, scenario)

    out_of_horizon = []
    receipts = _week_money(horizon)
    invoices = _week_money(horizon)
    events = [[] for _ in range(horizon)]
    invoice_marks = [[] for _ in range(horizon)]
    cash_marks = [[] for _ in range(horizon)]
    base_receipts = ZERO
    optional_receipts = ZERO

    for m in miles:
        for label, week in (
            ("event", m["event_week"]),
            ("invoice", m["invoice_week"]),
            ("cash", m["cash_week"]),
        ):
            if week >= horizon:
                out_of_horizon.append(
                    {"milestone": m["id"], "kind": label, "week": week, "horizon": horizon}
                )
        if m["invoice_week"] < horizon:
            invoices[m["invoice_week"]] += m["amount"]
            invoice_marks[m["invoice_week"]].append(m["id"])
        if m["event_week"] < horizon:
            events[m["event_week"]].append(m["id"] + ":" + m["event"])
        if m["cash_week"] < horizon:
            receipts[m["cash_week"]] += m["amount"]
            cash_marks[m["cash_week"]].append(m["id"])
            if m["in_base"]:
                base_receipts += m["amount"]
            else:
                optional_receipts += m["amount"]

    if out_of_horizon:
        raise CashflowError("out-of-horizon movements: %r" % out_of_horizon)

    if not a["optional_readout_enabled"] and base_receipts != BASE_TOTAL:
        raise CashflowError("base receipts %s != %s" % (base_receipts, BASE_TOTAL))
    if a["optional_readout_enabled"] and base_receipts != BASE_TOTAL:
        raise CashflowError("enabling optional readout must not change base receipts")

    weekly = []
    closing = opening
    trough = None
    trough_week = None
    for w in range(horizon):
        cash_cost = cost if w < cost_weeks else ZERO
        imputed_effort = imputed if w < imputed_weeks else ZERO
        pre_receipt = (closing - cash_cost).quantize(CENT)
        new_closing = (pre_receipt + receipts[w]).quantize(CENT)
        if trough is None or pre_receipt < trough:
            trough = pre_receipt
            trough_week = w
        weekly.append(
            {
                "week": w,
                "cash_cost": cash_cost,
                "imputed_effort_noncash": imputed_effort,
                "invoices_issued": invoices[w],
                "receipts": receipts[w],
                "pre_receipt_cash": pre_receipt,
                "closing_cash": new_closing,
                "events": list(events[w]),
                "invoice_ids": list(invoice_marks[w]),
                "cash_ids": list(cash_marks[w]),
            }
        )
        closing = new_closing

    # Peak funding with opening forced to zero (same costs/receipts).
    zero_trough = None
    z_close = ZERO
    for row in weekly:
        z_pre = (z_close - row["cash_cost"]).quantize(CENT)
        if zero_trough is None or z_pre < zero_trough:
            zero_trough = z_pre
        z_close = (z_pre + row["receipts"]).quantize(CENT)
    peak_before_opening = max(ZERO, -zero_trough).quantize(CENT)
    incremental_after_opening = max(ZERO, -trough).quantize(CENT)

    return {
        "scenario": scenario,
        "opening_liquidity_usd": opening,
        "horizon_weeks": horizon,
        "milestones": miles,
        "weekly": weekly,
        "trough": {
            "pre_receipt_cash": trough,
            "week": trough_week,
        },
        "funding": {
            "peak_funding_before_opening_liquidity": peak_before_opening,
            "incremental_need_after_opening_liquidity": incremental_after_opening,
        },
        "totals": {
            "base_receipts_usd": base_receipts,
            "optional_receipts_usd": optional_receipts,
            "cash_cost_usd": (cost * cost_weeks).quantize(CENT),
            "imputed_effort_noncash_usd": (imputed * imputed_weeks).quantize(CENT),
            "closing_cash_usd": weekly[-1]["closing_cash"] if weekly else opening,
        },
        "optional_in_base": False,
        "authority": dict(AUTHORITY),
        "roles": dict(ROLES),
    }


def project_all(workbook):
    return {name: project_scenario(workbook, name) for name in SCENARIOS}


def prime_university_register(workbook):
    """Planning register only. Amounts never enter TJLabs receipts."""
    return {
        "isolated": True,
        "funds_tjlabs_cash_model": False,
        "note": (
            "Prime-to-University invoices are a separate planning register. "
            "They are not Attribute 9's all-inclusive prime fee, not a TJLabs "
            "receipt, and not a guarantee that a subcontract will be paid."
        ),
        "rows": [
            {
                "id": "PU-PLAN-01",
                "description": "Prime University-facing assessment invoice (PLACEHOLDER)",
                "amount_usd": None,
                "status": "UNKNOWN_NOT_USED_IN_TJLABS_MODEL",
            }
        ],
        "tjlabs_base_workshare_usd": str(BASE_TOTAL),
    }
