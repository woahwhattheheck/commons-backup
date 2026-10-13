#!/usr/bin/env python3
"""Fail-closed proposal readiness preflight for Grand Rapids RFP 920-45-269.

Proposal state is untrusted. The library can return READY only when trusted host
integration passes an already verified authority object. The public CLI never
loads authority bytes or trust-root material, so unprivileged CLI execution can
only produce HOLD or INVALID. The tool never submits, signs, contacts the buyer,
mutates a portal, awards, invoices, or moves money.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

try:
    from .trusted_authority import (
        GATE_EVIDENCE_KIND,
        HEX64,
        REQUIRED_GATES,
        VerifiedAuthority,
        canonical_json,
    )
except ImportError:
    from trusted_authority import (
        GATE_EVIDENCE_KIND,
        HEX64,
        REQUIRED_GATES,
        VerifiedAuthority,
        canonical_json,
    )

SCHEMA_VERSION = "grand-rapids-920-45-269-preflight/v2"
ALLOWED_STATUS = {"PASS", "HOLD"}
SOLICITATION_ID = "920-45-269"
SAFE_EVIDENCE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}")
MAX_STATE_BYTES = 1_048_576


def _load_json_strict(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if len(raw) > MAX_STATE_BYTES:
        raise ValueError(f"state exceeds {MAX_STATE_BYTES} bytes")
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise ValueError("state must be strict UTF-8") from exc

    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise ValueError(f"state contains duplicate key {key!r}")
            out[key] = value
        return out

    try:
        value = json.loads(text, object_pairs_hook=no_duplicates)
    except json.JSONDecodeError as exc:
        raise ValueError("state is not valid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("state root must be an object")
    return value


def _authority_ref(state: dict[str, Any], errors: list[str]) -> tuple[int | None, str | None]:
    ref = state.get("authority")
    if not isinstance(ref, dict) or set(ref) != {"generation", "authority_sha256"}:
        errors.append("authority must be an exact generation/authority_sha256 object")
        return None, None
    generation = ref.get("generation")
    digest = ref.get("authority_sha256")
    if generation is None and digest is None:
        return None, None
    if type(generation) is not int or generation < 1:
        errors.append("authority.generation must be null or an integer >= 1")
        return None, None
    if not isinstance(digest, str) or HEX64.fullmatch(digest) is None:
        errors.append("authority.authority_sha256 must be null or lowercase 64-hex")
        return None, None
    return generation, digest


def evaluate(
    state: dict[str, Any],
    authority: VerifiedAuthority | None = None,
    *,
    authority_error: str | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    blockers: list[dict[str, str]] = []
    resolved_evidence: list[dict[str, str]] = []

    if not isinstance(state, dict):
        state = {}
        errors.append("state must be an object")
    expected_top = {"schema_version", "solicitation_id", "authority", "gates"}
    if set(state) != expected_top:
        errors.append("state has unexpected or missing top-level keys")

    if state.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION!r}")
    if state.get("solicitation_id") != SOLICITATION_ID:
        errors.append(f"solicitation_id must be exactly {SOLICITATION_ID!r}")

    ref_generation, ref_digest = _authority_ref(state, errors)
    if authority_error:
        errors.append(f"trusted authority rejected: {authority_error}")

    if authority is not None and not isinstance(authority, VerifiedAuthority):
        errors.append("authority must be a trusted-host VerifiedAuthority")
        authority = None

    bound_authority = False
    if authority is not None:
        if ref_generation is None or ref_digest is None:
            errors.append("state must bind the trusted-host authority generation and digest")
        elif (
            ref_generation != authority.generation
            or ref_digest != authority.authority_sha256
        ):
            errors.append("state authority reference is stale or does not match the trusted host root")
        else:
            bound_authority = True

    gates = state.get("gates")
    if not isinstance(gates, dict):
        errors.append("gates must be an object")
        gates = {}
    missing = sorted(set(REQUIRED_GATES) - set(gates))
    unknown = sorted(set(gates) - set(REQUIRED_GATES))
    if missing:
        errors.append("missing gates: " + ", ".join(missing))
    if unknown:
        errors.append("unknown gates: " + ", ".join(unknown))

    for gate in REQUIRED_GATES:
        entry = gates.get(gate)
        if not isinstance(entry, dict):
            continue
        if set(entry) != {"status", "evidence", "reason"}:
            errors.append(f"gate {gate!r} must have exact status/evidence/reason keys")
            continue
        status = entry.get("status")
        if status not in ALLOWED_STATUS:
            errors.append(f"gate {gate!r} status must be PASS or HOLD")
            continue
        reason = entry.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            errors.append(f"gate {gate!r} requires a non-empty reason")
        evidence = entry.get("evidence")
        if not isinstance(evidence, list) or not all(isinstance(v, str) for v in evidence):
            errors.append(f"gate {gate!r} evidence must be a list of string authority IDs")
            evidence = []
        elif len(set(evidence)) != len(evidence):
            errors.append(f"gate {gate!r} evidence IDs must be unique")
        elif any(SAFE_EVIDENCE_ID.fullmatch(v) is None for v in evidence):
            errors.append(f"gate {gate!r} contains a non-canonical evidence ID")

        if status == "HOLD":
            blockers.append({
                "gate": gate,
                "reason": reason.strip() if isinstance(reason, str) else "missing reason",
            })
            continue

        if not evidence:
            errors.append(f"gate {gate!r} PASS requires at least one authority evidence ID")
            continue
        if not bound_authority:
            blockers.append({
                "gate": gate,
                "reason": "PASS claim is not resolved against trusted-host current authority",
            })
            continue

        expected_kind = GATE_EVIDENCE_KIND[gate]
        for evidence_id in evidence:
            record = authority.evidence(evidence_id) if authority is not None else None
            if record is None:
                errors.append(
                    f"gate {gate!r} evidence {evidence_id!r} is absent from trusted authority"
                )
                continue
            if record.gate != gate or record.kind != expected_kind:
                errors.append(
                    f"gate {gate!r} evidence {evidence_id!r} has wrong gate/type authority"
                )
            if record.source_generation_sha256 != authority.source_generation_sha256:
                errors.append(
                    f"gate {gate!r} evidence {evidence_id!r} is stale for the current packet/addenda generation"
                )
                continue
            if record.gate == gate and record.kind == expected_kind:
                resolved_evidence.append({
                    "gate": gate,
                    "id": record.id,
                    "kind": record.kind,
                    "sha256": record.sha256,
                })

    for hard_gate in (
        "controlling_packet_acquired",
        "packet_sha256_verified",
        "owner_release_to_submit",
    ):
        entry = gates.get(hard_gate)
        if not isinstance(entry, dict) or entry.get("status") != "PASS":
            if not any(row["gate"] == hard_gate for row in blockers):
                blockers.append({"gate": hard_gate, "reason": "hard fail-closed submission gate"})

    status = "INVALID" if errors else ("HOLD" if blockers else "READY")
    material = {
        "schema_version": state.get("schema_version"),
        "solicitation_id": state.get("solicitation_id"),
        "authority": state.get("authority"),
        "gates": gates,
    }
    digest = hashlib.sha256(canonical_json(material)).hexdigest()
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "solicitation_id": SOLICITATION_ID,
        "status": status,
        "state_sha256": digest,
        "trusted_authority": {
            "verified_current": bound_authority,
            "generation": authority.generation if bound_authority and authority is not None else None,
            "authority_sha256": authority.authority_sha256 if bound_authority and authority is not None else None,
            "source_generation_sha256": (
                authority.source_generation_sha256
                if bound_authority and authority is not None
                else None
            ),
        },
        "resolved_evidence": resolved_evidence,
        "blockers": blockers,
        "errors": errors,
        "authority": (
            "readiness-evidence-only; no portal mutation, signature, submission, "
            "award, payment, accounting, or revenue authority"
        ),
    }
    receipt["receipt_sha256"] = hashlib.sha256(canonical_json(receipt)).hexdigest()
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Unprivileged Grand Rapids proposal-state preflight. This CLI never loads "
            "trusted authority and therefore cannot produce READY."
        )
    )
    parser.add_argument("state", type=Path)
    parser.add_argument("--write-receipt", type=Path)
    args = parser.parse_args()

    try:
        state = _load_json_strict(args.state)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    receipt = evaluate(state)
    rendered = json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.write_receipt:
        args.write_receipt.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if receipt["status"] in {"HOLD", "READY"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
