"""Independent source collection and notification delivery over existing roads."""
from __future__ import annotations
import hashlib
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Queue,Empty,Full
from threading import Event,Thread,RLock

from .store import now,redact,stable_id

def unwrap(value):
    for _ in range(6):
        if isinstance(value,dict) and isinstance(value.get("result"),dict): value=value["result"]
        elif isinstance(value,dict) and isinstance(value.get("structuredContent"),dict): value=value["structuredContent"]
        elif isinstance(value,dict) and isinstance(value.get("content"),list):
            texts=[v.get("text","") for v in value["content"] if v.get("type")=="text"]
            if not texts: break
            try: value=json.loads(texts[0])
            except (ValueError,TypeError): break
        else: break
    return value

def notification_delivery_state(receipt):
    """Keep unconfirmed sends recoverable without discarding native envelopes.

    A successful tool invocation alone does not establish a Slack delivery.
    The existing Slack road returns channel/ts; native connectors return the
    same message identity in message_context. Wrapper uncertainty and errors
    remain relevant even when an inner result contains a message handle.
    """
    pending=[receipt]
    seen={}
    failed=uncertain=confirmed=False
    while pending:
        value=pending.pop()
        if not isinstance(value,dict) or id(value) in seen: continue
        seen[id(value)]=value
        error=value.get("error")
        code=str(value.get("code") or (error.get("code") if isinstance(error,dict) else "") or "").lower()
        status=str(value.get("delivery_status") or value.get("status") or "").lower()
        uncertain=uncertain or (
            value.get("uncertain") is True
            or isinstance(error,dict) and error.get("uncertain") is True
            or status in {"uncertain","pending","sending","queued"}
            or code.endswith("_outcome_unknown")
            or error=="tool_effect_unknown_after_interruption"
            or isinstance(error,str) and error.lower().endswith("_outcome_unknown")
        )
        failed=failed or (
            value.get("isError") is True or value.get("ok") is False
            or value.get("success") is False or value.get("delivered") is False
            or bool(error) or status in {"failed","error","not_sent","rejected"}
        )
        context=value.get("message_context")
        if not isinstance(context,dict): context={}
        channel=context.get("channel_id") or value.get("channel")
        timestamp=context.get("message_ts") or value.get("ts")
        if isinstance(channel,str) and channel and isinstance(timestamp,str) and timestamp:
            confirmed=True
        for key in ("result","structuredContent"):
            if isinstance(value.get(key),dict): pending.append(value[key])
        content=value.get("content")
        for block in content if isinstance(content,list) else []:
            if not isinstance(block,dict) or block.get("type")!="text": continue
            try: parsed=json.loads(block.get("text",""))
            except (ValueError,TypeError): continue
            if isinstance(parsed,dict): pending.append(parsed)
    if uncertain or failed and confirmed: return "uncertain"
    if failed: return "failed"
    return "sent" if confirmed else "uncertain"

class Gateway:
    def __init__(self,url="http://127.0.0.1:8878",timeout=25):
        self.url=url.rstrip("/")
        self.timeout=timeout
    def call(self,name,arguments=None,operation_id=None,*,preserve_envelope=False,account_ref=None,service=None):
        context={}
        if account_ref is not None:
            if not isinstance(account_ref,str) or not account_ref.strip():
                raise ValueError("account_ref must be a nonempty string")
            context["account_ref"]=account_ref
            if service is not None:
                if not isinstance(service,str) or not service.strip():
                    raise ValueError("service must be a nonempty string")
                context["service"]=service
        elif service is not None:
            raise ValueError("service requires account_ref")
        op=operation_id or "telemetry-read:"+stable_id(name,arguments or {},context,now())
        body={"request_id":op,"call_id":op,"name":name,"arguments":arguments or {}}
        body.update(context)
        request=urllib.request.Request(self.url+"/v1/tools/call",data=json.dumps(body).encode(),headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(request,timeout=self.timeout) as response: value=json.load(response)
        if context:
            if value.get("isError") or value.get("error"):
                return value
            result=value.get("result",{})
            if isinstance(result,dict) and (result.get("isError") or result.get("error")):
                return value if preserve_envelope else result
            bound=result.get("source_context",{}) if isinstance(result,dict) else {}
            if (not isinstance(bound,dict) or bound.get("account_ref")!=account_ref
                    or service is not None and bound.get("service")!=service
                    or not bound.get("binding_id") or not bound.get("binding_evidence")):
                # Older/default gateways may ignore the selector. Keep that
                # complete response as error evidence, never source success.
                return {"isError":True,"code":"source_binding_unresolved",
                        "pending":True,"uncertain":False,"requested_source":context,
                        "response":value}
            # Retain both the untouched native envelope and its actual binding;
            # source readers unwrap only their traversal view.
            return value if preserve_envelope else result
        if preserve_envelope: return value
        if value.get("isError") or value.get("error"):
            return value
        return unwrap(value)

class Runner:
    def __init__(self,store,config=None):
        self.store=store
        self.config=config or {}
        self.stop_event=Event()
        self.queue=Queue(maxsize=4096)
        self.gateway=Gateway(self.config.get("gateway","http://127.0.0.1:8878"))
        self.thread=None
        self.last_provider={}
        self.errors={}
        self.dropped=0
        self.provider_threads=[]
        self.discovered_sources=[]
        self.reader_wakes={name:Event() for name in ("local","inventory","census","discovery","machine","slack","github","services")}
        self.storage_status={}
        self._storage_lock=RLock()
        self._storage_checked=0
        self._storage_reported={}
        self._pending_census_sources=[]
        self._pending_census_states={}
        self._pending_census_value=None
    def storage_ready(self,label="collection",*,refresh=False):
        with self._storage_lock:
            stamp=time.monotonic()
            if refresh or not self.storage_status or stamp-self._storage_checked>=5:
                floor=max(1024**3,int(self.config.get("collection_min_free_bytes",1024**3)))
                try:
                    free=shutil.disk_usage(Path(self.store.path).parent).free
                    status={"status":"ready" if free>=floor else "pending_storage","free_bytes":free,"required_free_bytes":floor,"observed_at":now(),"scope":"telemetry source collection only","checkpoints_preserved":True,"swarm_execution_independent":True}
                except OSError as error:
                    status={"status":"pending_storage","error":type(error).__name__,"required_free_bytes":floor,"observed_at":now(),"scope":"telemetry source collection only","checkpoints_preserved":True,"swarm_execution_independent":True}
                self.storage_status=status
                self._storage_checked=stamp
            status=dict(self.storage_status)
            last=self._storage_reported.get(label,{})
            if last.get("status")!=status["status"] or stamp-last.get("at",0)>=60:
                self._storage_reported[label]={"status":status["status"],"at":stamp}
                try:
                    self.store.state("storage_guard",status)
                    if status["status"]!="ready":
                        health=self.store.state("source_reader_health:"+label) or {}
                        self.store.state("source_reader_health:"+label,{**health,"status":"pending_storage","storage_observed_at":status["observed_at"],"required_free_bytes":status["required_free_bytes"],"checkpoints_preserved":True})
                except Exception as error: self.errors["storage-status"]=type(error).__name__
            return status["status"]=="ready"
    def storage_wait(self,label):
        return {"kind":label,"status":"pending_storage","checkpoints_preserved":True,"new_source_reads":0}
    def request_collection(self,kind):
        wake=self.reader_wakes.get(kind)
        if wake: wake.set()
        return bool(wake)
    def ingest_batch(self,events,**parts):
        batch_size=max(1,min(1000,int(self.config.get("source_ingest_batch_events",128))))
        results=[]
        for offset in range(0,len(events),batch_size):
            results.append(self.store.ingest(events[offset:offset+batch_size]))
        results.append(self.store.ingest([],**parts))
        return {"inserted":sum(result.get("inserted",0) for result in results),"events":len(events),"batches":len(results)}
    def offer(self,events,**parts):
        try: self.queue.put_nowait((events,parts)); return len(events)
        except Full: self.dropped+=len(events); return 0
    def collect_local(self):
        if not self.storage_ready("local"): return self.storage_wait("local")
        from .collectors import collect_transcripts
        roots=self.config.get("transcript_roots",[])
        if not roots: return {"inserted":0}
        result=collect_transcripts(
            roots,
            self.store.checkpoints(),
            self.config.get("transcript_batch_files",8),
            max_bytes_per_batch=self.config.get("transcript_batch_bytes",1024*1024),
            max_records_per_batch=self.config.get("transcript_batch_records",256),
        )
        coverage=result.get("coverage",[])
        if isinstance(coverage,dict): coverage=[coverage]
        for row in coverage:
            row.setdefault("source_id","transcripts")
            row.setdefault("source","machine-transcripts")
            row.setdefault("status","live" if row.get("complete") else "backfilling")
            row.setdefault("observed_at",now())
            row.setdefault("records",len(result.get("events",[])))
        return self.ingest_batch(result.get("events",[]),coverage=coverage,checkpoints=result.get("checkpoints",{}))
    def collect_census(self):
        from .census import collect_census,CensusCustodyPending,CensusStoragePending
        # Already returned originals are retried verbatim before any new read.
        for event in list(self._pending_census_sources):
            try: self.store.ingest([event])
            except Exception as error: raise CensusCustodyPending("retained_census_original") from error
            self._pending_census_sources.remove(event)
        if not self.storage_ready("census",refresh=True): return self.storage_wait("census")
        for tool,state in list(self._pending_census_states.items()):
            if not self.storage_ready("census",refresh=True): return self.storage_wait("census")
            self.store.ingest([],checkpoints={"census-events:"+tool:state})
            self._pending_census_states.pop(tool,None)
        if self._pending_census_value is not None:
            value=self._pending_census_value
            self.store.state("census",value)
            self.store.ingest([],coverage=value.get("coverage",[]))
            self._pending_census_value=None
        config={**self.config,"gateway_url":self.config.get("gateway","http://127.0.0.1:8878")}
        path=self.config.get("native_runtime_path")
        if path:
            try: config.update(json.loads(Path(path).read_text(encoding="utf-8-sig")))
            except (OSError,ValueError): pass
        saved=self.store.checkpoints()
        previous=self.store.state("census") or {}
        config["provider_event_state"]={tool:saved.get("census-events:"+tool,{}) for tool in ("gemini_events","grokbot_events")}
        config["source_read_allowed"]=lambda:self.storage_ready("census",refresh=True)
        def record_source(tool,args,raw,read_at,read_id,http_status):
            event={"event_id":"census-source:"+read_id,"source":tool,"source_id":"census:"+tool,
                   "event_type":"census_source_response","occurred_at":read_at,"observed_at":read_at,
                   "full_source":raw,"metadata":{"tool_name":tool,"arguments":dict(args),"read_id":read_id,
                   "http_status":http_status,"complete_response":True,
                   "response_representation":"http_body" if http_status is not None else "returned_tool_object"}}
            self._pending_census_sources.append(event)
            try: self.store.ingest([event])
            except Exception as error: raise CensusCustodyPending("retained_census_original") from error
            self._pending_census_sources.remove(event)
            return "source:"+hashlib.sha256(raw.encode("utf-8")).hexdigest()
        def persist_provider_state(tool,state):
            value=json.loads(json.dumps(state))
            self._pending_census_states[tool]=value
            if not self.storage_ready("census",refresh=True):
                raise CensusStoragePending("census_checkpoint_pending_storage")
            self.store.ingest([],checkpoints={"census-events:"+tool:value})
            self._pending_census_states.pop(tool,None)
        config["source_recorder"]=record_source
        config["persist_provider_state"]=persist_provider_state
        value=collect_census(config,state=previous.get("state"))
        self._pending_census_value=value
        if not self.storage_ready("census",refresh=True): return self.storage_wait("census")
        self.store.state("census",value)
        self.store.ingest([],coverage=value.get("coverage",[]))
        self._pending_census_value=None
        return value.get("counts",{})
    def collect_discovery(self):
        if not self.storage_ready("discovery"): return self.storage_wait("discovery")
        from .discovery import discover_sources
        config={**self.config,"service_catalog_path":self.config.get("service_catalog_path",str(Path(self.store.path).parent/"service-catalog.json"))}
        previous=self.store.state("source_discovery") or {}
        result=discover_sources(config,state=previous.get("state",{}))
        self.discovered_sources=result.get("sources",[])
        for key in ("slack_channels","github_repositories"):
            self.config[key]=sorted(set(self.config.get(key,[])+result.get(key,[])))
        self.store.state("source_discovery",result)
        coverage=result.get("coverage",[])
        if isinstance(coverage,dict): coverage=[coverage]
        self.store.ingest([],coverage=coverage+self.discovered_sources,accounts=result.get("accounts",[]))
        return {"sources":len(self.discovered_sources),"channels":len(self.config.get("slack_channels",[])),"repositories":len(self.config.get("github_repositories",[]))}
    def collect_machine(self):
        if not self.storage_ready("machine"): return self.storage_wait("machine")
        from .machine_activity import collect_machine_activity
        result=collect_machine_activity(self.config,checkpoints=self.store.checkpoints())
        coverage=result.get("coverage",[])
        if isinstance(coverage,dict): coverage=[coverage]
        return self.ingest_batch(result.get("events",[]),coverage=coverage,checkpoints=result.get("checkpoints",{}))
    def collect_extended(self,kind):
        if not self.storage_ready(kind): return self.storage_wait(kind)
        from .source_engine import SourceEngine
        return SourceEngine(self.store,self.config).run(kind)
    def _collect_source(self,source,reader):
        attempt=None
        try:
            attempt=self.store.collection_attempt(source)
        except Exception as exc:
            self.errors["diagnostic:"+source]=type(exc).__name__
        result=reader()
        outcome=result.get("local",result) if source=="local" and isinstance(result,dict) else result
        if isinstance(outcome,dict) and (outcome.get("status") in {"pending_storage","pending_recovery","busy"}
                                        or outcome.get("error") or outcome.get("busy") is True):
            return result
        if attempt is not None and (attempt["diagnostic"] is not None or source in self.errors):
            try:
                recovery=self.store.retire_collection_error(attempt)
                if not recovery["pending"]:
                    self.errors.pop(source,None)
            except Exception as exc:
                # Recovery bookkeeping cannot turn a completed read into failure.
                self.errors["diagnostic:"+source]=type(exc).__name__
        return result
    def _source_error(self,source,exc):
        self.errors[source]=type(exc).__name__
        try:
            self.store.ingest([],coverage=[{"source_id":source,"source":source.split(":")[0],"status":"pending_recovery","observed_at":now(),"complete":False,"error":type(exc).__name__,"collection_only":True}])
            self.store.state("source_reader_health:"+source,{"observed_at":now(),"error":type(exc).__name__,"complete":False,"retrying":True})
        except Exception as storage_error:
            # A failed diagnostic write cannot terminate a source worker.
            self.errors["diagnostic:"+source]=type(storage_error).__name__
    def collect_slack(self):
        if not self.storage_ready("slack"): return self.storage_wait("slack")
        from .collectors import normalize_slack
        checkpoints=self.store.checkpoints()
        result=[]
        channels=self.config.get("slack_channels",[])
        for channel in channels:
            sid="slack:"+channel
            checkpoint=checkpoints.get(sid,{})
            args={"channel_id":channel,"limit":100}
            if checkpoint.get("cursor"): args["cursor"]=checkpoint["cursor"]
            elif checkpoint.get("high_water"):
                args["oldest"]=str(max(0,float(checkpoint["high_water"])-300))
            try:
                payload=self.gateway.call("slack_read_channel",args)
                if payload.get("isError") or payload.get("error"):
                    self._source_error(sid,RuntimeError("connector_unavailable")); continue
                payload={**payload,"channel_id":channel}
                page_ref=self.store.custody.seal(payload,sid+":page:"+str(args.get("cursor",args.get("oldest","origin"))))
                events=normalize_slack(payload)
                for event in events: event.setdefault("metadata",{})["page_source_ref"]=page_ref
                native=payload.get("messages",[])
                cursor=(payload.get("response_metadata") or {}).get("next_cursor") or payload.get("next_cursor")
                timestamps=[str(v.get("ts")) for v in native if isinstance(v,dict) and v.get("ts")]
                high_water=max(timestamps,key=float) if timestamps else checkpoint.get("high_water")
                self.store.ingest(events,coverage=[{"source_id":sid,"source":"slack","scope":channel,"status":"live","observed_at":now(),"records":len(events),"complete":not bool(cursor),"cursor":cursor,"historical_complete":checkpoint.get("historical_complete",False) or not bool(cursor)}],checkpoints={sid:{"cursor":cursor,"high_water":high_water,"historical_complete":checkpoint.get("historical_complete",False) or not bool(cursor)}})
                # Thread pages are independent source partitions, including old roots with new replies.
                for message in native if isinstance(native,list) else []:
                    if not isinstance(message,dict) or not message.get("reply_count"): continue
                    ts=str(message.get("thread_ts") or message.get("ts"))
                    thread_id=sid+":"+ts
                    tc=checkpoints.get(thread_id,{})
                    thread_args={"channel_id":channel,"thread_ts":ts,"limit":100}
                    if tc.get("cursor"): thread_args["cursor"]=tc["cursor"]
                    try:
                        thread=self.gateway.call("slack_read_thread",thread_args)
                        thread={**thread,"channel_id":channel}
                        thread_ref=self.store.custody.seal(thread,thread_id+":page:"+str(thread_args.get("cursor","origin")))
                        te=normalize_slack(thread)
                        for event in te: event.setdefault("metadata",{})["page_source_ref"]=thread_ref
                        next_cursor=(thread.get("response_metadata") or {}).get("next_cursor") or thread.get("next_cursor")
                        self.store.ingest(te,coverage=[{"source_id":thread_id,"source":"slack","scope":channel+"/"+ts,"status":"live","observed_at":now(),"records":len(te),"complete":not bool(next_cursor),"cursor":next_cursor}],checkpoints={thread_id:{"cursor":next_cursor}})
                    except Exception as exc: self._source_error(thread_id,exc)
                result.append({"source":sid,"records":len(events)})
            except Exception as exc: self._source_error(sid,exc)
        return result
    def collect_github(self):
        if not self.storage_ready("github"): return self.storage_wait("github")
        from .collectors import normalize_github
        results=[]
        for repo in self.config.get("github_repositories",[]):
            sid="github:"+repo
            checkpoint=self.store.checkpoints().get(sid,{})
            page=int(checkpoint.get("page",1))
            command=[self.config.get("gh","gh"),"api",f"repos/{repo}/issues?state=all&sort=updated&direction=desc&per_page=100&page={page}"]
            try:
                completed=subprocess.run(command,capture_output=True,text=True,timeout=30,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
                if completed.returncode:
                    raise RuntimeError("github_connector_read_failed")
                data=json.loads(completed.stdout)
                page_ref=self.store.custody.seal(completed.stdout,sid+":issues:"+str(page))
                events=normalize_github({"items":data,"repository":repo},repo=repo)
                for event in events: event.setdefault("metadata",{})["page_source_ref"]=page_ref
                more=len(data)==100
                self.store.ingest(events,coverage=[{"source_id":sid,"source":"github","scope":repo,"status":"live","observed_at":now(),"records":len(events),"complete":not more,"historical_complete":checkpoint.get("historical_complete",False) or not more,"page":page}],checkpoints={sid:{"page":page+1 if more else 1,"historical_complete":checkpoint.get("historical_complete",False) or not more}})
                results.append({"source":sid,"records":len(events)})
            except Exception as exc: self._source_error(sid,exc)
        return results
    def collect_inventory(self):
        if not self.storage_ready("inventory"): return self.storage_wait("inventory")
        from .account_inventory import collect_account_inventory
        paths=self.config.get("inventory_paths",[])
        payloads=[]
        for path in paths:
            try:
                value=json.loads(Path(path).read_text(encoding="utf-8-sig"))
                payloads.append({"source":str(path),"data":value})
            except Exception as exc: self._source_error("inventory:"+Path(path).name,exc)
        try:
            if not self.storage_ready("inventory"): return self.storage_wait("inventory")
            refs=self.gateway.call("credential_references",{})
            if not refs.get("isError") and not refs.get("error"):
                payloads.append({"source":"shared-secure-reference-metadata","data":refs})
                self.errors.pop("inventory:credential_references",None)
                observed=now()
                self.store.ingest([],coverage=[{"source_id":"inventory:credential_references","source":"inventory","status":"observed","observed_at":observed,"complete":True,"records":len(refs.get("references",[])),"scope":"all returned shared secure credential reference metadata","same_references_for_every_peer":bool(refs.get("same_references_for_every_peer"))}])
                self.store.state("source_reader_health:inventory:credential_references",{"status":"observed","observed_at":observed,"records":len(refs.get("references",[])),"complete":True})
        except Exception as exc: self._source_error("inventory:credential_references",exc)
        result=collect_account_inventory(payloads)
        if isinstance(result,list): accounts=result; coverage=[]
        else: accounts=result.get("accounts",result.get("records",[])); coverage=result.get("coverage",[])
        if isinstance(coverage,dict): coverage=[coverage]
        return self.store.ingest([],accounts=accounts,coverage=coverage)
    def collect_once(self,providers=True):
        try:
            local=self._collect_source("local",self.collect_local)
        except Exception as exc:
            self._source_error("local",exc)
            local={"status":"pending_recovery","error":type(exc).__name__}
        provider_results={}
        if providers:
            try:
                provider_results["discovery"]=self._collect_source("discovery",self.collect_discovery)
            except Exception as exc: self._source_error("discovery",exc)
            with ThreadPoolExecutor(max_workers=3,thread_name_prefix="measurement-source") as pool:
                futures={name:pool.submit(self._collect_source,name,fn) for name,fn in (("slack",lambda:self.collect_extended("slack")),("github",lambda:self.collect_extended("github")),("services",lambda:self.collect_extended("services")),("inventory",self.collect_inventory),("census",self.collect_census),("machine",self.collect_machine))}
                for name,future in futures.items():
                    try:
                        provider_results[name]=future.result()
                    except Exception as exc: self._source_error(name,exc)
        state={"mode":"passive","observed_at":now(),"local":local,"providers":provider_results,"errors":self.errors,"dropped_observations":self.dropped,"jev_required":False}
        self.store.state("collector",state)
        return state
    def dispatch_notifications(self):
        channel=self.config.get("notification_channel")
        if not channel: return {"sent":0,"enabled":False,"scanned":0,"pages":0}
        from datetime import datetime,timezone,timedelta
        max_age=float(self.config.get("notification_max_age_seconds",3600))
        cutoff=(datetime.now(timezone.utc)-timedelta(seconds=max_age)).isoformat()
        sent=scanned=pages=0
        cursor=""
        while True:
            page=self.store.records("notifications",limit=1000,cursor=cursor,delivery_state="available",since=cutoff)
            pages+=1
            for note in page["notifications"]:
                scanned+=1
                if note.get("delivery_state")!="available" or note.get("status")=="resolved": continue
                # Backfill remains available in the feed, without replaying old notices to Slack.
                occurred=note.get("occurred_at")
                if not isinstance(occurred,str) or not occurred: continue
                try:
                    age=(datetime.now(timezone.utc)-datetime.fromisoformat(occurred.replace("Z","+00:00"))).total_seconds()
                    if age>max_age: continue
                except (ValueError,TypeError,KeyError): continue
                audience=note.get("audience")
                if note.get("owner_attention") or isinstance(audience,dict) and audience.get("owner_attention"): continue
                text=note.get("title","Swarm update")+"\n"+note.get("body","")
                refs=note.get("source_refs",[])
                urls=[v.get("url") if isinstance(v,dict) else v for v in refs]
                text+="".join("\n"+v for v in urls if isinstance(v,str) and v.startswith("https://"))
                operation_id="telemetry-notice:"+note["notification_id"]
                self.store.delivery_receipt(note["notification_id"],"pending",{"operation_id":operation_id})
                try:
                    receipt=self.gateway.call("slack_post_message",{"channel_id":channel,"text":text},operation_id,preserve_envelope=True)
                    state=notification_delivery_state(receipt)
                    self.store.delivery_receipt(note["notification_id"],state,receipt)
                    sent+=state=="sent"
                except Exception as exc:
                    self.store.delivery_receipt(note["notification_id"],"uncertain",{"operation_id":operation_id,"error":type(exc).__name__})
            if not page.get("has_more"): break
            next_cursor=page.get("next_cursor")
            if not isinstance(next_cursor,str) or next_cursor<=cursor:
                raise RuntimeError("Notification continuation cursor did not advance")
            cursor=next_cursor
        return {"sent":sent,"enabled":True,"scanned":scanned,"pages":pages}
    def start(self):
        self.thread=Thread(target=self.run,daemon=True,name="passive-swarm-measurement")
        self.thread.start()
        for name,fn in (("local",lambda:self.collect_once(providers=False)),("inventory",self.collect_inventory),("census",self.collect_census),("discovery",self.collect_discovery),("machine",self.collect_machine),("slack",lambda:self.collect_extended("slack")),("github",lambda:self.collect_extended("github")),("services",lambda:self.collect_extended("services"))):
            def loop(reader=fn,label=name):
                while not self.stop_event.is_set():
                    self.reader_wakes[label].clear()
                    try:
                        result=reader() if label=="local" else self._collect_source(label,reader)
                        self.last_provider[label]={"observed_at":now(),"result":result}
                        if label=="slack": self.dispatch_notifications()
                    except Exception as exc: self._source_error(label,exc)
                    interval=15 if label=="census" else float(self.config.get("local_refresh_seconds",5)) if label=="local" else float(self.config.get("provider_refresh_seconds",120))
                    self.reader_wakes[label].wait(interval)
            worker=Thread(target=loop,daemon=True,name="passive-"+name+"-collector")
            worker.start()
            self.provider_threads.append(worker)
    def run(self):
        pending=None
        while not self.stop_event.is_set() or pending is not None or not self.queue.empty():
            if pending is None:
                try: pending=self.queue.get(timeout=0.25)
                except Empty: continue
            events,parts=pending
            try:
                self.ingest_batch(events,**parts)
            except Exception as exc:
                # Keep the already accepted observation in-flight until its
                # bounded transaction succeeds; a full queue cannot discard it.
                self._source_error("observation-queue",exc)
                time.sleep(0.25)
            else:
                self.queue.task_done()
                pending=None
                self.errors.pop("observation-queue",None)
    def stop(self):
        self.stop_event.set()
        for wake in self.reader_wakes.values(): wake.set()
