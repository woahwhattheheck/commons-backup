#!/usr/bin/env python3
"""host/feature_tracker.py — evidence-derived feature tracker.

Append-only registry: features/registry/{id}.json
Append-only evidence: features/evidence/{id}.json
Projection: feature-tracker.json + feature-tracker.html

Status is derived from git/tree/receipt evidence. Author prose, chat,
Slack, ntfy 200, an open PR, and a claimed_status field never promote
SOURCE_BUILT, TESTS_PRESENT, or LIVE. Source and live stay separate. Pages is a bake.

  python3 host/feature_tracker.py
  python3 host/feature_tracker.py --root .
  python3 host/feature_tracker.py --write
  python3 host/feature_tracker.py --self-test
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    import hub_pages
except ImportError:
    hub_pages = None



def _preserve_live_cash(prev, doc, root=None):
    """Keep tip Autopsy/$199 product doors across feature-tracker remints.

    Paths only — never invent Stripe. Mirrors hub_pages KEEP (newbot-13/14).
    Retired products (deleted checkout page) are not resurrected.
    """
    if hub_pages is not None:
        return hub_pages._preserve_live_cash(prev, doc, root)
    if not isinstance(prev, dict) or not isinstance(doc, dict):
        return doc
    live = prev.get("live_cash")
    if isinstance(live, dict) and live.get("products"):
        if root is not None:
            live = dict(live)
            for key in ("products", "larger_fixed"):
                items = live.get(key)
                if isinstance(items, list):
                    live[key] = [
                        item for item in items
                        if not isinstance(item, dict)
                        or not item.get("path")
                        or os.path.isfile(os.path.join(root, item["path"]))
                    ]
            if not live.get("products") and not live.get("larger_fixed"):
                return doc
        doc["live_cash"] = live
    return doc


def _load_prev_tip_json(root, name):
    path = os.path.join(root, name)
    try:
        with open(path, encoding="utf-8") as handle:
            prev = json.load(handle)
    except (OSError, ValueError):
        return {}
    return prev if isinstance(prev, dict) else {}

SCHEMA_FEATURE = "commons-feature-v1"
SCHEMA_EVIDENCE = "commons-feature-evidence-v1"
SCHEMA_PROJECTION = "commons-feature-tracker-v1"
SCHEMA = SCHEMA_FEATURE
EVIDENCE_SCHEMA = SCHEMA_EVIDENCE
REGISTRY_DIR = os.path.join("features", "registry")
EVIDENCE_DIR = os.path.join("features", "evidence")
HTML_OUT = "feature-tracker.html"
JSON_OUT = "feature-tracker.json"
ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,80}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
BLOB_RE = re.compile(r"^[0-9a-f]{40,64}$")

EVIDENCE_KINDS = (
    "SOURCE_PATHS",
    "TEST_PATHS",
    "GIT_SHA",
    "BLOB",
    "LIVE_MEASUREMENT",
    "RECEIPT",
    "SUPERSEDE",
)

SOURCE_STATUSES = ("PLANNED", "SOURCE_BUILT", "DEGRADED")
TEST_STATUSES = ("UNTESTED", "TESTS_PRESENT", "DEGRADED")
LIVE_STATUSES = ("UNMEASURED", "LIVE", "DEGRADED")
ROLLUPS = ("PLANNED", "SOURCE_BUILT", "TESTS_PRESENT", "LIVE", "DEGRADED", "SUPERSEDED")
ROLLUP_SORT = ("LIVE", "TESTS_PRESENT", "SOURCE_BUILT", "DEGRADED", "PLANNED", "SUPERSEDED")

FEATURE_REQUIRED = (
    "schema",
    "id",
    "name",
    "capability",
    "owner_subsystem",
    "carrier",
    "claimed_paths",
    "test_paths",
    "public_entrypoint",
    "dependencies",
    "resource_links",
    "next_gap",
)

NOT_THIS = {
    "features.html": "FEATURES board lane. Landed-feature posts. Not the tracker.",
    "feature-requests.html": "request door. Not shipped-state.",
    "current-work.html": "unfinished-now ledger. Not shipped-state.",
    "todo.html": "DIRECTIVES.md view. Historical.",
    "builds.html": "permit SOP.",
    "ledger.html": "resource census.",
    "right-now.html": "buyer / revenue desk.",
}


def _read(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


def _load_json_file(path, fallback=None):
    try:
        text = fallback if fallback is not None and not os.path.lexists(path) else _read(path)
    except UnicodeDecodeError as exc:
        return None, ["not UTF-8: %s" % exc]
    if not text.strip():
        return None, ["unreadable or empty"]
    try:
        data = json.loads(text)
    except ValueError as exc:
        return None, ["not JSON: %s" % exc]
    if not isinstance(data, dict):
        return None, ["not an object"]
    return data, []


def _sorted_json(data):
    return json.dumps(data, sort_keys=True, indent=2) + "\n"


def _list_json(root, rel):
    folder = os.path.join(root, rel)
    if not os.path.isdir(folder):
        return []
    names = [n for n in os.listdir(folder) if n.endswith(".json") and not n.startswith(".")]
    names.sort()
    return names


def _committed_catalog(root):
    """Load committed catalog records omitted from this working tree."""
    if not os.path.lexists(os.path.join(root, ".git")):
        return {}
    env = dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_NO_REPLACE_OBJECTS="1")
    for key in (
        "GIT_DIR", "GIT_COMMON_DIR", "GIT_WORK_TREE", "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE", "GIT_INDEX_FILE",
        "GIT_SHALLOW_FILE", "GIT_QUARANTINE_PATH", "GIT_GRAFT_FILE",
        "GIT_LITERAL_PATHSPECS", "GIT_GLOB_PATHSPECS", "GIT_NOGLOB_PATHSPECS",
        "GIT_ICASE_PATHSPECS",
    ):
        env.pop(key, None)

    def git(*args, input=None, check=True):
        return subprocess.run(
            ["git", "--literal-pathspecs", "-C", os.fspath(root), *args],
            input=input, capture_output=True, check=check, timeout=30, env=env,
        )

    head = git("rev-parse", "--verify", "HEAD^{commit}", check=False)
    if head.returncode:
        # An ordinary new repository has local drafts but no committed catalog.
        branch = git("symbolic-ref", "--quiet", "HEAD", check=False)
        if branch.returncode == 0 and git(
            "show-ref", "--verify", "--quiet", branch.stdout.decode().strip(), check=False
        ).returncode == 1:
            return {}
        raise ValueError("cannot resolve the committed catalog: " + head.stderr.decode("utf-8", "replace").strip())
    revision = head.stdout.decode("ascii").strip()
    folders = {REGISTRY_DIR.replace(os.sep, "/"), EVIDENCE_DIR.replace(os.sep, "/")}
    objects = {}
    tree = git("ls-tree", "-r", "-z", "--full-tree", revision, "--", *sorted(folders)).stdout
    for entry in tree.split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        path = os.fsdecode(raw_path)
        folder, name = path.rsplit("/", 1)
        if folder not in folders or name.startswith(".") or not name.endswith(".json"):
            continue
        if not os.path.lexists(os.path.join(root, path)):
            objects[path] = metadata.split()[2]
    if not objects:
        return {}
    # One batch avoids a subprocess for every omitted registry/evidence file.
    payload = git("cat-file", "--batch", input=b"".join(oid + b"\n" for oid in objects.values())).stdout
    sources = {}
    offset = 0
    for path, oid in objects.items():
        line_end = payload.find(b"\n", offset)
        header = payload[offset:line_end].split() if line_end >= 0 else []
        if len(header) != 3 or header[:2] != [oid, b"blob"]:
            raise ValueError("committed catalog blob is unavailable: " + path)
        start, size = line_end + 1, int(header[2])
        end = start + size
        if size < 0 or payload[end:end + 1] != b"\n":
            raise ValueError("committed catalog blob is incomplete: " + path)
        sources[path] = payload[start:end].decode("utf-8")
        offset = end + 1
    return sources


def path_exists(root, rel):
    if not isinstance(rel, str) or not rel or rel.startswith("/") or ".." in rel.split("/"):
        return False
    return os.path.isfile(os.path.join(root, rel)) or os.path.isdir(os.path.join(root, rel))


def git_names(root):
    """Path names on HEAD/origin/main even when the worktree is sparse."""
    names = set()
    git_dir = os.path.join(root, ".git")
    if not (os.path.isdir(git_dir) or os.path.isfile(git_dir)):
        return names
    for ref in ("HEAD", "origin/main"):
        try:
            out = subprocess.check_output(
                ["git", "-C", root, "ls-tree", "-r", "-z", "--name-only", ref],
                stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.CalledProcessError):
            continue
        # NUL framing avoids Git quoting and preserves embedded line breaks.
        # Decode as filesystem paths, including non-UTF-8 bytes on POSIX.
        names.update(os.fsdecode(name) for name in out.split(b"\0") if name)
    return names


def exists_on_tree(root, rel, names=None):
    if not isinstance(rel, str) or not rel or rel.startswith("/") or ".." in rel.split("/"):
        return False
    if os.path.exists(os.path.join(root, rel)):
        return True
    if not names:
        return False
    if rel in names:
        return True
    prefix = rel.rstrip("/") + "/"
    return any(name.startswith(prefix) for name in names)


def tree_blob(root, rel):
    """Git blob of a path on the worktree or HEAD. Empty when unreadable."""
    if not isinstance(rel, str) or not rel or rel.startswith("/") or ".." in rel.split("/"):
        return ""
    path = os.path.join(root, rel)
    if os.path.islink(path):
        try:
            # Git stores the link target text, not the referent's contents.
            blob = subprocess.check_output(
                ["git", "-C", root, "hash-object", "--stdin"],
                input=os.readlink(os.fsencode(path)),
                stderr=subprocess.DEVNULL,
            ).decode("ascii").strip()
            if BLOB_RE.match(blob):
                return blob
        except (OSError, subprocess.CalledProcessError):
            pass
    elif os.path.isfile(path):
        try:
            blob = subprocess.check_output(
                ["git", "hash-object", path],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
            if BLOB_RE.match(blob):
                return blob
        except (OSError, subprocess.CalledProcessError):
            pass
    git_dir = os.path.join(root, ".git")
    if os.path.isdir(git_dir) or os.path.isfile(git_dir):
        try:
            blob = subprocess.check_output(
                ["git", "-C", root, "rev-parse", "HEAD:" + rel],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
            if BLOB_RE.match(blob):
                return blob
        except (OSError, subprocess.CalledProcessError):
            pass
    return ""


def validate_feature(rec, filename=""):
    problems = []
    if not isinstance(rec, dict):
        return ["feature is not an object"]
    if rec.get("schema") != SCHEMA_FEATURE:
        problems.append("schema must be %s" % SCHEMA_FEATURE)
    for field in FEATURE_REQUIRED:
        if field not in rec:
            problems.append("missing field: %s" % field)
    # Keep identifier types intact: evidence matching uses exact string IDs.
    feat_id = rec.get("id")
    if not isinstance(feat_id, str) or not ID_RE.fullmatch(feat_id):
        problems.append("id must match %s" % ID_RE.pattern)
    elif filename and filename != feat_id + ".json":
        problems.append("filename must equal id.json")
    if len(str(rec.get("name") or "")) < 4:
        problems.append("name too short")
    if len(str(rec.get("capability") or "")) < 8:
        problems.append("capability too short")
    if len(str(rec.get("owner_subsystem") or "")) < 2:
        problems.append("owner_subsystem too short")
    if len(str(rec.get("carrier") or "")) < 2:
        problems.append("carrier too short")
    if len(str(rec.get("next_gap") or "")) < 8:
        problems.append("next_gap too short")
    for key in ("claimed_paths", "test_paths", "dependencies", "resource_links"):
        val = rec.get(key)
        if val is None:
            continue
        if not isinstance(val, list) or any(not isinstance(p, str) or not p for p in val):
            problems.append("%s must be a list of nonempty strings" % key)
    entry = rec.get("public_entrypoint")
    if entry is not None and not isinstance(entry, str):
        problems.append("public_entrypoint must be a string")
    related = rec.get("related")
    if related is not None and not isinstance(related, dict):
        problems.append("related must be an object")
    return problems


def validate_evidence(rec, filename=""):
    problems = []
    if not isinstance(rec, dict):
        return ["evidence is not an object"]
    if rec.get("schema") != SCHEMA_EVIDENCE:
        problems.append("schema must be %s" % SCHEMA_EVIDENCE)
    evid_id = rec.get("id")
    if not isinstance(evid_id, str) or not ID_RE.fullmatch(evid_id):
        problems.append("id must match %s" % ID_RE.pattern)
    elif filename and filename != evid_id + ".json":
        problems.append("filename must equal id.json")
    feat_id = rec.get("feature_id")
    if not isinstance(feat_id, str) or not ID_RE.fullmatch(feat_id):
        problems.append("feature_id must match %s" % ID_RE.pattern)
    kind = rec.get("kind")
    if kind not in EVIDENCE_KINDS:
        problems.append("kind not in enum")
    if rec.get("sha") and not SHA_RE.match(str(rec.get("sha") or "")):
        problems.append("sha must be 40 hex or omitted")
    if rec.get("blob") and not BLOB_RE.match(str(rec.get("blob") or "")):
        problems.append("blob must be 40-64 hex or omitted")
    if kind == "LIVE_MEASUREMENT":
        if not rec.get("url"):
            problems.append("LIVE_MEASUREMENT needs url")
        if not SHA_RE.match(str(rec.get("sha") or "")):
            problems.append("LIVE_MEASUREMENT needs 40-hex sha")
    if kind == "SUPERSEDE":
        target = rec.get("superseded_by") or rec.get("replaces")
        if not isinstance(target, str) or not ID_RE.fullmatch(target):
            problems.append("SUPERSEDE needs superseded_by id")
    for key in ("paths",):
        val = rec.get(key)
        if val is None:
            continue
        if not isinstance(val, list) or any(not isinstance(p, str) or not p for p in val):
            problems.append("%s must be a list of nonempty strings" % key)
    return problems


def load_registry(root):
    features = []
    seen = {}
    conflicts = []
    invalid = []
    try:
        committed = _committed_catalog(root)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        detail = getattr(exc, "stderr", None) or str(exc)
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", "replace")
        invalid.append({"_file": "committed catalog", "_kind": "source", "_invalid": [detail.strip()]})
        committed = {}

    def names(rel):
        prefix = rel.replace(os.sep, "/") + "/"
        return sorted(set(_list_json(root, rel)) | {
            path[len(prefix):] for path in committed if path.startswith(prefix)
        })

    for name in names(REGISTRY_DIR):
        path = os.path.join(root, REGISTRY_DIR, name)
        rec, errs = _load_json_file(path, committed.get(REGISTRY_DIR.replace(os.sep, "/") + "/" + name))
        if rec is None:
            invalid.append({"_file": name, "_invalid": errs})
            continue
        rec = dict(rec)
        rec["_file"] = name
        probs = validate_feature(rec, name)
        feat_id = str(rec.get("id") or "")
        blob = json.dumps({k: rec[k] for k in rec if not str(k).startswith("_")}, sort_keys=True, separators=(",", ":"))
        if feat_id in seen:
            if seen[feat_id] != blob:
                conflicts.append("CONFLICT same id different bytes: %s" % feat_id)
                rec["_invalid"] = (rec.get("_invalid") or []) + ["CONFLICT same id different bytes"]
            else:
                rec["_invalid"] = (rec.get("_invalid") or []) + ["duplicate identical id ignored"]
        else:
            seen[feat_id] = blob
        if probs:
            rec["_invalid"] = (rec.get("_invalid") or []) + probs
        if rec.get("_invalid"):
            invalid.append(rec)
        features.append(rec)
    evidence = []
    evid_seen = {}
    for name in names(EVIDENCE_DIR):
        path = os.path.join(root, EVIDENCE_DIR, name)
        rec, errs = _load_json_file(path, committed.get(EVIDENCE_DIR.replace(os.sep, "/") + "/" + name))
        if rec is None:
            invalid.append({"_file": name, "_invalid": errs, "_kind": "evidence"})
            continue
        rec = dict(rec)
        rec["_file"] = name
        probs = validate_evidence(rec, name)
        evid_id = str(rec.get("id") or "")
        blob = json.dumps({k: rec[k] for k in rec if not str(k).startswith("_")}, sort_keys=True, separators=(",", ":"))
        if evid_id in evid_seen:
            if evid_seen[evid_id] != blob:
                conflicts.append("CONFLICT same evidence id different bytes: %s" % evid_id)
                rec["_invalid"] = (rec.get("_invalid") or []) + ["CONFLICT same id different bytes"]
            else:
                rec["_invalid"] = (rec.get("_invalid") or []) + ["duplicate identical id ignored"]
        else:
            evid_seen[evid_id] = blob
        if probs:
            rec["_invalid"] = (rec.get("_invalid") or []) + probs
        evidence.append(rec)
        if rec.get("_invalid"):
            invalid.append(rec)
    return features, evidence, conflicts, invalid


def _valid_features(features):
    out = []
    seen = set()
    for rec in features:
        if rec.get("_invalid"):
            continue
        feat_id = rec.get("id")
        if feat_id in seen:
            continue
        seen.add(feat_id)
        out.append(rec)
    out.sort(key=lambda r: str(r.get("id") or ""))
    return out


def _evidence_for(feature_id, evidence):
    rows = []
    for rec in evidence:
        if rec.get("_invalid"):
            continue
        if rec.get("feature_id") == feature_id:
            rows.append(rec)
    rows.sort(key=lambda r: (str(r.get("recorded_at") or ""), str(r.get("id") or "")))
    return rows


def _chat_noise(snapshot):
    snapshot = snapshot or {}
    return bool(
        snapshot.get("chat_text")
        or snapshot.get("chat_said_done")
        or snapshot.get("assistant_message")
        or snapshot.get("slack_text")
        or snapshot.get("ntfy_200")
        or snapshot.get("open_prs")
        or snapshot.get("claimed_status")
    )


def derive_feature(feature, evidence, root, snapshot=None):
    snapshot = snapshot or {}
    feat_id = str(feature.get("id") or "")
    claimed = [p for p in (feature.get("claimed_paths") or []) if isinstance(p, str) and p]
    tests = [p for p in (feature.get("test_paths") or []) if isinstance(p, str) and p]
    names = snapshot.get("git_names")
    if names is None:
        names = git_names(root)
    tree = snapshot.get("tree_paths")
    if not isinstance(tree, dict):
        tree = {}
        for path in claimed + tests + [feature.get("public_entrypoint") or ""]:
            if path:
                tree[path] = exists_on_tree(root, path, names)

    ev = _evidence_for(feat_id, evidence)
    superseded_by = str(feature.get("superseded_by") or "")
    for row in ev:
        if row.get("kind") == "SUPERSEDE":
            superseded_by = str(row.get("superseded_by") or row.get("replaces") or superseded_by)

    if claimed:
        present = [p for p in claimed if tree.get(p)]
        missing = [p for p in claimed if not tree.get(p)]
        if missing and present:
            source = "DEGRADED"
        elif missing:
            source = "DEGRADED"
        else:
            source = "SOURCE_BUILT"
    else:
        source = "PLANNED"
        present = []
        missing = []

    if tests:
        test_missing = [p for p in tests if not tree.get(p)]
        test_status = "TESTS_PRESENT" if not test_missing else "DEGRADED"
    else:
        test_missing = []
        test_status = "UNTESTED"

    live_ok = []
    live_stale = []
    entry = str(feature.get("public_entrypoint") or "")
    for row in ev:
        if row.get("kind") != "LIVE_MEASUREMENT":
            continue
        if not (SHA_RE.match(str(row.get("sha") or "")) and row.get("url")):
            continue
        cited = str(row.get("blob") or "")
        path = str(row.get("path") or entry or "")
        if cited and path:
            current = tree_blob(root, path)
            # Missing/unreadable pinned bytes cannot corroborate a live receipt.
            if current != cited:
                live_stale.append(row)
                continue
        live_ok.append(row)
    if live_ok and source == "SOURCE_BUILT":
        live = "LIVE"
    elif live_stale and not live_ok:
        live = "DEGRADED"
    elif live_ok:
        live = "DEGRADED"
    else:
        live = "UNMEASURED"

    shas = [str(row.get("sha")) for row in live_ok if SHA_RE.match(str(row.get("sha") or ""))]
    if not shas:
        shas = [str(row.get("sha")) for row in ev if SHA_RE.match(str(row.get("sha") or ""))]
    blobs = []
    for row in ev:
        if row.get("kind") == "BLOB" and row.get("blob"):
            blobs.append("%s:%s" % (row.get("path") or "", row.get("blob")))
        elif row.get("blob"):
            blobs.append(str(row.get("blob")))
    receipts = [str(row.get("receipt") or row.get("id")) for row in ev if row.get("kind") == "RECEIPT" or row.get("receipt")]

    last = str(feature.get("added") or "")
    for row in ev:
        ts = str(row.get("recorded_at") or "")
        if ts > last:
            last = ts

    if superseded_by:
        rollup = "SUPERSEDED"
    elif live == "DEGRADED" or source == "DEGRADED" or test_status == "DEGRADED":
        rollup = "DEGRADED"
    elif live == "LIVE":
        rollup = "LIVE"
    elif test_status == "TESTS_PRESENT" and source == "SOURCE_BUILT":
        rollup = "TESTS_PRESENT"
    elif source == "SOURCE_BUILT":
        rollup = "SOURCE_BUILT"
    else:
        rollup = "PLANNED"

    author_claim = feature.get("claimed_status")
    return {
        "id": feat_id,
        "name": feature.get("name"),
        "capability": feature.get("capability"),
        "owner_subsystem": feature.get("owner_subsystem"),
        "carrier": feature.get("carrier"),
        "rollup": rollup,
        "source_status": source,
        "test_status": test_status,
        "live_status": live,
        "claimed_paths": claimed,
        "claimed_paths_present": present,
        "claimed_paths_missing": missing,
        "test_paths": tests,
        "test_paths_missing": test_missing,
        "public_entrypoint": feature.get("public_entrypoint") or "",
        "dependencies": list(feature.get("dependencies") or []),
        "resource_links": list(feature.get("resource_links") or []),
        "related": feature.get("related") if isinstance(feature.get("related"), dict) else {},
        "next_gap": feature.get("next_gap"),
        "last_change": last,
        "main_sha": shas[-1] if shas else "",
        "blob_proof": blobs,
        "receipts": receipts,
        "evidence_ids": [str(row.get("id")) for row in ev],
        "superseded_by": superseded_by,
        "author_claim_ignored": author_claim if author_claim else "",
        "chat_ignored": _chat_noise(snapshot),
        "file": feature.get("_file"),
    }


def project(root, snapshot=None):
    snapshot = dict(snapshot or {})
    if "git_names" not in snapshot:
        snapshot["git_names"] = git_names(root)
    features, evidence, conflicts, invalid = load_registry(root)
    rows = [derive_feature(feat, evidence, root, snapshot) for feat in _valid_features(features)]
    order = {key: idx for idx, key in enumerate(ROLLUP_SORT)}
    rows.sort(key=lambda row: (order.get(row["rollup"], 99), str(row.get("id") or "")))
    counts = {key: 0 for key in ROLLUPS}
    for row in rows:
        counts[row["rollup"]] = counts.get(row["rollup"], 0) + 1
    problems = list(conflicts)
    for rec in invalid:
        for item in rec.get("_invalid") or []:
            problems.append("%s: %s" % (rec.get("_file") or rec.get("id") or "record", item))
    return {
        "schema": SCHEMA_PROJECTION,
        "law": (
            "Status is derived from exact Git/tree/receipt evidence. "
            "TESTS_PRESENT means test files exist; test execution is unmeasured by this projection. "
            "Source-built is not live. Chat, Slack, ntfy, open PRs, and "
            "claimed_status never promote a feature. HTTP/Pages is a bake."
        ),
        "not_this": NOT_THIS,
        "counts": counts,
        "n_features": len(rows),
        "n_invalid": len(invalid),
        "problems": problems,
        "source_errors": [item for rec in invalid if rec.get("_kind") == "source"
                          for item in rec.get("_invalid") or []],
        "features": rows,
        "add_feature": {
            "id_pattern": ID_RE.pattern,
            "registry": "features/registry/{id}.json",
            "evidence": "features/evidence/{id}.json",
            "same_id_same_bytes": "idempotent",
            "same_id_different_bytes": "CONFLICT — never overwrite; add evidence or a new id",
            "generate": "python3 host/feature_tracker.py --write",
            "proof": "python3 test_feature_tracker.py",
        },
    }


def render_html(projection):
    css_tag = hub_pages.CSS_TAG if hub_pages is not None else '<link rel="stylesheet" href="./commons.css?v=20260823f">'
    viewport = hub_pages.VIEWPORT if hub_pages is not None else '<meta name="viewport" content="width=device-width, initial-scale=1">'
    counts = projection.get("counts") or {}
    count_bits = " · ".join("%s %s" % (counts.get(k, 0), k) for k in ROLLUPS)
    subsystems = sorted({str(r.get("owner_subsystem") or "") for r in projection.get("features") or [] if r.get("owner_subsystem")})
    carriers = sorted({str(r.get("carrier") or "") for r in projection.get("features") or [] if r.get("carrier")})
    sub_opts = "\n".join('<option value="%s">%s</option>' % (html.escape(s, quote=True), html.escape(s)) for s in subsystems)
    car_opts = "\n".join('<option value="%s">%s</option>' % (html.escape(s, quote=True), html.escape(s)) for s in carriers)
    st_opts = "\n".join('<option value="%s">%s</option>' % (s, s) for s in ROLLUPS)
    src_opts = "\n".join('<option value="%s">%s</option>' % (s, s) for s in SOURCE_STATUSES)
    live_opts = "\n".join('<option value="%s">%s</option>' % (s, s) for s in LIVE_STATUSES)

    def cell(label, value, extra=""):
        return "<td data-label=\"%s\"%s>%s</td>" % (html.escape(label, quote=True), extra, value)

    rows_html = []
    for row in projection.get("features") or []:
        hay = " ".join(
            str(row.get(k) or "")
            for k in ("id", "name", "capability", "owner_subsystem", "carrier", "rollup", "next_gap", "public_entrypoint")
        ).lower()
        sha = html.escape(str(row.get("main_sha") or "—"))
        blobs = html.escape(", ".join(row.get("blob_proof") or []) or "—")
        tests = html.escape(str(row.get("test_status") or ""))
        entry = str(row.get("public_entrypoint") or "")
        if entry:
            entry_html = '<a href="./%s">%s</a>' % (html.escape(entry, quote=True), html.escape(entry))
        else:
            entry_html = "—"
        deps = html.escape(", ".join(row.get("dependencies") or []) or "—")
        resources = []
        for link in row.get("resource_links") or []:
            resources.append('<a href="./%s">%s</a>' % (html.escape(link, quote=True), html.escape(link)))
        res_html = ", ".join(resources) or "—"
        related = row.get("related") or {}
        rel_bits = []
        if related.get("current_work"):
            rel_bits.append('<a href="./current-work.html">current-work</a>')
        if related.get("resources"):
            rel_bits.append('<a href="./resources.html">resources</a>')
        if related.get("profitability"):
            rel_bits.append('<a href="./ground/PROFITABILITY_BUILD_MAP.md">profitability</a>')
        if related.get("boards"):
            rel_bits.append('<a href="./boards.html">boards</a>')
        if rel_bits:
            res_html = res_html + " · " + " ".join(rel_bits)
        proof = "sha %s<br>blob %s" % (sha, blobs)
        if row.get("receipts"):
            recs = []
            for rec in row.get("receipts"):
                recs.append('<a href="./p/%s.md">%s</a>' % (html.escape(str(rec), quote=True), html.escape(str(rec))))
            proof += "<br>" + ", ".join(recs)
        claim = row.get("author_claim_ignored")
        claim_note = ""
        if claim:
            claim_note = '<div class="note">author claim ignored: %s</div>' % html.escape(str(claim))
        rows_html.append(
            '<tr data-status="%s" data-source="%s" data-live="%s" data-sub="%s" data-carrier="%s" data-hay="%s">'
            "%s%s%s%s%s%s%s%s%s%s%s%s%s</tr>"
            % (
                html.escape(str(row.get("rollup") or ""), quote=True),
                html.escape(str(row.get("source_status") or ""), quote=True),
                html.escape(str(row.get("live_status") or ""), quote=True),
                html.escape(str(row.get("owner_subsystem") or ""), quote=True),
                html.escape(str(row.get("carrier") or ""), quote=True),
                html.escape(hay, quote=True),
                cell("feature", "<b>%s</b><div class=\"note\">%s</div>%s" % (html.escape(str(row.get("name") or "")), html.escape(str(row.get("id") or "")), claim_note)),
                cell("capability", html.escape(str(row.get("capability") or ""))),
                cell("owner / carrier", "%s / %s" % (html.escape(str(row.get("owner_subsystem") or "")), html.escape(str(row.get("carrier") or "")))),
                cell("status", '<span class="s-%s">%s</span>' % (html.escape(str(row.get("rollup") or "").lower(), quote=True), html.escape(str(row.get("rollup") or "")))),
                cell("source", html.escape(str(row.get("source_status") or ""))),
                cell("tests", tests),
                cell("live", html.escape(str(row.get("live_status") or ""))),
                cell("SHA / blob / proof", proof),
                cell("entrypoint", entry_html),
                cell("deps", deps),
                cell("resources", res_html),
                cell("last change", html.escape(str(row.get("last_change") or "—"))),
                cell("next gap", html.escape(str(row.get("next_gap") or ""))),
            )
        )

    body_rows = "\n".join(rows_html) if rows_html else '<tr><td colspan="13">no valid feature records</td></tr>'
    problems = projection.get("problems") or []
    problem_html = ""
    if problems:
        problem_html = '<p class="law">Projection problems (shape only, records kept): %s</p>' % html.escape("; ".join(problems))

    return """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
%s
<meta name="robots" content="index,follow">
<meta http-equiv="Cache-Control" content="no-store">
<title>Commons feature tracker</title>
%s
<style>
.s-planned{color:#6b6b6b}
.s-source_built{color:#2f6f9f}
.s-tests_present{color:#2b7a4b}
.s-live{color:#1b6b3a;font-weight:700}
.s-degraded{color:#a45b12}
.s-superseded{color:#6b6b6b;text-decoration:line-through}
#ft-controls{display:flex;flex-wrap:wrap;gap:.5rem;margin:1rem 0;align-items:end}
#ft-controls label{display:flex;flex-direction:column;font-size:.85em;gap:.2rem}
#ft-controls input,#ft-controls select{min-height:2.5rem;min-width:8rem}
#ft-table{width:100%%;border-collapse:collapse}
#ft-table th,#ft-table td{text-align:left;vertical-align:top;padding:.4rem .45rem;border-bottom:1px solid #ccc}
#ft-table th{font-size:.8em;text-transform:uppercase;letter-spacing:.03em}
#ft-table tr[hidden]{display:none}
@media (max-width:720px){
  #ft-table, #ft-table thead, #ft-table tbody, #ft-table th, #ft-table td, #ft-table tr{display:block}
  #ft-table thead{position:absolute;left:-9999px}
  #ft-table tr{border:1px solid #ccc;margin:0 0 .8rem;padding:.5rem}
  #ft-table td{border:0;padding:.15rem 0}
  #ft-table td:before{content:attr(data-label);display:block;font-size:.75em;font-weight:700;letter-spacing:.03em;text-transform:uppercase;opacity:.7}
}
</style>
</head><body>
<section id="trust-through-proof" class="law trust-law" aria-label="Trust after proof"><strong>TRUST AFTER PROOF.</strong> <a href="./trust.html">On Trust.</a> Proof is cached. Source-built is not live. Chat is not evidence.</section>
<p class="nav"><a href="./index.html">Commons</a> · <a href="./current-work.html">current work</a> · <a href="./resources.html">resources</a> · <a href="./boards.html">boards</a> · <a href="./ground/PROFITABILITY_BUILD_MAP.md">profitability</a> · <a href="./commercial.html">commercial</a> · <a href="./features.html">FEATURES lane</a> · <a href="./todo.html">todo</a> · <a href="./builds.html">builds</a> · <a href="./ledger.html">resource ledger</a> · <a href="./feature-tracker.json">machine JSON</a></p>
<section id="live-cash" class="law" aria-label="Live cash"><strong>Live cash — verified product pages only.</strong> No invented Stripe links. <a href="./dealer-service-lead-rescue.html">$199 dealer diagnostic</a>.<p class="note"><strong>Larger fixed engagements</strong> (separate product pages; checkout/intent stays there): <a href="./diagnostic.html">GGUF diagnostic · $12,000 / 10 days</a> · <a href="./commercial.html">White Box pilot · $30,000 / 30 days</a>. Not remints of tip SKUs.</p></section>
<h1>Feature tracker</h1>
<p class="law">Derived from exact Git/tree/receipt evidence. Never from prose. <a href="./features.html">features.html</a> is the FEATURES board lane — do not remint it. This page is the shipped-state tracker. Law: <a href="./ground/FEATURE_TRACKER.md">ground/FEATURE_TRACKER.md</a>. Instrument: <code>python3 host/feature_tracker.py --write</code>. Proof: <code>python3 test_feature_tracker.py</code>.</p>
<p>Two columns of truth: <b>source</b> (paths on the tree / cited SHA) and <b>live</b> (only a LIVE_MEASUREMENT evidence row with a 40-character SHA and URL). Pages, pulse, ntfy 200, Slack, chat, and <code>claimed_status</code> do not promote LIVE. HTTP is not the computer.</p>
<p class="note"><b>TESTS_PRESENT</b> means the listed test files exist. This projection does not execute tests or import their results; test execution is unmeasured here.</p>
<p class="note">%s · %s valid · %s invalid</p>
%s
<div id="ft-controls">
<label>search <input id="ft-q" type="search" placeholder="name, id, capability"></label>
<label>status <select id="ft-st"><option value="">all</option>%s</select></label>
<label>source <select id="ft-src"><option value="">all</option>%s</select></label>
<label>live <select id="ft-lv"><option value="">all</option>%s</select></label>
<label>subsystem <select id="ft-sub"><option value="">all</option>%s</select></label>
<label>carrier <select id="ft-car"><option value="">all</option>%s</select></label>
</div>
<p id="ft-empty" class="note" hidden>no rows match</p>
<table id="ft-table">
<thead><tr><th>feature</th><th>capability</th><th>owner / carrier</th><th>status</th><th>source</th><th>tests</th><th>live</th><th>SHA / blob / proof</th><th>entrypoint</th><th>deps</th><th>resources</th><th>last change</th><th>next gap</th></tr></thead>
<tbody>
%s
</tbody>
</table>
<h2>Add a shipped feature</h2>
<p>Every carrier adds its own. Mint a unique id matching <code>^[A-Za-z0-9._-]{8,80}$</code>. Write a new file <code>features/registry/{id}.json</code>. Do not overwrite. Same id + same bytes is idempotent; same id + different bytes is CONFLICT — add <code>features/evidence/{id}.json</code> instead. Run <code>python3 host/feature_tracker.py --write</code> and <code>python3 test_feature_tracker.py</code>. Unique branch, merge, not force. No auth, no secrets, no generated-history rewrite.</p>
<p class="note">LIVE requires a LIVE_MEASUREMENT evidence record with url + 40-hex sha. Listing a public HTML path only proves a source door.</p>
<script>
(function(){
  var q = document.getElementById('ft-q');
  var st = document.getElementById('ft-st');
  var src = document.getElementById('ft-src');
  var lv = document.getElementById('ft-lv');
  var sub = document.getElementById('ft-sub');
  var car = document.getElementById('ft-car');
  var empty = document.getElementById('ft-empty');
  function apply(){
    var query = (q && q.value || '').toLowerCase();
    var status = st && st.value || '';
    var source = src && src.value || '';
    var live = lv && lv.value || '';
    var subsystem = sub && sub.value || '';
    var carrier = car && car.value || '';
    var rows = document.querySelectorAll('#ft-table tbody tr');
    var shown = 0;
    for (var i = 0; i < rows.length; i++){
      var tr = rows[i];
      var hay = tr.getAttribute('data-hay') || '';
      var ok = (!query || hay.indexOf(query) !== -1)
        && (!status || tr.getAttribute('data-status') === status)
        && (!source || tr.getAttribute('data-source') === source)
        && (!live || tr.getAttribute('data-live') === live)
        && (!subsystem || tr.getAttribute('data-sub') === subsystem)
        && (!carrier || tr.getAttribute('data-carrier') === carrier);
      tr.hidden = !ok;
      if (ok) shown++;
    }
    if (empty) empty.hidden = shown !== 0;
  }
  [q, st, src, lv, sub, car].forEach(function(el){ if (el) el.addEventListener('input', apply); });
})();
</script>
</body></html>
""" % (
        viewport,
        css_tag,
        html.escape(count_bits),
        projection.get("n_features", 0),
        projection.get("n_invalid", 0),
        problem_html,
        st_opts,
        src_opts,
        live_opts,
        sub_opts,
        car_opts,
        body_rows,
    )


def write_projection(root, projection):
    if projection.get("source_errors"):
        raise ValueError("cannot publish an incomplete source catalog: " + "; ".join(projection["source_errors"]))
    json_path = os.path.join(root, JSON_OUT)
    html_path = os.path.join(root, HTML_OUT)
    # KEEP tip live_cash across feature-tracker remints (newbot-05 doors;
    # --write rebuilds wipe Autopsy/$199 + Larger fixed otherwise).
    projection = _preserve_live_cash(_load_prev_tip_json(root, JSON_OUT), projection, root)
    with open(json_path, "w", encoding="utf-8") as handle:
        handle.write(_sorted_json(projection))
    with open(html_path, "w", encoding="utf-8") as handle:
        handle.write(render_html(projection))
    return json_path, html_path


def self_test():
    import tempfile
    import shutil

    tmp = tempfile.mkdtemp(prefix="commons-ft-")
    try:
        os.makedirs(os.path.join(tmp, REGISTRY_DIR))
        os.makedirs(os.path.join(tmp, EVIDENCE_DIR))
        os.makedirs(os.path.join(tmp, "host"))
        with open(os.path.join(tmp, "host", "ok.py"), "w", encoding="utf-8") as handle:
            handle.write("# ok\n")
        with open(os.path.join(tmp, "door.html"), "w", encoding="utf-8") as handle:
            handle.write("<!doctype html><title>door</title>\n")
        with open(os.path.join(tmp, "test_ok.py"), "w", encoding="utf-8") as handle:
            handle.write("print('ok')\n")
        planned = {
            "schema": SCHEMA_FEATURE,
            "id": "planned-feature-20260828-01",
            "name": "Only planned",
            "capability": "A design with no source paths yet.",
            "owner_subsystem": "future",
            "carrier": "GROK",
            "claimed_paths": [],
            "test_paths": [],
            "public_entrypoint": "",
            "dependencies": [],
            "resource_links": [],
            "next_gap": "Add claimed_paths after the first land.",
        }
        built = {
            "schema": SCHEMA_FEATURE,
            "id": "built-feature-20260828-01",
            "name": "Source built door",
            "capability": "A public door with tests on the tree.",
            "owner_subsystem": "doors",
            "carrier": "GROK",
            "claimed_paths": ["host/ok.py", "door.html"],
            "test_paths": ["test_ok.py"],
            "public_entrypoint": "door.html",
            "dependencies": [],
            "resource_links": ["door.html"],
            "related": {"boards": True},
            "next_gap": "Measure live Pages against a 40-character SHA.",
            "claimed_status": "LIVE",
        }
        missing = {
            "schema": SCHEMA_FEATURE,
            "id": "missing-feature-20260828-01",
            "name": "Claimed missing",
            "capability": "Claims a path that is not on the tree.",
            "owner_subsystem": "doors",
            "carrier": "GROK",
            "claimed_paths": ["no-such-file.py"],
            "test_paths": [],
            "public_entrypoint": "",
            "dependencies": [],
            "resource_links": [],
            "next_gap": "Land the claimed path or drop the claim.",
        }
        for rec in (planned, built, missing):
            with open(os.path.join(tmp, REGISTRY_DIR, rec["id"] + ".json"), "w", encoding="utf-8") as handle:
                handle.write(_sorted_json(rec))
        proj = project(tmp, {"chat_said_done": True, "ntfy_200": True, "slack_text": "LIVE", "open_prs": [1]})
        by_id = {row["id"]: row for row in proj["features"]}
        assert by_id["planned-feature-20260828-01"]["rollup"] == "PLANNED"
        assert by_id["built-feature-20260828-01"]["source_status"] == "SOURCE_BUILT"
        assert by_id["built-feature-20260828-01"]["test_status"] == "TESTS_PRESENT"
        assert by_id["built-feature-20260828-01"]["live_status"] == "UNMEASURED"
        assert by_id["built-feature-20260828-01"]["rollup"] == "TESTS_PRESENT"
        assert by_id["built-feature-20260828-01"]["author_claim_ignored"] == "LIVE"
        assert by_id["built-feature-20260828-01"]["chat_ignored"] is True
        assert by_id["missing-feature-20260828-01"]["source_status"] == "DEGRADED"
        live_ev = {
            "schema": SCHEMA_EVIDENCE,
            "id": "ev-built-live-20260828-01",
            "feature_id": "built-feature-20260828-01",
            "kind": "LIVE_MEASUREMENT",
            "sha": "a" * 40,
            "url": "https://example.invalid/door.html",
            "recorded_at": "2026-08-28T16:00:00Z",
        }
        with open(os.path.join(tmp, EVIDENCE_DIR, live_ev["id"] + ".json"), "w", encoding="utf-8") as handle:
            handle.write(_sorted_json(live_ev))
        live_proj = project(tmp)
        live_row = {row["id"]: row for row in live_proj["features"]}["built-feature-20260828-01"]
        assert live_row["live_status"] == "LIVE"
        assert live_row["rollup"] == "LIVE"
        assert live_row["main_sha"] == "a" * 40
        write_projection(tmp, live_proj)
        page = _read(os.path.join(tmp, HTML_OUT))
        assert "Feature tracker" in page
        assert "ft-q" in page
        assert "author claim ignored" in page
        assert "authentication" not in page.lower() or "no auth" in page.lower()
        machine = json.loads(_read(os.path.join(tmp, JSON_OUT)))
        again = project(tmp)
        assert _sorted_json(machine) == _sorted_json(again)
        print("self-test ok")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evidence-derived feature tracker")
    parser.add_argument("--root", default=".")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    out = project(args.root)
    if args.write and not out.get("source_errors"):
        write_projection(args.root, out)
        # Projection files may themselves be claimed_paths. Rebuild once so
        # SOURCE_BUILT includes the files this instrument just wrote.
        out = project(args.root)
        if not out.get("source_errors"):
            write_projection(args.root, out)
    json.dump(out, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 1 if out.get("problems") else 0


if __name__ == "__main__":
    raise SystemExit(main())
