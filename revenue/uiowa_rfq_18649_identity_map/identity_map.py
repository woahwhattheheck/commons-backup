#!/usr/bin/env python3
"""Deterministic identity reconciliation, not assessment or release authority.

Python 3.10+, standard library only. No network, clock, random IDs, or source
execution. CLI exit status: 0 resolved, 1 inspectable unresolved links, 2 invalid.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
import math
import os
import string
import tempfile
from pathlib import Path
import sys
from typing import Any

SCHEMA = "uiowa.identity-map.v1"
KEY_FIELDS = ("namespace", "kind", "id", "revision")
KINDS = frozenset({"source", "observation", "finding", "recommendation", "service"})
Key = tuple[str, str, str, str]


class MappingError(ValueError):
    """Input is malformed or contradicts a declared identity constraint."""


def canonical(value: Any) -> str:
    """Stable JSON with finite numbers; retain Unicode and JSON type distinctions."""
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, UnicodeError) as exc:
        raise MappingError(f"not representable as finite JSON: {exc}") from exc


def validate_json_value(value: Any, label: str = "value", _active: set[int] | None = None) -> None:
    """Reject Python-only/coercible values so the library and JSON CLI agree."""
    active = set() if _active is None else _active
    if value is None or type(value) in (bool, int):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise MappingError(f"{label} contains a non-finite number")
        return
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeError as exc:
            raise MappingError(f"{label} contains an unpaired surrogate") from exc
        return
    if not isinstance(value, (dict, list)):
        raise MappingError(f"{label} must contain only JSON objects, arrays and scalar values")
    if id(value) in active:
        raise MappingError(f"{label} contains a circular value")
    active.add(id(value))
    try:
        if isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, str):
                    raise MappingError(f"{label} has a non-string object key")
                validate_json_value(key, label, active)
                validate_json_value(item, label, active)
        else:
            for item in value:
                validate_json_value(item, label, active)
    finally:
        active.remove(id(value))


def digest(domain: str, value: Any) -> str:
    try:
        raw = (domain + "\0" + canonical(value)).encode("utf-8")
    except UnicodeError as exc:
        raise MappingError("unpaired Unicode surrogate") from exc
    return hashlib.sha256(raw).hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MappingError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(text: str) -> Any:
    def bad_constant(value: str) -> None:
        raise MappingError(f"non-finite JSON constant: {value}")
    try:
        return json.loads(text, object_pairs_hook=_pairs, parse_constant=bad_constant)
    except json.JSONDecodeError as exc:
        raise MappingError(f"invalid JSON at line {exc.lineno}, column {exc.colno}") from exc
    except RecursionError as exc:
        raise MappingError("JSON nesting exceeds parser capacity") from exc


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MappingError(f"{label} must be a nonempty string (numeric IDs are not coerced)")
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise MappingError(f"{label} contains a control character")
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise MappingError(f"{label} contains an unpaired surrogate") from exc
    return value  # Deliberately no case folding, whitespace or Unicode normalization.


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(k, str) for k in value):
        raise MappingError(f"{label} must be an object with string keys")
    return value


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise MappingError(f"{label} must be an array")
    return value


def selector(value: Any, *, complete: bool = False) -> dict[str, str]:
    value = _object(value, "selector")
    required = set(KEY_FIELDS if complete else ("kind", "id"))
    if not required.issubset(value) or set(value) - set(KEY_FIELDS):
        raise MappingError("selector needs kind/id; only namespace/kind/id/revision are permitted")
    result = {k: _text(v, f"selector.{k}") for k, v in value.items()}
    if result["kind"] not in KINDS:
        raise MappingError(f"unsupported entity kind: {result['kind']}")
    return result


def key_of(value: dict[str, Any]) -> Key:
    selected = selector({k: value[k] for k in KEY_FIELDS if k in value}, complete=True)
    return tuple(selected[k] for k in KEY_FIELDS)  # type: ignore[return-value]


def occurrence_id(key: Key) -> str:
    return "occ-" + digest(SCHEMA + "/occurrence", key)


def entity_id(key: Key) -> str:
    return "ent-" + digest(SCHEMA + "/entity", key[:3])


class IdentityMap:
    """A snapshot index. Equality decisions group records; never overwrite them."""

    def __init__(self, records: Any, decisions: Any = None):
        validate_json_value(records, "records")
        validate_json_value(decisions, "equivalences")
        self.records: dict[Key, dict[str, Any]] = {}
        self.counts: dict[Key, int] = defaultdict(int)
        self.by_kind_id: dict[tuple[str, str], list[Key]] = defaultdict(list)
        for item in _list(records, "records"):
            item = _object(item, "record")
            key = key_of(item)
            if type(item.get("synthetic")) is not bool:
                raise MappingError("record.synthetic must be an explicit boolean")
            _object(item.get("payload"), "record.payload")
            locators = _list(item.get("source_locators"), "record.source_locators")
            if not locators:
                raise MappingError("each record needs at least one source locator")
            for locator in locators:
                _text(locator, "source locator")
            normalized = deepcopy(item)
            # Identical duplicate rows may coalesce; conflicting content never wins by order.
            if key in self.records and canonical(self.records[key]) != canonical(normalized):
                raise MappingError(f"conflicting duplicate occurrence: {canonical(list(key))}")
            self.records[key] = normalized
            self.counts[key] += 1
        self.parent = {key: key for key in self.records}
        for key in sorted(self.records):
            self.by_kind_id[(key[1], key[2])].append(key)
        self.decisions: list[dict[str, Any]] = []
        decision_ids: set[str] = set()
        for decision in _list([] if decisions is None else decisions, "equivalences"):
            decision = _object(decision, "equivalence")
            did = _text(decision.get("decision_id"), "decision_id")
            if did in decision_ids:
                raise MappingError(f"duplicate decision_id: {did}")
            decision_ids.add(did)
            _text(decision.get("reason"), "equivalence.reason")
            evidence = _list(decision.get("evidence_locators"), "equivalence.evidence_locators")
            if not evidence:
                raise MappingError("equivalence needs a retained evidence locator")
            for item in evidence:
                _text(item, "equivalence evidence locator")
            left = key_of(selector(decision.get("left"), complete=True))
            right = key_of(selector(decision.get("right"), complete=True))
            if left not in self.records or right not in self.records:
                raise MappingError(f"equivalence {did} has a missing endpoint")
            if left[1] != right[1]:
                raise MappingError(f"equivalence {did} mixes entity kinds")
            if self.records[left]["synthetic"] != self.records[right]["synthetic"]:
                raise MappingError(f"equivalence {did} mixes synthetic and non-synthetic records")
            relation = decision.get("relation")
            if relation not in ("same_entity", "different_entity"):
                raise MappingError(f"equivalence {did} needs same_entity or different_entity")
            saved = deepcopy(decision)
            self.decisions.append(saved)
            if relation == "same_entity":
                self._union(left, right)
        self.decisions.sort(key=lambda d: d["decision_id"])
        # Check after ALL unions, so negative constraints work across transitive chains.
        for decision in self.decisions:
            if decision["relation"] == "different_entity":
                if self._root(key_of(decision["left"])) == self._root(key_of(decision["right"])):
                    raise MappingError(f"contradictory equivalence decision: {decision['decision_id']}")
        groups: dict[Key, list[Key]] = defaultdict(list)
        for key in sorted(self.records):
            groups[self._root(key)].append(key)
        self.group_ids: dict[Key, str] = {}
        self.groups = []
        for keys in sorted(groups.values()):
            members = sorted(occurrence_id(k) for k in keys)
            gid = "eq-" + digest(SCHEMA + "/equivalence-snapshot", members)
            for key in keys:
                self.group_ids[key] = gid
            self.groups.append({"group_id": gid, "members": members})
        self.groups.sort(key=lambda row: row["group_id"])

    def _root(self, key: Key) -> Key:
        while self.parent[key] != key:
            self.parent[key] = self.parent[self.parent[key]]
            key = self.parent[key]
        return key

    def _union(self, left: Key, right: Key) -> None:
        left, right = self._root(left), self._root(right)
        if left != right:
            self.parent[max(left, right)] = min(left, right)

    def resolve(self, target: Any) -> dict[str, Any]:
        query = selector(target)
        candidates = [key for key in self.by_kind_id.get((query["kind"], query["id"]), [])
                      if all(key[KEY_FIELDS.index(field)] == value for field, value in query.items())]
        ids = sorted(occurrence_id(key) for key in candidates)
        groups = sorted({self.group_ids[key] for key in candidates})
        return {"selector": deepcopy(query),
                "status": "resolved" if len(ids) == 1 else "ambiguous" if ids else "missing",
                "resolved_id": ids[0] if len(ids) == 1 else None,
                "candidate_ids": ids, "equivalence_groups": groups,
                "note": ("Equivalence does not select a source revision or merge payloads."
                         if len(ids) > 1 and len(groups) == 1 else "")}

    def report(self, links: Any = None) -> dict[str, Any]:
        validate_json_value(links, "links")
        resolved_links = []
        ids: set[str] = set()
        for link in _list([] if links is None else links, "links"):
            link = _object(link, "link")
            lid = _text(link.get("link_id"), "link.link_id")
            if lid in ids:
                raise MappingError(f"duplicate link_id: {lid}")
            ids.add(lid)
            _text(link.get("relation"), "link.relation")
            left, right = self.resolve(link.get("from")), self.resolve(link.get("to"))
            resolved_links.append({"link_id": lid, "original": deepcopy(link),
                                   "from": left, "to": right,
                                   "status": "resolved" if left["status"] == right["status"] == "resolved"
                                   else "unresolved"})
        resolved_links.sort(key=lambda row: row["link_id"])
        collisions = []
        for (kind, raw_id), keys in sorted(self.by_kind_id.items()):
            if len(keys) > 1:
                collisions.append({"kind": kind, "id": raw_id,
                                   "candidate_ids": sorted(occurrence_id(k) for k in keys),
                                   "namespaces": sorted({k[0] for k in keys}),
                                   "revisions": sorted({k[3] for k in keys})})
        records = [{"occurrence_id": occurrence_id(k), "entity_id": entity_id(k),
                    "equivalence_group": self.group_ids[k], "duplicate_count": self.counts[k],
                    "original": deepcopy(self.records[k])} for k in sorted(self.records)]
        unresolved = sum(row["status"] != "resolved" for row in resolved_links)
        result = {"schema": SCHEMA, "assessment_authority": False,
                  "records": records, "equivalences": deepcopy(self.decisions),
                  "equivalence_groups": deepcopy(self.groups), "collisions": collisions,
                  "links": resolved_links,
                  "summary": {"input_records": sum(self.counts.values()), "occurrences": len(records),
                              "collisions": len(collisions), "links": len(resolved_links),
                              "unresolved_links": unresolved}}
        result["snapshot_sha256"] = digest(SCHEMA + "/report", result)
        return result


def reconcile(document: Any) -> dict[str, Any]:
    validate_json_value(document, "document")
    document = _object(document, "document")
    if document.get("schema") != SCHEMA:
        raise MappingError(f"document.schema must be {SCHEMA}")
    result = IdentityMap(document.get("records"), document.get("equivalences")).report(document.get("links"))
    # Retain undeclared component fields instead of silently discarding them.
    result["extensions"] = deepcopy({k: v for k, v in document.items()
                                     if k not in ("schema", "records", "equivalences", "links")})
    result.pop("snapshot_sha256")
    result["snapshot_sha256"] = digest(SCHEMA + "/report", result)
    return result


def render_markdown(report: dict[str, Any]) -> str:
    def cell(value: Any) -> str:
        # IDs are data, not Markdown/HTML markup or URLs to follow.
        return "".join("<br>" if char == "\n" else f"&#{ord(char)};"
                       if char in string.punctuation else char for char in str(value))
    summary = report["summary"]
    out = ["# Identity reconciliation — inspection only", "",
           "Original records remain in the JSON output. This is not a maturity rating, finding validation, or approval.", "",
           f"Occurrences: {summary['occurrences']}; collisions: {summary['collisions']}; "
           f"unresolved links: {summary['unresolved_links']}.", "",
           "## Original identity index", "",
           "|Namespace|Kind|Original ID|Revision|Synthetic|Occurrence|", "|---|---|---|---|---|---|"]
    for record in report["records"]:
        source = record["original"]
        out.append("|" + "|".join(cell(v) for v in [source[k] for k in KEY_FIELDS] +
                                 [source["synthetic"], record["occurrence_id"]]) + "|")
    out += ["", "## Reference diagnostics", "", "|Link|From|To|Status|", "|---|---|---|---|"]
    details = []
    for link in report["links"]:
        out.append("|" + "|".join(cell(v) for v in [link["link_id"], link["from"]["status"],
                                                  link["to"]["status"], link["status"]]) + "|")
        for side in ("from", "to"):
            endpoint = link[side]
            if endpoint["status"] != "resolved":
                details.append(f"{cell(link['link_id'])} {side}: {cell(canonical(endpoint))}")
    out += ["", *details]
    out += ["", "Exact occurrence IDs are revision-bound; entity IDs omit revision. Equivalence groups describe only this snapshot.",
            "No case folding, Unicode normalization, fuzzy matching, or first/last-row selection is performed.", "",
            f"Snapshot SHA-256: `{report['snapshot_sha256']}`", ""]
    return "\n".join(out)


def _check_report_paths(input_path: Path, output_paths: list[Path]) -> None:
    """Reject names or existing file identities shared with input/another output."""
    paths = [input_path, *output_paths]
    normalized = [path.resolve() for path in paths]
    if len(normalized) != len(set(normalized)):
        raise MappingError("input and output paths must be distinct")
    for index, left in enumerate(paths):
        for right in paths[index + 1:]:
            if left.exists() and right.exists() and left.samefile(right):
                raise MappingError("input and output files must have distinct file identities")
    for target in output_paths:
        if target.exists() and not target.is_file():
            raise MappingError("report output must be a file path")


def _publish_reports(reports: list[tuple[Path, str]]) -> None:
    """Stage every report before replacing destinations; replace each atomically.

    This prevents predictable second-destination failures from publishing a first
    report. The filesystem does not offer a multi-file transaction: a late
    replace/IO failure can still leave a partial pair and must return exit 2.
    Existing report files may be intentionally regenerated; source identities
    are checked separately. Destination symlinks are replaced, not followed.
    """
    staged: list[tuple[Path, Path]] = []
    try:
        for target, content in reports:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                             prefix=".identity-map-", suffix=".tmp",
                                             dir=target.parent, delete=False) as stream:
                temporary = Path(stream.name)
                staged.append((temporary, target))
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        for temporary, target in staged:
            os.replace(temporary, target)
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args(argv)
    try:
        outputs = [path for path in (args.output, args.markdown) if path is not None]
        _check_report_paths(args.input, outputs)
        report = reconcile(load_json(args.input.read_text(encoding="utf-8")))
        text = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
        reports = []
        if args.output:
            reports.append((args.output, text))
        if args.markdown:
            reports.append((args.markdown, render_markdown(report)))
        _publish_reports(reports)
        if not args.output:
            sys.stdout.write(text)
        return 1 if report["summary"]["unresolved_links"] else 0
    except (MappingError, OSError, UnicodeError, RecursionError) as exc:
        print(f"identity-map: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
