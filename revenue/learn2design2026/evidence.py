#!/usr/bin/env python3
"""CLI: source-pinned public Learn2Design measurement; never a score/rank claim."""
from __future__ import annotations
import argparse,json,math,sys,time
from pathlib import Path
from evidence_contract import (AUTHORITY,EVIDENCE_CLASS,EXPECTED_CANDIDATES,SCHEMA,EvidenceError,
    candidate_spec,confined,git_blob_sha1_bytes,load_candidate,read_json,validate_manifest,verify_organizer_source)
from evidence_receipts import (base_receipt,compare_receipts,verify_receipt,
    verify_receipt_integrity,compare_candidate_receipts)

def instantiate_candidate(cls):
    """Instantiate exact candidate code across dfbench API drift without editing candidate bytes.

    The pinned organizer revision makes OptimizationAlgorithm.__init__ abstract, while
    both already-merged candidates predate that no-op requirement. Official examples at
    the same revision implement ``def __init__(self): pass``. Permit only that single
    abstract-method gap and inherit the candidate optimize method unchanged.
    """
    abstract = set(getattr(cls, "__abstractmethods__", ()))
    if not abstract:
        return cls()
    if abstract != {"__init__"}:
        raise EvidenceError(f"candidate has unsupported abstract methods: {sorted(abstract)}")
    def _evidence_init(self):
        pass
    adapter = type(f"{cls.__name__}EvidenceInitAdapter", (cls,), {"__init__": _evidence_init, "__module__": cls.__module__})
    obj = adapter()
    if getattr(adapter, "algorithm_str", None) != getattr(cls, "algorithm_str", None):
        raise EvidenceError("evidence init adapter changed algorithm identity")
    if getattr(adapter, "optimize", None) is not getattr(cls, "optimize", None):
        raise EvidenceError("evidence init adapter changed optimize implementation")
    return obj

def pending(m,label,reason,root):
    s=candidate_spec(m,label);ok=git_blob_sha1_bytes(confined(root,s["path"]).read_bytes())==s["gitBlobSha1"]
    return base_receipt(m,label,"MEASUREMENT_PENDING",ok,False,None,str(reason)[:1000])
def measure(m,label,root,organizer):
    s=candidate_spec(m,label);verify_organizer_source(organizer);cls=load_candidate(root,label,s)
    try:
        from dfbench import Objective
        from dfbench.problems import ConstrainedVoyagerProblem
    except Exception as e:raise EvidenceError(f"organizer-backed dfbench unavailable: {e}") from e
    cell=m["cell"];obj=Objective(ConstrainedVoyagerProblem(),max_time=cell["maxTimeSeconds"],verbose=0);opt=instantiate_candidate(cls);t=time.monotonic()
    opt.optimize(obj,random_seed=cell["seed"]);elapsed=time.monotonic()-t;loss=float(obj.best_loss);count=int(obj.eval_count)
    if not math.isfinite(loss) or count<=0:raise EvidenceError(f"invalid measurement best_loss={loss!r} eval_count={count!r}")
    return base_receipt(m,label,"MEASURED",True,True,{"bestLoss":loss,"evalCount":count,"budgetExceeded":bool(obj.budget_exceeded),"elapsedSeconds":round(elapsed,6)},None)
def write(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8")
def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument("--repo-root",type=Path,default=Path(__file__).resolve().parents[2]);p.add_argument("--manifest",type=Path,default=Path(__file__).with_name("evidence_manifest.json"));sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("verify-manifest")
    q=sub.add_parser("pending");q.add_argument("--candidate",choices=sorted(EXPECTED_CANDIDATES),required=True);q.add_argument("--reason",required=True);q.add_argument("--out",type=Path,required=True)
    q=sub.add_parser("measure");q.add_argument("--candidate",choices=sorted(EXPECTED_CANDIDATES),required=True);q.add_argument("--organizer-source",type=Path,required=True);q.add_argument("--out",type=Path,required=True);q.add_argument("--require-measured",action="store_true")
    for name in ("verify-receipt","verify-integrity"):
        q=sub.add_parser(name);q.add_argument("receipt",type=Path)
    for name in ("compare","compare-candidates"):
        q=sub.add_parser(name);q.add_argument("serial",type=Path);q.add_argument("vectorized",type=Path);q.add_argument("--out",type=Path,required=True)
    a=p.parse_args(argv)
    try:
        m=validate_manifest(a.manifest,a.repo_root)
        if a.cmd=="verify-manifest":print("manifest: PASS");return 0
        if a.cmd=="pending":r=pending(m,a.candidate,a.reason,a.repo_root);write(a.out,r);verify_receipt_integrity(r,m);print("candidate receipt (integrity only):",r["receiptSha256"]);return 0
        if a.cmd=="measure":
            try:r=measure(m,a.candidate,a.repo_root,a.organizer_source)
            except Exception as e:
                r=pending(m,a.candidate,f"measurement unavailable: {e}",a.repo_root);write(a.out,r)
                if a.require_measured:raise EvidenceError(r["pendingReason"]) from e
                print(r["receiptSha256"]);return 0
            write(a.out,r);verify_receipt_integrity(r,m);print("candidate receipt (integrity only):",r["receiptSha256"]);return 0
        if a.cmd=="verify-integrity":verify_receipt_integrity(read_json(a.receipt),m);print("receipt integrity: PASS; execution provenance NOT VERIFIED");return 0
        if a.cmd=="verify-receipt":
            provenance=verify_receipt(read_json(a.receipt),m);print(json.dumps(provenance,sort_keys=True));return 0
        if a.cmd in ("compare","compare-candidates"):
            compare=compare_receipts if a.cmd=="compare" else compare_candidate_receipts
            r=compare(read_json(a.serial),read_json(a.vectorized),m);write(a.out,r);print(json.dumps(r,indent=2,sort_keys=True));return 0
    except EvidenceError as e:print(f"evidence error: {e}",file=sys.stderr);return 2
    return 2
if __name__=="__main__":raise SystemExit(main())
