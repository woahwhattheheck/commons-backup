#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Portable helper-only checks. Never materialize or import a production router."""
import ast
import copy
from pathlib import Path
from types import SimpleNamespace

import validate_production_patch as proof

HERE = Path(__file__).resolve().parent


def main():
    patch_helper = proof.helper_from_patch()
    tree = ast.parse((HERE / "v4_salvage_fast_clone.py").read_bytes())
    values = [node.value for node in tree.body if isinstance(node, ast.Assign)
              and any(isinstance(t, ast.Name) and t.id == "HELPERS" for t in node.targets)]
    proof.require(len(values) == 1, "ambiguous materializer HELPERS")
    source = ast.literal_eval(values[0])
    helper_tree = ast.parse(source)
    namespace = {"copy": copy}
    exec(compile(helper_tree, "<preserved-clone-helper>", "exec"), namespace)
    materializer_helper = SimpleNamespace(**{name: namespace[name] for name in proof.HELPER_NAMES})
    # Function ASTs must be identical between the two preserved transports.
    patched_lines, hunk = [], 0
    for line in proof.PATCH.read_text().splitlines():
        if line.startswith("@@"):
            hunk += 1
        elif hunk == 1 and line.startswith("+"):
            patched_lines.append(line[1:])
    proof.require(ast.dump(helper_tree) == ast.dump(ast.parse("\n".join(patched_lines))),
                  "patch/materializer helper drift")
    for name, helper in (("patch", patch_helper), ("materializer", materializer_helper)):
        contracts, sharing = proof.validate_fallback_and_graph_contracts(helper)
        print(f"{name}: contracts={contracts} sharing_cases={sharing} PASS")
    native_contracts = proof.validate_native_delta_contracts()
    print(f"native_delta_contracts={native_contracts} PASS")
    print("FAST CLONE GRAPH REPAIR PASS; production_activation=false; full_tape_gate=NOT_RUN")


if __name__ == "__main__":
    main()
