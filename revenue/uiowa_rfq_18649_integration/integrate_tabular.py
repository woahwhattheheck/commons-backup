#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,json
from collections import Counter
from pathlib import Path
import adapter_tabular

HERE=Path(__file__).resolve().parent
NAMES=("delivery_metrics","prioritization")

def load_contract():
    data=json.loads((HERE/"interface_map.json").read_text(encoding="utf-8"))
    if data.get("schema")!="uiowa-098-interface-map-v1":
        raise ValueError("interface map schema changed")
    return data

def build(repo:Path)->dict:
    contract=load_contract()
    specs={x["component"]:x for x in contract["components"]}
    records=[]
    records.extend(adapter_tabular.delivery(repo,specs["delivery_metrics"]))
    records.extend(adapter_tabular.prioritization(repo,specs["prioritization"]))
    ids=[r["canonical_id"] for r in records]
    if len(ids)!=len(set(ids)):
        raise ValueError("canonical id collision")
    counts=Counter((r["group"],r["component"]) for r in records)
    matrix=[]
    for group in contract["canonical_groups"]:
        row={"group":group}
        for name in NAMES:
            row[name]=counts[(group,name)]
        row["total"]=sum(row[n] for n in NAMES)
        matrix.append(row)
    return {
        "schema":"uiowa-098-tabular-integration-v1",
        "record_count":len(records),
        "components":list(NAMES),
        "records":records,
        "group_matrix":matrix,
        "boundary":{
            "synthetic_only":True,
            "native_ids_retained":True,
            "missing_values_preserved":True,
            "cross_group_assignment_inferred":False
        }
    }

def write_outputs(bundle:dict,out:Path):
    out.mkdir(parents=True,exist_ok=True)
    (out/"integration.json").write_text(json.dumps(bundle,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    fields=["group",*NAMES,"total"]
    with (out/"group-matrix.csv").open("w",encoding="utf-8",newline="") as fh:
        w=csv.DictWriter(fh,fieldnames=fields,lineterminator="\n")
        w.writeheader(); w.writerows(bundle["group_matrix"])
    holds=[r["native_id"] for r in bundle["records"] if r["attributes"].get("estimate_state")=="HOLD_MISSING_ESTIMATE"]
    text=[
        "# UIOWA-098 tabular integration rehearsal","",
        f"- Records: {bundle['record_count']}",
        f"- Components: {', '.join(bundle['components'])}",
        f"- Missing-estimate HOLD preserved: {', '.join(holds) or 'none'}","",
        "Native identifiers and source hashes are retained. CROSS recommendations are not assigned to a service group.",""
    ]
    (out/"report.md").write_text("\n".join(text),encoding="utf-8")

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--repo",type=Path,default=HERE.parents[1])
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args(argv)
    b=build(a.repo); write_outputs(b,a.out)
    print(f"PASS records={b['record_count']} components={len(b['components'])}")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
