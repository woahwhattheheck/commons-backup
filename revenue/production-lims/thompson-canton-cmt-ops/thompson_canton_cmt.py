from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

CONTRACT_ID = "thompson-canton-cmt-ops-lims-01"
EVALUATION_DATE = date(2026, 9, 9)
HOLD_OWNER = "CANTON-QA-HUMAN-QUEUE"
RESERVED_ACTOR_TOKENS = {
    "ai", "agent", "api", "assistant", "auto", "automated", "automation",
    "bot", "daemon", "integration", "machine", "robot", "scheduler",
    "service", "system", "workflow",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def source_digest(job: Mapping[str, Any]) -> str:
    return sha256_text(canonical_json(job))


def named_human(value: str) -> bool:
    if not isinstance(value, str):
        return False
    raw_tokens = re.findall(r"[A-Za-z0-9]+", value)
    tokens = [token.casefold() for token in raw_tokens]
    if len(tokens) < 2:
        return False
    if any(token in RESERVED_ACTOR_TOKENS for token in tokens):
        return False
    if any(len(token) < 2 for token in tokens):
        return False
    return sum(token.isalpha() for token in raw_tokens) >= 2


def build_registry() -> Dict[str, Dict[str, Any]]:
    return {
        "concrete": {
            "method_authority": "ASTM-SYNTHETIC",
            "method_code": "ASTM-SYN-CONCRETE",
            "method_revision": "2026.1",
            "technician_id": "TECH-CONCRETE-A",
            "qualification_id": "QUAL-CONCRETE-2026",
            "equipment_id": "EQ-CONCRETE-A",
            "scope_id": "SYN-SCOPE-CONCRETE-2026",
        },
        "aggregate": {
            "method_authority": "ANSI-SYNTHETIC",
            "method_code": "ANSI-SYN-AGGREGATE",
            "method_revision": "2026.2",
            "technician_id": "TECH-AGGREGATE-A",
            "qualification_id": "QUAL-AGGREGATE-2026",
            "equipment_id": "EQ-AGGREGATE-A",
            "scope_id": "SYN-SCOPE-AGGREGATE-2026",
        },
        "masonry": {
            "method_authority": "FEDERAL-SYNTHETIC",
            "method_code": "FED-SYN-MASONRY",
            "method_revision": "2026.3",
            "technician_id": "TECH-MASONRY-A",
            "qualification_id": "QUAL-MASONRY-2026",
            "equipment_id": "EQ-MASONRY-A",
            "scope_id": "SYN-SCOPE-MASONRY-2026",
        },
        "enclosure": {
            "method_authority": "ASTM-SYNTHETIC",
            "method_code": "ASTM-SYN-ENCLOSURE",
            "method_revision": "2026.4",
            "technician_id": "TECH-ENCLOSURE-A",
            "qualification_id": "QUAL-ENCLOSURE-2026",
            "equipment_id": "EQ-ENCLOSURE-A",
            "scope_id": "SYN-SCOPE-ENCLOSURE-2026",
        },
    }


def expected_slot(material_class: str, slot_number: int) -> str:
    return f"CANTON-{material_class.upper()}-SLOT-{slot_number:02d}"


@dataclass
class CantonState:
    processed_submissions: Dict[str, str] = field(default_factory=dict)
    scheduled_job_ids: Dict[str, str] = field(default_factory=dict)
    scheduled: List[Dict[str, Any]] = field(default_factory=list)
    result_stubs: List[Dict[str, Any]] = field(default_factory=list)
    staged_reports: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    holds: List[Dict[str, Any]] = field(default_factory=list)
    events: List[Dict[str, Any]] = field(default_factory=list)

    def digest(self) -> str:
        return sha256_text(canonical_json({
            "processed_submissions": self.processed_submissions,
            "scheduled_job_ids": self.scheduled_job_ids,
            "scheduled": self.scheduled,
            "result_stubs": self.result_stubs,
            "staged_reports": self.staged_reports,
            "holds": self.holds,
            "events": self.events,
        }))

    def worklist_digest(self) -> str:
        return sha256_text(canonical_json(self.scheduled))

    def result_digest(self) -> str:
        return sha256_text(canonical_json(self.result_stubs))

    def report_digest(self) -> str:
        ordered = [self.staged_reports[key] for key in sorted(self.staged_reports)]
        return sha256_text(canonical_json(ordered))


class ThompsonCantonGate:
    def __init__(self, registry: Mapping[str, Mapping[str, Any]] | None = None) -> None:
        self.registry = {key: dict(value) for key, value in (registry or build_registry()).items()}
        self.state = CantonState()

    def _result(self, job: Mapping[str, Any], state: str, code: str, *, idempotent: bool = False) -> Dict[str, Any]:
        return {
            "submission_id": job.get("submission_id"),
            "job_id": job.get("job_id"),
            "state": state,
            "code": code,
            "idempotent": idempotent,
        }

    def _hold(self, job: Mapping[str, Any], code: str) -> Dict[str, Any]:
        record = {
            "submission_id": job["submission_id"],
            "job_id": job["job_id"],
            "code": code,
            "owner": HOLD_OWNER,
        }
        self.state.holds.append(record)
        self.state.events.append({"type": "HOLD", **record})
        return self._result(job, "HOLD", code)

    def process(self, job: Mapping[str, Any]) -> Dict[str, Any]:
        if not isinstance(job, Mapping):
            raise ValueError("job must be a mapping")
        required = {
            "submission_id", "job_id", "request_id", "sample_id", "material_class",
            "method_authority", "method_code", "method_revision", "technician_id",
            "qualification_id", "equipment_id", "calibration_expires", "slot_number",
            "expected_schedule_key",
        }
        if any(key not in job for key in required):
            raise ValueError("job is missing required Canton gate fields")
        submission_id = job["submission_id"]
        job_id = job["job_id"]
        if not isinstance(submission_id, str) or not submission_id:
            raise ValueError("submission_id must be a non-empty string")
        if not isinstance(job_id, str) or not job_id:
            raise ValueError("job_id must be a non-empty string")

        digest = source_digest(job)
        prior = self.state.processed_submissions.get(submission_id)
        if prior is not None:
            if prior != digest:
                return self._result(job, "HOLD", "REPLAY_PAYLOAD_CONFLICT")
            return self._result(job, "IDEMPOTENT", "IDEMPOTENT_RETRY", idempotent=True)
        self.state.processed_submissions[submission_id] = digest

        if not isinstance(job["request_id"], str) or not job["request_id"].strip():
            return self._hold(job, "INCOMPLETE_REQUEST")
        if not isinstance(job["sample_id"], str) or not job["sample_id"].strip():
            return self._hold(job, "INCOMPLETE_REQUEST")

        route = self.registry.get(job["material_class"])
        if route is None:
            return self._hold(job, "METHOD_INELIGIBLE")
        if job["method_authority"] != route["method_authority"] or job["method_code"] != route["method_code"]:
            return self._hold(job, "METHOD_INELIGIBLE")
        if job["method_revision"] != route["method_revision"]:
            return self._hold(job, "METHOD_REVISION_MISMATCH")
        if job["technician_id"] != route["technician_id"] or job["qualification_id"] != route["qualification_id"]:
            return self._hold(job, "TECHNICIAN_UNQUALIFIED")
        if job["equipment_id"] != route["equipment_id"]:
            return self._hold(job, "EQUIPMENT_UNAVAILABLE")
        try:
            calibration_expires = date.fromisoformat(job["calibration_expires"])
        except (TypeError, ValueError):
            return self._hold(job, "CALIBRATION_EXPIRED")
        if calibration_expires < EVALUATION_DATE:
            return self._hold(job, "CALIBRATION_EXPIRED")
        if not isinstance(job["slot_number"], int) or isinstance(job["slot_number"], bool):
            return self._hold(job, "SCHEDULE_SLOT_INVALID")
        if job["slot_number"] < 1 or job["slot_number"] > 20:
            return self._hold(job, "SCHEDULE_SLOT_INVALID")
        schedule_key = expected_slot(job["material_class"], job["slot_number"])
        if job["expected_schedule_key"] != schedule_key:
            return self._hold(job, "SCHEDULE_SLOT_INVALID")
        if job_id in self.state.scheduled_job_ids:
            return self._hold(job, "DUPLICATE_JOB_ID")
        if any(item["schedule_key"] == schedule_key for item in self.state.scheduled):
            return self._hold(job, "SCHEDULE_COLLISION")

        schedule = {
            "job_id": job_id,
            "schedule_key": schedule_key,
            "material_class": job["material_class"],
            "scope_id": route["scope_id"],
            "method_authority": route["method_authority"],
            "method_code": route["method_code"],
            "method_revision": route["method_revision"],
            "technician_id": route["technician_id"],
            "qualification_id": route["qualification_id"],
            "equipment_id": route["equipment_id"],
            "calibration_expires": job["calibration_expires"],
            "run_state": "NOT_RUN",
            "source_sha256": digest,
        }
        result_stub = {
            "job_id": job_id,
            "state": "NOT_RUN",
            "schedule_key": schedule_key,
            "source_sha256": digest,
        }
        report = {
            "job_id": job_id,
            "state": "STAGED_PEER_REVIEW",
            "sent": False,
            "schedule_key": schedule_key,
            "source_sha256": digest,
        }
        self.state.scheduled_job_ids[job_id] = submission_id
        self.state.scheduled.append(schedule)
        self.state.result_stubs.append(result_stub)
        self.state.staged_reports[job_id] = report
        self.state.events.append({
            "type": "SCHEDULED_ELIGIBLE",
            "submission_id": submission_id,
            "job_id": job_id,
            "schedule_key": schedule_key,
            "source_sha256": digest,
        })
        return self._result(job, "SCHEDULED", "SCHEDULED_ELIGIBLE")

    def process_many(self, jobs: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        return [self.process(job) for job in jobs]

    def release_report(self, job_id: str, reviewer: str) -> Dict[str, Any]:
        report = self.state.staged_reports.get(job_id)
        if report is None:
            raise KeyError("report is not staged")
        if report.get("state") != "STAGED_PEER_REVIEW" or report.get("sent") is not False:
            raise ValueError("report is not in copy-only staged state")
        if not named_human(reviewer):
            raise PermissionError("named human peer reviewer required")
        released = copy.deepcopy(report)
        released["state"] = "RELEASED_BY_NAMED_HUMAN"
        released["reviewer"] = reviewer.strip()
        released["sent"] = False
        return released

    def automatic_release(self, job_id: str) -> Dict[str, Any]:
        raise PermissionError("automatic report release is disabled")

    def run_job(self, job_id: str) -> Dict[str, Any]:
        raise PermissionError("synthetic acceptance gate does not execute laboratory work")


def expand_fixture_recipe(recipe: Mapping[str, Any]) -> List[Dict[str, Any]]:
    expected_plan = {
        "INCOMPLETE_REQUEST": 4,
        "METHOD_REVISION_MISMATCH": 4,
        "TECHNICIAN_UNQUALIFIED": 4,
        "EQUIPMENT_UNAVAILABLE": 4,
        "CALIBRATION_EXPIRED": 4,
    }
    if recipe.get("contract_id") != CONTRACT_ID:
        raise ValueError("unexpected contract_id")
    if recipe.get("valid_count") != 80 or recipe.get("hold_plan") != expected_plan:
        raise ValueError("unexpected fixture dimensions")
    materials = recipe.get("materials")
    if materials != ["concrete", "aggregate", "masonry", "enclosure"]:
        raise ValueError("unexpected material classes")
    registry = build_registry()
    jobs: List[Dict[str, Any]] = []
    for index in range(80):
        material = materials[index % 4]
        route = registry[material]
        slot = (index // 4) + 1
        jobs.append({
            "submission_id": f"CANTON-SUB-{index + 1:03d}",
            "job_id": f"CANTON-JOB-{index + 1:03d}",
            "request_id": f"REQ-{index + 1:03d}",
            "sample_id": f"SAMPLE-{index + 1:03d}",
            "material_class": material,
            "method_authority": route["method_authority"],
            "method_code": route["method_code"],
            "method_revision": route["method_revision"],
            "technician_id": route["technician_id"],
            "qualification_id": route["qualification_id"],
            "equipment_id": route["equipment_id"],
            "calibration_expires": "2027-01-31",
            "slot_number": slot,
            "expected_schedule_key": expected_slot(material, slot),
            "expected_state": "SCHEDULED",
            "expected_code": "SCHEDULED_ELIGIBLE",
        })

    next_index = 80
    for code, count in expected_plan.items():
        for _ in range(count):
            material = materials[next_index % 4]
            route = registry[material]
            slot = (next_index // 4) + 1
            job = {
                "submission_id": f"CANTON-SUB-{next_index + 1:03d}",
                "job_id": f"CANTON-JOB-{next_index + 1:03d}",
                "request_id": f"REQ-{next_index + 1:03d}",
                "sample_id": f"SAMPLE-{next_index + 1:03d}",
                "material_class": material,
                "method_authority": route["method_authority"],
                "method_code": route["method_code"],
                "method_revision": route["method_revision"],
                "technician_id": route["technician_id"],
                "qualification_id": route["qualification_id"],
                "equipment_id": route["equipment_id"],
                "calibration_expires": "2027-01-31",
                "slot_number": slot,
                "expected_schedule_key": expected_slot(material, slot),
                "expected_state": "HOLD",
                "expected_code": code,
            }
            if code == "INCOMPLETE_REQUEST":
                job["request_id"] = ""
            elif code == "METHOD_REVISION_MISMATCH":
                job["method_revision"] = "2025.STALE"
            elif code == "TECHNICIAN_UNQUALIFIED":
                job["qualification_id"] = "QUAL-EXPIRED"
            elif code == "EQUIPMENT_UNAVAILABLE":
                job["equipment_id"] = "EQ-UNAVAILABLE"
            elif code == "CALIBRATION_EXPIRED":
                job["calibration_expires"] = "2026-08-31"
            jobs.append(job)
            next_index += 1
    return jobs


def load_fixture(path: Path) -> List[Dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, list):
        return value
    if isinstance(value, Mapping):
        return expand_fixture_recipe(value)
    raise ValueError("fixture must be a list or deterministic recipe")


def verify_manifest(fixture_path: Path, manifest_path: Path) -> Dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if sha256_bytes(fixture_path.read_bytes()) != manifest["fixture_sha256"]:
        raise ValueError("fixture SHA-256 mismatch")
    contract = dict(manifest)
    expected = contract.pop("manifest_sha256")
    if sha256_text(canonical_json(contract)) != expected:
        raise ValueError("manifest digest mismatch")
    return manifest


def summarize(results: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    states: Dict[str, int] = {}
    hold_codes: Dict[str, int] = {}
    for result in results:
        state = str(result["state"])
        states[state] = states.get(state, 0) + 1
        if state == "HOLD":
            code = str(result["code"])
            hold_codes[code] = hold_codes.get(code, 0) + 1
    return {"states": states, "hold_codes": dict(sorted(hold_codes.items()))}


def cli(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synthetic/read-only Thompson & Lichtner Canton CMT acceptance gate")
    parser.add_argument("fixture", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args(argv)
    manifest = verify_manifest(args.fixture, args.manifest)
    jobs = load_fixture(args.fixture)
    expanded_fixture_sha256 = sha256_text(canonical_json(jobs))
    gate = ThompsonCantonGate()
    first = gate.process_many(jobs)
    first_summary = summarize(first)
    audit_before = gate.state.digest()
    counts_before = (
        len(gate.state.scheduled), len(gate.state.holds), len(gate.state.events),
        len(gate.state.result_stubs), len(gate.state.staged_reports),
    )
    replay = gate.process_many(jobs)
    replay_summary = summarize(replay)
    counts_after = (
        len(gate.state.scheduled), len(gate.state.holds), len(gate.state.events),
        len(gate.state.result_stubs), len(gate.state.staged_reports),
    )
    audit_after = gate.state.digest()
    ok = (
        len(jobs) == manifest["fixture_count"] == 100
        and expanded_fixture_sha256 == manifest["expanded_fixture_sha256"]
        and first_summary["states"] == {"SCHEDULED": 80, "HOLD": 20}
        and first_summary["hold_codes"] == manifest["expected_hold_codes"]
        and len(gate.state.scheduled) == 80
        and all(item["run_state"] == "NOT_RUN" for item in gate.state.scheduled)
        and replay_summary["states"] == {"IDEMPOTENT": 100}
        and counts_before == counts_after
        and gate.state.worklist_digest() == manifest["expected_worklist_sha256"]
        and gate.state.result_digest() == manifest["expected_result_sha256"]
        and gate.state.report_digest() == manifest["expected_report_sha256"]
        and audit_before == audit_after == manifest["expected_audit_sha256"]
    )
    print(canonical_json({
        "ok": ok,
        "fixture_count": len(jobs),
        "first": first_summary,
        "replay": replay_summary,
        "scheduled": len(gate.state.scheduled),
        "run_count": sum(1 for item in gate.state.scheduled if item["run_state"] != "NOT_RUN"),
        "fixture_sha256": manifest["fixture_sha256"],
        "expanded_fixture_sha256": expanded_fixture_sha256,
        "worklist_sha256": gate.state.worklist_digest(),
        "result_sha256": gate.state.result_digest(),
        "report_sha256": gate.state.report_digest(),
        "audit_sha256": audit_after,
        "manifest_sha256": manifest["manifest_sha256"],
    }))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(cli())
