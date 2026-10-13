"""Pinned Kaggle file-agent loading contract, without optional HTTP/schema imports.

Execute the unmodified AST definitions listed below from the preserved upstream
sources. Only the local-file branch is used. This is not the hosted runner.
"""
from __future__ import annotations

import ast
from functools import lru_cache
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable, Dict, Tuple
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent


def selected(source, names, namespace):
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    nodes = [node for node in tree.body
             if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names]
    if {node.name for node in nodes} != set(names):
        raise ValueError(f"Missing pinned definitions in {source.name}")
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), namespace)


@lru_cache(maxsize=1)
def contract():
    upstream = HERE / "upstream"
    manifest = json.loads((upstream / "manifest.json").read_text())
    for name, item in manifest["files"].items():
        if hashlib.sha256((upstream / name).read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError(f"Pinned loader source changed: {name}")
    namespace = {"__name__": "kag_pack_pinned_contract",
                 "__file__": str(upstream / "errors.py")}
    exec(compile((upstream / "errors.py").read_text(), str(upstream / "errors.py"), "exec"), namespace)
    namespace.update(os=os, sys=sys, StringIO=StringIO, Any=Any, Callable=Callable,
                     Dict=Dict, Tuple=Tuple, Path=Path, urlparse=urlparse)
    selected(upstream / "utils.py", {"Struct", "structify", "read_file"}, namespace)
    selected(upstream / "agent.py", {"is_url", "get_last_callable", "build_agent"}, namespace)
    return namespace


def make_agent(path):
    """Use build_agent's file path, last-callable choice and argument slicing."""
    path = Path(path).resolve(strict=True)
    namespace = contract()
    function, _ = namespace["build_agent"](str(path), {}, "kaggriculture")

    def call(observation, configuration):
        return function(namespace["structify"](observation),
                        namespace["structify"](configuration))

    return call
