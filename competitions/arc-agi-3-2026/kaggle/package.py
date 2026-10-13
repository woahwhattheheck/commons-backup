"""Create a deterministic, no-network SAGE source bundle and notebook."""
from __future__ import annotations

import ast
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
from typing import Iterable

NETWORK_IMPORTS = frozenset({"requests", "httpx", "urllib", "socket", "aiohttp", "websockets"})
SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*=\s*['\"][^'\"]{8,}['\"]"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
)
EXCLUDED_DIRS = frozenset({"__pycache__", ".git", "evaluation", "kaggle", "tests"})


def _sha(path: Path) -> str:
    h = sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def discover_source(root: Path) -> tuple[Path, ...]:
    rows = []
    for path in root.rglob("*.py"):
        rel = path.relative_to(root)
        if any(part in EXCLUDED_DIRS for part in rel.parts):
            continue
        rows.append(rel)
    if not rows:
        raise ValueError("no Python source discovered")
    return tuple(sorted(rows, key=lambda p: p.as_posix()))


def scan_python(path: Path) -> tuple[str, ...]:
    text = path.read_text(encoding="utf-8")
    findings: list[str] = []
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        return (f"SYNTAX:{exc.lineno}:{exc.msg}",)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in NETWORK_IMPORTS:
                    findings.append(f"NETWORK_IMPORT:{alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in NETWORK_IMPORTS:
                findings.append(f"NETWORK_IMPORT:{node.module}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
            findings.append(f"DYNAMIC_EXEC:{node.func.id}")
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            findings.append("SECRET_PATTERN")
    return tuple(sorted(set(findings)))


def source_manifest(root: Path) -> dict[str, object]:
    root = root.resolve()
    files = discover_source(root)
    rows = []
    all_findings = []
    for rel in files:
        path = root / rel
        findings = scan_python(path)
        rows.append({"path": rel.as_posix(), "sha256": _sha(path), "bytes": path.stat().st_size, "findings": list(findings)})
        all_findings.extend(f"{rel}:{item}" for item in findings)
    manifest: dict[str, object] = {
        "schema": "arc3-sage-offline-source-manifest/v1",
        "files": rows,
        "network_or_secret_findings": sorted(all_findings),
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False)
    manifest["manifest_sha256"] = sha256(canonical.encode()).hexdigest()
    return manifest


def notebook_object() -> dict[str, object]:
    code = """from pathlib import Path\nimport runpy, sys\nROOT = Path.cwd() / 'src'\nsys.path.insert(0, str(ROOT))\nrunpy.run_path(str(ROOT / 'benchmark.py'), run_name='__main__')\n"""
    return {
        "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": ["# ARC3 SAGE offline benchmark\\n", "Generated deterministically; no network calls.\\n"]},
            {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": code.splitlines(keepends=True)},
        ],
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python", "version": "3"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def build_bundle(source_root: Path, output_dir: Path) -> dict[str, object]:
    source_root = source_root.resolve()
    output_dir = output_dir.resolve()
    if source_root == output_dir or source_root in output_dir.parents:
        # Output under source would make discovery self-referential on rerun.
        raise ValueError("output_dir must not be source_root or its descendant")
    manifest = source_manifest(source_root)
    if manifest["network_or_secret_findings"]:
        raise ValueError("source failed offline/secret scan")
    if output_dir.exists():
        shutil.rmtree(output_dir)
    (output_dir / "src").mkdir(parents=True)
    for row in manifest["files"]:
        rel = Path(row["path"])
        dest = output_dir / "src" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_root / rel, dest)
    (output_dir / "source_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    notebook = notebook_object()
    (output_dir / "offline_submission.ipynb").write_text(json.dumps(notebook, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return manifest
