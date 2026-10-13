from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

INPUT_SCHEMA = "invoice-resolution-pilot-input/v1"
PACKET_SCHEMA = "invoice-resolution-pilot-packet/v1"
PRODUCT_ID = "invoice-resolution-portal-pilot"
COMMERCIAL_STATE = "PROPOSED_NOT_ACCEPTED"
PRICE_USD = 2500
OPTIONAL_INTEGRATION_USD = 5000

ACTIONS = (
    "ACKNOWLEDGE_BALANCE",
    "OPEN_DISPUTE",
    "REQUEST_PAYMENT_PLAN_DISCUSSION",
)
EVIDENCE_CLASSES = ("CUSTOMER_PROVIDED", "INVOICE_SUPPORT")
EVENT_TYPES = ("REQUEST_SUBMITTED", "EVIDENCE_ATTACHED")
GENESIS_ROOT = "0" * 64
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")

HOLD_ORDER = (
    "HOLD_PRIOR_CHECKPOINT_OUT_OF_RANGE",
    "HOLD_PRIOR_CHAIN_MISMATCH",
    "HOLD_EVENT_CHRONOLOGY",
    "HOLD_FUTURE_EVENT",
    "HOLD_INVOICE_GENERATION_MISMATCH",
    "HOLD_REQUEST_REPLAY_MISMATCH",
    "HOLD_MULTIPLE_REQUESTS_OUT_OF_SCOPE",
    "HOLD_EVIDENCE_WITHOUT_REQUEST",
    "HOLD_EVIDENCE_REPLAY_MISMATCH",
    "HOLD_NO_REQUEST",
)
HOLD_INDEX = {value: idx for idx, value in enumerate(HOLD_ORDER)}

AUTHORITY = {
    "can_send_buyer_message": False,
    "can_take_payment": False,
    "can_approve_payment_plan": False,
    "can_adjudicate_dispute": False,
    "can_modify_invoice": False,
    "can_make_accounting_conclusion": False,
    "can_make_legal_conclusion": False,
    "customer_acceptance_claimed": False,
    "payment_claimed": False,
    "revenue_claimed": False,
}


class ContractError(ValueError):
    pass


def _pairs_no_duplicates(pairs: Iterable[Tuple[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ContractError("duplicate JSON key: %s" % key)
        out[key] = value
    return out


def _reject_constant(value: str) -> None:
    raise ContractError("non-finite JSON number: %s" % value)


def loads_strict(text: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise ContractError("invalid JSON: %s" % exc) from exc


def load_json_file(path: str) -> Any:
    raw = Path(path).read_bytes()
    if len(raw) > 1_000_000:
        raise ContractError("input exceeds 1,000,000 bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("input must be UTF-8") from exc
    return loads_strict(text)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _exact_keys(obj: Any, keys: Iterable[str], name: str) -> Mapping[str, Any]:
    if type(obj) is not dict:
        raise ContractError("%s must be an object" % name)
    expected = set(keys)
    actual = set(obj.keys())
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ContractError("%s keys mismatch missing=%r extra=%r" % (name, missing, extra))
    return obj


def _id(value: Any, name: str) -> str:
    if type(value) is not str or not ID_RE.fullmatch(value):
        raise ContractError("%s must be a narrow opaque identifier" % name)
    return value


def _hex64(value: Any, name: str) -> str:
    if type(value) is not str or not HEX64_RE.fullmatch(value):
        raise ContractError("%s must be lowercase sha256 hex" % name)
    return value


def _int(value: Any, name: str, minimum: int = 0, maximum: int = 10**15) -> int:
    if type(value) is not int or value < minimum or value > maximum:
        raise ContractError("%s must be an integer in [%d, %d]" % (name, minimum, maximum))
    return value


def _timestamp(value: Any, name: str) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise ContractError("%s must be an RFC3339 UTC timestamp ending in Z" % name)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError("%s is not a valid timestamp" % name) from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ContractError("%s must be UTC" % name)
    return parsed


def _currency(value: Any) -> str:
    if type(value) is not str or not CURRENCY_RE.fullmatch(value):
        raise ContractError("invoice.currency must be three uppercase ASCII letters")
    return value


def _invoice_binding(invoice: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "invoice_id": invoice["invoice_id"],
        "revision": invoice["revision"],
        "snapshot_sha256": invoice["snapshot_sha256"],
    }


def _event_binding(event: Mapping[str, Any]) -> Dict[str, Any]:
    binding = _exact_keys(
        event["invoice_binding"],
        ("invoice_id", "revision", "snapshot_sha256"),
        "event.invoice_binding",
    )
    return {
        "invoice_id": _id(binding["invoice_id"], "event.invoice_binding.invoice_id"),
        "revision": _id(binding["revision"], "event.invoice_binding.revision"),
        "snapshot_sha256": _hex64(
            binding["snapshot_sha256"], "event.invoice_binding.snapshot_sha256"
        ),
    }


def _validate_input(data: Any) -> Mapping[str, Any]:
    top = _exact_keys(
        data,
        ("schema", "case_id", "evaluated_at", "invoice", "prior_checkpoint", "events"),
        "input",
    )
    if top["schema"] != INPUT_SCHEMA:
        raise ContractError("unsupported input schema")
    _id(top["case_id"], "case_id")
    evaluated_at = _timestamp(top["evaluated_at"], "evaluated_at")

    invoice = _exact_keys(
        top["invoice"],
        (
            "invoice_id",
            "revision",
            "snapshot_sha256",
            "currency",
            "amount_minor",
            "balance_minor",
            "observed_at",
            "customer_ref",
        ),
        "invoice",
    )
    _id(invoice["invoice_id"], "invoice.invoice_id")
    _id(invoice["revision"], "invoice.revision")
    _hex64(invoice["snapshot_sha256"], "invoice.snapshot_sha256")
    _currency(invoice["currency"])
    amount = _int(invoice["amount_minor"], "invoice.amount_minor")
    balance = _int(invoice["balance_minor"], "invoice.balance_minor")
    if balance > amount:
        raise ContractError("invoice.balance_minor cannot exceed invoice.amount_minor")
    observed = _timestamp(invoice["observed_at"], "invoice.observed_at")
    if observed > evaluated_at:
        raise ContractError("invoice.observed_at cannot be after evaluated_at")
    _id(invoice["customer_ref"], "invoice.customer_ref")

    checkpoint = top["prior_checkpoint"]
    if checkpoint is not None:
        checkpoint = _exact_keys(
            checkpoint, ("event_count", "chain_root_sha256"), "prior_checkpoint"
        )
        _int(checkpoint["event_count"], "prior_checkpoint.event_count", 0, 1000)
        _hex64(checkpoint["chain_root_sha256"], "prior_checkpoint.chain_root_sha256")

    events = top["events"]
    if type(events) is not list or len(events) > 1000:
        raise ContractError("events must be a list of at most 1000 entries")

    for idx, event in enumerate(events):
        event = _exact_keys(
            event,
            ("event_id", "event_type", "observed_at", "invoice_binding", "payload"),
            "events[%d]" % idx,
        )
        _id(event["event_id"], "events[%d].event_id" % idx)
        if event["event_type"] not in EVENT_TYPES:
            raise ContractError("events[%d].event_type is unsupported" % idx)
        _timestamp(event["observed_at"], "events[%d].observed_at" % idx)
        _event_binding(event)
        payload = event["payload"]
        if event["event_type"] == "REQUEST_SUBMITTED":
            payload = _exact_keys(
                payload,
                ("request_id", "action", "statement_sha256"),
                "events[%d].payload" % idx,
            )
            _id(payload["request_id"], "events[%d].payload.request_id" % idx)
            if payload["action"] not in ACTIONS:
                raise ContractError("events[%d].payload.action is unsupported" % idx)
            _hex64(
                payload["statement_sha256"],
                "events[%d].payload.statement_sha256" % idx,
            )
        else:
            payload = _exact_keys(
                payload,
                ("request_id", "evidence_id", "evidence_sha256", "evidence_class"),
                "events[%d].payload" % idx,
            )
            _id(payload["request_id"], "events[%d].payload.request_id" % idx)
            _id(payload["evidence_id"], "events[%d].payload.evidence_id" % idx)
            _hex64(
                payload["evidence_sha256"],
                "events[%d].payload.evidence_sha256" % idx,
            )
            if payload["evidence_class"] not in EVIDENCE_CLASSES:
                raise ContractError(
                    "events[%d].payload.evidence_class is unsupported" % idx
                )
    return top


def _chain(events: List[Mapping[str, Any]]) -> Tuple[List[Dict[str, Any]], str]:
    root = GENESIS_ROOT
    chain: List[Dict[str, Any]] = []
    for idx, event in enumerate(events, start=1):
        event_sha = _sha(event)
        root = _sha({"sequence": idx, "previous_root_sha256": root, "event_sha256": event_sha})
        chain.append(
            {
                "sequence": idx,
                "event_id": event["event_id"],
                "event_sha256": event_sha,
                "chain_root_sha256": root,
            }
        )
    return chain, root


def _hold(holds: List[str], reason: str) -> None:
    if reason not in holds:
        holds.append(reason)


def _sort_holds(holds: List[str]) -> List[str]:
    return sorted(holds, key=lambda item: HOLD_INDEX.get(item, 10_000))


def compile_packet(data: Any) -> Dict[str, Any]:
    source = _validate_input(data)
    evaluated_at = _timestamp(source["evaluated_at"], "evaluated_at")
    invoice = source["invoice"]
    invoice_binding = _invoice_binding(invoice)
    events: List[Mapping[str, Any]] = source["events"]
    chain, chain_root = _chain(events)
    holds: List[str] = []

    checkpoint = source["prior_checkpoint"]
    if checkpoint is not None:
        count = checkpoint["event_count"]
        if count > len(events):
            _hold(holds, "HOLD_PRIOR_CHECKPOINT_OUT_OF_RANGE")
        else:
            observed_root = GENESIS_ROOT if count == 0 else chain[count - 1]["chain_root_sha256"]
            if observed_root != checkpoint["chain_root_sha256"]:
                _hold(holds, "HOLD_PRIOR_CHAIN_MISMATCH")

    seen_event_ids = set()
    previous_time: Optional[datetime] = None
    requests: Dict[str, Dict[str, Any]] = {}
    request_order: List[str] = []
    replay_count: Dict[str, int] = {}
    evidence: Dict[str, Dict[str, Any]] = {}
    evidence_order: List[str] = []

    for idx, event in enumerate(events):
        event_id = event["event_id"]
        if event_id in seen_event_ids:
            raise ContractError("duplicate event_id: %s" % event_id)
        seen_event_ids.add(event_id)

        event_time = _timestamp(event["observed_at"], "events[%d].observed_at" % idx)
        if previous_time is not None and event_time < previous_time:
            _hold(holds, "HOLD_EVENT_CHRONOLOGY")
        previous_time = event_time
        if event_time > evaluated_at:
            _hold(holds, "HOLD_FUTURE_EVENT")

        if _event_binding(event) != invoice_binding:
            _hold(holds, "HOLD_INVOICE_GENERATION_MISMATCH")

        payload = event["payload"]
        if event["event_type"] == "REQUEST_SUBMITTED":
            request_id = payload["request_id"]
            canonical_request = {
                "request_id": request_id,
                "action": payload["action"],
                "statement_sha256": payload["statement_sha256"],
                "invoice_binding": _event_binding(event),
            }
            if request_id not in requests:
                requests[request_id] = canonical_request
                request_order.append(request_id)
                replay_count[request_id] = 0
            elif requests[request_id] == canonical_request:
                replay_count[request_id] += 1
            else:
                _hold(holds, "HOLD_REQUEST_REPLAY_MISMATCH")
        else:
            request_id = payload["request_id"]
            if request_id not in requests:
                _hold(holds, "HOLD_EVIDENCE_WITHOUT_REQUEST")
            evidence_id = payload["evidence_id"]
            canonical_evidence = {
                "evidence_id": evidence_id,
                "request_id": request_id,
                "evidence_sha256": payload["evidence_sha256"],
                "evidence_class": payload["evidence_class"],
                "invoice_binding": _event_binding(event),
            }
            if evidence_id not in evidence:
                evidence[evidence_id] = canonical_evidence
                evidence_order.append(evidence_id)
            elif evidence[evidence_id] != canonical_evidence:
                _hold(holds, "HOLD_EVIDENCE_REPLAY_MISMATCH")

    if not requests:
        _hold(holds, "HOLD_NO_REQUEST")
    if len(requests) > 1:
        _hold(holds, "HOLD_MULTIPLE_REQUESTS_OUT_OF_SCOPE")

    selected_request: Optional[Dict[str, Any]] = None
    if len(request_order) == 1:
        req_id = request_order[0]
        selected_request = dict(requests[req_id])
        selected_request["identical_replay_count"] = replay_count[req_id]

    evidence_rows = [evidence[eid] for eid in evidence_order]
    action = selected_request["action"] if selected_request else None
    owner_review_export = {
        "review_required": True,
        "request_action": action,
        "review_instruction": (
            "Review the bound request and evidence. Record any business decision "
            "outside this compiler; this packet grants no payment, dispute, invoice, "
            "accounting, or legal authority."
        ),
        "customer_response_required_before_execution": False,
        "decision_authority": "HUMAN_OWNER_REQUIRED",
    }

    packet: Dict[str, Any] = {
        "schema": PACKET_SCHEMA,
        "product": {
            "product_id": PRODUCT_ID,
            "commercial_state": COMMERCIAL_STATE,
            "pilot_price_usd": PRICE_USD,
            "optional_integration_price_usd": OPTIONAL_INTEGRATION_USD,
            "scope": "ONE_INVOICE_ONE_WORKFLOW_ONE_INTAKE_SURFACE",
        },
        "case_id": source["case_id"],
        "evaluated_at": source["evaluated_at"],
        "invoice": {
            **invoice_binding,
            "currency": invoice["currency"],
            "amount_minor": invoice["amount_minor"],
            "balance_minor": invoice["balance_minor"],
            "observed_at": invoice["observed_at"],
            "customer_ref": invoice["customer_ref"],
        },
        "state": "OWNER_REVIEW_READY" if not holds else "HOLD",
        "holds": _sort_holds(holds),
        "request": selected_request,
        "evidence": evidence_rows,
        "event_chain": chain,
        "event_chain_root_sha256": chain_root,
        "next_checkpoint": {
            "event_count": len(events),
            "chain_root_sha256": chain_root,
        },
        "owner_review_export": owner_review_export,
        "authority": dict(AUTHORITY),
    }
    packet["receipt_sha256"] = _sha(packet)
    return packet


def verify_packet(data: Any, packet: Any) -> bool:
    if type(packet) is not dict:
        return False
    supplied = packet.get("receipt_sha256")
    if type(supplied) is not str or not HEX64_RE.fullmatch(supplied):
        return False
    without_receipt = dict(packet)
    without_receipt.pop("receipt_sha256", None)
    if _sha(without_receipt) != supplied:
        return False
    expected = compile_packet(data)
    return _canonical(expected) == _canonical(packet)


def render_owner_report(packet: Mapping[str, Any]) -> str:
    if packet.get("schema") != PACKET_SCHEMA:
        raise ContractError("unsupported packet schema")
    lines = [
        "# Invoice Resolution Pilot — Owner Review",
        "",
        "**State:** `%s`" % packet["state"],
        "**Commercial state:** `%s`" % packet["product"]["commercial_state"],
        "**Pilot price:** `$%d` (proposed, not accepted)" % packet["product"]["pilot_price_usd"],
        "",
        "## Invoice generation",
        "",
        "- invoice id: `%s`" % packet["invoice"]["invoice_id"],
        "- revision: `%s`" % packet["invoice"]["revision"],
        "- snapshot sha256: `%s`" % packet["invoice"]["snapshot_sha256"],
        "- event chain root: `%s`" % packet["event_chain_root_sha256"],
        "",
        "## Request",
        "",
    ]
    request = packet.get("request")
    if request:
        lines += [
            "- request id: `%s`" % request["request_id"],
            "- action: `%s`" % request["action"],
            "- identical replay count: `%d`" % request["identical_replay_count"],
        ]
    else:
        lines.append("- none")
    lines += ["", "## Holds", ""]
    holds = packet.get("holds") or []
    if holds:
        lines.extend("- `%s`" % hold for hold in holds)
    else:
        lines.append("- none")
    lines += [
        "",
        "## Authority ceiling",
        "",
        "This artifact does not take payment, approve a plan, adjudicate a dispute, "
        "modify an invoice, send a buyer message, or make accounting/legal conclusions.",
        "",
        "Receipt: `%s`" % packet["receipt_sha256"],
        "",
    ]
    return "\n".join(lines)


def _write_exclusive(path: str, text: str) -> None:
    target = Path(path)
    with target.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="invoice-resolution-pilot")
    sub = parser.add_subparsers(dest="command", required=True)

    compile_cmd = sub.add_parser("compile")
    compile_cmd.add_argument("--input", required=True)
    compile_cmd.add_argument("--packet-out")
    compile_cmd.add_argument("--report-out")

    verify_cmd = sub.add_parser("verify")
    verify_cmd.add_argument("--input", required=True)
    verify_cmd.add_argument("--packet", required=True)

    args = parser.parse_args(argv)
    if args.command == "compile":
        data = load_json_file(args.input)
        packet = compile_packet(data)
        rendered = json.dumps(packet, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
        if args.packet_out:
            _write_exclusive(args.packet_out, rendered)
        else:
            print(rendered, end="")
        if args.report_out:
            _write_exclusive(args.report_out, render_owner_report(packet))
        return 0

    data = load_json_file(args.input)
    packet = load_json_file(args.packet)
    if not verify_packet(data, packet):
        raise ContractError("packet verification failed")
    print("VERIFIED %s" % packet["receipt_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
