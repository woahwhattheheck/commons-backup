import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from onboarding import (
    ConflictError, OnboardingError, canonical, compile_packet, connect, decide_change,
    export_handoff, init_db, kickoff_state, load_json, open_workspace, receive_input,
    record_deliverable, request_change, review_deliverable, review_input,
    sha256_bytes, strict_loads, transition_milestone, validate_scope, verify_export,
)
import server as server_mod

NOW = "2026-09-16T14:30:00Z"

def base_scope():
    return {
        "deliverables": [
            {"id":"kickoff-plan","title":"Kickoff implementation plan"},
            {"id":"handoff-package","title":"Final implementation handoff package"},
        ],
        "exclusions": ["No provider or customer-system mutation", "No external sending from this workspace"],
        "assumptions": ["Customer inputs are supplied through an authorized local operator"],
        "acceptanceCriteria": [
            {"id":"criterion-plan","deliverableId":"kickoff-plan","text":"Plan is locally reviewed against the accepted scope"},
            {"id":"criterion-handoff","deliverableId":"handoff-package","text":"Handoff package is locally reviewed against the current scope generation"},
        ],
        "requiredInputs": [
            {"id":"client-brief","title":"Accepted client brief","roleRef":"role.client-owner"},
            {"id":"source-export","title":"Required source export","roleRef":"role.implementation-owner"},
        ],
        "milestones": [
            {"id":"kickoff","title":"Kickoff preparation","sequence":1,"dependsOn":[],"deliverableIds":["kickoff-plan"]},
            {"id":"delivery","title":"Implementation delivery","sequence":2,"dependsOn":["kickoff"],"deliverableIds":["handoff-package"]},
        ],
    }

def accepted_payload(scope=None):
    s = validate_scope(scope or base_scope())
    return {
        "workspaceId":"ws-demo-001", "clientRef":"client.synthetic", "workRef":"work.synthetic.001",
        "acceptedAt":"2026-09-16T13:00:00Z", "scopeRevision":1,
        "acceptedScopeSha256":sha256_bytes(canonical(s)), "currency":"USD", "referenceMinor":250000,
        "scope":s,
    }

class Harness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name)/"onboarding.db"
        self.conn = connect(self.db); init_db(self.conn)
    def tearDown(self):
        self.conn.close(); self.tmp.cleanup()
    def open(self, scope=None): return open_workspace(self.conn, accepted_payload(scope), "op-open", now=NOW)
    def ready_inputs(self):
        receive_input(self.conn,"ws-demo-001","client-brief","a"*64,"op-in-1",now=NOW)
        review_input(self.conn,"ws-demo-001","client-brief","ACCEPTED_LOCAL","op-in-r1",now=NOW)
        receive_input(self.conn,"ws-demo-001","source-export","b"*64,"op-in-2",now=NOW)
        review_input(self.conn,"ws-demo-001","source-export","ACCEPTED_LOCAL","op-in-r2",now=NOW)
    def complete_happy(self):
        self.ready_inputs()
        transition_milestone(self.conn,"ws-demo-001","kickoff","START","op-ms-1",now=NOW)
        record_deliverable(self.conn,"ws-demo-001","kickoff","kickoff-plan","c"*64,"op-d-1",now=NOW)
        review_deliverable(self.conn,"ws-demo-001","kickoff","kickoff-plan",1,"OWNER_APPROVED_LOCAL","op-dr-1",now=NOW)
        transition_milestone(self.conn,"ws-demo-001","kickoff","COMPLETE","op-ms-2",now=NOW)
        transition_milestone(self.conn,"ws-demo-001","delivery","START","op-ms-3",now=NOW)
        record_deliverable(self.conn,"ws-demo-001","delivery","handoff-package","d"*64,"op-d-2",now=NOW)
        review_deliverable(self.conn,"ws-demo-001","delivery","handoff-package",1,"CUSTOMER_REVIEWED_LOCAL","op-dr-2",now=NOW)
        transition_milestone(self.conn,"ws-demo-001","delivery","COMPLETE","op-ms-4",now=NOW)

class ProductTests(Harness):
    def test_happy_path_to_owner_handoff(self):
        self.open(); self.assertEqual(kickoff_state(self.conn,"ws-demo-001"),"INPUTS_REQUIRED")
        self.complete_happy(); p=compile_packet(self.conn,"ws-demo-001")
        self.assertEqual(p["handoffState"],"READY_FOR_OWNER_HANDOFF_REVIEW")
        self.assertFalse(p["authority"]["externalSend"]); self.assertFalse(p["authority"]["recognizedRevenue"])

    def test_missing_received_and_rejected_input_states(self):
        self.open(); receive_input(self.conn,"ws-demo-001","client-brief","a"*64,"x1",now=NOW)
        self.assertEqual(kickoff_state(self.conn,"ws-demo-001"),"INPUTS_REQUIRED")
        receive_input(self.conn,"ws-demo-001","source-export","b"*64,"x2",now=NOW)
        self.assertEqual(kickoff_state(self.conn,"ws-demo-001"),"OWNER_REVIEW_REQUIRED")
        review_input(self.conn,"ws-demo-001","client-brief","REJECTED_LOCAL","x3",now=NOW)
        self.assertEqual(kickoff_state(self.conn,"ws-demo-001"),"ON_HOLD")

    def test_operation_replay_and_changed_payload_conflict(self):
        self.open(); r1=receive_input(self.conn,"ws-demo-001","client-brief","a"*64,"repeat",now=NOW)
        r2=receive_input(self.conn,"ws-demo-001","client-brief","a"*64,"repeat",now=NOW)
        self.assertEqual(r1,r2)
        with self.assertRaises(ConflictError): receive_input(self.conn,"ws-demo-001","client-brief","b"*64,"repeat",now=NOW)

    def test_milestone_dependency_and_completion_gate(self):
        self.open(); self.ready_inputs()
        with self.assertRaises(OnboardingError): transition_milestone(self.conn,"ws-demo-001","delivery","START","dep-bad",now=NOW)
        transition_milestone(self.conn,"ws-demo-001","kickoff","START","dep-1",now=NOW)
        with self.assertRaises(OnboardingError): transition_milestone(self.conn,"ws-demo-001","kickoff","COMPLETE","dep-2",now=NOW)

    def test_stale_deliverable_review_after_revision(self):
        self.open(); self.ready_inputs(); transition_milestone(self.conn,"ws-demo-001","kickoff","START","s1",now=NOW)
        record_deliverable(self.conn,"ws-demo-001","kickoff","kickoff-plan","c"*64,"s2",now=NOW)
        review_deliverable(self.conn,"ws-demo-001","kickoff","kickoff-plan",1,"OWNER_APPROVED_LOCAL","s3",now=NOW)
        record_deliverable(self.conn,"ws-demo-001","kickoff","kickoff-plan","d"*64,"s4",now=NOW)
        with self.assertRaises(ConflictError): review_deliverable(self.conn,"ws-demo-001","kickoff","kickoff-plan",1,"OWNER_APPROVED_LOCAL","s5",now=NOW)
        with self.assertRaises(OnboardingError): transition_milestone(self.conn,"ws-demo-001","kickoff","COMPLETE","s6",now=NOW)

    def test_changed_required_input_invalidates_completed_delivery(self):
        self.open(); self.complete_happy()
        self.assertEqual(compile_packet(self.conn,"ws-demo-001")["handoffState"],"READY_FOR_OWNER_HANDOFF_REVIEW")
        receive_input(self.conn,"ws-demo-001","client-brief","e"*64,"replace-input",now=NOW)
        packet=compile_packet(self.conn,"ws-demo-001")
        self.assertEqual(packet["kickoffState"],"OWNER_REVIEW_REQUIRED")
        self.assertEqual(packet["handoffState"],"HOLD")
        self.assertTrue(all(m["state"]=="WAITING" for m in packet["milestones"]))
        self.assertTrue(all(d["review_decision"]=="UNREVIEWED" for d in packet["deliverables"]))
        review_input(self.conn,"ws-demo-001","client-brief","ACCEPTED_LOCAL","replace-review",now=NOW)
        packet=compile_packet(self.conn,"ws-demo-001")
        self.assertEqual(packet["kickoffState"],"READY_FOR_KICKOFF_REVIEW")
        self.assertEqual(packet["handoffState"],"HOLD")
        self.assertIn("MILESTONES_INCOMPLETE",packet["holds"])

    def test_pending_rejected_and_approved_change(self):
        self.open(); self.ready_inputs(); changed=base_scope(); changed["assumptions"]=["Revised local assumption"]
        request_change(self.conn,"ws-demo-001","chg-1",changed,"c1",now=NOW)
        self.assertEqual(kickoff_state(self.conn,"ws-demo-001"),"ON_HOLD")
        decide_change(self.conn,"ws-demo-001","chg-1","REJECTED_LOCAL","c2",now=NOW)
        self.assertEqual(kickoff_state(self.conn,"ws-demo-001"),"READY_FOR_KICKOFF_REVIEW")
        request_change(self.conn,"ws-demo-001","chg-2",changed,"c3",now=NOW)
        result=decide_change(self.conn,"ws-demo-001","chg-2","APPROVED_LOCAL","c4",now=NOW)
        self.assertEqual(result["generation"],2)
        self.assertEqual(kickoff_state(self.conn,"ws-demo-001"),"INPUTS_REQUIRED")
        packet=compile_packet(self.conn,"ws-demo-001"); self.assertEqual(packet["workspace"]["currentGeneration"],2)
        self.assertEqual(packet["inputs"][0]["artifact_revision"],0)

    def test_scope_validation_rejects_bad_dependency_and_bool_sequence(self):
        bad=base_scope(); bad["milestones"][1]["dependsOn"]=["missing"]
        with self.assertRaises(OnboardingError): validate_scope(bad)
        bad=base_scope(); bad["milestones"][0]["sequence"]=True
        with self.assertRaises(OnboardingError): validate_scope(bad)

    def test_accepted_scope_digest_is_authoritative(self):
        p=accepted_payload(); p["acceptedScopeSha256"]="0"*64
        with self.assertRaises(OnboardingError): open_workspace(self.conn,p,"bad-open",now=NOW)

    def test_duplicate_json_key_and_nonfinite_rejected(self):
        with self.assertRaises(OnboardingError): strict_loads('{"a":1,"a":2}')
        with self.assertRaises(OnboardingError): strict_loads('{"a":NaN}')

    def test_export_verify_and_tamper(self):
        self.open(); self.complete_happy(); out=Path(self.tmp.name)/"export"
        receipt=export_handoff(self.conn,"ws-demo-001",out); self.assertEqual(receipt["handoffState"],"READY_FOR_OWNER_HANDOFF_REVIEW")
        self.assertTrue(verify_export(self.conn,"ws-demo-001",out)["valid"])
        (out/"handoff.md").write_text("tampered",encoding="utf-8")
        with self.assertRaises(OnboardingError): verify_export(self.conn,"ws-demo-001",out)

    def test_export_refuses_overwrite_and_symlink_final(self):
        self.open(); out=Path(self.tmp.name)/"export"; out.mkdir(); (out/"handoff.json").write_text("occupied")
        with self.assertRaises(OnboardingError): export_handoff(self.conn,"ws-demo-001",out)
        if hasattr(os,"symlink"):
            out2=Path(self.tmp.name)/"export2"; out2.mkdir(); target=Path(self.tmp.name)/"target"; target.write_text("x")
            os.symlink(target,out2/"handoff.json")
            with self.assertRaises(OnboardingError): export_handoff(self.conn,"ws-demo-001",out2)

    def test_reopen_persists_identical_packet(self):
        self.open(); self.ready_inputs(); p1=compile_packet(self.conn,"ws-demo-001")
        self.conn.close(); self.conn=connect(self.db); init_db(self.conn); p2=compile_packet(self.conn,"ws-demo-001")
        self.assertEqual(p1,p2)

    def test_concurrent_exact_replay_creates_one_artifact_revision(self):
        self.open(); results=[]; errors=[]; barrier=threading.Barrier(2)
        def worker():
            c=connect(self.db); init_db(c)
            try:
                barrier.wait(); results.append(receive_input(c,"ws-demo-001","client-brief","a"*64,"concurrent-op",now=NOW))
            except Exception as exc: errors.append(exc)
            finally: c.close()
        t1=threading.Thread(target=worker); t2=threading.Thread(target=worker); t1.start(); t2.start(); t1.join(); t2.join()
        self.assertEqual(errors,[]); self.assertEqual(len(results),2); self.assertEqual(results[0],results[1])
        row=self.conn.execute("SELECT artifact_revision FROM input_state WHERE workspace_id='ws-demo-001' AND generation=1 AND input_id='client-brief'").fetchone()
        self.assertEqual(row["artifact_revision"],1)

    def test_http_is_read_only_and_loopback_restricted(self):
        self.open(); server_mod.Handler.db_path=str(self.db)
        httpd=ThreadingHTTPServer(("127.0.0.1",0),server_mod.Handler); port=httpd.server_address[1]
        th=threading.Thread(target=httpd.serve_forever,daemon=True); th.start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/workspaces",timeout=3) as r:
                data=json.loads(r.read()); self.assertTrue(data["readOnly"]); self.assertEqual(len(data["workspaces"]),1)
            req=urllib.request.Request(f"http://127.0.0.1:{port}/api/workspaces",data=b"{}",method="POST")
            with self.assertRaises(urllib.error.HTTPError) as cm: urllib.request.urlopen(req,timeout=3)
            self.assertEqual(cm.exception.code,405)
        finally:
            httpd.shutdown(); httpd.server_close(); th.join(timeout=3)
        with self.assertRaises(OnboardingError): server_mod.serve(str(self.db),"0.0.0.0",0)

    def test_readonly_http_does_not_create_missing_database(self):
        missing=Path(self.tmp.name)/"missing.db"; server_mod.Handler.db_path=str(missing)
        httpd=ThreadingHTTPServer(("127.0.0.1",0),server_mod.Handler); port=httpd.server_address[1]
        th=threading.Thread(target=httpd.serve_forever,daemon=True); th.start()
        try:
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/workspaces",timeout=3)
            self.assertEqual(cm.exception.code,400)
            self.assertFalse(missing.exists())
        finally:
            httpd.shutdown(); httpd.server_close(); th.join(timeout=3)

    def test_json_ingress_refuses_symlink(self):
        payload=accepted_payload(); source=Path(self.tmp.name)/"source.json"; source.write_text(json.dumps(payload),encoding="utf-8")
        if hasattr(os,"symlink"):
            link=Path(self.tmp.name)/"input-link.json"; os.symlink(source,link)
            with self.assertRaises(OnboardingError): load_json(link)

    def test_cli_init_status_and_export_verify(self):
        payload=accepted_payload(); inp=Path(self.tmp.name)/"accepted.json"; inp.write_text(json.dumps(payload),encoding="utf-8")
        cli=Path(__file__).with_name("onboarding.py"); db2=Path(self.tmp.name)/"cli.db"
        cp=subprocess.run([sys.executable,str(cli),"--db",str(db2),"init","--input",str(inp),"--op","cli-open"],capture_output=True,text=True,check=False)
        self.assertEqual(cp.returncode,0,cp.stderr)
        cp=subprocess.run([sys.executable,str(cli),"--db",str(db2),"status","--workspace","ws-demo-001"],capture_output=True,text=True,check=False)
        self.assertEqual(cp.returncode,0,cp.stderr); self.assertIn('"handoffState": "HOLD"',cp.stdout)

    def test_cli_source_does_not_enumerate_action_choices(self):
        source = Path(__file__).with_name("onboarding.py").read_text(encoding="utf-8")
        self.assertNotRegex(source, r'add_argument\(\s*"--action".{0,120}choices\s*=')
        self.assertRegex(source, r'add_argument\(\s*"--transition"')
        self.assertNotIn('args.action', source)

    def test_cli_milestone_uses_transition_flag(self):
        payload=accepted_payload(); inp=Path(self.tmp.name)/"accepted.json"; inp.write_text(json.dumps(payload),encoding="utf-8")
        cli=Path(__file__).with_name("onboarding.py"); db2=Path(self.tmp.name)/"cli.db"
        digest="a"*64
        def run(*extra):
            return subprocess.run([sys.executable,str(cli),"--db",str(db2),*extra],capture_output=True,text=True,check=False)
        self.assertEqual(run("init","--input",str(inp),"--op","cli-open").returncode,0)
        self.assertEqual(run("receive-input","--workspace","ws-demo-001","--input-id","client-brief","--sha",digest,"--op","cli-in-1").returncode,0)
        self.assertEqual(run("review-input","--workspace","ws-demo-001","--input-id","client-brief","--decision","ACCEPTED_LOCAL","--op","cli-in-r1").returncode,0)
        self.assertEqual(run("receive-input","--workspace","ws-demo-001","--input-id","source-export","--sha","b"*64,"--op","cli-in-2").returncode,0)
        self.assertEqual(run("review-input","--workspace","ws-demo-001","--input-id","source-export","--decision","ACCEPTED_LOCAL","--op","cli-in-r2").returncode,0)
        blocked=run("milestone","--workspace","ws-demo-001","--milestone-id","kickoff","--action","START","--op","cli-ms-old")
        self.assertNotEqual(blocked.returncode,0)
        self.assertIn("--transition", blocked.stderr)
        self.assertNotIn('"state": "IN_PROGRESS"', blocked.stdout)
        started=run("milestone","--workspace","ws-demo-001","--milestone-id","kickoff","--transition","START","--op","cli-ms-1")
        self.assertEqual(started.returncode,0,started.stderr)
        self.assertIn('"state": "IN_PROGRESS"',started.stdout)

    def test_cli_rejects_lone_surrogate_json(self):
        payload=accepted_payload()
        payload["scope"]["deliverables"][0]["title"]="\ud800"
        inp=Path(self.tmp.name)/"hostile.json"
        inp.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
        cli=Path(__file__).with_name("onboarding.py")
        for dash_o in (False, True):
            db=Path(self.tmp.name)/f"surr-{int(dash_o)}.db"
            cmd=[sys.executable] + (["-O"] if dash_o else []) + ["-B", str(cli), "--db", str(db), "init", "--input", str(inp), "--op", f"surr-{int(dash_o)}"]
            cp=subprocess.run(cmd, capture_output=True, text=True, check=False)
            self.assertNotEqual(cp.returncode, 0, cp.stdout+cp.stderr)
            combined=cp.stdout+cp.stderr
            self.assertNotIn("Traceback", combined)
            self.assertIn("non-Unicode-scalar", combined)

    def _swap_after_dir_open(self, original: Path, successor: Path, parked: Path):
        real_open=os.open
        swapped={"done": False}
        def hijack(path, flags, mode=0o777, *args, dir_fd=None, **kwargs):
            if dir_fd is None:
                fd=real_open(path, flags, mode, *args, **kwargs)
            else:
                fd=real_open(path, flags, mode, *args, dir_fd=dir_fd, **kwargs)
            if (
                not swapped["done"]
                and dir_fd is None
                and hasattr(os, "O_DIRECTORY")
                and flags & os.O_DIRECTORY
                and Path(path).resolve() == original.resolve()
            ):
                os.rename(original, parked)
                os.rename(successor, original)
                swapped["done"]=True
            return fd
        return hijack

    def test_export_parent_swap_keeps_original_generation(self):
        self.open(); self.complete_happy()
        original=Path(self.tmp.name)/"export"; successor=Path(self.tmp.name)/"successor"; parked=Path(self.tmp.name)/"parked"
        original.mkdir(); successor.mkdir()
        with patch("onboarding.os.open", self._swap_after_dir_open(original, successor, parked)):
            export_handoff(self.conn,"ws-demo-001", original)
        self.assertTrue((parked/"handoff.json").is_file())
        self.assertTrue((parked/"receipt.json").is_file())
        self.assertFalse((original/"handoff.json").exists())
        self.assertTrue(verify_export(self.conn,"ws-demo-001", parked)["valid"])

    def test_verify_parent_swap_reads_original_generation(self):
        self.open(); self.complete_happy()
        original=Path(self.tmp.name)/"export"
        export_handoff(self.conn,"ws-demo-001", original)
        successor=Path(self.tmp.name)/"successor"; successor.mkdir()
        for name, body in (("handoff.json", b"foreign-packet\n"), ("handoff.md", b"x"), ("milestones.csv", b"x"), ("receipt.json", b"{}")):
            (successor/name).write_bytes(body)
        parked=Path(self.tmp.name)/"parked"
        with patch("onboarding.os.open", self._swap_after_dir_open(original, successor, parked)):
            result=verify_export(self.conn,"ws-demo-001", original)
        self.assertTrue(result["valid"])
        self.assertEqual((original/"handoff.json").read_bytes(), b"foreign-packet\n")
        self.assertNotEqual((parked/"handoff.json").read_bytes(), b"foreign-packet\n")

if __name__ == "__main__": unittest.main(verbosity=2)
