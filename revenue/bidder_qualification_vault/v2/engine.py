from __future__ import annotations

import copy
from typing import Any

from .constants import INPUT_SCHEMA, OUTPUT_SCHEMA, STATES
from .lineage import _generation_conflicts
from .model import normalize_input
from .resolve import _resolve_requirement
from .strict import RegistryError, _parse_utc, canonical_json, load_json_strict, sha256_hex


def compile_registry(payload: Any) -> dict[str, Any]:
    """Compile a deterministic candidate manifest over caller-supplied bytes.

    This function does not authenticate the source generation or own current
    time. Its strongest positive state is therefore CANDIDATE_VERIFIED, never
    current/bid-ready authority.
    """
    normalized = normalize_input(copy.deepcopy(payload))
    as_of = _parse_utc(normalized["as_of"], "root.as_of")
    assert as_of is not None
    conflicts, superseded_by, _ = _generation_conflicts(normalized["evidence"])
    results = [
        _resolve_requirement(req, normalized["evidence"], normalized["entity_id"], as_of, conflicts, superseded_by)
        for req in normalized["requirements"]
    ]
    counts = {state: 0 for state in sorted(STATES)}
    for result in results:
        counts[result["state"]] += 1
    candidate_complete = all(r["state"] == "CANDIDATE_VERIFIED" for r in results)
    output: dict[str, Any] = {
        "schema": OUTPUT_SCHEMA,
        "generation_id": normalized["generation_id"],
        "entity_id": normalized["entity_id"],
        "as_of": normalized["as_of"],
        "as_of_authority": "CALLER_SUPPLIED_NOT_CURRENT_AUTHORITY",
        "source_authentication": "NOT_PERFORMED",
        "registry_sha256": sha256_hex(normalized),
        "requirements": results,
        "counts": counts,
        "candidate_requirements_satisfied": candidate_complete,
        # Retained as a compatibility fence: this compiler can never mint it.
        "ready_for_bid_consumption": False,
        "authority": {
            "current_evidence_authority": False,
            "external_contact_authorized": False,
            "submission_authorized": False,
            "signature_authorized": False,
            "pricing_authorized": False,
            "payment_authorized": False,
            "award_or_revenue_claim_authorized": False,
        },
    }
    output["receipt_sha256"] = sha256_hex(output)
    return output


def verify_receipt(payload: Any, receipt: Any) -> bool:
    """Verify deterministic replay only; never promote the receipt to current authority."""
    if not isinstance(receipt, dict):
        return False
    try:
        expected = compile_registry(payload)
    except RegistryError:
        return False
    try:
        return canonical_json(expected) == canonical_json(receipt)
    except RegistryError:
        return False


def render_markdown(receipt: dict[str, Any]) -> str:
    if receipt.get("schema") != OUTPUT_SCHEMA:
        raise RegistryError("receipt.schema:UNSUPPORTED")
    lines = [
        "# Bid Evidence Candidate Manifest",
        "",
        f"- Generation: `{receipt['generation_id']}`",
        f"- Entity: `{receipt['entity_id']}`",
        f"- Caller as-of: `{receipt['as_of']}`",
        f"- As-of authority: `{receipt['as_of_authority']}`",
        f"- Source authentication: `{receipt['source_authentication']}`",
        f"- Registry SHA-256: `{receipt['registry_sha256']}`",
        f"- Receipt SHA-256: `{receipt['receipt_sha256']}`",
        f"- Candidate requirements satisfied: `{'YES' if receipt['candidate_requirements_satisfied'] else 'NO'}`",
        "- Ready for bid consumption: `NO`",
        "",
        "| Requirement | Category | Stage | Candidate state | Evidence | Evidence SHA-256 | Reason |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in receipt["requirements"]:
        evidence = row["evidence_id"] or "—"
        evidence_sha = row["evidence_sha256"] or "—"
        lines.append(
            f"| `{row['requirement_id']}` | `{row['category']}` | `{row['stage']}` | "
            f"`{row['state']}` | `{evidence}` | `{evidence_sha}` | `{row['reason']}` |"
        )
    lines.extend([
        "",
        "> Candidate/integrity review only. Source authentication is not performed and the caller-supplied as-of value is not current-time authority. A separate trusted consumer must authenticate the exact source/root and own current time before any operational promotion. This manifest grants no contact, signature, pricing, submission, payment, award, or revenue authority.",
        "",
    ])
    return "\n".join(lines)
