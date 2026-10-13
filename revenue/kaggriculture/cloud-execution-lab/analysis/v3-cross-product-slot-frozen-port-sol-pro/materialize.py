#!/usr/bin/env python3
"""Authenticate and materialize #12100 into the selected FrozenSelected consumer."""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import ModuleType
from typing import Any, Iterable

OPERATION = "TITAN-V3-CROSS-PRODUCT-SLOT-EXECUTABLE-FROZEN-PORT-20260910-01"
DONOR_OPERATION = "TITAN-V3-CROSS-PRODUCT-SELL-SLOT-RESERVATION-CLOSURE-20260910-01"
EXPECTED_DONOR_HEAD = "47aa401c647f330cdd7acae31515e1351f557fad"
EXPECTED_DONOR_MATERIALIZER_BLOB = "881c8d27a8fb5b6b1740361b2b94437ba2c9a0a8"
EXPECTED_SCHEDULER_BLOB = "a483b24dd72b580d7d8811636b54d2d44f391575"
EXPECTED_FROZEN_BLOB = "fc7baf5c179818a55037f6a61d92984d81d1a21c"
EXPECTED_RUNTIME_BLOB = "b952c9c228ecbde592bf3d2df01638677abb0d24"
EXPECTED_CONFIG_BLOB = "3a3bef83899d3010fad623b628d9e95d9978111b"

OLD_BLOCK = """                    if len(orders)>=int(config.get('maxMarketOrdersPerTurn',10)):\n                        offered=sum(max(0,int(o[2])) for o in orders if o and o[0]=='SELL' and o[1]==item)\n                        if q>offered:return False"""

NEW_BLOCK = """                    offered=sum(max(0,int(o[2])) for o in orders if o and o[0]=='SELL' and o[1]==item)\n                    reserved=scheduling._planned_slot_reservations(\n                        self.planned,current,item,now,t,orders)\n                    if reserved is None:return False\n                    if q>offered and len(orders)+reserved>=int(config.get('maxMarketOrdersPerTurn',10)):return False"""


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _reject_constant(token: str) -> Any:
    raise ValueError(f"non-finite JSON constant {token!r}")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def load_json_strict(data: bytes) -> Any:
    try:
        return json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except UnicodeDecodeError as exc:
        raise ValueError(f"JSON is not UTF-8: {exc}") from exc


def _read_bound(path: Path, expected_blob: str, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular non-symlink file")
    data = path.read_bytes()
    actual = git_blob_sha(data)
    if actual != expected_blob:
        raise ValueError(f"{label} Git blob mismatch: {actual} != {expected_blob}")
    return data


def load_donor(path: Path) -> tuple[ModuleType, bytes]:
    data = _read_bound(path, EXPECTED_DONOR_MATERIALIZER_BLOB, "donor materializer")
    spec = importlib.util.spec_from_file_location("_titan_slot_reservation_donor", path)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load donor materializer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    expected = {
        "EXPECTED_SOURCE_BLOB": EXPECTED_SCHEDULER_BLOB,
        "OPERATION": DONOR_OPERATION,
        "OLD_BLOCK": OLD_BLOCK,
    }
    for name, value in expected.items():
        if getattr(module, name, None) != value:
            raise ValueError(f"donor {name} drifted")
    if "_planned_slot_reservations" not in getattr(module, "NEW_BLOCK", ""):
        raise ValueError("donor no longer wires the reservation helper")
    return module, data


def patch_frozen(source: str, *, expected_blob: str | None = EXPECTED_FROZEN_BLOB) -> str:
    raw = source.encode("utf-8")
    if expected_blob is not None and git_blob_sha(raw) != expected_blob:
        raise ValueError("frozen source Git blob does not match the selected consumer")
    if source.count("import scheduler as scheduling") != 1:
        raise ValueError("scheduler module import is missing or ambiguous")
    if "scheduling._planned_slot_reservations(" in source:
        raise ValueError("active reservation port is already present")
    if source.count(OLD_BLOCK) != 1:
        raise ValueError("copied FrozenSelected feasibility preimage is missing or ambiguous")
    patched = source.replace(OLD_BLOCK, NEW_BLOCK, 1)
    if patched == source:
        raise ValueError("empty frozen patch")
    ast.parse(patched)
    if OLD_BLOCK in patched or patched.count(NEW_BLOCK) != 1:
        raise ValueError("active frozen replacement cardinality is invalid")
    if patched.count("scheduling._planned_slot_reservations(") != 1:
        raise ValueError("active helper call cardinality is invalid")
    return patched


def materialize_pair(
    scheduler_source: str,
    frozen_source: str,
    donor: ModuleType,
    *,
    expected_scheduler_blob: str | None = EXPECTED_SCHEDULER_BLOB,
    expected_frozen_blob: str | None = EXPECTED_FROZEN_BLOB,
) -> tuple[str, str]:
    scheduler_post = donor.patch_source(
        scheduler_source,
        expected_blob=expected_scheduler_blob,
    )
    frozen_post = patch_frozen(frozen_source, expected_blob=expected_frozen_blob)
    ast.parse(scheduler_post)
    ast.parse(frozen_post)
    if scheduler_post.count("def _planned_slot_reservations(") != 1:
        raise ValueError("donor scheduler postimage lacks one helper")
    if "scheduling._planned_slot_reservations(" not in frozen_post:
        raise ValueError("frozen postimage is not connected to donor scheduler postimage")
    return scheduler_post, frozen_post


def _canonical_existing(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular non-symlink file")
    return path.resolve(strict=True)


def _canonical_new(path: Path, label: str) -> Path:
    if path.exists() or path.is_symlink():
        raise ValueError(f"{label} already exists")
    parent = path.parent.resolve(strict=True)
    if not parent.is_dir():
        raise ValueError(f"{label} parent is not a directory")
    return parent / path.name


def validate_paths(inputs: Iterable[tuple[str, Path]], outputs: Iterable[tuple[str, Path]]) -> tuple[dict[str, Path], dict[str, Path]]:
    resolved_inputs = {label: _canonical_existing(path, label) for label, path in inputs}
    resolved_outputs = {label: _canonical_new(path, label) for label, path in outputs}
    all_paths = [*resolved_inputs.values(), *resolved_outputs.values()]
    if len(set(all_paths)) != len(all_paths):
        raise ValueError("all source, output, and receipt paths must be pairwise distinct")
    return resolved_inputs, resolved_outputs


def _stage(path: Path, data: bytes) -> Path:
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    staged = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        return staged
    except BaseException:
        try:
            staged.unlink()
        except FileNotFoundError:
            pass
        raise


def publish_exclusive(payloads: list[tuple[Path, bytes]]) -> None:
    staged: list[tuple[Path, Path]] = []
    published: list[Path] = []
    try:
        for destination, data in payloads:
            staged.append((destination, _stage(destination, data)))
        for destination, temporary in staged:
            os.link(temporary, destination)
            published.append(destination)
        for directory in {path.parent for path, _ in payloads}:
            fd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    except BaseException:
        for destination in reversed(published):
            try:
                destination.unlink()
            except FileNotFoundError:
                pass
        raise
    finally:
        for _destination, temporary in staged:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def build_receipt(
    *,
    scheduler_source: bytes,
    frozen_source: bytes,
    runtime_source: bytes,
    config_source: bytes,
    donor_source: bytes,
    scheduler_post: bytes,
    frozen_post: bytes,
) -> dict[str, Any]:
    return {
        "schema": "titan-v3-cross-product-slot-executable-frozen-port-v1",
        "operation": OPERATION,
        "donor": {
            "head": EXPECTED_DONOR_HEAD,
            "operation": DONOR_OPERATION,
            "materializer_git_blob": git_blob_sha(donor_source),
            "materializer_sha256": sha256(donor_source),
        },
        "inputs": {
            "scheduler": {"git_blob": git_blob_sha(scheduler_source), "sha256": sha256(scheduler_source), "bytes": len(scheduler_source)},
            "frozen_selected": {"git_blob": git_blob_sha(frozen_source), "sha256": sha256(frozen_source), "bytes": len(frozen_source)},
            "titan_runtime": {"git_blob": git_blob_sha(runtime_source), "sha256": sha256(runtime_source), "bytes": len(runtime_source)},
            "config": {"git_blob": git_blob_sha(config_source), "sha256": sha256(config_source), "bytes": len(config_source)},
        },
        "outputs": {
            "scheduler": {"git_blob": git_blob_sha(scheduler_post), "sha256": sha256(scheduler_post), "bytes": len(scheduler_post)},
            "frozen_selected": {"git_blob": git_blob_sha(frozen_post), "sha256": sha256(frozen_post), "bytes": len(frozen_post)},
        },
        "activation": {
            "consumer": "frozen",
            "runtime_class": "titan_runtime.TitanAgent",
            "selected_class": "frozen_selected.FrozenSelected",
            "helper_owner": "scheduler._planned_slot_reservations",
            "active_call": "scheduling._planned_slot_reservations",
        },
        "changes": [
            "materialize the exact reviewed #12100 scheduler helper",
            "replace the one copied FrozenSelected product-local slot predicate",
            "connect the selected consumer to the donor helper through the scheduler module",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scheduler-source", type=Path, required=True)
    parser.add_argument("--frozen-source", type=Path, required=True)
    parser.add_argument("--donor-materializer", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--scheduler-output", type=Path, required=True)
    parser.add_argument("--frozen-output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    try:
        sources, outputs = validate_paths(
            [
                ("scheduler source", args.scheduler_source),
                ("frozen source", args.frozen_source),
                ("donor materializer", args.donor_materializer),
                ("runtime", args.runtime),
                ("config", args.config),
            ],
            [
                ("scheduler output", args.scheduler_output),
                ("frozen output", args.frozen_output),
                ("receipt", args.receipt),
            ],
        )
        scheduler_bytes = _read_bound(sources["scheduler source"], EXPECTED_SCHEDULER_BLOB, "scheduler source")
        frozen_bytes = _read_bound(sources["frozen source"], EXPECTED_FROZEN_BLOB, "frozen source")
        runtime_bytes = _read_bound(sources["runtime"], EXPECTED_RUNTIME_BLOB, "runtime")
        config_bytes = _read_bound(sources["config"], EXPECTED_CONFIG_BLOB, "config")
        config = load_json_strict(config_bytes)
        if not isinstance(config, dict) or config.get("consumer") != "frozen":
            raise ValueError("bound package config does not select consumer=frozen")
        donor, donor_bytes = load_donor(sources["donor materializer"])
        scheduler_post_text, frozen_post_text = materialize_pair(
            scheduler_bytes.decode("utf-8"),
            frozen_bytes.decode("utf-8"),
            donor,
        )
        scheduler_post = scheduler_post_text.encode("utf-8")
        frozen_post = frozen_post_text.encode("utf-8")
        receipt = build_receipt(
            scheduler_source=scheduler_bytes,
            frozen_source=frozen_bytes,
            runtime_source=runtime_bytes,
            config_source=config_bytes,
            donor_source=donor_bytes,
            scheduler_post=scheduler_post,
            frozen_post=frozen_post,
        )
        receipt_bytes = (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode("utf-8")
        publish_exclusive(
            [
                (outputs["scheduler output"], scheduler_post),
                (outputs["frozen output"], frozen_post),
                (outputs["receipt"], receipt_bytes),
            ]
        )
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
