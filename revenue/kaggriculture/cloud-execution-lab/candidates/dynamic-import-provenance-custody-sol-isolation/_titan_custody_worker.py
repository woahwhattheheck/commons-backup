"""Isolated child process for the TITAN dynamic import provenance gate."""
from __future__ import annotations

import builtins
import contextlib
import importlib
import importlib.util
import inspect
import io
import json
import platform
import sys
import traceback
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from _titan_custody_common import (
    SCHEMA,
    audit_manifest_tree,
    audit_module,
    canonical_bytes,
    dedupe_violations,
    origin_record,
    sha256_bytes,
    sha256_file,
    under,
)


def redact(text: str, roots: Sequence[Path]) -> str:
    if not roots:
        return text
    text = text.replace(str(roots[0]), "<candidate-root>")
    for index, root in enumerate(sorted(roots[1:], key=lambda item: len(str(item)), reverse=True), 1):
        text = text.replace(str(root), f"<external-root-{index}>")
    return text


def resolve_callable(module: Any, dotted: str) -> Any:
    value = module
    for component in dotted.split("."):
        if not hasattr(value, component):
            raise AttributeError(f"callable component {component!r} was not found")
        value = getattr(value, component)
    if not callable(value):
        raise TypeError(f"resolved object {dotted!r} is not callable")
    return value


def module_origin(module: Any) -> str | None:
    spec = getattr(module, "__spec__", None)
    return getattr(module, "__file__", None) or (
        getattr(spec, "origin", None) if spec is not None else None
    )


def preload_modules(request: Mapping[str, Any]) -> tuple[list[dict[str, str]], set[str]]:
    loaded: list[dict[str, str]] = []
    tainted: set[str] = set()
    for preload in request["preloads"]:
        name = preload["module"]
        source = Path(preload["path"]).resolve(strict=True)
        before = set(sys.modules)
        if preload["kind"] == "root":
            sys.path.insert(0, str(source))
            importlib.invalidate_caches()
            try:
                importlib.import_module(name)
            finally:
                try:
                    sys.path.remove(str(source))
                except ValueError:
                    pass
        elif preload["kind"] == "file":
            spec = importlib.util.spec_from_file_location(name, source)
            if spec is None or spec.loader is None:
                raise ImportError(f"cannot construct preload spec for {name}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            try:
                spec.loader.exec_module(module)
            except BaseException:
                sys.modules.pop(name, None)
                raise
        else:
            raise ValueError(f"unsupported preload kind: {preload['kind']!r}")
        loaded.append({"kind": preload["kind"], "module": name})
        for module_name in set(sys.modules) - before:
            module = sys.modules.get(module_name)
            if module is None:
                continue
            raw = module_origin(module)
            if not raw or raw in {"built-in", "frozen", "namespace"}:
                continue
            try:
                origin = Path(str(raw)).resolve(strict=False)
                anchor = source if preload["kind"] == "root" else source.parent
                if under(origin, anchor):
                    tainted.add(module_name)
            except (OSError, ValueError):
                pass
    return loaded, tainted


def activate(entry: Any, root: Path, manifest: Mapping[str, str], violations: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"mode": "titan-new-instance", "attempted": True, "ok": False}
    factory = getattr(entry, "_new_instance", None)
    if not callable(factory):
        violations.append({"code": "ACTIVATION_API_MISSING", "detail": "_new_instance"})
        raise AttributeError("TITAN _new_instance activation API is unavailable")

    feature_loader = getattr(entry, "_load_feature_config", None)
    if callable(feature_loader):
        feature_data = feature_loader(root)
        result["config_source"] = "entrypoint:_load_feature_config"
    else:
        candidates = (
            root / "TITAN-CONFIG.json",
            root / "app/games/kaggriculture/submission/feature_config.json",
        )
        config = next((path for path in candidates if path.is_file()), None)
        if config is None:
            violations.append({"code": "ACTIVATION_CONFIG_MISSING", "detail": "TITAN-CONFIG.json"})
            raise FileNotFoundError("candidate feature configuration is unavailable")
        rel = config.relative_to(root).as_posix()
        observed = sha256_file(config)
        if rel not in manifest:
            violations.append({"code": "ACTIVATION_CONFIG_UNMANIFESTED", "path": rel})
        elif observed != manifest[rel]:
            violations.append(
                {
                    "code": "ACTIVATION_CONFIG_HASH_MISMATCH",
                    "path": rel,
                    "expected_sha256": manifest[rel],
                    "observed_sha256": observed,
                }
            )
        feature_data = json.loads(config.read_text(encoding="utf-8"))
        result["config_source"] = rel
    if not isinstance(feature_data, Mapping):
        violations.append({"code": "ACTIVATION_CONFIG_INVALID", "detail": type(feature_data).__name__})
        raise TypeError("candidate feature configuration must be an object")
    instance = factory(root, dict(feature_data))
    result.update(ok=True, result_type=f"{type(instance).__module__}.{type(instance).__qualname__}")
    return result


def child_main() -> int:
    request = json.loads(sys.stdin.buffer.read())
    root = Path(request["candidate_root"]).resolve(strict=True)
    manifest: dict[str, str] = dict(request["manifest"])
    local_names = set(request["local_top_levels"])
    entry_rel = request["entrypoint"]
    entry_name = request["entry_module_name"]
    callable_name = request["callable"]
    activation_mode = request["activate"]
    external = [Path(item["path"]).resolve(strict=True) for item in request["preloads"]]
    redaction_roots = [root, *external]

    violations = audit_manifest_tree(root, manifest)
    imported: set[str] = set()
    output = io.StringIO()
    errors = io.StringIO()
    preloads: list[dict[str, str]] = []
    tainted: set[str] = set()
    collisions: list[str] = []
    callable_receipt: dict[str, Any] = {
        "name": callable_name,
        "resolved": False,
        "module": None,
        "source_path": None,
    }
    activation: dict[str, Any] = {
        "mode": activation_mode,
        "attempted": False,
        "ok": activation_mode == "none",
    }
    original_import = builtins.__import__

    def traced_import(
        name: str,
        globals: Mapping[str, Any] | None = None,
        locals: Mapping[str, Any] | None = None,
        fromlist: Sequence[str] = (),
        level: int = 0,
    ) -> Any:
        absolute = name
        if level and globals:
            package = globals.get("__package__") or globals.get("__name__")
            if package:
                try:
                    absolute = importlib.util.resolve_name("." * level + name, str(package))
                except (ImportError, ValueError):
                    pass
        if absolute:
            imported.add(absolute)
        return original_import(name, globals, locals, fromlist, level)

    try:
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            preloads, tainted = preload_modules(request)
            collisions = sorted(
                name for name in sys.modules if name.split(".", 1)[0] in local_names
            )
            sys.path.insert(0, str(root))
            importlib.invalidate_caches()
            builtins.__import__ = traced_import

            entry_path = root / PurePosixPath(entry_rel)
            if not entry_path.is_file():
                violations.append({"code": "ENTRYPOINT_MISSING", "path": entry_rel})
                raise FileNotFoundError(entry_path)
            observed_entry = sha256_file(entry_path)
            expected_entry = manifest.get(entry_rel)
            if expected_entry is None:
                violations.append({"code": "ENTRYPOINT_UNMANIFESTED", "path": entry_rel})
            elif observed_entry != expected_entry:
                violations.append(
                    {
                        "code": "ENTRYPOINT_HASH_MISMATCH",
                        "path": entry_rel,
                        "expected_sha256": expected_entry,
                        "observed_sha256": observed_entry,
                    }
                )

            spec = importlib.util.spec_from_file_location(entry_name, entry_path)
            if spec is None or spec.loader is None:
                violations.append({"code": "ENTRYPOINT_SPEC_UNAVAILABLE", "path": entry_rel})
                raise ImportError(f"cannot construct entrypoint spec for {entry_rel}")
            entry = importlib.util.module_from_spec(spec)
            sys.modules[entry_name] = entry
            try:
                spec.loader.exec_module(entry)
            except BaseException:
                sys.modules.pop(entry_name, None)
                raise

            target = resolve_callable(entry, callable_name)
            callable_receipt["resolved"] = True
            callable_receipt["module"] = getattr(target, "__module__", None)
            source_raw = inspect.getsourcefile(target) or inspect.getfile(target)
            source = Path(source_raw).resolve(strict=False) if source_raw else None
            if source is None:
                violations.append({"code": "CALLABLE_SOURCE_UNAVAILABLE"})
            elif under(source, root):
                callable_receipt["source_path"] = source.relative_to(root).as_posix()
            else:
                callable_receipt["source_path"] = f"OUTSIDE_ROOT/{source.name}"
                violations.append({"code": "CALLABLE_OUTSIDE_ROOT", "path": callable_receipt["source_path"]})
            if callable_receipt["module"] != entry_name:
                violations.append(
                    {"code": "CALLABLE_MODULE_MISMATCH", "detail": str(callable_receipt["module"])}
                )

            if activation_mode == "titan-new-instance":
                activation = activate(entry, root, manifest, violations)
            elif activation_mode != "none":
                raise ValueError(f"unsupported activation mode: {activation_mode}")
    except BaseException as exc:
        activation["ok"] = False
        activation["attempted"] = activation_mode != "none"
        violations.append(
            {
                "code": "EXECUTION_ERROR",
                "detail": f"{type(exc).__name__}: {redact(str(exc), redaction_roots)}",
                "traceback_sha256": sha256_bytes(
                    redact(traceback.format_exc(), redaction_roots).encode()
                ),
            }
        )
    finally:
        builtins.__import__ = original_import

    loaded: list[dict[str, Any]] = []
    for name, module in sorted(sys.modules.items()):
        if module is None:
            continue
        top = name.split(".", 1)[0]
        origin = origin_record(module_origin(module), root)
        in_root = origin.get("kind") == "filesystem" and (
            origin.get("lexical_inside_root") or origin.get("resolved_inside_root")
        )
        if name != entry_name and name not in tainted and top not in local_names and not in_root:
            continue
        record, found = audit_module(name, module, root, manifest)
        loaded.append(record)
        violations.extend(found)

    stdout = output.getvalue().encode()
    stderr = errors.getvalue().encode()
    violations = dedupe_violations(violations)
    receipt = {
        "schema": SCHEMA,
        "verdict": "PASS" if not violations else "FAIL",
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
            "flags": {
                "isolated": int(sys.flags.isolated),
                "no_user_site": int(sys.flags.no_user_site),
                "dont_write_bytecode": int(sys.flags.dont_write_bytecode),
                "ignore_environment": int(sys.flags.ignore_environment),
                "safe_path": int(getattr(sys.flags, "safe_path", 0)),
            },
        },
        "candidate": {
            "root": ".",
            "manifest_raw_sha256": request["manifest_raw_sha256"],
            "manifest_canonical_sha256": request["manifest_canonical_sha256"],
            "manifest_file_count": len(manifest),
            "entrypoint": entry_rel,
            "entrypoint_expected_sha256": manifest.get(entry_rel),
            "callable": callable_name,
            "activation": activation_mode,
        },
        "preloads": sorted(preloads, key=lambda item: (item["kind"], item["module"])),
        "startup_local_collisions": collisions,
        "requested_local_imports": sorted(
            name for name in imported if name.split(".", 1)[0] in local_names
        ),
        "callable_provenance": callable_receipt,
        "activation": activation,
        "loaded_modules": sorted(loaded, key=lambda item: item["name"]),
        "captured_output": {
            "stdout_bytes": len(stdout),
            "stdout_sha256": sha256_bytes(stdout),
            "stderr_bytes": len(stderr),
            "stderr_sha256": sha256_bytes(stderr),
        },
        "violations": violations,
    }
    sys.stdout.buffer.write(canonical_bytes(receipt) + b"\n")
    return 0 if receipt["verdict"] == "PASS" else 1
