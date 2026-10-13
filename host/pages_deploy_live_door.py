#!/usr/bin/env python3
"""Measure live Pages deploy receipt door vs in-tree canary.

Copy-filter / bake language only. Possessing the link stays authorization.
No login. Does not dispatch Actions. Does not cancel runs.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IN_TREE = ROOT / "pages-deploy.json"
LIVE_URL = "https://woahwhattheheck.github.io/commons/pages-deploy.json"
RAW_URL = (
    "https://raw.githubusercontent.com/woahwhattheheck/commons/main/pages-deploy.json"
)


def http_status(url: str, timeout: float = 20.0) -> int:
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status)
    except urllib.error.HTTPError as err:
        return int(err.code)


def measure(root: Path | None = None) -> dict[str, object]:
    here = Path(root) if root is not None else ROOT
    in_tree = here / IN_TREE.name
    payload: dict[str, object] = {
        "in_tree_present": in_tree.is_file(),
        "live_url": LIVE_URL,
        "raw_main_url": RAW_URL,
        "gate": False,
        "open_door": True,
        "owns_deploy_workflow": False,
    }
    if in_tree.is_file():
        body = json.loads(in_tree.read_text(encoding="utf-8"))
        payload["in_tree_source"] = body.get("source")
        payload["in_tree_sha"] = body.get("sha")
    return payload


def main() -> int:
    print(json.dumps(measure(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
