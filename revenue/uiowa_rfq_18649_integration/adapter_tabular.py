from __future__ import annotations
import csv,hashlib
from pathlib import Path
from typing import Any

def _csv(path:Path)->list[dict[str,str]]:
    with path.open(encoding="utf-8",newline="") as fh: return list(csv.DictReader(fh))
def _sha(path:Path)->str: return hashlib.sha256(path.read_bytes()).hexdigest()
def _need(row:dict[str,Any],field:str,source:str)->Any:
    value=row.get(field)
    if value is None or (isinstance(value,str) and not value.strip()): raise ValueError(f"{source}: missing {field}")
    return value
def _record(component,native,group,kind,source,digest,attrs):
    return {"canonical_id":f"{component}:{native}","component":component,"native_id":native,
            "group":group,"record_type":kind,"source_path":source,"source_sha256":digest,"attributes":attrs}

def delivery(repo:Path,spec:dict[str,Any])->list[dict[str,Any]]:
    source=spec["source"]; path=repo/source; rows=_csv(path); digest=_sha(path)
    need={"deployment_id","service","commit_at","deployed_at","intervention_required","recovered_at","unplanned_rework","notes"}
    if not rows or not need.issubset(rows[0]): raise ValueError("delivery_metrics columns changed")
    out=[]
    for row in rows:
        native=_need(row,"deployment_id",source); ng=_need(row,"service",source); group=spec["mapping"].get(ng)
        if not group: raise ValueError(f"delivery_metrics: unmapped {ng}")
        out.append(_record("delivery_metrics",native,group,"deployment",source,digest,{
            "native_service":ng,"commit_at":row["commit_at"] or None,"deployed_at":row["deployed_at"],
            "intervention_required":row["intervention_required"] or None,"recovered_at":row["recovered_at"] or None,
            "unplanned_rework":row["unplanned_rework"] or None}))
    return out

def prioritization(repo:Path,spec:dict[str,Any])->list[dict[str,Any]]:
    source=spec["source"]; path=repo/source; rows=_csv(path); digest=_sha(path)
    need={"id","title","quality","security","delivery","complexity","confidence","owner_role","dependencies","assumptions"}
    if not rows or not need.issubset(rows[0]): raise ValueError("prioritization columns changed")
    out=[]
    for row in rows:
        native=_need(row,"id",source)
        vals=[row[k].strip() for k in ("quality","security","delivery","complexity")]
        state="READY_FOR_NATIVE_SCORING" if all(vals) else "HOLD_MISSING_ESTIMATE"
        out.append(_record("prioritization",native,"CROSS","recommendation",source,digest,{
            "title":row["title"],"estimate_state":state,"confidence":row["confidence"] or None,
            "owner_role":row["owner_role"] or None,"dependencies":row["dependencies"] or None}))
    return out
