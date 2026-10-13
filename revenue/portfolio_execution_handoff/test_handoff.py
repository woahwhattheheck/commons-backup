import copy
import json
import unittest
from hashlib import sha256

from revenue.opportunity_portfolio.portfolio import compile_portfolio
from revenue.portfolio_execution_handoff.handoff import (
    HandoffError, SCHEMA, compile_handoff, render_markdown, verify_receipt,
)

D="a"*64
E="b"*64
F="c"*64

def opp(oid="o1", owner="AVAILABLE", seat=None, amount=10000, group=None):
    return {
        "id":oid,"title":"Meaningful work","source":{"ref":"source:1","digestSha256":D,"observedAt":"2026-09-13T09:00:00Z"},
        "freshUntil":"2026-09-14T09:00:00Z","deadline":"2026-09-15T09:00:00Z",
        "eligibility":{"status":"ELIGIBLE","evidenceSha256":E},
        "value":{"currency":"USD","amountMinor":amount,"probabilityBps":5000,"probabilityEvidenceSha256":F},
        "capacity":{"seat":1},"owner":{"status":owner,"seat":seat},"blockers":[],"dependsOn":[],
        "exclusiveGroup":group,"labels":[],
    }

def portfolio(*items, actor="ZKUR-T9W3"):
    return compile_portfolio({
        "schema":"commons-opportunity-portfolio/v1","actorSeat":actor,
        "opportunities":list(items),"capacities":{"seat":4},"currencyPriority":["USD"],
    },trusted_as_of="2026-09-13T10:00:00Z")

def ref(ts="1789294053.483199", digest=D):
    return {"kind":"SLACK_MESSAGE","ref":f"slack://C0BTRNE6Y58/{ts}","evidenceSha256":digest}

def handoff(oid="o1", owner="ZKUR-T9W3"):
    return {
      "opportunityId":oid,"ownerSeat":owner,
      "custody":{"state":"ACTIVE","claim":ref(),"claimedAt":"2026-09-13T10:01:00Z","generation":1},
      "nextAction":{"class":"BUILD","summary":"Build the selected bounded product","destination":ref("1789294054.483200",E),"evidenceSha256":F},
      "expiresAt":"2026-09-13T18:00:00Z",
    }

def req(p=None, hs=None):
    return {"schema":SCHEMA,"portfolioReceipt":p or portfolio(opp()),"handoffs":hs if hs is not None else [handoff()]}

class HandoffTests(unittest.TestCase):
    def good(self):
        return compile_handoff(req(), trusted_as_of="2026-09-13T10:02:00Z")

    def test_ready(self):
        self.assertEqual(self.good()["authority"]["strongestState"],"READY_FOR_OWNER_HANDOFF_REVIEW")
    def test_all_external_authority_false(self):
        r=self.good()
        for k,v in r["authority"].items():
            if k!="strongestState": self.assertIs(v,False)
    def test_verify(self): self.assertTrue(verify_receipt(self.good()))
    def test_verify_current(self): self.assertTrue(verify_receipt(self.good(),trusted_as_of="2026-09-13T12:00:00Z"))
    def test_expired_current_rejected(self):
        with self.assertRaises(HandoffError): verify_receipt(self.good(),trusted_as_of="2026-09-13T19:00:00Z")
    def test_markdown_authority(self):
        text=render_markdown(self.good()); self.assertIn("External action authority: **false**",text)
    def test_markdown_owner(self): self.assertIn("ZKUR-T9W3",render_markdown(self.good()))
    def test_tamper_digest(self):
        r=self.good(); r["handoffs"][0]["ownerSeat"]="evil"
        with self.assertRaises(HandoffError): verify_receipt(r)
    def test_wrong_input_digest(self):
        r=self.good(); r["inputDigestSha256"]="0"*64; u=dict(r); u.pop("receiptDigestSha256"); r["receiptDigestSha256"]=sha256(json.dumps(u,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        with self.assertRaises(HandoffError): verify_receipt(r)
    def test_portfolio_tamper(self):
        p=portfolio(opp()); p["portfolio"]=[]
        with self.assertRaises(HandoffError): compile_handoff(req(p),trusted_as_of="2026-09-13T10:02:00Z")
    def test_unselected_handoff_holds(self):
        p=portfolio(opp("o1",amount=10000,group="one"),opp("o2",amount=1000,group="one")); r=compile_handoff(req(p,[handoff("o1"),handoff("o2")]),trusted_as_of="2026-09-13T10:02:00Z")
        self.assertIn("UNSELECTED_HANDOFF:o2",r["globalHolds"])
    def test_missing_handoff_holds(self):
        p=portfolio(opp("o1"),opp("o2")); r=compile_handoff(req(p,[handoff("o1")]),trusted_as_of="2026-09-13T10:02:00Z")
        self.assertIn("MISSING_HANDOFF:o2",r["globalHolds"])
    def test_exact_complete_coverage_ready(self):
        p=portfolio(opp("o1"),opp("o2")); r=compile_handoff(req(p,[handoff("o2"),handoff("o1")]),trusted_as_of="2026-09-13T10:02:00Z")
        self.assertEqual(r["authority"]["strongestState"],"READY_FOR_OWNER_HANDOFF_REVIEW")
    def test_order_invariant(self):
        p=portfolio(opp("o1"),opp("o2"))
        a=compile_handoff(req(p,[handoff("o1"),handoff("o2")]),trusted_as_of="2026-09-13T10:02:00Z")
        b=compile_handoff(req(p,[handoff("o2"),handoff("o1")]),trusted_as_of="2026-09-13T10:02:00Z")
        self.assertEqual(a["receiptDigestSha256"],b["receiptDigestSha256"])
    def test_duplicate_id_rejected(self):
        with self.assertRaises(HandoffError): compile_handoff(req(hs=[handoff(),handoff()]),trusted_as_of="2026-09-13T10:02:00Z")
    def test_released_custody_holds(self):
        h=handoff();h["custody"]["state"]="RELEASED";r=compile_handoff(req(hs=[h]),trusted_as_of="2026-09-13T10:02:00Z")
        self.assertIn("CUSTODY_NOT_ACTIVE",r["handoffs"][0]["reasons"])
    def test_claim_future_holds(self):
        h=handoff();h["custody"]["claimedAt"]="2026-09-13T11:00:00Z";r=compile_handoff(req(hs=[h]),trusted_as_of="2026-09-13T10:02:00Z")
        self.assertIn("CLAIM_IN_FUTURE",r["handoffs"][0]["reasons"])
    def test_expired_holds(self):
        h=handoff();h["expiresAt"]="2026-09-13T10:01:30Z";r=compile_handoff(req(hs=[h]),trusted_as_of="2026-09-13T10:02:00Z")
        self.assertIn("HANDOFF_EXPIRED",r["handoffs"][0]["reasons"])
    def test_long_lifetime_holds(self):
        h=handoff();h["expiresAt"]="2026-09-14T10:02:00Z";r=compile_handoff(req(hs=[h]),trusted_as_of="2026-09-13T10:02:00Z")
        self.assertIn("HANDOFF_LIFETIME_EXCEEDS_24H",r["handoffs"][0]["reasons"])
    def test_expiry_after_deadline_holds(self):
        h=handoff();h["expiresAt"]="2026-09-15T10:00:00Z";r=compile_handoff(req(hs=[h]),trusted_as_of="2026-09-13T10:02:00Z")
        self.assertIn("HANDOFF_EXPIRES_AFTER_DEADLINE",r["handoffs"][0]["reasons"])
    def test_stale_source_holds(self):
        o=opp();o["freshUntil"]="2026-09-13T10:01:00Z";p=portfolio(o);r=compile_handoff(req(p),trusted_as_of="2026-09-13T10:02:00Z")
        self.assertIn("SOURCE_STALE",r["handoffs"][0]["reasons"])
    def test_closed_deadline_holds(self):
        o=opp();o["deadline"]="2026-09-13T10:02:00Z";p=portfolio(o);r=compile_handoff(req(p),trusted_as_of="2026-09-13T10:02:00Z")
        self.assertIn("DEADLINE_CLOSED",r["handoffs"][0]["reasons"])
    def test_owned_this_seat_must_match(self):
        p=portfolio(opp(owner="OWNED_BY_THIS_SEAT",seat="ZKUR-T9W3"))
        h=handoff(owner="OTHER")
        r=compile_handoff(req(p,[h]),trusted_as_of="2026-09-13T10:02:00Z")
        self.assertIn("OWNER_MISMATCH",r["handoffs"][0]["reasons"])
    def test_owned_this_seat_ready_when_match(self):
        p=portfolio(opp(owner="OWNED_BY_THIS_SEAT",seat="ZKUR-T9W3"))
        r=compile_handoff(req(p,[handoff()]),trusted_as_of="2026-09-13T10:02:00Z")
        self.assertEqual(r["authority"]["strongestState"],"READY_FOR_OWNER_HANDOFF_REVIEW")
    def test_pii_email_rejected(self):
        h=handoff();h["nextAction"]["summary"]="email a@b.com"
        with self.assertRaises(HandoffError): compile_handoff(req(hs=[h]),trusted_as_of="2026-09-13T10:02:00Z")
    def test_secret_rejected(self):
        h=handoff();h["nextAction"]["summary"]="xoxb-"+"A"*30
        with self.assertRaises(HandoffError): compile_handoff(req(hs=[h]),trusted_as_of="2026-09-13T10:02:00Z")
    def test_mutable_ref_rejected(self):
        h=handoff();h["custody"]["claim"]["ref"]="https://github.com/o/r/tree/main"
        with self.assertRaises(HandoffError): compile_handoff(req(hs=[h]),trusted_as_of="2026-09-13T10:02:00Z")
    def test_bad_ref_kind_rejected(self):
        h=handoff();h["custody"]["claim"]["kind"]="URL"
        with self.assertRaises(HandoffError): compile_handoff(req(hs=[h]),trusted_as_of="2026-09-13T10:02:00Z")
    def test_zero_generation_rejected(self):
        h=handoff();h["custody"]["generation"]=0
        with self.assertRaises(HandoffError): compile_handoff(req(hs=[h]),trusted_as_of="2026-09-13T10:02:00Z")
    def test_bool_generation_rejected(self):
        h=handoff();h["custody"]["generation"]=True
        with self.assertRaises(HandoffError): compile_handoff(req(hs=[h]),trusted_as_of="2026-09-13T10:02:00Z")
    def test_unknown_field_rejected(self):
        h=handoff();h["admin"]=True
        with self.assertRaises(HandoffError): compile_handoff(req(hs=[h]),trusted_as_of="2026-09-13T10:02:00Z")
    def test_bad_action_class_rejected(self):
        h=handoff();h["nextAction"]["class"]="SEND"
        with self.assertRaises(HandoffError): compile_handoff(req(hs=[h]),trusted_as_of="2026-09-13T10:02:00Z")
    def test_trusted_time_cannot_precede_portfolio(self):
        with self.assertRaises(HandoffError): compile_handoff(req(),trusted_as_of="2026-09-13T09:59:59Z")
    def test_portfolio_authority_flip_rejected_even_with_rehash(self):
        p=portfolio(opp());p["authority"]["externalActionsAuthorized"]=True
        u=dict(p);u.pop("receiptDigestSha256");p["receiptDigestSha256"]=sha256(json.dumps(u,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        # Stub verifier accepts digest; our contract layer must still reject authority.
        with self.assertRaises(HandoffError): compile_handoff(req(p),trusted_as_of="2026-09-13T10:02:00Z")
    def test_receipt_binds_source_digest(self):
        self.assertEqual(self.good()["handoffs"][0]["sourceDigestSha256"],D)
    def test_receipt_binds_portfolio_digest(self):
        r=self.good();self.assertEqual(r["sourcePortfolio"]["receiptDigestSha256"],r["normalizedInput"]["portfolioReceipt"]["receiptDigestSha256"])

if __name__=="__main__":
    unittest.main()
