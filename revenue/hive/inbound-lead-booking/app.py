#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,hashlib,io,json,sqlite3
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

SCHEMA='inbound-lead-booking/v1'
class DeskError(ValueError): pass

def _text(v,name):
    if not isinstance(v,str) or not v.strip(): raise DeskError(f'{name} must be text')
    return v.strip()
def _bool(v,name):
    if type(v) is not bool: raise DeskError(f'{name} must be boolean')
    return v
def _canon(obj): return json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()

def load_config(path):
    c=json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(c,dict) or c.get('schema')!=SCHEMA: raise DeskError('config schema mismatch')
    if not isinstance(c.get('routes'),list) or not c['routes']: raise DeskError('routes required')
    if not isinstance(c.get('slots'),list) or not c['slots']: raise DeskError('slots required')
    for r in c['routes']:
        if not isinstance(r,dict): raise DeskError('route must be object')
        for k in ('service','area','calendar'): _text(r.get(k),f'route.{k}')
    for s in c['slots']:
        if not isinstance(s,dict): raise DeskError('slot must be object')
        for k in ('id','calendar','start'): _text(s.get(k),f'slot.{k}')
    return c

class Desk:
    def __init__(self,db_path,config):
        self.db_path=str(db_path); self.config=config; self._init()
    @contextmanager
    def _db(self):
        db=sqlite3.connect(self.db_path,timeout=10,isolation_level=None); db.row_factory=sqlite3.Row; db.execute('PRAGMA journal_mode=WAL')
        try: yield db
        finally: db.close()
    def _init(self):
        with self._db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS leads(id INTEGER PRIMARY KEY,source_ref TEXT UNIQUE NOT NULL,payload_hash TEXT NOT NULL,name TEXT,email TEXT,phone TEXT,service TEXT,area TEXT,consent INTEGER NOT NULL,calendar TEXT,status TEXT NOT NULL,requested_slot TEXT,booking_slot TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS drafts(id INTEGER PRIMARY KEY,lead_id INTEGER UNIQUE NOT NULL,body TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS followups(id INTEGER PRIMARY KEY,lead_id INTEGER UNIQUE NOT NULL,reason TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'OPEN');
            CREATE TABLE IF NOT EXISTS slots(id TEXT PRIMARY KEY,calendar TEXT NOT NULL,start TEXT NOT NULL,lead_id INTEGER UNIQUE);
            ''')
            for s in self.config['slots']:
                db.execute('INSERT OR IGNORE INTO slots(id,calendar,start) VALUES(?,?,?)',(s['id'],s['calendar'],s['start']))
    def _route(self,service,area):
        return next((r for r in self.config['routes'] if r['service'].casefold()==service.casefold() and r['area'].casefold()==area.casefold()),None)
    def _alts(self,db,calendar):
        return [dict(r) for r in db.execute('SELECT id,start FROM slots WHERE calendar=? AND lead_id IS NULL ORDER BY start,id LIMIT 3',(calendar,))]
    def _result(self,db,lead_id,replayed=False):
        lead=dict(db.execute('SELECT * FROM leads WHERE id=?',(lead_id,)).fetchone())
        lead['consent']=bool(lead['consent']); lead['replayed']=replayed
        d=db.execute('SELECT body FROM drafts WHERE lead_id=?',(lead_id,)).fetchone(); lead['reply_draft']=d['body'] if d else None
        f=db.execute('SELECT reason,status FROM followups WHERE lead_id=?',(lead_id,)).fetchone(); lead['followup']=dict(f) if f else None
        lead['alternatives']=self._alts(db,lead['calendar']) if lead['calendar'] and not lead['booking_slot'] else []
        return lead
    def intake(self,payload):
        if not isinstance(payload,dict): raise DeskError('intake must be object')
        allowed={'source_ref','name','email','phone','service','area','consent','requested_slot'}
        if set(payload)-allowed: raise DeskError('unexpected intake keys')
        source=_text(payload.get('source_ref'),'source_ref'); name=_text(payload.get('name'),'name'); service=_text(payload.get('service'),'service'); area=_text(payload.get('area'),'area'); consent=_bool(payload.get('consent'),'consent')
        email=payload.get('email') or ''; phone=payload.get('phone') or ''; requested=payload.get('requested_slot') or ''
        if email: _text(email,'email')
        if phone: _text(phone,'phone')
        if not email and not phone: raise DeskError('email or phone required')
        if requested: _text(requested,'requested_slot')
        normalized={'source_ref':source,'name':name,'email':email,'phone':phone,'service':service,'area':area,'consent':consent,'requested_slot':requested}
        digest=hashlib.sha256(_canon(normalized)).hexdigest()
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT id,payload_hash FROM leads WHERE source_ref=?',(source,)).fetchone()
            if old:
                if old['payload_hash']!=digest: raise DeskError('source_ref already used with different payload')
                db.commit(); return self._result(db,old['id'],True)
            route=self._route(service,area); calendar=route['calendar'] if route else None; status='NEW'
            if not route: status='OUT_OF_AREA'
            elif not consent: status='CONSENT_REVIEW'
            cur=db.execute('INSERT INTO leads(source_ref,payload_hash,name,email,phone,service,area,consent,calendar,status,requested_slot) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(source,digest,name,email,phone,service,area,int(consent),calendar,status,requested))
            lead_id=cur.lastrowid
            if not route: db.execute('INSERT INTO followups(lead_id,reason) VALUES(?,?)',(lead_id,'OUT_OF_SERVICE_AREA'))
            elif not consent: db.execute('INSERT INTO followups(lead_id,reason) VALUES(?,?)',(lead_id,'CONSENT_REQUIRED'))
            else:
                db.execute('INSERT INTO drafts(lead_id,body) VALUES(?,?)',(lead_id,f'DRAFT — Hi {name}, thanks for asking about {service}. No message has been sent.'))
                if requested:
                    upd=db.execute('UPDATE slots SET lead_id=? WHERE id=? AND calendar=? AND lead_id IS NULL',(lead_id,requested,calendar))
                    if upd.rowcount==1:
                        db.execute("UPDATE leads SET booking_slot=?,status='BOOKED' WHERE id=?",(requested,lead_id))
                    else: db.execute("UPDATE leads SET status='AWAITING_SLOT' WHERE id=?",(lead_id,))
                else: db.execute("UPDATE leads SET status='AWAITING_SLOT' WHERE id=?",(lead_id,))
            db.commit(); return self._result(db,lead_id)
    def book(self,source_ref,slot_id):
        source=_text(source_ref,'source_ref'); slot=_text(slot_id,'slot_id')
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            lead=db.execute('SELECT * FROM leads WHERE source_ref=?',(source,)).fetchone()
            if not lead: raise DeskError('lead not found')
            if not lead['consent'] or not lead['calendar']: raise DeskError('lead not eligible for booking')
            if lead['booking_slot']:
                if lead['booking_slot']!=slot: raise DeskError('lead already booked elsewhere')
                db.commit(); return self._result(db,lead['id'],True)
            upd=db.execute('UPDATE slots SET lead_id=? WHERE id=? AND calendar=? AND lead_id IS NULL',(lead['id'],slot,lead['calendar']))
            if upd.rowcount!=1: raise DeskError('slot unavailable')
            db.execute("UPDATE leads SET booking_slot=?,status='BOOKED' WHERE id=?",(slot,lead['id']))
            db.commit(); return self._result(db,lead['id'])
    def state(self):
        with self._db() as db:
            return {'leads':[dict(r) for r in db.execute('SELECT id,source_ref,name,service,area,status,booking_slot FROM leads ORDER BY id')], 'slots':[dict(r) for r in db.execute('SELECT id,calendar,start,lead_id FROM slots ORDER BY start,id')], 'draft_count':db.execute('SELECT count(*) FROM drafts').fetchone()[0], 'followup_count':db.execute("SELECT count(*) FROM followups WHERE status='OPEN'").fetchone()[0]}
    def crm_csv(self):
        out=io.StringIO(newline=''); w=csv.writer(out,lineterminator='\n'); w.writerow(['lead_id','source_ref','name','email','phone','service','area','status','booking_slot'])
        with self._db() as db:
            for r in db.execute('SELECT id,source_ref,name,email,phone,service,area,status,booking_slot FROM leads ORDER BY id'): w.writerow(list(r))
        return out.getvalue()

def handler_for(desk):
    class H(BaseHTTPRequestHandler):
        def log_message(self,*a): pass
        def _send(self,code,body,ctype='application/json; charset=utf-8'):
            raw=body if isinstance(body,bytes) else body.encode(); self.send_response(code); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
        def do_GET(self):
            if self.path=='/state': self._send(200,json.dumps(desk.state(),sort_keys=True))
            elif self.path=='/crm.csv': self._send(200,desk.crm_csv(),'text/csv; charset=utf-8')
            else: self._send(404,json.dumps({'error':'not found'}))
        def do_POST(self):
            try:
                n=int(self.headers.get('Content-Length','0')); data=json.loads(self.rfile.read(n) or b'{}')
                if self.path=='/intake': result=desk.intake(data)
                elif self.path=='/book': result=desk.book(data.get('source_ref'),data.get('slot_id'))
                else: return self._send(404,json.dumps({'error':'not found'}))
                self._send(200,json.dumps(result,sort_keys=True))
            except (DeskError,json.JSONDecodeError,TypeError,ValueError) as e: self._send(400,json.dumps({'error':str(e)}))
    return H

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument('--db',default='desk.sqlite3'); p.add_argument('--config',default='demo_config.json'); sub=p.add_subparsers(dest='cmd',required=True)
    i=sub.add_parser('intake'); i.add_argument('json_file'); b=sub.add_parser('book'); b.add_argument('source_ref'); b.add_argument('slot_id'); sub.add_parser('state'); sub.add_parser('crm'); s=sub.add_parser('serve'); s.add_argument('--host',default='127.0.0.1'); s.add_argument('--port',type=int,default=8098)
    a=p.parse_args(argv); desk=Desk(a.db,load_config(a.config))
    if a.cmd=='intake': print(json.dumps(desk.intake(json.loads(Path(a.json_file).read_text())),indent=2,sort_keys=True))
    elif a.cmd=='book': print(json.dumps(desk.book(a.source_ref,a.slot_id),indent=2,sort_keys=True))
    elif a.cmd=='state': print(json.dumps(desk.state(),indent=2,sort_keys=True))
    elif a.cmd=='crm': print(desk.crm_csv(),end='')
    else:
        httpd=ThreadingHTTPServer((a.host,a.port),handler_for(desk)); print(f'http://{a.host}:{httpd.server_address[1]}',flush=True); httpd.serve_forever()
if __name__=='__main__': main()
