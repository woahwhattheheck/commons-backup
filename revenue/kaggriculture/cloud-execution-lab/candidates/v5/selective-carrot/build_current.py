# SPDX-License-Identifier: Apache-2.0
"""Materialize selective-carrot arms from an exact current V5 package."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
LAB_ROOT = HERE.parents[2]
SELECTIVE_SOURCE = HERE / "selective_carrot.py"
ENTRY_SOURCE = HERE / "current_entry.py"

# These are source identities, not a commit pin. The builder may remain valid
# across main commits that leave these exact implementation bytes unchanged.
EXPECTED_PARENT_MAIN_BLOB = "727c36ee3727db159f5879d4ac9a842a28ca570c"
EXPECTED_SELECTIVE_BLOB = "6af9a832dec058b7824fd7dd080f00ee50bb1d2f"
EXPECTED_ENTRY_BLOB = "f9cc0cecdb99d2711d33f9cec80c2f82d8f9dc89"


def git_blob_bytes(data: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def git_blob(path: Path) -> str:
    return git_blob_bytes(path.read_bytes())


def _regular_bytes(path: Path, label: str) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} must be a regular file")
    return path.read_bytes()


def _pinned_bytes(path: Path, expected: str, label: str) -> bytes:
    data = _regular_bytes(path, label)
    if git_blob_bytes(data) != expected:
        raise ValueError(f"{label} identity drift")
    return data


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


def _capacity(value: int) -> int:
    if type(value) is not int or value not in (4, 12):
        raise ValueError("max_active must be plain int 4 or 12")
    return value


def _source_snapshots() -> dict[str, bytes]:
    """Authenticate each mutable source once and return those exact bytes."""
    return {
        "selective": _pinned_bytes(
            SELECTIVE_SOURCE,
            EXPECTED_SELECTIVE_BLOB,
            "canonical selective-carrot source",
        ),
        "entry": _pinned_bytes(
            ENTRY_SOURCE,
            EXPECTED_ENTRY_BLOB,
            "canonical selective-carrot current entry",
        ),
        "parent": _pinned_bytes(
            LAB_ROOT / "main.py",
            EXPECTED_PARENT_MAIN_BLOB,
            "canonical current-V5 parent main.py",
        ),
    }


def build_candidate(
    baseline_root: Path, out: Path, max_active: int
) -> dict[str, object]:
    max_active = _capacity(max_active)
    baseline_root = baseline_root.resolve()
    out = out.resolve()
    if out.exists():
        raise ValueError("output directory must be new")
    if not baseline_root.is_dir():
        raise ValueError("baseline root must be a directory")
    if _at_or_below(out, baseline_root):
        raise ValueError("output directory must be outside baseline root")

    parent_main = baseline_root / "main.py"
    parent_main_bytes = _regular_bytes(parent_main, "baseline main.py")
    if git_blob_bytes(parent_main_bytes) != EXPECTED_PARENT_MAIN_BLOB:
        raise ValueError("expected exact current-V5 parent main.py")
    for collision in (
        "baseline_main.py",
        "selective_carrot.py",
        "CARROT-CAPACITY.json",
    ):
        if (baseline_root / collision).exists():
            raise ValueError(f"baseline already contains {collision}")

    sources = _source_snapshots()
    if parent_main_bytes != sources["parent"]:
        raise ValueError("CURRENT package parent differs from canonical source bytes")
    control_before = package_digest(baseline_root)
    try:
        shutil.copytree(
            baseline_root,
            out,
            symlinks=False,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
        copied_parent = _regular_bytes(out / "main.py", "copied baseline main.py")
        copied_control = package_digest(out)
        control_after = package_digest(baseline_root)
        if copied_parent != parent_main_bytes:
            raise ValueError("baseline main.py moved during materialization")
        if not control_before == copied_control == control_after:
            raise ValueError("baseline package moved during materialization")

        (out / "main.py").rename(out / "baseline_main.py")
        (out / "main.py").write_bytes(sources["entry"])
        (out / "selective_carrot.py").write_bytes(sources["selective"])
        profile = {
            "schema": "titan-v5-selective-carrot-current/v1",
            "max_active": max_active,
            "control_package_sha256": control_before,
            "parent_main_git_blob": EXPECTED_PARENT_MAIN_BLOB,
            "selective_carrot_git_blob": EXPECTED_SELECTIVE_BLOB,
            "entry_git_blob": EXPECTED_ENTRY_BLOB,
        }
        (out / "CARROT-CAPACITY.json").write_text(
            json.dumps(profile, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        candidate_digest = package_digest(out)
    except Exception:
        if out.exists():
            shutil.rmtree(out)
        raise

    return {
        "schema": "titan-v5-selective-carrot-current-build/v1",
        "max_active": max_active,
        "control_package_sha256": control_before,
        "candidate_package_sha256": candidate_digest,
        "parent_main_git_blob": EXPECTED_PARENT_MAIN_BLOB,
        "selective_carrot_git_blob": EXPECTED_SELECTIVE_BLOB,
        "entry_git_blob": EXPECTED_ENTRY_BLOB,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--max-active", required=True, type=int, choices=[4, 12])
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

    receipt = build_candidate(baseline_root, out, args.max_active)
    raw = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if receipt_path is not None:
        receipt_path.write_text(raw, encoding="utf-8")
    print(raw, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
