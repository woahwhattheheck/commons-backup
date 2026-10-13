from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from . import _legacy_engine as _legacy

GateInputError = _legacy.GateInputError
_parse_utc = _legacy._parse_utc

CURRENT_TEMPORAL_AUTHORITY = "PROCESS_UTC_CURRENT"
HISTORICAL_TEMPORAL_AUTHORITY = "HISTORICAL_INTEGRITY_ONLY"
EVIDENCE_AUTHORITY = "EVIDENCE_ONLY_NO_OPERATIONAL_RELEASE"

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_SNAPSHOT_AGE_SECONDS = 30 * 24 * 3600


def _canonical_bytes(value: Any) -> bytes:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise GateInputError("value is not canonical JSON") from exc
    if len(raw) > 1_048_576:
        raise GateInputError("canonical JSON exceeds the 1 MiB gate limit")
    return raw


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _legacy_evaluate(policy: Any, snapshot: Any, *, evaluated_at: str) -> dict[str, Any]:
    """Call the frozen v1 evaluator through its deterministic replay seam.

    Current main's v1 engine exposed ``evaluate(..., evaluated_at=...)``. A hardened donor may
    already expose ``_evaluate_historical_at`` instead. Supporting both shapes lets this public
    authority wrapper preserve the exact v1 evidence semantics while removing caller clock
    custody from the supported API.
    """
    historical = getattr(_legacy, "_evaluate_historical_at", None)
    if callable(historical):
        return historical(policy, snapshot, evaluated_at=evaluated_at)
    return _legacy.evaluate(policy, snapshot, evaluated_at=evaluated_at)


def _receipt_rehash(result: dict[str, Any], *, temporal_authority: str) -> dict[str, Any]:
    receipt = result["receipt"]
    receipt["authority"] = EVIDENCE_AUTHORITY
    receipt["temporal_authority"] = temporal_authority
    core = dict(receipt)
    core.pop("receipt_sha256", None)
    receipt["receipt_sha256"] = _sha256(core)
    return result


def _make_api(now_func, utc, datetime_type):
    def parse_utc(value: Any, *, name: str) -> datetime:
        if type(value) is not str or not value or len(value.encode("utf-8")) > 64 or not value.endswith("Z"):
            raise GateInputError(f"{name} must be bounded UTC with a trailing Z")
        try:
            parsed = datetime_type.fromisoformat(value[:-1] + "+00:00")
        except ValueError as exc:
            raise GateInputError(f"{name} is not an ISO-8601 timestamp") from exc
        if parsed.tzinfo is None or parsed.utcoffset() != utc.utcoffset(parsed):
            raise GateInputError(f"{name} must be UTC")
        return parsed

    def format_utc(value: datetime) -> str:
        return value.astimezone(utc).isoformat(timespec="microseconds").replace("+00:00", "Z")

    def process_now() -> datetime:
        try:
            value = now_func(utc)
        except Exception as exc:  # pragma: no cover - platform clock failure
            raise GateInputError("process UTC clock unavailable") from exc
        if type(value) is not datetime_type or value.tzinfo is None or value.utcoffset() != utc.utcoffset(value):
            raise GateInputError("process UTC clock returned a non-UTC datetime")
        return value

    def temporal_contract(policy: Any, snapshot: Any, evaluated_at: str) -> tuple[datetime, int]:
        """Re-validate all time-bearing input with closure-captured datetime primitives."""
        if type(policy) is not dict or set(policy) != {"schema", "max_snapshot_age_seconds", "sources"}:
            raise GateInputError("policy has wrong fields")
        max_age = policy["max_snapshot_age_seconds"]
        if type(max_age) is not int or not 0 <= max_age <= _MAX_SNAPSHOT_AGE_SECONDS:
            raise GateInputError("policy.max_snapshot_age_seconds is out of bounds")
        if type(snapshot) is not dict or set(snapshot) != {"schema", "capture_complete", "captured_at", "events"}:
            raise GateInputError("snapshot has wrong fields")
        evaluated = parse_utc(evaluated_at, name="evaluated_at")
        captured = parse_utc(snapshot["captured_at"], name="snapshot.captured_at")
        if captured > evaluated:
            raise GateInputError("snapshot captured_at cannot be after trusted evaluation time")
        events = snapshot["events"]
        if type(events) is not list:
            raise GateInputError("snapshot.events must be an array")
        for raw in events:
            if type(raw) is not dict:
                raise GateInputError("event must be an object")
            effective = parse_utc(raw.get("effective_at"), name="event.effective_at")
            observed = parse_utc(raw.get("observed_at"), name="event.observed_at")
            if effective > observed:
                raise GateInputError("event effective_at cannot be after observed_at")
            if observed > captured:
                raise GateInputError("event observed_at cannot be after snapshot captured_at")
            if observed > evaluated:
                raise GateInputError("event observed_at cannot be after trusted evaluation time")
        return evaluated - captured, max_age

    def historical_at(policy: Any, snapshot: Any, *, evaluated_at: str) -> dict[str, Any]:
        age, max_age = temporal_contract(policy, snapshot, evaluated_at)
        result = copy.deepcopy(_legacy_evaluate(policy, snapshot, evaluated_at=evaluated_at))
        receipt = result["receipt"]
        # The legacy engine displays whole seconds. Authority uses the exact timedelta instead.
        receipt["snapshot_age_seconds"] = int(age.total_seconds())
        holds = set(receipt.get("holds", []))
        if age > timedelta(seconds=max_age):
            holds.add("SNAPSHOT_STALE")
        else:
            holds.discard("SNAPSHOT_STALE")
        receipt["holds"] = sorted(holds)
        receipt["decision"] = "PASS" if not holds else "HOLD"
        return _receipt_rehash(result, temporal_authority=HISTORICAL_TEMPORAL_AUTHORITY)

    def verify_historical(result: Any, *, policy: Any, snapshot: Any) -> bool:
        """Verify deterministic replay only; never establishes current freshness."""
        try:
            if type(result) is not dict or set(result) != {"receipt", "report", "exceptions"}:
                return False
            receipt = result.get("receipt")
            if type(receipt) is not dict:
                return False
            if receipt.get("authority") != EVIDENCE_AUTHORITY:
                return False
            if receipt.get("temporal_authority") != HISTORICAL_TEMPORAL_AUTHORITY:
                return False
            supplied = receipt.get("receipt_sha256")
            core = dict(receipt)
            core.pop("receipt_sha256", None)
            if type(supplied) is not str or _HEX64_RE.fullmatch(supplied) is None or supplied != _sha256(core):
                return False
            expected = historical_at(policy, snapshot, evaluated_at=receipt["evaluated_at"])
            return _canonical_bytes(expected) == _canonical_bytes(result)
        except (GateInputError, KeyError, TypeError, ValueError):
            return False

    def promote_current(result: dict[str, Any]) -> dict[str, Any]:
        if result["receipt"].get("temporal_authority") != HISTORICAL_TEMPORAL_AUTHORITY:
            raise GateInputError("only historical engine output may be promoted")
        return _receipt_rehash(result, temporal_authority=CURRENT_TEMPORAL_AUTHORITY)

    def evaluate(policy: Any, snapshot: Any) -> dict[str, Any]:
        """Evaluate against process-owned current UTC; callers cannot select the clock."""
        now = process_now()
        return promote_current(historical_at(policy, snapshot, evaluated_at=format_utc(now)))

    def verify(result: Any, *, policy: Any, snapshot: Any) -> bool:
        """Verify integrity and freshness against verifier-owned process UTC."""
        try:
            now = process_now()
            if type(result) is not dict or set(result) != {"receipt", "report", "exceptions"}:
                return False
            receipt = result.get("receipt")
            if type(receipt) is not dict:
                return False
            if receipt.get("authority") != EVIDENCE_AUTHORITY:
                return False
            if receipt.get("temporal_authority") != CURRENT_TEMPORAL_AUTHORITY:
                return False
            recorded_time = parse_utc(receipt.get("evaluated_at"), name="result.receipt.evaluated_at")
            if recorded_time > now:
                return False

            # Prove the supplied result was coherent at its recorded instant.
            recorded = promote_current(
                historical_at(policy, snapshot, evaluated_at=receipt["evaluated_at"])
            )
            if _canonical_bytes(recorded) != _canonical_bytes(result):
                return False

            # Re-evaluate with a fresh verifier-owned clock. An old PASS may no longer be current.
            current = promote_current(historical_at(policy, snapshot, evaluated_at=format_utc(now)))
            if _canonical_bytes(current["report"]) != _canonical_bytes(result["report"]):
                return False
            if _canonical_bytes(current["exceptions"]) != _canonical_bytes(result["exceptions"]):
                return False
            invariant = set(current["receipt"]) - {"evaluated_at", "snapshot_age_seconds", "receipt_sha256"}
            return all(receipt.get(key) == current["receipt"].get(key) for key in invariant)
        except (GateInputError, KeyError, TypeError, ValueError):
            return False

    return historical_at, verify_historical, evaluate, verify


_evaluate_historical_at, _verify_historical, evaluate, verify = _make_api(
    datetime.now, timezone.utc, datetime
)
del _make_api
