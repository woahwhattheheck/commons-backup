# SPDX-License-Identifier: Apache-2.0
"""Materialize the V5 animal-yield-cap treatment from an exact V5 package."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
LAB_ROOT = HERE.parents[2]
HELPER_SOURCE = (
    LAB_ROOT
    / "candidates/v4/repairs/gameplay/animal-yield-headroom/animal_headroom_harvest.py"
)
ENGINE_SOURCE = LAB_ROOT / "reference/engine/kaggriculture.py"
ENTRY_SOURCE = HERE / "entry.py"

EXPECTED_PARENT_MAIN_BLOB = "9cf8feaa9a755ffdf85d8878baa07b1fc7940192"
EXPECTED_HELPER_BLOB = "b371532dd0af54cb36768b07a39d5401f15df6f0"
EXPECTED_ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"


def git_blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def package_digest(root: Path) -> str:
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"symlink not allowed in package: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if "__pycache__" in relative.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        rows.append(
            [relative.as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()]
        )
    raw = json.dumps(rows, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(raw).hexdigest()


def _at_or_below(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _require_source_identity() -> None:
    if git_blob(HELPER_SOURCE) != EXPECTED_HELPER_BLOB:
        raise ValueError("canonical ANIMAL-HEADROOM helper drift")
    if git_blob(ENGINE_SOURCE) != EXPECTED_ENGINE_BLOB:
        raise ValueError("official engine authority drift")


def build_candidate(baseline_root: Path, out: Path) -> dict[str, str]:
    baseline_root = baseline_root.resolve()
    out = out.resolve()
    if out.exists():
        raise ValueError("output directory must be new")
    if not baseline_root.is_dir():
        raise ValueError("baseline root must be a directory")
    if _at_or_below(out, baseline_root):
        raise ValueError("output directory must be outside baseline root")
    parent_main = baseline_root / "main.py"
    if not parent_main.is_file() or parent_main.is_symlink():
        raise ValueError("baseline main.py must be a regular file")
    if git_blob(parent_main) != EXPECTED_PARENT_MAIN_BLOB:
        raise ValueError("expected exact current V5 parent main.py")
    if (baseline_root / "baseline_main.py").exists():
        raise ValueError("baseline already contains baseline_main.py")
    if (baseline_root / "animal_headroom_harvest.py").exists():
        raise ValueError("baseline already contains animal_headroom_harvest.py")

    _require_source_identity()
    control_before = package_digest(baseline_root)
    try:
        shutil.copytree(
            baseline_root,
            out,
            symlinks=False,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
        copied_control = package_digest(out)
        control_after = package_digest(baseline_root)
        if not control_before == copied_control == control_after:
            raise ValueError("baseline package moved during materialization")

        (out / "main.py").rename(out / "baseline_main.py")
        shutil.copyfile(ENTRY_SOURCE, out / "main.py")
        shutil.copyfile(HELPER_SOURCE, out / "animal_headroom_harvest.py")
        candidate_digest = package_digest(out)
    except Exception:
        if out.exists():
            shutil.rmtree(out)
        raise

    return {
        "schema": "titan-v5-animal-yield-cap-candidate/v1",
        "control_package_sha256": control_before,
        "candidate_package_sha256": candidate_digest,
        "parent_main_git_blob": EXPECTED_PARENT_MAIN_BLOB,
        "helper_git_blob": EXPECTED_HELPER_BLOB,
        "engine_git_blob": EXPECTED_ENGINE_BLOB,
        "entry_git_blob": git_blob(ENTRY_SOURCE),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args(argv)

    baseline_root = args.baseline_root.resolve()
    out = args.out.resolve()
    receipt_path = args.receipt.resolve() if args.receipt else None
    if receipt_path is not None:
        if receipt_path.exists():
            raise ValueError("receipt path must be new")
        if _at_or_below(receipt_path, baseline_root) or _at_or_below(
            receipt_path, out
        ):
            raise ValueError("receipt path must be outside package roots")

    receipt = build_candidate(baseline_root, out)
    raw = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if receipt_path is not None:
        receipt_path.write_text(raw)
    print(raw, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
