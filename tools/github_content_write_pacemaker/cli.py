#!/usr/bin/env python3
"""CLI for connector-native GitHub write pacing."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from .github_write_pacemaker import (
    AmbiguousOutcome, NoDispatchableMutation, PacemakerError,
    PacemakerStore, parse_json, read_regular_bytes,
)

def emit(value):
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))

def build_parser():
    p=argparse.ArgumentParser(prog="github-content-write-pacemaker")
    p.add_argument("--db",required=True,type=Path)
    s=p.add_subparsers(dest="command",required=True)
    s.add_parser("init")
    x=s.add_parser("enqueue"); x.add_argument("--intent",required=True,type=Path)
    x=s.add_parser("claim-next"); x.add_argument("--minimum-interval-seconds",type=int,default=1)
    x=s.add_parser("record-result"); x.add_argument("--key",required=True); x.add_argument("--attempt",required=True,type=int); x.add_argument("--classification",required=True,choices=("committed","rejected","rate_limited","ambiguous")); x.add_argument("--reason",required=True); x.add_argument("--provider-status",type=int); x.add_argument("--provider-receipt-sha256"); x.add_argument("--retry-at")
    x=s.add_parser("reconcile"); x.add_argument("--key",required=True); x.add_argument("--outcome",required=True,choices=("committed","rejected","retry")); x.add_argument("--observation-ref",required=True); x.add_argument("--observation-sha256",required=True)
    x=s.add_parser("inspect"); x.add_argument("--key",required=True)
    x=s.add_parser("export-intent"); x.add_argument("--key",required=True)
    s.add_parser("list"); s.add_parser("verify")
    return p

def main(argv=None):
    a=build_parser().parse_args(argv)
    try:
        store=PacemakerStore(a.db)
        if a.command=="init": emit(store.verify())
        elif a.command=="enqueue":
            r,replay=store.enqueue(parse_json(read_regular_bytes(a.intent))); emit({"receipt":r,"replay":replay})
        elif a.command=="claim-next": emit(store.claim_next(a.minimum_interval_seconds).envelope())
        elif a.command=="record-result": emit(store.record_result(a.key,attempt=a.attempt,classification=a.classification,reason=a.reason,provider_status=a.provider_status,provider_receipt_sha256=a.provider_receipt_sha256,retry_at=a.retry_at))
        elif a.command=="reconcile": emit(store.reconcile(a.key,outcome=a.outcome,observation_ref=a.observation_ref,observation_sha256=a.observation_sha256))
        elif a.command=="inspect": emit(store.inspect(a.key))
        elif a.command=="export-intent": emit(store.export_intent(a.key))
        elif a.command=="list": emit({"receipts":store.list_receipts()})
        elif a.command=="verify": emit(store.verify())
        return 0
    except NoDispatchableMutation as exc:
        result = {"state":"NO_DISPATCH","reason":str(exc)}
        if exc.retry_at is not None:
            result.update(retryAt=exc.retry_at, retryAfterSeconds=exc.retry_after_seconds)
        emit(result)
        return 4
    except AmbiguousOutcome as exc: emit({"state":"RECONCILE_REQUIRED","reason":str(exc)}); return 5
    except (PacemakerError,OSError) as exc: print(f"HOLD: {exc}",file=sys.stderr); return 2

if __name__=="__main__": raise SystemExit(main())
