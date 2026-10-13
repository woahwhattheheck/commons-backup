"""Read-only loopback HTTP surface for the media-rights desk."""
import sqlite3,sys
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from rights_model import *
from rights_store import evaluate,queues,snapshot
from rights_batch import review_csv
HTTP_MUTATIONS=frozenset({'/api/place','/api/revoke'})
class ApiHandler(BaseHTTPRequestHandler):
    server_version='MediaRightsDesk/1'
    @property
    def db(self): return self.server.db_path
    def reply(self,status,payload):
        raw=canonical_bytes(payload); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(raw))); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(raw)
    def body(self): length=int(self.headers.get('Content-Length','0')); require(0<length<=MAX_INPUT_BYTES,'request body size invalid'); return loads_strict(self.rfile.read(length))
    def do_GET(self):
        try:
            if urlparse(self.path).path=='/api/snapshot': return self.reply(200,snapshot(self.db))
            if urlparse(self.path).path=='/':
                raw=self.server.ui_bytes; self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(raw))); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'"); self.end_headers(); self.wfile.write(raw); return
            self.reply(404,{'error':'not found'})
        except RightsError as e: self.reply(400,{'error':str(e)})
    def do_POST(self):
        try:
            path=urlparse(self.path).path
            if path in HTTP_MUTATIONS: return self.reply(405,{'error':'HTTP state mutation is disabled; use the local CLI for place/revoke'})
            body=self.body()
            if path=='/api/evaluate': return self.reply(200,evaluate(self.db,body))
            if path=='/api/batch':
                x=strict_object(body,{'csv'},'request')
                require(isinstance(x['csv'],str),'csv must be a string')
                return self.reply(200,review_csv(self.db,x['csv']))
            if path=='/api/queues': x=strict_object(body,{'as_of','horizon_days'},'request'); return self.reply(200,queues(self.db,x['as_of'],x['horizon_days']))
            self.reply(404,{'error':'not found'})
        except (RightsError,ValueError,sqlite3.Error) as e: self.reply(400,{'error':str(e)})
    def log_message(self,fmt,*args): print('media-rights-desk:',fmt%args,file=sys.stderr)
def serve(path,ui_path,host,port):
    require(host in {'127.0.0.1','::1','localhost'},'server is loopback-only'); require(type(port) is int and 1<=port<=65535,'port invalid'); ui=Path(ui_path); require(ui.is_file() and not ui.is_symlink(),'UI path must be a regular non-symlink file'); httpd=ThreadingHTTPServer((host,port),ApiHandler); httpd.db_path=Path(path); httpd.ui_bytes=ui.read_bytes(); print(f'Serving read-only local desk on http://{host}:{port}',file=sys.stderr); httpd.serve_forever()
