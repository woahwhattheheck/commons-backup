from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib, os, subprocess, sys, tempfile, unittest
from pathlib import Path

from tools.exact_head_ship_fence import fence
from tools.exact_head_ship_fence.fence import *

H, B, N, O = "1"*40, "2"*40, "4"*40, "9"*40

def ts(d=None): return (d or datetime.now(timezone.utc)).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
def packet():
    now = ts()
    return {
        "schema_version":1,"repository":"example/repo","base_branch":"main",
        "expected_pr_head":H,"current_pr_head":H,"construction_parent":B,"current_base_head":B,
        "observed_at":now,"max_age_seconds":3600,"snapshot_complete":True,
        "refs":{"pr_ref_exists":True,"base_ref_exists":True},
        "topology":{"candidate_paths_known":True,"candidate_paths":[{"path":"src/a.py","blob_sha":"3"*40}],
                    "base_delta_paths_known":True,"base_delta_paths":[],"evaluated_base_sha":B,"rejoin_proven":False,"rejoin_head_sha":None},
        "check_policy":[{"name":"tests (3.11)","required":True,"allow_skipped":False}],
        "checks":[{"name":"tests (3.11)","run_id":"run-1","head_sha":H,"status":"COMPLETED","conclusion":"SUCCESS","observed_at":now}],
        "review_policy":{"required":True,"min_passes":1},
        "reviews":[{"review_id":"review-1","reviewer":"github-actions[bot]","head_sha":H,"verdict":"PASS","observed_at":now}],
    }
def seal(r):
    body={k:v for k,v in r.items() if k!="receipt_sha256"}; r["receipt_sha256"]=hashlib.sha256(canonical_json_bytes(body)).hexdigest()

class Verdicts(unittest.TestCase):
    def test_ready_authority_and_verify(self):
        p=packet(); r=compile_current(p)
        self.assertEqual((r["verdict"],r["next_action"]),("READY_TO_MERGE_EVIDENCE","MERGE_AFTER_LIVE_RECENSUS"))
        self.assertFalse(any(r["authority"].values())); self.assertTrue(verify_current(r,p))

    def test_head_moved(self):
        p=packet(); p["current_pr_head"]=O; p["checks"][0]["head_sha"]=O; p["reviews"][0]["head_sha"]=O
        self.assertEqual(compile_current(p)["verdict"],"HOLD_HEAD_MOVED")

    def test_base_move_matrix(self):
        p=packet(); p["current_base_head"]=N; p["topology"]["base_delta_paths"]=[{"path":"docs/x.md","blob_sha":None}]
        self.assertEqual(compile_current(p)["verdict"],"HOLD_BASE_MOVED")
        p["topology"].update(evaluated_base_sha=N,rejoin_proven=True,rejoin_head_sha=H)
        self.assertEqual(compile_current(p)["verdict"],"READY_TO_MERGE_EVIDENCE")
        p["topology"]["base_delta_paths"]=[{"path":"src/a.py","blob_sha":None}]
        self.assertEqual(compile_current(p)["verdict"],"HOLD_BASE_MOVED")
        p["topology"]["base_delta_paths"]=[{"path":"docs/x.md","blob_sha":None}]; p["topology"]["rejoin_head_sha"]=O
        self.assertEqual(compile_current(p)["verdict"],"HOLD_BASE_MOVED")

    def test_topology_unknown(self):
        p=packet(); p["topology"]["candidate_paths_known"]=False; p["topology"]["candidate_paths"]=[]
        self.assertEqual(compile_current(p)["verdict"],"HOLD_TOPOLOGY_UNKNOWN")

    def test_ci_matrix(self):
        cases=[("QUEUED","NONE",False,"HOLD_CI_UNKNOWN"),("COMPLETED","CANCELLED",False,"HOLD_CI_UNKNOWN"),
               ("COMPLETED","SKIPPED",False,"HOLD_CI_UNKNOWN"),("COMPLETED","SKIPPED",True,"READY_TO_MERGE_EVIDENCE"),
               ("COMPLETED","FAILURE",False,"HOLD_CI_RED")]
        for status,conc,allow,want in cases:
            with self.subTest(status=status,conc=conc,allow=allow):
                p=packet(); p["checks"][0].update(status=status,conclusion=conc); p["check_policy"][0]["allow_skipped"]=allow
                self.assertEqual(compile_current(p)["verdict"],want)
        p=packet(); p["checks"]=[]; self.assertEqual(compile_current(p)["verdict"],"HOLD_CI_UNKNOWN")

    def test_review_matrix(self):
        p=packet(); p["reviews"][0]["head_sha"]=O
        self.assertEqual(compile_current(p)["verdict"],"HOLD_REVIEW_STALE")
        p=packet(); p["reviews"][0]["verdict"]="STOP"
        self.assertEqual(compile_current(p)["reason_codes"],["EXACT_HEAD_REVIEW_STOP"])
        p=packet(); p["reviews"]=[]; self.assertEqual(compile_current(p)["verdict"],"HOLD_REVIEW_STALE")

    def test_incomplete(self):
        p=packet(); p["snapshot_complete"]=False
        self.assertEqual(compile_current(p)["verdict"],"HOLD_INCOMPLETE_EVIDENCE")

class Boundary(unittest.TestCase):
    def test_strict_json_hostiles(self):
        for raw in (b'{"a":1,"a":2}',b'{"x":1.5}',b'{"x":NaN}',b'{"x":99999999999999999}',b'{"x":"\\ud800"}'):
            with self.subTest(raw=raw), self.assertRaises(EvidenceError): parse_json_bytes(raw)

    def test_schema_runtime_and_ref_hostiles(self):
        variants=[]
        p=packet(); p["extra"]=1; variants.append(p)
        p=packet(); p["max_age_seconds"]=True; variants.append(p)
        p=packet(); p["current_pr_head"]="deadbeef"; variants.append(p)
        p=packet(); p["refs"]["pr_ref_exists"]=False; variants.append(p)
        p=packet(); p["checks"][0]["head_sha"]=O; variants.append(p)
        for p in variants:
            with self.subTest(keys=list(p)), self.assertRaises(EvidenceError): compile_current(p)
        class D(dict): pass
        with self.assertRaises(EvidenceError): compile_current(D(packet()))

    def test_time_hostiles(self):
        p=packet(); future=ts(datetime.now(timezone.utc)+timedelta(hours=1)); p["observed_at"]=p["checks"][0]["observed_at"]=p["reviews"][0]["observed_at"]=future
        with self.assertRaises(EvidenceError): compile_current(p)
        p=packet(); old=ts(datetime.now(timezone.utc)-timedelta(hours=2)); p["max_age_seconds"]=60; p["observed_at"]=p["checks"][0]["observed_at"]=p["reviews"][0]["observed_at"]=old
        with self.assertRaises(EvidenceError): compile_current(p)

    def test_impossible_and_conflicting_checks(self):
        p=packet(); p["checks"][0].update(status="QUEUED",conclusion="SUCCESS")
        with self.assertRaises(EvidenceError): compile_current(p)
        p=packet(); q=deepcopy(p["checks"][0]); q["run_id"]="run-2"; p["checks"].append(q)
        with self.assertRaises(EvidenceError): compile_current(p)

    def test_path_canonicalization(self):
        p=packet(); p["topology"]["candidate_paths"]=[{"path":"z.py","blob_sha":None},{"path":"a.py","blob_sha":None}]
        with self.assertRaises(EvidenceError): compile_current(p)

class Verification(unittest.TestCase):
    def test_resealed_tamper_and_transplant_fail(self):
        p=packet(); r=compile_current(p); r.update(verdict="HOLD_CI_UNKNOWN",next_action="WAIT_FOR_CI",reason_codes=["REQUIRED_CHECK_NONTERMINAL"]); seal(r)
        self.assertFalse(verify_current(r,p))
        p=packet(); r=compile_current(p); q=deepcopy(p); q["topology"]["candidate_paths"]=[{"path":"src/z.py","blob_sha":"3"*40}]
        self.assertFalse(verify_current(r,q))

    def test_markdown_and_clock_capture(self):
        p=packet(); r=compile_current(p); md=render_markdown(r)
        self.assertIn("never authorizes a merge",md); self.assertIn("merge_authorized=false",md)
        old=fence._CURRENT_CLOCK
        try:
            fence._CURRENT_CLOCK=lambda: datetime(2000,1,1,tzinfo=timezone.utc)
            self.assertEqual(fence.compile_current(packet())["verdict"],"READY_TO_MERGE_EVIDENCE")
        finally: fence._CURRENT_CLOCK=old

class CLI(unittest.TestCase):
    def run_cli(self,*args,cwd):
        env=dict(os.environ); env["PYTHONPATH"]=str(cwd)
        return subprocess.run([sys.executable,"-m","tools.exact_head_ship_fence",*map(str,args)],cwd=cwd,env=env,capture_output=True,text=True,check=False)

    def test_round_trip_create_exclusive_and_bad_json(self):
        root=Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as td:
            td=Path(td); src=td/"s.json"; out=td/"out"; src.write_bytes(canonical_json_bytes(packet())+b"\n")
            a=self.run_cli("compile",src,out,cwd=root); self.assertEqual(a.returncode,0,a.stderr); before=(out/"report.json").read_bytes()
            b=self.run_cli("verify",src,out,cwd=root); self.assertEqual(b.returncode,0,b.stderr)
            c=self.run_cli("compile",src,out,cwd=root); self.assertEqual(c.returncode,2); self.assertEqual(before,(out/"report.json").read_bytes())
            bad=td/"bad.json"; bad.write_text('{"a":1,"a":2}')
            d=self.run_cli("compile",bad,td/"bad-out",cwd=root); self.assertEqual(d.returncode,2); self.assertNotIn("Traceback",d.stderr)

if __name__ == "__main__": unittest.main()
