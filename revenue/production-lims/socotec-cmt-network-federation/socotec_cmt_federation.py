from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Tuple

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


def legacy_payload_digest(payload: Mapping[str, Any]) -> str:
    return sha256_text(canonical_json(payload))


def build_registry() -> Dict[str, Dict[str, Any]]:
    registry: Dict[str, Dict[str, Any]] = {}
    for number in range(1, 26):
        namespace = f"SOC-{number:02d}"
        registry[f"CMT-SVC-{number:02d}"] = {
            "namespace": namespace,
            "scope_id": f"SCOPE-{number:02d}-2026",
            "method_code": f"CMT-METHOD-{number:02d}",
            "method_version": f"2026.{(number % 4) + 1}",
            "equipment_id": f"EQ-{number:02d}-A",
            "personnel_id": f"TECH-{number:02d}-A",
            "qualification_id": f"QUAL-{number:02d}-2026",
            "capacity": 40,
            "legacy_system": f"LEGACY-{number:02d}",
        }
    return registry


def _namespace_number(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"SOC-(\d{2})", value)
    if match is None:
        return None
    number = int(match.group(1))
    return number if 1 <= number <= 25 else None


def allowed_transfer(origin: str, destination: str) -> bool:
    origin_n = _namespace_number(origin)
    destination_n = _namespace_number(destination)
    if origin_n is None or destination_n is None:
        return False
    if origin_n == destination_n:
        return True
    predecessor = 25 if destination_n == 1 else destination_n - 1
    return origin_n == predecessor


def expected_transfer_ticket(origin: str, destination: str, job_id: str) -> str:
    return sha256_text(f"{origin}|{destination}|{job_id}|SOCOTEC-CMT-2026")[:24]


def named_human(value: str) -> bool:
    if not isinstance(value, str):
        return False
    tokens = [token.casefold() for token in re.findall(r"[A-Za-z0-9]+", value)]
    alpha_tokens = [token for token in tokens if any(char.isalpha() for char in token)]
    if len(tokens) < 2 or len(alpha_tokens) < 2:
        return False
    if any(token in RESERVED_ACTOR_TOKENS for token in tokens):
        return False
    if any(len(token) < 2 for token in tokens):
        return False
    return True


@dataclass
class FederationState:
    processed_submissions: Dict[str, str] = field(default_factory=dict)
    ready_job_ids: Dict[str, str] = field(default_factory=dict)
    accessions: List[Dict[str, Any]] = field(default_factory=list)
    staged_reports: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    holds: List[Dict[str, Any]] = field(default_factory=list)
    events: List[Dict[str, Any]] = field(default_factory=list)

    def digest(self) -> str:
        payload = {
            "processed_submissions": self.processed_submissions,
            "ready_job_ids": self.ready_job_ids,
            "accessions": self.accessions,
            "staged_reports": self.staged_reports,
            "holds": self.holds,
            "events": self.events,
        }
        return sha256_text(canonical_json(payload))


class SocotecCmtFederation:
    def __init__(self, registry: Mapping[str, Mapping[str, Any]] | None = None) -> None:
        self.registry: Dict[str, Dict[str, Any]] = {
            key: dict(value) for key, value in (registry or build_registry()).items()
        }
        self.state = FederationState()

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
        }
        self.state.holds.append(record)
        self.state.events.append({"type": "HOLD", **record})
        return self._result(job, "HOLD", code)

    def process(self, job: Mapping[str, Any]) -> Dict[str, Any]:
        required = {
            "submission_id", "job_id", "service_code", "origin_namespace", "scope_id",
            "method_code", "method_version", "equipment_id", "personnel_id",
            "qualification_id", "capacity_position", "legacy_payload",
            "legacy_payload_sha256", "expected_route_namespace",
        }
        if not isinstance(job, Mapping) or any(key not in job for key in required):
            raise ValueError("job is missing required federation fields")
        submission_id = job["submission_id"]
        job_id = job["job_id"]
        if not isinstance(submission_id, str) or not submission_id:
            raise ValueError("submission_id must be a non-empty string")
        if not isinstance(job_id, str) or not job_id:
            raise ValueError("job_id must be a non-empty string")

        digest = source_digest(job)
        prior_digest = self.state.processed_submissions.get(submission_id)
        if prior_digest is not None:
            if prior_digest != digest:
                return self._result(job, "HOLD", "REPLAY_PAYLOAD_CONFLICT")
            return self._result(job, "IDEMPOTENT", "IDEMPOTENT_REPLAY", idempotent=True)
        # Record the exact first-seen payload even for held submissions so replay is zero-add.
        self.state.processed_submissions[submission_id] = digest

        route = self.registry.get(job["service_code"])
        if route is None:
            return self._hold(job, "SCOPE_MISMATCH")
        if job["expected_route_namespace"] != route["namespace"]:
            return self._hold(job, "ROUTE_GOLDEN_MISMATCH")
        if job["scope_id"] != route["scope_id"]:
            return self._hold(job, "SCOPE_MISMATCH")
        if job["method_code"] != route["method_code"]:
            return self._hold(job, "SCOPE_MISMATCH")
        if job["method_version"] != route["method_version"]:
            return self._hold(job, "METHOD_VERSION_MISMATCH")
        if job["equipment_id"] != route["equipment_id"]:
            return self._hold(job, "EQUIPMENT_UNAVAILABLE")
        if job["personnel_id"] != route["personnel_id"] or job["qualification_id"] != route["qualification_id"]:
            return self._hold(job, "QUALIFICATION_INVALID")
        if not isinstance(job["capacity_position"], int) or isinstance(job["capacity_position"], bool):
            return self._hold(job, "CAPACITY_EXCEEDED")
        if job["capacity_position"] < 1 or job["capacity_position"] > route["capacity"]:
            return self._hold(job, "CAPACITY_EXCEEDED")
        if job_id in self.state.ready_job_ids:
            return self._hold(job, "DUPLICATE_JOB_ID")

        destination = route["namespace"]
        origin = job["origin_namespace"]
        if origin != destination:
            if not allowed_transfer(origin, destination):
                return self._hold(job, "UNAUTHORIZED_TRANSFER")
            if job.get("transfer_ticket") != expected_transfer_ticket(origin, destination, job_id):
                return self._hold(job, "UNAUTHORIZED_TRANSFER")

        payload = job["legacy_payload"]
        if not isinstance(payload, Mapping):
            return self._hold(job, "LEGACY_PAYLOAD_HASH_MISMATCH")
        if legacy_payload_digest(payload) != job["legacy_payload_sha256"]:
            return self._hold(job, "LEGACY_PAYLOAD_HASH_MISMATCH")
        expected_payload = {
            "job_id": job_id,
            "legacy_system": route["legacy_system"],
            "service_code": job["service_code"],
            "method_code": route["method_code"],
            "method_version": route["method_version"],
            "source_namespace": origin,
        }
        if dict(payload) != expected_payload:
            return self._hold(job, "LEGACY_PAYLOAD_CONTENT_MISMATCH")

        accession = {
            "job_id": job_id,
            "route_namespace": destination,
            "origin_namespace": origin,
            "service_code": job["service_code"],
            "scope_id": route["scope_id"],
            "method_code": route["method_code"],
            "method_version": route["method_version"],
            "equipment_id": route["equipment_id"],
            "personnel_id": route["personnel_id"],
            "qualification_id": route["qualification_id"],
            "legacy_payload_sha256": job["legacy_payload_sha256"],
            "source_sha256": digest,
            "transfer_authorized": origin == destination or allowed_transfer(origin, destination),
        }
        report = {
            "job_id": job_id,
            "state": "STAGED_HUMAN_REVIEW",
            "sent": False,
            "route_namespace": destination,
            "method_code": route["method_code"],
            "source_sha256": digest,
        }
        self.state.ready_job_ids[job_id] = submission_id
        self.state.accessions.append(accession)
        self.state.staged_reports[job_id] = report
        self.state.events.append({
            "type": "READY",
            "submission_id": submission_id,
            "job_id": job_id,
            "route_namespace": destination,
            "source_sha256": digest,
        })
        return self._result(job, "READY", "READY")

    def process_many(self, jobs: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        return [self.process(job) for job in jobs]

    def release_report(self, job_id: str, reviewer: str) -> Dict[str, Any]:
        report = self.state.staged_reports.get(job_id)
        if report is None:
            raise KeyError("report is not staged")
        if report.get("state") != "STAGED_HUMAN_REVIEW" or report.get("sent") is not False:
            raise ValueError("report is not in copy-only staged state")
        if not named_human(reviewer):
            raise PermissionError("named human reviewer required")
        released = copy.deepcopy(report)
        released["state"] = "RELEASED_BY_NAMED_HUMAN"
        released["reviewer"] = reviewer.strip()
        released["sent"] = False
        return released

    def automatic_release(self, job_id: str) -> Dict[str, Any]:
        raise PermissionError("automatic release is disabled")


def expand_fixture_recipe(recipe: Mapping[str, Any]) -> List[Dict[str, Any]]:
    if recipe.get("contract_id") != "socotec-cmt-network-federation-lims-01":
        raise ValueError("unexpected fixture contract_id")
    if recipe.get("namespace_count") != 25 or recipe.get("valid_count") != 400:
        raise ValueError("unexpected fixture dimensions")
    hold_plan = recipe.get("hold_plan")
    if hold_plan != {
        "SCOPE_MISMATCH": 17,
        "METHOD_VERSION_MISMATCH": 17,
        "EQUIPMENT_UNAVAILABLE": 17,
        "QUALIFICATION_INVALID": 17,
        "CAPACITY_EXCEEDED": 16,
        "DUPLICATE_JOB_ID": 16,
    }:
        raise ValueError("unexpected hold plan")
    registry = build_registry()
    jobs: List[Dict[str, Any]] = []
    for index in range(400):
        lab = (index % 25) + 1
        service_code = f"CMT-SVC-{lab:02d}"
        route = registry[service_code]
        job_id = f"SOCJOB-{index + 1:04d}"
        submission_id = f"SOCSUB-{index + 1:04d}"
        destination = route["namespace"]
        if index % int(recipe.get("authorized_transfer_every", 5)) == 0:
            predecessor = 25 if lab == 1 else lab - 1
            origin = f"SOC-{predecessor:02d}"
        else:
            origin = destination
        legacy = {
            "job_id": job_id,
            "legacy_system": route["legacy_system"],
            "service_code": service_code,
            "method_code": route["method_code"],
            "method_version": route["method_version"],
            "source_namespace": origin,
        }
        job: Dict[str, Any] = {
            "submission_id": submission_id,
            "job_id": job_id,
            "service_code": service_code,
            "origin_namespace": origin,
            "scope_id": route["scope_id"],
            "method_code": route["method_code"],
            "method_version": route["method_version"],
            "equipment_id": route["equipment_id"],
            "personnel_id": route["personnel_id"],
            "qualification_id": route["qualification_id"],
            "capacity_position": (index // 25) + 1,
            "legacy_payload": legacy,
            "legacy_payload_sha256": legacy_payload_digest(legacy),
            "expected_route_namespace": destination,
            "expected_state": "READY",
            "expected_code": "READY",
        }
        if origin != destination:
            job["transfer_ticket"] = expected_transfer_ticket(origin, destination, job_id)
        jobs.append(job)

    index = 400
    ordered_plan = [
        ("SCOPE_MISMATCH", 17),
        ("METHOD_VERSION_MISMATCH", 17),
        ("EQUIPMENT_UNAVAILABLE", 17),
        ("QUALIFICATION_INVALID", 17),
        ("CAPACITY_EXCEEDED", 16),
        ("DUPLICATE_JOB_ID", 16),
    ]
    for code, count in ordered_plan:
        for _ in range(count):
            base_index = (index - 400) % 400
            lab = (index % 25) + 1
            service_code = f"CMT-SVC-{lab:02d}"
            route = registry[service_code]
            submission_id = f"SOCSUB-{index + 1:04d}"
            job_id = f"SOCJOB-{index + 1:04d}"
            if code == "DUPLICATE_JOB_ID":
                job_id = f"SOCJOB-{base_index + 1:04d}"
            destination = route["namespace"]
            origin = destination
            legacy = {
                "job_id": job_id,
                "legacy_system": route["legacy_system"],
                "service_code": service_code,
                "method_code": route["method_code"],
                "method_version": route["method_version"],
                "source_namespace": origin,
            }
            job = {
                "submission_id": submission_id,
                "job_id": job_id,
                "service_code": service_code,
                "origin_namespace": origin,
                "scope_id": route["scope_id"],
                "method_code": route["method_code"],
                "method_version": route["method_version"],
                "equipment_id": route["equipment_id"],
                "personnel_id": route["personnel_id"],
                "qualification_id": route["qualification_id"],
                "capacity_position": (index // 25) + 1,
                "legacy_payload": legacy,
                "legacy_payload_sha256": legacy_payload_digest(legacy),
                "expected_route_namespace": destination,
                "expected_state": "HOLD",
                "expected_code": code,
            }
            if code == "SCOPE_MISMATCH":
                job["scope_id"] = "SCOPE-OUTSIDE-CONTRACT"
            elif code == "METHOD_VERSION_MISMATCH":
                job["method_version"] = "2025.STALE"
            elif code == "EQUIPMENT_UNAVAILABLE":
                job["equipment_id"] = "EQ-UNAVAILABLE"
            elif code == "QUALIFICATION_INVALID":
                job["qualification_id"] = "QUAL-EXPIRED"
            elif code == "CAPACITY_EXCEEDED":
                job["capacity_position"] = 41
            jobs.append(job)
            index += 1
    return jobs


def load_fixture(path: Path) -> List[Dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, list):
        return value
    if isinstance(value, Mapping):
        return expand_fixture_recipe(value)
    raise ValueError("fixture must be a JSON list or deterministic recipe object")


def verify_manifest(fixture_path: Path, manifest_path: Path) -> Dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw = fixture_path.read_bytes()
    if sha256_bytes(raw) != manifest["fixture_sha256"]:
        raise ValueError("fixture SHA-256 mismatch")
    contract = dict(manifest)
    expected_manifest_digest = contract.pop("manifest_sha256")
    if sha256_text(canonical_json(contract)) != expected_manifest_digest:
        raise ValueError("manifest digest mismatch")
    return manifest


def summarize(results: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    hold_codes: Dict[str, int] = {}
    for result in results:
        state = str(result["state"])
        counts[state] = counts.get(state, 0) + 1
        if state == "HOLD":
            code = str(result["code"])
            hold_codes[code] = hold_codes.get(code, 0) + 1
    return {"states": counts, "hold_codes": dict(sorted(hold_codes.items()))}


def cli(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synthetic/read-only SOCOTEC CMT network federation acceptance runner")
    parser.add_argument("fixture", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args(argv)
    manifest = verify_manifest(args.fixture, args.manifest)
    jobs = load_fixture(args.fixture)
    expanded_fixture_sha256 = sha256_text(canonical_json(jobs))
    federation = SocotecCmtFederation()
    first = federation.process_many(jobs)
    first_summary = summarize(first)
    before_replay = federation.state.digest()
    replay = federation.process_many(jobs)
    after_replay = federation.state.digest()
    replay_summary = summarize(replay)
    ok = (
        len(jobs) == manifest["fixture_count"] == 500
        and expanded_fixture_sha256 == manifest["expanded_fixture_sha256"]
        and first_summary["states"] == {"READY": 400, "HOLD": 100}
        and first_summary["hold_codes"] == manifest["expected_hold_codes"]
        and len(federation.state.accessions) == 400
        and len(federation.state.staged_reports) == 400
        and all(item["transfer_authorized"] for item in federation.state.accessions)
        and replay_summary["states"] == {"IDEMPOTENT": 500}
        and before_replay == after_replay == manifest["expected_audit_sha256"]
    )
    print(canonical_json({
        "ok": ok,
        "fixture_count": len(jobs),
        "first": first_summary,
        "replay": replay_summary,
        "accessions": len(federation.state.accessions),
        "reports_staged": len(federation.state.staged_reports),
        "audit_sha256": after_replay,
        "fixture_sha256": manifest["fixture_sha256"],
        "expanded_fixture_sha256": expanded_fixture_sha256,
        "manifest_sha256": manifest["manifest_sha256"],
    }))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(cli())
