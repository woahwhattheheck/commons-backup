from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping

from revenue.travelers_agent_toolcall_evidence.gate import (
    GateError,
    build_ledger,
    canonical_bytes,
    compile_batch,
    daily_root_manifest,
    sha256_json,
    verify_batch,
    verify_ledger,
    verify_root,
)


BUNDLE_SCHEMA = "agent-toolcall-evidence-bundle/v1"


def build_evidence_bundle(
    envelopes: Iterable[Mapping[str, Any]],
    day: str,
    policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    materialized_envelopes = [deepcopy(dict(item)) for item in envelopes]
    receipts = compile_batch(materialized_envelopes, policy)
    ledger = build_ledger(receipts)
    root = daily_root_manifest(ledger, day)
    bundle = {
        "schema": BUNDLE_SCHEMA,
        "day": day,
        "envelopes_sha256": sha256_json(materialized_envelopes),
        "receipts_sha256": sha256_json(receipts),
        "ledger_sha256": sha256_json(ledger),
        "root_sha256": sha256_json(root),
        "receipts": receipts,
        "ledger": ledger,
        "root": root,
    }
    bundle["bundle_sha256"] = sha256_json(bundle)
    return bundle


def verify_evidence_bundle(
    envelopes: Iterable[Mapping[str, Any]],
    bundle: Mapping[str, Any],
    policy: Mapping[str, Any] | None = None,
) -> bool:
    try:
        materialized_envelopes = [deepcopy(dict(item)) for item in envelopes]
        supplied = deepcopy(dict(bundle))
        if set(supplied) != {
            "schema",
            "day",
            "envelopes_sha256",
            "receipts_sha256",
            "ledger_sha256",
            "root_sha256",
            "receipts",
            "ledger",
            "root",
            "bundle_sha256",
        }:
            return False
        if supplied.get("schema") != BUNDLE_SCHEMA:
            return False
        day = supplied.get("day")
        if type(day) is not str:
            return False
        receipts = supplied.get("receipts")
        ledger = supplied.get("ledger")
        root = supplied.get("root")
        if type(receipts) is not list or type(ledger) is not list or type(root) is not dict:
            return False

        # Semantic proof: detached receipts must be exactly reproducible from the
        # admitted envelopes under the same validated policy generation. Rehashing
        # a forged receipt, including widened scope/currentness, cannot satisfy it.
        if not verify_batch(materialized_envelopes, receipts, policy):
            return False

        # Structural proof: rebuild the canonical chain from semantically verified
        # receipts, verify the supplied full chain, then build/verify the v2 root.
        # The root builder itself also refuses an invalid complete ledger.
        expected_ledger = build_ledger(receipts)
        if canonical_bytes(expected_ledger) != canonical_bytes(ledger):
            return False
        if not verify_ledger(ledger):
            return False
        expected_root = daily_root_manifest(ledger, day)
        if canonical_bytes(expected_root) != canonical_bytes(root):
            return False
        if not verify_root(root, ledger):
            return False

        if supplied.get("envelopes_sha256") != sha256_json(materialized_envelopes):
            return False
        if supplied.get("receipts_sha256") != sha256_json(receipts):
            return False
        if supplied.get("ledger_sha256") != sha256_json(ledger):
            return False
        if supplied.get("root_sha256") != sha256_json(root):
            return False

        claimed = supplied.pop("bundle_sha256", None)
        return claimed == sha256_json(supplied)
    except (GateError, KeyError, TypeError, ValueError):
        return False
