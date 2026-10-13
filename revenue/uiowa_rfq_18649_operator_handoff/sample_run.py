#!/usr/bin/env python3
"""Run trusted synthetic samples and preserve explicit execution evidence.

A successful plan is not a successful execution. Each invocation owns a fresh or
empty output directory; an old result cannot be reused as this run's evidence.
This is a trusted-code runner, not a process, filesystem, or network sandbox.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from preflight import DEFAULT_MANIFEST, load_manifest, repo_root_from, validate

HERE = Path(__file__).resolve().parent
RECEIPT_NAME = "sample-run-receipt.json"
RESERVATION_NAME = ".sample-run-in-progress"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_command(command: list[str], out_dir: Path) -> list[str]:
    return [arg.replace("${OUT}", str(out_dir)) for arg in command]


def inventory_outputs(out_dir: Path) -> list[dict[str, Any]]:
    """Hash only this run's regular output files, excluding runner metadata."""
    results: list[dict[str, Any]] = []
    if not out_dir.exists():
        return results
    for path in sorted(out_dir.rglob("*")):
        rel = path.relative_to(out_dir)
        if rel.parts[0] == RESERVATION_NAME or rel.as_posix() == RECEIPT_NAME:
            continue
        if path.is_symlink():
            raise ValueError(f"output is a symbolic link, not a captured artifact: {rel}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f"output is not a regular file: {rel}")
        results.append({"path": rel.as_posix(), "bytes": path.stat().st_size,
                        "sha256": sha256_file(path)})
    return results


def _captured(data: bytes | str | None) -> bytes:
    # TimeoutExpired may expose bytes even when text mode is used by a caller.
    if data is None:
        return b""
    return data.encode("utf-8", errors="replace") if isinstance(data, str) else data


def _streams(stdout: bytes | str | None, stderr: bytes | str | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for name, value in (("stdout", stdout), ("stderr", stderr)):
        data = _captured(value)
        result[f"{name}_sha256"] = sha256_bytes(data)
        result[f"{name}_excerpt"] = data.decode("utf-8", errors="replace")[-4000:]
    return result


def _reserve_output(out_dir: Path) -> tuple[Path, Path]:
    if out_dir.is_symlink():
        raise ValueError("--out must not be a symbolic link")
    out_dir = out_dir.resolve()
    if out_dir.exists() and (not out_dir.is_dir() or any(out_dir.iterdir())):
        raise ValueError("--out must be a new or empty directory; previous results are never overwritten")
    out_dir.mkdir(parents=True, exist_ok=True)
    reservation = out_dir / RESERVATION_NAME
    # mkdir without exist_ok also rejects a concurrent cooperating runner.
    reservation.mkdir()
    # Another invocation may have completed after the first emptiness check
    # but before this reservation was acquired. Re-check while holding it.
    try:
        if any(path != reservation for path in out_dir.iterdir()):
            raise ValueError("--out changed before reservation; use a new or empty directory")
    except BaseException:
        reservation.rmdir()
        raise
    return out_dir, reservation


def run_sample(
    manifest: dict[str, Any],
    root: Path,
    out_dir: Path,
    timeout: float,
    dry_run: bool,
    selected_assets: set[str] | None = None,
) -> dict[str, Any]:
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("--timeout must be a finite number > 0")
    root = root.resolve()
    preflight = validate(manifest, root, selected_assets)
    if not preflight["ok"]:
        raise RuntimeError("preflight failed: " + "; ".join(preflight["errors"]))

    assets = manifest["assets"]
    pending_commands = [asset["asset_id"] for asset in assets
                        if asset["status"] == "pending_at_snapshot" and asset.get("sample_commands")]
    if pending_commands:
        raise ValueError(f"pending-at-snapshot assets cannot define executable sample commands: {pending_commands}")
    known = {asset["asset_id"] for asset in assets}
    executable = {asset["asset_id"] for asset in assets if asset.get("sample_commands")}
    selected = set(selected_assets or [])
    unknown = selected - known
    non_executable = selected - executable - unknown
    if unknown:
        raise ValueError(f"unknown --asset values: {sorted(unknown)}")
    if non_executable:
        raise ValueError(f"selected assets have no executable sample commands: {sorted(non_executable)}")
    plan = [asset for asset in assets if asset.get("sample_commands")
            and (not selected or asset["asset_id"] in selected)]
    planned_steps = sum(len(asset["sample_commands"]) for asset in plan)
    if not planned_steps:
        raise ValueError("selection contains no executable sample commands")

    # Bind to the actual manifest value, not a claimed checkout identity.
    manifest_digest = sha256_bytes(json.dumps(manifest, sort_keys=True, ensure_ascii=True,
                                            separators=(",", ":"), allow_nan=False).encode("utf-8"))
    out_dir, reservation = _reserve_output(out_dir)
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    steps: list[dict[str, Any]] = []
    errors: list[str] = []
    outputs: list[dict[str, Any]] = []
    status = "PLANNED" if dry_run else "PASSED"
    try:
        for asset in plan:
            workdir = (root / asset["working_dir"]).resolve()
            for index, command in enumerate(asset["sample_commands"]):
                resolved = resolve_command(command, out_dir)
                script = (workdir / command[0]).resolve()
                step: dict[str, Any] = {
                    "asset_id": asset["asset_id"], "work_order": asset["work_order"],
                    "command_index": index, "cwd": str(workdir.relative_to(root)),
                    "argv": [sys.executable, *resolved], "dry_run": dry_run,
                    "returncode": None, "elapsed_seconds": 0.0,
                    "status": "PLANNED" if dry_run else "PENDING",
                }
                started = time.perf_counter()
                try:
                    step["entrypoint_sha256"] = sha256_file(script)
                    if not dry_run:
                        completed = subprocess.run(
                            step["argv"], cwd=workdir, env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=timeout, check=False,
                        )
                        step.update(_streams(completed.stdout, completed.stderr))
                        step["returncode"] = completed.returncode
                        step["status"] = "PASSED" if completed.returncode == 0 else "FAILED"
                        step["entrypoint_sha256_after"] = sha256_file(script)
                        if step["entrypoint_sha256_after"] != step["entrypoint_sha256"]:
                            step["status"] = "SOURCE_CHANGED"
                            step["error"] = "entrypoint bytes changed during execution"
                except subprocess.TimeoutExpired as exc:
                    step.update(_streams(exc.output, exc.stderr))
                    step.update(status="TIMED_OUT", error=f"command exceeded {timeout:g} seconds",
                                timeout_seconds=timeout)
                except OSError as exc:
                    if "stdout_sha256" not in step:
                        step.update(_streams(None, None))
                    step.update(status="EXECUTION_ERROR", error=f"{type(exc).__name__}: {exc}")
                if not dry_run:
                    step["elapsed_seconds"] = round(time.perf_counter() - started, 6)
                steps.append(step)
                if step["status"] not in {"PASSED", "PLANNED"}:
                    status = step["status"]
                    errors.append(f"{asset['asset_id']} command[{index}]: {step.get('error', 'nonzero exit')}")
                    break
            if status not in {"PASSED", "PLANNED"}:
                break

        try:
            outputs = inventory_outputs(out_dir)
        except (OSError, ValueError) as exc:
            errors.append(f"output inventory failed: {exc}")
            status = "INVENTORY_FAILED"

        executed = sum(not step["dry_run"] and step["status"] != "PENDING" for step in steps)
        verified = (not dry_run and status == "PASSED" and len(steps) == planned_steps
                    and all(step["status"] == "PASSED" for step in steps))
        receipt: dict[str, Any] = {
            "schema": "uiowa.operator-sample-run.v1", "receipt_revision": 2,
            "snapshot_main_sha": manifest["snapshot_main_sha"],
            "snapshot_semantics": "catalog snapshot, NOT the identity of the executed checkout",
            "manifest_sha256": manifest_digest,
            "provenance_scope": "canonical manifest and entrypoint files only; imported dependencies are not hashed",
            "python_version": sys.version,
            "dry_run": dry_run, "status": status,
            "selected_assets": sorted(selected) if selected else "all_executable_assets",
            "preflight_scope": preflight["filesystem_scope"],
            "preflight_skipped_assets": preflight["skipped_assets"],
            "planned_steps": planned_steps, "attempted_steps": executed,
            "steps": steps, "outputs": outputs, "errors": errors,
            "preflight_warnings": preflight["warnings"],
            "execution_verified": verified,
            # Compatibility: true for a valid dry-run PLAN, never evidence of execution.
            "success": status == "PLANNED" or verified,
            "guardrails": [
                "No shell=True execution is used.",
                "Only explicitly selected executable manifest assets are planned.",
                "The output directory was new or empty and reserved for this invocation.",
                "Dry-run plans are explicitly non-executed; inspect execution_verified.",
                "This runs trusted Python code; it is not a process, filesystem, or network sandbox.",
            ],
        }
        receipt_path = out_dir / RECEIPT_NAME
        receipt["receipt_path"] = str(receipt_path)
        # Never overwrite a file that existed before this write, including a
        # conflicting file unexpectedly created by a child command.
        with receipt_path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n")
        return receipt
    finally:
        # Remove only the empty reservation directory created by this invocation.
        reservation.rmdir()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--out", type=Path, required=True, help="New or empty output directory (one per invocation).")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--asset", action="append", dest="assets",
                        help="Run only a named executable asset; repeat to select multiple.")
    args = parser.parse_args(argv)
    try:
        receipt = run_sample(load_manifest(args.manifest), (args.root or repo_root_from()).resolve(),
                             args.out, args.timeout, args.dry_run, set(args.assets or []) or None)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"UIOWA-100 sample: ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"UIOWA-100 sample: {receipt['status']} steps={len(receipt['steps'])} "
          f"scope={receipt['preflight_scope']} "
          f"outputs={len(receipt['outputs'])} dry_run={receipt['dry_run']} "
          f"execution_verified={receipt['execution_verified']}")
    print(receipt["receipt_path"])
    return 0 if receipt["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
