from __future__ import annotations

from datetime import datetime
from typing import Any

from ._common import (
    SNAPSHOT_SCHEMA,
    QualificationInputError,
    _id_list,
    _identifier,
    _keys,
    _object,
)
from ._snapshot_capability import _parse_capability_evidence, _parse_partners
from ._snapshot_source import _parse_documents, _parse_source_capture

def _parse_snapshot(
    raw: Any,
    *,
    contract: dict[str, Any],
    evaluated: datetime,
    expected_rfp_sha256: str,
) -> dict[str, Any]:
    snap = _object(raw, "snapshot")
    _keys(snap, {"schema", "source_capture", "bidder", "partners", "capability_evidence"}, "snapshot")
    if snap["schema"] != SNAPSHOT_SCHEMA:
        raise QualificationInputError("unsupported snapshot schema")
    source, source_holds = _parse_source_capture(
        snap["source_capture"],
        contract=contract,
        evaluated=evaluated,
        expected_rfp_sha256=expected_rfp_sha256,
    )
    bidder = _object(snap["bidder"], "bidder")
    _keys(bidder, {"bidder_id", "organization_type", "hard_constraints", "documents"}, "bidder")
    bidder_id = _identifier(bidder["bidder_id"], "bidder.bidder_id")
    organization_type = _identifier(bidder["organization_type"], "bidder.organization_type")
    if organization_type not in {"CORPORATE", "NON_CORPORATE"}:
        raise QualificationInputError("bidder.organization_type invalid")
    hard_constraints = _id_list(bidder["hard_constraints"], "bidder.hard_constraints")
    documents, missing_documents, document_states = _parse_documents(
        bidder["documents"],
        contract=contract,
        evaluated=evaluated,
    )
    partners = _parse_partners(snap["partners"], evaluated=evaluated)
    if bidder_id in partners:
        raise QualificationInputError("bidder_id cannot also be a partner_id")
    coverage, uncommitted, stale_caps = _parse_capability_evidence(
        snap["capability_evidence"],
        bidder_id=bidder_id,
        partners=partners,
        contract=contract,
        evaluated=evaluated,
    )
    return {
        "source": source,
        "source_holds": source_holds,
        "bidder_id": bidder_id,
        "organization_type": organization_type,
        "hard_constraints": hard_constraints,
        "documents": documents,
        "missing_documents": missing_documents,
        "document_states": document_states,
        "partners": partners,
        "coverage": coverage,
        "uncommitted": uncommitted,
        "stale_caps": stale_caps,
    }
