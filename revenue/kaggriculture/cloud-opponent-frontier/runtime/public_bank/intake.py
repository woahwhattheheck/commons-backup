"""Fetch the exact T07 public opponent inputs; this command never imports them."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

SOURCES = {
    "lonespear-v18": {
        "repository": "lonespear/kaggriculture",
        "commit": "774b26093ccf4246525517d48420349b841b6e50",
        "entry": "main_v18.py",
        "license": "MIT",
        "files": {
            "main_v18.py": "23a5a70b04af9f1e2be2832ee8da58a9df6d6caa",
            "LICENSE": "b1f248dfe587c8643650af8c6155c8554d44fcd8",
        },
    },
    "cok-v10": {
        "repository": "COK-ZhangZiliang/Kaggriculture",
        "commit": "7ef67eac458cd9ecd13786063e2e581fbe7403ec",
        "entry": "main.py",
        "license": "Apache-2.0; retain upstream third-party notice and its scope",
        "files": {
            "main.py": "736577e3810f018f1844b8ac9824a4e69b4c37d3",
            "LICENSE": None,
            "LICENSES/Apache-2.0.txt": None,
            "THIRD_PARTY_NOTICES.md": "c7fc3d432c83bf207e84af54b3da9521d69df3c2",
        },
    },
}
MAX_BYTES = 4 * 1024 * 1024


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def fetch(destination: Path) -> dict:
    """Write pinned public bytes and provenance into a new output directory."""
    destination.mkdir(parents=True, exist_ok=False)
    manifest = {"schema": "titan.public-opponent-bank.v1", "executes_downloaded_code": False,
                "opponents": {}}
    for name, source in SOURCES.items():
        row = {k: v for k, v in source.items() if k != "files"}
        row["files"] = {}
        for filename, expected_blob in source["files"].items():
            url = f"https://raw.githubusercontent.com/{source['repository']}/{source['commit']}/{filename}"
            request = urllib.request.Request(url, headers={"User-Agent": "commons-titan-public-bank/1.0"})
            with urllib.request.urlopen(request, timeout=35) as response:
                data = response.read(MAX_BYTES + 1)
                status = response.status
            if len(data) > MAX_BYTES:
                raise ValueError(f"Oversized public source: {name}/{filename}")
            blob = git_blob(data)
            if expected_blob is not None and blob != expected_blob:
                raise ValueError(f"Pinned source changed: {name}/{filename}")
            path = destination / name / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            row["files"][filename] = {"sha256": digest(data), "git_blob": blob,
                                       "bytes": len(data), "source_url": url, "http_status": status}
        manifest["opponents"][name] = row
    (destination / "SOURCES.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def verify(directory: Path) -> dict:
    """Check artifact byte integrity offline; source licensing is recorded, not inferred."""
    manifest = json.loads((directory / "SOURCES.json").read_text(encoding="utf-8"))
    if manifest["schema"] != "titan.public-opponent-bank.v1":
        raise ValueError("Unknown public-bank manifest schema")
    if set(manifest["opponents"]) != set(SOURCES):
        raise ValueError("Opponent manifest differs from the frozen bank")
    for name, source in SOURCES.items():
        row = manifest["opponents"][name]
        if any(row[key] != source[key] for key in ("repository", "commit", "entry", "license")):
            raise ValueError(f"Source metadata changed: {name}")
        if set(row["files"]) != set(source["files"]):
            raise ValueError(f"Source closure changed: {name}")
        for filename, expected in source["files"].items():
            data = (directory / name / filename).read_bytes()
            entry = row["files"][filename]
            if len(data) != entry["bytes"] or digest(data) != entry["sha256"]:
                raise ValueError(f"Source bytes changed: {name}/{filename}")
            blob = git_blob(data)
            if blob != entry["git_blob"] or (expected is not None and blob != expected):
                raise ValueError(f"Source blob changed: {name}/{filename}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("fetch", "verify"))
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    result = fetch(args.directory) if args.command == "fetch" else verify(args.directory)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
