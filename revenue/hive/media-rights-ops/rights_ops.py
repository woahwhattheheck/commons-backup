#!/usr/bin/env python3
"""Content rights & usage-window operations desk; supplied-authority gate only."""
import argparse,json,sqlite3,sys
from pathlib import Path
from rights_model import *
from rights_store import import_manifest,evaluate,record_placement,revoke_grant,queues,snapshot
from rights_export import export_files,publish_export
from rights_http import serve
def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='cmd',required=True)
    x=sub.add_parser('import'); x.add_argument('db',type=Path); x.add_argument('manifest',type=Path); x.add_argument('--at',required=True)
    x=sub.add_parser('evaluate'); x.add_argument('db',type=Path); x.add_argument('intent',type=Path)
    x=sub.add_parser('place'); x.add_argument('db',type=Path); x.add_argument('intent',type=Path); x.add_argument('--at',required=True)
    x=sub.add_parser('revoke'); x.add_argument('db',type=Path); x.add_argument('grant_id'); x.add_argument('--at',required=True)
    x=sub.add_parser('queues'); x.add_argument('db',type=Path); x.add_argument('--as-of',required=True); x.add_argument('--horizon-days',type=int,default=30)
    x=sub.add_parser('export'); x.add_argument('db',type=Path); x.add_argument('output',type=Path); x.add_argument('--as-of',required=True); x.add_argument('--horizon-days',type=int,default=30)
    x=sub.add_parser('serve'); x.add_argument('db',type=Path); x.add_argument('--ui',type=Path,default=Path(__file__).with_name('desk.html')); x.add_argument('--host',default='127.0.0.1'); x.add_argument('--port',type=int,default=8765)
    a=p.parse_args(argv)
    try:
        if a.cmd=='import': out=import_manifest(a.db,read_strict_json(a.manifest),a.at)
        elif a.cmd=='evaluate': out=evaluate(a.db,read_strict_json(a.intent))
        elif a.cmd=='place': out=record_placement(a.db,read_strict_json(a.intent),a.at)
        elif a.cmd=='revoke': out=revoke_grant(a.db,a.grant_id,a.at)
        elif a.cmd=='queues': out=queues(a.db,a.as_of,a.horizon_days)
        elif a.cmd=='export': out=publish_export(a.db,a.output,a.as_of,a.horizon_days)
        elif a.cmd=='serve': serve(a.db,a.ui,a.host,a.port); return 0
        else: raise AssertionError(a.cmd)
        print(json.dumps(out,sort_keys=True,separators=(',',':'))); return 0
    except (RightsError,OSError,sqlite3.Error,ValueError) as e: print(f'MEDIA RIGHTS DESK ERROR: {e}',file=sys.stderr); return 2
if __name__=='__main__': raise SystemExit(main())
