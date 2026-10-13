#!/usr/bin/env python3
"""Fail-closed alignment checks between authoritative offer terms and projections.

The checker is intentionally policy-agnostic.  A small JSON spec names source
and projection documents, selects stable views from those documents, then
states the exact relations that must hold.  This keeps catalog validation from
inventing business semantics when source contracts use different shapes.

Example:

    python host/offer_contract_alignment.py --spec path/to/alignment.json

Exit codes:
  0  all rules pass
  1  one or more alignment rules fail
  2  invalid spec, unsafe path, unreadable JSON, or ambiguous selector
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "offer-contract-alignment/v1"
REPORT_VERSION = "offer-contract-alignment-report/v1"
NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
GIT_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
RULE_KINDS = {
    "equal",
    "normalized_text_equal",
    "number_equal",
    "normalized_list_equal",
    "target_subset_of_source",
    "source_subset_of_target",
    "git_blob_sha",
}


class AlignmentError(ValueError):
    pass


@dataclass(frozen=True)
class LoadedDocument:
    path: str
    resolved: Path
    value: Any
    raw: bytes


def _object_no_dupes(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise AlignmentError("duplicate JSON key: %s" % key)
        out[key] = value
    return out


def _reject_json_constant(value: str) -> None:
    raise AlignmentError("non-finite JSON number is not allowed: %s" % value)


def _load_json_bytes(raw: bytes, label: str) -> Any:
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_object_no_dupes,
            parse_float=Decimal,
            parse_constant=_reject_json_constant,
        )
    except UnicodeDecodeError as exc:
        raise AlignmentError("%s must be UTF-8 JSON" % label) from exc
    except json.JSONDecodeError as exc:
        raise AlignmentError("%s is invalid JSON: %s" % (label, exc)) from exc
    except InvalidOperation as exc:
        raise AlignmentError("%s contains a JSON number outside the supported decimal range" % label) from exc


def _safe_relative_path(root: Path, value: Any, field: str) -> tuple[str, Path]:
    if not isinstance(value, str) or not value or "\\" in value:
        raise AlignmentError("%s must be a non-empty repo-relative POSIX path" % field)
    raw = Path(value)
    if raw.is_absolute() or any(part in {"", ".", ".."} for part in value.split("/")):
        raise AlignmentError("%s must be canonical and stay below root" % field)
    try:
        root_resolved = root.resolve(strict=True)
        resolved = (root_resolved / raw).resolve(strict=True)
        resolved.relative_to(root_resolved)
    except (OSError, ValueError) as exc:
        raise AlignmentError("%s does not resolve safely below root: %s" % (field, value)) from exc
    if not resolved.is_file():
        raise AlignmentError("%s is not a file: %s" % (field, value))
    return value, resolved


def _decode_pointer_part(part: str) -> str:
    # RFC 6901 permits only ~0 and ~1 escapes. Reject dangling/unknown forms.
    out: list[str] = []
    index = 0
    while index < len(part):
        if part[index] != "~":
            out.append(part[index])
            index += 1
            continue
        if index + 1 >= len(part) or part[index + 1] not in {"0", "1"}:
            raise AlignmentError("invalid JSON Pointer escape")
        out.append("~" if part[index + 1] == "0" else "/")
        index += 2
    return "".join(out)


def _pointer(value: Any, pointer: Any, field: str) -> Any:
    if pointer == "":
        return value
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise AlignmentError("%s must be a JSON Pointer" % field)
    node = value
    for raw_part in pointer.split("/")[1:]:
        part = _decode_pointer_part(raw_part)
        if isinstance(node, dict):
            if part not in node:
                raise AlignmentError("%s does not resolve: %s" % (field, pointer))
            node = node[part]
        elif isinstance(node, list):
            if not re.fullmatch(r"0|[1-9][0-9]*", part):
                raise AlignmentError("%s has invalid array index: %s" % (field, pointer))
            index = int(part)
            if index >= len(node):
                raise AlignmentError("%s array index is out of range: %s" % (field, pointer))
            node = node[index]
        else:
            raise AlignmentError("%s crosses a scalar: %s" % (field, pointer))
    return node


def _json_selector_equal(left: Any, right: Any) -> bool:
    """Compare selector values by JSON type domains, not Python coercions."""
    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if isinstance(left, (int, Decimal)) or isinstance(right, (int, Decimal)):
        if not isinstance(left, (int, Decimal)) or not isinstance(right, (int, Decimal)):
            return False
        return Decimal(str(left)) == Decimal(str(right))
    if isinstance(left, str) or isinstance(right, str):
        return isinstance(left, str) and isinstance(right, str) and left == right
    if isinstance(left, list) or isinstance(right, list):
        return (
            isinstance(left, list)
            and isinstance(right, list)
            and len(left) == len(right)
            and all(_json_selector_equal(a, b) for a, b in zip(left, right))
        )
    if isinstance(left, dict) or isinstance(right, dict):
        return (
            isinstance(left, dict)
            and isinstance(right, dict)
            and set(left) == set(right)
            and all(_json_selector_equal(left[key], right[key]) for key in left)
        )
    return False


def _selector(document: Any, spec: Any, field: str) -> Any:
    if not isinstance(spec, dict):
        raise AlignmentError("%s must be an object" % field)
    allowed = {"document", "pointer", "match"}
    unknown = set(spec) - allowed
    if unknown:
        raise AlignmentError("%s has unknown fields: %s" % (field, ", ".join(sorted(unknown))))
    has_pointer = "pointer" in spec
    has_match = "match" in spec
    if has_pointer == has_match:
        raise AlignmentError("%s requires exactly one of pointer or match" % field)
    if has_pointer:
        return _pointer(document, spec["pointer"], field + ".pointer")

    match = spec["match"]
    if not isinstance(match, dict) or set(match) != {"collection", "field", "equals"}:
        raise AlignmentError("%s.match requires collection, field, equals" % field)
    collection = _pointer(document, match["collection"], field + ".match.collection")
    if not isinstance(collection, list):
        raise AlignmentError("%s.match.collection must resolve to an array" % field)
    key = match["field"]
    if not isinstance(key, str) or not key:
        raise AlignmentError("%s.match.field must be a non-empty string" % field)
    hits = [
        row
        for row in collection
        if isinstance(row, dict)
        and key in row
        and _json_selector_equal(row[key], match["equals"])
    ]
    if len(hits) != 1:
        raise AlignmentError("%s.match must resolve exactly one row; got %d" % (field, len(hits)))
    return hits[0]


def _normalize_text(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise AlignmentError("%s must be a string" % field)
    return " ".join(value.split()).casefold()


def _normalize_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        raise AlignmentError("%s must be an array" % field)
    normalized = [_normalize_text(item, "%s[%d]" % (field, index)) for index, item in enumerate(value)]
    if len(normalized) != len(set(normalized)):
        raise AlignmentError("%s must not contain duplicate normalized strings" % field)
    return normalized


def _decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise AlignmentError("%s must be an integer or decimal string" % field)
    try:
        out = Decimal(str(value))
    except InvalidOperation as exc:
        raise AlignmentError("%s is not a finite decimal" % field) from exc
    if not out.is_finite():
        raise AlignmentError("%s is not a finite decimal" % field)
    return out


def _git_blob_sha1(raw: bytes) -> str:
    header = b"blob " + str(len(raw)).encode("ascii") + b"\0"
    return hashlib.sha1(header + raw).hexdigest()


def _ref_value(views: dict[str, Any], ref: Any, field: str) -> Any:
    if not isinstance(ref, dict) or set(ref) != {"view", "pointer"}:
        raise AlignmentError("%s requires exactly view and pointer" % field)
    view = ref["view"]
    if view not in views:
        raise AlignmentError("%s references unknown view %r" % (field, view))
    return _pointer(views[view], ref["pointer"], field + ".pointer")


def _rule_result(
    rule: dict[str, Any],
    *,
    views: dict[str, Any],
    documents: dict[str, LoadedDocument],
) -> dict[str, Any]:
    rule_id = rule.get("id")
    kind = rule.get("kind")
    if not isinstance(rule_id, str) or not NAME_RE.fullmatch(rule_id):
        raise AlignmentError("rule.id must match %s" % NAME_RE.pattern)
    if kind not in RULE_KINDS:
        raise AlignmentError("rule %s has unsupported kind %r" % (rule_id, kind))

    if kind == "git_blob_sha":
        if set(rule) != {"id", "kind", "document", "target"}:
            raise AlignmentError("git_blob_sha rule %s has invalid fields" % rule_id)
        document_name = rule["document"]
        if document_name not in documents:
            raise AlignmentError("rule %s references unknown document %r" % (rule_id, document_name))
        expected = _ref_value(views, rule["target"], "rule %s.target" % rule_id)
        if not isinstance(expected, str) or not GIT_SHA1_RE.fullmatch(expected):
            raise AlignmentError("rule %s target must be a 40-character lowercase Git SHA-1" % rule_id)
        actual = _git_blob_sha1(documents[document_name].raw)
        ok = actual == expected
        return {
            "id": rule_id,
            "kind": kind,
            "ok": ok,
            "detail": "match" if ok else "git blob mismatch: expected %s, got %s" % (expected, actual),
        }

    if set(rule) != {"id", "kind", "source", "target"}:
        raise AlignmentError("rule %s has invalid fields" % rule_id)
    source = _ref_value(views, rule["source"], "rule %s.source" % rule_id)
    target = _ref_value(views, rule["target"], "rule %s.target" % rule_id)

    if kind == "equal":
        ok = source == target and type(source) is type(target)
    elif kind == "normalized_text_equal":
        ok = _normalize_text(source, "rule %s.source" % rule_id) == _normalize_text(target, "rule %s.target" % rule_id)
    elif kind == "number_equal":
        ok = _decimal(source, "rule %s.source" % rule_id) == _decimal(target, "rule %s.target" % rule_id)
    elif kind == "normalized_list_equal":
        ok = _normalize_list(source, "rule %s.source" % rule_id) == _normalize_list(target, "rule %s.target" % rule_id)
    elif kind == "target_subset_of_source":
        source_set = set(_normalize_list(source, "rule %s.source" % rule_id))
        target_set = set(_normalize_list(target, "rule %s.target" % rule_id))
        ok = target_set <= source_set
    elif kind == "source_subset_of_target":
        source_set = set(_normalize_list(source, "rule %s.source" % rule_id))
        target_set = set(_normalize_list(target, "rule %s.target" % rule_id))
        ok = source_set <= target_set
    else:  # pragma: no cover - guarded above
        raise AssertionError(kind)

    return {
        "id": rule_id,
        "kind": kind,
        "ok": ok,
        "detail": "match" if ok else "relation failed",
    }


def check_alignment(spec: Any, *, root: Path) -> dict[str, Any]:
    if not isinstance(spec, dict):
        raise AlignmentError("spec must be an object")
    if set(spec) != {"schema_version", "documents", "views", "rules"}:
        raise AlignmentError("spec fields must be schema_version, documents, views, rules")
    if spec["schema_version"] != SCHEMA_VERSION:
        raise AlignmentError("schema_version must be %s" % SCHEMA_VERSION)

    document_specs = spec["documents"]
    if not isinstance(document_specs, dict) or not document_specs:
        raise AlignmentError("documents must be a non-empty object")
    documents: dict[str, LoadedDocument] = {}
    for name, document_spec in document_specs.items():
        if not isinstance(name, str) or not NAME_RE.fullmatch(name):
            raise AlignmentError("document names must match %s" % NAME_RE.pattern)
        if not isinstance(document_spec, dict) or set(document_spec) != {"path"}:
            raise AlignmentError("documents.%s requires exactly path" % name)
        relative, resolved = _safe_relative_path(root, document_spec["path"], "documents.%s.path" % name)
        try:
            raw = resolved.read_bytes()
        except OSError as exc:
            raise AlignmentError("cannot read document %s: %s" % (relative, exc)) from exc
        documents[name] = LoadedDocument(
            path=relative,
            resolved=resolved,
            value=_load_json_bytes(raw, relative),
            raw=raw,
        )

    view_specs = spec["views"]
    if not isinstance(view_specs, dict) or not view_specs:
        raise AlignmentError("views must be a non-empty object")
    views: dict[str, Any] = {}
    for name, view_spec in view_specs.items():
        if not isinstance(name, str) or not NAME_RE.fullmatch(name):
            raise AlignmentError("view names must match %s" % NAME_RE.pattern)
        if not isinstance(view_spec, dict):
            raise AlignmentError("views.%s must be an object" % name)
        document_name = view_spec.get("document")
        if document_name not in documents:
            raise AlignmentError("views.%s references unknown document %r" % (name, document_name))
        views[name] = _selector(documents[document_name].value, view_spec, "views.%s" % name)

    rules = spec["rules"]
    if not isinstance(rules, list) or not rules:
        raise AlignmentError("rules must be a non-empty array")
    ids: set[str] = set()
    results: list[dict[str, Any]] = []
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise AlignmentError("rules[%d] must be an object" % index)
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not NAME_RE.fullmatch(rule_id):
            raise AlignmentError("rules[%d].id must match %s" % (index, NAME_RE.pattern))
        if rule_id in ids:
            raise AlignmentError("duplicate rule id: %s" % rule_id)
        ids.add(rule_id)
        results.append(_rule_result(rule, views=views, documents=documents))

    return {
        "schema_version": REPORT_VERSION,
        "ok": all(row["ok"] for row in results),
        "documents": {
            name: {
                "path": document.path,
                "git_blob_sha1": _git_blob_sha1(document.raw),
                "sha256": hashlib.sha256(document.raw).hexdigest(),
            }
            for name, document in sorted(documents.items())
        },
        "rules": results,
    }


def _read_spec(path: Path) -> Any:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise AlignmentError("cannot read spec: %s" % exc) from exc
    return _load_json_bytes(raw, str(path))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, help="alignment spec JSON")
    parser.add_argument("--root", default=".", help="repository/root directory (default: .)")
    args = parser.parse_args(argv)
    root = Path(args.root)
    try:
        report = check_alignment(_read_spec(Path(args.spec)), root=root)
    except AlignmentError as exc:
        print(json.dumps({"schema_version": REPORT_VERSION, "ok": False, "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())