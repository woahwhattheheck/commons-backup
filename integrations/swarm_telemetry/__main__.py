"""Run passive collection, the human dashboard, or agent queries."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from .store import redact
from .peer_store import PeerStore as Store

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=("serve","collect","snapshot","export","ingest","query"))
    parser.add_argument("--state",type=Path,default=Path("state/swarm-telemetry"))
    parser.add_argument("--config",type=Path)
    parser.add_argument("--host",default="127.0.0.1")
    parser.add_argument("--port",type=int,default=8893)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--input",type=Path)
    parser.add_argument("--source",choices=("slack","github","events"),default="events")
    parser.add_argument("--roots",nargs="*")
    parser.add_argument("--limit-files",type=int)
    parser.add_argument("--local-only",action="store_true")
    parser.add_argument("--public",action="store_true")
    parser.add_argument("--tool",default="get_swarm_snapshot")
    parser.add_argument("--arguments",default="{}")
    args=parser.parse_args(argv)
    try:
        config=json.loads(args.config.read_text(encoding="utf-8-sig")) if args.config else {}
        if args.roots is not None: config["transcript_roots"]=args.roots
        if args.limit_files is not None: config["transcript_batch_files"]=args.limit_files
        store=Store(args.state/"telemetry.sqlite3")
        if args.command=="snapshot":
            from .agent_queries import measurements
            result=measurements(store)
        elif args.command=="export":
            if not args.output: raise ValueError("--output required")
            result=store.export(args.output,public=args.public)
        elif args.command=="query":
            from .peer_server import call
            arguments=json.loads(args.arguments)
            result=call(store,args.tool,arguments)
        elif args.command=="ingest":
            data=json.loads(args.input.read_text(encoding="utf-8-sig")) if args.input else json.load(sys.stdin)
            if args.source=="events": events=data if isinstance(data,list) else data.get("events",[])
            else:
                from .collectors import normalize_slack,normalize_github
                events=normalize_slack(data) if args.source=="slack" else normalize_github(data)
            coverage=data.get("coverage",[]) if isinstance(data,dict) else []
            result=store.ingest(events,coverage=coverage)
        elif args.command=="collect":
            from .peer_runner import PeerRunner as Runner
            result=Runner(store,config).collect_once(providers=not args.local_only)
        else:
            from .peer_runner import PeerRunner as Runner
            from .peer_server import PeerServer as Server
            runner=Runner(store,config)
            server=Server((args.host,args.port),store,runner)
            runner.start()
            print(json.dumps({"ok":True,"dashboard":f"http://{args.host}:{args.port}/","mcp":f"http://{args.host}:{args.port}/mcp","state":str(args.state),"mode":"passive","jev_required":False}),flush=True)
            try: server.serve_forever()
            except KeyboardInterrupt: pass
            finally: runner.stop(); server.server_close()
            return 0
        print(json.dumps(redact(result),ensure_ascii=False),flush=True)
        if args.command=="collect" and result.get("errors"):
            print(json.dumps({"ok":False,"error":"collection_failed","sources":redact(result["errors"])}),file=sys.stderr)
            return 1
        return 0
    except Exception as exc:
        print(json.dumps({"ok":False,"error":type(exc).__name__,"message":redact(str(exc))}),file=sys.stderr)
        return 1

if __name__=="__main__": raise SystemExit(main())
