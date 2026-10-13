"""Deterministic 400-object golden acceptance corpus."""
from __future__ import annotations
import hashlib, json
from typing import Any
GOLDEN_CORPUS_SHA256 = "2202b2e2e61daa008cddc6c1227489d9259980e80359f9faa2598115ba18f17e"
def _digest(label: str) -> str: return hashlib.sha256(label.encode("utf-8")).hexdigest()
def build_golden_input() -> dict[str, Any]:
    scope=[{"framework":"SOC2","control":"CC6.1"},{"framework":"ISO27001","control":"A.5.15"},{"framework":"HITRUST","control":"01.a"},{"framework":"PCI-DSS","control":"7.2.1"}]
    def row(evidence_id:str,*,owner:str="owner:assurance",collected:str="2026-09-01T12:00:00Z",coverage_start:str="2026-01-01T00:00:00Z",coverage_end:str="2026-04-30T23:59:59Z",mappings:list[dict[str,str]]|None=None,checksum:str|None=None,freshness_rule:str="freshness-90d",source_ref:str|None=None)->dict[str,Any]:
        ordinal=int(evidence_id.split("-")[-1]); mappings=[scope[ordinal%len(scope)]] if mappings is None else mappings; checksum=_digest(evidence_id) if checksum is None else checksum; source_ref=f"source:{evidence_id.lower()}" if source_ref is None else source_ref
        return {"evidence_id":evidence_id,"owner_ref":owner,"collected_at":collected,"coverage_start":coverage_start,"coverage_end":coverage_end,"mappings":mappings,"checksum_sha256":checksum,"freshness_rule_id":freshness_rule,"source_ref":source_ref}
    evidence=[]
    evidence.extend(row(f"REUSE-{i:03d}") for i in range(240))
    evidence.extend(row(f"STALE-{i:03d}",collected="2026-05-01T12:00:00Z") for i in range(50))
    evidence.extend(row(f"SCOPE-{i:03d}",mappings=[{"framework":"SOC2","control":"OUTSIDE"}]) for i in range(20))
    evidence.extend(row(f"SCOPE-{i:03d}",coverage_start="2026-02-01T00:00:00Z") for i in range(20,40))
    evidence.extend(row(f"OWNER-{i:03d}",owner="") for i in range(35))
    evidence.extend(row(f"INC-{i:03d}",checksum="") for i in range(12))
    evidence.extend(row(f"INC-{i:03d}",mappings=[]) for i in range(12,24))
    evidence.extend(row(f"INC-{i:03d}",freshness_rule="") for i in range(24,35))
    if len(evidence)!=400: raise AssertionError("golden corpus cardinality drift")
    return {"schema":"commons.multi-framework-evidence-freshness/v1","assessment":{"assessment_id":"schellman-synthetic-2026","period_start":"2026-01-01T00:00:00Z","period_end":"2026-04-30T23:59:59Z","scope":scope},"freshness_policy":{"rule_id":"freshness-90d","max_age_days":90},"evidence":evidence}
def golden_corpus_sha256()->str:
    encoded=json.dumps(build_golden_input(),ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8"); return hashlib.sha256(encoded).hexdigest()
