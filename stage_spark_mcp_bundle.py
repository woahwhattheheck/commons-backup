#!/usr/bin/env python3
"""Stage the Commons MCP runtime graph for Vercel Hobby deploys.

Vercel CLI 56.1.0 does not honor directory un-ignores in .vercelignore after
a catch-all deny. Runs 33218271833 and 33219467177 each uploaded 7 root files
and failed: api/mcp.py did not match any Serverless Function. Copy the runtime
graph into a small directory and deploy from there instead of the whole repo.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

HOBBY_UPLOAD_CAP = 5000

RUNTIME_FILES = (
    "api/mcp.py",
    "api/owner_context.py",
    "api/jev.py",
    "api/cua_s1.py",
    "api/cua_s1_form.mjs",
    "api/cua_s1_fixture.mjs",
    "commons_mcp.py",
    "commons_publication_policy.py",
    "commons_mcp_app.html",
    "webmcp.html",
    "model_language.py",
    "relay_manifest.py",
    "relay-manifest.json",  # imported at module load; missing => FUNCTION_INVOCATION_FAILED
    "owner_enroll.py",
    "owner_net.py",
    "host/observatory.py",
    "host/owner_context.py",
    "host/jev.py",
    "host/cua_s1_cloud/__init__.py",
    "host/cua_s1_cloud/runtime_onnx.py",
    "host/cua_s1_cloud/cua-s1-forms.onnx",
    "hub_pages.py",  # static import from host/observatory.py
    "memory_board.py",  # continue_from_observation session-memory opt-in
    "vercel.json",
    "requirements.txt",
    "package.json",
    "package-lock.json",
)

RUNTIME_TREES = (
    "carriers",
    "harnesses",
    "protocol",
    "integrations/grokcom_revenue",
)


def stage_bundle(src: Path, dst: Path) -> list[str]:
    src = src.resolve()
    dst = dst.resolve()
    dst.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for rel in RUNTIME_FILES:
        source = src / rel
        if not source.is_file():
            raise FileNotFoundError("missing runtime file %s" % rel)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(rel)
    for tree in RUNTIME_TREES:
        source = src / tree
        if not source.is_dir():
            raise FileNotFoundError("missing runtime tree %s" % tree)
        target = dst / tree
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for path in target.rglob("*"):
            if path.is_file():
                copied.append(str(path.relative_to(dst)).replace("\\", "/"))
    copied.sort()
    if len(copied) >= HOBBY_UPLOAD_CAP:
        raise RuntimeError(
            "staged %s files; Hobby api-upload-free cap is %s" % (len(copied), HOBBY_UPLOAD_CAP)
        )
    return copied


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", default=".", help="repository root")
    parser.add_argument("--dst", required=True, help="empty-or-new staging directory")
    args = parser.parse_args(argv)
    copied = stage_bundle(Path(args.src), Path(args.dst))
    print("staged", len(copied), "files")
    print("includes_api_mcp", "api/mcp.py" in copied)
    return 0


if __name__ == "__main__":
    sys.exit(main())
