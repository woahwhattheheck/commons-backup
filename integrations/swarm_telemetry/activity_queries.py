"""Deduplicated outcomes with immutable event dates and explicit unknown coverage."""
from __future__ import annotations
import json
import re
from datetime import datetime
from .store import iso, now
from .agent_inventory import NOTE

PR_URL=re.compile(r"^https://([^/]+)/([^/]+)/([^/]+)/pull/(\d+)(?:[/?#]|$)")
EXPLICIT_TYPES={"build_completed","build_failed","deployment_completed","deployment_failed",
                "infrastructure_created","tool_registered","tool_created"}

def project(store,limit=4000):
    """Advance a finite metadata-only event traversal; persist its exact cursor."""
    with store._write_lock,store.connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS peer_outcomes (event_id TEXT PRIMARY KEY,occurred_at TEXT,observed_at TEXT,event_type TEXT,url TEXT)")
        prior=db.execute("SELECT payload FROM runtime_state WHERE key='peer_outcome_projection'").fetchone()
        cursor=json.loads(prior[0]).get('cursor',0) if prior else 0
        rows=list(db.execute("SELECT seq,event_id,occurred_at,observed_at,event_type,url FROM events WHERE seq>? ORDER BY seq LIMIT ?",(cursor,limit)))
        for r in rows:
            if r['event_type'] in EXPLICIT_TYPES:db.execute("INSERT OR REPLACE INTO peer_outcomes VALUES (?,?,?,?,?)",[r[k] for k in ('event_id','occurred_at','observed_at','event_type','url')])
        if rows:cursor=rows[-1]['seq']
        through=db.execute("SELECT COALESCE(MAX(seq),0) FROM events").fetchone()[0]
        state={'cursor':cursor,'through_event_cursor':through,'complete':cursor>=through,'observed_at':now(),'scope':'Explicit outcome projection over retained events; source event dates are preserved.'}
        db.execute("INSERT OR REPLACE INTO runtime_state VALUES (?,?)",('peer_outcome_projection',json.dumps(state)))
    return state

def activity(store, *, since=None,until=None):
    start,end=iso(since),iso(until)
    if since and not start or until and not end:raise ValueError("Invalid activity timestamp")
    if start and end and start>=end:raise ValueError("since must precede until")
    def inside(at):
        at=iso(at)
        if not at:return False
        value=datetime.fromisoformat(at.replace("Z","+00:00"))
        return ((not start or value>=datetime.fromisoformat(start.replace("Z","+00:00")))
                and (not end or value<datetime.fromisoformat(end.replace("Z","+00:00"))))
    prs={};explicit={};unresolved=0;explicit_indexed=False
    with store.connect() as db:
        rows=db.execute("SELECT payload FROM events WHERE source='github' AND event_type IN ('pr_merged','pr_activity','activity')")
        for record in rows:
            row=json.loads(record[0]);url=row.get("url") or "";match=PR_URL.match(url)
            if not match:continue
            # Repository plus number prevents cross-repository numeric collisions.
            canonical="https://"+"/".join(match.groups()[:3])+"/pull/"+match.group(4)
            m=row.get("metadata") or {};fact=prs.setdefault(canonical,{"url":canonical,"source_refs":[],"created_at":None,"merged_at":None,"observed_at":None})
            created=iso(m.get("provider_created_at"));merged=iso(m.get("merged_at")) or (iso(row.get("occurred_at")) if row.get("event_type")=="pr_merged" else None)
            if created:fact["created_at"]=created
            if merged:fact["merged_at"]=merged
            observed=iso(row.get("observed_at"))
            if observed and (not fact["observed_at"] or observed>fact["observed_at"]):fact["observed_at"]=observed
            ref=row.get("source_record_ref") or m.get("page_source_ref")
            if ref and ref not in fact["source_refs"]:fact["source_refs"].append(ref)
        marks=",".join("?" for _ in EXPLICIT_TYPES)
        explicit_indexed=bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='peer_outcomes'").fetchone())
        if explicit_indexed:
            for record in db.execute("SELECT * FROM peer_outcomes"):
                if inside(record["occurred_at"]):explicit[record["event_id"]]={k:record[k] for k in ("event_id","occurred_at","observed_at","event_type","url")}
    opened=[v for v in prs.values() if inside(v["created_at"])];merged=[v for v in prs.values() if inside(v["merged_at"])]
    # Missing creation clocks remain unknown rather than acquiring the read time.
    unresolved=sum(not v["created_at"] for v in prs.values())
    kinds={k:sum(v["event_type"]==k for v in explicit.values()) if explicit_indexed else None for k in sorted(EXPLICIT_TYPES)}
    from .github_metrics import observed
    return store.envelope(measured_at=now(),since=start,until=end,peer_note=NOTE,
        provider_window_aggregates=observed(store,since,until),
        counts_are_lower_bounds=True,corpus_complete=False,
        pull_requests={"opened_in_window_lower_bound":len(opened),"merged_in_window_lower_bound":len(merged),
                       "known_pr_entities":len(prs),"missing_creation_dates":unresolved,
                       "opened_source_records":opened,"merged_source_records":merged,
                       "scope":"Distinct canonical PR URLs with retained provider creation/merge dates. Current open/closed totals are not inferred from old observations."},
        explicit_outcomes={"counts":kinds,"events":list(explicit.values()),"query_index_ready":explicit_indexed,
                           "projection":store.state('peer_outcome_projection'),
                           "query_pending_reason":None if explicit_indexed else "outcome_projection_preparing",
                           "scope":"Explicit normalized outcome events only. Missing builds, infrastructure and tool observations remain coverage gaps; mentions or tool calls are not successful outcomes."})
