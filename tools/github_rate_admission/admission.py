#!/usr/bin/env python3
"""Per-host GitHub admission ledger: stdlib SQLite, no network or credentials."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS gates (
    account TEXT NOT NULL, bucket TEXT NOT NULL, resource TEXT NOT NULL,
    kind TEXT NOT NULL, until_epoch INTEGER, strikes INTEGER NOT NULL,
    event_id TEXT NOT NULL, PRIMARY KEY(account, bucket, resource)
);
CREATE TABLE IF NOT EXISTS leases (
    operation_id TEXT PRIMARY KEY, account TEXT NOT NULL, bucket TEXT NOT NULL,
    resource TEXT NOT NULL, created_epoch INTEGER NOT NULL,
    lease_until INTEGER NOT NULL, state TEXT NOT NULL, outcome TEXT
);
CREATE TABLE IF NOT EXISTS observations (
    event_id TEXT PRIMARY KEY, account TEXT NOT NULL, bucket TEXT NOT NULL,
    resource TEXT NOT NULL, kind TEXT NOT NULL, observed_epoch INTEGER NOT NULL,
    operation_id TEXT
);
CREATE TABLE IF NOT EXISTS audits (
    id INTEGER PRIMARY KEY AUTOINCREMENT, when_epoch INTEGER NOT NULL,
    account TEXT NOT NULL, bucket TEXT NOT NULL, resource TEXT NOT NULL,
    action TEXT NOT NULL, reason TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS leases_current ON leases(account, bucket, state, lease_until);
"""


def connect(path: str):
    loc = Path(path)
    loc.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(loc), timeout=10, isolation_level=None)
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def classify(status: int | None, message: str = "", *, pre_provider: bool = False):
    if pre_provider:
        return "PRE_PROVIDER"
    msg = message.lower()
    if status == 401 or "bad credentials" in msg:
        return "AUTH_DENIED"
    if status == 429 or (status == 403 and any(x in msg for x in
            ("secondary rate limit", "abuse detection", "rate limit exceeded", "rate limiting"))):
        return "SECONDARY_LIMIT"
    if status == 403 and "resource not accessible by integration" in msg:
        return "APP_PERMISSION"
    if status == 403:
        return "UNCLASSIFIED_403"
    if status and status >= 500:
        return "SERVER_ERROR"
    return "OTHER"


def acquire(db, account: str, bucket: str, resource: str, operation_id: str,
            now: int, lease_seconds: int = 180, max_inflight: int = 4):
    """Atomic reservation. Reuse of an operation ID is always rejected, including after settlement."""
    if not all((account, bucket, resource, operation_id)) or lease_seconds < 1 or max_inflight < 1:
        raise ValueError("nonempty IDs, positive lease and capacity required")
    db.execute("BEGIN IMMEDIATE")
    try:
        # An expired reservation might have dispatched a provider write: do not replay it.
        db.execute("UPDATE leases SET state='unknown' WHERE state='reserved' AND lease_until<=?", (now,))
        old = db.execute("SELECT state, outcome FROM leases WHERE operation_id=?", (operation_id,)).fetchone()
        if old:
            result = {"admitted": False, "reason": "operation_id_already_seen", "state": old[0], "outcome": old[1]}
        else:
            gates = db.execute("SELECT resource, kind, until_epoch FROM gates WHERE account=? AND bucket=? AND (resource='*' OR resource=?)", (account,bucket,resource)).fetchall()
            blocked = [dict(resource=g[0], kind=g[1], until_epoch=g[2]) for g in gates if g[2] is None or g[2] > now]
            unknown = db.execute("SELECT operation_id FROM leases WHERE account=? AND bucket=? AND resource=? AND state='unknown' LIMIT 1", (account,bucket,resource)).fetchone()
            active_same = db.execute("SELECT operation_id FROM leases WHERE account=? AND bucket=? AND resource=? AND state='reserved' AND lease_until>? LIMIT 1", (account,bucket,resource,now)).fetchone()
            capacity = db.execute("SELECT count(*) FROM leases WHERE account=? AND bucket=? AND state='reserved' AND lease_until>?",(account,bucket,now)).fetchone()[0]
            if blocked:
                result = {"admitted":False,"reason":"gate_blocked","gates":blocked}
            elif unknown:
                result = {"admitted":False,"reason":"unreconciled_effect","operation_id":unknown[0]}
            elif active_same:
                result = {"admitted":False,"reason":"resource_reserved","operation_id":active_same[0]}
            elif capacity >= max_inflight:
                result = {"admitted":False,"reason":"account_capacity","inflight":capacity,"max_inflight":max_inflight}
            else:
                expires = now+lease_seconds
                db.execute("INSERT INTO leases VALUES (?,?,?,?,?,?,?,NULL)", (operation_id,account,bucket,resource,now,expires,"reserved"))
                result = {"admitted":True,"operation_id":operation_id,"lease_until":expires,"inflight":capacity+1,"max_inflight":max_inflight}
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def observe(db, account: str, bucket: str, resource: str, event_id: str,
            now: int, status: int | None, message: str, pre_provider=False,
            retry_after: int = 0, operation_id: str | None = None):
    """Record a provider result once; do not infer write outcome from HTTP alone."""
    if not all((account,bucket,resource,event_id)) or retry_after < 0:
        raise ValueError("nonempty IDs and nonnegative Retry-After required")
    kind = classify(status,message,pre_provider=pre_provider)
    db.execute("BEGIN IMMEDIATE")
    try:
        original = db.execute("SELECT kind FROM observations WHERE event_id=?",(event_id,)).fetchone()
        if original:
            result = {"classification":original[0],"duplicate_event":True,"gate_updated":False}
        else:
            db.execute("INSERT INTO observations VALUES (?,?,?,?,?,?,?)", (event_id,account,bucket,resource,kind,now,operation_id))
            target = "*" if kind in ("SECONDARY_LIMIT", "AUTH_DENIED") else resource
            updated = kind in ("SECONDARY_LIMIT","AUTH_DENIED","APP_PERMISSION","UNCLASSIFIED_403")
            until = None
            if updated:
                old = db.execute("SELECT until_epoch,strikes FROM gates WHERE account=? AND bucket=? AND resource=?",(account,bucket,target)).fetchone()
                active_strikes = old[1] if old and (old[0] is None or old[0]>now) else 0
                strikes = active_strikes+1 if kind=="SECONDARY_LIMIT" else 1
                if kind=="SECONDARY_LIMIT":
                    hold = max(retry_after, min(300*(2**min(strikes-1,4)), 3600))
                    until = max(now+hold, old[0] if old and old[0] is not None else 0)
                db.execute("INSERT INTO gates VALUES (?,?,?,?,?,?,?) ON CONFLICT(account,bucket,resource) DO UPDATE SET kind=excluded.kind,until_epoch=excluded.until_epoch,strikes=excluded.strikes,event_id=excluded.event_id", (account,bucket,target,kind,until,strikes,event_id))
            result={"classification":kind,"duplicate_event":False,"gate_updated":updated,"scope":target if updated else None,"until_epoch":until}
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def settle(db, operation_id: str, outcome: str):
    """Settling a timeout as unknown fences this exact resource pending explicit reconciliation."""
    if outcome not in ("confirmed", "no-effect", "unknown"):
        raise ValueError("outcome must be confirmed, no-effect, or unknown")
    db.execute("BEGIN IMMEDIATE")
    try:
        row=db.execute("SELECT state FROM leases WHERE operation_id=?",(operation_id,)).fetchone()
        if not row:
            result={"updated":False,"reason":"operation_not_found"}
        elif row[0]=="settled":
            result={"updated":False,"reason":"already_settled"}
        else:
            state="unknown" if outcome=="unknown" else "settled"
            db.execute("UPDATE leases SET state=?,outcome=? WHERE operation_id=?",(state,outcome,operation_id))
            result={"updated":True,"operation_id":operation_id,"state":state,"outcome":outcome}
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def clear_gate(db, account: str, bucket: str, resource: str, reason: str, now: int):
    if len(reason.strip()) < 12:
        raise ValueError("explicit reconciliation reason of at least 12 characters required")
    db.execute("BEGIN IMMEDIATE")
    try:
        cur=db.execute("DELETE FROM gates WHERE account=? AND bucket=? AND resource=?",(account,bucket,resource))
        db.execute("INSERT INTO audits(when_epoch,account,bucket,resource,action,reason) VALUES(?,?,?,?,?,?)",(now,account,bucket,resource,"clear-gate",reason))
        db.commit()
        return {"cleared":bool(cur.rowcount),"resource":resource,"reason":reason}
    except Exception:
        db.rollback()
        raise


def status(db, account=None, bucket=None, now=None):
    now=int(time.time()) if now is None else now
    cond=[];args=[]
    if account:
        cond.append("account=?");args.append(account)
    if bucket:
        cond.append("bucket=?");args.append(bucket)
    wh=" WHERE "+" AND ".join(cond) if cond else ""
    rows=db.execute("SELECT account,bucket,resource,kind,until_epoch,strikes,event_id FROM gates"+wh,args).fetchall()
    active=[dict(zip(("account","bucket","resource","kind","until_epoch","strikes","event_id"),r)) for r in rows if r[4] is None or r[4]>now]
    rows=db.execute("SELECT operation_id,account,bucket,resource,lease_until,state,outcome FROM leases"+wh,args).fetchall()
    leases=[dict(zip(("operation_id","account","bucket","resource","lease_until","state","outcome"),r)) for r in rows if r[5]=="unknown" or (r[5]=="reserved" and r[4]>now)]
    return {"as_of_epoch":now,"active_gates":active,"open_leases":leases,"gate_count":len(active),"open_count":len(leases)}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",required=True,help="Same-host shared SQLite ledger path (NOT network/NFS WAL)")
    cmd=p.add_subparsers(dest="command",required=True)
    a=cmd.add_parser("acquire",help="Reserve before ANY external provider operation")
    for x in (a,):
        for key in ("account","bucket","resource","operation"):
            x.add_argument("--"+key,required=True)
    a.add_argument("--lease-seconds",type=int,default=180)
    a.add_argument("--max-inflight",type=int,default=4)
    a.add_argument("--now",type=int)
    o=cmd.add_parser("observe",help="Classify provider outcome, log and apply quota/permission fences")
    for key in ("account","bucket","resource","event"):
        o.add_argument("--"+key,required=True)
    o.add_argument("--http-status",type=int)
    o.add_argument("--message",default="")
    o.add_argument("--pre-provider",action="store_true")
    o.add_argument("--retry-after",type=int,default=0)
    o.add_argument("--operation")
    o.add_argument("--now",type=int)
    s=cmd.add_parser("settle",help="After provider readback: confirmed, definitive no-effect, or unknown")
    s.add_argument("--operation",required=True)
    s.add_argument("--outcome",required=True,choices=["confirmed","no-effect","unknown"])
    st=cmd.add_parser("status",help="Export outstanding guards and operation fences")
    st.add_argument("--account")
    st.add_argument("--bucket")
    st.add_argument("--now",type=int)
    c=cmd.add_parser("clear-gate",help="Manual verified repair only; audited")
    for key in ("account","bucket","resource","reason"):
        c.add_argument("--"+key,required=True)
    c.add_argument("--now",type=int)
    args=p.parse_args(argv)
    now=int(time.time()) if getattr(args,"now",None) is None else args.now
    db=connect(args.db)
    try:
        if args.command=="acquire":
            r=acquire(db,args.account,args.bucket,args.resource,args.operation,now,args.lease_seconds,args.max_inflight)
        elif args.command=="observe":
            r=observe(db,args.account,args.bucket,args.resource,args.event,now,args.http_status,args.message,args.pre_provider,args.retry_after,args.operation)
        elif args.command=="settle":
            r=settle(db,args.operation,args.outcome)
        elif args.command=="status":
            r=status(db,args.account,args.bucket,now)
        else:
            r=clear_gate(db,args.account,args.bucket,args.resource,args.reason,now)
        print(json.dumps(r,sort_keys=True))
        if args.command=="acquire" and not r["admitted"]:
            return 2
        return 0
    finally:
        db.close()

if __name__=="__main__":
    try:
        sys.exit(main())
    except (ValueError,sqlite3.DatabaseError) as exc:
        print(json.dumps({"error":str(exc)}),file=sys.stderr)
        sys.exit(1)