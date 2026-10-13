"""Small provider aggregates complement full source traversal; neither replaces it."""
from __future__ import annotations
import json
import hashlib
import urllib.request
import urllib.parse
from datetime import datetime,timezone,timedelta
from pathlib import Path
from .store import iso,now
from .discovery import _existing_credential

def retain(store, *, metric,author,since,until,account_ref,actor_id,read_at,raw,headers=None):
    value=json.loads(raw);key=hashlib.sha256(json.dumps([metric,author,since,until]).encode()).hexdigest()
    source="github-metric:"+key;event="github-metric-read:"+key+":"+read_at
    store.ingest([{"event_id":event,"source":"github_provider_aggregate","source_id":source,
                  "event_type":"source_read","observed_at":read_at,"occurred_at":read_at,
                  "full_source":raw,"metadata":{"metric":metric,"author":author,
                      "since":since,"until":until,"account_ref":account_ref,"actor_id":actor_id,
                      "response_headers":headers or {}}}])
    with store.connect() as db:
        ref=json.loads(db.execute("SELECT payload FROM events WHERE event_id=?",(event,)).fetchone()[0])["source_record_ref"]
    facts=[]
    for item in value.get("items",[]):
        url=item.get("html_url") or ""
        if "/pull/" not in url:continue
        merged=iso((item.get("pull_request") or {}).get("merged_at"));created=iso(item.get("created_at"))
        facts.append({"event_id":"github-metric-fact:"+hashlib.sha256((url+str(merged)+str(created)).encode()).hexdigest(),
            "source":"github","source_id":url,"event_type":"pr_merged" if merged else "pr_activity",
            "occurred_at":merged or created,"observed_at":read_at,"url":url,"status":"merged" if merged else "observed",
            "metadata":{"provider_created_at":created,"merged_at":merged,"page_source_ref":ref,
                        "provider_metric":metric,"author":(item.get("user") or {}).get("login")}})
    if facts:store.ingest(facts)
    row={"metric":metric,"author":author,"since":since,"until":until,
         "account_ref":account_ref,"actor_id":actor_id,"source_read_at":read_at,
         "reported_value":value.get("total_count"),"provider_incomplete_results":value.get("incomplete_results"),
         "source_record_ref":ref,"scope":"Provider search aggregate for this author and creation window; full source traversal remains independent."}
    store.state(source,row);store.ingest([],coverage=[{"source_id":source,"source":"github_provider_aggregate",
        "account_ref":account_ref,"observed_at":read_at,"complete":False,"status":"observed",
        "scope":row["scope"],"provider_aggregate_complete":value.get("incomplete_results") is False}])
    return row

def collect(store,config):
    windows=list(config.get("github_metric_windows") or [])
    if not windows:return {"configured":False,"scope":"No additional aggregate windows configured; full GitHub readers remain independent."}
    policy_path=Path(config.get("github_account_routing_path") or Path.home()/".commons"/"github-account-routing.json")
    policy=json.loads(policy_path.read_text(encoding="utf-8-sig"));binding=policy["default_working"]
    ref=binding["credential_ref"];token=_existing_credential(config,ref)
    if not isinstance(token,str) or not token:raise RuntimeError("working_account_credential_unavailable")
    def read(path):
        req=urllib.request.Request("https://api.github.com"+path,headers={"Authorization":"Bearer "+token,
            "Accept":"application/vnd.github+json","User-Agent":"Commons-Telemetry/1.0"})
        with urllib.request.urlopen(req,timeout=15) as response:raw=response.read().decode();headers=dict(response.headers)
        return raw,headers,now()
    raw,_,_=read("/user");actor=json.loads(raw)
    if actor.get("id")!=binding["actor_id"]:raise RuntimeError("working_account_actor_mismatch")
    # A finite rotating read batch, independent of source backfill and swarm work.
    jobs=[{**w,"metric":metric} for w in windows for metric in ("created_prs","created_prs_now_merged")]
    position=int((store.state("github_metric_cursor") or {}).get("position",0))%len(jobs);done=[]
    for offset in range(min(4,len(jobs))):
        job=jobs[(position+offset)%len(jobs)];start=iso(job["since"]);end=iso(job["until"])
        if not start or not end or start>=end:raise ValueError("Invalid metric window")
        inclusive_end=(datetime.fromisoformat(end.replace("Z","+00:00"))-timedelta(seconds=1)).isoformat().replace("+00:00","Z")
        query="is:pr author:"+job["author"]+" created:"+start+".."+inclusive_end
        if job["metric"]=="created_prs_now_merged":query+=" is:merged"
        raw,headers,at=read("/search/issues?"+urllib.parse.urlencode({"q":query,"per_page":1}))
        done.append(retain(store,metric=job["metric"],author=job["author"],since=start,until=end,
                           account_ref=ref,actor_id=actor["id"],read_at=at,raw=raw,headers=headers))
        store.state("github_metric_cursor",{"position":(position+offset+1)%len(jobs)})
    return {"captured":len(done),"account_ref":ref,"actor_id":actor["id"],"source_reads":done}

def observed(store,since,until):
    start,end=iso(since),iso(until);current=datetime.now(timezone.utc);rows=[]
    with store.connect() as db:values=[json.loads(r[0]) for r in db.execute("SELECT payload FROM runtime_state WHERE key LIKE 'github-metric:%'")]
    for value in values:
        if start and value["since"]!=start or end and value["until"]!=end:continue
        age=(current-datetime.fromisoformat(value["source_read_at"].replace("Z","+00:00"))).total_seconds()
        fresh=0<=age<=300
        rows.append({**value,"age_seconds":age,"fresh":fresh,
                     "value":value["reported_value"] if fresh else None,
                     "counts_are_lower_bounds":True,"corpus_complete":False})
    return rows
