# SPDX-License-Identifier: Apache-2.0
"""Exact-source current-ABI carrier for #12019 final SpatialTempo revalidation."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Final

TARGET: Final = Path("revenue/kaggriculture/cloud-execution-lab/main.py")
SPATIAL_TARGET: Final = Path("revenue/kaggriculture/cloud-execution-lab/spatial_tempo.py")
EXPECTED_MAIN_GIT_BLOB_SHA1: Final = "727c36ee3727db159f5879d4ac9a842a28ca570c"
EXPECTED_SPATIAL_GIT_BLOB_SHA1: Final = "a2f13cd9871e6da24b2ccf3297c4c96ac324100e"
OPERATION: Final = "TITAN-V4-12019-FINAL-SPATIAL-GUARD-CURRENT-ABI-20260919-01"

OLD: Final = """                if nonterminal:\n                    returned, report = self.overflow_safe_drop.transform(returned, obs, cfg)\n                    self.diagnostics['overflow_safe_drop'] = report\n                    self._checkpoint_finalizer(obs, returned, 'overflow_safe_drop')\n            return returned\n"""

NEW: Final = """                if nonterminal:\n                    returned, report = self.overflow_safe_drop.transform(returned, obs, cfg)\n                    self.diagnostics['overflow_safe_drop'] = report\n                    self._checkpoint_finalizer(obs, returned, 'overflow_safe_drop')\n            # SpatialTempo may have bound an idle-FERT proposal before late\n            # pressure/procurement/overflow market transforms. Re-run its\n            # shared final-action guard only after those transforms so the\n            # proposal slot is rebound to the bytes that can actually leave\n            # this boundary, or the paired DROP is failed closed.\n            spatial = getattr(self, 'spatial', None)\n            if spatial is not None and completed:\n                returned = spatial.guard_returned(obs, returned)\n                self._checkpoint_finalizer(obs, returned, 'spatial_final_guard')\n            return returned\n"""


def git_blob_sha1(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def validate_sources(tree: Path) -> tuple[bytes, bytes]:
    main_source = (tree / TARGET).read_bytes()
    spatial_source = (tree / SPATIAL_TARGET).read_bytes()
    main_sha = git_blob_sha1(main_source)
    spatial_sha = git_blob_sha1(spatial_source)
    if main_sha != EXPECTED_MAIN_GIT_BLOB_SHA1:
        raise ValueError(f"main.py preimage Git blob mismatch: {main_sha}")
    if spatial_sha != EXPECTED_SPATIAL_GIT_BLOB_SHA1:
        raise ValueError(f"spatial_tempo.py guard Git blob mismatch: {spatial_sha}")
    return main_source, spatial_source


def patch_bytes(main_source: bytes) -> bytes:
    if git_blob_sha1(main_source) != EXPECTED_MAIN_GIT_BLOB_SHA1:
        raise ValueError("main.py preimage Git blob mismatch")
    text = main_source.decode("utf-8")
    count = text.count(OLD)
    if count != 1:
        raise ValueError(f"main.py anchor expected once, found {count}")
    candidate = text.replace(OLD, NEW, 1)
    if candidate.count(NEW) != 1 or OLD in candidate:
        raise ValueError("replacement closure failed")
    compile(candidate, str(TARGET), "exec")
    return candidate.encode("utf-8")


def _new_output_path(tree: Path, requested: Path) -> Path:
    # Resolve directory aliases, but never dereference an output leaf: even a
    # dangling symlink must be refused rather than followed into a new file.
    target = requested.absolute()
    target = target.parent.resolve() / target.name
    if target == tree or tree in target.parents:
        raise ValueError("outputs must be outside the canonical source tree")
    try:
        target.lstat()
    except FileNotFoundError:
        pass
    else:
        raise FileExistsError(f"refusing to replace an existing output: {target}")
    return target


def _write_new_bytes(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    # 'x' reserves a fresh inode atomically. A file/link that appears after
    # preflight cannot be truncated, including a hardlink to either input.
    with target.open("xb") as stream:
        stream.write(data)
    if target.read_bytes() != data:
        raise OSError(f"output readback mismatch: {target}")


def materialize(tree: Path, output: Path, *, receipt_path: Path | None = None) -> dict:
    tree = tree.resolve()
    main_source, spatial_source = validate_sources(tree)
    candidate = patch_bytes(main_source)
    target = _new_output_path(tree, output)
    receipt_target = (
        _new_output_path(tree, receipt_path) if receipt_path is not None else None
    )
    if target == receipt_target:
        raise ValueError("candidate and receipt must use distinct new paths")
    receipt = {
        "operation": OPERATION,
        "target": TARGET.as_posix(),
        "guard_source": SPATIAL_TARGET.as_posix(),
        "source_git_blob_sha1": git_blob_sha1(main_source),
        "guard_git_blob_sha1": git_blob_sha1(spatial_source),
        "candidate_git_blob_sha1": git_blob_sha1(candidate),
        "source_bytes": len(main_source),
        "candidate_bytes": len(candidate),
        "changed": main_source != candidate,
        "composition_authority": "none; current-ABI carrier only",
    }
    _write_new_bytes(target, candidate)
    # Re-authenticate both inputs before emitting a success receipt. This is
    # source/nonmutation custody, not authorization to install the candidate.
    validate_sources(tree)
    if receipt_target is not None:
        payload = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
        _write_new_bytes(receipt_target, payload.encode("utf-8"))
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tree", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    receipt = materialize(args.tree, args.output, receipt_path=args.receipt)
    payload = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
