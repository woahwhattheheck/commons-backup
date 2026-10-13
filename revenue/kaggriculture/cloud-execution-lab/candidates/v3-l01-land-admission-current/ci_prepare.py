# SPDX-License-Identifier: Apache-2.0
"""Prepare immutable historical/current packages and their provenance."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from ci_support import download, extract_verified, git_blob_id, invoke_python, run, sha256


def historical_check(
    repo: Path, lane: Path, work: Path, pin: dict[str, Any]
) -> Path:
    historical = pin["historical_source"]
    panel = (
        "revenue/kaggriculture/cloud-execution-lab/candidates/"
        "v3-l01-leader-mechanics/panels"
    )
    base_url = (
        f"https://raw.githubusercontent.com/{os.environ['GITHUB_REPOSITORY']}/"
        f"{historical['head_commit']}/{panel}"
    )
    output = work / "historical-l01"
    baseline = output / "canonical.GAMES.jsonl"
    candidate = output / "land.GAMES.jsonl"
    download(f"{base_url}/canonical.GAMES.jsonl", baseline)
    download(f"{base_url}/land.GAMES.jsonl", candidate)
    actual = {
        "baseline": git_blob_id(baseline.read_bytes()),
        "candidate": git_blob_id(candidate.read_bytes()),
    }
    expected = {
        "baseline": historical["baseline_games_git_blob"],
        "candidate": historical["land_games_git_blob"],
    }
    if actual != expected:
        raise ValueError(f"historical panel identities drifted: {actual!r} != {expected!r}")
    invoke_python(
        Path(sys.executable), lane / "panel_delta.py",
        [
            "--baseline", baseline, "--candidate", candidate,
            "--opponents", ",".join(historical["opponents"]),
            "--seed-start", min(historical["seeds"]),
            "--seed-count", len(historical["seeds"]),
            "--expect-historical-l01",
            "--json-out", output / "DELTA.json",
            "--markdown-out", output / "DELTA.md",
        ], cwd=repo,
    )
    return output / "DELTA.json"


def build_current(
    repo: Path, lane: Path, lab: Path, work: Path
) -> dict[str, Any]:
    invoke_python(
        Path(sys.executable), lane / "build_candidate.py",
        [
            "--lab-root", lab, "--output-root", work / "current",
            "--mechanism", lane / "land_admission.py",
        ], cwd=repo,
    )
    return json.loads((work / "current/BUILD.json").read_text(encoding="utf-8"))


def install_engine(
    repo: Path, lab: Path, work: Path, pin: dict[str, Any]
) -> tuple[Path, Path]:
    venv = work / ".venv"
    run([sys.executable, "-m", "venv", str(venv)], cwd=repo)
    python, pip = venv / "bin/python", venv / "bin/pip"
    engine_pin = pin["official_engine"]
    run([str(pip), "install", "--quiet", engine_pin["package"]], cwd=repo)
    package = Path(subprocess.check_output(
        [
            str(python), "-c",
            "import kaggle_environments,os;print(os.path.dirname(kaggle_environments.__file__))",
        ], cwd=repo, text=True,
    ).strip())
    engine = work / "engine"
    engine.mkdir()
    sources = {
        "kaggriculture.py": package / "envs/kaggriculture/kaggriculture.py",
        "kaggriculture.json": package / "envs/kaggriculture/kaggriculture.json",
        "utils.py": package / "utils.py",
    }
    for name, source in sources.items():
        target = engine / name
        shutil.copyfile(source, target)
        if sha256(target) != engine_pin[f"{name}_sha256"]:
            raise ValueError(f"official engine hash mismatch for {name}")

    v1_hash = pin["holdout"]["v1_submitted_archive_sha256"]
    v1_archive = lab / f"exports/historical/titan-{v1_hash}.tar.gz"
    if sha256(v1_archive) != v1_hash:
        raise ValueError("submitted V1 archive hash mismatch")
    v1 = work / "v1"
    extract_verified(v1_archive, v1)
    if not (v1 / "main.py").is_file():
        raise FileNotFoundError("submitted V1 archive lacks main.py")
    return python, engine


def route_probe(repo: Path, lane: Path, work: Path, python: Path) -> Path:
    baseline = work / "ROUTES-baseline.json"
    candidate = work / "ROUTES-land.json"
    report = work / "ROUTE-DIFF.json"
    invoke_python(
        python, lane / "route_probe.py",
        ["snapshot", "--package", work / "current/baseline", "--output", baseline],
        cwd=repo,
    )
    invoke_python(
        python, lane / "route_probe.py",
        [
            "snapshot", "--package", work / "current/land", "--apply-land",
            "--output", candidate,
        ], cwd=repo,
    )
    invoke_python(
        python, lane / "route_probe.py",
        [
            "compare", "--baseline", baseline, "--candidate", candidate,
            "--mechanism", lane / "land_admission.py", "--output", report,
        ], cwd=repo,
    )
    return report


def opponent_paths(repo: Path, lab: Path, work: Path) -> dict[str, Path]:
    base = repo / "revenue/kaggriculture"
    return {
        "arlene": lab / "runtime/variants/v1/reference/next-panel/vendor/arlene.py",
        "apex": base / "cloud-policy-portfolio/vendor/apex/main.py",
        "kaito_v43": base / "cloud-frontier-policy/vendor/kaito_v43.py",
        "cok_v10": base / "cloud-policy-portfolio/revision2/vendor/opponents/cok-v10.py",
        "public_bt12": base / "cloud-frontier-decision/public-opponent/submission.py",
        "v1_submitted": work / "v1/main.py",
    }


def write_manifest(
    repo: Path, lab: Path, work: Path, pin: dict[str, Any],
    build: dict[str, Any], engine: Path, historical_delta: Path,
) -> None:
    holdout = pin["holdout"]
    opponents = opponent_paths(repo, lab, work)
    for path in opponents.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    checkout = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()
    manifest = {
        "schema": "titan-v3-land-admission-holdout-manifest-v1",
        "operation": pin["operation"],
        "checkout_sha": checkout,
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
        "workflow_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "build": build,
        "historical_l01_delta_sha256": sha256(historical_delta),
        "engine": {
            "package": pin["official_engine"]["package"],
            **{
                f"{name}_sha256": sha256(engine / name)
                for name in ("kaggriculture.py", "kaggriculture.json", "utils.py")
            },
        },
        "opponents": {
            name: {"path": str(path), "sha256": sha256(path)}
            for name, path in opponents.items()
        },
        "seeds": list(range(
            holdout["seed_start"], holdout["seed_start"] + holdout["seed_count"]
        )),
        "candidate_seats": holdout["candidate_seats"],
        "scheduled_games_per_arm": holdout["scheduled_games_per_arm"],
        "scheduled_games_total": holdout["scheduled_games_total"],
        "workers": holdout["workers"],
        "action_timeout_seconds": holdout["action_timeout_seconds"],
    }
    (work / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
