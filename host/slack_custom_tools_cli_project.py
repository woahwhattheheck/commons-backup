#!/usr/bin/env python3
"""Slack CLI project for Commons Service Tools (apps.manifest.create leftover).

Peer worker `host/slack_service_tag_worker.py` is the HTTP poller. This module
is the complementary Slack CLI *project*: `.slack/hooks.json`, get-manifest,
and start so `slack manifest validate` / `slack app install` / `slack run`
work after Bryce completes the `#needs-bryce` CLI challenge.

Does not remint cursor-slack-custom-tools-install-20260902-01.
Does not steal the service-tag catalog, worker, or GHA workflow.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PROJECT_DIR = ROOT / "host" / "slack_custom_tools_cli"
SOURCE_MANIFEST = ROOT / "host" / "slack_custom_tools_manifest.json"
SIGNIN_CHANNEL_ID = "C0BRX6EV739"
ORG_GRANT = "--org-workspace-grant=all"

HOOKS = {
    "hooks": {
        "get-manifest": "python3 get_manifest.py",
        "start": "python3 start.py",
    },
    "config": {
        "watch": {
            "manifest": {"paths": ["manifest.json"]},
            "app": {"filter-regex": "\\.py$", "paths": ["."]},
        }
    },
}

GITIGNORE = "\n".join(
    [
        "apps.json",
        "apps.dev.json",
        "credentials.json",
        "cache/",
        "",
    ]
)

CONFIG = {
    "project-id": "commons-service-tools",
    "manifest": {"source": "local"},
}


def project_dir(dest: Path | None = None) -> Path:
    return dest if dest is not None else PROJECT_DIR


def manifest_validate_argv(cli: str) -> list[str]:
    return [cli, "manifest", "validate", "--source", "local"]


def app_install_argv(cli: str) -> list[str]:
    """Slack CLI wraps apps.manifest.create during install after login."""
    return [cli, "app", "install", ORG_GRANT]


def run_argv(cli: str) -> list[str]:
    return [cli, "run", ORG_GRANT]


def after_login_argv(cli: str) -> list[list[str]]:
    return [manifest_validate_argv(cli), app_install_argv(cli), run_argv(cli)]


def _copy_manifest(dest_root: Path) -> Path:
    target = dest_root / "manifest.json"
    if SOURCE_MANIFEST.is_file():
        shutil.copyfile(SOURCE_MANIFEST, target)
        return target
    try:
        from slack_custom_tools_install import build_manifest
    except ImportError:
        import sys

        sys.path.insert(0, str(ROOT / "host"))
        from slack_custom_tools_install import build_manifest  # type: ignore
    payload = build_manifest()
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return target


def write_project(dest: Path | None = None) -> Path:
    """Materialize the Slack CLI project. Idempotent. Never writes tokens."""
    root = project_dir(dest)
    slack_dir = root / ".slack"
    slack_dir.mkdir(parents=True, exist_ok=True)
    (slack_dir / "hooks.json").write_text(
        json.dumps(HOOKS, indent=2) + "\n", encoding="utf-8"
    )
    (slack_dir / "config.json").write_text(
        json.dumps(CONFIG, indent=2) + "\n", encoding="utf-8"
    )
    (slack_dir / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
    src_get = PROJECT_DIR / "get_manifest.py"
    src_start = PROJECT_DIR / "start.py"
    if dest is not None:
        if src_get.is_file():
            shutil.copyfile(src_get, root / "get_manifest.py")
        if src_start.is_file():
            shutil.copyfile(src_start, root / "start.py")
    _copy_manifest(root)
    return root


def project_ready(dest: Path | None = None) -> bool:
    root = project_dir(dest)
    needed = [
        root / ".slack" / "hooks.json",
        root / "get_manifest.py",
        root / "start.py",
        root / "manifest.json",
    ]
    return all(path.is_file() for path in needed)


def status(dest: Path | None = None, home: str | None = None) -> dict[str, Any]:
    import slack_custom_tools_install as inst

    cli_status = inst.status(home=home)
    ready = project_ready(dest)
    logged_in = bool(cli_status.get("logged_in"))
    out: dict[str, Any] = {
        "id": "cursor-slack-custom-tools-cli-project-20260902-01",
        "project_dir": str(project_dir(dest)),
        "project_ready": ready,
        "cli_installed": bool(cli_status.get("installed")),
        "logged_in": logged_in,
        "needs_owner_signin": not logged_in,
        "signin_channel_id": SIGNIN_CHANNEL_ID,
        "signin_channel": "#needs-bryce",
        "commons_admission": False,
        "wraps": "apps.manifest.create",
        "after_login": [
            "slack manifest validate --source local",
            "slack app install --org-workspace-grant=all",
            "slack run --org-workspace-grant=all",
        ],
        "not_stolen": [
            "host/slack_service_tag_worker.py",
            "host/slack_service_tag.py",
            "ground/SLACK_SERVICE_TAGS.json",
            ".github/workflows/slack-service-tags.yml",
        ],
    }
    cli = cli_status.get("cli")
    if cli:
        out["after_login_argv"] = after_login_argv(str(cli))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--write-project", action="store_true")
    args = parser.parse_args(argv)
    if args.write_project:
        path = write_project()
        print(str(path))
        return 0
    payload = status()
    print(json.dumps(payload, indent=2))
    return 0 if payload.get("project_ready") else 2


if __name__ == "__main__":
    raise SystemExit(main())
