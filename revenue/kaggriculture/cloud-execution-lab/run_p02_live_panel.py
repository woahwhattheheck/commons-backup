#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run and bind the P02 candidate-versus-current official-engine panel."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ENGINE_HASHES = {
    "kaggriculture.py": "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e",
    "kaggriculture.json": "a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867",
    "utils.py": "537b627b11784d424147ef57ebb0369b039bf83c9f891e81f10486b1f552334b",
}
OPERATION = "op:titan-v25-orders-20260909-P02-sol-helix-integration-01"
ISOLATED_IMPORT_PROBE = (
    "from observed_clone import detached_json_value\n"
    "import scheduler\n"
    "from p02_candidate import agent as candidate\n"
    "from main import agent as current\n"
    "assert callable(detached_json_value) and callable(candidate) and callable(current)\n"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def isolated_source_pythonpath(lab: Path) -> str:
    """Bare imports in isolated workers resolve the archive's attributed siblings.

    The official evaluator strips the worker environment and only inserts the
    agent parent. Root modules that ``build_integrated.source_files`` copies
    from outside the lab (observed_clone, seller_snapshot, …) must therefore
    appear on PYTHONPATH. See test_e07_hosted_source_path and
    test_p02_isolated_source_path.
    """
    lab = lab.resolve()
    if str(lab) not in sys.path:
        sys.path.insert(0, str(lab))
    from build_integrated import source_files
    ordered = [lab]
    seen = {lab}
    for member, source in source_files().items():
        if Path(member).parent != Path("."):
            continue
        origin = (lab / source).resolve()
        if not origin.is_file():
            raise FileNotFoundError(
                f"mapped root module {member} missing at {origin}")
        parent = origin.parent
        if parent not in seen:
            seen.add(parent)
            ordered.append(parent)
    return os.pathsep.join(str(path) for path in ordered)


def patch_evaluator(source: Path, target: Path) -> None:
    text = source.read_text(encoding="utf-8")
    old = '''        env = {"PATH": os.defpath, "HOME": self.directory.name, "LANG": "C.UTF-8",
               "PYTHONHASHSEED": str(rng_seed % (2**32)), "PYTHONDONTWRITEBYTECODE": "1"}'''
    new = old + '''
        if os.environ.get("TITAN_P02_TRACE_DIR"):
            env["TITAN_P02_TRACE_DIR"] = os.environ["TITAN_P02_TRACE_DIR"]
        if os.environ.get("TITAN_P02_PYTHONPATH"):
            env["PYTHONPATH"] = os.environ["TITAN_P02_PYTHONPATH"]'''
    if text.count(old) != 1:
        raise RuntimeError("evaluator environment seam changed")
    target.write_text(text.replace(old, new), encoding="utf-8")


def assert_isolated_source_imports(lab: Path, pythonpath: str) -> None:
    """Fail closed before the 64-game panel if stripped workers cannot import."""
    with tempfile.TemporaryDirectory(prefix="kag-eval-agent-") as tmp:
        env = {
            "PATH": os.defpath,
            "HOME": tmp,
            "LANG": "C.UTF-8",
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": pythonpath,
        }
        result = subprocess.run(
            [sys.executable, "-B", "-c", ISOLATED_IMPORT_PROBE],
            cwd=tmp, env=env, capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "isolated official-panel workers cannot import lab agents: "
                + (result.stderr or result.stdout)[:1500]
            )


def run_bank(*, workspace: Path, work: Path, bank: str, seeds: list[int],
             pythonpath: str) -> None:
    lab = workspace / "revenue/kaggriculture/cloud-execution-lab"
    output = work / bank
    traces = output / "traces"
    traces.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, TITAN_P02_TRACE_DIR=str(traces),
               TITAN_P02_PYTHONPATH=pythonpath)
    command = [
        sys.executable, "-B", str(workspace / "results/v25/s24/runner.py"),
        "--python", sys.executable,
        "--evaluator", str(work / "evaluate-p02.py"),
        "--engine-dir", str(work / "engine"),
        "--loader", str(workspace / "revenue/kaggriculture/20260907-offline-agent/evaluate.py"),
        "--candidate", str(lab / "p02_candidate.py") + "::agent",
        "--seeds", ",".join(map(str, seeds)),
        "--workers", "8", "--action-timeout", "1.25",
        "--startup-timeout", "60", "--game-timeout", "1800",
        "--opponent", "current=" + str(lab / "main.py") + "::agent",
        "--output-dir", str(output),
    ]
    subprocess.run(command, cwd=workspace, env=env, check=True)
    subprocess.run([
        sys.executable, str(lab / "summarize_p02_panel.py"),
        "--trace-dir", str(traces), "--games", str(output / "GAMES.jsonl"),
        "--output", str(output / "TELEMETRY.json"),
    ], cwd=workspace, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--head", required=True)
    args = parser.parse_args()
    workspace, work = args.workspace.resolve(), args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    lab = workspace / "revenue/kaggriculture/cloud-execution-lab"
    pythonpath = isolated_source_pythonpath(lab)

    import kaggle_environments
    package = Path(kaggle_environments.__file__).resolve().parent
    engine = work / "engine"
    engine.mkdir(exist_ok=True)
    sources = {
        "kaggriculture.py": package / "envs/kaggriculture/kaggriculture.py",
        "kaggriculture.json": package / "envs/kaggriculture/kaggriculture.json",
        "utils.py": package / "utils.py",
    }
    for name, source in sources.items():
        shutil.copy2(source, engine / name)
        actual = sha256(engine / name)
        if actual != ENGINE_HASHES[name]:
            raise RuntimeError(f"official engine mismatch for {name}: {actual}")

    evaluator = lab / "reference/evaluator/evaluate.py"
    patch_evaluator(evaluator, work / "evaluate-p02.py")
    assert_isolated_source_imports(lab, pythonpath)
    banks = {"dev": list(range(2609093201, 2609093217)),
             "holdout": list(range(2609094201, 2609094217))}
    for bank, seeds in banks.items():
        run_bank(workspace=workspace, work=work, bank=bank, seeds=seeds,
                 pythonpath=pythonpath)

    files = {}
    for path in sorted(work.rglob("*")):
        if path.is_file():
            files[str(path.relative_to(work))] = {"bytes": path.stat().st_size, "sha256": sha256(path)}
    manifest = {
        "schema": "titan-p02-live-official-panel-v1", "operation": OPERATION,
        "exact_head": args.head, "engine": {"version": "kaggle-environments==1.32.7", **ENGINE_HASHES},
        "candidate": "revenue/kaggriculture/cloud-execution-lab/p02_candidate.py::agent",
        "control": "revenue/kaggriculture/cloud-execution-lab/main.py::agent",
        "isolated_pythonpath": pythonpath,
        "both_candidate_seats": True, "seed_banks": banks, "files_before_manifest": files,
    }
    (work / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    lines = ["# P02 official candidate-versus-current panel", ""]
    for bank in ("dev", "holdout"):
        game = json.loads((work / bank / "SUMMARY.json").read_text())
        trace = json.loads((work / bank / "TELEMETRY.json").read_text())
        overall = game["overall"]
        lines += [
            f"## {bank}", "",
            f"- Complete: {game['completed']}/{game['scheduled']}; incomplete {game['incomplete']}; key errors {len(game['key_errors'])}.",
            f"- Candidate W/T/L: {overall['W']}/{overall['T']}/{overall['L']}; mean terminal margin {overall['mean_margin']}.",
            f"- Changed action rows: {trace['changed_action_rows']}; trace rows {trace['trace_rows']}; events `{json.dumps(trace['events'], sort_keys=True)}`.",
            "",
        ]
    lines += [
        "The control is the unchanged canonical source at the exact triggering head.",
        "This is matched official-engine evidence, not a hosted Kaggle or leaderboard result.",
    ]
    (work / "RESULTS.md").write_text("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
