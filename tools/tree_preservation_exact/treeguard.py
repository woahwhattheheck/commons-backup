"""Exact Git-tree preservation checks. No network, checkout, object write or ref write.

A separately reviewed, SHA-256-pinned edit contract is applied to the actual base
Git tree in memory. Equality with the candidate root proves that no other tree
entry changed (under the repository's Git object-hash identity assumptions).
This is a source-composition check, not test, approval, or merge authority.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Protocol

SCHEMA = "git-tree-preservation-contract/v1"
REPORT_SCHEMA = "git-tree-preservation-report/v1"
PACK_SCHEMA = "git-tree-object-witness/v1"
MAX_JSON = 48 * 1024 * 1024
MAX_OBJECT = 8 * 1024 * 1024
MAX_OBJECTS = 2048
MAX_TOTAL_OBJECT_BYTES = 24 * 1024 * 1024
MAX_EDITS = 10000
MAX_DEPTH = 64
LEAF_MODES = {"100644", "100755", "120000", "160000"}
ALL_MODES = LEAF_MODES | {"040000"}


class GuardError(ValueError):
    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail
        super().__init__(code + (": " + detail if detail else ""))


def fail(code: str, detail: str = "") -> None:
    raise GuardError(code, detail)


def canonical(value: Any) -> bytes:
    try:
        return (json.dumps(value, sort_keys=True, ensure_ascii=True,
                           separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")
    except (ValueError, TypeError, RecursionError) as exc:
        raise GuardError("INVALID_JSON_VALUE") from exc


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, val in items:
        if key in result:
            fail("DUPLICATE_JSON_KEY")
        result[key] = val
    return result


def _number_reject(_: str) -> Any:
    fail("NON_INTEGER_JSON_NUMBER")


def load_json(raw: bytes) -> Any:
    if type(raw) is not bytes or len(raw) > MAX_JSON:
        fail("INPUT_SIZE_LIMIT")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                          parse_float=_number_reject, parse_constant=_number_reject)
    except GuardError:
        raise
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise GuardError("INVALID_JSON") from exc


def exact_keys(obj: Any, keys: set[str], name: str) -> dict[str, Any]:
    if type(obj) is not dict or set(obj) != keys:
        fail("SCHEMA_FIELDS", name)
    return obj


def oid_check(value: Any, fmt: str) -> str:
    length = {"sha1": 40, "sha256": 64}.get(fmt)
    if length is None or type(value) is not str or not re.fullmatch(
            "[0-9a-f]{" + str(length) + "}", value):
        fail("INVALID_OBJECT_ID")
    if value == "0" * length:
        fail("ZERO_OBJECT_ID")
    return value


def object_id(kind: str, raw: bytes, fmt: str) -> str:
    if fmt not in {"sha1", "sha256"} or kind not in {"tree", "commit", "blob"}:
        fail("OBJECT_TYPE_OR_FORMAT")
    h = hashlib.new(fmt)
    h.update(kind.encode("ascii") + b" " + str(len(raw)).encode("ascii") + b"\0")
    h.update(raw)
    return h.hexdigest()


@dataclass(frozen=True)
class Entry:
    mode: str
    oid: str

    def json(self) -> dict[str, str]:
        return {"mode": self.mode, "oid": self.oid}


def entry_check(value: Any, fmt: str) -> Entry | None:
    if value is None:
        return None
    exact_keys(value, {"mode", "oid"}, "entry")
    if type(value["mode"]) is not str or value["mode"] not in LEAF_MODES:
        fail("LEAF_MODE_REQUIRED")
    return Entry(value["mode"], oid_check(value["oid"], fmt))


def path_check(value: Any) -> tuple[bytes, ...]:
    if type(value) is not str:
        fail("INVALID_EDIT_PATH")
    try:
        raw = value.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise GuardError("INVALID_EDIT_PATH") from exc
    parts = raw.split(b"/")
    # Literal paths only. No glob, option, path traversal, control, or .git path.
    if (not raw or len(raw) > 4096 or len(parts) > MAX_DEPTH or b"\\" in raw
            or any(c < 32 or c == 127 for c in raw)
            or any(c in raw for c in (b"*", b"?", b"[", b"]"))
            or any(not p or p in {b".", b".."} or p.lower() == b".git" for p in parts)):
        fail("INVALID_EDIT_PATH")
    return tuple(parts)


def contract_check(raw: bytes, pin: str, repository: str) -> dict[str, Any]:
    if type(pin) is not str or not re.fullmatch(r"[0-9a-f]{64}", pin):
        fail("CONTRACT_PIN_REQUIRED")
    if not hmac.compare_digest(sha256(raw), pin):
        fail("CONTRACT_PIN_MISMATCH")
    value = load_json(raw)
    exact_keys(value, {"schema", "repository", "object_format", "base_commit", "edits"}, "contract")
    if value["schema"] != SCHEMA:
        fail("CONTRACT_VERSION")
    if (type(repository) is not str or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
            or len(repository) > 200 or value["repository"] != repository):
        fail("REPOSITORY_LABEL_MISMATCH")
    fmt = value["object_format"]
    if type(fmt) is not str or fmt not in {"sha1", "sha256"}:
        fail("OBJECT_TYPE_OR_FORMAT")
    oid_check(value["base_commit"], fmt)
    edits = value["edits"]
    if type(edits) is not list or not 1 <= len(edits) <= MAX_EDITS:
        fail("EDIT_COUNT_LIMIT")
    seen: set[tuple[bytes, ...]] = set()
    for edit in edits:
        exact_keys(edit, {"path", "before", "after"}, "edit")
        parts = path_check(edit["path"])
        if parts in seen:
            fail("DUPLICATE_EDIT_PATH")
        seen.add(parts)
        before, after = entry_check(edit["before"], fmt), entry_check(edit["after"], fmt)
        if before == after:
            fail("NOOP_EDIT")
    for path in seen:
        if any(path[:n] in seen for n in range(1, len(path))):
            fail("OVERLAPPING_EDIT_PATHS")
    return value


def tree_encode(entries: dict[bytes, Entry], fmt: str) -> bytes:
    # Git sorts directories as if their names had a trailing slash.
    order = sorted(entries, key=lambda n: n + (b"/" if entries[n].mode == "040000" else b""))
    result = bytearray()
    for name in order:
        entry = entries[name]
        if not name or b"/" in name or b"\0" in name or name in {b".", b".."}:
            fail("INVALID_TREE_NAME")
        if entry.mode not in ALL_MODES:
            fail("INVALID_TREE_MODE")
        oid_check(entry.oid, fmt)
        raw_mode = b"40000" if entry.mode == "040000" else entry.mode.encode("ascii")
        result.extend(raw_mode + b" " + name + b"\0" + bytes.fromhex(entry.oid))
    if len(result) > MAX_OBJECT:
        fail("OBJECT_SIZE_LIMIT")
    return bytes(result)


def tree_decode(raw: bytes, fmt: str) -> dict[bytes, Entry]:
    width = 20 if fmt == "sha1" else 32
    result: dict[bytes, Entry] = {}
    pos = 0
    while pos < len(raw):
        space, nul = raw.find(b" ", pos), raw.find(b"\0", pos)
        if space <= pos or nul <= space + 1 or nul + 1 + width > len(raw):
            fail("MALFORMED_TREE")
        mode_raw = raw[pos:space]
        try:
            mode = mode_raw.decode("ascii")
        except UnicodeError as exc:
            raise GuardError("MALFORMED_TREE") from exc
        mode = "040000" if mode == "40000" else mode
        name = raw[space + 1:nul]
        if name in result:
            fail("DUPLICATE_TREE_NAME")
        if mode not in ALL_MODES:
            fail("INVALID_TREE_MODE")
        result[name] = Entry(mode, raw[nul + 1:nul + 1 + width].hex())
        pos = nul + 1 + width
    # Reject noncanonical ordering, modes, malformed names, and zero OIDs.
    if tree_encode(result, fmt) != raw:
        fail("NONCANONICAL_TREE")
    return result


class ObjectStore(Protocol):
    object_format: str
    def read(self, oid: str) -> tuple[str, bytes]: ...


class WitnessStore:
    """Content-address-verified commit/tree objects; no blob contents required."""
    def __init__(self, value: Any):
        exact_keys(value, {"schema", "object_format", "objects"}, "witness")
        if (value["schema"] != PACK_SCHEMA or type(value["object_format"]) is not str
                or value["object_format"] not in {"sha1", "sha256"}):
            fail("WITNESS_VERSION_OR_FORMAT")
        self.object_format = value["object_format"]
        objects = value["objects"]
        if type(objects) is not list or len(objects) > MAX_OBJECTS:
            fail("OBJECT_COUNT_LIMIT")
        self.objects: dict[str, tuple[str, bytes]] = {}
        total = 0
        for item in objects:
            exact_keys(item, {"oid", "type", "data_b64"}, "witness object")
            oid = oid_check(item["oid"], self.object_format)
            if oid in self.objects:
                fail("DUPLICATE_WITNESS_OBJECT")
            if (type(item["type"]) is not str or item["type"] not in {"tree", "commit"}
                    or type(item["data_b64"]) is not str):
                fail("WITNESS_OBJECT_TYPE")
            try:
                raw = base64.b64decode(item["data_b64"], validate=True)
            except (ValueError, TypeError) as exc:
                raise GuardError("INVALID_BASE64") from exc
            if base64.b64encode(raw).decode("ascii") != item["data_b64"]:
                fail("NONCANONICAL_BASE64")
            total += len(raw)
            if len(raw) > MAX_OBJECT or total > MAX_TOTAL_OBJECT_BYTES:
                fail("OBJECT_SIZE_LIMIT")
            if object_id(item["type"], raw, self.object_format) != oid:
                fail("OBJECT_HASH_MISMATCH")
            self.objects[oid] = (item["type"], raw)

    def read(self, oid: str) -> tuple[str, bytes]:
        if oid not in self.objects:
            fail("MISSING_WITNESS_OBJECT", oid)
        return self.objects[oid]


def github_tree_object(value: Any) -> tuple[str, bytes]:
    """Import one COMPLETE non-recursive GitHub Git Trees response.

    Hash verification, not the supplied `truncated` flag alone, establishes
    correspondence to the supplied tree OID. That OID must itself be anchored
    independently. URL/size metadata are not source-authentication evidence.
    """
    if (type(value) is not dict or not {"sha", "tree", "truncated"} <= set(value)
            or set(value) - {"sha", "tree", "truncated", "url"}):
        fail("GITHUB_TREE_SCHEMA")
    if value["truncated"] is not False:
        fail("GITHUB_TREE_TRUNCATED_OR_UNKNOWN")
    oid = oid_check(value["sha"], "sha1")
    if type(value["tree"]) is not list or len(value["tree"]) > 100000:
        fail("GITHUB_TREE_ENTRY_LIMIT")
    if "url" in value and type(value["url"]) is not str:
        fail("GITHUB_TREE_SCHEMA")
    entries: dict[bytes, Entry] = {}
    for item in value["tree"]:
        required = {"path", "mode", "type", "sha"}
        if (type(item) is not dict or not required <= set(item)
                or set(item) - required - {"url", "size"}):
            fail("GITHUB_TREE_ENTRY_SCHEMA")
        mode = item["mode"]
        if type(mode) is not str or mode not in ALL_MODES or type(item["path"]) is not str:
            fail("GITHUB_TREE_ENTRY_SCHEMA")
        expected_type = "tree" if mode == "040000" else "commit" if mode == "160000" else "blob"
        if item["type"] != expected_type:
            fail("GITHUB_TREE_ENTRY_TYPE")
        if "size" in item and (type(item["size"]) is not int or not 0 <= item["size"] <= 2**53 - 1):
            fail("GITHUB_TREE_ENTRY_SIZE")
        if "url" in item and type(item["url"]) is not str:
            fail("GITHUB_TREE_ENTRY_SCHEMA")
        try:
            name = item["path"].encode("utf-8", "strict")
        except UnicodeError as exc:
            raise GuardError("GITHUB_TREE_PATH_ENCODING") from exc
        if name in entries:
            fail("DUPLICATE_TREE_NAME")
        entries[name] = Entry(mode, oid_check(item["sha"], "sha1"))
    raw = tree_encode(entries, "sha1")
    if object_id("tree", raw, "sha1") != oid:
        fail("GITHUB_TREE_HASH_MISMATCH")
    return oid, raw


class GitStore:
    """Read-only local object access. Does not clone or fetch missing objects."""
    def __init__(self, repo: str, timeout: float = 45.0):
        if not 0 < timeout <= 600:
            fail("INVALID_TIMEOUT")
        git = shutil.which("git")
        if not git:
            fail("GIT_UNAVAILABLE")
        if not Path(repo).is_dir():
            fail("REPOSITORY_UNAVAILABLE")
        self.deadline = time.monotonic() + timeout
        self.argv = [git, "--no-pager", "--no-replace-objects", "--no-lazy-fetch",
                     "--no-optional-locks", "-c", "protocol.allow=never", "-c", "gc.auto=0",
                     "-c", "core.fsmonitor=false", "-C", str(Path(repo).resolve())]
        self.env = {"PATH": os.environ.get("PATH", os.defpath), "LANG": "C", "LC_ALL": "C",
                    "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                    "GIT_TERMINAL_PROMPT": "0", "GIT_NO_REPLACE_OBJECTS": "1",
                    "GIT_NO_LAZY_FETCH": "1", "GIT_OPTIONAL_LOCKS": "0"}
        self.object_format = self._run(["rev-parse", "--show-object-format"], cap=128).decode("ascii").strip()
        if self.object_format not in {"sha1", "sha256"}:
            fail("OBJECT_TYPE_OR_FORMAT")

    def _run(self, argv: list[str], stdin: bytes | None = None, cap: int = MAX_OBJECT) -> bytes:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            fail("GIT_TIMEOUT")
        # stdout goes to a temporary ordinary file rather than an unbounded pipe.
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as error:
            try:
                result = subprocess.run(self.argv + argv, input=stdin, stdout=output,
                                        stderr=error, env=self.env, timeout=remaining, check=False)
            except subprocess.TimeoutExpired as exc:
                raise GuardError("GIT_TIMEOUT") from exc
            except OSError as exc:
                raise GuardError("GIT_IO_ERROR") from exc
            if result.returncode:
                # Do not leak repository config, private paths, or credentials from stderr.
                fail("GIT_READ_FAILED", "exit=" + str(result.returncode))
            if output.tell() > cap:
                fail("GIT_OUTPUT_LIMIT")
            output.seek(0)
            return output.read(cap + 1)

    def read(self, oid: str) -> tuple[str, bytes]:
        oid_check(oid, self.object_format)
        info = self._run(["cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)"],
                         stdin=oid.encode("ascii") + b"\n", cap=256).decode("ascii").split()
        if len(info) != 3 or info[0] != oid or info[1] not in {"tree", "commit"}:
            fail("GIT_OBJECT_UNAVAILABLE_OR_TYPE")
        if not info[2].isdigit() or int(info[2]) > MAX_OBJECT:
            fail("OBJECT_SIZE_LIMIT")
        raw = self._run(["cat-file", info[1], oid], cap=int(info[2]))
        if len(raw) != int(info[2]) or object_id(info[1], raw, self.object_format) != oid:
            fail("OBJECT_HASH_MISMATCH")
        return info[1], raw

    def ref_oid(self, ref: str) -> str:
        if (type(ref) is not str or not re.fullmatch(r"refs/(heads|remotes)/[A-Za-z0-9_./-]+", ref)
                or ".." in ref or "//" in ref or ref.endswith(("/", ".lock", "."))):
            fail("INVALID_REF")
        oid = self._run(["show-ref", "--verify", "--hash", ref], cap=128).decode("ascii").strip()
        return oid_check(oid, self.object_format)


class Session:
    def __init__(self, store: ObjectStore):
        self.store = store
        self.fmt = store.object_format
        self.objects: dict[str, tuple[str, bytes]] = {}
        self.byte_count = 0
        self.base_tree_reads: set[str] = set()

    def read(self, oid: str, expected_type: str) -> bytes:
        oid_check(oid, self.fmt)
        if oid not in self.objects:
            kind, raw = self.store.read(oid)
            if kind not in {"tree", "commit"} or type(raw) is not bytes:
                fail("OBJECT_TYPE_OR_FORMAT")
            if len(raw) > MAX_OBJECT or object_id(kind, raw, self.fmt) != oid:
                fail("OBJECT_HASH_MISMATCH")
            self.byte_count += len(raw)
            if len(self.objects) >= MAX_OBJECTS or self.byte_count > MAX_TOTAL_OBJECT_BYTES:
                fail("OBJECT_COUNT_OR_TOTAL_LIMIT")
            self.objects[oid] = (kind, raw)
        kind, raw = self.objects[oid]
        if kind != expected_type:
            fail("OBJECT_TYPE_MISMATCH")
        return raw

    def commit(self, oid: str) -> tuple[str, list[str]]:
        raw = self.read(oid, "commit")
        header, sep, _ = raw.partition(b"\n\n")
        if not sep:
            fail("MALFORMED_COMMIT")
        lines = header.split(b"\n")
        if not lines or not lines[0].startswith(b"tree "):
            fail("MALFORMED_COMMIT")
        trees = [line[5:] for line in lines if line.startswith(b"tree ")]
        if len(trees) != 1:
            fail("MALFORMED_COMMIT")
        try:
            tree = oid_check(trees[0].decode("ascii"), self.fmt)
            parents = [oid_check(line[7:].decode("ascii"), self.fmt)
                       for line in lines if line.startswith(b"parent ")]
        except UnicodeError as exc:
            raise GuardError("MALFORMED_COMMIT") from exc
        if len(parents) != len(set(parents)):
            fail("DUPLICATE_COMMIT_PARENT")
        return tree, parents

    def tree(self, oid: str) -> dict[bytes, Entry]:
        self.base_tree_reads.add(oid)
        return tree_decode(self.read(oid, "tree"), self.fmt)

    def witness(self) -> dict[str, Any]:
        return {"schema": PACK_SCHEMA, "object_format": self.fmt,
                "objects": [{"oid": oid, "type": kind,
                             "data_b64": base64.b64encode(raw).decode("ascii")}
                            for oid, (kind, raw) in sorted(self.objects.items())]}


def _apply(session: Session, original: str | None, edits: list[tuple[tuple[bytes, ...], Entry | None, Entry | None]],
           depth: int = 0) -> tuple[str, dict[bytes, Entry]]:
    if depth > MAX_DEPTH:
        fail("TREE_DEPTH_LIMIT")
    entries = {} if original is None else session.tree(original)
    groups: dict[bytes, list[tuple[tuple[bytes, ...], Entry | None, Entry | None]]] = {}
    for path, before, after in edits:
        groups.setdefault(path[0], []).append((path, before, after))
    for name, group in sorted(groups.items()):
        if len(group[0][0]) == 1:
            if len(group) != 1:
                fail("OVERLAPPING_EDIT_PATHS")
            _, before, after = group[0]
            found = entries.get(name)
            if found != before:
                fail("BEFORE_ENTRY_MISMATCH", name.decode("utf-8", "backslashreplace"))
            if after is None:
                del entries[name]
            else:
                entries[name] = after
        else:
            child = entries.get(name)
            if child is not None and child.mode != "040000":
                fail("PATH_BLOCKED_BY_LEAF", name.decode("utf-8", "backslashreplace"))
            new_oid, new_entries = _apply(session, child.oid if child else None,
                                         [(p[1:], b, a) for p, b, a in group], depth + 1)
            if new_entries:
                entries[name] = Entry("040000", new_oid)
            else:
                entries.pop(name, None)
    return object_id("tree", tree_encode(entries, session.fmt), session.fmt), entries


def build_plan(store: ObjectStore, contract_raw: bytes, contract_pin: str,
               repository: str) -> dict[str, Any]:
    """Construct the exact GitHub tree request, without submitting anything."""
    contract = contract_check(contract_raw, contract_pin, repository)
    if store.object_format != contract["object_format"]:
        fail("OBJECT_FORMAT_MISMATCH")
    # GitHub's documented Git Data schema uses SHA-1 object identifiers.
    if store.object_format != "sha1":
        fail("GITHUB_PLAN_REQUIRES_SHA1")
    session = Session(store)
    base_tree, _ = session.commit(contract["base_commit"])
    edits = [(path_check(e["path"]), entry_check(e["before"], session.fmt),
              entry_check(e["after"], session.fmt)) for e in contract["edits"]]
    expected_tree, _ = _apply(session, base_tree, edits)
    rows = []
    for edit in sorted(contract["edits"], key=lambda e: path_check(e["path"])):
        entry = edit["after"] if edit["after"] is not None else edit["before"]
        mode = entry["mode"]
        rows.append({"path": edit["path"], "mode": mode,
                     "type": "commit" if mode == "160000" else "blob",
                     "sha": None if edit["after"] is None else edit["after"]["oid"]})
    result = {"schema": "git-tree-preservation-plan/v1", "state": "REQUEST_ONLY_NOT_EXECUTED",
              "repository_label": repository, "object_format": session.fmt,
              "contract_sha256": contract_pin, "base_commit": contract["base_commit"],
              "base_tree": base_tree, "expected_tree": expected_tree,
              "request": {"base_tree": base_tree, "tree": rows},
              "required_candidate_parents": [contract["base_commit"]],
              "candidate_checked": False, "remote_mutation_performed": False,
              "merge_authorized": False, "witness": session.witness()}
    result["receipt_sha256"] = sha256(canonical(result))
    return result


def _json_entry(entry: Entry | None) -> dict[str, str] | None:
    return None if entry is None else entry.json()


def _root_deltas(expected: dict[bytes, Entry], candidate: dict[bytes, Entry]) -> list[dict[str, Any]]:
    result = []
    for name in sorted(set(expected) | set(candidate)):
        if expected.get(name) != candidate.get(name):
            result.append({"path_display": name.decode("utf-8", "backslashreplace"),
                           "path_b64": base64.b64encode(name).decode("ascii"),
                           "expected": _json_entry(expected.get(name)),
                           "actual": _json_entry(candidate.get(name))})
    return result


def audit(store: ObjectStore, contract_raw: bytes, contract_pin: str,
          repository: str, candidate: str) -> dict[str, Any]:
    contract = contract_check(contract_raw, contract_pin, repository)
    fmt = contract["object_format"]
    if store.object_format != fmt:
        fail("OBJECT_FORMAT_MISMATCH")
    oid_check(candidate, fmt)
    session = Session(store)
    base = contract["base_commit"]
    base_tree, _ = session.commit(base)
    candidate_tree, parents = session.commit(candidate)
    edits = [(path_check(e["path"]), entry_check(e["before"], fmt), entry_check(e["after"], fmt))
             for e in contract["edits"]]
    expected_tree, expected_root = _apply(session, base_tree, edits)
    base_reads = len(session.base_tree_reads)
    actual_root = tree_decode(session.read(candidate_tree, "tree"), fmt)
    reasons = []
    if parents != [base]:
        reasons.append("CANDIDATE_NOT_DIRECT_CHILD_OF_BASE")
    if candidate_tree != expected_tree:
        reasons.append("UNDECLARED_TREE_CHANGE")
    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA, "evidence_class": "CONTENT_ADDRESSED_OBJECT_REPLAY",
        "repository_label": repository, "object_format": fmt,
        "contract_sha256": contract_pin, "base_commit": base, "base_tree": base_tree,
        "candidate_commit": candidate, "candidate_tree": candidate_tree,
        "candidate_parents": parents, "expected_tree": expected_tree,
        "state": "HOLD" if reasons else "TREE_MATCH", "reasons": reasons,
        "declared_edit_count": len(edits), "base_tree_objects_read": base_reads,
        "root_deltas": _root_deltas(expected_root, actual_root),
        "authority": {"merge_authorized": False, "tests_passed": False,
                      "hosted_ci_verified": False, "current_remote_ref_verified": False,
                      "contract_approval_authenticated": False, "source_safety_proven": False,
                      "repository_identity_authenticated": False, "remote_mutation_performed": False},
        "witness": session.witness(),
    }
    report["receipt_sha256"] = sha256(canonical(report))
    return report


def replay(report_raw: bytes, contract_raw: bytes, contract_pin: str,
           repository: str, candidate: str) -> dict[str, Any]:
    value = load_json(report_raw)
    if type(value) is not dict or "witness" not in value:
        fail("INVALID_REPORT")
    expected = audit(WitnessStore(value["witness"]), contract_raw, contract_pin, repository, candidate)
    if canonical(value) != canonical(expected):
        fail("REPORT_REPLAY_MISMATCH")
    return {"state": "REPLAY_MATCH", "replayed_tree_state": expected["state"],
            "receipt_sha256": expected["receipt_sha256"], "candidate_commit": candidate,
            "current_remote_ref_verified": False, "merge_authorized": False}


def read_file(path: str) -> bytes:
    # Filesystem is an operator-trusted local boundary. Final symlinks/FIFOs are
    # rejected; ancestor replacement resistance is not claimed.
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_NONBLOCK"):
        fail("UNSUPPORTED_LOCAL_FILE_PLATFORM")
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    try:
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_JSON:
                fail("INPUT_NOT_BOUNDED_REGULAR_FILE")
            raw = stream.read(MAX_JSON + 1)
            after = os.fstat(stream.fileno())
            if (len(raw) > MAX_JSON or before.st_size != len(raw)
                    or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                    != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
                fail("INPUT_CHANGED_DURING_READ")
            return raw
    except GuardError:
        raise
    except OSError as exc:
        raise GuardError("INPUT_READ_FAILED") from exc


def publish(path: str | None, value: Any) -> None:
    raw = canonical(value)
    if len(raw) > MAX_JSON:
        fail("OUTPUT_SIZE_LIMIT")
    if path is None:
        sys.stdout.buffer.write(raw)
        return
    # Create-exclusive, no overwrite. A failed write can leave a partial file;
    # callers must not treat its mere existence as a valid receipt.
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise GuardError("OUTPUT_CREATE_OR_WRITE_FAILED") from exc


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["plan", "audit", "replay"])
    parser.add_argument("--contract", required=True)
    parser.add_argument("--contract-sha256", required=True)
    parser.add_argument("--repository", required=True, help="Reviewed logical owner/repo label, not authenticated provenance")
    parser.add_argument("--candidate", help="Full immutable candidate commit OID")
    parser.add_argument("--repo", help="Existing local Git checkout or bare repository; never fetched")
    parser.add_argument("--ref", help="Optional local ref before/after fence; not a remote lock")
    parser.add_argument("--report", help="Retained report for offline replay")
    parser.add_argument("--output", help="New output file; never overwritten")
    parser.add_argument("--timeout", type=float, default=45.0)
    args = parser.parse_args(argv)
    try:
        raw = read_file(args.contract)
        contract = contract_check(raw, args.contract_sha256, args.repository)
        if args.mode != "plan" and not args.candidate:
            fail("CANDIDATE_REQUIRED")
        if args.mode == "plan" and args.candidate:
            fail("PLAN_HAS_NO_CANDIDATE")
        if args.mode == "replay":
            if not args.report or args.repo or args.ref:
                fail("REPLAY_ARGUMENTS")
            result = replay(read_file(args.report), raw, args.contract_sha256,
                            args.repository, args.candidate)
            publish(args.output, result)
            return 0
        if not args.repo or args.report:
            fail("AUDIT_ARGUMENTS")
        store = GitStore(args.repo, args.timeout)
        if args.ref and store.ref_oid(args.ref) != contract["base_commit"]:
            fail("LOCAL_REF_NOT_AT_BASE")
        result = (build_plan(store, raw, args.contract_sha256, args.repository) if args.mode == "plan"
                  else audit(store, raw, args.contract_sha256, args.repository, args.candidate))
        if args.ref and store.ref_oid(args.ref) != contract["base_commit"]:
            fail("LOCAL_REF_MOVED_DURING_AUDIT")
        publish(args.output, result)
        if args.ref:
            print("Local ref matched base before/after; this is not a remote lease or merge permission.", file=sys.stderr)
        return 0 if args.mode == "plan" or result["state"] == "TREE_MATCH" else 1
    except GuardError as exc:
        print(json.dumps({"state": "HOLD", "reason": exc.code, "detail": exc.detail,
                          "merge_authorized": False}, sort_keys=True), file=sys.stderr)
        return 2
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError) as exc:
        # Fail closed without leaking possibly sensitive input or provider stderr.
        print(json.dumps({"state": "HOLD", "reason": "UNEXPECTED_INPUT_OR_IO",
                          "error_class": type(exc).__name__, "merge_authorized": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli())
