"""Offline adapter for validating the RSNA Knee public submission contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from rsna_knee_toolkit import LABELS, validate_submission, write_submission


def _smoke() -> dict[str, object]:
    """Exercise only synthetic IDs and constant synthetic confidence scores."""
    study_ids = [f"synthetic-study-{index:02d}" for index in range(6)]
    predictions = {
        label: [0.2 + (index % 4) * 0.2 for index in range(len(study_ids))]
        for label in LABELS
    }
    with TemporaryDirectory() as directory:
        path = Path(directory) / "submission.csv"
        write_submission(study_ids, predictions, path)
        return validate_submission(path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="RSNA Knee 2026 data-free submission-contract adapter"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate an existing CSV")
    validate.add_argument("submission", type=Path)

    subparsers.add_parser("smoke", help="run a synthetic contract smoke test")
    args = parser.parse_args()

    result = (
        validate_submission(args.submission)
        if args.command == "validate"
        else _smoke()
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
