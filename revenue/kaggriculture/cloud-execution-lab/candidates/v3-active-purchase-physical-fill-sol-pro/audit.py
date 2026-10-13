# SPDX-License-Identifier: Apache-2.0
"""Fail-closed source, carrier, evaluator, and experiment audit."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any

from materialize import (
    EXPECTED_POINTER_GIT_BLOB,
    EXPECTED_SOURCE_GIT_BLOB,
    POINTER,
    SOURCE,
    git_blob_sha1_bytes,
    materialize,
)
from physical_fill import (
    EXPECTED_ENGINE_GIT_BLOB,
    EXPECTED_FROZEN_SELECTED_GIT_BLOB,
    EXPECTED_SCHEDULER_GIT_BLOB,
    NEW_METHOD,
    git_blob_sha1,
    patch_scheduler_bytes,
)
from trace_evaluator import EXPECTED_EVALUATOR_GIT_BLOB, git_blob, transform

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
REPO = LAB.parents[2]
EVALUATOR = LAB.parent / "cloud-eval" / "evaluate.py"
WORKFLOW = REPO / ".github" / "workflows" / "titan-v3-active-purchase-physical-fill-sol-pro.yml"
README = HERE / "README.md"
RUN_PANEL = HERE / "run_panel.sh"
COMPARE = HERE / "compare.py"
OPERATION = "TITAN-V3-ACTIVE-PURCHASE-PHYSICAL-FILL-20260910-01"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_regular(path: Path) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(f"required regular file missing: {path}")
    return path.read_bytes()


def audit() -> dict[str, Any]:
    scheduler = LAB / "scheduler.py"
    frozen = LAB / "frozen_selected.py"
    engine = LAB / "reference" / "engine" / "kaggriculture.py"
    source_identities = {
        "scheduler.py": git_blob_sha1(scheduler),
        "frozen_selected.py": git_blob_sha1(frozen),
        "reference/engine/kaggriculture.py": git_blob_sha1(engine),
        "runtime/integrated-selected/CURRENT-ARCHIVE.json": git_blob_sha1_bytes(require_regular(POINTER)),
        "runtime/integrated-selected/CURRENT-SOURCE.json": git_blob_sha1_bytes(require_regular(SOURCE)),
        "../cloud-eval/evaluate.py": git_blob(require_regular(EVALUATOR)),
    }
    expected = {
        "scheduler.py": EXPECTED_SCHEDULER_GIT_BLOB,
        "frozen_selected.py": EXPECTED_FROZEN_SELECTED_GIT_BLOB,
        "reference/engine/kaggriculture.py": EXPECTED_ENGINE_GIT_BLOB,
        "runtime/integrated-selected/CURRENT-ARCHIVE.json": EXPECTED_POINTER_GIT_BLOB,
        "runtime/integrated-selected/CURRENT-SOURCE.json": EXPECTED_SOURCE_GIT_BLOB,
        "../cloud-eval/evaluate.py": EXPECTED_EVALUATOR_GIT_BLOB,
    }
    if source_identities != expected:
        raise RuntimeError(f"source identity drift: {source_identities}")

    candidate_scheduler, patch_receipt = patch_scheduler_bytes(require_regular(scheduler))
    if candidate_scheduler.count(NEW_METHOD) != 1:
        raise RuntimeError("candidate scheduler does not contain one replacement method")
    evaluator_source = require_regular(EVALUATOR)
    evaluator_candidate = transform(evaluator_source)

    with tempfile.TemporaryDirectory(prefix="titan-active-fill-audit-") as tmp:
        materialization = materialize(Path(tmp) / "arms")
    if materialization["candidate"]["changed_members"] != ["scheduler.py"]:
        raise RuntimeError("materializer changed more than scheduler.py")

    workflow = require_regular(WORKFLOW).decode("utf-8")
    run_panel = require_regular(RUN_PANEL).decode("utf-8")
    readme = require_regular(README).decode("utf-8")
    compare = require_regular(COMPARE).decode("utf-8")
    required_fragments = {
        "workflow": [
            "python -m unittest -v test_physical_fill.py",
            "bash \"$CASE/run_panel.sh\"",
            "python build_integrated.py --check",
        ],
        "run_panel": [
            "--opponent \"arlene=",
            "--opponent \"v1=",
            "--materialization \"$OUT/MATERIALIZATION.json\"",
            "--evaluator-receipt \"$OUT/EVALUATOR-PATCH.json\"",
        ],
        "README": [OPERATION, "same-turn", "fails closed"],
        "compare": [OPERATION, "tested_action_sha256", "EXPECTED_SEEDS"],
    }
    documents = {"workflow": workflow, "run_panel": run_panel, "README": readme, "compare": compare}
    for name, fragments in required_fragments.items():
        for fragment in fragments:
            if fragment not in documents[name]:
                raise RuntimeError(f"{name} contract fragment missing: {fragment}")

    candidate_files = {}
    for path in sorted(HERE.iterdir()):
        if path.is_file() and not path.is_symlink():
            candidate_files[path.name] = {
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
    return {
        "schema_version": 1,
        "operation": OPERATION,
        "source_identities": source_identities,
        "patch": patch_receipt,
        "evaluator": {
            "source_git_blob": git_blob(evaluator_source),
            "generated_git_blob": git_blob(evaluator_candidate),
            "generated_sha256": hashlib.sha256(evaluator_candidate).hexdigest(),
        },
        "materialization": materialization,
        "candidate_files": candidate_files,
        "canonical_mutation": False,
        "kaggle_mutation": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()
    result = audit()
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "operation": result["operation"],
        "source_members": len(result["source_identities"]),
        "changed_members": result["materialization"]["candidate"]["changed_members"],
        "candidate_files": len(result["candidate_files"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
