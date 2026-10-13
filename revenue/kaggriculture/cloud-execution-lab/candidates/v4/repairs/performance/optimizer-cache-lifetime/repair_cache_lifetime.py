# SPDX-License-Identifier: Apache-2.0
"""Source-only native optimizer lifetime repair; never edits the production root.

The output preserves all optimizer statements and wraps only its private model's
use in try/finally. An explicit Git-blob pin is required for composed successors.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path

SOURCE_GIT = "f23d3a8b5ee5e82029026e7f8f44eb36c143a5a3"
SCHEDULER_GIT = "a483b24dd72b580d7d8811636b54d2d44f391575"
MARKER = "# CACHELIFE: release this call's private model even on interruption."
FINALIZER = """    finally:
        # CACHELIFE: release this call's private model even on interruption.
        model.quote.cache_clear()
        model.single.cache_clear()
        model.joint.cache_clear()
        del model.single, model.joint
"""


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def project(node: ast.AST) -> str:
    return ast.dump(node, include_attributes=False)


def transform(source: str, expected_source_git: str = SOURCE_GIT) -> str:
    """Return a pinned successor, preserving every original optimizer statement.

    Peers can supply their independently reviewed input blob explicitly. Pins are
    identity checks, not a claim that arbitrary supplied source was reviewed.
    """
    require(len(expected_source_git) == 40 and
            all(c in "0123456789abcdef" for c in expected_source_git),
            "expected source must be a full lowercase Git blob SHA")
    require(git_blob(source.encode("utf-8")) == expected_source_git,
            "source Git blob mismatch")
    require(MARKER not in source, "repair already applied")
    require("\r" not in source and source.endswith("\n"), "require LF-terminated source")
    tree = ast.parse(source)
    targets = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == "optimize_lot"]
    require(len(targets) == 1 and isinstance(targets[0], ast.FunctionDef),
            "one synchronous optimize_lot required")
    function = targets[0]
    require(not function.decorator_list and len(function.body) > 2,
            "unexpected optimizer shape")
    prefix = ast.parse("end=dates[-1]\nmodel=MarketPath(item,inventory,params,shops,config,now,end)\n").body
    require([project(n) for n in function.body[:2]] == [project(n) for n in prefix],
            "private model construction drift")
    for statement in function.body[2:]:
        for node in ast.walk(statement):
            require(not (isinstance(node, ast.Name) and node.id == "model"
                         and isinstance(node.ctx, (ast.Store, ast.Del))),
                    "private model is rebound or deleted")
            require(not isinstance(node, (ast.Yield, ast.YieldFrom, ast.Await)),
                    "optimizer cannot suspend")
    # Only immediate score calls may consume this private owner. Do not destroy
    # caches of a model returned, aliased, borrowed, or published by a successor.
    parents = {child: parent for parent in ast.walk(function)
               for child in ast.iter_child_nodes(parent)}
    for statement in function.body[2:]:
        for node in ast.walk(statement):
            if isinstance(node, ast.Name) and node.id == "model":
                attribute = parents.get(node)
                call = parents.get(attribute)
                require(isinstance(attribute, ast.Attribute) and attribute.value is node
                        and attribute.attr == "score" and isinstance(call, ast.Call)
                        and call.func is attribute, "private model escapes direct score use")
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "MarketPath"]
    require(len(classes) == 1, "one MarketPath required")
    initializers = [n for n in classes[0].body
                    if isinstance(n, ast.FunctionDef) and n.name == "__init__"]
    require(len(initializers) == 1, "one MarketPath initializer required")
    expected_caches = ast.parse("""self.quote=lru_cache(maxsize=2048)(lambda inv:m.market_price(item,inv,params))
self.single=lru_cache(maxsize=8192)(self._single)
self.joint=lru_cache(maxsize=8192)(self._joint)
""").body
    for expected in expected_caches:
        require(sum(project(n) == project(expected) for n in initializers[0].body) == 1,
                "native per-model cache construction drift")
    lines = source.splitlines(keepends=True)
    # Include comments/blank lines after construction, not just AST statements.
    start = function.body[1].end_lineno
    end = function.end_lineno
    original = lines[start:end]
    require(all(not line.strip() or line.startswith("    ") for line in original),
            "unexpected optimizer indentation")
    output = "".join(lines[:start]) + "    try:\n" + "".join(
        "    " + line if line.strip() else line for line in original
    ) + FINALIZER + "".join(lines[end:])
    candidate = ast.parse(output)
    result = next(n for n in candidate.body if isinstance(n, ast.FunctionDef)
                  and n.name == "optimize_lot")
    require(len(result.body) == 3 and isinstance(result.body[2], ast.Try),
            "invalid generated lifetime scope")
    scoped = result.body[2]
    require(not scoped.handlers and not scoped.orelse, "unexpected catch/else")
    require([project(n) for n in scoped.body] ==
            [project(n) for n in function.body[2:]], "optimizer statement drift")
    # Strip only the newly introduced scope and prove the complete module AST.
    result.body = result.body[:2] + scoped.body
    require(project(candidate) == project(tree), "non-lifetime AST drift")
    compile(output, "selected_sell_core.py", "exec")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--expected-source-git", default=SOURCE_GIT)
    args = parser.parse_args()
    require(not args.source.is_symlink(), "source must not be a symlink")
    require(args.source.resolve() != args.output.resolve(), "input/output alias")
    raw = args.source.read_bytes()
    output = transform(raw.decode("utf-8"), args.expected_source_git).encode("utf-8")
    # Exclusive creation also rejects symlinks, hard-link aliases, and overwrites.
    with args.output.open("xb") as stream:
        stream.write(output)
    print(json.dumps({"schema": "titan-v4-cache-lifetime-materialization/v1",
                      "input_git_blob": git_blob(raw), "output_git_blob": git_blob(output),
                      "output_sha256": hashlib.sha256(output).hexdigest(),
                      "production_mutation": False}, sort_keys=True))


if __name__ == "__main__":
    main()
