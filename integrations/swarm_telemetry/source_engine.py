"""Resumable source readers and open native-connector response bridge."""
from __future__ import annotations
import json
import copy
import time
from datetime import datetime
from pathlib import Path
from threading import RLock
from .store import now,stable_id

READERS={"github":"github_activity","slack":"slack_activity","services":"service_activity"}
_READER_LOCKS={kind:RLock() for kind in READERS}

def _distinct_sources(rows):
    sources={}
    for row in rows or []:
        if not isinstance(row,dict): continue
        request=row.get("reader") if isinstance(row.get("reader"),dict) else {}
        identity=row.get("source_id") or stable_id(row.get("service") or row.get("source"),row.get("account_ref"),row.get("scope"),row.get("source_locator"),row.get("repository"),row.get("tool_name") or request.get("tool_name"))
        sources[identity]={**sources.get(identity,{}),**row}
    return list(sources.values())

def _coverage(value,kind):
    if isinstance(value,dict):
        rows=[{k:v for k,v in value.items() if k!="rows"}]+list(value.get("rows",[]))
    else: rows=list(value or [])
    for index,row in enumerate(rows):
        row.setdefault("source_id",stable_id(kind,row.get("service"),row.get("account_ref"),row.get("scope"),index))
        row.setdefault("source",kind)
    return rows

class SourceEngine:
    def __init__(self,store,config=None):
        self.store=store
        self.config=config or {}
    def _sources(self,kind=None):
        sources=list((self.store.state("source_discovery") or {}).get("sources",[]))
        for source_reader in READERS: sources.extend(self.store.state("source_reader_sources:"+source_reader) or [])
        sources=_distinct_sources(sources)
        if kind:
            def matches(row):
                service=str(row.get("service") or row.get("source") or "").lower()
                if kind=="services": return service not in {"github","slack"}
                return service==kind
            sources=[row for row in sources if matches(row)]
        return sources
    def run(self,kind):
        with _READER_LOCKS[kind]: return self._run(kind)
    def _run(self,kind):
        from importlib import import_module
        module=import_module("."+READERS[kind],__package__)
        fn=getattr(module,"collect_"+("service" if kind=="services" else kind)+"_activity")
        config=dict(self.config)
        discovery=self.store.state("source_discovery") or {}
        config["github_repositories"]=sorted(set(config.get("github_repositories",[])+discovery.get("github_repositories",[])))
        config.setdefault("source_catalog_path",str(Path(self.store.path).parent/"service-catalog.json"))
        state=self.store.state("source_reader:"+kind) or {}
        consumed=self.store.state("native_consumed:"+kind) or {}
        responses,metadata=self.store.native_responses()
        receipts={}
        mismatches={}
        identical_observations=0
        for job_id,ref in responses.items():
            record=metadata.get(job_id,{})
            owner=record.get("reader") or ("slack" if job_id.startswith("slack-read:") else "services")
            if owner!=kind: continue
            job=(state.get("jobs") or {}).get(job_id,{})
            fields=[]
            if record.get("response_ref",ref)!=ref: fields.append("response_ref")
            if job:
                tool,args=module._request(job) if kind=="slack" else (job.get("tool_name"),job.get("args",{}))
                expected={"tool_name":tool,"account_ref":job.get("account_ref"),"service":job.get("service") or kind}
                # Compare supplied source context before reading or consuming
                # the envelope. Older receipts may omit these annotations.
                fields.extend(key for key,value in expected.items() if key in record and value is not None and record[key]!=value)
            if fields:
                mismatches[job_id]=fields
                continue
            known=consumed.get(job_id)==ref
            raw=None if known else json.loads(self.store.custody.read(ref))
            if known or kind=="slack" and job.get("last_native_result_sha256")==module._digest(raw):
                # A committed reader checkpoint proves this exact envelope was
                # consumed even if interruption preceded the receipt-index write.
                # A later identical live-tail read is still a fresh observation.
                # Reuse its content projection, but renew the existing poll clock
                # only when the captured request is still this exact live tail.
                if (kind=="slack" and job.get("kind") in {"tail","thread_tail"}
                        and job.get("status")=="live" and not job.get("cursor")
                        and record.get("arguments")==module._request(job)[1]):
                    try:
                        captured=datetime.fromisoformat(record["observed_at"].replace("Z","+00:00")).timestamp()
                        attempted=datetime.fromisoformat(job["last_attempt_at"].replace("Z","+00:00")).timestamp()
                    except (KeyError,TypeError,ValueError,OverflowError,OSError):
                        pass
                    else:
                        if captured>attempted:
                            job["last_attempt_at"]=record["observed_at"]
                            job["next_attempt_epoch"]=max(float(job.get("next_attempt_epoch",0)),captured+float(config.get("slack_tail_seconds",30)))
                            job["attempts"]=int(job.get("attempts",0))+1
                            job["identical_response_observations"]=int(job.get("identical_response_observations",0))+1
                            identical_observations+=1
                consumed[job_id]=ref
                continue
            if "arguments" in record and job and args!=record["arguments"]:
                mismatches[job_id]=["arguments"]
                continue
            receipts[job_id]={"payload":raw,"source_ref":{"ref":ref}}
            if kind=="slack" and job: job["next_attempt_epoch"]=0
        config["native_results"]=receipts
        prior_digests={key:job.get("last_native_result_sha256") for key,job in state.get("jobs",{}).items()}
        if kind=="slack" and receipts:
            config["slack_native_receipts_only"]=True
            config["slack_page_budget"]=min(len(receipts),max(1,min(1000,int(config.get("native_receipt_page_budget",128)))))
            ready=sorted((job for job in state.get("jobs",{}).values() if not job.get("complete") and float(job.get("next_attempt_epoch",0))<=time.time()),key=lambda job:job["job_id"])
            state["round_robin"]=next((index for index,job in enumerate(ready) if job["job_id"] in receipts),state.get("round_robin",0))
        reader=config.get("read_page")
        if kind=="services" and not callable(reader) and config.get("native_connector_gateway"):
            from .runner import Gateway
            gateway=Gateway(config["native_connector_gateway"],config.get("timeout_seconds",25))
            reader=lambda name,args,account_ref:gateway.call(name,args,account_ref=account_ref)
        kwargs={"config":config,"state":state,"sources":self._sources(kind)}
        # GitHub uses its account-specific readers from config. The native
        # callback keyword belongs to the Slack and service collector APIs.
        if kind in {"slack","services"} and callable(reader): kwargs["read_page"]=reader
        result=fn(**kwargs)
        events=result.get("events",[])
        batch_size=max(1,min(1000,int(config.get("source_ingest_batch_events",128))))
        for offset in range(0,len(events),batch_size): self.store.ingest(events[offset:offset+batch_size])
        sources=_distinct_sources(result.get("sources",[]))
        rows=_coverage(result.get("coverage",[]),kind)
        all_rows=rows+_coverage(sources,kind)
        for offset in range(0,len(all_rows),batch_size): self.store.ingest([],coverage=all_rows[offset:offset+batch_size])
        accounts=result.get("accounts",[])
        for offset in range(0,len(accounts),batch_size): self.store.ingest([],accounts=accounts[offset:offset+batch_size])
        new_state=result.get("state",{})
        # Exact envelopes commit before cursors advance; interrupted batches replay safely.
        self.store.state("source_reader:"+kind,new_state)
        self.store.state("source_reader_sources:"+kind,sources)
        pending=result.get("pending_native_reads")
        if pending is None:
            pending=[]
            for job in new_state.get("jobs",{}).values():
                if job.get("complete"): continue
                item=copy.deepcopy(job)
                request=item.get("reader",{})
                item.update(tool_name=request.get("tool_name"),args=request.get("arguments",{}),reader=kind)
                pending.append(item)
        self.store.state("source_jobs:"+kind,pending)
        seen={event.get("metadata",{}).get("job_id") for event in events}
        seen.update(key for key,job in new_state.get("jobs",{}).items() if key in receipts and job.get("last_native_result_sha256")!=prior_digests.get(key))
        for job_id in seen:
            if job_id in receipts: consumed[job_id]=responses[job_id]
        self.store.state("native_consumed:"+kind,consumed)
        native_pending=len(pending)
        # GitHub retains selector coverage separately from native handoff jobs.
        # Its incomplete rows include aliases, templates and account recovery.
        health={"observed_at":now(),"events":len(events),"pending":result.get("pending_selectors",native_pending),"pending_native_jobs":native_pending,"complete":bool(rows) and not mismatches and all(row.get("complete",False) for row in rows),"full_source_retained":True,"sampling":False,"native_receipts_available":len(receipts),"native_receipts_consumed":len(consumed),"native_identical_observations":identical_observations,"native_receipt_mismatches":mismatches}
        self.store.state("source_reader_health:"+kind,health)
        return {"kind":kind,**health}
    def jobs(self,reader=None,limit=None,cursor=0):
        readers=[kind for kind in READERS if not reader or reader==kind]
        return self.store.source_job_page(readers,cursor=cursor,limit=limit)
    def record_response(self,payload):
        job_id=str(payload["job_id"])
        raw=payload["payload"]
        reader=payload.get("reader") or ("slack" if job_id.startswith("slack-read:") else "services")
        if reader not in READERS: raise ValueError("Unknown source reader")
        ref=self.store.custody.seal(raw,payload.get("source_id") or job_id)
        event={"event_id":"native-response:"+stable_id(job_id,ref["sha256"]),"source":payload.get("service","native-connector"),"source_id":payload.get("source_id") or job_id,"event_type":"native_source_response","occurred_at":payload.get("occurred_at") or now(),"observed_at":now(),"status":"captured","summary":"Complete native connector response captured","source_record_ref":ref,"metadata":{"job_id":job_id,"account_ref":payload.get("account_ref"),"tool_name":payload.get("tool_name"),"exact_response":True}}
        self.store.ingest([event])
        metadata={key:payload[key] for key in ("arguments","tool_name","account_ref","service") if key in payload}
        metadata.update(reader=reader,observed_at=now(),response_ref=ref["ref"])
        self.store.record_native_response(job_id,ref["ref"],metadata)
        return self.store.envelope(job_id=job_id,reader=reader,source_record_ref=ref,captured=True)
