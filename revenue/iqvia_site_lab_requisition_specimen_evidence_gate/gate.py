"""Deterministic, read-only requisition-to-specimen declared-evidence gate.

Version 2 evaluates eight closed source-record projections. Every source reference
is recomputed from the exact canonical source record before any operational
classification is derived. This proves internal consistency of the declared
evidence generation only; it does not authenticate an external provider or source.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from datetime import datetime, timezone
from typing import Any, Iterable

SCHEMA = "iqvia-site-lab-requisition-specimen-evidence-gate/v2"
AUTHORITY = "EVIDENCE_ONLY_HUMAN_SITE_LAB_RESOLUTION"
STATUS_READY = "EVIDENCE_CONSISTENT_FOR_HUMAN_REVIEW"
STATUS_HOLD = "HOLD"
SOURCE_REF_KIND = "CANONICAL_DECLARED_SOURCE_RECORD_SHA256"

CODES = (
    "PROTOCOL_VISIT_MISMATCH",
    "REQUISITION_GENERATION_MISMATCH",
    "KIT_INVALID_FOR_COLLECTION",
    "COLLECTION_WINDOW_BREACH",
    "COURIER_EVIDENCE_INVALID",
    "ACCESSION_METHOD_INCOMPATIBLE",
    "UNRESOLVED_QUERY",
)

SOURCE_KEYS = (
    "protocol",
    "requisition",
    "kit",
    "collection",
    "courier",
    "accession",
    "method",
    "queries",
)

PACKET_KEYS = {"schema", "packet_id", "sources", "source_refs"}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")


class EvidenceError(ValueError):
    """Raised when input cannot be treated as one closed evidence generation."""


def _assert_json_domain(value: Any, field: str, depth: int = 0) -> None:
    if depth > 12:
        raise EvidenceError(f"{field} exceeds maximum nesting depth")
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise EvidenceError(f"{field} contains a non-finite number")
        return
    if type(value) is list:
        if len(value) > 10000:
            raise EvidenceError(f"{field} contains an oversized list")
        for idx, item in enumerate(value):
            _assert_json_domain(item, f"{field}[{idx}]", depth + 1)
        return
    if type(value) is dict:
        if len(value) > 128:
            raise EvidenceError(f"{field} contains an oversized object")
        for key, item in value.items():
            if type(key) is not str:
                raise EvidenceError(f"{field} object keys must be strings")
            _assert_json_domain(item, f"{field}.{key}", depth + 1)
        return
    raise EvidenceError(f"{field} must contain only exact JSON-domain values")


def canonical_bytes(value: Any) -> bytes:
    _assert_json_domain(value, "value")
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise EvidenceError("value must be canonical JSON") from exc


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _exact_dict(value: Any, keys: set[str], field: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise EvidenceError(f"{field} must be an exact JSON object")
    if set(value) != keys:
        raise EvidenceError(f"{field} must contain exactly {sorted(keys)}")
    return dict(value)


def _bounded_text(value: Any, field: str, limit: int = 256) -> str:
    if type(value) is not str or not value or len(value.encode("utf-8")) > limit:
        raise EvidenceError(f"{field} must be a bounded non-empty string")
    return value


def _identifier(value: Any, field: str) -> str:
    text = _bounded_text(value, field, 128)
    if not ID_RE.fullmatch(text):
        raise EvidenceError(f"{field} is not a canonical identifier")
    return text


def _hash(value: Any, field: str) -> str:
    text = _bounded_text(value, field, 64)
    if not HASH_RE.fullmatch(text):
        raise EvidenceError(f"{field} must be lowercase sha256 hex")
    return text


def _time_text(value: Any, field: str) -> str:
    text = _bounded_text(value, field, 40)
    if not text.endswith("Z"):
        raise EvidenceError(f"{field} must be UTC RFC3339 ending in Z")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise EvidenceError(f"{field} must be RFC3339") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise EvidenceError(f"{field} must be UTC")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _time(value: Any, field: str) -> datetime:
    return datetime.fromisoformat(_time_text(value, field)[:-1] + "+00:00")


def _number(value: Any, field: str, lo: float, hi: float) -> float:
    if type(value) not in (int, float):
        raise EvidenceError(f"{field} must be numeric")
    out = float(value)
    if not math.isfinite(out) or out < lo or out > hi:
        raise EvidenceError(f"{field} must be finite in [{lo}, {hi}]")
    return out


def _optional_number(value: Any, field: str, lo: float, hi: float) -> float | None:
    if value is None:
        return None
    return _number(value, field, lo, hi)


def _optional_id(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _identifier(value, field)


def _sample_types(value: Any) -> list[str]:
    if type(value) is not list or not 1 <= len(value) <= 32:
        raise EvidenceError("method.allowed_sample_types must be a bounded non-empty list")
    items = [_identifier(item, "method.allowed_sample_types[]") for item in value]
    if len(items) != len(set(items)):
        raise EvidenceError("method.allowed_sample_types contains duplicates")
    return sorted(items)


def _query_items(value: Any) -> list[dict[str, Any]]:
    if type(value) is not list or len(value) > 64:
        raise EvidenceError("queries.items must be a bounded list")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for idx, raw in enumerate(value):
        obj = _exact_dict(
            raw,
            {"query_id", "status", "resolution_evidence_hash"},
            f"queries.items[{idx}]",
        )
        query_id = _identifier(obj["query_id"], f"queries.items[{idx}].query_id")
        if query_id in seen:
            raise EvidenceError("queries.items contains duplicate query_id")
        seen.add(query_id)
        status = _bounded_text(obj["status"], f"queries.items[{idx}].status", 32)
        if status not in {"OPEN", "RESOLVED"}:
            raise EvidenceError("query status must be OPEN or RESOLVED")
        evidence = obj["resolution_evidence_hash"]
        if status == "RESOLVED":
            evidence = _hash(evidence, f"queries.items[{idx}].resolution_evidence_hash")
        elif evidence is not None:
            raise EvidenceError("OPEN query cannot carry resolution evidence")
        out.append(
            {
                "query_id": query_id,
                "status": status,
                "resolution_evidence_hash": evidence,
            }
        )
    return sorted(out, key=lambda row: row["query_id"])


def compute_source_refs(sources: Any) -> dict[str, str]:
    """Hash each exact declared source record before semantic normalization."""
    obj = _exact_dict(sources, set(SOURCE_KEYS), "sources")
    refs: dict[str, str] = {}
    for key in SOURCE_KEYS:
        if type(obj[key]) is not dict:
            raise EvidenceError(f"sources.{key} must be an exact JSON object")
        refs[key] = sha256_value(obj[key])
    return refs


def _source_refs(value: Any) -> dict[str, str]:
    obj = _exact_dict(value, set(SOURCE_KEYS), "source_refs")
    return {key: _hash(obj[key], f"source_refs.{key}") for key in SOURCE_KEYS}


def _normalize_sources(raw: dict[str, Any]) -> dict[str, Any]:
    protocol = _exact_dict(raw["protocol"], {"protocol_id", "visit_id"}, "sources.protocol")
    requisition = _exact_dict(
        raw["requisition"],
        {
            "protocol_id",
            "visit_id",
            "version",
            "collection_window_start",
            "collection_window_end",
            "required_sample_type",
        },
        "sources.requisition",
    )
    kit = _exact_dict(
        raw["kit"],
        {"lot", "expires_at", "transport_min_c", "transport_max_c"},
        "sources.kit",
    )
    collection = _exact_dict(
        raw["collection"],
        {"collected_at", "sample_type", "kit_lot", "requisition_version"},
        "sources.collection",
    )
    courier = _exact_dict(
        raw["courier"],
        {"scan_id", "temperature_c", "kit_lot"},
        "sources.courier",
    )
    accession = _exact_dict(
        raw["accession"],
        {"accession_id", "sample_type", "method_id", "requisition_version"},
        "sources.accession",
    )
    method = _exact_dict(
        raw["method"],
        {"method_id", "allowed_sample_types"},
        "sources.method",
    )
    queries = _exact_dict(
        raw["queries"],
        {"requisition_version", "items"},
        "sources.queries",
    )

    window_start = _time_text(requisition["collection_window_start"], "sources.requisition.collection_window_start")
    window_end = _time_text(requisition["collection_window_end"], "sources.requisition.collection_window_end")
    if _time(window_end, "sources.requisition.collection_window_end") < _time(
        window_start, "sources.requisition.collection_window_start"
    ):
        raise EvidenceError("requisition collection window is inverted")

    min_c = _number(kit["transport_min_c"], "sources.kit.transport_min_c", -100.0, 100.0)
    max_c = _number(kit["transport_max_c"], "sources.kit.transport_max_c", -100.0, 100.0)
    if max_c < min_c:
        raise EvidenceError("kit transport temperature range is inverted")

    return {
        "protocol": {
            "protocol_id": _identifier(protocol["protocol_id"], "sources.protocol.protocol_id"),
            "visit_id": _identifier(protocol["visit_id"], "sources.protocol.visit_id"),
        },
        "requisition": {
            "protocol_id": _identifier(requisition["protocol_id"], "sources.requisition.protocol_id"),
            "visit_id": _identifier(requisition["visit_id"], "sources.requisition.visit_id"),
            "version": _identifier(requisition["version"], "sources.requisition.version"),
            "collection_window_start": window_start,
            "collection_window_end": window_end,
            "required_sample_type": _identifier(
                requisition["required_sample_type"], "sources.requisition.required_sample_type"
            ),
        },
        "kit": {
            "lot": _identifier(kit["lot"], "sources.kit.lot"),
            "expires_at": _time_text(kit["expires_at"], "sources.kit.expires_at"),
            "transport_min_c": min_c,
            "transport_max_c": max_c,
        },
        "collection": {
            "collected_at": _time_text(collection["collected_at"], "sources.collection.collected_at"),
            "sample_type": _identifier(collection["sample_type"], "sources.collection.sample_type"),
            "kit_lot": _identifier(collection["kit_lot"], "sources.collection.kit_lot"),
            "requisition_version": _identifier(
                collection["requisition_version"], "sources.collection.requisition_version"
            ),
        },
        "courier": {
            "scan_id": _optional_id(courier["scan_id"], "sources.courier.scan_id"),
            "temperature_c": _optional_number(
                courier["temperature_c"], "sources.courier.temperature_c", -100.0, 100.0
            ),
            "kit_lot": _identifier(courier["kit_lot"], "sources.courier.kit_lot"),
        },
        "accession": {
            "accession_id": _identifier(accession["accession_id"], "sources.accession.accession_id"),
            "sample_type": _identifier(accession["sample_type"], "sources.accession.sample_type"),
            "method_id": _identifier(accession["method_id"], "sources.accession.method_id"),
            "requisition_version": _identifier(
                accession["requisition_version"], "sources.accession.requisition_version"
            ),
        },
        "method": {
            "method_id": _identifier(method["method_id"], "sources.method.method_id"),
            "allowed_sample_types": _sample_types(method["allowed_sample_types"]),
        },
        "queries": {
            "requisition_version": _identifier(
                queries["requisition_version"], "sources.queries.requisition_version"
            ),
            "items": _query_items(queries["items"]),
        },
    }


def normalize_packet(raw: Any) -> dict[str, Any]:
    obj = _exact_dict(raw, PACKET_KEYS, "packet")
    if obj["schema"] != SCHEMA:
        raise EvidenceError("unsupported packet schema")
    packet_id = _identifier(obj["packet_id"], "packet_id")
    raw_sources = _exact_dict(obj["sources"], set(SOURCE_KEYS), "sources")
    declared_refs = _source_refs(obj["source_refs"])
    recomputed_refs = compute_source_refs(raw_sources)
    if declared_refs != recomputed_refs:
        mismatched = [key for key in SOURCE_KEYS if declared_refs[key] != recomputed_refs[key]]
        raise EvidenceError(f"source_refs do not bind exact declared source records: {mismatched}")
    sources = _normalize_sources(raw_sources)
    return {
        "schema": SCHEMA,
        "packet_id": packet_id,
        "sources": sources,
        "source_refs": declared_refs,
        "source_ref_kind": SOURCE_REF_KIND,
        "source_authenticity_verified": False,
    }


def evaluate_packet(raw: Any) -> dict[str, Any]:
    p = normalize_packet(raw)
    s = p["sources"]
    protocol, requisition = s["protocol"], s["requisition"]
    kit, collection, courier = s["kit"], s["collection"], s["courier"]
    accession, method, queries = s["accession"], s["method"], s["queries"]
    collected_at = _time(collection["collected_at"], "sources.collection.collected_at")
    reasons: list[dict[str, Any]] = []

    def hold(code: str, source_names: Iterable[str]) -> None:
        refs = {key: p["source_refs"][key] for key in sorted(set(source_names))}
        reasons.append({"code": code, "source_refs": refs})

    if (
        requisition["protocol_id"] != protocol["protocol_id"]
        or requisition["visit_id"] != protocol["visit_id"]
    ):
        hold("PROTOCOL_VISIT_MISMATCH", ("protocol", "requisition"))

    if (
        collection["requisition_version"] != requisition["version"]
        or accession["requisition_version"] != requisition["version"]
        or queries["requisition_version"] != requisition["version"]
    ):
        hold(
            "REQUISITION_GENERATION_MISMATCH",
            ("requisition", "collection", "accession", "queries"),
        )

    if (
        collection["kit_lot"] != kit["lot"]
        or courier["kit_lot"] != kit["lot"]
        or collected_at > _time(kit["expires_at"], "sources.kit.expires_at")
    ):
        hold("KIT_INVALID_FOR_COLLECTION", ("kit", "collection", "courier"))

    if not (
        _time(requisition["collection_window_start"], "sources.requisition.collection_window_start")
        <= collected_at
        <= _time(requisition["collection_window_end"], "sources.requisition.collection_window_end")
    ):
        hold("COLLECTION_WINDOW_BREACH", ("collection", "requisition"))

    temp = courier["temperature_c"]
    if (
        courier["scan_id"] is None
        or temp is None
        or not (kit["transport_min_c"] <= temp <= kit["transport_max_c"])
    ):
        hold("COURIER_EVIDENCE_INVALID", ("courier", "kit"))

    if (
        collection["sample_type"] != requisition["required_sample_type"]
        or accession["sample_type"] != collection["sample_type"]
        or accession["method_id"] != method["method_id"]
        or accession["sample_type"] not in method["allowed_sample_types"]
    ):
        hold(
            "ACCESSION_METHOD_INCOMPATIBLE",
            ("collection", "accession", "method", "requisition"),
        )

    unresolved = [
        q for q in queries["items"]
        if q["status"] != "RESOLVED" or not q["resolution_evidence_hash"]
    ]
    if unresolved:
        hold("UNRESOLVED_QUERY", ("queries",))

    reasons = sorted(reasons, key=lambda item: item["code"])
    status = STATUS_READY if not reasons else STATUS_HOLD
    evidence_digest = sha256_value(p)
    return {
        "schema": SCHEMA,
        "authority": AUTHORITY,
        "source_ref_kind": SOURCE_REF_KIND,
        "source_authenticity_verified": False,
        "packet_id": p["packet_id"],
        "status": status,
        "reason_codes": [item["code"] for item in reasons],
        "reasons": reasons,
        "source_refs": p["source_refs"],
        "source_digest": sha256_value(p["source_refs"]),
        "evidence_digest": evidence_digest,
    }


def evaluate_batch(packets: Iterable[Any]) -> dict[str, Any]:
    rows = list(packets)
    if not 1 <= len(rows) <= 10000:
        raise EvidenceError("batch must contain 1..10000 packets")
    normalized_ids: set[str] = set()
    results: list[dict[str, Any]] = []
    for raw in rows:
        result = evaluate_packet(raw)
        packet_id = result["packet_id"]
        if packet_id in normalized_ids:
            raise EvidenceError(f"duplicate packet_id: {packet_id}")
        normalized_ids.add(packet_id)
        results.append(result)
    results.sort(key=lambda row: row["packet_id"])
    counts = {STATUS_READY: 0, STATUS_HOLD: 0}
    reason_counts = {code: 0 for code in CODES}
    for row in results:
        counts[row["status"]] += 1
        for code in row["reason_codes"]:
            reason_counts[code] += 1
    core = {
        "schema": SCHEMA,
        "authority": AUTHORITY,
        "source_ref_kind": SOURCE_REF_KIND,
        "source_authenticity_verified": False,
        "packet_count": len(results),
        "status_counts": counts,
        "reason_counts": reason_counts,
        "results": results,
    }
    return {**core, "batch_digest": sha256_value(core)}


def verify_report(packets: Iterable[Any], report: Any) -> bool:
    if type(report) is not dict:
        return False
    try:
        expected = evaluate_batch(packets)
        return canonical_bytes(expected) == canonical_bytes(report)
    except EvidenceError:
        return False


def render_json(report: Any) -> bytes:
    if type(report) is not dict:
        raise EvidenceError("report must be an exact JSON object")
    return canonical_bytes(report) + b"\n"


def render_csv(report: Any) -> bytes:
    obj = _exact_dict(
        report,
        {
            "schema",
            "authority",
            "source_ref_kind",
            "source_authenticity_verified",
            "packet_count",
            "status_counts",
            "reason_counts",
            "results",
            "batch_digest",
        },
        "report",
    )
    sink = io.StringIO(newline="")
    writer = csv.writer(sink, lineterminator="\n")
    writer.writerow(
        [
            "packet_id",
            "status",
            "reason_codes",
            "source_digest",
            "evidence_digest",
            "source_refs_json",
        ]
    )
    for row in obj["results"]:
        writer.writerow(
            [
                row["packet_id"],
                row["status"],
                "|".join(row["reason_codes"]),
                row["source_digest"],
                row["evidence_digest"],
                canonical_bytes(row["source_refs"]).decode("utf-8"),
            ]
        )
    return sink.getvalue().encode("utf-8")


def output_manifest(report: Any) -> dict[str, Any]:
    if type(report) is not dict:
        raise EvidenceError("report must be an exact JSON object")
    json_bytes = render_json(report)
    csv_bytes = render_csv(report)
    return {
        "schema": SCHEMA,
        "authority": AUTHORITY,
        "source_ref_kind": SOURCE_REF_KIND,
        "source_authenticity_verified": False,
        "packet_count": report["packet_count"],
        "batch_digest": report["batch_digest"],
        "json_sha256": hashlib.sha256(json_bytes).hexdigest(),
        "csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
    }
