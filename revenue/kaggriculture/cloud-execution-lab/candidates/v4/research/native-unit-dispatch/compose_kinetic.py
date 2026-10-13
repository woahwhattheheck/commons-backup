# SPDX-License-Identifier: Apache-2.0
"""Source-bound unit helper fusion for the single TITAN V4 candidate workspace.

No runtime activation: writes an explicitly named scratch module. Non-target
source bytes are preserved; changed dependency/function spans fail closed.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import tempfile

BASE_BLOB = "044a4f9c0a4a44dde10ada57563238bcaf82075d"
DEPENDENCIES = {'_farmer_position': '466d9705b68f4dd4bf3678c3037b0a95403b05f86ec5b57ca0030f7f43afb383', '_farmer_inventory': 'aadbfb8a4a7f66ce75d2cc6bb1c1b0f22bb2bedbc881b8932a8526304d46107d', '_set_farmer_position': 'bee0f862e2b42428e5d61f22c14b228616d1fa102ba627dd5fb7490e33f039bb'}
BASE_SPAN_SHA256 = '2a0335111cbc61607120371006c0152fd0b48819b1ae8a5fbc011f6593cd70ed'
CANDIDATE_SPAN_SHA256 = '6d3e599bceeab0ee1866a55190b8a54256f36ef1b3211228ad8dec059618d108'

ALIASES = """# KINETIC: retain dynamic helper overrides; cache no mutable world state.
_KINETIC_POSITION = _farmer_position
_KINETIC_INVENTORY = _farmer_inventory
_KINETIC_SET_POSITION = _set_farmer_position
_KINETIC_LIST = list


"""
REPLACEMENTS = (
    ("    pos = _farmer_position(farm, idx)", """    if _farmer_position is _KINETIC_POSITION:
        if idx == 0:
            pos = farm["farmer"]
        else:
            pos = farm["hands"][idx - 1] if idx - 1 < len(farm["hands"]) else None
    else:
        pos = _farmer_position(farm, idx)"""),
    ("    inv = _farmer_inventory(private, idx)", """    if _farmer_inventory is _KINETIC_INVENTORY:
        while len(private["inventories"]) <= idx:
            private["inventories"].append({})
        inv = private["inventories"][idx]
    else:
        inv = _farmer_inventory(private, idx)"""),
    ("        _set_farmer_position(farm, idx, (nx, ny))", """        if _set_farmer_position is _KINETIC_SET_POSITION and list is _KINETIC_LIST:
            if idx == 0:
                farm["farmer"] = [nx, ny]
            else:
                farm["hands"][idx - 1] = [nx, ny]
        else:
            _set_farmer_position(farm, idx, (nx, ny))"""),
)


def digest(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def function_span(source: str, name: str) -> tuple[int, int, str]:
    """Exact UTF-8 source span, including the function's final newline."""
    nodes = [n for n in ast.parse(source).body
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if len(nodes) != 1 or nodes[0].decorator_list:
        raise ValueError(f"Expected one undecorated function: {name}")
    node = nodes[0]
    lines = source.splitlines(keepends=True)
    start = sum(map(len, lines[:node.lineno - 1]))
    end = sum(map(len, lines[:node.end_lineno]))
    return start, end, source[start:end]


def compose(source: str) -> str:
    """Fuse only authenticated leaf helpers inside _apply_unit_action.

    Every original operation, lookup order, alias side effect and non-movement
    action branch remains. Rebound helpers use the original call sites. The
    optimized movement assignment is used only with the captured list binding.
    """
    for name, expected in DEPENDENCIES.items():
        if digest(function_span(source, name)[2]) != expected:
            raise ValueError(f"Changed dependency: {name}")
    start, end, old = function_span(source, "_apply_unit_action")
    if digest(old) == CANDIDATE_SPAN_SHA256:
        if not source[:start].endswith(ALIASES) or source.count(ALIASES) != 1:
            raise ValueError("Candidate alias block missing, duplicated or changed")
        prefix = source[:start - len(ALIASES)]
        suffix = source[end:]
        if "_KINETIC_" in prefix + suffix:
            raise ValueError("Unexpected KINETIC alias name outside authenticated block")
        return source
    if digest(old) != BASE_SPAN_SHA256:
        raise ValueError("Changed _apply_unit_action span: explicit rebase required")
    if "_KINETIC_" in source:
        raise ValueError("KINETIC alias collision")
    new = old
    for before, after in REPLACEMENTS:
        if new.count(before) != 1:
            raise ValueError("Expected exactly one helper call site")
        new = new.replace(before, after, 1)
    if digest(new) != CANDIDATE_SPAN_SHA256:
        raise ValueError("Generated span does not match authenticated candidate")
    result = source[:start] + ALIASES + new + source[end:]
    compile(result, "kinetic-composed-mechanics", "exec")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("Input must remain immutable; name a different scratch output")
    if args.receipt and args.receipt.resolve() in {args.input.resolve(), args.output.resolve()}:
        parser.error("Receipt must not overwrite source or output")
    try:
        raw = args.input.read_bytes()
        result = compose(raw.decode("utf-8")).encode("utf-8")
    except (OSError, UnicodeError, ValueError, SyntaxError) as exc:
        parser.exit(2, f"KINETIC rejected input: {exc}\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=args.output.parent, delete=False) as tmp:
        temporary = Path(tmp.name)
        tmp.write(result)
    try:
        temporary.replace(args.output)
    finally:
        temporary.unlink(missing_ok=True)
    receipt = {"source_blob": git_blob(raw), "output_blob": git_blob(result),
               "source_sha256": hashlib.sha256(raw).hexdigest(),
               "output_sha256": hashlib.sha256(result).hexdigest(),
               "scope": "source composition only; not execution or promotion"}
    if args.receipt:
        args.receipt.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
