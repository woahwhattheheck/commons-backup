from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


AUTH_SCOPE = "conditional_after_registration_and_rule_acceptance"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(state_path: Path) -> tuple[bool, list[str]]:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    reasons: list[str] = []

    auth = state.get("written_dataset_authorization") or {}
    if auth.get("received") is not True:
        reasons.append("written dataset authorization missing")
    if auth.get("scope") != AUTH_SCOPE:
        reasons.append("written dataset authorization scope missing/invalid")
    if auth.get("official_mirrors_only") is not True:
        reasons.append("official-mirrors-only authorization boundary missing")
    if auth.get("noncommercial_competition_use_only") is not True:
        reasons.append("noncommercial competition-use authorization boundary missing")

    for key in ("official_registration_complete", "kaggle_rules_accepted", "dataset_terms_accepted", "submission_authorized"):
        if state.get(key) is not True:
            reasons.append(f"{key}=false")
    submission = state.get("submission") or {}
    path = Path(submission.get("path", ""))
    expected = submission.get("sha256", "")
    if not path.is_file():
        reasons.append("submission artifact missing")
    elif len(expected) != 64 or sha256(path) != expected:
        reasons.append("submission sha256 mismatch")
    if not (state.get("validation") or {}).get("subject_disjoint", False):
        reasons.append("subject-disjoint validation evidence missing")
    score = (state.get("validation") or {}).get("exact_accuracy")
    if not isinstance(score, (int, float)) or not 0 <= score <= 1:
        reasons.append("validation exact_accuracy missing/invalid")
    return not reasons, reasons


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("state", nargs="?", default="readiness.json")
    args = parser.parse_args()
    ok, reasons = check(Path(args.state))
    print(json.dumps({"ready": ok, "reasons": reasons}, sort_keys=True))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
