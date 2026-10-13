"""Offline demo of authenticated Muse readiness; fixture signer only."""
from __future__ import annotations
import hashlib, hmac, json, os
from .core import MUSE_REGISTRY_SCHEMA, MUSE_TRUST_KEY_ENV, acquire, begin_send, intent_fingerprint

KEY="synthetic-demo-muse-trust-key-material"
INTENT={"counterparty_key":"example.com","route_key":"email:sales@example.com","thread_key":"gmail:demo-thread","purpose_key":"paid-pilot-followup"}
CLAIMANT={"claimant_id":"demo-seat","session_id":"demo-session"}

def canon(v): return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)
def fixture_registry():
    receipt={"receipt_id":"demo-muse-r1","request_key":"demo-muse-q1","intent_fingerprint":intent_fingerprint(INTENT),
             "selected_claimant_id":CLAIMANT["claimant_id"],"selected_session_id":CLAIMANT["session_id"],"lease_generation":1,
             "decision":"SELECTED","arbitrated_at":"2026-09-17T03:14:59Z","expires_at":"2026-09-17T03:25:00Z",
             "source_ref":"fixture://muse/demo-selection","source_sha256":hashlib.sha256(b"synthetic-muse-selection").hexdigest()}
    body={"schema":MUSE_REGISTRY_SCHEMA,"generated_at":"2026-09-17T03:15:00Z","receipts":[receipt]}
    return {**body,"signature_hmac_sha256":hmac.new(KEY.encode(),canon(body).encode(),hashlib.sha256).hexdigest()}

os.environ[MUSE_TRUST_KEY_ENV]=KEY
waiting=acquire(intent=INTENT,claimant=CLAIMANT,now="2026-09-17T03:15:00Z",ttl_s=600,muse=None)
ready=acquire(intent=INTENT,claimant=CLAIMANT,now="2026-09-17T03:15:00Z",ttl_s=600,muse=fixture_registry())
fenced=begin_send(lease=ready["lease"],body_sha256=hashlib.sha256(b"demo body bytes").hexdigest(),provider="gmail",now="2026-09-17T03:16:00Z")
print(json.dumps({"without_authenticated_muse":waiting,"with_authenticated_muse":ready,"fenced_attempt":fenced,
                  "note":"No Muse/provider network call occurred. The demo signer exists only in this fixture module."},indent=2,sort_keys=True))
