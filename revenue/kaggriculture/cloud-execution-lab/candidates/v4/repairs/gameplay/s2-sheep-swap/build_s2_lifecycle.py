# SPDX-License-Identifier: Apache-2.0
"""Compose an explicit parked S2 source, preserving the current prefix/day fixes."""
from __future__ import annotations
import argparse
import ast
import hashlib
from pathlib import Path

PARENT_BLOB = "f1962bec590f0e63e27334c8d6a6e0e980a13518"
MECHANICS_BLOB = "044a4f9c0a4a44dde10ada57563238bcaf82075d"
MARKER = "# S2_NATIVE_UNIT_CUSTODY_V1\n"


def git_blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def compose(parent: bytes, mechanics: bytes, helper: bytes | None = None) -> bytes:
    if git_blob(mechanics) != MECHANICS_BLOB:
        raise ValueError("mechanics source differs from the validated native primitive")
    if git_blob(parent) != PARENT_BLOB:
        raise ValueError("S2 source differs from the validated prefix/day-coverage parent")
    if helper is None:
        helper = Path(__file__).with_name("s2_unit_custody.py").read_bytes()
    source = parent.decode("utf-8")
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                and n.name == "_projected_shed")
    lines = source.splitlines(keepends=True)
    lines[node.lineno - 1:node.end_lineno] = [
        "def _projected_shed(action, obs):\n",
        "    return _s2_projected_shed(action, obs)\n",
    ]
    source = "".join(lines)
    old = '            actor = pending_place["actor"]\n            state["carrying"][actor] = max(0, state["carrying"].get(actor, 0) - 1)\n'
    if source.count(old) != 1:
        raise ValueError("placement confirmation anchor changed")
    # Actual successful unit placement already debits the custody token once.
    source = source.replace(old, "", 1)
    start = source.index("    result = copy.deepcopy(parent_action)\n")
    end_marker = '    result["farmer"], result["hands"] = workers[0], workers[1:]\n'
    end = source.index(end_marker, start) + len(end_marker)
    source = (source[:start] + "    result = _s2_unit_stage(observation, parent_action, state)\n"
              + source[end:])
    output = (source + "\n\n" + MARKER).encode() + helper
    compile(output, "s2_lifecycle_candidate.py", "exec")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--mechanics", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() in (args.source.resolve(), args.mechanics.resolve()):
        parser.error("output must not overwrite either input")
    output = compose(args.source.read_bytes(), args.mechanics.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Existing unrelated bytes are never replaced by this research tool.
    if args.output.exists():
        if args.output.read_bytes() != output:
            parser.error("output already exists with different bytes")
    else:
        with args.output.open("xb") as stream:
            stream.write(output)
    print(git_blob(output))


if __name__ == "__main__":
    main()
