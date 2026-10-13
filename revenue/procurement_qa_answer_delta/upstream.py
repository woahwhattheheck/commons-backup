"""Validation/binding for landed solicitation-ingest artifacts."""
from __future__ import annotations
from typing import Any
from .schema import (BOUNDARY, UP_ACTIVE, UP_GAPS, UP_RECEIPT, Error, _keys, _require_false_authority, _requirement, _sha, _string, _timestamp, _integer, canon, digest)

def _upstream(value: Any):
    _keys(
        value,
        [
            "active_set",
            "active_set_sha256",
            "gaps",
            "gaps_sha256",
            "receipt",
            "receipt_sha256",
        ],
        "upstream",
    )
    active = value["active_set"]
    gaps = value["gaps"]
    receipt = value["receipt"]
    active_sha = _sha(value["active_set_sha256"], "upstream.active_set_sha256")
    gaps_sha = _sha(value["gaps_sha256"], "upstream.gaps_sha256")
    receipt_sha = _sha(value["receipt_sha256"], "upstream.receipt_sha256")
    if digest(canon(active)) != active_sha:
        raise Error("upstream: active_set exact canonical bytes drift")
    if digest(canon(gaps)) != gaps_sha:
        raise Error("upstream: gaps exact canonical bytes drift")
    if digest(canon(receipt)) != receipt_sha:
        raise Error("upstream: receipt exact canonical bytes drift")

    _keys(
        active,
        [
            "schema",
            "truth_boundary",
            "pack_id",
            "evaluated_at",
            "current_source",
            "deadline",
            "requirements",
            "attachments",
            "killed_sources",
            "authority",
        ],
        "upstream.active_set",
    )
    if active["schema"] != UP_ACTIVE or active["truth_boundary"] != BOUNDARY:
        raise Error("upstream.active_set: unsupported schema/boundary")
    _require_false_authority(active["authority"], "upstream.active_set.authority")
    pack_id = _string(active["pack_id"], "upstream.active_set.pack_id", token=True)
    _timestamp(active["evaluated_at"], "upstream.active_set.evaluated_at")
    current = active["current_source"]
    _keys(current, ["source_id", "identity", "ref", "sha256", "captured_at", "sequence"], "upstream.current_source")
    current_norm = {
        "source_id": _string(current["source_id"], "upstream.current_source.source_id", token=True),
        "identity": _string(current["identity"], "upstream.current_source.identity"),
        "ref": _string(current["ref"], "upstream.current_source.ref"),
        "sha256": _sha(current["sha256"], "upstream.current_source.sha256"),
        "captured_at": _timestamp(current["captured_at"], "upstream.current_source.captured_at")[0],
        "sequence": _integer(current["sequence"], "upstream.current_source.sequence", 0),
    }
    reqs = active["requirements"]
    if type(reqs) is not list:
        raise Error("upstream.active_set.requirements: list required")
    requirements = [_requirement(row, f"upstream.requirements[{idx}]", upstream=True) for idx, row in enumerate(reqs)]
    by_lineage = {}
    for row in requirements:
        if row["lineage_id"] in by_lineage:
            raise Error("upstream.active_set: duplicate active lineage")
        by_lineage[row["lineage_id"]] = row

    deadline = active["deadline"]
    deadline_norm = None
    if deadline is not None:
        _keys(deadline, ["value", "utc", "source_id", "identity", "ref", "sha256"], "upstream.deadline")
        value_raw, value_dt = _timestamp(deadline["value"], "upstream.deadline.value")
        utc_raw, utc_dt = _timestamp(deadline["utc"], "upstream.deadline.utc")
        if value_dt != utc_dt:
            raise Error("upstream.deadline: value/utc mismatch")
        deadline_norm = {
            "value": value_raw,
            "utc": utc_raw,
            "source_id": _string(deadline["source_id"], "upstream.deadline.source_id", token=True),
            "identity": _string(deadline["identity"], "upstream.deadline.identity"),
            "ref": _string(deadline["ref"], "upstream.deadline.ref"),
            "sha256": _sha(deadline["sha256"], "upstream.deadline.sha256"),
        }

    _keys(gaps, ["schema", "truth_boundary", "pack_id", "status", "hold_reasons", "gaps", "authority"], "upstream.gaps")
    if gaps["schema"] != UP_GAPS or gaps["truth_boundary"] != BOUNDARY or gaps["pack_id"] != pack_id:
        raise Error("upstream.gaps: schema/boundary/pack mismatch")
    _require_false_authority(gaps["authority"], "upstream.gaps.authority")
    if type(gaps["gaps"]) is not list:
        raise Error("upstream.gaps.gaps: list required")
    gap_by_id = {}
    for idx, row in enumerate(gaps["gaps"]):
        if type(row) is not dict:
            raise Error(f"upstream.gaps[{idx}]: object required")
        gap_id = _string(row.get("gap_id"), f"upstream.gaps[{idx}].gap_id", token=True)
        if gap_id in gap_by_id:
            raise Error("upstream.gaps: duplicate gap_id")
        gap_by_id[gap_id] = row

    _keys(
        receipt,
        [
            "schema",
            "truth_boundary",
            "status",
            "pack_id",
            "pack_sha256",
            "selector_sha256",
            "active_set_sha256",
            "gaps_sha256",
            "markdown_sha256",
            "readiness_sha256",
            "authority",
        ],
        "upstream.receipt",
    )
    if receipt["schema"] != UP_RECEIPT or receipt["truth_boundary"] != BOUNDARY or receipt["pack_id"] != pack_id:
        raise Error("upstream.receipt: schema/boundary/pack mismatch")
    _require_false_authority(receipt["authority"], "upstream.receipt.authority")
    if receipt["active_set_sha256"] != active_sha or receipt["gaps_sha256"] != gaps_sha:
        raise Error("upstream.receipt: active/gaps digest mismatch")
    if receipt["status"] != gaps["status"]:
        raise Error("upstream.receipt: status mismatch")
    for key in ("pack_sha256", "selector_sha256", "markdown_sha256", "readiness_sha256"):
        _sha(receipt[key], f"upstream.receipt.{key}")
    return {
        "pack_id": pack_id,
        "active": active,
        "active_sha256": active_sha,
        "gaps": gaps,
        "gaps_sha256": gaps_sha,
        "receipt": receipt,
        "receipt_sha256": receipt_sha,
        "current_source": current_norm,
        "requirements": by_lineage,
        "gaps_by_id": gap_by_id,
        "deadline": deadline_norm,
    }
