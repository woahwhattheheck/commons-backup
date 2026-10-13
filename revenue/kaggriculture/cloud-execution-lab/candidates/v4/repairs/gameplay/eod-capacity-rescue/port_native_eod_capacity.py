# SPDX-License-Identifier: Apache-2.0
"""Port the preserved EOD helper's dependencies, not its policy, to native TITAN.

This source-pinned adapter does not edit a runtime, archive, config, or feature
flag. It keeps the donor's public call/guards and false-by-default admission.
The four shared predicates below are transcribed from H3c blob
79c3fd029054a2db5931609db06f6b9aa4d4be3c. No legacy router is executed.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
from pathlib import Path

DONOR_BLOB = "9ad4092453e2332b0914f90ca89791b18f2229c2"
H3C_BLOB = "79c3fd029054a2db5931609db06f6b9aa4d4be3c"
RUNTIME_BLOB = "b952c9c228ecbde592bf3d2df01638677abb0d24"

# Same helpers/config as the authenticated H3c dependency. The EOD donor uses
# no other H3c function; inlining avoids an otherwise unnecessary legacy ABI.
SHARED_PREDICATES = '''STANDARD_CONFIG = {
    "boardSize": 10,
    "turnsPerDay": 24,
    "shedCapacity": 100,
    "maxMarketOrdersPerTurn": 10,
}


def _cfg(configuration: Any, name: str):
    if configuration is None:
        return _MISSING
    try:
        if isinstance(configuration, dict):
            return configuration.get(name, _MISSING)
        return getattr(configuration, name, _MISSING)
    except Exception:
        return _MISSING


def _standard_configuration(configuration: Any) -> bool:
    for name, expected in STANDARD_CONFIG.items():
        actual = _cfg(configuration, name)
        if actual is _MISSING or type(actual) is not int or actual != expected:
            return False
    return True


def _strict_inventory_total(mapping: Any) -> int | None:
    if not isinstance(mapping, dict):
        return None
    total = 0
    for item, quantity in mapping.items():
        if not isinstance(item, str) or type(quantity) is not int or quantity < 0:
            return None
        total += quantity
    return total


def _parent_rows(action: Any):
    if not isinstance(action, dict):
        return None
    farmer = action.get("farmer", _MISSING)
    hands = action.get("hands", _MISSING)
    if not isinstance(farmer, list) or not isinstance(hands, list):
        return None
    if any(not isinstance(command, list) for command in hands):
        return None
    return [farmer, *hands]
'''


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def native_source(donor: str) -> str:
    """Return a dependency-only transplant; refuse changed donor bytes."""
    if git_blob(donor.encode("utf-8")) != DONOR_BLOB:
        raise ValueError("EOD donor pin mismatch; review source rather than bypassing pin")
    h3c_import = "import h3c_goose_eod_cap_rescue as h3c"
    router_import = "import r04_full_router as r04"
    if donor.count(h3c_import) != 1 or donor.count(router_import) != 1:
        raise ValueError("Unexpected dependency seam")
    allowed = {"_MISSING", "_cfg", "_standard_configuration", "_parent_rows",
               "_strict_inventory_total", "STANDARD_CONFIG"}
    for node in ast.walk(ast.parse(donor)):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == "h3c" and node.attr not in allowed:
                raise ValueError("Donor now needs an unported H3c dependency")
    source = donor.replace(h3c_import, SHARED_PREDICATES).replace(
        router_import, "import mechanics as r04").replace("h3c.", "")
    compile(source, "native_eod_capacity_rescue.py", "exec")
    return source


def wire_runtime(runtime: str) -> str:
    """Produce an OFF-by-default current-ABI candidate in memory, never on main.

    This is a source placement/contract experiment, not promotion authority.
    It runs after stock/capital guards and before final action observers. The
    full runtime's other branches and shared lifecycle logic stay unchanged.
    """
    if git_blob(runtime.encode("utf-8")) != RUNTIME_BLOB:
        raise ValueError("Native runtime pin mismatch; rebase against lifecycle owner")
    tree = ast.parse(runtime)
    features = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Features")
    names = {n.target.id for n in features.body if isinstance(n, ast.AnnAssign)
             and isinstance(n.target, ast.Name)}
    if "r04_eod_capacity_rescue" in names:
        raise ValueError("Feature already exists; do not double-wire")
    lines = runtime.splitlines(keepends=True)
    lines.insert(features.end_lineno, "    r04_eod_capacity_rescue: bool = False\n")
    source = "".join(lines)
    seam = "        returned = self._early_capital_selected(obs, cfg or {}, returned)\n"
    if source.count(seam) != 1:
        raise ValueError("Final-action seam is not unique")
    hook = ("        if self.features.r04_eod_capacity_rescue:\n"
            "            from native_eod_capacity_rescue import apply_eod_capacity_rescue\n"
            "            returned = apply_eod_capacity_rescue(returned, obs, cfg or {}, enabled=True)\n")
    source = source.replace(seam, seam + hook)
    compile(source, "native_eod_capacity_runtime.py", "exec")
    return source


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--donor", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # Exclusive creation: do not accidentally replace production or peer work.
    with args.output.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(native_source(args.donor.read_text(encoding="utf-8")))


if __name__ == "__main__":
    main()
