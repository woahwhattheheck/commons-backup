#!/usr/bin/env python3
"""Synthetic/read-only CSU malt cutoff, expansion, routing, and QC bridge."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import argparse, copy, hashlib, json, re

TASK_ID="csu-malt-method-expansion-lims-01"; CURRENT="CURRENT_WEEK"; NEXT="NEXT_WEEK"
DUP="DUPLICATE_ID"; UNSUP="UNSUPPORTED_GRAIN_METHOD"; MISS="MISSING_IDENTITY_PACKAGE"
STAGED="STAGED_HUMAN_REVIEW"; RELEASED="RELEASED_BY_NAMED_HUMAN"
RESERVED_REVIEWER_TOKENS=frozenset({"ai","agent","auto","automated","automation","bot","robot","service","system"})

def digest(v): return hashlib.sha256((json.dumps(v,sort_keys=True,separators=(",",":"))+"\n").encode()).hexdigest()
def file_sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def _named_human(reviewer):
    if not isinstance(reviewer,str): return None
    name=reviewer.strip()
    if not name: return None
    tokens=[t.casefold() for t in re.findall(r"[A-Za-z]+",name)]
    if len(tokens)<2 or any(t in RESERVED_REVIEWER_TOKENS for t in tokens): return None
    return name

@dataclass
class Ledger:
    seen:set[str]=field(default_factory=set); seen_payloads:dict[str,str]=field(default_factory=dict)
    accessions:dict=field(default_factory=dict); jobs:dict=field(default_factory=dict); reports:dict=field(default_factory=dict)
    holds:dict=field(default_factory=dict); events:list=field(default_factory=list)
    def counts(self): return {"processed":len(self.seen),"accessions":len(self.accessions),"jobs":len(self.jobs),"reports":len(self.reports),"holds":len(self.holds),"events":len(self.events)}

def load(fixture,manifest):
    m=json.loads(Path(manifest).read_text()); actual=file_sha(fixture)
    if actual!=m["fixture_sha256"]: raise ValueError(f"FIXTURE_HASH_MISMATCH expected={m['fixture_sha256']} actual={actual}")
    p=json.loads(Path(fixture).read_text())
    if p.get("task_id")!=TASK_ID or p.get("schema_version")!=2: raise ValueError("FIXTURE_RECIPE_INVALID")
    rows=[]
    for i in range(1,61):
        rows.append(row(i,"BEFORE_CUTOFF","PROTEIN_PANEL" if i<=6 else "CORE",qc="QC-BREACH-01" if i in (7,8) else f"QC-{((i-1)//10)+1:02d}",ok=i not in (7,8)))
    for i in range(61,69): rows.append(row(i,"AFTER_CUTOFF","CORE",qc="QC-07"))
    for i in range(69,73): rows.append(row(i,"BEFORE_CUTOFF","CORE",sample=f"MALT-{i-68:03d}",fault=DUP,qc="QC-08"))
    for i in range(73,77): rows.append(row(i,"BEFORE_CUTOFF","CORE",grain="SORGHUM",fault=UNSUP,qc="QC-08"))
    for i in range(77,81): rows.append(row(i,"BEFORE_CUTOFF",None if i%2==0 else "CORE",sample=None if i%2 else f"MALT-{i:03d}",fault=MISS,qc="QC-08"))
    if len(rows)!=80: raise AssertionError("FIXTURE_RECIPE_COUNT")
    return rows,m

def row(i,phase,package,sample="AUTO",grain="BARLEY",fault=None,qc="QC-01",ok=True):
    if sample=="AUTO": sample=f"MALT-{i:03d}"
    return {"submission_id":f"SUB-{i:03d}","sample_id":sample,"grain":grain,"package":package,"received_phase":phase,"qc_batch":qc,"qc_ok":ok,"seeded_fault":fault,"source_ref":f"synthetic://csu/malt/{i:03d}.json"}

def reserved_samples(L):
    return set(L.accessions) | {h["sample_id"] for h in L.holds.values() if h.get("sample_id")}

def classify(r,L,m):
    if not r["sample_id"] or not r["package"]: return MISS
    phase=r.get("received_phase")
    if phase not in ("BEFORE_CUTOFF","AFTER_CUTOFF"): raise ValueError("RECEIVED_PHASE_INVALID")
    if r["sample_id"] in reserved_samples(L): return DUP
    if r["grain"] not in m["supported_grains_by_package"].get(r["package"],[]): return UNSUP
    return CURRENT if phase=="BEFORE_CUTOFF" else NEXT

def process(r,L,m):
    sid=r["submission_id"]; fingerprint=digest(r)
    if sid in L.seen:
        if L.seen_payloads.get(sid)!=fingerprint: raise ValueError("SUBMISSION_ID_PAYLOAD_MISMATCH")
        return "IDEMPOTENT_REPLAY"
    status=classify(r,L,m); L.seen.add(sid); L.seen_payloads[sid]=fingerprint
    if status in (DUP,UNSUP,MISS):
        L.holds[sid]={"sample_id":r["sample_id"],"hold_code":status}; L.events.append((sid,"HOLD",status)); return status
    sample=r["sample_id"]; L.accessions[sample]={"submission_id":sid,"sample_id":sample,"package":r["package"],"week_route":status,"source_hash":digest([r["source_ref"],sample])}
    methods=m["package_methods"][r["package"]]
    for method in methods:
        jid=f"{sample}:{method['method_id']}"
        if jid in L.jobs: raise AssertionError("DUPLICATE_JOB")
        j={"job_id":jid,"sample_id":sample,"method_id":method["method_id"],"method_version":method["method_version"],"unit":method["unit"],"route":"THIRD_PARTY" if method["method_id"]=="ASBC-PROTEIN" else "INTERNAL","week_route":status,"qc_batch":r["qc_batch"]}
        j["job_hash"]=digest(j); L.jobs[jid]=j
    if r["qc_ok"]:
        L.reports[sample]={"sample_id":sample,"status":STAGED,"reviewer":None,"expansion_hash":digest([x["method_id"] for x in methods])}; L.events.append((sid,"STAGE_REPORT",STAGED))
    else: L.events.append((sid,"QC_BLOCK_REPORT",r["qc_batch"]))
    return status

def run(rows,m,L=None):
    L=L or Ledger(); before=L.counts(); statuses={}
    for r in rows:
        s=process(r,L,m); statuses[s]=statuses.get(s,0)+1
    after=L.counts(); return L,statuses,{k:after[k]-before[k] for k in before}

def release(L,sample,reviewer):
    reviewer=_named_human(reviewer)
    if reviewer is None: raise ValueError("NAMED_HUMAN_REVIEWER_REQUIRED")
    if sample not in L.reports: raise KeyError("REPORT_NOT_FOUND")
    out=copy.deepcopy(L.reports[sample]); out.update(status=RELEASED,reviewer=reviewer); return out

def verify(rows,m,L,statuses):
    expected={CURRENT:60,NEXT:8,DUP:4,UNSUP:4,MISS:4}
    if statuses!=expected: raise AssertionError((statuses,expected))
    if L.counts()!={"processed":80,"accessions":68,"jobs":130,"reports":66,"holds":12,"events":80}: raise AssertionError(L.counts())
    third=[j for j in L.jobs.values() if j["route"]=="THIRD_PARTY"]
    if len(third)!=6 or any(j["method_id"]!="ASBC-PROTEIN" for j in third): raise AssertionError("THIRD_PARTY_PROTEIN")
    blocked={r["sample_id"] for r in rows if r["qc_batch"]=="QC-BREACH-01"}
    if len(blocked)!=2 or not blocked.isdisjoint(L.reports): raise AssertionError("QC_BREACH_REPORT")
    for a in L.accessions.values():
        got=sorted(j["method_id"] for j in L.jobs.values() if j["sample_id"]==a["sample_id"]); want=sorted(x["method_id"] for x in m["package_methods"][a["package"]])
        if got!=want: raise AssertionError("EXPANSION_MISMATCH")
    if any(r["status"]!=STAGED or r["reviewer"] is not None for r in L.reports.values()): raise AssertionError("RELEASE_POLICY")
    return {"status_counts":statuses,"ledger_counts":L.counts(),"third_party_protein_jobs":6,"qc_breach_batches":1}

def main(argv=None):
    here=Path(__file__).parent; p=argparse.ArgumentParser(); p.add_argument("--fixture",type=Path,default=here/"fixtures/csu_80_submissions.json"); p.add_argument("--manifest",type=Path,default=here/"fixtures/manifest.json"); a=p.parse_args(argv)
    rows,m=load(a.fixture,a.manifest); L,s,_=run(rows,m); acc=verify(rows,m,L,s); before=L.counts(); _,rs,delta=run(rows,m,L)
    if delta!={k:0 for k in before} or L.counts()!=before or rs!={"IDEMPOTENT_REPLAY":80}: raise AssertionError("REPLAY_NOT_IDEMPOTENT")
    print(json.dumps({"task_id":TASK_ID,"acceptance":acc,"replay_delta":delta,"release_policy":STAGED},sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
