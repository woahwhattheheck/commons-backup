#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import verify_archive as gate


RUNTIME = '''\
from dataclasses import dataclass
@dataclass(frozen=True)
class Features:
    consumer: str = "frozen"
    seed: bool = False
    funding: bool = False
    redundant_hire: bool = False
    terminal_route: bool = False
    committed: bool = False
    budget_seconds: float = 1.0
    reserve_seconds: float = 0.01
    terminal_history: bool = False
    history_hypotheses: dict | None = None
    terminal_tie_break: str = "baseline"
    spatial_pathing: bool = False
    spatial_tempo: bool = False
    fourth_quadrant: bool = False
    market_pressure: bool = False
    committed_seed_retry: bool = False
    operating_stock: bool = False
    idle_fertilizer: bool = False
    crop_release: bool = False
    early_capital: bool = False
    weed_continuation: bool = False
class Controller:
    def __init__(self):
        self.cur=0
        self.R={0:[{"farmer":["PASS"],"hands":[],"market":[]} for _ in range(720)]}
        self.act=self.parent_act
    def parent_act(self, obs):
        return {"farmer":["PASS"],"hands":[],"market":[]}
class TitanAgent:
    def __init__(self, features=None, **_kwargs):
        self.features=features or Features(); self.spatial=None; self.controller=None
    def _initialize(self):
        from spatial_tempo import SpatialTempo
        self.controller=Controller(); f=self.features
        if any((f.spatial_pathing,f.spatial_tempo,f.idle_fertilizer,f.crop_release,f.weed_continuation)):
            if self.spatial is None:
                self.spatial=SpatialTempo(object(),pathing=f.spatial_pathing,tempo=f.spatial_tempo,
                    idle_fertilizer=f.idle_fertilizer,crop_release=f.crop_release,
                    weed_continuation=f.weed_continuation)
            self.spatial.install(self.controller)
'''

SPATIAL = '''\
from copy import deepcopy
class SpatialTempo:
    def __init__(self, mechanics, pathing=True, tempo=True, seed_reserve=None,
                 idle_fertilizer=False, crop_release=False, weed_continuation=False):
        self.m=mechanics; self.pathing=pathing; self.tempo=tempo
        self.idle_fertilizer=idle_fertilizer; self.crop_release=crop_release
        self.weed_continuation=weed_continuation
        self.plans={}; self.active={}; self.events=[]; self._committed=None
    def _scrub(self):
        if self.weed_continuation: return
        self.plans={k:v for k,v in self.plans.items() if v.get("kind")!="weed_continuation"}
        self.active={k:v for k,v in self.active.items() if k in self.plans}
        self.events=[e for e in self.events if e.get("kind")!="weed_continuation"]
        if self._committed is not None:
            c=dict(self._committed)
            c["plans"]={k:v for k,v in c.get("plans",{}).items() if v.get("kind")!="weed_continuation"}
            c["active"]={k:v for k,v in c.get("active",{}).items() if k in c["plans"]}
            c["events"]=[e for e in c.get("events",[]) if e.get("kind")!="weed_continuation"]
            c["patches"]={key:{k:v for k,v in patch.items() if k in c["plans"]}
                          for key,patch in c.get("patches",{}).items()}
            self._committed=c
    def install(self, controller):
        self._scrub(); original=controller.act
        def act(obs): return self.transform(obs,original(obs),controller)
        controller.act=act
    def _deliver_idle_fertilizer(self,*args,**kwargs): return None
    def _collect_idle_fertilizer(self,*args,**kwargs): return None
    def _continue_weed(self,*args,**kwargs): return False
    def transform(self,obs,selected,controller):
        if self.weed_continuation and self._continue_weed(obs,selected,controller,24): return selected
        return selected
    def future_seed_requests(self,after_step):
        out={}
        for p in self.plans.values():
            if p.get("obligation",[""])[0]=="PLANT":
                out[p["obligation"][1]]=out.get(p["obligation"][1],0)+1
        return out
'''

MAIN = '''\
def _new_instance(root, feature_data):
    from titan_runtime import TitanAgent, Features
    return TitanAgent(Features(**feature_data))
'''


def strict_manifest(files):
    config=json.loads(files["TITAN-CONFIG.json"])
    return json.dumps({"default":config,"entrypoint":"main.py::agent","runtime":{
        name:{"bytes":len(files[name]),"sha256":gate._hash_bytes(files[name]),"source_path":name}
        for name in ("TITAN-CONFIG.json","titan_runtime.py","spatial_tempo.py")
    }},sort_keys=True,indent=2).encode()+b"\n"


def archive(path: Path, files: dict[str, bytes]):
    with tarfile.open(path,"w:gz",format=tarfile.PAX_FORMAT) as tf:
        for name,data in sorted(files.items()):
            info=tarfile.TarInfo(name); info.size=len(data); info.mtime=0; info.mode=0o644
            tf.addfile(info,io.BytesIO(data))


class GateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        config={"consumer":"frozen","spatial_pathing":False,"spatial_tempo":False,
                "idle_fertilizer":True,"crop_release":True,"weed_continuation":False}
        self.files={"main.py":MAIN.encode(),"titan_runtime.py":RUNTIME.encode(),
                    "spatial_tempo.py":SPATIAL.encode(),
                    "TITAN-CONFIG.json":json.dumps(config,sort_keys=True).encode()+b"\n"}
        self.files["SOURCE.json"]=strict_manifest(self.files)
        self.base=self.root/"base.tar.gz"; archive(self.base,self.files)

    def tearDown(self): self.temp.cleanup()

    def contract(self, **updates):
        parsed=gate.read_archive(self.base)
        data={"schema":1,"expected_base":{"sha256":parsed.sha256,"bytes":parsed.size,
              "members":parsed.member_count},"required_touched_members":[],
              "allowed_changed_members":[],"allowed_added_members":[],
              "allowed_deleted_members":[],
              "manifest_bound_members":["TITAN-CONFIG.json","titan_runtime.py","spatial_tempo.py"],
              "probe_timeout_seconds":15}
        data.update(updates); path=self.root/"contract.json"
        path.write_text(json.dumps(data)); return path


    def verify_mutation_fails_probe(self, *, runtime=None, spatial=None):
        files=dict(self.files)
        if runtime is not None: files["titan_runtime.py"]=runtime.encode()
        if spatial is not None: files["spatial_tempo.py"]=spatial.encode()
        files["SOURCE.json"]=strict_manifest(files)
        candidate=self.root/("mutation-%d.tar.gz" % len(list(self.root.glob("mutation-*.tar.gz"))))
        archive(candidate,files)
        changed=[]
        if runtime is not None: changed.append("titan_runtime.py")
        if spatial is not None: changed.append("spatial_tempo.py")
        changed.append("SOURCE.json")
        contract=self.contract(allowed_changed_members=changed)
        with self.assertRaises(gate.GateFailure) as caught:
            gate.verify(self.base,candidate,contract,ROOT/"runtime_probe.py")
        self.assertEqual(caught.exception.code,"probe.failed")
        return caught.exception.message

    def test_full_executable_matrix_passes(self):
        receipt=gate.verify(self.base,self.base,self.contract(),ROOT/"runtime_probe.py")
        self.assertEqual(receipt["status"],"PASS")
        self.assertEqual(len(receipt["probe"]["matrix"]),32)
        self.assertEqual(len(receipt["probe"]["reachability"]),8)
        self.assertTrue(receipt["probe"]["stale_w0_reinitialization"]["retained_idle_fertilizer"])


    def test_mutation_kills_coupled_construction_gate(self):
        broken=RUNTIME.replace(
            "if any((f.spatial_pathing,f.spatial_tempo,f.idle_fertilizer,f.crop_release,f.weed_continuation)):",
            "if f.spatial_pathing or f.spatial_tempo:")
        message=self.verify_mutation_fails_probe(runtime=broken)
        self.assertIn("capability mask",message)

    def test_mutation_kills_hidden_w0_call(self):
        broken=SPATIAL.replace(
            "if self.weed_continuation and self._continue_weed(obs,selected,controller,24): return selected",
            "if self._continue_weed(obs,selected,controller,24): return selected")
        message=self.verify_mutation_fails_probe(spatial=broken)
        self.assertIn("reachability mismatch",message)

    def test_mutation_kills_stale_w1_reinstall(self):
        broken=SPATIAL.replace(
            "if self.weed_continuation: return",
            "return  # mutation: never scrub",1)
        message=self.verify_mutation_fails_probe(spatial=broken)
        self.assertIn("retained stale weed state",message)

    def test_mutation_kills_true_feature_default(self):
        broken=RUNTIME.replace("weed_continuation: bool = False",
                               "weed_continuation: bool = True")
        message=self.verify_mutation_fails_probe(runtime=broken)
        self.assertIn("must default to literal False",message)

    def test_mutation_kills_unconditional_all_off_install(self):
        broken=RUNTIME.replace(
            "if any((f.spatial_pathing,f.spatial_tempo,f.idle_fertilizer,f.crop_release,f.weed_continuation)):",
            "if True:")
        message=self.verify_mutation_fails_probe(runtime=broken)
        self.assertIn("expected spatial=False",message)

    def test_missing_explicit_w0_holds(self):
        files=dict(self.files); config=json.loads(files["TITAN-CONFIG.json"])
        del config["weed_continuation"]
        files["TITAN-CONFIG.json"]=json.dumps(config).encode(); files["SOURCE.json"]=strict_manifest(files)
        candidate=self.root/"missing.tar.gz"; archive(candidate,files)
        contract=self.contract(allowed_changed_members=["TITAN-CONFIG.json","SOURCE.json"])
        with self.assertRaises(gate.GateFailure) as caught:
            gate.verify(self.base,candidate,contract,ROOT/"runtime_probe.py")
        self.assertEqual(caught.exception.code,"config.weed_continuation_missing")

    def test_config_w0_must_be_literal_false(self):
        for value in (True, 0, "false", None):
            with self.subTest(value=value):
                files=dict(self.files); config=json.loads(files["TITAN-CONFIG.json"])
                config["weed_continuation"]=value
                files["TITAN-CONFIG.json"]=json.dumps(config).encode()
                files["SOURCE.json"]=strict_manifest(files)
                candidate=self.root/("bad-w0-%s.tar.gz" % type(value).__name__)
                archive(candidate,files)
                contract=self.contract(allowed_changed_members=["TITAN-CONFIG.json","SOURCE.json"])
                with self.assertRaises(gate.GateFailure) as caught:
                    gate.verify(self.base,candidate,contract,ROOT/"runtime_probe.py")
                self.assertEqual(caught.exception.code,"config.weed_continuation_not_false")

    def test_manifest_must_bind_changed_source(self):
        files=dict(self.files); files["spatial_tempo.py"]+=b"# drift\n"
        candidate=self.root/"drift.tar.gz"; archive(candidate,files)
        contract=self.contract(allowed_changed_members=["spatial_tempo.py"])
        with self.assertRaises(gate.GateFailure) as caught:
            gate.verify(self.base,candidate,contract,ROOT/"runtime_probe.py")
        self.assertEqual(caught.exception.code,"manifest.hash")

    def test_unlisted_member_change_holds(self):
        files=dict(self.files); files["main.py"]+=b"# drift\n"
        candidate=self.root/"drift.tar.gz"; archive(candidate,files)
        with self.assertRaises(gate.GateFailure) as caught:
            gate.verify(self.base,candidate,self.contract(),ROOT/"runtime_probe.py")
        self.assertEqual(caught.exception.code,"delta.changed")

    def test_required_touch_is_enforced(self):
        contract=self.contract(required_touched_members=["titan_runtime.py"],
                               allowed_changed_members=["titan_runtime.py"])
        with self.assertRaises(gate.GateFailure) as caught:
            gate.verify(self.base,self.base,contract,ROOT/"runtime_probe.py")
        self.assertEqual(caught.exception.code,"delta.required")

    def test_archive_rejects_duplicate_and_link_members(self):
        duplicate=self.root/"duplicate.tar.gz"
        with tarfile.open(duplicate,"w:gz") as tf:
            for _ in range(2):
                info=tarfile.TarInfo("main.py"); info.size=1; tf.addfile(info,io.BytesIO(b"x"))
        with self.assertRaises(gate.GateFailure) as caught:
            gate.read_archive(duplicate)
        self.assertEqual(caught.exception.code,"archive.duplicate")
        link=self.root/"link.tar.gz"
        with tarfile.open(link,"w:gz") as tf:
            info=tarfile.TarInfo("escape"); info.type=tarfile.SYMTYPE; info.linkname="../../x"; tf.addfile(info)
        with self.assertRaises(gate.GateFailure) as caught:
            gate.read_archive(link)
        self.assertEqual(caught.exception.code,"archive.member_type")

    def test_regular_file_parent_collision_is_rejected(self):
        collision=self.root/"collision.tar.gz"
        with tarfile.open(collision,"w:gz") as tf:
            parent=tarfile.TarInfo("a"); parent.size=1; tf.addfile(parent,io.BytesIO(b"x"))
            child=tarfile.TarInfo("a/b"); child.size=1; tf.addfile(child,io.BytesIO(b"y"))
        with self.assertRaises(gate.GateFailure) as caught:
            gate.read_archive(collision)
        self.assertEqual(caught.exception.code,"archive.path_collision")

    def test_pass_receipt_is_path_independent(self):
        contract=self.contract()
        first=gate.verify(self.base,self.base,contract,ROOT/"runtime_probe.py")
        copied=self.root/"nested"/"renamed.tar.gz"; copied.parent.mkdir(); copied.write_bytes(self.base.read_bytes())
        second=gate.verify(copied,copied,contract,ROOT/"runtime_probe.py")
        self.assertEqual(first["receipt_sha256"],second["receipt_sha256"])
        self.assertNotIn("path",first["base"])

    def test_json_rejects_duplicate_keys_and_nonfinite(self):
        for raw,code in ((b'{"a":1,"a":2}',"json.duplicate_key"),(b'{"a":NaN}',"json.non_finite")):
            with self.assertRaises(gate.GateFailure) as caught:
                gate._strict_json_bytes(raw,"fixture")
            self.assertEqual(caught.exception.code,code)

    def test_base_identity_is_exact(self):
        contract=json.loads(self.contract().read_text()); contract["expected_base"]["sha256"]="0"*64
        path=self.root/"wrong.json"; path.write_text(json.dumps(contract))
        with self.assertRaises(gate.GateFailure) as caught:
            gate.verify(self.base,self.base,path,ROOT/"runtime_probe.py")
        self.assertEqual(caught.exception.code,"base.sha256")


if __name__=="__main__": unittest.main()
