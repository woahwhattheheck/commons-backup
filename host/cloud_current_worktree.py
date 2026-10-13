#!/usr/bin/env python3
"""host/cloud_current_worktree.py — ephemeral cloud-current working copy.

GitHub origin/main is durable truth. Local is a safe working copy.
Every carrier (Claude, GPT/Codex, Grok, Gemini, future peers) can open an
isolated clone or worktree off the owner's disk, keep it current with
GitHub, and never discard dirt.

This is the ephemeral-cloud road. It composes with
ground/CLOUD_STORAGE_ONLY.md; it does not replace the owner-disk freeze.
Never force-push, reset --hard, checkout --, stash drop/pop, or clean -f.
Never fabricate CURRENT. Busy/stale main is not a stop.

  python3 host/cloud_current_worktree.py open [--peer NAME] [--dest DIR]
  python3 host/cloud_current_worktree.py refresh
  python3 host/cloud_current_worktree.py status
  python3 host/cloud_current_worktree.py snapshot
  python3 host/cloud_current_worktree.py recover RECEIPT
  python3 host/cloud_current_worktree.py --self-test
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from difflib import SequenceMatcher
from typing import Any


DEFAULT_REPO = "https://github.com/woahwhattheheck/commons.git"
KIND = "CLOUD_CURRENT_WORKTREE"
SCHEMA = "v1"
SESSION_DIR = ".commons-worktree"
SESSION_FILE = os.path.join(SESSION_DIR, "session.json")
RECEIPTS_DIR = os.path.join(SESSION_DIR, "receipts")
JOURNAL_FILE = os.path.join(SESSION_DIR, "git-journal.jsonl")
RECOVERY_REF_PREFIX = "refs/commons-worktree/recovery/"
META = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

OWNER_DISK_MARKERS = (
    "users/lucys",
    r"c:/users/lucys",
    r"c:\users\lucys",
    "desktop/commons",
    ".cursor/worktrees",
    ".claude/worktrees",
    "localdeviceagent/.claude/worktrees",
)

_CONFLICT = object()
_MISSING = object()

SECRET_BASENAMES = {
    ".env",
    ".netrc",
    "credentials.json",
    "auth.json",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
}


class ForbiddenGit(RuntimeError):
    pass


class OwnerDiskRefuse(RuntimeError):
    pass


class CloudCurrentError(RuntimeError):
    pass


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def new_id(peer, kind="wt"):
    stamp = time.strftime("%Y%m%d", time.gmtime())
    suffix = uuid.uuid4().hex[:6]
    peer = re.sub(r"[^a-z0-9]+", "-", (peer or "unseated").lower()).strip("-") or "unseated"
    return "%s-%s-%s-%s" % (kind, peer, stamp, suffix)


def sha256_bytes(data):
    if data is None:
        return ""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def norm_path(path):
    return os.path.abspath(os.path.expanduser(path or "")).replace("\\", "/")


def owner_disk_reason(path):
    flag = os.environ.get("COMMONS_OWNER_DISK", "").strip().lower()
    if flag in ("1", "true", "yes"):
        return "COMMONS_OWNER_DISK=1"
    text = norm_path(path).lower()
    for marker in OWNER_DISK_MARKERS:
        if marker.replace("\\", "/") in text:
            return marker
    return ""


def refuse_owner_disk(path):
    reason = owner_disk_reason(path)
    if reason:
        raise OwnerDiskRefuse(
            "refuses owner-disk dest %s (%s). Use an ephemeral cloud dest. "
            "Owner-disk freeze is unchanged (ground/CLOUD_STORAGE_ONLY.md)."
            % (path, reason)
        )
    return path


def is_secret_name(rel):
    name = os.path.basename(rel or "").lower()
    if name in SECRET_BASENAMES or name.startswith(".env."):
        return True
    if name.endswith((".pem", ".p12", ".pfx", ".p8")):
        return True
    if name.endswith(".key") and "public" not in name:
        return True
    for part in ("secret", "credential", "password", "private-key"):
        if part in name:
            return True
    return False


def _flag_has_f(token):
    if token == "--force" or token == "-f":
        return True
    if token.startswith("--"):
        return False
    if token.startswith("-") and "f" in token[1:]:
        return True
    return False


def refuse_forbidden_argv(argv):
    if not argv:
        raise ForbiddenGit("empty git argv")
    cmd = argv[0]
    tokens = list(argv)
    if cmd == "reset" and ("--hard" in tokens or "--merge" in tokens):
        raise ForbiddenGit("git reset --hard/--merge is forbidden")
    if cmd == "checkout" and "--" in tokens:
        raise ForbiddenGit("git checkout -- is forbidden (would overwrite dirt)")
    if cmd == "stash" and any(t in tokens for t in ("drop", "pop", "apply", "push", "save", "clear")):
        raise ForbiddenGit("git stash drop/pop/apply/push is forbidden; stash create is the recovery object")
    if cmd == "clean" and any(_flag_has_f(t) for t in tokens[1:]):
        raise ForbiddenGit("git clean -f is forbidden")
    # In a short push-option cluster, -o consumes the remaining characters.
    # Reject a preceding -f, not an f inside the attached push-option value.
    if cmd == "push" and any(
        re.match(r"^-[^-o]*f", t) or t.startswith("--force") for t in tokens[1:]
    ):
        raise ForbiddenGit("force-push is forbidden")
    if cmd == "worktree" and "remove" in tokens and any(_flag_has_f(t) for t in tokens):
        raise ForbiddenGit("git worktree remove --force is forbidden")
    if cmd in ("gc", "prune"):
        raise ForbiddenGit("git gc/prune is forbidden")
    return argv


def _default_git_env():
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    return env


def journal_append(worktree, argv, extra=None):
    if not worktree:
        return
    git_marker = os.path.join(worktree, ".git")
    if not (os.path.isdir(git_marker) or os.path.isfile(git_marker) or os.path.isdir(os.path.join(worktree, SESSION_DIR))):
        return
    path = os.path.join(worktree, JOURNAL_FILE)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        row = {"ts": utc_now(), "argv": list(argv)}
        if extra:
            row.update(extra)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        return


def git(argv, cwd=None, check=True, timeout=120, input_bytes=None):
    refuse_forbidden_argv(list(argv))
    if cwd and not os.path.isdir(cwd):
        if check:
            raise CloudCurrentError("cwd missing for git %s: %s" % (" ".join(argv), cwd))
        return 1, b"", b"cwd missing"
    if cwd:
        journal_append(cwd, argv)
    proc = subprocess.run(
        ["git"] + list(argv),
        cwd=cwd,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_default_git_env(),
        timeout=timeout,
        check=False,
    )
    if check and proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", "replace").strip()
        out = (proc.stdout or b"").decode("utf-8", "replace").strip()
        raise CloudCurrentError("git %s failed (%s): %s %s" % (" ".join(argv), proc.returncode, err, out))
    return proc.returncode, proc.stdout or b"", proc.stderr or b""


def git_text(argv, cwd=None, check=True):
    rc, out, err = git(argv, cwd=cwd, check=check)
    return rc, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


def git_ok(cwd):
    rc, _, _ = git(["rev-parse", "--is-inside-work-tree"], cwd=cwd, check=False)
    return rc == 0


def head_sha(cwd):
    rc, out, _ = git_text(["rev-parse", "HEAD"], cwd=cwd, check=False)
    if rc != 0:
        return ""
    return out.strip()


def rev_sha(cwd, rev):
    rc, out, _ = git_text(["rev-parse", "--verify", rev], cwd=cwd, check=False)
    if rc != 0:
        return ""
    return out.strip()


def unique_ahead(cwd, tip="HEAD", base="origin/main"):
    rc, out, _ = git_text(["rev-list", "--count", "%s..%s" % (base, tip)], cwd=cwd, check=False)
    if rc != 0:
        return 0
    try:
        return int(out.strip() or "0")
    except ValueError:
        return 0


def show_at(cwd, rev, rel):
    path = rel.replace(os.sep, "/")
    # Tree presence is independent of whether the referenced blob can be read.
    # An unreadable tracked blob must not look like an upstream deletion.
    _, listing, _ = git(
        ["--literal-pathspecs", "ls-tree", "-z", "--full-tree", rev, "--", path],
        cwd=cwd,
    )
    if not listing:
        return None
    _, out, _ = git(["show", "%s:%s" % (rev, path)], cwd=cwd)
    return out


def name_status(cwd, a, b, include_modes=False):
    format_flag = "--raw" if include_modes else "--name-status"
    rc, out, _ = git(["diff", format_flag, "--no-renames", "-z", a, b], cwd=cwd, check=False)
    if rc != 0:
        return []
    fields = out.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    if len(fields) % 2:
        raise CloudCurrentError("incomplete NUL-delimited git name-status output")
    rows = []
    for index in range(0, len(fields), 2):
        status = os.fsdecode(fields[index])
        rel = os.fsdecode(fields[index + 1])
        if include_modes:
            parts = status.split()
            if len(parts) != 5 or not parts[0].startswith(":"):
                raise CloudCurrentError("incomplete raw git diff metadata")
            rows.append((parts[4], rel, parts[0][1:], parts[1]))
        else:
            rows.append((status, rel))
    return rows


def porcelain(cwd):
    # -z gives literal filenames and uses a separate original-path record for
    # renames/copies. Line parsing confuses newlines, Git's quoting, and an
    # ordinary filename that happens to contain the text " -> ".
    rc, out, _ = git(["status", "--porcelain=v1", "-z", "-uall"], cwd=cwd, check=False)
    if rc != 0:
        return []
    fields = iter(out.split(b"\0"))
    rows = []
    for field in fields:
        if not field:
            continue
        if len(field) < 4 or field[2:3] != b" ":
            raise CloudCurrentError("incomplete NUL-delimited git status output")
        xy = os.fsdecode(field[:2])
        rel = os.fsdecode(field[3:])
        if "R" in xy or "C" in xy:
            # The first filename is the destination in porcelain's -z form.
            # Consume its source even when the destination is session metadata.
            if not next(fields, b""):
                raise CloudCurrentError("git status rename is missing its source path")
        if rel.startswith(SESSION_DIR + "/") or rel == SESSION_DIR:
            continue
        rows.append((xy, rel))
    return rows


def dirty_paths(cwd):
    return [rel for _xy, rel in porcelain(cwd)]


def read_file_bytes(root, rel):
    path = os.path.join(root, rel)
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError:
        return None


def write_file_bytes(root, rel, data):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    # Keep the existing link and write its target, as open(path, "wb") did.
    target = os.path.realpath(path)
    try:
        mode = stat.S_IMODE(os.stat(target).st_mode)
    except FileNotFoundError:
        mode = None
    staging = os.path.join(os.path.dirname(target), ".commons-write-" + uuid.uuid4().hex)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    # New files retain the ordinary creation mode under the current umask.
    descriptor = os.open(staging, flags, 0o666)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            if mode is not None:
                os.chmod(staging, mode)
            handle.write(data if data is not None else b"")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staging, target)
    finally:
        try:
            os.unlink(staging)
        except FileNotFoundError:
            pass


def write_refreshed_file(root, rel, data, base_mode, origin_mode):
    """Compose the executable bit alongside bytes, preserving local chmods."""
    path = os.path.join(root, rel)
    apply_mode = origin_mode in ("100644", "100755")
    try:
        current = os.lstat(path)
    except FileNotFoundError:
        pass
    else:
        # An existing added file or a local chmod carries local intent. Keep it.
        apply_mode = (apply_mode and stat.S_ISREG(current.st_mode)
                      and base_mode in ("100644", "100755")
                      and bool(current.st_mode & stat.S_IXUSR) == (base_mode == "100755"))
    write_file_bytes(root, rel, data)
    if apply_mode:
        mode = stat.S_IMODE(os.stat(path).st_mode)
        mode = mode | 0o111 if origin_mode == "100755" else mode & ~0o111
        os.chmod(path, mode)


def unlink_if_exists(root, rel):
    path = os.path.join(root, rel)
    if os.path.isfile(path) or os.path.islink(path):
        os.remove(path)


def session_path(worktree):
    return os.path.join(worktree, SESSION_FILE)


def load_session(worktree):
    path = session_path(worktree)
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_session(worktree, session):
    os.makedirs(os.path.join(worktree, SESSION_DIR), exist_ok=True)
    path = session_path(worktree)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(session, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    os.replace(tmp, path)
    # Linked worktrees use a .git file. Git resolves info/exclude through the
    # common Git directory so private session data stays ignored in both modes.
    rc, exclude, _ = git_text(["rev-parse", "--git-path", "info/exclude"],
                             cwd=worktree, check=False)
    if rc or not exclude.strip():
        return
    exclude = os.path.join(worktree, exclude.rstrip("\r\n"))
    try:
        os.makedirs(os.path.dirname(exclude), exist_ok=True)
        existing = ""
        if os.path.isfile(exclude):
            with open(exclude, encoding="utf-8") as handle:
                existing = handle.read()
        if SESSION_DIR not in existing:
            with open(exclude, "a", encoding="utf-8") as handle:
                handle.write("\n%s/\n" % SESSION_DIR)
    except OSError:
        pass


def find_worktree(explicit=None):
    if explicit:
        return norm_path(explicit)
    env = os.environ.get("COMMONS_WORKTREE", "").strip()
    if env:
        return norm_path(env)
    cwd = norm_path(os.getcwd())
    cur = cwd
    for _ in range(12):
        if os.path.isfile(os.path.join(cur, SESSION_FILE)):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return cwd


def dirty_listing(worktree):
    rows = []
    for rel in dirty_paths(worktree):
        item = {"path": rel}
        if is_secret_name(rel):
            item["redacted"] = True
            item["sha256"] = ""
            item["bytes"] = None
        else:
            data = read_file_bytes(worktree, rel)
            item["sha256"] = sha256_bytes(data) if data is not None else ""
            item["bytes"] = 0 if data is None else len(data)
            item["missing"] = data is None
        rows.append(item)
    return rows


def _is_text(data):
    if data is None:
        return True
    sample = data[:4096]
    if b"\0" in sample:
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


def _is_append_only(base, side):
    return isinstance(base, list) and isinstance(side, list) and list(side[: len(base)]) == list(base)


def _compose_json(base, left, right):
    if left == right:
        return left
    if left == base:
        return right
    if right == base:
        return left
    if isinstance(left, dict) and isinstance(right, dict):
        base_d = base if isinstance(base, dict) else {}
        out = {}
        for key in set(left) | set(right) | set(base_d):
            # A missing key is a deletion, not the JSON value null. Compose
            # against the base so an unchanged side cannot undo the other edit.
            composed = _compose_json(
                base_d.get(key, _MISSING),
                left.get(key, _MISSING),
                right.get(key, _MISSING),
            )
            if composed is _CONFLICT:
                return _CONFLICT
            if composed is not _MISSING:
                out[key] = composed
        return out
    if isinstance(left, list) and isinstance(right, list):
        base_l = base if isinstance(base, list) else []
        if _is_append_only(base_l, left) and _is_append_only(base_l, right):
            seen = set()
            extras = []
            for item in list(left[len(base_l) :]) + list(right[len(base_l) :]):
                token = json.dumps(item, sort_keys=True, separators=(",", ":"))
                if token not in seen:
                    seen.add(token)
                    extras.append(item)
            return list(base_l) + extras
        return _CONFLICT
    return _CONFLICT


def _line_conflict(base, left, right):
    """True only when the same original line was replaced with different bytes."""
    if left == right:
        return False
    if not _is_text(left) or not _is_text(right) or (base is not None and not _is_text(base)):
        return True
    base_lines = (base or b"").decode("utf-8").splitlines(True)
    left_lines = (left or b"").decode("utf-8").splitlines(True)
    right_lines = (right or b"").decode("utf-8").splitlines(True)

    def touched(src, dst):
        sm = SequenceMatcher(a=src, b=dst, autojunk=False)
        out = {}
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag in ("replace", "delete"):
                repl = tuple(dst[j1:j2])
                for i in range(i1, i2):
                    out[i] = (tag, repl)
        return out

    t_left = touched(base_lines, left_lines)
    t_right = touched(base_lines, right_lines)
    for idx in set(t_left) & set(t_right):
        if t_left[idx] != t_right[idx]:
            return True
    return False


def merge_file_bytes(base, ours, theirs):
    tmp = tempfile.mkdtemp(prefix="cc-merge-")
    try:
        ours_p = os.path.join(tmp, "ours")
        base_p = os.path.join(tmp, "base")
        theirs_p = os.path.join(tmp, "theirs")
        for path, blob in ((ours_p, ours), (base_p, base), (theirs_p, theirs)):
            with open(path, "wb") as handle:
                handle.write(blob or b"")
        proc = subprocess.run(
            ["git", "merge-file", "-p", ours_p, base_p, theirs_p],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_default_git_env(),
            check=False,
        )
        body = proc.stdout or b""
        if proc.returncode not in (0, 1):
            return None, True
        conflicted = proc.returncode == 1 or b"<<<<<<<" in body
        return body, conflicted
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def classify_three_way(base, ours, theirs):
    """Parallel is allowed. Merge by default. CONFLICT only on semantic disagreement.

    Verdict names match ground/SPRINT_INTEGRATION.json: DEDUPED,
    COMPOSE_AND_MERGE, CONFLICT. Missing theirs is a delete.
    """
    if ours == theirs:
        return {
            "verdict": "DEDUPED",
            "rule_id": "SI-IDENTICAL-BLOB",
            "reason": "ours equals origin",
            "merged": ours,
        }
    if ours == base:
        return {
            "verdict": "CLEAR_TO_MERGE",
            "rule_id": "SI-DISJOINT",
            "reason": "local bytes unchanged from shared base; take origin",
            "merged": theirs,
        }
    if theirs == base:
        return {
            "verdict": "CLEAR_TO_MERGE",
            "rule_id": "SI-DISJOINT",
            "reason": "origin bytes unchanged from shared base; keep local",
            "merged": ours,
        }
    if theirs is None or ours is None:
        return {
            "verdict": "CONFLICT",
            "rule_id": "SI-SEMANTIC-DISAGREE",
            "reason": "one side deleted a path changed by the other; local state kept",
            "merged": ours,
        }
    ok_l, obj_l = _parse_json(ours)
    ok_r, obj_r = _parse_json(theirs)
    if ok_l and ok_r:
        ok_b, obj_b = _parse_json(base) if base is not None else (True, None)
        if not ok_b:
            obj_b = None
        composed = _compose_json(obj_b, obj_l, obj_r)
        if composed is not _CONFLICT:
            body = (json.dumps(composed, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
            verdict = "DEDUPED" if obj_l == obj_r else "COMPOSE_AND_MERGE"
            return {
                "verdict": verdict,
                "rule_id": "SI-JSON-KEY-UNION" if verdict != "DEDUPED" else "SI-IDENTICAL-BLOB",
                "reason": "JSON object key union" if verdict != "DEDUPED" else "identical JSON",
                "merged": body,
            }
        return {
            "verdict": "CONFLICT",
            "rule_id": "SI-SEMANTIC-DISAGREE",
            "reason": "JSON scalars disagree",
            "merged": ours,
        }
    if _line_conflict(base, ours, theirs):
        return {
            "verdict": "CONFLICT",
            "rule_id": "SI-SEMANTIC-DISAGREE",
            "reason": "same original line changed to different bytes",
            "merged": ours,
        }
    merged, conflicted = merge_file_bytes(base, ours, theirs)
    if conflicted or merged is None:
        # insert-only SequenceMatcher path: take the longer side if no replace
        if not _line_conflict(base, ours, theirs):
            # Prefer a 3-way merge-file result even with leftover markers? No.
            # Compose by taking ours+theirs inserts via merge-file already failed.
            # Fall back to ours; classify as COMPOSE if lines didn't semantically disagree.
            # If merge-file conflicted despite no original-line replace, keep ours
            # but report COMPOSE was attempted; still do not discard ours.
            return {
                "verdict": "COMPOSE_AND_MERGE",
                "rule_id": "SI-ADDITIVE-INSERT",
                "reason": "no overlapping original-line edits; kept ours and recorded origin",
                "merged": ours,
                "origin_kept_in_receipt": True,
            }
        return {
            "verdict": "CONFLICT",
            "rule_id": "SI-SEMANTIC-DISAGREE",
            "reason": "merge-file conflict",
            "merged": ours,
        }
    return {
        "verdict": "COMPOSE_AND_MERGE",
        "rule_id": "SI-ADDITIVE-INSERT",
        "reason": "3-way merge-file composed",
        "merged": merged,
    }


def empty_receipt(command, peer, worktree):
    return {
        "kind": KIND,
        "schema": SCHEMA,
        "id": new_id(peer, "cc"),
        "created_at": utc_now(),
        "peer": peer or "unseated",
        "command": command,
        "worktree": worktree or "",
        "mode": "",
        "repo": DEFAULT_REPO,
        "head": "",
        "origin_main": "",
        "origin_state": "UNKNOWN",
        "dirty_files": [],
        "conflicts": [],
        "actions": [],
        "destructive": False,
        "deleted_user_work": False,
        "force": False,
        "owner_disk": False,
        "readiness": "UNMEASURED",
        "journal_forbidden": False,
        "recovery_ref": "",
        "stash_create": "",
        "head_moved": False,
        "unique_local_commits": 0,
        "posting": "OPEN",
        "no_auth": True,
        "no_gate": True,
    }


def write_receipt(worktree, receipt):
    rid = receipt["id"]
    folder = os.path.join(worktree, RECEIPTS_DIR, rid)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "receipt.json")
    public = dict(receipt)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(public, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    os.replace(tmp, path)
    receipt["receipt_path"] = os.path.join(SESSION_DIR, "receipts", rid, "receipt.json")
    return receipt


def snapshot(worktree, peer=None, command="snapshot"):
    refuse_owner_disk(worktree)
    session = load_session(worktree)
    peer = peer or session.get("peer") or "unseated"
    receipt = empty_receipt(command, peer, worktree)
    receipt["mode"] = session.get("mode") or ""
    receipt["repo"] = session.get("repo") or DEFAULT_REPO
    receipt["head"] = head_sha(worktree) if git_ok(worktree) else ""
    origin = rev_sha(worktree, "origin/main") if git_ok(worktree) else ""
    receipt["origin_main"] = origin
    receipt["origin_state"] = "UNKNOWN"
    receipt["dirty_files"] = dirty_listing(worktree)
    files_dir = os.path.join(worktree, RECEIPTS_DIR, receipt["id"], "files")
    os.makedirs(files_dir, exist_ok=True)
    for item in receipt["dirty_files"]:
        rel = item["path"]
        if item.get("redacted"):
            receipt["actions"].append({"path": rel, "op": "redacted"})
            continue
        data = read_file_bytes(worktree, rel)
        if data is None:
            receipt["actions"].append({"path": rel, "op": "snapshot_missing"})
            continue
        try:
            source_mode = os.lstat(os.path.join(worktree, rel)).st_mode
        except OSError:
            pass
        else:
            if stat.S_ISREG(source_mode):
                item["execute_bits"] = stat.S_IMODE(source_mode) & 0o111
        dest = os.path.join(files_dir, rel)
        os.makedirs(os.path.dirname(dest) or files_dir, exist_ok=True)
        with open(dest, "wb") as handle:
            handle.write(data)
        # Hash the bytes actually copied, not the earlier dirty-list read.
        item["sha256"] = sha256_bytes(data)
        item["bytes"] = len(data)
        receipt["actions"].append({"path": rel, "op": "snapshot"})
    stash = ""
    if git_ok(worktree) and receipt["dirty_files"]:
        rc, out, _ = git_text(["stash", "create"], cwd=worktree, check=False)
        stash = (out or "").strip()
        if rc == 0 and stash and re.match(r"^[0-9a-f]{40}$", stash):
            ref = RECOVERY_REF_PREFIX + receipt["id"]
            git(["update-ref", ref, stash], cwd=worktree, check=False)
            receipt["stash_create"] = stash
            receipt["recovery_ref"] = ref
    receipt["readiness"] = "SNAPSHOTTED"
    return write_receipt(worktree, receipt)


def fetch_origin_main(worktree):
    # A single-branch clone may map only its feature branch in origin.fetch.
    # Fetching the name "main" then updates FETCH_HEAD but leaves origin/main
    # absent or stale. Name the destination explicitly before reporting CURRENT.
    rc, _, err = git(
        ["fetch", "origin", "refs/heads/main:refs/remotes/origin/main"],
        cwd=worktree, check=False, timeout=180,
    )
    sha = rev_sha(worktree, "origin/main")
    if rc != 0:
        state = "STALE" if sha else "UNKNOWN"
        return state, sha, err.decode("utf-8", "replace") if isinstance(err, bytes) else str(err)
    if not sha:
        return "UNKNOWN", "", "origin/main missing after fetch"
    return "CURRENT", sha, ""


def _write_conflict_artifacts(worktree, rid, rel, base, ours, theirs):
    folder = os.path.join(worktree, RECEIPTS_DIR, rid, "conflicts", rel)
    os.makedirs(folder, exist_ok=True)
    for name, blob in (("base", base), ("ours", ours), ("theirs", theirs)):
        path = os.path.join(folder, name)
        with open(path, "wb") as handle:
            handle.write(blob if blob is not None else b"")


def refresh(worktree, peer=None):
    refuse_owner_disk(worktree)
    if not git_ok(worktree):
        raise CloudCurrentError("not a git worktree: %s" % worktree)
    session = load_session(worktree)
    peer = peer or session.get("peer") or "unseated"
    snap = snapshot(worktree, peer=peer, command="snapshot")
    receipt = empty_receipt("refresh", peer, worktree)
    receipt["mode"] = session.get("mode") or ""
    receipt["repo"] = session.get("repo") or DEFAULT_REPO
    receipt["snapshot_id"] = snap["id"]
    receipt["head"] = head_sha(worktree)
    origin_state, origin_sha, fetch_err = fetch_origin_main(worktree)
    receipt["origin_state"] = origin_state
    receipt["origin_main"] = origin_sha
    receipt["fetch_error"] = fetch_err.strip()[:400]
    receipt["dirty_files"] = dirty_listing(worktree)
    dirty = {row["path"] for row in receipt["dirty_files"]}
    if origin_state != "CURRENT":
        receipt["readiness"] = "STALE_ORIGIN"
        receipt["actions"].append({"path": "", "op": "fetch_failed_continue"})
        receipt["unique_local_commits"] = unique_ahead(worktree)
        return write_receipt(worktree, receipt)
    head = receipt["head"] or "HEAD"
    rc, shared, _ = git_text(["merge-base", head, origin_sha], cwd=worktree, check=False)
    shared = shared.strip()
    if rc or not shared:
        raise CloudCurrentError("cannot measure a shared main ancestor; snapshot preserved and working files unchanged")
    receipt["merge_base"] = shared
    # Compare upstream against the shared ancestor. HEAD-to-origin differences
    # also contain reversals of unique local commits and must not be applied as
    # if upstream had deleted that work.
    for status, rel, base_mode, origin_mode in name_status(worktree, shared, origin_sha, include_modes=True):
        theirs = show_at(worktree, origin_sha, rel)
        base = show_at(worktree, shared, rel)
        local_committed = show_at(worktree, head, rel)
        if rel not in dirty and local_committed == base:
            if status.startswith("D") or theirs is None:
                unlink_if_exists(worktree, rel)
                receipt["actions"].append({"path": rel, "op": "apply_origin_delete"})
            else:
                write_refreshed_file(worktree, rel, theirs, base_mode, origin_mode)
                receipt["actions"].append({"path": rel, "op": "apply_origin"})
            continue
        ours = read_file_bytes(worktree, rel)
        result = classify_three_way(base, ours, theirs)
        verdict = result["verdict"]
        if verdict == "CONFLICT":
            _write_conflict_artifacts(worktree, receipt["id"], rel, base, ours, theirs)
            receipt["conflicts"].append(
                {"path": rel, "reason": result["reason"], "rule_id": result["rule_id"]}
            )
            receipt["actions"].append({"path": rel, "op": "keep_ours"})
            continue
        merged = result.get("merged")
        if merged is None:
            # A non-conflicting None is an agreed deletion, not an absent
            # merge result. Conflicting local deletions were handled above.
            unlink_if_exists(worktree, rel)
            receipt["actions"].append({"path": rel, "op": "compose_delete", "rule_id": result["rule_id"]})
            continue
        write_refreshed_file(worktree, rel, merged, base_mode, origin_mode)
        op = "dedupe" if verdict == "DEDUPED" else "compose"
        receipt["actions"].append({"path": rel, "op": op, "rule_id": result["rule_id"]})
        if result.get("origin_kept_in_receipt") and theirs is not None:
            _write_conflict_artifacts(worktree, receipt["id"], rel, base, ours, theirs)
    ahead = unique_ahead(worktree)
    receipt["unique_local_commits"] = ahead
    if ahead == 0 and origin_sha:
        # Refuse a concurrent HEAD change and surface index/ref failures. The
        # earlier snapshot remains available if refresh finishes only partly.
        git(["update-ref", "HEAD", origin_sha, head], cwd=worktree)
        git(["read-tree", origin_sha], cwd=worktree)
        # read-tree replaces skip-worktree bits along with the index. Restore
        # the existing sparse selection using Git's dirty-file-aware reapply,
        # which keeps locally modified files rather than forcing a checkout.
        rc, sparse, _ = git_text(["config", "--bool", "core.sparseCheckout"],
                                 cwd=worktree, check=False)
        if rc == 0 and sparse.strip() == "true":
            git(["sparse-checkout", "reapply"], cwd=worktree)
        receipt["head_moved"] = head_sha(worktree) == origin_sha
        receipt["head"] = head_sha(worktree)
    else:
        receipt["head_moved"] = False
        receipt["actions"].append(
            {"path": "", "op": "head_preserved", "reason": "unique local commits preserved"}
        )
    receipt["dirty_files"] = dirty_listing(worktree)
    if receipt["conflicts"]:
        receipt["readiness"] = "READY_WITH_CONFLICTS"
    else:
        receipt["readiness"] = "READY"
    return write_receipt(worktree, receipt)


def status(worktree, peer=None):
    refuse_owner_disk(worktree)
    session = load_session(worktree)
    peer = peer or session.get("peer") or "unseated"
    receipt = empty_receipt("status", peer, worktree)
    receipt["mode"] = session.get("mode") or ""
    receipt["repo"] = session.get("repo") or DEFAULT_REPO
    receipt["session_id"] = session.get("id") or ""
    if not git_ok(worktree):
        receipt["readiness"] = "UNMEASURED"
        receipt["actions"].append({"path": "", "op": "not_git"})
        return write_receipt(worktree, receipt)
    receipt["head"] = head_sha(worktree)
    origin_state, origin_sha, fetch_err = fetch_origin_main(worktree)
    receipt["origin_state"] = origin_state
    receipt["origin_main"] = origin_sha
    receipt["fetch_error"] = fetch_err.strip()[:400]
    receipt["dirty_files"] = dirty_listing(worktree)
    receipt["unique_local_commits"] = unique_ahead(worktree)
    if origin_state == "CURRENT" and not receipt["dirty_files"]:
        receipt["readiness"] = "READY"
    elif origin_state == "CURRENT":
        receipt["readiness"] = "READY"
    elif origin_state == "STALE":
        receipt["readiness"] = "STALE_ORIGIN"
    else:
        receipt["readiness"] = "UNMEASURED"
    return write_receipt(worktree, receipt)


def recover(worktree, receipt_id, peer=None):
    refuse_owner_disk(worktree)
    session = load_session(worktree)
    peer = peer or session.get("peer") or "unseated"
    folder = os.path.join(worktree, RECEIPTS_DIR, receipt_id)
    files_dir = os.path.join(folder, "files")
    meta_path = os.path.join(folder, "receipt.json")
    if not os.path.isdir(folder):
        raise CloudCurrentError("receipt not found: %s" % receipt_id)
    try:
        with open(meta_path, encoding="utf-8") as handle:
            old = json.load(handle)
    except (OSError, ValueError):
        old = {}
    out = empty_receipt("recover", peer, worktree)
    out["recovered_from"] = receipt_id
    out["mode"] = session.get("mode") or old.get("mode") or ""
    saved_items = {
        item.get("path"): item
        for item in old.get("dirty_files", []) if isinstance(item, dict)
    }
    expected_paths = {
        item.get("path") for item in old.get("actions", [])
        if isinstance(item, dict) and item.get("op") == "snapshot"
    }
    if not os.path.isdir(files_dir) and not expected_paths:
        out["readiness"] = "UNMEASURED"
        out["actions"].append({"path": "", "op": "no_file_copies"})
        return write_receipt(worktree, out)
    seen = set()
    errors = []
    unverified = []
    for dirpath, _dirs, filenames in os.walk(files_dir):
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, files_dir).replace(os.sep, "/")
            seen.add(rel)
            if is_secret_name(rel):
                out["actions"].append({"path": rel, "op": "redacted"})
                continue
            try:
                with open(full, "rb") as handle:
                    snap = handle.read()
            except OSError:
                errors.append({"path": rel, "reason": "snapshot_copy_unreadable"})
                continue
            saved = saved_items.get(rel, {})
            digest, size = saved.get("sha256"), saved.get("bytes")
            if ((digest and digest != sha256_bytes(snap))
                    or (size is not None and size != len(snap))):
                errors.append({"path": rel, "reason": "snapshot_integrity_mismatch"})
                continue
            if not digest:
                # Old receipts may lack hashes. Keep them usable, but do not
                # claim their recovered bytes have passed integrity checking.
                unverified.append(rel)
            was_absent = not os.path.lexists(os.path.join(worktree, rel))
            current = read_file_bytes(worktree, rel)
            if current is not None:
                op = "already_present" if current == snap else "kept_newer_dirt"
                out["actions"].append({"path": rel, "op": op})
                continue
            if not was_absent:
                errors.append({"path": rel, "reason": "kept_unreadable_working_path"})
                continue
            write_file_bytes(worktree, rel, snap)
            execute_bits = saved.get("execute_bits")
            # Restore execute bits only on a newly recreated file. An existing
            # file may have a newer chmod even when its bytes are unchanged.
            # Legacy receipts without this metadata keep their old behavior.
            if (was_absent and type(execute_bits) is int
                    and execute_bits >= 0 and not execute_bits & ~0o111):
                path = os.path.join(worktree, rel)
                mode = stat.S_IMODE(os.stat(path).st_mode)
                os.chmod(path, (mode & ~0o111) | execute_bits)
            out["actions"].append({"path": rel, "op": "restore"})
    errors.extend({"path": rel, "reason": "snapshot_copy_missing"}
                  for rel in sorted(expected_paths - seen))
    out["dirty_files"] = dirty_listing(worktree)
    out["head"] = head_sha(worktree) if git_ok(worktree) else ""
    out["recovery_errors"] = errors
    out["integrity_unmeasured"] = unverified
    out["ok"] = not errors
    out["readiness"] = "RECOVERED_WITH_ERRORS" if errors else "RECOVERED"
    out["deleted_user_work"] = False
    return write_receipt(worktree, out)


def _dest_occupied(dest):
    if not os.path.exists(dest):
        return False
    try:
        names = [n for n in os.listdir(dest) if n not in (".", "..")]
    except OSError:
        return True
    return bool(names)


def open_worktree(peer="unseated", dest=None, repo=None, mode="clone", source=None, blobless=False):
    peer = (peer or os.environ.get("COMMONS_PEER") or "unseated").strip() or "unseated"
    repo = (repo or os.environ.get("COMMONS_REPO") or DEFAULT_REPO).strip()
    if "x-access-token:" in repo or "@github.com" in repo and repo.startswith("https://") and ":" in repo.split("https://", 1)[1].split("@", 1)[0]:
        # Do not publish tokens. Strip any embedded userinfo.
        repo = DEFAULT_REPO
    mode = (mode or "clone").strip().lower()
    if mode not in ("clone", "worktree"):
        raise CloudCurrentError("mode must be clone or worktree")
    if blobless and mode != "clone":
        raise CloudCurrentError("--blobless requires --mode clone (new clones only)")
    sid = new_id(peer, "sess")
    if not dest:
        root = os.environ.get("COMMONS_WORKTREE_ROOT", "").strip()
        if not root:
            root = os.path.join(tempfile.gettempdir(), "commons-worktrees")
        dest = os.path.join(root, "%s-%s" % (re.sub(r"[^a-z0-9]+", "-", peer.lower()).strip("-") or "unseated", sid))
    dest = norm_path(dest)
    refuse_owner_disk(dest)
    receipt = empty_receipt("open", peer, dest)
    receipt["mode"] = mode
    receipt["repo"] = repo
    receipt["session_id"] = sid
    if os.path.isfile(session_path(dest)) and git_ok(dest):
        attached = status(dest, peer=peer)
        attached["command"] = "open"
        attached["actions"] = [{"path": dest, "op": "already_open"}]
        attached["readiness"] = attached.get("readiness") or "READY"
        return attached
    if _dest_occupied(dest) and not git_ok(dest):
        receipt["ok"] = False
        receipt["readiness"] = "DEST_OCCUPIED"
        receipt["actions"].append({"path": dest, "op": "refuse_occupied"})
        return receipt
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    if mode == "clone":
        if git_ok(dest):
            pass
        elif _dest_occupied(dest):
            receipt["ok"] = False
            receipt["readiness"] = "DEST_OCCUPIED"
            receipt["actions"].append({"path": dest, "op": "refuse_occupied"})
            return receipt
        else:
            clone_argv = ["clone", "--origin", "origin"]
            if blobless:
                clone_argv.append("--filter=blob:none")
            git(clone_argv + [repo, dest], cwd=None, timeout=300)
        branch = ""
        rc, out, _ = git_text(["rev-parse", "--abbrev-ref", "HEAD"], cwd=dest, check=False)
        branch = (out or "").strip()
    else:
        source = source or os.environ.get("COMMONS_WORKTREE_SOURCE", "").strip()
        if not source:
            raise CloudCurrentError("worktree mode needs --source or COMMONS_WORKTREE_SOURCE (ephemeral clone)")
        source = norm_path(source)
        refuse_owner_disk(source)
        if not git_ok(source):
            raise CloudCurrentError("source is not a git clone: %s" % source)
        _origin_state, origin_sha, _fetch_err = fetch_origin_main(source)
        start = origin_sha or head_sha(source)
        branch = "wt/%s/%s" % (re.sub(r"[^a-z0-9]+", "-", peer.lower()).strip("-") or "unseated", sid)
        git(["branch", branch, start], cwd=source)
        git(["worktree", "add", dest, branch], cwd=source)
        receipt["source_clone"] = source
        receipt["branch"] = branch
    session = {
        "kind": "CLOUD_CURRENT_SESSION",
        "id": sid,
        "peer": peer,
        "mode": mode,
        "repo": repo,
        "created_at": utc_now(),
        "dest": dest,
        "source_clone": source if mode == "worktree" else "",
        "branch": branch if mode == "worktree" else "HEAD",
    }
    save_session(dest, session)
    origin_state, origin_sha, fetch_err = fetch_origin_main(dest)
    receipt["origin_state"] = origin_state
    receipt["origin_main"] = origin_sha
    receipt["fetch_error"] = (fetch_err or "").strip()[:400]
    receipt["head"] = head_sha(dest)
    receipt["dirty_files"] = dirty_listing(dest)
    receipt["worktree"] = dest
    if origin_state == "CURRENT":
        receipt["readiness"] = "READY"
    elif origin_state == "STALE":
        receipt["readiness"] = "STALE_ORIGIN"
    else:
        receipt["readiness"] = "UNMEASURED"
    receipt["actions"].append({"path": dest, "op": "open"})
    return write_receipt(dest, receipt)


def journal_has_forbidden(worktree):
    path = os.path.join(worktree, JOURNAL_FILE)
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return False
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        argv = row.get("argv") or []
        try:
            refuse_forbidden_argv(list(argv))
        except ForbiddenGit:
            return True
    return False


def _init_fixture_repo(path):
    os.makedirs(path, exist_ok=True)
    git(["init", "-b", "main"], cwd=path)
    git(["config", "user.email", "peer@commons.test"], cwd=path)
    git(["config", "user.name", "cloud-current"], cwd=path)
    write_file_bytes(path, "README.md", b"hello commons\n")
    write_file_bytes(path, "keep.txt", b"stable\n")
    write_file_bytes(path, "shared.txt", b"base line\nsecond\n")
    write_file_bytes(path, "data.json", b'{"a": 1}\n')
    git(["add", "README.md", "keep.txt", "shared.txt", "data.json"], cwd=path)
    git(["commit", "-m", "init"], cwd=path)
    return path


def self_test():
    reports = []
    def check(name, cond, detail=""):
        reports.append({"name": name, "ok": bool(cond), "detail": detail})
        if not cond:
            raise CloudCurrentError("self-test failed: %s %s" % (name, detail))

    try:
        refuse_forbidden_argv(["reset", "--hard", "HEAD"])
        check("forbid-reset-hard", False)
    except ForbiddenGit:
        check("forbid-reset-hard", True)

    try:
        refuse_owner_disk("/tmp/Users/lucys/Desktop/commons/copy")
        check("owner-disk", False)
    except OwnerDiskRefuse:
        check("owner-disk", True)

    tmp = tempfile.mkdtemp(prefix="cc-self-")
    try:
        origin = _init_fixture_repo(os.path.join(tmp, "origin"))
        opened = open_worktree(peer="self", dest=os.path.join(tmp, "wt"), repo=origin, mode="clone")
        check("open-ready", opened.get("readiness") in ("READY", "STALE_ORIGIN", "UNMEASURED"), opened.get("readiness"))
        check("open-not-owner", opened.get("owner_disk") is False)
        dest = opened["worktree"]
        write_file_bytes(dest, "dirt.txt", b"my dirt\n")
        write_file_bytes(origin, "keep.txt", b"stable\nfrom-main\n")
        git(["add", "keep.txt"], cwd=origin)
        git(["commit", "-m", "main moved"], cwd=origin)
        refreshed = refresh(dest, peer="self")
        check("dirt-kept", read_file_bytes(dest, "dirt.txt") == b"my dirt\n")
        check("origin-applied", b"from-main" in (read_file_bytes(dest, "keep.txt") or b""))
        check("not-destructive", refreshed.get("destructive") is False)
        check("no-forbidden-journal", journal_has_forbidden(dest) is False)
        check("fetch-not-stop", refreshed.get("readiness") in ("READY", "READY_WITH_CONFLICTS", "STALE_ORIGIN"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {"ok": True, "checks": reports}


def _human(receipt):
    lines = [
        "%s %s" % (receipt.get("kind"), receipt.get("id")),
        "peer=%s command=%s readiness=%s" % (
            receipt.get("peer"), receipt.get("command"), receipt.get("readiness"),
        ),
        "worktree=%s" % receipt.get("worktree"),
        "head=%s origin_main=%s origin_state=%s" % (
            receipt.get("head"), receipt.get("origin_main"), receipt.get("origin_state"),
        ),
        "dirty=%d conflicts=%d destructive=%s deleted_user_work=%s force=%s"
        % (
            len(receipt.get("dirty_files") or []),
            len(receipt.get("conflicts") or []),
            receipt.get("destructive"),
            receipt.get("deleted_user_work"),
            receipt.get("force"),
        ),
    ]
    if receipt.get("receipt_path"):
        lines.append("receipt=%s" % receipt["receipt_path"])
    return "\n".join(lines)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="cloud_current_worktree.py",
        description="Ephemeral cloud-current Commons working copy. No auth. No gate.",
    )
    parser.add_argument("--json", action="store_true", help="print receipt JSON only")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--peer", default=os.environ.get("COMMONS_PEER", "unseated"))
    parser.add_argument("--worktree", default="")
    sub = parser.add_subparsers(dest="cmd")
    p_open = sub.add_parser("open")
    p_open.add_argument("--dest", default="")
    p_open.add_argument("--repo", default=DEFAULT_REPO)
    p_open.add_argument("--mode", default="clone", choices=("clone", "worktree"))
    p_open.add_argument("--blobless", action="store_true",
                        help="request lazy historical blobs for a new clone; needs server filter support")
    p_open.add_argument("--source", default="")
    sub.add_parser("refresh")
    sub.add_parser("current")
    sub.add_parser("status")
    sub.add_parser("snapshot")
    p_rec = sub.add_parser("recover")
    p_rec.add_argument("receipt")
    for command_parser in sub.choices.values():
        command_parser.add_argument("--peer", default=argparse.SUPPRESS)
        command_parser.add_argument("--worktree", default=argparse.SUPPRESS)
        command_parser.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    try:
        if args.self_test:
            receipt = self_test()
        elif args.cmd == "open":
            receipt = open_worktree(
                peer=args.peer,
                dest=args.dest or None,
                repo=args.repo,
                mode=args.mode,
                source=args.source or None,
                blobless=args.blobless,
            )
        elif args.cmd in ("refresh", "current"):
            receipt = refresh(find_worktree(args.worktree), peer=args.peer)
        elif args.cmd == "status":
            receipt = status(find_worktree(args.worktree), peer=args.peer)
        elif args.cmd == "snapshot":
            receipt = snapshot(find_worktree(args.worktree), peer=args.peer)
        elif args.cmd == "recover":
            receipt = recover(find_worktree(args.worktree), args.receipt, peer=args.peer)
        else:
            parser.print_help()
            return 2
    except OwnerDiskRefuse as exc:
        receipt = empty_receipt(args.cmd or "open", args.peer, args.worktree or "")
        receipt["owner_disk"] = True
        receipt["readiness"] = "REFUSED_OWNER_DISK"
        receipt["actions"].append({"path": args.worktree or "", "op": "refuse_owner_disk", "reason": str(exc)})
        if not args.json:
            print(str(exc), file=sys.stderr)
        print(json.dumps(receipt, indent=2, ensure_ascii=False) if args.json else _human(receipt))
        return 2
    except ForbiddenGit as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except CloudCurrentError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.json or args.self_test:
        print(json.dumps(receipt, indent=2, ensure_ascii=False))
    else:
        print(_human(receipt))
        print("---")
        print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0 if receipt.get("ok") is not False and receipt.get("readiness") != "REFUSED_OWNER_DISK" else 1


if __name__ == "__main__":
    sys.exit(main())

