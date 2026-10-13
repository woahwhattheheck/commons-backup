# SPDX-License-Identifier: Apache-2.0
"""Archive, source, and engine helpers for unit-capacity occurrence analysis."""
from __future__ import annotations

import ast
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import random
import sys
import tempfile
import types
from typing import Any, Callable, Mapping
import zipfile

EXPECTED_ARCHIVE_SHA256 = (
    "aaa2d811a919b6b1c2219082753cfe476a0a0fac7567d3ad1d72c9f373a912f9"
)
MANIFEST_SCHEMA = "titan.delve.funding-evidence.v1"
RESULT_SCHEMA = "titan.unit-capacity-occurrence.v1"
ENGINE_MEMBERS = (
    "engine/engine/kaggriculture.py",
    "engine/engine/kaggriculture.json",
    "engine/engine/utils.py",
)
MAX_MEMBER_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024


class Struct(dict):
    """Small attribute-access mapping matching the existing offline evaluators."""

    def __getattr__(self, key: str) -> Any:
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key) from None

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value


def structify(value: Any) -> Any:
    if isinstance(value, dict):
        return Struct({key: structify(item) for key, item in value.items()})
    if isinstance(value, list):
        return [structify(item) for item in value]
    return value


def plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [plain(item) for item in value]
    return value


def encoded(value: Any) -> bytes:
    return json.dumps(
        plain(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def parse_object(data: bytes, name: str) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=unique_object)
    except (UnicodeError, ValueError) as exc:
        raise ValueError(f"invalid JSON object {name}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {name}")
    return value


def read_verified_archive(
    archive_path: Path, expected_archive_sha256: str
) -> tuple[dict[str, bytes], dict[str, Any]]:
    raw_archive = archive_path.read_bytes()
    archive_digest = sha256(raw_archive)
    if archive_digest != expected_archive_sha256.lower():
        raise ValueError(
            "evidence archive SHA-256 mismatch: "
            f"expected {expected_archive_sha256}, got {archive_digest}"
        )
    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            if sum(info.file_size for info in infos) > MAX_TOTAL_BYTES:
                raise ValueError("evidence archive exceeds 32 MiB uncompressed")
            members: dict[str, bytes] = {}
            for info in infos:
                path = PurePosixPath(info.filename)
                if path.is_absolute() or ".." in path.parts or "\\" in info.filename:
                    raise ValueError(f"ambiguous archive member path: {info.filename}")
                if info.filename in members:
                    raise ValueError(f"duplicate archive member: {info.filename}")
                if info.file_size > MAX_MEMBER_BYTES:
                    raise ValueError(f"archive member exceeds 8 MiB: {info.filename}")
                members[info.filename] = archive.read(info)
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise ValueError(f"cannot read evidence ZIP: {exc}") from exc

    manifest = parse_object(members.get("MANIFEST.json", b""), "MANIFEST.json")
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError("unexpected evidence manifest schema")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError("manifest files is not an object")
    expected_names = set(files) | {"MANIFEST.json"}
    if set(members) != expected_names:
        missing = sorted(expected_names - set(members))
        extra = sorted(set(members) - expected_names)
        raise ValueError(f"archive/manifest member mismatch; missing={missing}, extra={extra}")
    for name, row in files.items():
        if not isinstance(row, dict):
            raise ValueError(f"invalid manifest row: {name}")
        data = members[name]
        if row.get("bytes") != len(data) or row.get("sha256") != sha256(data):
            raise ValueError(f"manifest identity mismatch: {name}")
    for name in ENGINE_MEMBERS:
        if name not in members:
            raise ValueError(f"missing pinned engine member: {name}")
    return members, {
        "archive_sha256": archive_digest,
        "archive_bytes": len(raw_archive),
        "manifest_sha256": sha256(members["MANIFEST.json"]),
        "manifested_files": len(files),
        "engine_sha256": {
            PurePosixPath(name).name: sha256(members[name]) for name in ENGINE_MEMBERS
        },
    }


def load_engine(members: Mapping[str, bytes], module_name: str) -> Any:
    """Compile the captured engine bytes; never delegate to a source loader/pyc."""
    utils_bytes = members[ENGINE_MEMBERS[2]]
    tree = ast.parse(utils_bytes, filename=ENGINE_MEMBERS[2])
    helper = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "resolve_episode_seed"
    )
    namespace: dict[str, Any] = {
        "Any": Any,
        "Callable": Callable,
        "random": random,
    }
    exec(
        compile(ast.Module(body=[helper], type_ignores=[]), ENGINE_MEMBERS[2], "exec"),
        namespace,
    )

    previous_package = sys.modules.get("kaggle_environments")
    previous_utils = sys.modules.get("kaggle_environments.utils")
    package = types.ModuleType("kaggle_environments")
    utils = types.ModuleType("kaggle_environments.utils")
    utils.resolve_episode_seed = namespace["resolve_episode_seed"]
    sys.modules["kaggle_environments"] = package
    sys.modules["kaggle_environments.utils"] = utils
    try:
        with tempfile.TemporaryDirectory(prefix="titan-capacity-engine-") as directory:
            root = Path(directory)
            engine_path = root / "kaggriculture.py"
            spec_path = root / "kaggriculture.json"
            engine_path.write_bytes(members[ENGINE_MEMBERS[0]])
            spec_path.write_bytes(members[ENGINE_MEMBERS[1]])
            module = types.ModuleType(module_name)
            module.__file__ = str(engine_path)
            sys.modules[module_name] = module
            try:
                exec(
                    compile(members[ENGINE_MEMBERS[0]], str(engine_path), "exec"),
                    module.__dict__,
                )
            except BaseException:
                sys.modules.pop(module_name, None)
                raise
            return module
    finally:
        if previous_package is None:
            sys.modules.pop("kaggle_environments", None)
        else:
            sys.modules["kaggle_environments"] = previous_package
        if previous_utils is None:
            sys.modules.pop("kaggle_environments.utils", None)
        else:
            sys.modules["kaggle_environments.utils"] = previous_utils


def decoded_frame_rows(payload: bytes, name: str) -> tuple[list[dict[str, Any]], bytes]:
    try:
        decoded = gzip.decompress(payload)
    except (OSError, EOFError) as exc:
        raise ValueError(f"incomplete frame gzip: {name}: {exc}") from exc
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(decoded.splitlines()):
        rows.append(parse_object(line, f"{name}:{index + 1}"))
    if not rows:
        raise ValueError(f"empty frame stream: {name}")
    return rows, decoded


def discover_complete_streams(members: Mapping[str, bytes]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int], dict[str, Any]] = {}
    for frame_name in sorted(name for name in members if name.endswith(".frames.jsonl.gz")):
        result_name = frame_name.removesuffix(".frames.jsonl.gz") + ".json"
        if result_name not in members:
            continue
        result = parse_object(members[result_name], result_name)
        if result.get("status") != "complete":
            continue
        seat = result.get("candidate_seat")
        if type(seat) is not int or seat not in (0, 1):
            raise ValueError(f"invalid candidate seat: {result_name}")
        try:
            decoded = gzip.decompress(members[frame_name])
        except (OSError, EOFError) as exc:
            raise ValueError(f"incomplete frame gzip: {frame_name}: {exc}") from exc
        if not decoded.strip():
            raise ValueError(f"empty frame stream: {frame_name}")
        key = (sha256(decoded), seat)
        if key not in grouped:
            grouped[key] = {
                "key": f"{key[0]}:seat{seat}",
                "frame_sha256": key[0],
                "frame_member": frame_name,
                "result_member": result_name,
                "result": result,
                "aliases": [],
            }
        grouped[key]["aliases"].append(
            {
                "frame_member": frame_name,
                "result_member": result_name,
                "compressed_sha256": sha256(members[frame_name]),
                "seed": result.get("seed"),
                "candidate_seat": seat,
                "arm": result.get("arm"),
                "trace_sha256": result.get("trace_sha256"),
                "scores": result.get("scores"),
            }
        )
    if not grouped:
        raise ValueError("no complete retained frame streams")
    return list(grouped.values())
