# SPDX-License-Identifier: Apache-2.0
"""Deterministic cross-episode reset oracle for TITAN.

The production candidate keeps its one-second deadline unchanged.  This verifier
changes only the isolated test worker's deadline timer implementation so the
reset-invariance oracle measures retained process state instead of virtualized
runner wall-clock jitter from ``sys.settrace()``.  The existing outer
``ThreadPoolExecutor.result(timeout=2)`` watchdog remains active for every
candidate call, so a blocking/hung callback still fails the verifier.

Deadline semantics are covered separately by the production deadline tests.  In
this oracle, both AB and BA execute the complete candidate path without a
jitter-dependent fallback PASS, then the retained reset harness compares exact
action hashes and terminal rewards and still proves step-zero instance
replacement.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

# ``python -I /abs/path/to/this.py`` deliberately does not prepend the script
# directory to sys.path.  The hosted live-source proof uses isolated mode, so
# bootstrap only this reviewed verifier directory before importing its retained
# sibling harness.  Candidate/source roots are still added separately by the
# retained loader and are never inferred from the caller working directory.
HERE = Path(__file__).resolve()
LAB = HERE.parent
if str(LAB) not in sys.path:
    sys.path.insert(0, str(LAB))

import test_worker_reset as reset


def install_deterministic_deadline(root: Path):
    """Disable only wall-clock cancellation in this isolated verifier process.

    Return the original timer class so focused unit tests can restore it.  The
    replacement intentionally does not install ``sys.settrace`` or touch the
    deadline ContextVar.  It preserves the exact ``DeadlineExceeded`` identity
    expected by caller exception handling but never raises it.
    """
    root = Path(root).resolve()
    for item in (root, root / "checks"):
        text = str(item)
        if text not in sys.path:
            sys.path.insert(0, text)

    import titan_runtime

    deadline = titan_runtime.deadline
    original = deadline._DeadlineTimer
    if getattr(original, "_titan_reset_deterministic_oracle", False):
        return getattr(original, "_titan_reset_original_timer", original)

    class _NoWallClockTimer:
        _titan_reset_deterministic_oracle = True
        _titan_reset_original_timer = original

        def __init__(self, seconds):
            self.seconds = float(seconds)
            self.expired = deadline.DeadlineExceeded(
                "wall-clock cancellation disabled in deterministic reset oracle"
            )

        def __enter__(self):
            return self

        def __exit__(self, _kind, _error, _traceback):
            return False

    deadline._DeadlineTimer = _NoWallClockTimer
    return original


def run_worker(root: Path, order: list[str], output: Path) -> dict[str, Any]:
    install_deterministic_deadline(root)
    result = reset._worker(Path(root), list(order))
    result["deadline_mode"] = "deterministic-reset-oracle/no-wallclock-cancellation"
    output = Path(output)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def _run_worker(_script: Path, root: Path, order: list[str], output: Path):
    """Adapter used by reset._verify(); always launch this deterministic worker."""
    process = subprocess.run(
        [
            sys.executable,
            "-I",
            str(HERE),
            "--worker",
            str(root),
            "--order",
            *order,
            "--output",
            str(output),
        ],
        cwd=Path(root).parent,
        capture_output=True,
        text=True,
        timeout=360,
    )
    if process.returncode:
        raise RuntimeError(process.stdout + process.stderr)
    return json.loads(Path(output).read_text(encoding="utf-8"))


def verify() -> dict[str, Any]:
    """Reuse the retained oracle topology with deterministic worker execution."""
    original_run_worker = reset._run_worker
    reset._run_worker = _run_worker
    try:
        receipt = reset._verify()
    finally:
        reset._run_worker = original_run_worker

    receipt = dict(receipt)
    receipt["schema"] = "titan-v4-reset-invariance-deterministic/v1"
    receipt["deadline_mode"] = "deterministic-reset-oracle/no-wallclock-cancellation"
    receipt["claim"] = (
        "For these two full official-interpreter games on one persistent worker "
        "thread, with wall-clock deadline cancellation disabled only inside the "
        "isolated reset oracle, action trace and terminal result are identical "
        "whether each game runs first in a fresh process or second after the "
        "other game; step zero replaces the prior TitanAgent singleton. The "
        "per-call two-second outer worker watchdog remains active."
    )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--order", nargs="*", choices=sorted(reset.SCENARIOS))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.worker is not None:
        if not args.order or args.output is None:
            parser.error("--worker requires --order and --output")
        run_worker(args.worker, args.order, args.output)
        return 0

    if args.order or args.output is not None:
        parser.error("--order/--output require --worker")
    print(json.dumps(verify(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
