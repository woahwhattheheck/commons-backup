"""Verify the immutable KAG-COMPOSE selection and validation receipt."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name: str) -> dict:
    return json.loads((HERE / "results" / name).read_text())


def main() -> int:
    selection = json.loads((HERE / "selection.json").read_text())
    reports = {name: load(record["file"]) for name, record in selection["reports"].items()}
    for name, record in selection["reports"].items():
        path = HERE / "results" / record["file"]
        if sha256(path) != record["sha256"]:
            raise ValueError(f"{name}: report hash mismatch")
        report = reports[name]
        if any(game["status"] != "complete" for game in report["games"]):
            raise ValueError(f"{name}: incomplete game")
        if not report["reproducibility"]["same_trace_and_scores"]:
            raise ValueError(f"{name}: reproducibility replay failed")
    if sum(len(reports[name]["games"]) for name in ("rowan_public", "pipeline_development", "balanced_development")) != 72:
        raise ValueError("Expected exactly 72 development games")
    if len(reports["balanced_validation"]["games"]) != 20:
        raise ValueError("Expected exactly 20 validation games")
    balanced = reports["balanced_development"]["summary"]
    rowan = reports["rowan_public"]["summary"]
    public_floor = min(balanced[name]["mean_margin"] for name in ("kaito_v43", "igor_multiroute"))
    rowan_floor = min(rowan[name]["mean_margin"] for name in ("kaito_v43", "igor_multiroute"))
    if not (balanced["rowan_dispatch"]["mean_margin"] > 0 and
            balanced["sorrel_balanced"]["mean_margin"] > 0 and public_floor >= rowan_floor):
        raise ValueError("Selected candidate no longer satisfies the declared gate")
    if sha256(HERE / "candidate.py") != selection["selected_sha256"]:
        raise ValueError("Selected candidate hash mismatch")
    print(json.dumps({"development_games": 72, "validation_games": 20,
                      "selected": selection["selected"], "gate": "PASS"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
