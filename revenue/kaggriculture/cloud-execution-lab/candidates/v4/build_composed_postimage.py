#!/usr/bin/env python3
"""Fail-closed executor for the sole canonical TITAN V4 composition graph.

This tool is deliberately narrower than a generic plugin runner.  It executes
only component IDs that are both `state=compose` in COMPOSITION.json and have
an explicit, source-pinned adapter in ADAPTERS below.  Blocked/evidence-only
components are never executed, new compose components fail until an adapter is
reviewed, and production paths are never modified: input is copied to a new
scratch output tree and atomically published only after every pin/postimage
check succeeds.
"""
from __future__ import annotations

import argparse
import hashlib
import types
import json
import os
import shutil
import stat
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA = "titan-v4-postimage/v1"
MANIFEST_NAME = "COMPOSITION.json"
CHECKER_NAME = "check_composition_graph.py"
RECEIPT_NAME = "V4-POSTIMAGE.json"


class MaterializationError(ValueError):
    pass


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise MaterializationError("duplicate JSON key: " + key)
        out[key] = value
    return out


def load_json(path: Path) -> tuple[dict[str, Any], bytes]:
    data = path.read_bytes()
    try:
        parsed = json.loads(data.decode("utf-8"), object_pairs_hook=_strict_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MaterializationError(f"invalid JSON {path.name}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise MaterializationError(f"{path.name}: top-level object required")
    return parsed, data


def _safe_rel(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise MaterializationError("unsafe relative path")
    p = PurePosixPath(value)
    if p.is_absolute() or any(part in ("", ".", "..") for part in p.parts):
        raise MaterializationError("unsafe relative path: " + value)
    return p


def _under(root: Path, rel: str, *, must_exist: bool = True) -> Path:
    p = root.joinpath(*_safe_rel(rel).parts)
    try:
        root_real = root.resolve(strict=True)
        if p.is_symlink():
            raise MaterializationError("symlink refused: " + rel)
        resolved = p.resolve(strict=must_exist)
        resolved.relative_to(root_real)
    except (FileNotFoundError, RuntimeError, OSError, ValueError) as exc:
        if isinstance(exc, MaterializationError):
            raise
        raise MaterializationError("path escapes/missing: " + rel) from exc
    if must_exist and not resolved.is_file():
        raise MaterializationError("regular file required: " + rel)
    return resolved


def _blob_id(identity: Any) -> str:
    if not isinstance(identity, str) or not identity.startswith("git-blob:"):
        raise MaterializationError("git-blob identity required")
    value = identity.split(":", 1)[1]
    if len(value) != 40 or any(c not in "0123456789abcdef" for c in value):
        raise MaterializationError("invalid Git blob identity: " + identity)
    return value


def _surface_file(surface: Any) -> str:
    if not isinstance(surface, str) or not surface:
        raise MaterializationError("nonempty transform surface required")
    rel = surface.split("::", 1)[0]
    _safe_rel(rel)
    return rel


def _load_module(path: Path, expected_blob: str, label: str):
    data = path.read_bytes()
    actual = git_blob(data)
    if actual != expected_blob:
        raise MaterializationError(
            f"adapter source drift for {label}: expected {expected_blob}, got {actual}"
        )
    name = "titan_v4_postimage_" + hashlib.sha256(
        (label + expected_blob).encode("utf-8")
    ).hexdigest()[:16]
    module = types.ModuleType(name)
    module.__file__ = str(path)
    try:
        exec(compile(data, str(path), "exec"), module.__dict__)
    except Exception as exc:
        raise MaterializationError("cannot load pinned adapter: " + label) from exc
    return module


def _tree_index(root: Path, *, exclude: set[str] | None = None) -> dict[str, dict[str, Any]]:
    exclude = exclude or set()
    rows: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if rel in exclude:
            continue
        if path.is_symlink():
            raise MaterializationError("symlink refused in package: " + rel)
        mode = path.lstat().st_mode
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            raise MaterializationError("special file refused in package: " + rel)
        data = path.read_bytes()
        rows[rel] = {
            "bytes": len(data),
            "git_blob": git_blob(data),
            "sha256": sha256(data),
        }
    return rows


def _tree_digest(rows: dict[str, dict[str, Any]]) -> str:
    h = hashlib.sha256()
    for rel in sorted(rows):
        row = rows[rel]
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(str(row["bytes"]).encode("ascii"))
        h.update(b"\0")
        h.update(row["git_blob"].encode("ascii"))
        h.update(b"\0")
        h.update(row["sha256"].encode("ascii"))
        h.update(b"\n")
    return h.hexdigest()


def _copy_tree(source: Path, dest: Path) -> None:
    source = source.resolve(strict=True)
    if not source.is_dir():
        raise MaterializationError("package must be a directory")
    dest.mkdir(parents=True, exist_ok=False)
    for path in sorted(source.rglob("*")):
        rel = path.relative_to(source)
        target = dest / rel
        if path.is_symlink():
            raise MaterializationError("symlink refused in package: " + rel.as_posix())
        mode = path.lstat().st_mode
        if stat.S_ISDIR(mode):
            target.mkdir(exist_ok=True)
        elif stat.S_ISREG(mode):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            os.chmod(target, stat.S_IMODE(mode))
        else:
            raise MaterializationError("special file refused in package: " + rel.as_posix())


def _component_transforms(component: dict[str, Any]) -> dict[str, dict[str, str]]:
    raw = component.get("transforms")
    if not isinstance(raw, list) or not raw:
        raise MaterializationError(component.get("id", "component") + ": transforms required")
    out: dict[str, dict[str, str]] = {}
    for item in raw:
        if not isinstance(item, dict):
            raise MaterializationError("transform object required")
        rel = _surface_file(item.get("surface"))
        if rel in out:
            raise MaterializationError("duplicate transform surface file: " + rel)
        out[rel] = {
            "before": _blob_id(item.get("input_identity")),
            "after": _blob_id(item.get("output_identity")),
        }
    return out


def _assert_before(worktree: Path, transforms: dict[str, dict[str, str]]) -> dict[str, bytes]:
    data: dict[str, bytes] = {}
    for rel, edge in transforms.items():
        path = _under(worktree, rel)
        raw = path.read_bytes()
        actual = git_blob(raw)
        if actual != edge["before"]:
            raise MaterializationError(
                f"{rel}: composition preimage mismatch; expected {edge['before']}, got {actual}"
            )
        data[rel] = raw
    return data


def _assert_after(worktree: Path, transforms: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rel in sorted(transforms):
        path = _under(worktree, rel)
        raw = path.read_bytes()
        actual = git_blob(raw)
        expected = transforms[rel]["after"]
        if actual != expected:
            raise MaterializationError(
                f"{rel}: composition postimage mismatch; expected {expected}, got {actual}"
            )
        if rel.endswith(".py"):
            compile(raw, rel, "exec")
        rows.append({
            "path": rel,
            "before_git_blob": transforms[rel]["before"],
            "after_git_blob": actual,
            "bytes": len(raw),
            "sha256": sha256(raw),
        })
    return rows


def _repo_root(workspace: Path, manifest: dict[str, Any]) -> Path:
    raw = manifest.get("canonical_root")
    if not isinstance(raw, str):
        raise MaterializationError("canonical_root required for repository support sources")
    rel = _safe_rel(raw)
    root = workspace.resolve(strict=True)
    for _ in rel.parts:
        root = root.parent
    expected = root.joinpath(*rel.parts).resolve(strict=True)
    if expected != workspace.resolve(strict=True):
        raise MaterializationError("workspace does not match manifest canonical_root")
    return root


def _load_support_source(workspace: Path, repo_root: Path, key: str, expected_blob: str) -> bytes:
    if not isinstance(key, str) or ":" not in key:
        raise MaterializationError("support source key must be scope:path")
    scope, rel = key.split(":", 1)
    if scope == "workspace":
        base = workspace
    elif scope == "repo":
        base = repo_root
    else:
        raise MaterializationError("unknown support source scope: " + scope)
    data = _under(base, rel).read_bytes()
    actual = git_blob(data)
    if actual != expected_blob:
        raise MaterializationError(
            f"support source drift for {key}: expected {expected_blob}, got {actual}"
        )
    return data


def _write_support(worktree: Path, rel: str, data: bytes) -> dict[str, Any]:
    path = _under(worktree, rel, must_exist=False)
    before = None
    if path.exists():
        before_data = path.read_bytes()
        before = git_blob(before_data)
        if before_data != data:
            raise MaterializationError(rel + ": existing support output differs from pinned source")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return {
        "path": rel,
        "role": "support",
        "before_git_blob": before,
        "after_git_blob": git_blob(data),
        "bytes": len(data),
        "sha256": sha256(data),
    }


def _require_entrypoints(component: dict[str, Any], expected: tuple[str, ...]) -> None:
    raw = component.get("entrypoints")
    if raw != list(expected):
        raise MaterializationError(
            f"{component.get('id')}: entrypoint list differs from reviewed adapter contract"
        )


def _run_fast_tape(component: dict[str, Any], workspace: Path, worktree: Path,
                   modules: dict[str, Any], sources: dict[str, bytes]) -> list[dict[str, Any]]:
    expected_eps = ("repairs/performance/fast-tape-clone/port_current_runtime.py",)
    _require_entrypoints(component, expected_eps)
    transforms = _component_transforms(component)
    if set(transforms) != {"titan_runtime.py"}:
        raise MaterializationError("fast-tape adapter owns only titan_runtime.py")
    before = _assert_before(worktree, transforms)["titan_runtime.py"]
    module = modules[expected_eps[0]]
    transform = getattr(module, "transform", None)
    if not callable(transform):
        raise MaterializationError("fast-tape adapter missing transform()")
    result = transform(before, transforms["titan_runtime.py"]["before"])
    if not isinstance(result, bytes):
        raise MaterializationError("fast-tape transform did not return bytes")
    if git_blob(result) != transforms["titan_runtime.py"]["after"]:
        raise MaterializationError("fast-tape transform output disagrees with COMPOSITION.json")
    _under(worktree, "titan_runtime.py").write_bytes(result)
    return _assert_after(worktree, transforms)


def _run_funding_stack(component: dict[str, Any], workspace: Path, worktree: Path,
                       modules: dict[str, Any], sources: dict[str, bytes]) -> list[dict[str, Any]]:
    expected_eps = (
        "repairs/performance/funding-replay/apply_town_funding.py",
        "repairs/runtime/joint-unit-projection/compose.py",
        "repairs/performance/funding-replay/apply_funding_replay.py",
        "repairs/performance/funding-replay/compose_funding_capacity.py",
    )
    _require_entrypoints(component, expected_eps)
    if component.get("source_order") != list(expected_eps):
        raise MaterializationError("funding stack source_order differs from reviewed adapter contract")
    transforms = _component_transforms(component)
    if set(transforms) != {"scheduler.py", "frozen_selected.py"}:
        raise MaterializationError("funding adapter owns only scheduler.py + frozen_selected.py")
    before = _assert_before(worktree, transforms)
    scheduler = before["scheduler.py"].decode("utf-8")
    frozen = before["frozen_selected.py"].decode("utf-8")

    town = modules[expected_eps[0]]
    unit = modules[expected_eps[1]]
    funding = modules[expected_eps[2]]
    cap = modules[expected_eps[3]]
    for module, func in ((town, "apply"), (unit, "compose_sources"),
                         (funding, "apply"), (cap, "apply")):
        if not callable(getattr(module, func, None)):
            raise MaterializationError("pinned funding adapter missing callable: " + func)

    # Exact reviewed source order from COMPOSITION.json.
    frozen = town.apply(frozen)
    scheduler, frozen = unit.compose_sources(scheduler, frozen)
    frozen = funding.apply(frozen)
    frozen = cap.apply(frozen)
    scheduler_b = scheduler.encode("utf-8")
    frozen_b = frozen.encode("utf-8")
    compile(scheduler_b, "scheduler.py", "exec")
    compile(frozen_b, "frozen_selected.py", "exec")
    if git_blob(scheduler_b) != transforms["scheduler.py"]["after"]:
        raise MaterializationError("funding stack scheduler postimage disagrees with COMPOSITION.json")
    if git_blob(frozen_b) != transforms["frozen_selected.py"]["after"]:
        raise MaterializationError("funding stack frozen postimage disagrees with COMPOSITION.json")
    _under(worktree, "scheduler.py").write_bytes(scheduler_b)
    _under(worktree, "frozen_selected.py").write_bytes(frozen_b)
    return _assert_after(worktree, transforms)


def _run_scoped_construction(component: dict[str, Any], workspace: Path, worktree: Path,
                             modules: dict[str, Any], sources: dict[str, bytes]) -> list[dict[str, Any]]:
    ep = "repairs/performance/compose_scoped_constructor.py"
    helper_key = "repo:revenue/kaggriculture/cloud-quickstep/scoped_method_cache.py"
    _require_entrypoints(component, (ep,))
    transforms = _component_transforms(component)
    if set(transforms) != {"scheduler.py", "selected_sell_core.py"}:
        raise MaterializationError("scoped-construction adapter owns only scheduler.py + selected_sell_core.py")
    before = _assert_before(worktree, transforms)
    module = modules[ep]
    compose = getattr(module, "compose", None)
    if not callable(compose):
        raise MaterializationError("scoped-construction adapter missing compose()")
    helper = sources.get(helper_key)
    if not isinstance(helper, bytes):
        raise MaterializationError("scoped-construction pinned helper missing")
    rows: list[dict[str, Any]] = []
    for rel in ("scheduler.py", "selected_sell_core.py"):
        result = compose(before[rel], helper)
        if not isinstance(result, tuple) or len(result) != 2 or not isinstance(result[0], bytes):
            raise MaterializationError("scoped-construction compose() returned invalid result")
        if git_blob(result[0]) != transforms[rel]["after"]:
            raise MaterializationError(rel + ": scoped-construction postimage disagrees with COMPOSITION.json")
        _under(worktree, rel).write_bytes(result[0])
    rows.extend(_assert_after(worktree, transforms))
    rows.append(_write_support(worktree, "scoped_method_cache.py", helper))
    return rows


def _run_projection_clone(component: dict[str, Any], workspace: Path, worktree: Path,
                          modules: dict[str, Any], sources: dict[str, bytes]) -> list[dict[str, Any]]:
    ep = "repairs/performance/projection-state-clone/compose.py"
    helper_key = "workspace:repairs/performance/projection-state-clone/projection_clone.py"
    _require_entrypoints(component, (ep,))
    transforms = _component_transforms(component)
    if set(transforms) != {"frozen_selected.py", "early_capital.py"}:
        raise MaterializationError("projection clone adapter owns only frozen_selected.py + early_capital.py")
    before = _assert_before(worktree, transforms)
    module = modules[ep]
    compose = getattr(module, "compose_sources", None)
    if not callable(compose):
        raise MaterializationError("projection clone adapter missing compose_sources()")
    helper = sources.get(helper_key)
    if not isinstance(helper, bytes):
        raise MaterializationError("projection clone pinned helper missing")
    expected_sha = getattr(module, "HELPER_SHA256", None)
    if expected_sha != sha256(helper):
        raise MaterializationError("projection clone helper SHA256 disagrees with composer")
    frozen, capital = compose(
        before["frozen_selected.py"].decode("utf-8"),
        before["early_capital.py"].decode("utf-8"),
    )
    outputs = {"frozen_selected.py": frozen.encode("utf-8"),
               "early_capital.py": capital.encode("utf-8")}
    for rel, data in outputs.items():
        if git_blob(data) != transforms[rel]["after"]:
            raise MaterializationError(rel + ": projection clone postimage disagrees with COMPOSITION.json")
        _under(worktree, rel).write_bytes(data)
    rows = _assert_after(worktree, transforms)
    rows.append(_write_support(worktree, "projection_clone.py", helper))
    return rows


def _run_h3s420(component: dict[str, Any], workspace: Path, worktree: Path,
                 modules: dict[str, Any], sources: dict[str, bytes]) -> list[dict[str, Any]]:
    ep = "research/sale-window-engagement/compose_current_h3s420.py"
    _require_entrypoints(component, (ep,))
    transforms = _component_transforms(component)
    if set(transforms) != {"frozen_selected.py"}:
        raise MaterializationError("h3s420 adapter owns only frozen_selected.py")
    before = _assert_before(worktree, transforms)["frozen_selected.py"]
    module = modules[ep]
    compose = getattr(module, "compose", None)
    if not callable(compose):
        raise MaterializationError("h3s420 adapter missing compose()")
    result = compose(before, enabled=True)
    if not isinstance(result, bytes):
        raise MaterializationError("h3s420 compose() did not return bytes")
    if git_blob(result) != transforms["frozen_selected.py"]["after"]:
        raise MaterializationError("h3s420 postimage disagrees with COMPOSITION.json")
    _under(worktree, "frozen_selected.py").write_bytes(result)
    return _assert_after(worktree, transforms)


# Adapter source blobs are content identities from canonical main at authoring.
# Any composer edit must be explicitly reviewed/rebound here before execution.
ADAPTERS: dict[str, dict[str, Any]] = {
    "fast-tape-clone-current-runtime": {
        "entrypoints": {
            "repairs/performance/fast-tape-clone/port_current_runtime.py":
                "4c7474062292feb25638ae0af5161e9d5382e6f5",
        },
        "runner": _run_fast_tape,
    },
    "funding-capacity-stack": {
        "entrypoints": {
            "repairs/performance/funding-replay/apply_town_funding.py":
                "527811763c80e627895d8e11319f8877b18105e6",
            "repairs/runtime/joint-unit-projection/compose.py":
                "e1127c4aad842278a9e617903b0718d21c00f348",
            "repairs/performance/funding-replay/apply_funding_replay.py":
                "d579759e8f6bd6c4649d58f220b1b193a9bda491",
            "repairs/performance/funding-replay/compose_funding_capacity.py":
                "d8aa0a6cde7ec74142b806d29d1dca5201d9757a",
        },
        "runner": _run_funding_stack,
    },
    "scoped-construction": {
        "entrypoints": {
            "repairs/performance/compose_scoped_constructor.py":
                "4267520ae966b16bad33083aaa9fb7772f7de045",
        },
        "sources": {
            "repo:revenue/kaggriculture/cloud-quickstep/scoped_method_cache.py":
                "1438a95e69e76c97542b9b95bff1ca3745fa284e",
        },
        "support_outputs": ["scoped_method_cache.py"],
        "runner": _run_scoped_construction,
    },
    "projection-state-clone": {
        "entrypoints": {
            "repairs/performance/projection-state-clone/compose.py":
                "3f53a5c74c369be0555d63c470bb0519bcb3e306",
        },
        "sources": {
            "workspace:repairs/performance/projection-state-clone/projection_clone.py":
                "cf2cd8913bd990469ebf2e5733eee28c6af569ea",
        },
        "support_outputs": ["projection_clone.py"],
        "runner": _run_projection_clone,
    },
    "h3s420-sale-window": {
        "entrypoints": {
            "research/sale-window-engagement/compose_current_h3s420.py":
                "7c5778b4d6d7c47f8feca7e800fc8093267b66f8",
        },
        "runner": _run_h3s420,
    },
}


def _load_checker(workspace: Path):
    path = _under(workspace, CHECKER_NAME)
    data = path.read_bytes()
    name = "titan_v4_postimage_checker_" + git_blob(data)[:12]
    module = types.ModuleType(name)
    module.__file__ = str(path)
    try:
        exec(compile(data, str(path), "exec"), module.__dict__)
    except Exception as exc:
        raise MaterializationError("cannot load composition checker") from exc
    validate = getattr(module, "validate_manifest", None)
    if not callable(validate):
        raise MaterializationError("composition checker missing validate_manifest()")
    return module


def _component_map(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = manifest.get("components")
    if not isinstance(raw, list):
        raise MaterializationError("components list required")
    out: dict[str, dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise MaterializationError("valid component objects required")
        cid = item["id"]
        if cid in out:
            raise MaterializationError("duplicate component id: " + cid)
        out[cid] = item
    return out


def validate_execution_contract(workspace: Path, manifest: dict[str, Any],
                                graph: dict[str, Any],
                                adapters: dict[str, dict[str, Any]] = ADAPTERS
                                ) -> dict[str, dict[str, Any]]:
    if graph.get("ok") is not True:
        raise MaterializationError("composition graph is not valid")
    plan = graph.get("plan")
    if not isinstance(plan, list) or any(not isinstance(x, str) for x in plan):
        raise MaterializationError("composition graph returned invalid plan")
    components = _component_map(manifest)
    active = sorted(cid for cid, comp in components.items() if comp.get("state") == "compose")
    if sorted(plan) != active:
        raise MaterializationError("checker plan does not equal active compose set")
    unsupported = sorted(set(plan) - set(adapters))
    if unsupported:
        raise MaterializationError("compose component lacks reviewed adapter: " + ", ".join(unsupported))

    loaded: dict[str, dict[str, Any]] = {}
    for cid in plan:
        spec = adapters[cid]
        entrypoints = spec.get("entrypoints")
        runner = spec.get("runner")
        if not isinstance(entrypoints, dict) or not callable(runner):
            raise MaterializationError("malformed adapter registry: " + cid)
        comp_eps = components[cid].get("entrypoints")
        if comp_eps != list(entrypoints):
            raise MaterializationError(cid + ": manifest entrypoints differ from reviewed adapter registry")
        modules: dict[str, Any] = {}
        for rel, expected_blob in entrypoints.items():
            if not isinstance(expected_blob, str) or len(expected_blob) != 40:
                raise MaterializationError("malformed adapter blob pin: " + rel)
            modules[rel] = _load_module(_under(workspace, rel), expected_blob, cid + ":" + rel)
        source_specs = spec.get("sources", {})
        if not isinstance(source_specs, dict):
            raise MaterializationError("malformed adapter support sources: " + cid)
        source_bytes: dict[str, bytes] = {}
        if source_specs:
            repo_root = _repo_root(workspace, manifest)
            for key, expected_blob in source_specs.items():
                if not isinstance(expected_blob, str) or len(expected_blob) != 40:
                    raise MaterializationError("malformed support source blob pin: " + str(key))
                source_bytes[key] = _load_support_source(
                    workspace, repo_root, key, expected_blob
                )
        outputs = spec.get("support_outputs", [])
        if (not isinstance(outputs, list)
                or any(not isinstance(rel, str) for rel in outputs)
                or len(set(outputs)) != len(outputs)):
            raise MaterializationError("malformed support output registry: " + cid)
        for rel in outputs:
            _safe_rel(rel)
        loaded[cid] = {"runner": runner, "modules": modules, "sources": source_bytes}
    return loaded


def _same_or_nested(a: Path, b: Path) -> bool:
    try:
        a.resolve().relative_to(b.resolve())
        return True
    except ValueError:
        return False


def materialize(workspace: Path, package: Path, output: Path,
                *, manifest_path: Path | None = None,
                adapters: dict[str, dict[str, Any]] = ADAPTERS) -> dict[str, Any]:
    workspace = workspace.resolve(strict=True)
    package = package.resolve(strict=True)
    output = output.absolute()
    manifest_path = manifest_path or workspace / MANIFEST_NAME
    manifest, manifest_bytes = load_json(manifest_path)
    checker = _load_checker(workspace)
    graph = checker.validate_manifest(manifest, workspace)
    loaded = validate_execution_contract(workspace, manifest, graph, adapters)
    components = _component_map(manifest)

    if output.exists():
        raise MaterializationError("output already exists")
    if _same_or_nested(output, package) or _same_or_nested(package, output):
        raise MaterializationError("input/output trees must be disjoint")

    input_rows = _tree_index(package)
    parent = output.parent
    parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix="." + output.name + ".tmp-", dir=parent))
    # mkdtemp created the directory; _copy_tree expects to create it.
    temp.rmdir()
    component_receipts: list[dict[str, Any]] = []
    try:
        _copy_tree(package, temp)
        if _tree_index(temp) != input_rows:
            raise MaterializationError("input package changed during scratch copy")
        for cid in graph["plan"]:
            loaded_spec = loaded[cid]
            files = loaded_spec["runner"](
                components[cid], workspace, temp, loaded_spec["modules"], loaded_spec["sources"]
            )
            component_receipts.append({"id": cid, "files": files})

        output_rows = _tree_index(temp)
        changed = sorted(
            rel for rel in set(input_rows) | set(output_rows)
            if input_rows.get(rel) != output_rows.get(rel)
        )
        required = {
            _surface_file(t["surface"])
            for cid in graph["plan"]
            for t in components[cid].get("transforms", [])
            if isinstance(t, dict) and "surface" in t
        }
        support = {
            rel
            for cid in graph["plan"]
            for rel in adapters[cid].get("support_outputs", [])
        }
        changed_set = set(changed)
        if not required.issubset(changed_set) or not changed_set.issubset(required | support):
            raise MaterializationError(
                "changed-file set exceeds reviewed transform/support outputs: "
                f"changed={changed!r}, required={sorted(required)!r}, allowed={sorted(required | support)!r}"
            )

        checker_path = _under(workspace, CHECKER_NAME)
        adapter_receipt = {}
        for cid in graph["plan"]:
            adapter_receipt[cid] = {
                "entrypoints": [
                    {"path": rel, "git_blob": blob}
                    for rel, blob in adapters[cid]["entrypoints"].items()
                ],
                "support_sources": [
                    {"source": key, "git_blob": blob}
                    for key, blob in adapters[cid].get("sources", {}).items()
                ],
                "support_outputs": list(adapters[cid].get("support_outputs", [])),
            }
        receipt: dict[str, Any] = {
            "schema": SCHEMA,
            "release_authorized": False,
            "production_activation": False,
            "canonical_branch": manifest.get("canonical_branch"),
            "canonical_root": manifest.get("canonical_root"),
            "manifest": {
                "git_blob": git_blob(manifest_bytes),
                "sha256": sha256(manifest_bytes),
            },
            "checker": {
                "git_blob": git_blob(checker_path.read_bytes()),
                "sha256": sha256(checker_path.read_bytes()),
            },
            "plan": list(graph["plan"]),
            "blocked": list(graph.get("blocked", [])),
            "evidence_only": list(graph.get("evidence_only", [])),
            "adapters": adapter_receipt,
            "components": component_receipts,
            "changed_files": changed,
            "input_tree": {
                "files": len(input_rows),
                "bytes": sum(row["bytes"] for row in input_rows.values()),
                "sha256": _tree_digest(input_rows),
            },
            "output_tree": {
                "files": len(output_rows),
                "bytes": sum(row["bytes"] for row in output_rows.values()),
                "sha256": _tree_digest(output_rows),
            },
        }
        receipt_bytes = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")
        (temp / RECEIPT_NAME).write_bytes(receipt_bytes)
        # The receipt is deliberately excluded from output_tree to avoid a circular digest.
        os.replace(temp, output)
        return receipt
    except BaseException:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def check_only(workspace: Path, *, manifest_path: Path | None = None,
               adapters: dict[str, dict[str, Any]] = ADAPTERS) -> dict[str, Any]:
    workspace = workspace.resolve(strict=True)
    manifest_path = manifest_path or workspace / MANIFEST_NAME
    manifest, manifest_bytes = load_json(manifest_path)
    checker = _load_checker(workspace)
    graph = checker.validate_manifest(manifest, workspace)
    validate_execution_contract(workspace, manifest, graph, adapters)
    return {
        "ok": True,
        "schema": SCHEMA,
        "manifest_git_blob": git_blob(manifest_bytes),
        "plan": graph["plan"],
        "blocked": graph.get("blocked", []),
        "evidence_only": graph.get("evidence_only", []),
        "release_authorized": False,
        "production_activation": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path(__file__).parent)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--check", action="store_true", help="validate graph + pinned adapters only")
    parser.add_argument("--package", type=Path, help="authenticated extracted native package")
    parser.add_argument("--output", type=Path, help="new disposable composed output directory")
    args = parser.parse_args()
    try:
        if args.check:
            if args.package is not None or args.output is not None:
                raise MaterializationError("--check cannot be combined with --package/--output")
            result = check_only(args.workspace, manifest_path=args.manifest)
        else:
            if args.package is None or args.output is None:
                raise MaterializationError("--package and --output are required unless --check is used")
            result = materialize(
                args.workspace, args.package, args.output, manifest_path=args.manifest
            )
    except (MaterializationError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
