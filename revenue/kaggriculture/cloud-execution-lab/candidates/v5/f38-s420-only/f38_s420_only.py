#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Materialize the TITAN V5 F38 S420-only source arm from exact production20f.

F38 is deliberately source-only while the V5 runtime gate is closed. It reads
an authenticated production20f archive and publishes only a transformed
``frozen_selected.py`` plus a provenance receipt. It never emits a candidate
archive, component, CURRENT/default pointer, release, or submission artifact.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Callable

BASELINE_ARCHIVE_SHA256 = "20f201161b14af7755146b08207593f9fa5df641d2f31e680792ea62c0e24239"
BASELINE_MEMBER_COUNT = 92
FROZEN_PATH = "frozen_selected.py"
SCHEDULER_PATH = "scheduler.py"
MAIN_PATH = "main.py"
CONFIG_PATH = "TITAN-CONFIG.json"
FROZEN_SHA256 = "5ca1bc39efed756de71207f46926744ea69f9d2f300dd7b9c1a8cc4dbefeb9ef"
SCHEDULER_SHA256 = "00d72a5c6b511e73ed1923ea402c4a36e0f9490f3b4c177490ddc72440f4a64a"
MAIN_SHA256 = "b98aec64f83ea9a216def7ab1fef320a6498ae37816f506af1f891c934027035"
CONFIG_SHA256 = "ba18563683125fd89d5473ddb8a5c3e9431db1787a3046f618a9e03af2cb44af"
SUPPRESS_NEW_PLANS_AFTER = 420
SELLER_HORIZON = 8
RECEIPT_SCHEMA = "titan.v5.f38-s420-only-source/v1"
MARKER = "# TITAN-F38-S420-ONLY: suppress new plan selection at/after step 420.\n"

_BLOCK_START = "        budget=self.cash_reserve(obs,config,base,end)\n"
_BLOCK_END = "        out=copy.deepcopy(base)\n"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


def _method_span(source: str, class_name: str, method_name: str) -> tuple[int, int]:
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    classes = [
        node for node in ast.parse(source).body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    ]
    if len(classes) != 1:
        raise ValueError(f"{class_name}: missing or ambiguous source boundary")
    methods = [
        node for node in classes[0].body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == method_name
    ]
    if len(methods) != 1 or methods[0].decorator_list:
        raise ValueError(f"{class_name}.{method_name}: missing, ambiguous or decorated")
    node = methods[0]
    return offsets[node.lineno - 1], offsets[node.end_lineno]


def _rewrite_source_text(source: str) -> str:
    """Apply only the canonical S420 new-plan suppression to FrozenSelected."""
    if MARKER.strip() in source:
        raise ValueError("F38 S420 marker already present")
    if "H3S420_BASELINE_HORIZON" in source or "HORIZON = H3S420_BASELINE_HORIZON" in source:
        raise ValueError("H3 horizon override present; F38 requires production horizon 8")

    method_start, method_end = _method_span(source, "FrozenSelected", "transform")
    method = source[method_start:method_end]
    if method.count(_BLOCK_START) != 1:
        raise ValueError("FrozenSelected transform start marker drift")
    relative_start = method.index(_BLOCK_START)
    post_start = method[relative_start:]
    if post_start.count(_BLOCK_END) != 1:
        raise ValueError("FrozenSelected transform end marker drift")
    relative_end = method.index(_BLOCK_END, relative_start)

    block = method[relative_start:relative_end]
    if f"if now < {SUPPRESS_NEW_PLANS_AFTER}:" in block:
        raise ValueError("S420 guard already present in new-plan block")
    indented = "".join(
        ("    " + line) if line.strip() else line
        for line in block.splitlines(keepends=True)
    )
    guard = (
        "        " + MARKER
        + f"        if now < {SUPPRESS_NEW_PLANS_AFTER}:\n"
        + indented
    )
    rewritten_method = method[:relative_start] + guard + method[relative_end:]
    out = source[:method_start] + rewritten_method + source[method_end:]
    compile(out, "<f38-s420-only-frozen-selected>", "exec")

    # Text outside the selected new-plan block must be byte-for-byte identical.
    if not out.startswith(source[:method_start + relative_start]):
        raise AssertionError("F38 changed source before the target block")
    original_suffix = source[method_start + relative_end:]
    if not out.endswith(original_suffix):
        raise AssertionError("F38 changed source after the target block")
    if "H3S420_BASELINE_HORIZON" in out or "HORIZON = H3S420_BASELINE_HORIZON" in out:
        raise AssertionError("F38 introduced an H3 horizon override")
    return out


def rewrite_frozen_selected(
    source: bytes,
    *,
    expected_sha256: str = FROZEN_SHA256,
) -> bytes:
    if digest(source) != expected_sha256:
        raise ValueError("frozen_selected.py identity mismatch")
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("frozen_selected.py is not UTF-8") from exc
    return _rewrite_source_text(text).encode("utf-8")


def build_from_members(
    baseline: dict[str, bytes],
    *,
    expected_frozen_sha256: str = FROZEN_SHA256,
    expected_scheduler_sha256: str = SCHEDULER_SHA256,
    expected_main_sha256: str = MAIN_SHA256,
    expected_config_sha256: str = CONFIG_SHA256,
    expected_member_count: int = BASELINE_MEMBER_COUNT,
) -> tuple[dict[str, bytes], dict]:
    """Build source-only F38 outputs from authenticated production members.

    The expected-* overrides exist solely to test the pure builder with small
    synthetic member maps. The CLI exposes no overrides.
    """
    if len(baseline) != expected_member_count:
        raise ValueError(
            f"baseline member count mismatch: {len(baseline)} != {expected_member_count}"
        )
    expected = {
        FROZEN_PATH: expected_frozen_sha256,
        SCHEDULER_PATH: expected_scheduler_sha256,
        MAIN_PATH: expected_main_sha256,
        CONFIG_PATH: expected_config_sha256,
    }
    for name, sha256 in expected.items():
        body = baseline.get(name)
        if body is None:
            raise ValueError(f"baseline is missing authenticated member: {name}")
        if digest(body) != sha256:
            raise ValueError(f"authenticated member identity mismatch: {name}")

    source = baseline[FROZEN_PATH]
    transformed = rewrite_frozen_selected(source, expected_sha256=expected_frozen_sha256)
    if transformed == source:
        raise AssertionError("F38 transform produced no source delta")

    treatment = dict(baseline)
    treatment[FROZEN_PATH] = transformed
    if set(treatment) != set(baseline):
        raise AssertionError("F38 changed archive membership")
    changed = sorted(name for name in baseline if baseline[name] != treatment[name])
    if changed != [FROZEN_PATH]:
        raise AssertionError(f"F38 changed unexpected members: {changed}")
    for name, body in baseline.items():
        if name != FROZEN_PATH and treatment[name] != body:
            raise AssertionError(f"F38 changed retained member: {name}")

    receipt = {
        "schema": RECEIPT_SCHEMA,
        "arm": "F38-S420-only",
        "baseline_archive_sha256": BASELINE_ARCHIVE_SHA256,
        "baseline_member_count": expected_member_count,
        "source_preimage_sha256": expected_frozen_sha256,
        "source_postimage_sha256": digest(transformed),
        "authenticated_retained_members": {
            SCHEDULER_PATH: expected_scheduler_sha256,
            MAIN_PATH: expected_main_sha256,
            CONFIG_PATH: expected_config_sha256,
        },
        "changed_members": [FROZEN_PATH],
        "seller_horizon": SELLER_HORIZON,
        "new_plan_suppression": {
            "step_gte": SUPPRESS_NEW_PLANS_AFTER,
            "scope": "FrozenSelected.transform new-plan selection block only",
        },
        "preserved_semantics": [
            "production scheduler and horizon remain unchanged",
            "new plan selection remains enabled before step 420",
            "post-selection tail remains byte-identical after the guarded block",
            "inherited/base SELL rows and already-planned due commitments remain materialized by the untouched tail",
        ],
        "candidate_archive_materialized": False,
        "component_materialized": False,
        "native_economics_status": "BLOCKED_BY_RUNTIME_GATE",
        "kaggle_submission_hold": True,
    }
    receipt_raw = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")
    outputs = {FROZEN_PATH: transformed, "RECEIPT.json": receipt_raw}
    return outputs, receipt


def _load_production_support(here: Path):
    stage_path = (
        here.parent
        / "production-v3-postprocessor-attribution"
        / "materialize_stage_knockouts.py"
    )
    stage = _load_module("_titan_v5_f38_stage_support", stage_path)
    if stage.BASELINE_ARCHIVE_SHA256 != BASELINE_ARCHIVE_SHA256:
        raise RuntimeError("production-v3 support archive pin drift")
    return stage


def materialize(
    baseline_path: Path,
    source_out: Path,
    receipt_out: Path,
    *,
    publisher: Callable[[list[tuple[Path, bytes]]], None] | None = None,
) -> dict:
    baseline_path = Path(baseline_path)
    source_out = Path(source_out)
    receipt_out = Path(receipt_out)
    if not baseline_path.is_file() or baseline_path.is_symlink():
        raise ValueError(f"baseline must be an ordinary file: {baseline_path}")
    if source_out.resolve(strict=False) == receipt_out.resolve(strict=False):
        raise ValueError("source and receipt destinations must differ")

    raw = baseline_path.read_bytes()
    if digest(raw) != BASELINE_ARCHIVE_SHA256:
        raise ValueError("production20f archive identity mismatch")

    here = Path(__file__).resolve().parent
    stage = _load_production_support(here)
    baseline = stage.support.parse_archive_bytes(raw, BASELINE_ARCHIVE_SHA256)
    stage.support.verify_semantic_topology(
        baseline,
        stage.SEMANTIC_MEMBER_SHA256,
        stage.SEMANTIC_ANCHORS,
    )
    outputs, receipt = build_from_members(baseline)

    if publisher is None:
        custody = _load_module(
            "_titan_v5_f38_publication_custody",
            here.parent / "selective-carrot" / "publication_custody.py",
        )
        publisher = custody.publish_exclusive
    publisher([
        (source_out, outputs[FROZEN_PATH]),
        (receipt_out, outputs["RECEIPT.json"]),
    ])
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--source-out", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    receipt = materialize(args.baseline, args.source_out, args.receipt)
    print(json.dumps({
        "arm": receipt["arm"],
        "baseline_archive_sha256": receipt["baseline_archive_sha256"],
        "source_postimage_sha256": receipt["source_postimage_sha256"],
        "candidate_archive_materialized": False,
        "native_economics_status": receipt["native_economics_status"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
