#!/usr/bin/env python3
"""Patch exactly one JSON object while preserving every byte outside its span.

The tool is intentionally conservative. It binds both the full input file and the
raw target object bytes by SHA-256, resolves the target with RFC 6901 JSON Pointer,
rejects duplicate object keys, and proves that the patched document differs
semantically only at the selected target.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


class PatchError(ValueError):
    """Raised when a requested patch cannot be proven safe."""


@dataclass(frozen=True)
class Node:
    value: Any
    start: int
    end: int


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _reject_nonstandard_constant(value: str) -> Any:
    raise PatchError(f"non-standard JSON constant {value!r} is not allowed")


def _decode_pointer(pointer: str) -> tuple[str, ...]:
    if pointer == "":
        return ()
    if not pointer.startswith("/"):
        raise PatchError("JSON Pointer must be empty or begin with '/'")
    out: list[str] = []
    for raw in pointer[1:].split("/"):
        i = 0
        decoded: list[str] = []
        while i < len(raw):
            if raw[i] != "~":
                decoded.append(raw[i])
                i += 1
                continue
            if i + 1 >= len(raw) or raw[i + 1] not in "01":
                raise PatchError("invalid JSON Pointer escape")
            decoded.append("~" if raw[i + 1] == "0" else "/")
            i += 2
        out.append("".join(decoded))
    return tuple(out)


class _SpanParser:
    def __init__(self, text: str):
        self.text = text
        self.decoder = json.JSONDecoder(parse_constant=_reject_nonstandard_constant)
        self.nodes: dict[tuple[str, ...], Node] = {}

    def parse(self) -> tuple[Any, dict[tuple[str, ...], Node]]:
        pos = self._skip_ws(0)
        value, end = self._value(pos, ())
        tail = self._skip_ws(end)
        if tail != len(self.text):
            raise PatchError(f"unexpected trailing data at character {tail}")
        return value, self.nodes

    def _skip_ws(self, pos: int) -> int:
        text = self.text
        while pos < len(text) and text[pos] in " \t\r\n":
            pos += 1
        return pos

    def _value(self, pos: int, path: tuple[str, ...]) -> tuple[Any, int]:
        if pos >= len(self.text):
            raise PatchError("unexpected end of JSON")
        start = pos
        ch = self.text[pos]
        if ch == "{":
            value, end = self._object(pos, path)
        elif ch == "[":
            value, end = self._array(pos, path)
        else:
            try:
                value, end = self.decoder.raw_decode(self.text, pos)
            except json.JSONDecodeError as exc:
                raise PatchError(str(exc)) from exc
        self.nodes[path] = Node(value=value, start=start, end=end)
        return value, end

    def _string(self, pos: int) -> tuple[str, int]:
        try:
            value, end = self.decoder.raw_decode(self.text, pos)
        except json.JSONDecodeError as exc:
            raise PatchError(str(exc)) from exc
        if not isinstance(value, str):
            raise PatchError(f"expected object key string at character {pos}")
        return value, end

    def _object(self, pos: int, path: tuple[str, ...]) -> tuple[dict[str, Any], int]:
        assert self.text[pos] == "{"
        pos = self._skip_ws(pos + 1)
        obj: dict[str, Any] = {}
        if pos < len(self.text) and self.text[pos] == "}":
            return obj, pos + 1
        while True:
            if pos >= len(self.text) or self.text[pos] != '"':
                raise PatchError(f"expected object key at character {pos}")
            key, pos = self._string(pos)
            if key in obj:
                raise PatchError(f"duplicate object key {key!r} is ambiguous")
            pos = self._skip_ws(pos)
            if pos >= len(self.text) or self.text[pos] != ":":
                raise PatchError(f"expected ':' after object key {key!r}")
            pos = self._skip_ws(pos + 1)
            value, pos = self._value(pos, path + (key,))
            obj[key] = value
            pos = self._skip_ws(pos)
            if pos >= len(self.text):
                raise PatchError("unexpected end of object")
            if self.text[pos] == "}":
                return obj, pos + 1
            if self.text[pos] != ",":
                raise PatchError(f"expected ',' or '}}' at character {pos}")
            pos = self._skip_ws(pos + 1)

    def _array(self, pos: int, path: tuple[str, ...]) -> tuple[list[Any], int]:
        assert self.text[pos] == "["
        pos = self._skip_ws(pos + 1)
        arr: list[Any] = []
        if pos < len(self.text) and self.text[pos] == "]":
            return arr, pos + 1
        index = 0
        while True:
            value, pos = self._value(pos, path + (str(index),))
            arr.append(value)
            index += 1
            pos = self._skip_ws(pos)
            if pos >= len(self.text):
                raise PatchError("unexpected end of array")
            if self.text[pos] == "]":
                return arr, pos + 1
            if self.text[pos] != ",":
                raise PatchError(f"expected ',' or ']' at character {pos}")
            pos = self._skip_ws(pos + 1)


def _replace_semantic(root: Any, path: tuple[str, ...], replacement: dict[str, Any]) -> Any:
    if not path:
        return replacement
    root_copy = copy.deepcopy(root)
    parent = root_copy
    for segment in path[:-1]:
        if isinstance(parent, dict):
            if segment not in parent:
                raise PatchError(f"pointer segment {segment!r} does not exist")
            parent = parent[segment]
        elif isinstance(parent, list):
            if not segment.isdigit() or (segment != "0" and segment.startswith("0")):
                raise PatchError(f"invalid array index {segment!r}")
            idx = int(segment)
            if idx >= len(parent):
                raise PatchError(f"array index {idx} out of range")
            parent = parent[idx]
        else:
            raise PatchError(f"pointer descends through scalar at {segment!r}")
    leaf = path[-1]
    if isinstance(parent, dict):
        if leaf not in parent:
            raise PatchError(f"pointer segment {leaf!r} does not exist")
        parent[leaf] = replacement
    elif isinstance(parent, list):
        if not leaf.isdigit() or (leaf != "0" and leaf.startswith("0")):
            raise PatchError(f"invalid array index {leaf!r}")
        idx = int(leaf)
        if idx >= len(parent):
            raise PatchError(f"array index {idx} out of range")
        parent[idx] = replacement
    else:
        raise PatchError("pointer parent is a scalar")
    return root_copy


def _parse_replacement(raw: bytes) -> tuple[dict[str, Any], str]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PatchError("replacement is not UTF-8") from exc
    value, nodes = _SpanParser(text).parse()
    if not isinstance(value, dict):
        raise PatchError("replacement JSON value must be an object")
    # The parser above already rejects duplicate keys at every depth.
    return value, text[nodes[()].start : nodes[()].end]


def patch_json_object(
    source: bytes,
    *,
    pointer: str,
    expected_file_sha256: str,
    expected_target_sha256: str,
    replacement: bytes,
) -> tuple[bytes, dict[str, Any]]:
    """Return patched bytes and a machine-readable proof receipt."""
    actual_file_sha = sha256_bytes(source)
    if actual_file_sha != expected_file_sha256.lower():
        raise PatchError(
            f"file SHA-256 mismatch: expected {expected_file_sha256.lower()}, got {actual_file_sha}"
        )
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PatchError("source is not UTF-8") from exc

    root, nodes = _SpanParser(text).parse()
    path = _decode_pointer(pointer)
    if path not in nodes:
        raise PatchError(f"JSON Pointer {pointer!r} does not resolve")
    target = nodes[path]
    if not isinstance(target.value, dict):
        raise PatchError("target JSON value must be an object")

    # Character offsets and byte offsets coincide only for ASCII. Convert safely.
    prefix = text[: target.start].encode("utf-8")
    target_bytes = text[target.start : target.end].encode("utf-8")
    suffix = text[target.end :].encode("utf-8")
    actual_target_sha = sha256_bytes(target_bytes)
    if actual_target_sha != expected_target_sha256.lower():
        raise PatchError(
            f"target SHA-256 mismatch: expected {expected_target_sha256.lower()}, got {actual_target_sha}"
        )

    replacement_value, replacement_text = _parse_replacement(replacement)
    replacement_bytes = replacement_text.encode("utf-8")
    patched = prefix + replacement_bytes + suffix
    if patched == source:
        raise PatchError("replacement produces a byte-identical document")

    patched_root, _ = _SpanParser(patched.decode("utf-8")).parse()
    expected_root = _replace_semantic(root, path, replacement_value)
    if patched_root != expected_root:
        raise PatchError("patched document changed semantics outside the selected target")
    if not patched.startswith(prefix) or not patched.endswith(suffix):
        raise PatchError("byte-preservation proof failed")

    receipt = {
        "pointer": pointer,
        "before_sha256": actual_file_sha,
        "after_sha256": sha256_bytes(patched),
        "target_before_sha256": actual_target_sha,
        "target_after_sha256": sha256_bytes(replacement_bytes),
        "prefix_sha256": sha256_bytes(prefix),
        "suffix_sha256": sha256_bytes(suffix),
        "prefix_bytes": len(prefix),
        "target_before_bytes": len(target_bytes),
        "target_after_bytes": len(replacement_bytes),
        "suffix_bytes": len(suffix),
        "target_start_byte": len(prefix),
        "target_end_byte": len(prefix) + len(target_bytes),
        "outside_target_bytes_preserved": True,
    }
    return patched, receipt


def _paths_alias(left: Path, right: Path) -> bool:
    try:
        if left.resolve() == right.resolve():
            return True
    except OSError:
        pass
    try:
        return left.exists() and right.exists() and os.path.samefile(left, right)
    except OSError:
        return False


def _validate_product_paths(
    source: Path,
    replacement: Path,
    output: Path,
    receipt: Path | None,
) -> None:
    inputs = (("source", source), ("replacement", replacement))
    products = [("output", output)]
    if receipt is not None:
        products.append(("receipt", receipt))

    for product_name, product_path in products:
        for input_name, input_path in inputs:
            if _paths_alias(product_path, input_path):
                raise PatchError(
                    f"{product_name} must differ from {input_name}; "
                    "this tool never overwrites its inputs"
                )
    if receipt is not None and _paths_alias(output, receipt):
        raise PatchError("receipt must differ from output")


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("--pointer", required=True, help="RFC 6901 JSON Pointer to one object")
    p.add_argument("--expected-file-sha256", required=True)
    p.add_argument("--expected-target-sha256", required=True)
    p.add_argument("--replacement-file", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path, help="write the proven patched document to a new path")
    p.add_argument("--receipt", type=Path, help="optional JSON proof receipt")
    return p


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    _validate_product_paths(
        args.source,
        args.replacement_file,
        args.output,
        args.receipt,
    )
    source = args.source.read_bytes()
    replacement = args.replacement_file.read_bytes()
    patched, receipt = patch_json_object(
        source,
        pointer=args.pointer,
        expected_file_sha256=args.expected_file_sha256,
        expected_target_sha256=args.expected_target_sha256,
        replacement=replacement,
    )
    _write_atomic(args.output, patched)
    if args.receipt:
        payload = (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode("utf-8")
        _write_atomic(args.receipt, payload)
    else:
        print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
