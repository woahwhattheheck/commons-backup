#!/usr/bin/env python3
"""Local-first client implementation onboarding and delivery handoff workspace.

All mutation is local SQLite/CLI. The HTTP surface in server.py is read-only.
No network/provider/payment/customer-send authority exists in this module.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sqlite3
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

SCHEMA_VERSION = 1
SAFE_INT = 9_007_199_254_740_991
REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
ALLOWED_REVIEW = {"OWNER_APPROVED_LOCAL", "CUSTOMER_REVIEWED_LOCAL", "REJECTED_LOCAL"}
APPROVED_REVIEW = {"OWNER_APPROVED_LOCAL", "CUSTOMER_REVIEWED_LOCAL"}


class OnboardingError(Exception):
    pass


class ConflictError(OnboardingError):
    pass


def canonical(obj: Any) -> bytes:
    try:
        return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except UnicodeEncodeError as exc:
        raise OnboardingError("canonical JSON contains non-Unicode-scalar characters") from exc


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def strict_loads(text: str) -> Any:
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise OnboardingError(f"duplicate JSON key: {key}")
            out[key] = value
        return out
    try:
        return json.loads(text, object_pairs_hook=hook, parse_constant=lambda x: (_ for _ in ()).throw(OnboardingError(f"non-finite JSON value: {x}")))
    except OnboardingError:
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        raise OnboardingError(f"invalid JSON: {exc}") from exc


def load_json(path: str | os.PathLike[str]) -> Any:
    p = Path(path)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(p, flags)
    except OSError as exc:
        raise OnboardingError(f"input must be a readable regular non-symlink file: {p}") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise OnboardingError(f"input must be a regular file: {p}")
        if info.st_size > 2_000_000:
            raise OnboardingError("input exceeds 2 MB")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, min(131072, 2_000_001 - total))
            if not chunk:
                break
            chunks.append(chunk); total += len(chunk)
            if total > 2_000_000:
                raise OnboardingError("input exceeds 2 MB")
        data = b"".join(chunks)
    finally:
        os.close(fd)
    try:
        return strict_loads(data.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise OnboardingError("input must be UTF-8") from exc


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_utc(value: Any, field: str) -> str:
    if not isinstance(value, str) or not UTC_RE.fullmatch(value):
        raise OnboardingError(f"{field} must be canonical UTC seconds")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise OnboardingError(f"{field} invalid UTC") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise OnboardingError(f"{field} noncanonical UTC")
    return value


def validate_ref(value: Any, field: str) -> str:
    if not isinstance(value, str) or not REF_RE.fullmatch(value):
        raise OnboardingError(f"{field} must be an opaque ref")
    return value


def validate_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise OnboardingError(f"{field} must be lowercase SHA-256")
    return value


def validate_int(value: Any, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise OnboardingError(f"{field} must be integer")
    if value < minimum or value > SAFE_INT:
        raise OnboardingError(f"{field} out of range")
    return value


def validate_text(value: Any, field: str, *, max_len: int = 500, nonempty: bool = True) -> str:
    if not isinstance(value, str):
        raise OnboardingError(f"{field} must be string")
    if any(0xD800 <= ord(ch) <= 0xDFFF for ch in value):
        raise OnboardingError(f"{field} contains non-Unicode-scalar characters")
    if nonempty and not value.strip():
        raise OnboardingError(f"{field} cannot be empty")
    if len(value) > max_len or "\x00" in value:
        raise OnboardingError(f"{field} invalid length/content")
    return value


def exact_keys(obj: Any, expected: set[str], field: str) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise OnboardingError(f"{field} must be object")
    keys = set(obj)
    if keys != expected:
        raise OnboardingError(f"{field} keys mismatch: expected {sorted(expected)}, got {sorted(keys)}")
    return obj


def _list(value: Any, field: str, *, min_len: int = 0, max_len: int = 100) -> list[Any]:
    if not isinstance(value, list) or len(value) < min_len or len(value) > max_len:
        raise OnboardingError(f"{field} must be list length {min_len}..{max_len}")
    return value


def validate_scope(scope: Any) -> dict[str, Any]:
    s = exact_keys(scope, {"deliverables", "exclusions", "assumptions", "acceptanceCriteria", "requiredInputs", "milestones"}, "scope")
    out: dict[str, Any] = {}

    deliverables: list[dict[str, str]] = []
    deliverable_ids: set[str] = set()
    for i, raw in enumerate(_list(s["deliverables"], "deliverables", min_len=1, max_len=50)):
        d = exact_keys(raw, {"id", "title"}, f"deliverables[{i}]")
        did = validate_ref(d["id"], f"deliverables[{i}].id")
        if did in deliverable_ids:
            raise OnboardingError(f"duplicate deliverable id: {did}")
        deliverable_ids.add(did)
        deliverables.append({"id": did, "title": validate_text(d["title"], f"deliverables[{i}].title", max_len=200)})
    out["deliverables"] = deliverables

    exclusions = [validate_text(x, f"exclusions[{i}]", max_len=300) for i, x in enumerate(_list(s["exclusions"], "exclusions", min_len=1, max_len=50))]
    assumptions = [validate_text(x, f"assumptions[{i}]", max_len=300) for i, x in enumerate(_list(s["assumptions"], "assumptions", min_len=1, max_len=50))]
    out["exclusions"] = exclusions
    out["assumptions"] = assumptions

    criteria: list[dict[str, str]] = []
    criterion_ids: set[str] = set()
    for i, raw in enumerate(_list(s["acceptanceCriteria"], "acceptanceCriteria", min_len=1, max_len=100)):
        c = exact_keys(raw, {"id", "deliverableId", "text"}, f"acceptanceCriteria[{i}]")
        cid = validate_ref(c["id"], f"acceptanceCriteria[{i}].id")
        did = validate_ref(c["deliverableId"], f"acceptanceCriteria[{i}].deliverableId")
        if cid in criterion_ids:
            raise OnboardingError(f"duplicate criterion id: {cid}")
        if did not in deliverable_ids:
            raise OnboardingError(f"criterion {cid} references unknown deliverable {did}")
        criterion_ids.add(cid)
        criteria.append({"id": cid, "deliverableId": did, "text": validate_text(c["text"], f"acceptanceCriteria[{i}].text", max_len=300)})
    out["acceptanceCriteria"] = criteria

    inputs: list[dict[str, str]] = []
    input_ids: set[str] = set()
    for i, raw in enumerate(_list(s["requiredInputs"], "requiredInputs", min_len=1, max_len=100)):
        r = exact_keys(raw, {"id", "title", "roleRef"}, f"requiredInputs[{i}]")
        iid = validate_ref(r["id"], f"requiredInputs[{i}].id")
        if iid in input_ids:
            raise OnboardingError(f"duplicate input id: {iid}")
        input_ids.add(iid)
        inputs.append({
            "id": iid,
            "title": validate_text(r["title"], f"requiredInputs[{i}].title", max_len=200),
            "roleRef": validate_ref(r["roleRef"], f"requiredInputs[{i}].roleRef"),
        })
    out["requiredInputs"] = inputs

    milestones: list[dict[str, Any]] = []
    milestone_ids: set[str] = set()
    sequences: set[int] = set()
    raw_milestones = _list(s["milestones"], "milestones", min_len=1, max_len=50)
    for i, raw in enumerate(raw_milestones):
        m = exact_keys(raw, {"id", "title", "sequence", "dependsOn", "deliverableIds"}, f"milestones[{i}]")
        mid = validate_ref(m["id"], f"milestones[{i}].id")
        seq = validate_int(m["sequence"], f"milestones[{i}].sequence", minimum=1)
        if mid in milestone_ids or seq in sequences:
            raise OnboardingError("duplicate milestone id or sequence")
        milestone_ids.add(mid); sequences.add(seq)
        deps = [validate_ref(x, f"milestones[{i}].dependsOn") for x in _list(m["dependsOn"], f"milestones[{i}].dependsOn", max_len=20)]
        dids = [validate_ref(x, f"milestones[{i}].deliverableIds") for x in _list(m["deliverableIds"], f"milestones[{i}].deliverableIds", min_len=1, max_len=50)]
        if len(set(deps)) != len(deps) or len(set(dids)) != len(dids):
            raise OnboardingError("duplicate milestone dependency/deliverable")
        if any(x not in deliverable_ids for x in dids):
            raise OnboardingError(f"milestone {mid} references unknown deliverable")
        milestones.append({"id": mid, "title": validate_text(m["title"], f"milestones[{i}].title", max_len=200), "sequence": seq, "dependsOn": deps, "deliverableIds": dids})
    by_id = {m["id"]: m for m in milestones}
    for m in milestones:
        for dep in m["dependsOn"]:
            if dep not in by_id or by_id[dep]["sequence"] >= m["sequence"]:
                raise OnboardingError(f"milestone {m['id']} has invalid dependency {dep}")
    milestones.sort(key=lambda x: (x["sequence"], x["id"]))
    out["milestones"] = milestones
    return out


def validate_open_payload(payload: Any) -> dict[str, Any]:
    p = exact_keys(payload, {"workspaceId", "clientRef", "workRef", "acceptedAt", "scopeRevision", "acceptedScopeSha256", "currency", "referenceMinor", "scope"}, "accepted-work")
    scope = validate_scope(p["scope"])
    digest = sha256_bytes(canonical(scope))
    accepted_digest = validate_sha(p["acceptedScopeSha256"], "acceptedScopeSha256")
    if accepted_digest != digest:
        raise OnboardingError("acceptedScopeSha256 does not match canonical scope")
    currency = p["currency"]
    if not isinstance(currency, str) or not CURRENCY_RE.fullmatch(currency):
        raise OnboardingError("currency must be ISO-style uppercase 3-letter code")
    return {
        "workspaceId": validate_ref(p["workspaceId"], "workspaceId"),
        "clientRef": validate_ref(p["clientRef"], "clientRef"),
        "workRef": validate_ref(p["workRef"], "workRef"),
        "acceptedAt": validate_utc(p["acceptedAt"], "acceptedAt"),
        "scopeRevision": validate_int(p["scopeRevision"], "scopeRevision", minimum=1),
        "acceptedScopeSha256": accepted_digest,
        "currency": currency,
        "referenceMinor": validate_int(p["referenceMinor"], "referenceMinor", minimum=0),
        "scope": scope,
    }


def connect(db_path: str | os.PathLike[str]) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=10.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def connect_readonly(db_path: str | os.PathLike[str]) -> sqlite3.Connection:
    p = Path(db_path)
    if p.is_symlink() or not p.is_file():
        raise OnboardingError("read-only database must already exist as a regular non-symlink file")
    uri = f"file:{quote(str(p.absolute()), safe='/:')}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=10.0, isolation_level=None)
    except sqlite3.Error as exc:
        raise OnboardingError(f"cannot open read-only database: {exc}") from exc
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    try:
        row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    except sqlite3.Error as exc:
        conn.close()
        raise OnboardingError("database is not an initialized onboarding workspace") from exc
    if row is None or row["value"] != str(SCHEMA_VERSION):
        conn.close()
        raise OnboardingError("unsupported or missing schema version")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS workspaces(
      workspace_id TEXT PRIMARY KEY, client_ref TEXT NOT NULL, work_ref TEXT NOT NULL UNIQUE,
      accepted_scope_digest TEXT NOT NULL, accepted_at TEXT NOT NULL, scope_revision INTEGER NOT NULL,
      currency TEXT NOT NULL, reference_minor INTEGER NOT NULL, current_generation INTEGER NOT NULL,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS scope_generations(
      workspace_id TEXT NOT NULL, generation INTEGER NOT NULL, scope_json TEXT NOT NULL, scope_sha TEXT NOT NULL,
      source_kind TEXT NOT NULL, source_ref TEXT NOT NULL, created_at TEXT NOT NULL,
      PRIMARY KEY(workspace_id,generation), FOREIGN KEY(workspace_id) REFERENCES workspaces(workspace_id)
    );
    CREATE TABLE IF NOT EXISTS input_state(
      workspace_id TEXT NOT NULL, generation INTEGER NOT NULL, input_id TEXT NOT NULL,
      title TEXT NOT NULL, role_ref TEXT NOT NULL, artifact_revision INTEGER NOT NULL DEFAULT 0,
      artifact_sha TEXT, status TEXT NOT NULL, updated_at TEXT NOT NULL,
      PRIMARY KEY(workspace_id,generation,input_id)
    );
    CREATE TABLE IF NOT EXISTS milestone_state(
      workspace_id TEXT NOT NULL, generation INTEGER NOT NULL, milestone_id TEXT NOT NULL,
      sequence INTEGER NOT NULL, title TEXT NOT NULL, state TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0,
      updated_at TEXT NOT NULL, PRIMARY KEY(workspace_id,generation,milestone_id)
    );
    CREATE TABLE IF NOT EXISTS deliverable_state(
      workspace_id TEXT NOT NULL, generation INTEGER NOT NULL, milestone_id TEXT NOT NULL, deliverable_id TEXT NOT NULL,
      artifact_revision INTEGER NOT NULL DEFAULT 0, artifact_sha TEXT, review_decision TEXT NOT NULL,
      reviewed_revision INTEGER, updated_at TEXT NOT NULL,
      PRIMARY KEY(workspace_id,generation,milestone_id,deliverable_id)
    );
    CREATE TABLE IF NOT EXISTS change_requests(
      workspace_id TEXT NOT NULL, change_id TEXT NOT NULL, base_generation INTEGER NOT NULL,
      proposed_scope_json TEXT NOT NULL, proposed_scope_sha TEXT NOT NULL, status TEXT NOT NULL,
      created_at TEXT NOT NULL, decided_at TEXT,
      PRIMARY KEY(workspace_id,change_id)
    );
    CREATE TABLE IF NOT EXISTS operations(
      op_id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload_sha TEXT NOT NULL, result_json TEXT NOT NULL, created_at TEXT NOT NULL
    );
    """)
    conn.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('schema_version',?)", (str(SCHEMA_VERSION),))
    row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    if row is None or row["value"] != str(SCHEMA_VERSION):
        raise OnboardingError("unsupported schema version")


def _mutate(conn: sqlite3.Connection, op_id: str, kind: str, payload: Any, fn: Callable[[], dict[str, Any]], *, now: str | None = None) -> dict[str, Any]:
    validate_ref(op_id, "opId")
    payload_sha = sha256_bytes(canonical(payload))
    timestamp = validate_utc(now, "now") if now is not None else utc_now()
    conn.execute("BEGIN IMMEDIATE")
    try:
        existing = conn.execute("SELECT kind,payload_sha,result_json FROM operations WHERE op_id=?", (op_id,)).fetchone()
        if existing is not None:
            if existing["kind"] != kind or existing["payload_sha"] != payload_sha:
                raise ConflictError(f"operation id conflict: {op_id}")
            result = strict_loads(existing["result_json"])
            conn.execute("COMMIT")
            return result
        result = fn()
        conn.execute("INSERT INTO operations(op_id,kind,payload_sha,result_json,created_at) VALUES(?,?,?,?,?)",
                     (op_id, kind, payload_sha, canonical(result).decode("utf-8"), timestamp))
        conn.execute("COMMIT")
        return result
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


def _seed_generation(conn: sqlite3.Connection, workspace_id: str, generation: int, scope: dict[str, Any], now: str) -> None:
    for item in scope["requiredInputs"]:
        conn.execute("INSERT INTO input_state(workspace_id,generation,input_id,title,role_ref,status,updated_at) VALUES(?,?,?,?,?,'MISSING',?)",
                     (workspace_id, generation, item["id"], item["title"], item["roleRef"], now))
    deliverable_titles = {d["id"]: d["title"] for d in scope["deliverables"]}
    for m in scope["milestones"]:
        conn.execute("INSERT INTO milestone_state(workspace_id,generation,milestone_id,sequence,title,state,updated_at) VALUES(?,?,?,?,?,'WAITING',?)",
                     (workspace_id, generation, m["id"], m["sequence"], m["title"], now))
        for did in m["deliverableIds"]:
            _ = deliverable_titles[did]
            conn.execute("INSERT INTO deliverable_state(workspace_id,generation,milestone_id,deliverable_id,review_decision,updated_at) VALUES(?,?,?,?,'UNREVIEWED',?)",
                         (workspace_id, generation, m["id"], did, now))


def open_workspace(conn: sqlite3.Connection, payload: Any, op_id: str, *, now: str | None = None) -> dict[str, Any]:
    p = validate_open_payload(payload)
    timestamp = validate_utc(now, "now") if now else utc_now()
    def action() -> dict[str, Any]:
        if conn.execute("SELECT 1 FROM workspaces WHERE workspace_id=? OR work_ref=?", (p["workspaceId"], p["workRef"])).fetchone():
            raise ConflictError("workspaceId/workRef already exists")
        conn.execute("INSERT INTO workspaces VALUES(?,?,?,?,?,?,?,?,?,?)", (
            p["workspaceId"], p["clientRef"], p["workRef"], p["acceptedScopeSha256"], p["acceptedAt"], p["scopeRevision"],
            p["currency"], p["referenceMinor"], 1, timestamp))
        scope_json = canonical(p["scope"]).decode("utf-8")
        conn.execute("INSERT INTO scope_generations VALUES(?,?,?,?,?,?,?)", (p["workspaceId"], 1, scope_json, p["acceptedScopeSha256"], "ACCEPTED_WORK", p["workRef"], timestamp))
        _seed_generation(conn, p["workspaceId"], 1, p["scope"], timestamp)
        return {"workspaceId": p["workspaceId"], "generation": 1, "state": "INPUTS_REQUIRED", "acceptedScopeSha256": p["acceptedScopeSha256"]}
    return _mutate(conn, op_id, "OPEN_WORKSPACE", p, action, now=timestamp)


def _workspace(conn: sqlite3.Connection, workspace_id: str) -> sqlite3.Row:
    validate_ref(workspace_id, "workspaceId")
    row = conn.execute("SELECT * FROM workspaces WHERE workspace_id=?", (workspace_id,)).fetchone()
    if row is None:
        raise OnboardingError(f"unknown workspace: {workspace_id}")
    return row


def _scope(conn: sqlite3.Connection, workspace_id: str, generation: int | None = None) -> dict[str, Any]:
    ws = _workspace(conn, workspace_id)
    gen = ws["current_generation"] if generation is None else generation
    row = conn.execute("SELECT scope_json FROM scope_generations WHERE workspace_id=? AND generation=?", (workspace_id, gen)).fetchone()
    if row is None:
        raise OnboardingError("scope generation missing")
    return strict_loads(row["scope_json"])


def kickoff_state(conn: sqlite3.Connection, workspace_id: str) -> str:
    ws = _workspace(conn, workspace_id); gen = ws["current_generation"]
    pending = conn.execute("SELECT 1 FROM change_requests WHERE workspace_id=? AND status='PENDING_LOCAL'", (workspace_id,)).fetchone()
    if pending:
        return "ON_HOLD"
    rows = conn.execute("SELECT status FROM input_state WHERE workspace_id=? AND generation=? ORDER BY input_id", (workspace_id, gen)).fetchall()
    statuses = [r["status"] for r in rows]
    if any(s == "REJECTED_LOCAL" for s in statuses):
        return "ON_HOLD"
    if any(s == "MISSING" for s in statuses):
        return "INPUTS_REQUIRED"
    if any(s == "RECEIVED" for s in statuses):
        return "OWNER_REVIEW_REQUIRED"
    if statuses and all(s == "ACCEPTED_LOCAL" for s in statuses):
        return "READY_FOR_KICKOFF_REVIEW"
    return "ON_HOLD"


def _invalidate_delivery_for_input_change(conn: sqlite3.Connection, workspace_id: str, generation: int, timestamp: str) -> None:
    conn.execute(
        "UPDATE milestone_state SET state='WAITING',revision=revision+1,updated_at=? "
        "WHERE workspace_id=? AND generation=? AND state!='WAITING'",
        (timestamp, workspace_id, generation),
    )
    conn.execute(
        "UPDATE deliverable_state SET review_decision='UNREVIEWED',reviewed_revision=NULL,updated_at=? "
        "WHERE workspace_id=? AND generation=? AND review_decision!='UNREVIEWED'",
        (timestamp, workspace_id, generation),
    )


def receive_input(conn: sqlite3.Connection, workspace_id: str, input_id: str, artifact_sha: str, op_id: str, *, now: str | None = None) -> dict[str, Any]:
    validate_ref(input_id, "inputId"); validate_sha(artifact_sha, "artifactSha256")
    payload = {"workspaceId": workspace_id, "inputId": input_id, "artifactSha256": artifact_sha}
    timestamp = validate_utc(now, "now") if now else utc_now()
    def action() -> dict[str, Any]:
        ws = _workspace(conn, workspace_id); gen = ws["current_generation"]
        row = conn.execute("SELECT artifact_revision,artifact_sha,status FROM input_state WHERE workspace_id=? AND generation=? AND input_id=?", (workspace_id, gen, input_id)).fetchone()
        if row is None: raise OnboardingError("input not in current scope")
        if row["artifact_revision"] >= 1 and row["artifact_sha"] == artifact_sha and row["status"] == "ACCEPTED_LOCAL":
            return {"workspaceId": workspace_id, "generation": gen, "inputId": input_id, "artifactRevision": row["artifact_revision"], "artifactSha256": artifact_sha, "status": "ACCEPTED_LOCAL"}
        changed_artifact = row["artifact_revision"] >= 1 and row["artifact_sha"] != artifact_sha
        if changed_artifact:
            _invalidate_delivery_for_input_change(conn, workspace_id, gen, timestamp)
        rev = row["artifact_revision"] + 1 if row["artifact_sha"] != artifact_sha or row["artifact_revision"] == 0 else row["artifact_revision"]
        conn.execute("UPDATE input_state SET artifact_revision=?,artifact_sha=?,status='RECEIVED',updated_at=? WHERE workspace_id=? AND generation=? AND input_id=?", (rev, artifact_sha, timestamp, workspace_id, gen, input_id))
        return {"workspaceId": workspace_id, "generation": gen, "inputId": input_id, "artifactRevision": rev, "artifactSha256": artifact_sha, "status": "RECEIVED"}
    return _mutate(conn, op_id, "RECEIVE_INPUT", payload, action, now=timestamp)


def review_input(conn: sqlite3.Connection, workspace_id: str, input_id: str, decision: str, op_id: str, *, now: str | None = None) -> dict[str, Any]:
    validate_ref(input_id, "inputId")
    if decision not in {"ACCEPTED_LOCAL", "REJECTED_LOCAL"}: raise OnboardingError("invalid input review decision")
    payload = {"workspaceId": workspace_id, "inputId": input_id, "decision": decision}
    timestamp = validate_utc(now, "now") if now else utc_now()
    def action() -> dict[str, Any]:
        ws = _workspace(conn, workspace_id); gen = ws["current_generation"]
        row = conn.execute("SELECT artifact_revision,artifact_sha,status FROM input_state WHERE workspace_id=? AND generation=? AND input_id=?", (workspace_id, gen, input_id)).fetchone()
        if row is None or row["artifact_revision"] < 1 or row["artifact_sha"] is None: raise OnboardingError("input has no received artifact")
        if decision == "REJECTED_LOCAL":
            _invalidate_delivery_for_input_change(conn, workspace_id, gen, timestamp)
        conn.execute("UPDATE input_state SET status=?,updated_at=? WHERE workspace_id=? AND generation=? AND input_id=?", (decision, timestamp, workspace_id, gen, input_id))
        return {"workspaceId": workspace_id, "generation": gen, "inputId": input_id, "artifactRevision": row["artifact_revision"], "artifactSha256": row["artifact_sha"], "status": decision}
    return _mutate(conn, op_id, "REVIEW_INPUT", payload, action, now=timestamp)


def _milestone_spec(scope: dict[str, Any], milestone_id: str) -> dict[str, Any]:
    for m in scope["milestones"]:
        if m["id"] == milestone_id: return m
    raise OnboardingError("unknown milestone in current scope")


def transition_milestone(conn: sqlite3.Connection, workspace_id: str, milestone_id: str, action_name: str, op_id: str, *, now: str | None = None) -> dict[str, Any]:
    validate_ref(milestone_id, "milestoneId")
    if action_name not in {"START", "COMPLETE", "REOPEN"}: raise OnboardingError("invalid milestone action")
    payload = {"workspaceId": workspace_id, "milestoneId": milestone_id, "action": action_name}
    timestamp = validate_utc(now, "now") if now else utc_now()
    def action() -> dict[str, Any]:
        ws = _workspace(conn, workspace_id); gen = ws["current_generation"]; scope = _scope(conn, workspace_id, gen)
        spec = _milestone_spec(scope, milestone_id)
        row = conn.execute("SELECT state,revision FROM milestone_state WHERE workspace_id=? AND generation=? AND milestone_id=?", (workspace_id, gen, milestone_id)).fetchone()
        if row is None: raise OnboardingError("milestone state missing")
        state = row["state"]
        if action_name == "START":
            if kickoff_state(conn, workspace_id) != "READY_FOR_KICKOFF_REVIEW": raise OnboardingError("kickoff prerequisites not ready")
            if state not in {"WAITING", "REOPENED"}: raise OnboardingError("milestone cannot start from current state")
            for dep in spec["dependsOn"]:
                dep_row = conn.execute("SELECT state FROM milestone_state WHERE workspace_id=? AND generation=? AND milestone_id=?", (workspace_id, gen, dep)).fetchone()
                if dep_row is None or dep_row["state"] != "DONE": raise OnboardingError(f"milestone dependency not done: {dep}")
            new_state = "IN_PROGRESS"
        elif action_name == "COMPLETE":
            if state != "IN_PROGRESS": raise OnboardingError("milestone must be in progress")
            for did in spec["deliverableIds"]:
                d = conn.execute("SELECT artifact_revision,artifact_sha,review_decision,reviewed_revision FROM deliverable_state WHERE workspace_id=? AND generation=? AND milestone_id=? AND deliverable_id=?", (workspace_id, gen, milestone_id, did)).fetchone()
                if d is None or d["artifact_revision"] < 1 or d["artifact_sha"] is None or d["review_decision"] not in APPROVED_REVIEW or d["reviewed_revision"] != d["artifact_revision"]:
                    raise OnboardingError(f"deliverable not locally reviewed: {did}")
            new_state = "DONE"
        else:
            if state != "DONE": raise OnboardingError("only done milestone can reopen")
            new_state = "REOPENED"
        rev = row["revision"] + 1
        conn.execute("UPDATE milestone_state SET state=?,revision=?,updated_at=? WHERE workspace_id=? AND generation=? AND milestone_id=?", (new_state, rev, timestamp, workspace_id, gen, milestone_id))
        return {"workspaceId": workspace_id, "generation": gen, "milestoneId": milestone_id, "state": new_state, "revision": rev}
    return _mutate(conn, op_id, "MILESTONE_TRANSITION", payload, action, now=timestamp)


def record_deliverable(conn: sqlite3.Connection, workspace_id: str, milestone_id: str, deliverable_id: str, artifact_sha: str, op_id: str, *, now: str | None = None) -> dict[str, Any]:
    validate_ref(milestone_id, "milestoneId"); validate_ref(deliverable_id, "deliverableId"); validate_sha(artifact_sha, "artifactSha256")
    payload = {"workspaceId": workspace_id, "milestoneId": milestone_id, "deliverableId": deliverable_id, "artifactSha256": artifact_sha}
    timestamp = validate_utc(now, "now") if now else utc_now()
    def action() -> dict[str, Any]:
        ws = _workspace(conn, workspace_id); gen = ws["current_generation"]
        m = conn.execute("SELECT state FROM milestone_state WHERE workspace_id=? AND generation=? AND milestone_id=?", (workspace_id, gen, milestone_id)).fetchone()
        if m is None or m["state"] != "IN_PROGRESS": raise OnboardingError("deliverable artifact requires in-progress milestone")
        d = conn.execute("SELECT artifact_revision FROM deliverable_state WHERE workspace_id=? AND generation=? AND milestone_id=? AND deliverable_id=?", (workspace_id, gen, milestone_id, deliverable_id)).fetchone()
        if d is None: raise OnboardingError("deliverable not assigned to milestone/current scope")
        rev = d["artifact_revision"] + 1
        conn.execute("UPDATE deliverable_state SET artifact_revision=?,artifact_sha=?,review_decision='UNREVIEWED',reviewed_revision=NULL,updated_at=? WHERE workspace_id=? AND generation=? AND milestone_id=? AND deliverable_id=?", (rev, artifact_sha, timestamp, workspace_id, gen, milestone_id, deliverable_id))
        return {"workspaceId": workspace_id, "generation": gen, "milestoneId": milestone_id, "deliverableId": deliverable_id, "artifactRevision": rev, "artifactSha256": artifact_sha, "reviewDecision": "UNREVIEWED"}
    return _mutate(conn, op_id, "RECORD_DELIVERABLE", payload, action, now=timestamp)


def review_deliverable(conn: sqlite3.Connection, workspace_id: str, milestone_id: str, deliverable_id: str, artifact_revision: int, decision: str, op_id: str, *, now: str | None = None) -> dict[str, Any]:
    validate_ref(milestone_id, "milestoneId"); validate_ref(deliverable_id, "deliverableId"); validate_int(artifact_revision, "artifactRevision", minimum=1)
    if decision not in ALLOWED_REVIEW: raise OnboardingError("invalid deliverable review decision")
    payload = {"workspaceId": workspace_id, "milestoneId": milestone_id, "deliverableId": deliverable_id, "artifactRevision": artifact_revision, "decision": decision}
    timestamp = validate_utc(now, "now") if now else utc_now()
    def action() -> dict[str, Any]:
        ws = _workspace(conn, workspace_id); gen = ws["current_generation"]
        d = conn.execute("SELECT artifact_revision,artifact_sha FROM deliverable_state WHERE workspace_id=? AND generation=? AND milestone_id=? AND deliverable_id=?", (workspace_id, gen, milestone_id, deliverable_id)).fetchone()
        if d is None or d["artifact_sha"] is None: raise OnboardingError("no deliverable artifact")
        if d["artifact_revision"] != artifact_revision: raise ConflictError("stale deliverable review revision")
        conn.execute("UPDATE deliverable_state SET review_decision=?,reviewed_revision=?,updated_at=? WHERE workspace_id=? AND generation=? AND milestone_id=? AND deliverable_id=?", (decision, artifact_revision, timestamp, workspace_id, gen, milestone_id, deliverable_id))
        return {"workspaceId": workspace_id, "generation": gen, "milestoneId": milestone_id, "deliverableId": deliverable_id, "artifactRevision": artifact_revision, "artifactSha256": d["artifact_sha"], "reviewDecision": decision}
    return _mutate(conn, op_id, "REVIEW_DELIVERABLE", payload, action, now=timestamp)


def request_change(conn: sqlite3.Connection, workspace_id: str, change_id: str, proposed_scope: Any, op_id: str, *, now: str | None = None) -> dict[str, Any]:
    validate_ref(change_id, "changeId"); scope = validate_scope(proposed_scope)
    payload = {"workspaceId": workspace_id, "changeId": change_id, "proposedScope": scope}
    timestamp = validate_utc(now, "now") if now else utc_now()
    def action() -> dict[str, Any]:
        ws = _workspace(conn, workspace_id); gen = ws["current_generation"]
        if conn.execute("SELECT 1 FROM change_requests WHERE workspace_id=? AND status='PENDING_LOCAL'", (workspace_id,)).fetchone():
            raise ConflictError("another change request is pending")
        proposed_sha = sha256_bytes(canonical(scope))
        conn.execute("INSERT INTO change_requests(workspace_id,change_id,base_generation,proposed_scope_json,proposed_scope_sha,status,created_at) VALUES(?,?,?,?,?,'PENDING_LOCAL',?)", (workspace_id, change_id, gen, canonical(scope).decode("utf-8"), proposed_sha, timestamp))
        return {"workspaceId": workspace_id, "changeId": change_id, "baseGeneration": gen, "proposedScopeSha256": proposed_sha, "status": "PENDING_LOCAL"}
    return _mutate(conn, op_id, "REQUEST_CHANGE", payload, action, now=timestamp)


def decide_change(conn: sqlite3.Connection, workspace_id: str, change_id: str, decision: str, op_id: str, *, now: str | None = None) -> dict[str, Any]:
    validate_ref(change_id, "changeId")
    if decision not in {"APPROVED_LOCAL", "REJECTED_LOCAL"}: raise OnboardingError("invalid change decision")
    payload = {"workspaceId": workspace_id, "changeId": change_id, "decision": decision}
    timestamp = validate_utc(now, "now") if now else utc_now()
    def action() -> dict[str, Any]:
        ws = _workspace(conn, workspace_id)
        row = conn.execute("SELECT * FROM change_requests WHERE workspace_id=? AND change_id=?", (workspace_id, change_id)).fetchone()
        if row is None or row["status"] != "PENDING_LOCAL": raise OnboardingError("change request not pending")
        if row["base_generation"] != ws["current_generation"]: raise ConflictError("change request base generation is stale")
        if decision == "REJECTED_LOCAL":
            conn.execute("UPDATE change_requests SET status='REJECTED_LOCAL',decided_at=? WHERE workspace_id=? AND change_id=?", (timestamp, workspace_id, change_id))
            return {"workspaceId": workspace_id, "changeId": change_id, "status": "REJECTED_LOCAL", "generation": ws["current_generation"]}
        new_gen = ws["current_generation"] + 1
        scope = strict_loads(row["proposed_scope_json"])
        conn.execute("INSERT INTO scope_generations VALUES(?,?,?,?,?,?,?)", (workspace_id, new_gen, row["proposed_scope_json"], row["proposed_scope_sha"], "APPROVED_CHANGE_LOCAL", change_id, timestamp))
        _seed_generation(conn, workspace_id, new_gen, scope, timestamp)
        conn.execute("UPDATE workspaces SET current_generation=? WHERE workspace_id=?", (new_gen, workspace_id))
        conn.execute("UPDATE change_requests SET status='APPROVED_LOCAL',decided_at=? WHERE workspace_id=? AND change_id=?", (timestamp, workspace_id, change_id))
        return {"workspaceId": workspace_id, "changeId": change_id, "status": "APPROVED_LOCAL", "generation": new_gen, "scopeSha256": row["proposed_scope_sha"]}
    return _mutate(conn, op_id, "DECIDE_CHANGE", payload, action, now=timestamp)


def compile_packet(conn: sqlite3.Connection, workspace_id: str) -> dict[str, Any]:
    ws = _workspace(conn, workspace_id); gen = ws["current_generation"]; scope = _scope(conn, workspace_id, gen)
    sg = conn.execute("SELECT scope_sha,source_kind,source_ref FROM scope_generations WHERE workspace_id=? AND generation=?", (workspace_id, gen)).fetchone()
    inputs = [dict(r) for r in conn.execute("SELECT input_id,title,role_ref,artifact_revision,artifact_sha,status FROM input_state WHERE workspace_id=? AND generation=? ORDER BY input_id", (workspace_id, gen))]
    milestones = [dict(r) for r in conn.execute("SELECT milestone_id,sequence,title,state,revision FROM milestone_state WHERE workspace_id=? AND generation=? ORDER BY sequence,milestone_id", (workspace_id, gen))]
    deliverables = [dict(r) for r in conn.execute("SELECT milestone_id,deliverable_id,artifact_revision,artifact_sha,review_decision,reviewed_revision FROM deliverable_state WHERE workspace_id=? AND generation=? ORDER BY milestone_id,deliverable_id", (workspace_id, gen))]
    changes = [dict(r) for r in conn.execute("SELECT change_id,base_generation,proposed_scope_sha,status,created_at,decided_at FROM change_requests WHERE workspace_id=? ORDER BY created_at,change_id", (workspace_id,))]

    holds: list[str] = []
    kstate = kickoff_state(conn, workspace_id)
    if kstate != "READY_FOR_KICKOFF_REVIEW": holds.append(f"KICKOFF:{kstate}")
    if any(m["state"] != "DONE" for m in milestones): holds.append("MILESTONES_INCOMPLETE")
    latest_by_deliverable = {d["deliverable_id"]: d for d in deliverables}
    for c in scope["acceptanceCriteria"]:
        d = latest_by_deliverable.get(c["deliverableId"])
        if d is None or d["artifact_revision"] < 1 or d["review_decision"] not in APPROVED_REVIEW or d["reviewed_revision"] != d["artifact_revision"]:
            holds.append(f"CRITERION_UNSATISFIED:{c['id']}")
    if any(c["status"] == "PENDING_LOCAL" for c in changes): holds.append("CHANGE_PENDING")
    handoff_state = "READY_FOR_OWNER_HANDOFF_REVIEW" if not holds else "HOLD"

    packet = {
        "schema": "client-implementation-onboarding/v1",
        "authority": {
            "externalSend": False, "calendarMutation": False, "contractMutation": False,
            "paymentMutation": False, "providerMutation": False, "customerSystemMutation": False,
            "buyerAcceptanceInference": False, "recognizedRevenue": False,
        },
        "workspace": {
            "workspaceId": ws["workspace_id"], "clientRef": ws["client_ref"], "workRef": ws["work_ref"],
            "acceptedAt": ws["accepted_at"], "acceptedScopeSha256": ws["accepted_scope_digest"],
            "scopeRevision": ws["scope_revision"], "currency": ws["currency"], "referenceMinor": ws["reference_minor"],
            "currentGeneration": gen, "currentScopeSha256": sg["scope_sha"], "scopeSourceKind": sg["source_kind"], "scopeSourceRef": sg["source_ref"],
        },
        "kickoffState": kstate,
        "handoffState": handoff_state,
        "holds": sorted(set(holds)),
        "scope": scope,
        "inputs": inputs,
        "milestones": milestones,
        "deliverables": deliverables,
        "changes": changes,
    }
    return packet


def render_markdown(packet: dict[str, Any]) -> bytes:
    w = packet["workspace"]
    lines = [
        "# Client implementation onboarding handoff", "",
        f"- Workspace: `{w['workspaceId']}`", f"- Work: `{w['workRef']}`", f"- Current scope generation: {w['currentGeneration']}",
        f"- Current scope SHA-256: `{w['currentScopeSha256']}`", f"- Kickoff state: **{packet['kickoffState']}**", f"- Handoff state: **{packet['handoffState']}**", "",
        "## Holds", "",
    ]
    lines += [f"- {x}" for x in packet["holds"]] or ["- none"]
    lines += ["", "## Required inputs", ""]
    for r in packet["inputs"]:
        lines.append(f"- `{r['input_id']}` — {r['status']} — artifact rev {r['artifact_revision']} — `{r['artifact_sha'] or 'none'}`")
    lines += ["", "## Milestones", ""]
    for m in packet["milestones"]:
        lines.append(f"- {m['sequence']}. `{m['milestone_id']}` — **{m['state']}** (rev {m['revision']})")
    lines += ["", "## Deliverables", ""]
    for d in packet["deliverables"]:
        lines.append(f"- `{d['deliverable_id']}` / `{d['milestone_id']}` — rev {d['artifact_revision']} — {d['review_decision']} — `{d['artifact_sha'] or 'none'}`")
    lines += ["", "## Authority", "", "Owner-review support only. This workspace does not send externally, schedule meetings, sign contracts, charge/refund, mutate providers/customer systems, infer buyer acceptance, or recognize revenue.", ""]
    return ("\n".join(lines)).encode("utf-8")


def render_csv(packet: dict[str, Any]) -> bytes:
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["sequence", "milestone_id", "state", "revision", "deliverable_id", "artifact_revision", "review_decision", "artifact_sha256"])
    d_by_m: dict[str, list[dict[str, Any]]] = {}
    for d in packet["deliverables"]: d_by_m.setdefault(d["milestone_id"], []).append(d)
    for m in packet["milestones"]:
        for d in d_by_m.get(m["milestone_id"], []):
            writer.writerow([m["sequence"], m["milestone_id"], m["state"], m["revision"], d["deliverable_id"], d["artifact_revision"], d["review_decision"], d["artifact_sha"] or ""])
    return buf.getvalue().encode("utf-8")


def _open_real_dir(path: Path, *, create: bool) -> int:
    if path.exists():
        if path.is_symlink() or not path.is_dir():
            raise OnboardingError("output directory must be real directory")
    elif create:
        try:
            os.mkdir(path, 0o700)
        except FileExistsError:
            if path.is_symlink() or not path.is_dir():
                raise OnboardingError("output directory must be real directory")
        except OSError as exc:
            raise OnboardingError(f"cannot create output directory: {exc}") from exc
    else:
        if path.is_symlink() or not path.is_dir():
            raise OnboardingError("output directory must be real directory")
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        dir_fd = os.open(path, flags)
    except OSError as exc:
        raise OnboardingError(f"cannot open output directory: {exc}") from exc
    try:
        info = os.fstat(dir_fd)
        if not stat.S_ISDIR(info.st_mode):
            raise OnboardingError("output directory must be real directory")
        return dir_fd
    except Exception:
        os.close(dir_fd)
        raise


def _leaf_name(name: str) -> str:
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        raise OnboardingError(f"invalid output name: {name}")
    return name


def _exclusive_write_at(dir_fd: int, name: str, data: bytes) -> None:
    name = _leaf_name(name)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(name, flags, 0o600, dir_fd=dir_fd)
    except FileExistsError as exc:
        raise OnboardingError(f"refusing to overwrite existing output: {name}") from exc
    except OSError as exc:
        raise OnboardingError(f"cannot create output {name}: {exc}") from exc
    try:
        view = memoryview(data)
        while view:
            n = os.write(fd, view)
            if n <= 0:
                raise OnboardingError("short output write")
            view = view[n:]
        os.fsync(fd)
    finally:
        os.close(fd)


def _read_regular_at(dir_fd: int, name: str) -> bytes:
    name = _leaf_name(name)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(name, flags, dir_fd=dir_fd)
    except OSError as exc:
        raise OnboardingError(f"missing/nonregular export file: {name}") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise OnboardingError(f"missing/nonregular export file: {name}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 131072)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def export_handoff(conn: sqlite3.Connection, workspace_id: str, out_dir: str | os.PathLike[str]) -> dict[str, Any]:
    packet = compile_packet(conn, workspace_id)
    target = Path(out_dir)
    dir_fd = _open_real_dir(target, create=True)
    try:
        packet_bytes = canonical(packet) + b"\n"
        md_bytes = render_markdown(packet)
        csv_bytes = render_csv(packet)
        receipt = {
            "schema": "client-implementation-onboarding-export-receipt/v1",
            "workspaceId": workspace_id,
            "packetSha256": sha256_bytes(packet_bytes),
            "markdownSha256": sha256_bytes(md_bytes),
            "csvSha256": sha256_bytes(csv_bytes),
            "handoffState": packet["handoffState"],
            "authorityExternalSend": False,
        }
        receipt_bytes = canonical(receipt) + b"\n"
        _exclusive_write_at(dir_fd, "handoff.json", packet_bytes)
        _exclusive_write_at(dir_fd, "handoff.md", md_bytes)
        _exclusive_write_at(dir_fd, "milestones.csv", csv_bytes)
        _exclusive_write_at(dir_fd, "receipt.json", receipt_bytes)
        return receipt
    finally:
        os.close(dir_fd)


def verify_export(conn: sqlite3.Connection, workspace_id: str, out_dir: str | os.PathLike[str]) -> dict[str, Any]:
    target = Path(out_dir)
    names = ["handoff.json", "handoff.md", "milestones.csv", "receipt.json"]
    dir_fd = _open_real_dir(target, create=False)
    try:
        packet_bytes = _read_regular_at(dir_fd, names[0])
        md_bytes = _read_regular_at(dir_fd, names[1])
        csv_bytes = _read_regular_at(dir_fd, names[2])
        receipt_bytes = _read_regular_at(dir_fd, names[3])
    finally:
        os.close(dir_fd)
    receipt = strict_loads(receipt_bytes.decode("utf-8"))
    exact_keys(receipt, {"schema", "workspaceId", "packetSha256", "markdownSha256", "csvSha256", "handoffState", "authorityExternalSend"}, "receipt")
    if receipt["schema"] != "client-implementation-onboarding-export-receipt/v1" or receipt["workspaceId"] != workspace_id or receipt["authorityExternalSend"] is not False:
        raise OnboardingError("receipt identity/authority mismatch")
    for field, data in [("packetSha256", packet_bytes), ("markdownSha256", md_bytes), ("csvSha256", csv_bytes)]:
        if receipt[field] != sha256_bytes(data): raise OnboardingError(f"receipt digest mismatch: {field}")
    packet = compile_packet(conn, workspace_id)
    expected_packet = canonical(packet) + b"\n"; expected_md = render_markdown(packet); expected_csv = render_csv(packet)
    if packet_bytes != expected_packet or md_bytes != expected_md or csv_bytes != expected_csv:
        raise OnboardingError("export does not match current workspace state")
    if receipt["handoffState"] != packet["handoffState"]: raise OnboardingError("receipt handoff state mismatch")
    return {"valid": True, "workspaceId": workspace_id, "handoffState": packet["handoffState"], "packetSha256": sha256_bytes(packet_bytes)}


def list_workspaces(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT workspace_id,client_ref,work_ref,current_generation FROM workspaces ORDER BY workspace_id").fetchall()
    return [{"workspaceId": r["workspace_id"], "clientRef": r["client_ref"], "workRef": r["work_ref"], "generation": r["current_generation"], "kickoffState": kickoff_state(conn, r["workspace_id"]), "handoffState": compile_packet(conn, r["workspace_id"])["handoffState"]} for r in rows]


def _cli() -> int:
    ap = argparse.ArgumentParser(description="Client implementation onboarding workspace")
    ap.add_argument("--db", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("--input", required=True); p.add_argument("--op", required=True)
    p = sub.add_parser("status"); p.add_argument("--workspace", required=True)
    p = sub.add_parser("receive-input"); p.add_argument("--workspace", required=True); p.add_argument("--input-id", required=True); p.add_argument("--sha", required=True); p.add_argument("--op", required=True)
    p = sub.add_parser("review-input"); p.add_argument("--workspace", required=True); p.add_argument("--input-id", required=True); p.add_argument("--decision", required=True, choices=["ACCEPTED_LOCAL","REJECTED_LOCAL"]); p.add_argument("--op", required=True)
    p = sub.add_parser("milestone"); p.add_argument("--workspace", required=True); p.add_argument("--milestone-id", required=True); p.add_argument("--transition", required=True, choices=["START","COMPLETE","REOPEN"]); p.add_argument("--op", required=True)
    p = sub.add_parser("deliverable"); p.add_argument("--workspace", required=True); p.add_argument("--milestone-id", required=True); p.add_argument("--deliverable-id", required=True); p.add_argument("--sha", required=True); p.add_argument("--op", required=True)
    p = sub.add_parser("review-deliverable"); p.add_argument("--workspace", required=True); p.add_argument("--milestone-id", required=True); p.add_argument("--deliverable-id", required=True); p.add_argument("--revision", required=True, type=int); p.add_argument("--decision", required=True, choices=sorted(ALLOWED_REVIEW)); p.add_argument("--op", required=True)
    p = sub.add_parser("request-change"); p.add_argument("--workspace", required=True); p.add_argument("--change-id", required=True); p.add_argument("--scope", required=True); p.add_argument("--op", required=True)
    p = sub.add_parser("decide-change"); p.add_argument("--workspace", required=True); p.add_argument("--change-id", required=True); p.add_argument("--decision", required=True, choices=["APPROVED_LOCAL","REJECTED_LOCAL"]); p.add_argument("--op", required=True)
    p = sub.add_parser("export"); p.add_argument("--workspace", required=True); p.add_argument("--out-dir", required=True)
    p = sub.add_parser("verify"); p.add_argument("--workspace", required=True); p.add_argument("--out-dir", required=True)
    args = ap.parse_args()
    conn = connect(args.db); init_db(conn)
    try:
        if args.cmd == "init": result = open_workspace(conn, load_json(args.input), args.op)
        elif args.cmd == "status": result = compile_packet(conn, args.workspace)
        elif args.cmd == "receive-input": result = receive_input(conn, args.workspace, args.input_id, args.sha, args.op)
        elif args.cmd == "review-input": result = review_input(conn, args.workspace, args.input_id, args.decision, args.op)
        elif args.cmd == "milestone": result = transition_milestone(conn, args.workspace, args.milestone_id, args.transition, args.op)
        elif args.cmd == "deliverable": result = record_deliverable(conn, args.workspace, args.milestone_id, args.deliverable_id, args.sha, args.op)
        elif args.cmd == "review-deliverable": result = review_deliverable(conn, args.workspace, args.milestone_id, args.deliverable_id, args.revision, args.decision, args.op)
        elif args.cmd == "request-change": result = request_change(conn, args.workspace, args.change_id, load_json(args.scope), args.op)
        elif args.cmd == "decide-change": result = decide_change(conn, args.workspace, args.change_id, args.decision, args.op)
        elif args.cmd == "export": result = export_handoff(conn, args.workspace, args.out_dir)
        elif args.cmd == "verify": result = verify_export(conn, args.workspace, args.out_dir)
        else: raise OnboardingError("unknown command")
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except OnboardingError as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    except UnicodeEncodeError as exc:
        print(json.dumps({"error": "canonical JSON contains non-Unicode-scalar characters"}, sort_keys=True), file=sys.stderr)
        return 2
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(_cli())
