"""Reproduce declared ROWAN + SORREL Kaggriculture policy compositions.

Derived from ROWAN, SORREL, Euler, ASTRA-WORK / TokenJunkieLabs.
SPDX-License-Identifier: MIT OR CC-BY-4.0
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
REVENUE = HERE.parents[1]
ROWAN = REVENUE / "kaggriculture" / "cloud-dispatch" / "candidate.py"
SORREL = REVENUE / "kaggriculture" / "cloud-herd" / "variants.py"
ROWAN_SHA256 = "d87fafab8c9267d508533cd04e7ab8fa8e7c5f71414d9935ec4ddd977f0e7f74"
DECLARED = {
    "dispatch_pipeline": {"pipeline": True},
    "dispatch_balanced": {"pipeline": True, "capital_weight": 0.5},
}


def _sorrel_module():
    spec = importlib.util.spec_from_file_location("sorrel_variants", SORREL)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the frozen SORREL generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(source: str, options: dict) -> str:
    """Apply only SORREL's purchasing transform to ROWAN's selected bytes."""
    if hashlib.sha256(source.encode()).hexdigest() != ROWAN_SHA256:
        raise ValueError("Expected the exact selected ROWAN candidate")
    if options not in DECLARED.values():
        raise ValueError("Options were not declared before development")
    sorrel = _sorrel_module()
    start = source.index("    affordable_animal = None\n")
    end = source.index("\n    total_capacity = len(spots)", start)
    updated = (source[:start] +
        "    affordable_animal = choose_purchase(obs, configuration, remaining_days,\n"
        "        horizon, production, demand, future_prices, policy)\n" + source[end:])
    marker = "\ndef distance(a, b):"
    if updated.count(marker) != 1:
        raise ValueError("Expected one helper insertion location")
    updated = updated.replace(marker, "\nHERD = " + repr(options) + "\n" + sorrel.HELPER + marker, 1)
    updated = ("# FLORA composition: exact ROWAN dispatch_sales + SORREL purchasing.\n"
               "# SPDX-License-Identifier: MIT OR CC-BY-4.0\n" + updated)
    ast.parse(updated)
    return updated


def generate(output: Path) -> dict[str, str]:
    source = ROWAN.read_text()
    output.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name, options in DECLARED.items():
        path = output / f"{name}.py"
        data = build(source, options)
        path.write_text(data)
        hashes[name] = hashlib.sha256(data.encode()).hexdigest()
    return hashes


if __name__ == "__main__":
    import argparse, json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(generate(args.output), indent=2, sort_keys=True))
