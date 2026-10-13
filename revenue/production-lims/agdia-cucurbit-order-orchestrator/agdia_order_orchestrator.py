"""Synthetic/deidentified Agdia cucurbit mail-in order orchestration shadow."""
from __future__ import annotations
import copy, hashlib, json, re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEMAND_ID="agdia-cucurbit-order-orchestrator-lims-01"
MANIFEST_PREFIX="AGDIA-CUCURBIT-SYNTHETIC-MANIFEST-V1\n"
HOLD_CODES=("ORPHAN_OR_MISSING_FORM","MISSING_TUBE","PERMIT_REFERENCE_INVALID","LICENSE_REFERENCE_INVALID","CROP_PANEL_MISMATCH","ASSAY_VERSION_UNAPPROVED")
SPECS=(
    ("CUCUMBER","CUC-VIRUS-A","R3"),
    ("MELON","CUC-VIRUS-B","R2"),
    ("SQUASH","CUC-PATHOGEN-C","R4"),
)
FORBIDDEN_PHI_KEYS={"patient","patient_name","dob","mrn","medical_record_number","diagnosis","ssn"}
RESERVED_RELEASE_ACTORS={"agent","automation","system","bot","autonomous","auto","service","ai"}

class IntegrityError(ValueError): pass
def _canon(v:Any)->str:return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False)
def _sha(v:str)->str:return hashlib.sha256(v.encode("utf-8")).hexdigest()
def _record_hash(r):return _sha(_canon(r))
def _envelope(m):
    keys=("demand_id","fixture_version","dataset_sha256","expanded_records_sha256","record_count","expected_ready","expected_hold","expected_hold_codes","aliquots_per_case","approved_specs")
    return {k:m[k] for k in keys}
def verify_manifest_signature(m):
    if m.get("signature_alg")!="sha256-content-envelope-v1":raise IntegrityError("unsupported manifest signature algorithm")
    if m.get("signature")!=_sha(MANIFEST_PREFIX+_canon(_envelope(m))):raise IntegrityError("manifest signature mismatch")

def _hashes(*,case_id,package_id,form_id,tube_ids,package_count,form_count,tube_count,crop,panel,assay_version,contact_id,custody):
    source={"case_id":case_id,"package_id":package_id,"form_id":form_id,"tube_ids":tube_ids,"package_count":package_count,"form_count":form_count,"tube_count":tube_count,"crop":crop,"panel":panel,"assay_version":assay_version,"contact_id":contact_id}
    return {"source_sha256":_sha(_canon(source)),"custody_sha256":_sha(_canon(custody)),"route_sha256":_sha(_canon({"crop":crop,"panel":panel,"assay_version":assay_version,"designated_contact_id":contact_id}))}

def _expand(row):
    if len(row)!=2:raise IntegrityError("fixture row width mismatch")
    n,truth=row
    if not isinstance(n,int) or not 1<=n<=300:raise IntegrityError("fixture row out of range")
    crop,panel,version=SPECS[(n-1)%3]
    case=f"AGDIA-CASE-{n:04d}"; pkg=f"PKG-SYN-{n:04d}"; form=f"FORM-SYN-{n:04d}"
    tubes=[f"TUBE-SYN-{n:04d}-A",f"TUBE-SYN-{n:04d}-B"]; pc=fc=1; tc=2
    permit_active=license_active=True; contact=f"CONTACT-SYN-{((n-1)%20)+1:03d}"
    custody=["MAIL_RECEIVED","PACKAGE_OPENED","FORM_MATCHED","TUBES_RECONCILED"]
    if truth=="ORPHAN_OR_MISSING_FORM": form=None; fc=0; custody=["MAIL_RECEIVED","PACKAGE_OPENED"]
    elif truth=="MISSING_TUBE": tubes=tubes[:1]; tc=1; custody=["MAIL_RECEIVED","PACKAGE_OPENED","FORM_MATCHED"]
    elif truth=="PERMIT_REFERENCE_INVALID":permit_active=False
    elif truth=="LICENSE_REFERENCE_INVALID":license_active=False
    elif truth=="CROP_PANEL_MISMATCH":panel={"CUCUMBER":"CUC-PATHOGEN-C","MELON":"CUC-VIRUS-A","SQUASH":"CUC-VIRUS-B"}[crop]
    elif truth=="ASSAY_VERSION_UNAPPROVED":version="R0-UNAPPROVED"
    base={"case_id":case,"deidentified":True,"package_id":pkg,"form_id":form,"tube_ids":tubes,"package_count":pc,"form_count":fc,"tube_count":tc,"crop":crop,"panel":panel,"assay_version":version,"permit_ref":f"PERMIT-SYN-{((n-1)%12)+1:03d}","permit_active":permit_active,"license_ref":f"LICENSE-SYN-{((n-1)%10)+1:03d}","license_active":license_active,"designated_contact_id":contact,"custody_chain":custody}
    base.update(_hashes(case_id=case,package_id=pkg,form_id=form,tube_ids=tubes,package_count=pc,form_count=fc,tube_count=tc,crop=crop,panel=panel,assay_version=version,contact_id=contact,custody=custody))
    base["truth_hold"]=truth
    return base

def _rows(c):
    if c.get("schema")!="deterministic-generator-v1":raise IntegrityError("fixture schema mismatch")
    g=c.get("generator")
    if not isinstance(g,dict) or (g.get("record_count"),g.get("clean_count"),g.get("aliquots_per_case"))!=(300,240,2):raise IntegrityError("fixture generator dimensions mismatch")
    holds={}
    for seg in g.get("hold_segments",[]):
        code,start,count=seg.get("code"),seg.get("start"),seg.get("count")
        if code not in HOLD_CODES or not isinstance(start,int) or not isinstance(count,int):raise IntegrityError("invalid HOLD segment")
        for off in range(count):
            n=start+off
            if n in holds or not 1<=n<=300:raise IntegrityError("overlapping/out-of-range HOLD segment")
            holds[n]=code
    if set(holds)!=set(range(241,301)):raise IntegrityError("HOLD segments must cover cases 241..300")
    return [[n,holds.get(n)] for n in range(1,301)]

def verify_records(records,m):
    verify_manifest_signature(m)
    if m.get("demand_id")!=DEMAND_ID or len(records)!=m.get("record_count"):raise IntegrityError("manifest/record mismatch")
    ids=[r["case_id"] for r in records]
    if len(ids)!=len(set(ids)):raise IntegrityError("duplicate case_id")
    if _sha(_canon(records))!=m.get("expanded_records_sha256"):raise IntegrityError("expanded record hash mismatch")
    truth=Counter(r["truth_hold"] for r in records if r["truth_hold"])
    if truth!=Counter(m["expected_hold_codes"]) or len(records)-sum(truth.values())!=m["expected_ready"]:raise IntegrityError("truth-set mismatch")
    approved=m["approved_specs"]
    for r in records:
        if not r.get("deidentified") or ({k.lower() for k in r}&FORBIDDEN_PHI_KEYS):raise IntegrityError("fixture must remain deidentified/PHI-free")
        h=_hashes(case_id=r["case_id"],package_id=r["package_id"],form_id=r["form_id"],tube_ids=r["tube_ids"],package_count=r["package_count"],form_count=r["form_count"],tube_count=r["tube_count"],crop=r["crop"],panel=r["panel"],assay_version=r["assay_version"],contact_id=r["designated_contact_id"],custody=r["custody_chain"])
        if any(r.get(k)!=v for k,v in h.items()):raise IntegrityError("source/custody/route hash mismatch")
        if r["crop"] not in approved:raise IntegrityError("unknown crop")

def load_fixture(fixture_path=None,manifest_path=None):
    base=Path(__file__).resolve().parent/"fixtures"; fp=Path(fixture_path) if fixture_path else base/"agdia_300_cases.json"; mp=Path(manifest_path) if manifest_path else base/"manifest.json"
    text=fp.read_text(); m=json.loads(mp.read_text())
    if _sha(text)!=m.get("dataset_sha256"):raise IntegrityError("dataset file hash mismatch")
    c=json.loads(text)
    if c.get("fixture_version")!=m.get("fixture_version"):raise IntegrityError("fixture version mismatch")
    records=[_expand(row) for row in _rows(c)]; verify_records(records,m); return records,m

def _classify(r,m):
    if r["form_count"]!=1 or not r["form_id"]:return "ORPHAN_OR_MISSING_FORM"
    if r["tube_count"]!=2 or len(r["tube_ids"])!=2:return "MISSING_TUBE"
    if not r["permit_active"]:return "PERMIT_REFERENCE_INVALID"
    if not r["license_active"]:return "LICENSE_REFERENCE_INVALID"
    spec=m["approved_specs"][r["crop"]]
    if r["panel"]!=spec["panel"]:return "CROP_PANEL_MISMATCH"
    if r["assay_version"]!=spec["assay_version"]:return "ASSAY_VERSION_UNAPPROVED"

@dataclass
class ReplayReport:
    ready:int; hold:int; replayed:int; hold_counts:dict[str,int]; accessions_added:int; panels_added:int; aliquots_added:int; reports_added:int; holds_added:int; events_added:int; state_digest:str; outcomes:list[dict[str,Any]]

class AgdiaOrderShadow:
    def __init__(self,authoritative_state=None):
        self.authoritative_state=copy.deepcopy(authoritative_state or {}); self._af=_sha(_canon(self.authoritative_state))
        self.accessions={}; self.panels={}; self.aliquots={}; self.staged_reports={}; self.holds={}; self.events=[]; self._seen=set()
    @property
    def authoritative_fingerprint(self):
        cur=_sha(_canon(self.authoritative_state))
        if cur!=self._af:raise IntegrityError("authoritative state changed inside read-only shadow")
        return cur
    def state_digest(self):
        return _sha(_canon({"accessions":self.accessions,"panels":self.panels,"aliquots":self.aliquots,"staged_reports":self.staged_reports,"holds":self.holds,"events":self.events,"seen":sorted(self._seen)}))
    def replay(self,records,m):
        verify_records(records,m); self.authoritative_fingerprint
        ready=hold=replayed=aa=pa=ala=ra=ha=ea=0; counts=Counter(); outcomes=[]
        for r in records:
            cid=r["case_id"]
            if cid in self._seen:
                replayed+=1; outcomes.append({"case_id":cid,"status":"IDEMPOTENT_REPLAY","hold_code":self.holds.get(cid,{}).get("hold_code"),"record_sha256":_record_hash(r)}); continue
            code=_classify(r,m)
            if code!=r["truth_hold"]:raise IntegrityError(f"classifier/truth mismatch {cid}")
            self._seen.add(cid)
            if code:
                hold+=1; counts[code]+=1; self.holds[cid]={"case_id":cid,"hold_code":code,"report_created":0,"aliquots_created":0}; ha+=1
                out={"case_id":cid,"status":"HOLD","hold_code":code,"report_created":0,"aliquots_created":0,"record_sha256":_record_hash(r)}
            else:
                ready+=1
                if (r["package_count"],r["form_count"],r["tube_count"],len(r["tube_ids"]))!=(1,1,2,2):raise IntegrityError("package/form/tube reconciliation mismatch")
                self.accessions[cid]={"case_id":cid,"accession_id":f"ACC-{cid[-4:]}","package_count":1,"form_count":1,"tube_count":2,"source_sha256":r["source_sha256"],"custody_sha256":r["custody_sha256"]}; aa+=1
                self.panels[cid]={"case_id":cid,"crop":r["crop"],"panel":r["panel"],"assay_version":r["assay_version"],"route_sha256":r["route_sha256"]}; pa+=1
                for i in range(1,m["aliquots_per_case"]+1):
                    aid=f"{cid}-ALIQ-{i}"; self.aliquots[aid]={"case_id":cid,"aliquot_id":aid,"panel":r["panel"],"state":"STAGED_NOT_STARTED"}; ala+=1
                self.staged_reports[cid]={"case_id":cid,"state":"STAGED_HUMAN_REVIEW","designated_contact_id":r["designated_contact_id"],"sent":False,"released_by":None,"route_sha256":r["route_sha256"]}; ra+=1
                out={"case_id":cid,"status":"READY","hold_code":None,"panel":r["panel"],"assay_version":r["assay_version"],"aliquots_created":m["aliquots_per_case"],"report_created":1,"designated_contact_id":r["designated_contact_id"],"sent":False,"source_sha256":r["source_sha256"],"custody_sha256":r["custody_sha256"],"route_sha256":r["route_sha256"],"record_sha256":_record_hash(r)}
            self.events.append({"sequence":len(self.events)+1,"case_id":cid,"status":out["status"],"hold_code":out["hold_code"],"record_sha256":out["record_sha256"]}); ea+=1; outcomes.append(out)
        if not replayed and (ready!=m["expected_ready"] or hold!=m["expected_hold"] or counts!=Counter(m["expected_hold_codes"])):raise IntegrityError("replay count mismatch")
        self.authoritative_fingerprint
        return ReplayReport(ready,hold,replayed,dict(sorted(counts.items())),aa,pa,ala,ra,ha,ea,self.state_digest(),outcomes)
    def release_report(self,case_id,reviewer_name):
        if not isinstance(reviewer_name,str):raise PermissionError("named human reviewer is required")
        reviewer=reviewer_name.strip()
        tokens=re.findall(r"[a-z]+",reviewer.casefold())
        reserved=any("".join(tokens[start:end]) in RESERVED_RELEASE_ACTORS
                     for start in range(len(tokens))
                     for end in range(start+1,len(tokens)+1))
        if len(tokens)<2 or reserved:raise PermissionError("named human reviewer is required")
        report=self.staged_reports.get(case_id)
        if report is None:raise KeyError(case_id)
        if report["state"]!="STAGED_HUMAN_REVIEW" or report["released_by"] is not None:raise PermissionError("report is not awaiting human review")
        report["state"]="RELEASED_BY_NAMED_HUMAN"; report["released_by"]=reviewer
        return {"case_id":case_id,"state":report["state"],"released_by":reviewer,"designated_contact_id":report["designated_contact_id"]}
    def automatic_release(self,*_,**__):raise PermissionError("automatic release is disabled; named human approval is required")
