#!/usr/bin/env python3
"""Synthetic/read-only BA Sciences multi-site stability intake shadow."""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

DEMAND_ID = "basciences-multisite-stability-intake-lims-01"
FIXTURE_VERSION = "basciences-multisite-stability-intake-v1"
FIXTURE_SCHEMA = "deterministic-generator-v1"
MANIFEST_PREFIX = "BASCIENCES-MULTISITE-STABILITY-SYNTHETIC-MANIFEST-V1\n"
HOLD_CODES = (
    "EXPIRED_QUOTE",
    "QUOTE_PO_CONFLICT",
    "MISSING_CONTROLLED_OR_STORAGE_DATA",
    "ABSENT_SPECIFICATION",
    "AMBIGUOUS_RESULT_MAPPING",
    "INCORRECT_STABILITY_TOTALS",
)
ROUTES: dict[str, dict[str, Any]] = {
    "MICRO": {"site_id": "SYN-BA-SITE-A", "method_id": "SYN-MICRO-PANEL-V1", "result_count": 2},
    "CHEMISTRY": {"site_id": "SYN-BA-SITE-B", "method_id": "SYN-CHEM-PANEL-V1", "result_count": 3},
    "WATER": {"site_id": "SYN-BA-SITE-C", "method_id": "SYN-WATER-PANEL-V1", "result_count": 2},
    "STABILITY": {"site_id": "SYN-BA-SITE-A", "method_id": "SYN-STABILITY-PANEL-V1", "result_count": 4},
}
PULL_OFFSETS_DAYS = (0, 30, 90, 180)
STABILITY_UNITS_PER_PULL = 2
RESERVED_ACTORS = {
    "auto", "automatic", "automation", "bot", "system", "service", "agent", "scheduler",
    "worker", "pipeline", "anonymous", "unknown", "workflow", "assistant", "account", "ai",
}
FORBIDDEN_KEYS = {
    "patient", "patient_name", "dob", "mrn", "diagnosis", "ssn", "password", "secret",
    "token", "api_key", "customer_name", "email", "phone", "substance_name",
}

class IntegrityError(ValueError):
    pass


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(value: Any) -> str:
    if isinstance(value, bytes):
        payload = value
    elif isinstance(value, str):
        payload = value.encode("utf-8")
    else:
        payload = _canon(value).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _manifest_envelope(manifest: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "demand_id", "fixture_version", "dataset_sha256", "expanded_records_sha256",
        "record_count", "expected_ready", "expected_hold", "expected_hold_codes",
        "routes", "pull_offsets_days", "stability_units_per_pull",
    )
    return {key: manifest[key] for key in keys}


def verify_manifest_signature(manifest: Mapping[str, Any]) -> None:
    if manifest.get("signature_alg") != "sha256-content-envelope-v1":
        raise IntegrityError("manifest signature algorithm mismatch")
    expected = sha256_hex(MANIFEST_PREFIX + _canon(_manifest_envelope(manifest)))
    if manifest.get("signature") != expected:
        raise IntegrityError("manifest signature mismatch")


def _truth_map(payload: Mapping[str, Any]) -> dict[int, str]:
    if payload.get("schema") != FIXTURE_SCHEMA or payload.get("fixture_version") != FIXTURE_VERSION:
        raise IntegrityError("fixture schema/version mismatch")
    generator = payload.get("generator")
    if not isinstance(generator, dict):
        raise IntegrityError("fixture generator missing")
    if (generator.get("record_count"), generator.get("ready_count")) != (220, 180):
        raise IntegrityError("fixture generator dimensions mismatch")
    truth: dict[int, str] = {}
    for segment in generator.get("hold_segments", []):
        if not isinstance(segment, dict):
            raise IntegrityError("invalid hold segment")
        code, start, count = segment.get("code"), segment.get("start"), segment.get("count")
        if code not in HOLD_CODES or not isinstance(start, int) or isinstance(start, bool) or not isinstance(count, int) or isinstance(count, bool):
            raise IntegrityError("invalid hold segment")
        for index in range(start, start + count):
            if index in truth or not 181 <= index <= 220:
                raise IntegrityError("overlapping/out-of-range hold segment")
            truth[index] = code
    if set(truth) != set(range(181, 221)):
        raise IntegrityError("hold segments must cover 181..220")
    return truth


def _add_days(date_text: str, days: int) -> str:
    return (dt.date.fromisoformat(date_text) + dt.timedelta(days=days)).isoformat()


def _document_core(index: int, truth: str | None) -> dict[str, Any]:
    form_type = tuple(ROUTES)[(index - 1) % len(ROUTES)]
    if truth == "INCORRECT_STABILITY_TOTALS":
        form_type = "STABILITY"
    route = ROUTES[form_type]
    received_date = (dt.date(2026, 1, 5) + dt.timedelta(days=(index - 1) % 35)).isoformat()
    quote_id = f"Q-SYN-{index:04d}"
    po_quote_id = quote_id
    quote_expires = _add_days(received_date, 30)
    specification_id = f"SPEC-SYN-{((index - 1) % 12) + 1:02d}"
    controlled_sample = index % 9 == 0
    controlled_handling_complete = True
    storage_condition = "SYN-ROOM" if form_type != "STABILITY" else "SYN-STABILITY-25C"
    mapping_unique = True
    expected_stability_total = len(PULL_OFFSETS_DAYS) * STABILITY_UNITS_PER_PULL if form_type == "STABILITY" else 0
    stability_total = expected_stability_total
    if truth == "EXPIRED_QUOTE":
        quote_expires = _add_days(received_date, -1)
    elif truth == "QUOTE_PO_CONFLICT":
        po_quote_id = f"Q-SYN-CONFLICT-{index:04d}"
    elif truth == "MISSING_CONTROLLED_OR_STORAGE_DATA":
        if controlled_sample:
            controlled_handling_complete = False
        else:
            storage_condition = ""
    elif truth == "ABSENT_SPECIFICATION":
        specification_id = ""
    elif truth == "AMBIGUOUS_RESULT_MAPPING":
        mapping_unique = False
    elif truth == "INCORRECT_STABILITY_TOTALS":
        stability_total = expected_stability_total + 1
    return {
        "record_id": f"BA-INTAKE-{index:04d}",
        "synthetic": True,
        "deidentified": True,
        "form_type": form_type,
        "form_version": "SYN-2026.1",
        "quote_id": quote_id,
        "po_id": f"PO-SYN-{index:04d}",
        "po_quote_id": po_quote_id,
        "quote_expires": quote_expires,
        "received_date": received_date,
        "specification_id": specification_id,
        "controlled_sample": controlled_sample,
        "controlled_handling_complete": controlled_handling_complete,
        "storage_condition": storage_condition,
        "sample_line_id": f"LINE-{index:04d}-01",
        "mapping_unique": mapping_unique,
        "site_id": route["site_id"],
        "method_id": route["method_id"],
        "expected_result_count": route["result_count"],
        "stability_total": stability_total,
        "expected_stability_total": expected_stability_total,
        "truth_hold": truth,
    }


def _record(index: int, truth: str | None) -> dict[str, Any]:
    document = _document_core(index, truth)
    document_sha256 = sha256_hex(document)
    signature = sha256_hex("BA-SYNTHETIC-SIGNED-DOCUMENT-V1\n" + document_sha256)
    return {
        **document,
        "document_sha256": document_sha256,
        "document_signature": signature,
    }


def expand_fixture(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    truth = _truth_map(payload)
    return [_record(index, truth.get(index)) for index in range(1, 221)]


def _verify_record_signature(record: Mapping[str, Any]) -> None:
    core = dict(record)
    got_signature = core.pop("document_signature", None)
    got_document_sha = core.pop("document_sha256", None)
    expected_sha = sha256_hex(core)
    if got_document_sha != expected_sha:
        raise IntegrityError("document hash mismatch")
    if got_signature != sha256_hex("BA-SYNTHETIC-SIGNED-DOCUMENT-V1\n" + expected_sha):
        raise IntegrityError("document signature mismatch")


def verify_records(records: Sequence[Mapping[str, Any]], manifest: Mapping[str, Any]) -> None:
    verify_manifest_signature(manifest)
    if manifest.get("demand_id") != DEMAND_ID or len(records) != manifest.get("record_count"):
        raise IntegrityError("manifest/record mismatch")
    if manifest.get("routes") != ROUTES or tuple(manifest.get("pull_offsets_days", [])) != PULL_OFFSETS_DAYS:
        raise IntegrityError("manifest route/pull contract mismatch")
    if manifest.get("stability_units_per_pull") != STABILITY_UNITS_PER_PULL:
        raise IntegrityError("manifest stability units mismatch")
    if sha256_hex(list(records)) != manifest.get("expanded_records_sha256"):
        raise IntegrityError("expanded record hash mismatch")
    truth = Counter(record.get("truth_hold") for record in records if record.get("truth_hold"))
    if truth != Counter(manifest.get("expected_hold_codes", {})):
        raise IntegrityError("truth hold counts mismatch")
    if len(records) - sum(truth.values()) != manifest.get("expected_ready"):
        raise IntegrityError("ready count mismatch")
    if len({record.get("record_id") for record in records}) != len(records):
        raise IntegrityError("duplicate record_id")
    for record in records:
        if not record.get("synthetic") or not record.get("deidentified"):
            raise IntegrityError("fixture boundary")
        if {str(key).casefold() for key in record} & FORBIDDEN_KEYS:
            raise IntegrityError("forbidden sensitive-shaped field")
        _verify_record_signature(record)


def load_fixture(fixture_path: str | Path | None = None, manifest_path: str | Path | None = None):
    base = Path(__file__).resolve().parent / "fixtures"
    fixture = Path(fixture_path) if fixture_path else base / "basciences_220_intakes.json"
    manifest_file = Path(manifest_path) if manifest_path else base / "manifest.json"
    fixture_text = fixture.read_text(encoding="utf-8")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if sha256_hex(fixture_text) != manifest.get("dataset_sha256"):
        raise IntegrityError("fixture file hash mismatch")
    payload = json.loads(fixture_text)
    records = expand_fixture(payload)
    verify_records(records, manifest)
    return records, manifest


def _hold_code(record: Mapping[str, Any]) -> str | None:
    received = dt.date.fromisoformat(record["received_date"])
    expires = dt.date.fromisoformat(record["quote_expires"])
    if expires < received:
        return "EXPIRED_QUOTE"
    if record["po_quote_id"] != record["quote_id"]:
        return "QUOTE_PO_CONFLICT"
    if (record["controlled_sample"] and not record["controlled_handling_complete"]) or not record["storage_condition"]:
        return "MISSING_CONTROLLED_OR_STORAGE_DATA"
    if not record["specification_id"]:
        return "ABSENT_SPECIFICATION"
    if not record["mapping_unique"]:
        return "AMBIGUOUS_RESULT_MAPPING"
    if record["form_type"] == "STABILITY" and record["stability_total"] != record["expected_stability_total"]:
        return "INCORRECT_STABILITY_TOTALS"
    return None


def _prov(record: Mapping[str, Any], field: str, value: Any) -> dict[str, Any]:
    return {
        "value": value,
        "source_sha256": record["document_sha256"],
        "source_coordinate": f"form:{record['form_type']} field:{field}",
    }


def _normalized(record: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    fields = (
        "form_type", "quote_id", "po_id", "specification_id", "storage_condition",
        "sample_line_id", "site_id", "method_id", "expected_result_count",
    )
    return {field: _prov(record, field, record[field]) for field in fields}


def _pull_schedule(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    if record["form_type"] != "STABILITY":
        return []
    return [
        {
            "pull_index": index + 1,
            "offset_days": offset,
            "pull_date": _add_days(record["received_date"], offset),
            "units": STABILITY_UNITS_PER_PULL,
            "source_sha256": record["document_sha256"],
        }
        for index, offset in enumerate(PULL_OFFSETS_DAYS)
    ]


def _name_tokens(name: str) -> list[str]:
    text = " ".join(name.strip().split()).casefold()
    return [token for token in "".join(ch if ch.isalpha() else " " for ch in text).split() if token]


def _named_human(name: Any) -> str:
    if not isinstance(name, str):
        raise PermissionError("named human reviewer required")
    normalized = " ".join(name.strip().split())
    tokens = _name_tokens(normalized)
    if len([token for token in tokens if len(token) >= 2]) < 2:
        raise PermissionError("two alphabetic name tokens required")
    for start in range(len(tokens)):
        combined = ""
        for end in range(start, min(len(tokens), start + 3)):
            combined += tokens[end]
            if combined in RESERVED_ACTORS:
                raise PermissionError("named human reviewer required")
    return normalized


@dataclass(frozen=True)
class ReplayResult:
    ready: int
    hold: int
    replayed: int
    accessions_added: int
    jobs_added: int
    results_added: int
    reports_added: int
    pulls_added: int
    holds_added: int
    events_added: int
    hold_counts: dict[str, int]
    state_digest: str


class BASciencesStabilityIntakeShadow:
    def __init__(self, authoritative_state: Mapping[str, Any] | None = None):
        self.authoritative_state = copy.deepcopy(dict(authoritative_state or {}))
        self._authoritative_sha = sha256_hex(self.authoritative_state)
        self.accessions: dict[str, dict[str, Any]] = {}
        self.jobs: dict[str, dict[str, Any]] = {}
        self.results: dict[str, list[dict[str, Any]]] = {}
        self.reports: dict[str, dict[str, Any]] = {}
        self.pull_schedules: dict[str, list[dict[str, Any]]] = {}
        self.holds: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []
        self._payload_hashes: dict[str, str] = {}

    @property
    def authoritative_fingerprint(self) -> str:
        current = sha256_hex(self.authoritative_state)
        if current != self._authoritative_sha:
            raise IntegrityError("authoritative state mutated")
        return current

    def state_digest(self) -> str:
        return sha256_hex({
            "accessions": self.accessions,
            "jobs": self.jobs,
            "results": self.results,
            "reports": self.reports,
            "pull_schedules": self.pull_schedules,
            "holds": self.holds,
            "events": self.events,
            "payload_hashes": self._payload_hashes,
        })

    def replay(self, records: Sequence[Mapping[str, Any]], manifest: Mapping[str, Any]) -> ReplayResult:
        # Fail a changed-content same-ID replay before any state or event mutation.
        for record in records:
            record_id = record.get("record_id") if isinstance(record, Mapping) else None
            if isinstance(record_id, str) and record_id in self._payload_hashes:
                if self._payload_hashes[record_id] != sha256_hex(record):
                    raise IntegrityError("REPLAY_PAYLOAD_MISMATCH")
        verify_records(records, manifest)
        self.authoritative_fingerprint
        ready = hold = replayed = aa = ja = resa = repa = pa = ha = ea = 0
        counts = Counter()
        for record in records:
            record_id = record["record_id"]
            payload_hash = sha256_hex(record)
            if record_id in self._payload_hashes:
                if self._payload_hashes[record_id] != payload_hash:
                    raise IntegrityError("REPLAY_PAYLOAD_MISMATCH")
                replayed += 1
                continue
            code = _hold_code(record)
            if code != record["truth_hold"]:
                raise IntegrityError(f"truth/classifier mismatch {record_id}")
            self._payload_hashes[record_id] = payload_hash
            if code:
                hold += 1
                counts[code] += 1
                self.holds[record_id] = {
                    "record_id": record_id,
                    "hold_code": code,
                    "source_sha256": record["document_sha256"],
                    "testing_created": 0,
                    "report_created": 0,
                    "pulls_created": 0,
                }
                ha += 1
                status = "HOLD"
            else:
                ready += 1
                route = ROUTES[record["form_type"]]
                normalized = _normalized(record)
                accession_id = f"BA-ACC-{record_id[-4:]}"
                self.accessions[record_id] = {
                    "record_id": record_id,
                    "accession_id": accession_id,
                    "site_id": route["site_id"],
                    "normalized": normalized,
                    "source_sha256": record["document_sha256"],
                }
                aa += 1
                self.jobs[record_id] = {
                    "record_id": record_id,
                    "accession_id": accession_id,
                    "site_id": route["site_id"],
                    "method_id": route["method_id"],
                    "state": "STAGED_NOT_RUN",
                    "source_sha256": record["document_sha256"],
                }
                ja += 1
                result_rows = [
                    {
                        "result_id": f"RES-{record_id}-{index + 1:02d}",
                        "ordinal": index + 1,
                        "state": "SYNTHETIC_NOT_EVALUATED",
                        "source_sha256": record["document_sha256"],
                    }
                    for index in range(route["result_count"])
                ]
                self.results[record_id] = result_rows
                resa += len(result_rows)
                pulls = _pull_schedule(record)
                if pulls:
                    self.pull_schedules[record_id] = pulls
                    pa += len(pulls)
                report_core = {
                    "record_id": record_id,
                    "accession_id": accession_id,
                    "site_id": route["site_id"],
                    "method_id": route["method_id"],
                    "result_ids": [item["result_id"] for item in result_rows],
                    "normalized_sha256": sha256_hex(normalized),
                    "pull_schedule_sha256": sha256_hex(pulls) if pulls else None,
                    "source_sha256": record["document_sha256"],
                    "state": "STAGED_HUMAN_REVIEW",
                    "released_by": None,
                    "sent": False,
                }
                report_core["report_digest"] = sha256_hex(report_core)
                self.reports[record_id] = report_core
                repa += 1
                status = "READY"
            self.events.append({
                "sequence": len(self.events) + 1,
                "record_id": record_id,
                "status": status,
                "hold_code": code,
                "payload_sha256": payload_hash,
            })
            ea += 1
        if not replayed:
            if ready != manifest["expected_ready"] or hold != manifest["expected_hold"]:
                raise IntegrityError("acceptance count mismatch")
            if counts != Counter(manifest["expected_hold_codes"]):
                raise IntegrityError("hold distribution mismatch")
        self.authoritative_fingerprint
        return ReplayResult(
            ready, hold, replayed, aa, ja, resa, repa, pa, ha, ea,
            dict(sorted(counts.items())), self.state_digest()
        )

    def release_report(self, record_id: str, reviewer_name: Any) -> dict[str, Any]:
        reviewer = _named_human(reviewer_name)
        report = self.reports.get(record_id)
        if report is None:
            raise KeyError(record_id)
        if report["state"] != "STAGED_HUMAN_REVIEW" or report["released_by"] is not None:
            raise PermissionError("report not eligible for release")
        out = copy.deepcopy(report)
        out["state"] = "RELEASED_BY_NAMED_HUMAN"
        out["released_by"] = reviewer
        out["sent"] = False
        return out

    def automatic_release(self, *_: Any, **__: Any) -> None:
        raise PermissionError("automatic release disabled")


def run_acceptance(fixture_path: str | Path | None = None, manifest_path: str | Path | None = None) -> dict[str, Any]:
    records, manifest = load_fixture(fixture_path, manifest_path)
    shadow = BASciencesStabilityIntakeShadow({"adapter_mode": "read-only", "production_writes": 0})
    first = shadow.replay(records, manifest)
    digest = first.state_digest
    second = shadow.replay(records, manifest)
    if second.replayed != 220 or any((second.accessions_added, second.jobs_added, second.results_added,
                                     second.reports_added, second.pulls_added, second.holds_added, second.events_added)):
        raise IntegrityError("replay not zero-add")
    if second.state_digest != digest:
        raise IntegrityError("replay state drift")
    released = shadow.release_report(next(iter(shadow.reports)), "Jordan Reviewer")
    return {
        "demand_id": DEMAND_ID,
        "ready": first.ready,
        "hold": first.hold,
        "hold_counts": first.hold_counts,
        "accessions": len(shadow.accessions),
        "jobs": len(shadow.jobs),
        "results": sum(len(rows) for rows in shadow.results.values()),
        "reports": len(shadow.reports),
        "stability_schedules": len(shadow.pull_schedules),
        "pull_events": sum(len(rows) for rows in shadow.pull_schedules.values()),
        "replay_zero_add": True,
        "state_digest": digest,
        "authoritative_fingerprint": shadow.authoritative_fingerprint,
        "release_state": released["state"],
        "released_by": released["released_by"],
        "sent": released["sent"],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate the frozen synthetic BA Sciences multi-site intake fixture.")
    parser.add_argument("--fixture")
    parser.add_argument("--manifest")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        output = run_acceptance(args.fixture, args.manifest)
    except (IntegrityError, OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps({"ok": True, **output}, sort_keys=True, separators=(",", ":")))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
