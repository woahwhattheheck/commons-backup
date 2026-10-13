"""Fail-closed external submission readiness validator for ProofLens."""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

SCHEMA = "prooflens-submission-readiness/v1"
RELEASE_KEYS = {
    "aws_deployment_proven",
    "held_out_evaluation_measured",
    "demo_video_ready",
    "human_team_bio_confirmed",
    "devpost_terms_accepted",
    "final_submission_authorized",
}
EXTERNAL_KEYS = {"submitted", "organizer_accepted", "prize_awarded", "payment_received"}


def validate(raw: Any) -> tuple[str, list[str]]:
    if type(raw) is not dict or set(raw) != {"schema", "release_gates", "external_state"}:
        raise ValueError("top-level readiness schema mismatch")
    if raw["schema"] != SCHEMA:
        raise ValueError("unsupported readiness schema")
    release = raw["release_gates"]
    external = raw["external_state"]
    if type(release) is not dict or set(release) != RELEASE_KEYS:
        raise ValueError("release_gates key mismatch")
    if type(external) is not dict or set(external) != EXTERNAL_KEYS:
        raise ValueError("external_state key mismatch")
    if any(type(value) is not bool for value in release.values()):
        raise ValueError("all release_gates values must be booleans")
    if any(type(value) is not bool for value in external.values()):
        raise ValueError("all external_state values must be booleans")

    if external["payment_received"] and not external["prize_awarded"]:
        raise ValueError("payment_received cannot be true before prize_awarded")
    if external["prize_awarded"] and not external["organizer_accepted"]:
        raise ValueError("prize_awarded cannot be true before organizer_accepted")
    if external["organizer_accepted"] and not external["submitted"]:
        raise ValueError("organizer_accepted cannot be true before submitted")
    if external["submitted"] and not all(release.values()):
        raise ValueError("submitted cannot be true while a release gate is false")

    missing = sorted(key for key, value in release.items() if not value)
    return ("READY_FOR_OWNER_SUBMISSION" if not missing else "BLOCKED", missing)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=pathlib.Path)
    parser.add_argument("--expect-blocked", action="store_true")
    args = parser.parse_args(argv)
    raw = json.loads(args.path.read_text(encoding="utf-8"))
    state, missing = validate(raw)
    print(json.dumps({"state": state, "missing_release_gates": missing}, sort_keys=True))
    if args.expect_blocked:
        return 0 if state == "BLOCKED" else 3
    return 0 if state == "READY_FOR_OWNER_SUBMISSION" else 2


if __name__ == "__main__":
    sys.exit(main())
