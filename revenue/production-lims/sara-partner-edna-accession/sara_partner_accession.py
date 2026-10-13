"""Synthetic/read-only SARA partner eDNA/qPCR accession shadow."""
from __future__ import annotations
import copy, hashlib, json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

DEMAND_ID="sara-partner-edna-accession-lims-01"
MANIFEST_PREFIX="SARA-PARTNER-EDNA-SYNTHETIC-MANIFEST-V1\n"
HOLD_CODES=("MISSING_SUBMITTER_OR_CUSTODY","MATRIX_ANALYTE_MISMATCH","DUPLICATE_ID","HOLD_TIME_BREACH","PARTNER_CLIENT_IDENTITY_MISMATCH","QPCR_CONTROL_FAIL")
FACILITY_ID="SARA-REGIONAL-ENV-LAB"
PROGRAM_CLIENT={"SARA_INTERNAL":"CLIENT-SARA-INTERNAL","PARTNER_GBRA":"CLIENT-GUADALUPE-BLANCO","PARTNER_NUECES":"CLIENT-NUECES-RIVER","PARTNER_UPPER_GUADALUPE":"CLIENT-UPPER-GUADALUPE"}
ROUTES={
    ("WATER","EDNA_FISH"):("SCOPE-EDNA-WATER","EDNA-FISH-R3","EDNA-4.2"),
    ("WATER","QPCR_ENTEROCOCCUS"):("SCOPE-QPCR-WATER","QPCR-ENTERO-R5","QPCR-5.1"),
    ("SEDIMENT","EDNA_INVASIVE_MUSSEL"):("SCOPE-EDNA-SEDIMENT","EDNA-MUSSEL-R2","EDNA-4.1"),
}
RESERVED={"auto","automatic","automation","bot","system","service","service-account","agent","ai","scheduler","worker","pipeline","anonymous","unknown"}
FORBIDDEN={"patient","patient_name","dob","mrn","medical_record_number","diagnosis","ssn","password","secret","token","api_key"}

class IntegrityError(ValueError): pass
def _canon(v:Any)->str:return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False)
def _sha(s:str)->str:return hashlib.sha256(s.encode()).hexdigest()
def _record_hash(r:Mapping[str,Any])->str:return _sha(_canon(r))
def _manifest_routes():
    return {f"{m}|{a}":{"scope_id":s,"panel_version":p,"method_version":v} for (m,a),(s,p,v) in ROUTES.items()}
def _envelope(m):
    keys=("demand_id","fixture_version","dataset_sha256","expanded_records_sha256","record_count","expected_ready","expected_hold","expected_hold_codes","facility_id","program_client","routes","control_batch_size")
    return {k:m[k] for k in keys}
def verify_manifest_signature(m):
    if m.get("signature_alg")!="sha256-content-envelope-v1" or m.get("signature")!=_sha(MANIFEST_PREFIX+_canon(_envelope(m))):raise IntegrityError("manifest signature mismatch")

def _route(i):
    m,a=tuple(ROUTES)[(i-1)%len(ROUTES)]; s,p,v=ROUTES[(m,a)]; return m,a,s,p,v
def _program(i):
    p=tuple(PROGRAM_CLIENT)[(i-1)%len(PROGRAM_CLIENT)]; return p,PROGRAM_CLIENT[p]
def _hashes(r):
    source={k:r[k] for k in ("record_id","external_submission_id","program_id","client_id","submitter_id","facility_id","matrix","analyte","scope_id","panel_version","method_version","control_batch_id","control_pass","collection_hour","receipt_hour","hold_time_hours","raw_value","unit","qualifier")}
    custody={k:r[k] for k in ("container_id","coc_id","custody_complete","custody_events")}
    route={k:r[k] for k in ("facility_id","scope_id","panel_version","method_version","control_batch_id","program_id","client_id")}
    report={k:r[k] for k in ("record_id","external_submission_id","program_id","client_id","scope_id","panel_version","method_version","raw_value","unit","qualifier")}
    return {"source_sha256":_sha(_canon(source)),"custody_sha256":_sha(_canon(custody)),"route_sha256":_sha(_canon(route)),"expected_report_digest":_sha(_canon(report))}

def _expand(i:int,truth:str|None):
    matrix,analyte,scope,panel,version=_route(i); program,client=_program(i)
    ext=f"SARA-SUB-{i:04d}"; submitter=f"SUBMITTER-SYN-{((i-1)%24)+1:03d}"; complete=True
    custody=["COLLECTED","COC_SIGNED","RECEIVED","ACCESSION_REVIEW"]
    receipt,limit=12,24; batch=f"CTRL-{((i-1)//4)+1:03d}"; control=True
    if truth==HOLD_CODES[0]:
        if i%2: submitter=None
        else: complete=False; custody=["COLLECTED","RECEIVED"]
    elif truth==HOLD_CODES[1]: analyte={"WATER":"EDNA_INVASIVE_MUSSEL","SEDIMENT":"QPCR_ENTEROCOCCUS"}[matrix]
    elif truth==HOLD_CODES[2]: ext=f"SARA-SUB-{i-208:04d}"
    elif truth==HOLD_CODES[3]: receipt,limit=49,48
    elif truth==HOLD_CODES[4]:
        ps=tuple(PROGRAM_CLIENT); client=PROGRAM_CLIENT[ps[(ps.index(program)+1)%len(ps)]]
    elif truth==HOLD_CODES[5]:
        matrix,analyte="WATER","QPCR_ENTEROCOCCUS"; scope,panel,version=ROUTES[(matrix,analyte)]
        batch="CTRL-FAIL-A" if i<=236 else "CTRL-FAIL-B"; control=i not in (233,237)
    r={"record_id":f"SARA-REC-{i:04d}","deidentified":True,"external_submission_id":ext,"program_id":program,"client_id":client,"submitter_id":submitter,"facility_id":FACILITY_ID,"container_id":f"CONTAINER-SYN-{i:04d}","coc_id":f"COC-SYN-{i:04d}","custody_complete":complete,"custody_events":custody,"matrix":matrix,"analyte":analyte,"scope_id":scope,"panel_version":panel,"method_version":version,"control_batch_id":batch,"control_pass":control,"collection_hour":0,"receipt_hour":receipt,"hold_time_hours":limit,"raw_value":i*17,"unit":"copies/L","qualifier":"SYNTHETIC","truth_hold":truth}
    r.update(_hashes(r)); return r

def _rows(payload):
    if payload.get("schema")!="deterministic-generator-v1":raise IntegrityError("fixture schema mismatch")
    g=payload.get("generator")
    if not isinstance(g,dict) or (g.get("record_count"),g.get("clean_count"))!=(240,192):raise IntegrityError("fixture generator dimensions mismatch")
    holds={}
    for seg in g.get("hold_segments",[]):
        code,start,count=seg.get("code"),seg.get("start"),seg.get("count")
        if code not in HOLD_CODES or not isinstance(start,int) or isinstance(start,bool) or not isinstance(count,int) or isinstance(count,bool):raise IntegrityError("invalid HOLD segment")
        for n in range(start,start+count):
            if n in holds or not 1<=n<=240:raise IntegrityError("overlapping/out-of-range HOLD segment")
            holds[n]=code
    if set(holds)!=set(range(193,241)):raise IntegrityError("HOLD segments must cover 193..240")
    return [(i,holds.get(i)) for i in range(1,241)]

def verify_records(records,m):
    verify_manifest_signature(m)
    if m.get("demand_id")!=DEMAND_ID or len(records)!=m.get("record_count") or m.get("facility_id")!=FACILITY_ID:raise IntegrityError("manifest/record mismatch")
    if m.get("program_client")!=PROGRAM_CLIENT or m.get("routes")!=_manifest_routes() or m.get("control_batch_size")!=4:raise IntegrityError("manifest contract mismatch")
    if _sha(_canon(records))!=m.get("expanded_records_sha256"):raise IntegrityError("expanded record hash mismatch")
    truth=Counter(r["truth_hold"] for r in records if r["truth_hold"])
    if truth!=Counter(m.get("expected_hold_codes",{})) or len(records)-sum(truth.values())!=m.get("expected_ready"):raise IntegrityError("truth-set mismatch")
    if len({r["record_id"] for r in records})!=len(records):raise IntegrityError("duplicate record_id")
    for r in records:
        if not r.get("deidentified") or ({str(k).lower() for k in r}&FORBIDDEN):raise IntegrityError("fixture safety boundary")
        if any(r.get(k)!=v for k,v in _hashes(r).items()):raise IntegrityError("provenance hash mismatch")

def load_fixture(fixture_path=None,manifest_path=None):
    base=Path(__file__).resolve().parent/"fixtures"; fp=Path(fixture_path) if fixture_path else base/"sara_240_submissions.json"; mp=Path(manifest_path) if manifest_path else base/"manifest.json"
    text=fp.read_text(); m=json.loads(mp.read_text())
    if _sha(text)!=m.get("dataset_sha256"):raise IntegrityError("dataset file hash mismatch")
    payload=json.loads(text)
    if payload.get("fixture_version")!=m.get("fixture_version"):raise IntegrityError("fixture version mismatch")
    records=[_expand(i,t) for i,t in _rows(payload)]; verify_records(records,m); return records,m

def _classify(r,seen,failed):
    if not isinstance(r.get("submitter_id"),str) or not r["submitter_id"] or not r.get("custody_complete"):return HOLD_CODES[0]
    route=ROUTES.get((r.get("matrix"),r.get("analyte")))
    if route is None or tuple(r.get(k) for k in ("scope_id","panel_version","method_version"))!=route:return HOLD_CODES[1]
    ext=r.get("external_submission_id")
    if not isinstance(ext,str) or not ext or ext in seen:return HOLD_CODES[2]
    vals=(r.get("collection_hour"),r.get("receipt_hour"),r.get("hold_time_hours"))
    if any(isinstance(v,bool) or not isinstance(v,int) for v in vals) or vals[1]-vals[0]>vals[2]:return HOLD_CODES[3]
    if PROGRAM_CLIENT.get(r.get("program_id"))!=r.get("client_id"):return HOLD_CODES[4]
    if r.get("control_batch_id") in failed:return HOLD_CODES[5]

def _named_human(name):
    if not isinstance(name,str):raise PermissionError("named human reviewer required")
    n=" ".join(name.strip().split()); low=n.casefold(); toks="".join(c if c.isalnum() else " " for c in low).split()
    if not n or low in RESERVED or any(t in RESERVED for t in toks):raise PermissionError("named human reviewer required")
    if len([t for t in toks if any(c.isalpha() for c in t)])<2:raise PermissionError("two-token human name required")
    return n

@dataclass
class ReplayReport:
    ready:int; hold:int; replayed:int; hold_counts:dict[str,int]; accessions_added:int; jobs_added:int; reports_added:int; holds_added:int; events_added:int; state_digest:str; outcomes:list[dict[str,Any]]

class SaraPartnerAccessionShadow:
    def __init__(self,authoritative_state=None):
        self.authoritative_state=copy.deepcopy(authoritative_state or {}); self._af=_sha(_canon(self.authoritative_state))
        self.accessions={}; self.jobs={}; self.staged_reports={}; self.holds={}; self.events=[]; self._seen=set(); self._external=set()
    @property
    def authoritative_fingerprint(self):
        if _sha(_canon(self.authoritative_state))!=self._af:raise IntegrityError("authoritative state mutated")
        return self._af
    def state_digest(self):return _sha(_canon({"accessions":self.accessions,"jobs":self.jobs,"staged_reports":self.staged_reports,"holds":self.holds,"events":self.events,"seen":sorted(self._seen),"external":sorted(self._external)}))
    def replay(self,records,m):
        verify_records(records,m); self.authoritative_fingerprint
        failed={r["control_batch_id"] for r in records if r.get("control_pass") is False}
        ready=hold=replayed=aa=ja=ra=ha=ea=0; counts=Counter(); outcomes=[]
        for r in records:
            rid=r["record_id"]
            if rid in self._seen:
                replayed+=1; outcomes.append({"record_id":rid,"status":"IDEMPOTENT_REPLAY","hold_code":self.holds.get(rid,{}).get("hold_code"),"record_sha256":_record_hash(r)}); continue
            code=_classify(r,self._external,failed)
            if code!=r["truth_hold"]:raise IntegrityError(f"classifier/truth mismatch {rid}")
            before=(
                copy.deepcopy(dict(self.accessions)),
                copy.deepcopy(dict(self.jobs)),
                copy.deepcopy(dict(self.staged_reports)),
                copy.deepcopy(dict(self.holds)),
                copy.deepcopy(list(self.events)),
                set(self._seen),
                set(self._external),
            )
            try:
                self._seen.add(rid)
                if code!=HOLD_CODES[2]:self._external.add(r["external_submission_id"])
                if code:
                    self.holds[rid]={"record_id":rid,"hold_code":code,"jobs_created":0,"report_created":0,"program_id":r["program_id"],"client_id":r["client_id"]}
                    out={"record_id":rid,"status":"HOLD","hold_code":code,"jobs_created":0,"report_created":0,"record_sha256":_record_hash(r)}
                else:
                    client=PROGRAM_CLIENT[r["program_id"]]
                    if r["client_id"]!=client:raise IntegrityError("client/program leak")
                    acc=f"ACC-{rid[-4:]}"; self.accessions[rid]={"record_id":rid,"accession_id":acc,"external_submission_id":r["external_submission_id"],"facility_id":r["facility_id"],"program_id":r["program_id"],"client_id":client,"source_sha256":r["source_sha256"],"custody_sha256":r["custody_sha256"]}
                    self.jobs[rid]={"record_id":rid,"accession_id":acc,"facility_id":r["facility_id"],"scope_id":r["scope_id"],"panel_version":r["panel_version"],"method_version":r["method_version"],"control_batch_id":r["control_batch_id"],"route_sha256":r["route_sha256"],"state":"STAGED_NOT_STARTED"}
                    self.staged_reports[rid]={"record_id":rid,"state":"STAGED_HUMAN_QA","program_id":r["program_id"],"client_id":client,"facility_id":r["facility_id"],"report_digest":r["expected_report_digest"],"source_sha256":r["source_sha256"],"custody_sha256":r["custody_sha256"],"released_by":None,"sent":False}
                    out={"record_id":rid,"status":"READY","hold_code":None,"facility_id":r["facility_id"],"scope_id":r["scope_id"],"panel_version":r["panel_version"],"control_batch_id":r["control_batch_id"],"program_id":r["program_id"],"client_id":client,"source_sha256":r["source_sha256"],"custody_sha256":r["custody_sha256"],"report_digest":r["expected_report_digest"],"sent":False,"record_sha256":_record_hash(r)}
                self.events.append({"sequence":len(self.events)+1,"record_id":rid,"status":out["status"],"hold_code":out["hold_code"],"record_sha256":out["record_sha256"]})
            except Exception:
                (
                    self.accessions,
                    self.jobs,
                    self.staged_reports,
                    self.holds,
                    self.events,
                    self._seen,
                    self._external,
                )=before
                raise
            if code:
                hold+=1; counts[code]+=1; ha+=1
            else:
                ready+=1; aa+=1; ja+=1; ra+=1
            ea+=1; outcomes.append(out)
        if not replayed and (ready!=m["expected_ready"] or hold!=m["expected_hold"] or counts!=Counter(m["expected_hold_codes"])):raise IntegrityError("replay counts mismatch")
        self.authoritative_fingerprint
        return ReplayReport(ready,hold,replayed,dict(sorted(counts.items())),aa,ja,ra,ha,ea,self.state_digest(),outcomes)
    def release_report(self,rid,reviewer_name):
        reviewer=_named_human(reviewer_name); report=self.staged_reports.get(rid)
        if report is None:raise KeyError(rid)
        if report["state"]!="STAGED_HUMAN_QA" or report["released_by"] is not None:raise PermissionError("not eligible")
        out=copy.deepcopy(report); out["state"]="RELEASED_BY_NAMED_HUMAN"; out["released_by"]=reviewer; return out
    def automatic_release(self,*_,**__):raise PermissionError("automatic release disabled")

def run_acceptance():
    records,m=load_fixture(); s=SaraPartnerAccessionShadow({"adapter_mode":"read-only","production_writes":0}); first=s.replay(records,m); digest=first.state_digest; second=s.replay(records,m)
    if second.replayed!=240 or any((second.accessions_added,second.jobs_added,second.reports_added,second.holds_added,second.events_added)) or second.state_digest!=digest:raise IntegrityError("replay not idempotent")
    released=s.release_report(next(iter(s.staged_reports)),"Jordan Reviewer")
    return {"demand_id":DEMAND_ID,"ready":first.ready,"hold":first.hold,"hold_counts":first.hold_counts,"accessions":len(s.accessions),"jobs":len(s.jobs),"staged_reports":len(s.staged_reports),"replay_zero_add":True,"state_digest":digest,"authoritative_fingerprint":s.authoritative_fingerprint,"release_state":released["state"],"released_by":released["released_by"],"sent":released["sent"]}
if __name__=="__main__":print(json.dumps(run_acceptance(),sort_keys=True))