from __future__ import annotations
import contextlib, hashlib, io, json, os, tempfile, unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock
import tools.outbound_send_guard.route_lifecycle as route
from tools.outbound_send_guard.route_lifecycle import RouteError, evaluate, main, parse_json_bytes

RECIPIENT="jonathan.e.jones@accenture.com"; MID="1a099d24be909146"; ASOF="2026-09-13T08:12:00Z"; SENT="2026-09-13T08:10:57Z"; SHA="a"*64

def ev(events=None,**kw):
    value={"schema_version":"outbound-route-lifecycle-evidence/v1","capture_id":"acc-001","recipient":RECIPIENT,"provider_message_id":MID,"sent_at":SENT,"as_of":ASOF,"complete":True,"next_cursor":None,"query_id":"gmail:dsn:accenture:001","events":events or []}; value.update(kw); return value

def event(event_id="d1",kind="dsn",at="2026-09-13T08:11:33Z",smtp=550,status="5.1.1",recipient=RECIPIENT,mid=MID,source="1a099d25494478fa"):
    return {"event_id":event_id,"kind":kind,"provider_message_id":mid,"recipient":recipient,"observed_at":at,"source_id":source,"source_sha256":SHA,"smtp_code":smtp if kind=="dsn" else None,"enhanced_status":status if kind=="dsn" else None}

class RouteLifecycleTests(unittest.TestCase):
    def decision(self, evidence): return evaluate(evidence)["payload"]
    def test_live_550_511_user_unknown_blocks_exact_route(self):
        p=self.decision(ev([event()])); self.assertEqual(p["decision"],"BLOCK_ROUTE"); self.assertIn("5.1.1", " ".join(p["reasons"])); self.assertFalse(p["same_route_resend_authorized"]); self.assertTrue(p["alternate_route_requires_independent_send_guard"]); self.assertFalse(p["side_effects_authorized"])
    def test_temporary_and_nonallowlisted_permanent_failures_hold(self):
        for smtp,status in [(421,"4.2.2"),(550,"5.7.1"),(552,"5.2.2")]:
            with self.subTest(status=status): self.assertEqual(self.decision(ev([event(smtp=smtp,status=status)]))["decision"],"HOLD_ROUTE")
    def test_delivered_and_unconfirmed_are_not_send_authority(self):
        p=self.decision(ev([event(kind="delivered")])); self.assertEqual(p["decision"],"DELIVERED"); self.assertFalse(p["same_route_resend_authorized"])
        p=self.decision(ev()); self.assertEqual(p["decision"],"UNCONFIRMED"); self.assertFalse(p["same_route_resend_authorized"])
    def test_complaint_and_unsubscribe_block(self):
        for kind in ("complaint","unsubscribe"):
            with self.subTest(kind=kind): self.assertEqual(self.decision(ev([event(kind=kind)]))["decision"],"BLOCK_ROUTE")
    def test_conflicting_delivered_and_failure_hold_unknown(self):
        p=self.decision(ev([event(),event(event_id="ok",kind="delivered",at="2026-09-13T08:11:40Z",source="delivered-1")])); self.assertEqual(p["decision"],"HOLD_ROUTE"); self.assertEqual(p["authority"],"unknown")
    def test_temporary_failure_then_strictly_later_delivery_settles_delivered(self):
        delayed=event(event_id="temp",at="2026-09-13T08:11:20Z",smtp=421,status="4.2.2",source="dsn-temp")
        delivered=event(event_id="ok",kind="delivered",at="2026-09-13T08:11:40Z",source="delivered-1")
        for rows in ([delayed,delivered],[delivered,delayed]):
            with self.subTest(order=[row["event_id"] for row in rows]):
                p=self.decision(ev(rows)); self.assertEqual(p["decision"],"DELIVERED"); self.assertEqual(p["authority"],"complete"); self.assertIn("strictly postdates", " ".join(p["reasons"]))
                self.assertFalse(p["same_route_resend_authorized"]); self.assertTrue(p["alternate_route_requires_independent_send_guard"]); self.assertFalse(p["side_effects_authorized"])
    def test_temporary_failure_at_or_after_delivery_holds(self):
        delivered=event(event_id="ok",kind="delivered",at="2026-09-13T08:11:30Z",source="delivered-1")
        for at in ("2026-09-13T08:11:30Z","2026-09-13T08:11:40Z"):
            with self.subTest(at=at):
                delayed=event(event_id="temp",at=at,smtp=421,status="4.2.2",source="dsn-temp")
                p=self.decision(ev([delivered,delayed])); self.assertEqual(p["decision"],"HOLD_ROUTE"); self.assertEqual(p["authority"],"unknown")
    def test_recipient_intent_block_survives_delivery_in_either_order(self):
        delivered=event(event_id="ok",kind="delivered",at="2026-09-13T08:11:30Z",source="delivered-1")
        for kind,at in (("unsubscribe","2026-09-13T08:11:20Z"),("unsubscribe","2026-09-13T08:11:40Z"),("complaint","2026-09-13T08:11:40Z")):
            with self.subTest(kind=kind,at=at):
                intent=event(event_id=f"intent-{kind}-{at}",kind=kind,at=at,source=f"intent-{kind}")
                p=self.decision(ev([delivered,intent])); self.assertEqual(p["decision"],"BLOCK_ROUTE"); self.assertEqual(p["authority"],"complete"); self.assertIn("delivery evidence does not erase", " ".join(p["reasons"]))
    def test_nonallowlisted_permanent_failure_is_not_superseded_by_delivery(self):
        permanent=event(event_id="policy",at="2026-09-13T08:11:20Z",smtp=550,status="5.7.1",source="dsn-policy")
        delivered=event(event_id="ok",kind="delivered",at="2026-09-13T08:11:40Z",source="delivered-1")
        p=self.decision(ev([permanent,delivered])); self.assertEqual(p["decision"],"HOLD_ROUTE"); self.assertEqual(p["authority"],"unknown")
    def test_source_scope_and_time_fences(self):
        cases=[ev([event(mid="other")]),ev([event(recipient="other@example.com")]),ev([event(at="2026-09-13T08:10:00Z")]),ev([event(at="2026-09-13T08:12:01Z")]),ev(as_of="2026-09-13T08:09:00Z")]
        for case in cases:
            with self.subTest(case=case),self.assertRaises(RouteError): evaluate(case)
    def test_completion_and_pagination_fail_closed(self):
        for case in [ev(complete=False),ev(next_cursor="page2")]:
            with self.subTest(case=case),self.assertRaises(RouteError): evaluate(case)
    def test_smtp_and_enhanced_class_must_agree(self):
        for smtp,status in [(550,"4.1.1"),(421,"5.1.1"),(250,"2.0.0")]:
            with self.subTest(smtp=smtp,status=status),self.assertRaises(RouteError): evaluate(ev([event(smtp=smtp,status=status)]))
    def test_exact_duplicates_collapse_conflicting_event_ids_reject(self):
        row=event(); p=self.decision(ev([row,deepcopy(row)])); self.assertEqual(p["exact_duplicates_collapsed"],1); self.assertEqual(p["event_refs"],["dsn:d1"])
        other=deepcopy(row); other["enhanced_status"]="5.7.1"
        with self.assertRaisesRegex(RouteError,"conflicting rows"): evaluate(ev([row,other]))
    def test_non_dsn_cannot_smuggle_failure_codes(self):
        row=event(kind="delivered"); row["smtp_code"]=550; row["enhanced_status"]="5.1.1"
        with self.assertRaises(RouteError): evaluate(ev([row]))
    def test_strict_json_types_unknown_fields_and_digest_stability(self):
        with self.assertRaises(RouteError): evaluate(ev(complete=1))
        bad=ev(); bad["mystery"]=1
        with self.assertRaises(RouteError): evaluate(bad)
        with self.assertRaises(RouteError): parse_json_bytes(b'{"schema_version":"x","schema_version":"y"}',"evidence")
        first=evaluate(ev([event()])); second=evaluate(deepcopy(ev([event()]))); self.assertEqual(first,second); self.assertEqual(len(first["receipt_sha256"]),64)
    def test_source_hash_is_bound(self):
        raw=json.dumps(ev([event()]),indent=2).encode(); obj=parse_json_bytes(raw,"evidence"); r=evaluate(obj,source_sha256=hashlib.sha256(raw).hexdigest()); self.assertEqual(r["payload"]["source_evidence_sha256"],hashlib.sha256(raw).hexdigest())
    def test_cli_semantic_exit_codes(self):
        expected=[(ev([event()]),5),(ev([event(smtp=421,status="4.2.2")]),4),(ev([event(kind="delivered")]),0),(ev(),3)]
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for idx,(value,code) in enumerate(expected):
                inp=root/f"in{idx}.json"; out=root/f"out{idx}.json"; inp.write_text(json.dumps(value)); self.assertEqual(main(["--evidence",str(inp),"--out",str(out)]),code); self.assertTrue(out.exists())
    def test_cli_direct_hardlink_symlink_aliases_preserve_input(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); inp=root/"in.json"; inp.write_text(json.dumps(ev())); before=inp.read_bytes(); self.assertEqual(main(["--evidence",str(inp),"--out",str(inp)]),2); self.assertEqual(inp.read_bytes(),before)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); inp=root/"in.json"; out=root/"out.json"; inp.write_text(json.dumps(ev())); os.link(inp,out); before=inp.read_bytes(); self.assertEqual(main(["--evidence",str(inp),"--out",str(out)]),2); self.assertEqual(out.read_bytes(),before)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); inp=root/"in.json"; out=root/"out.json"; inp.write_text(json.dumps(ev()))
            try: out.symlink_to(inp)
            except OSError as exc: self.skipTest(f"symlink unavailable: {exc}")
            self.assertEqual(main(["--evidence",str(inp),"--out",str(out)]),2); self.assertTrue(out.is_symlink())
    def test_cli_replace_failure_preserves_old_output_and_cleans_stage(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); inp=root/"in.json"; out=root/"out.json"; inp.write_text(json.dumps(ev())); out.write_text("old\n")
            with mock.patch.object(route.os,"replace",side_effect=OSError("forced replace failure")),contextlib.redirect_stderr(io.StringIO()): code=main(["--evidence",str(inp),"--out",str(out)])
            self.assertEqual(code,2); self.assertEqual(out.read_text(),"old\n"); self.assertFalse(any(".stage-" in p.name for p in root.iterdir()))

if __name__=="__main__": unittest.main()
