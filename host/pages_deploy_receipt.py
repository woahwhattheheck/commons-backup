#!/usr/bin/env python3
"""In-tree pages-deploy.json canary so github-pages[bot] cannot 404 the receipt.

pages-deploy.yml still writes `_site/pages-deploy.json` into the Actions
artifact. A later branch publish from `llms.txt`/`fresh.md` overwrites that
artifact with the git tree. If the receipt is only in `_site/`, live 404s.

This helper owns the committed canary at repo root. It does not write
`.github/workflows/pages-deploy.yml`, remint Fable, or flip Pages source.

Copy-filter language is rsync/tar exclude/keep, not admission.
Possessing the link stays authorization. No login.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "pages-deploy.json"
WORKFLOW = ROOT / ".github" / "workflows" / "pages-deploy.yml"
OVERWRITE_CITE = "cursor-pages-deploy-json-overwrite-20260902-01"
SOURCE = "in-tree-canary"
REQUIRED_KEYS = ("sha", "run_id", "excludes", "keeps", "source")
_SHA40 = re.compile(r"^[0-9a-f]{40}$")


def posix(path: str | Path) -> str:
    return str(path).replace("\\", "/").lstrip("./")


def load_receipt(root: Path | None = None) -> dict[str, Any]:
    here = Path(root) if root is not None else ROOT
    path = here / RECEIPT.name
    return json.loads(path.read_text(encoding="utf-8"))


def receipt_errors(payload: dict[str, Any]) -> tuple[str, ...]:
    errors: list[str] = []
    for key in REQUIRED_KEYS:
        if key not in payload:
            errors.append(f"missing:{key}")
    sha = str(payload.get("sha") or "")
    if sha and not _SHA40.match(sha):
        errors.append("sha_not_40_hex")
    if payload.get("source") != SOURCE:
        errors.append("source_not_in_tree_canary")
    if payload.get("survives_github_pages_bot_overwrite") is not True:
        errors.append("missing_overwrite_survive")
    if payload.get("owns_deploy_workflow") is True:
        errors.append("steals_deploy_workflow")
    if payload.get("gate") is True:
        errors.append("gate_true")
    if not isinstance(payload.get("excludes"), list):
        errors.append("excludes_not_list")
    if not isinstance(payload.get("keeps"), list):
        errors.append("keeps_not_list")
    keeps = payload.get("keeps") or []
    if isinstance(keeps, list):
        for must in ("chunks/", "action.html", "pay.html"):
            if must not in keeps:
                errors.append(f"keep_missing:{must}")
    return tuple(errors)


def in_tree(root: Path | None = None) -> bool:
    here = Path(root) if root is not None else ROOT
    return (here / RECEIPT.name).is_file()


def report(root: Path | None = None) -> dict[str, Any]:
    here = Path(root) if root is not None else ROOT
    path = here / RECEIPT.name
    payload: dict[str, Any] | None = None
    errors: tuple[str, ...] = ("missing_file",)
    if path.is_file():
        payload = json.loads(path.read_text(encoding="utf-8"))
        errors = receipt_errors(payload)
    return {
        "path": posix(RECEIPT.name),
        "in_tree": path.is_file(),
        "errors": list(errors),
        "cite": OVERWRITE_CITE,
        "source": SOURCE,
        "owns_deploy_workflow": False,
        "workflow_untouched": True,
        "pages_source_unflipped": True,
        "copy_filter_is_not_admission": True,
        "open_door": True,
        "gate": False,
        "sha": None if payload is None else payload.get("sha"),
        "run_id": None if payload is None else payload.get("run_id"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the in-tree pages-deploy.json canary."
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    payload = report(args.root)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if not payload["errors"] else 1
    if payload["errors"]:
        print("pages-deploy.json errors: " + ", ".join(payload["errors"]))
        return 1
    print(payload["path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
