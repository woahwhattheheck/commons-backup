from __future__ import annotations
import copy
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from products.agent_toolcall_evidence_gate import engine, golden

NOW = golden.NOW


def setup():
    p, a, l, cases = golden.panel(); req = copy.deepcopy(cases[0][1])
    return p, req, a, l


def roots(p, a, l):
    return engine.canonical_sha(engine._normalize_policy(p)), engine.canonical_sha(engine._normalize_authority(a)), engine.ledger_head(l)


def eval_case(p, r, a, l, now=NOW):
    ps, aa, lh = roots(p, a, l)
    return engine.evaluate(p, r, a, l, expected_policy_sha256=ps, expected_authority_sha256=aa, expected_ledger_head=lh, _now=now)


class GateTests(unittest.TestCase):
    def test_golden_panel_exact_192_allow_48_hold(self):
        result = golden.run_panel()
        self.assertEqual(result["case_count"], 240); self.assertEqual(result["allowed"], 192); self.assertEqual(result["held"], 48)
        families = {"TOOL_ACTION_DISALLOWED", "ROLE_RESOURCE_MISMATCH", "RESTRICTED_DATA_EXPOSURE", "MISSING_APPROVAL", "BUDGET_RATE_BREACH", "REPLAY_COLLISION"}
        for family in families:
            self.assertEqual(sum(family in r["reasons"] for r in result["rows"]), 8)
        self.assertFalse(any(r["decision"] == engine.EXECUTE_ALLOWED and r["expected"] != "ALLOW" for r in result["rows"]))

    def test_good_read_allowed(self):
        p,r,a,l=setup(); receipt=eval_case(p,r,a,l); self.assertEqual(receipt["decision"], engine.EXECUTE_ALLOWED); self.assertFalse(receipt["authority_ceiling"]["external_mutation_performed"])

    def test_tool_action_disallowed(self):
        p,r,a,l=setup(); r["action"]="delete"; self.assertIn("TOOL_ACTION_DISALLOWED", eval_case(p,r,a,l)["reasons"])

    def test_role_resource_mismatch(self):
        p,r,a,l=setup(); r["resource"]="repo:workspace/x"; self.assertIn("ROLE_RESOURCE_MISMATCH", eval_case(p,r,a,l)["reasons"])

    def test_restricted_data_exposure(self):
        p,r,a,l=setup(); r["data_class"]="SECRET"; self.assertIn("RESTRICTED_DATA_EXPOSURE", eval_case(p,r,a,l)["reasons"])

    def test_agent_version_disallowed(self):
        p,r,a,l=setup(); r["agent_version"]="6.0"; self.assertIn("AGENT_VERSION_DISALLOWED", eval_case(p,r,a,l)["reasons"])

    def test_agent_role_disallowed(self):
        p,r,a,l=setup(); r["actor_role"]="admin"; self.assertIn("AGENT_ROLE_DISALLOWED", eval_case(p,r,a,l)["reasons"])

    def test_missing_approval(self):
        p,r,a,l=setup(); r.update(action="write", resource="repo:workspace/x", data_class="INTERNAL"); self.assertIn("MISSING_APPROVAL", eval_case(p,r,a,l)["reasons"])

    def test_valid_approval_allows(self):
        p,r,a,l=setup(); r.update(action="write", resource="repo:workspace/x", data_class="INTERNAL", estimated_cost_cents=20)
        aid="ap-special"; r["approval_ids"]=[aid]; a["approvals"].append({"approval_id": aid, "kind":"HUMAN_CHANGE", "scope_sha256":engine.request_scope_sha(r), "issued_at":"2026-09-17T08:00:00Z", "expires_at":"2026-09-17T10:00:00Z", "issuer":"owner"})
        self.assertEqual(eval_case(p,r,a,l)["decision"], engine.EXECUTE_ALLOWED)

    def test_approval_transplant_detected(self):
        p,r,a,l=setup(); r.update(action="write", resource="repo:workspace/x", data_class="INTERNAL", estimated_cost_cents=20)
        aid="ap-special"; r["approval_ids"]=[aid]; scope=engine.request_scope_sha(r); a["approvals"].append({"approval_id":aid,"kind":"HUMAN_CHANGE","scope_sha256":scope,"issued_at":"2026-09-17T08:00:00Z","expires_at":"2026-09-17T10:00:00Z","issuer":"owner"}); r["resource"]="repo:workspace/y"
        self.assertIn("APPROVAL_SCOPE_MISMATCH", eval_case(p,r,a,l)["reasons"])

    def test_expired_approval_missing(self):
        p,r,a,l=setup(); r.update(action="write", resource="repo:workspace/x", data_class="INTERNAL", estimated_cost_cents=20)
        aid="ap-special"; r["approval_ids"]=[aid]; a["approvals"].append({"approval_id":aid,"kind":"HUMAN_CHANGE","scope_sha256":engine.request_scope_sha(r),"issued_at":"2026-09-16T08:00:00Z","expires_at":"2026-09-16T10:00:00Z","issuer":"owner"})
        self.assertIn("MISSING_APPROVAL", eval_case(p,r,a,l)["reasons"])

    def test_budget_per_call_breach(self):
        p,r,a,l=setup(); r["estimated_cost_cents"]=21; self.assertIn("BUDGET_RATE_BREACH", eval_case(p,r,a,l)["reasons"])

    def test_rate_call_count_breach(self):
        p,r,a,l=setup(); p["rules"][0]["max_calls_per_window"]=1
        event={"schema":engine.EVENT_SCHEMA,"sequence":1,"prev_event_sha256":engine.GENESIS,"operation_key":"old-op","trace_id":"old-trace","request_sha256":"a"*64,"occurred_at":"2026-09-17T08:59:50Z","actor_role":"builder","tool":"repo","action":"read","resource":"repo:public/x","cost_cents":1,"outcome":"SENT"}; event["event_sha256"]=engine.canonical_sha(engine._event_body(event)); l["events"]=[event]
        self.assertIn("BUDGET_RATE_BREACH", eval_case(p,r,a,l)["reasons"])

    def test_window_cost_breach(self):
        p,r,a,l=setup(); p["rules"][0]["max_cost_cents_per_window"]=4
        self.assertIn("BUDGET_RATE_BREACH", eval_case(p,r,a,l)["reasons"])

    def test_replay_operation_key(self):
        p,r,a,l=setup(); event={"schema":engine.EVENT_SCHEMA,"sequence":1,"prev_event_sha256":engine.GENESIS,"operation_key":r["operation_key"],"trace_id":"other-trace","request_sha256":"a"*64,"occurred_at":"2026-09-17T08:50:00Z","actor_role":"builder","tool":"repo","action":"read","resource":"repo:public/x","cost_cents":1,"outcome":"SENT"}; event["event_sha256"]=engine.canonical_sha(engine._event_body(event)); l["events"]=[event]
        self.assertIn("REPLAY_COLLISION", eval_case(p,r,a,l)["reasons"])

    def test_replay_trace_id(self):
        p,r,a,l=setup(); event={"schema":engine.EVENT_SCHEMA,"sequence":1,"prev_event_sha256":engine.GENESIS,"operation_key":"other-op","trace_id":r["trace_id"],"request_sha256":"a"*64,"occurred_at":"2026-09-17T08:50:00Z","actor_role":"builder","tool":"repo","action":"read","resource":"repo:public/x","cost_cents":1,"outcome":"SENT"}; event["event_sha256"]=engine.canonical_sha(engine._event_body(event)); l["events"]=[event]
        self.assertIn("REPLAY_COLLISION", eval_case(p,r,a,l)["reasons"])

    def test_ledger_event_hash_tamper_rejected(self):
        p,r,a,l=setup(); e=engine.make_ledger_event(eval_case(p,r,a,l),r,outcome="SENT",occurred_at=NOW,sequence=1,prev_event_sha256=engine.GENESIS); e["cost_cents"]+=1; l["events"]=[e]
        with self.assertRaises(engine.GateError): roots(p,a,l)

    def test_ledger_chain_truncation_detected_by_retained_head(self):
        p,r,a,l=setup(); receipt=eval_case(p,r,a,l); e=engine.make_ledger_event(receipt,r,outcome="SENT",occurred_at=NOW,sequence=1,prev_event_sha256=engine.GENESIS); l["events"]=[e]; ps,aa,head=roots(p,a,l); l["events"]=[]
        with self.assertRaises(engine.GateError): engine.evaluate(p,r,a,l,expected_policy_sha256=ps,expected_authority_sha256=aa,expected_ledger_head=head,_now=NOW)

    def test_policy_tamper_against_retained_root_rejected(self):
        p,r,a,l=setup(); ps,aa,lh=roots(p,a,l); p["rules"][0]["max_cost_cents"]=999
        with self.assertRaises(engine.GateError): engine.evaluate(p,r,a,l,expected_policy_sha256=ps,expected_authority_sha256=aa,expected_ledger_head=lh,_now=NOW)

    def test_authority_tamper_against_retained_root_rejected(self):
        p,r,a,l=setup(); ps,aa,lh=roots(p,a,l); a["authority_id"]="changed"
        with self.assertRaises(engine.GateError): engine.evaluate(p,r,a,l,expected_policy_sha256=ps,expected_authority_sha256=aa,expected_ledger_head=lh,_now=NOW)

    def test_stale_policy_holds(self):
        p,r,a,l=setup(); self.assertIn("STALE_POLICY", eval_case(p,r,a,l,datetime(2026,10,2,tzinfo=timezone.utc))["reasons"])

    def test_policy_not_yet_effective_holds(self):
        p,r,a,l=setup(); self.assertIn("POLICY_NOT_YET_EFFECTIVE", eval_case(p,r,a,l,datetime(2026,8,31,tzinfo=timezone.utc))["reasons"])

    def test_stale_request_holds(self):
        p,r,a,l=setup(); r["requested_at"]="2026-09-17T08:00:00Z"; self.assertIn("STALE_REQUEST", eval_case(p,r,a,l)["reasons"])

    def test_future_request_holds(self):
        p,r,a,l=setup(); r["requested_at"]="2026-09-17T09:01:00Z"; self.assertIn("REQUEST_FROM_FUTURE", eval_case(p,r,a,l)["reasons"])

    def test_duplicate_json_rejected(self):
        with self.assertRaises(engine.GateError): engine.strict_loads(b'{"a":1,"a":2}')

    def test_nan_rejected(self):
        with self.assertRaises(engine.GateError): engine.strict_loads(b'{"a":NaN}')

    def test_bool_as_int_rejected(self):
        p,r,a,l=setup(); r["estimated_cost_cents"]=True
        with self.assertRaises(engine.GateError): eval_case(p,r,a,l)

    def test_unknown_request_key_rejected(self):
        p,r,a,l=setup(); r["execute_now"]=True
        with self.assertRaises(engine.GateError): eval_case(p,r,a,l)

    def test_policy_ambiguous_rules_hold(self):
        p,r,a,l=setup(); dup=copy.deepcopy(p["rules"][0]); dup["rule_id"]="read-public-2"; p["rules"].append(dup)
        self.assertIn("POLICY_RULE_AMBIGUOUS", eval_case(p,r,a,l)["reasons"])

    def test_make_event_requires_allowed_receipt(self):
        p,r,a,l=setup(); r["action"]="delete"; rec=eval_case(p,r,a,l)
        with self.assertRaises(engine.GateError): engine.make_ledger_event(rec,r,outcome="SENT",occurred_at=NOW,sequence=1,prev_event_sha256=engine.GENESIS)

    def test_make_event_binds_request(self):
        p,r,a,l=setup(); rec=eval_case(p,r,a,l); changed=copy.deepcopy(r); changed["resource"]="repo:public/other"
        with self.assertRaises(engine.GateError): engine.make_ledger_event(rec,changed,outcome="SENT",occurred_at=NOW,sequence=1,prev_event_sha256=engine.GENESIS)

    def test_event_round_trip_chain(self):
        p,r,a,l=setup(); rec=eval_case(p,r,a,l); e=engine.make_ledger_event(rec,r,outcome="SENT",occurred_at=NOW,sequence=1,prev_event_sha256=engine.GENESIS); l["events"]=[e]; self.assertEqual(engine.ledger_head(l),e["event_sha256"])

    def test_input_order_deterministic(self):
        p,r,a,l=setup(); rec1=eval_case(p,r,a,l); p["allowed_agents"][0]["roles"].reverse(); p["rules"].reverse(); rec2=eval_case(p,r,a,l); self.assertEqual(engine.canonical_bytes(rec1),engine.canonical_bytes(rec2))

    def test_receipt_reason_order_stable(self):
        p,r,a,l=setup(); r["action"]="delete"; r["agent_version"]="bad"; rec=eval_case(p,r,a,l); self.assertEqual(rec["reasons"],sorted(rec["reasons"]))

    def test_file_reader_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); target=root/"real.json"; target.write_text('{}'); link=root/"link.json"
            try: os.symlink(target.name,link)
            except (OSError,NotImplementedError): self.skipTest("symlink unsupported")
            with self.assertRaises((engine.GateError,OSError)): engine.read_json_file(str(link))

    def test_file_reader_rejects_fifo_without_blocking(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"fifo"; os.mkfifo(p)
            with self.assertRaises(engine.GateError): engine.read_json_file(str(p))

    def test_external_commercial_authority_always_false(self):
        p,r,a,l=setup(); rec=eval_case(p,r,a,l); ceiling=rec["authority_ceiling"]
        for k in ("external_mutation_performed","buyer_acceptance_proven","contract_proven","payment_proven","revenue_proven"): self.assertFalse(ceiling[k])

if __name__ == "__main__": unittest.main()
