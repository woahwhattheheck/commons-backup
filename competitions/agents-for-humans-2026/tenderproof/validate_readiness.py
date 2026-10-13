from __future__ import annotations

import argparse
import json
from pathlib import Path

REQUIRED_EXTERNAL = (
    "strands_live_run_verified",
    "aws_builder_id_verified",
    "public_repo_requirement_verified",
    "architecture_diagram_verified",
    "public_demo_video_verified",
    "devpost_registration_and_terms_accepted",
    "final_submission_authorized",
)


def validate(data: object) -> tuple[bool, list[str]]:
    if not isinstance(data, dict):
        return False, ["readiness root must be an object"]
    missing = [key for key in REQUIRED_EXTERNAL if data.get(key) is not True]
    claimed = data.get("submission_state")
    if missing and claimed != "BLOCKED":
        return False, ["submission_state must remain BLOCKED while external gates are incomplete"] + missing
    if not missing and claimed not in {"READY", "SUBMITTED"}:
        return False, ["all external gates are true but submission_state is not READY/SUBMITTED"]
    return not missing, missing


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--expect-blocked", action="store_true")
    args = parser.parse_args()
    data = json.loads(args.path.read_text(encoding="utf-8"))
    ready, missing = validate(data)
    if args.expect_blocked:
        if ready or data.get("submission_state") != "BLOCKED":
            print("expected a truthful BLOCKED state")
            return 1
        print("BLOCKED as expected: " + ", ".join(missing))
        return 0
    if ready:
        print("READY")
        return 0
    print("BLOCKED: " + ", ".join(missing))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
