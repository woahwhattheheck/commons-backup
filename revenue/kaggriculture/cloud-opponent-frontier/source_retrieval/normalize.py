"""Extract reviewed public Python/notebook sources without executing any source.

This is an extraction/provenance utility, not a license, lineage, or runtime
approval. The caller must inspect the receipt and exercise the actual agent.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import shutil
import tempfile
from typing import Any

SCHEMA = "titan.public-source-normalization.v1"


class SourceError(ValueError):
    """The supplied bytes cannot be normalized by the declared transformation."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")


def pointer(document: Any, path: str) -> Any:
    """Resolve an explicit RFC 6901-style pointer; never search for a matching ID."""
    if path == "":
        return document
    if not path.startswith("/"):
        raise SourceError("A JSON pointer must be empty or start with '/'")
    current = document
    try:
        for part in path[1:].split("/"):
            # Reject malformed escapes instead of silently interpreting them.
            i = 0
            while i < len(part):
                if part[i] == "~":
                    if i + 1 >= len(part) or part[i + 1] not in "01":
                        raise SourceError("Malformed JSON pointer escape")
                    i += 1
                i += 1
            part = part.replace("~1", "/").replace("~0", "~")
            if isinstance(current, list):
                if not part.isascii() or not part.isdigit() or (len(part) > 1 and part[0] == "0"):
                    raise SourceError("Non-canonical array index in JSON pointer")
                current = current[int(part)]
            elif isinstance(current, dict):
                current = current[part]
            else:
                raise SourceError("JSON pointer traverses a scalar")
    except (KeyError, IndexError) as exc:
        raise SourceError(f"JSON pointer not present: {path}") from exc
    return current


def strict_json(text: str) -> Any:
    """Keep evidence unambiguous: reject duplicate keys and non-finite numbers."""
    def pairs(items: list[tuple[str, Any]]) -> dict:
        result = {}
        for key, value in items:
            if key in result:
                raise SourceError(f"Duplicate JSON evidence key: {key}")
            result[key] = value
        return result

    def nonfinite(value: str) -> None:
        raise SourceError(f"Non-finite JSON evidence value: {value}")

    return json.loads(text, object_pairs_hook=pairs, parse_constant=nonfinite)


def source_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(line, str) for line in value):
        return "".join(value)
    raise SourceError("Source must be a string or an array of strings")


def local_name(name: str, notebook_root: str | None = None) -> str:
    """Map only an explicitly selected notebook root into the fresh output tree."""
    if not isinstance(name, str) or not name or any(c in name for c in "\\\x00\r\n${}"):
        raise SourceError("Output path must be a literal POSIX filename")
    path = PurePosixPath(name)
    if ".." in path.parts:
        raise SourceError("Output path escapes the new source package")
    if path.is_absolute():
        if notebook_root is None:
            raise SourceError("Absolute notebook path requires --notebook-root")
        root = PurePosixPath(notebook_root)
        if not root.is_absolute() or ".." in root.parts:
            raise SourceError("Notebook root must be an absolute literal POSIX path")
        try:
            path = path.relative_to(root)
        except ValueError as exc:
            raise SourceError("Output path is outside the declared notebook root") from exc
    if not path.parts or path.parts[0] == "provenance":
        raise SourceError("Empty path or reserved provenance directory")
    return str(path)


def notebook_files(notebook: Any, *, notebook_root: str | None = None,
                   code_cells: list[int] | None = None,
                   entrypoint: str = "main.py") -> tuple[dict[str, bytes], list[dict], list[int]]:
    if not isinstance(notebook, dict) or notebook.get("nbformat") != 4 or not isinstance(notebook.get("cells"), list):
        raise SourceError("Expected a version-4 notebook object")
    cells = notebook["cells"]
    files: dict[str, bytes] = {}
    writes: list[dict] = []
    omitted: list[int] = []
    if code_cells is not None:
        if not code_cells or len(set(code_cells)) != len(code_cells):
            raise SourceError("Explicit code-cell selection must be nonempty and unique")
        chunks = []
        for index in code_cells:
            if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(cells):
                raise SourceError("Code-cell index is outside this notebook")
            cell = cells[index]
            if not isinstance(cell, dict) or cell.get("cell_type") != "code":
                raise SourceError("Selected notebook cell is not code")
            text = source_text(cell.get("source"))
            # Compilation parses Python but never executes imports, calls or magics.
            try:
                compile(text, f"cell-{index}", "exec")
            except SyntaxError as exc:
                raise SourceError(f"Selected code cell {index} is not plain Python") from exc
            chunks.append(text)
            writes.append({"cell": index, "path": entrypoint, "operation": "explicit-python-concatenation",
                           "source_sha256": digest(text.encode("utf-8"))})
        files[entrypoint] = "\n\n".join(chunks).encode("utf-8")
        omitted = [i for i, cell in enumerate(cells)
                   if isinstance(cell, dict) and cell.get("cell_type") == "code" and i not in code_cells]
        return files, writes, omitted
    for index, cell in enumerate(cells):
        if not isinstance(cell, dict):
            raise SourceError(f"Notebook cell {index} is not an object")
        if cell.get("cell_type") != "code":
            continue
        text = source_text(cell.get("source"))
        lines = text.splitlines(keepends=True)
        if not lines or not lines[0].startswith("%%writefile"):
            omitted.append(index)
            continue
        try:
            words = shlex.split(lines[0])
        except ValueError as exc:
            raise SourceError(f"Malformed writefile directive in cell {index}") from exc
        if not words or words[0] != "%%writefile":
            raise SourceError(f"Unsupported cell magic in cell {index}")
        arguments = words[1:]
        append = False
        if arguments and arguments[0] in ("-a", "--append"):
            append, arguments = True, arguments[1:]
        if len(arguments) != 1 or arguments[0].startswith("-"):
            raise SourceError(f"Unsupported writefile arguments in cell {index}")
        name = local_name(arguments[0], notebook_root)
        payload = "".join(lines[1:]).encode("utf-8")
        files[name] = (files.get(name, b"") if append else b"") + payload
        writes.append({"cell": index, "path": name, "operation": "append" if append else "overwrite",
                       "source_sha256": digest(text.encode("utf-8")), "written_sha256": digest(payload)})
    if not files:
        raise SourceError("No literal %%writefile cells; select reviewed plain Python cells explicitly")
    return files, writes, omitted


def decode_payload(raw: bytes, *, input_format: str, source_pointer: str | None) -> tuple[str, Any]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SourceError("Source input is not UTF-8") from exc
    if input_format == "python" and source_pointer is None:
        return "python", text
    try:
        obj = strict_json(text)
    except (ValueError, TypeError) as exc:
        raise SourceError("Expected JSON notebook or provider response") from exc
    if source_pointer is not None:
        obj = pointer(obj, source_pointer)
        if isinstance(obj, str):
            try:
                decoded = strict_json(obj)
            except ValueError:
                decoded = None
            if isinstance(decoded, dict) and "nbformat" in decoded:
                obj = decoded
            else:
                return "python", obj
    if isinstance(obj, dict) and "nbformat" in obj:
        return "notebook", obj
    raise SourceError("Provider wrapper requires an explicit --source-pointer; no source field is guessed")


def normalize(input_path: Path, metadata_path: Path, output: Path, *,
              input_format: str = "auto", source_pointer: str | None = None,
              source_url: str | None = None, version_pointer: str | None = None,
              expected_version: str | None = None, license_pointer: str | None = None,
              licenses: list[Path] | None = None, notebook_root: str | None = None,
              code_cells: list[int] | None = None, entrypoint: str = "main.py") -> dict:
    if input_format not in ("auto", "python", "json"):
        raise SourceError("Input format must be auto, python, or json")
    raw, metadata_raw = input_path.read_bytes(), metadata_path.read_bytes()
    try:
        metadata = strict_json(metadata_raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise SourceError("Metadata evidence must be UTF-8 JSON") from exc
    if not isinstance(metadata, dict):
        raise SourceError("Metadata evidence must be an object")
    name = local_name(entrypoint)
    if input_format == "auto":
        input_format = "python" if input_path.suffix.lower() == ".py" else "json"
    kind, payload = decode_payload(raw, input_format=input_format, source_pointer=source_pointer)
    if kind == "python":
        if code_cells is not None:
            raise SourceError("Code-cell selection requires a notebook")
        files = {name: payload.encode("utf-8")}
        writes, omitted = [{"path": name, "operation": "decoded-python-source"}], []
    else:
        files, writes, omitted = notebook_files(payload, notebook_root=notebook_root,
                                                code_cells=code_cells, entrypoint=name)
    if name not in files:
        raise SourceError(f"Entrypoint {name} was not emitted; no entrypoint is invented")
    for path, data in files.items():
        if any(other.startswith(path + "/") for other in files):
            raise SourceError("File/directory collision in extracted outputs")
        if path.endswith(".py"):
            try:
                compile(data, path, "exec")
            except (SyntaxError, ValueError) as exc:
                raise SourceError(f"Extracted Python does not parse: {path}") from exc
    actual_version = None
    if version_pointer is not None:
        actual_version = pointer(metadata, version_pointer)
        if isinstance(actual_version, bool) or not isinstance(actual_version, (str, int)):
            raise SourceError("Version field must be a string or integer, not a title or object")
    version_status = "UNCOMPARED"
    if expected_version is not None:
        version_status = "MISSING" if actual_version is None else ("MATCH" if str(actual_version) == str(expected_version) else "MISMATCH")
    license_observed = pointer(metadata, license_pointer) if license_pointer is not None else None
    evidence_files = {"provenance/SOURCE.raw": raw, "provenance/METADATA.json": metadata_raw}
    license_records = []
    for number, path in enumerate(licenses or []):
        data = path.read_bytes()
        target = f"provenance/licenses/{number:02d}-{path.name}"
        evidence_files[target] = data
        license_records.append({"path": target, "bytes": len(data), "sha256": digest(data)})
    manifest = {"schema": SCHEMA, "entrypoint": name, "input_kind": kind,
                "source_url": source_url, "input_sha256": digest(raw), "metadata_sha256": digest(metadata_raw),
                "source_pointer": source_pointer, "notebook_root": notebook_root,
                "version": {"pointer": version_pointer, "expected": expected_version,
                            "observed": actual_version, "comparison": version_status,
                            "meaning": "field comparison only; URL/title is not version evidence"},
                "license": {"pointer": license_pointer, "observed": license_observed, "files": license_records,
                            "meaning": "preserved evidence, not an inferred license or legal determination"},
                "writes": writes, "unexecuted_code_cells": omitted,
                "files": {path: {"bytes": len(data), "sha256": digest(data)} for path, data in sorted(files.items())},
                "execution_performed": False, "runtime_dependency_completeness": "UNMEASURED",
                "generator_sha256": digest(Path(__file__).read_bytes())}
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"Use a fresh output directory: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".source-normalize-", dir=output.parent))
    try:
        for path, data in {**files, **evidence_files, "provenance/MANIFEST.json": canonical(manifest)}.items():
            target = temporary / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        # Reserve the destination exclusively; rename() alone can replace an
        # empty directory created by another process between check and rename.
        output.mkdir()
        try:
            for child in temporary.iterdir():
                os.rename(child, output / child.name)
        except BaseException:
            shutil.rmtree(output)
            raise
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--format", choices=("auto", "python", "json"), default="auto", dest="input_format")
    parser.add_argument("--source-pointer")
    parser.add_argument("--source-url")
    parser.add_argument("--version-pointer")
    parser.add_argument("--expected-version")
    parser.add_argument("--license-pointer")
    parser.add_argument("--license", action="append", type=Path, default=[], dest="licenses")
    parser.add_argument("--notebook-root")
    parser.add_argument("--code-cell", action="append", type=int, dest="code_cells")
    parser.add_argument("--entrypoint", default="main.py")
    args = vars(parser.parse_args())
    args["input_path"] = args.pop("input")
    args["metadata_path"] = args.pop("metadata")
    try:
        manifest = normalize(**args)
    except (SourceError, OSError) as exc:
        parser.exit(2, f"NORMALIZE_ERROR: {exc}\n")
    print(json.dumps({"output": str(args["output"]), "entrypoint": manifest["entrypoint"],
                      "files": len(manifest["files"]), "version": manifest["version"]["comparison"],
                      "execution_performed": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
