from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

READY_FOR_SCREEN = "READY_FOR_SCREEN"
HOLD = "HOLD"
DUPLICATE_ASSIGNMENT = "DUPLICATE_ASSIGNMENT"
SOURCE_DESTINATION_MISMATCH = "SOURCE_DESTINATION_MISMATCH"
WRONG_POOL_MEMBERSHIP = "WRONG_POOL_MEMBERSHIP"
VOLUME_BALANCE_FAILURE = "VOLUME_BALANCE_FAILURE"
STALE_PROTOCOL = "STALE_PROTOCOL"
ORPHANED_RUN_LINK = "ORPHANED_RUN_LINK"
DEFECT_CODES = (
    DUPLICATE_ASSIGNMENT,
    SOURCE_DESTINATION_MISMATCH,
    WRONG_POOL_MEMBERSHIP,
    VOLUME_BALANCE_FAILURE,
    STALE_PROTOCOL,
    ORPHANED_RUN_LINK,
)
SCHEMA = "peapod-compound-plate-provenance-gate/v1"
RECORD_SCHEMA = "peapod-compound-plate-provenance-record/v1"
TRANSFER_KEYS = frozenset(
    "sequence transfer_id compound_master_id source_vial_id source_plate_id source_well "
    "source_plate_lot source_volume_ul_before transfer_volume_ul source_volume_ul_after "
    "source_concentration_um membership_type pool_id destination_plate_id destination_well "
    "destination_plate_lot destination_compound_master_id assay_protocol_id "
    "assay_protocol_version control_well_map_hash instrument_run_id".split()
)
COMPOUND_KEYS = frozenset(
    "source_vial_id source_plate_id source_well source_plate_lot source_concentration_um".split()
)
PROTOCOL_KEYS = frozenset("current_version control_well_map_hash".split())
RUN_KEYS = frozenset("destination_plate_id assay_protocol_id".split())


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require_keys(value: Mapping[str, Any], expected: frozenset[str], where: str) -> None:
    if not isinstance(value, Mapping):
        raise ValueError(f"{where}: expected mapping")
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing or unknown:
        parts = []
        if missing:
            parts.append(f"missing fields: {missing}")
        if unknown:
            parts.append(f"unknown fields: {unknown}")
        raise ValueError(f"{where}: " + "; ".join(parts))


def text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError(f"{where}: invalid string")
    if any(ord(char) < 0x20 for char in value):
        raise ValueError(f"{where}: control character")
    return value


def decimal_text(value: Any, where: str) -> str:
    if isinstance(value, bool):
        raise ValueError(f"{where}: boolean is not numeric")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{where}: invalid decimal") from exc
    if not number.is_finite():
        raise ValueError(f"{where}: non-finite decimal")
    if number < 0:
        raise ValueError(f"{where}: negative decimal")
    if number == 0:
        return "0"
    rendered = format(number.normalize(), "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def normalize_context(context: Mapping[str, Any]) -> dict[str, Any]:
    require_keys(context, frozenset({"compounds", "pools", "protocols", "runs"}), "context")
    for name in ("compounds", "pools", "protocols", "runs"):
        if not isinstance(context[name], Mapping):
            raise ValueError(f"context.{name}: expected mapping")
    compounds: dict[str, Any] = {}
    for compound_id, raw in sorted(context["compounds"].items()):
        compound_id = text(compound_id, "compound id")
        require_keys(raw, COMPOUND_KEYS, f"compound {compound_id}")
        compounds[compound_id] = {
            "source_vial_id": text(raw["source_vial_id"], "source_vial_id"),
            "source_plate_id": text(raw["source_plate_id"], "source_plate_id"),
            "source_well": text(raw["source_well"], "source_well"),
            "source_plate_lot": text(raw["source_plate_lot"], "source_plate_lot"),
            "source_concentration_um": decimal_text(raw["source_concentration_um"], "source_concentration_um"),
        }
    pools: dict[str, list[str]] = {}
    for pool_id, members in sorted(context["pools"].items()):
        pool_id = text(pool_id, "pool id")
        if not isinstance(members, Sequence) or isinstance(members, (str, bytes)):
            raise ValueError("pool members: expected sequence")
        normalized = [text(member, "pool member") for member in members]
        if len(normalized) != len(set(normalized)):
            raise ValueError("pool members: duplicate")
        pools[pool_id] = sorted(normalized)
    protocols: dict[str, Any] = {}
    for protocol_id, raw in sorted(context["protocols"].items()):
        protocol_id = text(protocol_id, "protocol id")
        require_keys(raw, PROTOCOL_KEYS, f"protocol {protocol_id}")
        protocols[protocol_id] = {
            "current_version": text(raw["current_version"], "current_version"),
            "control_well_map_hash": text(raw["control_well_map_hash"], "control_well_map_hash"),
        }
    runs: dict[str, Any] = {}
    for run_id, raw in sorted(context["runs"].items()):
        run_id = text(run_id, "run id")
        require_keys(raw, RUN_KEYS, f"run {run_id}")
        runs[run_id] = {
            "destination_plate_id": text(raw["destination_plate_id"], "destination_plate_id"),
            "assay_protocol_id": text(raw["assay_protocol_id"], "assay_protocol_id"),
        }
    return {"compounds": compounds, "pools": pools, "protocols": protocols, "runs": runs}


def normalize_transfer(raw: Mapping[str, Any]) -> dict[str, Any]:
    require_keys(raw, TRANSFER_KEYS, "transfer")
    if isinstance(raw["sequence"], bool) or not isinstance(raw["sequence"], int) or raw["sequence"] < 1:
        raise ValueError("sequence: expected positive integer")
    membership = text(raw["membership_type"], "membership_type")
    if membership not in {"singleton", "pool"}:
        raise ValueError("membership_type: expected singleton or pool")
    pool_id = raw["pool_id"]
    if pool_id is not None:
        pool_id = text(pool_id, "pool_id")
    if (membership == "singleton") != (pool_id is None):
        raise ValueError("pool_id inconsistent with membership_type")
    row = {key: raw[key] for key in TRANSFER_KEYS}
    row["sequence"] = raw["sequence"]
    row["membership_type"] = membership
    row["pool_id"] = pool_id
    text_fields = TRANSFER_KEYS - {
        "sequence", "membership_type", "pool_id",
        "source_volume_ul_before", "transfer_volume_ul",
        "source_volume_ul_after", "source_concentration_um",
    }
    for key in text_fields:
        row[key] = text(raw[key], key)
    for key in (
        "source_volume_ul_before",
        "transfer_volume_ul",
        "source_volume_ul_after",
        "source_concentration_um",
    ):
        row[key] = decimal_text(raw[key], key)
    return row
