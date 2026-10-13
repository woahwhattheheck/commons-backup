"""Synthetic/read-only New Bloom multi-state beverage CoA provenance shadow."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

DEMAND_ID = "newbloom-multistate-beverage-coa-lims-01"
MANIFEST_PREFIX = "NEWBLOOM-MULTISTATE-BEVERAGE-SYNTHETIC-MANIFEST-V1\n"
HOLD_CODES = (
    "MISSING_PH_OR_STORAGE_METADATA",
    "RULE_PACK_VERSION_MISMATCH",
    "DUPLICATE_BATCH_ID",
    "HOMOGENEITY_EXCEPTION",
)
STATE_PACKS = {
    "CA-SYN": "SYN-CA-BEV-2026.1",
    "CO-SYN": "SYN-CO-BEV-2026.1",
    "IL-SYN": "SYN-IL-BEV-2026.1",
    "MA-SYN": "SYN-MA-BEV-2026.1",
    "MI-SYN": "SYN-MI-BEV-2026.1",
    "NV-SYN": "SYN-NV-BEV-2026.1",
    "NY-SYN": "SYN-NY-BEV-2026.1",
    "WA-SYN": "SYN-WA-BEV-2026.1",
}
ANALYTE_SCHEMA = (
    ("ANALYTE_ALPHA", "mg/L", "0.10"),
    ("ANALYTE_BETA", "mg/L", "0.20"),
    ("ANALYTE_GAMMA", "mg/L", "0.50"),
)
RESERVED = {
    "auto", "automatic", "automation", "bot", "system", "service",
    "service-account", "agent", "ai", "scheduler", "worker", "pipeline",
    "anonymous", "unknown",
}
FORBIDDEN = {
    "patient", "patient_name", "dob", "mrn", "medical_record_number",
    "diagnosis", "ssn", "password", "secret", "token", "api_key",
}


class IntegrityError(ValueError):
    pass


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _record_hash(record: Mapping[str, Any]) -> str:
    return _sha(_canon(record))


def _manifest_analytes() -> list[dict[str, str]]:
    return [
        {"analyte": analyte, "unit": unit, "loq": loq}
        for analyte, unit, loq in ANALYTE_SCHEMA
    ]


def _manifest_envelope(manifest: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "demand_id", "fixture_version", "dataset_sha256",
        "expanded_records_sha256", "record_count", "expected_ready",
        "expected_hold", "expected_hold_codes", "state_packs",
        "analyte_schema", "drafts_per_ready",
    )
    return {key: manifest[key] for key in keys}


def verify_manifest_signature(manifest: Mapping[str, Any]) -> None:
    if manifest.get("signature_alg") != "sha256-content-envelope-v1":
        raise IntegrityError("manifest signature algorithm mismatch")
    expected = _sha(MANIFEST_PREFIX + _canon(_manifest_envelope(manifest)))
    if manifest.get("signature") != expected:
        raise IntegrityError("manifest signature mismatch")


def _results(index: int) -> list[dict[str, Any]]:
    values = (index * 7, index * 11, index * 13)
    return [
        {
            "analyte": analyte,
            "value": value,
            "unit": unit,
            "loq": loq,
            "method_version": "SYN-BEV-ANALYTICS-1.0",
        }
        for (analyte, unit, loq), value in zip(ANALYTE_SCHEMA, values)
    ]


def _source_result_hash(results: list[dict[str, Any]]) -> str:
    return _sha(_canon(results))


def _result_schema_hash(results: list[dict[str, Any]]) -> str:
    schema = [
        {"analyte": item["analyte"], "unit": item["unit"], "loq": item["loq"]}
        for item in results
    ]
    return _sha(_canon(schema))


def _expand(index: int, truth_hold: str | None) -> dict[str, Any]:
    packs = tuple(STATE_PACKS)
    submitted_pack = packs[(index - 1) % len(packs)]
    batch_id = f"NB-BATCH-{index:04d}"
    ph: str | None = f"{3 + ((index - 1) % 7) / 10:.1f}"
    storage: str | None = "SYNTHETIC_AMBIENT"
    submitted_version = STATE_PACKS[submitted_pack]
    homogeneity_pass = True

    if truth_hold == HOLD_CODES[0]:
        if index % 2:
            ph = None
        else:
            storage = None
    elif truth_hold == HOLD_CODES[1]:
        submitted_version = "SYN-WRONG-RULE-PACK-0"
    elif truth_hold == HOLD_CODES[2]:
        batch_id = f"NB-BATCH-{index - 88:04d}"
    elif truth_hold == HOLD_CODES[3]:
        homogeneity_pass = False

    results = _results(index)
    source_result_hash = _source_result_hash(results)
    record = {
        "record_id": f"NB-REC-{index:04d}",
        "deidentified": True,
        "batch_id": batch_id,
        "matrix": "SYNTHETIC_BEVERAGE",
        "submitted_state_pack": submitted_pack,
        "submitted_rule_pack_version": submitted_version,
        "ph": ph,
        "storage": storage,
        "homogeneity_pass": homogeneity_pass,
        "results": results,
        "source_result_sha256": source_result_hash,
        "result_schema_sha256": _result_schema_hash(results),
        "truth_hold": truth_hold,
    }
    record["record_sha256"] = _sha(_canon(record))
    return record


def _rows(payload: Mapping[str, Any]) -> list[tuple[int, str | None]]:
    if payload.get("schema") != "deterministic-generator-v1":
        raise IntegrityError("fixture schema mismatch")
    generator = payload.get("generator")
    if not isinstance(generator, dict):
        raise IntegrityError("missing generator")
    if (generator.get("record_count"), generator.get("clean_count")) != (96, 72):
        raise IntegrityError("fixture generator dimensions mismatch")
    if generator.get("state_pack_cycle") != list(STATE_PACKS):
        raise IntegrityError("state-pack cycle mismatch")

    holds: dict[int, str] = {}
    for segment in generator.get("hold_segments", []):
        if not isinstance(segment, dict):
            raise IntegrityError("invalid HOLD segment")
        code, start, count = segment.get("code"), segment.get("start"), segment.get("count")
        if code not in HOLD_CODES:
            raise IntegrityError("unknown HOLD code")
        if (
            not isinstance(start, int) or isinstance(start, bool)
            or not isinstance(count, int) or isinstance(count, bool)
        ):
            raise IntegrityError("invalid HOLD segment bounds")
        for row in range(start, start + count):
            if row in holds or not 1 <= row <= 96:
                raise IntegrityError("overlapping/out-of-range HOLD segment")
            holds[row] = code
    if set(holds) != set(range(73, 97)):
        raise IntegrityError("HOLD segments must cover rows 73..96 exactly")
    return [(index, holds.get(index)) for index in range(1, 97)]


def verify_records(records: list[Mapping[str, Any]], manifest: Mapping[str, Any]) -> None:
    verify_manifest_signature(manifest)
    if manifest.get("demand_id") != DEMAND_ID:
        raise IntegrityError("demand mismatch")
    if len(records) != manifest.get("record_count"):
        raise IntegrityError("record-count mismatch")
    if manifest.get("state_packs") != STATE_PACKS:
        raise IntegrityError("state-pack manifest mismatch")
    if manifest.get("analyte_schema") != _manifest_analytes():
        raise IntegrityError("analyte manifest mismatch")
    if manifest.get("drafts_per_ready") != len(STATE_PACKS):
        raise IntegrityError("draft-count manifest mismatch")
    if _sha(_canon(records)) != manifest.get("expanded_records_sha256"):
        raise IntegrityError("expanded record hash mismatch")

    truth = Counter(record["truth_hold"] for record in records if record["truth_hold"])
    if truth != Counter(manifest.get("expected_hold_codes", {})):
        raise IntegrityError("truth-set mismatch")
    if len(records) - sum(truth.values()) != manifest.get("expected_ready"):
        raise IntegrityError("READY truth-set mismatch")
    if len({record["record_id"] for record in records}) != len(records):
        raise IntegrityError("duplicate record_id")

    pack_counts = Counter(record["submitted_state_pack"] for record in records)
    if pack_counts != Counter({pack: 12 for pack in STATE_PACKS}):
        raise IntegrityError("state pack distribution mismatch")

    for record in records:
        if not record.get("deidentified"):
            raise IntegrityError("fixture must be deidentified")
        if {str(key).lower() for key in record} & FORBIDDEN:
            raise IntegrityError("fixture safety boundary")
        if record.get("source_result_sha256") != _source_result_hash(record.get("results", [])):
            raise IntegrityError("source-result hash mismatch")
        if record.get("result_schema_sha256") != _result_schema_hash(record.get("results", [])):
            raise IntegrityError("analyte/unit/LOQ schema hash mismatch")
        base = dict(record)
        recorded_hash = base.pop("record_sha256", None)
        if recorded_hash != _sha(_canon(base)):
            raise IntegrityError("record hash mismatch")


def load_fixture(fixture_path: str | Path | None = None, manifest_path: str | Path | None = None):
    base = Path(__file__).resolve().parent / "fixtures"
    fixture = Path(fixture_path) if fixture_path else base / "newbloom_96_batches.json"
    manifest_file = Path(manifest_path) if manifest_path else base / "manifest.json"
    fixture_text = fixture.read_text()
    manifest = json.loads(manifest_file.read_text())
    if _sha(fixture_text) != manifest.get("dataset_sha256"):
        raise IntegrityError("dataset file hash mismatch")
    payload = json.loads(fixture_text)
    if payload.get("fixture_version") != manifest.get("fixture_version"):
        raise IntegrityError("fixture version mismatch")
    records = [_expand(index, truth) for index, truth in _rows(payload)]
    verify_records(records, manifest)
    return records, manifest


def _classify(record: Mapping[str, Any], seen_batch_ids: set[str]) -> str | None:
    if not isinstance(record.get("ph"), str) or not record.get("ph"):
        return HOLD_CODES[0]
    if not isinstance(record.get("storage"), str) or not record.get("storage"):
        return HOLD_CODES[0]
    pack = record.get("submitted_state_pack")
    if pack not in STATE_PACKS or record.get("submitted_rule_pack_version") != STATE_PACKS[pack]:
        return HOLD_CODES[1]
    batch_id = record.get("batch_id")
    if not isinstance(batch_id, str) or not batch_id or batch_id in seen_batch_ids:
        return HOLD_CODES[2]
    if record.get("homogeneity_pass") is not True:
        return HOLD_CODES[3]
    return None


def _named_human(name: str, approval_id: str) -> tuple[str, str]:
    if not isinstance(name, str):
        raise PermissionError("named human reviewer required")
    normalized = " ".join(name.strip().split())
    identity_tokens = re.findall(r"[^\W_]+", normalized.casefold())
    words = [token for token in identity_tokens if any(c.isalpha() for c in token)]
    if not normalized or any(token in RESERVED for token in identity_tokens) or len(words) < 2:
        raise PermissionError("two-token named human reviewer required")
    if not isinstance(approval_id, str):
        raise PermissionError("approval id required")
    approval = approval_id.strip()
    if not approval.startswith("APR-") or len(approval) < 8 or any(ch.isspace() for ch in approval):
        raise PermissionError("explicit approval id required")
    return normalized, approval


@dataclass
class ReplayReport:
    ready: int
    hold: int
    replayed: int
    hold_counts: dict[str, int]
    packets_added: int
    drafts_added: int
    holds_added: int
    events_added: int
    state_digest: str
    outcomes: list[dict[str, Any]]


class NewBloomBeverageCoAShadow:
    def __init__(self, authoritative_state: Mapping[str, Any] | None = None):
        self.authoritative_state = copy.deepcopy(authoritative_state or {})
        self._authoritative_fingerprint = _sha(_canon(self.authoritative_state))
        self.staged_packets: dict[str, dict[str, Any]] = {}
        self.holds: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []
        self._seen_records: set[str] = set()
        self._seen_batch_ids: set[str] = set()

    @property
    def authoritative_fingerprint(self) -> str:
        current = _sha(_canon(self.authoritative_state))
        if current != self._authoritative_fingerprint:
            raise IntegrityError("authoritative state mutated")
        return current

    def state_digest(self) -> str:
        return _sha(_canon({
            "staged_packets": self.staged_packets,
            "holds": self.holds,
            "events": self.events,
            "seen_records": sorted(self._seen_records),
            "seen_batch_ids": sorted(self._seen_batch_ids),
        }))

    def replay(self, records: list[Mapping[str, Any]], manifest: Mapping[str, Any]) -> ReplayReport:
        verify_records(records, manifest)
        self.authoritative_fingerprint
        ready = hold = replayed = packets_added = drafts_added = holds_added = events_added = 0
        hold_counts: Counter[str] = Counter()
        outcomes: list[dict[str, Any]] = []

        for record in records:
            record_id = record["record_id"]
            if record_id in self._seen_records:
                replayed += 1
                outcomes.append({
                    "record_id": record_id,
                    "status": "IDEMPOTENT_REPLAY",
                    "hold_code": self.holds.get(record_id, {}).get("hold_code"),
                    "record_sha256": record["record_sha256"],
                })
                continue

            code = _classify(record, self._seen_batch_ids)
            if code != record["truth_hold"]:
                raise IntegrityError(f"classifier/truth mismatch {record_id}: {code} != {record['truth_hold']}")
            self._seen_records.add(record_id)
            if code != HOLD_CODES[2]:
                self._seen_batch_ids.add(record["batch_id"])

            if code:
                hold += 1
                hold_counts[code] += 1
                self.holds[record_id] = {
                    "record_id": record_id,
                    "batch_id": record["batch_id"],
                    "hold_code": code,
                    "packets_created": 0,
                    "drafts_created": 0,
                }
                holds_added += 1
                outcome = {
                    "record_id": record_id,
                    "status": "HOLD",
                    "hold_code": code,
                    "packets_created": 0,
                    "drafts_created": 0,
                    "record_sha256": record["record_sha256"],
                }
            else:
                ready += 1
                source_hash = record["source_result_sha256"]
                schema_hash = record["result_schema_sha256"]
                drafts = []
                for state_pack, rule_version in STATE_PACKS.items():
                    copied_results = copy.deepcopy(record["results"])
                    if _source_result_hash(copied_results) != source_hash:
                        raise IntegrityError("draft source-result drift")
                    if _result_schema_hash(copied_results) != schema_hash:
                        raise IntegrityError("draft analyte/unit/LOQ drift")
                    drafts.append({
                        "state_pack": state_pack,
                        "rule_pack_version": rule_version,
                        "matrix": record["matrix"],
                        "ph": record["ph"],
                        "storage": record["storage"],
                        "results": copied_results,
                        "source_result_sha256": source_hash,
                        "result_schema_sha256": schema_hash,
                        "compliance_status": "NOT_EVALUATED",
                        "state": "STAGED_HUMAN_REVIEW",
                        "released_by": None,
                        "approval_id": None,
                        "sent": False,
                    })
                packet = {
                    "record_id": record_id,
                    "batch_id": record["batch_id"],
                    "submitted_state_pack": record["submitted_state_pack"],
                    "state": "STAGED_HUMAN_REVIEW",
                    "source_result_sha256": source_hash,
                    "result_schema_sha256": schema_hash,
                    "drafts": drafts,
                    "released_by": None,
                    "approval_id": None,
                    "sent": False,
                }
                self.staged_packets[record_id] = packet
                packets_added += 1
                drafts_added += len(drafts)
                outcome = {
                    "record_id": record_id,
                    "status": "STAGED_HUMAN_REVIEW",
                    "hold_code": None,
                    "packet_created": True,
                    "draft_count": len(drafts),
                    "source_result_sha256": source_hash,
                    "result_schema_sha256": schema_hash,
                    "record_sha256": record["record_sha256"],
                }

            self.events.append({
                "sequence": len(self.events) + 1,
                "record_id": record_id,
                "status": outcome["status"],
                "hold_code": outcome["hold_code"],
                "record_sha256": record["record_sha256"],
            })
            events_added += 1
            outcomes.append(outcome)

        if not replayed:
            if ready != manifest["expected_ready"] or hold != manifest["expected_hold"]:
                raise IntegrityError("replay counts mismatch")
            if hold_counts != Counter(manifest["expected_hold_codes"]):
                raise IntegrityError("replay HOLD distribution mismatch")

        self.authoritative_fingerprint
        return ReplayReport(
            ready=ready,
            hold=hold,
            replayed=replayed,
            hold_counts=dict(sorted(hold_counts.items())),
            packets_added=packets_added,
            drafts_added=drafts_added,
            holds_added=holds_added,
            events_added=events_added,
            state_digest=self.state_digest(),
            outcomes=outcomes,
        )

    def release_packet(self, record_id: str, reviewer_name: str, approval_id: str) -> dict[str, Any]:
        reviewer, approval = _named_human(reviewer_name, approval_id)
        packet = self.staged_packets.get(record_id)
        if packet is None:
            raise KeyError(record_id)
        if packet["state"] != "STAGED_HUMAN_REVIEW" or packet["released_by"] is not None:
            raise PermissionError("packet not eligible to release a certificate")
        released = copy.deepcopy(packet)
        released["state"] = "RELEASED_BY_NAMED_HUMAN"
        released["released_by"] = reviewer
        released["approval_id"] = approval
        released["sent"] = False
        for draft in released["drafts"]:
            draft["state"] = "RELEASED_BY_NAMED_HUMAN"
            draft["released_by"] = reviewer
            draft["approval_id"] = approval
            draft["sent"] = False
        return released

    def automatic_release(self, record_id: str) -> None:
        raise PermissionError(f"automatic CoA release disabled: {record_id}")


def run_acceptance() -> dict[str, Any]:
    records, manifest = load_fixture()
    shadow = NewBloomBeverageCoAShadow({"mode": "production-read-only", "records": 41})
    first = shadow.replay(records, manifest)
    before_second = first.state_digest
    second = shadow.replay(records, manifest)
    record_id = next(iter(shadow.staged_packets))
    released = shadow.release_packet(record_id, "Jordan Reviewer", "APR-SYN-0001")
    draft_source_hashes = {draft["source_result_sha256"] for draft in released["drafts"]}
    draft_schema_hashes = {draft["result_schema_sha256"] for draft in released["drafts"]}
    return {
        "ready": first.ready,
        "hold": first.hold,
        "hold_counts": first.hold_counts,
        "packets": len(shadow.staged_packets),
        "drafts": sum(len(packet["drafts"]) for packet in shadow.staged_packets.values()),
        "replayed": second.replayed,
        "replay_zero_add": (
            second.packets_added == 0
            and second.drafts_added == 0
            and second.holds_added == 0
            and second.events_added == 0
            and second.state_digest == before_second
        ),
        "state_digest": second.state_digest,
        "release_state": released["state"],
        "release_approval_id": released["approval_id"],
        "sent": released["sent"],
        "draft_source_hash_count": len(draft_source_hashes),
        "draft_schema_hash_count": len(draft_schema_hashes),
        "authoritative_fingerprint": shadow.authoritative_fingerprint,
    }


if __name__ == "__main__":
    print(json.dumps(run_acceptance(), sort_keys=True))
