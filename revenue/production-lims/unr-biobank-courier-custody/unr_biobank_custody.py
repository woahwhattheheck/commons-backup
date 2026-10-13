"""Synthetic/deidentified UNR biobank courier-to-freezer custody shadow."""
from __future__ import annotations
import copy, hashlib, json, re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEMAND_ID="unr-biobank-courier-custody-lims-01"
MANIFEST_PREFIX="UNR-BIOBANK-SYNTHETIC-MANIFEST-V1\n"
HOLD_CODES=("IRB_MTA_REFERENCE_INVALID","CUSTODY_TEMPERATURE_FAIL","DUPLICATE_BARCODE","SPECIMEN_MANIFEST_MISMATCH","UNAPPROVED_TRANSPORT_ROUTE")
FORBIDDEN_PHI_KEYS={"patient","patient_name","name","dob","date_of_birth","mrn","medical_record_number","address","phone","email","ssn"}
RESERVED_ACTOR_TOKENS={
    "ai","agent","api","assistant","auto","automated","automation",
    "bot","daemon","integration","machine","robot","scheduler",
    "service","system","workflow",
}

class IntegrityError(ValueError): pass
def _canonical(v:Any)->str:return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False)
def _sha256_text(v:str)->str:return hashlib.sha256(v.encode()).hexdigest()
def _record_hash(r:dict[str,Any])->str:return _sha256_text(_canonical(r))
def _manifest_envelope(m):
    return {k:m[k] for k in ("demand_id","fixture_version","dataset_sha256","expanded_records_sha256","record_count","expected_ready","expected_hold","expected_hold_codes","approved_routes","aliquots_per_specimen")}
def verify_manifest_signature(m):
    if m.get("signature_alg")!="sha256-content-envelope-v1":raise IntegrityError("unsupported manifest signature algorithm")
    if m.get("signature")!=_sha256_text(MANIFEST_PREFIX+_canonical(_manifest_envelope(m))):raise IntegrityError("manifest content-envelope signature mismatch")

def _positions_for(n:int,a:int=2)->dict[str,str]:
    base=f"FZ-A:R{((n-1)//30)+1}:B{(((n-1)//10)%3)+1}:S{((n-1)%10)+1:02d}"
    return {"parent":base+":P",**{f"aliquot_{i}":base+f":A{i}" for i in range(1,a+1)}}

def _lineage_hashes(*,shipment_id,study_ref,irb_ref,mta_ref,package_id,barcode,manifest_specimen_id,specimen_id,courier_id,route,custody_chain,receipt_temp_c,positions):
    values=(
        ("source_sha256",{"shipment_id":shipment_id,"study_ref":study_ref,"irb_ref":irb_ref,"mta_ref":mta_ref,"package_id":package_id,"barcode":barcode,"manifest_specimen_id":manifest_specimen_id,"specimen_id":specimen_id}),
        ("courier_sha256",{"courier_id":courier_id,"route":route}),
        ("custody_sha256",{"custody_chain":custody_chain}),
        ("temperature_sha256",{"receipt_temp_c":receipt_temp_c}),
        ("position_sha256",positions),
    )
    return {k:_sha256_text(_canonical(v)) for k,v in values}

def _expand_fixture_row(row:list[Any],a:int=2)->dict[str,Any]:
    if len(row)!=3:raise IntegrityError("fixture row width mismatch")
    n,truth,dup=row
    if not isinstance(n,int) or not 1<=n<=120:raise IntegrityError("fixture row number out of range")
    shipment=f"UNR-SHIP-{n:04d}"; study=f"STUDY-{((n-1)%12)+1:03d}"; irb=f"IRB-SYN-{((n-1)%12)+1:03d}"; mta=f"MTA-SYN-{((n-1)%8)+1:03d}"
    irb_active=mta_active=True
    package=f"PKG-{n:04d}"; barcode=f"BC-SYN-{(dup if dup is not None else n):04d}"; courier=f"COURIER-{((n-1)%4)+1:02d}"
    route="CAMPUS_COLD_CHAIN" if n%2 else "CONTRACT_COLD_CHAIN"
    custody=["COURIER_PICKUP","BIOBANK_RECEIVE"]; temp=round(3.0+(n%8)*.25,2)
    specimen=f"SPEC-SYN-{n:04d}"; manifest_specimen=specimen
    if truth=="IRB_MTA_REFERENCE_INVALID":
        if n%2:irb_active=False
        else:mta_active=False
    elif truth=="CUSTODY_TEMPERATURE_FAIL":
        if n%2:custody=["COURIER_PICKUP"]
        else:temp=12.5
    elif truth=="SPECIMEN_MANIFEST_MISMATCH":manifest_specimen=f"SPEC-SYN-MISMATCH-{n:04d}"
    elif truth=="UNAPPROVED_TRANSPORT_ROUTE":route="UNAPPROVED_ROUTE"
    positions=_positions_for(n,a)
    base={"shipment_id":shipment,"study_ref":study,"irb_ref":irb,"mta_ref":mta,"irb_active":irb_active,"mta_active":mta_active,"package_id":package,"barcode":barcode,"courier_id":courier,"route":route,"custody_chain":custody,"receipt_temp_c":temp,"deidentified":True,"manifest_specimen_id":manifest_specimen,"specimen_id":specimen,"aliquot_count":a,"positions":positions}
    base.update(_lineage_hashes(shipment_id=shipment,study_ref=study,irb_ref=irb,mta_ref=mta,package_id=package,barcode=barcode,manifest_specimen_id=manifest_specimen,specimen_id=specimen,courier_id=courier,route=route,custody_chain=custody,receipt_temp_c=temp,positions=positions))
    base["truth_hold"]=truth
    return base

def _rows_from_generator(c):
    if c.get("schema")!="deterministic-generator-v1":raise IntegrityError("fixture schema mismatch")
    g=c.get("generator")
    if not isinstance(g,dict) or (g.get("record_count"),g.get("clean_count"),g.get("aliquots_per_specimen"))!=(120,90,2):raise IntegrityError("fixture generator dimensions mismatch")
    holds={}
    for s in g.get("hold_segments",[]):
        code,start,count=s.get("code"),s.get("start"),s.get("count")
        if code not in HOLD_CODES or not isinstance(start,int) or not isinstance(count,int):raise IntegrityError("invalid HOLD segment")
        for off in range(count):
            n=start+off
            if n in holds or not 1<=n<=120:raise IntegrityError("overlapping or out-of-range HOLD segment")
            dup=None
            if code=="DUPLICATE_BARCODE":
                ds=s.get("duplicate_start")
                if not isinstance(ds,int):raise IntegrityError("duplicate segment missing duplicate_start")
                dup=ds+off
            holds[n]=(code,dup)
    if set(holds)!=set(range(91,121)):raise IntegrityError("HOLD segments must cover exactly shipments 91..120")
    return [[n,*holds.get(n,(None,None))] for n in range(1,121)]

def verify_records(records,m):
    verify_manifest_signature(m)
    if m.get("demand_id")!=DEMAND_ID or len(records)!=m.get("record_count"):raise IntegrityError("manifest/record mismatch")
    ids=[r["shipment_id"] for r in records]
    if len(ids)!=len(set(ids)):raise IntegrityError("duplicate shipment_id")
    if _sha256_text(_canonical(records))!=m.get("expanded_records_sha256"):raise IntegrityError("expanded record-set hash mismatch")
    truth=Counter(r["truth_hold"] for r in records if r["truth_hold"] is not None)
    if truth!=Counter(m["expected_hold_codes"]) or len(records)-sum(truth.values())!=m["expected_ready"]:raise IntegrityError("truth-set mismatch")
    for r in records:
        if not r.get("deidentified") or ({k.lower() for k in r}&FORBIDDEN_PHI_KEYS):raise IntegrityError("fixture must stay deidentified/PHI-free")
        if r.get("aliquot_count")!=m["aliquots_per_specimen"]:raise IntegrityError("aliquot-count contract mismatch")
        h=_lineage_hashes(shipment_id=r["shipment_id"],study_ref=r["study_ref"],irb_ref=r["irb_ref"],mta_ref=r["mta_ref"],package_id=r["package_id"],barcode=r["barcode"],manifest_specimen_id=r["manifest_specimen_id"],specimen_id=r["specimen_id"],courier_id=r["courier_id"],route=r["route"],custody_chain=r["custody_chain"],receipt_temp_c=r["receipt_temp_c"],positions=r["positions"])
        if any(r.get(k)!=v for k,v in h.items()):raise IntegrityError("lineage hash mismatch")

def load_fixture(fixture_path=None,manifest_path=None):
    base=Path(__file__).resolve().parent/"fixtures"; fp=Path(fixture_path) if fixture_path else base/"unr_120_shipments.json"; mp=Path(manifest_path) if manifest_path else base/"manifest.json"
    text=fp.read_text(); m=json.loads(mp.read_text())
    if _sha256_text(text)!=m.get("dataset_sha256"):raise IntegrityError("dataset file hash mismatch")
    c=json.loads(text)
    if c.get("fixture_version")!=m.get("fixture_version"):raise IntegrityError("fixture version mismatch")
    records=[_expand_fixture_row(row,m["aliquots_per_specimen"]) for row in _rows_from_generator(c)]
    verify_records(records,m); return records,m

def _classify(r,seen,approved):
    if not r["irb_active"] or not r["mta_active"]:return "IRB_MTA_REFERENCE_INVALID"
    if r["custody_chain"]!=["COURIER_PICKUP","BIOBANK_RECEIVE"] or not 2<=r["receipt_temp_c"]<=8:return "CUSTODY_TEMPERATURE_FAIL"
    if r["barcode"] in seen:return "DUPLICATE_BARCODE"
    if r["manifest_specimen_id"]!=r["specimen_id"]:return "SPECIMEN_MANIFEST_MISMATCH"
    if r["route"] not in approved:return "UNAPPROVED_TRANSPORT_ROUTE"

def named_human(value:str)->bool:
    if not isinstance(value,str):return False
    tokens=[token.casefold() for token in re.findall(r"[A-Za-z0-9]+",value)]
    alpha_tokens=[token for token in tokens if any(char.isalpha() for char in token)]
    if len(tokens)<2 or len(alpha_tokens)<2:return False
    if any(len(token)<2 for token in tokens):return False
    alpha_segments=re.findall(r"[a-z]+",value.casefold())
    reserved=any(
        "".join(alpha_segments[i:j]) in RESERVED_ACTOR_TOKENS
        for i in range(len(alpha_segments))
        for j in range(i+1,len(alpha_segments)+1)
    )
    if reserved:return False
    return True

@dataclass
class ReplayReport:
    ready_for_storage:int; hold:int; replayed:int; hold_counts:dict[str,int]; specimens_added:int; aliquots_added:int; positions_added:int; holds_added:int; events_added:int; state_digest:str; outcomes:list[dict[str,Any]]

class UNRBiobankCustodyShadow:
    def __init__(self,authoritative_state=None):
        self.authoritative_state=copy.deepcopy(authoritative_state or {}); self._af=_sha256_text(_canonical(self.authoritative_state))
        self.specimens={}; self.aliquots={}; self.positions={}; self.holds={}; self.events=[]; self.research_use={}; self._seen_shipments=set()
    @property
    def authoritative_fingerprint(self):
        cur=_sha256_text(_canonical(self.authoritative_state))
        if cur!=self._af:raise IntegrityError("authoritative state changed inside read-only shadow")
        return cur
    def state_digest(self):
        return _sha256_text(_canonical({"specimens":self.specimens,"aliquots":self.aliquots,"positions":self.positions,"holds":self.holds,"events":self.events,"research_use":self.research_use,"seen_shipments":sorted(self._seen_shipments)}))
    def replay(self,records,m):
        verify_records(records,m); self.authoritative_fingerprint; seen={v["barcode"] for v in self.specimens.values()}
        ready=hold=replayed=sa=aa=pa=ha=ea=0; counts=Counter(); outcomes=[]
        for r in records:
            sid=r["shipment_id"]
            if sid in self._seen_shipments:
                replayed+=1; outcomes.append({"shipment_id":sid,"status":"IDEMPOTENT_REPLAY","hold_code":self.holds.get(sid,{}).get("hold_code"),"record_sha256":_record_hash(r)}); continue
            code=_classify(r,seen,m["approved_routes"])
            if code!=r["truth_hold"]:raise IntegrityError("classifier/truth mismatch")
            self._seen_shipments.add(sid); seen.add(r["barcode"])
            if code is None:
                ready+=1; specimen={"shipment_id":sid,"specimen_id":r["specimen_id"],"barcode":r["barcode"],"study_ref":r["study_ref"],**{k:r[k] for k in ("source_sha256","courier_sha256","custody_sha256","temperature_sha256","position_sha256")},"storage_state":"READY_FOR_STORAGE","research_available":False}
                self.specimens[sid]=specimen; sa+=1
                for label,coord in r["positions"].items():
                    if coord in self.positions:raise IntegrityError("freezer coordinate collision")
                    occupant=r["specimen_id"]
                    if label!="parent":
                        i=int(label.split("_")[1]); occupant=f"{r['specimen_id']}-A{i}"; self.aliquots[occupant]={"shipment_id":sid,"parent_specimen_id":r["specimen_id"],"aliquot_id":occupant,"coordinate":coord,"research_available":False}; aa+=1
                    self.positions[coord]=occupant; pa+=1
                outcome={"shipment_id":sid,"status":"READY_FOR_STORAGE","hold_code":None,"specimen_created":1,"aliquots_created":r["aliquot_count"],"positions_created":1+r["aliquot_count"],"research_available":False,"record_sha256":_record_hash(r),**{k:r[k] for k in ("source_sha256","courier_sha256","custody_sha256","temperature_sha256","position_sha256")}}
            else:
                hold+=1; counts[code]+=1; self.holds[sid]={"shipment_id":sid,"hold_code":code,"specimen_created":0,"aliquots_created":0,"positions_created":0}; ha+=1
                outcome={"shipment_id":sid,"status":"HOLD","hold_code":code,"specimen_created":0,"aliquots_created":0,"positions_created":0,"research_available":False,"record_sha256":_record_hash(r)}
            self.events.append({"sequence":len(self.events)+1,"shipment_id":sid,"status":outcome["status"],"hold_code":outcome["hold_code"],"record_sha256":outcome["record_sha256"]}); ea+=1; outcomes.append(outcome)
        if not replayed and (ready!=m["expected_ready"] or hold!=m["expected_hold"] or counts!=Counter(m["expected_hold_codes"])):raise IntegrityError("replay count mismatch")
        self.authoritative_fingerprint
        return ReplayReport(ready,hold,replayed,dict(sorted(counts.items())),sa,aa,pa,ha,ea,self.state_digest(),outcomes)
    def authorize_research_use(self,shipment_id,reviewer_name):
        if not isinstance(reviewer_name,str) or not named_human(reviewer_name):
            raise PermissionError("named human reviewer is required")
        if shipment_id not in self.specimens:raise KeyError(shipment_id)
        if shipment_id in self.research_use:
            return self.research_use[shipment_id]
        reviewer=reviewer_name.strip()
        self.specimens[shipment_id]["research_available"]=True
        for a in self.aliquots.values():
            if a["shipment_id"]==shipment_id:a["research_available"]=True
        receipt={"shipment_id":shipment_id,"state":"RESEARCH_USE_AUTHORIZED_BY_NAMED_HUMAN","reviewed_by":reviewer}
        self.research_use[shipment_id]=receipt
        return receipt
    def automatic_research_release(self,*_,**__):raise PermissionError("automatic research-use release is disabled; named human approval is required")
