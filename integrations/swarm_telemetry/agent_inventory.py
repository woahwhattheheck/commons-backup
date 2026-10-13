"""Whole native identity inventories, separate from fresh execution observations.

Reading an app catalog does not refresh its provider watermark. Source containers
such as Slack threads and GitHub repositories are never agent instances.
"""
from __future__ import annotations
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from .store import iso, now, redact

AGENT_HARNESSES = {"codex", "codex-cli", "claude-code", "gemini-cli", "chatgpt",
                   "chatgpt-work", "gpt-cloud", "grokbot", "grok", "kimi", "cursor"}
NOTE = ("These measurements are a lower bound on the swarm. Read source dates, "
        "freshness and gaps before using a count. Peers can improve this tool, "
        "its adapters and source coverage; preserve source identities and dates. "
        "Telemetry observes work and never grants access or controls execution.")

def schema(store):
    with store.connect() as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='agent_observations'").fetchone():return
    with store._write_lock, store.connect() as db:
        db.executescript("""
          CREATE TABLE IF NOT EXISTS agent_observations (
            identity TEXT NOT NULL, source_id TEXT NOT NULL, session_id TEXT NOT NULL,
            harness TEXT NOT NULL, provider TEXT, created_at TEXT, last_activity_at TEXT,
            read_at TEXT, payload TEXT NOT NULL, PRIMARY KEY(identity,source_id));
          CREATE INDEX IF NOT EXISTS agent_inventory_query
            ON agent_observations(harness,provider,identity);
        """)

def identity(harness, sid):
    # Native app context and the transcript describe the same Codex/ChatGPT seat.
    family = "codex" if harness in {"codex", "codex-cli"} else harness
    if family in {"chatgpt-work", "gpt-cloud"}: family = "chatgpt"
    return family + ":" + str(sid)

def retain_inventory(store, source_id, rows, coverage, *, raw=None):
    """Seal the full read before updating any identity projection."""
    schema(store)
    read_at = coverage["read_at"]
    body = json.dumps(raw if raw is not None else rows, ensure_ascii=False)
    digest = hashlib.sha256(body.encode()).hexdigest()
    event_id = "agent-inventory:" + source_id + ":" + digest
    store.ingest([{"event_id":event_id, "source":"agent_inventory", "source_id":source_id,
                   "observed_at":read_at, "occurred_at":coverage.get("source_watermark"),
                   "event_type":"source_read", "full_source":body,
                   "summary":"Complete identity inventory read; execution is measured separately."}])
    with store.connect() as db:
        event = db.execute("SELECT payload FROM events WHERE event_id=?", (event_id,)).fetchone()
    ref = json.loads(event[0])["source_record_ref"]
    coverage = {**coverage, "source_id":source_id, "source":"agent_inventory",
                "observed_at":read_at, "source_record_ref":ref, "records":len(rows),
                "complete":False, "corpus_complete":False}
    with store._write_lock, store.connect() as db:
        for original in rows:
            row = redact({**original, "read_at":read_at, "source_id":source_id,
                          "source_record_ref":ref, "runtime_status":"unknown"})
            sid, harness = row["session_id"], row["harness"]
            row["identity"] = identity(harness, sid)
            db.execute("INSERT OR REPLACE INTO agent_observations VALUES (?,?,?,?,?,?,?,?,?)",
                (row["identity"],source_id,sid,harness,row.get("provider"),row.get("created_at"),
                 row.get("last_activity_at"),read_at,json.dumps(row,ensure_ascii=False)))
    store.ingest([],coverage=[coverage])
    return coverage

def _read_db(path, query):
    # SQLite transaction gives a coherent live-WAL read without copying a database.
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+"?mode=ro", uri=True, timeout=10)) as db:
        db.row_factory=sqlite3.Row
        db.execute("BEGIN")
        return [dict(r) for r in db.execute(query)]

def collect_native_inventory(store, config):
    home=Path(config.get("codex_home") or Path.home()/".codex")
    results=[]
    roads=[("codex-native-db",config.get("codex_state_path") or home/"state_5.sqlite"),
           ("chatgpt-native-catalog",config.get("native_catalog_path") or home/"sqlite"/"codex-dev.db")]
    for source_id,path in roads:
        try:
            if source_id=="codex-native-db":
                raw=_read_db(path,"SELECT id,source,thread_source,model_provider,model,agent_path,agent_nickname,agent_role,created_at,updated_at,archived,rollout_path FROM threads")
                rows=[]
                for r in raw:
                    try: origin=json.loads(r["source"])
                    except (ValueError,TypeError): origin={}
                    spawn=(origin.get("subagent") or {}).get("thread_spawn") or {}
                    rows.append({"session_id":r["id"],"agent_id":r["id"],"harness":"codex",
                        "provider":r["model_provider"],"model":r.get("model"),
                        "created_at":iso(r["created_at"]),"last_activity_at":iso(r["updated_at"]),
                        "parent_session_id":spawn.get("parent_thread_id"),
                        "agent_path":r["agent_path"],"agent_nickname":r["agent_nickname"],
                        "agent_role":r["agent_role"],"archived":bool(r["archived"]),
                        "source_kind":r["thread_source"],"rollout_path":r["rollout_path"]})
                coverage={"read_at":now(),"inventory_complete":True,"cached_provider_inventory":False,
                          "scope":"All rows in the current local Codex native database, including subagents and archived history."}
            else:
                # All account bindings and the full catalog, rather than a sidebar page.
                raw=_read_db(path,"SELECT c.*,h.host_kind,s.watermark_updated_at,s.initial_build_complete,s.last_full_reconciled_at FROM local_thread_catalog c JOIN local_thread_catalog_hosts h USING(host_id) LEFT JOIN local_thread_catalog_sync_state s USING(host_id) WHERE h.host_kind='chatgpt'")
                rows=[{"session_id":r["thread_id"],"agent_id":r["thread_id"],"harness":"chatgpt",
                       "provider":"openai","account_ref":r["host_id"],"summary":r["display_title"],
                       "created_at":iso(r["source_created_at"]),"last_activity_at":iso(r["source_updated_at"]),
                       "source_recency_at":iso(r.get("source_recency_at")),
                       "conversation_origin":r.get("conversation_origin"),
                       "source_kind":r["source_kind"],"missing_candidate":bool(r["missing_candidate"]),
                       "source_async_status":r.get("chatgpt_async_status"),
                       "provider_watermark":iso(r.get("watermark_updated_at")),
                       "last_full_reconciled_at":iso(r.get("last_full_reconciled_at"))} for r in raw]
                bindings={r["host_id"]:{"account_ref":r["host_id"],
                     "provider_watermark":iso(r.get("watermark_updated_at")),
                     "last_full_reconciled_at":iso(r.get("last_full_reconciled_at")),
                     "initial_build_complete":bool(r.get("initial_build_complete"))} for r in raw}
                coverage={"read_at":now(),"inventory_complete":True,"cached_provider_inventory":True,
                          "source_watermark":max((x["provider_watermark"] for x in bindings.values() if x["provider_watermark"]),default=None),
                          "bindings":list(bindings.values()),"scope":"Every retained Chat mode GPT catalog row across all native account bindings. Provider reconciliation can lag; this is historical membership, not live execution.",
                          "unread_regions":["Provider changes after each binding watermark; deleted or inaccessible conversations outside the retained catalog."]}
            results.append(retain_inventory(store,source_id,rows,coverage,raw=raw))
        except Exception as exc:
            with store.connect() as db:
                previous=db.execute("SELECT payload FROM coverage WHERE source_id=?",(source_id,)).fetchone()
            row={**(json.loads(previous[0]) if previous else {}),
                 "source_id":source_id,"source":"agent_inventory","observed_at":now(),
                 "status":"pending_recovery","complete":False,"error":type(exc).__name__,
                 "previous_inventory_preserved":True}
            store.ingest([],coverage=[row]);results.append(row)
    native_path=config.get("native_runtime_path")
    if native_path:
        try:
            context=json.loads(Path(native_path).read_text(encoding="utf-8-sig"))
            rows=[{"session_id":r.get("session_id") or r["id"],"agent_id":r.get("agent_id") or r.get("session_id") or r["id"],
                   "harness":r["harness"],"provider":r.get("provider") or "openai",
                   "summary":r.get("task_title") or r.get("title"),"last_activity_at":iso(r.get("updatedAt")),
                   "native_source_record_ref":r.get("source_record_ref")}
                  for r in context.get("native_sessions",[]) if r.get("harness") in AGENT_HARNESSES]
            results.append(retain_inventory(store,"native-app-projection",rows,
                {"read_at":now(),"source_watermark":context.get("observed_at"),"inventory_complete":False,
                 "cached_provider_inventory":True,"native_original_source_refs":list({r["native_source_record_ref"] for r in rows if r.get("native_source_record_ref")}),
                 "scope":"Retained native API page projection, linked to the untouched original source receipt. Original API read time is preserved; reading this file is not a new provider observation."},raw=context))
        except Exception as exc:
            store.ingest([],coverage=[{"source_id":"native-app-projection","source":"agent_inventory",
                "observed_at":now(),"complete":False,"status":"pending_recovery","error":type(exc).__name__}])
    return {"sources":results,"corpus_complete":False,"peer_note":NOTE}

def _age(at, current):
    stamp=iso(at)
    return (current-datetime.fromisoformat(stamp.replace("Z","+00:00"))).total_seconds() if stamp else None
