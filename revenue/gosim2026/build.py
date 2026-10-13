"""Build a real ARC agent bundle from exact HTTPS Git revisions; no inference.

Run on ephemeral cloud compute. No clones, vendored object stores or runtime
archives are created on the owner's PC. This script has no registration or
submission operation and does not fetch competition task data.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from pathlib import Path, PurePosixPath
import urllib.request
import zipfile

ARC_REPO = "code-philia/agentic-requirement-compiler"
ARC_COMMIT = "bf7b703d7e349834a1a16513f140aad55b790fe3"
TEMPLATE_REPO = "Weiyu-Kong/arc-template"
TEMPLATE_COMMIT = "e4ac841073726bf3e35552c6bc789c0f2f075098"
FORBIDDEN = re.compile(r"llama[._-]cpp|llama\.cpp|node-llama-cpp|llama-(?:cli|server|bench|quantize)", re.I)
FIXED_TIME = (2026, 9, 7, 0, 0, 0)


def fetch_source(repo: str, revision: str) -> dict[str, bytes]:
    url = f"https://codeload.github.com/{repo}/zip/{revision}"
    request = urllib.request.Request(url, headers={"User-Agent": "Commons-GOSIM-preparation"})
    with urllib.request.urlopen(request, timeout=90) as response:
        archive = response.read()
    result: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        for item in bundle.infolist():
            if item.is_dir():
                continue
            parts = PurePosixPath(item.filename).parts
            if len(parts) < 2 or ".." in parts or PurePosixPath(item.filename).is_absolute():
                raise ValueError("Invalid upstream archive path")
            name = str(PurePosixPath(*parts[1:]))
            if ((item.external_attr >> 16) & 0o170000) == 0o120000:
                raise ValueError("Unexpected symbolic link in upstream archive")
            if FORBIDDEN.search(name):
                raise ValueError("Prohibited upstream dependency path")
            result[name] = bundle.read(item)
    return result


def dependency_lines(data: bytes) -> list[str]:
    return [line.strip() for line in data.decode("utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def assemble(arc: dict[str, bytes], templates: dict[str, bytes],
             adapter: bytes, dependency_lock: bytes | None = None) -> dict[str, bytes]:
    entries = {name[4:]: data for name, data in arc.items() if name.startswith("src/")}
    if "main.py" not in entries or "requirements.txt" not in entries:
        raise ValueError("Pinned ARC source layout changed")
    for name, data in templates.items():
        entries["arc-template/" + name] = data
    for name, data in entries.items():
        if FORBIDDEN.search(name):
            raise ValueError("Prohibited source path")
        if name.endswith(("requirements.txt", "pyproject.toml", "package.json")):
            if FORBIDDEN.search(data.decode("utf-8")):
                raise ValueError("Prohibited dependency declaration")
    if dependency_lock is not None:
        if FORBIDDEN.search(dependency_lock.decode("utf-8")):
            raise ValueError("Prohibited locked dependency")
        entries["requirements.upstream.txt"] = entries["requirements.txt"]
        entries["requirements.txt"] = dependency_lock
    entries["arc_cli.py"] = entries.pop("main.py")
    entries["main.py"] = adapter
    entries["LICENSE-ARC"] = arc["LICENSE"]
    entries["NOTICE-COMMONS.txt"] = (
        f"ARC baseline: https://github.com/{ARC_REPO}/tree/{ARC_COMMIT}\n"
        f"Template gitlink: https://github.com/{TEMPLATE_REPO}/tree/{TEMPLATE_COMMIT}\n"
        "ARC MIT license is retained in LICENSE-ARC.\n"
        "Commons changes: fixed CLI adapter and runner model environment mapping.\n"
        "No qualifier solution, contest score or production run is represented by this package.\n"
    ).encode()
    validate_layout(entries)
    entries["BUILD-MANIFEST.json"] = (json.dumps({
        "schema": "commons-gosim-arc-bundle-v1",
        "arc_revision": ARC_COMMIT, "template_revision": TEMPLATE_COMMIT,
        "purpose": "generic_prequalifier_harness_preparation",
        "model_calls_during_build": 0,
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(entries.items())},
    }, indent=2, sort_keys=True) + "\n").encode()
    return entries


def validate_layout(entries: dict[str, bytes]) -> None:
    required = ("main.py", "arc_cli.py", "requirements.txt", "arc-template/catalog.yaml",
                "arcbench_agent_runtime/__init__.py", "core/workflow.py")
    absent = [name for name in required if name not in entries]
    if absent:
        raise ValueError("Incomplete runnable ARC bundle: " + ", ".join(absent))
    for name, data in entries.items():
        if name.endswith(".py"):
            compile(data, name, "exec")


def zip_bytes(entries: dict[str, bytes]) -> bytes:
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, data)
    return target.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    entries = assemble(fetch_source(ARC_REPO, ARC_COMMIT),
                       fetch_source(TEMPLATE_REPO, TEMPLATE_COMMIT),
                       Path(__file__).with_name("adapter.py").read_bytes(),
                       Path(__file__).with_name("requirements.resolved.txt").read_bytes())
    archive = zip_bytes(entries)
    # Do not overwrite an earlier candidate; each cloud job uses a new artifact.
    with args.output.open("xb") as handle:
        handle.write(archive)
    print(json.dumps({"archive": args.output.name, "files": len(entries),
                      "sha256": hashlib.sha256(archive).hexdigest(),
                      "arc_revision": ARC_COMMIT, "model_calls": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
