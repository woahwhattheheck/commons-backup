"""Synthetic/read-only AS9100 traveler evidence reconciliation for Polar Semiconductor."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

DEMAND_ID = "trace-polar-as9100-lims-01"
MANIFEST_PREFIX = "TRACE-POLAR-AS9100-SYNTHETIC-MANIFEST-V1\n"
APPROVED_REVISION = "R4"
EXPECTED_STATUSES = {
    "W1": "REVIEW_READY",
    "W2": "HOLD_REVISION",
    "W3": "HOLD_CAL_AND_SIGNATURE",
}
EXCEPTION_CODES = (
    "RECIPE_REVISION_MISMATCH",
    "CALIBRATION_EXPIRED",
    "OPERATOR_SIGNATURE_MISSING",
)
RESERVED_REVIEWERS = {
    "auto", "automatic", "automation", "bot", "system", "service",
    "service-account", "agent", "ai", "scheduler", "worker", "pipeline",
    "anonymous", "unknown",
}
FORBIDDEN_KEYS = {
    "password", "secret", "token", "api_key", "credential", "recipe_parameters",
    "process_parameters", "production_target", "customer_secret",
}


class IntegrityError(ValueError):
    pass


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _manifest_envelope(manifest: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "demand_id", "fixture_version", "dataset_sha256", "expanded_steps_sha256",
        "step_count", "wafer_count", "approved_revision", "expected_statuses",
        "expected_exception_codes", "expected_exception_count", "expected_pack_count",
    )
    return {key: manifest[key] for key in keys}


def verify_manifest_signature(manifest: Mapping[str, Any]) -> None:
    if manifest.get("signature_alg") != "sha256-content-envelope-v1":
        raise IntegrityError("unsupported manifest signature algorithm")
    expected = _sha(MANIFEST_PREFIX + _canon(_manifest_envelope(manifest)))
    if manifest.get("signature") != expected:
        raise IntegrityError("manifest signature mismatch")


def expand_fixture(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    if payload.get("schema") != "deterministic-generator-v1":
        raise IntegrityError("fixture schema mismatch")
    generator = payload.get("generator")
    if not isinstance(generator, dict):
        raise IntegrityError("fixture generator missing")
    wafer_ids = generator.get("wafer_ids")
    steps_per_wafer = generator.get("steps_per_wafer")
    if wafer_ids != ["W1", "W2", "W3"] or steps_per_wafer != 12:
        raise IntegrityError("fixture dimensions mismatch")
    if generator.get("approved_revision") != APPROVED_REVISION:
        raise IntegrityError("approved revision mismatch")

    revision_override = generator.get("revision_override", {})
    expired_calibration = generator.get("expired_calibration", {})
    blank_signoff = generator.get("blank_signoff", {})
    steps: list[dict[str, Any]] = []
    for wafer_id in wafer_ids:
        for number in range(1, steps_per_wafer + 1):
            revision = APPROVED_REVISION
            override = revision_override.get(wafer_id)
            if isinstance(override, dict) and override.get("step") == number:
                revision = override.get("revision")
            calibration_valid = not (
                isinstance(expired_calibration.get(wafer_id), dict)
                and expired_calibration[wafer_id].get("step") == number
            )
            signoff = f"Operator {((number - 1) % 4) + 1:02d}"
            if (
                isinstance(blank_signoff.get(wafer_id), dict)
                and blank_signoff[wafer_id].get("step") == number
            ):
                signoff = ""
            base = {
                "wafer_id": wafer_id,
                "traveler_id": f"TRAV-{wafer_id}-SYN",
                "step_id": f"STEP-{number:02d}",
                "sequence": number,
                "recipe_revision": revision,
                "calibration_id": f"CAL-SYN-{number:02d}",
                "calibration_valid": calibration_valid,
                "operator_signoff": signoff,
                "measurement_evidence_id": f"MEAS-{wafer_id}-{number:02d}",
                "qms_reference": f"QMS-SYN-{wafer_id}-{number:02d}",
                "synthetic": True,
            }
            base["source_sha256"] = _sha(_canon(base))
            steps.append(base)
    return steps


def _validate_step(step: Mapping[str, Any]) -> None:
    if not step.get("synthetic"):
        raise IntegrityError("non-synthetic step rejected")
    lowered = {str(key).lower() for key in step}
    if lowered & FORBIDDEN_KEYS:
        raise IntegrityError("fixture contains forbidden operational/secret field")
    expected_hash = _sha(_canon({key: value for key, value in step.items() if key != "source_sha256"}))
    if step.get("source_sha256") != expected_hash:
        raise IntegrityError("step source hash mismatch")


def verify_fixture(steps: list[dict[str, Any]], manifest: Mapping[str, Any]) -> None:
    verify_manifest_signature(manifest)
    if manifest.get("demand_id") != DEMAND_ID:
        raise IntegrityError("demand mismatch")
    if manifest.get("approved_revision") != APPROVED_REVISION:
        raise IntegrityError("manifest revision mismatch")
    if manifest.get("wafer_count") != 3 or manifest.get("step_count") != 36:
        raise IntegrityError("manifest counts mismatch")
    if len(steps) != 36 or len({step["wafer_id"] for step in steps}) != 3:
        raise IntegrityError("expanded fixture counts mismatch")
    if _sha(_canon(steps)) != manifest.get("expanded_steps_sha256"):
        raise IntegrityError("expanded fixture hash mismatch")
    for step in steps:
        _validate_step(step)
    counts = Counter(step["wafer_id"] for step in steps)
    if counts != Counter({"W1": 12, "W2": 12, "W3": 12}):
        raise IntegrityError("traveler step cardinality mismatch")
    for wafer_id in ("W1", "W2", "W3"):
        seq = [step["sequence"] for step in steps if step["wafer_id"] == wafer_id]
        if seq != list(range(1, 13)):
            raise IntegrityError("traveler sequence mismatch")


def load_fixture(fixture_path: str | Path | None = None, manifest_path: str | Path | None = None):
    base = Path(__file__).resolve().parent / "fixtures"
    fixture = Path(fixture_path) if fixture_path else base / "polar_as9100_3_wafers.json"
    manifest_file = Path(manifest_path) if manifest_path else base / "manifest.json"
    text = fixture.read_text(encoding="utf-8")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if _sha(text) != manifest.get("dataset_sha256"):
        raise IntegrityError("fixture file hash mismatch")
    payload = json.loads(text)
    if payload.get("fixture_version") != manifest.get("fixture_version"):
        raise IntegrityError("fixture version mismatch")
    steps = expand_fixture(payload)
    verify_fixture(steps, manifest)
    return steps, manifest


def _exception_rows(wafer_steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for step in wafer_steps:
        if step["recipe_revision"] != APPROVED_REVISION:
            rows.append({
                "wafer_id": step["wafer_id"], "step_id": step["step_id"],
                "code": "RECIPE_REVISION_MISMATCH", "observed": step["recipe_revision"],
                "expected": APPROVED_REVISION, "source_sha256": step["source_sha256"],
            })
        if not step["calibration_valid"]:
            rows.append({
                "wafer_id": step["wafer_id"], "step_id": step["step_id"],
                "code": "CALIBRATION_EXPIRED", "calibration_id": step["calibration_id"],
                "source_sha256": step["source_sha256"],
            })
        if not step["operator_signoff"].strip():
            rows.append({
                "wafer_id": step["wafer_id"], "step_id": step["step_id"],
                "code": "OPERATOR_SIGNATURE_MISSING", "source_sha256": step["source_sha256"],
            })
    return rows


def _status_for(exceptions: list[dict[str, Any]]) -> str:
    codes = {row["code"] for row in exceptions}
    if not codes:
        return "REVIEW_READY"
    if codes == {"RECIPE_REVISION_MISMATCH"}:
        return "HOLD_REVISION"
    if codes == {"CALIBRATION_EXPIRED", "OPERATOR_SIGNATURE_MISSING"}:
        return "HOLD_CAL_AND_SIGNATURE"
    return "HOLD_EVIDENCE_EXCEPTION"


def _named_human(name: str) -> str:
    if not isinstance(name, str):
        raise PermissionError("named human reviewer required")
    normalized = " ".join(name.strip().split())
    identity_tokens = re.findall(r"[^\W\d_]+", normalized.casefold())
    if not normalized or any(token in RESERVED_REVIEWERS for token in identity_tokens):
        raise PermissionError("named human reviewer required")
    alpha_tokens = [token for token in identity_tokens if any(char.isalpha() for char in token)]
    if len(alpha_tokens) < 2:
        raise PermissionError("two-token human name required")
    return normalized


@dataclass
class ReplayResult:
    review_ready: int
    held: int
    replayed: int
    exceptions_added: int
    packs_added: int
    events_added: int
    statuses: dict[str, str]
    state_digest: str
    evidence_manifest_sha256: str


class PolarAs9100Shadow:
    def __init__(self, authoritative_state: Mapping[str, Any] | None = None):
        self.authoritative_state = copy.deepcopy(authoritative_state or {})
        self._authoritative_fingerprint = _sha(_canon(self.authoritative_state))
        self.evidence_packs: dict[str, dict[str, Any]] = {}
        self.exceptions: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self._processed: set[str] = set()

    @property
    def authoritative_fingerprint(self) -> str:
        current = _sha(_canon(self.authoritative_state))
        if current != self._authoritative_fingerprint:
            raise IntegrityError("authoritative state mutated")
        return current

    def state_digest(self) -> str:
        return _sha(_canon({
            "evidence_packs": self.evidence_packs,
            "exceptions": self.exceptions,
            "events": self.events,
            "processed": sorted(self._processed),
        }))

    def evidence_manifest_sha256(self) -> str:
        return _sha(_canon({
            "packs": [self.evidence_packs[key] for key in sorted(self.evidence_packs)],
            "exceptions": self.exceptions,
        }))

    def replay(self, steps: list[dict[str, Any]], manifest: Mapping[str, Any]) -> ReplayResult:
        verify_fixture(steps, manifest)
        self.authoritative_fingerprint
        review_ready = held = replayed = exceptions_added = packs_added = events_added = 0
        statuses: dict[str, str] = {}
        for wafer_id in ("W1", "W2", "W3"):
            if wafer_id in self._processed:
                replayed += 1
                statuses[wafer_id] = self.evidence_packs[wafer_id]["status"]
                continue
            wafer_steps = [step for step in steps if step["wafer_id"] == wafer_id]
            exceptions = _exception_rows(wafer_steps)
            status = _status_for(exceptions)
            statuses[wafer_id] = status
            if status == "REVIEW_READY":
                review_ready += 1
            else:
                held += 1
            trace_matrix = [
                {
                    "step_id": step["step_id"],
                    "recipe_revision": step["recipe_revision"],
                    "calibration_id": step["calibration_id"],
                    "calibration_valid": step["calibration_valid"],
                    "operator_signoff_present": bool(step["operator_signoff"].strip()),
                    "measurement_evidence_id": step["measurement_evidence_id"],
                    "qms_reference": step["qms_reference"],
                    "source_sha256": step["source_sha256"],
                }
                for step in wafer_steps
            ]
            pack_core = {
                "wafer_id": wafer_id,
                "status": status,
                "traveler_id": wafer_steps[0]["traveler_id"],
                "step_count": len(wafer_steps),
                "approved_revision": APPROVED_REVISION,
                "exception_codes": [row["code"] for row in exceptions],
                "trace_matrix_sha256": _sha(_canon(trace_matrix)),
                "source_step_hashes": [step["source_sha256"] for step in wafer_steps],
                "disposition_state": "STAGED_HUMAN_DISPOSITION",
                "disposed_by": None,
                "sent": False,
            }
            pack = dict(pack_core)
            pack["evidence_pack_sha256"] = _sha(_canon(pack_core))
            self.evidence_packs[wafer_id] = pack
            self.exceptions.extend(copy.deepcopy(exceptions))
            self.events.append({
                "sequence": len(self.events) + 1,
                "wafer_id": wafer_id,
                "status": status,
                "evidence_pack_sha256": pack["evidence_pack_sha256"],
            })
            self._processed.add(wafer_id)
            exceptions_added += len(exceptions)
            packs_added += 1
            events_added += 1
        if not replayed:
            if statuses != manifest.get("expected_statuses"):
                raise IntegrityError("status truth-set mismatch")
            if len(self.exceptions) != manifest.get("expected_exception_count"):
                raise IntegrityError("exception count mismatch")
            if Counter(row["code"] for row in self.exceptions) != Counter(manifest.get("expected_exception_codes")):
                raise IntegrityError("exception truth-set mismatch")
            if len(self.evidence_packs) != manifest.get("expected_pack_count"):
                raise IntegrityError("evidence pack count mismatch")
        self.authoritative_fingerprint
        return ReplayResult(
            review_ready=review_ready,
            held=held,
            replayed=replayed,
            exceptions_added=exceptions_added,
            packs_added=packs_added,
            events_added=events_added,
            statuses=statuses,
            state_digest=self.state_digest(),
            evidence_manifest_sha256=self.evidence_manifest_sha256(),
        )

    def disposition_copy(self, wafer_id: str, reviewer_name: str, decision: str = "APPROVED_FOR_HUMAN_DISPOSITION") -> dict[str, Any]:
        reviewer = _named_human(reviewer_name)
        pack = self.evidence_packs.get(wafer_id)
        if pack is None:
            raise KeyError(wafer_id)
        if pack["status"] != "REVIEW_READY":
            raise PermissionError("held evidence cannot release a report")
        if decision not in {"APPROVED_FOR_HUMAN_DISPOSITION", "REJECTED_BY_HUMAN"}:
            raise ValueError("unsupported human disposition")
        out = copy.deepcopy(pack)
        out["disposition_state"] = decision
        out["disposed_by"] = reviewer
        out["sent"] = False
        return out

    def automatic_disposition(self, *_args: Any, **_kwargs: Any) -> None:
        raise PermissionError("automatic release is disabled")


def run_acceptance() -> dict[str, Any]:
    steps, manifest = load_fixture()
    shadow = PolarAs9100Shadow({"traveler_adapter": "read-only", "qms_adapter": "read-only", "production_writes": 0})
    first = shadow.replay(steps, manifest)
    digest = first.state_digest
    evidence_hash = first.evidence_manifest_sha256
    second = shadow.replay(steps, manifest)
    if second.replayed != 3 or any((second.exceptions_added, second.packs_added, second.events_added)):
        raise IntegrityError("replay not idempotent")
    if second.state_digest != digest or second.evidence_manifest_sha256 != evidence_hash:
        raise IntegrityError("replay hash drift")
    disposition = shadow.disposition_copy("W1", "Jordan Reviewer")
    return {
        "demand_id": DEMAND_ID,
        "step_count": len(steps),
        "statuses": first.statuses,
        "exception_count": len(shadow.exceptions),
        "evidence_pack_count": len(shadow.evidence_packs),
        "replay_zero_add": True,
        "state_digest": digest,
        "evidence_manifest_sha256": evidence_hash,
        "authoritative_fingerprint": shadow.authoritative_fingerprint,
        "human_disposition_state": disposition["disposition_state"],
        "human_disposed_by": disposition["disposed_by"],
        "sent": disposition["sent"],
    }


if __name__ == "__main__":
    print(json.dumps(run_acceptance(), sort_keys=True))
