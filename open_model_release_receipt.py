#!/usr/bin/env python3
"""Verify a bounded open-model release manifest and emit durable receipts."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


EXPECTED_ARTIFACTS = {
    "weights",
    "config",
    "tokenizer",
    "loader_ref",
    "data_provenance",
    "license",
    "evaluation",
    "sha256sums",
}
MAX_TOTAL_BYTES = 10 * 1024 * 1024
MAX_TIMEOUT_SECONDS = 60


class ManifestError(ValueError):
    """The manifest is outside the deliberately small trial contract."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_bounded(reference: str, base: Path, remaining: int) -> bytes:
    parsed = urllib.parse.urlparse(reference)
    if parsed.scheme in {"http", "https"}:
        request = urllib.request.Request(reference, headers={"User-Agent": "commons-release-receipt/1"})
        with urllib.request.urlopen(request, timeout=MAX_TIMEOUT_SECONDS) as response:
            data = response.read(remaining + 1)
    elif parsed.scheme:
        raise ManifestError(f"unsupported artifact scheme: {parsed.scheme}")
    else:
        path = (base / reference).resolve()
        try:
            path.relative_to(base.resolve())
        except ValueError as exc:
            raise ManifestError(f"artifact escapes manifest directory: {reference}") from exc
        with path.open("rb") as handle:
            data = handle.read(remaining + 1)
    if len(data) > remaining:
        raise ManifestError("artifact bytes exceed the 10 MiB trial limit")
    return data


def _load_manifest(path: Path) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 8:
        raise ManifestError("manifest must declare exactly eight artifacts")
    names = [row.get("name") for row in artifacts if isinstance(row, dict)]
    if len(names) != 8 or set(names) != EXPECTED_ARTIFACTS or len(set(names)) != 8:
        raise ManifestError("artifact names must match the eight-item release contract")
    for row in artifacts:
        if not isinstance(row.get("path"), str) or not row["path"]:
            raise ManifestError(f"artifact {row.get('name')!r} needs a path")
        digest = row.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ManifestError(f"artifact {row['name']!r} needs a SHA-256")
        try:
            int(digest, 16)
        except ValueError as exc:
            raise ManifestError(f"artifact {row['name']!r} has an invalid SHA-256") from exc
    loader = manifest.get("loader")
    if not isinstance(loader, dict) or not isinstance(loader.get("command"), list):
        raise ManifestError("loader.command must be an argument list")
    if not loader["command"] or not all(isinstance(part, str) and part for part in loader["command"]):
        raise ManifestError("loader.command must contain non-empty strings")
    timeout = loader.get("timeout_seconds", MAX_TIMEOUT_SECONDS)
    if not isinstance(timeout, int) or not 1 <= timeout <= MAX_TIMEOUT_SECONDS:
        raise ManifestError("loader timeout must be between 1 and 60 seconds")
    if not isinstance(manifest.get("release_id"), str) or not manifest["release_id"]:
        raise ManifestError("release_id is required")
    return manifest


def verify(manifest_path: str | Path) -> dict:
    path = Path(manifest_path).resolve()
    manifest = _load_manifest(path)
    rows = []
    remaining = MAX_TOTAL_BYTES
    for artifact in manifest["artifacts"]:
        actual = None
        size = None
        error = None
        try:
            data = _read_bounded(artifact["path"], path.parent, remaining)
            remaining -= len(data)
            size = len(data)
            actual = _sha256(data)
        except (OSError, urllib.error.URLError, ManifestError) as exc:
            error = f"{type(exc).__name__}: {exc}"
        passed = actual == artifact["sha256"] and error is None
        rows.append({
            "name": artifact["name"],
            "path": artifact["path"],
            "expected_sha256": artifact["sha256"],
            "actual_sha256": actual,
            "bytes": size,
            "passed": passed,
            "error": error,
        })

    loader = manifest["loader"]
    loader_cwd = (path.parent / loader.get("cwd", ".")).resolve()
    try:
        loader_cwd.relative_to(path.parent)
    except ValueError as exc:
        raise ManifestError("loader cwd escapes manifest directory") from exc
    try:
        completed = subprocess.run(
            loader["command"],
            cwd=loader_cwd,
            capture_output=True,
            text=True,
            timeout=loader.get("timeout_seconds", MAX_TIMEOUT_SECONDS),
            check=False,
        )
        loader_result = {
            "command": loader["command"],
            "exit_code": completed.returncode,
            "stdout": completed.stdout[-4096:],
            "stderr": completed.stderr[-4096:],
            "passed": completed.returncode == 0,
            "error": None,
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        loader_result = {
            "command": loader["command"],
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "passed": False,
            "error": f"{type(exc).__name__}: {exc}",
        }

    artifact_passes = sum(row["passed"] for row in rows)
    passed = artifact_passes == 8 and loader_result["passed"]
    return {
        "schema": "commons.open-model-release-receipt.v1",
        "release_id": manifest["release_id"],
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if passed else "FAIL",
        "artifact_passes": artifact_passes,
        "artifact_total": 8,
        "artifacts": rows,
        "loader": loader_result,
    }


def render_html(receipt: dict) -> str:
    rows = []
    for row in receipt["artifacts"]:
        rows.append(
            "<tr><td>{}</td><td>{}</td><td>{}</td><td><code>{}</code></td>"
            "<td><code>{}</code></td></tr>".format(
                html.escape(row["name"]),
                html.escape(row["path"]),
                "PASS" if row["passed"] else "FAIL",
                html.escape(row["expected_sha256"]),
                html.escape(row["actual_sha256"] or row["error"] or "unresolved"),
            )
        )
    status = receipt["status"]
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Open model release receipt</title><style>
body{{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#172033}}.artifact-table{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;min-width:48rem}}th,td{{border:1px solid #ccd3df;padding:.55rem;text-align:left;vertical-align:top}}code{{overflow-wrap:anywhere}}.PASS{{color:#067647}}.FAIL{{color:#b42318}}
</style></head><body><h1>Open model release receipt</h1>
<p>Release: <strong>{release}</strong></p><p>Verified: {time}</p>
<h2 class="{status}">{status} — {passes}/8 artifacts; loader {loader}</h2>
<div class="artifact-table" role="region" aria-label="Artifact verification results" tabindex="0"><table><thead><tr><th>Artifact</th><th>Reference</th><th>Gate</th><th>Expected SHA-256</th><th>Observed</th></tr></thead><tbody>{rows}</tbody></table></div>
<h2>Loader</h2><p>Exit code: <code>{exit_code}</code></p><pre>{stdout}</pre>
</body></html>""".format(
        release=html.escape(receipt["release_id"]), time=html.escape(receipt["verified_at"]),
        status=status, passes=receipt["artifact_passes"],
        loader="PASS" if receipt["loader"]["passed"] else "FAIL", rows="".join(rows),
        exit_code=html.escape(str(receipt["loader"]["exit_code"])),
        stdout=html.escape(receipt["loader"]["stdout"] or receipt["loader"]["error"] or ""),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="release-receipt")
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("manifest")
    verify_parser.add_argument("--json-out", default="receipt.json")
    verify_parser.add_argument("--html-out", default="receipt.html")
    args = parser.parse_args(argv)
    try:
        receipt = verify(args.manifest)
    except (OSError, json.JSONDecodeError, ManifestError) as exc:
        print(f"release-receipt: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    Path(args.json_out).write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    Path(args.html_out).write_text(render_html(receipt), encoding="utf-8")
    print(f"{receipt['status']} {receipt['artifact_passes']}/8 loader={'PASS' if receipt['loader']['passed'] else 'FAIL'}")
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
