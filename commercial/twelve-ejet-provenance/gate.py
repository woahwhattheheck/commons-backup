#!/usr/bin/env python3
"""Deterministic E-Jet batch provenance evidence gate.

Consumes one batch JSON document and emits a canonical JSON decision plus a
minimal deterministic PDF dossier. Standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

REQUIRED_HANDOFF_STAGES = ("production_release", "carrier_pickup", "buyer_receipt")
MASS_TOLERANCE_RATIO = Decimal("0.005")
MIN_MASS_TOLERANCE_L = Decimal("0.5")


def _decimal(value: Any) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not result.is_finite():
        return None
    return result


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def _reason(code: str, detail: str) -> dict[str, str]:
    return {"code": code, "detail": detail}


def evaluate(batch: dict[str, Any]) -> dict[str, Any]:
    reasons: list[dict[str, str]] = []

    batch_id = batch.get("batch_id")
    if not isinstance(batch_id, str) or not batch_id.strip():
        reasons.append(_reason("BATCH_ID_MISSING", "batch_id must be a non-empty string"))
        batch_id = "UNSPECIFIED"

    source = batch.get("source") if isinstance(batch.get("source"), dict) else {}
    feedstock_l = _decimal(source.get("feedstock_liters"))
    electricity_mwh = _decimal(source.get("electricity_mwh"))
    protocol_id = source.get("protocol_id")
    if feedstock_l is None or feedstock_l <= 0:
        reasons.append(_reason("FEEDSTOCK_INPUT_INVALID", "source.feedstock_liters must be > 0"))
    if electricity_mwh is None or electricity_mwh < 0:
        reasons.append(_reason("ELECTRICITY_INPUT_INVALID", "source.electricity_mwh must be >= 0"))
    if not isinstance(protocol_id, str) or not protocol_id.strip():
        reasons.append(_reason("SOURCE_PROTOCOL_MISSING", "source.protocol_id is required"))

    output = batch.get("output") if isinstance(batch.get("output"), dict) else {}
    ejet_l = _decimal(output.get("ejet_liters"))
    coproduct_l = _decimal(output.get("coproduct_liters"))
    loss_l = _decimal(output.get("loss_liters"))
    output_values = (ejet_l, coproduct_l, loss_l)
    if any(v is None or v < 0 for v in output_values):
        reasons.append(_reason("OUTPUT_VOLUME_INVALID", "all output volume fields must be >= 0"))

    mass_balance: dict[str, Any] = {"checked": False}
    if feedstock_l is not None and feedstock_l > 0 and all(v is not None and v >= 0 for v in output_values):
        accounted = sum(output_values, Decimal("0"))  # type: ignore[arg-type]
        variance = accounted - feedstock_l
        tolerance = max(MIN_MASS_TOLERANCE_L, feedstock_l * MASS_TOLERANCE_RATIO)
        mass_balance = {
            "checked": True,
            "input_liters": str(feedstock_l.normalize()),
            "accounted_liters": str(accounted.normalize()),
            "variance_liters": str(variance.normalize()),
            "tolerance_liters": str(tolerance.normalize()),
        }
        if abs(variance) > tolerance:
            reasons.append(_reason("MASS_BALANCE_OUT_OF_TOLERANCE", f"absolute variance {variance} L exceeds tolerance {tolerance} L"))

    assay = batch.get("assay") if isinstance(batch.get("assay"), dict) else {}
    spec_id = assay.get("spec_id")
    sample_id = assay.get("sample_id")
    assay_result = assay.get("result")
    if not isinstance(spec_id, str) or not spec_id.strip():
        reasons.append(_reason("ASSAY_SPEC_MISSING", "assay.spec_id is required"))
    if not isinstance(sample_id, str) or not sample_id.strip():
        reasons.append(_reason("ASSAY_SAMPLE_MISSING", "assay.sample_id is required"))
    if assay_result != "PASS":
        reasons.append(_reason("ASSAY_NOT_PASS", "assay.result must equal PASS"))

    sustainability = batch.get("sustainability") if isinstance(batch.get("sustainability"), dict) else {}
    ci = _decimal(sustainability.get("carbon_intensity_gco2e_mj"))
    method = sustainability.get("method")
    if ci is None or ci < 0:
        reasons.append(_reason("CARBON_INTENSITY_INVALID", "carbon_intensity_gco2e_mj must be >= 0"))
    if not isinstance(method, str) or not method.strip():
        reasons.append(_reason("SUSTAINABILITY_METHOD_MISSING", "sustainability.method is required"))

    handoffs = batch.get("handoffs") if isinstance(batch.get("handoffs"), list) else []
    by_stage: dict[str, dict[str, Any]] = {}
    for index, handoff in enumerate(handoffs):
        if not isinstance(handoff, dict):
            reasons.append(_reason("HANDOFF_INVALID", f"handoffs[{index}] must be an object"))
            continue
        stage = handoff.get("stage")
        if not isinstance(stage, str) or not stage.strip():
            reasons.append(_reason("HANDOFF_STAGE_MISSING", f"handoffs[{index}].stage is required"))
            continue
        if stage in by_stage:
            reasons.append(_reason("HANDOFF_STAGE_DUPLICATE", f"stage {stage} appears more than once"))
        else:
            by_stage[stage] = handoff

    ordered_times: list[tuple[str, datetime]] = []
    for stage in REQUIRED_HANDOFF_STAGES:
        handoff = by_stage.get(stage)
        if handoff is None:
            reasons.append(_reason("HANDOFF_STAGE_MISSING", f"required stage {stage} is missing"))
            continue
        owner = handoff.get("owner")
        if not isinstance(owner, str) or not owner.strip():
            reasons.append(_reason("HANDOFF_OWNER_MISSING", f"stage {stage} has no owner"))
        ts = _timestamp(handoff.get("timestamp"))
        if ts is None:
            reasons.append(_reason("HANDOFF_TIMESTAMP_INVALID", f"stage {stage} needs an offset-aware RFC3339 timestamp"))
        else:
            ordered_times.append((stage, ts))

    for (prev_stage, prev_ts), (stage, ts) in zip(ordered_times, ordered_times[1:]):
        if ts < prev_ts:
            reasons.append(_reason("HANDOFF_SEQUENCE_INVALID", f"{stage} timestamp precedes {prev_stage}"))

    reasons.sort(key=lambda item: (item["code"], item["detail"]))
    status = "PASS" if not reasons else "HOLD"
    decision: dict[str, Any] = {
        "schema": "ejet-batch-provenance-gate/v1",
        "batch_id": batch_id,
        "status": status,
        "reason_codes": reasons,
        "mass_balance": mass_balance,
        "evidence": {
            "source_protocol_id": protocol_id,
            "assay_spec_id": spec_id,
            "assay_sample_id": sample_id,
            "assay_result": assay_result,
            "sustainability_method": method,
            "carbon_intensity_gco2e_mj": None if ci is None else str(ci.normalize()),
            "handoff_stages": [stage for stage in REQUIRED_HANDOFF_STAGES if stage in by_stage],
        },
    }
    canonical = json.dumps(decision, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    decision["evidence_sha256"] = hashlib.sha256(canonical).hexdigest()
    return decision


def canonical_json(decision: dict[str, Any]) -> bytes:
    return (json.dumps(decision, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode("ascii")


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def render_pdf(decision: dict[str, Any]) -> bytes:
    lines = [
        "E-JET BATCH PROVENANCE DOSSIER",
        f"Batch: {decision['batch_id']}",
        f"Gate: {decision['status']}",
        f"Evidence SHA-256: {decision['evidence_sha256']}",
        "",
        "Decision reasons:",
    ]
    reasons = decision["reason_codes"]
    if not reasons:
        lines.append("- none")
    else:
        for item in reasons[:18]:
            lines.append(f"- {item['code']}: {item['detail']}")
    mb = decision["mass_balance"]
    lines.extend(["", "Mass balance:"])
    if mb.get("checked"):
        lines.append(f"input={mb['input_liters']} L accounted={mb['accounted_liters']} L variance={mb['variance_liters']} L tolerance={mb['tolerance_liters']} L")
    else:
        lines.append("not checked: required numeric inputs were incomplete")
    lines = [re.sub(r"[^\x20-\x7e]", "?", line)[:110] for line in lines]
    stream_parts = ["BT", "/F1 10 Tf", "50 760 Td", "12 TL"]
    for i, line in enumerate(lines):
        if i:
            stream_parts.append("T*")
        stream_parts.append(f"({_pdf_escape(line)}) Tj")
    stream_parts.append("ET")
    stream = ("\n".join(stream_parts) + "\n").encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n% deterministic-ejet-provenance\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{index} 0 obj\n".encode("ascii"))
        out.extend(obj)
        out.extend(b"\nendobj\n")
    xref = len(out)
    out.extend(f"xref\n0 {len(objects)+1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    out.extend(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii"))
    return bytes(out)


def run(input_path: Path, output_dir: Path) -> tuple[Path, Path, dict[str, Any]]:
    batch = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(batch, dict):
        raise ValueError("input JSON root must be an object")
    decision = evaluate(batch)
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(decision["batch_id"]))[:80]
    json_path = output_dir / f"{safe_id}.decision.json"
    pdf_path = output_dir / f"{safe_id}.dossier.pdf"
    json_path.write_bytes(canonical_json(decision))
    pdf_path.write_bytes(render_pdf(decision))
    return json_path, pdf_path, decision


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="batch evidence JSON")
    parser.add_argument("--out", type=Path, default=Path("out"), help="output directory")
    args = parser.parse_args()
    json_path, pdf_path, decision = run(args.input, args.out)
    print(json.dumps({"status": decision["status"], "json": str(json_path), "pdf": str(pdf_path), "evidence_sha256": decision["evidence_sha256"]}, sort_keys=True))
    return 0 if decision["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
