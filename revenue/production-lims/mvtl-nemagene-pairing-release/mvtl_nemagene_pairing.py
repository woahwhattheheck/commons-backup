"""Synthetic/read-only MVTL NEMAGENE fertility/SCN pairing shadow."""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

DEMAND_ID = "mvtl-nemagene-pairing-release-lims-01"
MANIFEST_PREFIX = "MVTL-NEMAGENE-SYNTHETIC-MANIFEST-V1\n"
HOLD_CODES = ("DUPLICATE_BARCODE", "MISSING_ID", "ADDON_SAMPLE_MISMATCH", "DIVERGENT_RECEIPT")
RESERVED = {"auto","automatic","automation","bot","system","service","service-account","agent","ai","scheduler","worker","pipeline","anonymous","unknown"}
FORBIDDEN = {"patient","diagnosis","ssn","password","secret","token","api_key","credential"}

class IntegrityError(ValueError): pass

def _canon(v: Any) -> str:
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def _plus_business_days(date_text: str, count: int = 2) -> str:
    day = dt.date.fromisoformat(date_text)
    added = 0
    while added < count:
        day += dt.timedelta(days=1)
        if day.weekday() < 5:
            added += 1
    return day.isoformat()

def _envelope(m: Mapping[str, Any]) -> dict[str, Any]:
    keys = ("demand_id","fixture_version","dataset_sha256","expanded_records_sha256","record_count","expected_valid","expected_hold","expected_hold_codes","expected_fertility_scn","sla_business_days")
    return {k:m[k] for k in keys}

def verify_manifest_signature(m: Mapping[str, Any]) -> None:
    if m.get("signature_alg") != "sha256-content-envelope-v1": raise IntegrityError("manifest signature algorithm")
    if m.get("signature") != _sha(MANIFEST_PREFIX + _canon(_envelope(m))): raise IntegrityError("manifest signature mismatch")

def _truth_map(payload: Mapping[str, Any]) -> dict[int, str]:
    if payload.get("schema") != "deterministic-generator-v1": raise IntegrityError("fixture schema")
    g = payload.get("generator")
    if not isinstance(g, dict) or (g.get("record_count"),g.get("valid_count"),g.get("fertility_scn_valid_count")) != (500,400,250): raise IntegrityError("fixture dimensions")
    truth: dict[int,str] = {}
    for seg in g.get("hold_segments",[]):
        code,start,count = seg.get("code"),seg.get("start"),seg.get("count")
        if code not in HOLD_CODES or not all(isinstance(v,int) and not isinstance(v,bool) for v in (start,count)): raise IntegrityError("hold segment")
        for i in range(start,start+count):
            if i in truth or not 401 <= i <= 500: raise IntegrityError("hold overlap/range")
            truth[i] = code
    if set(truth) != set(range(401,501)): raise IntegrityError("hold coverage")
    return truth

def _record(i: int, truth: str | None) -> dict[str, Any]:
    is_scn = i <= 250 or i > 400
    sample_id = f"SOIL-{i:04d}"
    barcode = f"MVTL-{i:04d}"
    fertility_accession = f"FERT-{i:04d}"
    receipt_date = (dt.date(2026,1,5) + dt.timedelta(days=(i-1)%70)).isoformat()
    due_date = _plus_business_days(receipt_date)
    scn_sample_id = sample_id if is_scn else None
    scn_result_id = f"SCN-RESULT-{i:04d}" if is_scn else None
    if truth == "DUPLICATE_BARCODE": barcode = f"MVTL-{i-400:04d}"
    elif truth == "MISSING_ID": sample_id = "" if i % 2 else sample_id; fertility_accession = "" if i % 2 == 0 else fertility_accession
    elif truth == "ADDON_SAMPLE_MISMATCH": scn_sample_id = f"SOIL-{((i-400)%25)+1:04d}"
    elif truth == "DIVERGENT_RECEIPT": due_date = _plus_business_days(receipt_date, 3)
    base = {
        "order_id": f"ORDER-{i:04d}", "sample_id": sample_id, "barcode": barcode,
        "fertility_accession": fertility_accession, "has_scn_addon": is_scn,
        "scn_sample_id": scn_sample_id, "scn_result_id": scn_result_id,
        "receipt_date": receipt_date, "signed_receipt_date": receipt_date,
        "sla_due_date": due_date, "fertility_result_digest": _sha(f"fertility:{i}:synthetic"),
        "scn_result_digest": _sha(f"scn:{i}:synthetic") if is_scn else None,
        "synthetic": True, "truth_hold": truth,
    }
    base["source_sha256"] = _sha(_canon(base))
    return base

def expand_fixture(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    truth = _truth_map(payload)
    return [_record(i, truth.get(i)) for i in range(1,501)]

def verify_records(records: list[dict[str,Any]], m: Mapping[str,Any]) -> None:
    verify_manifest_signature(m)
    if m.get("demand_id") != DEMAND_ID or len(records) != 500: raise IntegrityError("manifest count/demand")
    if _sha(_canon(records)) != m.get("expanded_records_sha256"): raise IntegrityError("expanded hash")
    truth = Counter(r["truth_hold"] for r in records if r["truth_hold"])
    if truth != Counter(m.get("expected_hold_codes",{})) or 500-sum(truth.values()) != m.get("expected_valid"): raise IntegrityError("truth counts")
    if sum(1 for r in records[:400] if r["has_scn_addon"]) != m.get("expected_fertility_scn"): raise IntegrityError("fertility+SCN count")
    for r in records:
        if not r.get("synthetic") or ({str(k).lower() for k in r} & FORBIDDEN): raise IntegrityError("fixture boundary")
        check = dict(r); got = check.pop("source_sha256")
        if got != _sha(_canon(check)): raise IntegrityError("source hash")

def load_fixture(fixture_path=None, manifest_path=None):
    base = Path(__file__).resolve().parent / "fixtures"
    fp = Path(fixture_path) if fixture_path else base / "mvtl_500_soil_orders.json"
    mp = Path(manifest_path) if manifest_path else base / "manifest.json"
    text = fp.read_text(encoding="utf-8"); m = json.loads(mp.read_text(encoding="utf-8"))
    if _sha(text) != m.get("dataset_sha256"): raise IntegrityError("fixture hash")
    payload = json.loads(text)
    if payload.get("fixture_version") != m.get("fixture_version"): raise IntegrityError("fixture version")
    records = expand_fixture(payload); verify_records(records,m); return records,m

def _classify(r: Mapping[str,Any], seen_barcodes:set[str]) -> str | None:
    if not isinstance(r.get("sample_id"),str) or not r["sample_id"] or not isinstance(r.get("fertility_accession"),str) or not r["fertility_accession"]: return "MISSING_ID"
    barcode = r.get("barcode")
    if not isinstance(barcode,str) or not barcode or barcode in seen_barcodes: return "DUPLICATE_BARCODE"
    if r.get("has_scn_addon") and r.get("scn_sample_id") != r.get("sample_id"): return "ADDON_SAMPLE_MISMATCH"
    if r.get("receipt_date") != r.get("signed_receipt_date") or r.get("sla_due_date") != _plus_business_days(r["signed_receipt_date"]): return "DIVERGENT_RECEIPT"
    return None

def _named_human(name: str) -> str:
    if not isinstance(name,str): raise PermissionError("named human required")
    n = " ".join(name.strip().split())
    if not n: raise PermissionError("named human required")
    tokens = [t for t in n.casefold().replace("_"," ").replace("-"," ").split() if t]
    if any(t in RESERVED for t in tokens): raise PermissionError("named human required")
    if len([t for t in tokens if any(c.isalpha() for c in t)]) < 2: raise PermissionError("two-token human name required")
    return n

@dataclass
class ReplayResult:
    valid:int; hold:int; fertility_scn:int; replayed:int; accessions_added:int; scn_jobs_added:int; reports_added:int; holds_added:int; events_added:int; hold_counts:dict[str,int]; state_digest:str; combined_manifest_sha256:str

class MvtlNemageneShadow:
    def __init__(self, authoritative_state=None):
        self.authoritative_state = copy.deepcopy(authoritative_state or {})
        self._af = _sha(_canon(self.authoritative_state))
        self.accessions={}; self.scn_jobs={}; self.reports={}; self.holds={}; self.events=[]; self._processed=set(); self._barcodes=set()
    @property
    def authoritative_fingerprint(self):
        now=_sha(_canon(self.authoritative_state))
        if now != self._af: raise IntegrityError("authoritative state mutated")
        return now
    def state_digest(self):
        return _sha(_canon({"accessions":self.accessions,"scn_jobs":self.scn_jobs,"reports":self.reports,"holds":self.holds,"events":self.events,"processed":sorted(self._processed),"barcodes":sorted(self._barcodes)}))
    def combined_manifest_sha256(self):
        return _sha(_canon({"reports":[self.reports[k] for k in sorted(self.reports)],"holds":[self.holds[k] for k in sorted(self.holds)]}))
    def replay(self, records, m):
        verify_records(records,m); self.authoritative_fingerprint
        valid=hold=fertility_scn=replayed=aa=sj=ra=ha=ea=0; counts=Counter()
        for r in records:
            oid=r["order_id"]
            if oid in self._processed:
                replayed += 1; continue
            code=_classify(r,self._barcodes)
            if code != r["truth_hold"]: raise IntegrityError(f"truth/classifier mismatch {oid}: {code} != {r['truth_hold']}")
            self._processed.add(oid)
            if code:
                hold+=1; counts[code]+=1; self.holds[oid]={"order_id":oid,"hold_code":code,"jobs_created":0,"report_created":0,"source_sha256":r["source_sha256"]}; ha+=1
            else:
                valid+=1; self._barcodes.add(r["barcode"])
                acc={"order_id":oid,"sample_id":r["sample_id"],"barcode":r["barcode"],"fertility_accession":r["fertility_accession"],"receipt_date":r["receipt_date"],"sla_due_date":r["sla_due_date"],"source_sha256":r["source_sha256"]}
                self.accessions[oid]=acc; aa+=1
                scn_lineage=None
                if r["has_scn_addon"]:
                    fertility_scn+=1
                    job={"order_id":oid,"fertility_accession":r["fertility_accession"],"scn_sample_id":r["scn_sample_id"],"scn_result_id":r["scn_result_id"],"scn_result_digest":r["scn_result_digest"],"source_sha256":r["source_sha256"]}
                    if job["scn_sample_id"] != r["sample_id"]: raise IntegrityError("SCN orphan")
                    self.scn_jobs[oid]=job; sj+=1
                    scn_lineage=_sha(_canon(job))
                core={"order_id":oid,"sample_id":r["sample_id"],"fertility_accession":r["fertility_accession"],"fertility_result_digest":r["fertility_result_digest"],"scn_result_digest":r["scn_result_digest"],"scn_lineage_sha256":scn_lineage,"receipt_date":r["receipt_date"],"sla_due_date":r["sla_due_date"],"source_sha256":r["source_sha256"],"state":"STAGED_HUMAN_REVIEW","released_by":None,"sent":False}
                core["combined_result_digest"]=_sha(_canon(core)); self.reports[oid]=core; ra+=1
            self.events.append({"sequence":len(self.events)+1,"order_id":oid,"status":"HOLD" if code else "READY","hold_code":code,"source_sha256":r["source_sha256"]}); ea+=1
        if not replayed:
            if valid != m["expected_valid"] or hold != m["expected_hold"] or fertility_scn != m["expected_fertility_scn"] or counts != Counter(m["expected_hold_codes"]): raise IntegrityError("acceptance counts")
            if len(self.scn_jobs) != m["expected_fertility_scn"] or len({j["scn_result_id"] for j in self.scn_jobs.values()}) != len(self.scn_jobs): raise IntegrityError("SCN duplicate/orphan")
        self.authoritative_fingerprint
        return ReplayResult(valid,hold,fertility_scn,replayed,aa,sj,ra,ha,ea,dict(sorted(counts.items())),self.state_digest(),self.combined_manifest_sha256())
    def release_report(self, order_id: str, reviewer_name: str):
        reviewer=_named_human(reviewer_name); report=self.reports.get(order_id)
        if report is None: raise KeyError(order_id)
        if report["state"] != "STAGED_HUMAN_REVIEW": raise PermissionError("not staged")
        out=copy.deepcopy(report); out["state"]="RELEASED_BY_NAMED_HUMAN"; out["released_by"]=reviewer; out["sent"]=False; return out
    def automatic_release(self,*_,**__): raise PermissionError("automatic release disabled")

def run_acceptance():
    records,m=load_fixture(); s=MvtlNemageneShadow({"incumbent_lims":"authoritative-read-only","writes":0}); first=s.replay(records,m); sd=first.state_digest; cm=first.combined_manifest_sha256; second=s.replay(records,m)
    if second.replayed!=500 or any((second.accessions_added,second.scn_jobs_added,second.reports_added,second.holds_added,second.events_added)) or second.state_digest!=sd or second.combined_manifest_sha256!=cm: raise IntegrityError("replay drift")
    released=s.release_report(next(iter(s.reports)),"Jordan Reviewer")
    return {"demand_id":DEMAND_ID,"valid":first.valid,"hold":first.hold,"fertility_scn":first.fertility_scn,"hold_counts":first.hold_counts,"accessions":len(s.accessions),"scn_jobs":len(s.scn_jobs),"reports":len(s.reports),"replay_zero_add":True,"state_digest":sd,"combined_manifest_sha256":cm,"authoritative_fingerprint":s.authoritative_fingerprint,"release_state":released["state"],"released_by":released["released_by"],"sent":released["sent"]}

if __name__ == "__main__": print(json.dumps(run_acceptance(),sort_keys=True))
