"""SustainProof: deterministic disconnected-first sustainment handoff reconciliation.

This module is deliberately local/offline. It reconciles evidence-bound maintenance
and supply state without contacting providers, dispatching work, ordering parts, or
performing any external action. Output is human-review evidence only.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from typing import Any, Iterable

VERSION = "xtech.search10.sustainproof.handoff/v1"
REPORT_VERSION = "xtech.search10.sustainproof.report/v1"
SAFE_INT = (1 << 53) - 1
MAX_EVENTS = 2048
MAX_TEXT = 128
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
UTC_FMT = "%Y-%m-%dT%H:%M:%SZ"
KINDS = {"WORK_ORDER", "PARTS", "INSPECTION"}
WORK_STATES = {"OPEN", "WAITING_PART", "READY_FOR_MAINTENANCE", "CLOSED"}
PART_STATES = {"AVAILABLE", "RESERVED", "OUT_OF_STOCK"}
INSPECTION_STATES = {"PASS", "REINSPECT", "HOLD"}


class ContractError(ValueError):
    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail
        super().__init__(code if not detail else f"{code}:{detail}")


def _pairs_no_duplicates(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ContractError("JSON_DUPLICATE_KEY", key)
        out[key] = value
    return out


def parse_json_strict(raw: str) -> Any:
    def reject_constant(value: str) -> None:
        raise ContractError("JSON_NONFINITE", value)

    try:
        return json.loads(raw, object_pairs_hook=_pairs_no_duplicates, parse_constant=reject_constant)
    except ContractError:
        raise
    except json.JSONDecodeError as exc:
        raise ContractError("JSON_INVALID", str(exc)) from exc


def canonical_json(value: Any) -> str:
    def check(node: Any, path: str = "$") -> Any:
        if node is None or isinstance(node, (str, bool)):
            return node
        if isinstance(node, int) and not isinstance(node, bool):
            if abs(node) > SAFE_INT:
                raise ContractError("UNSAFE_INTEGER", path)
            return node
        if isinstance(node, list):
            if len(node) > MAX_EVENTS:
                raise ContractError("ARRAY_TOO_LARGE", path)
            return [check(item, f"{path}[]") for item in node]
        if type(node) is dict:
            return {str(k): check(v, f"{path}.{k}") for k, v in node.items()}
        raise ContractError("NON_JSON_VALUE", f"{path}:{type(node).__name__}")

    return json.dumps(check(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _exact(value: Any, keys: set[str], path: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ContractError("EXPECTED_OBJECT", path)
    got = set(value)
    if got != keys:
        raise ContractError("OBJECT_SHAPE", f"{path}:missing={sorted(keys-got)},extra={sorted(got-keys)}")
    return value


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or len(value) > MAX_TEXT or ID_RE.fullmatch(value) is None:
        raise ContractError("INVALID_TEXT", path)
    return value


def _digest(value: Any, path: str) -> str:
    if not isinstance(value, str) or SHA_RE.fullmatch(value) is None:
        raise ContractError("INVALID_SHA256", path)
    return value


def _safe_int(value: Any, path: str, *, minimum: int = 0, maximum: int = SAFE_INT) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum or value > maximum:
        raise ContractError("INVALID_INTEGER", path)
    return value


def _utc(value: Any, path: str) -> datetime:
    if not isinstance(value, str):
        raise ContractError("INVALID_UTC", path)
    try:
        parsed = datetime.strptime(value, UTC_FMT).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ContractError("INVALID_UTC", path) from exc
    if parsed.strftime(UTC_FMT) != value:
        raise ContractError("NONCANONICAL_UTC", path)
    return parsed


def _utc_string(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).strftime(UTC_FMT)


def _payload_for_digest(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "streamRef": event["streamRef"],
        "subjectRef": event["subjectRef"],
        "generation": event["generation"],
        "previousEventSha256": event["previousEventSha256"],
        "kind": event["kind"],
        "state": event["state"],
        "quantity": event["quantity"],
        "partRef": event["partRef"],
        "observedAt": event["observedAt"],
        "evidenceSha256": event["evidenceSha256"],
    }


def event_sha256(event: dict[str, Any]) -> str:
    """Digest one validated event, excluding its caller label/eventId."""
    return sha256_json(_payload_for_digest(event))


def _validate_event(raw: Any, path: str) -> dict[str, Any]:
    event = _exact(
        raw,
        {
            "eventId", "streamRef", "subjectRef", "generation", "previousEventSha256",
            "kind", "state", "quantity", "partRef", "observedAt", "evidenceSha256",
        },
        path,
    )
    _text(event["eventId"], f"{path}.eventId")
    _text(event["streamRef"], f"{path}.streamRef")
    _text(event["subjectRef"], f"{path}.subjectRef")
    _safe_int(event["generation"], f"{path}.generation", minimum=1, maximum=1_000_000)
    if event["previousEventSha256"] is not None:
        _digest(event["previousEventSha256"], f"{path}.previousEventSha256")
    kind = event["kind"]
    if kind not in KINDS:
        raise ContractError("INVALID_KIND", path)
    state = event["state"]
    allowed = WORK_STATES if kind == "WORK_ORDER" else PART_STATES if kind == "PARTS" else INSPECTION_STATES
    if state not in allowed:
        raise ContractError("INVALID_STATE", f"{path}.state")
    _safe_int(event["quantity"], f"{path}.quantity", maximum=1_000_000)
    if event["partRef"] is not None:
        _text(event["partRef"], f"{path}.partRef")
    if kind == "WORK_ORDER":
        if state == "WAITING_PART" and event["partRef"] is None:
            raise ContractError("WAITING_PART_REQUIRES_PART_REF", path)
        if state != "WAITING_PART" and event["partRef"] is not None:
            raise ContractError("PART_REF_ONLY_WHEN_WAITING_PART", path)
    elif event["partRef"] is not None:
        raise ContractError("PART_REF_ONLY_ON_WORK_ORDER", path)
    if kind != "PARTS" and event["quantity"] != 0:
        raise ContractError("QUANTITY_ONLY_ON_PARTS", path)
    if kind == "PARTS":
        if state in {"AVAILABLE", "RESERVED"} and event["quantity"] < 1:
            raise ContractError("PART_QUANTITY_STATE_MISMATCH", path)
        if state == "OUT_OF_STOCK" and event["quantity"] != 0:
            raise ContractError("PART_QUANTITY_STATE_MISMATCH", path)
    _utc(event["observedAt"], f"{path}.observedAt")
    _digest(event["evidenceSha256"], f"{path}.evidenceSha256")
    return event


@dataclass(frozen=True)
class ChainState:
    stream_ref: str
    subject_ref: str
    kind: str
    latest: dict[str, Any]
    latest_sha256: str


def _normalize_events(raw_events: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_events, list) or not (1 <= len(raw_events) <= MAX_EVENTS):
        raise ContractError("EVENTS_INVALID")
    by_id: dict[str, dict[str, Any]] = {}
    for idx, raw in enumerate(raw_events):
        event = _validate_event(raw, f"events[{idx}]")
        existing = by_id.get(event["eventId"])
        if existing is not None:
            if canonical_json(existing) != canonical_json(event):
                raise ContractError("EVENT_ID_DRIFT", event["eventId"])
            continue
        by_id[event["eventId"]] = event
    return sorted(
        by_id.values(),
        key=lambda event: (event["streamRef"], event["subjectRef"], event["generation"], event["eventId"]),
    )


def _build_chains(events: list[dict[str, Any]], as_of: datetime, max_age: timedelta) -> tuple[list[ChainState], list[str]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for event in events:
        grouped.setdefault((event["streamRef"], event["subjectRef"]), []).append(event)

    chains: list[ChainState] = []
    reasons: list[str] = []
    for (stream_ref, subject_ref), rows in sorted(grouped.items()):
        kinds = {row["kind"] for row in rows}
        if len(kinds) != 1:
            reasons.append(f"KIND_FORK:{stream_ref}:{subject_ref}")
            continue
        by_generation: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            by_generation.setdefault(row["generation"], []).append(row)
        if min(by_generation) != 1 or set(by_generation) != set(range(1, max(by_generation) + 1)):
            reasons.append(f"GENERATION_GAP:{stream_ref}:{subject_ref}")
            continue
        prior_sha: str | None = None
        prior_observed: datetime | None = None
        latest: dict[str, Any] | None = None
        latest_sha = ""
        valid = True
        for generation in range(1, max(by_generation) + 1):
            candidates = by_generation[generation]
            semantic = {event_sha256(candidate) for candidate in candidates}
            if len(semantic) != 1:
                reasons.append(f"GENERATION_FORK:{stream_ref}:{subject_ref}:{generation}")
                valid = False
                break
            row = sorted(candidates, key=lambda item: item["eventId"])[0]
            expected_prev = None if generation == 1 else prior_sha
            if row["previousEventSha256"] != expected_prev:
                reasons.append(f"CHAIN_LINK_INVALID:{stream_ref}:{subject_ref}:{generation}")
                valid = False
                break
            observed = _utc(row["observedAt"], "observedAt")
            if observed > as_of:
                reasons.append(f"FUTURE_EVENT:{stream_ref}:{subject_ref}:{generation}")
                valid = False
                break
            if prior_observed is not None and observed < prior_observed:
                reasons.append(f"CHRONOLOGY_REWIND:{stream_ref}:{subject_ref}:{generation}")
                valid = False
                break
            prior_observed = observed
            prior_sha = event_sha256(row)
            latest = row
            latest_sha = prior_sha
        if not valid or latest is None:
            continue
        latest_at = _utc(latest["observedAt"], "observedAt")
        if as_of - latest_at > max_age:
            reasons.append(f"STALE_CHAIN:{stream_ref}:{subject_ref}")
            continue
        chains.append(ChainState(stream_ref, subject_ref, latest["kind"], latest, latest_sha))
    return chains, sorted(set(reasons))


def compile_handoff(document: Any, *, as_of: datetime | None = None) -> dict[str, Any]:
    doc = _exact(document, {"version", "maxAgeHours", "events"}, "input")
    if doc["version"] != VERSION:
        raise ContractError("VERSION_INVALID")
    max_age_hours = _safe_int(doc["maxAgeHours"], "maxAgeHours", minimum=1, maximum=24 * 30)
    current = as_of or datetime.now(timezone.utc).replace(microsecond=0)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ContractError("AS_OF_MUST_BE_TIMEZONE_AWARE")
    current = current.astimezone(timezone.utc).replace(microsecond=0)
    events = _normalize_events(doc["events"])
    chains, reasons = _build_chains(events, current, timedelta(hours=max_age_hours))

    work = {(c.stream_ref, c.subject_ref): c for c in chains if c.kind == "WORK_ORDER"}
    work_subject_counts: dict[str, int] = {}
    for chain in work.values():
        work_subject_counts[chain.subject_ref] = work_subject_counts.get(chain.subject_ref, 0) + 1
    reasons.extend(
        f"WORK_ORDER_SUBJECT_AMBIGUOUS:{subject_ref}"
        for subject_ref, count in sorted(work_subject_counts.items()) if count > 1
    )
    reasons = sorted(set(reasons))
    parts_by_ref: dict[str, list[ChainState]] = {}
    inspections_by_work: dict[str, list[ChainState]] = {}
    for chain in chains:
        if chain.kind == "PARTS":
            parts_by_ref.setdefault(chain.subject_ref, []).append(chain)
        elif chain.kind == "INSPECTION":
            inspections_by_work.setdefault(chain.subject_ref, []).append(chain)

    handoffs: list[dict[str, Any]] = []
    for key, chain in sorted(work.items()):
        event = chain.latest
        item_reasons: list[str] = []
        if event["state"] == "CLOSED":
            state = "CLOSED_NO_ACTION"
        else:
            state = "READY_FOR_HUMAN_HANDOFF"
            inspect_candidates = inspections_by_work.get(event["subjectRef"], [])
            if len(inspect_candidates) > 1:
                item_reasons.append("INSPECTION_AUTHORITY_AMBIGUOUS")
            elif len(inspect_candidates) == 1 and inspect_candidates[0].latest["state"] in {"REINSPECT", "HOLD"}:
                item_reasons.append(f"INSPECTION_{inspect_candidates[0].latest['state']}")
            if event["state"] == "WAITING_PART":
                part_candidates = parts_by_ref.get(event["partRef"], [])
                if not part_candidates:
                    item_reasons.append("PART_STATE_MISSING")
                elif len(part_candidates) > 1:
                    item_reasons.append("PART_AUTHORITY_AMBIGUOUS")
                else:
                    part = part_candidates[0]
                    if part.latest["state"] != "AVAILABLE" or part.latest["quantity"] < 1:
                        item_reasons.append("PART_NOT_AVAILABLE")
            if item_reasons:
                state = "HOLD_FOR_HUMAN_REVIEW"
        handoffs.append(
            {
                "streamRef": chain.stream_ref,
                "workOrderRef": chain.subject_ref,
                "sourceGeneration": event["generation"],
                "sourceEventSha256": chain.latest_sha256,
                "workState": event["state"],
                "state": state,
                "reasons": sorted(item_reasons),
                "partRef": event["partRef"],
            }
        )

    overall = "HOLD_FOR_HUMAN_REVIEW" if reasons or any(h["state"] == "HOLD_FOR_HUMAN_REVIEW" for h in handoffs) else "READY_FOR_HUMAN_HANDOFF"
    if not handoffs:
        overall = "HOLD_FOR_HUMAN_REVIEW"
        reasons = sorted(set(reasons + ["NO_WORK_ORDERS"]))
    core = {
        "version": REPORT_VERSION,
        "evaluatedAt": _utc_string(current),
        "mode": "HISTORICAL_INTEGRITY_ONLY" if as_of is not None else "CURRENT_PROCESS_UTC",
        "inputSha256": sha256_json({"version": doc["version"], "maxAgeHours": doc["maxAgeHours"], "events": events}),
        "overallState": overall,
        "chainReasons": reasons,
        "handoffs": handoffs,
        "authority": {
            "dispatchAuthorized": False,
            "purchaseAuthorized": False,
            "maintenanceAuthorized": False,
            "providerWriteAuthorized": False,
            "submissionAuthorized": False,
        },
    }
    return {**core, "receiptSha256": sha256_json(core)}
