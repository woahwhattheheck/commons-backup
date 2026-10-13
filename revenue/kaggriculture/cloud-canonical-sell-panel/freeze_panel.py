#!/usr/bin/env python3
"""Freeze every executable/input byte before the first paired game."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree(path):
    return {str(item.relative_to(path)): {"bytes": item.stat().st_size, "sha256": digest(item)}
            for item in sorted(path.rglob("*")) if item.is_file() and "__pycache__" not in item.parts}


candidate = ROOT / "actors/candidate-default"
control = ROOT / "actors/control-frozen"
runtime = ROOT / "runtime/revenue/kaggriculture"
engine = Path("/workspace/scratch/a958dc9af03f/engine-artifact/engine")
archive = ROOT / "titan-current.tar.gz"
manifest = {
    "claim": "canonical PR10144 DEFAULT vs exact frozen SELL control; both seats",
    "task_url": "https://chatgpt.com/c/6a9f40a1-4f48-83e9-b057-79e3447de9ed",
    "vm_session": "01a07e14-7c72-7c21-8a1f-65a4422c0008",
    "main_at_collision_scan": "fd8d02eca3290d51361db2da46001ef1a70908ff",
    "canonical_merge": "4f743f8ec29bddc36220b2169a2609fe159776e2",
    "canonical_source": "fa7ff3711cdeaa346f78ae5e905eb1446aa7ecc4",
    "archive": {"bytes": archive.stat().st_size, "sha256": digest(archive)},
    "source_json_sha256": digest(candidate / "SOURCE.json"),
    "enabled_config": json.loads((candidate / "TITAN-CONFIG.json").read_text()),
    "enabled_config_sha256": digest(candidate / "TITAN-CONFIG.json"),
    "control": {"constructor": "TitanAgent(Features(consumer='frozen', seed=False))",
                "wrapper_sha256": digest(control / "control.py")},
    "seeds": list(range(9922013, 9922029)),
    "stage_1_seeds": list(range(9922013, 9922017)),
    "seats": [0, 1],
    "limits": {"action_rpc_seconds": 1.0, "startup_seconds": 10.0,
               "game_seconds_between_steps": 120.0, "remaining_overage_time": 0},
    "engine_ref": "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c",
    "engine_files": tree(engine),
    "evaluator": {"path": "cloud-eval/evaluate.py", "sha256": digest(runtime / "cloud-eval/evaluate.py")},
    "loader": {"path": "20260907-offline-agent/evaluate.py", "sha256": digest(runtime / "20260907-offline-agent/evaluate.py")},
    "candidate_runtime": tree(candidate),
    "control_runtime": tree(control),
    "commands": {
        "stage_1": "python -B evaluate.py --engine-dir ENGINE --candidate candidate-default/main.py --opponent frozen_sell=control-frozen/control.py --seeds 9922013,9922014,9922015,9922016 --action-timeout 1.0 --output stage-4.json",
        "stage_2": "same command with seeds 9922017..9922028; combined analysis covers all 16 assigned seeds",
    },
    "exclusions": ["no Claude 384-game rerun", "no T15 adaptive panel", "no public-opponent bank", "no Kaggle upload"],
}

# The control copy must retain every canonical archive byte exactly; only its
# additive wrapper may differ from the candidate directory.
for relative, record in manifest["candidate_runtime"].items():
    assert manifest["control_runtime"][relative] == record, relative

out = ROOT / "lab/FREEZE.json"
out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
print(digest(out), out)
