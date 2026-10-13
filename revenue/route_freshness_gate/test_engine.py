#!/usr/bin/env python3
from __future__ import annotations
import json, subprocess, sys, tempfile, unittest
from pathlib import Path
from revenue.route_freshness_gate.engine import GateInputError, compile_packet, parse_json_text, render_markdown, verify_packet
A="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
B="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
C="cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
D="dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
E="eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
F="ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
EVAL="2026-09-16T18:00:00Z"
PAST="2026-09-16T17:00:00Z"
EARLIER="2026-09-16T16:00:00Z"
FUTURE="2026-09-16T19:00:00Z"
def base_packet(**overrides):
    packet={"schema_version":1,"evaluated_at":EVAL,"organization_digest":A,"route":{"route_identity_digest":B,"route_kind":"EMAIL","route_state":"LIVE","purpose_generation_digest":C,"alias_digests":[D]},"source":{"authority_class":"PRIMARY_SYSTEM","observed_at":EARLIER,"current_through":EVAL,"source_digest":E},"provider_history":[],"company_prior_touches":[],"muse_receipt_digest":None}
    packet.update(overrides)
    return packet
def ev(eid,kind,when,digest,route=B,resolves=None):
    return {"event_id":eid,"kind":kind,"occurred_at":when,"event_digest":digest,"resolves_event_id":resolves,"purpose_generation_digest":C,"route_identity_digest":route}
class Tests(unittest.TestCase):
    def test_ready(self):
        packet=compile_packet(base_packet()); self.assertEqual(packet["decision"],"READY_FOR_MUSE_CENSUS"); self.assertFalse(packet["send_authorized"]); verify_packet(packet); self.assertIn("READY_FOR_MUSE_CENSUS", render_markdown(packet))
    def test_hard_dnr(self):
        self.assertEqual(compile_packet(base_packet(provider_history=[ev("dnr-1","HARD_DNR",PAST,F)]))["decision"],"HARD_DNR")
    def test_bounce(self):
        self.assertEqual(compile_packet(base_packet(provider_history=[ev("bounce-1","BOUNCE",PAST,F,D)]))["decision"],"DEAD_ROUTE")
    def test_auto_ack_no_mask(self):
        self.assertEqual(compile_packet(base_packet(provider_history=[ev("bounce-1","BOUNCE",EARLIER,E), ev("ack-1","AUTO_ACK",PAST,F,resolves="bounce-1")]))["decision"],"DEAD_ROUTE")
    def test_ambiguous(self):
        self.assertEqual(compile_packet(base_packet(provider_history=[ev("amb-1","AMBIGUOUS",PAST,F)]))["decision"],"HOLD_PROVIDER_AMBIGUOUS")
    def test_ambiguous_resolved(self):
        self.assertEqual(compile_packet(base_packet(provider_history=[ev("amb-1","AMBIGUOUS",EARLIER,E), ev("hum-1","HUMAN_REPLY",PAST,F,resolves="amb-1")]))["decision"],"READY_FOR_MUSE_CENSUS")
    def test_prior_touch(self):
        other="1111111111111111111111111111111111111111111111111111111111111111"
        raw=base_packet(company_prior_touches=[{"touch_id":"touch-other","occurred_at":PAST,"touch_digest":F,"route_identity_digest":other,"purpose_generation_digest":C,"current":True}])
        self.assertEqual(compile_packet(raw)["decision"],"HOLD_COMPANY_PRIOR_TOUCH")
    def test_human_reopen(self):
        other="1111111111111111111111111111111111111111111111111111111111111111"
        raw=base_packet(provider_history=[ev("hum-1","HUMAN_REPLY",PAST,E)], company_prior_touches=[{"touch_id":"touch-other","occurred_at":EARLIER,"touch_digest":F,"route_identity_digest":other,"purpose_generation_digest":C,"current":True}])
        self.assertEqual(compile_packet(raw)["decision"],"READY_FOR_MUSE_CENSUS")
    def test_stale(self):
        raw=base_packet(); raw["source"]["current_through"]=PAST; self.assertEqual(compile_packet(raw)["decision"],"HOLD_STALE_ROUTE")
    def test_muse_no_promote(self):
        raw=base_packet(); raw["source"]["current_through"]=PAST; raw["muse_receipt_digest"]=F
        packet=compile_packet(raw); self.assertEqual(packet["decision"],"HOLD_STALE_ROUTE"); self.assertTrue(any("trace metadata" in r for r in packet["reasons"]))
    def test_historical(self):
        self.assertEqual(compile_packet(base_packet(), historical=True)["decision"],"HOLD_STALE_ROUTE")
    def test_collapse(self):
        event=ev("sent-1","SENT",PAST,F); self.assertEqual(compile_packet(base_packet(provider_history=[event, dict(event)]))["event_ids"],["sent-1"])
    def test_conflict(self):
        event=ev("sent-1","SENT",PAST,F); other=dict(event); other["event_digest"]=E
        with self.assertRaises(GateInputError):
            compile_packet(base_packet(provider_history=[event, other]))
    def test_future(self):
        with self.assertRaises(GateInputError):
            compile_packet(base_packet(provider_history=[ev("sent-1","SENT",FUTURE,F)]))
    def test_bool_schema(self):
        raw=base_packet(); raw["schema_version"]=True
        with self.assertRaises(GateInputError):
            compile_packet(raw)
    def test_dup_keys(self):
        with self.assertRaises(GateInputError):
            parse_json_text('{"schema_version":1,"schema_version":1}')
    def test_emailish(self):
        with self.assertRaises(GateInputError):
            compile_packet(base_packet(provider_history=[ev("user@example.com","SENT",PAST,F)]))
    def test_tamper(self):
        packet=compile_packet(base_packet()); packet["decision"]="HARD_DNR"
        with self.assertRaises(GateInputError):
            verify_packet(packet)
    def test_cli(self):
        engine=Path(__file__).resolve().parent/"engine.py"; root=Path(__file__).resolve().parents[2]; fixture=base_packet(); fixture["route"]["alias_digests"]=[]
        with tempfile.TemporaryDirectory() as tmp:
            inp=Path(tmp)/"in.json"; out=Path(tmp)/"out.json"; md=Path(tmp)/"out.md"
            inp.write_text(json.dumps(fixture), encoding="utf-8")
            compiled=subprocess.run([sys.executable,str(engine),"compile","--input",str(inp),"--output",str(out),"--markdown",str(md)],capture_output=True,text=True,cwd=str(root))
            self.assertEqual(compiled.returncode,0,compiled.stderr)
            verified=subprocess.run([sys.executable,str(engine),"verify","--input",str(out)],capture_output=True,text=True,cwd=str(root))
            self.assertEqual(verified.returncode,0,verified.stderr); self.assertIn("OK", verified.stdout)
if __name__=="__main__":
    unittest.main()
