#!/usr/bin/env python3
"""Leakage-safe exploratory bias screening with deterministic robustness evidence."""
from __future__ import annotations
import argparse,csv,hashlib,json,math,random
from pathlib import Path
from statistics import fmean,median
from typing import Optional,Sequence

DEFAULT_EXCLUDED_PREFIXES=("svi_","cvi_","ruca_","rucc_","nchs_","tribal_","usdm_","usfs_","mtbs_","heat_","wildfire_","drought_")
SCHEMA_VERSION="bias-discovery-evidence/v2"
COMPONENT_PROVENANCE_COLUMNS=("transport_gap","transport_defined","building_gap","building_defined","poi_gap","poi_defined")
MIN_STRONG_BOOTSTRAP_ITERATIONS=1000
MIN_STRONG_PERMUTATIONS=2000

def numeric(value:Optional[str])->Optional[float]:
    if value is None or value.strip()=="": return None
    try: n=float(value)
    except (TypeError,ValueError): return None
    return n if math.isfinite(n) else None

def load_scores(path:Path,*,require_components:bool=False)->dict[str,float]:
    out={}
    with path.open(newline="",encoding="utf-8") as h:
        r=csv.DictReader(h)
        if not r.fieldnames or not {"GEOID","coverage_gap_score"}<=set(r.fieldnames):
            raise ValueError("score CSV must contain GEOID and coverage_gap_score")
        if require_components:
            missing=[name for name in COMPONENT_PROVENANCE_COLUMNS if name not in r.fieldnames]
            if missing:
                raise ValueError("components CSV is missing derived diagnostic columns: "+", ".join(missing))
        for row_number,row in enumerate(r,start=2):
            g=(row.get("GEOID") or "").strip(); s=numeric(row.get("coverage_gap_score"))
            canonical=len(g)==11 and g.isdigit()
            if require_components:
                if not canonical:
                    raise ValueError(f"components CSV row {row_number} has non-canonical GEOID")
                if s is None:
                    raise ValueError(f"components CSV row {row_number} has missing or non-finite derived score")
            elif not canonical or s is None:
                continue
            if not 0<=s<=1: raise ValueError(f"coverage_gap_score outside [0,1] for GEOID {g}")
            if g in out: raise ValueError(f"duplicate GEOID in score CSV: {g}")
            out[g]=s
    if not out: raise ValueError("no usable scores")
    return out

def quantile_cut(values:Sequence[float],fraction:float)->float:
    if not 0<=fraction<=1: raise ValueError("quantile fraction must be within [0,1]")
    v=sorted(values)
    if len(v)<4: raise ValueError("at least four numeric rows required")
    return v[int(round((len(v)-1)*fraction))]

def _effect(paired,lo=.25,hi=.75):
    q1=quantile_cut([x[0] for x in paired],lo); q3=quantile_cut([x[0] for x in paired],hi)
    low=[x for x in paired if x[0]<=q1]; high=[x for x in paired if x[0]>=q3]
    if q1>=q3 or not low or not high: return None
    lm=fmean(x[1] for x in low); hm=fmean(x[1] for x in high)
    return {"low_cut":q1,"high_cut":q3,"low":low,"high":high,"low_mean_gap":lm,"high_mean_gap":hm,"signed_delta":hm-lm}

def _pct(values,fraction):
    v=sorted(values); pos=(len(v)-1)*fraction; a=math.floor(pos); b=math.ceil(pos)
    if a==b: return v[a]
    w=pos-a; return v[a]*(1-w)+v[b]*w

def _rng(seed,field,purpose):
    d=hashlib.sha256(f"{seed}:{field}:{purpose}".encode()).digest()
    return random.Random(int.from_bytes(d[:8],"big"))

def _bootstrap(low,high,n,rng):
    if n<20: raise ValueError("bootstrap_iterations must be at least 20")
    ds=[]
    for _ in range(n):
        l=[low[rng.randrange(len(low))] for _ in low]; h=[high[rng.randrange(len(high))] for _ in high]
        ds.append(fmean(h)-fmean(l))
    return _pct(ds,.025),_pct(ds,.975)

def _permutation(low,high,observed,n,rng):
    if n<20: raise ValueError("permutations must be at least 20")
    all_scores=list(low)+list(high); split=len(low); extreme=0; target=abs(observed)
    for _ in range(n):
        x=all_scores[:]; rng.shuffle(x)
        if abs(fmean(x[split:])-fmean(x[:split]))>=target-1e-15: extreme+=1
    return (extreme+1)/(n+1)

def _bh(results):
    ranked=sorted(enumerate(results),key=lambda x:x[1]["permutation_p"]); m=len(ranked); running=1.0
    for reverse,(i,r) in enumerate(reversed(ranked),1):
        rank=m-reverse+1; running=min(running,r["permutation_p"]*m/rank); results[i]["fdr_q"]=min(1.0,running)

def _sign(x,tol=1e-15): return 1 if x>tol else -1 if x<-tol else 0

def _threshold_stability(paired,base):
    effects=[]
    for lo,hi in ((.2,.8),(.25,.75),(1/3,2/3)):
        e=_effect(paired,lo,hi)
        if e: effects.append({"lower_fraction":lo,"upper_fraction":hi,"signed_delta":e["signed_delta"]})
    sign=_sign(base)
    return {"effects":effects,"sign_agreement":sum(_sign(x["signed_delta"])==sign for x in effects)/len(effects) if effects else 0.0}

def _county_jackknife(paired,base):
    counties=sorted({g[:5] for _,_,g in paired}); ds=[]
    for county in counties:
        kept=[x for x in paired if x[2][:5]!=county]
        if len(kept)<8 or len({x[0] for x in kept})<4: continue
        e=_effect(kept)
        if e: ds.append(e["signed_delta"])
    agree=sum(_sign(x)==_sign(base) for x in ds)/len(ds) if ds else None
    return {"counties":len(counties),"evaluated":len(ds),"sign_agreement":agree,"min_delta":min(ds,default=None),"max_delta":max(ds,default=None)}

def _missingness(rows,scores,field):
    yes=[]; no=[]
    for row in rows:
        g=(row.get("GEOID") or "").strip()
        if g not in scores: continue
        (no if numeric(row.get(field)) is None else yes).append(scores[g])
    matched=len(yes)+len(no)
    return {"matched_rows":matched,"numeric_rows":len(yes),"missing_or_non_numeric_rows":len(no),
            "missing_rate":len(no)/matched if matched else 0.0,
            "missing_vs_observed_gap_delta":fmean(no)-fmean(yes) if no and yes else None}

def _cluster(group,descending):
    ordered=sorted(group,key=lambda x:(x[1],x[2]),reverse=descending)
    counts={}
    for _,_,g in group: counts[g[:5]]=counts.get(g[:5],0)+1
    county,count=(max(counts.items(),key=lambda x:(x[1],x[0])) if counts else (None,0))
    return {"examples":[x[2] for x in ordered[:10]],"county_count":len(counts),"largest_county":county,
            "largest_county_fraction":count/len(group) if group else 0.0}

def _load_strata(path:Path):
    with path.open(newline="",encoding="utf-8") as h:
        r=csv.DictReader(h)
        if not r.fieldnames or "GEOID" not in r.fieldnames: raise ValueError("strata CSV must contain GEOID")
        if len(set(r.fieldnames))!=len(r.fieldnames): raise ValueError("duplicate strata CSV header")
        fields=list(r.fieldnames); rows=list(r)
    if not rows: raise ValueError("empty strata CSV")
    for field in fields:
        normalized=field.lower().replace("-","_").replace(" ","_")
        if "coverage_gap" in normalized:
            raise ValueError(f"strata CSV contains target-like coverage-gap field: {field}")
    seen_geoids=set()
    for row_number,row in enumerate(rows,start=2):
        g=(row.get("GEOID") or "").strip()
        if not(len(g)==11 and g.isdigit()):
            raise ValueError(f"strata CSV row {row_number} has non-canonical GEOID")
        if g in seen_geoids: raise ValueError(f"duplicate GEOID in strata CSV: {g}")
        seen_geoids.add(g)
    return fields,rows,seen_geoids

def analyze(scores:dict[str,float],strata_path:Path,min_rows:int,prefixes:tuple[str,...],*,
            bootstrap_iterations:int=1000,permutations:int=2000,seed:int=20260913)->list[dict]:
    if min_rows<8: raise ValueError("min_rows must be at least 8")
    fields,rows,_=_load_strata(strata_path)
    results=[]
    lowered_prefixes=tuple(p.lower() for p in prefixes)
    for field in (f for f in fields if f and f!="GEOID" and not f.lower().startswith(lowered_prefixes)):
        paired=[]
        for row in rows:
            g=(row.get("GEOID") or "").strip()
            if g in scores:
                v=numeric(row.get(field))
                if v is not None: paired.append((v,scores[g],g))
        if len(paired)<min_rows or len({x[0] for x in paired})<4: continue
        e=_effect(paired)
        if not e: continue
        low=[x[1] for x in e["low"]]; high=[x[1] for x in e["high"]]
        field_seed=int.from_bytes(hashlib.sha256(f"{seed}:{field}".encode()).digest()[:8],"big")
        ci=_bootstrap(low,high,bootstrap_iterations,_rng(field_seed,field,"bootstrap"))
        p=_permutation(low,high,e["signed_delta"],permutations,_rng(field_seed,field,"permutation"))
        results.append({"field":field,"rows":len(paired),"q1":e["low_cut"],"q3":e["high_cut"],
            "low_group_rows":len(low),"high_group_rows":len(high),"low_mean_gap":e["low_mean_gap"],
            "high_mean_gap":e["high_mean_gap"],"low_median_gap":median(low),"high_median_gap":median(high),
            "absolute_delta":abs(e["signed_delta"]),"signed_delta":e["signed_delta"],
            "bootstrap_95_ci":list(ci),"bootstrap_excludes_zero":ci[0]>0 or ci[1]<0,"permutation_p":p,
            "threshold_stability":_threshold_stability(paired,e["signed_delta"]),
            "county_jackknife":_county_jackknife(paired,e["signed_delta"]),
            "missingness":_missingness(rows,scores,field),"high_group":_cluster(e["high"],True),
            "low_group":_cluster(e["low"],False)})
    _bh(results)
    production_budget=(bootstrap_iterations>=MIN_STRONG_BOOTSTRAP_ITERATIONS and permutations>=MIN_STRONG_PERMUTATIONS)
    for r in results:
        cj=r["county_jackknife"]["sign_agreement"]
        r["production_resampling_budget"]=production_budget
        r["screening_strength"]="strong" if (production_budget and r["bootstrap_excludes_zero"] and r["fdr_q"]<=.10
            and r["threshold_stability"]["sign_agreement"]==1.0 and (cj is None or cj>=.80)) else "exploratory"
    return sorted(results,key=lambda r:(r["screening_strength"]!="strong",r["fdr_q"],-r["absolute_delta"],r["field"]))

def sha256_file(path:Path)->str:
    d=hashlib.sha256()
    with path.open("rb") as h:
        for block in iter(lambda:h.read(1024*1024),b""): d.update(block)
    return d.hexdigest()

def build_evidence_packet(components_csv:Path,strata_csv:Path,candidates:list[dict],*,min_rows:int,
        bootstrap_iterations:int,permutations:int,seed:int,excluded_prefixes:Sequence[str])->dict:
    return {"schema_version":SCHEMA_VERSION,
        "claim_boundary":"Exploratory screening only. A ranked field is not a causal, population-significant, organizer-validated, or prize-winning discovery.",
        "inputs":{"components_sha256":sha256_file(components_csv),"strata_sha256":sha256_file(strata_csv)},
        "method":{"primary_contrast":"upper versus lower quartile mean derived coverage-gap score",
            "bootstrap":{"iterations":bootstrap_iterations,"interval":"deterministic percentile 95%"},
            "permutation":{"iterations":permutations,"p_value":"two-sided empirical with +1 correction","multiple_testing":"Benjamini-Hochberg FDR"},
            "strong_gate":{"minimum_bootstrap_iterations":MIN_STRONG_BOOTSTRAP_ITERATIONS,"minimum_permutations":MIN_STRONG_PERMUTATIONS},
            "stability":["20/80, 25/75, and 33/67 threshold sign agreement","leave-one-county-out sign agreement when evaluable",
                         "high/low group county concentration","candidate missingness versus observed score delta"],
            "seed":seed,"min_rows":min_rows,"excluded_prefixes":list(excluded_prefixes)},
        "candidates":candidates,
        "writeup_gate":["verify field semantics and source/license","inspect named/map context for exemplar tracts",
                        "quantify sensitivity and missingness","show the pattern is outside the fixed automated scorecard",
                        "explain a concrete emergency-dispatch, evacuation, or disaster-relief consequence",
                        "do not move any external-data feature into the scored submission pipeline"]}

def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("components_csv",type=Path); p.add_argument("strata_csv",type=Path); p.add_argument("output_json",type=Path)
    p.add_argument("--min-rows",type=int,default=100); p.add_argument("--bootstrap-iterations",type=int,default=1000)
    p.add_argument("--permutations",type=int,default=2000); p.add_argument("--seed",type=int,default=20260913)
    p.add_argument("--include-fixed-scorecard-families",action="store_true"); a=p.parse_args(argv)
    prefixes=() if a.include_fixed_scorecard_families else DEFAULT_EXCLUDED_PREFIXES
    scores=load_scores(a.components_csv,require_components=True)
    _,_,strata_geoids=_load_strata(a.strata_csv)
    missing_scores=strata_geoids-set(scores)
    if missing_scores:
        sample=sorted(missing_scores)[:3]
        raise ValueError(f"components CSV is missing {len(missing_scores)} strata GEOIDs: {', '.join(sample)}")
    candidates=analyze(scores,a.strata_csv,a.min_rows,prefixes,
        bootstrap_iterations=a.bootstrap_iterations,permutations=a.permutations,seed=a.seed)
    packet=build_evidence_packet(a.components_csv,a.strata_csv,candidates,min_rows=a.min_rows,
        bootstrap_iterations=a.bootstrap_iterations,permutations=a.permutations,seed=a.seed,excluded_prefixes=prefixes)
    packet["population"]={"valid_component_scores":len(scores),"strata_rows":len(strata_geoids),"strata_missing_scores":0}
    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(packet,indent=2,sort_keys=True)+"\n",encoding="utf-8"); return 0
if __name__=="__main__": raise SystemExit(main())
