"""Receipt integrity, recorded measurement provenance, and matched comparisons."""
from __future__ import annotations
import importlib.metadata, json, math, os, platform
from typing import Any
from evidence_contract import (AUTHORITY,EVIDENCE_CLASS,EXPECTED_CANDIDATES,SCHEMA,
    EvidenceError,canonical_sha256,candidate_spec,expected_manifest)
from evidence_provenance import recorded_provenance


def _ver(name:str):
    try:return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:return None

def runner_fingerprint()->dict[str,Any]:
    return {"python":platform.python_version(),"platform":platform.platform(),"machine":platform.machine(),
      "githubRunId":os.environ.get("GITHUB_RUN_ID"),"githubRunAttempt":os.environ.get("GITHUB_RUN_ATTEMPT"),
      "githubJob":os.environ.get("GITHUB_JOB"),"runnerOs":os.environ.get("RUNNER_OS"),"runnerArch":os.environ.get("RUNNER_ARCH")}

def environment_record()->dict[str,Any]:
    return {"runner":runner_fingerprint(),"packages":{n:_ver(n) for n in ("dfbench","jax","learn2design","optax")}}

def sign(p:dict[str,Any])->dict[str,Any]:
    """Legacy name: compute content integrity only, NOT an authority signature."""
    u=dict(p);u.pop("receiptSha256",None);return {**u,"receiptSha256":canonical_sha256(u)}

def base_receipt(m,label,status,source_ok,organizer_ok,measurement,pending,env=None):
    """Produce a candidate receipt. MEASURED is the producer's assertion only."""
    s=candidate_spec(m,label)
    return sign({"schemaVersion":SCHEMA,"evidenceClass":EVIDENCE_CLASS,"status":status,
      "candidate":{"label":label,**s},"organizer":dict(m["organizer"]),"cell":dict(m["cell"]),
      "sourceVerified":source_ok,"organizerSourceVerified":organizer_ok,
      "environment":environment_record() if env is None else env,"measurement":measurement,
      "pendingReason":pending,"authority":dict(AUTHORITY)})

def verify_receipt_integrity(r:dict[str,Any],m:dict[str,Any])->None:
    """Validate content and source labels; do not establish execution provenance."""
    if not isinstance(r,dict):raise EvidenceError("receipt must be an object")
    try:
        json.dumps(r,allow_nan=False)
        if canonical_sha256(m)!=canonical_sha256(expected_manifest()):
            raise EvidenceError("manifest differs from hard-pinned evidence contract")
        d=r.get("receiptSha256");u=dict(r);u.pop("receiptSha256",None)
        if not isinstance(d,str) or d!=canonical_sha256(u):raise EvidenceError("receipt digest mismatch")
    except (ValueError,TypeError,OverflowError) as e:
        raise EvidenceError("receipt/manifest must be finite JSON") from e
    if type(r.get("schemaVersion")) is not int or r["schemaVersion"]!=SCHEMA or r.get("evidenceClass")!=EVIDENCE_CLASS:
        raise EvidenceError("receipt class mismatch")
    authority=r.get("authority")
    if not isinstance(authority,dict) or set(authority)!=set(AUTHORITY) or any(v is not False for v in authority.values()):
        raise EvidenceError("authority ceiling changed")
    candidate=r.get("candidate");label=candidate.get("label") if isinstance(candidate,dict) else None
    if not isinstance(label,str) or label not in EXPECTED_CANDIDATES or candidate!={"label":label,**EXPECTED_CANDIDATES[label]}:
        raise EvidenceError("candidate identity drift")
    if r.get("organizer")!=m["organizer"] or r.get("cell")!=m["cell"]:raise EvidenceError("organizer/cell mismatch")
    env=r.get("environment")
    if not isinstance(env,dict) or not isinstance(env.get("runner"),dict) or not isinstance(env.get("packages"),dict):
        raise EvidenceError("environment malformed")
    if r.get("status")=="MEASURED":
        if r.get("sourceVerified") is not True or r.get("organizerSourceVerified") is not True:raise EvidenceError("measured source verification missing")
        x=r.get("measurement");loss=x.get("bestLoss") if isinstance(x,dict) else None;count=x.get("evalCount") if isinstance(x,dict) else None
        if isinstance(loss,bool) or not isinstance(loss,(int,float)):raise EvidenceError("bestLoss must be finite")
        if isinstance(count,bool) or not isinstance(count,int) or count<=0:raise EvidenceError("evalCount must be positive int")
        elapsed=x.get("elapsedSeconds")
        if isinstance(elapsed,bool) or not isinstance(elapsed,(int,float)) or elapsed<0:raise EvidenceError("elapsedSeconds must be nonnegative")
        if type(x.get("budgetExceeded")) is not bool or r.get("pendingReason") is not None:raise EvidenceError("measured receipt malformed")
        try:
            if not math.isfinite(float(loss)) or not math.isfinite(float(elapsed)):raise EvidenceError("measurement must be finite")
        except OverflowError as e:raise EvidenceError("measurement outside finite range")
    elif r.get("status")=="MEASUREMENT_PENDING":
        if r.get("measurement") is not None or not isinstance(r.get("pendingReason"),str) or not r["pendingReason"]:
            raise EvidenceError("pending receipt malformed")
    else:raise EvidenceError("unsupported receipt status")

def verify_receipt(r:dict[str,Any],m:dict[str,Any])->dict[str,Any]:
    """Require exact historical provider evidence, not self-authored verification."""
    verify_receipt_integrity(r,m)
    if r["status"]!="MEASURED":raise EvidenceError("measurement provenance unavailable for pending receipt")
    return recorded_provenance(r)

def make_measured_for_test(m,label,best_loss,eval_count,runner):
    """Synthetic candidate helper; its result does NOT pass verify_receipt()."""
    env=environment_record();env["runner"]=runner
    return base_receipt(m,label,"MEASURED",True,True,{"bestLoss":float(best_loss),"evalCount":int(eval_count),"budgetExceeded":True,"elapsedSeconds":30.0},None,env)

def compare_candidate_receipts(a,b,m):
    """Compare supplied values, explicitly without measured-execution authority."""
    verify_receipt_integrity(a,m);verify_receipt_integrity(b,m);d={a["candidate"]["label"]:a,b["candidate"]["label"]:b}
    if set(d)!=set(EXPECTED_CANDIDATES):raise EvidenceError("comparison requires serial_v1 and vectorized_v2")
    s,v=d["serial_v1"],d["vectorized_v2"]
    if s["status"]!="MEASURED" or v["status"]!="MEASURED":raise EvidenceError("comparison requires measured candidate receipts")
    if s["environment"]["runner"]!=v["environment"]["runner"]:raise EvidenceError("runner fingerprints differ")
    if s["environment"]["packages"]!=v["environment"]["packages"]:raise EvidenceError("package environments differ")
    sm,vm=s["measurement"],v["measurement"]
    delta=vm["bestLoss"]-sm["bestLoss"]
    if not math.isfinite(float(delta)):raise EvidenceError("loss delta outside finite range")
    w="serial_v1" if sm["bestLoss"]<vm["bestLoss"] else "vectorized_v2" if vm["bestLoss"]<sm["bestLoss"] else "tie"
    return sign({"schemaVersion":SCHEMA,"evidenceClass":EVIDENCE_CLASS,"status":"UNVERIFIED_CANDIDATE_COMPARISON",
      "measurementProvenanceVerified":False,
      "organizer":dict(m["organizer"]),"cell":dict(m["cell"]),"runner":s["environment"]["runner"],
      "candidates":{"serial_v1":s["receiptSha256"],"vectorized_v2":v["receiptSha256"]},
      "result":{"lowerBestLoss":w,"serialBestLoss":sm["bestLoss"],"vectorizedBestLoss":vm["bestLoss"],
        "bestLossDeltaVectorMinusSerial":delta,"serialEvalCount":sm["evalCount"],
        "vectorizedEvalCount":vm["evalCount"],"evalCountDeltaVectorMinusSerial":vm["evalCount"]-sm["evalCount"]},
      "interpretation":"Supplied receipt values only; execution provenance is unverified. Not an organizer-backed measurement or official competition result.",
      "authority":dict(AUTHORITY)})

def compare_receipts(a,b,m):
    """Compare only exact measurements independently recorded from one provider run."""
    pa,pb=verify_receipt(a,m),verify_receipt(b,m)
    if any(pa[k]!=pb[k] for k in ("repository","runId","runAttempt","jobId","artifactId","artifactSha256","checkoutSha")):
        raise EvidenceError("recorded execution provenance differs")
    out=compare_candidate_receipts(a,b,m)
    out.update({"status":"RECORDED_MATCHED_PUBLIC_DEVELOPMENT_COMPARISON",
      "measurementProvenanceVerified":True,
      "provenance":{a["candidate"]["label"]:pa,b["candidate"]["label"]:pb},
      "interpretation":"Recorded public ConstrainedVoyager development evidence only; not hidden-topology/H100/official competition performance or live CI status."})
    return sign(out)

def verify_comparison(report,a,b,m)->None:
    """Recompute from recorded inputs; a rehashed forged comparison is not proof."""
    expected=compare_receipts(a,b,m)
    try:
        matches=canonical_sha256(report)==canonical_sha256(expected)
    except (TypeError,ValueError,OverflowError) as e:
        raise EvidenceError("comparison must be JSON") from e
    if not matches:raise EvidenceError("comparison differs from recorded inputs")
