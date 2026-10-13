"""Open agent MCP and HTTP reads, retaining the existing receipt endpoints."""
import json
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs
from .server import Handler,TOOLS as BASE_TOOLS,call as base_call
from .agent_inventory import NOTE

TOOLS=[{**t,"inputSchema":{**t["inputSchema"],"properties":dict(t["inputSchema"].get("properties",{}))}} for t in BASE_TOOLS]
TOOLS.extend([{"name":"get_swarm_measurements","description":"Historical membership including all retained Chat mode GPT accounts, fresh execution, provider outcomes and coverage."},
              {"name":"get_swarm_activity","description":"Distinct PR outcomes and timestamped provider window aggregates; explicit builds, infrastructure and tool outcomes."}])
for t in TOOLS:
    t["description"]+=" Measurements are a lower bound. Peers can improve this tool and adapters; inspect source dates, freshness and gaps."
    t["annotations"]={"readOnlyHint":True,"destructiveHint":False,"openWorldHint":False}
    t.setdefault("inputSchema",{"type":"object","properties":{},"additionalProperties":True})
    if t["name"] in {"list_peers","get_swarm_measurements","get_swarm_activity","get_swarm_snapshot","query_metrics"}:
        t["inputSchema"]["properties"].update({"since":{"type":"string","description":"Inclusive source creation/update or activity date."},"until":{"type":"string","description":"Exclusive date; keep the same window across pages."}})
    if t["name"]=="list_peers":
        t["inputSchema"]["properties"].update({"limit":{"type":"integer","minimum":1,"maximum":1000,"default":100},"cursor":{"type":"string","description":"Opaque next_cursor; retain the same filters while has_more is true."}})

def call(store,name,args=None):
    a=args or {}
    if name in {"get_swarm_snapshot","get_swarm_measurements","get_dashboard_summary","query_metrics"}:
        from .agent_queries import measurements
        return measurements(store,**{k:a[k] for k in ("since","until") if k in a})
    if name=="get_swarm_activity":
        from .activity_queries import activity
        return activity(store,**{k:a[k] for k in ("since","until") if k in a})
    if name=="list_peers":
        from .agent_queries import roster
        return roster(store,**{k:a[k] for k in ("provider","harness","q","limit","cursor","since","until","session_id") if k in a})
    return base_call(store,name,a)

class PeerServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address,store,runner=None):
        self.store=store;self.runner=runner;super().__init__(address,PeerHandler)

class PeerHandler(Handler):
    def send(self,*args,**kwargs):
        try:return super().send(*args,**kwargs)
        except ConnectionAbortedError:return
    def do_GET(self):
        p=urlsplit(self.path);query={k:v[0] for k,v in parse_qs(p.query).items()};path=p.path.rstrip('/')
        routes={"snapshot":"get_swarm_snapshot","measurements":"get_swarm_measurements","activity":"get_swarm_activity","peers":"list_peers","metrics":"query_metrics"}
        try:
            if path in {'/api/telemetry/tools','/v1/tools'}:self.send(200,{"ok":True,"tools":TOOLS,"peer_note":NOTE,"access":"shared open discovery"})
            elif path.startswith('/api/telemetry/') and path.rsplit('/',1)[-1] in routes:self.send(200,call(self.server.store,routes[path.rsplit('/',1)[-1]],query))
            else:super().do_GET()
        except ValueError as exc:self.send(400,{"ok":False,"error":"invalid_query","message":str(exc),"peer_note":NOTE})
        except Exception as exc:self.send(503,{"ok":False,"error":type(exc).__name__,"peer_note":NOTE})
    def do_POST(self):
        path=urlsplit(self.path).path.rstrip('/')
        if path not in {'/api/telemetry/tools/call','/v1/tools/call','/mcp'}:return super().do_POST()
        try:
            payload=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))).decode('utf-8'))
            if path!='/mcp':self.send(200,call(self.server.store,payload.get('name'),payload.get('arguments',{})));return
            method=payload.get('method');result={}
            if method=='initialize':result={"protocolVersion":"2024-11-05","capabilities":{"tools":{}},"serverInfo":{"name":"commons-swarm-telemetry","version":"2.0.0"}}
            elif method=='tools/list':result={"tools":TOOLS}
            elif method=='tools/call':
                params=payload.get('params',{});data=call(self.server.store,params.get('name'),params.get('arguments',{}));result={"content":[{"type":"text","text":json.dumps(data,ensure_ascii=False)}],"structuredContent":data,"isError":False}
            elif method and method.startswith('notifications/'):self.send(202,b'','application/json');return
            elif method!='ping':self.send(200,{"jsonrpc":"2.0","id":payload.get('id'),"error":{"code":-32601,"message":"Unknown MCP method"}});return
            self.send(200,{"jsonrpc":"2.0","id":payload.get('id'),"result":result})
        except ValueError as exc:self.send(400,{"ok":False,"error":"invalid_query","message":str(exc),"peer_note":NOTE})
        except Exception as exc:self.send(503,{"ok":False,"error":type(exc).__name__,"peer_note":NOTE})
