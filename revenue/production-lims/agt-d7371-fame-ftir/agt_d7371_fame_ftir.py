from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

CONTRACT_ID = "agt-d7371-fame-ftir-lims-01"
METHOD_CODE = "ASTM D7371"
METHOD_VERSION = "SYNTHETIC-2026.1"
UNITS = "% v/v"
ROUNDING_DECIMALS = 1
SYNTHETIC_FAME_MAX_VV = 5.0
QC_STANDARD_ID = "AGT-SYN-QC-FAME-3P0"
QC_TARGET_VV = 3.0
QC_RECOVERY_MIN = 98.0
QC_RECOVERY_MAX = 102.0
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


def source_digest(record: Mapping[str, Any]) -> str:
    return sha256_text(canonical_json(record))


def named_human(value: str) -> bool:
    if not isinstance(value, str):
        return False
    tokens = re.findall(r"[A-Za-z]+", value)
    if len(tokens) < 2:
        return False
    folded = [token.casefold() for token in tokens]
    if any(token in RESERVED_ACTOR_TOKENS for token in folded):
        return False
    return all(len(token) >= 2 for token in tokens)


def expected_ftir_payload(sample_id: str, raw_fame_vv: float, qc_recovery_pct: float) -> str:
    return (
        f"AGT-SYNTHETIC-FTIR|sample={sample_id}|method={METHOD_CODE}|"
        f"version={METHOD_VERSION}|raw_fame_vv={raw_fame_vv:.4f}|"
        f"qc_standard={QC_STANDARD_ID}|qc_recovery_pct={qc_recovery_pct:.3f}"
    )


def rounded_fame(raw_fame_vv: float) -> float:
    return round(float(raw_fame_vv) + 1e-12, ROUNDING_DECIMALS)


@dataclass
class AgTState:
    processed_submissions: Dict[str, str] = field(default_factory=dict)
    accession_by_sample: Dict[str, str] = field(default_factory=dict)
    accessions: List[Dict[str, Any]] = field(default_factory=list)
    staged_reports: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    holds: List[Dict[str, Any]] = field(default_factory=list)
    events: List[Dict[str, Any]] = field(default_factory=list)

    def digest(self) -> str:
        return sha256_text(canonical_json({
            "processed_submissions": self.processed_submissions,
            "accession_by_sample": self.accession_by_sample,
            "accessions": self.accessions,
            "staged_reports": self.staged_reports,
            "holds": self.holds,
            "events": self.events,
        }))

    def accession_digest(self) -> str:
        return sha256_text(canonical_json(self.accessions))

    def report_digest(self) -> str:
        ordered = [self.staged_reports[key] for key in sorted(self.staged_reports)]
        return sha256_text(canonical_json(ordered))


class AgTD7371Lane:
    """Synthetic/deidentified D7371-style intake/QC/staged-release acceptance lane.

    This harness deliberately has no production adapter and makes no petroleum
    conformance, compliance, or release determination.
    """

    def __init__(self) -> None:
        self.state = AgTState()

    def _result(
        self,
        record: Mapping[str, Any],
        state: str,
        code: str,
        *,
        idempotent: bool = False,
    ) -> Dict[str, Any]:
        return {
            "submission_id": record.get("submission_id"),
            "sample_id": record.get("sample_id"),
            "state": state,
            "code": code,
            "idempotent": idempotent,
        }

    def _hold(self, record: Mapping[str, Any], code: str) -> Dict[str, Any]:
        item = {
            "submission_id": record["submission_id"],
            "sample_id": record["sample_id"],
            "code": code,
        }
        self.state.holds.append(item)
        self.state.events.append({"type": "HOLD", **item})
        return self._result(record, "HOLD", code)

    def process(self, record: Mapping[str, Any]) -> Dict[str, Any]:
        required = {
            "submission_id", "sample_id", "collector_name", "collection_date",
            "seal_id", "container_id", "method_code", "method_version",
            "units", "rounding_decimals", "ftir_filename", "ftir_payload",
            "ftir_sha256", "raw_fame_vv", "reported_fame_vv",
            "qc_standard_id", "qc_target_vv", "qc_recovery_pct",
        }
        if not isinstance(record, Mapping) or any(key not in record for key in required):
            raise ValueError("record is missing required AGT fields")
        submission_id = record["submission_id"]
        sample_id = record["sample_id"]
        if not isinstance(submission_id, str) or not submission_id.strip():
            raise ValueError("submission_id must be a nonblank string")
        if not isinstance(sample_id, str) or not sample_id.strip():
            raise ValueError("sample_id must be a nonblank string")

        digest = source_digest(record)
        prior = self.state.processed_submissions.get(submission_id)
        if prior is not None:
            if prior != digest:
                return self._result(record, "HOLD", "REPLAY_PAYLOAD_CONFLICT")
            return self._result(record, "IDEMPOTENT", "IDEMPOTENT_REPLAY", idempotent=True)

        # Convert values that can raise only after replay classification, but still
        # before binding first-seen state. This preserves replay conflict precedence.
        try:
            qc_target_vv = float(record["qc_target_vv"])
        except (TypeError, ValueError) as exc:
            raise ValueError("qc_target_vv must be numeric") from exc

        # Bind first-seen content even for held submissions so exact replay is zero-add.
        self.state.processed_submissions[submission_id] = digest

        custody_fields = ("collector_name", "collection_date", "seal_id", "container_id")
        if any(not isinstance(record[key], str) or not record[key].strip() for key in custody_fields):
            return self._hold(record, "INCOMPLETE_CUSTODY")

        if record["method_code"] != METHOD_CODE or record["method_version"] != METHOD_VERSION:
            return self._hold(record, "METHOD_BINDING_MISMATCH")
        if record["units"] != UNITS or record["rounding_decimals"] != ROUNDING_DECIMALS:
            return self._hold(record, "RESULT_FORMAT_MISMATCH")

        if sample_id in self.state.accession_by_sample:
            return self._hold(record, "DUPLICATE_SAMPLE_ID")

        if not isinstance(record["raw_fame_vv"], (int, float)) or isinstance(record["raw_fame_vv"], bool):
            return self._hold(record, "RESULT_FORMAT_MISMATCH")
        if not isinstance(record["reported_fame_vv"], (int, float)) or isinstance(record["reported_fame_vv"], bool):
            return self._hold(record, "RESULT_FORMAT_MISMATCH")
        if rounded_fame(record["raw_fame_vv"]) != float(record["reported_fame_vv"]):
            return self._hold(record, "RESULT_FORMAT_MISMATCH")

        if record["qc_standard_id"] != QC_STANDARD_ID or qc_target_vv != QC_TARGET_VV:
            return self._hold(record, "QC_MISMATCH")
        if not isinstance(record["qc_recovery_pct"], (int, float)) or isinstance(record["qc_recovery_pct"], bool):
            return self._hold(record, "QC_MISMATCH")
        if not (QC_RECOVERY_MIN <= float(record["qc_recovery_pct"]) <= QC_RECOVERY_MAX):
            return self._hold(record, "QC_MISMATCH")

        payload = expected_ftir_payload(
            sample_id,
            float(record["raw_fame_vv"]),
            float(record["qc_recovery_pct"]),
        )
        if record["ftir_payload"] != payload:
            return self._hold(record, "FTIR_SOURCE_MISMATCH")
        if record["ftir_filename"] != f"{sample_id}.spc.synthetic.txt":
            return self._hold(record, "FTIR_SOURCE_MISMATCH")
        if sha256_text(payload) != record["ftir_sha256"]:
            return self._hold(record, "FTIR_SOURCE_MISMATCH")

        # This is a synthetic acceptance envelope only, not a real product specification.
        if float(record["reported_fame_vv"]) > SYNTHETIC_FAME_MAX_VV:
            return self._hold(record, "OOS_FAME")

        accession = {
            "sample_id": sample_id,
            "accession_id": f"AGT-ACC-{sample_id}",
            "method_code": METHOD_CODE,
            "method_version": METHOD_VERSION,
            "units": UNITS,
            "rounding_decimals": ROUNDING_DECIMALS,
            "reported_fame_vv": float(record["reported_fame_vv"]),
            "qc_standard_id": QC_STANDARD_ID,
            "qc_target_vv": QC_TARGET_VV,
            "qc_recovery_pct": float(record["qc_recovery_pct"]),
            "ftir_filename": record["ftir_filename"],
            "ftir_sha256": record["ftir_sha256"],
            "source_sha256": digest,
        }
        report = {
            "sample_id": sample_id,
            "state": "STAGED_HUMAN_REVIEW",
            "sent": False,
            "reported_fame_vv": float(record["reported_fame_vv"]),
            "units": UNITS,
            "method_code": METHOD_CODE,
            "method_version": METHOD_VERSION,
            "source_sha256": digest,
            "ftir_sha256": record["ftir_sha256"],
        }
        self.state.accession_by_sample[sample_id] = submission_id
        self.state.accessions.append(accession)
        self.state.staged_reports[sample_id] = report
        self.state.events.append({
            "type": "READY",
            "submission_id": submission_id,
            "sample_id": sample_id,
            "source_sha256": digest,
            "ftir_sha256": record["ftir_sha256"],
        })
        return self._result(record, "READY", "READY")

    def process_many(self, records: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        return [self.process(record) for record in records]

    def release_report(self, sample_id: str, reviewer: str) -> Dict[str, Any]:
        report = self.state.staged_reports.get(sample_id)
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

    def automatic_release(self, sample_id: str) -> Dict[str, Any]:
        raise PermissionError("automatic release is disabled")


def expand_fixture_recipe(recipe: Mapping[str, Any]) -> List[Dict[str, Any]]:
    if recipe.get("contract_id") != CONTRACT_ID:
        raise ValueError("unexpected contract_id")
    if recipe.get("valid_count") != 80:
        raise ValueError("unexpected valid_count")
    if recipe.get("hold_plan") != {
        "INCOMPLETE_CUSTODY": 10,
        "DUPLICATE_SAMPLE_ID": 5,
        "OOS_FAME": 5,
    }:
        raise ValueError("unexpected hold plan")

    records: List[Dict[str, Any]] = []

    def make_record(index: int, sample_id: str, raw: float) -> Dict[str, Any]:
        recovery = 99.0 + ((index % 7) * 0.5)
        payload = expected_ftir_payload(sample_id, raw, recovery)
        return {
            "submission_id": f"AGT-SUB-{index + 1:03d}",
            "sample_id": sample_id,
            "collector_name": f"Synthetic Collector {(index % 8) + 1}",
            "collection_date": f"2026-09-{(index % 8) + 1:02d}",
            "seal_id": f"SEAL-{index + 1:03d}",
            "container_id": f"CONT-{index + 1:03d}",
            "method_code": METHOD_CODE,
            "method_version": METHOD_VERSION,
            "units": UNITS,
            "rounding_decimals": ROUNDING_DECIMALS,
            "ftir_filename": f"{sample_id}.spc.synthetic.txt",
            "ftir_payload": payload,
            "ftir_sha256": sha256_text(payload),
            "raw_fame_vv": raw,
            "reported_fame_vv": rounded_fame(raw),
            "qc_standard_id": QC_STANDARD_ID,
            "qc_target_vv": QC_TARGET_VV,
            "qc_recovery_pct": recovery,
            "expected_state": "READY",
            "expected_code": "READY",
        }

    for index in range(80):
        raw = 1.0 + ((index % 35) * 0.1) + ((index % 3) * 0.01)
        records.append(make_record(index, f"AGT-SAMPLE-{index + 1:03d}", raw))

    # 10 incomplete custody records.
    for offset in range(10):
        index = 80 + offset
        record = make_record(index, f"AGT-SAMPLE-{index + 1:03d}", 2.2 + offset * 0.03)
        field = ("collector_name", "collection_date", "seal_id", "container_id")[offset % 4]
        record[field] = ""
        record["expected_state"] = "HOLD"
        record["expected_code"] = "INCOMPLETE_CUSTODY"
        records.append(record)

    # 5 duplicate sample IDs; duplicate only the identity, not submission ID.
    for offset in range(5):
        index = 90 + offset
        duplicate_sample_id = f"AGT-SAMPLE-{offset + 1:03d}"
        record = make_record(index, duplicate_sample_id, 2.5 + offset * 0.04)
        record["expected_state"] = "HOLD"
        record["expected_code"] = "DUPLICATE_SAMPLE_ID"
        records.append(record)

    # 5 synthetic OOS FAME results.
    for offset in range(5):
        index = 95 + offset
        raw = 5.6 + offset * 0.2
        record = make_record(index, f"AGT-SAMPLE-{index + 1:03d}", raw)
        record["expected_state"] = "HOLD"
        record["expected_code"] = "OOS_FAME"
        records.append(record)

    return records


def load_fixture(path: Path) -> List[Dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, list):
        return value
    if isinstance(value, Mapping):
        return expand_fixture_recipe(value)
    raise ValueError("fixture must be a JSON list or deterministic recipe")


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
    parser = argparse.ArgumentParser(description="Synthetic/read-only AGT D7371 FAME FTIR acceptance lane")
    parser.add_argument("fixture", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args(argv)

    manifest = verify_manifest(args.fixture, args.manifest)
    records = load_fixture(args.fixture)
    expanded_fixture_sha256 = sha256_text(canonical_json(records))

    lane = AgTD7371Lane()
    first = lane.process_many(records)
    first_summary = summarize(first)
    before = lane.state.digest()
    counts_before = (
        len(lane.state.accessions), len(lane.state.holds),
        len(lane.state.events), len(lane.state.staged_reports),
    )
    replay = lane.process_many(records)
    after = lane.state.digest()
    counts_after = (
        len(lane.state.accessions), len(lane.state.holds),
        len(lane.state.events), len(lane.state.staged_reports),
    )
    replay_summary = summarize(replay)

    ok = (
        len(records) == manifest["fixture_count"] == 100
        and expanded_fixture_sha256 == manifest["expanded_fixture_sha256"]
        and first_summary["states"] == {"READY": 80, "HOLD": 20}
        and first_summary["hold_codes"] == manifest["expected_hold_codes"]
        and len(lane.state.accessions) == 80
        and len({item["sample_id"] for item in lane.state.accessions}) == 80
        and len(lane.state.staged_reports) == 80
        and replay_summary["states"] == {"IDEMPOTENT": 100}
        and counts_before == counts_after
        and lane.state.accession_digest() == manifest["expected_accession_sha256"]
        and lane.state.report_digest() == manifest["expected_report_sha256"]
        and before == after == manifest["expected_audit_sha256"]
    )
    print(canonical_json({
        "ok": ok,
        "fixture_count": len(records),
        "first": first_summary,
        "replay": replay_summary,
        "accessions": len(lane.state.accessions),
        "reports_staged": len(lane.state.staged_reports),
        "fixture_sha256": manifest["fixture_sha256"],
        "expanded_fixture_sha256": expanded_fixture_sha256,
        "accession_sha256": lane.state.accession_digest(),
        "report_sha256": lane.state.report_digest(),
        "audit_sha256": after,
        "manifest_sha256": manifest["manifest_sha256"],
    }))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(cli())
