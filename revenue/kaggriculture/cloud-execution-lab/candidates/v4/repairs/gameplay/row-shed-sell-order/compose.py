# SPDX-License-Identifier: Apache-2.0
"""Compose STRATUM row-shed ordering into the current V4 selected SELL seam.

The transform is deliberately source-only. It consumes the caller-owned
post-unit projection already computed by ``FrozenSelected.transform`` and then
hands the reordered action back to that same current seller. It never creates a
controller, scheduler, config key, runtime entrypoint, archive or release.

Default custody is the authenticated LOOM-5 CAPTRACE+LIVEPATH frozen postimage.
A different whole-file input may be supplied only explicitly for reproduction;
the method-level source pin remains mandatory and the receipt binds the actual
authenticated whole-file input rather than claiming canonical predecessor bytes.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path

ROW_SHED_SOURCE_BLOB = "5d3f1137a300480f6574accd9ccdfb3e11e431cf"
ROW_SHED_SOURCE_SHA256 = "e0460c91db6ad2487778f18dcec4b2ee41a53b833eaa0831425a56fd07d0fc42"
GRAPH_PREDECESSOR_FROZEN_BLOB = "4a5d3d5f4bed04acf73c7339e41fed56badf34c9"
GRAPH_PREDECESSOR_FROZEN_SHA256 = "4dc1de418632edd0a0bb66b9b01ab267c73225badabf0b62b5dee81d50233c5e"
METHOD_BEFORE_SHA256 = "593ef59a03a3e9a54d001ab12edc7c11ca0c803f20759f5b51b2c82d036457ea"
# Filled from the deterministic method rewrite below and asserted by tests.
METHOD_AFTER_SHA256 = "327a2dfbf8af9a88fb97c98b85c2cbc4357e1a2937d37930c053b7ea0c29e639"

IMPORT_ANCHOR = (
    "from selected_sell_core import optimize_lot, joint_plan_metrics, shared_slot_ledger\n"
)
IMPORT_LINE = "from row_shed_sell_order import RowShedSellOrder\n"
CALL_ANCHOR = "        farm,private=post_units(obs,base,config)\n"
CALL_INJECT = '''        row_shed = RowShedSellOrder()\n        base = row_shed.transform(\n            obs, config, base, post_unit_shed=private['shed'], fallback_action=base)\n        self.row_shed_diagnostics = row_shed.diagnostics.copy()\n'''


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _method_span(source: str) -> tuple[int, int, str]:
    tree = ast.parse(source)
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "FrozenSelected"]
    if len(classes) != 1:
        raise ValueError("expected exactly one FrozenSelected class")
    methods = [n for n in classes[0].body
               if isinstance(n, ast.FunctionDef) and n.name == "transform"]
    if len(methods) != 1 or methods[0].decorator_list:
        raise ValueError("FrozenSelected.transform is missing, duplicated or decorated")
    node = methods[0]
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    start, end = offsets[node.lineno - 1], offsets[node.end_lineno]
    return start, end, source[start:end]


def compose_frozen(source: str) -> str:
    """Return a byte-preserving rewrite outside one import and one method seam."""
    ast.parse(source)
    start, end, method = _method_span(source)
    observed = hashlib.sha256(method.encode("utf-8")).hexdigest()

    already_imported = source.count(IMPORT_LINE)
    already_called = "row_shed.transform(" in method
    if observed == METHOD_AFTER_SHA256:
        if already_imported != 1 or not already_called:
            raise ValueError("row-shed postimage is only partially composed")
        return source
    if observed != METHOD_BEFORE_SHA256:
        raise ValueError("FrozenSelected.transform source drift; rebase explicitly")
    if already_imported or already_called:
        raise ValueError("row-shed seam is partially composed")
    if source.count(IMPORT_ANCHOR) != 1:
        raise ValueError("selected-sell import anchor is missing or ambiguous")
    if method.count(CALL_ANCHOR) != 1:
        raise ValueError("post-unit projection anchor is missing or ambiguous")

    changed_method = method.replace(CALL_ANCHOR, CALL_ANCHOR + CALL_INJECT, 1)
    changed_digest = hashlib.sha256(changed_method.encode("utf-8")).hexdigest()
    if changed_digest != METHOD_AFTER_SHA256:
        raise ValueError("unexpected row-shed method postimage")

    result = source[:start] + changed_method + source[end:]
    result = result.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT_LINE, 1)
    compile(result, "frozen_selected.py", "exec")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True,
                        help="Runtime/source tree containing frozen_selected.py")
    parser.add_argument("--output", type=Path, required=True,
                        help="New source-only output directory")
    parser.add_argument("--frozen-blob", default=GRAPH_PREDECESSOR_FROZEN_BLOB,
                        help="Explicit whole-file input pin; default is canonical LOOM postimage")
    args = parser.parse_args()

    donor_path = Path(__file__).with_name("row_shed_sell_order.py")
    donor = donor_path.read_bytes()
    if git_blob(donor) != ROW_SHED_SOURCE_BLOB or hashlib.sha256(donor).hexdigest() != ROW_SHED_SOURCE_SHA256:
        raise SystemExit("row_shed_sell_order.py does not match canonical STRATUM source")

    frozen_path = args.package / "frozen_selected.py"
    frozen = frozen_path.read_bytes()
    input_blob = git_blob(frozen)
    input_sha256 = hashlib.sha256(frozen).hexdigest()
    if input_blob != args.frozen_blob:
        raise SystemExit(f"frozen_selected.py input blob {input_blob} != explicit pin {args.frozen_blob}")

    changed = compose_frozen(frozen.decode("utf-8")).encode("utf-8")
    canonical_graph_input = (
        input_blob == GRAPH_PREDECESSOR_FROZEN_BLOB
        and input_sha256 == GRAPH_PREDECESSOR_FROZEN_SHA256
    )
    receipt = {
        "schema": "titan-v4-row-shed-composition/v1",
        "scope": "current-selected-sell-row-order-only",
        "release_authorized": False,
        "production_activated": False,
        "source_copied_verbatim": True,
        "canonical_source": {
            "path": "repairs/gameplay/row-shed-sell-order/row_shed_sell_order.py",
            "git_blob": ROW_SHED_SOURCE_BLOB,
            "sha256": ROW_SHED_SOURCE_SHA256,
        },
        "graph_predecessor": {
            "surface": "frozen_selected.py",
            "git_blob": input_blob,
            "sha256": input_sha256,
        },
        "canonical_graph_predecessor": {
            "surface": "frozen_selected.py",
            "git_blob": GRAPH_PREDECESSOR_FROZEN_BLOB,
            "sha256": GRAPH_PREDECESSOR_FROZEN_SHA256,
            "matches_input": canonical_graph_input,
        },
        "materialization": {
            "input_git_blob": input_blob,
            "output_git_blob": git_blob(changed),
            "output_sha256": hashlib.sha256(changed).hexdigest(),
            "method_before_sha256": METHOD_BEFORE_SHA256,
            "method_after_sha256": METHOD_AFTER_SHA256,
        },
        "order": [
            "current FrozenSelected post_units projection",
            "canonical RowShedSellOrder using private['shed']",
            "existing FrozenSelected SELL economics",
        ],
        "limitations": [
            "source composition only",
            "noncanonical explicit reproduction inputs are receipt-bound but are not canonical graph evidence",
            "default graph predecessor must still be materialized by the sole graph runner",
            "no official-engine/full-game activation evidence is claimed",
        ],
    }

    # All source, blob and compile checks finish before creating output bytes.
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "frozen_selected.py").write_bytes(changed)
    (args.output / "row_shed_sell_order.py").write_bytes(donor)
    (args.output / "ROW-SHED-COMPOSITION.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
