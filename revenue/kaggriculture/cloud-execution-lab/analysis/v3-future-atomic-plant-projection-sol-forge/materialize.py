#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Materialize TITAN's scheduler with official future PLANT packet semantics.

The canonical inputs are immutable.  Candidate and receipt publication is
create-only and transactional: every byte is validated and staged first; targets
must not exist or alias an input; completed staging files are atomically linked
into place; exact readback is required; and any BaseException rolls back every
published target before the error escapes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Any

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
DEFAULT_SOURCE = LAB / "scheduler.py"
DEFAULT_ENGINE = LAB / "reference" / "engine" / "kaggriculture.py"

SOURCE_BASE_MAIN = "3854f1cc46340f5099ade910e2cfc7b36606425e"
VERIFIED_MAIN = "2e2e7e52fd2d5c62117ac49c7f1eabb505078ffb"
BASE_MAIN = SOURCE_BASE_MAIN  # Compatibility for the first handoff/tests.
BASE_SCHEDULER_GIT_BLOB = "a483b24dd72b580d7d8811636b54d2d44f391575"
OFFICIAL_ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
SCHEMA = "titan-v3-future-atomic-plant-projection-materializer-v3"

OLD_POST_UNITS = '''def post_units(obs, action, config, *, shed_capacity=None):
    """Exact deterministic engine unit stage on the player's observed farm."""
    farm = detached_json_value(obs['farms'][obs['player']])
    private = detached_json_value(obs['private'])
    acts = [action.get('farmer',['PASS']), *action.get('hands',[])]
    demand = {}
    for a in acts:
        if a and a[0]=='PLANT' and len(a)>1:
            demand[a[1]]=demand.get(a[1],0)+1
    blocked={p for p,n in demand.items() if n>private['seeds'].get(p,0)}
    capacity=int(config.get('shedCapacity',100)) if shed_capacity is None else int(shed_capacity)
    for i,a in enumerate(acts):
        if a and a[0]=='PLANT' and a[1] in blocked:a=['PASS']
        m._apply_unit_action(farm,private,i,a,len(farm['tiles']),int(obs['step'])//int(config.get('turnsPerDay',24)),int(config.get('turnsPerDay',24)),capacity)
    return farm, private
'''

NEW_POST_UNITS = '''def _apply_unit_packet(farm, private, action, *, board_size, day,
                       turns_per_day, shed_capacity, untrusted_seed_crops=()):
    """Apply one farmer+hands packet with crop-local trust boundaries.

    Trusted crops use the official same-row atomic PLANT admission.  A crop with
    an earlier unmodeled future BUY_SEED is explicitly untrusted: its requests
    retain predecessor sequential behavior rather than making an atomic decision
    against a stale seed ledger.  Other actions keep their original actor order.
    """
    packet=action if isinstance(action,dict) else {}
    farmer_action=packet.get('farmer',['PASS'])
    hands_actions=packet.get('hands',[])
    if not isinstance(hands_actions,list):hands_actions=[]
    acts=[farmer_action,*hands_actions]
    demand={}
    for a in acts:
        if isinstance(a,list) and len(a)>=2 and a[0]=='PLANT':
            demand[a[1]]=demand.get(a[1],0)+1
    seeds=private.get('seeds',{}) if hasattr(private,'get') else {}
    untrusted=set(untrusted_seed_crops)
    blocked={crop for crop,n in demand.items()
             if crop not in untrusted and n>seeds.get(crop,0)}
    for i,a in enumerate(acts):
        if isinstance(a,list) and len(a)>=2 and a[0]=='PLANT' and a[1] in blocked:
            a=['PASS']
        m._apply_unit_action(farm,private,i,a,board_size,day,turns_per_day,shed_capacity)
    return blocked


def post_units(obs, action, config, *, shed_capacity=None):
    """Exact deterministic engine unit stage on the player's observed farm."""
    farm = detached_json_value(obs['farms'][obs['player']])
    private = detached_json_value(obs['private'])
    turns_per_day=max(1,int(config.get('turnsPerDay',24)))
    capacity=int(config.get('shedCapacity',100)) if shed_capacity is None else int(shed_capacity)
    _apply_unit_packet(farm,private,action,
        board_size=len(farm['tiles']),day=int(obs['step'])//turns_per_day,
        turns_per_day=turns_per_day,shed_capacity=capacity)
    return farm, private
'''

OLD_PROFILE_SETUP = '''        profile=[]
        route=self.controller.R[self.controller.cur]
'''

NEW_PROFILE_SETUP = '''        profile=[]
        route=self.controller.R[self.controller.cur]
        # receipt_profile does not replay market funding/cash, so a prior future
        # BUY_SEED makes that crop's projected seed ledger unknown.  Preserve the
        # predecessor's sequential behavior for only those crops rather than
        # applying an atomic decision to stale seed stock.
        untrusted_seed_crops=set()
'''

OLD_FUTURE_PACKET = '''            if t>now:
                act=route[t] if t<len(route) else parent.PASS
                acts=[act.get('farmer',['PASS']),*act.get('hands',[])]
                for i,a in enumerate(acts):
                    m._apply_unit_action(f,p,i,a,len(f['tiles']),t//24,24,10**6)
'''

NEW_FUTURE_PACKET = '''            if t>now:
                act=route[t] if t<len(route) else parent.PASS
                _apply_unit_packet(f,p,act,
                    board_size=len(f['tiles']),day=t//24,turns_per_day=24,
                    shed_capacity=10**6,
                    untrusted_seed_crops=untrusted_seed_crops)
'''

OLD_MARKET_SEED_GUARD = '''            for o in orders:
                if not o:continue
                if o[0]=='SELL' and o[1]!=item:
'''

NEW_MARKET_SEED_GUARD = '''            for o in orders:
                if not o:continue
                if (isinstance(o,list) and len(o)>=2 and
                        o[0]=='BUY_SEED' and isinstance(o[1],str)):
                    untrusted_seed_crops.add(o[1])
                if o[0]=='SELL' and o[1]!=item:
'''


class MaterializationError(RuntimeError):
    """A source, target, publication, or readback invariant failed."""


def git_blob(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise MaterializationError(
            f"{label} preimage count is {count}, expected exactly 1"
        )
    return text.replace(old, new, 1)


def _regular_input(path: Path, *, label: str) -> tuple[Path, bytes]:
    """Resolve one immutable regular-file input without accepting symlink leaves."""
    requested = Path(path)
    try:
        metadata = requested.lstat()
    except OSError as exc:
        raise MaterializationError(f"{label} cannot be inspected: {requested}: {exc}") from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise MaterializationError(f"{label} must not be a symlink: {requested}")
    if not stat.S_ISREG(metadata.st_mode):
        raise MaterializationError(f"{label} is not a regular file: {requested}")
    try:
        resolved = requested.resolve(strict=True)
        data = resolved.read_bytes()
    except OSError as exc:
        raise MaterializationError(f"{label} cannot be read: {requested}: {exc}") from exc
    return resolved, data


def _same_existing_file(left: Path, right: Path) -> bool:
    try:
        return os.path.samefile(left, right)
    except (FileNotFoundError, OSError):
        return False


def _target_path(
    path: Path,
    *,
    label: str,
    immutable_inputs: tuple[Path, ...],
) -> Path:
    """Return a canonical create-only target and reject every known alias form."""
    requested = Path(path)
    if not requested.name or requested.name in (".", ".."):
        raise MaterializationError(f"{label} has no file name: {requested}")
    try:
        parent = requested.parent.resolve(strict=True)
    except OSError as exc:
        raise MaterializationError(
            f"{label} parent must already exist: {requested.parent}: {exc}"
        ) from exc
    if not parent.is_dir():
        raise MaterializationError(f"{label} parent is not a directory: {parent}")
    target = parent / requested.name

    try:
        metadata = target.lstat()
    except FileNotFoundError:
        metadata = None
    except OSError as exc:
        raise MaterializationError(f"{label} cannot be inspected: {target}: {exc}") from exc

    if metadata is not None:
        for source in immutable_inputs:
            if _same_existing_file(target, source):
                raise MaterializationError(
                    f"{label} aliases immutable input {source}: {target}"
                )
        if stat.S_ISLNK(metadata.st_mode):
            raise MaterializationError(f"{label} must not be a symlink: {target}")
        raise MaterializationError(f"{label} already exists (create-only): {target}")

    for source in immutable_inputs:
        if target == source:
            raise MaterializationError(
                f"{label} aliases immutable input {source}: {target}"
            )
    return target


def _assert_inputs_unchanged(
    source: Path,
    source_bytes: bytes,
    engine: Path,
    engine_bytes: bytes,
) -> None:
    try:
        actual_source = source.read_bytes()
        actual_engine = engine.read_bytes()
    except OSError as exc:
        raise MaterializationError(f"immutable input became unreadable: {exc}") from exc
    if actual_source != source_bytes:
        raise MaterializationError("canonical scheduler changed during materialization")
    if actual_engine != engine_bytes:
        raise MaterializationError("official engine changed during materialization")


def _stage_bytes(target: Path, data: bytes) -> Path:
    """Flush one complete same-directory staging inode; publish nothing."""
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            remaining = memoryview(data)
            while remaining:
                written = stream.write(remaining)
                if written is None or written <= 0:
                    raise OSError("staging write made no progress")
                remaining = remaining[written:]
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        if temporary.read_bytes() != data:
            raise MaterializationError(f"staging readback mismatch: {temporary}")
        return temporary
    except BaseException:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def _fsync_directory(directory: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(directory, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _publish_create_only(staged: Path, target: Path) -> None:
    """Atomically expose a completed staging inode without replacing anything."""
    try:
        os.link(staged, target, follow_symlinks=False)
        _fsync_directory(target.parent)
    except FileExistsError as exc:
        raise MaterializationError(
            f"target appeared during create-only publication: {target}"
        ) from exc
    except OSError as exc:
        raise MaterializationError(f"cannot publish {target}: {exc}") from exc


def _unlink_our_publication(staged: Path, target: Path) -> None:
    """Remove only a target that still aliases this invocation's staging inode."""
    try:
        if target.is_symlink() or not target.exists():
            return
        if os.path.samefile(staged, target):
            target.unlink()
            _fsync_directory(target.parent)
    except (FileNotFoundError, OSError):
        # The caller reports rollback failure separately by checking target state.
        return


def _cleanup_staged(paths: list[Path]) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def materialize(
    source: Path,
    engine: Path,
    output: Path,
    receipt_path: Path,
) -> dict[str, Any]:
    source, source_bytes = _regular_input(source, label="scheduler source")
    engine, engine_bytes = _regular_input(engine, label="official engine")
    if _same_existing_file(source, engine):
        raise MaterializationError("scheduler source and official engine alias")

    output = _target_path(
        output,
        label="candidate output",
        immutable_inputs=(source, engine),
    )
    receipt_path = _target_path(
        receipt_path,
        label="receipt output",
        immutable_inputs=(source, engine),
    )
    if output == receipt_path:
        raise MaterializationError(
            f"candidate output and receipt output alias: {output}"
        )

    source_blob = git_blob(source_bytes)
    engine_blob = git_blob(engine_bytes)
    if source_blob != BASE_SCHEDULER_GIT_BLOB:
        raise MaterializationError(
            "scheduler source drift: "
            f"expected {BASE_SCHEDULER_GIT_BLOB}, got {source_blob}"
        )
    if engine_blob != OFFICIAL_ENGINE_GIT_BLOB:
        raise MaterializationError(
            "official engine drift: "
            f"expected {OFFICIAL_ENGINE_GIT_BLOB}, got {engine_blob}"
        )

    try:
        source_text = source_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MaterializationError("scheduler is not UTF-8") from exc

    candidate = replace_once(
        source_text,
        OLD_POST_UNITS,
        NEW_POST_UNITS,
        label="current-unit atomic primitive",
    )
    candidate = replace_once(
        candidate,
        OLD_PROFILE_SETUP,
        NEW_PROFILE_SETUP,
        label="future seed-trust state",
    )
    candidate = replace_once(
        candidate,
        OLD_FUTURE_PACKET,
        NEW_FUTURE_PACKET,
        label="future route packet",
    )
    candidate = replace_once(
        candidate,
        OLD_MARKET_SEED_GUARD,
        NEW_MARKET_SEED_GUARD,
        label="future BUY_SEED uncertainty guard",
    )
    if candidate == source_text:
        raise MaterializationError("candidate unexpectedly equals source")
    compile(candidate, str(output), "exec")
    candidate_bytes = candidate.encode("utf-8")

    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "base_main": SOURCE_BASE_MAIN,
        "source_base_main": SOURCE_BASE_MAIN,
        "verified_main": VERIFIED_MAIN,
        "source": {
            "path": "scheduler.py",
            "bytes": len(source_bytes),
            "git_blob": source_blob,
            "sha256": sha256(source_bytes),
        },
        "official_engine": {
            "path": "reference/engine/kaggriculture.py",
            "bytes": len(engine_bytes),
            "git_blob": engine_blob,
            "sha256": sha256(engine_bytes),
        },
        "candidate": {
            "path": "generated/scheduler.py",
            "bytes": len(candidate_bytes),
            "git_blob": git_blob(candidate_bytes),
            "sha256": sha256(candidate_bytes),
        },
        "receipt": {"path": "generated/RECEIPT.json"},
        "publication": {
            "mode": "atomic_create_only_hardlink",
            "targets_preexisting": False,
            "exact_readback_required": True,
            "rollback_on_base_exception": True,
        },
        "replacements": {
            "shared_atomic_unit_packet": 1,
            "future_receipt_profile_callsite": 1,
        },
        "guards": {
            "future_seed_trust_state": 1,
            "future_buy_seed_uncertainty_fallback": 1,
        },
        "scope": {
            "trusted_future_crop": "official atomic admission",
            "crop_after_future_buy_seed": "preserve predecessor sequential behavior",
        },
        "canonical_source_mutated": False,
        "official_engine_mutated": False,
        "score_claim": False,
        "disposition": "SOURCE_REAL_ACTION_UNMEASURED",
    }
    receipt_bytes = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )

    _assert_inputs_unchanged(source, source_bytes, engine, engine_bytes)
    staged_pairs: list[tuple[Path, Path, bytes]] = []
    try:
        staged_pairs.append(
            (_stage_bytes(output, candidate_bytes), output, candidate_bytes)
        )
        staged_pairs.append(
            (_stage_bytes(receipt_path, receipt_bytes), receipt_path, receipt_bytes)
        )
        _assert_inputs_unchanged(source, source_bytes, engine, engine_bytes)
        for staged, target, _ in staged_pairs:
            _publish_create_only(staged, target)
        for _, target, expected in staged_pairs:
            if target.is_symlink() or not target.is_file():
                raise MaterializationError(f"published target is not regular: {target}")
            if target.read_bytes() != expected:
                raise MaterializationError(f"published readback mismatch: {target}")
        _assert_inputs_unchanged(source, source_bytes, engine, engine_bytes)
    except BaseException as exc:
        for staged, target, _ in reversed(staged_pairs):
            _unlink_our_publication(staged, target)
        rollback_residue = [
            str(target)
            for staged, target, _ in staged_pairs
            if target.exists() and _same_existing_file(staged, target)
        ]
        _cleanup_staged([staged for staged, _, _ in staged_pairs])
        try:
            _assert_inputs_unchanged(source, source_bytes, engine, engine_bytes)
        except BaseException as integrity_exc:
            raise MaterializationError(
                f"publication failed and immutable input integrity was lost: {integrity_exc}"
            ) from exc
        if rollback_residue:
            raise MaterializationError(
                "publication failed and rollback left invocation-owned targets: "
                + ", ".join(rollback_residue)
            ) from exc
        raise
    finally:
        _cleanup_staged([staged for staged, _, _ in staged_pairs])

    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--engine", type=Path, default=DEFAULT_ENGINE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    receipt = materialize(args.source, args.engine, args.output, args.receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
