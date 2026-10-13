#!/usr/bin/env python3
"""Execute addressed Commons ACTION posts.

The action record is the instruction register.  A new p/*.md record with
kind: ACTION is fired once.  Repository actions use actions/results/<id>.json
as their terminal latch.  Device actions additionally require a durable,
history-backed reservation before a separate read-only runner may execute.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
POSTS = ROOT / "p"
RESULTS = ROOT / "actions" / "results"
DEVICE_RESERVATIONS = ROOT / "actions" / "device-reservations"
ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,80}$")
DEVICE_TARGETS = {"BRYCE-PC", "BRYCE_PHONE", "BRYCE-PHONE", "CURRENT-DEVICE", "DEVICE"}
MAX_ACTION_VERB_CHARS = 160
MAX_DEVICE_TARGET_CHARS = 1024
WRITER_OK = {"wrote", "exists", "unchanged"}
GROK_COM_HARNESS = "grok.com authenticated browser via Commons MCP"
GROK_SUBMIT_SCHEMA = "commons-grok-executor-submit/v1"
GROK_COMMAND_SCHEMA = "commons-grok-executor-command/v1"


def _load_board_ingest():
    """Load the repository writer only for github-scope POST/REPLY work."""
    import board_ingest as module

    globals()["board_ingest"] = module
    return module


def __getattr__(name: str):
    # Preserve the historical module attribute for callers/tests without making
    # the device executor import board_ingest and its mutable dependency graph.
    if name == "board_ingest":
        return _load_board_ingest()
    raise AttributeError(name)


def parse_record(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8")
    head, sep, body = text.partition("\n---\n")
    if not sep:
        return None
    meta: dict[str, str] = {}
    for line in head.splitlines():
        key, mark, value = line.partition(":")
        if mark:
            meta[key.strip().lower()] = value.strip()
    if meta.get("kind", "").upper() != "ACTION":
        return None
    ident = meta.get("id", "")
    if not ID_RE.fullmatch(ident):
        return None
    verb = meta.get("act", "").strip().upper()
    if not verb:
        return None
    payload = body.lstrip("\n")
    lines = payload.splitlines()
    if lines and lines[0].strip().upper() == verb:
        lines.pop(0)
    if lines and lines[0].lower().startswith("target:"):
        lines.pop(0)
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and lines[0].lower().startswith("circuit:"):
        # Additive composition marker. Absent on ordinary single-verb pastes.
        meta.setdefault("circuit", lines[0].split(":", 1)[1].strip())
        lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)
    try:
        record_path = str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        record_path = str(path)
    return {"path": record_path, "meta": meta, "verb": verb,
            "target": meta.get("target", "").strip(), "payload": "\n".join(lines)}


CIRCUIT_WRAPPERS = {"CIRCUIT", "COMPOSE"}
STEP_MARK = re.compile(r"(?m)^---\s*STEP(?:\s+\d+)?\s*---\s*$")


def split_circuit_verbs(text: str) -> list[str]:
    """Split an ordered verb list. Comma / semicolon / pipe / arrow / newline.

    Spaces inside a token stay part of the verb (`MAKE IT SO`).
    This is not an allowlist: every nonempty token is kept.
    """
    if not (text or "").strip():
        return []
    parts = re.split(r"\s*(?:,|;|\||->|→|\n)\s*", text.strip())
    return [part.strip().upper() for part in parts if part.strip()]


def circuit_step_id(ident: str, index: int) -> str:
    suffix = "-s%02d" % index
    keep = max(8, 80 - len(suffix))
    return ident[:keep] + suffix


def _parse_step_block(text: str, default_verb: str = "", default_target: str = "") -> dict:
    """Parse one step body: optional verb line, optional target:, then payload."""
    lines = text.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    verb = (default_verb or "").strip().upper()
    target = default_target
    if lines and lines[0].lower().startswith("verb:"):
        verb = lines.pop(0).split(":", 1)[1].strip().upper()
    elif lines and lines[0].lower().startswith("act:"):
        verb = lines.pop(0).split(":", 1)[1].strip().upper()
    elif lines and verb and lines[0].strip().upper() == verb:
        lines.pop(0)
    elif (
        not verb
        and lines
        and not lines[0].lower().startswith("target:")
        and ":" not in lines[0]
    ):
        verb = lines.pop(0).strip().upper()
    if lines and lines[0].lower().startswith("target:"):
        target = lines.pop(0).split(":", 1)[1].strip()
    while lines and not lines[0].strip():
        lines.pop(0)
    return {"verb": verb, "target": target, "payload": "\n".join(lines)}


def _parse_verb_headed_steps(payload: str, verbs: list[str], default_target: str) -> list[dict] | None:
    """Split a paste on exact verb-header lines when circuit: listed those verbs."""
    if len(verbs) < 2:
        return None
    pat = re.compile(r"(?im)^(" + "|".join(re.escape(v) for v in verbs) + r")\s*$")
    matches = list(pat.finditer(payload))
    if len(matches) < 2:
        return None
    steps = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(payload)
        step = _parse_step_block(payload[match.end():end], match.group(1).upper(), default_target)
        if step["verb"]:
            steps.append(step)
    return steps if len(steps) >= 2 else None


def parse_circuit_steps(rec: dict) -> list[dict] | None:
    """Return ordered steps when this paste is an explicit circuit; else None.

    Single-verb records stay on the existing execute() path. Circuit mode is
    opt-in via `circuit:`, act CIRCUIT/COMPOSE, ---STEP--- plus a circuit
    marker, or a JSON step array on a circuit wrapper. Bare `---` is not a
    separator (PATCH diffs use it).
    """
    meta = rec.get("meta") or {}
    verb = (rec.get("verb") or "").strip().upper()
    payload = rec.get("payload") or ""
    default_target = rec.get("target") or ""
    circuit_field = (meta.get("circuit") or "").strip()
    wrapper = verb in CIRCUIT_WRAPPERS
    verbs = split_circuit_verbs(circuit_field)
    marked = bool(STEP_MARK.search(payload))

    if not wrapper and not verbs and not marked:
        return None

    if wrapper or verbs:
        stripped = payload.strip()
        if stripped.startswith("["):
            try:
                data = json.loads(stripped)
            except json.JSONDecodeError:
                data = None
            if isinstance(data, list) and len(data) >= 2 and all(isinstance(item, dict) for item in data):
                steps = []
                for item in data:
                    step_verb = str(item.get("verb") or item.get("act") or "").strip().upper()
                    if not step_verb:
                        continue
                    raw_payload = item.get("payload")
                    if raw_payload is None:
                        step_payload = ""
                    elif isinstance(raw_payload, str):
                        step_payload = raw_payload
                    else:
                        step_payload = json.dumps(raw_payload)
                    steps.append({
                        "verb": step_verb,
                        "target": str(item.get("target") or default_target or "").strip(),
                        "payload": step_payload,
                    })
                if len(steps) >= 2:
                    return steps

    if marked and (wrapper or verbs):
        blocks = [block.strip("\n") for block in STEP_MARK.split(payload)]
        if blocks and not blocks[0].strip():
            blocks = blocks[1:]
        elif blocks and verbs and not _parse_step_block(blocks[0], verbs[0], default_target)["verb"]:
            blocks = blocks[1:]
        elif blocks and wrapper and not _parse_step_block(blocks[0], "", default_target)["verb"]:
            blocks = blocks[1:]
        steps = []
        for i, block in enumerate(blocks):
            default = verbs[i] if i < len(verbs) else ""
            step = _parse_step_block(block, default, default_target)
            if step["verb"]:
                steps.append(step)
        return steps if len(steps) >= 2 else None

    headed = _parse_verb_headed_steps(payload, verbs, default_target)
    if headed:
        return headed
    return None


def execute_circuit(rec: dict, scope: str, steps: list[dict]) -> dict:
    """Run parsed steps in order through execute(). No identity/approval/allowlist."""
    ident = rec["meta"]["id"]
    step_rows: list[dict] = []
    all_changed: list[str] = []
    canonical_records: dict[str, str] = {}
    action_outputs: dict[str, str] = {}
    action_deletions: list[str] = []
    failed_step = None
    for index, step in enumerate(steps, start=1):
        step_id = circuit_step_id(ident, index)
        step_meta = {key: value for key, value in rec["meta"].items() if key != "circuit"}
        step_meta["id"] = step_id
        step_meta["act"] = step["verb"]
        step_rec = {
            "path": rec.get("path", ""),
            "meta": step_meta,
            "verb": step["verb"],
            "target": step["target"],
            "payload": step["payload"],
        }
        try:
            result = execute(step_rec, scope, _skip_circuit=True)
        except Exception as exc:
            result = {
                "id": step_id,
                "verb": step["verb"],
                "target": step["target"],
                "scope": scope,
                "ok": False,
                "error": str(exc),
                "changed": [],
                "canonical_records": {},
                "action_outputs": {},
                "action_deletions": [],
                "executed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
        result["step"] = index
        result["circuit_id"] = ident
        path = result_path(step_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        try:
            result_name = str(path.relative_to(ROOT)).replace("\\", "/")
        except ValueError:
            result_name = "actions/results/%s.json" % step_id
        step_rows.append({
            "step": index,
            "id": step_id,
            "verb": step["verb"],
            "target": step["target"],
            "ok": bool(result.get("ok")),
            "error": result.get("error"),
            "output": result.get("output"),
            "result": result_name,
        })
        all_changed.extend(result.get("changed") or [])
        all_changed.append(result_name)
        canonical_records.update(result.get("canonical_records") or {})
        action_outputs.update(result.get("action_outputs") or {})
        action_outputs[result_name] = file_sha256(path)
        action_deletions.extend(result.get("action_deletions") or [])
        if not result.get("ok"):
            failed_step = index
            break
    ok = failed_step is None
    error = None
    if not ok:
        last = step_rows[-1]
        error = "circuit step %d (%s) failed: %s" % (
            failed_step, last.get("verb") or "?", last.get("error") or "step failed",
        )
    return {
        "id": ident,
        "verb": rec["verb"],
        "target": rec.get("target") or "",
        "scope": scope,
        "ok": ok,
        "circuit": True,
        "steps": step_rows,
        "failed_step": failed_step,
        "error": error,
        "output": "circuit %d/%d ok" % (sum(1 for row in step_rows if row.get("ok")), len(steps)),
        "changed": sorted(set(all_changed)),
        "canonical_records": canonical_records,
        "action_outputs": action_outputs,
        "action_deletions": sorted(set(action_deletions)),
        "executed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def is_device_target(target: str) -> bool:
    up = target.strip().upper()
    return up in DEVICE_TARGETS or up.startswith("DEVICE:") or up.startswith("BRYCE-PC:")


def is_grok_com_target(target: str) -> bool:
    """Recognize the browser carrier address, not a repository directory."""
    normalized = target.strip().upper().rstrip("/")
    return normalized in {"GROK.COM", "HTTPS://GROK.COM", "HTTP://GROK.COM"}


def is_grok_executor_target(target: str) -> bool:
    """Recognize the public action address for executor lease transitions."""
    return target.strip().upper().rstrip("/") == "GROK.EXECUTOR"


def _job_owner(meta: dict) -> str:
    """Carry the sender into the existing uppercase Commons job claim field."""
    owner = re.sub(r"[^A-Z0-9_]", "_", str(meta.get("from") or "UNSEATED").upper())[:32]
    return owner if re.fullmatch(r"[A-Z][A-Z0-9_]{1,31}", owner) else "UNSEATED"


def queue_grok_com_task(meta: dict, verb: str, payload: str, ident: str) -> dict:
    """Route a GROK.COM action into the one durable shared executor queue.

    This process never owns a browser and never submits the prompt. It records
    the requester, exact bytes, structural-capture START packet, bounded retry
    contract, and submit-once state machine. Healthy authenticated browser hosts
    lease the resulting wake_jobs row through the Grok executor adapter.
    """
    task_bytes = payload.strip()
    if not task_bytes:
        raise ValueError("GROK.COM task payload must be non-empty")

    envelope: dict = {}
    try:
        decoded = json.loads(task_bytes)
    except json.JSONDecodeError:
        decoded = None
    if isinstance(decoded, dict) and decoded.get("schema") == GROK_SUBMIT_SCHEMA:
        allowed = {
            "schema", "run_key", "exact_prompts", "origin", "lineage",
            "conversation_url", "lease_seconds", "max_attempts", "budget_tokens",
        }
        unknown = sorted(set(decoded) - allowed)
        if unknown:
            raise ValueError("unknown Grok submit envelope fields: " + ", ".join(unknown))
        envelope = decoded
        exact_prompts = envelope.get("exact_prompts")
        if (
            not isinstance(exact_prompts, list)
            or not exact_prompts
            or not all(isinstance(item, str) and item.strip() for item in exact_prompts)
        ):
            raise ValueError("Grok submit exact_prompts must be a non-empty string array")
    else:
        exact_prompts = [task_bytes]

    from integrations.grok_executor_queue import GrokExecutorQueue, SCHEMA

    before = working_state()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    at = now.isoformat().replace("+00:00", "Z")
    source_action = "p/%s.md" % ident
    run_key = str(envelope.get("run_key") or meta.get("run_key") or ("grok-action-" + ident)).strip()
    default_origin = {
        "task_id": ident,
        "session_id": str(meta.get("session_id") or meta.get("event_id") or source_action),
        "thread_id": str(meta.get("thread_ts") or meta.get("target") or ""),
        "source": "commons-action",
        "event_id": str(meta.get("event_id") or source_action),
        "requester": str(meta.get("from") or "UNSEATED"),
    }
    supplied_origin = envelope.get("origin")
    if supplied_origin is not None and not isinstance(supplied_origin, dict):
        raise ValueError("Grok submit origin must be an object")
    origin = dict(supplied_origin or default_origin)
    for key, value in default_origin.items():
        origin.setdefault(key, value)
    lineage = envelope.get("lineage")
    if lineage is None and meta.get("parent_run_key"):
        lineage = {
            "parent_run_key": str(meta.get("parent_run_key")),
            "parent_conversation_url": str(meta.get("parent_conversation_url") or ""),
        }
    queued = GrokExecutorQueue(ROOT / "wake_jobs").enqueue({
        "job_id": ident,
        "run_key": run_key,
        "origin": origin,
        "lineage": lineage,
        "conversation_url": envelope.get("conversation_url") or "",
        "exact_prompts": exact_prompts,
        "lease_seconds": int(envelope.get("lease_seconds") or 300),
        "max_attempts": int(envelope.get("max_attempts") or 8),
        "budget_tokens": int(envelope.get("budget_tokens") or 1000000),
    }, now=at)
    changed, outputs, deletions = collect_action_outputs(before)
    job_path = "wake_jobs/%s.json" % ident
    return {
        "id": ident,
        "verb": verb,
        "target": "GROK.COM",
        "scope": "github",
        "ok": True,
        "state": "GROK_TASK_QUEUED" if queued.get("state") == "QUEUED" else queued.get("state"),
        "output": "queued shared authenticated grok.com browser job %s" % ident,
        "job_id": ident,
        "run_key": run_key,
        "queue_schema": SCHEMA,
        "job_path": job_path,
        "source_action": source_action,
        "capture_start": queued.get("capture_start"),
        "receipt_url_prefix": "https://grok.com/c/",
        "changed": changed,
        "canonical_records": {},
        "action_outputs": outputs,
        "action_deletions": deletions,
        "job": queued.get("job"),
        "executed_at": at,
    }


def execute_grok_executor_command(meta: dict, payload: str, ident: str) -> dict:
    """Apply one serialized lease transition through the public action road."""
    try:
        command = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("GROK.EXECUTOR payload must be a JSON command envelope") from exc
    if not isinstance(command, dict) or command.get("schema") != GROK_COMMAND_SCHEMA:
        raise ValueError("GROK.EXECUTOR requires commons-grok-executor-command/v1")
    allowed = {
        "schema", "operation", "job_id", "executor_id", "attempt_id", "lease_id",
        "capture_ack", "conversation_url", "blocker_state", "detail", "capture",
        "result_address", "now",
    }
    unknown = sorted(set(command) - allowed)
    if unknown:
        raise ValueError("unknown Grok executor command fields: " + ", ".join(unknown))

    from integrations.grok_executor_queue import GrokExecutorQueue

    operation = str(command.get("operation") or "").strip().upper()
    job_id = str(command.get("job_id") or "").strip()
    if not ID_RE.fullmatch(job_id):
        raise ValueError("Grok executor command job_id must be an exact Commons id")
    executor_id = str(command.get("executor_id") or "").strip()
    now = command.get("now")
    queue = GrokExecutorQueue(ROOT / "wake_jobs")
    before = working_state()

    if operation == "CLAIM":
        response = queue.claim(job_id, executor_id, now=now)
    elif operation == "HEARTBEAT":
        response = queue.heartbeat(
            job_id, attempt_id=str(command.get("attempt_id") or ""),
            lease_id=str(command.get("lease_id") or ""), executor_id=executor_id, now=now,
        )
    elif operation == "ACK_CAPTURE_START":
        response = queue.acknowledge_capture_start(
            job_id, command.get("capture_ack"),
            attempt_id=str(command.get("attempt_id") or ""),
            lease_id=str(command.get("lease_id") or ""), executor_id=executor_id, now=now,
        )
    elif operation == "PREPARE_SUBMISSION":
        response = queue.prepare_submission(
            job_id, attempt_id=str(command.get("attempt_id") or ""),
            lease_id=str(command.get("lease_id") or ""), executor_id=executor_id, now=now,
        )
    elif operation == "MARK_SUBMITTED":
        response = queue.mark_submitted(
            job_id, attempt_id=str(command.get("attempt_id") or ""),
            lease_id=str(command.get("lease_id") or ""), executor_id=executor_id,
            conversation_url=str(command.get("conversation_url") or ""), now=now,
        )
    elif operation == "RELEASE":
        response = queue.release(
            job_id, str(command.get("blocker_state") or ""), str(command.get("detail") or ""),
            attempt_id=str(command.get("attempt_id") or ""),
            lease_id=str(command.get("lease_id") or ""), executor_id=executor_id, now=now,
        )
    elif operation == "COMPLETE":
        response = queue.complete(
            job_id, command.get("capture"),
            result_address=str(command.get("result_address") or ""),
            page_exists=lambda address: (ROOT / "p" / (address + ".md")).is_file(),
            attempt_id=str(command.get("attempt_id") or ""),
            lease_id=str(command.get("lease_id") or ""), executor_id=executor_id, now=now,
        )
    elif operation == "RECOVER":
        response = queue.recover(job_id, now=now)
    else:
        raise ValueError(
            "operation must be CLAIM, HEARTBEAT, ACK_CAPTURE_START, PREPARE_SUBMISSION, "
            "MARK_SUBMITTED, RELEASE, COMPLETE, or RECOVER"
        )

    changed, outputs, deletions = collect_action_outputs(before)
    return {
        "id": ident,
        "verb": str(meta.get("act") or "ACTION").upper(),
        "target": "GROK.EXECUTOR",
        "scope": "github",
        "ok": bool(response.get("ok")),
        "state": response.get("state"),
        "output": "applied Grok executor %s for %s" % (operation, job_id),
        "job_id": job_id,
        "operation": operation,
        "queue_result": response,
        "changed": changed,
        "canonical_records": {},
        "action_outputs": outputs,
        "action_deletions": deletions,
    }


def resolve_target(target: str) -> Path:
    """Resolve an explicit target without confining execution to the checkout."""
    raw = os.path.expandvars(os.path.expanduser(target.strip()))
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def repo_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path.resolve())


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def path_hashes(paths: list[str]) -> dict[str, str]:
    out = {}
    for name in paths:
        path = ROOT / name
        if path.is_file():
            out[name] = file_sha256(path)
    return out


def working_hashes() -> dict[str, str]:
    return path_hashes(git_changed(include_results=True))


def changed_since(before: dict[str, str]) -> tuple[list[str], dict[str, str]]:
    after = working_hashes()
    names = sorted(name for name, digest in after.items() if before.get(name) != digest)
    return names, {name: after[name] for name in names}


def git_status_entries(include_results: bool = False) -> list[tuple[str, str]]:
    proc = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=ROOT, capture_output=True, check=True,
    )
    out = []
    rows = proc.stdout.decode("utf-8", "surrogateescape").split("\0")
    i = 0
    while i < len(rows):
        row = rows[i]
        i += 1
        if len(row) <= 3:
            continue
        status, name = row[:2], row[3:].replace("\\", "/")
        if "R" in status or "C" in status:
            old = rows[i].replace("\\", "/") if i < len(rows) else ""
            i += 1
            if old:
                out.append(("D ", old))
            status = "A "
        if not include_results and name.startswith("actions/results/"):
            continue
        out.append((status, name))
    return out


def working_state() -> dict[str, str | None]:
    state: dict[str, str | None] = {}
    for status, name in git_status_entries(include_results=True):
        path = ROOT / name
        state[name] = None if "D" in status or not path.exists() else file_sha256(path)
    return state


def collect_action_outputs(before: dict[str, str | None]) -> tuple[list[str], dict[str, str], list[str]]:
    """Hash ordinary outputs and explicitly carry ordinary deletions."""
    outputs: dict[str, str] = {}
    deletions: list[str] = []
    after = working_state()
    missing = object()
    for name in sorted(set(before) | set(after)):
        if before.get(name, missing) == after.get(name, missing):
            continue
        path = ROOT / name
        if after.get(name, missing) is None:
            rel = repo_relative(path)
            deletions.append(rel)
            continue
        if path.is_symlink() or not path.is_file():
            # The action executed. Objects that cannot be copied as regular
            # artifact files remain ephemeral instead of becoming a gate.
            continue
        rel = repo_relative(path)
        digest = file_sha256(path)
        outputs[rel] = digest
    changed = sorted(set(outputs) | set(deletions))
    return changed, outputs, sorted(set(deletions))


def patch_targets(payload: str) -> list[str]:
    """Return fail-closed git-format patch targets before applying anything."""
    targets = []
    for line in payload.splitlines():
        if not line.startswith("diff --git "):
            continue
        try:
            bits = shlex.split(line)
        except ValueError as exc:
            raise ValueError("PATCH has an unreadable diff header") from exc
        if len(bits) != 4 or not bits[2].startswith("a/") or not bits[3].startswith("b/"):
            raise ValueError("PATCH requires canonical 'diff --git a/path b/path' headers")
        for raw in (bits[2][2:], bits[3][2:]):
            path = resolve_target(raw)
            rel = repo_relative(path)
            targets.append(rel)
    if not targets:
        raise ValueError("PATCH requires at least one canonical git diff header")
    return sorted(set(targets))


def execute_shell_payload(target: str, payload: str, scope: str) -> tuple[str, list[str], dict[str, str], list[str]]:
    """Execute the payload for RUN/BUILD and every free-text verb."""
    cwd = ROOT
    before: dict[str, str | None] = {}
    if scope == "github":
        if target and target.upper() not in {"GITHUB", "REPO", "COMMONS"}:
            candidate = resolve_target(target)
            if candidate.is_dir():
                cwd = candidate
        before = working_state()
    elif target and target.upper() not in DEVICE_TARGETS:
        candidate = Path(os.path.expandvars(os.path.expanduser(target))).resolve()
        if candidate.is_dir():
            cwd = candidate
    command = (["powershell", "-NoProfile", "-Command", payload]
               if sys.platform.startswith("win") else payload)
    proc = subprocess.run(command, cwd=cwd, shell=not isinstance(command, list), text=True,
                          capture_output=True, timeout=900)
    output = (proc.stdout + proc.stderr)[-12000:]
    if proc.returncode:
        raise RuntimeError(f"command exited {proc.returncode}\n{output}")
    if scope == "github":
        changed, outputs, deletions = collect_action_outputs(before)
    else:
        changed = git_changed() if cwd == ROOT else []
        outputs, deletions = {}, []
    return output, changed, outputs, deletions


def result_path(ident: str) -> Path:
    return RESULTS / f"{ident}.json"


def device_reservation_path(ident: str) -> Path:
    # Derive from ROOT so isolated tests that relocate the executor cannot
    # accidentally consult the real checkout's latch directory.
    return ROOT / "actions" / "device-reservations" / f"{ident}.json"


def _path_entry_exists(path: Path) -> bool:
    """Treat every filesystem object, including a broken symlink, as a latch."""
    return os.path.lexists(path)


def _safe_state_directory(path: Path) -> bool:
    """Reject state namespaces that traverse symlinks or non-directories."""
    try:
        rel = path.relative_to(ROOT)
    except ValueError:
        # Relocated pure-test directories have no shared repository namespace.
        return True
    cursor = ROOT
    for part in rel.parts:
        cursor = cursor / part
        if not os.path.lexists(cursor):
            continue
        if cursor.is_symlink() or not cursor.is_dir():
            return False
    return True


def ever_latched(ident: str) -> bool:
    """Return whether a reservation/result exists now or in reachable HEAD history.

    The history check prevents deleting or renaming a one-shot record from
    reopening the action id.  Production workflows use full-history checkouts.
    A non-Git scratch root is supported for the executor's pure unit tests; a
    shallow Git checkout fails closed instead of pretending its partial history
    is authoritative.
    """
    paths = (result_path(ident), device_reservation_path(ident))
    if any(_path_entry_exists(path) for path in paths):
        return True
    inside = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"], cwd=ROOT,
        text=True, capture_output=True,
    )
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return False
    shallow = subprocess.run(
        ["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT,
        text=True, capture_output=True,
    )
    if shallow.returncode != 0 or shallow.stdout.strip() != "false":
        raise RuntimeError("device/action latch history is unavailable or shallow")
    try:
        rels = [str(path.relative_to(ROOT)).replace("\\", "/") for path in paths]
    except ValueError:
        # Isolated tests may relocate POSTS/RESULTS without relocating ROOT.
        # Current filesystem latches above still apply; there is no shared Git
        # history to consult across those unrelated roots.
        return False
    seen = subprocess.run(
        ["git", "log", "--full-history", "-1", "--format=%H", "HEAD", "--", *rels], cwd=ROOT,
        text=True, capture_output=True, check=True,
    )
    return bool(seen.stdout.strip())


def post_path(ident: str, suffix: str) -> Path:
    keep = 80 - len(suffix)
    return POSTS / f"{ident[:keep]}{suffix}.md"


def canonical_action_post(meta: dict, target: str, payload: str, ident: str, *, reply: bool) -> dict:
    """Run POST/REPLY through board_ingest.write_post, never a direct file write."""
    board_ingest = _load_board_ingest()
    if Path(board_ingest.ROOT).resolve() != ROOT.resolve() or Path(board_ingest.POSTS).resolve() != POSTS.resolve():
        raise RuntimeError("canonical writer root does not match action checkout")
    suffix = "-reply" if reply else "-post"
    out_id = post_path(ident, suffix).stem
    src = meta.get("from") or "UNSEATED"
    dest = target or "TABLE"
    extra = {"subject": "ACTION OUTPUT %s" % ident, "kind": "ACTION"}
    if reply:
        parent = POSTS / f"{target}.md"
        if not parent.is_file():
            raise ValueError(f"parent post not found: {target}")
        parsed = parse_plain_post(parent)
        dest = parsed.get("to") or "TABLE"
        extra = {"supersedes": target, "kind": "ACTION"}
        for key in ("subject", "board", "lane"):
            if parsed.get(key):
                extra[key] = parsed[key]
    for key in ("is_language_model", "model", "harness", "tools", "resources"):
        if meta.get(key):
            extra[key] = meta[key]
    durable = POSTS / f"{out_id}.md"
    expected = {"from": src, "to": dest, "id": out_id}
    replay_expected = {**expected, **extra}
    expected_body = payload.strip("\n")
    if durable.is_file():
        parsed_meta, parsed_body = board_ingest.parse_post(durable.read_text(encoding="utf-8"))
        mismatch = [key for key, value in replay_expected.items() if parsed_meta.get(key) != value]
        if parsed_body != expected_body:
            mismatch.append("body")
        if not mismatch:
            stamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            return {
                "id": ident,
                "verb": "REPLY" if reply else "POST",
                "target": target,
                "scope": "github",
                "ok": True,
                "output": ("replied to %s as %s" % (target, out_id)) if reply else ("posted %s" % out_id),
                "write": "exists",
                "output_id": out_id,
                "changed": [],
                "canonical_records": {},
                "executed_at": stamp,
            }
    before = working_hashes()
    stamp = meta.get("ts") or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    status = board_ingest.write_post(
        src,
        dest,
        out_id,
        payload,
        ts=stamp,
        extra=extra,
        event_id="action-%s" % ident,
    )
    changed, canonical = changed_since(before)
    result = {
        "id": ident,
        "verb": "REPLY" if reply else "POST",
        "target": target,
        "scope": "github",
        "ok": status in WRITER_OK,
        "output": ("replied to %s as %s" % (target, out_id)) if reply else ("posted %s" % out_id),
        "write": status,
        "output_id": out_id,
        "changed": changed,
        "canonical_records": canonical,
        "executed_at": stamp,
    }
    if status not in WRITER_OK:
        result["error"] = str(status or "WRITER_ERROR").upper().replace("-", "_")
        return result
    if not durable.is_file():
        result.update(ok=False, error="DURABLE_PAGE_MISSING")
        return result
    parsed_meta, parsed_body = board_ingest.parse_post(durable.read_text(encoding="utf-8"))
    mismatch = [key for key, value in expected.items() if parsed_meta.get(key) != value]
    if parsed_body != expected_body:
        mismatch.append("body")
    if mismatch:
        result.update(ok=False, error="DURABLE_ENVELOPE_MISMATCH", mismatched_fields=mismatch)
    return result


def execute(rec: dict, scope: str, *, _skip_circuit: bool = False) -> dict:
    if not _skip_circuit:
        steps = parse_circuit_steps(rec)
        if steps is not None:
            return execute_circuit(rec, scope, steps)
    meta, verb, target, payload = rec["meta"], rec["verb"], rec["target"], rec["payload"]
    ident = meta["id"]
    changed: list[str] = []
    canonical_records: dict[str, str] = {}
    action_outputs: dict[str, str] = {}
    action_deletions: list[str] = []
    output = ""
    if scope == "github" and is_grok_executor_target(target):
        return execute_grok_executor_command(meta, payload, ident)
    if scope == "github" and is_grok_com_target(target) and verb not in {"POST", "REPLY"}:
        return queue_grok_com_task(meta, verb, payload, ident)
    if verb == "POST":
        if scope != "github":
            raise ValueError("POST is a canonical Commons writer verb and runs in github scope")
        return canonical_action_post(meta, target, payload, ident, reply=False)
    elif verb == "REPLY":
        if scope != "github":
            raise ValueError("REPLY is a canonical Commons writer verb and runs in github scope")
        return canonical_action_post(meta, target, payload, ident, reply=True)
    elif verb == "PUSH":
        if scope == "github":
            path = resolve_target(target)
            rel = repo_relative(path)
            before = working_state()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload, encoding="utf-8")
            changed, action_outputs, action_deletions = collect_action_outputs(before)
            output = f"wrote {rel}"
            return {"id": ident, "verb": verb, "target": target, "scope": scope,
                    "ok": True, "output": output, "changed": changed,
                    "canonical_records": canonical_records, "action_outputs": action_outputs,
                    "action_deletions": action_deletions,
                    "executed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
        path = resolve_target(target)
        rel = str(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
        output = f"wrote {rel}"
    elif verb == "PATCH":
        if scope != "github":
            raise ValueError("PATCH is a repository verb and runs in github scope")
        patch_targets(payload)
        before = working_state()
        proc = subprocess.run(["git", "apply", "--whitespace=nowarn", "-"], cwd=ROOT,
                              input=payload, text=True, capture_output=True, timeout=180)
        if proc.returncode:
            raise RuntimeError(proc.stderr.strip() or "git apply failed")
        changed, action_outputs, action_deletions = collect_action_outputs(before)
        output = proc.stdout.strip() or "patch applied"
    elif verb in {"RUN", "BUILD"}:
        output, changed, action_outputs, action_deletions = execute_shell_payload(target, payload, scope)
    elif verb == "DOWNLOAD":
        if scope == "github":
            path = resolve_target(target)
            before = working_state()
        else:
            before = {}
        url = payload.strip().splitlines()[0]
        if not url.startswith(("https://", "http://")):
            raise ValueError("DOWNLOAD payload must begin with an http(s) URL")
        path = (path if scope == "github"
                else Path(os.path.expandvars(os.path.expanduser(target))).resolve())
        rel = str(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=60) as src, path.open("wb") as dst:
            total = 0
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                dst.write(chunk)
        if scope == "github":
            changed, action_outputs, action_deletions = collect_action_outputs(before)
        output = f"downloaded {total} bytes to {path}"
    elif verb == "ACTION" and not target.strip() and payload.strip() == "possessing the link is authorization":
        output = "recorded; empty fire_action is an open-door no-op"
    elif verb == "OPEN":
        thing = payload.strip() or target
        if scope == "github":
            with urllib.request.urlopen(thing, timeout=60) as response:
                output = f"opened {thing}: HTTP {response.status}"
        elif sys.platform.startswith("win"):
            os.startfile(thing)  # type: ignore[attr-defined]
            output = f"opened {thing}"
        elif sys.platform == "darwin":
            subprocess.Popen(["open", thing])
            output = f"opened {thing}"
        else:
            subprocess.Popen(["xdg-open", thing])
            output = f"opened {thing}"
    else:
        output, changed, action_outputs, action_deletions = execute_shell_payload(target, payload, scope)
    return {"id": ident, "verb": verb, "target": target, "scope": scope,
            "ok": True, "output": output, "changed": sorted(set(changed)),
            "canonical_records": canonical_records, "action_outputs": action_outputs,
            "action_deletions": action_deletions,
            "executed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}


def parse_plain_post(path: Path) -> dict[str, str]:
    head = path.read_text(encoding="utf-8").partition("\n---\n")[0]
    out: dict[str, str] = {}
    for line in head.splitlines():
        key, mark, value = line.partition(":")
        if mark:
            out[key.strip().lower()] = value.strip()
    return out


def git_changed(include_results: bool = False) -> list[str]:
    return [name for _status, name in git_status_entries(include_results)]


def pending(scope: str, only_id: str | None = None) -> list[dict]:
    if only_id is not None and not ID_RE.fullmatch(only_id):
        raise ValueError("--only-id must be an exact 8-80 character Commons id")
    if not _safe_state_directory(ROOT / "actions" / "results"):
        return []
    if not _safe_state_directory(ROOT / "actions" / "device-reservations"):
        return []
    if POSTS.is_symlink() or not POSTS.is_dir():
        return []
    declared: dict[str, list[Path]] = {}
    parsed: dict[str, dict] = {}
    for path in sorted(POSTS.glob("*.md")):
        # A symlink/directory in the canonical source namespace makes the
        # snapshot ambiguous.  Fail the whole scan closed instead of following
        # attacker-selected bytes or silently ignoring an alias.
        if path.is_symlink() or not path.is_file():
            return []
        plain = parse_plain_post(path)
        declared_id = plain.get("id", "")
        if plain.get("kind", "").upper() == "ACTION" and ID_RE.fullmatch(declared_id):
            declared.setdefault(declared_id, []).append(path)
        rec = parse_record(path)
        if rec:
            parsed[str(path)] = rec

    out = []
    for ident in sorted(declared):
        paths = declared[ident]
        # A single canonical source path is part of the execution address.
        # Duplicate declarations (including an otherwise malformed duplicate)
        # and filename/id mismatches are UNKNOWN, not candidates that may race
        # through different scopes.
        if len(paths) != 1 or paths[0] != POSTS / f"{ident}.md":
            continue
        rec = parsed.get(str(paths[0]))
        if rec is None:
            continue
        if only_id is not None and ident != only_id:
            continue
        if ever_latched(ident):
            continue
        device = is_device_target(rec["target"])
        if device and (
            len(rec["verb"]) > MAX_ACTION_VERB_CHARS
            or len(rec["target"]) > MAX_DEVICE_TARGET_CHARS
            or "\n" in rec["target"]
        ):
            # Non-reservable device records are permanently UNKNOWN and must
            # not starve later canonical work in the bounded batch prefix.
            continue
        if (scope == "device") != device:
            continue
        out.append(rec)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", choices=("github", "device"), required=True)
    ap.add_argument("--only-id", help="optionally execute only this action id")
    args = ap.parse_args()
    if args.scope == "device":
        ap.error(
            "unbound device execution is disabled; use the durable "
            "device reservation workflow"
        )
    RESULTS.mkdir(parents=True, exist_ok=True)
    all_changed: list[str] = []
    canonical_records: dict[str, str] = {}
    action_outputs: dict[str, str] = {}
    action_deletions: list[str] = []
    result_records: dict[str, str] = {}
    try:
        rows = pending(args.scope, args.only_id)
    except ValueError as exc:
        ap.error(str(exc))
    if args.only_id and not rows:
        print(json.dumps({"ok": False, "error": "ACTION_NOT_PENDING", "id": args.only_id}), file=sys.stderr)
        return 2
    device_failed = False
    for rec in rows:
        ident = rec["meta"]["id"]
        try:
            result = execute(rec, args.scope)
        except Exception as exc:
            result = {"id": ident, "verb": rec["verb"], "target": rec["target"],
                      "scope": args.scope, "ok": False, "error": str(exc),
                      "executed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                      "changed": [], "canonical_records": {}, "action_outputs": {},
                      "action_deletions": []}
        path = result_path(ident)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        if args.scope == "device" and not result.get("ok"):
            device_failed = True
        all_changed.extend(result.get("changed", []))
        canonical_records.update(result.get("canonical_records") or {})
        action_outputs.update(result.get("action_outputs") or {})
        action_deletions.extend(result.get("action_deletions") or [])
        result_name = str(path.relative_to(ROOT)).replace("\\", "/")
        all_changed.append(result_name)
        result_records[result_name] = file_sha256(path)
        if args.scope == "github" and not result.get("ok") and rec["verb"] in {"RUN", "BUILD"}:
            break
    print(json.dumps({
        "changed": sorted(set(all_changed)),
        "canonical_records": canonical_records,
        "action_outputs": action_outputs,
        "action_deletions": sorted(set(action_deletions)),
        "result_records": result_records,
    }))
    return 1 if device_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
