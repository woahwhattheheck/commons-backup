"""Load and validate the editable cash-flow workbook (JSON)."""

from __future__ import annotations

import json
import os
from decimal import Decimal, InvalidOperation

try:
    from .canonical import (
        BASE_MILESTONES,
        BASE_TOTAL,
        COMMERCIAL_BLOB,
        OPTIONAL_READOUT,
        SCHEMA,
    )
except ImportError:
    from canonical import (
        BASE_MILESTONES,
        BASE_TOTAL,
        COMMERCIAL_BLOB,
        OPTIONAL_READOUT,
        SCHEMA,
    )

MAX_FILE_BYTES = 200_000
MAX_HORIZON = 52


class CashflowError(Exception):
    """Workbook cannot be projected without inventing an input."""


def D(value, field):
    if isinstance(value, bool) or value is None:
        raise CashflowError("%s must be a decimal string" % field)
    try:
        qty = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise CashflowError("%s is not a decimal: %r" % (field, value))
    if qty.as_tuple().exponent < -2:
        raise CashflowError("%s has sub-cent precision: %r" % (field, value))
    return qty.quantize(Decimal("0.01"))


def load_workbook(path):
    st = os.stat(path)
    if st.st_size > MAX_FILE_BYTES:
        raise CashflowError("workbook %r exceeds %d bytes" % (path, MAX_FILE_BYTES))
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise CashflowError("workbook must be a JSON object")
    validate_workbook(data)
    return data


def validate_workbook(data):
    if data.get("schema") != SCHEMA:
        raise CashflowError("unsupported schema %r" % (data.get("schema"),))
    if data.get("commercial_blob") != COMMERCIAL_BLOB:
        raise CashflowError(
            "workbook commercial_blob %r is not pinned %r"
            % (data.get("commercial_blob"), COMMERCIAL_BLOB)
        )
    a = data.get("assumptions")
    if not isinstance(a, dict):
        raise CashflowError("assumptions must be an object")
    horizon = a.get("horizon_weeks")
    if not isinstance(horizon, int) or isinstance(horizon, bool):
        raise CashflowError("horizon_weeks must be a JSON integer")
    if horizon < 1 or horizon > MAX_HORIZON:
        raise CashflowError("horizon_weeks out of bounds")
    for key in (
        "opening_liquidity_usd",
        "cash_cost_usd_per_week",
        "imputed_effort_usd_per_week",
        "optional_readout_usd",
    ):
        D(a.get(key), key)
    if D(a.get("optional_readout_usd"), "optional_readout_usd") != OPTIONAL_READOUT:
        raise CashflowError("optional readout must stay $4000.00")
    for key in (
        "cash_cost_weeks",
        "imputed_weeks",
        "collection_lag_prompt_weeks",
        "collection_lag_delayed_weeks",
        "kickoff_event_week",
        "draft_event_week",
        "final_event_week",
        "extended_final_event_week",
        "optional_event_week",
    ):
        v = a.get(key)
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            raise CashflowError("%s must be a non-negative JSON integer" % key)
    if a.get("optional_readout_enabled") not in (True, False):
        raise CashflowError("optional_readout_enabled must be a JSON boolean")
    rows = a.get("base_milestones")
    if not isinstance(rows, list) or len(rows) != 3:
        raise CashflowError("base_milestones must have three rows")
    total = Decimal("0.00")
    for expected, row in zip(BASE_MILESTONES, rows):
        if row.get("id") != expected["id"]:
            raise CashflowError("milestone id %r is not %r" % (row.get("id"), expected["id"]))
        amt = D(row.get("amount"), "milestone " + expected["id"])
        if amt != expected["amount"]:
            raise CashflowError("milestone %s amount is not $%s" % (expected["id"], expected["amount"]))
        if row.get("event") != expected["event"]:
            raise CashflowError("milestone %s event was rewritten" % expected["id"])
        total += amt
    if total != BASE_TOTAL:
        raise CashflowError("base milestones %s do not reconcile to $%s" % (total, BASE_TOTAL))
    return data
