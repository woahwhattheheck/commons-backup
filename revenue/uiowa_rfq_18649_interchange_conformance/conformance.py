"""Independent JSON/CSV conformance and source-confirmed legacy recovery.

The operator-selected codec is Python code: load only a trusted local module.
No network, service access, assessment scoring or authenticity verification.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import importlib.util
import io
import json
import math
import sys
import tempfile
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any

CANONICAL_FORMAT = "uiowa-json-interchange/v1"
LEGACY_HEADER = ["pointer", "type", "value", "presence"]
MAX_BYTES = 16 * 1024 * 1024


class CheckError(ValueError):
    """Input cannot be interpreted without unsupported assumptions."""


def _validate(value: Any, depth: int = 0) -> None:
    if depth > 100:
        raise CheckError("reference nesting exceeds 100")
    if type(value) is dict:
        for key, child in value.items():
            if type(key) is not str:
                raise CheckError("object keys must be strings")
            key.encode("utf-8")
            _validate(child, depth + 1)
    elif type(value) is list:
        for child in value:
            _validate(child, depth + 1)
    elif type(value) is str:
        value.encode("utf-8")
    elif type(value) is float:
        if not math.isfinite(value):
            raise CheckError("non-finite number")
    elif value is not None and type(value) not in (bool, int):
        raise CheckError("not a JSON value")


def semantic_text(value: Any) -> str:
    _validate(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def same_json(left: Any, right: Any) -> bool:
    """Object order is immaterial; number types, signed zero and text are exact."""
    return semantic_text(left) == semantic_text(right)


def strict_json(raw: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise CheckError(f"duplicate JSON key: {key!r}")
            result[key] = value
        return result

    def constant(value: str) -> Any:
        raise CheckError(f"non-finite JSON constant: {value}")

    def exact_float(token: str) -> float:
        value = float(token)
        if not math.isfinite(value) or Decimal(repr(value)) != Decimal(token):
            raise CheckError("decimal token would change value in the supported float representation")
        return value

    try:
        value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=pairs,
                           parse_constant=constant, parse_float=exact_float)
        _validate(value)
        return value
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise CheckError(str(exc)) from exc


def bounded_bytes(path: Path) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise CheckError(f"input exceeds {MAX_BYTES} bytes: {path.name}")
    return data


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_identity(path: Path) -> dict[str, Any]:
    data = bounded_bytes(path)
    return {"name": path.name, "bytes": len(data), "sha256": digest(data),
            "git_blob": hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()}


def load_codec(path: Path) -> tuple[ModuleType, dict[str, Any]]:
    """Execute exactly the bytes whose identity is returned, not a later reread."""
    data = bounded_bytes(path)
    identity = {"name": path.name, "bytes": len(data), "sha256": digest(data),
                "git_blob": hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()}
    name = "_uiowa_codec_" + identity["sha256"][:16]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None:
        raise CheckError("cannot construct codec module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        exec(compile(data, str(path), "exec"), module.__dict__)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    for attr in ("to_rows", "from_rows", "write_csv", "read_csv"):
        if not callable(getattr(module, attr, None)):
            raise CheckError(f"codec missing required callable {attr}")
    return module, identity


def documents(fixture: Any) -> list[tuple[str, Any]]:
    return [
        ("fixture", fixture), ("root-null", None), ("root-scalar", "root"),
        ("root-array", [False, 1, 1.0, -0.0, [], {}]),
        ("empty-containers", {"object": {}, "array": []}),
        ("empty-key-sibling", {"": "blank", "id": "retained"}),
        ("numeric-object", {"0": "finding", "1": "source"}),
        ("nested-numeric-object", {"evidence": {"01": "locator", "2": "note"}}),
        ("escaped-keys", {"a/b": {"~": {"": "note"}}, "a~1b": "distinct"}),
        ("unicode-distinct", {"é": "composed", "e\u0301": "decomposed", "公式": "資料"}),
        ("presence", {"empty": "", "null": None, "false": False, "zero": 0}),
        ("number-types", {"integer": 1, "float": 1.0, "positive": 0.0, "negative": -0.0}),
        ("line-endings", {"note": "A\rB\r\nC\nD\tE\u0007"}),
        ("large-note", {"note": "x" * 140_000}),
        ("formula-text", {"=key": "=SUM(A1:A2)", "note": "+1\n-2\n@name"}),
    ]


def audit(codec: ModuleType, identity: dict[str, Any], fixture: Any) -> dict[str, Any]:
    checks: list[dict[str, str]] = []

    def check(name: str, action: Any) -> None:
        try:
            action()
        except Exception as exc:
            checks.append({"id": name, "status": "FAIL", "detail": f"{type(exc).__name__}: {exc}"[:300]})
        else:
            checks.append({"id": name, "status": "PASS", "detail": "observed expected result"})

    def roundtrip(document: Any, csv_path: Path | None = None) -> None:
        before = semantic_text(document)
        if csv_path is None:
            rows = codec.to_rows(document)
            rows_before = copy.deepcopy(rows)
            restored = codec.from_rows(rows)
            if rows != rows_before:
                raise CheckError("decoder mutated supplied transport rows")
        else:
            codec.write_csv(document, csv_path)
            restored = codec.read_csv(csv_path)
        if semantic_text(document) != before:
            raise CheckError("codec mutated original document")
        if not same_json(document, restored):
            raise CheckError("JSON meaning changed (including exact types, keys or text)")

    with tempfile.TemporaryDirectory(prefix="uiowa-conformance-") as directory:
        for index, (name, document) in enumerate(documents(fixture)):
            check("rows/" + name, lambda d=document: roundtrip(d))
            check("csv/" + name, lambda d=document, i=index: roundtrip(d, Path(directory) / f"{i}.csv"))

    def reject(rows: Any) -> None:
        try:
            codec.from_rows(rows)
        except ValueError:
            return
        raise CheckError("malformed transport accepted instead of a ValueError diagnostic")

    original = codec.to_rows({"a": "one", "b": "two"})
    if getattr(codec, "FORMAT", None) == CANONICAL_FORMAT:
        duplicate = copy.deepcopy(original)
        duplicate[-1][0] = duplicate[-2][0]
        corrupt_type = copy.deepcopy(original)
        corrupt_type[-1][1] = "integer"
    else:
        duplicate = copy.deepcopy(original)
        duplicate[-1]["pointer"] = duplicate[-2]["pointer"]
        corrupt_type = copy.deepcopy(original)
        corrupt_type[-1]["type"] = "integer"
        corrupt_type[-1]["presence"] = "null"
    for name, rows in (("duplicate-member", duplicate), ("type-disagreement", corrupt_type),
                       ("missing-node", original[:-1]), ("extra-node", original + [original[-1]])):
        check("reject/" + name, lambda r=rows: reject(r))

    passed = sum(item["status"] == "PASS" for item in checks)
    return {"schema": "uiowa.interchange.conformance.v1", "authority": "FORMAT_TESTS_ONLY",
            "source": identity, "fixture_semantic_sha256": digest(semantic_text(fixture).encode()),
            "scope": "JSON node and CSV transport only; not XLSX, DOCX, PDF, UI, authenticity or assessment validity",
            "counts": {"passed": passed, "failed": len(checks) - passed, "total": len(checks)},
            "checks": checks}


def expected_legacy_rows(document: Any) -> list[list[str]]:
    """Verify the old published encoding against an original; never decode it.

    This matches legacy transport blob 7c43550f8fcb99cb5697dca3e16cf89ded1a46fd.
    The original object order is part of this conservative recovery contract.
    """
    _validate(document)
    rows: list[list[str]] = [LEGACY_HEADER.copy()]

    def walk(node: Any, pointer: str) -> None:
        if type(node) in (dict, list):
            if not node:
                rows.append([pointer or "/", "object" if type(node) is dict else "array", "", "empty"])
            elif type(node) is dict:
                for key, child in node.items():
                    walk(child, pointer + "/" + key.replace("~", "~0").replace("/", "~1"))
            else:
                for i, child in enumerate(node):
                    walk(child, pointer + "/" + str(i))
            return
        kind = {str: "string", int: "integer", float: "float", bool: "bool", type(None): "null"}[type(node)]
        value = "" if node is None else ("true" if node is True else "false" if node is False else str(node))
        presence = "null" if node is None else "empty" if node == "" else "present"
        rows.append([pointer or "/", kind, value, presence])

    walk(document, "")
    return rows


def recover(codec: ModuleType, identity: dict[str, Any], reference_path: Path,
            legacy_path: Path, destination: Path) -> dict[str, Any]:
    if getattr(codec, "FORMAT", None) != CANONICAL_FORMAT:
        raise CheckError("recovery requires the canonical explicit-node v1 codec")
    reference_raw, legacy_raw = bounded_bytes(reference_path), bounded_bytes(legacy_path)
    document = strict_json(reference_raw)
    previous = csv.field_size_limit()
    try:
        csv.field_size_limit(MAX_BYTES)
        actual = list(csv.reader(io.StringIO(legacy_raw.decode("utf-8-sig"), newline=""), strict=True))
    except (csv.Error, UnicodeError) as exc:
        raise CheckError(f"legacy CSV unreadable: {exc}") from exc
    finally:
        csv.field_size_limit(previous)
    expected = expected_legacy_rows(document)
    if actual != expected:
        mismatch = next((i for i, (a, b) in enumerate(zip(actual, expected), 1) if a != b),
                        min(len(actual), len(expected)) + 1)
        raise CheckError(f"legacy/reference mismatch at logical CSV row {mismatch}; no recovery written")
    rows = codec.to_rows(document)
    if not same_json(document, codec.from_rows(copy.deepcopy(rows))):
        raise CheckError("canonical codec failed independent type-sensitive verification")
    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator="\r\n").writerows(rows)
    output = buffer.getvalue().encode("utf-8")
    decoded_rows = list(csv.reader(io.StringIO(output.decode("utf-8"), newline=""), strict=True))
    if not same_json(document, codec.from_rows(decoded_rows)):
        raise CheckError("serialized CSV failed independent type-sensitive verification")
    # Only now create the destination. Existing inputs/exports are never replaced.
    with destination.open("xb") as stream:
        stream.write(output)
    return {"schema": "uiowa.interchange.recovery.v1", "status": "SOURCE_CONFIRMED_FORMAT_MIGRATION",
            "authority": "NO_AUTHENTICITY_OR_ASSESSMENT_ASSERTION", "codec": identity,
            "original_json_sha256": digest(reference_raw), "legacy_csv_sha256": digest(legacy_raw),
            "new_csv_sha256": digest(output), "semantic_sha256": digest(semantic_text(document).encode()),
            "legacy_rows": len(actual) - 1, "new_rows": len(rows) - 2,
            "limitation": "Original JSON is required; matching rows cannot establish which original produced an ambiguous legacy file."}


def markdown(report: dict[str, Any]) -> str:
    count = report["counts"]
    lines = ["# Independent interchange conformance", "", report["scope"], "",
             f"Codec Git blob: `{report['source']['git_blob']}`", "",
             f"Observed: {count['passed']} PASS / {count['failed']} FAIL / {count['total']} checks.", "",
             "| Check | Result | Observation |", "|---|---|---|"]
    for item in report["checks"]:
        lines.append("| " + " | ".join(item[key].replace("|", "\\|").replace("\n", " ") for key in ("id", "status", "detail")) + " |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    run = sub.add_parser("audit")
    run.add_argument("--codec", required=True, type=Path)
    run.add_argument("--fixture", type=Path, default=Path(__file__).with_name("synthetic.json"))
    migration = sub.add_parser("recover")
    migration.add_argument("--codec", required=True, type=Path)
    migration.add_argument("--original-json", required=True, type=Path)
    migration.add_argument("--legacy-csv", required=True, type=Path)
    migration.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        codec, identity = load_codec(args.codec)
        if args.action == "audit":
            report = audit(codec, identity, strict_json(bounded_bytes(args.fixture)))
            status = int(report["counts"]["failed"] > 0)
        else:
            report = recover(codec, identity, args.original_json, args.legacy_csv, args.destination)
            status = 0
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
        return status
    except (OSError, ValueError, UnicodeError, RecursionError) as exc:
        print(f"interchange-conformance: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
