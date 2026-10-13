from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from core import (
    AuditConfig,
    ContractError,
    apply_review_candidate,
    audit_surface,
    build_bundle_bytes,
    build_receipt,
    canonical_json_bytes,
    deterministic_npz_bytes,
    load_calibration,
    load_inputs,
    sha256_bytes,
    validate_manifest,
    verify_bundle_bytes,
    verify_receipt,
    write_metrics_csv,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Vesuvius CT-ridge audit + conservative review proposal tool")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, default=Path(__file__).with_name("real_derived_calibration.json"))
    parser.add_argument("--max-offset", type=int, default=3)
    parser.add_argument("--point-stride", type=int, default=1)
    parser.add_argument("--apply-review-candidate", action="store_true", help="opt-in review artifact only; no topology-preservation claim")
    args = parser.parse_args()

    with args.manifest.open("r", encoding="utf-8") as fh:
        raw_manifest = json.load(fh)
    manifest = validate_manifest(raw_manifest)
    ct, labels, digests = load_inputs(manifest, args.manifest.parent)
    calibration = load_calibration(args.calibration)
    audit = audit_surface(ct, labels, AuditConfig(max_offset=args.max_offset, point_stride=args.point_stride))
    candidate, candidate_meta = apply_review_candidate(labels, audit, enabled=args.apply_review_candidate)

    args.output.mkdir(parents=True, exist_ok=True)
    arrays = {
        "accepted": audit["accepted"].astype(np.uint8),
        "confidence": audit["confidence"].astype(np.float32),
        "normals": audit["normals"].astype(np.float32),
        "proposed_offset": audit["proposed_offset"].astype(np.float32),
    }
    if args.apply_review_candidate:
        arrays["review_candidate"] = candidate.astype(np.uint8)
    evidence_bytes = deterministic_npz_bytes(arrays)
    evidence_path = args.output / "evidence.npz"
    evidence_path.write_bytes(evidence_bytes)
    metrics_path = args.output / "metrics.csv"
    write_metrics_csv(metrics_path, audit["summary"])
    report = {
        "format": "vesuvius-ct-ridge-report/v1",
        "summary": audit["summary"],
        "blocks": audit["blocks"],
        "candidate": candidate_meta,
        "calibration": calibration,
        "claims": {
            "raw_dataset059_execution": False,
            "topology_preserved": False,
            "automatic_correction": False,
            "prize_or_submission": False,
        },
    }
    report_bytes = canonical_json_bytes(report) + b"\n"
    report_path = args.output / "report.json"
    report_path.write_bytes(report_bytes)
    artifact_digests = {
        "evidence.npz": sha256_bytes(evidence_bytes),
        "metrics.csv": sha256_bytes(metrics_path.read_bytes()),
        "report.json": sha256_bytes(report_bytes),
    }
    receipt = build_receipt(
        manifest=manifest,
        input_digests=digests,
        audit=audit,
        calibration=calibration,
        artifacts=artifact_digests,
    )
    receipt_bytes = canonical_json_bytes(receipt) + b"\n"
    (args.output / "receipt.json").write_bytes(receipt_bytes)
    bundle, _ = build_bundle_bytes({
        "evidence.npz": evidence_bytes,
        "metrics.csv": metrics_path.read_bytes(),
        "report.json": report_bytes,
        "receipt.json": receipt_bytes,
    })
    (args.output / "vesuvius-review-bundle.zip").write_bytes(bundle)
    if not verify_receipt(receipt):
        raise ContractError("self-verification of receipt failed")
    verify_bundle_bytes(bundle)
    print(json.dumps({
        "decision": audit["summary"]["decision"],
        "bundle_sha256": sha256_bytes(bundle),
        "receipt_sha256": receipt["receipt_sha256"],
        "candidate_enabled": args.apply_review_candidate,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
