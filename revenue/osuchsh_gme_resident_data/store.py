"""Versioned resident administration store with audit and aggregate analytics."""

from __future__ import annotations

import copy
from collections import Counter
from typing import Any, Iterable, Mapping

from .codec import (
    ALLOWED_FIELDS,
    DIRECT_IDENTIFIERS,
    ROLE_VIEW_FIELDS,
    ROLE_WRITE_FIELDS,
    AuditError,
    ConflictError,
    DataError,
    PermissionDenied,
    StaleWriteError,
    _SHA256_RE,
    _require_text,
    digest,
    validate_record,
)
from .migration import MigrationPlan, compile_migration

class ResidentStore:
    """Small deterministic administration store with CAS and hash-chained audit.

    Initial migration authority is bound to an owner-supplied source generation at
    construction.  The rows are deep-copied and validated immediately, then every
    applied plan is recompiled from that retained generation before any record is
    admitted.  A MigrationPlan is therefore an inspectable proposal/receipt, not a
    caller-mintable authorization token.
    """

    def __init__(self, migration_rows: Iterable[Mapping[str, Any]] | None = None) -> None:
        self._records: dict[str, dict[str, Any]] = {}
        self._versions: dict[str, int] = {}
        self._audit: list[dict[str, Any]] = []
        self._migration_rows: tuple[Mapping[str, Any], ...] | None = None
        self._migration_plan_digest: str | None = None
        if migration_rows is not None:
            retained = tuple(copy.deepcopy(list(migration_rows)))
            expected = compile_migration(retained)
            self._migration_rows = retained
            self._migration_plan_digest = expected.plan_digest

    def _append_audit(
        self,
        *,
        action: str,
        actor_role: str,
        resident_id: str,
        before_version: int,
        after_version: int,
        changes: Mapping[str, Any],
    ) -> dict[str, Any]:
        prev_hash = self._audit[-1]["event_hash"] if self._audit else "0" * 64
        payload = {
            "seq": len(self._audit) + 1,
            "action": action,
            "actor_role": actor_role,
            "resident_id": resident_id,
            "before_version": before_version,
            "after_version": after_version,
            "changes_digest": digest(dict(changes)),
            "prev_hash": prev_hash,
        }
        event = {**payload, "event_hash": digest(payload)}
        self._audit.append(event)
        return copy.deepcopy(event)

    def apply_migration(
        self,
        plan: MigrationPlan,
        *,
        actor_role: str = "admin",
    ) -> dict[str, Any]:
        if not self._migration_rows:
            raise DataError("initial migration requires a retained source generation")
        if actor_role != "admin":
            raise PermissionDenied("only admin may apply a compiled migration")
        if type(plan) is not MigrationPlan:
            raise DataError("migration plan type invalid")

        # A public dataclass + public digest is not authority. Recompile only the
        # privately retained generation; callers cannot select an alternate source.
        expected = compile_migration(copy.deepcopy(self._migration_rows))
        if plan != expected or plan.plan_digest != self._migration_plan_digest:
            raise DataError("migration plan does not match retained source generation")

        if type(plan.source_rows) is not int or plan.source_rows < len(plan.records):
            raise DataError("migration source_rows invalid")
        if not isinstance(plan.plan_digest, str) or not _SHA256_RE.fullmatch(plan.plan_digest):
            raise DataError("migration plan digest invalid")
        plan_body = {
            "records": list(plan.records),
            "conflicts": list(plan.conflicts),
            "source_rows": plan.source_rows,
        }
        if digest(plan_body) != plan.plan_digest:
            raise DataError("migration plan digest mismatch")
        if plan.conflicts:
            raise ConflictError("migration plan contains unresolved conflicts")
        if self._records:
            raise ConflictError("initial migration requires an empty store")

        clean_records: list[dict[str, Any]] = []
        seen: set[str] = set()
        for record in plan.records:
            clean = validate_record(record, require_all=True)
            if clean != dict(record):
                raise DataError("migration plan record is not canonical")
            rid = clean["resident_id"]
            if rid in seen:
                raise ConflictError("duplicate resident in migration")
            seen.add(rid)
            clean_records.append(clean)

        for record in clean_records:
            rid = record["resident_id"]
            self._records[rid] = copy.deepcopy(record)
            self._versions[rid] = 1
            self._append_audit(
                action="MIGRATE_CREATE",
                actor_role=actor_role,
                resident_id=rid,
                before_version=0,
                after_version=1,
                changes=record,
            )
        return self.receipt()

    def view(self, resident_id: str, *, role: str, self_resident_id: str | None = None) -> dict[str, Any]:
        rid = _require_text("resident_id", resident_id, max_len=32).upper()
        if role not in ROLE_VIEW_FIELDS:
            raise PermissionDenied("unknown role")
        if role == "resident_self" and self_resident_id != rid:
            raise PermissionDenied("resident_self may view only own record")
        if rid not in self._records:
            raise DataError("resident not found")
        fields = ROLE_VIEW_FIELDS[role]
        return {
            "resident": {k: copy.deepcopy(v) for k, v in self._records[rid].items() if k in fields},
            "version": self._versions[rid],
        }

    def update(
        self,
        resident_id: str,
        *,
        expected_version: int,
        patch: Mapping[str, Any],
        actor_role: str,
    ) -> dict[str, Any]:
        rid = _require_text("resident_id", resident_id, max_len=32).upper()
        if rid not in self._records:
            raise DataError("resident not found")
        if type(expected_version) is not int or expected_version < 1:
            raise DataError("expected_version must be a positive integer")
        if self._versions[rid] != expected_version:
            raise StaleWriteError("stale resident version")
        if actor_role not in ROLE_WRITE_FIELDS:
            raise PermissionDenied("unknown role")
        if not isinstance(patch, Mapping) or not patch:
            raise DataError("patch must be a non-empty object")
        if "resident_id" in patch:
            raise DataError("resident_id is immutable")
        unauthorized = set(patch) - ROLE_WRITE_FIELDS[actor_role]
        if unauthorized:
            raise PermissionDenied(f"role cannot write fields: {sorted(unauthorized)}")
        clean_patch = validate_record(patch, require_all=False)
        candidate = {**self._records[rid], **clean_patch}
        candidate = validate_record(candidate, require_all=True)
        if candidate == self._records[rid]:
            raise DataError("no-op update rejected")
        before = self._versions[rid]
        after = before + 1
        self._records[rid] = candidate
        self._versions[rid] = after
        event = self._append_audit(
            action="UPDATE",
            actor_role=actor_role,
            resident_id=rid,
            before_version=before,
            after_version=after,
            changes=clean_patch,
        )
        return {"resident_id": rid, "version": after, "event_hash": event["event_hash"]}

    def analytics_export(self, *, role: str) -> dict[str, Any]:
        if role not in {"admin", "auditor", "program_director"}:
            raise PermissionDenied("role cannot export analytics")
        # Aggregate-only export: never emits a resident row or direct identifier.
        by_program = Counter(record["program"] for record in self._records.values())
        by_pgy = Counter(str(record["pgy_level"]) for record in self._records.values())
        by_status = Counter(record["training_status"] for record in self._records.values())
        result = {
            "record_count": len(self._records),
            "by_program": dict(sorted(by_program.items())),
            "by_pgy_level": dict(sorted(by_pgy.items())),
            "by_training_status": dict(sorted(by_status.items())),
        }
        # Defense in depth against accidental future identifier additions.
        if any(key in result for key in DIRECT_IDENTIFIERS):
            raise DataError("direct identifier escaped analytics boundary")
        return result

    def audit_events(self, *, role: str) -> tuple[dict[str, Any], ...]:
        if role not in {"admin", "auditor"}:
            raise PermissionDenied("role cannot read audit events")
        return tuple(copy.deepcopy(self._audit))

    def verify_audit(
        self,
        events: Iterable[Mapping[str, Any]] | None = None,
    ) -> bool:
        if not self._migration_rows:
            raise DataError("audit verification requires a retained source generation")
        candidate = list(copy.deepcopy(self._audit if events is None else list(events)))
        prev_hash = "0" * 64
        for expected_seq, event in enumerate(candidate, start=1):
            required = {
                "seq",
                "action",
                "actor_role",
                "resident_id",
                "before_version",
                "after_version",
                "changes_digest",
                "prev_hash",
                "event_hash",
            }
            if set(event) != required:
                raise AuditError("audit event shape invalid")
            if event["seq"] != expected_seq or event["prev_hash"] != prev_hash:
                raise AuditError("audit sequence/link invalid")
            if not isinstance(event["changes_digest"], str) or not _SHA256_RE.fullmatch(event["changes_digest"]):
                raise AuditError("audit changes digest invalid")
            payload = {k: event[k] for k in required - {"event_hash"}}
            expected_hash = digest(payload)
            if event["event_hash"] != expected_hash:
                raise AuditError("audit event hash invalid")
            prev_hash = expected_hash
        return True

    def receipt(self) -> dict[str, Any]:
        if not self._migration_rows:
            raise DataError("receipt requires a retained source generation")
        self.verify_audit()
        record_snapshot = [
            {"resident_id": rid, "version": self._versions[rid], "record": self._records[rid]}
            for rid in sorted(self._records)
        ]
        return {
            "schema": "osuchsh-gme-resident-data-receipt-v1",
            "record_count": len(record_snapshot),
            "records_digest": digest(record_snapshot),
            "audit_event_count": len(self._audit),
            "audit_head": self._audit[-1]["event_hash"] if self._audit else "0" * 64,
            "audit_valid": True,
            "clinical_decision_support": False,
            "live_osu_data_used": False,
        }
