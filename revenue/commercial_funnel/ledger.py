from __future__ import annotations

from collections import defaultdict
from typing import Any

from .common import (
    HOLD,
    INPUT_SCHEMA,
    MAX_EVIDENCE_AGE_SECONDS,
    MAX_OPPORTUNITIES,
    PACKET_SCHEMA,
    READY,
    RECEIPT_SCHEMA,
    STAGES,
    STAGE_INDEX,
    FunnelError,
    canonical_json,
    exact_keys,
    parse_time,
    require_id,
    sha256,
    strict_loads,
    validate_json_scalars,
    validate_source,
)
from .model import csv_bytes, markdown_bytes, metrics, normalize_opportunity, source_key


def _hold(opportunities: list[dict[str, Any]], impacted: set[str], reason: str) -> None:
    for opp in opportunities:
        if opp["id"] in impacted:
            opp["hold_reasons"] = sorted(set(opp["hold_reasons"]) | {reason})
            opp["state"] = HOLD
            opp["next_evidence_needed"] = "REVIEW_HOLD_REASONS"


def _semantic_digest_projection(raw: dict[str, Any], field: str) -> dict[str, Any]:
    """Canonicalize provider identity without erasing raw-input conflict evidence.

    GitHub repository owner/name identity is case-insensitive. The authority model
    already validates and case-folds source identities before role/reuse checks;
    the packet input digest must apply the same equivalence. Other raw event
    fields remain untouched so conflicting same-ID rows still bind distinct input
    bytes instead of disappearing behind normalized event retention.
    """
    digest_opp = dict(raw)
    offer = dict(raw["offer"])
    offer["source"] = validate_source(offer["source"], f"{field}.offer.source")
    digest_opp["offer"] = offer

    unique_events: dict[bytes, dict[str, Any]] = {}
    for i, event in enumerate(raw["events"]):
        digest_event = dict(event)
        digest_event["evidence"] = validate_source(
            event["evidence"], f"{field}.events[{i}].evidence"
        )
        unique_events[canonical_json(digest_event)] = digest_event
    digest_opp["events"] = [unique_events[key] for key in sorted(unique_events)]
    return digest_opp


def compile_funnel(value: Any, *, as_of: str) -> dict[str, Any]:
    validate_json_scalars(value)
    root = exact_keys(value, required=("schema", "opportunities"), field="$")
    if root["schema"] != INPUT_SCHEMA:
        raise FunnelError("unsupported input schema")
    evaluated = parse_time(as_of, "as_of")
    raw_opportunities = root["opportunities"]
    if not isinstance(raw_opportunities, list) or not raw_opportunities or len(raw_opportunities) > MAX_OPPORTUNITIES:
        raise FunnelError(f"opportunities must contain 1..{MAX_OPPORTUNITIES} items")

    normalized: list[dict[str, Any]] = []
    ids: set[str] = set()
    event_evidence_owners: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    offer_source_owners: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    offer_identity_sources: dict[
        tuple[str, str, str],
        dict[tuple[str, str, str, str], set[str]],
    ] = defaultdict(lambda: defaultdict(set))

    for i, raw in enumerate(raw_opportunities):
        opp, usage = normalize_opportunity(raw, f"opportunities[{i}]", evaluated)
        if opp["id"] in ids:
            raise FunnelError(f"duplicate opportunity id: {opp['id']}")
        ids.add(opp["id"])
        normalized.append(opp)
        for key, owners in usage.items():
            event_evidence_owners[key].update(owners)

        offer_key = source_key(opp["offer"]["source"])
        offer_source_owners[offer_key].add(opp["id"])
        identity = (opp["family"], opp["offer"]["id"], opp["offer"]["version"])
        offer_identity_sources[identity][offer_key].add(opp["id"])

    cross_reused = {
        key: owners for key, owners in event_evidence_owners.items() if len(owners) > 1
    }
    if cross_reused:
        _hold(
            normalized,
            set().union(*cross_reused.values()),
            "EVIDENCE_REUSED_ACROSS_OPPORTUNITIES",
        )

    # Offer-definition bytes and commercial-event evidence are different semantic
    # roles. Rebinding one immutable object across those roles is ambiguous even
    # when the uses occur in different opportunities.
    cross_role_keys = set(event_evidence_owners) & set(offer_source_owners)
    if cross_role_keys:
        impacted: set[str] = set()
        for key in cross_role_keys:
            impacted.update(event_evidence_owners[key])
            impacted.update(offer_source_owners[key])
        _hold(normalized, impacted, "EVIDENCE_ROLE_CONFLICT")

    # One logical offer version has one immutable definition. Multiple
    # opportunities may reference that same definition, but the same logical
    # identity cannot silently resolve to different source objects.
    for sources in offer_identity_sources.values():
        if len(sources) > 1:
            _hold(
                normalized,
                set().union(*sources.values()),
                "OFFER_SOURCE_IDENTITY_CONFLICT",
            )

    normalized.sort(key=lambda opp: opp["id"])
    packet_metrics = metrics(normalized)
    overall = READY if packet_metrics["held_opportunity_count"] == 0 else HOLD
    digest_opportunities = [
        _semantic_digest_projection(raw, f"opportunities[{i}]")
        for i, raw in enumerate(raw_opportunities)
    ]
    digest_opportunities.sort(
        key=lambda item: (require_id(item["id"], "opportunity.id"), canonical_json(item))
    )
    input_digest = sha256(
        canonical_json({"schema": INPUT_SCHEMA, "opportunities": digest_opportunities})
    )
    authority = {
        "buyer_contact_authorized": False,
        "acceptance_authorized": False,
        "contract_execution_authorized": False,
        "fulfillment_authorized": False,
        "transfer_authorized": False,
        "payment_or_provider_mutation_authorized": False,
        "cash_availability_asserted": False,
        "accounting_or_tax_authority": False,
        "revenue_recognition_authorized": False,
    }
    packet_base = {
        "schema": PACKET_SCHEMA,
        "state": overall,
        "evaluated_at": as_of,
        "max_evidence_age_seconds": MAX_EVIDENCE_AGE_SECONDS,
        "input_sha256": input_digest,
        "metrics": packet_metrics,
        "opportunities": normalized,
        "authority": authority,
    }
    json_bytes = canonical_json(packet_base)
    report_csv = csv_bytes(normalized)
    report_markdown = markdown_bytes(packet_base)
    outputs = {
        "report_json_sha256": sha256(json_bytes),
        "report_csv_sha256": sha256(report_csv),
        "report_markdown_sha256": sha256(report_markdown),
    }
    packet = dict(packet_base)
    packet["outputs"] = outputs
    packet_sha = sha256(canonical_json(packet))
    receipt_base = {
        "schema": RECEIPT_SCHEMA,
        "state": overall,
        "evaluated_at": as_of,
        "input_sha256": input_digest,
        "packet_sha256": packet_sha,
        "outputs": outputs,
        "authority": authority,
    }
    receipt = dict(receipt_base)
    receipt["receipt_sha256"] = sha256(canonical_json(receipt_base))
    return {"packet": packet, "receipt": receipt, "json": json_bytes, "csv": report_csv, "markdown": report_markdown}


def verify_compilation(value: Any, *, as_of: str, packet: Any, receipt: Any) -> bool:
    try:
        expected = compile_funnel(value, as_of=as_of)
        if not isinstance(packet, dict) or not isinstance(receipt, dict):
            return False
        if canonical_json(packet) != canonical_json(expected["packet"]):
            return False
        if canonical_json(receipt) != canonical_json(expected["receipt"]):
            return False
        receipt_without_digest = {key: val for key, val in receipt.items() if key != "receipt_sha256"}
        return receipt.get("receipt_sha256") == sha256(canonical_json(receipt_without_digest))
    except (FunnelError, TypeError, ValueError, OverflowError):
        return False


def verify_artifacts(
    value: Any,
    *,
    as_of: str,
    packet: Any,
    receipt: Any,
    report_json: bytes,
    report_csv: bytes,
    report_markdown: bytes,
) -> bool:
    """Byte-verify an artifact set at its explicitly supplied historical instant."""
    try:
        expected = compile_funnel(value, as_of=as_of)
        if not verify_compilation(value, as_of=as_of, packet=packet, receipt=receipt):
            return False
        return (
            report_json == expected["json"]
            and report_csv == expected["csv"]
            and report_markdown == expected["markdown"]
            and receipt.get("outputs", {}).get("report_json_sha256") == sha256(report_json)
            and receipt.get("outputs", {}).get("report_csv_sha256") == sha256(report_csv)
            and receipt.get("outputs", {}).get("report_markdown_sha256") == sha256(report_markdown)
        )
    except (FunnelError, TypeError, ValueError, OverflowError):
        return False


def verify_artifacts_current(
    value: Any,
    *,
    trusted_now: str,
    packet: Any,
    receipt: Any,
    report_json: bytes,
    report_csv: bytes,
    report_markdown: bytes,
) -> bool:
    """Verify original bytes and independently re-evaluate time-sensitive truth now.

    The receipt's own evaluation instant is used only to prove that the stored
    bytes are the exact deterministic result originally emitted. Currentness is
    established separately against trusted runtime UTC, never a time selected by
    the artifact or caller.
    """
    try:
        if not isinstance(packet, dict) or not isinstance(receipt, dict):
            return False
        evaluated_at = receipt.get("evaluated_at")
        if not isinstance(evaluated_at, str):
            return False
        evaluated = parse_time(evaluated_at, "receipt.evaluated_at")
        current_time = parse_time(trusted_now, "trusted_now")
        if evaluated > current_time:
            return False

        if not verify_artifacts(
            value,
            as_of=evaluated_at,
            packet=packet,
            receipt=receipt,
            report_json=report_json,
            report_csv=report_csv,
            report_markdown=report_markdown,
        ):
            return False

        current_packet = compile_funnel(value, as_of=trusted_now)["packet"]
        # These fields contain the time-sensitive semantic truth of the packet.
        # Output hashes and evaluated_at intentionally differ when re-evaluated.
        semantic_fields = (
            "schema",
            "state",
            "max_evidence_age_seconds",
            "input_sha256",
            "metrics",
            "opportunities",
            "authority",
        )
        return all(
            canonical_json(packet.get(field)) == canonical_json(current_packet.get(field))
            for field in semantic_fields
        )
    except (FunnelError, TypeError, ValueError, OverflowError):
        return False


__all__ = [
    "HOLD",
    "INPUT_SCHEMA",
    "PACKET_SCHEMA",
    "READY",
    "RECEIPT_SCHEMA",
    "STAGES",
    "STAGE_INDEX",
    "FunnelError",
    "canonical_json",
    "compile_funnel",
    "strict_loads",
    "verify_artifacts",
    "verify_artifacts_current",
    "verify_compilation",
]
