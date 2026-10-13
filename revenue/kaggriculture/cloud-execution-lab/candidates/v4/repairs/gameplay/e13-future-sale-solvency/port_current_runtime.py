#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Current-ABI V4 port of the E13 post-future-sale solvency repair.

The canonical runtime is never edited by this tool.  It authenticates the live
FrozenSelected source and pinned interpreter, replaces exactly one top-level
``funded_minimum_now`` function in a disconnected candidate, compiles it, and
emits a deterministic custody receipt.

Historical source: PR #12037.  The old packet stayed source-real/action-
unmeasured; this V4 port preserves that evidence boundary while making the
method-scoped transform consumable by the sole V4 composition graph.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
from typing import Any

OPERATION = "TITAN-V4-E13-FUTURE-SALE-SOLVENCY-PORT-20260912"
SOURCE_REL = Path("revenue/kaggriculture/cloud-execution-lab/frozen_selected.py")
ENGINE_REL = Path("revenue/kaggriculture/cloud-execution-lab/reference/engine/kaggriculture.py")
EXPECTED_SOURCE_GIT_BLOB = "fc7baf5c179818a55037f6a61d92984d81d1a21c"
EXPECTED_ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
TARGET_FUNCTION = "funded_minimum_now"


class PortError(RuntimeError):
    pass


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def find_repo_root(start: Path | None = None) -> Path:
    origin = (start or Path(__file__).resolve()).resolve()
    for candidate in (origin, *origin.parents):
        root = candidate.parent if candidate.is_file() else candidate
        if (root / SOURCE_REL).is_file() and (root / ENGINE_REL).is_file():
            return root
    raise PortError("repository root not found")


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _reject_symlink_prefix(path: Path, label: str) -> None:
    """Reject any existing symlink component, including the final path."""
    absolute = Path(os.path.abspath(os.fspath(path)))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise PortError(f"{label} path has symlink component: {current}")
        if not current.exists():
            break


def _scratch_destination(root: Path, path: Path, label: str) -> Path:
    """Return a resolved external scratch path or fail closed.

    E13 is a candidate materializer, not a repository writer. Both candidate
    and receipt must live completely outside the checked-out repository. We
    check lexical containment, symlink ancestry, and resolved containment so a
    caller cannot redirect writes onto any runtime/repo file.
    """
    root = root.resolve()
    lexical = Path(os.path.abspath(os.fspath(path)))
    root_lexical = Path(os.path.abspath(os.fspath(root)))
    if _is_within(lexical, root_lexical):
        raise PortError(f"refusing to overwrite repository path for {label}: {lexical}")
    _reject_symlink_prefix(lexical, label)
    resolved = lexical.resolve(strict=False)
    if _is_within(resolved, root):
        raise PortError(f"refusing to overwrite repository path for {label}: {resolved}")
    return resolved


def _function_byte_span(source: bytes, name: str) -> tuple[int, int]:
    text = source.decode("utf-8")
    tree = ast.parse(text)
    matches = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    if len(matches) != 1:
        raise PortError(f"expected exactly one top-level {name}, found {len(matches)}")
    node = matches[0]
    if node.end_lineno is None:
        raise PortError("AST did not expose target end line")
    lines = text.splitlines(keepends=True)
    start = len("".join(lines[: node.lineno - 1]).encode("utf-8"))
    end = len("".join(lines[: node.end_lineno]).encode("utf-8"))
    return start, end


REPLACEMENT_FUNCTION = r'''def funded_minimum_now(obs, config, base, farm, private, route, end,
                       current, targets, item, stress_units=32):
    """Smallest current sale preserving bounded inherited acquisition fills.

    The legacy E13 prefix remains authoritative through the turn before the
    first actually executed positive-cash future SELL.  Fixed acquisitions on
    strictly later turns are also protected, crediting represented future cash
    exactly instead of treating any positive receipt as a full capital reset.
    Same-turn acquisitions remain outside this repair (SOL-ESCROW boundary).
    """
    def _strict_nonnegative_int(value, label):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f'{label} must be a plain nonnegative integer')
        return value

    now = _strict_nonnegative_int(obs.get('step'), 'step')
    end = _strict_nonnegative_int(end, 'end')
    if end < now:
        raise ValueError('end must not precede step')
    baseline = _strict_nonnegative_int(current.get(item, 0), f'current[{item!r}]')
    raw_max_orders = _strict_nonnegative_int(
        config.get('maxMarketOrdersPerTurn', 10),
        'maxMarketOrdersPerTurn',
    )
    # Official _process_market normalizes this setting with max(1, int(...)).
    # E13 must use the same effective prefix everywhere: both its local sale
    # materializer and inherited _funding_trace re-read the configuration.
    max_orders = max(1, raw_max_orders)
    effective_config = dict(config)
    effective_config['maxMarketOrdersPerTurn'] = max_orders
    stress_units = _strict_nonnegative_int(stress_units, 'stress_units')
    certificate = {
        'item': item, 'baseline_now': baseline, 'prefix_end': end,
        'funding_turn': None, 'stress_units': stress_units,
        'raw_max_market_orders': raw_max_orders,
        'effective_max_market_orders': max_orders,
        'fallback': False,
    }
    try:
        reference_market = materialize_sales(
            base['market'], current, private['shed'], targets, max_orders)
        scout = _funding_trace(
            obs, effective_config, farm, private, route, now, end,
            reference_market, stress_units=0)
        prefix_end, funding_turn = _funding_prefix_end(scout, now, end)
        certificate['prefix_end'] = prefix_end
        certificate['funding_turn'] = funding_turn
        if prefix_end == end:
            reference = scout
        else:
            reference = _funding_trace(
                obs, effective_config, farm, private, route, now, prefix_end,
                reference_market, stress_units=0)

        prefix_required = {
            key: units for key, units in reference['acquisitions'] if units > 0}
        post_funding_required = (
            {
                key: units
                for key, units in scout['acquisitions']
                if units > 0 and key[0] > funding_turn
            }
            if funding_turn is not None
            else {}
        )
        required = dict(prefix_required)
        required.update(post_funding_required)
        comparison_end = end if post_funding_required else prefix_end

        certificate['prefix_reference_acquisitions'] = sum(prefix_required.values())
        certificate['post_funding_acquisitions'] = sum(post_funding_required.values())
        certificate['reference_acquisitions'] = sum(required.values())
        certificate['protected_acquisition_rows'] = len(required)
        certificate['comparison_end'] = comparison_end
        certificate['reference_terminal_cash'] = reference['cash']
        certificate['solvency_reference_terminal_cash'] = scout['cash']
        if not required:
            certificate['minimum_now'] = 0
            return 0, certificate

        for quantity in range(baseline + 1):
            totals = dict(current)
            totals[item] = quantity
            candidate_market = materialize_sales(
                base['market'], totals, private['shed'], targets, max_orders)
            traces = [
                _funding_trace(
                    obs, effective_config, farm, private, route, now, comparison_end,
                    candidate_market, stress_units=0),
                _funding_trace(
                    obs, effective_config, farm, private, route, now, comparison_end,
                    candidate_market, stress_units=stress_units),
            ]
            safe = True
            for trace in traces:
                filled = dict(trace['acquisitions'])
                if any(filled.get(key, 0) < units for key, units in required.items()):
                    safe = False
                    break
            if safe:
                certificate['minimum_now'] = quantity
                certificate['scenario_terminal_cash'] = [trace['cash'] for trace in traces]
                return quantity, certificate
    except Exception as exc:
        certificate['error'] = f'{type(exc).__name__}: {exc}'[:500]
    certificate['fallback'] = True
    certificate['minimum_now'] = baseline
    return baseline, certificate
'''.strip("\n") + "\n"


def build_candidate(source: bytes) -> bytes:
    observed = git_blob_sha(source)
    if observed != EXPECTED_SOURCE_GIT_BLOB:
        raise PortError(
            f"FrozenSelected drift: expected {EXPECTED_SOURCE_GIT_BLOB}, got {observed}")
    text = source.decode("utf-8")
    anchors = (
        "def _funding_prefix_end(trace, now, end):",
        "if t > now and cash > 0:",
        "prefix_end, funding_turn = _funding_prefix_end(scout, now, end)",
        "required = {key: units for key, units in reference['acquisitions'] if units > 0}",
    )
    missing = [anchor for anchor in anchors if anchor not in text]
    if missing:
        raise PortError(f"authenticated source missing predecessor anchors: {missing!r}")
    start, end = _function_byte_span(source, TARGET_FUNCTION)
    candidate = source[:start] + REPLACEMENT_FUNCTION.encode("utf-8") + source[end:]
    compile(candidate, "<v4-e13-candidate>", "exec")
    _function_byte_span(candidate, TARGET_FUNCTION)
    candidate_text = candidate.decode("utf-8")
    if candidate_text.count("def funded_minimum_now(") != 1:
        raise PortError("target function cardinality changed")
    if "comparison_end = end if post_funding_required else prefix_end" not in candidate_text:
        raise PortError("post-funding solvency boundary missing")
    return candidate


def materialize(root: Path, output: Path, receipt: Path) -> dict[str, object]:
    root = root.resolve()
    source_path = root / SOURCE_REL
    engine_path = root / ENGINE_REL
    source = source_path.read_bytes()
    engine = engine_path.read_bytes()
    source_blob = git_blob_sha(source)
    engine_blob = git_blob_sha(engine)
    if source_blob != EXPECTED_SOURCE_GIT_BLOB:
        raise PortError(f"source Git blob mismatch: {source_blob}")
    if engine_blob != EXPECTED_ENGINE_GIT_BLOB:
        raise PortError(f"engine Git blob mismatch: {engine_blob}")

    output = _scratch_destination(root, output, "candidate output")
    receipt = _scratch_destination(root, receipt, "receipt output")
    if output == receipt:
        raise PortError("candidate and receipt paths must differ")

    candidate = build_candidate(source)
    record: dict[str, object] = {
        "schema": "titan.v4.e13-future-sale-solvency.port.v1",
        "operation": OPERATION,
        "disposition": "CURRENT_ABI_SOURCE_REAL_ACTION_UNMEASURED",
        "source": {
            "path": SOURCE_REL.as_posix(),
            "git_blob_sha1": source_blob,
            "sha256": sha256(source),
            "bytes": len(source),
        },
        "engine": {
            "path": ENGINE_REL.as_posix(),
            "git_blob_sha1": engine_blob,
            "sha256": sha256(engine),
            "bytes": len(engine),
        },
        "candidate": {
            "function_replaced": TARGET_FUNCTION,
            "git_blob_sha1": git_blob_sha(candidate),
            "sha256": sha256(candidate),
            "bytes": len(candidate),
            "byte_delta": len(candidate) - len(source),
            "replacement_sha256": sha256(REPLACEMENT_FUNCTION.encode("utf-8")),
        },
        "custody": {
            "replacement_count": 1,
            "canonical_source_mutated": False,
            "canonical_engine_mutated": False,
            "outputs_external_to_repository": True,
            "symlink_ancestry_rejected": True,
            "post_sale_scope": "acquisition_turn_strictly_greater_than_funding_turn",
            "same_turn_order_aware_scope": "preserved_for_SOL_ESCROW",
        },
        "claims": {
            "returned_action_activation": False,
            "gameplay_strength": False,
            "score_causality": False,
            "production_promotion": False,
        },
    }
    receipt_bytes = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    output = _scratch_destination(root, output, "candidate output")
    receipt = _scratch_destination(root, receipt, "receipt output")
    out_tmp = _scratch_destination(root, output.with_name(output.name + ".tmp"), "candidate temp")
    rec_tmp = _scratch_destination(root, receipt.with_name(receipt.name + ".tmp"), "receipt temp")
    if out_tmp == rec_tmp or out_tmp in {output, receipt} or rec_tmp in {output, receipt}:
        raise PortError("temporary and final output paths must be distinct")

    out_tmp.write_bytes(candidate)
    rec_tmp.write_bytes(receipt_bytes)
    os.replace(out_tmp, output)
    os.replace(rec_tmp, receipt)
    if output.read_bytes() != candidate or receipt.read_bytes() != receipt_bytes:
        raise PortError("materialized output readback mismatch")
    if source_path.read_bytes() != source or engine_path.read_bytes() != engine:
        raise PortError("canonical inputs changed during materialization")
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()
    root = args.root.resolve() if args.root else find_repo_root()
    print(json.dumps(materialize(root, args.output, args.receipt), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
