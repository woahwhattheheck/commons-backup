"""Body-free receipts and persistent-state verification."""

from __future__ import annotations
import sqlite3
from typing import Any, Dict, List, Mapping
from .codec import canonical_json, digest, parse_json
from .constants import (
    ALL_STATES, DB_SCHEMA, DISPATCHING, RECEIPT_SCHEMA, RECONCILE_REQUIRED, SCHEMA,
)
from .errors import PacemakerError, StoreInvariantError
from .intent import normalize_intent


class StoreReadMixin:
    def export_intent(self, key: str) -> Dict[str, Any]:
        """Recover retained request content without claiming or changing it."""
        db = self._connect()
        try:
            row = db.execute("SELECT * FROM mutations WHERE mutation_key=?", (key,)).fetchone()
            if not row:
                raise PacemakerError("unknown mutation key")
            self._verify_row(row)
            return {
                "schema": "commons-github-content-write-recovery/v1",
                "intent": {
                    "schema": SCHEMA,
                    "mutationKey": row["mutation_key"],
                    "method": row["method"],
                    "apiPath": row["api_path"],
                    "description": row["description"],
                    "body": parse_json(bytes(row["body_json"])),
                },
                "receipt": self._receipt(row),
            }
        finally:
            db.close()

    def inspect(self, key: str) -> Dict[str, Any]:
        db = self._connect()
        try:
            row = db.execute("SELECT * FROM mutations WHERE mutation_key=?", (key,)).fetchone()
            if not row:
                raise PacemakerError("unknown mutation key")
            self._verify_row(row)
            return self._receipt(row)
        finally:
            db.close()

    def list_receipts(self) -> List[Dict[str, Any]]:
        db = self._connect()
        try:
            receipts = []
            for row in db.execute("SELECT * FROM mutations ORDER BY seq"):
                self._verify_row(row)
                receipts.append(self._receipt(row))
            return receipts
        finally:
            db.close()

    def verify(self) -> Dict[str, Any]:
        db = self._connect()
        try:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise StoreInvariantError("SQLite integrity check failed")
            mutation_count = 0
            unresolved = 0
            for row in db.execute("SELECT * FROM mutations ORDER BY seq"):
                self._verify_row(row)
                mutation_count += 1
                unresolved += row["state"] in {DISPATCHING, RECONCILE_REQUIRED}
            if unresolved > 1:
                raise StoreInvariantError("more than one unresolved provider effect")
            return {"schema": DB_SCHEMA, "integrity": "VALID",
                    "mutationCount": mutation_count,
                    "unresolvedEffectCount": unresolved,
                    "authority": {"callerAdmissionRequired": False,
                    "approvalGrantedByPacemaker": False,
                    "rawProviderWritersBlocked": False,
                    "directNetworkClientPresent": False}}
        finally:
            db.close()

    def _verify_row(self, row: sqlite3.Row) -> None:
        if row["state"] not in ALL_STATES:
            raise StoreInvariantError("unknown state")
        body = parse_json(bytes(row["body_json"]))
        if digest(canonical_json(body)) != row["body_sha256"]:
            raise StoreInvariantError("body digest mismatch")
        semantic = digest(canonical_json({"method": row["method"],
            "apiPath": row["api_path"], "bodySha256": row["body_sha256"]}))
        if semantic != row["semantic_sha256"]:
            raise StoreInvariantError("semantic digest mismatch")
        value = {"schema": SCHEMA, "mutationKey": row["mutation_key"],
                 "method": row["method"], "apiPath": row["api_path"],
                 "description": row["description"], "body": body}
        if normalize_intent(value).intent_sha256 != row["intent_sha256"]:
            raise StoreInvariantError("intent digest mismatch")

    def _receipt(self, row: Mapping[str, Any]) -> Dict[str, Any]:
        d = dict(row)
        receipt = {"schema": RECEIPT_SCHEMA, "sequence": d["seq"],
          "mutationKey": d["mutation_key"], "semanticSha256": d["semantic_sha256"],
          "intentSha256": d["intent_sha256"], "bodySha256": d["body_sha256"],
          "method": d["method"], "apiPath": d["api_path"],
          "descriptionSha256": digest(d["description"].encode()), "state": d["state"],
          "attemptCount": d["attempts"], "enqueuedAt": d["enqueued_at"],
          "updatedAt": d["updated_at"], "claimedAt": d["claimed_at"],
          "retryAt": d["retry_at"], "providerStatus": d["provider_status"],
          "providerReceiptSha256": d["provider_receipt_sha256"],
          "observationRefSha256": d["observation_ref_sha256"],
          "observationSha256": d["observation_sha256"], "reason": d["reason"],
          "authority": {"callerAdmissionRequired": False,
          "approvalGrantedByPacemaker": False, "rawProviderWritersBlocked": False,
          "distributedExclusionClaimed": False, "directNetworkClientPresent": False}}
        receipt["receiptSha256"] = digest(canonical_json(receipt))
        return receipt
