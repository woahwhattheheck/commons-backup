"""Small stdlib CLI for deterministic FusionMeter calibration and gating."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .calibrate import fit_certificate
from .core import MeterSample, canonical_json, predict
from .readiness import evaluate_readiness, validate_readiness_document


def _load(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _write(path: str, value: Any) -> None:
    Path(path).write_text(canonical_json(value) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fusionmeter")
    sub = parser.add_subparsers(dest="command", required=True)

    calibrate = sub.add_parser("calibrate")
    calibrate.add_argument("training_json")
    calibrate.add_argument("validation_json")
    calibrate.add_argument("output_json")
    calibrate.add_argument("--source-sha256", required=True)
    calibrate.add_argument("--evidence-class", default="SYNTHETIC", choices=["SYNTHETIC", "LAB_ANALOG", "REPRESENTATIVE_POC"])

    estimate = sub.add_parser("estimate")
    estimate.add_argument("certificate_json")
    estimate.add_argument("sample_json")

    readiness = sub.add_parser("readiness")
    readiness.add_argument("certificate_json")
    readiness.add_argument("readiness_json")

    args = parser.parse_args(argv)
    if args.command == "calibrate":
        certificate = fit_certificate(
            _load(args.training_json),
            _load(args.validation_json),
            source_sha256=args.source_sha256,
            evidence_class=args.evidence_class,
        )
        _write(args.output_json, certificate)
        print(canonical_json(certificate))
        return 0
    if args.command == "estimate":
        result = predict(_load(args.certificate_json), MeterSample.from_mapping(_load(args.sample_json)))
        print(canonical_json(result))
        return 0
    if args.command == "readiness":
        readiness_doc = _load(args.readiness_json)
        validate_readiness_document(readiness_doc)
        result = evaluate_readiness(_load(args.certificate_json), readiness_doc)
        print(canonical_json(result))
        return 0 if result["status"] == "READY" else 2
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
