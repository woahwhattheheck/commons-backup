# SPDX-License-Identifier: Apache-2.0
"""Promotion attempt orchestration.

Builds per-predecessor gate bundles from a pinned submission, shells out
to the *existing* gate scripts (never a reimplementation), and returns the
structured outcome the receipt layer seals.

Two strategies:

* ``paired`` (default) — one ``gate.py`` invocation per predecessor slot
  (frozen control, LAND, ...) against the same pinned candidate snapshot.
  Verdict is PROMOTE only when every slot promotes.
* ``dual`` — the atomic ``dual_predecessor_gate.py`` comparison, used when
  the two predecessor slots carry genuinely distinct artifact identities.
  The queue generates the strict run-custody receipts the dual gate
  demands, bound to the exact bytes it snapshotted.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping

from . import GATE_DIR_NAME, POLICY_VERSION
from .pinning import PinStore, canonical_json, sha256_bytes, sha256_file, utcnow_iso

HERE = Path(__file__).resolve().parent.parent
DEFAULT_GATE_DIR = HERE.parent / GATE_DIR_NAME

EXIT_PROMOTE = 0
EXIT_INVALID = 2
EXIT_REJECT = 3

CUSTODY_RECEIPT_TYPE = "titan-paired-run-custody/v1"


class RunError(Exception):
    pass


# --------------------------------------------------------------------------
# config
# --------------------------------------------------------------------------

def load_predecessor_config(path: Path) -> dict:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if config.get("schema_version") != 1:
        raise RunError("predecessor config schema_version must be 1")
    for key in ("engine", "runner", "slots"):
        if key not in config:
            raise RunError(f"predecessor config missing key: {key}")
    slots = config["slots"]
    if len(slots) < 1:
        raise RunError("predecessor config needs at least one slot")
    names = [slot["name"] for slot in slots.values()]
    if len(set(names)) != len(names):
        raise RunError("predecessor slot names must be distinct")
    return config


def _hex(value: str, lengths: tuple[int, ...], label: str) -> str:
    if not isinstance(value, str) or len(value) not in lengths:
        raise RunError(f"{label}: expected {' or '.join(map(str, lengths))} hex chars")
    try:
        int(value, 16)
    except ValueError as exc:
        raise RunError(f"{label}: expected hexadecimal") from exc
    return value.lower()


def _commit(value: str, label: str) -> str:
    return _hex(value, (40, 64), label)


# --------------------------------------------------------------------------
# grid + bundle construction
# --------------------------------------------------------------------------

def extract_grid(games_path: Path) -> dict:
    """Declared grid derived deterministically from a pinned games panel."""
    seeds: set[int] = set()
    opponents: set[str] = set()
    seats: set[int] = set()
    count = 0
    with open(games_path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            seed = row.get("seed")
            opponent = row.get("opponent")
            seat = row.get("candidate_seat")
            if not isinstance(seed, int) or isinstance(seed, bool):
                raise RunError(f"non-integer seed in {games_path}")
            if not isinstance(opponent, str) or not opponent:
                raise RunError(f"bad opponent in {games_path}")
            if seat not in (0, 1):
                raise RunError(f"bad candidate_seat in {games_path}")
            seeds.add(seed)
            opponents.add(opponent)
            seats.add(seat)
            count += 1
    if not seeds or not opponents or seats != {0, 1}:
        raise RunError(f"incomplete grid in {games_path}")
    expected = len(seeds) * len(opponents) * 2
    if count != expected:
        raise RunError(
            f"row count {count} != grid {len(seeds)}x{len(opponents)}x2 in {games_path}"
        )
    return {
        "seeds": sorted(seeds),
        "opponents": sorted(opponents),
        "seats": [0, 1],
        "expected_cells": expected,
    }


def build_provenance(
    *,
    engine_commit: str,
    engine_sha256: str,
    runner_commit: str,
    runner_sha256: str,
    baseline_artifact_sha256: str,
    candidate_artifact_sha256: str,
) -> dict:
    return {
        "engine_commit": _commit(engine_commit, "engine.commit"),
        "engine_sha256": _hex(engine_sha256, (64,), "engine.sha256"),
        "runner_commit": _commit(runner_commit, "runner.commit"),
        "runner_sha256": _hex(runner_sha256, (64,), "runner.sha256"),
        "baseline_artifact_sha256": _hex(
            baseline_artifact_sha256, (64,), "baseline artifact"
        ),
        "candidate_artifact_sha256": _hex(
            candidate_artifact_sha256, (64,), "candidate artifact"
        ),
    }


def build_contract(
    *,
    panel_id: str,
    baseline_name: str,
    candidate_name: str,
    grid: Mapping,
    provenance: Mapping,
    policy: Mapping,
) -> dict:
    return {
        "schema_version": 1,
        "panel_id": panel_id,
        "baseline_name": baseline_name,
        "candidate_name": candidate_name,
        "seeds": list(grid["seeds"]),
        "opponents": list(grid["opponents"]),
        "seats": [0, 1],
        "expected_cells": grid["expected_cells"],
        "provenance": dict(provenance),
        "policy": dict(policy),
    }


def build_evidence(*, panel_id: str, provenance: Mapping, exact_command: str) -> dict:
    return {
        "schema_version": 1,
        "panel_id": panel_id,
        "provenance": dict(provenance),
        "exact_command": exact_command,
    }


def build_custody_receipt(
    *,
    panel_id: str,
    baseline_name: str,
    candidate_name: str,
    exact_command: str,
    provenance: Mapping,
    grid: Mapping,
    file_hashes: Mapping[str, str],
) -> dict:
    """Strict run-custody receipt (titan-paired-run-custody/v1) for one slot."""
    return {
        "schema_version": 1,
        "receipt_type": CUSTODY_RECEIPT_TYPE,
        "panel_id": panel_id,
        "baseline_name": baseline_name,
        "candidate_name": candidate_name,
        "exact_command": exact_command,
        "provenance": dict(provenance),
        "grid": {
            "seeds": sorted(grid["seeds"]),
            "opponents": sorted(grid["opponents"]),
            "seats": sorted(grid["seats"]),
            "expected_cells": grid["expected_cells"],
        },
        "sha256": {
            key: _hex(file_hashes[key], (64,), f"custody sha256.{key}")
            for key in (
                "contract",
                "evidence",
                "engine_artifact",
                "runner_artifact",
                "baseline_artifact",
                "candidate_artifact",
                "baseline_games",
                "candidate_games",
            )
        },
    }


def _write_json(path: Path, value: Mapping) -> str:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return sha256_file(path)


# --------------------------------------------------------------------------
# gate invocation (wire the existing scripts; never reimplement them)
# --------------------------------------------------------------------------

def _invoke_gate(script: Path, args: list[str], *, cwd: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, str(script), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=3600,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _report_summary(report: Mapping) -> dict:
    checks = report.get("checks", [])
    aggregate = ((report.get("metrics") or {}).get("aggregate") or {})
    own_delta = aggregate.get("own_delta") or {}
    return {
        "verdict": report.get("verdict"),
        "valid": report.get("valid"),
        "panel_id": report.get("panel_id"),
        "grid": report.get("grid"),
        "failed_checks": sorted(
            item.get("name") for item in checks if not item.get("pass")
        ),
        "aggregate": {
            "mean_own_delta": own_delta.get("mean"),
            "median_own_delta": own_delta.get("median"),
            "mean_margin_delta": (aggregate.get("margin_delta") or {}).get("mean"),
            "result_regressions": aggregate.get("result_regressions"),
            "new_losses": aggregate.get("new_losses"),
        },
    }


# --------------------------------------------------------------------------
# attempt
# --------------------------------------------------------------------------

class Attempt:
    def __init__(
        self,
        *,
        state_dir: Path,
        gate_dir: Path = DEFAULT_GATE_DIR,
        gate_script: Path | None = None,
        dual_gate_script: Path | None = None,
    ) -> None:
        self.state_dir = Path(state_dir)
        self.gate_dir = Path(gate_dir)
        self.gate_script = gate_script or self.gate_dir / "gate.py"
        self.dual_gate_script = dual_gate_script or self.gate_dir / "dual_predecessor_gate.py"
        for script in (self.gate_script, self.dual_gate_script):
            if not script.is_file():
                raise RunError(f"gate script missing: {script}")
        self.pins = PinStore(self.state_dir / "pin-store")
        self.gate_sha256 = {
            "gate.py": sha256_file(self.gate_script),
            "dual_predecessor_gate.py": sha256_file(self.dual_gate_script),
        }

    # -- preparation -----------------------------------------------------
    def prepare(
        self,
        *,
        submission_id: str,
        candidate_name: str,
        pin_manifest: Mapping,
        config: Mapping,
        policy: Mapping,
        strategy: str = "auto",
    ) -> dict:
        """Pin artifacts, derive per-slot bundles. Pure until gate runs."""
        work = Path(tempfile.mkdtemp(prefix=f"pq-{submission_id}-"))
        inputs = pin_manifest["inputs"]
        candidate_artifact = self.pins.blob_path(inputs["candidate_artifact"]["sha256"])
        candidate_games = self.pins.blob_path(inputs["candidate_games"]["sha256"])
        candidate_artifact_sha = inputs["candidate_artifact"]["sha256"]
        candidate_games_sha = inputs["candidate_games"]["sha256"]

        engine_cfg, runner_cfg = config["engine"], config["runner"]
        engine_artifact = self.pins.put_blob(Path(engine_cfg["identity_file"]))
        runner_artifact = self.pins.put_blob(Path(runner_cfg["identity_file"]))

        slots: dict[str, dict] = {}
        for slot_key, slot_cfg in config["slots"].items():
            baseline_games_src = Path(slot_cfg["games"])
            baseline_games = self.pins.put_blob(baseline_games_src)
            baseline_artifact = self.pins.put_blob(Path(slot_cfg["artifact_file"]))
            grid = extract_grid(self.pins.blob_path(baseline_games["sha256"]))
            if "expected_grid" in slot_cfg:
                declared = slot_cfg["expected_grid"]
                for key in ("seeds", "opponents", "seats", "expected_cells"):
                    if grid[key] != declared[key]:
                        raise RunError(
                            f"slot {slot_key}: observed grid drift on {key}"
                        )
            provenance = build_provenance(
                engine_commit=engine_cfg["commit"],
                engine_sha256=engine_artifact["sha256"],
                runner_commit=runner_cfg["commit"],
                runner_sha256=runner_artifact["sha256"],
                baseline_artifact_sha256=baseline_artifact["sha256"],
                candidate_artifact_sha256=candidate_artifact_sha,
            )
            panel_id = f"{submission_id}-vs-{slot_key}"
            exact_command = (
                f"promote.py run --id {submission_id} "
                f"[queue strategy; slot={slot_key} panel={panel_id}]"
            )
            contract = build_contract(
                panel_id=panel_id,
                baseline_name=slot_cfg["name"],
                candidate_name=candidate_name,
                grid=grid,
                provenance=provenance,
                policy=policy,
            )
            evidence = build_evidence(
                panel_id=panel_id,
                provenance=provenance,
                exact_command=exact_command,
            )
            slot_dir = work / slot_key
            slot_dir.mkdir(parents=True, exist_ok=True)
            contract_sha = _write_json(slot_dir / "CONTRACT.json", contract)
            evidence_sha = _write_json(slot_dir / "PROVENANCE.json", evidence)
            slots[slot_key] = {
                "key": slot_key,
                "name": slot_cfg["name"],
                "panel_id": panel_id,
                "exact_command": exact_command,
                "grid": grid,
                "provenance": provenance,
                "contract_sha256": contract_sha,
                "evidence_sha256": evidence_sha,
                "baseline_games_sha256": baseline_games["sha256"],
                "baseline_artifact_sha256": baseline_artifact["sha256"],
                "dir": slot_dir,
            }

        if strategy == "auto":
            artifact_shas = {s["baseline_artifact_sha256"] for s in slots.values()}
            strategy = (
                "dual"
                if len(slots) == 2 and len(artifact_shas) == 2
                else "paired"
            )
        elif strategy not in ("paired", "dual"):
            raise RunError(f"unknown strategy: {strategy}")
        if strategy == "dual" and len(slots) != 2:
            raise RunError("dual strategy needs exactly two predecessor slots")

        return {
            "work_dir": work,
            "submission_id": submission_id,
            "candidate_name": candidate_name,
            "strategy": strategy,
            "candidate_artifact": candidate_artifact,
            "candidate_games": candidate_games,
            "candidate_artifact_sha256": candidate_artifact_sha,
            "candidate_games_sha256": candidate_games_sha,
            "engine_artifact_sha256": engine_artifact["sha256"],
            "runner_artifact_sha256": runner_artifact["sha256"],
            "slots": slots,
        }

    # -- paired strategy -------------------------------------------------
    def _run_paired(self, prepped: Mapping) -> list[dict]:
        comparisons = []
        for slot_key, slot in prepped["slots"].items():
            slot_dir = slot["dir"]
            report_path = slot_dir / "GATE-REPORT.json"
            started = time.monotonic()
            code, stdout, stderr = _invoke_gate(
                self.gate_script,
                [
                    "--contract", str(slot_dir / "CONTRACT.json"),
                    "--evidence", str(slot_dir / "PROVENANCE.json"),
                    "--baseline", str(self.pins.blob_path(slot["baseline_games_sha256"])),
                    "--candidate", str(prepped["candidate_games"]),
                    "--report", str(report_path),
                ],
                cwd=self.gate_dir,
            )
            elapsed_ms = int((time.monotonic() - started) * 1000)
            if code == EXIT_INVALID or not report_path.is_file():
                raise RunError(
                    f"slot {slot_key}: gate INVALID "
                    f"(exit={code}) stdout={stdout[-2000:]} stderr={stderr[-2000:]}"
                )
            if code not in (EXIT_PROMOTE, EXIT_REJECT):
                raise RunError(
                    f"slot {slot_key}: unexpected gate exit={code} "
                    f"stderr={stderr[-2000:]}"
                )
            report = json.loads(report_path.read_text(encoding="utf-8"))
            summary = _report_summary(report)
            comparisons.append(
                {
                    "slot": slot_key,
                    "strategy": "paired",
                    "baseline_name": slot["name"],
                    "panel_id": slot["panel_id"],
                    "verdict": summary["verdict"],
                    "exit_code": code,
                    "report_sha256": sha256_file(report_path),
                    "grid": summary["grid"],
                    "failed_checks": summary["failed_checks"],
                    "aggregate": summary["aggregate"],
                    "input_sha256": {
                        "contract": slot["contract_sha256"],
                        "evidence": slot["evidence_sha256"],
                        "baseline_games": slot["baseline_games_sha256"],
                        "candidate_games": prepped["candidate_games_sha256"],
                    },
                    "duration_ms": elapsed_ms,
                }
            )
        return comparisons

    # -- dual strategy ---------------------------------------------------
    def _run_dual(self, prepped: Mapping) -> list[dict]:
        slot_keys = list(prepped["slots"])
        slot_a, slot_b = (prepped["slots"][k] for k in slot_keys)
        file_hashes_base = {
            "engine_artifact": prepped["engine_artifact_sha256"],
            "runner_artifact": prepped["runner_artifact_sha256"],
            "candidate_artifact": prepped["candidate_artifact_sha256"],
            "candidate_games": prepped["candidate_games_sha256"],
        }
        args: list[str] = []
        dual_summaries = []
        for slot, prefix in ((slot_a, "predecessor-a"), (slot_b, "predecessor-b")):
            slot_dir = slot["dir"]
            file_hashes = {
                **file_hashes_base,
                "contract": slot["contract_sha256"],
                "evidence": slot["evidence_sha256"],
                "baseline_artifact": slot["baseline_artifact_sha256"],
                "baseline_games": slot["baseline_games_sha256"],
            }
            receipt = build_custody_receipt(
                panel_id=slot["panel_id"],
                baseline_name=slot["name"],
                candidate_name=prepped["candidate_name"],
                exact_command=slot["exact_command"],
                provenance=slot["provenance"],
                grid=slot["grid"],
                file_hashes=file_hashes,
            )
            receipt_sha = _write_json(slot_dir / "CUSTODY-RECEIPT.json", receipt)
            args += [
                f"--{prefix}-contract", str(slot_dir / "CONTRACT.json"),
                f"--{prefix}-evidence", str(slot_dir / "PROVENANCE.json"),
                f"--{prefix}-games",
                str(self.pins.blob_path(slot["baseline_games_sha256"])),
                f"--{prefix}-receipt", str(slot_dir / "CUSTODY-RECEIPT.json"),
                f"--{prefix}-artifact",
                str(self.pins.blob_path(slot["baseline_artifact_sha256"])),
            ]
            dual_summaries.append({"slot": slot["key"], "receipt_sha256": receipt_sha})
        work = prepped["work_dir"]
        report_path = work / "DUAL-GATE-REPORT.json"
        args += [
            "--candidate-games", str(prepped["candidate_games"]),
            "--candidate-artifact",
            str(self.pins.blob_path(prepped["candidate_artifact_sha256"])),
            "--engine-artifact",
            str(self.pins.blob_path(prepped["engine_artifact_sha256"])),
            "--runner-artifact",
            str(self.pins.blob_path(prepped["runner_artifact_sha256"])),
            "--report", str(report_path),
        ]
        started = time.monotonic()
        code, stdout, stderr = _invoke_gate(
            self.dual_gate_script, args, cwd=self.gate_dir
        )
        elapsed_ms = int((time.monotonic() - started) * 1000)
        if code == EXIT_INVALID or not report_path.is_file():
            raise RunError(
                f"dual gate INVALID (exit={code}) "
                f"stdout={stdout[-2000:]} stderr={stderr[-2000:]}"
            )
        if code not in (EXIT_PROMOTE, EXIT_REJECT):
            raise RunError(f"dual gate unexpected exit={code} stderr={stderr[-2000:]}")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        verdict = report.get("verdict")
        inner_reports = report.get("comparisons", {})
        comparisons = []
        for item, dual_key in zip(dual_summaries, ("predecessor_a", "predecessor_b")):
            inner = inner_reports.get(dual_key, {})
            comparisons.append(
                {
                    "slot": item["slot"],
                    "strategy": "dual",
                    "verdict": inner.get("verdict"),
                    "exit_code": code,
                    "report_sha256": sha256_file(report_path),
                    "custody_receipt_sha256": item["receipt_sha256"],
                    "grid": (inner.get("grid") or {}),
                    "failed_checks": sorted(
                        c.get("name")
                        for c in (inner.get("checks") or [])
                        if not c.get("pass")
                    ),
                    "duration_ms": elapsed_ms,
                }
            )
        if verdict != "PROMOTE" and all(
            c["verdict"] == "PROMOTE" for c in comparisons
        ):
            raise RunError("dual gate verdict disagrees with comparison verdicts")
        return comparisons

    # -- full attempt ----------------------------------------------------
    def execute(
        self,
        *,
        submission_id: str,
        candidate_name: str,
        pin_manifest: Mapping,
        config: Mapping,
        policy: Mapping,
        strategy: str = "auto",
    ) -> dict:
        started_at = utcnow_iso()
        started = time.monotonic()
        prepped = self.prepare(
            submission_id=submission_id,
            candidate_name=candidate_name,
            pin_manifest=pin_manifest,
            config=config,
            policy=policy,
            strategy=strategy,
        )
        try:
            if prepped["strategy"] == "dual":
                comparisons = self._run_dual(prepped)
            else:
                comparisons = self._run_paired(prepped)
        finally:
            pass  # work dir retained under state for audit; see below
        verdict = (
            "PROMOTE"
            if comparisons and all(c["verdict"] == "PROMOTE" for c in comparisons)
            else "REJECT"
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        audit_dir = self.state_dir / "attempts" / submission_id
        audit_dir.mkdir(parents=True, exist_ok=True)
        work = prepped["work_dir"]
        target = audit_dir / f"attempt-{len(list(audit_dir.glob('attempt-*')))}"
        work.replace(target)
        return {
            "submission_id": submission_id,
            "strategy": prepped["strategy"],
            "verdict": verdict,
            "comparisons": comparisons,
            "gate_sha256": self.gate_sha256,
            "predecessor_identity": {
                slot_key: {
                    "name": slot["name"],
                    "artifact_sha256": slot["baseline_artifact_sha256"],
                    "games_sha256": slot["baseline_games_sha256"],
                    "contract_sha256": slot["contract_sha256"],
                    "evidence_sha256": slot["evidence_sha256"],
                    "panel_id": slot["panel_id"],
                }
                for slot_key, slot in prepped["slots"].items()
            },
            "timings": {
                "started_at": started_at,
                "finished_at": utcnow_iso(),
                "duration_ms": duration_ms,
                "per_slot_ms": {
                    c["slot"]: c["duration_ms"] for c in comparisons
                },
            },
            "audit_dir": str(target),
        }
