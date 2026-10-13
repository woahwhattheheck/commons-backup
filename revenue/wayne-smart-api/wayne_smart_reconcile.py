"""Deterministic synthetic/read-only Wayne RESA SMART API reconciliation shadow."""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

TASK_ID = "wayne-smart-api-01"
PREFIX = "WAYNE-SMART-SYNTHETIC-MANIFEST-V1\n"
RECONCILED = "RECONCILED"
DUPLICATE_NOOP = "DUPLICATE_NOOP"
HOLD_UNKNOWN_COMMIT = "HOLD_UNKNOWN_COMMIT"
HOLD_UNAUTHORIZED = "HOLD_UNAUTHORIZED"
HOLD_LEDGER_VARIANCE = "HOLD_LEDGER_VARIANCE"
EXPECTED_KNOWN_COMMITS = {f"SMART-COMMIT-{n:04d}" for n in range(1, 121)}


class IntegrityError(ValueError):
    """Frozen synthetic fixture or reconciliation invariant failed."""


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def manifest_envelope(manifest: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "task_id",
        "schema_version",
        "fixture_version",
        "record_count",
        "fixture_sha256",
        "expanded_records_sha256",
        "expected_statuses",
        "expected_ledger_variance_cents",
        "expected_duplicate_mutation_effects",
        "expected_unauthorized_reads",
        "synthetic_only",
        "forbidden_fields",
    )
    return {key: manifest[key] for key in keys}


def verify_manifest(manifest: Mapping[str, Any]) -> None:
    if manifest.get("task_id") != TASK_ID or manifest.get("schema_version") != 1:
        raise IntegrityError("manifest identity mismatch")
    if manifest.get("signature_alg") != "sha256-content-envelope-v1":
        raise IntegrityError("unsupported manifest signature")
    expected = sha_text(PREFIX + canonical(manifest_envelope(manifest)))
    if manifest.get("signature") != expected:
        raise IntegrityError("manifest content-envelope signature mismatch")


def expand_fixture(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    if (
        payload.get("task_id") != TASK_ID
        or payload.get("schema_version") != 1
        or payload.get("synthetic_only") is not True
        or payload.get("record_count") != 150
    ):
        raise IntegrityError("fixture identity/shape mismatch")
    generator = payload.get("generator")
    if not isinstance(generator, Mapping):
        raise IntegrityError("fixture generator missing")

    expected_segments = {
        "authorized_known": {"start": 1, "count": 120},
        "duplicate_mutation": {"start": 121, "count": 10, "duplicate_start": 1},
        "unknown_commit": {"start": 131, "count": 10},
        "unauthorized_principal": {"start": 141, "count": 10},
    }
    if generator != expected_segments:
        raise IntegrityError("fixture generator contract mismatch")

    records: list[dict[str, Any]] = []
    for n in range(1, 151):
        truth = RECONCILED
        authorized = True
        mutation_index = n
        commit_id = f"SMART-COMMIT-{n:04d}"

        if 121 <= n <= 130:
            truth = DUPLICATE_NOOP
            mutation_index = 1 + (n - 121)
            commit_id = f"SMART-COMMIT-{mutation_index:04d}"
        elif 131 <= n <= 140:
            truth = HOLD_UNKNOWN_COMMIT
            commit_id = f"SMART-UNKNOWN-{n:04d}"
        elif 141 <= n <= 150:
            truth = HOLD_UNAUTHORIZED
            authorized = False
            commit_id = f"SMART-COMMIT-{((n - 141) % 120) + 1:04d}"

        expected_cents = 100_000 + mutation_index * 137
        records.append(
            {
                "record_id": f"WAYNE-STATE-{n:04d}",
                "mutation_key": f"WAYNE-MUT-{mutation_index:04d}",
                "commit_id": commit_id,
                "principal_role": (
                    "SMART_RECONCILER" if authorized else "UNAUTHORIZED_SYNTHETIC_ROLE"
                ),
                "authorized": authorized,
                "ledger_account": f"SYNTH-ACCOUNT-{((mutation_index - 1) % 12) + 1:02d}",
                "expected_cents": expected_cents,
                "posted_cents": expected_cents,
                "source_uri": f"synthetic://wayne-smart/{n:04d}.json",
                "truth_status": truth,
            }
        )
    return records


def verify_records(records: list[dict[str, Any]], manifest: Mapping[str, Any]) -> None:
    verify_manifest(manifest)
    if len(records) != manifest.get("record_count"):
        raise IntegrityError("expanded record count mismatch")
    if sha_text(canonical(records)) != manifest.get("expanded_records_sha256"):
        raise IntegrityError("expanded record-set hash mismatch")
    expected = Counter(manifest["expected_statuses"])
    actual = Counter(record["truth_status"] for record in records)
    if actual != expected:
        raise IntegrityError("truth-set distribution mismatch")
    forbidden = set(manifest["forbidden_fields"])
    record_ids: set[str] = set()
    for record in records:
        if forbidden.intersection(record):
            raise IntegrityError("forbidden identity field present")
        if record["record_id"] in record_ids:
            raise IntegrityError("duplicate record_id")
        record_ids.add(record["record_id"])
        if not str(record.get("source_uri", "")).startswith("synthetic://"):
            raise IntegrityError("non-synthetic source URI")
        for key in ("expected_cents", "posted_cents"):
            value = record.get(key)
            if isinstance(value, bool) or not isinstance(value, int):
                raise IntegrityError(f"{key} must be integer cents")


def load_fixture(
    fixture_path: str | Path | None = None,
    manifest_path: str | Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    base = Path(__file__).resolve().parent / "fixtures"
    fixture_path = Path(fixture_path) if fixture_path else base / "wayne_150_states.json"
    manifest_path = Path(manifest_path) if manifest_path else base / "manifest.json"
    fixture_text = fixture_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if sha_text(fixture_text) != manifest.get("fixture_sha256"):
        raise IntegrityError("fixture file hash mismatch")
    records = expand_fixture(json.loads(fixture_text))
    verify_records(records, manifest)
    return records, manifest


@dataclass(frozen=True)
class ReplayReport:
    statuses: dict[str, int]
    processed: int
    reconciled: int
    duplicate_noop: int
    holds: int
    staged_effects_added: int
    holds_added: int
    events_added: int
    protected_reads_added: int
    unauthorized_reads_added: int
    duplicate_mutation_effects: int
    ledger_variance_cents: int
    idempotent_replays: int
    state_digest: str


class WayneSmartShadow:
    """Read-only shadow state. The supplied authoritative state is copied and fingerprinted."""

    def __init__(self, authoritative_state: Mapping[str, Any] | None = None) -> None:
        self.authoritative_state = copy.deepcopy(dict(authoritative_state or {}))
        self._authoritative_digest = sha_text(canonical(self.authoritative_state))
        self.processed_record_ids: set[str] = set()
        self.staged_by_mutation: dict[str, dict[str, Any]] = {}
        self.holds: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []
        self.protected_reads: list[dict[str, Any]] = []

    def authoritative_digest(self) -> str:
        current = sha_text(canonical(self.authoritative_state))
        if current != self._authoritative_digest:
            raise IntegrityError("authoritative state changed inside read-only shadow")
        return current

    def state_digest(self) -> str:
        return sha_text(
            canonical(
                {
                    "processed_record_ids": sorted(self.processed_record_ids),
                    "staged_by_mutation": self.staged_by_mutation,
                    "holds": self.holds,
                    "events": self.events,
                    "protected_reads": self.protected_reads,
                }
            )
        )

    def _classify(self, record: Mapping[str, Any]) -> str:
        if record["authorized"] is not True:
            return HOLD_UNAUTHORIZED
        if record["commit_id"] not in EXPECTED_KNOWN_COMMITS:
            return HOLD_UNKNOWN_COMMIT
        if record["mutation_key"] in self.staged_by_mutation:
            return DUPLICATE_NOOP
        if record["expected_cents"] != record["posted_cents"]:
            return HOLD_LEDGER_VARIANCE
        return RECONCILED

    def replay(
        self, records: list[dict[str, Any]], manifest: Mapping[str, Any]
    ) -> ReplayReport:
        verify_records(records, manifest)
        self.authoritative_digest()

        statuses: Counter[str] = Counter()
        before_effects = len(self.staged_by_mutation)
        before_holds = len(self.holds)
        before_events = len(self.events)
        before_reads = len(self.protected_reads)
        idempotent = 0
        duplicate_mutation_effects = 0
        ledger_variance = 0

        for record in records:
            record_id = record["record_id"]
            if record_id in self.processed_record_ids:
                idempotent += 1
                statuses["IDEMPOTENT_REPLAY"] += 1
                continue

            status = self._classify(record)
            if status != record["truth_status"]:
                raise IntegrityError(
                    f"classifier/truth mismatch {record_id}: {status} != {record['truth_status']}"
                )
            self.processed_record_ids.add(record_id)
            statuses[status] += 1

            if status == HOLD_UNAUTHORIZED:
                self.holds[record_id] = {
                    "record_id": record_id,
                    "hold_code": status,
                    "commit_id": record["commit_id"],
                    "protected_read": False,
                }
                self.events.append(
                    {"record_id": record_id, "event": "HOLD", "code": status}
                )
                continue

            if status == HOLD_UNKNOWN_COMMIT:
                self.holds[record_id] = {
                    "record_id": record_id,
                    "hold_code": status,
                    "commit_id": record["commit_id"],
                    "protected_read": False,
                }
                self.events.append(
                    {"record_id": record_id, "event": "HOLD", "code": status}
                )
                continue

            if status == DUPLICATE_NOOP:
                if record["mutation_key"] not in self.staged_by_mutation:
                    duplicate_mutation_effects += 1
                self.events.append(
                    {
                        "record_id": record_id,
                        "event": DUPLICATE_NOOP,
                        "mutation_key": record["mutation_key"],
                    }
                )
                continue

            if status == HOLD_LEDGER_VARIANCE:
                delta = record["posted_cents"] - record["expected_cents"]
                ledger_variance += delta
                self.holds[record_id] = {
                    "record_id": record_id,
                    "hold_code": status,
                    "variance_cents": delta,
                    "protected_read": False,
                }
                self.events.append(
                    {"record_id": record_id, "event": "HOLD", "code": status}
                )
                continue

            self.protected_reads.append(
                {
                    "record_id": record_id,
                    "principal_role": record["principal_role"],
                    "authorized": True,
                    "synthetic_only": True,
                }
            )
            variance = record["posted_cents"] - record["expected_cents"]
            ledger_variance += variance
            if variance != 0:
                raise IntegrityError("nonzero ledger variance reached reconciliation path")
            self.staged_by_mutation[record["mutation_key"]] = {
                "record_id": record_id,
                "mutation_key": record["mutation_key"],
                "commit_id": record["commit_id"],
                "ledger_account": record["ledger_account"],
                "expected_cents": record["expected_cents"],
                "posted_cents": record["posted_cents"],
                "status": "READ_ONLY_RECONCILED",
                "source_uri": record["source_uri"],
            }
            self.events.append(
                {
                    "record_id": record_id,
                    "event": "STAGE_READ_ONLY_RECONCILIATION",
                    "mutation_key": record["mutation_key"],
                }
            )

        unauthorized_reads = sum(
            1 for item in self.protected_reads if item.get("authorized") is not True
        )
        self.authoritative_digest()
        return ReplayReport(
            statuses=dict(sorted(statuses.items())),
            processed=len(records) - idempotent,
            reconciled=statuses[RECONCILED],
            duplicate_noop=statuses[DUPLICATE_NOOP],
            holds=statuses[HOLD_UNKNOWN_COMMIT] + statuses[HOLD_UNAUTHORIZED],
            staged_effects_added=len(self.staged_by_mutation) - before_effects,
            holds_added=len(self.holds) - before_holds,
            events_added=len(self.events) - before_events,
            protected_reads_added=len(self.protected_reads) - before_reads,
            unauthorized_reads_added=unauthorized_reads,
            duplicate_mutation_effects=duplicate_mutation_effects,
            ledger_variance_cents=ledger_variance,
            idempotent_replays=idempotent,
            state_digest=self.state_digest(),
        )


def run_default() -> dict[str, Any]:
    records, manifest = load_fixture()
    shadow = WayneSmartShadow({"mode": "external-authoritative-read-only"})
    first = shadow.replay(records, manifest)
    before = first.state_digest
    second = shadow.replay(records, manifest)
    expected_statuses = dict(sorted(manifest["expected_statuses"].items()))
    if first.statuses != expected_statuses:
        raise IntegrityError("first-run status contract mismatch")
    if first.duplicate_mutation_effects != manifest["expected_duplicate_mutation_effects"]:
        raise IntegrityError("duplicate mutation effect contract mismatch")
    if first.ledger_variance_cents != manifest["expected_ledger_variance_cents"]:
        raise IntegrityError("ledger variance contract mismatch")
    if first.unauthorized_reads_added != manifest["expected_unauthorized_reads"]:
        raise IntegrityError("unauthorized read contract mismatch")
    if (
        second.idempotent_replays != 150
        or second.staged_effects_added
        or second.holds_added
        or second.events_added
        or second.protected_reads_added
        or second.state_digest != before
    ):
        raise IntegrityError("full replay was not side-effect free")
    return {
        "task_id": TASK_ID,
        "records": len(records),
        "statuses": first.statuses,
        "ledger_variance_cents": first.ledger_variance_cents,
        "duplicate_mutation_effects": first.duplicate_mutation_effects,
        "unauthorized_reads": first.unauthorized_reads_added,
        "unknown_commits_held": first.statuses[HOLD_UNKNOWN_COMMIT],
        "authoritative_writes": 0,
        "replay": {
            "idempotent": second.idempotent_replays,
            "staged_effects_added": second.staged_effects_added,
            "holds_added": second.holds_added,
            "events_added": second.events_added,
            "protected_reads_added": second.protected_reads_added,
            "state_unchanged": second.state_digest == before,
        },
    }


def main() -> int:
    print(json.dumps(run_default(), sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
