# SPDX-License-Identifier: MIT
"""Prepare an offline TITAN workspace from the existing v2 transport artifacts.

No network, candidate execution, notebook execution, compilation, or games.
The source snapshot is preserved; it is not a claim about current selection.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
import tempfile
import zipfile

SOURCE_TAR = "titan-reusable-sources.tar"
MANIFEST = "SOURCE-MANIFEST.json"
BASE = "revenue/kaggriculture/"
EVALUATOR = BASE + "cloud-eval/evaluate.py"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def relative_name(name: str) -> str:
    """Accept canonical relative file names, without archive traversal/aliases."""
    if (not isinstance(name, str) or not name or "\\" in name or "\0" in name
            or ":" in name or name.startswith("/")
            or any(part in ("", ".", "..") for part in name.split("/"))):
        raise ValueError(f"Noncanonical archive member: {name!r}")
    return str(PurePosixPath(name))


def checked(data: bytes, expected: dict, label: str, *, git: bool = False) -> bytes:
    if len(data) != expected["size_bytes"] or sha256(data) != expected["sha256"]:
        raise ValueError(f"Size or SHA-256 mismatch: {label}")
    if git and blob(data) != expected["git_blob"]:
        raise ValueError(f"Git blob mismatch: {label}")
    return data


def zip_members(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    entries = {}
    for item in archive.infolist():
        name = relative_name(item.filename.rstrip("/") if item.is_dir() else item.filename)
        if name in entries:
            raise ValueError(f"Duplicate ZIP member: {name}")
        entries[name] = item
    return entries


def source_members(data: bytes, expected: dict) -> dict[str, bytes]:
    """Read exact regular files; directory entries are structural, never links."""
    files, seen = {}, set()
    for name in expected:
        relative_name(name)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
        for item in archive:
            name = relative_name(item.name)
            if name in seen:
                raise ValueError(f"Duplicate TAR member: {name}")
            seen.add(name)
            if item.isdir():
                continue
            if not item.isfile() or name not in expected:
                raise ValueError(f"Unexpected/nonregular source member: {name}")
            if item.size != expected[name]["size_bytes"]:
                raise ValueError(f"Size mismatch: {name}")
            stream = archive.extractfile(item)
            if stream is None:
                raise ValueError(f"Unreadable source member: {name}")
            with stream:
                files[name] = checked(stream.read(), expected[name], name, git=True)
    if set(files) != set(expected):
        raise ValueError("Source member set differs from the manifest")
    return files


def engine_contract(source: bytes) -> tuple[str, dict[str, str]]:
    """Read the existing evaluator's literal pins without importing source code."""
    values = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ("ENGINE_REF", "ENGINE_BLOBS"):
                    values[target.id] = ast.literal_eval(node.value)
    return values["ENGINE_REF"], values["ENGINE_BLOBS"]


def prepare(sources_zip: Path, engine_zip: Path, output: Path,
            expected_source_sha256: str) -> dict:
    """Verify before writing and publish a new workspace; never overlay old work."""
    if not re.fullmatch(r"[0-9a-f]{64}", expected_source_sha256):
        raise ValueError("Expected the lowercase SHA-256 from the source artifact receipt")
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"Use a new output directory: {output}")
    source_raw = Path(sources_zip).read_bytes()
    if sha256(source_raw) != expected_source_sha256:
        raise ValueError("Source ZIP differs from the supplied artifact SHA-256")
    with zipfile.ZipFile(io.BytesIO(source_raw)) as archive:
        entries = zip_members(archive)
        manifest_raw = archive.read(entries[MANIFEST])
        manifest = json.loads(manifest_raw)
        if manifest["schema"] != "titan.pinned-source-export.v2":
            raise ValueError("Expected v2 transport with the complete file-loader closure")
        if not re.fullmatch(r"[0-9a-f]{40}", manifest["source_commit"]):
            raise ValueError("Expected an exact source commit")
        transported = {}
        for name, expected in manifest["archives"].items():
            relative_name(name)
            transported[name] = checked(archive.read(entries[name]), expected, name)
        files = source_members(transported[SOURCE_TAR], manifest["files"])
        reuse = archive.read(entries["REUSE.md"])
    engine_raw = checked(Path(engine_zip).read_bytes(), manifest["engine_artifact"], "engine ZIP")
    engine_ref, pins = engine_contract(files[EVALUATOR])
    if engine_ref != manifest["engine_artifact"]["engine_ref"]:
        raise ValueError("Engine ref differs between transport and evaluator")
    cache = relative_name(manifest["engine_artifact"]["cache_subdirectory"])
    engine_files = {}
    with zipfile.ZipFile(io.BytesIO(engine_raw)) as archive:
        entries = zip_members(archive)
        for name in (*pins, "LICENSE"):
            relative_name(name)
            data = archive.read(entries[f"{cache}/{name}"])
            if name in pins and blob(data) != pins[name]:
                raise ValueError(f"Official engine blob mismatch: {name}")
            engine_files[name] = data
    paths = {
        "repository": "sources", "engine": "engine",
        "evaluator": "sources/" + EVALUATOR,
        "file_loader": "sources/" + BASE + "cloud-pack/official.py",
        "adapter_builder": "sources/" + BASE + "cloud-pack/pack.py",
        "arlene": "sources/" + BASE + "cloud-frontier-policy/next-panel/vendor/arlene.py",
        "apex_source": "sources/" + BASE + "cloud-frontier-policy/next-panel/vendor/apex",
        "snapshot_sell": "sources/" + BASE + "cloud-titan-composition/arms/sell.py",
    }
    for name in ("evaluator", "file_loader", "adapter_builder", "arlene", "snapshot_sell"):
        if paths[name].removeprefix("sources/") not in files:
            raise ValueError(f"Missing v2 consumer dependency: {name}")
    receipt = {
        "schema": "titan.offline-source-workspace.v1",
        "source_commit": manifest["source_commit"],
        "source_zip_sha256": sha256(source_raw), "engine_zip_sha256": sha256(engine_raw),
        "manifest_sha256": sha256(manifest_raw), "source_file_count": len(files),
        "engine_ref": engine_ref,
        "engine_files": {name: {"sha256": sha256(data), "git_blob": blob(data)}
                         for name, data in engine_files.items()},
        "paths_relative_to_workspace": paths,
        "candidate_executed": False, "apex_compiled": False, "games": 0,
        "selection_status": "Frozen transport snapshot, not current-main or selected-policy evidence",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="titan-bootstrap-", dir=output.parent) as staging:
        workspace = Path(staging) / "workspace"
        for name, data in files.items():
            target = workspace / "sources" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        for name, data in engine_files.items():
            target = workspace / "engine" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        transport = workspace / "transport"
        transport.mkdir()
        (transport / MANIFEST).write_bytes(manifest_raw)
        (transport / "REUSE.md").write_bytes(reuse)
        for name, data in transported.items():
            if name != SOURCE_TAR:  # Preserve optional checkpoint archives without unpacking/executing.
                target = transport / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        (workspace / "workspace.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        if output.exists() or output.is_symlink():
            raise FileExistsError(f"Output appeared during preparation: {output}")
        workspace.rename(output)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources-zip", type=Path, required=True)
    parser.add_argument("--source-sha256", required=True, help="Expected digest from the source artifact receipt")
    parser.add_argument("--engine-zip", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New isolated cloud workspace directory")
    args = parser.parse_args()
    try:
        receipt = prepare(args.sources_zip, args.engine_zip, args.output, args.source_sha256)
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError, zipfile.BadZipFile) as exc:
        parser.exit(2, f"bootstrap: {exc}\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
