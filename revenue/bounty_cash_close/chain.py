from __future__ import annotations

from typing import Any

from .core import (
    CloseBoardError, KINDS, PROVIDER_CLASSES, RAIL_CLASSES, ZERO_SHA256,
    _event_core, _keys, _sha, _text, format_utc, parse_utc, sha256_obj,
)

def _validate_event(raw: Any, label: str) -> dict[str, Any]:
    obj = _keys(
        raw,
        {
            "event_id",
            "kind",
            "observed_at_utc",
            "provider_class",
            "provider_ref",
            "external_ref",
            "evidence_sha256",
            "previous_receipt_sha256",
            "receipt_sha256",
        },
        label,
    )
    kind = obj["kind"]
    if type(kind) is not str or kind not in KINDS:
        raise CloseBoardError(f"{label}.kind invalid")
    provider_class = obj["provider_class"]
    if type(provider_class) is not str or provider_class not in PROVIDER_CLASSES:
        raise CloseBoardError(f"{label}.provider_class invalid")
    event = {
        "event_id": _text(obj["event_id"], f"{label}.event_id"),
        "kind": kind,
        "observed_at_utc": format_utc(parse_utc(obj["observed_at_utc"], f"{label}.observed_at_utc")),
        "provider_class": provider_class,
        "provider_ref": _text(obj["provider_ref"], f"{label}.provider_ref"),
        "external_ref": _text(obj["external_ref"], f"{label}.external_ref"),
        "evidence_sha256": _sha(obj["evidence_sha256"], f"{label}.evidence_sha256"),
        "previous_receipt_sha256": _sha(obj["previous_receipt_sha256"], f"{label}.previous_receipt_sha256"),
        "receipt_sha256": _sha(obj["receipt_sha256"], f"{label}.receipt_sha256"),
    }
    expected = sha256_obj(_event_core(event))
    if event["receipt_sha256"] != expected:
        raise CloseBoardError(f"{label} receipt hash mismatch")
    if kind == "PAYOUT_ACKNOWLEDGED" and provider_class != "SPONSOR":
        raise CloseBoardError("PAYOUT_ACKNOWLEDGED must be observed from SPONSOR")
    if kind == "SETTLEMENT_OBSERVED" and provider_class not in RAIL_CLASSES:
        raise CloseBoardError("SETTLEMENT_OBSERVED requires independent payment-rail provider class")
    return event

def _order_chain(receipts: list[dict[str, Any]], label: str) -> list[dict[str, Any]]:
    if not receipts:
        return []
    by_hash = {r["receipt_sha256"]: r for r in receipts}
    if len(by_hash) != len(receipts):
        raise CloseBoardError(f"{label} duplicate receipt hash")
    by_id = {r["event_id"] for r in receipts}
    if len(by_id) != len(receipts):
        raise CloseBoardError(f"{label} duplicate event_id")
    roots = [r for r in receipts if r["previous_receipt_sha256"] == ZERO_SHA256]
    if len(roots) != 1:
        raise CloseBoardError(f"{label} must have exactly one chain root")
    successors: dict[str, list[dict[str, Any]]] = {}
    for receipt in receipts:
        prev = receipt["previous_receipt_sha256"]
        if prev != ZERO_SHA256 and prev not in by_hash:
            raise CloseBoardError(f"{label} references missing previous receipt")
        successors.setdefault(prev, []).append(receipt)
    for prev, children in successors.items():
        if prev != ZERO_SHA256 and len(children) > 1:
            raise CloseBoardError(f"{label} receipt chain forks")
    ordered: list[dict[str, Any]] = []
    current = roots[0]
    seen: set[str] = set()
    while True:
        digest = current["receipt_sha256"]
        if digest in seen:
            raise CloseBoardError(f"{label} receipt chain loops")
        seen.add(digest)
        ordered.append(current)
        children = successors.get(digest, [])
        if not children:
            break
        current = children[0]
    if len(ordered) != len(receipts):
        raise CloseBoardError(f"{label} receipt chain disconnected")
    last_time = -1
    for idx, receipt in enumerate(ordered):
        when = parse_utc(receipt["observed_at_utc"], f"{label}[{idx}].observed_at_utc")
        if when <= last_time:
            raise CloseBoardError(f"{label} chronology must be strictly increasing")
        last_time = when
    return ordered

def _validate_semantics(receipts: list[dict[str, Any]]) -> None:
    kinds = [r["kind"] for r in receipts]
    for singleton in (
        "SUBMISSION_DELIVERED",
        "GATE_FOLLOWUP_SENT",
        "TECHNICAL_ACCEPTED",
        "COMPENSATION_ASK_SENT",
        "COMPENSATION_FOLLOWUP_SENT",
        "PAYOUT_ACKNOWLEDGED",
        "SETTLEMENT_OBSERVED",
        "TERMINAL_NONPAY",
    ):
        if kinds.count(singleton) > 1:
            raise CloseBoardError(f"duplicate semantic event {singleton}")
    def pos(kind: str) -> int | None:
        try:
            return kinds.index(kind)
        except ValueError:
            return None
    delivered = pos("SUBMISSION_DELIVERED")
    accepted = pos("TECHNICAL_ACCEPTED")
    ask = pos("COMPENSATION_ASK_SENT")
    follow = pos("COMPENSATION_FOLLOWUP_SENT")
    payout = pos("PAYOUT_ACKNOWLEDGED")
    settled = pos("SETTLEMENT_OBSERVED")
    gate_follow = pos("GATE_FOLLOWUP_SENT")
    blocked_positions = [i for i, k in enumerate(kinds) if k == "GATE_BLOCKED"]
    terminal = pos("TERMINAL_NONPAY")
    if accepted is not None and (delivered is None or accepted <= delivered):
        raise CloseBoardError("technical acceptance requires prior delivered submission")
    if ask is not None and (accepted is None or ask <= accepted):
        raise CloseBoardError("compensation ask requires prior technical acceptance")
    if follow is not None and (ask is None or follow <= ask):
        raise CloseBoardError("compensation follow-up requires prior compensation ask")
    if payout is not None and (ask is None or payout <= ask):
        raise CloseBoardError("payout acknowledgement requires prior compensation ask")
    if settled is not None and (payout is None or settled <= payout):
        raise CloseBoardError("settlement requires prior payout acknowledgement")
    if gate_follow is not None and not any(i < gate_follow for i in blocked_positions):
        raise CloseBoardError("gate follow-up requires prior blocked gate")
    if terminal is not None and terminal != len(kinds) - 1:
        raise CloseBoardError("terminal nonpay must be final receipt")
    if settled is not None and terminal is not None:
        raise CloseBoardError("settled and terminal nonpay conflict")
