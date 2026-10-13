"""Load and validate the editable staffing workbook."""

from __future__ import annotations

import json
import os
from decimal import Decimal, InvalidOperation

try:
    from .canonical import COMMERCIAL_BLOB, PARTICIPANT_SCENARIOS, SCHEMA, SPECIALIST_HOURS_IN_BASE
except ImportError:
    from canonical import COMMERCIAL_BLOB, PARTICIPANT_SCENARIOS, SCHEMA, SPECIALIST_HOURS_IN_BASE

MAX_FILE_BYTES = 200_000


class StaffingError(Exception):
    """Workbook cannot be scheduled without inventing an input."""


def D(value, field):
    if isinstance(value, bool) or value is None:
        raise StaffingError("%s must be a decimal string" % field)
    try:
        qty = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise StaffingError("%s is not a decimal: %r" % (field, value))
    if qty < 0:
        raise StaffingError("%s is negative" % field)
    return qty.quantize(Decimal("0.01"))


def load_workbook(path):
    st = os.stat(path)
    if st.st_size > MAX_FILE_BYTES:
        raise StaffingError("workbook %r exceeds %d bytes" % (path, MAX_FILE_BYTES))
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise StaffingError("workbook must be a JSON object")
    validate_workbook(data)
    return data


def validate_workbook(data):
    if data.get("schema") != SCHEMA:
        raise StaffingError("unsupported schema %r" % (data.get("schema"),))
    if data.get("commercial_blob") != COMMERCIAL_BLOB:
        raise StaffingError("workbook commercial_blob is not the pinned COMMERCIAL.md blob")
    a = data.get("assumptions")
    if not isinstance(a, dict):
        raise StaffingError("assumptions must be an object")
    horizon = a.get("horizon_weeks")
    if horizon not in (6, 8):
        raise StaffingError("horizon_weeks must be 6 or 8")
    for key in ("specialist_capacity_hours_per_week", "prime_capacity_hours_per_week"):
        cap = D(a.get(key), key)
        if cap == 0:
            raise StaffingError("%s is zero; invalid capacity is rejected" % key)
    for key in (
        "evidence_access_delay_weeks",
        "interview_schedule_delay_weeks",
        "review_delay_weeks",
    ):
        v = a.get(key)
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            raise StaffingError("%s must be a non-negative JSON integer" % key)
    parts = a.get("participant_count")
    if parts not in PARTICIPANT_SCENARIOS:
        raise StaffingError("participant_count must be one of %s" % (PARTICIPANT_SCENARIOS,))
    hours = a.get("specialist_task_hours")
    if not isinstance(hours, dict):
        raise StaffingError("specialist_task_hours must be an object")
    total = Decimal("0.00")
    for task, raw in hours.items():
        total += D(raw, "specialist_task_hours." + task)
    if total != SPECIALIST_HOURS_IN_BASE:
        raise StaffingError(
            "specialist task hours %s do not reconcile to %s" % (total, SPECIALIST_HOURS_IN_BASE)
        )
    onsite = D(a.get("specialist_onsite_subset_hours"), "specialist_onsite_subset_hours")
    if onsite != 0:
        raise StaffingError("TJLabs onsite subset must stay 0 (remote default; travel excluded)")
    prime_onsite = D(a.get("prime_onsite_subset_hours"), "prime_onsite_subset_hours")
    prime_interviews = D(a.get("prime_task_hours", {}).get("interviews"), "prime interviews")
    if prime_onsite > prime_interviews:
        raise StaffingError("prime onsite subset cannot exceed interview hours")
    return data
