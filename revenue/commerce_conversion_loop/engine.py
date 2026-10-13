from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
MAX_INPUT_BYTES = 1_000_000
MAX_EVENTS = 32
MAX_TEXT = 4096
MAX_REF = 512
SAFE_INT_MAX = 9_000_000_000_000_000

EVENT_TYPES = (
    "OFFER_SHIPPED", "TARGET_QUALIFIED", "OUTBOUND_SUBMITTED",
    "DELIVERY_CONFIRMED", "DELIVERY_FAILED", "REPLY_OBSERVED",
    "PROPOSAL_OBSERVED", "PAYMENT_OBSERVED",
)
STAGE_ORDER = {
    "OFFER_SHIPPED": 0, "TARGET_QUALIFIED": 1, "OUTBOUND_SUBMITTED": 2,
    "DELIVERY_CONFIRMED": 3, "DELIVERY_FAILED": 3, "REPLY_OBSERVED": 4,
    "PROPOSAL_OBSERVED": 5, "PAYMENT_OBSERVED": 6,
}
FACT_KEYS = {
    "OFFER_SHIPPED": {"offerId", "artifactRef", "artifactCommit"},
    "TARGET_QUALIFIED": {"targetId", "qualificationCode"},
    "OUTBOUND_SUBMITTED": {"providerCode", "submissionId"},
    "DELIVERY_CONFIRMED": {"deliveryId"},
    "DELIVERY_FAILED": {"failureId", "reasonCode"},
    "REPLY_OBSERVED": {"replyId"},
    "PROPOSAL_OBSERVED": {"proposalId"},
    "PAYMENT_OBSERVED": {"paymentId", "amountMinor", "currency"},
}
PARENT_TYPE = {
    "TARGET_QUALIFIED": "OFFER_SHIPPED",
    "OUTBOUND_SUBMITTED": "TARGET_QUALIFIED",
    "DELIVERY_CONFIRMED": "OUTBOUND_SUBMITTED",
    "DELIVERY_FAILED": "OUTBOUND_SUBMITTED",
    "REPLY_OBSERVED": "DELIVERY_CONFIRMED",
    "PROPOSAL_OBSERVED": "REPLY_OBSERVED",
    "PAYMENT_OBSERVED": "PROPOSAL_OBSERVED",
}
STATE_FOR_TYPE = {
    "OFFER_SHIPPED": "OFFER_ONLY",
    "TARGET_QUALIFIED": "TARGET_QUALIFIED",
    "OUTBOUND_SUBMITTED": "OUTBOUND_PENDING_DELIVERY",
    "DELIVERY_CONFIRMED": "OUTBOUND_DELIVERED",
    "DELIVERY_FAILED": "OUTBOUND_DELIVERY_FAILED",
    "REPLY_OBSERVED": "REPLY_OBSERVED",
    "PROPOSAL_OBSERVED": "PROPOSAL_OBSERVED",
    "PAYMENT_OBSERVED": "PAYMENT_OBSERVED",
}
NEXT_EXPERIMENT = {
    "OFFER_ONLY": ("QUALIFY_ONE_TARGET", "TARGET_QUALIFIED"),
    "TARGET_QUALIFIED": ("OWNER_REVIEW_ONE_BOUNDED_OUTBOUND_EXPERIMENT", "OUTBOUND_SUBMITTED"),
    "OUTBOUND_PENDING_DELIVERY": ("RECONCILE_PROVIDER_DELIVERY", "DELIVERY_CONFIRMED_OR_FAILED"),
    "OUTBOUND_DELIVERY_FAILED": ("RESEARCH_NEW_ROUTE_BEFORE_ANY_NEW_CLAIM", "NEW_OWNER_REVIEW_REQUIRED"),
    "OUTBOUND_DELIVERED": ("WAIT_FOR_OR_INSPECT_GENUINE_REPLY", "REPLY_OBSERVED"),
    "REPLY_OBSERVED": ("PREPARE_OWNER_REVIEWED_PROPOSAL_EVIDENCE", "PROPOSAL_OBSERVED"),
    "PROPOSAL_OBSERVED": ("OBSERVE_PAYMENT_OR_EXPLICIT_DECLINE", "PAYMENT_OBSERVED_OR_DECLINE"),
    "PAYMENT_OBSERVED": ("RECONCILE_FULFILLMENT_AND_ACCOUNTING_OUTSIDE_THIS_TOOL", "OUTSIDE_SCOPE"),
    "HOLD": ("RESOLVE_PROVENANCE_HOLD", "CORRECTED_RETAINED_EVIDENCE"),
}
AUTHORITY = {
    "sendAuthorized": False,
    "followupAuthorized": False,
    "proposalAuthorized": False,
    "paymentAuthorized": False,
    "refundAuthorized": False,
    "providerMutationAuthorized": False,
    "fulfillmentAuthorized": False,
    "ledgerMutationAuthorized": False,
    "revenueRecognitionAuthorized": False,
}

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SUSPICIOUS_TEXT_RE = re.compile(
    r"(?i)(?:bearer\s+[A-Za-z0-9._~-]{12,}|(?:api[_ -]?key|secret|password)\s*[:=]|"
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
)


class EvidenceError(ValueError):
    pass


@dataclass(frozen=True)
class ArtifactBundle:
    packet_json: bytes
    summary_md: bytes
    events_csv: bytes
    receipt_txt: bytes


def _pairs_no_dupes(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise EvidenceError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def parse_json_bytes(data: bytes) -> dict[str, Any]:
    if not isinstance(data, (bytes, bytearray)):
        raise EvidenceError("input must be bytes")
    if len(data) > MAX_INPUT_BYTES:
        raise EvidenceError("input exceeds size bound")
    try:
        text = bytes(data).decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise EvidenceError("input is not valid UTF-8") from exc

    def reject_float(raw: str) -> Any:
        raise EvidenceError(f"floats are forbidden: {raw}")

    def reject_constant(raw: str) -> Any:
        raise EvidenceError(f"non-finite number is forbidden: {raw}")

    try:
        value = json.loads(
            text,
            object_pairs_hook=_pairs_no_dupes,
            parse_float=reject_float,
            parse_constant=reject_constant,
        )
    except EvidenceError:
        raise
    except json.JSONDecodeError as exc:
        raise EvidenceError("invalid JSON") from exc
    if not isinstance(value, dict):
        raise EvidenceError("top-level JSON must be an object")
    return value


def _expect_keys(obj: dict[str, Any], keys: set[str], where: str) -> None:
    got = set(obj)
    if got != keys:
        raise EvidenceError(
            f"{where} keys mismatch; missing={sorted(keys-got)}, extra={sorted(got-keys)}"
        )


def _expect_str(value: Any, where: str, *, max_len: int = MAX_TEXT) -> str:
    if not isinstance(value, str) or not value or len(value) > max_len:
        raise EvidenceError(f"{where} must be a non-empty bounded string")
    if "\x00" in value or "\r" in value:
        raise EvidenceError(f"{where} contains forbidden control characters")
    return value


def _expect_id(value: Any, where: str) -> str:
    text = _expect_str(value, where, max_len=128)
    if not ID_RE.fullmatch(text):
        raise EvidenceError(f"{where} is not a canonical opaque id")
    return text


def _expect_sha(value: Any, where: str) -> str:
    text = _expect_str(value, where, max_len=64)
    if not SHA_RE.fullmatch(text):
        raise EvidenceError(f"{where} must be lowercase sha256")
    return text


def _expect_commit(value: Any, where: str) -> str:
    text = _expect_str(value, where, max_len=40)
    if not COMMIT_RE.fullmatch(text):
        raise EvidenceError(f"{where} must be lowercase 40-hex commit id")
    return text


def _expect_utc(value: Any, where: str) -> str:
    import datetime as dt
    text = _expect_str(value, where, max_len=20)
    if not UTC_RE.fullmatch(text):
        raise EvidenceError(f"{where} must be whole-second UTC")
    try:
        dt.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise EvidenceError(f"{where} is not a real UTC timestamp") from exc
    return text


def _expect_int(value: Any, where: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EvidenceError(f"{where} must be an integer, not bool/float")
    if value < minimum or value > SAFE_INT_MAX:
        raise EvidenceError(f"{where} is outside safe integer bounds")
    return value


def _validate_safe_evidence_text(value: Any, where: str) -> str:
    text = _expect_str(value, where, max_len=MAX_TEXT)
    if SUSPICIOUS_TEXT_RE.search(text):
        raise EvidenceError(f"{where} appears to contain contact or secret-shaped material")
    return text


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def evidence_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_source(doc: dict[str, Any]) -> dict[str, Any]:
    _expect_keys(doc, {"schemaVersion", "opportunityId", "events"}, "root")
    if isinstance(doc["schemaVersion"], bool) or doc["schemaVersion"] != SCHEMA_VERSION:
        raise EvidenceError("unsupported schemaVersion")
    opportunity_id = _expect_id(doc["opportunityId"], "opportunityId")
    events_raw = doc["events"]
    if not isinstance(events_raw, list) or not (1 <= len(events_raw) <= MAX_EVENTS):
        raise EvidenceError("events must be a bounded non-empty array")

    normalized: list[dict[str, Any]] = []
    seen_event_ids: set[str] = set()
    for idx, raw in enumerate(events_raw):
        where = f"events[{idx}]"
        if not isinstance(raw, dict):
            raise EvidenceError(f"{where} must be an object")
        _expect_keys(raw, {
            "eventId", "opportunityId", "eventType", "occurredAt", "sourceRef",
            "evidenceText", "sourceSha256", "parentEventId", "facts",
        }, where)
        event_id = _expect_id(raw["eventId"], f"{where}.eventId")
        if event_id in seen_event_ids:
            raise EvidenceError(f"duplicate eventId: {event_id}")
        seen_event_ids.add(event_id)
        event_opp = _expect_id(raw["opportunityId"], f"{where}.opportunityId")
        event_type = _expect_str(raw["eventType"], f"{where}.eventType", max_len=32)
        if event_type not in EVENT_TYPES:
            raise EvidenceError(f"{where}.eventType is unsupported")
        occurred_at = _expect_utc(raw["occurredAt"], f"{where}.occurredAt")
        source_ref = _expect_str(raw["sourceRef"], f"{where}.sourceRef", max_len=MAX_REF)
        evidence_text = _validate_safe_evidence_text(raw["evidenceText"], f"{where}.evidenceText")
        source_sha = _expect_sha(raw["sourceSha256"], f"{where}.sourceSha256")
        if evidence_sha256(evidence_text) != source_sha:
            raise EvidenceError(f"{where}.sourceSha256 does not match evidenceText")
        parent = raw["parentEventId"]
        if parent is not None:
            parent = _expect_id(parent, f"{where}.parentEventId")
        facts = raw["facts"]
        if not isinstance(facts, dict):
            raise EvidenceError(f"{where}.facts must be an object")
        _expect_keys(facts, FACT_KEYS[event_type], f"{where}.facts")
        nf: dict[str, Any] = {}
        if event_type == "OFFER_SHIPPED":
            nf["offerId"] = _expect_id(facts["offerId"], f"{where}.facts.offerId")
            nf["artifactRef"] = _expect_str(facts["artifactRef"], f"{where}.facts.artifactRef", max_len=MAX_REF)
            nf["artifactCommit"] = _expect_commit(facts["artifactCommit"], f"{where}.facts.artifactCommit")
        elif event_type == "TARGET_QUALIFIED":
            nf["targetId"] = _expect_id(facts["targetId"], f"{where}.facts.targetId")
            nf["qualificationCode"] = _expect_id(facts["qualificationCode"], f"{where}.facts.qualificationCode")
        elif event_type == "OUTBOUND_SUBMITTED":
            nf["providerCode"] = _expect_id(facts["providerCode"], f"{where}.facts.providerCode")
            nf["submissionId"] = _expect_id(facts["submissionId"], f"{where}.facts.submissionId")
        elif event_type == "DELIVERY_CONFIRMED":
            nf["deliveryId"] = _expect_id(facts["deliveryId"], f"{where}.facts.deliveryId")
        elif event_type == "DELIVERY_FAILED":
            nf["failureId"] = _expect_id(facts["failureId"], f"{where}.facts.failureId")
            nf["reasonCode"] = _expect_id(facts["reasonCode"], f"{where}.facts.reasonCode")
        elif event_type == "REPLY_OBSERVED":
            nf["replyId"] = _expect_id(facts["replyId"], f"{where}.facts.replyId")
        elif event_type == "PROPOSAL_OBSERVED":
            nf["proposalId"] = _expect_id(facts["proposalId"], f"{where}.facts.proposalId")
        else:
            nf["paymentId"] = _expect_id(facts["paymentId"], f"{where}.facts.paymentId")
            nf["amountMinor"] = _expect_int(facts["amountMinor"], f"{where}.facts.amountMinor", minimum=1)
            currency = _expect_str(facts["currency"], f"{where}.facts.currency", max_len=3)
            if not CURRENCY_RE.fullmatch(currency):
                raise EvidenceError(f"{where}.facts.currency must be uppercase ISO-like code")
            nf["currency"] = currency
        normalized.append({
            "eventId": event_id, "opportunityId": event_opp, "eventType": event_type,
            "occurredAt": occurred_at, "sourceRef": source_ref, "evidenceText": evidence_text,
            "sourceSha256": source_sha, "parentEventId": parent, "facts": nf,
        })

    normalized.sort(key=lambda e: (e["occurredAt"], STAGE_ORDER[e["eventType"]], e["eventId"]))
    return {"schemaVersion": SCHEMA_VERSION, "opportunityId": opportunity_id, "events": normalized}


def retained_root(source: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(normalize_source(source))).hexdigest()


def _analyze(normalized: dict[str, Any]) -> tuple[str, list[str], list[dict[str, Any]]]:
    opp = normalized["opportunityId"]
    events = normalized["events"]
    findings: list[str] = []
    for e in events:
        if e["opportunityId"] != opp:
            findings.append("OPPORTUNITY_SCOPE_DRIFT")

    by_id = {e["eventId"]: e for e in events}
    by_type = {t: [] for t in EVENT_TYPES}
    evidence_owner: dict[tuple[str, str], str] = {}
    for e in events:
        by_type[e["eventType"]].append(e)
        key = (e["sourceRef"], e["sourceSha256"])
        prior = evidence_owner.get(key)
        if prior is not None and prior != e["eventId"]:
            findings.append("EVIDENCE_IDENTITY_REUSED_ACROSS_EVENTS")
        evidence_owner[key] = e["eventId"]

    if len(by_type["OFFER_SHIPPED"]) != 1:
        findings.append("EXACTLY_ONE_OFFER_REQUIRED")
    for t in EVENT_TYPES:
        if t != "OFFER_SHIPPED" and len(by_type[t]) > 1:
            findings.append(f"DUPLICATE_STAGE_{t}")
    if by_type["DELIVERY_CONFIRMED"] and by_type["DELIVERY_FAILED"]:
        findings.append("CONFLICTING_DELIVERY_TERMINALS")

    for e in events:
        et = e["eventType"]
        if et == "OFFER_SHIPPED":
            if e["parentEventId"] is not None:
                findings.append("OFFER_PARENT_MUST_BE_NULL")
            continue
        parent = by_id.get(e["parentEventId"]) if e["parentEventId"] else None
        if parent is None:
            findings.append(f"MISSING_PARENT_{et}")
            continue
        if parent["eventType"] != PARENT_TYPE[et]:
            findings.append(f"WRONG_PARENT_TYPE_{et}")
        if parent["opportunityId"] != e["opportunityId"]:
            findings.append(f"PARENT_SCOPE_DRIFT_{et}")
        if parent["occurredAt"] > e["occurredAt"]:
            findings.append(f"CHRONOLOGY_REGRESSION_{et}")

    if by_type["DELIVERY_FAILED"]:
        failed_at = by_type["DELIVERY_FAILED"][0]["occurredAt"]
        for t in ("REPLY_OBSERVED", "PROPOSAL_OBSERVED", "PAYMENT_OBSERVED"):
            if by_type[t] and by_type[t][0]["occurredAt"] >= failed_at:
                findings.append(f"POSITIVE_STAGE_AFTER_FAILED_DELIVERY_{t}")

    findings = sorted(set(findings))
    if findings:
        state = "HOLD"
    else:
        deepest = max(events, key=lambda e: (STAGE_ORDER[e["eventType"]], e["occurredAt"], e["eventId"]))
        state = STATE_FOR_TYPE[deepest["eventType"]]
    public_events = [{
        "eventId": e["eventId"], "eventType": e["eventType"], "occurredAt": e["occurredAt"],
        "sourceRef": e["sourceRef"], "sourceSha256": e["sourceSha256"],
        "parentEventId": e["parentEventId"],
    } for e in events]
    return state, findings, public_events


def compile_packet(source: dict[str, Any], expected_retained_root: str) -> dict[str, Any]:
    expected = _expect_sha(expected_retained_root, "expected_retained_root")
    normalized = normalize_source(source)
    actual = hashlib.sha256(_canonical(normalized)).hexdigest()
    state, findings, public_events = _analyze(normalized)
    if actual != expected:
        state = "HOLD"
        findings = sorted(set(findings + ["RETAINED_ROOT_MISMATCH"]))
    next_action, expected_next = NEXT_EXPERIMENT[state]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "opportunityId": normalized["opportunityId"],
        "retainedRoot": actual,
        "expectedRetainedRoot": expected,
        "observedState": state,
        "findings": findings,
        "nextExperiment": {
            "code": next_action,
            "expectedEvidence": expected_next,
            "ownerReviewRequired": True,
        },
        "events": public_events,
        "authority": dict(AUTHORITY),
        "truthBoundary": (
            "Observed retained evidence only. Provider submission is not delivery; "
            "payment evidence is not revenue recognition; digests prove byte identity, "
            "not external authenticity or completeness."
        ),
    }


def _formula_safe(value: str) -> str:
    return "'" + value if value and value[0] in ("=", "+", "-", "@", "\t", "\r") else value


def render_bundle(source: dict[str, Any], expected_retained_root: str) -> ArtifactBundle:
    packet = compile_packet(source, expected_retained_root)
    packet_json = _canonical(packet)
    md = [
        "# Commerce Conversion Loop — owner review", "",
        f"- Opportunity: {packet['opportunityId']}",
        f"- Observed state: **{packet['observedState']}**",
        f"- Retained root: {packet['retainedRoot']}",
        f"- Next experiment: {packet['nextExperiment']['code']}",
        f"- Expected next evidence: {packet['nextExperiment']['expectedEvidence']}",
        "- Owner review required: **true**", "", "## Findings",
    ]
    md.extend([f"- {f}" for f in packet["findings"]] or ["- none"])
    md += [
        "", "## Authority ceiling",
        "No send, follow-up, proposal, payment/refund, provider mutation, fulfillment, ledger mutation, or revenue-recognition authority is granted by this artifact.",
        "", "## Truth boundary", packet["truthBoundary"], "",
    ]
    summary_md = "\n".join(md).encode("utf-8")

    sio = io.StringIO(newline="")
    writer = csv.writer(sio, lineterminator="\n")
    writer.writerow(["event_id", "event_type", "occurred_at", "source_ref", "source_sha256", "parent_event_id"])
    for e in packet["events"]:
        writer.writerow([_formula_safe(str(e[k] or "")) for k in (
            "eventId", "eventType", "occurredAt", "sourceRef", "sourceSha256", "parentEventId"
        )])
    events_csv = sio.getvalue().encode("utf-8")
    hashes = {
        "events.csv": hashlib.sha256(events_csv).hexdigest(),
        "packet.json": hashlib.sha256(packet_json).hexdigest(),
        "summary.md": hashlib.sha256(summary_md).hexdigest(),
    }
    receipt_payload = _canonical({
        "schemaVersion": SCHEMA_VERSION,
        "artifactSha256": hashes,
        "retainedRoot": packet["retainedRoot"],
    })
    receipt = hashlib.sha256(receipt_payload).hexdigest()
    receipt_txt = (f"receipt_sha256={receipt}\n" + receipt_payload.decode("utf-8")).encode("utf-8")
    return ArtifactBundle(packet_json, summary_md, events_csv, receipt_txt)


def verify_bundle(source: dict[str, Any], expected_retained_root: str, *, packet_json: bytes,
                  summary_md: bytes, events_csv: bytes, receipt_txt: bytes) -> bool:
    expected = render_bundle(source, expected_retained_root)
    return (
        packet_json == expected.packet_json and summary_md == expected.summary_md
        and events_csv == expected.events_csv and receipt_txt == expected.receipt_txt
    )


def read_regular_file(path: str | os.PathLike[str], *, max_bytes: int = MAX_INPUT_BYTES) -> bytes:
    p = Path(path)
    try:
        st = os.lstat(p)
    except OSError as exc:
        raise EvidenceError(f"cannot lstat input: {p}") from exc
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        raise EvidenceError("input must be a regular non-symlink file")
    if st.st_size > max_bytes:
        raise EvidenceError("input exceeds size bound")
    try:
        fd = os.open(p, os.O_RDONLY)
    except OSError as exc:
        raise EvidenceError(f"cannot open input: {p}") from exc
    try:
        fst = os.fstat(fd)
        if not stat.S_ISREG(fst.st_mode) or (fst.st_dev, fst.st_ino) != (st.st_dev, st.st_ino):
            raise EvidenceError("input changed between lstat and open")
        data = bytearray()
        while True:
            chunk = os.read(fd, min(65536, max_bytes + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > max_bytes:
                raise EvidenceError("input exceeds size bound")
        fst2 = os.fstat(fd)
        if (fst2.st_dev, fst2.st_ino, fst2.st_size) != (fst.st_dev, fst.st_ino, fst.st_size):
            raise EvidenceError("input changed during read")
        return bytes(data)
    finally:
        os.close(fd)


def write_bundle_exclusive(output_dir: str | os.PathLike[str], bundle: ArtifactBundle) -> None:
    out = Path(output_dir)
    try:
        out.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise EvidenceError("output directory already exists") from exc
    if out.is_symlink():
        raise EvidenceError("output directory may not be a symlink")
    items = {
        "packet.json": bundle.packet_json,
        "summary.md": bundle.summary_md,
        "events.csv": bundle.events_csv,
        "receipt.txt": bundle.receipt_txt,
    }
    for name, data in items.items():
        fd = os.open(out / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            offset = 0
            while offset < len(data):
                offset += os.write(fd, data[offset:])
            os.fsync(fd)
        finally:
            os.close(fd)
