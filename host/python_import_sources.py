#!/usr/bin/env python3
"""Map literal Python imports and explicitly named assets under one local root."""
from __future__ import annotations

import argparse
import ast
from collections import deque
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys


class ImportMapError(ValueError):
    """The requested local source map could not be read."""


class ImportLimit(Exception):
    """Stop without hiding already observed sources or pending work."""


class SourceMap:
    def __init__(self, root: Path, *, max_files: int, max_bytes: int,
                 max_file_bytes: int, max_imports: int):
        self.root = root
        self.limits = dict(max_files=max_files, max_bytes=max_bytes,
                           max_file_bytes=max_file_bytes, max_imports=max_imports)
        self.queue = deque()
        self.scheduled = set()
        self.files = []
        self.imports = []
        self.resolutions = {}
        self.errors = []
        self.skipped = []
        self.limits_reached = set()
        self.bytes_read = 0
        self.interrupted_source = None

    def probe(self, relative: str) -> dict:
        path = self.root / relative
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(self.root)
            mode = resolved.stat().st_mode
            kind = "file" if stat.S_ISREG(mode) else "directory" if stat.S_ISDIR(mode) else "special"
            return {"kind": kind, "resolved": resolved}
        except FileNotFoundError:
            return {"kind": "missing"}
        except (OSError, RuntimeError, ValueError) as exc:
            return {"kind": "unavailable", "detail": type(exc).__name__}

    def schedule(self, relative: str) -> None:
        if relative not in self.scheduled:
            self.scheduled.add(relative)
            self.queue.append(relative)

    def resolve(self, module: str) -> dict:
        if module in self.resolutions:
            return self.resolutions[module]
        parts = module.split(".")
        result = {"module": module, "status": "not_local", "sources": [],
                  "namespace_directories": []}
        if not module or any(not part.isidentifier() for part in parts):
            result["status"] = "unresolved_name"
        else:
            for index in range(1, len(parts) + 1):
                prefix = "/".join(parts[:index])
                package_path, module_path = prefix + "/__init__.py", prefix + ".py"
                package = self.probe(package_path)
                local_module = self.probe(module_path)
                if package["kind"] == "file":
                    result["sources"].append(package_path)
                    result["status"] = "local_package"
                elif package["kind"] not in ("missing", "directory"):
                    result.update(status="unavailable", candidate=package_path,
                                  detail=package["kind"])
                    break
                elif local_module["kind"] == "file":
                    result["sources"].append(module_path)
                    result["status"] = "local_module" if index == len(parts) else "not_a_package"
                    break
                elif local_module["kind"] not in ("missing", "directory"):
                    result.update(status="unavailable", candidate=module_path,
                                  detail=local_module["kind"])
                    break
                else:
                    directory = self.probe(prefix)
                    if directory["kind"] == "directory":
                        result["namespace_directories"].append(prefix)
                        result["status"] = "local_namespace"
                    else:
                        found_prefix = result["sources"] or result["namespace_directories"]
                        result.update(
                            status="unresolved_local" if found_prefix else "not_local",
                            candidates=[package_path, module_path],
                        )
                        if directory["kind"] not in ("missing", "directory"):
                            result.update(status="unavailable", candidate=prefix,
                                          detail=directory["kind"])
                        break
        self.resolutions[module] = result
        for relative in result["sources"]:
            self.schedule(relative)
        return result

    def record(self, row: dict) -> None:
        if len(self.imports) >= self.limits["max_imports"]:
            self.limits_reached.add("max_imports")
            raise ImportLimit
        self.imports.append(row)

    def request(self, relative: str, node: ast.AST, module: str, kind: str,
                **extra) -> dict:
        # Check before resolution so a stopped edge cannot silently queue work.
        if len(self.imports) >= self.limits["max_imports"]:
            self.limits_reached.add("max_imports")
            raise ImportLimit
        resolution = self.resolve(module)
        self.record(dict(source=relative, line=node.lineno, kind=kind,
                         module=module, resolution=resolution["status"], **extra))
        return resolution

    def imports_from(self, relative: str, tree: ast.AST) -> None:
        pieces = list(PurePosixPath(relative).with_suffix("").parts)
        package = pieces[:-1]
        aliases = {"__import__"}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "importlib":
                aliases.update(alias.asname or alias.name for alias in node.names
                               if alias.name == "import_module")
        nodes = [node for node in ast.walk(tree)
                 if isinstance(node, (ast.Import, ast.ImportFrom))
                 or (isinstance(node, ast.Call)
                     and ((isinstance(node.func, ast.Name) and node.func.id in aliases)
                          or (isinstance(node.func, ast.Attribute)
                              and node.func.attr == "import_module")))]
        nodes.sort(key=lambda node: (node.lineno, node.col_offset))
        for node in nodes:
            if isinstance(node, ast.Call):
                literal = node.args[0].value if node.args and isinstance(node.args[0], ast.Constant) else None
                self.record(dict(source=relative, line=node.lineno, kind="dynamic_call",
                                 module=literal if isinstance(literal, str) else None,
                                 resolution="not_followed"))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    self.request(relative, node, alias.name, "import")
            elif node.module == "__future__" and node.level == 0:
                self.record(dict(source=relative, line=node.lineno, kind="language_directive",
                                 module="__future__", resolution="not_a_source_request"))
            else:
                if node.level:
                    if node.level > len(package):
                        self.record(dict(source=relative, line=node.lineno, kind="from",
                                         module=node.module, level=node.level,
                                         resolution="relative_beyond_root"))
                        continue
                    base_parts = package[:len(package) - node.level + 1]
                    base = ".".join(base_parts + (node.module.split(".") if node.module else []))
                else:
                    base = node.module or ""
                resolution = self.request(relative, node, base, "from", level=node.level)
                for alias in node.names:
                    if alias.name == "*":
                        self.record(dict(source=relative, line=node.lineno, kind="star",
                                         module=base, resolution="exports_not_followed"))
                    elif resolution["status"] in ("local_package", "local_namespace"):
                        child = self.request(relative, node, base + "." + alias.name,
                                             "from_member", member=alias.name)
                        # A missing child can be an attribute, not a missing dependency.
                        if child["status"] in ("unresolved_local", "not_local"):
                            self.imports[-1]["resolution"] = "attribute_or_missing_submodule"

    def read_source(self, relative: str, *, kind: str = "source",
                    skipped: list[dict] | None = None) -> bytes | None:
        observed = self.probe(relative)
        if observed["kind"] != "file":
            raise ImportMapError(kind + " is " + observed["kind"])
        descriptor = os.open(observed["resolved"], os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
        try:
            with os.fdopen(descriptor, "rb") as stream:
                descriptor = None
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode):
                    raise ImportMapError(kind + " is not a regular file")
                if before.st_size > self.limits["max_file_bytes"]:
                    (self.skipped if skipped is None else skipped).append(
                        dict(path=relative, reason="max_file_bytes", bytes=before.st_size))
                    self.limits_reached.add("max_file_bytes")
                    return None
                if before.st_size > self.limits["max_bytes"] - self.bytes_read:
                    self.limits_reached.add("max_bytes")
                    raise ImportLimit
                raw = stream.read(before.st_size)
                self.bytes_read += len(raw)
                after = os.fstat(stream.fileno())
                if (len(raw) != before.st_size
                        or (before.st_size, before.st_mtime_ns)
                        != (after.st_size, after.st_mtime_ns)):
                    raise ImportMapError(kind + " changed while reading")
                return raw
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def scan(self, entries: list[str]) -> dict:
        for entry in entries:
            self.schedule(entry)
            parts = PurePosixPath(entry).parts
            for end in range(1, len(parts)):
                initializer = "/".join(parts[:end]) + "/__init__.py"
                if self.probe(initializer)["kind"] == "file":
                    self.schedule(initializer)
        while self.queue:
            if len(self.files) + len(self.skipped) + len(self.errors) >= self.limits["max_files"]:
                self.limits_reached.add("max_files")
                break
            relative = self.queue.popleft()
            try:
                raw = self.read_source(relative)
                if raw is None:
                    continue
                tree = ast.parse(raw, filename=relative)
                blob = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
                self.files.append(dict(path=relative, bytes=len(raw), blob_sha=blob,
                                       sha256=hashlib.sha256(raw).hexdigest()))
                self.imports_from(relative, tree)
            except ImportLimit:
                self.interrupted_source = relative
                break
            except (OSError, ValueError, RuntimeError, SyntaxError, RecursionError) as exc:
                detail = str(exc) if isinstance(exc, ImportMapError) else type(exc).__name__
                self.errors.append(dict(path=relative, detail=detail))
        unavailable = [name for name, row in self.resolutions.items()
                       if row["status"] == "unavailable"]
        return dict(
            schema_version=1, root=str(self.root), entries=entries,
            files=self.files, imports=self.imports,
            resolutions=list(self.resolutions.values()),
            errors=self.errors,
            coverage=dict(
                scope="literal Python imports under the explicit local root",
                scan_finished=not (self.queue or self.interrupted_source or self.skipped
                                   or self.errors or unavailable),
                source_files=len(self.files), source_bytes_read=self.bytes_read,
                import_records=len(self.imports), limits=self.limits,
                limits_reached=sorted(self.limits_reached), skipped_sources=self.skipped,
                pending_sources=list(self.queue), interrupted_source=self.interrupted_source,
                unavailable_modules=unavailable,
                runtime_completeness="not_evaluated",
            ),
        )


    def include_assets(self, result: dict, assets: list[str]) -> dict:
        """Append opaque file identities without importing or parsing assets."""
        requested = list(dict.fromkeys(assets))
        pending = deque(requested)
        retained = {row["path"]: row for row in self.files}
        files, skipped, errors, reused = [], [], [], []
        source_bytes = self.bytes_read
        interrupted = None
        attempted = 0
        source_observations = len(self.files) + len(self.skipped) + len(self.errors)
        while pending:
            relative = pending[0]
            if relative in retained:
                # The exact source bytes were already read within these limits.
                files.append(dict(retained[relative], reused_source=True))
                reused.append(relative)
                pending.popleft()
                continue
            if source_observations + attempted >= self.limits["max_files"]:
                self.limits_reached.add("max_files")
                break
            pending.popleft()
            attempted += 1
            try:
                raw = self.read_source(relative, kind="asset", skipped=skipped)
                if raw is None:
                    continue
                blob = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
                files.append(dict(path=relative, bytes=len(raw), blob_sha=blob,
                                  sha256=hashlib.sha256(raw).hexdigest(),
                                  reused_source=False))
            except ImportLimit:
                interrupted = relative
                break
            except (OSError, ValueError, RuntimeError) as exc:
                detail = str(exc) if isinstance(exc, ImportMapError) else type(exc).__name__
                errors.append(dict(path=relative, detail=detail))
        assets_finished = not (pending or interrupted or skipped or errors)
        result.update(requested_assets=requested, assets=files, asset_errors=errors)
        result["coverage"].update(
            scope="literal Python imports and explicit assets under the local root",
            scan_finished=result["coverage"]["scan_finished"] and assets_finished,
            explicit_assets_finished=assets_finished,
            asset_files=len(files), asset_files_read=len(files) - len(reused),
            asset_bytes_read=self.bytes_read - source_bytes,
            total_bytes_read=self.bytes_read, reused_source_assets=reused,
            limits_reached=sorted(self.limits_reached), skipped_assets=skipped,
            pending_assets=list(pending), interrupted_asset=interrupted,
        )
        return result


def positive(value: str) -> int:
    result = int(value)
    if result <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="one explicit local Python import root")
    parser.add_argument("--entry", action="append", required=True,
                        help="relative .py source path; repeat for multiple entries")
    parser.add_argument("--asset", action="append", default=[],
                        help="explicit relative resource path; read as opaque bytes; repeatable")
    parser.add_argument("--max-files", type=positive, default=256)
    parser.add_argument("--max-bytes", type=positive, default=8 * 1024 * 1024)
    parser.add_argument("--max-file-bytes", type=positive, default=1024 * 1024)
    parser.add_argument("--max-imports", type=positive, default=4096)
    args = parser.parse_args(argv)
    try:
        root = Path(args.root).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ImportMapError("root must be an existing directory")
        entries = []
        for entry in args.entry:
            parts = entry.split("/")
            if (not entry or "\\" in entry or "\0" in entry or entry.startswith("/")
                    or any(part in ("", ".", "..") for part in parts)
                    or not entry.endswith(".py")):
                raise ImportMapError("entry must be a relative .py path without traversal")
            if entry not in entries:
                entries.append(entry)
        assets = []
        for asset in args.asset:
            parts = asset.split("/")
            if (not asset or "\\" in asset or "\0" in asset or asset.startswith("/")
                    or any(part in ("", ".", "..") for part in parts)):
                raise ImportMapError("asset must be a relative file path without traversal")
            if asset not in assets:
                assets.append(asset)
        mapper = SourceMap(root, max_files=args.max_files, max_bytes=args.max_bytes,
                           max_file_bytes=args.max_file_bytes, max_imports=args.max_imports)
        result = mapper.scan(entries)
        if assets:
            result = mapper.include_assets(result, assets)
    except (OSError, ValueError, RuntimeError) as exc:
        detail = str(exc) if isinstance(exc, ImportMapError) else type(exc).__name__
        result = dict(error="IMPORT_MAP_INPUT", detail=detail)
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        print("python import sources: input could not be read", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    if result["errors"]:
        print("python import sources: %d source read/parse errors; see JSON errors" %
              len(result["errors"]), file=sys.stderr)
        return 1
    if result.get("asset_errors"):
        print("python import sources: %d asset read errors; see JSON asset_errors" %
              len(result["asset_errors"]), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
