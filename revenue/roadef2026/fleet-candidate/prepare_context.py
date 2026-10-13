#!/usr/bin/env python3
"""Build-time only: verify four immutable source archives and stage a fresh context.

No cloning, installation, compilation, runtime networking, or publication occurs.
Only the known source families needed by these solvers/checker are extracted.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import time
import urllib.error
import urllib.request
import zipfile


ARCHIVES = {
    "sedge": {
        "file": "sedge-source.zip",
        "url": "https://raw.githubusercontent.com/woahwhattheheck/commons/c7c8679bb0330c932413e85f8f0646b30501cf07/revenue/roadef2026/sedge/source.zip",
        "sha256": "c93e8809fb01bcec48bc1b02444325cb17d9ad46034e8678ebca0a025c79bd2f",
        "main": "sedge-roadef-solver/main.cpp"},
    "flora": {
        "file": "flora-source.zip",
        "url": "https://raw.githubusercontent.com/woahwhattheheck/commons/fe4b29a3a2e08f251e5cd07e075d27279d154907/revenue/roadef2026/cloud-optimizer/source.zip",
        "sha256": "3673e77cdd8ab5a5c89cc12f81d9b0dbbccd7a237d30097dd061ab443f96db8b",
        "main": "cloud-optimizer/main.cpp"},
    "checker": {
        "file": "official.zip",
        "url": "https://gitlab.com/api/v4/projects/Orange-OpenSource%2Fnetwork-optimization-tools%2Fchallenge-roadef-2026/repository/archive.zip?sha=d84d319a7fdb8de3b1866830d2eaa2937871e5ae",
        "sha256": "e03b9ebf266755097e236d880830631574f528b872e44b67dc45af4796bd5ca8",
        "main": "checker/src/main.cpp"},
    "networktools": {
        "file": "networktools.zip",
        "url": "https://gitlab.com/api/v4/projects/Orange-OpenSource%2Fnetwork-optimization-tools%2Fnetworktools/repository/archive.zip?sha=aebafc9ee91891e5d721bb86725e8cf1533877d1",
        "sha256": "0e35f270bf100592e824c9a6ad0356eeee56cc40b594c04df7513e54148f9247",
        "main": "networktools/networktools.h"},
}
SOURCE_SUFFIXES = {".h", ".hpp", ".cpp", ".c"}
# Sparsehash deliberately ships these public C++ headers without extensions.
SPARSEHASH_HEADERS = {"dense_hash_map", "dense_hash_set", "sparse_hash_map",
                      "sparse_hash_set", "sparsetable", "traits"}


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_verified(spec, directory, archive_dir):
    target = directory / spec["file"]
    if archive_dir is not None:
        # An optional existing archive folder supports fully offline build prep.
        source = archive_dir / spec["file"]
        if sha256(source) != spec["sha256"]:
            raise ValueError(f"SHA-256 mismatch: {source}")
        shutil.copyfile(source, target)
    else:
        for attempt in range(3):
            try:
                request = urllib.request.Request(spec["url"], headers={"User-Agent": "ROADEF-source-preparation/1"})
                with urllib.request.urlopen(request, timeout=60) as response, target.open("wb") as output:
                    if not response.geturl().startswith("https://"):
                        raise ValueError("Source download redirected away from HTTPS")
                    shutil.copyfileobj(response, output, 1024 * 1024)
                break
            except (urllib.error.URLError, TimeoutError, OSError):
                target.unlink(missing_ok=True)
                if attempt == 2:
                    raise
                time.sleep(attempt + 1)
    if sha256(target) != spec["sha256"]:
        target.unlink(missing_ok=True)
        raise ValueError(f"Pinned archive hash mismatch for {spec['file']}; no substitute source accepted")
    return target


def member_path(info):
    name = info.filename
    path = PurePosixPath(name)
    normalized = name.lower().replace("_", "-")
    if (path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name or
            any(part in ("", ".") for part in path.parts)):
        raise ValueError(f"Unsafe ZIP member path: {name}")
    if "llama.cpp" in normalized or "llama-cpp" in normalized:
        raise ValueError("Archive contains a prohibited dependency family")
    if stat.S_ISLNK(info.external_attr >> 16):
        raise ValueError(f"ZIP symbolic links are not accepted: {name}")
    return path


def archive_members(archive, spec):
    infos = archive.infolist()
    seen = set()
    for info in infos:
        path = member_path(info)
        if info.is_dir():
            continue
        if path in seen:
            raise ValueError(f"Duplicate ZIP member: {path}")
        seen.add(path)
    marker = PurePosixPath(spec["main"])
    matches = [path for path in seen if path == marker or str(path).endswith("/" + str(marker))]
    if len(matches) != 1:
        raise ValueError(f"Expected one source marker {marker}; found {len(matches)}")
    matched = matches[0]
    if spec["main"] in ("sedge-roadef-solver/main.cpp", "cloud-optimizer/main.cpp"):
        prefix = matched.parent
    else:
        prefix = PurePosixPath(*matched.parts[:-len(marker.parts)])
    for info in infos:
        if info.is_dir():
            continue
        path = member_path(info)
        if not path.is_relative_to(prefix):
            raise ValueError("Pinned archive contains files outside its single project root")
        yield info, path.relative_to(prefix)


def copy_archive_sources(archive_path, name, spec, destination):
    with zipfile.ZipFile(archive_path) as archive:
        for info, relative in archive_members(archive, spec):
            parts = relative.parts
            target = None
            if name in ("sedge", "flora"):
                if str(relative) == "main.cpp" or (name == "sedge" and parts[0] == "vendor"):
                    target = destination / "sources" / name / relative
                elif str(relative) == "LICENSE":
                    target = destination / "attribution" / (name.upper() + "-LICENSE")
            elif name == "checker":
                if parts[:2] == ("checker", "src") and relative.suffix.lower() in SOURCE_SUFFIXES:
                    target = destination / "sources" / "checker" / Path(*parts[1:])
                elif str(relative) == "LICENSE":
                    target = destination / "attribution" / "Orange-checker-LICENSE"
            elif name == "networktools":
                sparsehash_header = (parts[:3] == ("networktools", "@deps", "sparsehash") and
                                     len(parts) == 4 and relative.name in SPARSEHASH_HEADERS)
                if parts[0] == "networktools" and (relative.suffix.lower() in SOURCE_SUFFIXES or
                                                   sparsehash_header):
                    target = destination / "sources" / "networktools" / relative
                elif str(relative) == "LICENSE":
                    target = destination / "attribution" / "Orange-networktools-LICENSE"
                elif (parts[:2] == ("networktools", "@deps") and
                      ("license" in relative.name.lower() or "copying" in relative.name.lower())):
                    target = destination / "attribution" / "networktools-dependencies" / Path(*parts[2:])
            if target is not None:
                if not target.resolve().is_relative_to(destination.resolve()):
                    raise ValueError("Resolved ZIP target escaped context")
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)


def prepare(destination, runtime_root, candidate, archive_dir=None):
    if destination.exists():
        raise ValueError("Choose a fresh build context; existing paths are never overwritten")
    candidate = candidate.resolve(strict=True)
    required = ("run.sh", "supervisor.py", "compare_checker.py", "build.sh", "Dockerfile", "README.md", "ATTRIBUTION.md")
    for name in required:
        (runtime_root / name).resolve(strict=True)
    # Verify all four archive byte identities before creating the context.
    with tempfile.TemporaryDirectory(prefix="roadef-source-prep-") as scratch:
        scratch = Path(scratch)
        archives = {name: fetch_verified(spec, scratch, archive_dir) for name, spec in ARCHIVES.items()}
        # Validate every member name and unique project marker before extraction.
        for name, archive_path in archives.items():
            with zipfile.ZipFile(archive_path) as archive:
                list(archive_members(archive, ARCHIVES[name]))
        destination.mkdir(parents=True)
        # mkdir above is the exclusive claim: never clean an existing context
        # or a competing creator's path when that claim fails. After it succeeds,
        # roll back our own partial tree on any catchable staging failure.
        try:
            for name, archive_path in archives.items():
                copy_archive_sources(archive_path, name, ARCHIVES[name], destination)
            for name in required:
                target = destination / ("attribution/ATTRIBUTION.md" if name == "ATTRIBUTION.md" else name)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(runtime_root / name, target)
            if (runtime_root / ".dockerignore").is_file():
                shutil.copyfile(runtime_root / ".dockerignore", destination / ".dockerignore")
            target = destination / "sources" / "candidate" / "main.cpp"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(candidate, target)
            shutil.copyfile(destination / "sources/sedge/vendor/rapidjson-LICENSE",
                            destination / "attribution/RapidJSON-LICENSE")
            for required_source in ("sources/sedge/main.cpp", "sources/flora/main.cpp", "sources/candidate/main.cpp",
                                    "sources/checker/src/main.cpp", "sources/checker/src/CLI11.hpp",
                                    "sources/networktools/networktools/networktools.h"):
                if not (destination / required_source).is_file():
                    raise ValueError(f"Missing required staged source: {required_source}")
            manifest = {"stage_version": 2, "submitted": False,
                        "archives": {name: {"url": spec["url"], "sha256": spec["sha256"]} for name, spec in ARCHIVES.items()},
                        "files": [{"path": path.relative_to(destination).as_posix(), "sha256": sha256(path)}
                                  for path in sorted(destination.rglob("*")) if path.is_file()]}
            (destination / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        except BaseException as error:
            try:
                shutil.rmtree(destination)
            except OSError as cleanup_error:
                # Keep the preparation failure primary and expose failed cleanup.
                raise error from cleanup_error
            raise

    return manifest


def main():
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("context"))
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--archive-dir", type=Path, help="Existing folder with the four pinned ZIP names; skip networking")
    args = parser.parse_args()
    candidate = args.candidate
    if candidate is None:
        options = [root / "main.cpp", root / "sources/candidate/main.cpp"]
        candidate = next((path for path in options if path.is_file()), None)
    if candidate is None:
        raise ValueError("Supply --candidate or place main.cpp beside this script")
    destination = args.output.resolve()
    manifest = prepare(destination, root, candidate, args.archive_dir.resolve() if args.archive_dir else None)
    print(json.dumps({"context": str(destination), "files": len(manifest["files"]),
                      "archive_hashes_verified": 4, "built": False, "submitted": False}))


if __name__ == "__main__":
    main()
