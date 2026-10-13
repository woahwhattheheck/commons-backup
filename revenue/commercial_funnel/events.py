from __future__ import annotations

from datetime import datetime
from typing import Any

from .common import (
    ALL_STAGES,
    MAX_EVIDENCE_AGE_SECONDS,
    STAGE_INDEX,
    FunnelError,
    exact_keys,
    parse_time,
    require_id,
    validate_money,
    validate_noncash,
    validate_source,
)


def validate_event(raw: Any, field: str, as_of: datetime) -> tuple[dict[str, Any], list[str]]:
    event = exact_keys(raw, required=("id", "stage", "observed_at", "evidence"), optional=("proves", "money", "noncash", "reversal_of"), field=field)
    event_id = require_id(event["id"], f"{field}.id")
    stage = event["stage"]
    if stage not in ALL_STAGES:
        raise FunnelError(f"{field}.stage invalid")
    observed_raw = event["observed_at"]
    observed = parse_time(observed_raw, f"{field}.observed_at")
    reasons: list[str] = []
    if observed > as_of:
        reasons.append("EVIDENCE_FROM_FUTURE")
    if int((as_of - observed).total_seconds()) > MAX_EVIDENCE_AGE_SECONDS:
        reasons.append("EVIDENCE_STALE")
    evidence = validate_source(event["evidence"], f"{field}.evidence")

    proves_raw = event.get("proves", [])
    if not isinstance(proves_raw, list):
        raise FunnelError(f"{field}.proves must be array")
    proves: list[str] = []
    seen_proves: set[str] = set()
    for i, proved in enumerate(proves_raw):
        if proved not in STAGE_INDEX:
            raise FunnelError(f"{field}.proves[{i}] invalid")
        if stage not in STAGE_INDEX:
            raise FunnelError(f"{field}.proves not allowed for special stage")
        if STAGE_INDEX[proved] >= STAGE_INDEX[stage]:
            raise FunnelError(f"{field}.proves may contain only prior stages")
        if proved in seen_proves:
            raise FunnelError(f"{field}.proves duplicate stage")
        seen_proves.add(proved)
        proves.append(proved)
    proves.sort(key=STAGE_INDEX.__getitem__)

    out: dict[str, Any] = {"id": event_id, "stage": stage, "observed_at": observed_raw, "evidence": evidence, "proves": proves}
    if stage == "CASH":
        if "money" not in event:
            raise FunnelError(f"{field}.money required for CASH")
        out["money"] = validate_money(event["money"], f"{field}.money")
        if "noncash" in event or "reversal_of" in event:
            raise FunnelError(f"{field} CASH cannot carry noncash/reversal_of")
    elif stage == "CASH_REVERSAL":
        if "money" not in event or "reversal_of" not in event:
            raise FunnelError(f"{field} CASH_REVERSAL requires money and reversal_of")
        out["money"] = validate_money(event["money"], f"{field}.money")
        out["reversal_of"] = require_id(event["reversal_of"], f"{field}.reversal_of")
        if "noncash" in event:
            raise FunnelError(f"{field} CASH_REVERSAL cannot carry noncash")
    elif stage == "NONCASH_AWARD":
        if "noncash" not in event:
            raise FunnelError(f"{field}.noncash required for NONCASH_AWARD")
        out["noncash"] = validate_noncash(event["noncash"], f"{field}.noncash")
        if "money" in event or "reversal_of" in event:
            raise FunnelError(f"{field} NONCASH_AWARD cannot carry cash fields")
    elif "money" in event or "noncash" in event or "reversal_of" in event:
        raise FunnelError(f"{field} non-money stage cannot carry money/noncash/reversal")
    return out, reasons
