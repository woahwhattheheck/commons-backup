# SPDX-License-Identifier: Apache-2.0
"""Build one immutable production-v3 R04 route-matrix candidate."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil

from build_delivery import archive_bytes, digest, members
from build_production_recovery import (
    CANDIDATE_SHA,
    DELIVERY_SHA,
    V31_SHA,
    compose,
)
from route_matrix import (
    FINAL_PLAN_STEP,
    ROUTE_STEP,
    TERMINAL_PLAN,
    force_plan_at,
)

ROUTER = "r04_full_router.py"
ROUTER_SHA256 = "41ea55c5f20c43cd58c5099fbadb212de62ec95a95dfc2e6e1e19c3d4d55b39a"


def build(v31_archive, delivery_archive, plan_index, selection_step=ROUTE_STEP):
    """Compose exact production-v3, then force one authenticated route choice."""
    v31 = members(v31_archive, V31_SHA)
    delivery = members(delivery_archive, DELIVERY_SHA)
    overlay = Path(__file__).with_name("production_recovery_overlay.txt").read_bytes()
    files = compose(v31, delivery, overlay, "v3")
    if digest(archive_bytes(files)) != CANDIDATE_SHA:
        raise ValueError("production-v3 baseline identity drift")

    before = files[ROUTER]
    if digest(before) != ROUTER_SHA256:
        raise ValueError("production-v3 R04 router identity drift")
    after = force_plan_at(before, plan_index, selection_step)

    exact_terminal_control = (
        selection_step == FINAL_PLAN_STEP and plan_index == TERMINAL_PLAN
    )
    if (after == before) != exact_terminal_control:
        raise ValueError("route forcing identity contract violated")

    files = dict(files)
    files[ROUTER] = after
    return files, before, after


def _resolved(path):
    return Path(path).resolve(strict=False)


def _validate_publication_paths(out, tar_path, receipt_path):
    resolved = [_resolved(path) for path in (out, tar_path, receipt_path)]
    if len(set(resolved)) != len(resolved):
        raise ValueError("output directory, archive, and receipt paths must be distinct")
    out_resolved, tar_resolved, receipt_resolved = resolved
    if out_resolved in tar_resolved.parents or out_resolved in receipt_resolved.parents:
        raise ValueError("archive and receipt must not be inside the output directory")


def _reserve(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o644)
    stat = os.fstat(fd)
    return fd, (stat.st_dev, stat.st_ino)


def _write_reserved(fd, payload):
    view = memoryview(payload)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("short write while publishing route-matrix artifact")
        view = view[written:]
    os.fsync(fd)


def _unlink_if_owned(path, identity):
    path = Path(path)
    try:
        stat = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return
    if (stat.st_dev, stat.st_ino) == identity:
        path.unlink()


def _rmtree_if_owned(path, identity):
    path = Path(path)
    try:
        stat = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return
    if (stat.st_dev, stat.st_ino) == identity and path.is_dir():
        shutil.rmtree(path)


def _publish(
    files,
    before,
    after,
    packed,
    plan_index,
    selection_step,
    out,
    tar_path,
    receipt_path,
):
    """Publish one archive/receipt pair without overwriting foreign outputs."""
    out = Path(out)
    tar_path = Path(tar_path)
    receipt_path = Path(receipt_path)
    _validate_publication_paths(out, tar_path, receipt_path)
    if out.exists():
        raise FileExistsError("output directory already exists")

    tar_fd = None
    receipt_fd = None
    owned_finals = []
    out_identity = None
    try:
        tar_fd, tar_identity = _reserve(tar_path)
        owned_finals.append((tar_path, tar_identity))
        receipt_fd, receipt_identity = _reserve(receipt_path)
        owned_finals.append((receipt_path, receipt_identity))

        out.mkdir(parents=True)
        out_stat = out.stat(follow_symlinks=False)
        out_identity = (out_stat.st_dev, out_stat.st_ino)
        for name, body in files.items():
            path = out / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)

        changed_members = [] if after == before else [ROUTER]
        receipt = {
            "schema": "titan-v5-route-matrix-build/v1",
            "baseline_candidate_archive_sha256": CANDIDATE_SHA,
            "v31_archive_sha256": V31_SHA,
            "delivery_archive_sha256": DELIVERY_SHA,
            "plan_index": plan_index,
            "selection_step": selection_step,
            "selection_kind": (
                "shop_pair" if selection_step == ROUTE_STEP else "terminal"
            ),
            "route_step": ROUTE_STEP,
            "final_plan_step": FINAL_PLAN_STEP,
            "terminal_plan": TERMINAL_PLAN,
            "changed_members": changed_members,
            "router_before_sha256": digest(before),
            "router_after_sha256": digest(after),
            "candidate_archive_sha256": digest(packed),
            "files": {name: digest(body) for name, body in sorted(files.items())},
            "kaggle_submission_hold": True,
        }
        receipt_bytes = (json.dumps(receipt, indent=2) + "\n").encode("utf-8")

        # Both final names already belong to this invocation. Write the archive
        # first, then its receipt; any caught write/fsync failure rolls back
        # only the inodes reserved above.
        _write_reserved(tar_fd, packed)
        _write_reserved(receipt_fd, receipt_bytes)
        os.close(tar_fd)
        tar_fd = None
        os.close(receipt_fd)
        receipt_fd = None
        return receipt
    except BaseException:
        for fd in (tar_fd, receipt_fd):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
        if out_identity is not None:
            _rmtree_if_owned(out, out_identity)
        for path, identity in reversed(owned_finals):
            _unlink_if_owned(path, identity)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v31", type=Path, required=True)
    parser.add_argument("--delivery", type=Path, required=True)
    parser.add_argument("--plan-index", type=int, required=True)
    parser.add_argument(
        "--selection-step",
        type=int,
        choices=(ROUTE_STEP, FINAL_PLAN_STEP),
        default=ROUTE_STEP,
        help="R04 plan-selection boundary to force (default: step 144)",
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--tar", type=Path, required=True)
    args = parser.parse_args()
    receipt_path = args.out.parent / (args.out.name + "-manifest.json")

    files, before, after = build(
        args.v31, args.delivery, args.plan_index, args.selection_step
    )
    packed = archive_bytes(files)
    try:
        _publish(
            files,
            before,
            after,
            packed,
            args.plan_index,
            args.selection_step,
            args.out,
            args.tar,
            receipt_path,
        )
    except (FileExistsError, ValueError) as exc:
        parser.error(str(exc))

    print(json.dumps({
        "plan_index": args.plan_index,
        "selection_step": args.selection_step,
        "candidate_archive_sha256": digest(packed),
        "members": len(files),
    }))


if __name__ == "__main__":
    main()
