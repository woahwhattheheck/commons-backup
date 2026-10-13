#!/usr/bin/env python3
"""Cross-harness restart proof on the existing per-agent memory pad.

Process A loads a persisted claim pad, appends one WORK_STATE event with a
durable event ID (the Commons ``entry_id`` / ``p/{id}.md`` id), writes pad
bytes, records the before/after git-blob SHA, then exits.

Process B is a new Python process. It reads the same pad file, finds that
event ID, and resumes from the distilled work state. It does not accept or
need the original prompt text.

This is not a second memory system. It uses ``board_ingest.write_post`` plus
``memory_board.derive`` to project ``memory/{CLAIM}.json``. Memory stays
optional context. The posting-prerequisite lock stays out.

  python3 host/memory_restart.py seed --root DIR --actor CLAIM
  python3 host/memory_restart.py append --root DIR --actor CLAIM --event-id ID
  python3 host/memory_restart.py resume --root DIR --actor CLAIM --event-id ID
  python3 host/memory_restart.py prove --root DIR
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import board_ingest
import memory_board


HARNESS = "host/memory_restart.py"
EVENT_ID_FIELD = "entry_id"
DEFAULT_ACTOR = "RESTART"
DEFAULT_CREATE_ID = "restart-memory-create-01"
DEFAULT_EVENT_ID = "restart-ws-20260831-01"
CREATE_TS = "2026-08-31T01:46:00Z"
APPEND_TS = "2026-08-31T01:46:01Z"
NEXT_ACTION = "continue-memory-restart"
EMPTY_SHA = "0" * 40


def git_blob_sha(data):
    """Git blob SHA-1 of exact pad bytes. Missing file is 40 zeros."""
    if data is None:
        return EMPTY_SHA
    if not isinstance(data, (bytes, bytearray)):
        data = str(data).encode("utf-8")
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def pad_path(root, actor):
    return os.path.join(os.path.abspath(root), "memory",
                        memory_board.canonical_actor(actor) + ".json")


def pad_sha_at(root, actor):
    path = pad_path(root, actor)
    if not os.path.isfile(path):
        return EMPTY_SHA
    with open(path, "rb") as handle:
        return git_blob_sha(handle.read())


def read_pad_file(root, actor):
    """Cross-process readback: bytes on disk, not an in-process cache."""
    path = pad_path(root, actor)
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("pad is not an object")
    return data


def find_event(board, event_id):
    wanted = str(event_id or "").strip()
    for entry in (board or {}).get("entries") or []:
        if not isinstance(entry, dict):
            continue
        if str(entry.get(EVENT_ID_FIELD) or "") == wanted:
            return entry
    return None


def next_action_from(entry):
    body = str((entry or {}).get("body") or "")
    for line in body.splitlines():
        if line.startswith("next="):
            return line.split("=", 1)[1].strip()
    return ""


def work_state_body(event_id):
    """Distilled resume state. The original prompt is not stored."""
    return "next=%s\ncursor=%s\n" % (NEXT_ACTION, event_id)


def receipt(event_id, before, after, found=0, next_action=""):
    parts = [
        "event_id=%s" % event_id,
        "before=%s" % before,
        "after=%s" % after,
        "found=%s" % int(found),
        "pid=%s" % os.getpid(),
    ]
    if next_action:
        parts.append("next=%s" % next_action)
    return " ".join(parts)


def _bind(root):
    root = os.path.abspath(root)
    posts = os.path.join(root, "p")
    os.makedirs(posts, exist_ok=True)
    os.makedirs(os.path.join(root, "by"), exist_ok=True)
    os.makedirs(os.path.join(root, "to"), exist_ok=True)
    os.makedirs(os.path.join(root, "memory"), exist_ok=True)
    saved = (board_ingest.ROOT, board_ingest.POSTS, board_ingest.BY, board_ingest.TO)
    board_ingest.ROOT = root
    board_ingest.POSTS = posts
    board_ingest.BY = os.path.join(root, "by")
    board_ingest.TO = os.path.join(root, "to")
    memory_board.clear_cache(root)
    return saved


def _unbind(saved):
    board_ingest.ROOT, board_ingest.POSTS, board_ingest.BY, board_ingest.TO = saved


def _quiet_write_post(src, dest, mid, body, ts, extra):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        return board_ingest.write_post(src, dest, mid, body, ts, extra)


def write_pad_bytes(root, actor):
    """Project the existing append-only log onto memory/{CLAIM}.json."""
    rows = board_ingest.list_posts()
    _actors, boards = memory_board.derive(rows)
    actor = memory_board.canonical_actor(actor)
    board = boards.get(actor)
    if not board:
        raise SystemExit("no pad for %s" % actor)
    path = pad_path(root, actor)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = json.dumps(board, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
    return path


def seed_pad(root, actor, create_id=DEFAULT_CREATE_ID, ts=CREATE_TS):
    actor = memory_board.canonical_actor(actor)
    saved = _bind(root)
    try:
        extra = {
            "kind": "MEMORY_CREATE",
            "actor_id": actor,
            "memory_id": create_id,
            "memory_kind": "ROLE",
            "actor_class": "CLOUD_MODEL",
            "intelligence_kind": "LLM",
            "surface": "Commons",
        }
        result = _quiet_write_post(
            actor, "MEMORY", create_id,
            "optional restart-proof context", ts, extra,
        )
        if result != "wrote":
            raise SystemExit("seed write_post=%s" % result)
        write_pad_bytes(root, actor)
        return pad_sha_at(root, actor)
    finally:
        _unbind(saved)
        memory_board.clear_cache(root)


def append_work_state(root, actor, event_id, prompt=None, ts=APPEND_TS):
    """Process A: load pad, append WORK_STATE, write bytes, record SHA.

    ``prompt`` is discarded session context. It is never written to the pad
    and is not required for resume.
    """
    del prompt  # not replayed; work state is the resume cursor
    actor = memory_board.canonical_actor(actor)
    event_id = str(event_id or "").strip()
    if not memory_board.ID_RE.match(event_id):
        raise SystemExit("event_id must be an 8-80 character Commons id")
    if not os.path.isfile(pad_path(root, actor)):
        raise SystemExit("persisted pad missing: %s" % pad_path(root, actor))
    before = pad_sha_at(root, actor)
    saved = _bind(root)
    try:
        existing = memory_board.board_record(root, actor)
        if not existing:
            raise SystemExit("persisted pad has no board for %s" % actor)
        extra = {
            "kind": "MEMORY_APPEND",
            "actor_id": actor,
            "memory_id": existing.get("memory_id") or DEFAULT_CREATE_ID,
            "memory_kind": "WORK_STATE",
        }
        result = _quiet_write_post(
            actor, "MEMORY", event_id, work_state_body(event_id), ts, extra,
        )
        if result != "wrote":
            raise SystemExit("append write_post=%s" % result)
        write_pad_bytes(root, actor)
        after = pad_sha_at(root, actor)
    finally:
        _unbind(saved)
        memory_board.clear_cache(root)
    print(receipt(event_id, before, after, found=0), flush=True)
    return before, after


def resume_work_state(root, actor, event_id):
    """Process B: new interpreter. Read pad bytes. Resume from event ID."""
    actor = memory_board.canonical_actor(actor)
    event_id = str(event_id or "").strip()
    sha = pad_sha_at(root, actor)
    board = read_pad_file(root, actor)
    entry = find_event(board, event_id)
    if not entry:
        print(receipt(event_id, sha, sha, found=0), flush=True)
        return 1
    if str(entry.get("kind") or "").strip().upper() != "WORK_STATE":
        print(receipt(event_id, sha, sha, found=0), flush=True)
        return 1
    nxt = next_action_from(entry)
    print(receipt(event_id, sha, sha, found=1, next_action=nxt), flush=True)
    return 0


def _run_child(args):
    env = os.environ.copy()
    env["PYTHONPATH"] = REPO + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, os.path.join(REPO, "host", "memory_restart.py")] + list(args),
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def prove(root, actor=DEFAULT_ACTOR, event_id=DEFAULT_EVENT_ID, prompt=None):
    """Seed, then Process A appends, then Process B resumes. Two PIDs."""
    seed_pad(root, actor)
    secret = str(prompt or "")
    append_args = [
        "append", "--root", root, "--actor", actor, "--event-id", event_id,
    ]
    if secret:
        append_args.extend(["--prompt", secret])
    child_a = _run_child(append_args)
    child_b = _run_child([
        "resume", "--root", root, "--actor", actor, "--event-id", event_id,
    ])
    line_a = (child_a.stdout or "").strip().splitlines()[-1] if child_a.stdout else ""
    line_b = (child_b.stdout or "").strip().splitlines()[-1] if child_b.stdout else ""
    print(line_a, flush=True)
    print(line_b, flush=True)
    if child_a.returncode != 0 or child_b.returncode != 0:
        return 1
    if secret and secret in (child_b.stdout or "") + (child_b.stderr or ""):
        return 1
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Restart proof on the existing memory pad",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    seed = sub.add_parser("seed", help="create a persisted claim pad")
    seed.add_argument("--root", required=True)
    seed.add_argument("--actor", default=DEFAULT_ACTOR)
    seed.add_argument("--create-id", default=DEFAULT_CREATE_ID)

    append = sub.add_parser("append", help="Process A: append WORK_STATE and exit")
    append.add_argument("--root", required=True)
    append.add_argument("--actor", default=DEFAULT_ACTOR)
    append.add_argument("--event-id", required=True)
    append.add_argument(
        "--prompt",
        default=None,
        help="discarded session context; never written; resume does not take this",
    )

    resume = sub.add_parser("resume", help="Process B: read pad and resume")
    resume.add_argument("--root", required=True)
    resume.add_argument("--actor", default=DEFAULT_ACTOR)
    resume.add_argument("--event-id", required=True)

    proof = sub.add_parser("prove", help="two-process A-then-B proof")
    proof.add_argument("--root", required=True)
    proof.add_argument("--actor", default=DEFAULT_ACTOR)
    proof.add_argument("--event-id", default=DEFAULT_EVENT_ID)
    proof.add_argument("--prompt", default=None)

    args = parser.parse_args(argv)
    if args.cmd == "seed":
        sha = seed_pad(args.root, args.actor, args.create_id)
        print(receipt(args.create_id, EMPTY_SHA, sha, found=0), flush=True)
        return 0
    if args.cmd == "append":
        append_work_state(args.root, args.actor, args.event_id, prompt=args.prompt)
        return 0
    if args.cmd == "resume":
        return resume_work_state(args.root, args.actor, args.event_id)
    if args.cmd == "prove":
        return prove(args.root, args.actor, args.event_id, prompt=args.prompt)
    return 2


if __name__ == "__main__":
    sys.exit(main())
