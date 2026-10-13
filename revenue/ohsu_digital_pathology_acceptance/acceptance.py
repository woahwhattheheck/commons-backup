#!/usr/bin/env python3
"""Deterministic, synthetic/no-PHI acceptance harness for Epic Beaker ↔ pathology IMS flows.

This module validates integration evidence only. It does not make clinical decisions,
interpret pathology images, connect to production systems, or process patient records.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,96}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PHI_LIKE_KEYS = {
    "patient_name", "patient", "mrn", "medical_record_number", "dob", "date_of_birth",
    "address", "phone", "email", "ssn", "patient_id", "pid_3", "pid_5",
}
STATUS_ORDER = {"ORDERED": 0, "IMAGE_AVAILABLE": 1, "QC_COMPLETE": 2, "PATHOLOGIST_REVIEWED": 3}
ALLOWED_EVENT_TYPES = {"order", "status", "link", "ai_provenance", "case_close"}


class AcceptanceError(ValueError):
    """Input is not valid integration evidence under this harness contract."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _require_object(value: Any, name: str = "event") -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AcceptanceError(f"{name} must be a JSON object")
    return value


def _require_id(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or ID_RE.fullmatch(value) is None:
        raise AcceptanceError(f"{field_name} must match {ID_RE.pattern}")
    return value


def _require_seq(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AcceptanceError("seq must be a non-negative integer")
    return value


def _reject_phi_like_keys(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in PHI_LIKE_KEYS:
                raise AcceptanceError(f"PHI-like field is not accepted by the synthetic harness: {path}.{key}")
            _reject_phi_like_keys(child, f"{path}.{key}")
    elif isinstance(value, list):
        for i, child in enumerate(value):
            _reject_phi_like_keys(child, f"{path}[{i}]")


def _exact_keys(event: dict[str, Any], required: set[str], optional: set[str] = set()) -> None:
    missing = required - event.keys()
    extra = event.keys() - required - optional
    if missing:
        raise AcceptanceError(f"missing fields: {sorted(missing)}")
    if extra:
        raise AcceptanceError(f"unknown fields: {sorted(extra)}")


@dataclass
class SlideState:
    case_id: str
    slide_id: str
    order_event_id: str
    status: str = "ORDERED"
    deep_link: str | None = None
    ai_receipts: list[str] = field(default_factory=list)


class AcceptanceSession:
    """Stateful deterministic validator for a captured synthetic integration transcript."""

    def __init__(self) -> None:
        self.events: dict[str, dict[str, Any]] = {}
        self.event_order: list[str] = []
        self.slides: dict[tuple[str, str], SlideState] = {}
        self.closed_cases: set[str] = set()
        self.duplicate_replays = 0

    def apply(self, raw_event: Any) -> None:
        event = _require_object(raw_event)
        _reject_phi_like_keys(event)
        common = {"type", "event_id", "seq"}
        if not common.issubset(event):
            raise AcceptanceError(f"missing common fields: {sorted(common - event.keys())}")
        event_type = event["type"]
        if event_type not in ALLOWED_EVENT_TYPES:
            raise AcceptanceError(f"unsupported event type: {event_type!r}")
        event_id = _require_id(event["event_id"], "event_id")
        _require_seq(event["seq"])

        existing = self.events.get(event_id)
        if existing is not None:
            if canonical_json(existing) != canonical_json(event):
                raise AcceptanceError(f"event_id conflict: {event_id}")
            self.duplicate_replays += 1
            return

        if event_type == "order":
            self._apply_order(event)
        elif event_type == "status":
            self._apply_status(event)
        elif event_type == "link":
            self._apply_link(event)
        elif event_type == "ai_provenance":
            self._apply_ai_provenance(event)
        elif event_type == "case_close":
            self._apply_case_close(event)
        else:
            raise AcceptanceError("unreachable event type")

        self.events[event_id] = event
        self.event_order.append(event_id)

    def _get_slide(self, case_id: Any, slide_id: Any) -> SlideState:
        key = (_require_id(case_id, "case_id"), _require_id(slide_id, "slide_id"))
        state = self.slides.get(key)
        if state is None:
            raise AcceptanceError(f"slide has no prior order: {key[0]}/{key[1]}")
        return state

    def _apply_order(self, event: dict[str, Any]) -> None:
        _exact_keys(event, {"type", "event_id", "seq", "message", "case_id", "slide_id", "order_id"})
        if event["message"] != "OML^O21":
            raise AcceptanceError("order evidence must use OML^O21")
        case_id = _require_id(event["case_id"], "case_id")
        slide_id = _require_id(event["slide_id"], "slide_id")
        _require_id(event["order_id"], "order_id")
        key = (case_id, slide_id)
        if case_id in self.closed_cases:
            raise AcceptanceError(f"case already closed: {case_id}")
        if key in self.slides:
            raise AcceptanceError(f"duplicate slide order with a new event_id: {case_id}/{slide_id}")
        self.slides[key] = SlideState(case_id, slide_id, event["event_id"])

    def _apply_status(self, event: dict[str, Any]) -> None:
        _exact_keys(event, {"type", "event_id", "seq", "message", "case_id", "slide_id", "status"})
        if event["message"] != "SSU^U03":
            raise AcceptanceError("slide status evidence must use one SSU^U03 event per slide")
        state = self._get_slide(event["case_id"], event["slide_id"])
        status = event["status"]
        if status not in STATUS_ORDER or status == "ORDERED":
            raise AcceptanceError(f"unsupported slide status: {status!r}")
        if state.case_id in self.closed_cases:
            raise AcceptanceError(f"case already closed: {state.case_id}")
        if STATUS_ORDER[status] < STATUS_ORDER[state.status]:
            raise AcceptanceError(f"status regression: {state.status} -> {status}")
        if STATUS_ORDER[status] == STATUS_ORDER[state.status]:
            raise AcceptanceError("same status must replay the original event_id; a new event_id is ambiguous")
        state.status = status

    def _apply_link(self, event: dict[str, Any]) -> None:
        _exact_keys(event, {"type", "event_id", "seq", "case_id", "slide_id", "scope", "linked_id", "url"})
        state = self._get_slide(event["case_id"], event["slide_id"])
        scope = event["scope"]
        if scope not in {"case", "slide"}:
            raise AcceptanceError("link scope must be 'case' or 'slide'")
        expected = state.case_id if scope == "case" else state.slide_id
        if event["linked_id"] != expected:
            raise AcceptanceError(f"link identity mismatch: expected {expected!r}")
        url = event["url"]
        if not isinstance(url, str):
            raise AcceptanceError("url must be a string")
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise AcceptanceError("deep link must use an absolute https URL")
        if parsed.username or parsed.password:
            raise AcceptanceError("deep link must not embed credentials")
        state.deep_link = url

    def _apply_ai_provenance(self, event: dict[str, Any]) -> None:
        _exact_keys(event, {
            "type", "event_id", "seq", "case_id", "slide_id", "adapter", "model_name",
            "model_version", "artifact_sha256", "input_sha256", "purpose", "authority",
        })
        state = self._get_slide(event["case_id"], event["slide_id"])
        _require_id(event["adapter"], "adapter")
        _require_id(event["model_name"], "model_name")
        _require_id(event["model_version"], "model_version")
        if not isinstance(event["artifact_sha256"], str) or SHA256_RE.fullmatch(event["artifact_sha256"]) is None:
            raise AcceptanceError("artifact_sha256 must be lowercase SHA-256 hex")
        if not isinstance(event["input_sha256"], str) or SHA256_RE.fullmatch(event["input_sha256"]) is None:
            raise AcceptanceError("input_sha256 must be lowercase SHA-256 hex")
        if event["authority"] != "decision_support_only":
            raise AcceptanceError("AI adapter evidence cannot assert autonomous clinical authority")
        if not isinstance(event["purpose"], str) or not (1 <= len(event["purpose"]) <= 160):
            raise AcceptanceError("purpose must be a 1..160 character string")
        state.ai_receipts.append(event["event_id"])

    def _apply_case_close(self, event: dict[str, Any]) -> None:
        _exact_keys(event, {"type", "event_id", "seq", "message", "case_id"})
        if event["message"] != "ORU^R01":
            raise AcceptanceError("case-close synchronization evidence must use ORU^R01")
        case_id = _require_id(event["case_id"], "case_id")
        if case_id in self.closed_cases:
            raise AcceptanceError("same case close must replay the original event_id")
        states = [s for s in self.slides.values() if s.case_id == case_id]
        if not states:
            raise AcceptanceError(f"cannot close unknown case: {case_id}")
        not_available = [s.slide_id for s in states if STATUS_ORDER[s.status] < STATUS_ORDER["IMAGE_AVAILABLE"]]
        if not_available:
            raise AcceptanceError(f"cannot close case before every ordered slide is image-available: {sorted(not_available)}")
        self.closed_cases.add(case_id)

    def receipt(self) -> dict[str, Any]:
        ordered_events = [self.events[event_id] for event_id in self.event_order]
        cases = sorted({s.case_id for s in self.slides.values()})
        linked = sum(1 for s in self.slides.values() if s.deep_link is not None)
        ai_count = sum(len(s.ai_receipts) for s in self.slides.values())
        receipt = {
            "schema": "ohsu-digpath-acceptance/v1",
            "authority": "integration_acceptance_only",
            "clinical_decision_authority": False,
            "phi_accepted": False,
            "unique_event_count": len(ordered_events),
            "duplicate_replay_count": self.duplicate_replays,
            "case_count": len(cases),
            "slide_count": len(self.slides),
            "linked_slide_count": linked,
            "ai_provenance_count": ai_count,
            "closed_cases": sorted(self.closed_cases),
            "event_sha256": digest(ordered_events),
            "slides": [
                {
                    "case_id": state.case_id,
                    "slide_id": state.slide_id,
                    "status": state.status,
                    "has_deep_link": state.deep_link is not None,
                    "ai_provenance_count": len(state.ai_receipts),
                }
                for _, state in sorted(self.slides.items())
            ],
        }
        receipt["receipt_sha256"] = digest(receipt)
        return receipt


def parse_jsonl(lines: Iterable[str]) -> AcceptanceSession:
    session = AcceptanceSession()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line, object_pairs_hook=_no_duplicate_keys)
        except (json.JSONDecodeError, AcceptanceError) as exc:
            raise AcceptanceError(f"line {line_number}: {exc}") from exc
        try:
            session.apply(event)
        except AcceptanceError as exc:
            raise AcceptanceError(f"line {line_number}: {exc}") from exc
    return session


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise AcceptanceError(f"duplicate JSON key: {key}")
        obj[key] = value
    return obj


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events", type=Path, help="synthetic JSONL transcript")
    parser.add_argument("--out", type=Path, help="write canonical receipt JSON to this path")
    args = parser.parse_args(argv)
    try:
        with args.events.open("r", encoding="utf-8") as handle:
            receipt = parse_jsonl(handle).receipt()
        text = json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        if args.out:
            args.out.write_text(text, encoding="utf-8")
        else:
            sys.stdout.write(text)
        return 0
    except (AcceptanceError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
