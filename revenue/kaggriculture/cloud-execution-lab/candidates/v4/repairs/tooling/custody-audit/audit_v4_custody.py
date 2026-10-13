#!/usr/bin/env python3
"""Read-only, immutable-Git custody census; never a gameplay promotion gate.

Run from any checkout with Python 3.10+: python audit_v4_custody.py --repo .
Exit 0: all recorded pins have ordinary-file custody and source/test pins pair.
Exit 1: custody or source/test-reference gaps. Exit 2: invalid evidence/error.
Exit 3: requested ref moved during the census (the pinned report remains valid).
No candidate modules, materializers, Git hooks or shell commands are executed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

WORKSPACE = "revenue/kaggriculture/cloud-execution-lab/candidates/v4"
OID = re.compile(r"[0-9a-f]{40}\Z")
REGULAR = {"100644", "100755"}
KINDS = {"100644": "blob", "100755": "blob", "120000": "blob",
         "160000": "commit", "040000": "tree"}


class EvidenceError(ValueError):
    """The supplied evidence cannot support a complete custody census."""


def require(ok: bool, message: str) -> None:
    # Do not use assert: the census has identical semantics under python -O.
    if not ok:
        raise EvidenceError(message)


def oid(value: Any) -> str:
    require(type(value) is str and OID.fullmatch(value) is not None,
            "expected a lowercase full SHA-1 Git object ID")
    return value


def object_id(kind: str, data: bytes) -> str:
    return hashlib.sha1(kind.encode() + b" " + str(len(data)).encode()
                        + b"\0" + data).hexdigest()


@dataclass(frozen=True)
class Entry:
    mode: str
    kind: str
    sha: str


def parse_tree(raw: bytes) -> dict[str, Entry]:
    require(not raw or raw.endswith(b"\0"), "truncated ls-tree record")
    result: dict[str, Entry] = {}
    for row in raw.split(b"\0")[:-1]:
        try:
            head, path_raw = row.split(b"\t", 1)
            mode, kind, sha = head.decode("ascii").split(" ")
            path = path_raw.decode("utf-8")
        except (ValueError, UnicodeError) as exc:
            raise EvidenceError("malformed ls-tree record") from exc
        require(mode in KINDS and KINDS[mode] == kind, "invalid Git mode/type")
        require(path and all(p not in {"", ".", ".."} for p in path.split("/")),
                "non-relative/non-canonical tree path")
        require(path not in result, "duplicate tree path")
        result[path] = Entry(mode, kind, oid(sha))
    return result


def verify_tree(entries: dict[str, Entry], expected: str) -> None:
    """Rebuild every directory OID, including root, to detect omitted records."""
    oid(expected)
    children: dict[str, list[tuple[str, Entry]]] = defaultdict(list)
    directories = {""}
    for path, entry in entries.items():
        parent, _, name = path.rpartition("/")
        if parent:
            require(parent in entries and entries[parent].kind == "tree",
                    "missing/non-directory parent: " + parent)
        children[parent].append((name, entry))
        if entry.kind == "tree":
            directories.add(path)
    for directory in sorted(directories):
        rows = sorted(children[directory],
                      key=lambda pair: pair[0].encode("utf-8")
                      + (b"/" if pair[1].kind == "tree" else b""))
        data = b"".join(("40000" if e.kind == "tree" else e.mode).encode()
                        + b" " + name.encode("utf-8") + b"\0"
                        + bytes.fromhex(e.sha) for name, e in rows)
        wanted = expected if directory == "" else entries[directory].sha
        require(object_id("tree", data) == wanted,
                "incomplete or mixed tree snapshot: " + (directory or "/"))


def strict_json(raw: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in items:
            require(key not in out, "duplicate JSON key: " + key)
            out[key] = value
        return out

    def bad_constant(value: str) -> None:
        raise EvidenceError("non-finite JSON value: " + value)

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad_constant)
    except (ValueError, UnicodeError) as exc:
        raise EvidenceError("invalid metadata JSON: " + str(exc)) from exc


@dataclass(frozen=True)
class Snapshot:
    commit: str
    tree: str
    entries: dict[str, Entry]
    canonical: bytes
    ledger: bytes
    blobs: dict[str, bytes]


def git(repo: Path, *args: str) -> bytes:
    env = dict(os.environ, GIT_NO_REPLACE_OBJECTS="1", GIT_OPTIONAL_LOCKS="0",
               GIT_TERMINAL_PROMPT="0", GIT_NO_LAZY_FETCH="1")
    try:
        run = subprocess.run(["git", "-C", str(repo), *args], env=env,
                             capture_output=True, check=True, timeout=60)
        return run.stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise EvidenceError("read-only Git command failed: " + str(exc)) from exc


def resolve(repo: Path, ref: str) -> str:
    require(type(ref) is str and bool(ref) and "\0" not in ref, "invalid ref")
    return oid(git(repo, "rev-parse", "--verify", "--end-of-options",
                   ref + "^{commit}").decode("ascii").strip())


def read_snapshot(repo: Path, ref: str = "main") -> Snapshot:
    commit = resolve(repo, ref)  # Resolve once; every subsequent read is immutable.
    tree = oid(git(repo, "rev-parse", "--verify", commit + ":" + WORKSPACE)
               .decode("ascii").strip())
    entries = parse_tree(git(repo, "ls-tree", "-r", "-t", "-z", tree))
    verify_tree(entries, tree)
    metadata = []
    for path in ("CANONICAL.json", "INTEGRATION.json"):
        entry = entries.get(path)
        require(entry is not None and entry.mode in REGULAR, "missing regular " + path)
        raw = git(repo, "cat-file", "blob", entry.sha)
        require(object_id("blob", raw) == entry.sha, "metadata blob drift: " + path)
        metadata.append(raw)
    # A tree reference alone does not prove readable source/test byte custody.
    declared: set[str] = set()

    def collect(value: Any) -> None:
        if type(value) is dict:
            for key, child in value.items():
                if key.endswith("_blob"):
                    declared.add(oid(child))
                elif key.endswith("_blobs"):
                    require(type(child) is list and bool(child), "invalid blob list")
                    declared.update(oid(item) for item in child)
                else:
                    collect(child)
        elif type(value) is list:
            for child in value:
                collect(child)

    collect(strict_json(metadata[1]))
    present = {entry.sha for entry in entries.values() if entry.mode in REGULAR}
    blobs = {}
    for sha in sorted(declared & present):
        raw = git(repo, "cat-file", "blob", sha)
        require(object_id("blob", raw) == sha, "referenced blob byte mismatch: " + sha)
        blobs[sha] = raw
    return Snapshot(commit, tree, entries, *metadata, blobs)


def census(snapshot: Snapshot) -> dict[str, Any]:
    oid(snapshot.commit)
    verify_tree(snapshot.entries, snapshot.tree)
    documents = []
    for name, raw in (("CANONICAL.json", snapshot.canonical),
                      ("INTEGRATION.json", snapshot.ledger)):
        entry = snapshot.entries.get(name)
        require(entry is not None and entry.mode in REGULAR, "nonregular " + name)
        require(object_id("blob", raw) == entry.sha, "mixed metadata snapshot: " + name)
        doc = strict_json(raw)
        require(type(doc) is dict, "metadata root must be an object")
        require(doc.get("canonical_branch") == "main", "canonical branch is not main")
        require(doc.get("workspace") == WORKSPACE, "canonical workspace mismatch")
        documents.append(doc)
    _, ledger = documents
    require(ledger.get("schema") == "titan-v4-integration-ledger/v1", "unknown ledger schema")
    for group in ("landed", "recovered_not_yet_composed"):
        require(type(ledger.get(group)) is list, "missing lane group: " + group)
        for lane in ledger[group]:
            require(type(lane) is dict and type(lane.get("lane")) is str
                    and bool(lane["lane"]), "invalid lane record")

    require(bool(ledger["landed"] or ledger["recovered_not_yet_composed"]),
            "no recorded source lanes; an empty census cannot prove custody")

    regular: dict[str, list[str]] = defaultdict(list)
    nonregular: dict[str, list[str]] = defaultdict(list)
    for path, entry in snapshot.entries.items():
        dest = regular if entry.mode in REGULAR else nonregular
        dest[entry.sha].append(WORKSPACE + "/" + path)
    references: list[dict[str, Any]] = []

    def add(value: Any, pointer: str, lane: str | None) -> None:
        sha = oid(value)
        paths = sorted(regular.get(sha, []))
        if paths:
            require(sha in snapshot.blobs, "unreadable/unverified in-tree blob: " + sha)
            require(object_id("blob", snapshot.blobs[sha]) == sha,
                    "referenced blob byte mismatch: " + sha)
        references.append({"pointer": pointer, "lane": lane, "blob": sha,
                           "status": "exact_bytes_present" if paths else "missing_exact_bytes",
                           "paths": paths,
                           "nonregular_matches": sorted(nonregular.get(sha, []))})

    def walk(value: Any, pointer: str = "", lane: str | None = None) -> None:
        if type(value) is dict:
            lane = value.get("lane", lane)
            for key in sorted(value):
                child = value[key]
                p = pointer + "/" + key.replace("~", "~0").replace("/", "~1")
                if key.endswith("_blob"):
                    add(child, p, lane)
                elif key.endswith("_blobs"):
                    require(type(child) is list and bool(child), "empty/invalid blob list: " + p)
                    for i, sha in enumerate(child):
                        add(sha, p + "/" + str(i), lane)
                else:
                    walk(child, p, lane)
        elif type(value) is list:
            for i, child in enumerate(value):
                walk(child, pointer + "/" + str(i), lane)

    walk(ledger)
    gaps = []
    for group in ("landed", "recovered_not_yet_composed"):
        for i, lane in enumerate(ledger[group]):
            for role, keys in (("source", ("source_blob", "generator_blob")),
                               ("test", ("test_blob", "test_blobs"))):
                if not any(key in lane for key in keys):
                    gaps.append({"pointer": f"/{group}/{i}", "lane": lane["lane"],
                                 "gap": "missing_" + role + "_pin"})
    missing = sum(r["status"] == "missing_exact_bytes" for r in references)
    return {"schema": "titan-v4-custody-census/v1", "commit": snapshot.commit,
            "workspace_tree": snapshot.tree, "workspace": WORKSPACE,
            "ledger_blob": snapshot.entries["INTEGRATION.json"].sha,
            "canonical_blob": snapshot.entries["CANONICAL.json"].sha,
            "complete_tree_verified": True, "referenced_blobs_verified": len(snapshot.blobs),
            "pin_references": len(references),
            "missing_pin_references": missing, "lane_reference_gaps": gaps,
            "custody_complete": missing == 0 and not gaps,
            "composition_proven": False, "production_activation_proven": False,
            "economics_proven": False, "references": references,
            "interpretation": "Missing pins may be stale, replaced, or lost; do not restore old bytes automatically. Presence proves only byte custody, not execution or approval."}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--ref", default="main", help="read once, then pin all object reads")
    args = parser.parse_args(argv)
    try:
        snapshot = read_snapshot(args.repo, args.ref)
        result = census(snapshot)
        after = resolve(args.repo, args.ref)
        result["ref_at_end"] = after
        result["ref_moved"] = after != snapshot.commit
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
        if result["ref_moved"]:
            return 3
        return 0 if result["custody_complete"] else 1
    except (EvidenceError, UnicodeError) as exc:
        print(json.dumps({"schema": "titan-v4-custody-census/v1", "error": str(exc),
                          "custody_complete": False}, sort_keys=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())
