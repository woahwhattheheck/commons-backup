#!/usr/bin/env python3
"""Build the ROADEF qualification ZIP in an ephemeral cloud workspace only.
This packages SEDGE's accepted solver. It never registers or emails an entry.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import urllib.request
import zipfile

SOURCE_COMMIT = "c7c8679bb0330c932413e85f8f0646b30501cf07"
SOURCE_SHA256 = "c93e8809fb01bcec48bc1b02444325cb17d9ad46034e8678ebca0a025c79bd2f"
PREFIX = "sedge-roadef-solver/"
BASE = "https://raw.githubusercontent.com/woahwhattheheck/commons"
REQUIRED = {"Dockerfile", "run.sh", "main.cpp", "Makefile", "LICENSE"}

def fetch(revision, path):
    with urllib.request.urlopen(f"{BASE}/{revision}/{path}", timeout=60) as response:
        return response.read()

def sha(data):
    return hashlib.sha256(data).hexdigest()

def zip_bytes(files):
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 9, 7, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (0o100755 if name == "run.sh" else 0o100644) << 16
            archive.writestr(info, data)
    return result.getvalue()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata-revision", required=True)
    parser.add_argument("--output", default="out")
    parser.add_argument("--team-id", default="")
    args = parser.parse_args()
    original = fetch(SOURCE_COMMIT, "revenue/roadef2026/sedge/source.zip")
    if sha(original) != SOURCE_SHA256:
        raise ValueError("The pinned SEDGE source archive differs from its delivery hash")
    files = {}
    with zipfile.ZipFile(io.BytesIO(original)) as archive:
        for item in archive.infolist():
            if item.is_dir():
                continue
            if not item.filename.startswith(PREFIX):
                raise ValueError(f"Unexpected enclosing directory: {item.filename}")
            name = item.filename[len(PREFIX):]
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or name in files:
                raise ValueError(f"Ambiguous archive path: {name}")
            files[name] = archive.read(item)
    if not REQUIRED.issubset(files) or "vendor/rapidjson/document.h" not in files:
        raise ValueError("Required implementation files are missing")
    runtime = {name: sha(data) for name, data in files.items()
               if name in REQUIRED or name.startswith("vendor/")}
    # Preserve every implementation and bundled-license byte. Only current
    # documentation/receipt copies replace their pre-container-status versions.
    for name in ("README.md", "method.pdf", "make_method.py", "CONTAINER-VALIDATION.json"):
        files[name] = fetch(args.metadata_revision, f"revenue/roadef2026/sedge/{name}")
    if not files["method.pdf"].startswith(b"%PDF-"):
        raise ValueError("Method is not a PDF")
    result = zip_bytes(files)
    assert result == zip_bytes(files), "Archive generation must be deterministic"
    with zipfile.ZipFile(io.BytesIO(result)) as check:
        assert set(check.namelist()) == set(files)
        for name, data in files.items():
            assert check.read(name) == data
        assert all(sha(check.read(name)) == digest for name, digest in runtime.items())
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    team_id = args.team_id.strip()
    if team_id and (PurePosixPath(team_id).name != team_id or "/" in team_id or "\\" in team_id):
        raise ValueError("Team ID must be the organizer ID, not a pathname")
    filename = f"{team_id}.zip" if team_id else "qualification-unregistered.zip"
    (output / filename).write_bytes(result)
    manifest = {
        "state": "PACKAGED_NOT_SUBMITTED",
        "team_id": team_id or None,
        "filename": filename,
        "sha256": sha(result),
        "bytes": len(result),
        "source_commit": SOURCE_COMMIT,
        "source_zip_sha256": SOURCE_SHA256,
        "metadata_revision": args.metadata_revision,
        "runtime_files_preserved": len(runtime),
        "runtime_sha256": runtime,
        "files": {name: {"bytes": len(data), "sha256": sha(data)} for name, data in sorted(files.items())},
        "qualification_deadline_utc": "2026-09-14T21:59:00Z",
        "registration_or_submission_sent": False,
        "accepted_execution_evidence": "https://github.com/woahwhattheheck/commons/actions/runs/34080604676",
        "tests": ["root build context", "all required files", "implementation byte identity",
                  "ZIP readback all members", "deterministic packaging"],
    }
    (output / "package-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({k: manifest[k] for k in ("state", "filename", "sha256", "bytes", "runtime_files_preserved", "tests")}))
if __name__ == "__main__":
    main()
