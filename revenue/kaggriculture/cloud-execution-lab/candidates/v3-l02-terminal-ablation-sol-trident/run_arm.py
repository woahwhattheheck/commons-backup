# SPDX-License-Identifier: Apache-2.0
"""Run one L02 ablation arm through the existing complete paired panel."""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import sys

from ablation import ARMS

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "v3-l02-ledger-tranche"
RUNNER = SOURCE / "run_panel.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("_sol_trident_l02_panel", RUNNER)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {RUNNER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--arm", choices=ARMS, required=True)
    known, remaining = parser.parse_known_args(argv)
    arm = known.arm
    entry = HERE / f"candidate_{arm}.py"
    if not entry.is_file():
        raise FileNotFoundError(entry)

    runner = _load_runner()
    original_dependency_receipt = runner.dependency_receipt
    original_markdown = runner.markdown

    def agent_spec(variant: str) -> str:
        path = runner.LAB / "main.py" if variant == "baseline" else entry
        return str(path.resolve()) + "::agent"

    def dependency_receipt(head: str, *, evaluator=None):
        saved_here = runner.HERE
        runner.HERE = SOURCE
        try:
            receipt = original_dependency_receipt(head, evaluator=evaluator)
        finally:
            runner.HERE = saved_here
        receipt["sha256"]["candidate"] = runner.sha256_file(entry)
        receipt["sha256"]["candidate_base"] = runner.sha256_file(HERE / "candidate_base.py")
        receipt["sha256"]["ablation"] = runner.sha256_file(HERE / "ablation.py")
        receipt["ablation_arm"] = arm
        receipt["ablation_bundle"] = runner.tree_sha256(HERE)
        return receipt

    def markdown(report):
        text = original_markdown(report)
        return text.replace(
            "# TITAN L02 ledger-coherent tranche — development panel",
            f"# TITAN L02 `{arm}` ablation — development screen",
            1,
        )

    runner._agent_spec = agent_spec
    runner.dependency_receipt = dependency_receipt
    runner.markdown = markdown
    return int(runner.main(remaining))


if __name__ == "__main__":
    raise SystemExit(main())
