#!/usr/bin/env python3
"""Synthetic/read-only 48-hour hold-rescue queue for Big Onion.

The module consumes only a frozen synthetic fixture and returns operator
recommendations. It never sends, retries, collects, charges, mutates provider
state, or writes customer/payment systems.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

DEMAND_ID = "big-onion-hold-rescue-01"
FIXTURE_SCHEMA = "synthetic-hold-rescue-fixture-v1"
FIXTURE_VERSION = "big-onion-hold-rescue-v1"
MANIFEST_PREFIX = "BIG-ONION-HOLD-RESCUE-SYNTHETIC-MANIFEST-V1\n"
ELIGIBLE_STATES = frozenset({"UNPAID", "FAILED_DEPOSIT"})
CUTOFF_HOURS = 48
FORBIDDEN_KEYS = frozenset({
    "email", "phone", "customer_name", "name", "address", "card",
    "card_number", "account_number", "bank_account", "routing_number",
    "payment_token", "payment_method", "password", "secret", "api_key",
})
FORBIDDEN_KEY_SHAPES = frozenset(
    "".join(char for char in key.casefold() if char.isalnum())
    for key in FORBIDDEN_KEYS
)


class IntegrityError(ValueError):
    """The frozen synthetic evidence does not match its signed manifest."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(value: bytes | str | Any) -> str:
    if isinstance(value, bytes):
        payload = value
    elif isinstance(value, str):
        payload = value.encode("utf-8")
    else:
        payload = canonical_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _manifest_envelope(manifest: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "demand_id", "fixture_schema", "fixture_version", "dataset_sha256",
        "event_count", "as_of", "cutoff_hours", "eligible_states",
        "expected_eligible_ids",
    )
    return {key: manifest[key] for key in keys}


def verify_manifest_signature(manifest: Mapping[str, Any]) -> None:
    if manifest.get("signature_alg") != "sha256-content-envelope-v1":
        raise IntegrityError("manifest signature algorithm mismatch")
    expected = sha256_hex(MANIFEST_PREFIX + json.dumps(
        _manifest_envelope(manifest), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ))
    if manifest.get("signature") != expected:
        raise IntegrityError("manifest signature mismatch")


def _parse_timestamp(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(dt.timezone.utc)


def _key_shape(value: Any) -> str:
    return "".join(char for char in str(value).casefold() if char.isalnum())


def _sensitive_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            if _key_shape(key) in FORBIDDEN_KEY_SHAPES:
                found.add(str(key))
            found.update(_sensitive_keys(child))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for child in value:
            found.update(_sensitive_keys(child))
    return found


def _event_decision(event: Any, as_of: dt.datetime, cutoff_hours: int) -> tuple[bool, str, int | None]:
    if not isinstance(event, Mapping):
        return False, "MALFORMED_ROW", None
    if _sensitive_keys(event):
        raise IntegrityError("synthetic fixture contains forbidden sensitive-shaped fields")
    event_id = event.get("event_id")
    state = event.get("queue_state")
    resolved = event.get("resolved")
    source_ref = event.get("source_ref")
    if (
        event.get("synthetic") is not True
        or not isinstance(event_id, str) or not event_id
        or not isinstance(state, str)
        or not isinstance(resolved, bool)
        or not isinstance(source_ref, str) or not source_ref.startswith("SYNTHETIC-")
    ):
        return False, "MALFORMED_ROW", None
    observed = _parse_timestamp(event.get("first_observed_at"))
    if observed is None or observed > as_of:
        return False, "MALFORMED_ROW", None
    age_seconds = (as_of - observed).total_seconds()
    age_hours = int(age_seconds // 3600)
    if resolved:
        return False, "ALREADY_RESOLVED", age_hours
    if state not in ELIGIBLE_STATES:
        return False, "INELIGIBLE_STATE", age_hours
    if age_seconds < cutoff_hours * 3600:
        return False, "TOO_YOUNG", age_hours
    return True, "ELIGIBLE", age_hours


@dataclass(frozen=True)
class RescueResult:
    recommendations: tuple[dict[str, Any], ...]
    diagnostics: tuple[dict[str, Any], ...]
    sends: int = 0
    actions: int = 0
    provider_writes: int = 0
    state_mutations: int = 0
    events_added: int = 0

    def digest(self) -> str:
        return sha256_hex({
            "recommendations": self.recommendations,
            "diagnostics": self.diagnostics,
            "sends": self.sends,
            "actions": self.actions,
            "provider_writes": self.provider_writes,
            "state_mutations": self.state_mutations,
            "events_added": self.events_added,
        })


class BigOnionHoldRescue:
    """Pure read-only evaluator over an immutable authoritative snapshot copy."""

    def __init__(self, authoritative_state: Mapping[str, Any] | None = None):
        self.authoritative_state = copy.deepcopy(dict(authoritative_state or {}))
        self._authoritative_sha256 = sha256_hex(self.authoritative_state)

    @property
    def authoritative_fingerprint(self) -> str:
        current = sha256_hex(self.authoritative_state)
        if current != self._authoritative_sha256:
            raise IntegrityError("authoritative snapshot mutated")
        return current

    def evaluate(self, events: Sequence[Any], *, as_of: str, cutoff_hours: int = CUTOFF_HOURS) -> RescueResult:
        when = _parse_timestamp(as_of)
        if when is None:
            raise IntegrityError("as_of must be an offset-aware ISO timestamp")
        if isinstance(cutoff_hours, bool) or not isinstance(cutoff_hours, int) or cutoff_hours != CUTOFF_HOURS:
            raise IntegrityError("cutoff_hours must remain exactly 48")
        self.authoritative_fingerprint
        recommendations: list[dict[str, Any]] = []
        diagnostics: list[dict[str, Any]] = []
        for source_index, event in enumerate(events):
            eligible, reason, age_hours = _event_decision(event, when, cutoff_hours)
            event_id = event.get("event_id") if isinstance(event, Mapping) else None
            diagnostics.append({
                "source_index": source_index,
                "event_id": event_id if isinstance(event_id, str) else None,
                "eligible": eligible,
                "reason": reason,
                "age_hours": age_hours,
            })
            if not eligible:
                continue
            recommendations.append({
                "event_id": event_id,
                "queue_state": event["queue_state"],
                "age_hours": age_hours,
                "source_index": source_index,
                "source_ref": event["source_ref"],
                "recommended_action": "HUMAN_REVIEW_ONLY",
            })
        self.authoritative_fingerprint
        return RescueResult(tuple(recommendations), tuple(diagnostics))


def load_fixture(fixture_path: str | Path | None = None, manifest_path: str | Path | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    base = Path(__file__).resolve().parent / "fixtures"
    fixture = Path(fixture_path) if fixture_path else base / "six_events.json"
    manifest_file = Path(manifest_path) if manifest_path else base / "manifest.json"
    fixture_bytes = fixture.read_bytes()
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    verify_manifest_signature(manifest)
    if sha256_hex(fixture_bytes) != manifest.get("dataset_sha256"):
        raise IntegrityError("fixture hash mismatch")
    payload = json.loads(fixture_bytes)
    if payload.get("schema") != FIXTURE_SCHEMA or payload.get("fixture_version") != FIXTURE_VERSION:
        raise IntegrityError("fixture schema/version mismatch")
    if payload.get("as_of") != manifest.get("as_of"):
        raise IntegrityError("fixture as_of mismatch")
    events = payload.get("events")
    if not isinstance(events, list) or len(events) != manifest.get("event_count"):
        raise IntegrityError("fixture event count mismatch")
    if any(isinstance(event, Mapping) and _sensitive_keys(event) for event in events):
        raise IntegrityError("synthetic fixture contains forbidden sensitive-shaped fields")
    return payload, manifest


def run_acceptance(fixture_path: str | Path | None = None, manifest_path: str | Path | None = None) -> dict[str, Any]:
    payload, manifest = load_fixture(fixture_path, manifest_path)
    evaluator = BigOnionHoldRescue({"mode": "read-only", "provider_writes": 0})
    first = evaluator.evaluate(payload["events"], as_of=payload["as_of"], cutoff_hours=manifest["cutoff_hours"])
    second = evaluator.evaluate(payload["events"], as_of=payload["as_of"], cutoff_hours=manifest["cutoff_hours"])
    eligible_ids = [item["event_id"] for item in first.recommendations]
    if eligible_ids != manifest["expected_eligible_ids"]:
        raise IntegrityError("eligible ID acceptance mismatch")
    if first != second or first.digest() != second.digest():
        raise IntegrityError("replay drift")
    if any((first.sends, first.actions, first.provider_writes, first.state_mutations, first.events_added)):
        raise IntegrityError("read-only side-effect boundary violated")
    truth = [event.get("event_id") for event in payload["events"] if event.get("truth_eligible") is True]
    if truth != eligible_ids:
        raise IntegrityError("fixture truth mismatch")
    return {
        "demand_id": DEMAND_ID,
        "eligible_ids": eligible_ids,
        "recommendation_count": len(first.recommendations),
        "replay_identical": True,
        "result_digest": first.digest(),
        "authoritative_fingerprint": evaluator.authoritative_fingerprint,
        "sends": first.sends,
        "actions": first.actions,
        "provider_writes": first.provider_writes,
        "state_mutations": first.state_mutations,
        "events_added": first.events_added,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate the frozen synthetic Big Onion 48h hold-rescue queue.")
    parser.add_argument("--fixture")
    parser.add_argument("--manifest")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        output = run_acceptance(args.fixture, args.manifest)
    except (IntegrityError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps({"ok": True, **output}, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
