from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from unittest import mock

from revenue.organization_contact_pressure import compiler, gate, ledger_head, verifier


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def ts(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


class GateFixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.now = datetime(2026, 9, 14, 2, 55, 0, tzinfo=timezone.utc)
        self.key_id = "primary-20260914"
        self.verifier_id = "commons-host-1"
        self.key = bytes.fromhex("42" * 32)
        self.organization = digest("example-organization")
        self.route_a = digest("route-a")
        self.route_b = digest("route-b")
        self.route_c = digest("route-c")
        self.policy = {
            "policy_generation": 7,
            "contact_cooldown_seconds": 3600,
            "request_max_age_seconds": 600,
            "ledger_max_age_seconds": 600,
            "ready_validity_seconds": 120,
            "max_future_skew_seconds": 5,
        }
        self.authority_issued_at = self.now - timedelta(hours=1)
        self._make_dirs()
        self._write_active_key()
        self.write_authority()
        self.write_ledger([])

    def _make_dirs(self) -> None:
        for name in ("keys", "authorities", "ledgers"):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        (self.root / "ledger-heads" / self.organization).mkdir(parents=True, exist_ok=True)

    def _write_private(self, path: Path, data: bytes) -> None:
        path.write_bytes(data)
        if os.name != "nt":
            path.chmod(0o600)

    def _write_active_key(self) -> None:
        self._write_private(self.root / "keys" / f"{self.key_id}.key", self.key.hex().encode() + b"\n")
        pointer = {
            "schema": gate.KEY_POINTER_SCHEMA,
            "key_id": self.key_id,
            "verifier_id": self.verifier_id,
        }
        self._write_private(self.root / "active-key.json", gate._canonical_bytes(pointer) + b"\n")

    def authority_body(self, **overrides):
        body = {
            "schema": gate.AUTHORITY_SCHEMA,
            "organization_scope_sha256": self.organization,
            "route_scope_sha256s": sorted([self.route_a, self.route_b]),
            "policy": dict(self.policy),
            "issued_at": ts(self.authority_issued_at),
            "valid_until": ts(self.now + timedelta(days=1)),
            "key_id": self.key_id,
            "verifier_id": self.verifier_id,
        }
        body.update(overrides)
        return body

    def write_authority(self, *, key: Optional[bytes] = None, signature: Optional[str] = None, **overrides):
        body = self.authority_body(**overrides)
        document = {**body, "signature": signature or gate._hmac_hex(key or self.key, body)}
        path = self.root / "authorities" / f"{self.organization}.json"
        self._write_private(path, gate._canonical_bytes(document) + b"\n")
        return document

    def event_id(self, label: str) -> str:
        return label if len(label) == 64 and all(ch in "0123456789abcdef" for ch in label) else digest(f"event:{label}")

    def event(
        self,
        event_id: str,
        kind: str,
        *,
        route: Optional[str] = None,
        observed_at: Optional[datetime] = None,
        organization: Optional[str] = None,
        target_event_id: Optional[str] = None,
        source: Optional[str] = None,
        provider: Optional[str] = None,
    ):
        return {
            "event_id": self.event_id(event_id),
            "organization_scope_sha256": organization or self.organization,
            "route_scope_sha256": route or self.route_a,
            "kind": kind,
            "observed_at": ts(observed_at or (self.now - timedelta(minutes=10))),
            "source_ref_sha256": source or digest(f"source:{event_id}"),
            "provider_evidence_sha256": provider or digest(f"provider:{event_id}"),
            "target_event_id": self.event_id(target_event_id) if target_event_id is not None else None,
        }

    def ledger_body(self, events, *, generation: Optional[int] = None, updated_at: Optional[datetime] = None, **overrides):
        normalized = []
        for event in events:
            row, view = gate._normalize_event(event)
            normalized.append((view.observed_at, view.event_id, view.canonical, row))
        normalized.sort(key=lambda item: (item[0], item[1], item[2]))
        rows = [item[3] for item in normalized]
        seen = {}
        canonical_rows = []
        for row in rows:
            row_bytes = gate._canonical_bytes(row)
            prior = seen.get(row["event_id"])
            if prior is None:
                seen[row["event_id"]] = row_bytes
                canonical_rows.append(row)
            elif prior != row_bytes:
                canonical_rows.append(row)
        rows = canonical_rows
        unique_ids = set(seen)
        body = {
            "schema": gate.LEDGER_SCHEMA,
            "organization_scope_sha256": self.organization,
            "generation": len(unique_ids) if generation is None else generation,
            "policy_generation": self.policy["policy_generation"],
            "updated_at": ts(updated_at or self.now),
            "events": rows,
            "key_id": self.key_id,
            "verifier_id": self.verifier_id,
        }
        body.update(overrides)
        return body

    def write_ledger_head(
        self,
        document: dict,
        *,
        key: Optional[bytes] = None,
        signature: Optional[str] = None,
        committed_at: Optional[datetime] = None,
    ):
        canonical = gate._canonical_bytes(document)
        state_body = {
            field: value
            for field, value in document.items()
            if field not in {"signature", "updated_at"}
        }
        body = {
            "schema": ledger_head.LEDGER_HEAD_SCHEMA,
            "organization_scope_sha256": self.organization,
            "policy_generation": document["policy_generation"],
            "ledger_generation": document["generation"],
            "ledger_state_sha256": gate._sha256(gate._canonical_bytes(state_body)),
            "ledger_sha256": gate._sha256(canonical),
            "ledger_updated_at": document["updated_at"],
            "committed_at": ts(
                committed_at
                or gate._parse_time(document["updated_at"], "ledger.updated_at")
            ),
            "key_id": self.key_id,
            "verifier_id": self.verifier_id,
        }
        checkpoint = {**body, "signature": signature or gate._hmac_hex(key or self.key, body)}
        path = self.root / "ledger-heads" / self.organization / ledger_head._ledger_head_filename(body)
        data = gate._canonical_bytes(checkpoint) + b"\n"
        if path.exists():
            if path.read_bytes() != data:
                raise RuntimeError("ledger head filename collision")
        else:
            self._write_private(path, data)
        return checkpoint

    def write_ledger(
        self,
        events,
        *,
        key: Optional[bytes] = None,
        signature: Optional[str] = None,
        generation: Optional[int] = None,
        updated_at: Optional[datetime] = None,
        raw_document: Optional[dict] = None,
        write_head: bool = True,
        **overrides,
    ):
        if raw_document is None:
            body = self.ledger_body(events, generation=generation, updated_at=updated_at, **overrides)
            document = {**body, "signature": signature or gate._hmac_hex(key or self.key, body)}
        else:
            document = raw_document
        path = self.root / "ledgers" / f"{self.organization}.json"
        self._write_private(path, gate._canonical_bytes(document) + b"\n")
        if write_head:
            self.write_ledger_head(document)
        return document

    def request(self, *, route: Optional[str] = None, requested_at: Optional[datetime] = None, **overrides):
        body = {
            "schema": gate.REQUEST_SCHEMA,
            "organization_scope_sha256": self.organization,
            "proposed_route_scope_sha256": route or self.route_a,
            "proposed_event_id": self.event_id("proposal-zrt-1"),
            "operation_id": "ORG-CONTACT-PRESSURE-GATE-ZRTP3X9-20260913",
            "requested_at": ts(requested_at or self.now),
            "source_ref_sha256": digest("request-source"),
        }
        body.update(overrides)
        return gate._canonical_bytes(body)

    def compile(self, request: Optional[bytes] = None, *, now: Optional[datetime] = None):
        with mock.patch.object(compiler, "_authority_root", return_value=self.root), mock.patch.object(
            compiler, "_utc_now", return_value=now or self.now
        ):
            return gate.compile_current(request or self.request())

    def verify_integrity(self, receipt) -> dict:
        data = receipt if isinstance(receipt, bytes) else self.receipt_bytes(receipt)
        with mock.patch.object(verifier, "_authority_root", return_value=self.root):
            return gate.verify_receipt_integrity(data)

    def verify_current(self, receipt, *, now: Optional[datetime] = None) -> dict:
        data = receipt if isinstance(receipt, bytes) else self.receipt_bytes(receipt)
        with mock.patch.object(verifier, "_authority_root", return_value=self.root), mock.patch.object(
            verifier, "_utc_now", return_value=now or self.now
        ):
            return gate.verify_receipt_current(data)

    def receipt_bytes(self, receipt) -> bytes:
        return gate._canonical_bytes(receipt) + b"\n"
