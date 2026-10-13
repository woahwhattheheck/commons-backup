from __future__ import annotations

import re
from typing import Any

from _contract_support import (
    DetachedSigner,
    EvidenceInputError,
    LegFinding,
    MANIFEST_VERSION,
    SIGNATURE,
    STATUS_COMPLETE,
    STATUS_HOLD,
    _acknowledged,
    _canonical_bytes,
    _decimal,
    _fail,
    _identifier,
    _normalize_shipments,
    _plain,
    _sha256,
    _text,
    _ts,
    _walk_reject,
)

def _leg_findings(shipment: dict[str, Any]) -> tuple[list[LegFinding], list[dict[str, Any]]]:
    shipment_id = shipment["shipment_id"]
    legs = shipment["legs"]
    id_counts: dict[str, int] = {}
    for leg in legs:
        id_counts[leg["leg_id"].lower()] = id_counts.get(leg["leg_id"].lower(), 0) + 1
    by_id = {leg["leg_id"]: leg for leg in legs if id_counts[leg["leg_id"].lower()] == 1}
    by_sequence: dict[int, list[dict[str, Any]]] = {}
    for leg in legs:
        by_sequence.setdefault(leg["sequence"], []).append(leg)

    findings: list[LegFinding] = []
    projected: list[dict[str, Any]] = []
    for leg in sorted(legs, key=lambda item: (item["sequence"], item["leg_id"])):
        codes: set[str] = set()
        leg_id = leg["leg_id"]
        pickup = _ts(leg["pickup_at"], "pickup_at")
        handoff = _ts(leg["handoff_at"], "handoff_at")
        window_start = _ts(leg["window_start"], "window_start")
        window_end = _ts(leg["window_end"], "window_end")
        if not (pickup <= handoff and window_start <= window_end):
            codes.add("TIMESTAMP_ORDER_INVALID")
        if not leg["courier_id"] or not leg["custodian_from"] or not leg["custodian_to"]:
            codes.add("CUSTODY_GAP")

        if id_counts[leg_id.lower()] > 1:
            codes.add("LEG_GRAPH_INVALID")
        if leg["sequence"] == 1:
            if leg["predecessor_leg_id"] is not None:
                codes.add("LEG_GRAPH_INVALID")
        else:
            previous_candidates = by_sequence.get(leg["sequence"] - 1, [])
            predecessor = by_id.get(leg["predecessor_leg_id"] or "")
            if len(previous_candidates) != 1 or predecessor is None or predecessor not in previous_candidates:
                codes.add("LEG_GRAPH_INVALID")
            else:
                if predecessor["custodian_to"] != leg["custodian_from"]:
                    codes.add("CUSTODY_GAP")
                if _ts(predecessor["handoff_at"], "predecessor.handoff_at") > pickup:
                    codes.add("CUSTODY_GAP")
        if leg["sequence"] > 1 and not by_sequence.get(leg["sequence"] - 1):
            codes.add("LEG_GRAPH_INVALID")
        if len(by_sequence.get(leg["sequence"], [])) > 1:
            codes.add("LEG_GRAPH_INVALID")

        sensor = leg["sensor"]
        minimum = _decimal(sensor["min_temp_c"], "sensor.min_temp_c")
        maximum = _decimal(sensor["max_temp_c"], "sensor.max_temp_c")
        observed_min = _decimal(sensor["observed_min_c"], "sensor.observed_min_c")
        observed_max = _decimal(sensor["observed_max_c"], "sensor.observed_max_c")
        if minimum > maximum or observed_min > observed_max:
            codes.add("TEMPERATURE_RANGE_INVALID")
        if sensor["packout_id"] != leg["packout_id"]:
            codes.add("PACKOUT_TEMPERATURE_MISMATCH")
        excursion = observed_min < minimum or observed_max > maximum
        if excursion and not _acknowledged(leg["incidents"], "TEMP_EXCURSION"):
            codes.add("EXCURSION_UNACKNOWLEDGED")

        if not leg["documents"]:
            codes.add("DOCUMENT_INVALID")
        else:
            for document in leg["documents"]:
                valid_from = _ts(document["valid_from"], "document.valid_from")
                valid_until = _ts(document["valid_until"], "document.valid_until")
                if valid_from > pickup or valid_until < handoff:
                    codes.add("DOCUMENT_INVALID")
                    break

        breached = pickup < window_start or handoff > window_end
        if breached and not _acknowledged(leg["incidents"], "WINDOW_BREACH"):
            codes.add("WINDOW_BREACH_UNACKNOWLEDGED")

        recipient = leg["recipient"]
        pod = leg["pod"]
        if not recipient["recipient_id"] or not recipient["received_at"] or not pod["pod_id"] or not pod["signed_by"] or not pod["signed_at"]:
            codes.add("RECIPIENT_POD_INCOMPLETE")
        elif _ts(recipient["received_at"], "recipient.received_at") < handoff or _ts(pod["signed_at"], "pod.signed_at") < handoff:
            codes.add("RECIPIENT_POD_INCOMPLETE")

        ordered = tuple(sorted(codes))
        status = STATUS_HOLD if ordered else STATUS_COMPLETE
        findings.append(LegFinding(shipment_id, leg_id, leg["sequence"], status, ordered))
        projected.append(
            {
                "shipment_id": shipment_id,
                "service_line": shipment["service_line"],
                "material_class": shipment["material_class"],
                "leg_id": leg_id,
                "sequence": leg["sequence"],
                "status": status,
                "codes": list(ordered),
                "evidence_digest": _sha256(_canonical_bytes(leg)),
            }
        )
    return findings, projected


def prepare_manifest(shipments: Any) -> dict[str, Any]:
    _walk_reject(shipments)
    normalized = _normalize_shipments(shipments)
    all_findings: list[LegFinding] = []
    projected: list[dict[str, Any]] = []
    shipment_rows: list[dict[str, Any]] = []
    for shipment in normalized:
        findings, projection = _leg_findings(shipment)
        all_findings.extend(findings)
        projected.extend(projection)
        codes = sorted({code for finding in findings for code in finding.codes})
        shipment_rows.append(
            {
                "shipment_id": shipment["shipment_id"],
                "service_line": shipment["service_line"],
                "status": STATUS_HOLD if codes else STATUS_COMPLETE,
                "codes": codes,
                "evidence_digest": _sha256(_canonical_bytes(shipment)),
            }
        )

    held_legs = [finding for finding in all_findings if finding.status == STATUS_HOLD]
    held_shipments = [row for row in shipment_rows if row["status"] == STATUS_HOLD]
    code_counts: dict[str, int] = {}
    for finding in held_legs:
        for code in finding.codes:
            code_counts[code] = code_counts.get(code, 0) + 1

    core = {
        "version": MANIFEST_VERSION,
        "authority": "evidence-completeness-only",
        "dispatch_authorized": False,
        "release_authorized": False,
        "clinical_decision_inferred": False,
        "temperature_disposition_inferred": False,
        "customs_judgment_inferred": False,
        "summary": {
            "shipment_count": len(normalized),
            "complete_shipments": len(normalized) - len(held_shipments),
            "held_shipments": len(held_shipments),
            "leg_count": len(all_findings),
            "complete_legs": len(all_findings) - len(held_legs),
            "held_legs": len(held_legs),
            "hold_code_counts": dict(sorted(code_counts.items())),
            "service_lines": sorted({shipment["service_line"] for shipment in normalized}),
        },
        "shipments": sorted(shipment_rows, key=lambda row: row["shipment_id"]),
        "legs": sorted(projected, key=lambda row: (row["shipment_id"], row["sequence"], row["leg_id"])),
    }
    digest = _sha256(_canonical_bytes(core))
    return {**core, "manifest_digest": digest, "signature": None}


def validate_prepared_manifest(prepared: Any) -> dict[str, Any]:
    if not _plain(prepared):
        _fail("MALFORMED_INPUT", "prepared manifest must be an object")
    if prepared.get("signature") is not None:
        _fail("MALFORMED_INPUT", "prepared manifest already has a signature")
    digest = prepared.get("manifest_digest")
    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        _fail("MALFORMED_INPUT", "manifest_digest must be lowercase SHA-256")
    core = dict(prepared)
    core.pop("manifest_digest", None)
    core.pop("signature", None)
    if core.get("version") != MANIFEST_VERSION:
        _fail("MALFORMED_INPUT", f"manifest version must be {MANIFEST_VERSION}")
    actual = _sha256(_canonical_bytes(core))
    if actual != digest:
        _fail("MANIFEST_DIGEST_MISMATCH", "prepared manifest digest does not match its contents")
    return dict(prepared)


def attach_signature(prepared: Any, *, signer_id: Any, algorithm: Any, signature: Any) -> dict[str, Any]:
    validated = validate_prepared_manifest(prepared)
    signer = _identifier(signer_id, "signer_id")
    alg = _text(algorithm, "algorithm", maximum=100)
    sig = _text(signature, "signature", minimum=16, maximum=4096)
    if not SIGNATURE.fullmatch(sig):
        _fail("MALFORMED_INPUT", "signature must be printable base64/identifier-safe text")
    result = dict(validated)
    result["signature"] = {
        "signer_id": signer,
        "algorithm": alg,
        "covers": "manifest_digest_sha256",
        "value": sig,
    }
    return result


def sign_manifest(shipments: Any, signer: DetachedSigner) -> dict[str, Any]:
    prepared = prepare_manifest(shipments)
    signer_id = _identifier(signer.signer_id, "signer.signer_id")
    algorithm = _text(signer.algorithm, "signer.algorithm", maximum=100)
    try:
        raw_signature = signer.sign_digest(bytes.fromhex(prepared["manifest_digest"]))
    except Exception as exc:  # fail closed; signer implementation is externally supplied
        _fail("SIGNER_FAILURE", f"detached signer failed: {exc}")
    return attach_signature(prepared, signer_id=signer_id, algorithm=algorithm, signature=raw_signature)


def canonical_manifest_bytes(manifest: Any) -> bytes:
    if not _plain(manifest):
        _fail("MALFORMED_INPUT", "manifest must be an object")
    return _canonical_bytes(manifest) + b"\n"
