from __future__ import annotations
import contextlib, hashlib, io, json, os, tempfile, unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock
from tools.outbound_send_guard.evidence_compiler import CompileError, compile_evidence, compile_with_receipt, main, parse_json_bytes
from tools.outbound_send_guard.guard import evaluate

RECIPIENT="matt@scientist.com"; OFFER="scientist-clinical-lab-sow-result-evidence-reconciler-01"; AS_OF="2026-09-13T07:19:30Z"
def mailbox(messages=None,**kw):
 v={"schema_version":"outbound-mailbox-export/v1","capture_id":"cap-001","recipient":RECIPIENT,"as_of":AS_OF,"collected_at":"2026-09-13T07:19:40Z","query_id":"gmail:bidir:scientist:001","complete":True,"next_page_token":None,"messages":messages or []}; v.update(kw); return v
def slack(events=None,**kw):
 v={"schema_version":"outbound-slack-export/v1","capture_id":"cap-001","recipient":RECIPIENT,"as_of":AS_OF,"collected_at":"2026-09-13T07:19:50Z","query_id":"slack:recipient:scientist:001","complete":True,"next_cursor":None,"events":events or []}; v.update(kw); return v
def mail(message_id="m1",direction="outbound",at="2026-09-13T07:10:58Z",offer_id=None,state=None,counterparty=RECIPIENT):
 return {"message_id":message_id,"direction":direction,"counterparty":counterparty,"observed_at":at,"provider_state":state or ("sent" if direction=="outbound" else "received"),"offer_id":offer_id}
def event(event_id="s1",kind="sent",at="2026-09-13T07:11:00Z",offer_id=None,provider_message_id=None,recipient=RECIPIENT):
 return {"event_id":event_id,"kind":kind,"recipient":recipient,"observed_at":at,"offer_id":offer_id,"provider_message_id":provider_message_id}
def intent(): return {"schema_version":"outbound-send-intent/v1","intent_id":"i1","recipient":RECIPIENT,"offer_id":OFFER,"requested_at":"2026-09-13T07:20:00Z","route_kind":"email"}

class EvidenceCompilerTests(unittest.TestCase):
 def test_guard_compatible_clean_and_live_incident(self):
  evidence,summary=compile_evidence(mailbox(),slack()); self.assertEqual(evidence["schema_version"],"outbound-send-evidence/v1"); self.assertEqual(summary["capture_id"],"cap-001"); self.assertEqual(evaluate(intent(),evidence)["payload"]["decision"],"ALLOW_NEW")
  evidence,_=compile_evidence(mailbox([mail(message_id="1a0999adcef566f2",offer_id=OFFER)]),slack()); self.assertEqual(evaluate(intent(),evidence)["payload"]["decision"],"DO_NOT_RESEND")
 def test_provider_join_valid_and_conflicts_fail(self):
  evidence,_=compile_evidence(mailbox([mail(offer_id=OFFER)]),slack([event(provider_message_id="m1",offer_id=OFFER)])); self.assertEqual(evidence["slack"]["events"][0]["provider_message_id"],"m1")
  cases=[(mailbox(),slack([event(provider_message_id="missing")]),"absent from complete outbound"),(mailbox([mail(direction="inbound")]),slack([event(provider_message_id="m1")]),"absent from complete outbound"),(mailbox([mail(offer_id="a")]),slack([event(provider_message_id="m1",offer_id="b")]),"conflicts with provider offer_id")]
  for mb,sl,msg in cases:
   with self.subTest(msg=msg),self.assertRaisesRegex(CompileError,msg): compile_evidence(mb,sl)
 def test_completion_and_pagination_fail_closed(self):
  cases=[(mailbox(complete=False),slack(),"mailbox export is incomplete"),(mailbox(),slack(complete=False),"slack export is incomplete"),(mailbox(next_page_token="p2"),slack(),"next_page_token must be null"),(mailbox(),slack(next_cursor="c2"),"next_cursor must be null")]
  for mb,sl,msg in cases:
   with self.subTest(msg=msg),self.assertRaisesRegex(CompileError,msg): compile_evidence(mb,sl)
 def test_capture_scope_and_boundary_must_match(self):
  cases=[(mailbox(),slack(capture_id="other"),"capture_id must match"),(mailbox(),slack(recipient="other@example.com"),"recipient scopes must match"),(mailbox(),slack(as_of="2026-09-13T07:19:29Z"),"as_of boundaries must match")]
  for mb,sl,msg in cases:
   with self.subTest(msg=msg),self.assertRaisesRegex(CompileError,msg): compile_evidence(mb,sl)
 def test_rows_cannot_escape_scope_or_boundary(self):
  cases=[(mailbox([mail(at="2026-09-13T07:19:31Z")]),slack()),(mailbox(),slack([event(at="2026-09-13T07:19:31Z")])),(mailbox([mail(counterparty="other@example.com")]),slack()),(mailbox(),slack([event(recipient="other@example.com")]))]
  for mb,sl in cases:
   with self.subTest(mb=mb,sl=sl),self.assertRaises(CompileError): compile_evidence(mb,sl)
 def test_provider_states_and_slack_provider_field_are_strict(self):
  cases=[(mailbox([mail(state="failed")]),slack()),(mailbox([mail(direction="inbound",state="sent")]),slack()),(mailbox(),slack([event(kind="lead",provider_message_id="m1")]))]
  for mb,sl in cases:
   with self.subTest(mb=mb,sl=sl),self.assertRaises(CompileError): compile_evidence(mb,sl)
 def test_exact_duplicates_collapse_conflicts_reject(self):
  r=mail(message_id="dup",offer_id=OFFER); evidence,summary=compile_evidence(mailbox([r,deepcopy(r)]),slack()); self.assertEqual(len(evidence["mailbox"]["messages"]),1); self.assertEqual(summary["mailbox_exact_duplicates_collapsed"],1)
  r=event(event_id="dup",kind="lead"); evidence,summary=compile_evidence(mailbox(),slack([r,deepcopy(r)])); self.assertEqual(len(evidence["slack"]["events"]),1); self.assertEqual(summary["slack_exact_duplicates_collapsed"],1)
  a=mail(message_id="dup"); b=deepcopy(a); b["offer_id"]="changed"
  with self.assertRaisesRegex(CompileError,"conflicting rows"): compile_evidence(mailbox([a,b]),slack())
  a=event(event_id="dup",kind="lead"); b=deepcopy(a); b["kind"]="hard_dnr"
  with self.assertRaisesRegex(CompileError,"conflicting rows"): compile_evidence(mailbox(),slack([a,b]))
 def test_strict_types_fields_times_and_consumer_bounds(self):
  bad=[(mailbox(complete=1),slack()),(mailbox(collected_at="2026-09-13T07:19:00Z"),slack()),(mailbox(query_id="q"*201),slack())]
  x=mailbox(); x["mystery"]=True; bad.append((x,slack()))
  for mb,sl in bad:
   with self.subTest(mb=mb),self.assertRaises(CompileError): compile_evidence(mb,sl)
  with self.assertRaisesRegex(CompileError,"duplicate JSON object key"): parse_json_bytes(b'{"schema_version":"x","schema_version":"y"}',"mailbox")
 def test_policy_strict_and_propagated(self):
  evidence,_=compile_evidence(mailbox(),slack(),{"cross_offer_cooldown_days":7,"max_evidence_age_seconds":60,"max_future_skew_seconds":5}); self.assertEqual(evidence["policy"]["cross_offer_cooldown_days"],7)
  with self.assertRaises(CompileError): compile_evidence(mailbox(),slack(),{"cross_offer_cooldown_days":True})
 def test_receipt_deterministic_and_binds_raw_sources(self):
  mb=json.dumps(mailbox(),indent=2).encode(); sl=json.dumps(slack(),separators=(",",":")).encode(); first=compile_with_receipt(mb,sl); self.assertEqual(first,compile_with_receipt(mb,sl)); evidence,receipt=first; self.assertFalse(receipt["payload"]["side_effects_authorized"]); self.assertEqual(receipt["payload"]["sources"]["mailbox_sha256"],hashlib.sha256(mb).hexdigest()); self.assertEqual(len(receipt["payload"]["evidence_sha256"]),64)
 def _paths(self,root):
  mb=root/"mailbox.json"; sl=root/"slack.json"; ev=root/"evidence.json"; rc=root/"receipt.json"; mb.write_text(json.dumps(mailbox())); sl.write_text(json.dumps(slack())); return mb,sl,ev,rc
 def test_cli_rejects_direct_output_output_hardlink_and_symlink_aliases(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); mb,sl,ev,rc=self._paths(root); before=mb.read_bytes(); self.assertEqual(main(["--mailbox",str(mb),"--slack",str(sl),"--evidence-out",str(mb),"--receipt-out",str(rc)]),2); self.assertEqual(mb.read_bytes(),before)
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); mb,sl,ev,rc=self._paths(root); self.assertEqual(main(["--mailbox",str(mb),"--slack",str(sl),"--evidence-out",str(ev),"--receipt-out",str(ev)]),2); self.assertFalse(ev.exists())
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); mb,sl,ev,rc=self._paths(root); os.link(mb,ev); before=mb.read_bytes(); self.assertEqual(main(["--mailbox",str(mb),"--slack",str(sl),"--evidence-out",str(ev),"--receipt-out",str(rc)]),2); self.assertEqual(ev.read_bytes(),before)
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); mb,sl,ev,rc=self._paths(root)
   try: ev.symlink_to(mb)
   except OSError as exc: self.skipTest(f"symlink unavailable: {exc}")
   self.assertEqual(main(["--mailbox",str(mb),"--slack",str(sl),"--evidence-out",str(ev),"--receipt-out",str(rc)]),2); self.assertTrue(ev.is_symlink())
 def test_cli_success_and_atomic_second_output_rollback(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); mb,sl,ev,rc=self._paths(root); mb.write_text(json.dumps(mailbox([mail(offer_id=OFFER)]))); self.assertEqual(main(["--mailbox",str(mb),"--slack",str(sl),"--evidence-out",str(ev),"--receipt-out",str(rc)]),0); self.assertEqual(json.loads(ev.read_text())["schema_version"],"outbound-send-evidence/v1"); self.assertFalse(any(".stage-" in p.name or ".backup-" in p.name for p in root.iterdir()))
  import tools.outbound_send_guard.evidence_compiler as compiler
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); mb,sl,ev,rc=self._paths(root); ev.write_text("old-evidence\n"); rc.write_text("old-receipt\n"); real=compiler.os.replace
   def fail(src,dst):
    if Path(dst)==rc and ".stage-" in Path(src).name: raise OSError("forced receipt publication failure")
    return real(src,dst)
   err=io.StringIO()
   with mock.patch.object(compiler.os,"replace",side_effect=fail),contextlib.redirect_stderr(err): code=compiler.main(["--mailbox",str(mb),"--slack",str(sl),"--evidence-out",str(ev),"--receipt-out",str(rc)])
   self.assertEqual(code,2); self.assertIn("forced receipt publication failure",err.getvalue()); self.assertEqual(ev.read_text(),"old-evidence\n"); self.assertEqual(rc.read_text(),"old-receipt\n"); self.assertFalse(any(".stage-" in p.name or ".backup-" in p.name for p in root.iterdir()))
if __name__=="__main__": unittest.main()
