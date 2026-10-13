from __future__ import annotations
from datetime import datetime, timezone
from . import gate

NOW=datetime(2026,9,17,19,0,0,tzinfo=timezone.utc)

def request(*,product="devin",model="swe-2",session_id=None,free_only=True):
    return{"schema":gate.REQUEST_SCHEMA,"provider":"cognition","account_id":"acct-redacted","product":product,"model":model,"session_id":session_id,"free_only":free_only}

def event(event_id,*,scope="MODEL",kind="ZERO_COST_CONFIRMED",amount=0,product="devin",model="swe-2",session_id=None,event_at="2026-09-17T18:30:00Z",observed_at="2026-09-17T18:31:00Z",valid_until="2026-09-18T18:30:00Z",authority="PROVIDER_AUTHENTICATED"):
    if scope=="ACCOUNT":product=model=session_id=None
    elif scope=="PRODUCT":model=session_id=None
    elif scope=="MODEL":session_id=None
    if kind in("CHARGE_PAID","CHARGE_FAILED"):valid_until=None
    return{"event_id":event_id,"scope":scope,"provider":"cognition","account_id":"acct-redacted","product":product,"model":model,"session_id":session_id,"kind":kind,"amount_minor":amount,"currency":"USD","event_at_utc":event_at,"observed_at_utc":observed_at,"valid_until_utc":valid_until,"source_ref":f"provider:redacted:{event_id}","source_sha256":(event_id[0].lower() if event_id[0].lower() in"abcdef" else"a")*64,"authority":authority}

def snapshot(events,req=None):return{"schema":gate.SNAPSHOT_SCHEMA,"request":req or request(),"evidence":events}
