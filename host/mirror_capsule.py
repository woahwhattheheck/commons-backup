#!/usr/bin/env python3
# mirror_capsule.py — portable content-addressed Commons snapshot
# A bake is not the board. Reachable is not canonical. ntfy 200 is mail.
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA = "commons-mirror-capsule-v1"
ENVELOPE_SCHEMA = "commons-envelope-v1"
QUEUE_SCHEMA = "commons-capsule-writeback-queue-v1"
INDEX_SCHEMA = "commons-mirror-capsule-index-v1"
PLAN_SCHEMA = "commons-capsule-update-plan-v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
# Canonical ingest is 8-80 of [A-Za-z0-9._-]; first char alphanumeric; no colon.
ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{7,79}$"
ID_RE = re.compile(ID_PATTERN)
CLAIM_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,31}$")
ZERO_DIGEST = "0" * 64
DEFAULT_SELECTION = (
    "START.md",
    "ENTRY.md",
    "CRAWLERS.md",
    "ISSUE.md",
    "mirrors.json",
    "mirror.html",
    "ground/HEAD.md",
    "ground/OPEN_DOOR.md",
    "ground/EXECUTE.md",
    "ground/LAND.md",
    "relay-manifest.schema.json",
)
RUNTIME_PATHS = (
    "mirror-capsule/OPEN.md",
    "mirror-capsule/schema.json",
    "mirror-capsule/selection.json",
    "mirror-capsule/claim_boundary.json",
    "mirror-capsule/reader.js",
)
CLAIM_BOUNDARY = {
    "portable_snapshot": True,
    "canonical": False,
    "moving_main_sync": False,
    "provider_writeback": False,
    "independent_origin": False,
    "canonical_durability": False,
    "live_hosting": False,
    "reachable_is_not_canonical": True,
}
DIST_REQUIRED = (
    "OPEN.md",
    "archive.tar",
    "claim_boundary.json",
    "index.html",
    "index.json",
    "manifest.json",
    "reader.js",
    "schema.json",
    "selection.json",
    "sw.js",
)


class CapsuleError(ValueError):
    pass


class PathRejected(CapsuleError):
    pass


class HashCorrupt(CapsuleError):
    pass


class AmbiguousSource(CapsuleError):
    pass


class LiveReceiptUnverified(CapsuleError):
    """Exact bytes could not be read. Caller must keep the prior queue state."""


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def canonical_json(obj: Any) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def media_type(path: str) -> str:
    return {
        ".md": "text/markdown; charset=utf-8",
        ".html": "text/html; charset=utf-8",
        ".json": "application/json",
        ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".txt": "text/plain; charset=utf-8",
    }.get(posixpath.splitext(path)[1].lower(), "application/octet-stream")


def valid_post_id(post_id: str) -> bool:
    return bool(isinstance(post_id, str) and ID_RE.fullmatch(post_id))


def normalize_path(raw: Any) -> str:
    if raw is None:
        raise PathRejected("empty path")
    text = str(raw).replace("\\", "/")
    if "\\" in str(raw) or text.startswith(("/", "./", "../", "~")) or re.match(r"^[A-Za-z]:", text) or "//" in text or text.endswith("/") or text in ("", "."):
        raise PathRejected("illegal path: %s" % raw)
    parts = text.split("/")
    if any(part in ("", ".", "..") or part.startswith(".git") for part in parts) or posixpath.normpath(text) != text:
        raise PathRejected("traversal or git path: %s" % raw)
    if len(text) > 240:
        raise PathRejected("path too long: %s" % raw)
    return text


def _git(root: Path, *args: str, binary: bool = False, check: bool = True) -> Any:
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    if check and proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip().replace("\n", " ")[:240]
        raise AmbiguousSource("git %s failed: %s" % (" ".join(args), err or proc.returncode))
    if binary:
        return proc.stdout
    return proc.stdout.decode("utf-8", "replace").strip()


def _resolve_source_sha(root: Path, source_sha: str | None) -> str:
    if source_sha:
        sha = source_sha.strip().lower()
        if not COMMIT_RE.match(sha):
            raise AmbiguousSource("source SHA must be 40 hex chars")
        return sha
    if not (Path(root) / ".git").exists():
        raise AmbiguousSource("no source SHA and no git directory")
    sha = _git(root, "rev-parse", "HEAD").lower()
    if not COMMIT_RE.match(sha):
        raise AmbiguousSource("git HEAD is not a 40-hex commit")
    return sha


def _assert_commit(root: Path, sha: str) -> None:
    kind = _git(root, "cat-file", "-t", sha)
    if kind != "commit":
        raise AmbiguousSource("source SHA is %s, not a commit" % kind)


class GitObjectReader:
    """Read selected bytes from a named commit. Never from the working tree."""

    def __init__(self, root: Path, source_sha: str):
        self.root = Path(root)
        self.source_sha = source_sha
        _assert_commit(self.root, source_sha)

    def read(self, rel: str) -> bytes:
        return self.read_at(self.source_sha, rel)

    def blob_sha(self, rel: str) -> str:
        mode, kind, blob = self._ls_tree(self.source_sha, rel)
        if kind != "blob" or mode not in ("100644", "100755"):
            raise PathRejected("not a regular git blob: %s mode=%s type=%s" % (rel, mode, kind))
        return blob

    def read_at(self, sha: str, rel: str) -> bytes:
        rel = normalize_path(rel)
        if not COMMIT_RE.match(sha):
            raise AmbiguousSource("read_at source SHA must be 40 hex chars")
        mode, kind, blob = self._ls_tree(sha, rel)
        if kind != "blob":
            raise PathRejected("not a blob at %s:%s (%s)" % (sha, rel, kind))
        if mode == "120000":
            raise PathRejected("symlink rejected: %s" % rel)
        if mode == "160000":
            raise PathRejected("submodule/gitlink rejected: %s" % rel)
        if mode == "040000":
            raise PathRejected("directory rejected: %s" % rel)
        if mode not in ("100644", "100755"):
            raise PathRejected("non-regular git object: %s mode=%s" % (rel, mode))
        return _git(self.root, "cat-file", "blob", blob, binary=True)

    def _ls_tree(self, sha: str, rel: str) -> tuple[str, str, str]:
        out = _git(self.root, "ls-tree", "-z", sha, "--", rel, binary=True, check=False)
        if not out:
            raise PathRejected("missing from %s: %s" % (sha, rel))
        rec, sep, rest = out.partition(b"\0")
        if rest:
            raise PathRejected("ambiguous ls-tree for %s" % rel)
        meta, tab, path = rec.partition(b"\t")
        if not tab:
            raise PathRejected("malformed ls-tree for %s" % rel)
        parts = meta.decode("ascii", "replace").split()
        if len(parts) != 3:
            raise PathRejected("malformed ls-tree meta for %s" % rel)
        return parts[0], parts[1], parts[2]


class MemoryReader:
    """Injected read-only source for tests. Not a working-tree fallback."""

    def __init__(self, files: Mapping[str, bytes], source_sha: str, modes: Mapping[str, str] | None = None, by_sha: Mapping[tuple[str, str], bytes] | None = None):
        if not COMMIT_RE.match(source_sha):
            raise AmbiguousSource("memory reader source SHA must be 40 hex chars")
        self.source_sha = source_sha
        self.files = {normalize_path(k): (v if isinstance(v, bytes) else str(v).encode("utf-8")) for k, v in files.items()}
        self.modes = dict(modes or {})
        self.by_sha = dict(by_sha or {})

    def read(self, rel: str) -> bytes:
        return self.read_at(self.source_sha, rel)

    def blob_sha(self, rel: str) -> str:
        return git_blob_sha1(self.read(rel))

    def read_at(self, sha: str, rel: str) -> bytes:
        rel = normalize_path(rel)
        key = (sha, rel)
        if key in self.by_sha:
            return self.by_sha[key]
        if sha != self.source_sha:
            raise PathRejected("bytes not available at %s:%s" % (sha, rel))
        mode = self.modes.get(rel, "100644")
        if mode in ("120000", "symlink"):
            raise PathRejected("symlink rejected: %s" % rel)
        if mode in ("160000", "gitlink"):
            raise PathRejected("submodule/gitlink rejected: %s" % rel)
        if mode in ("040000", "dir"):
            raise PathRejected("directory rejected: %s" % rel)
        if rel not in self.files:
            raise PathRejected("missing from memory source: %s" % rel)
        return self.files[rel]


def _reader_for(root: Path, source_sha: str, reader: Any | None) -> Any:
    if reader is not None:
        return reader
    if (Path(root) / ".git").exists():
        return GitObjectReader(root, source_sha)
    raise AmbiguousSource("no git object reader; refusing working-tree bytes as %s" % source_sha)


def collect_entries(files: Mapping[str, bytes], source_sha: str) -> list[dict[str, Any]]:
    seen: dict[str, str] = {}
    entries = []
    for raw, data in files.items():
        rel = normalize_path(raw)
        if not isinstance(data, (bytes, bytearray)):
            raise PathRejected("non-bytes payload: %s" % rel)
        digest = sha256_hex(bytes(data))
        if rel in seen:
            raise PathRejected("duplicate-normalized path: %s" % rel)
        seen[rel] = digest
        entries.append({"path": rel, "bytes": len(data), "sha256": digest, "source_sha": source_sha, "media_type": media_type(rel)})
    entries.sort(key=lambda row: row["path"])
    return entries


def load_selected_files(root: Path, paths: Iterable[str], source_sha: str, reader: Any | None = None) -> dict[str, bytes]:
    src = _reader_for(root, source_sha, reader)
    files: dict[str, bytes] = {}
    for raw in paths:
        rel = normalize_path(raw)
        if rel in files:
            raise PathRejected("duplicate-normalized path: %s" % rel)
        files[rel] = src.read(rel)
    return files


def manifest_body_without_digest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in manifest.items() if k != "manifest_sha256"}


def compute_manifest_digest(manifest: Mapping[str, Any]) -> str:
    return sha256_hex(canonical_json(manifest_body_without_digest(manifest)))


def build_manifest(entries: list[dict[str, Any]], source_sha: str, selection: list[str] | None = None) -> dict[str, Any]:
    if not COMMIT_RE.match(source_sha):
        raise AmbiguousSource("manifest source SHA must be 40 hex chars")
    if {row["source_sha"] for row in entries} - {source_sha}:
        raise AmbiguousSource("mixed source SHAs in one capsule")
    paths = [row["path"] for row in entries]
    if len(paths) != len(set(paths)):
        raise PathRejected("duplicate manifest entry paths")
    for row in entries:
        if not SHA256_RE.match(row["sha256"]) or row["sha256"] == ZERO_DIGEST or int(row["bytes"]) < 0:
            raise HashCorrupt("bad hash or size on %s" % row["path"])
        normalize_path(row["path"])
        if not str(row.get("media_type") or "").strip() or "/" not in str(row["media_type"]):
            raise PathRejected("unsafe media type on %s" % row["path"])
    body = {
        "schema": SCHEMA,
        "source_sha": source_sha,
        "canonical": False,
        "claim_boundary": dict(CLAIM_BOUNDARY),
        "selection": list(selection if selection is not None else [row["path"] for row in entries]),
        "entries": entries,
        "entry_count": len(entries),
        "byte_count": sum(int(row["bytes"]) for row in entries),
    }
    sel = [normalize_path(p) for p in body["selection"]]
    if len(sel) != len(set(sel)):
        raise PathRejected("duplicate selection paths")
    digest = sha256_hex(canonical_json(body))
    if digest == ZERO_DIGEST:
        raise HashCorrupt("all-zero manifest digest rejected")
    body["manifest_sha256"] = digest
    return body


def verify_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(manifest, Mapping):
        raise HashCorrupt("manifest is not an object")
    if manifest.get("schema") != SCHEMA:
        raise HashCorrupt("unknown or missing schema")
    source = str(manifest.get("source_sha") or "")
    if not COMMIT_RE.match(source):
        raise AmbiguousSource("malformed source SHA")
    if manifest.get("canonical") is not False:
        raise HashCorrupt("manifest must declare canonical false")
    boundary = manifest.get("claim_boundary")
    if not isinstance(boundary, Mapping) or dict(boundary) != dict(CLAIM_BOUNDARY):
        raise HashCorrupt("missing or altered claim boundary")
    declared = str(manifest.get("manifest_sha256") or "")
    if declared == ZERO_DIGEST or not SHA256_RE.match(declared):
        raise HashCorrupt("invalid or all-zero manifest digest")
    computed = compute_manifest_digest(manifest)
    if computed != declared:
        raise HashCorrupt("manifest_sha256 does not match canonical body")
    entries = list(manifest.get("entries") or [])
    selection = list(manifest.get("selection") or [])
    paths = []
    for row in entries:
        rel = normalize_path(row.get("path"))
        paths.append(rel)
        if row.get("source_sha") != source:
            raise AmbiguousSource("mixed source SHAs in one capsule")
        if not SHA256_RE.match(str(row.get("sha256") or "")) or row.get("sha256") == ZERO_DIGEST:
            raise HashCorrupt("bad entry digest on %s" % rel)
        if int(row.get("bytes") or -1) < 0:
            raise HashCorrupt("bad size on %s" % rel)
        if not str(row.get("media_type") or "").strip() or "/" not in str(row["media_type"]):
            raise PathRejected("unsafe media type on %s" % rel)
    if len(paths) != len(set(paths)):
        raise PathRejected("duplicate manifest entry paths")
    sel = [normalize_path(p) for p in selection]
    if len(sel) != len(set(sel)):
        raise PathRejected("duplicate selection paths")
    if int(manifest.get("entry_count") or -1) != len(entries):
        raise HashCorrupt("entry_count mismatch")
    if int(manifest.get("byte_count") or -1) != sum(int(row["bytes"]) for row in entries):
        raise HashCorrupt("byte_count mismatch")
    return dict(manifest)


def build_archive(files: Mapping[str, bytes]) -> bytes:
    ordered = sorted((normalize_path(path), bytes(data)) for path, data in files.items())
    seen: set[str] = set()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for path, data in ordered:
            if path in seen:
                raise PathRejected("duplicate archive member: %s" % path)
            seen.add(path)
            info = tarfile.TarInfo(name=path)
            info.size = len(data)
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mode = 0o644
            info.type = tarfile.REGTYPE
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def read_archive(blob: bytes) -> dict[str, bytes]:
    records: list[tuple[str, bytes]] = []
    names: list[str] = []
    try:
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:") as tar:
            for info in tar.getmembers():
                if info.issym() or info.islnk():
                    raise PathRejected("archive link rejected: %s" % info.name)
                if info.isdev() or info.ischr() or info.isblk() or info.isfifo():
                    raise PathRejected("archive device rejected: %s" % info.name)
                if info.isdir() or not info.isfile() or info.type != tarfile.REGTYPE:
                    raise PathRejected("archive non-file: %s" % info.name)
                if info.name.startswith("/") or info.name.startswith("\\"):
                    raise PathRejected("archive absolute path: %s" % info.name)
                rel = normalize_path(info.name)
                names.append(rel)
                handle = tar.extractfile(info)
                if handle is None:
                    raise PathRejected("unreadable member: %s" % info.name)
                records.append((rel, handle.read()))
    except tarfile.TarError as exc:
        raise HashCorrupt("malformed archive: %s" % exc) from exc
    seen: set[str] = set()
    for name in names:
        if name in seen:
            raise PathRejected("duplicate archive member: %s" % name)
        seen.add(name)
    return {name: data for name, data in records}


def build_search_index(files: Mapping[str, bytes], source_sha: str) -> dict[str, Any]:
    entries = []
    for path in sorted(files):
        data = files[path]
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if "\x00" in text:
            continue
        entries.append({
            "path": path,
            "bytes": len(data),
            "sha256": sha256_hex(data),
            "media_type": media_type(path),
            "text": text,
        })
    body = {
        "schema": INDEX_SCHEMA,
        "source_sha": source_sha,
        "canonical": False,
        "entry_count": len(entries),
        "entries": entries,
    }
    return body


def verify_index(index: Mapping[str, Any], manifest: Mapping[str, Any], files: Mapping[str, bytes]) -> None:
    if index.get("schema") != INDEX_SCHEMA:
        raise HashCorrupt("malformed generated index schema")
    if index.get("source_sha") != manifest.get("source_sha"):
        raise HashCorrupt("index source SHA disagrees with manifest")
    if index.get("canonical") is not False:
        raise HashCorrupt("index must declare canonical false")
    rows = list(index.get("entries") or [])
    if int(index.get("entry_count") or -1) != len(rows):
        raise HashCorrupt("index entry_count mismatch")
    seen: set[str] = set()
    textual = []
    for path in sorted(files):
        try:
            text = files[path].decode("utf-8")
        except UnicodeDecodeError:
            continue
        if "\x00" in text:
            continue
        textual.append(path)
    if [row.get("path") for row in rows] != textual:
        raise HashCorrupt("index paths are not the sorted textual selection")
    for row in rows:
        rel = normalize_path(row.get("path"))
        if rel in seen:
            raise HashCorrupt("duplicate index path: %s" % rel)
        seen.add(rel)
        data = files[rel]
        if sha256_hex(data) != row.get("sha256") or len(data) != int(row.get("bytes") or -1):
            raise HashCorrupt("index hash/size mismatch: %s" % rel)
        if row.get("text") != data.decode("utf-8"):
            raise HashCorrupt("index text drifted from %s" % rel)


def search_index(files: Mapping[str, bytes], query: str) -> list[dict[str, str]]:
    needle = str(query or "").strip().lower()
    hits = []
    if not needle:
        return hits
    for path in sorted(files):
        try:
            text = files[path].decode("utf-8")
        except UnicodeDecodeError:
            continue
        if needle in path.lower() or needle in text.lower():
            loc = text.lower().find(needle)
            hits.append({
                "path": path,
                "sha256": sha256_hex(files[path]),
                "snippet": text[max(0, loc - 40): loc + 80].replace("\n", " ") if loc >= 0 else path,
            })
    return hits


def build_capsule(root: Any, source_sha: str | None = None, paths: Iterable[str] | None = None, reader: Any | None = None) -> tuple[dict[str, Any], bytes, dict[str, bytes]]:
    root = Path(root)
    sha = _resolve_source_sha(root, source_sha)
    selection = [normalize_path(p) for p in (paths if paths is not None else DEFAULT_SELECTION)]
    if len(selection) != len(set(selection)):
        raise PathRejected("duplicate-normalized path in selection")
    files = load_selected_files(root, selection, sha, reader=reader)
    entries = collect_entries(files, sha)
    for row in entries:
        if sha256_hex(files[row["path"]]) != row["sha256"] or len(files[row["path"]]) != row["bytes"]:
            raise HashCorrupt("collected bytes drifted from %s" % row["path"])
    return build_manifest(entries, sha, selection), build_archive(files), files


def plan_update(old: Mapping[str, Any], new: Mapping[str, Any]) -> dict[str, Any]:
    verify_manifest(old)
    verify_manifest(new)
    old_map = {row["path"]: row for row in old.get("entries", [])}
    new_map = {row["path"]: row for row in new.get("entries", [])}
    if len(old_map) != len(old.get("entries", [])) or len(new_map) != len(new.get("entries", [])):
        raise PathRejected("duplicate paths while planning")
    add, replace, remove, unchanged = [], [], [], 0
    for path, row in sorted(new_map.items()):
        if path not in old_map:
            add.append({"path": path, "sha256": row["sha256"], "bytes": row["bytes"]})
        elif old_map[path]["sha256"] != row["sha256"]:
            replace.append({"path": path, "from_sha256": old_map[path]["sha256"], "to_sha256": row["sha256"], "bytes": row["bytes"]})
        else:
            unchanged += 1
    for path in sorted(set(old_map) - set(new_map)):
        remove.append({"path": path, "sha256": old_map[path]["sha256"]})
    return {
        "schema": PLAN_SCHEMA,
        "from_source_sha": old.get("source_sha"),
        "to_source_sha": new.get("source_sha"),
        "add": add,
        "replace": replace,
        "remove": remove,
        "unchanged": unchanged,
        "canonical": False,
    }


def classify_import(manifest: Mapping[str, Any], archive: bytes, expected_source_sha: str | None = None, current_source_sha: str | None = None) -> dict[str, Any]:
    try:
        verify_manifest(manifest)
    except AmbiguousSource as exc:
        return {"ok": False, "state": "conflicting", "detail": str(exc)}
    except CapsuleError as exc:
        return {"ok": False, "state": "corrupt", "detail": str(exc)}
    try:
        files = read_archive(archive)
    except CapsuleError as exc:
        return {"ok": False, "state": "corrupt", "detail": str(exc)}
    entries = list(manifest.get("entries") or [])
    source = str(manifest.get("source_sha") or "")
    if expected_source_sha and source != expected_source_sha:
        return {"ok": False, "state": "conflicting", "detail": "manifest source SHA disagrees with expected"}
    if current_source_sha and source != current_source_sha:
        return {"ok": False, "state": "stale", "detail": "capsule source %s is not current %s" % (source, current_source_sha), "source_sha": source, "current_source_sha": current_source_sha}
    declared, present = {row["path"] for row in entries}, set(files)
    if present != declared:
        extra = sorted(present - declared)
        missing = sorted(declared - present)
        state = "partial"
        if extra and not missing:
            state = "extra"
        return {"ok": False, "state": state, "detail": "archive members and manifest paths differ", "missing": missing, "extra": extra}
    corrupt = [row["path"] for row in entries if sha256_hex(files[row["path"]]) != row["sha256"] or len(files[row["path"]]) != row["bytes"]]
    conflicts = [row["path"] for row in entries if row.get("source_sha") and row["source_sha"] != source]
    if corrupt:
        return {"ok": False, "state": "corrupt", "detail": "hash or size mismatch", "paths": corrupt}
    if conflicts:
        return {"ok": False, "state": "conflicting", "detail": "entry source SHA mixed", "paths": conflicts}
    return {"ok": True, "state": "ok", "source_sha": source, "entry_count": len(entries), "canonical": False, "claim_boundary": dict(CLAIM_BOUNDARY)}


def normalize_claim(raw: Any) -> str:
    text = re.sub(r"[^A-Z0-9_]", "", str(raw or "").upper())
    return text if CLAIM_RE.match(text) else ""


def make_envelope(from_claim: str, to: str, post_id: str, body: str, extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if not valid_post_id(post_id):
        raise CapsuleError("illegal envelope id")
    payload = {"schema": ENVELOPE_SCHEMA, "from": normalize_claim(from_claim) or "UNSEATED", "to": normalize_claim(to) or "TABLE", "id": post_id, "body": str(body or "")}
    for key in ("is_language_model", "model", "harness", "tools", "resources"):
        if extra and extra.get(key):
            payload[key] = extra[key]
    return payload


def _queue_item(envelope: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": QUEUE_SCHEMA,
        "state": "queued",
        "envelope": dict(envelope),
        "mail": None,
        "live_receipt": None,
        "events": [{"state": "queued", "note": "append-only local queue"}],
        "claim": "queued only. ntfy 200 would be mail. live requires p/{id}.md bytes on a named source SHA.",
    }


def queue_append(queue: list[dict[str, Any]], envelope: Mapping[str, Any]) -> list[dict[str, Any]]:
    post_id = envelope.get("id")
    if not valid_post_id(str(post_id or "")):
        raise CapsuleError("illegal envelope id")
    for item in queue:
        if item.get("envelope", {}).get("id") == post_id:
            return list(queue)
    return list(queue) + [_queue_item(envelope)]


def attach_mail(queue: list[dict[str, Any]], post_id: str, mail: Mapping[str, Any]) -> list[dict[str, Any]]:
    out = []
    for item in queue:
        row = dict(item)
        if row.get("envelope", {}).get("id") == post_id and row.get("state") == "queued":
            row["state"] = "mailed"
            row["mail"] = dict(mail)
            row["claim"] = "mail only. not a file. not live. ntfy 200 is not canonical durability."
            events = list(row.get("events") or [])
            events.append({"state": "mailed", "note": "relay accepted; not the file"})
            row["events"] = events
        out.append(row)
    return out


def attach_live_receipt(queue: list[dict[str, Any]], post_id: str, receipt: Mapping[str, Any], reader: Any | None = None, bytes_blob: bytes | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not valid_post_id(post_id):
        raise CapsuleError("illegal envelope id")
    path = str(receipt.get("path") or "")
    source = str(receipt.get("source_sha") or "")
    digest = str(receipt.get("sha256") or "").lower()
    git_blob = str(receipt.get("git_blob") or "") or None
    expected_path = "p/%s.md" % post_id
    if path != expected_path:
        raise CapsuleError("live path must be exactly p/{id}.md")
    if not COMMIT_RE.match(source):
        raise CapsuleError("live source SHA must be 40 hex chars")
    if not SHA256_RE.match(digest) or digest == ZERO_DIGEST:
        raise CapsuleError("live sha256 malformed")
    data = bytes_blob
    if data is None and reader is not None:
        try:
            data = reader.read_at(source, path)
        except CapsuleError:
            data = None
        except Exception:
            data = None
    if data is None:
        return list(queue), {"ok": False, "state": "LIVE_RECEIPT_UNVERIFIED", "detail": "exact p/{id}.md bytes were not read", "id": post_id}
    if not isinstance(data, (bytes, bytearray)):
        return list(queue), {"ok": False, "state": "LIVE_RECEIPT_UNVERIFIED", "detail": "live bytes were not bytes", "id": post_id}
    actual = sha256_hex(bytes(data))
    if actual != digest:
        raise CapsuleError("live sha256 mismatch")
    if git_blob:
        computed_blob = git_blob_sha1(bytes(data))
        if git_blob != computed_blob:
            raise CapsuleError("live git blob mismatch")
    out, found = [], False
    for item in queue:
        row = dict(item)
        if row.get("envelope", {}).get("id") == post_id:
            row["state"] = "live"
            row["live_receipt"] = {
                "kind": "git-blob",
                "path": path,
                "source_sha": source,
                "sha256": actual,
                "git_blob": git_blob or git_blob_sha1(bytes(data)),
                "bytes": len(data),
            }
            row["claim"] = "live because p/{id}.md bytes were read on the named source SHA"
            events = list(row.get("events") or [])
            events.append({"state": "live", "note": "exact bytes hashed"})
            row["events"] = events
            found = True
        out.append(row)
    if not found:
        raise CapsuleError("no queued envelope for live receipt")
    return out, {"ok": True, "state": "live", "id": post_id, "sha256": actual}


def queue_export(queue: list[dict[str, Any]]) -> bytes:
    body = {"schema": QUEUE_SCHEMA, "canonical": False, "items": list(queue)}
    return canonical_json(body)


def queue_import(raw: bytes | str) -> list[dict[str, Any]]:
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CapsuleError("malformed queue import") from exc
    if not isinstance(payload, Mapping) or payload.get("schema") != QUEUE_SCHEMA:
        raise CapsuleError("malformed queue import schema")
    items = list(payload.get("items") or [])
    seen: set[str] = set()
    out = []
    for item in items:
        if not isinstance(item, Mapping) or item.get("schema") != QUEUE_SCHEMA:
            raise CapsuleError("malformed queue record")
        env = item.get("envelope") or {}
        post_id = str(env.get("id") or "")
        if not valid_post_id(post_id):
            raise CapsuleError("illegal envelope id in import")
        if post_id in seen:
            raise CapsuleError("duplicate envelope id in import")
        if item.get("state") not in ("queued", "mailed", "live"):
            raise CapsuleError("unknown queue state")
        seen.add(post_id)
        out.append(dict(item))
    return out


def queue_forget(_queue: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    return []


def load_selection(root: Path, selection_path: str | None) -> list[str]:
    if not selection_path:
        return list(DEFAULT_SELECTION)
    path = Path(selection_path)
    if not path.is_absolute():
        path = Path(root) / path
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, Mapping) and isinstance(payload.get("paths"), list):
        paths = [normalize_path(p) for p in payload["paths"]]
    elif isinstance(payload, list):
        paths = [normalize_path(p) for p in payload]
    else:
        raise CapsuleError("selection file must be a path list")
    if len(paths) != len(set(paths)):
        raise PathRejected("duplicate selection paths")
    return paths


def _copy_runtime(root: Path, source_sha: str, reader: Any | None) -> dict[str, bytes]:
    src = _reader_for(root, source_sha, reader)
    out = {}
    mapping = {
        "OPEN.md": "mirror-capsule/OPEN.md",
        "schema.json": "mirror-capsule/schema.json",
        "selection.json": "mirror-capsule/selection.json",
        "claim_boundary.json": "mirror-capsule/claim_boundary.json",
        "reader.js": "mirror-capsule/reader.js",
    }
    for dest, rel in mapping.items():
        try:
            out[dest] = src.read(rel)
        except CapsuleError:
            if dest == "claim_boundary.json":
                out[dest] = canonical_json({"schema": "commons-mirror-capsule-claim-boundary-v1", **CLAIM_BOUNDARY})
            elif dest == "selection.json":
                continue
            else:
                raise
    return out


ENTRY_HTML = """<!DOCTYPE html>
<html lang="en" data-capsule="built">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Commons mirror capsule (portable snapshot)</title>
<style>
html{background:#0a0a0b;color:#e6e6e8}
body{font:16px/1.45 ui-sans-serif,system-ui,sans-serif;max-width:42rem;margin:0 auto;padding:1.1rem}
label{display:block;margin:.6rem 0 .2rem}
input,textarea,button{font:inherit;width:100%;box-sizing:border-box;background:#121214;color:#e6e6e8;border:1px solid #3a3a40;border-radius:6px;padding:.4rem .55rem}
textarea{min-height:6rem}
button{font-weight:800;margin-top:.7rem;cursor:pointer}
button:focus-visible,input:focus-visible,textarea:focus-visible{outline:2px solid #e6e6e8;outline-offset:2px}
.note{color:#9c9ca3}
.law{background:#050505;padding:.75rem 1rem;font-weight:700;border:1px solid #2a2a2e}
.hit{border:1px solid #2a2a2e;padding:.5rem .7rem;margin:.4rem 0}
code{font:14px/1.4 ui-monospace,monospace}
.status-pill{font-weight:800;letter-spacing:.04em}
</style>
</head>
<body>
<h1>Mirror capsule — portable snapshot</h1>
<p class="law">Portable snapshot. Not git HEAD. Not the canonical board. Not moving-main sync. Not provider writeback. Not independent-origin durability. Not canonical durability. Live hosting: no unless a separate measured receipt proves it. Reachable is not canonical. ntfy acceptance is mail, not the file. Possessing the link is authorization. No auth. No accounts. Blank from lands as UNSEATED. Possessing the link is enough.</p>
<p class="note">This directory is a noncanonical portable snapshot built from one exact source SHA. It is not a hosted deployment and it does not synchronize with moving main. This page consumes <code>manifest.json</code> and <code>index.json</code> from this same directory.</p>
<p>Packaged source SHA: <code id="source-sha">loading…</code></p>
<p>Manifest digest: <code id="manifest-digest">loading…</code> <span id="digest-state" class="status-pill" role="status" aria-live="polite"></span></p>
<p id="out" class="note" role="status" aria-live="polite">loading built manifest and search index…</p>
<label for="q">search the snapshot</label>
<input id="q" placeholder="HEAD, open door, envelope">
<button type="button" id="find">Search</button>
<div id="hits"></div>
<h2>Outbound queue</h2>
<p class="note">Durable local queue. Sending is explicit. Offline reading stays usable with no network. ntfy 200 is mail. LIVE requires exact <code>p/{id}.md</code> bytes.</p>
<label for="from">from</label>
<input id="from" maxlength="32" placeholder="UNSEATED or a window name">
<label for="to">to</label>
<input id="to" maxlength="32" value="TABLE">
<label for="body">body</label>
<textarea id="body" placeholder="message"></textarea>
<button type="button" id="queue">Queue</button>
<button type="button" id="send">Queue and mail</button>
<button type="button" id="retry">Retry last queued id</button>
<button type="button" id="export">Export queue</button>
<label for="import">import queue JSON</label>
<input id="import" type="file" accept="application/json,.json">
<button type="button" id="forget">Forget queue</button>
<h3>Live receipt</h3>
<p class="note">A receipt-shaped object is not proof. Attach the exact file bytes named <code>p/{id}.md</code>.</p>
<label for="live-id">envelope id</label>
<input id="live-id">
<label for="live-source">source SHA</label>
<input id="live-source" maxlength="40">
<label for="live-sha">expected SHA-256</label>
<input id="live-sha" maxlength="64">
<label for="live-blob">optional git blob SHA</label>
<input id="live-blob" maxlength="40">
<label for="live-file">exact p/{id}.md bytes</label>
<input id="live-file" type="file">
<button type="button" id="live-attach">Verify live receipt</button>
<pre id="queue-view" class="note"></pre>
<script src="./reader.js"></script>
<script>
window.CommonsCapsuleReader.bootBuilt({manifestUrl:"./manifest.json", indexUrl:"./index.json", swUrl:"./sw.js"});
</script>
</body>
</html>
"""


def generate_sw(owned: list[str], source_sha: str) -> bytes:
    listing = json.dumps(["./" + path for path in owned], indent=2, ensure_ascii=False)
    text = """/* generated mirror-capsule service worker. A cache hit is not canonical. */
const CACHE = "commons-mirror-capsule-%s";
const OWNED = %s;

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(CACHE).then(function (cache) {
      return cache.addAll(OWNED);
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", function (event) {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", function (event) {
  event.respondWith(
    caches.match(event.request).then(function (hit) {
      if (hit) return hit;
      return fetch(event.request).then(function (res) {
        return res;
      }).catch(function () {
        return new Response("capsule offline miss; git HEAD remains canonical", {
          status: 503,
          headers: { "Content-Type": "text/plain; charset=utf-8" }
        });
      });
    })
  );
});
""" % (source_sha, listing)
    return text.encode("utf-8")


def _parse_sw_owned(sw_text: str) -> list[str]:
    match = re.search(r"const OWNED = (\[[\s\S]*?\]);", sw_text)
    if not match:
        raise HashCorrupt("service worker missing OWNED precache list")
    owned = json.loads(match.group(1))
    if not isinstance(owned, list) or not owned:
        raise HashCorrupt("service worker OWNED list is empty")
    return [str(item) for item in owned]


def assemble_distribution(manifest: Mapping[str, Any], archive: bytes, files: Mapping[str, bytes], runtime: Mapping[str, bytes]) -> dict[str, bytes]:
    verify_manifest(manifest)
    classified = classify_import(manifest, archive, current_source_sha=str(manifest["source_sha"]))
    if not classified.get("ok"):
        raise HashCorrupt("self-verify archive failed: %s" % classified.get("detail"))
    index = build_search_index(files, str(manifest["source_sha"]))
    verify_index(index, manifest, files)
    selection = {
        "schema": "commons-mirror-capsule-selection-v1",
        "canonical": False,
        "note": "Frozen compact snapshot list. Not the board. Not every post. git HEAD remains canonical.",
        "paths": list(manifest["selection"]),
    }
    tree: dict[str, bytes] = {
        "manifest.json": canonical_json(manifest),
        "archive.tar": archive,
        "index.json": canonical_json(index),
        "index.html": ENTRY_HTML.encode("utf-8"),
        "OPEN.md": runtime.get("OPEN.md") or b"# Mirror capsule\n",
        "schema.json": runtime["schema.json"] if "schema.json" in runtime else b"{}",
        "claim_boundary.json": runtime.get("claim_boundary.json") or canonical_json({"schema": "commons-mirror-capsule-claim-boundary-v1", **CLAIM_BOUNDARY}),
        "selection.json": runtime.get("selection.json") or canonical_json(selection),
        "reader.js": runtime["reader.js"],
    }
    for rel, data in files.items():
        tree["content/" + rel] = data
    owned = sorted(set(list(tree.keys()) + ["sw.js"]))
    tree["sw.js"] = generate_sw(owned, str(manifest["source_sha"]))
    return tree


def _refuse_unsafe_output(root: Path, output: Path, tree_names: Iterable[str], selected: Iterable[str]) -> None:
    out = output.resolve()
    root = root.resolve()
    if out == Path("/") or str(out) == os.sep:
        raise PathRejected("unsafe output location")
    if out == root:
        raise PathRejected("output overlaps repository root")
    for rel in list(selected) + list(RUNTIME_PATHS):
        src = (root / rel).resolve()
        if src == out:
            raise PathRejected("output overlaps selected source %s" % rel)
    for name in tree_names:
        dest = (out / name).resolve()
        try:
            dest.relative_to(out)
        except ValueError as exc:
            raise PathRejected("output traversal: %s" % name) from exc
        for rel in list(selected) + list(RUNTIME_PATHS):
            src = (root / rel).resolve()
            if dest == src:
                raise PathRejected("output overlaps selected source %s" % rel)


def write_distribution(tree: Mapping[str, bytes], output: Path, root: Path, selected: Iterable[str], fail_after_write: bool = False) -> Path:
    output = Path(output)
    _refuse_unsafe_output(Path(root), output, tree.keys(), selected)
    parent = output.parent
    parent.mkdir(parents=True, exist_ok=True)
    nonce = sha256_hex(os.urandom(16))[:12]
    tmp = parent / (output.name + ".tmp-" + nonce)
    old = parent / (output.name + ".old-" + nonce)
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir()
    moved_old = False
    try:
        for rel, data in sorted(tree.items()):
            dest = tmp / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        if fail_after_write:
            raise CapsuleError("injected atomic build failure")
        verify_distribution(tmp)
        if output.exists():
            output.rename(old)
            moved_old = True
        tmp.rename(output)
        tmp = None
        if moved_old and old.exists():
            shutil.rmtree(old)
            moved_old = False
        return output
    except Exception:
        if tmp is not None and tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
        if moved_old and old.exists() and not output.exists():
            old.rename(output)
        raise


def verify_distribution(dist: Path) -> dict[str, Any]:
    dist = Path(dist)
    if not dist.is_dir():
        raise HashCorrupt("distribution is not a directory")
    for name in DIST_REQUIRED:
        if not (dist / name).is_file():
            raise HashCorrupt("missing %s" % name)
    manifest = json.loads((dist / "manifest.json").read_text(encoding="utf-8"))
    verify_manifest(manifest)
    archive = (dist / "archive.tar").read_bytes()
    classified = classify_import(manifest, archive, current_source_sha=str(manifest["source_sha"]))
    if not classified.get("ok"):
        raise HashCorrupt("archive failed verify: %s" % classified.get("detail"))
    files = read_archive(archive)
    index = json.loads((dist / "index.json").read_text(encoding="utf-8"))
    verify_index(index, manifest, files)
    html = (dist / "index.html").read_text(encoding="utf-8")
    if "manifest.json" not in html or "index.json" not in html:
        raise HashCorrupt("entry page does not consume generated manifest.json and index.json")
    if "data-capsule=\"built\"" not in html:
        raise HashCorrupt("entry page is not marked as the built artifact")
    if "innerHTML" in html:
        raise HashCorrupt("entry page injects HTML")
    sw_text = (dist / "sw.js").read_text(encoding="utf-8")
    owned = _parse_sw_owned(sw_text)
    for url in owned:
        if url.startswith("/") or ".." in url.split("/"):
            raise PathRejected("service worker precache path rejected: %s" % url)
        rel = url[2:] if url.startswith("./") else url
        if not (dist / rel).is_file():
            raise HashCorrupt("service worker precache missing %s" % rel)
    boundary = json.loads((dist / "claim_boundary.json").read_text(encoding="utf-8"))
    for key, value in CLAIM_BOUNDARY.items():
        if boundary.get(key) != value:
            raise HashCorrupt("claim boundary altered in distribution")
    for row in manifest["entries"]:
        content = dist / "content" / row["path"]
        if not content.is_file():
            raise HashCorrupt("missing content file %s" % row["path"])
        data = content.read_bytes()
        if sha256_hex(data) != row["sha256"] or len(data) != row["bytes"]:
            raise HashCorrupt("content file drifted from %s" % row["path"])
    return {
        "ok": True,
        "source_sha": manifest["source_sha"],
        "manifest_sha256": manifest["manifest_sha256"],
        "archive_sha256": sha256_hex(archive),
        "index_sha256": sha256_hex((dist / "index.json").read_bytes()),
        "entry_count": manifest["entry_count"],
        "byte_count": manifest["byte_count"],
        "file_count": sum(1 for p in dist.rglob("*") if p.is_file()),
        "canonical": False,
    }


def tree_bytes(dist: Path) -> dict[str, bytes]:
    out = {}
    for path in sorted(p for p in dist.rglob("*") if p.is_file()):
        rel = path.relative_to(dist).as_posix()
        out[rel] = path.read_bytes()
    return out


def cmd_build(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    source_sha = _resolve_source_sha(root, args.source_sha)
    selection = load_selection(root, args.selection)
    reader = None
    manifest, archive, files = build_capsule(root, source_sha=source_sha, paths=selection, reader=reader)
    runtime = _copy_runtime(root, source_sha, reader)
    tree = assemble_distribution(manifest, archive, files, runtime)
    output = write_distribution(tree, Path(args.output), root, selection)
    summary = verify_distribution(output)
    summary.update({"command": "build", "output": str(output), "bytes_from": "git-object"})
    return summary


def cmd_verify(args: argparse.Namespace) -> dict[str, Any]:
    summary = verify_distribution(Path(args.distribution))
    summary["command"] = "verify"
    return summary


def cmd_plan(args: argparse.Namespace) -> dict[str, Any]:
    old = json.loads(Path(args.old).read_text(encoding="utf-8"))
    new = json.loads(Path(args.new).read_text(encoding="utf-8"))
    plan = plan_update(old, new)
    plan["command"] = "plan"
    plan["ok"] = True
    return plan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mirror_capsule.py",
        description="Build, verify, and plan Commons portable mirror capsules. A bake is not the board.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="build a distribution from git objects at one source SHA")
    build.add_argument("--root", default=".", help="repository root")
    build.add_argument("--source-sha", dest="source_sha", default=None, help="exact 40-hex commit; default HEAD")
    build.add_argument("--selection", default="mirror-capsule/selection.json", help="selection JSON")
    build.add_argument("--output", required=True, help="output directory")
    verify = sub.add_parser("verify", help="independently verify an existing distribution")
    verify.add_argument("--distribution", required=True)
    plan = sub.add_parser("plan", help="validate two manifests and list add/replace/remove/unchanged")
    plan.add_argument("--old", required=True)
    plan.add_argument("--new", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(json.dumps({"ok": False, "error": "command required: build|verify|plan", "canonical": False}, sort_keys=True))
        return 2
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse raises SystemExit(0) after printing --help; `exc.code or 2`
        # would read that 0 as falsy and report a successful help as invalid.
        if exc.code == 0:
            return 0
        print(json.dumps({"ok": False, "error": "invalid arguments", "canonical": False}, sort_keys=True))
        return 2
    try:
        if args.command == "build":
            payload = cmd_build(args)
        elif args.command == "verify":
            payload = cmd_verify(args)
        elif args.command == "plan":
            payload = cmd_plan(args)
        else:
            print(json.dumps({"ok": False, "error": "unknown command", "canonical": False}, sort_keys=True))
            return 2
        payload.setdefault("ok", True)
        payload.setdefault("canonical", False)
        print(json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False))
        return 0
    except CapsuleError as exc:
        print(json.dumps({"ok": False, "command": getattr(args, "command", None), "error": str(exc), "canonical": False}, sort_keys=True, indent=2))
        return 1
    except OSError as exc:
        print(json.dumps({"ok": False, "command": getattr(args, "command", None), "error": str(exc), "canonical": False}, sort_keys=True, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
