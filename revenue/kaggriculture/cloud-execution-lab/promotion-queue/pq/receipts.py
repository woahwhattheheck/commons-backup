# SPDX-License-Identifier: Apache-2.0
"""Tamper-evident promotion receipts.

A receipt binds the queue pin, the per-predecessor gate bundles, the gate
verdicts, and the policy version into one canonical JSON document. The
``integrity.digest`` field is the SHA-256 of the canonical encoding of
the receipt *without* the digest itself; ``verify_receipt`` recomputes it,
so any edit to inputs, results, or metadata invalidates the receipt.
Receipts for repeated attempts on one submission form a hash chain via
``integrity.prev_receipt_digest``.

This is tamper-*evident*, not key-signed: anyone can recompute the digest
and confirm the bytes are unchanged. Key-based signing is future work
(see README).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping

from . import RECEIPT_TYPE, SCHEMA_VERSION
from .pinning import canonical_json, utcnow_iso
from .signing import SIGNATURE_ALGORITHM, sign_receipt, verify_signature


def receipt_digest(body: Mapping) -> str:
    """Digest of the canonical receipt body (integrity.digest and any
    integrity.signature excluded: the digest seals the unsigned body, and
    the signature in turn covers the sealed digest)."""
    scrubbed = dict(body)
    integrity = dict(scrubbed.get("integrity", {}))
    integrity.pop("digest", None)
    integrity.pop("signature", None)
    scrubbed["integrity"] = integrity
    return hashlib.sha256(canonical_json(scrubbed)).hexdigest()


class ReceiptStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.dir = self.root / "receipts"
        self.dir.mkdir(parents=True, exist_ok=True)

    def build(
        self,
        *,
        submission_id: str,
        attempt_n: int,
        policy_version: str,
        pin_manifest: Mapping,
        predecessors: Mapping,
        comparisons: list[Mapping],
        verdict: str,
        timings: Mapping,
        prev_receipt_digest: str | None,
        extra: Mapping | None = None,
        signing_key: bytes | None = None,
    ) -> dict:
        body = {
            "schema_version": SCHEMA_VERSION,
            "receipt_type": RECEIPT_TYPE,
            "receipt_id": f"r-{submission_id}-a{attempt_n}",
            "submission_id": submission_id,
            "attempt": attempt_n,
            "created_at": utcnow_iso(),
            "policy_version": policy_version,
            "verdict": verdict,
            "queue_pin": {
                "pin_id": pin_manifest["pin_id"],
                "input_digest": pin_manifest["input_digest"],
                "inputs": {
                    name: {
                        "sha256": rec["sha256"],
                        "bytes": rec["bytes"],
                    }
                    for name, rec in pin_manifest["inputs"].items()
                },
            },
            "predecessors": predecessors,
            "comparisons": comparisons,
            "timings": timings,
            "integrity": {
                "algorithm": "sha256-canonical-json-v1",
                "digest": None,
                "prev_receipt_digest": prev_receipt_digest,
            },
        }
        if extra:
            body["extra"] = dict(extra)
        if signing_key is not None:
            body["integrity"]["algorithm"] = SIGNATURE_ALGORITHM
        body["integrity"]["digest"] = receipt_digest(body)
        if signing_key is not None:
            body["integrity"]["signature"] = sign_receipt(body, signing_key)
        return body

    def save(self, receipt: Mapping) -> Path:
        path = self.dir / f"{receipt['receipt_id']}.json"
        path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return path

    def load(self, receipt_id: str) -> dict:
        path = self.dir / f"{receipt_id}.json"
        if not path.is_file():
            raise KeyError(f"unknown receipt: {receipt_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def verify(self, receipt: Mapping, signing_key: bytes | None = None) -> tuple[bool, str]:
        """Recompute the digest; returns (ok, reason).

        When ``signing_key`` is provided, also verifies the key signature,
        so a consumer can confirm both integrity and attribution."""
        stored = (receipt.get("integrity") or {}).get("digest")
        if not stored:
            return False, "missing integrity.digest"
        if receipt_digest(receipt) != stored:
            return False, "digest mismatch: receipt bytes were modified"
        if signing_key is not None:
            return verify_signature(receipt, signing_key)
        return True, "ok"
