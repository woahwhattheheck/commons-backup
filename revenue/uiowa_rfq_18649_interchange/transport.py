"""Lossless JSON transport for assessment evidence; standard library only.

CSV cells use explicit p:/j: prefixes. No cell is interpreted as a formula,
number, date, or missing value by this codec. This is not an authority verifier.
"""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal
import hashlib
import io
import json
import math
from pathlib import Path
from typing import Any, Iterable

FORMAT = "uiowa-json-interchange/v1"
HEADER = ["pointer", "kind", "value"]
MAX_DEPTH = 128
CSV_FIELD_LIMIT = 16 * 1024 * 1024


class InterchangeError(ValueError):
    """The supplied transport cannot be decoded without changing its meaning."""


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InterchangeError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _constant(value: str) -> Any:
    raise InterchangeError(f"non-finite JSON constant: {value}")


def _float_token(token: str) -> float:
    """Reject source precision loss before a binary float can hide it.

    Compare decimal numeric values before/after Python's JSON float rendering;
    lexical trailing zeroes/exponent spelling are not source-byte identity.
    """
    value = float(token)
    if not math.isfinite(value):
        raise InterchangeError("non-finite JSON number")
    if Decimal(token) != Decimal(repr(value)):
        raise InterchangeError(
            "JSON floating token would lose precision; retain it as explicit decimal text")
    return value


def _check(value: Any, depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        raise InterchangeError(f"JSON nesting exceeds supported depth {MAX_DEPTH}")
    if type(value) is dict:
        for key, child in value.items():
            if type(key) is not str:
                raise InterchangeError("JSON object keys must be strings")
            key.encode("utf-8", errors="strict")
            _check(child, depth + 1)
    elif type(value) is list:
        for child in value:
            _check(child, depth + 1)
    elif type(value) is str:
        value.encode("utf-8", errors="strict")
    elif type(value) is float:
        if not math.isfinite(value):
            raise InterchangeError("non-finite JSON number")
    elif value is not None and type(value) not in (bool, int):
        raise InterchangeError(f"not a JSON value: {type(value).__name__}")


def loads(text: str) -> Any:
    """Read JSON with duplicate-key, non-finite and Unicode-scalar checks."""
    try:
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant,
                           parse_float=_float_token)
        _check(value)
        return value
    except (ValueError, UnicodeError, RecursionError, OverflowError) as exc:
        raise InterchangeError(str(exc)) from exc


def canonical_json(value: Any) -> str:
    """Deterministic semantic receipt; not the source file's byte identity."""
    try:
        _check(value)
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise InterchangeError(str(exc)) from exc


def document_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _literal(value: Any) -> str:
    return "j:" + json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                              allow_nan=False)


def _escape(part: str) -> str:
    return part.replace("~", "~0").replace("/", "~1")


def _unescape(part: str) -> str:
    value = part.replace("~1", "/").replace("~0", "~")
    if _escape(value) != part:
        raise InterchangeError(f"non-canonical JSON pointer segment: {part!r}")
    return value


def to_rows(document: Any) -> list[list[str]]:
    """Serialize every JSON node in preorder, retaining null/empty/absent states.

    Object and array values are child counts. Leaf values are strict JSON
    literals. Object member order is retained; receipts ignore member order.
    """
    canonical_json(document)
    rows = [[FORMAT, "", ""], HEADER.copy()]

    def visit(value: Any, pointer: str) -> None:
        kind = {dict: "object", list: "array", str: "string", int: "integer",
                float: "float", bool: "boolean", type(None): "null"}[type(value)]
        rows.append(["p:" + json.dumps(pointer, ensure_ascii=False), kind,
                     _literal(len(value) if kind in ("object", "array") else value)])
        if kind == "object":
            for key, child in value.items():
                visit(child, pointer + "/" + _escape(key))
        elif kind == "array":
            for i, child in enumerate(value):
                visit(child, pointer + "/" + str(i))

    visit(document, "")
    return rows


def from_rows(rows: Iterable[Iterable[str]]) -> Any:
    """Decode typed rows with one lookahead, rejecting missing/reordered/extra nodes.

    Validate rows as they arrive instead of retaining the complete transport
    table alongside the reconstructed document.
    """
    table = iter(rows)

    def next_row() -> list[str] | None:
        try:
            row = next(table)
        except StopIteration:
            return None
        if type(row) is not list:
            row = list(row)
        if (len(row) != 3 or type(row[0]) is not str
                or type(row[1]) is not str or type(row[2]) is not str):
            raise InterchangeError("every transport row must contain exactly three text cells")
        return row

    if next_row() != [FORMAT, "", ""] or next_row() != HEADER:
        raise InterchangeError("missing or unsupported interchange header")
    current = next_row()
    if current is None:
        raise InterchangeError("missing or unsupported interchange header")

    def parse_row(row: list[str]) -> tuple[str, str, Any]:
        p, kind, literal = row
        if not p.startswith("p:") or not literal.startswith("j:"):
            raise InterchangeError("pointer/value cells require p:/j: prefixes")
        pointer, value = loads(p[2:]), loads(literal[2:])
        if type(pointer) is not str:
            raise InterchangeError("pointer must be a JSON string")
        return pointer, kind, value

    def take(expected: str, depth: int,
             decoded: tuple[str, str, Any] | None = None) -> Any:
        nonlocal current
        if depth > MAX_DEPTH:
            raise InterchangeError(f"JSON nesting exceeds supported depth {MAX_DEPTH}")
        if current is None:
            raise InterchangeError(f"missing node at {expected!r}")
        pointer, kind, value = parse_row(current) if decoded is None else decoded
        current = next_row()
        if pointer != expected:
            raise InterchangeError(f"expected pointer {expected!r}; got {pointer!r}")
        if kind in ("object", "array"):
            if type(value) is not int or value < 0:
                raise InterchangeError(f"invalid child count at {pointer!r}")
            children: Any = {} if kind == "object" else []
            for i in range(value):
                if kind == "array":
                    children.append(take(pointer + "/" + str(i), depth + 1))
                    continue
                if current is None:
                    raise InterchangeError(f"missing object child at {pointer!r}")
                child_row = parse_row(current)
                next_pointer = child_row[0]
                prefix = pointer + "/"
                if not next_pointer.startswith(prefix):
                    raise InterchangeError(f"object child not under {pointer!r}")
                segment = next_pointer[len(prefix):]
                if "/" in segment:
                    raise InterchangeError("object child must be an immediate descendant")
                key = _unescape(segment)
                if key in children:
                    raise InterchangeError(f"duplicate object member at {next_pointer!r}")
                children[key] = take(next_pointer, depth + 1, child_row)
            return children
        types = {"string": str, "integer": int, "float": float,
                 "boolean": bool, "null": type(None)}
        if kind not in types or type(value) is not types[kind]:
            raise InterchangeError(f"kind/literal mismatch at {pointer!r}: {kind}")
        return value

    result = take("", 0)
    if current is not None:
        raise InterchangeError("extra rows after the complete document")
    canonical_json(result)
    return result


def write_csv(document: Any, path: str | Path) -> None:
    """Create a standalone UTF-8 CSV; refuse to overwrite an existing file."""
    rows = to_rows(document)
    if any(len(cell) > CSV_FIELD_LIMIT for row in rows for cell in row):
        raise InterchangeError("CSV field exceeds supported 16 Mi characters; use JSON")
    with Path(path).open("x", encoding="utf-8", newline="") as stream:
        csv.writer(stream, lineterminator="\r\n").writerows(rows)


def read_csv(path: str | Path) -> Any:
    # The stdlib CSV parser defaults to 128 KiB per field. The interchange
    # format intentionally permits larger notes; keep the change scoped.
    previous = csv.field_size_limit()
    try:
        csv.field_size_limit(CSV_FIELD_LIMIT)
        with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
            return from_rows(csv.reader(stream, strict=True))
    except (csv.Error, UnicodeError) as exc:
        raise InterchangeError(str(exc)) from exc
    finally:
        csv.field_size_limit(previous)


def csv_text(document: Any) -> str:
    stream = io.StringIO(newline="")
    csv.writer(stream, lineterminator="\r\n").writerows(to_rows(document))
    return stream.getvalue()


def read_json(path: str | Path) -> Any:
    return loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(document: Any, path: str | Path) -> None:
    text = canonical_json(document) + "\n"
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


# Public names retained from merged PR #16197. Legacy leaf-only CSV is not
# guessed: import it only via the source-confirmed recovery companion.
TransportError = InterchangeError
load_json = read_json


def dump_json(document: Any, path: str | Path) -> Path:
    write_json(document, path)
    return Path(path)


def write_xlsx(document: Any, path: str | Path) -> Path:
    try:
        from .workbook import write_xlsx as writer
    except ImportError:
        from workbook import write_xlsx as writer
    writer(document, path)
    return Path(path)


def read_xlsx(path: str | Path) -> Any:
    try:
        from .workbook import read_xlsx as reader
    except ImportError:
        from workbook import read_xlsx as reader
    return reader(path)


def project_docx(path: str | Path) -> dict[str, Any]:
    try:
        from .projection_io import project_docx as reader
    except ImportError:
        from projection_io import project_docx as reader
    return reader(path)


def project_pdf(path: str | Path) -> dict[str, Any]:
    try:
        from .projection_io import project_pdf as reader
    except ImportError:
        from projection_io import project_pdf as reader
    return reader(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("export", "import", "compare"))
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            document = read_json(args.source)
            write_csv(document, args.destination)
        elif args.command == "import":
            document = read_csv(args.source)
            write_json(document, args.destination)
        else:
            document = read_json(args.source)
            if canonical_json(document) != canonical_json(read_json(args.destination)):
                raise InterchangeError("documents differ (including JSON types)")
        print(json.dumps({"result": "PASS", "document_sha256": document_sha256(document),
                          "authority": "FORMAT_INTEGRITY_ONLY"}))
        return 0
    except (OSError, InterchangeError) as exc:
        parser.exit(2, f"interchange: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
