#!/usr/bin/env python3
"""Host injects+surfaces; cpu_fwd is the computer; connected GGUF is software
and on this machine was already WhiteBox-edited except Smol.

This additive launcher delegates only to pfc_load.py and pfc_harness.py.
The default software is C:/llm/models/Llama-3.3-70B-Instruct-Q4_K_M.gguf.
It never implements inference, recreates model weights as gates, fabricates,
or maps titan.gguf. Unsafe or missing delegated tools are refused.
"""

from __future__ import annotations

import argparse
import ast
import os
from pathlib import Path
import subprocess
import sys
from typing import Sequence


HERE = Path(__file__).resolve().parent
DEFAULT_MODEL_NAME = "Llama-3.3-70B-Instruct-Q4_K_M.gguf"

try:
    sys.path.insert(0, str(HERE))
    from pfc_paths import ROOT as PFC_ROOT  # type: ignore
    from pfc_paths import p as pfc_path  # type: ignore

    DEFAULT_MODEL = pfc_path(f"models/{DEFAULT_MODEL_NAME}")
except (ImportError, AttributeError):
    PFC_ROOT = os.environ.get("PFC_ROOT", "C:/llm").replace("\\", "/").rstrip("/")
    DEFAULT_MODEL = f"{PFC_ROOT}/models/{DEFAULT_MODEL_NAME}"


class UnsafeTool(RuntimeError):
    """The requested existing-tool path does not satisfy the runtime laws."""


def _display_command(argv: Sequence[str]) -> str:
    return subprocess.list2cmdline([str(part) for part in argv])


def _tool_source(name: str) -> tuple[Path, str, ast.Module]:
    path = HERE / name
    if not path.is_file():
        raise UnsafeTool(f"required tool is missing: {path}")
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise UnsafeTool(f"required tool cannot be safely inspected: {path}: {exc}") from exc
    return path, source, tree


def _import_roots(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def _whole_file_mmaps(tree: ast.AST) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_mmap = (
            isinstance(func, ast.Attribute)
            and func.attr == "mmap"
            or isinstance(func, ast.Name)
            and func.id == "mmap"
        )
        if is_mmap and len(node.args) >= 2:
            length = node.args[1]
            if isinstance(length, ast.Constant) and length.value == 0:
                lines.append(node.lineno)
    return lines


def _function(tree: ast.Module, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _validate(tool_name: str, action: str) -> Path:
    path, source, tree = _tool_source(tool_name)

    imports = _import_roots(tree)
    forbidden = sorted(imports.intersection({"numpy", "torch", "tensorflow", "jax"}))
    if forbidden:
        raise UnsafeTool(f"{path.name} imports host inference package(s): {', '.join(forbidden)}")

    required = _function(tree, action)
    if required is None:
        raise UnsafeTool(f"{path.name} does not expose the required {action!r} operation")

    source_lower = source.lower()
    recreated_ops = ("def matmul", "def attention", "def softmax", "def rmsnorm", "def rope")
    found_ops = [term[4:] for term in recreated_ops if term in source_lower]
    if found_ops:
        raise UnsafeTool(
            f"{path.name} appears to recreate forward-pass operations on the host: "
            + ", ".join(found_ops)
        )

    if action == "ask":
        mmap_lines = _whole_file_mmaps(tree)
        if mmap_lines:
            joined = ", ".join(str(line) for line in mmap_lines)
            raise UnsafeTool(f"{path.name} whole-file mmaps titan-compatible storage at line(s) {joined}")

        defaults = required.args.defaults
        if defaults and any(
            isinstance(default, ast.Constant)
            and isinstance(default.value, int)
            and default.value > 0
            for default in defaults
        ):
            raise UnsafeTool(f"{path.name} has a fixed integer generation cap in ask()")

    return path


def _delegate(tool_name: str, action: str, arguments: Sequence[str]) -> int:
    intended_path = HERE / tool_name
    intended = [sys.executable, str(intended_path), action, *arguments]
    try:
        tool = _validate(tool_name, action)
    except UnsafeTool as exc:
        print(f"REFUSED (fail closed): {exc}", file=sys.stderr)
        print("Intended existing-tool command (not run):", file=sys.stderr)
        print(f"  {_display_command(intended)}", file=sys.stderr)
        return 2

    command = [sys.executable, str(tool), action, *arguments]
    completed = subprocess.run(command, shell=False, check=False)
    return int(completed.returncode)


def _load(model: str) -> int:
    # pfc_load.py accepts the model as its first argument, without a command word.
    intended_path = HERE / "pfc_load.py"
    intended = [sys.executable, str(intended_path), model]
    try:
        tool = _validate("pfc_load.py", "load")
    except UnsafeTool as exc:
        print(f"REFUSED (fail closed): {exc}", file=sys.stderr)
        print("Intended existing-tool command (not run):", file=sys.stderr)
        print(f"  {_display_command(intended)}", file=sys.stderr)
        return 2

    completed = subprocess.run(
        [sys.executable, str(tool), model],
        shell=False,
        check=False,
    )
    return int(completed.returncode)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Additive fail-closed wrapper for existing Muhlnickel load/harness tools."
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"connected GGUF software (default: {DEFAULT_MODEL})",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("load", help="delegate model installation to pfc_load.py")
    subparsers.add_parser("connect", help="delegate reflector connection to pfc_harness.py")
    ask_parser = subparsers.add_parser("ask", help="delegate prompt injection/surfacing to pfc_harness.py")
    ask_parser.add_argument("prompt", help="prompt to inject")
    args = parser.parse_args(argv)

    if args.command == "load":
        return _load(args.model)
    if args.command == "connect":
        return _delegate("pfc_harness.py", "connect", [args.model])
    return _delegate("pfc_harness.py", "ask", [args.prompt])


if __name__ == "__main__":
    raise SystemExit(main())
