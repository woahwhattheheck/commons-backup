from __future__ import annotations

import argparse
import json
from pathlib import Path

from .engine import (
    RoadV2Error, admit_pseudo_labels, build_profile, build_receipt, canonical_bytes,
    compile_submission, csv_text_map, ensemble, loads_strict, sha256_hex,
    validate_manifest, verify_receipt,
)


def _pred_arg(values: list[str]) -> dict[str, Path]:
    out = {}
    for value in values:
        if "=" not in value:
            raise RoadV2Error("prediction arguments must be MODEL=PATH")
        model, path = value.split("=", 1)
        if not model or model in out:
            raise RoadV2Error("duplicate/empty prediction model")
        out[model] = Path(path)
    return out


def _read_prediction_files(args: list[str], *, prefix: str) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    paths = _pred_arg(args); out = {}; digests = {}
    for model, path in sorted(paths.items()):
        raw = path.read_bytes(); out[model], _, _ = csv_text_map(raw, where=f"{prefix}:{model}"); digests[model] = sha256_hex(raw)
    return out, digests


def build(ns: argparse.Namespace) -> int:
    manifest = validate_manifest(loads_strict(Path(ns.manifest).read_bytes()))
    train_raw = Path(ns.train).read_bytes(); labels, _, _ = csv_text_map(train_raw, where="Train.csv")
    oof, _ = _read_prediction_files(ns.oof, prefix="OOF")
    test_predictions, test_digests = _read_prediction_files(ns.pred, prefix="TEST")
    profile = build_profile(manifest, labels, oof)
    chosen, audit = ensemble(manifest, profile, labels, test_predictions)
    pseudo = admit_pseudo_labels(audit, chosen, min_support_models=ns.min_support_models, min_support_ppm=ns.min_support_ppm, min_agreement_ppm=ns.min_agreement_ppm)
    sample_raw = Path(ns.sample).read_bytes(); submission = compile_submission(sample_raw, chosen)
    receipt = build_receipt(manifest, profile, audit, pseudo, sample_raw=sample_raw, submission_raw=submission, input_prediction_digests=test_digests)
    out = Path(ns.out)
    if out.exists():
        raise RoadV2Error("output directory already exists")
    out.mkdir(parents=True)
    (out / "submission.csv").write_bytes(submission)
    (out / "profile.json").write_bytes(canonical_bytes(profile) + b"\n")
    (out / "ensemble-audit.json").write_bytes(canonical_bytes(audit) + b"\n")
    (out / "pseudo-labels.json").write_bytes(canonical_bytes(pseudo) + b"\n")
    (out / "receipt.json").write_bytes(canonical_bytes(receipt) + b"\n")
    print(json.dumps({"state": "LOCAL_BUILD_COMPLETE_NOT_SUBMITTED", "rows": audit["row_count"], "pseudo_labels": len(pseudo["rows"]), "receipt_sha256": receipt["receipt_sha256"]}, sort_keys=True, separators=(",", ":")))
    return 0


def verify(ns: argparse.Namespace) -> int:
    receipt = loads_strict(Path(ns.receipt).read_bytes())
    ok = verify_receipt(receipt, sample_raw=Path(ns.sample).read_bytes(), submission_raw=Path(ns.submission).read_bytes())
    print("PASS" if ok else "FAIL")
    return 0 if ok else 2


def main() -> int:
    p = argparse.ArgumentParser(description="R.O.A.D. Barbados OCR v2 competition-safe ensemble/pseudo-label core")
    sp = p.add_subparsers(dest="cmd", required=True)
    b = sp.add_parser("build")
    b.add_argument("--manifest", required=True); b.add_argument("--train", required=True); b.add_argument("--sample", required=True)
    b.add_argument("--oof", action="append", default=[], required=True, help="MODEL=CSV")
    b.add_argument("--pred", action="append", default=[], required=True, help="MODEL=CSV")
    b.add_argument("--out", required=True)
    b.add_argument("--min-support-models", type=int, default=2)
    b.add_argument("--min-support-ppm", type=int, default=600000)
    b.add_argument("--min-agreement-ppm", type=int, default=850000)
    b.set_defaults(func=build)
    v = sp.add_parser("verify"); v.add_argument("--receipt", required=True); v.add_argument("--sample", required=True); v.add_argument("--submission", required=True); v.set_defaults(func=verify)
    ns = p.parse_args()
    try:
        return ns.func(ns)
    except RoadV2Error as exc:
        raise SystemExit(f"ROAD OCR v2 HOLD: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
