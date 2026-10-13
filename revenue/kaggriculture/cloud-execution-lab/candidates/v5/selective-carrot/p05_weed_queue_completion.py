# SPDX-License-Identifier: Apache-2.0
"""Materialize the TITAN V5 P05 weed-queue PASS catch-up component.

This module does not activate gameplay.  It authenticates the exact production-v3
archive and exact baseline R04 router, applies one source-local transformation,
and publishes a staging-composer component plus manifest with submission hold.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile

from publication_custody import publish_exclusive

BASELINE_ARCHIVE_SHA256 = "20f201161b14af7755146b08207593f9fa5df641d2f31e680792ea62c0e24239"
ROUTER_MEMBER = "r04_full_router.py"
ROUTER_PREIMAGE_SHA256 = "41ea55c5f20c43cd58c5099fbadb212de62ec95a95dfc2e6e1e19c3d4d55b39a"
COMPONENT_ID = "p05-weed-queue-pass-catchup"
COMPONENT_SCHEMA = "titan-v5-staging-component/v1"

_ANCHOR = (
    b'        queue = state.queues.setdefault(worker, deque())\n'
    b'        queue.append(list(workers[worker]))\n'
    b'        x, y = view.positions[worker]\n'
)
_REPLACEMENT = (
    b'        queue = state.queues.setdefault(worker, deque())\n'
    b'        authored = list(workers[worker])\n'
    b'        if not (queue and authored == ["PASS"]):\n'
    b'            queue.append(authored)\n'
    b'        x, y = view.positions[worker]\n'
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def transform_router(source: bytes) -> bytes:
    """Apply the P05 source transform exactly once, rejecting drift."""
    if source.count(_ANCHOR) != 1:
        raise ValueError("P05 router anchor must occur exactly once")
    return source.replace(_ANCHOR, _REPLACEMENT, 1)


def _read_router(archive_bytes: bytes) -> bytes:
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:*") as bundle:
        members = [member for member in bundle.getmembers() if member.name == ROUTER_MEMBER]
        if len(members) != 1:
            raise ValueError(f"expected exactly one {ROUTER_MEMBER} member")
        member = members[0]
        if not member.isfile():
            raise ValueError(f"{ROUTER_MEMBER} is not a regular file")
        stream = bundle.extractfile(member)
        if stream is None:
            raise ValueError(f"could not read {ROUTER_MEMBER}")
        return stream.read()


def build_component(
    archive_bytes: bytes,
    *,
    expected_archive_sha256: str = BASELINE_ARCHIVE_SHA256,
    expected_router_sha256: str = ROUTER_PREIMAGE_SHA256,
) -> tuple[bytes, bytes]:
    """Return exact patched-router bytes and canonical COMPONENT.json bytes.

    The overridable hashes exist only to make the pure builder testable with a
    synthetic archive.  The CLI intentionally exposes no hash overrides.
    """
    archive_sha = _sha256(archive_bytes)
    if archive_sha != expected_archive_sha256:
        raise ValueError(
            f"production-v3 archive SHA256 mismatch: {archive_sha} != {expected_archive_sha256}"
        )

    router = _read_router(archive_bytes)
    router_sha = _sha256(router)
    if router_sha != expected_router_sha256:
        raise ValueError(
            f"r04_full_router.py SHA256 mismatch: {router_sha} != {expected_router_sha256}"
        )

    patched = transform_router(router)
    manifest = {
        "schema": COMPONENT_SCHEMA,
        "component_id": COMPONENT_ID,
        "baseline_archive_sha256": expected_archive_sha256,
        "depends_on": [],
        "conflicts_with": [],
        "overlap_after": {},
        "replacements": {
            ROUTER_MEMBER: {
                "source": ROUTER_MEMBER,
                "preimage_sha256": expected_router_sha256,
                "postimage_sha256": _sha256(patched),
            }
        },
        "kaggle_submission_hold": True,
    }
    manifest_bytes = (
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    return patched, manifest_bytes


def materialize(archive_path: Path, output_dir: Path) -> None:
    """Publish one composer-ready component without touching a policy/default."""
    archive_bytes = archive_path.read_bytes()
    patched, manifest = build_component(archive_bytes)
    publish_exclusive(
        [
            (output_dir / ROUTER_MEMBER, patched),
            (output_dir / "COMPONENT.json", manifest),
        ]
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    materialize(args.baseline, args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
