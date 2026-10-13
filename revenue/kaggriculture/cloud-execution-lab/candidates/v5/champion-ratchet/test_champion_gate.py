#!/usr/bin/env python3
from __future__ import annotations
import hashlib, importlib.util, json, tempfile
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location("G", HERE/"champion_gate.py")
G=importlib.util.module_from_spec(SPEC); assert SPEC and SPEC.loader; SPEC.loader.exec_module(G)

def blob(data:bytes): return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
def sha(data:bytes): return hashlib.sha256(data).hexdigest()
def write_json(p,v): p.write_text(json.dumps(v,sort_keys=True,separators=(",",":")),encoding="utf-8")

class Fixture:
    def __init__(self):
        self.t=tempfile.TemporaryDirectory(); self.root=Path(self.t.name)
        self.kg=self.root/"kg"; self.eng=self.root/"engine"; self.kg.mkdir(); self.eng.mkdir()
        self.repo_pins={}
        for rel in G.REPO_GIT_BLOBS:
            data=("repo:"+rel).encode(); p=self.kg/rel; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(data)
            self.repo_pins[rel]=blob(data)
        self.engine_pins={}
        for name in G.ENGINE_GIT_BLOBS:
            data=("engine:"+name).encode(); p=self.eng/name; p.write_bytes(data); self.engine_pins[name]=blob(data)
        self.h=G.authenticate_harness(self.kg,self.eng,repo_pins=self.repo_pins,engine_pins=self.engine_pins)
        targets=[]
        for sub in (101,202):
            replays=[]
            for j in range(3):
                replays.append({"episode_id":sub*10+j,"seed":sub*100+j,
                                "recorded_opponent_seat":j%2,"kind":"recorded_action_trace"})
            targets.append({"submission_id":sub,"status":"complete","replays":replays})
        self.manifest={"schema":"titan.gauntlet.top30-union.v1","targets":targets}
        self.manifest_path=self.root/"manifest.json"; write_json(self.manifest_path,self.manifest)
        self.manifest_sha=sha(self.manifest_path.read_bytes())
        self.m=G.load_manifest(self.manifest_path,expected_sha256=self.manifest_sha,expected_targets=2)
        self.v31=self.root/"v31.tar.gz"; self.inc=self.root/"inc.tar.gz"; self.cand=self.root/"cand.tar.gz"
        self.v31.write_bytes(b"v31"); self.inc.write_bytes(b"inc"); self.cand.write_bytes(b"candidate")
        self.v31_sha=sha(b"v31"); self.inc_sha=sha(b"inc"); self.cand_sha=sha(b"candidate")
        self.old_v31=G.V31_ARCHIVE_SHA256; G.V31_ARCHIVE_SHA256=self.v31_sha
        self.roots={}
        for label,archive_sha,own_delta in (("v31",self.v31_sha,0),("inc",self.inc_sha,-10),("cand",self.cand_sha,10)):
            self.roots[label]=self.make_policy(label,archive_sha,own_delta)
    def close(self):
        G.V31_ARCHIVE_SHA256=self.old_v31; self.t.cleanup()
    def make_policy(self,label,archive_sha,delta,shards=2):
        roots=[]; fixtures=self.m["fixtures"]
        for shard in range(shards):
            r=self.root/f"{label}-{shard}"; r.mkdir(); roots.append(r)
            ids=[f for i,f in enumerate(fixtures) if i%shards==shard]
            run={"candidate_sha256":archive_sha,"index_sha256":("a" if shard==0 else "b")*64,
                 "engine":self.h["engine"],
                 "evaluator_sha256":self.h["repo"]["cloud-execution-lab/reference/evaluator/evaluate.py"]["sha256"],
                 "loader_sha256":self.h["repo"]["20260907-offline-agent/evaluate.py"]["sha256"],
                 "selected_fixtures":len(ids),"group":"all","shard":shard,"shards":shards,
                 "submission_hold":True}
            write_json(r/"run.json",run)
            for f in ids:
                for seat in (0,1):
                    own=1000+f["seed"]%17+seat+delta; rival=900+f["seed"]%11
                    scores=[None,None]; scores[seat]=own; scores[1-seat]=rival
                    rec={"seed":f["seed"],"candidate_seat":seat,"status":"complete","scores":scores,
                         "steps":G.EXPECTED_CALLBACKS,"opponent":f["id"],"submission_id":f["submission_id"],
                         "kind":"recorded_trace","adaptive":False,
                         "recorded_orientation":seat==f["candidate_seat_for_recorded_orientation"],
                         "family":f"recorded-submission:{f['submission_id']}","candidate_sha256":archive_sha}
                    write_json(r/f"{f['id']}-p{seat}.json",rec)
        return roots
    def eval(self,**kw):
        return G.evaluate(kg_root=self.kg,engine_dir=self.eng,manifest_path=self.manifest_path,
                          v31_archive=self.v31,incumbent_archive=self.inc,candidate_archive=self.cand,
                          v31_roots=self.roots["v31"],incumbent_roots=self.roots["inc"],candidate_roots=self.roots["cand"],
                          expected_manifest_sha=self.manifest_sha,expected_targets=2,
                          repo_pins=self.repo_pins,engine_pins=self.engine_pins,**kw)

class Tests(unittest.TestCase):
    def setUp(self): self.f=Fixture()
    def tearDown(self): self.f.close()
    def test_end_to_end_pass_is_not_release_authority(self):
        r=self.f.eval(); self.assertEqual(12,r["cell_count"]); self.assertTrue(r["champion_ready"])
        self.assertFalse(r["release_authority"]); self.assertGreater(r["own_sum_delta_vs_v31"],0)
        self.assertEqual(4,len(r["strata"]))
        self.assertEqual(G.V31_SOURCE_COMMIT,r["v31_source_commit"])
        self.assertEqual(G.V31_SUBMISSION_ID,r["v31_submission_id"])
        self.assertEqual(self.f.v31_sha,r["v31_archive_sha256"])
    def test_exact_v31_identity_constants(self):
        self.assertEqual("a90d888f03987ef0b35cfd20ec3519c6144db08a", G.V31_SOURCE_COMMIT)
        self.assertEqual(56172377, G.V31_SUBMISSION_ID)
        self.assertEqual("5db3921f85efbc7596e5a1e7e198fc5f4644ceea43d8e8323c74ded7b4ba4361", self.f.old_v31)
        saved=G.V31_ARCHIVE_SHA256
        G.V31_ARCHIVE_SHA256=self.f.old_v31
        try:
            ident=G.authenticate_v31_identity()
        finally:
            G.V31_ARCHIVE_SHA256=saved
        self.assertEqual("a90d888f03987ef0b35cfd20ec3519c6144db08a", ident["v31_source_commit"])
        self.assertEqual(56172377, ident["v31_submission_id"])
        self.assertEqual("5db3921f85efbc7596e5a1e7e198fc5f4644ceea43d8e8323c74ded7b4ba4361", ident["v31_archive_sha256"])
    def test_stale_source_commit_rejected_in_release_replay(self):
        with self.assertRaisesRegex(G.ChampionError,"stale V3.1 source_commit"):
            G.authenticate_v31_identity(source_commit="0"*40)
        with self.assertRaisesRegex(G.ChampionError,"stale V3.1 source_commit"):
            self.f.eval(claimed_v31_source_commit="0"*40)
    def test_stale_submission_id_rejected_in_release_replay(self):
        with self.assertRaisesRegex(G.ChampionError,"stale V3.1 submission_id"):
            G.authenticate_v31_identity(submission_id=1)
        with self.assertRaisesRegex(G.ChampionError,"stale V3.1 submission_id"):
            self.f.eval(claimed_v31_submission_id=1)
    def test_stale_archive_identity_rejected(self):
        with self.assertRaisesRegex(G.ChampionError,"exact submitted V3.1"):
            G.authenticate_v31_identity(archive_sha256="f"*64)
    def test_balanced_favorable_subset_cannot_authorize(self):
        p=next(self.f.roots["cand"][0].glob("*-p0.json")); mate=p.with_name(p.name.replace("-p0.json","-p1.json"))
        p.unlink(); mate.unlink()
        with self.assertRaisesRegex(G.ChampionError,"full roster"): self.f.eval()
    def test_limit_like_selected_fixture_receipt_cannot_authorize(self):
        rp=self.f.roots["cand"][0]/"run.json"; x=json.loads(rp.read_text()); x["selected_fixtures"]=1; write_json(rp,x)
        with self.assertRaisesRegex(G.ChampionError,"--limit"): self.f.eval()
    def test_cross_policy_index_drift_fails(self):
        rp=self.f.roots["cand"][1]/"run.json"; x=json.loads(rp.read_text()); x["index_sha256"]="c"*64; write_json(rp,x)
        with self.assertRaisesRegex(G.ChampionError,"index authority"): self.f.eval()
    def test_archive_bytes_bind_run(self):
        self.f.cand.write_bytes(b"changed")
        with self.assertRaisesRegex(G.ChampionError,"archive/run mismatch"): self.f.eval()
    def test_wrong_v31_bytes_fail_exact_floor(self):
        G.V31_ARCHIVE_SHA256="f"*64
        with self.assertRaisesRegex(G.ChampionError,"exact submitted V3.1"): self.f.eval()
    def test_margin_improves_while_own_loses_rejects(self):
        for root in self.f.roots["cand"]:
            for p in root.glob("*-p?.json"):
                x=json.loads(p.read_text()); seat=x["candidate_seat"]
                v31p=next(r/p.name for r in self.f.roots["v31"] if (r/p.name).exists()); v=json.loads(v31p.read_text())
                x["scores"][seat]=v["scores"][seat]-1; x["scores"][1-seat]=v["scores"][1-seat]-100; write_json(p,x)
        with self.assertRaisesRegex(G.ChampionError,"strictly beat V3.1"): self.f.eval()
    def test_negative_submission_seat_stratum_fails_despite_positive_total(self):
        fixtures=self.f.m["fixtures"]; low_sub=fixtures[0]["submission_id"]; high_sub=fixtures[-1]["submission_id"]
        for root in self.f.roots["cand"]:
            for p in root.glob("*-p?.json"):
                x=json.loads(p.read_text()); seat=x["candidate_seat"]
                v31p=next(r/p.name for r in self.f.roots["v31"] if (r/p.name).exists()); v=json.loads(v31p.read_text())
                if x["submission_id"]==low_sub and seat==0: x["scores"][seat]=v["scores"][seat]-1
                if x["submission_id"]==high_sub and seat==0: x["scores"][seat]=v["scores"][seat]+100
                write_json(p,x)
        with self.assertRaisesRegex(G.ChampionError,"negative own-score stratum"): self.f.eval()
    def test_harness_git_blob_drift_fails(self):
        rel=next(iter(self.f.repo_pins)); (self.f.kg/rel).write_bytes(b"tampered")
        with self.assertRaisesRegex(G.ChampionError,"repo authority drift"): self.f.eval()
    def test_engine_drift_fails(self):
        name=next(iter(self.f.engine_pins)); (self.f.eng/name).write_bytes(b"tampered")
        with self.assertRaisesRegex(G.ChampionError,"engine authority drift"): self.f.eval()
    def test_manifest_hash_and_cardinality_are_authority(self):
        with self.assertRaisesRegex(G.ChampionError,"SHA256 mismatch"):
            G.load_manifest(self.f.manifest_path,expected_sha256="0"*64,expected_targets=2)
        with self.assertRaisesRegex(G.ChampionError,"expected 41 corpus targets"):
            G.load_manifest(self.f.manifest_path,expected_sha256=self.f.manifest_sha)
    def test_duplicate_json_key_rejected(self):
        p=self.f.root/"dup.json"; p.write_text('{"a":1,"a":2}')
        with self.assertRaisesRegex(G.ChampionError,"duplicate JSON"): G._read_json(p)

if __name__=="__main__": unittest.main()
