#!/usr/bin/env python3
"""Synthetic evidence-lineage ledger for the American Injectables build demand."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "americaninj-lineage-v1"
FIXTURE_SCHEMA = "americaninj-fixture-spec-v1"
INTAKE_HOLDS = {
    "DUPLICATE_PROGRAM_BATCH_ID",
    "CONTAINER_LINE_MISMATCH",
    "MISSING_FORMULATION_OR_METHOD_VERSION",
}
POST_INTAKE_HOLDS = {"IPC_FILL_FAILURE", "STERILITY_QC_FAILURE"}
BANNED_RELEASE_ACTORS = {"agent", "automation", "system", "bot", "autonomous", "auto", "ai", "service"}


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(value: Any) -> str:
    text = value if isinstance(value, str) else canonical(value)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def evidence_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "sponsor_program", "formulation_version", "method_version", "batch_id",
        "material_lot", "container_format", "capability_route", "result_value",
        "result_unit", "source_id",
    )
    return {key: record.get(key, "") for key in keys}


def evidence_sha256(record: Mapping[str, Any]) -> str:
    return sha256(evidence_payload(record))


def record_sha256(record: Mapping[str, Any]) -> str:
    return sha256(dict(record))


def _blank() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "submissions": {}, "program_batch_seen": {}, "jobs": {},
        "dossiers": {}, "events": [],
    }


def _read_ledger(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _blank()
    ledger = json.loads(path.read_text(encoding="utf-8"))
    if ledger.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("ledger schema mismatch")
    return ledger


def _write_ledger(path: Path, ledger: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(ledger, indent=2, sort_keys=True) + "\n"
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def _event(ledger: dict[str, Any], sid: str, name: str, **extra: Any) -> None:
    item = {"ordinal": len(ledger["events"]) + 1, "submission_id": sid, "event": name}
    item.update(extra)
    ledger["events"].append(item)


def _outcome(record: Mapping[str, Any], status: str, hold_code: str | None, scheduled: bool) -> dict[str, Any]:
    return {
        "submission_id": record["submission_id"], "status": status,
        "hold_code": hold_code, "scheduled": scheduled,
        "dossier_state": "STAGED_HUMAN_REVIEW" if status == "READY" else None,
        "lineage_sha256": evidence_sha256(record),
        "record_sha256": record_sha256(record),
    }


def _validate(record: Mapping[str, Any]) -> None:
    required = {
        "submission_id", "program_id", "sponsor_program", "batch_id", "material_lot",
        "container_format", "line_capabilities", "capability_route", "formulation_version",
        "method_version", "ipc_fill_pass", "sterility_qc_pass", "result_value",
        "result_unit", "source_id", "source_sha256",
    }
    missing = required - set(record)
    if missing:
        raise ValueError("record missing keys: " + ",".join(sorted(missing)))
    if evidence_sha256(record) != record["source_sha256"]:
        raise ValueError(f"source hash mismatch for {record['submission_id']}")


def summarize_ledger(ledger: Mapping[str, Any]) -> dict[str, Any]:
    submissions = ledger["submissions"]
    holds = Counter(v["hold_code"] for v in submissions.values() if v["status"] == "HOLD")
    return {
        "processed_records": len(submissions),
        "ready": sum(v["status"] == "READY" for v in submissions.values()),
        "hold": sum(v["status"] == "HOLD" for v in submissions.values()),
        "hold_codes": dict(sorted(holds.items())),
        "scheduled_jobs": len(ledger["jobs"]),
        "staged_or_released_dossiers": len(ledger["dossiers"]),
        "events": len(ledger["events"]),
    }


def process_records(records: Iterable[Mapping[str, Any]], ledger_path: os.PathLike[str] | str) -> dict[str, Any]:
    batch = [dict(record) for record in records]
    for record in batch:
        _validate(record)

    path = Path(ledger_path)
    ledger = _read_ledger(path)
    before = canonical(ledger)
    ready = hold = scheduled_jobs = staged = replayed = 0
    hold_codes: Counter[str] = Counter()

    for record in batch:
        sid = str(record["submission_id"])
        incoming_record_sha256 = record_sha256(record)
        if sid in ledger["submissions"]:
            if ledger["submissions"][sid].get("record_sha256") != incoming_record_sha256:
                raise ValueError(f"submission replay payload mismatch for {sid}")
            replayed += 1
            continue

        identity = f"{record['program_id']}|{record['batch_id']}"
        scheduled = False
        code: str | None = None
        if identity in ledger["program_batch_seen"]:
            code = "DUPLICATE_PROGRAM_BATCH_ID"
        else:
            ledger["program_batch_seen"][identity] = sid
            if record["container_format"] not in set(record["line_capabilities"]):
                code = "CONTAINER_LINE_MISMATCH"
            elif not record.get("formulation_version") or not record.get("method_version"):
                code = "MISSING_FORMULATION_OR_METHOD_VERSION"
            else:
                scheduled = True
                scheduled_jobs += 1
                job_id = f"JOB-{sid}"
                ledger["jobs"][sid] = {
                    "job_id": job_id, "submission_id": sid,
                    "capability_route": record["capability_route"],
                    "container_format": record["container_format"],
                    "method_version": record["method_version"],
                }
                _event(ledger, sid, "JOB_SCHEDULED", job_id=job_id)
                if not record["ipc_fill_pass"]:
                    code = "IPC_FILL_FAILURE"
                elif not record["sterility_qc_pass"]:
                    code = "STERILITY_QC_FAILURE"

        if code is not None:
            result = _outcome(record, "HOLD", code, scheduled)
            hold += 1
            hold_codes[code] += 1
            _event(ledger, sid, "HOLD", hold_code=code, scheduled=scheduled)
        else:
            result = _outcome(record, "READY", None, True)
            ready += 1
            staged += 1
            dossier_id = f"DOSSIER-{sid}"
            ledger["dossiers"][sid] = {
                "dossier_id": dossier_id, "submission_id": sid,
                "state": "STAGED_HUMAN_REVIEW", "released_by": None,
                "lineage": evidence_payload(record),
                "lineage_sha256": evidence_sha256(record),
            }
            _event(ledger, sid, "DOSSIER_STAGED", dossier_id=dossier_id)
            _event(ledger, sid, "READY", lineage_sha256=result["lineage_sha256"])
        ledger["submissions"][sid] = result

    if canonical(ledger) != before:
        _write_ledger(path, ledger)
    return {
        "schema_version": SCHEMA_VERSION, "input_records": len(batch),
        "new_records": ready + hold, "replayed": replayed,
        "delta": {
            "ready": ready, "hold": hold, "scheduled_jobs": scheduled_jobs,
            "staged_dossiers": staged, "hold_codes": dict(sorted(hold_codes.items())),
        },
        "totals": summarize_ledger(ledger),
    }


def release_dossier(submission_id: str, ledger_path: os.PathLike[str] | str, *, human_name: str, named_human: bool) -> dict[str, Any]:
    path = Path(ledger_path)
    ledger = _read_ledger(path)
    result = ledger["submissions"].get(submission_id)
    if result is None:
        raise KeyError(submission_id)
    if result["status"] != "READY":
        raise ValueError("held submissions cannot release a dossier")
    dossier = ledger["dossiers"][submission_id]
    if not isinstance(human_name, str):
        raise PermissionError("release requires an explicit named human")
    name = " ".join(human_name.strip().split())
    lowered = name.casefold()
    compact = "".join(ch for ch in lowered if ch.isalnum())
    tokens = "".join(ch if ch.isalnum() else " " for ch in lowered).split()
    reserved = compact in BANNED_RELEASE_ACTORS or any(token in BANNED_RELEASE_ACTORS for token in tokens)
    if named_human is not True or len(name) < 2 or reserved:
        raise PermissionError("release requires an explicit named human")
    if dossier["state"] == "RELEASED":
        if dossier["released_by"] != name:
            raise ValueError("dossier already released by another named human")
        return dict(dossier)
    dossier["state"], dossier["released_by"] = "RELEASED", name
    result["dossier_state"] = "RELEASED"
    _event(ledger, submission_id, "DOSSIER_RELEASED", human_name=name)
    _write_ledger(path, ledger)
    return dict(dossier)


def _synthetic(index: int, kind: str, duplicate_of: int | None = None) -> dict[str, Any]:
    base = index if duplicate_of is None else duplicate_of
    container = "VIAL" if base % 2 == 0 else "SYRINGE"
    record: dict[str, Any] = {
        "submission_id": f"SUB-{index:03d}", "program_id": f"PRG-{base:03d}",
        "sponsor_program": f"SYNTH-PROGRAM-{base:03d}", "batch_id": f"BATCH-{base:03d}",
        "material_lot": f"MAT-{index:03d}", "container_format": container,
        "line_capabilities": [container],
        "capability_route": "SYNTH-VIAL-LINE" if container == "VIAL" else "SYNTH-SYRINGE-LINE",
        "formulation_version": f"FORM-v{base % 3 + 1}", "method_version": f"METHOD-v{base % 4 + 1}",
        "ipc_fill_pass": True, "sterility_qc_pass": True,
        "result_value": str(1000 + index), "result_unit": "arb_unit",
        "source_id": f"synthetic-source-{index:03d}",
    }
    if kind == "CONTAINER_LINE_MISMATCH":
        record["line_capabilities"] = ["SYRINGE" if container == "VIAL" else "VIAL"]
    elif kind == "MISSING_FORMULATION_OR_METHOD_VERSION":
        record["method_version"] = ""
    elif kind == "IPC_FILL_FAILURE":
        record["ipc_fill_pass"] = False
    elif kind == "STERILITY_QC_FAILURE":
        record["sterility_qc_pass"] = False
    elif kind not in {"READY", "DUPLICATE_PROGRAM_BATCH_ID"}:
        raise ValueError(f"unknown fixture cohort: {kind}")
    record["source_sha256"] = evidence_sha256(record)
    return record


def load_fixture(path: os.PathLike[str] | str) -> list[dict[str, Any]]:
    spec = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(spec, list):
        return [dict(item) for item in spec]
    if not isinstance(spec, dict) or spec.get("schema_version") != FIXTURE_SCHEMA:
        raise ValueError("fixture spec schema mismatch")
    records: list[dict[str, Any]] = []
    index = 0
    for cohort in spec.get("cohorts", []):
        start = cohort.get("duplicate_of_start")
        for offset in range(int(cohort["count"])):
            duplicate_of = None if start is None else int(start) + offset
            records.append(_synthetic(index, str(cohort["kind"]), duplicate_of))
            index += 1
    if index != int(spec.get("records", index)):
        raise ValueError("fixture record count mismatch")
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Process synthetic American Injectables lineage records")
    parser.add_argument("fixture")
    parser.add_argument("--ledger", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(process_records(load_fixture(args.fixture), args.ledger), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
