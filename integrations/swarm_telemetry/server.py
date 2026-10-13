"""Human dashboard and open agent reads over cached measurements."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

WEB = Path(__file__).with_name("web")
TOOLS = [
    {"name":"get_swarm_snapshot","description":"Cached passive measurements, usage and source coverage."},
    {"name":"get_dashboard_summary","description":"Immediate cached all-service counts with asynchronous refresh and paginated source details."},
    {"name":"list_peers","description":"Recorded peers and native sessions, with provider, harness and explicit runtime state."},
    {"name":"get_changes_since","description":"Incremental observations after a stable event cursor."},
    {"name":"get_work_context","description":"Work relationships and contributing events with stable history pagination."},
    {"name":"trace_operation","description":"Observed attempts and outcomes for one operation with stable history pagination."},
    {"name":"list_accounts_and_services","description":"Account and service reference metadata; no credential values."},
    {"name":"get_source_coverage","description":"Collection coverage, gaps, freshness and checkpoints."},
    {"name":"query_metrics","description":"Defined counts, usage, provider/harness breakdowns and activity."},
    {"name":"get_notifications","description":"Passive notices with source references, delivery state, filters and stable continuation cursors."},
    {"name":"get_collection_jobs","description":"Open resumable native-connector reads for the full corpus; no assignment or admission."},
]
for tool in TOOLS:
    tool["inputSchema"]={"type":"object","properties":{key:{"type":"string"} for key in ("provider","harness","source","q","session_id","work_id","operation_id")},"additionalProperties":True}
    if tool["name"]=="get_notifications":
        tool["inputSchema"]["properties"].update({
            "limit":{"type":"integer","minimum":1,"maximum":10000,"default":1000,"description":"Maximum notices per page."},
            "cursor":{"type":"string","description":"Use next_cursor from the previous page while has_more is true; retain the same filters."},
            "q":{"type":"string","description":"Search the stored notification content."},
        })
    if tool["name"] in {"get_work_context","trace_operation"}:
        tool["inputSchema"]["properties"].update({
            "limit":{"type":"integer","minimum":1,"maximum":1000,"default":1000,"description":"Maximum events per history page."},
            "cursor":{"type":"integer","minimum":0,"default":0,"description":"Use next_cursor while has_more is true; retain the same history filters and order."},
            "order":{"type":"string","enum":["asc","desc"],"default":"asc","description":"Event sequence order for this history."},
            "event_id":{"type":"string","description":"Optional exact event identity within this history."},
        })
    if tool["name"]=="get_work_context":
        tool["inputSchema"]["properties"]["limit"]["description"]="Maximum work items or work-history events per page."
        tool["inputSchema"]["properties"]["cursor"]={"type":["integer","string"],"default":0,
            "description":"Without work_id, use the opaque work-list next_cursor; with work_id, use the integer event next_cursor. Continue while has_more is true."}

def call(store, name, args=None):
    args=args or {}
    if name=="get_swarm_snapshot": return store.snapshot(detailed=str(args.get("detailed","")).lower() in {"1","true","yes"})
    if name=="get_dashboard_summary": return store.dashboard_summary()
    if name=="list_peers": return store.peers(**{k:args[k] for k in ("provider","harness","q","limit") if k in args})
    if name=="get_changes_since": return store.events(**{k:args[k] for k in ("cursor","limit","source","provider","harness","q","session_id","work_id","operation_id","event_id","order") if k in args})
    if name=="get_work_context":
        if args.get("work_id"): return store.events(limit=args.get("limit",1000),**{k:args[k] for k in ("cursor","source","provider","harness","q","session_id","work_id","operation_id","event_id","order") if k in args})
        return store.work(**{k:args[k] for k in ("limit","cursor") if k in args})
    if name=="trace_operation": return store.events(limit=args.get("limit",1000),**{k:args[k] for k in ("cursor","source","provider","harness","q","session_id","work_id","operation_id","event_id","order") if k in args})
    if name=="list_accounts_and_services": return store.records("accounts",**{k:args[k] for k in ("limit","cursor","q","source","provider","harness") if k in args})
    if name=="get_source_coverage": return store.records("coverage",**{k:args[k] for k in ("limit","cursor","q","source","provider","harness") if k in args})
    if name=="query_metrics": return store.metrics()
    if name=="get_notifications": return store.records("notifications",**{k:args[k] for k in ("limit","cursor","q","source","provider","harness") if k in args})
    if name=="get_collection_jobs":
        from .source_engine import SourceEngine
        return SourceEngine(store).jobs(**{k:args[k] for k in ("reader","limit","cursor") if k in args})
    raise ValueError("Unknown measurement tool: "+str(name))

class Server(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address,store,runner=None):
        self.store=store
        self.runner=runner
        super().__init__(address,Handler)

class Handler(BaseHTTPRequestHandler):
    server_version="CommonsSwarmTelemetry/1"
    def log_message(self,*_): pass
    def send(self,status,value,content_type="application/json; charset=utf-8"):
        if not isinstance(value,bytes): value=json.dumps(value,ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type",content_type)
        self.send_header("Content-Length",str(len(value)))
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.end_headers()
        try: self.wfile.write(value)
        except (BrokenPipeError,ConnectionResetError): pass

    def do_GET(self):
        parsed=urlsplit(self.path)
        query={k:v[0] for k,v in parse_qs(parsed.query).items()}
        path=parsed.path.rstrip("/") or "/"
        routes={"snapshot":"get_swarm_snapshot","peers":"list_peers","events":"get_changes_since","changes":"get_changes_since","accounts":"list_accounts_and_services","coverage":"get_source_coverage","work":"get_work_context","metrics":"query_metrics","notifications":"get_notifications","operation":"trace_operation","source-jobs":"get_collection_jobs"}
        try:
            if path in {"/health","/api/telemetry/health"}:
                runner=self.server.runner
                self.send(200,{"ok":True,"service":"commons-swarm-telemetry","version":"1.0.0","mode":"passive","jev_required":False,"runtime":self.server.store.state("collector"),"storage":self.server.store.state("storage_guard"),"readers":{kind:self.server.store.state("source_reader_health:"+kind) for kind in ("slack","github","services")},"collector_progress":dict(runner.last_provider) if runner else {},"collector_threads":[{"name":worker.name,"alive":worker.is_alive()} for worker in ([runner.thread]+runner.provider_threads) if worker] if runner else [],"collector_errors":dict(runner.errors) if runner else {}})
            elif path=="/api/telemetry/tools": self.send(200,{"ok":True,"tools":TOOLS,"access":"shared open discovery"})
            elif path=="/v1/tools": self.send(200,{"ok":True,"tools":TOOLS})
            elif path=="/api/telemetry/source-record":
                self.send(200,self.server.store.custody.envelope(query.get("ref","")))
            elif path=="/api/telemetry/summary":
                value=self.server.store.dashboard_summary()
                self.send(200 if value.get("summary_ready") else 202,value)
            elif path=="/api/telemetry/source-groups":
                self.send(200,self.server.store.coverage_group_page(**{key:query[key] for key in ("limit","cursor") if key in query}))
            elif path=="/api/telemetry/manifest":
                self.send(200,{"ok":True,"version":"1","dashboard":"/","tools":"/api/telemetry/tools","mcp":"/mcp","data":"/api/telemetry/snapshot","dashboard_summary":"/api/telemetry/summary","source_group_details":"/api/telemetry/source-groups?limit=100&cursor=CURSOR","observation":"POST /api/telemetry/observe","source_ingest":"POST /api/telemetry/source-events","source_receipt":"POST /api/telemetry/source-response","source_record":"/api/telemetry/source-record?ref=REF","policy":"Passive measurement; existing work never waits for telemetry; Jev optional."})
            elif path.startswith("/api/telemetry/") and path.rsplit("/",1)[-1] in routes:
                self.send(200,call(self.server.store,routes[path.rsplit("/",1)[-1]],query))
            elif path=="/data-snapshot.json": self.send(200,self.server.store.snapshot(detailed=True))
            elif path in {"/","/index.html","/app.js","/style.css"}:
                file=WEB/("index.html" if path=="/" else path[1:])
                mime={".html":"text/html; charset=utf-8",".js":"text/javascript; charset=utf-8",".css":"text/css; charset=utf-8"}[file.suffix]
                self.send(200,file.read_bytes(),mime)
            else: self.send(404,{"ok":False,"error":"not_found"})
        except (ValueError,TypeError) as exc:
            self.send(400,{"ok":False,"error":"invalid_query","message":str(exc)})
        except Exception as exc:
            self.send(503,{"ok":False,"error":type(exc).__name__,"message":"Measurement temporarily unavailable. Swarm execution is independent."})

    def do_POST(self):
        try:
            length=int(self.headers.get("Content-Length","0"))
            if length<=0:
                self.send(413,{"ok":False,"error":"observation_size"}); return
            payload=json.loads(self.rfile.read(length).decode("utf-8"))
            path=urlsplit(self.path).path
            if path=="/api/telemetry/observe":
                events=payload.get("events",[payload] if "event_type" in payload else [])
                if self.server.runner:
                    accepted=self.server.runner.offer(events,coverage=payload.get("coverage"),accounts=payload.get("accounts"))
                    self.send(202,{"ok":True,"queued":accepted,"durable":False,"message":"Optional observation queued independently of work."})
                else:
                    self.send(200,self.server.store.ingest(events,coverage=payload.get("coverage"),accounts=payload.get("accounts")))
            elif path=="/api/telemetry/source-events":
                # Source collectors commit complete originals before their
                # checkpoint advances. Optional work observation stays async.
                result=self.server.store.ingest(payload.get("events",[]),coverage=payload.get("coverage"),accounts=payload.get("accounts"),checkpoints=payload.get("checkpoints"))
                self.send(200,{**result,"durable":True})
            elif path in {"/api/telemetry/tools/call","/v1/tools/call"}: self.send(200,call(self.server.store,payload.get("name"),payload.get("arguments",{})))
            elif path=="/api/telemetry/source-response":
                from .source_engine import SourceEngine
                runner=self.server.runner
                result=SourceEngine(self.server.store,runner.config if runner else {}).record_response(payload)
                if runner: runner.request_collection(result["reader"])
                self.send(200,result)
            elif path=="/mcp":
                method=payload.get("method")
                result=None
                if method=="initialize": result={"protocolVersion":"2024-11-05","capabilities":{"tools":{}},"serverInfo":{"name":"commons-swarm-telemetry","version":"1.0.0"}}
                elif method=="tools/list": result={"tools":TOOLS}
                elif method=="tools/call":
                    params=payload.get("params",{})
                    data=call(self.server.store,params.get("name"),params.get("arguments",{}))
                    result={"content":[{"type":"text","text":json.dumps(data,ensure_ascii=False)}],"structuredContent":data,"isError":False}
                elif method=="ping": result={}
                elif method and method.startswith("notifications/"):
                    self.send(202,b"","application/json"); return
                else:
                    self.send(200,{"jsonrpc":"2.0","id":payload.get("id"),"error":{"code":-32601,"message":"Unknown MCP method"}}); return
                self.send(200,{"jsonrpc":"2.0","id":payload.get("id"),"result":result})
            else: self.send(404,{"ok":False,"error":"not_found"})
        except (ValueError,TypeError,UnicodeError) as exc:
            self.send(400,{"ok":False,"error":"invalid_observation","message":str(exc)})
        except Exception as exc:
            self.send(503,{"ok":False,"error":type(exc).__name__,"message":"Observation unavailable; work remains independent."})
