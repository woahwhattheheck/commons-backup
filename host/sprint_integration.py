#!/usr/bin/env python3
"""Exact Commons sprint-integration checker.

Merge is the default. Parallel branches are not collisions. CONFLICT is
classified only when competing work touches the same effective code AND
disagrees semantically.

Busy main, a stale base, and unrelated checks are recorded as facts. They
are never a verdict and never a stop.

Stdlib only. Durable policy: ground/SPRINT_INTEGRATION.json
"""
from __future__ import annotations

import hashlib
import json
import os
from difflib import SequenceMatcher

POLICY_PATH = "ground/SPRINT_INTEGRATION.json"
CHECKER_PATH = "host/sprint_integration.py"
LAW_PATH = "ground/SPRINT_INTEGRATION.md"

VERDICTS = (
    "CLEAR_TO_MERGE",
    "COMPOSE_AND_MERGE",
    "DEDUPED",
    "CONFLICT",
)
NOT_STOPPING = (
    "busy_main",
    "stale_base",
    "unrelated_checks",
    "parallel_branches",
)
RULE_IDS = (
    "SI-DISJOINT",
    "SI-IDENTICAL-BLOB",
    "SI-ADDITIVE-INSERT",
    "SI-JSON-KEY-UNION",
    "SI-SEMANTIC-DISAGREE",
)

_RANK = {
    "CLEAR_TO_MERGE": 0,
    "DEDUPED": 1,
    "COMPOSE_AND_MERGE": 2,
    "CONFLICT": 3,
}

_FIXTURE_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sprint_integration_fixtures")


def git_blob_sha(data):
    """Git blob SHA-1 (the hash GitHub file.sha uses)."""
    if data is None:
        return None
    if not isinstance(data, (bytes, bytearray)):
        data = str(data).encode("utf-8")
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def load_policy(root=None):
    path = os.path.join(root or _repo_root(), POLICY_PATH)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def changed_map(base, side):
    """Paths whose bytes differ from base, including adds and deletes."""
    out = {}
    for path in set(base) | set(side):
        b = base.get(path)
        s = side.get(path)
        if b != s:
            out[path] = s
    return out


def _is_text(data):
    if data is None:
        return True
    if b"\0" in data[:4096]:
        return False
    try:
        data.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def _parse_json(data):
    if data is None:
        return False, None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return False, None
    text = text.strip()
    if not text or text[0] not in "{[":
        return False, None
    try:
        return True, json.loads(text)
    except ValueError:
        return False, None


def _json_verdict(base_obj, left_obj, right_obj):
    """Compose JSON values. Returns (verdict, reason) or None if not JSON-shaped."""
    if left_obj == right_obj:
        return "DEDUPED", "identical JSON values"
    if type(left_obj) is not type(right_obj):
        return "CONFLICT", "JSON types disagree"
    if isinstance(left_obj, dict) and isinstance(right_obj, dict):
        base_d = base_obj if isinstance(base_obj, dict) else {}
        worst = "DEDUPED"
        for key in set(left_obj) | set(right_obj) | set(base_d):
            in_l = key in left_obj
            in_r = key in right_obj
            in_b = key in base_d
            if in_l and in_r:
                sub = _json_verdict(base_d.get(key), left_obj[key], right_obj[key])
                if sub is None:
                    if left_obj[key] == right_obj[key]:
                        continue
                    return "CONFLICT", "JSON key %r not composable" % (key,)
                v, reason = sub
                if _RANK[v] > _RANK[worst]:
                    worst = v
                if v == "CONFLICT":
                    return "CONFLICT", "JSON key %r: %s" % (key, reason)
            elif in_l and not in_r:
                if in_b and left_obj[key] != base_d[key]:
                    worst = "COMPOSE_AND_MERGE" if _RANK["COMPOSE_AND_MERGE"] > _RANK[worst] else worst
                else:
                    worst = "COMPOSE_AND_MERGE"
            elif in_r and not in_l:
                if in_b and right_obj[key] != base_d[key]:
                    worst = "COMPOSE_AND_MERGE" if _RANK["COMPOSE_AND_MERGE"] > _RANK[worst] else worst
                else:
                    worst = "COMPOSE_AND_MERGE"
        if worst == "DEDUPED" and left_obj != right_obj:
            worst = "COMPOSE_AND_MERGE"
        return worst, "JSON object key union"
    if isinstance(left_obj, list) and isinstance(right_obj, list):
        base_l = base_obj if isinstance(base_obj, list) else []
        if _is_append_only(base_l, left_obj) and _is_append_only(base_l, right_obj):
            return "COMPOSE_AND_MERGE", "JSON array append-only union"
        return "CONFLICT", "JSON arrays are not append-only relative to base"
    return "CONFLICT", "JSON scalars disagree"


def _is_append_only(base, side):
    return isinstance(base, list) and isinstance(side, list) and list(side[:len(base)]) == list(base)


def _line_verdict(base, left, right):
    """Additive line merge. Insert-only hunks compose even at the same index."""
    base_lines = (base or b"").decode("utf-8").splitlines(True)
    left_lines = (left or b"").decode("utf-8").splitlines(True)
    right_lines = (right or b"").decode("utf-8").splitlines(True)
    if left_lines == right_lines:
        return "DEDUPED", "SI-IDENTICAL-BLOB", "identical text after decode"

    def touched_and_repl(src, dst):
        sm = SequenceMatcher(a=src, b=dst, autojunk=False)
        touched = {}
        inserts_only = True
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            if tag in ("replace", "delete"):
                inserts_only = False
                repl = tuple(dst[j1:j2])
                for i in range(i1, i2):
                    touched[i] = (tag, repl)
            # insert does not touch original lines
        return touched, inserts_only

    t_left, ins_left = touched_and_repl(base_lines, left_lines)
    t_right, ins_right = touched_and_repl(base_lines, right_lines)
    overlap = set(t_left) & set(t_right)
    for idx in overlap:
        if t_left[idx] != t_right[idx]:
            return (
                "CONFLICT",
                "SI-SEMANTIC-DISAGREE",
                "original line %d changed to different bytes on both sides" % (idx + 1,),
            )
    if ins_left and ins_right and not t_left and not t_right:
        return "COMPOSE_AND_MERGE", "SI-ADDITIVE-INSERT", "both sides insert only; original lines untouched"
    if not overlap:
        return "COMPOSE_AND_MERGE", "SI-ADDITIVE-INSERT", "no overlapping original-line edits"
    # overlapping original lines but identical replacements, plus possible inserts
    if left_lines != right_lines:
        return "COMPOSE_AND_MERGE", "SI-ADDITIVE-INSERT", "overlapping original-line edits are identical; remainder composes"
    return "DEDUPED", "SI-IDENTICAL-BLOB", "identical after overlapping hunks"


def classify_path(path, base, left, right):
    """Classify one path. Missing side is None bytes (deleted / never added)."""
    evidence = {
        "path": path,
        "base_blob": git_blob_sha(base),
        "left_blob": git_blob_sha(left),
        "right_blob": git_blob_sha(right),
    }
    if left == right:
        evidence.update({
            "verdict": "DEDUPED",
            "rule_id": "SI-IDENTICAL-BLOB",
            "reason": "byte-identical blobs on both sides",
        })
        return evidence
    if not _is_text(left) or not _is_text(right) or (base is not None and not _is_text(base)):
        evidence.update({
            "verdict": "CONFLICT",
            "rule_id": "SI-SEMANTIC-DISAGREE",
            "reason": "non-text blobs differ and cannot be composed",
        })
        return evidence

    ok_l, obj_l = _parse_json(left)
    ok_r, obj_r = _parse_json(right)
    if ok_l and ok_r:
        ok_b, obj_b = _parse_json(base) if base is not None else (True, None)
        if not ok_b:
            obj_b = None
        verdict, reason = _json_verdict(obj_b, obj_l, obj_r)
        evidence.update({
            "verdict": verdict,
            "rule_id": "SI-JSON-KEY-UNION" if verdict != "CONFLICT" else "SI-SEMANTIC-DISAGREE",
            "reason": reason,
        })
        if verdict == "DEDUPED":
            evidence["rule_id"] = "SI-IDENTICAL-BLOB"
        return evidence

    verdict, rule_id, reason = _line_verdict(base, left, right)
    evidence.update({"verdict": verdict, "rule_id": rule_id, "reason": reason})
    return evidence


def classify_pair(base, left, right, meta=None):
    """Classify two competing trees against a shared base.

    base/left/right: path -> bytes (absent path omitted).
    meta: optional dict with base_sha, left_sha, right_sha, left_label, right_label,
    and any not-stopping facts (busy_main, stale_base, unrelated_checks).
    """
    meta = dict(meta or {})
    left_changed = changed_map(base, left)
    right_changed = changed_map(base, right)
    overlap = sorted(set(left_changed) & set(right_changed))
    paths = {}
    rule_ids = []
    reasons = []
    worst = "CLEAR_TO_MERGE"
    if not overlap:
        rule_ids.append("SI-DISJOINT")
        reasons.append("no overlapping changed paths")
    for path in overlap:
        row = classify_path(path, base.get(path), left.get(path), right.get(path))
        paths[path] = row
        rule_ids.append(row["rule_id"])
        reasons.append("%s: %s" % (path, row["reason"]))
        if _RANK[row["verdict"]] > _RANK[worst]:
            worst = row["verdict"]
    if overlap and worst == "CLEAR_TO_MERGE":
        worst = "DEDUPED"
    facts = {name: bool(meta.get(name)) for name in NOT_STOPPING}
    # parallel branches are a fact of this comparison, never a stop
    facts["parallel_branches"] = True
    return {
        "verdict": worst,
        "base_sha": meta.get("base_sha") or "",
        "left_sha": meta.get("left_sha") or "",
        "right_sha": meta.get("right_sha") or "",
        "left_label": meta.get("left_label") or "left",
        "right_label": meta.get("right_label") or "right",
        "left_paths": sorted(left_changed),
        "right_paths": sorted(right_changed),
        "overlapping_paths": overlap,
        "blob_hashes": {
            path: {
                "base": paths[path]["base_blob"],
                "left": paths[path]["left_blob"],
                "right": paths[path]["right_blob"],
            }
            for path in paths
        },
        "paths": paths,
        "rule_ids": rule_ids,
        "reasons": reasons,
        "not_stopping": list(NOT_STOPPING),
        "facts": facts,
    }


def load_fixture(name, root=None):
    """Load host/sprint_integration_fixtures/<name>/{base,left,right}/... as path->bytes.

    Side directories are deltas overlaid on base. An omitted path is unchanged,
    not deleted. That is the fixture contract; classify_pair still treats a
    missing path in a fully-specified tree as a delete.
    """
    fixture = os.path.join(root or _FIXTURE_ROOT, name)
    sides = {}
    for side in ("base", "left", "right"):
        tree = {}
        side_root = os.path.join(fixture, side)
        if os.path.isdir(side_root):
            for dirpath, _dirs, files in os.walk(side_root):
                for filename in files:
                    full = os.path.join(dirpath, filename)
                    rel = os.path.relpath(full, side_root).replace("\\", "/")
                    with open(full, "rb") as fh:
                        tree[rel] = fh.read()
        sides[side] = tree
    base = sides["base"]
    left = dict(base)
    left.update(sides["left"])
    right = dict(base)
    right.update(sides["right"])
    return {"base": base, "left": left, "right": right}


def classify_fixture(name, root=None, meta=None):
    sides = load_fixture(name, root=root)
    return classify_pair(sides["base"], sides["left"], sides["right"], meta=meta)


def teach_line(repo="woahwhattheheck/commons"):
    return (
        "*sprint* MERGE DEFAULT · parallel branches are not collisions · "
        "CONFLICT only when same effective code disagrees · "
        "busy main / stale base / unrelated checks are not stops · "
        "<https://github.com/%s/blob/main/%s|policy> · "
        "<https://github.com/%s/blob/main/%s|law>"
        % (repo, POLICY_PATH, repo, LAW_PATH)
    )


def format_slack_lines(scan, repo="woahwhattheheck/commons"):
    """Compact Slack lines. Teach the rule, then exact PR verdicts with evidence."""
    lines = [teach_line(repo)]
    by_pr = {}
    raw_by_pr = scan.get("by_pr") or {}
    if isinstance(raw_by_pr, dict):
        for key, info in raw_by_pr.items():
            try:
                number = int(key)
            except (TypeError, ValueError):
                continue
            if isinstance(info, dict):
                by_pr[number] = info
    prs = {}
    for pr in scan.get("prs") or []:
        if not isinstance(pr, dict):
            continue
        try:
            number = int(pr.get("number"))
        except (TypeError, ValueError):
            continue
        prs[number] = pr
    if by_pr:
        bits = []
        for number in sorted(by_pr):
            info = by_pr[number]
            pr = prs.get(number, {})
            bits.append("`#%s` *%s* `%s`→`%s`" % (
                number,
                info.get("verdict") or "CLEAR_TO_MERGE",
                (pr.get("base_sha") or "")[:7] or "?",
                (pr.get("head_sha") or "")[:7] or "?",
            ))
        lines.append("*open PRs* " + " · ".join(bits[:8]))
    for pair in scan.get("pairs") or []:
        if pair.get("verdict") != "CONFLICT":
            continue
        overlap = pair.get("overlapping_paths") or []
        blobs = pair.get("blob_hashes") or {}
        path = overlap[0] if overlap else "?"
        blob = blobs.get(path) or {}
        lines.append(
            ":warning: *CONFLICT* %s vs %s path `%s` %s left `%s` right `%s` base `%s` head-L `%s` head-R `%s`"
            % (
                pair.get("left_label"),
                pair.get("right_label"),
                path,
                ",".join(pair.get("rule_ids") or ["SI-SEMANTIC-DISAGREE"]),
                (blob.get("left") or "")[:12],
                (blob.get("right") or "")[:12],
                (pair.get("base_sha") or "")[:7],
                (pair.get("left_sha") or "")[:7],
                (pair.get("right_sha") or "")[:7],
            )
        )
    return lines[:12]


def _blob_bytes(fetch_json, repo, sha):
    if not sha:
        return None
    payload = fetch_json("/repos/%s/git/blobs/%s" % (repo, sha))
    if not isinstance(payload, dict):
        return None
    content = payload.get("content") or ""
    encoding = payload.get("encoding") or "base64"
    if encoding == "base64":
        import base64
        try:
            return base64.b64decode(content)
        except (ValueError, TypeError):
            return None
    if encoding == "utf-8":
        return content.encode("utf-8")
    return None


def _contents_bytes(fetch_json, repo, path, ref):
    payload = fetch_json("/repos/%s/contents/%s" % (repo, path), ref=ref)
    if not isinstance(payload, dict) or payload.get("type") != "file":
        return None
    sha = payload.get("sha")
    return _blob_bytes(fetch_json, repo, sha)


def _pr_files(fetch_json, repo, number):
    try:
        number = int(number)
    except (TypeError, ValueError):
        return {}
    if number < 1:
        return {}
    files = fetch_json("/repos/%s/pulls/%d/files" % (repo, number), per_page=100)
    if not isinstance(files, list):
        return {}
    out = {}
    for entry in files:
        if not isinstance(entry, dict):
            continue
        path = entry.get("filename") or ""
        if not path:
            continue
        if entry.get("status") == "removed":
            out[path] = {"sha": None, "status": "removed"}
        else:
            out[path] = {"sha": entry.get("sha") or None, "status": entry.get("status") or "modified"}
    return out


def pulse_scan(fetch_json, repo, head_sha, max_prs=20):
    """Classify open PRs against each other using GitHub API fetch_json(path, **params)."""
    pulls = fetch_json("/repos/%s/pulls" % repo, state="open", per_page=max_prs, base="main")
    if not isinstance(pulls, list):
        pulls = []
    prs = []
    for pr in pulls:
        if not isinstance(pr, dict):
            continue
        try:
            number = int(pr.get("number"))
        except (TypeError, ValueError):
            continue
        if number < 1:
            continue
        base_sha = ((pr.get("base") or {}).get("sha")) or ""
        head = (pr.get("head") or {}).get("sha") or ""
        files = _pr_files(fetch_json, repo, number)
        prs.append({
            "number": number,
            "title": (pr.get("title") or "")[:72],
            "base_sha": base_sha,
            "head_sha": head,
            "stale_base": bool(head_sha and base_sha and base_sha != head_sha),
            "paths": sorted(files),
            "files": files,
        })
    pairs = []
    by_pr = {}
    for i, left in enumerate(prs):
        worst = "CLEAR_TO_MERGE"
        for right in prs[i + 1:]:
            overlap = sorted(set(left["paths"]) & set(right["paths"]))
            if not overlap:
                continue
            base_tree, left_tree, right_tree = {}, {}, {}
            for path in overlap:
                lf = left["files"].get(path) or {}
                rf = right["files"].get(path) or {}
                left_tree[path] = _blob_bytes(fetch_json, repo, lf.get("sha")) if lf.get("sha") else None
                right_tree[path] = _blob_bytes(fetch_json, repo, rf.get("sha")) if rf.get("sha") else None
                base_tree[path] = _contents_bytes(fetch_json, repo, path, head_sha)
            result = classify_pair(
                base_tree, left_tree, right_tree,
                meta={
                    "base_sha": head_sha or "",
                    "left_sha": left["head_sha"],
                    "right_sha": right["head_sha"],
                    "left_label": "#%s" % left["number"],
                    "right_label": "#%s" % right["number"],
                    "stale_base": left["stale_base"] or right["stale_base"],
                    "busy_main": True,
                    "unrelated_checks": True,
                    "parallel_branches": True,
                },
            )
            pairs.append(result)
            if _RANK[result["verdict"]] > _RANK[worst]:
                worst = result["verdict"]
            other = by_pr.get(right["number"], {"verdict": "CLEAR_TO_MERGE"})
            if _RANK[result["verdict"]] > _RANK[other["verdict"]]:
                by_pr[right["number"]] = {"verdict": result["verdict"], "vs": left["number"]}
        by_pr.setdefault(left["number"], {"verdict": worst})
        if _RANK[worst] > _RANK[by_pr[left["number"]]["verdict"]]:
            by_pr[left["number"]] = {"verdict": worst}
    scan = {
        "policy": POLICY_PATH,
        "head": head_sha or "",
        "prs": [{k: v for k, v in p.items() if k != "files"} for p in prs],
        "pairs": pairs,
        "by_pr": {str(k): v for k, v in by_pr.items()},
        "not_stopping": list(NOT_STOPPING),
    }
    scan["slack_lines"] = format_slack_lines(scan, repo)
    return scan


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Commons sprint-integration checker")
    parser.add_argument("--fixture", help="classify a named fixture")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.fixture:
        result = classify_fixture(args.fixture)
        if args.json:
            print(json.dumps(result, indent=1, sort_keys=True))
        else:
            print(result["verdict"], " ".join(result["rule_ids"]))
        return 0 if result["verdict"] in VERDICTS else 1
    if args.self_test:
        expected = {
            "disjoint": "CLEAR_TO_MERGE",
            "identical_blobs": "DEDUPED",
            "additive_compose": "COMPOSE_AND_MERGE",
            "semantic_conflict": "CONFLICT",
        }
        failed = 0
        for name, verdict in expected.items():
            got = classify_fixture(name)["verdict"]
            ok = got == verdict
            print("%s %s %s" % ("ok" if ok else "FAIL", name, got))
            failed += not ok
        return 1 if failed else 0
    print("usage: sprint_integration.py --fixture NAME | --self-test")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
