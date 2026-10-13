#!/usr/bin/env python3
"""host/unbuilt_items.py — claimed_paths vs current main.

Surfaces named leftovers without reminting landed p/. Slack CLAIMED,
chat, ntfy 200, an open PR, and a Pages bake never close a row.
Four projector aliases stay OPEN_ALIAS.

  python3 host/unbuilt_items.py
  python3 host/unbuilt_items.py --root .
  python3 host/unbuilt_items.py --main-sha <40-hex>
  python3 host/unbuilt_items.py --write
  python3 host/unbuilt_items.py --self-test
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys


SCHEMA = "commons-unbuilt-items-v1"
DEFAULT_ROOT = "."
SEED_REL = os.path.join("ground", "UNBUILT_ITEMS.json")
JSON_OUT = "unbuilt-items.json"
CURRENT_WORK_REL = os.path.join("ground", "CURRENT_WORK.json")
FEATURE_REG_REL = os.path.join("features", "registry")
ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,80}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
KINDS = ("NAMED_LEFTOVER", "OPEN_ALIAS", "BUILDABLE", "OWNER_PLATFORM", "DEVICE_PINNED")
ALIAS_IDS = (
    "kimi-settled-facts-20260829-01",
    "kimi-session-memory-20260829-02",
    "kimi-agent-retirement-20260829-02",
    "bryce-land-subzero-walker-20260829-01",
)
CLAUDE_LEFTOVER_ID = "claude-derived-unbuilt-item-post-20260830"


def _preserve_live_cash(prev, doc, root=None):
    """Keep tip product doors across unbuilt-items remints.

    Paths only — never invent Stripe. Mirrors hub_pages KEEP (newbot-13/14).
    Retired products (deleted checkout page) are not resurrected.
    """
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


def _read(root, rel, snapshot=None):
    if snapshot and snapshot.get("main_paths_complete"):
        return snapshot["source_documents"].get(rel.replace(os.sep, "/"), "")
    path = os.path.join(root, rel)
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


def load_json(text):
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "not JSON"}
    if not isinstance(data, dict):
        return {"error": "not an object"}
    return data


def path_exists(root, rel, snapshot=None):
    if not isinstance(rel, str) or not rel or rel.startswith("/") or ".." in rel.split("/"):
        return False
    if snapshot and snapshot.get("main_paths_complete"):
        return bool(snapshot["main_paths"].get(rel.replace(os.sep, "/").rstrip("/")))
    target = os.path.join(root, rel)
    return os.path.isfile(target) or os.path.isdir(target)


def glob_receipts(root, pattern, snapshot=None):
    hits = []
    if snapshot and snapshot.get("main_paths_complete"):
        return sorted(
            path for path in snapshot["main_paths"]
            if path.startswith("p/") and "/" not in path[2:]
            and path.endswith(".md") and fnmatch.fnmatch(path, pattern)
        )
    folder = os.path.join(root, "p")
    if not os.path.isdir(folder):
        return hits
    needle = os.path.basename(str(pattern or ""))
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".md"):
            continue
        rel = os.path.join("p", name)
        if needle and fnmatch.fnmatch(rel, pattern):
            hits.append(rel)
    return hits


def validate_item(item, seen=None):
    problems = []
    if not isinstance(item, dict):
        return ["item is not an object"]
    job_id = str(item.get("id") or "")
    if not ID_RE.match(job_id):
        problems.append("id must match %s" % ID_RE.pattern)
    elif seen is not None:
        blob = json.dumps(item, sort_keys=True, separators=(",", ":"))
        prior = seen.get(job_id)
        if prior is None:
            seen[job_id] = blob
        elif prior != blob:
            problems.append("CONFLICT same id different bytes: %s" % job_id)
    if item.get("kind") not in KINDS:
        problems.append("kind not in enum")
    title = str(item.get("title") or "")
    if len(title) < 8:
        problems.append("title too short")
    paths = item.get("claimed_paths")
    if paths is None:
        paths = []
    if not isinstance(paths, list) or any(not isinstance(p, str) or not p for p in paths):
        problems.append("claimed_paths must be a list of nonempty strings")
    return problems


def validate_catalog(data):
    problems = []
    if not isinstance(data, dict):
        return ["catalog is not an object"]
    if data.get("schema") != SCHEMA:
        problems.append("schema must be %s" % SCHEMA)
    items = data.get("items")
    if not isinstance(items, list):
        problems.append("items must be a list")
        return problems
    seen = {}
    for item in items:
        problems.extend(validate_item(item, seen))
    have = {str(item.get("id") or "") for item in items if isinstance(item, dict)}
    if CLAUDE_LEFTOVER_ID not in have:
        problems.append("missing named leftover %s" % CLAUDE_LEFTOVER_ID)
    for ident in ALIAS_IDS:
        if ident not in have:
            problems.append("missing unclosed alias %s" % ident)
    return problems


def chatter(snapshot):
    snapshot = snapshot or {}
    return bool(
        snapshot.get("chat_text")
        or snapshot.get("chat_said_done")
        or snapshot.get("assistant_message")
        or snapshot.get("slack_text")
        or snapshot.get("slack_claimed")
        or snapshot.get("ntfy_200")
        or snapshot.get("open_prs")
        or snapshot.get("pages_bake")
    )


def reconcile_item(item, root, snapshot):
    snapshot = snapshot or {}
    item = item if isinstance(item, dict) else {}
    job_id = str(item.get("id") or "")
    kind = item.get("kind")
    claimed = [p for p in (item.get("claimed_paths") or []) if isinstance(p, str) and p]
    main_sha = str(snapshot.get("main_sha") or "")
    main_paths = snapshot.get("main_paths") if isinstance(snapshot.get("main_paths"), dict) else {}
    present = []
    missing = []
    for path in claimed:
        exists = bool(main_paths[path]) if path in main_paths else path_exists(root, path, snapshot)
        (present if exists else missing).append(path)
    receipt_hits = []
    pattern = str(item.get("receipt_glob") or "")
    if pattern:
        receipt_hits = glob_receipts(root, pattern, snapshot)
    result = {
        "id": job_id,
        "title": item.get("title"),
        "kind": kind,
        "from": item.get("from") or "",
        "claimed_paths": claimed,
        "present": present,
        "missing": missing,
        "receipt_hits": receipt_hits,
        "chat_ignored": chatter(snapshot),
        "main_sha": "",
        "stay_unclosed": bool(item.get("stay_unclosed")),
        "do_not_remint": bool(item.get("do_not_remint")),
        "status": "UNBUILT",
        "notes": item.get("notes") or "",
    }
    if kind == "DEVICE_PINNED" or item.get("stay_unclosed"):
        result["status"] = "OPEN_ALIAS" if item.get("stay_unclosed") else "PINNED"
        return result
    if kind == "OWNER_PLATFORM":
        result["status"] = "NEEDS_OWNER"
        return result
    if item.get("stay_unclosed_until_receipt"):
        if receipt_hits and SHA_RE.fullmatch(main_sha):
            result["status"] = "LANDED"
            result["main_sha"] = main_sha
        else:
            result["status"] = "UNBUILT"
        return result
    if SHA_RE.match(main_sha) and claimed and not missing:
        result["status"] = "LANDED"
        result["main_sha"] = main_sha
        return result
    result["status"] = "UNBUILT"
    return result


def harvest_claimed(root, rel, source, snapshot):
    snapshot = snapshot or {}
    rows = []
    if rel.endswith(".json") and path_exists(root, rel, snapshot):
        data = load_json(_read(root, rel, snapshot))
        items = data.get("items") if isinstance(data, dict) else []
        if not isinstance(items, list):
            items = []
        for item in items:
            if not isinstance(item, dict):
                continue
            claimed = [p for p in (item.get("claimed_paths") or []) if isinstance(p, str) and p]
            if not claimed:
                continue
            missing = [p for p in claimed if not path_exists(root, p, snapshot)]
            if not missing:
                continue
            rows.append(
                reconcile_item(
                    {
                        "id": str(item.get("id") or "harvested-item"),
                        "title": str(item.get("title") or item.get("name") or item.get("id") or "harvested"),
                        "kind": "BUILDABLE",
                        "from": item.get("from") or source,
                        "claimed_paths": claimed,
                        "notes": "harvested from %s; missing claimed_paths on this tree" % source,
                    },
                    root,
                    snapshot,
                )
            )
        return rows
    folder = os.path.join(root, rel)
    if snapshot.get("main_paths_complete"):
        prefix = rel.replace(os.sep, "/").rstrip("/") + "/"
        names = [path[len(prefix):] for path in snapshot["source_documents"]
                 if path.startswith(prefix) and "/" not in path[len(prefix):]]
    else:
        if not os.path.isdir(folder):
            return rows
        names = os.listdir(folder)
    for name in sorted(names):
        if not name.endswith(".json"):
            continue
        data = load_json(_read(root, os.path.join(rel, name), snapshot))
        if not isinstance(data, dict):
            continue
        claimed = [p for p in (data.get("claimed_paths") or []) if isinstance(p, str) and p]
        missing = [p for p in claimed if not path_exists(root, p, snapshot)]
        if not claimed or not missing:
            continue
        rows.append(
            reconcile_item(
                {
                    "id": str(data.get("id") or name[:-5]),
                    "title": str(data.get("name") or data.get("id") or name),
                    "kind": "BUILDABLE",
                    "from": data.get("carrier") or source,
                    "claimed_paths": claimed,
                    "notes": "harvested from %s; missing claimed_paths on this tree" % source,
                },
                root,
                snapshot,
            )
        )
    return rows


def project(catalog, root, snapshot):
    problems = validate_catalog(catalog)
    items = catalog.get("items") if isinstance(catalog, dict) else []
    if not isinstance(items, list):
        items = []
    live = [reconcile_item(item, root, snapshot) for item in items if isinstance(item, dict)]
    seen = {row["id"] for row in live}
    harvested = []
    for rel, source in (
        (CURRENT_WORK_REL, "current-work"),
        (FEATURE_REG_REL, "feature-registry"),
    ):
        for row in harvest_claimed(root, rel, source, snapshot):
            if row["id"] in seen:
                continue
            seen.add(row["id"])
            harvested.append(row)
    all_rows = live + harvested
    unbuilt = [row for row in all_rows if row.get("status") == "UNBUILT"]
    aliases = [row for row in all_rows if row.get("status") == "OPEN_ALIAS"]
    return {
        "schema": SCHEMA,
        "problems": problems,
        "main_sha": str((snapshot or {}).get("main_sha") or ""),
        "chat_ignored": chatter(snapshot),
        "items": all_rows,
        "unbuilt": unbuilt,
        "open_aliases": aliases,
        "alias_ids": list(ALIAS_IDS),
        "named_leftover": CLAUDE_LEFTOVER_ID,
        "do_not": [
            "remint landed p/",
            "close four projector aliases",
            "queue exhausted grok.com wake_jobs",
            "name fire_action",
            "spend the $5 tip",
            "add seats or gates",
        ],
    }


def _git_snapshot(root, main_sha):
    """Read definitions and path evidence from one existing Git commit."""
    git_env = dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_NO_REPLACE_OBJECTS="1")
    for key in (
        "GIT_DIR", "GIT_COMMON_DIR", "GIT_WORK_TREE", "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE", "GIT_INDEX_FILE",
        "GIT_SHALLOW_FILE", "GIT_QUARANTINE_PATH", "GIT_GRAFT_FILE",
        "GIT_LITERAL_PATHSPECS", "GIT_GLOB_PATHSPECS", "GIT_NOGLOB_PATHSPECS",
        "GIT_ICASE_PATHSPECS",
    ):
        git_env.pop(key, None)

    def git(*args, input=None):
        return subprocess.run(
            ["git", "--literal-pathspecs", "-C", os.fspath(root), *args],
            input=input, capture_output=True, check=True, timeout=30, env=git_env,
        ).stdout

    resolved = git("rev-parse", "--verify", main_sha + "^{commit}").decode().strip()
    if resolved != main_sha:
        raise ValueError("main SHA does not name a commit")
    objects = {}
    for entry in git("ls-tree", "-r", "-t", "-z", "--full-tree", main_sha).split(b"\0"):
        if entry:
            metadata, path = entry.split(b"\t", 1)
            objects[path.decode("utf-8", "surrogateescape")] = metadata.split()[2]
    paths = dict.fromkeys(objects, True)
    seed = SEED_REL.replace(os.sep, "/")
    current = CURRENT_WORK_REL.replace(os.sep, "/")
    prefix = FEATURE_REG_REL.replace(os.sep, "/") + "/"
    documents = [seed]
    if current in paths:
        documents.append(current)
    documents.extend(sorted(path for path in paths if path.startswith(prefix)
                            and "/" not in path[len(prefix):] and path.endswith(".json")))
    if seed not in objects:
        raise ValueError("source catalog is absent from the requested commit")
    # Read exact blobs together without checkout or archive attribute filters.
    payload = git("cat-file", "--batch", input=b"".join(objects[path] + b"\n" for path in documents))
    sources = {}
    offset = 0
    for path in documents:
        line_end = payload.find(b"\n", offset)
        header = payload[offset:line_end].split() if line_end >= 0 else []
        if len(header) != 3 or header[0] != objects[path] or header[1] != b"blob":
            raise ValueError("definition blob is unavailable at the requested commit: " + path)
        start, size = line_end + 1, int(header[2])
        end = start + size
        if payload[end:end + 1] != b"\n":
            raise ValueError("incomplete definition blob at the requested commit: " + path)
        sources[path] = payload[start:end].decode("utf-8")
        offset = end + 1
    return {"main_sha": main_sha, "main_paths": paths,
            "main_paths_complete": True, "source_documents": sources}


def measure_tree(root, main_sha=""):
    if main_sha and not SHA_RE.fullmatch(str(main_sha)):
        return {"error": "main SHA must be 40 lowercase hex characters", "items": [], "unbuilt": []}
    try:
        snapshot = (_git_snapshot(root, main_sha) if main_sha else
                    {"main_sha": "", "main_paths": {}})
        catalog = load_json(_read(root, SEED_REL, snapshot))
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", "replace")
        return {"error": "cannot read the requested catalog snapshot: " + detail.strip(),
                "items": [], "unbuilt": []}
    if catalog.get("error"):
        return {"error": catalog["error"], "items": [], "unbuilt": []}
    return project(catalog, root, snapshot)


def write_projection(root, main_sha=""):
    out = measure_tree(root, main_sha)
    # Keep the last usable task view when source loading or validation fails.
    # The caller still receives the error and reports a nonzero exit status.
    if out.get("error") or out.get("problems"):
        return out
    # KEEP tip live_cash across unbuilt-items remints (newbot-05 doors;
    # --write rebuilds wipe tip doors otherwise).
    out = _preserve_live_cash(_load_prev_tip_json(root, JSON_OUT), out, root)
    path = os.path.join(root, JSON_OUT)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(out, handle, indent=2)
        handle.write("\n")
    return out


def self_test():
    tmp_items = {
        "schema": SCHEMA,
        "items": [
            {
                "id": CLAUDE_LEFTOVER_ID,
                "title": "Claude-derived unbuilt-item post is not surfaced",
                "kind": "NAMED_LEFTOVER",
                "claimed_paths": [],
                "receipt_glob": "p/claude*unbuilt*.md",
                "stay_unclosed_until_receipt": True,
            },
            {
                "id": "kimi-settled-facts-20260829-01",
                "title": "kimi settled facts projector alias",
                "kind": "OPEN_ALIAS",
                "claimed_paths": ["p/kimi-settled-facts-20260829-01.md"],
                "stay_unclosed": True,
            },
            {
                "id": "kimi-session-memory-20260829-02",
                "title": "kimi session memory projector alias",
                "kind": "OPEN_ALIAS",
                "claimed_paths": ["p/kimi-session-memory-20260829-02.md"],
                "stay_unclosed": True,
            },
            {
                "id": "kimi-agent-retirement-20260829-02",
                "title": "kimi agent retirement projector alias",
                "kind": "OPEN_ALIAS",
                "claimed_paths": ["p/kimi-agent-retirement-20260829-02.md"],
                "stay_unclosed": True,
            },
            {
                "id": "bryce-land-subzero-walker-20260829-01",
                "title": "Bryce land subzero walker projector alias",
                "kind": "OPEN_ALIAS",
                "claimed_paths": ["p/bryce-land-subzero-walker-20260829-01.md"],
                "stay_unclosed": True,
            },
        ],
    }
    assert validate_catalog(tmp_items) == []
    sha = "a" * 40
    chatter_snap = {
        "main_sha": sha,
        "chat_said_done": True,
        "slack_claimed": True,
        "ntfy_200": True,
        "open_prs": [1],
        "main_paths": {"p/kimi-settled-facts-20260829-01.md": True},
    }
    alias = reconcile_item(tmp_items["items"][1], ".", chatter_snap)
    assert alias["status"] == "OPEN_ALIAS"
    assert alias["chat_ignored"] is True
    leftover = reconcile_item(tmp_items["items"][0], ".", chatter_snap)
    assert leftover["status"] == "UNBUILT"
    built = reconcile_item(
        {
            "id": "demo-built-item-20260830-01",
            "title": "demo built item",
            "kind": "BUILDABLE",
            "claimed_paths": ["ground/UNBUILT_ITEMS.md"],
        },
        ".",
        {"main_sha": sha, "main_paths": {"ground/UNBUILT_ITEMS.md": True}},
    )
    assert built["status"] == "LANDED"
    empty = reconcile_item(
        {
            "id": "demo-empty-paths-20260830-01",
            "title": "demo empty paths",
            "kind": "BUILDABLE",
            "claimed_paths": [],
        },
        ".",
        {"main_sha": sha},
    )
    assert empty["status"] == "UNBUILT"
    print("self-test ok")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Unbuilt items: claimed_paths vs current main")
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--main-sha", default="", help="official 40-character main SHA")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    out = write_projection(args.root, args.main_sha) if args.write else measure_tree(args.root, args.main_sha)
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 1 if out.get("error") or out.get("problems") else 0


if __name__ == "__main__":
    sys.exit(main())
