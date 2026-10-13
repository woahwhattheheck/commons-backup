"""Indexed peer measurements over retained identities, with serve-time freshness."""
from __future__ import annotations
import base64
import hashlib
import json
from datetime import datetime, timezone
from .store import iso, now
from .agent_inventory import AGENT_HARNESSES, NOTE, identity, schema, _age

def _runtime(store):
    census=store.state("census") or {};current=datetime.now(timezone.utc);rows=[]
    for original in census.get("peers",[]):
        row=dict(original);sid=row.get("session_id");h=row.get("harness")
        if any(r in {"gemini_get_request","grokbot_inspect","gemini_events","grokbot_events"} for r in (row.get("source_refs") or [])):continue
        # Process presence is a distinct census and cannot create another seat.
        if not sid or str(sid).startswith("process:") or h not in AGENT_HARNESSES:continue
        age=_age(row.get("observed_at"),current)
        fresh=age is not None and 0<=age<=300 and row.get("basis")=="runtime_observation"
        row["identity"]=identity(h,sid)
        row["runtime_observation"]={"observed_at":iso(row.get("observed_at")),"age_seconds":age,
            "fresh":fresh,"reported_status":row.get("status"),"status":row.get("status") if fresh else "unknown",
            "source_refs":row.get("source_refs",[])}
        rows.append(row)
    return rows,census

def _query(store,filters):
    runtime,census=_runtime(store)
    marks=",".join("?" for _ in AGENT_HARNESSES)
    # SQL groups identities before pagination; source-container sessions stay out.
    sql="""WITH raw AS (
      SELECT identity,created_at,last_activity_at,payload FROM agent_observations
      UNION ALL SELECT
        (CASE WHEN lower(harness)='codex-cli' THEN 'codex'
              WHEN lower(harness) IN ('chatgpt-work','gpt-cloud') THEN 'chatgpt'
              ELSE lower(harness) END)||':'||session_id,NULL,last_activity_at,payload
        FROM sessions WHERE lower(harness) IN ("""+marks+""")
      UNION ALL SELECT json_extract(value,'$.identity'),NULL,
        json_extract(value,'$.last_activity_at'),value FROM json_each(?)
    ), grouped AS (
      SELECT identity,MIN(created_at) created_at,MAX(last_activity_at) last_activity_at,
        json_group_array(json(payload)) observations FROM raw GROUP BY identity
    ), filtered AS (SELECT * FROM grouped WHERE 1=1 """
    args=sorted(AGENT_HARNESSES)+[json.dumps(runtime)]
    if filters.get("provider"):
        sql+=" AND EXISTS (SELECT 1 FROM json_each(observations) WHERE json_extract(value,'$.provider')=?)"
        args.append(filters["provider"])
    if filters.get("harness"):
        sql+=" AND identity LIKE ?";args.append(identity(filters["harness"],"")+"%")
    if filters.get("session_id"):
        sql+=" AND EXISTS (SELECT 1 FROM json_each(observations) WHERE json_extract(value,'$.session_id')=?)"
        args.append(filters["session_id"])
    if filters.get("q"):
        sql+=" AND observations LIKE ?";args.append("%"+str(filters["q"])+"%")
    clauses=[]
    for key in ("created_at","last_activity_at"):
        clause=[]
        if filters.get("since"):clause.append("julianday("+key+")>=julianday(?)");args.append(filters["since"])
        if filters.get("until"):clause.append("julianday("+key+")<julianday(?)");args.append(filters["until"])
        if clause:clauses.append("("+" AND ".join(clause)+")")
    if clauses:sql+=" AND ("+" OR ".join(clauses)+")"
    return sql+") ",args,census,runtime

def _filters(**values):
    for key in ("since","until"):
        if values.get(key):
            values[key]=iso(values[key])
            if not values[key]:raise ValueError("Invalid "+key+" timestamp")
    if values.get("since") and values.get("until") and values["since"]>=values["until"]:
        raise ValueError("since must precede the exclusive until timestamp")
    return values

def _coverage(store):
    with store.connect() as db:
        rows=[json.loads(r[0]) for r in db.execute("SELECT payload FROM coverage WHERE source_id IN ('codex-native-db','chatgpt-native-catalog','native-app-projection','native-app-sessions')")]
    for row in rows:
        row["read_age_seconds"]=_age(row.get("read_at"),datetime.now(timezone.utc))
        # A newly read cache retains every account's original source watermark.
        row["current_provider_inventory_verified"]=(not row.get("cached_provider_inventory",True)
            and row.get("status")!="pending_recovery" and row["read_age_seconds"] is not None
            and 0<=row["read_age_seconds"]<=300)
    return rows

def roster(store, *, provider=None,harness=None,q=None,since=None,until=None,
           cursor="",limit=100,session_id=None):
    schema(store);filters=_filters(provider=provider,harness=harness,q=q,since=since,until=until,session_id=session_id)
    fp=hashlib.sha256(json.dumps(filters,sort_keys=True).encode()).hexdigest();after=""
    if cursor:
        try:token=json.loads(base64.urlsafe_b64decode(str(cursor).encode()))
        except Exception as exc:raise ValueError("Invalid peer cursor") from exc
        if token.get("filters")!=fp:raise ValueError("Retain the same peer filters across pages")
        after=token["after"]
    sql,args,census,_=_query(store,filters);size=max(1,min(int(limit),1000))
    with store.connect() as db:
        total=db.execute(sql+"SELECT COUNT(*) FROM filtered",args).fetchone()[0]
        rows=list(db.execute(sql+"SELECT * FROM filtered WHERE identity>? ORDER BY identity LIMIT ?",args+[after,size+1]))
    more=len(rows)>size;peers=[];current=datetime.now(timezone.utc)
    for dbrow in rows[:size]:
        originals=json.loads(dbrow["observations"]);item={"identity":dbrow["identity"],"source_observations":[]}
        for row in originals:
            for k in ("session_id","agent_id","provider","model","harness","summary","parent_session_id","parent_agent_id","agent_path","agent_nickname","agent_role","archived","missing_candidate","source_kind","runtime_observation","native_source_record_ref"):
                if row.get(k) is not None:item[k]=row[k]
            item["source_observations"].append({k:row[k] for k in ("source_id","source_record_ref","read_at","provider_watermark","last_full_reconciled_at","last_activity_at","account_ref") if row.get(k) is not None})
        item["created_at"]=dbrow["created_at"];item["last_activity_at"]=dbrow["last_activity_at"]
        obs=item.get("runtime_observation") or {};item["status"]=obs.get("status","unknown")
        item["runtime_status"]=item["status"];item["reported_status"]=obs.get("reported_status")
        item["activity_age_seconds"]=_age(item["last_activity_at"],current)
        item["recently_observed"]=item["activity_age_seconds"] is not None and 0<=item["activity_age_seconds"]<=900
        peers.append(item)
    next_cursor=base64.urlsafe_b64encode(json.dumps({"filters":fp,"after":peers[-1]["identity"]}).encode()).decode() if more else None
    return store.envelope(peers=peers,returned=len(peers),total_known=total,
        next_cursor=next_cursor,has_more=more,result_complete=not more,corpus_complete=False,complete=False,
        measured_at=now(),peer_note=NOTE,counts_are_lower_bounds=True,
        scope="Distinct agent/session identities; source containers excluded. Time filters match recorded creation or last activity in [since,until). Intervening activity requires event history.",
        pagination="Continue with the same filters. New discoveries before a cursor appear on a fresh traversal.",
        inventory_coverage=_coverage(store),census_coverage=census.get("coverage",[]))

def measurements(store, *, since=None,until=None):
    schema(store);filters=_filters(since=since,until=until)
    sql,args,census,runtime=_query(store,filters)
    with store.connect() as db:
        counts={r[0]:r[1] for r in db.execute(sql+"SELECT substr(identity,1,instr(identity,':')-1),COUNT(*) FROM filtered GROUP BY 1",args)}
        usage_rows=[json.loads(r[0]) for r in db.execute("SELECT payload FROM sessions WHERE lower(harness) IN ("+",".join("?" for _ in AGENT_HARNESSES)+")",sorted(AGENT_HARNESSES))]
    usage={};usage_sessions=0;latest_usage=None
    for row in usage_rows:
        values=row.get("usage") or {}
        if values:
            usage_sessions+=1
            if row.get("last_activity_at") and (not latest_usage or row["last_activity_at"]>latest_usage):latest_usage=row["last_activity_at"]
        for key,value in values.items():
            if isinstance(value,(int,float)) and not isinstance(value,bool):usage[key]=usage.get(key,0)+value
    partitions={"provider_observations":[],"process_presence":[],"unclassified_runtime_observations":[]}
    current=datetime.now(timezone.utc)
    for row in census.get("peers",[]):
        refs=row.get("source_refs") or [];sid=str(row.get("session_id") or "")
        kind=("process_presence" if sid.startswith("process:") or (row.get("metadata") or {}).get("pid")
              else "provider_observations" if any(r in {"gemini_get_request","grokbot_inspect","gemini_events","grokbot_events"} for r in refs)
              else "unclassified_runtime_observations" if row.get("harness") not in AGENT_HARNESSES else None)
        if not kind:continue
        age=_age(row.get("observed_at"),current);fresh=age is not None and 0<=age<=300
        partitions[kind].append({**row,"age_seconds":age,"fresh":fresh,
            "reported_status":row.get("status"),"status":row.get("status") if fresh else "unknown"})
    # Current observations are independent of the historical query window.
    fresh={r["identity"]:r for r in runtime if r["runtime_observation"]["fresh"]}
    from .activity_queries import activity
    outcomes=activity(store,since=since,until=until)
    return store.envelope(measured_at=now(),peer_note=NOTE,counts_are_lower_bounds=True,
        historical={"known_agent_instances":sum(counts.values()),"by_harness":counts,"since":filters.get("since"),"until":filters.get("until"),
                    "window_basis":"Recorded creation, native update or retained transcript activity dates. This is inventory history, separate from execution."},
        current_runtime={"fresh_observed_instances":len(fresh),
            "executing_observed_lower_bound":sum(r["runtime_observation"]["status"] in {"executing","running","started"} for r in fresh.values()),
            "swarm_executing_total":None,"max_observation_age_seconds":300,
            "scope":"Fresh connected execution observations only. Missing or expired sources are unknown. Process presence is separate from agent/session identity."},
        inventory_coverage=_coverage(store),census_coverage=census.get("coverage",[]),
        activity=outcomes,
        runtime_source_partitions=partitions,
        historical_reported_usage={"metrics":usage,"sessions_with_usage":usage_sessions,"latest_retained_activity_at":latest_usage,
            "scope":"All retained incremental usage from recognized agent harnesses. This is incomplete historical accounting; the inventory time window does not filter these counters. Unreported measures are absent."},
        source_coverage_summary=store.coverage_service_summary(),
        corpus_complete=False,complete=False)
