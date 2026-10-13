"""SQLite state machine for supplied-authority media operations."""
from __future__ import annotations
import json,sqlite3
from datetime import timedelta
from pathlib import Path
from rights_model import *
def connect(path):
    con=sqlite3.connect(path,timeout=30.0,isolation_level=None); con.row_factory=sqlite3.Row; con.execute('PRAGMA foreign_keys=ON'); con.execute('PRAGMA journal_mode=WAL'); con.execute('PRAGMA synchronous=FULL'); return con
def initialize(path):
    path.parent.mkdir(parents=True,exist_ok=True); con=connect(path)
    try:
        con.executescript("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);CREATE TABLE IF NOT EXISTS assets(asset_id TEXT PRIMARY KEY,sha256 TEXT NOT NULL,parent_asset_id TEXT REFERENCES assets(asset_id));CREATE TABLE IF NOT EXISTS grants(grant_id TEXT PRIMARY KEY,asset_id TEXT NOT NULL REFERENCES assets(asset_id),authority_ref TEXT NOT NULL,valid_from TEXT NOT NULL,valid_until TEXT NOT NULL,channels_json TEXT NOT NULL,territories_json TEXT NOT NULL,revoked_at TEXT);CREATE TABLE IF NOT EXISTS placements(request_id TEXT PRIMARY KEY,intent_sha256 TEXT NOT NULL,asset_id TEXT NOT NULL REFERENCES assets(asset_id),channel TEXT NOT NULL,territory TEXT NOT NULL,starts_at TEXT NOT NULL,ends_at TEXT NOT NULL,grant_id TEXT NOT NULL REFERENCES grants(grant_id),recorded_at TEXT NOT NULL);CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY AUTOINCREMENT,event_type TEXT NOT NULL,ref_id TEXT NOT NULL,at TEXT NOT NULL,payload_sha256 TEXT NOT NULL);"); con.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('schema',?)",(SCHEMA,))
    finally: con.close()
def lineage(con,aid):
    row=con.execute('SELECT asset_id,parent_asset_id FROM assets WHERE asset_id=?',(aid,)).fetchone(); require(row is not None,f'unknown asset_id: {aid}'); out=[]; seen=set()
    while row is not None:
        cur=str(row['asset_id']); require(cur not in seen,'stored asset lineage cycle'); seen.add(cur); out.append(cur); parent=row['parent_asset_id']; row=None if parent is None else con.execute('SELECT asset_id,parent_asset_id FROM assets WHERE asset_id=?',(parent,)).fetchone(); require(parent is None or row is not None,'stored asset lineage broken')
    return out
def import_manifest(path,doc,imported_at):
    m=normalize_manifest(doc); at=norm_time(imported_at,'imported_at'); initialize(path); con=connect(path)
    try:
        con.execute('BEGIN IMMEDIATE'); require(con.execute('SELECT COUNT(*) FROM assets').fetchone()[0]==0,'asset registry already initialized'); require(con.execute('SELECT COUNT(*) FROM grants').fetchone()[0]==0,'grant registry already initialized'); pending={x['asset_id']:x for x in m['assets']}; inserted=set()
        while pending:
            moved=False
            for aid in sorted(list(pending)):
                x=pending[aid]
                if x['parent_asset_id'] is None or x['parent_asset_id'] in inserted: con.execute('INSERT INTO assets VALUES(?,?,?)',(aid,x['sha256'],x['parent_asset_id'])); inserted.add(aid); del pending[aid]; moved=True
            require(moved,'could not resolve asset lineage')
        for g in m['grants']: con.execute('INSERT INTO grants VALUES(?,?,?,?,?,?,?,NULL)',(g['grant_id'],g['asset_id'],g['authority_ref'],g['valid_from'],g['valid_until'],json.dumps(g['channels'],separators=(',',':')),json.dumps(g['territories'],separators=(',',':'))))
        digest=sha256_bytes(canonical_bytes(m)); con.execute("INSERT INTO audit(event_type,ref_id,at,payload_sha256) VALUES('IMPORT','manifest',?,?)",(at,digest)); con.execute("INSERT OR REPLACE INTO meta VALUES('manifest_sha256',?)",(digest,)); con.execute('COMMIT'); return {'status':'IMPORTED','assets':len(m['assets']),'grants':len(m['grants']),'manifest_sha256':digest}
    except Exception:
        if con.in_transaction: con.execute('ROLLBACK')
        raise
    finally: con.close()
def _evaluate(con,n):
    lineage(con,n['asset_id']); rows=con.execute("SELECT * FROM grants WHERE asset_id=? ORDER BY grant_id",(n['asset_id'],)).fetchall(); digest=sha256_bytes(canonical_bytes(n))
    if not rows: return {'status':'HOLD','selected_grant_id':None,'reasons':['MISSING_GRANT'],'intent_sha256':digest}
    good=[]; failures=set(); start=parse_time(n['starts_at'],'starts_at'); end=parse_time(n['ends_at'],'ends_at')
    for r in rows:
        bad=set()
        if r['revoked_at'] is not None: bad.add('REVOKED_GRANT')
        if start<parse_time(r['valid_from'],'valid_from') or end>parse_time(r['valid_until'],'valid_until'): bad.add('WINDOW_NOT_AUTHORIZED')
        if n['channel'] not in json.loads(r['channels_json']): bad.add('CHANNEL_NOT_AUTHORIZED')
        if n['territory'] not in json.loads(r['territories_json']): bad.add('TERRITORY_NOT_AUTHORIZED')
        if bad: failures.update(bad)
        else: good.append(str(r['grant_id']))
    return {'status':'READY_ON_SUPPLIED_AUTHORITY','selected_grant_id':sorted(good)[0],'reasons':[],'intent_sha256':digest} if good else {'status':'HOLD','selected_grant_id':None,'reasons':sorted(failures),'intent_sha256':digest}
def evaluate(path,intent):
    n=normalize_intent(intent); con=connect(path)
    try:
        con.execute('BEGIN')
        return _evaluate(con,n)
    finally:
        if con.in_transaction: con.execute('ROLLBACK')
        con.close()
def record_placement(path,intent,recorded_at):
    n=normalize_intent(intent,True); at=norm_time(recorded_at,'recorded_at'); rid=n['request_id']; content={k:n[k] for k in ('request_id','asset_id','channel','territory','starts_at','ends_at')}; digest=sha256_bytes(canonical_bytes(content)); con=connect(path)
    try:
        con.execute('BEGIN IMMEDIATE'); prior=con.execute('SELECT * FROM placements WHERE request_id=?',(rid,)).fetchone()
        if prior is not None: require(prior['intent_sha256']==digest,'request_id replay changed placement intent'); con.execute('COMMIT'); return {'status':'IDEMPOTENT_REPLAY','request_id':rid,'grant_id':prior['grant_id'],'intent_sha256':digest,'recorded_at':prior['recorded_at']}
        ev=_evaluate(con,{k:n[k] for k in ('asset_id','channel','territory','starts_at','ends_at')})
        if ev['status']!='READY_ON_SUPPLIED_AUTHORITY': con.execute('COMMIT'); return {'status':'HOLD','request_id':rid,'reasons':ev['reasons'],'intent_sha256':digest}
        gid=str(ev['selected_grant_id']); con.execute('INSERT INTO placements VALUES(?,?,?,?,?,?,?,?,?)',(rid,digest,n['asset_id'],n['channel'],n['territory'],n['starts_at'],n['ends_at'],gid,at)); con.execute("INSERT INTO audit(event_type,ref_id,at,payload_sha256) VALUES('PLACEMENT',?,?,?)",(rid,at,digest)); con.execute('COMMIT'); return {'status':'RECORDED','request_id':rid,'grant_id':gid,'intent_sha256':digest,'recorded_at':at}
    except Exception:
        if con.in_transaction: con.execute('ROLLBACK')
        raise
    finally: con.close()
def revoke_grant(path,grant_id,revoked_at):
    gid=strict_id(grant_id,'grant_id'); at=norm_time(revoked_at,'revoked_at'); con=connect(path)
    try:
        con.execute('BEGIN IMMEDIATE'); row=con.execute('SELECT revoked_at FROM grants WHERE grant_id=?',(gid,)).fetchone(); require(row is not None,f'unknown grant_id: {gid}')
        if row['revoked_at'] is not None: require(row['revoked_at']==at,'grant revocation is immutable once recorded'); con.execute('COMMIT'); return {'status':'IDEMPOTENT_REPLAY','grant_id':gid,'revoked_at':at}
        digest=sha256_bytes(canonical_bytes({'grant_id':gid,'revoked_at':at})); con.execute('UPDATE grants SET revoked_at=? WHERE grant_id=?',(at,gid)); con.execute("INSERT INTO audit(event_type,ref_id,at,payload_sha256) VALUES('REVOKE',?,?,?)",(gid,at,digest)); con.execute('COMMIT'); return {'status':'REVOKED','grant_id':gid,'revoked_at':at,'receipt_sha256':digest}
    except Exception:
        if con.in_transaction: con.execute('ROLLBACK')
        raise
    finally: con.close()
def _queues_from_connection(con,as_of,horizon_days=30):
    require(type(horizon_days) is int and 0<=horizon_days<=3650,'horizon_days must be an integer 0..3650'); now=parse_time(as_of,'as_of'); end=now+timedelta(days=horizon_days)
    renewal=[]
    for r in con.execute('SELECT * FROM grants ORDER BY grant_id'):
        until=parse_time(r['valid_until'],'valid_until')
        if r['revoked_at'] is None and until<now: renewal.append({'grant_id':r['grant_id'],'asset_id':r['asset_id'],'state':'EXPIRED','valid_until':r['valid_until'],'authority_ref':r['authority_ref']})
        elif r['revoked_at'] is None and until<=end: renewal.append({'grant_id':r['grant_id'],'asset_id':r['asset_id'],'state':'EXPIRING','valid_until':r['valid_until'],'authority_ref':r['authority_ref']})
    retract=[]
    rows=con.execute('SELECT p.request_id,p.asset_id,p.channel,p.territory,p.starts_at,p.ends_at,p.grant_id,g.revoked_at FROM placements p JOIN grants g ON g.grant_id=p.grant_id WHERE g.revoked_at IS NOT NULL ORDER BY p.request_id')
    for r in rows:
        if parse_time(r['ends_at'],'ends_at')>parse_time(r['revoked_at'],'revoked_at'):
            retract.append(dict(r))
    return {'as_of':norm_time(as_of,'as_of'),'horizon_days':horizon_days,'renewal_review':renewal,'retraction_review':retract}
def queues(path,as_of,horizon_days=30):
    con=connect(path)
    try:
        con.execute('BEGIN')
        return _queues_from_connection(con,as_of,horizon_days)
    finally:
        if con.in_transaction: con.execute('ROLLBACK')
        con.close()
def _snapshot_from_connection(con):
    assets=[dict(r) for r in con.execute('SELECT asset_id,sha256,parent_asset_id FROM assets ORDER BY asset_id')]; grants=[]
    for r in con.execute('SELECT * FROM grants ORDER BY grant_id'): grants.append({'grant_id':r['grant_id'],'asset_id':r['asset_id'],'authority_ref':r['authority_ref'],'valid_from':r['valid_from'],'valid_until':r['valid_until'],'channels':json.loads(r['channels_json']),'territories':json.loads(r['territories_json']),'revoked_at':r['revoked_at']})
    placements=[dict(r) for r in con.execute('SELECT request_id,intent_sha256,asset_id,channel,territory,starts_at,ends_at,grant_id,recorded_at FROM placements ORDER BY request_id')]; audit=[dict(r) for r in con.execute('SELECT seq,event_type,ref_id,at,payload_sha256 FROM audit ORDER BY seq')]; row=con.execute("SELECT value FROM meta WHERE key='manifest_sha256'").fetchone(); body={'schema':EXPORT_SCHEMA,'manifest_sha256':None if row is None else row[0],'assets':assets,'grants':grants,'placements':placements,'audit':audit}; body['snapshot_sha256']=sha256_bytes(canonical_bytes(body)); return body
def snapshot(path):
    con=connect(path)
    try:
        con.execute('BEGIN')
        return _snapshot_from_connection(con)
    finally:
        if con.in_transaction: con.execute('ROLLBACK')
        con.close()
