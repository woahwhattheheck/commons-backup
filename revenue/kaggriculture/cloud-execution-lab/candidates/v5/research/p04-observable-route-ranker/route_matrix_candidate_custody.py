#!/usr/bin/env python3
"""Candidate-custody CLI for P04 route-matrix row receipts.

The public ``route_matrix_row_receipt.py`` facade dispatches here. The older
row/snapshot helpers live in ``_route_matrix_row_receipt_core.py``; this layer
adds proof that the route manifest, canonical candidate archive, materialized
payload, and bytes executed by the pinned evaluator are the same candidate.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

import _route_matrix_row_receipt_core as core

OFFICIAL_FILE_LOADER_SHA256 = "83e53481e3f71be30062a87a15439aa06380f6a917d066e8c1807b1eaefb6b23"
OFFICIAL_UPSTREAM_MANIFEST_SHA256 = "040ed98ca34d47ff56a9fcced2bdde28799a5a3b4a1957baae11406c87320740"
PUBLICATION_CUSTODY_SHA256 = "d159448917c92ec77e8c4d8a0f0f9122c5eca326e72f9d59539fc59bc6a60b62"
BUILD_DELIVERY_SHA256 = "8f578d0904946796fb2793c24f57dd7cef6bbaf09d3cb175f4d39f17ec84a4ae"
_PRIVATE_CANDIDATE_SPEC = "__titan_route_worker_private_candidate__"


def _safe_member(name: Any) -> str:
    if not isinstance(name, str) or not name:
        raise ValueError("candidate manifest member names must be nonempty strings")
    path = Path(name)
    if (path.is_absolute() or name.startswith(("/", "\\"))
            or any(part in ("", ".", "..") for part in path.parts)):
        raise ValueError(f"unsafe candidate manifest member path: {name!r}")
    return Path(*path.parts).as_posix()


def _capture_regular_bytes(path: Path, label: str) -> tuple[Path, bytes]:
    """Single-open one final path without following a final-component symlink."""
    original = Path(path)
    try:
        before = original.lstat()
    except OSError as exc:
        raise ValueError(f"cannot inspect {label}: {exc}") from exc
    if stat.S_ISLNK(before.st_mode):
        raise ValueError(f"{label} must not be a symlink")
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"{label} must be an ordinary file")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(original, flags)
    except OSError as exc:
        raise ValueError(f"cannot open {label}: {exc}") from exc
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            raise ValueError(f"{label} must be an ordinary file")
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError(f"{label} changed before capture")
        chunks = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        body = b"".join(chunks)
    finally:
        os.close(fd)
    return original.absolute(), body


def _load_exact_module(name: str, path: Path, expected_sha256: str):
    """Authenticate one captured byte stream and execute exactly that stream."""
    source_path, body = _capture_regular_bytes(path, name)
    actual = hashlib.sha256(body).hexdigest()
    if actual != expected_sha256:
        raise ValueError(f"{name} identity drift: {actual}")
    spec = importlib.util.spec_from_loader(name, loader=None, origin=str(source_path))
    if spec is None:
        raise ValueError(f"cannot import {name}")
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(source_path)
    sys.modules[spec.name] = module
    try:
        exec(compile(body, str(source_path), "exec"), module.__dict__)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return module


def _build_delivery_module():
    path = Path(__file__).resolve().parents[2] / "selective-carrot" / "build_delivery.py"
    return _load_exact_module("titan_v5_build_delivery", path, BUILD_DELIVERY_SHA256)


def canonical_archive_members(archive: Path, expected_sha256: str) -> dict[str, bytes]:
    """Decode via the exact route-builder archive parser.

    ``build_delivery.members`` single-reads and SHA-authenticates the gzip tar,
    and rejects non-files, duplicate/noncanonical paths, traversal and backslashes.
    """
    return _build_delivery_module().members(Path(archive), expected_sha256)


def capture_candidate(root: Path, archive: Path, manifest: dict[str, Any]):
    """Single-read one manifest-bound root and prove its canonical tar is identical."""
    root, archive = Path(root), Path(archive)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("candidate root must be an ordinary directory")
    if archive.is_symlink() or not archive.is_file():
        raise ValueError("candidate archive must be an ordinary file")

    raw_files = core._mapping(manifest.get("files"), "route manifest files")
    expected: dict[str, str] = {}
    for raw_name, digest in raw_files.items():
        name = _safe_member(raw_name)
        if name in expected:
            raise ValueError("duplicate normalized candidate member")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError(f"invalid candidate member SHA256: {name}")
        expected[name] = digest
    if "main.py" not in expected or core.ROUTER not in expected:
        raise ValueError("candidate manifest must bind main.py and r04_full_router.py")

    actual: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"candidate root contains symlink: {path.relative_to(root)}")
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
        elif not path.is_dir():
            raise ValueError(f"unsupported candidate filesystem entry: {path}")
    if actual != set(expected):
        raise ValueError(
            "candidate root member set drift: "
            f"missing={sorted(set(expected)-actual)} extra={sorted(actual-set(expected))}"
        )

    captured: dict[str, bytes] = {}
    for name in sorted(expected):
        _, body = _capture_regular_bytes(root / Path(name), f"candidate root member {name}")
        if hashlib.sha256(body).hexdigest() != expected[name]:
            raise ValueError(f"candidate root member SHA256 drift: {name}")
        captured[name] = body

    archive_sha = manifest.get("candidate_archive_sha256")
    if not isinstance(archive_sha, str) or len(archive_sha) != 64:
        raise ValueError("route manifest is missing candidate archive SHA256")
    archived = canonical_archive_members(archive, archive_sha)
    archive_map = {
        name: hashlib.sha256(body).hexdigest()
        for name, body in sorted(archived.items())
    }
    if archive_map != expected:
        raise ValueError("candidate archive member SHA map does not match route manifest files")
    if archived != captured:
        raise ValueError("candidate archive bytes do not match executable root capture")

    manifest_sha = hashlib.sha256(
        json.dumps(expected, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return captured, {
        "candidate_archive_sha256": archive_sha,
        "candidate_files_manifest_sha256": manifest_sha,
        "member_count": len(captured),
        "archive_root_byte_identity": True,
    }


def _capture_official_closure(official_loader: Path) -> tuple[dict[str, bytes], dict[str, Any]]:
    loader_path, loader_body = _capture_regular_bytes(official_loader, "official file loader")
    loader_sha = hashlib.sha256(loader_body).hexdigest()
    if loader_sha != OFFICIAL_FILE_LOADER_SHA256:
        raise ValueError(f"official file-loader identity drift: {loader_sha}")

    upstream = loader_path.parent / "upstream"
    _, manifest_body = _capture_regular_bytes(
        upstream / "manifest.json", "official upstream manifest"
    )
    manifest_sha = hashlib.sha256(manifest_body).hexdigest()
    if manifest_sha != OFFICIAL_UPSTREAM_MANIFEST_SHA256:
        raise ValueError(f"official upstream manifest identity drift: {manifest_sha}")
    try:
        manifest = json.loads(manifest_body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid official upstream manifest: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("ref") != core.ENGINE_REF:
        raise ValueError("official upstream manifest engine ref drift")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("official upstream manifest has no files")

    closure = {
        "official.py": loader_body,
        "upstream/manifest.json": manifest_body,
    }
    file_hashes = {}
    for raw_name, item in sorted(files.items()):
        name = _safe_member(raw_name)
        if not isinstance(item, dict):
            raise ValueError(f"official upstream manifest entry must be an object: {name}")
        expected = item.get("sha256")
        if not isinstance(expected, str) or len(expected) != 64:
            raise ValueError(f"official upstream manifest SHA256 is invalid: {name}")
        _, body = _capture_regular_bytes(upstream / Path(name), f"official upstream {name}")
        actual = hashlib.sha256(body).hexdigest()
        if actual != expected:
            raise ValueError(f"official upstream identity drift: {name}: {actual}")
        closure[f"upstream/{name}"] = body
        file_hashes[name] = actual

    closure_hash = hashlib.sha256(
        json.dumps(
            {name: hashlib.sha256(body).hexdigest() for name, body in sorted(closure.items())},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return closure, {
        "official_file_loader_sha256": loader_sha,
        "official_upstream_manifest_sha256": manifest_sha,
        "official_upstream_files_sha256": file_hashes,
        "official_closure_sha256": closure_hash,
        "official_closure_member_count": len(closure),
    }


def _b64_tree(tree: dict[str, bytes]) -> dict[str, str]:
    return {
        name: base64.b64encode(body).decode("ascii")
        for name, body in sorted(tree.items())
    }


def _worker_adapter_source(
    captured: dict[str, bytes], loader_closure: dict[str, bytes]
) -> bytes:
    """Build a path-independent bootstrap containing all authenticated executable bytes."""
    if "main.py" not in captured:
        raise ValueError("captured candidate is missing main.py")
    candidate_json = json.dumps(_b64_tree(captured), sort_keys=True, separators=(",", ":"))
    loader_json = json.dumps(_b64_tree(loader_closure), sort_keys=True, separators=(",", ":"))
    source = f"""# Generated from authenticated captured bytes; no caller path is reopened.
import base64
import hashlib
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

_CANDIDATE = {candidate_json}
_LOADER = {loader_json}


def _decode(tree):
    return {{name: base64.b64decode(value, validate=True) for name, value in tree.items()}}


def _publish(root, tree):
    for name, body in sorted(tree.items()):
        path = root / Path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())


def _verify(root, tree):
    actual = {{
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file()
    }}
    if actual != set(tree):
        raise ValueError("worker-private closure member set drift")
    for name, body in tree.items():
        if hashlib.sha256((root / Path(name)).read_bytes()).digest() != hashlib.sha256(body).digest():
            raise ValueError("worker-private closure byte drift: " + name)


def _freeze(root):
    paths = sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True)
    for path in paths:
        if path.is_file():
            os.chmod(path, 0o400)
        elif path.is_dir():
            os.chmod(path, 0o500)
    os.chmod(root, 0o500)


_candidate = _decode(_CANDIDATE)
_loader = _decode(_LOADER)
_custody = tempfile.TemporaryDirectory(prefix="titan-route-worker-captured-")
_root = Path(_custody.name)
_candidate_root = _root / "candidate"
_loader_root = _root / "loader"
_candidate_root.mkdir()
_loader_root.mkdir()
_publish(_candidate_root, _candidate)
_publish(_loader_root, _loader)
_verify(_candidate_root, _candidate)
_verify(_loader_root, _loader)

_official_path = _loader_root / "official.py"
_official_body = _loader["official.py"]
_spec = importlib.util.spec_from_loader(
    "titan_route_worker_official", loader=None, origin=str(_official_path)
)
if _spec is None:
    raise ValueError("cannot construct worker-private official loader module")
_official = importlib.util.module_from_spec(_spec)
_official.__file__ = str(_official_path)
sys.modules[_spec.name] = _official
exec(compile(_official_body, str(_official_path), "exec"), _official.__dict__)
agent = _official.make_agent(_candidate_root / "main.py")
_verify(_candidate_root, _candidate)
_verify(_loader_root, _loader)
_freeze(_candidate_root)
_freeze(_loader_root)
"""
    return source.encode()


def private_snapshot(captured: dict[str, bytes], official_loader: Path):
    """Capture the full file-agent closure and build a caller-path-free adapter."""
    loader_closure, authority = _capture_official_closure(official_loader)
    adapter = _worker_adapter_source(captured, loader_closure)
    authority = dict(authority)
    authority.update({
        "generated_adapter_sha256": hashlib.sha256(adapter).hexdigest(),
        "private_snapshot_member_count": len(captured),
        "adapter_embeds_captured_candidate": True,
        "adapter_embeds_captured_loader_closure": True,
        "caller_paths_embedded": False,
    })
    return adapter, authority


def _private_actor_class(evaluator: Any, adapter: bytes):
    """Wrap the pinned Actor so candidate bootstrap bytes exist only in its private cwd."""
    original = evaluator.Actor
    adapter_sha = hashlib.sha256(adapter).hexdigest()

    class PrivateCandidateActor(original):
        def __init__(
            self, spec, cache, loader, rng_seed, startup_timeout=10.0
        ):
            self._route_private_candidate = spec == _PRIVATE_CANDIDATE_SPEC
            self._route_adapter_sha256 = None
            self._route_adapter_removed_after_ready = None
            if not self._route_private_candidate:
                super().__init__(spec, cache, loader, rng_seed, startup_timeout)
                return

            globals_dict = original.__init__.__globals__
            tempfile_module = globals_dict.get("tempfile")
            if tempfile_module is None or not hasattr(tempfile_module, "TemporaryDirectory"):
                raise ValueError("pinned evaluator Actor tempfile API drift")
            real_tempfile = tempfile_module
            prepared: dict[str, Any] = {}

            class _PrivateTempfile:
                @staticmethod
                def TemporaryDirectory(*args, **kwargs):
                    holder = real_tempfile.TemporaryDirectory(*args, **kwargs)
                    private_root = Path(holder.name)
                    path = private_root / "candidate-adapter.py"
                    with path.open("xb") as stream:
                        stream.write(adapter)
                        stream.flush()
                        os.fsync(stream.fileno())
                    if hashlib.sha256(path.read_bytes()).hexdigest() != adapter_sha:
                        holder.cleanup()
                        raise ValueError("actor-private adapter publication drift")
                    os.chmod(path, 0o400)
                    os.chmod(private_root, 0o500)
                    prepared.update(holder=holder, root=private_root, path=path)
                    return holder

            globals_dict["tempfile"] = _PrivateTempfile
            error = None
            try:
                super().__init__(
                    "candidate-adapter.py::agent",
                    cache,
                    loader,
                    rng_seed,
                    startup_timeout,
                )
            except BaseException as exc:
                error = exc
                raise
            finally:
                globals_dict["tempfile"] = real_tempfile
                private_root = prepared.get("root")
                path = prepared.get("path")
                if private_root is not None:
                    try:
                        os.chmod(private_root, 0o700)
                    except OSError:
                        pass
                if path is not None:
                    try:
                        actual = hashlib.sha256(path.read_bytes()).hexdigest()
                        self._route_adapter_sha256 = actual
                        if actual != adapter_sha and error is None:
                            raise ValueError("actor-private adapter changed during startup")
                    finally:
                        try:
                            path.unlink()
                            self._route_adapter_removed_after_ready = True
                        except FileNotFoundError:
                            self._route_adapter_removed_after_ready = False

        def report(self):
            result = super().report()
            if self._route_private_candidate:
                result.update({
                    "candidate_adapter_sha256": self._route_adapter_sha256,
                    "candidate_adapter_expected_sha256": adapter_sha,
                    "candidate_adapter_actor_private": True,
                    "candidate_adapter_removed_after_ready": self._route_adapter_removed_after_ready,
                })
            return result

    return PrivateCandidateActor, adapter_sha


def shared_publication():
    path = Path(__file__).resolve().parents[2] / "selective-carrot" / "publication_custody.py"
    module = _load_exact_module(
        "titan_v5_publication_custody", path, PUBLICATION_CUSTODY_SHA256
    )
    return module.publish_exclusive


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evaluator", type=Path, required=True)
    p.add_argument("--engine-dir", type=Path, required=True)
    p.add_argument("--loader", type=Path, required=True)
    p.add_argument("--official-file-loader", type=Path, required=True)
    p.add_argument("--candidate-root", type=Path, required=True)
    p.add_argument("--candidate-archive", type=Path, required=True)
    p.add_argument("--route-manifest", type=Path, required=True)
    p.add_argument("--opponent-label", required=True)
    p.add_argument("--opponent", required=True)
    p.add_argument("--opponent-entry-sha256", required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--seat", type=int, choices=(0, 1), required=True)
    p.add_argument("--plan-index", type=int, choices=range(13), required=True)
    p.add_argument("--rng-seed", type=int, default=20260912)
    p.add_argument("--action-timeout", type=float, default=1.25)
    p.add_argument("--startup-timeout", type=float, default=10.0)
    p.add_argument("--game-timeout", type=float, default=900.0)
    p.add_argument("--row-out", type=Path, required=True)
    p.add_argument("--receipt-out", type=Path, required=True)
    args = p.parse_args()

    manifest = core.validate_route_manifest(
        core._load_json(args.route_manifest, "route manifest"), args.plan_index
    )
    if core.sha256_file(args.loader) != core.LOADER_SHA256:
        raise ValueError("loader identity drift")
    evaluator = core._import_exact_evaluator(args.evaluator)
    captured, materialization = capture_candidate(
        args.candidate_root, args.candidate_archive, manifest
    )
    adapter, snapshot_authority = private_snapshot(captured, args.official_file_loader)
    private_actor, adapter_sha = _private_actor_class(evaluator, adapter)

    opponent = evaluator.resolve_spec(args.opponent)
    o_before = core._entry_fingerprint(
        evaluator, opponent, args.opponent_entry_sha256, "opponent"
    )
    engine, engine_hashes = evaluator.get_engine(args.engine_dir, args.loader)
    pair = (
        [_PRIVATE_CANDIDATE_SPEC, opponent]
        if args.seat == 0
        else [opponent, _PRIVATE_CANDIDATE_SPEC]
    )
    original_actor = evaluator.Actor
    evaluator.Actor = private_actor
    try:
        game, snapshot = core.play_with_public_snapshot(
            evaluator, engine, pair, args.engine_dir, args.loader, args.seed, args.seat,
            args.rng_seed, args.action_timeout, args.startup_timeout, args.game_timeout,
        )
    finally:
        evaluator.Actor = original_actor

    actor_reports = game.get("actors")
    if not isinstance(actor_reports, list) or len(actor_reports) != 2:
        raise ValueError("native game did not return two actor reports")
    candidate_actor = actor_reports[args.seat]
    if (
        not isinstance(candidate_actor, dict)
        or candidate_actor.get("candidate_adapter_sha256") != adapter_sha
        or candidate_actor.get("candidate_adapter_expected_sha256") != adapter_sha
        or candidate_actor.get("candidate_adapter_actor_private") is not True
        or candidate_actor.get("candidate_adapter_removed_after_ready") is not True
    ):
        raise ValueError("candidate worker-private adapter custody failed")
    o_after = core._entry_fingerprint(
        evaluator, opponent, args.opponent_entry_sha256, "opponent"
    )
    if o_after != o_before:
        raise ValueError("opponent entry fingerprint changed during native game")

    candidate_identity = {
        "entry": "candidate-adapter.py",
        "callable": "agent",
        "sha256": adapter_sha,
        "execution_custody": "actor-private-captured-closure",
    }
    row = core.make_row(
        manifest, args.plan_index, args.seed, args.opponent_label, args.seat, snapshot, game
    )
    receipt = {
        "schema": core.SCHEMA,
        "route_candidate_archive_sha256": manifest["candidate_archive_sha256"],
        "baseline_candidate_archive_sha256": core.PRODUCTION_ARCHIVE_SHA256,
        "forced_plan": args.plan_index,
        "selection_step": core.ROUTE_STEP,
        "evaluator_sha256": core.EVALUATOR_SHA256,
        "loader_sha256": core.LOADER_SHA256,
        "engine_ref": core.ENGINE_REF,
        "engine_sha256": engine_hashes,
        "candidate": candidate_identity,
        "candidate_materialization": materialization,
        "candidate_snapshot_authority": snapshot_authority,
        "candidate_actor_custody": {
            key: candidate_actor[key]
            for key in (
                "candidate_adapter_sha256",
                "candidate_adapter_expected_sha256",
                "candidate_adapter_actor_private",
                "candidate_adapter_removed_after_ready",
            )
        },
        "opponent_label": args.opponent_label,
        "opponent": o_after,
        "seed": args.seed,
        "seat": args.seat,
        "rng_seed": args.rng_seed,
        "snapshot_sha256": row["snapshot_sha256"],
        "game_trace_sha256": game.get("trace_sha256"),
        "steps": game.get("steps"),
        "episode_steps": game.get("episode_steps"),
        "private_observation_persisted": False,
        "p04_row_sha256": hashlib.sha256(
            json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest(),
    }
    row_bytes = (
        json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()
    receipt_bytes = (
        json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode()
    shared_publication()(((args.row_out, row_bytes), (args.receipt_out, receipt_bytes)))
    print(json.dumps({
        "seed": args.seed,
        "opponent": args.opponent_label,
        "seat": args.seat,
        "forced_plan": args.plan_index,
        "snapshot_sha256": row["snapshot_sha256"],
        "terminal_margin": row["terminal_margin"],
    }, sort_keys=True))
    return 0