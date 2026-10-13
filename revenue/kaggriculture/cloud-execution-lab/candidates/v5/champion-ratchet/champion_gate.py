#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Authenticate and score a full V5 champion panel against exact submitted V3.1."""
from __future__ import annotations
import argparse, hashlib, json, math, os, re, stat, sys, uuid
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "titan-v5-champion-ratchet-receipt/v2"
V31_ARCHIVE_SHA256 = "5db3921f85efbc7596e5a1e7e198fc5f4644ceea43d8e8323c74ded7b4ba4361"
V31_SOURCE_COMMIT = "a90d888f03987ef0b35cfd20ec3519c6144db08a"
V31_SUBMISSION_ID = 56172377
CORPUS_MANIFEST_SHA256 = "510ca5c5438fb65d29755f2009f07bb85bbf3e8963054b88c4abe3ec3737924e"
CORPUS_REL = "cloud-execution-lab/candidates/v5/gauntlet-top30-union/manifest.json"
EXPECTED_TARGETS = 41
EXPECTED_REPLAYS_PER_TARGET = 3
EXPECTED_CALLBACKS = 719
REPO_GIT_BLOBS = {
    "cloud-execution-lab/reference/evaluator/evaluate.py": "6d9edcc4ec5eeee22c8a6faec6ddd208a9a2e9e7",
    "20260907-offline-agent/evaluate.py": "387712c7b85dae4e624a3aab11df96f1ddb5b451",
    "cloud-pack/pack.py": "2407c7467fc60eda8864283d736c743a886bc549",
}
ENGINE_GIT_BLOBS = {
    "kaggriculture.py": "3c202c7ee921da239356789e266b694635103fc4",
    "kaggriculture.json": "b354d06b742fe48402513792253f1a5c29366b20",
    "utils.py": "91c8822ee6201ba4a5a8416c7dbe34f95dd61c87",
}
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX40 = re.compile(r"^[0-9a-f]{40}$")

class ChampionError(ValueError):
    pass

def _strict_object(pairs):
    out={}
    for k,v in pairs:
        if k in out: raise ChampionError(f"duplicate JSON key: {k}")
        out[k]=v
    return out

def _reject_constant(token):
    raise ChampionError(f"non-finite JSON constant: {token}")

def _loads(raw: bytes, source: str):
    try:
        text=raw.decode("utf-8")
        return json.loads(text, object_pairs_hook=_strict_object, parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ChampionError(f"{source}: invalid UTF-8 JSON") from exc

def _read_plain_file(path: Path):
    """Read one ordinary file through one no-follow, nonblocking descriptor or fail closed."""
    path=Path(path)
    nofollow=getattr(os,"O_NOFOLLOW",None)
    nonblock=getattr(os,"O_NONBLOCK",None)
    if type(nofollow) is not int or nofollow == 0:
        raise ChampionError("platform lacks O_NOFOLLOW; refusing release evidence")
    if type(nonblock) is not int or nonblock == 0:
        raise ChampionError("platform lacks O_NONBLOCK; refusing release evidence")
    flags=os.O_RDONLY | nofollow | nonblock | getattr(os,"O_CLOEXEC",0)
    try:
        fd=os.open(path,flags)
    except OSError as exc:
        raise ChampionError(f"{path}: evidence must be an ordinary non-symlink file") from exc
    try:
        try:
            mode=os.fstat(fd).st_mode
        except OSError as exc:
            raise ChampionError(f"cannot stat evidence file {path}") from exc
        if not stat.S_ISREG(mode):
            raise ChampionError(f"{path}: evidence must be an ordinary non-symlink file")
        chunks=[]
        while True:
            try:
                chunk=os.read(fd,1024*1024)
            except OSError as exc:
                raise ChampionError(f"cannot read evidence file {path}") from exc
            if not chunk: break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        try: os.close(fd)
        except OSError: pass

def _read_json(path: Path):
    path=Path(path)
    raw=_read_plain_file(path)
    return _loads(raw, str(path)), hashlib.sha256(raw).hexdigest()

def _canon(v):
    return json.dumps(v, sort_keys=True, separators=(",",":"), ensure_ascii=False, allow_nan=False).encode()

def _digest(v):
    return hashlib.sha256(_canon(v)).hexdigest()

def _git_blob(data: bytes):
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()

def _sha_file(path: Path):
    return hashlib.sha256(_read_plain_file(path)).hexdigest()

def _plain_int(v, field, lo=0):
    if type(v) is not int or v < lo: raise ChampionError(f"{field} must be a plain int >= {lo}")
    return v

def _score(v, field):
    if type(v) not in (int,float) or not math.isfinite(v): raise ChampionError(f"{field} must be finite")
    return v

def authenticate_v31_identity(*, source_commit=None, submission_id=None, archive_sha256=None):
    """Bind source+submission+archive. Stale claimed identity is non-authorizing."""
    if source_commit is None:
        source_commit = V31_SOURCE_COMMIT
    if submission_id is None:
        submission_id = V31_SUBMISSION_ID
    if archive_sha256 is None:
        archive_sha256 = V31_ARCHIVE_SHA256
    if type(source_commit) is not str or _HEX40.fullmatch(source_commit) is None:
        raise ChampionError("V3.1 source_commit malformed")
    if source_commit != V31_SOURCE_COMMIT:
        raise ChampionError("stale V3.1 source_commit")
    if type(submission_id) is not int or submission_id != V31_SUBMISSION_ID:
        raise ChampionError("stale V3.1 submission_id")
    if type(archive_sha256) is not str or _HEX64.fullmatch(archive_sha256) is None:
        raise ChampionError("V3.1 archive SHA256 malformed")
    if archive_sha256 != V31_ARCHIVE_SHA256:
        raise ChampionError("V3.1 archive bytes do not match exact submitted V3.1")
    return {
        "v31_source_commit": V31_SOURCE_COMMIT,
        "v31_submission_id": V31_SUBMISSION_ID,
        "v31_archive_sha256": V31_ARCHIVE_SHA256,
    }

def authenticate_repo(kg_root: Path, *, repo_pins=REPO_GIT_BLOBS):
    kg=Path(kg_root).resolve(strict=True); repo={}
    for rel,pin in repo_pins.items():
        p=(kg/rel).resolve(strict=True)
        try: p.relative_to(kg)
        except ValueError: raise ChampionError(f"repo path escaped: {rel}")
        data=p.read_bytes()
        if _git_blob(data)!=pin: raise ChampionError(f"repo authority drift: {rel}")
        repo[rel]={"git_blob":pin,"sha256":hashlib.sha256(data).hexdigest()}
    return repo

def authenticate_engine(engine_dir: Path, *, engine_pins=ENGINE_GIT_BLOBS):
    eng=Path(engine_dir).resolve(strict=True); engine={}
    for name,pin in engine_pins.items():
        p=(eng/name).resolve(strict=True)
        try: p.relative_to(eng)
        except ValueError: raise ChampionError(f"engine path escaped: {name}")
        data=p.read_bytes()
        if _git_blob(data)!=pin: raise ChampionError(f"engine authority drift: {name}")
        engine[name]=hashlib.sha256(data).hexdigest()
    return engine

def authenticate_harness(kg_root: Path, engine_dir: Path, *,
                         repo_pins=REPO_GIT_BLOBS, engine_pins=ENGINE_GIT_BLOBS):
    return {"repo":authenticate_repo(kg_root,repo_pins=repo_pins),
            "engine":authenticate_engine(engine_dir,engine_pins=engine_pins)}

def load_manifest(path: Path, *, expected_sha256=CORPUS_MANIFEST_SHA256,
                  expected_targets=EXPECTED_TARGETS, replays_per_target=EXPECTED_REPLAYS_PER_TARGET):
    manifest, sha=_read_json(path)
    if sha != expected_sha256: raise ChampionError("corpus manifest SHA256 mismatch")
    if type(manifest) is not dict or manifest.get("schema")!="titan.gauntlet.top30-union.v1":
        raise ChampionError("unexpected corpus manifest schema")
    targets=manifest.get("targets")
    if type(targets) is not list or len(targets)!=expected_targets:
        raise ChampionError(f"expected {expected_targets} corpus targets")
    fixtures=[]; seen_sub=set(); seen_fixture=set()
    for ti,target in enumerate(targets):
        if type(target) is not dict or target.get("status")!="complete":
            raise ChampionError(f"target[{ti}] is incomplete")
        sub=_plain_int(target.get("submission_id"), f"target[{ti}].submission_id", 1)
        if sub in seen_sub: raise ChampionError("duplicate submission_id")
        seen_sub.add(sub)
        replays=target.get("replays")
        if type(replays) is not list or len(replays)!=replays_per_target:
            raise ChampionError(f"submission {sub} must have {replays_per_target} replays")
        for ri,replay in enumerate(replays):
            if type(replay) is not dict or replay.get("kind")!="recorded_action_trace":
                raise ChampionError(f"submission {sub} replay[{ri}] malformed")
            ep=_plain_int(replay.get("episode_id"), "episode_id", 1)
            seed=_plain_int(replay.get("seed"), "seed", 0)
            recorded_seat=_plain_int(replay.get("recorded_opponent_seat"), "recorded_opponent_seat", 0)
            if recorded_seat not in (0,1): raise ChampionError("recorded_opponent_seat must be 0 or 1")
            fid=f"trace-sub-{sub}-ep-{ep}"
            if fid in seen_fixture: raise ChampionError("duplicate fixture id")
            seen_fixture.add(fid)
            fixtures.append({"id":fid,"submission_id":sub,"seed":seed,
                             "candidate_seat_for_recorded_orientation":1-recorded_seat})
    return {"sha256":sha,"fixtures":fixtures,"target_count":len(targets)}

def _scan_policy(label: str, roots: Iterable[Path], archive_sha: str, fixtures: list[dict[str,Any]],
                 harness: dict[str,Any]):
    roots=list(roots)
    by_id={f["id"]:f for f in fixtures}; ordered=[f["id"] for f in fixtures]
    seen_roots=set(); runs={}; cells={}; roots_by_shard={}; source_hashes={}
    evaluator_rel="cloud-execution-lab/reference/evaluator/evaluate.py"
    loader_rel="20260907-offline-agent/evaluate.py"
    evaluator_sha=harness["repo"][evaluator_rel]["sha256"]
    loader_sha=harness["repo"][loader_rel]["sha256"]
    for raw_root in roots:
        root=Path(raw_root).resolve(strict=True)
        if root in seen_roots: raise ChampionError(f"duplicate {label} root")
        seen_roots.add(root)
        run, run_sha=_read_json(root/"run.json")
        if type(run) is not dict: raise ChampionError(f"{root}/run.json must be object")
        if run.get("candidate_sha256")!=archive_sha: raise ChampionError(f"{label} archive/run mismatch")
        if run.get("group")!="all": raise ChampionError(f"{label} run must use group=all")
        if run.get("submission_hold") is not True: raise ChampionError(f"{label} run missing submission_hold")
        shard=_plain_int(run.get("shard"), f"{label}.shard")
        shards=_plain_int(run.get("shards"), f"{label}.shards",1)
        if shard>=shards or shard in runs: raise ChampionError(f"invalid/duplicate {label} shard")
        if run.get("evaluator_sha256")!=evaluator_sha: raise ChampionError(f"{label} evaluator mismatch")
        if run.get("loader_sha256")!=loader_sha: raise ChampionError(f"{label} loader mismatch")
        if run.get("engine")!=harness["engine"]: raise ChampionError(f"{label} engine mismatch")
        index_sha=run.get("index_sha256")
        if type(index_sha) is not str or _HEX64.fullmatch(index_sha) is None:
            raise ChampionError(f"{label} index_sha256 malformed")
        runs[shard]={"shards":shards,"index_sha256":index_sha,"run_sha256":run_sha,
                     "selected_fixtures":_plain_int(run.get("selected_fixtures"),"selected_fixtures")}
        roots_by_shard[shard]=root
        source_hashes[f"run/{shard}.json"]=run_sha
    if not runs: raise ChampionError(f"no {label} roots")
    shard_counts={r["shards"] for r in runs.values()}
    if len(shard_counts)!=1: raise ChampionError(f"{label} roots disagree on shard count")
    shards=next(iter(shard_counts))
    if set(runs)!=set(range(shards)): raise ChampionError(f"{label} incomplete shard set")
    for shard in range(shards):
        expected_ids={fid for i,fid in enumerate(ordered) if i%shards==shard}
        if runs[shard]["selected_fixtures"]!=len(expected_ids):
            raise ChampionError(f"{label} shard {shard} selected_fixtures mismatch; --limit is non-authorizing")
        root=roots_by_shard[shard]
        expected_names={f"{fid}-p{seat}.json" for fid in expected_ids for seat in (0,1)}
        actual_names={p.name for p in root.glob("*.json") if p.name!="run.json"}
        if actual_names!=expected_names:
            raise ChampionError(f"{label} shard {shard} cell set differs from canonical full roster")
        for name in sorted(expected_names):
            p=root/name; record, sha=_read_json(p)
            m=re.match(r"^(.*)-p([01])\.json$",name); assert m
            fid=m.group(1); seat=int(m.group(2)); fixture=by_id[fid]
            if type(record) is not dict: raise ChampionError(f"{p} must be object")
            checks={
                "opponent":fid, "submission_id":fixture["submission_id"], "seed":fixture["seed"],
                "candidate_seat":seat, "candidate_sha256":archive_sha, "kind":"recorded_trace",
                "adaptive":False, "status":"complete", "steps":EXPECTED_CALLBACKS,
            }
            for key,expected in checks.items():
                if record.get(key)!=expected: raise ChampionError(f"{label} {name} {key} mismatch")
            if record.get("recorded_orientation") != (seat==fixture["candidate_seat_for_recorded_orientation"]):
                raise ChampionError(f"{label} {name} recorded_orientation mismatch")
            if record.get("family") != f"recorded-submission:{fixture['submission_id']}":
                raise ChampionError(f"{label} {name} family mismatch")
            scores=record.get("scores")
            if type(scores) is not list or len(scores)!=2: raise ChampionError(f"{label} {name} scores malformed")
            scores=[_score(v,f"{label}.{name}.scores") for v in scores]
            key=(fid,seat)
            cells[key]={"fixture":fid,"submission_id":fixture["submission_id"],"seed":fixture["seed"],
                        "seat":seat,"own":scores[seat],"rival":scores[1-seat]}
            source_hashes[f"{shard}/{name}"]=sha
    run_authority=[{"shard":i, **runs[i]} for i in range(shards)]
    return {"cells":cells,"runs":runs,"run_authority":run_authority,
            "source_digest":_digest(source_hashes),"shards":shards}

def _strata_and_score(inc, champ, cand):
    keys=sorted(cand)
    totals={k:0 for k in ("inc_own","champ_own","cand_own","inc_margin","champ_margin","cand_margin")}
    new_inc=new_champ=0; strata={}; panel=[]
    for key in keys:
        a,b,c=inc[key],champ[key],cand[key]
        for field in ("fixture","submission_id","seed","seat"):
            if a[field]!=b[field] or a[field]!=c[field]: raise ChampionError(f"cross-policy metadata mismatch: {key}")
        im=a["own"]-a["rival"]; hm=b["own"]-b["rival"]; cm=c["own"]-c["rival"]
        totals["inc_own"]+=a["own"]; totals["champ_own"]+=b["own"]; totals["cand_own"]+=c["own"]
        totals["inc_margin"]+=im; totals["champ_margin"]+=hm; totals["cand_margin"]+=cm
        if im>=0 and cm<0: new_inc+=1
        if hm>=0 and cm<0: new_champ+=1
        sk=(c["submission_id"],c["seat"]); bucket=strata.setdefault(sk,{"inc":0,"champ":0,"cand":0,"n":0})
        bucket["inc"]+=a["own"]; bucket["champ"]+=b["own"]; bucket["cand"]+=c["own"]; bucket["n"]+=1
        panel.append({"fixture":c["fixture"],"submission_id":c["submission_id"],"seed":c["seed"],"seat":c["seat"],
                      "incumbent":[a["own"],a["rival"]],"v31":[b["own"],b["rival"]],
                      "candidate":[c["own"],c["rival"]]})
    own_inc=totals["cand_own"]-totals["inc_own"]; own_v31=totals["cand_own"]-totals["champ_own"]
    mar_inc=totals["cand_margin"]-totals["inc_margin"]; mar_v31=totals["cand_margin"]-totals["champ_margin"]
    if own_inc<0: raise ChampionError(f"candidate regresses incumbent own score: {own_inc}")
    if own_v31<=0: raise ChampionError(f"candidate does not strictly beat V3.1 own score: {own_v31}")
    if mar_inc<0: raise ChampionError(f"candidate regresses incumbent margin: {mar_inc}")
    if mar_v31<0: raise ChampionError(f"candidate regresses V3.1 margin: {mar_v31}")
    if new_inc or new_champ: raise ChampionError(f"candidate creates new losses: incumbent={new_inc} v31={new_champ}")
    out=[]
    for (sub,seat),v in sorted(strata.items()):
        di=v["cand"]-v["inc"]; dv=v["cand"]-v["champ"]
        if di<0 or dv<0: raise ChampionError(f"negative own-score stratum submission={sub} seat={seat}")
        out.append({"submission_id":sub,"seat":seat,"cells":v["n"],
                    "own_delta_vs_incumbent":di,"own_delta_vs_v31":dv})
    return {"own_sum_delta_vs_incumbent":own_inc,"own_sum_delta_vs_v31":own_v31,
            "margin_sum_delta_vs_incumbent":mar_inc,"margin_sum_delta_vs_v31":mar_v31,
            "new_losses_vs_incumbent":new_inc,"new_losses_vs_v31":new_champ,
            "strata":out,"panel_digest":_digest(panel)}

def evaluate(*, kg_root:Path, engine_dir:Path, manifest_path:Path,
             v31_archive:Path, incumbent_archive:Path, candidate_archive:Path,
             v31_roots, incumbent_roots, candidate_roots,
             expected_manifest_sha=CORPUS_MANIFEST_SHA256, expected_targets=EXPECTED_TARGETS,
             repo_pins=REPO_GIT_BLOBS, engine_pins=ENGINE_GIT_BLOBS,
             claimed_v31_source_commit=None, claimed_v31_submission_id=None):
    identity=authenticate_v31_identity(
        source_commit=claimed_v31_source_commit,
        submission_id=claimed_v31_submission_id,
        archive_sha256=None,
    )
    harness=authenticate_harness(kg_root,engine_dir,repo_pins=repo_pins,engine_pins=engine_pins)
    manifest=load_manifest(manifest_path,expected_sha256=expected_manifest_sha,expected_targets=expected_targets)
    v31_sha=_sha_file(v31_archive); inc_sha=_sha_file(incumbent_archive); cand_sha=_sha_file(candidate_archive)
    if v31_sha!=V31_ARCHIVE_SHA256: raise ChampionError("V3.1 archive bytes do not match exact submitted V3.1")
    if len({v31_sha,inc_sha,cand_sha})!=3: raise ChampionError("V3.1, incumbent, candidate archives must be distinct")
    v31=_scan_policy("v31",v31_roots,v31_sha,manifest["fixtures"],harness)
    inc=_scan_policy("incumbent",incumbent_roots,inc_sha,manifest["fixtures"],harness)
    cand=_scan_policy("candidate",candidate_roots,cand_sha,manifest["fixtures"],harness)
    if not (v31["shards"]==inc["shards"]==cand["shards"]): raise ChampionError("cross-policy shard counts differ")
    for shard in range(v31["shards"]):
        if len({v31["runs"][shard]["index_sha256"],inc["runs"][shard]["index_sha256"],cand["runs"][shard]["index_sha256"]})!=1:
            raise ChampionError(f"cross-policy index authority differs on shard {shard}")
    if not (set(v31["cells"])==set(inc["cells"])==set(cand["cells"])):
        raise ChampionError("cross-policy cell topology differs")
    expected_cells=len(manifest["fixtures"])*2
    if len(cand["cells"])!=expected_cells: raise ChampionError("panel cardinality mismatch")
    score=_strata_and_score(inc["cells"],v31["cells"],cand["cells"])
    return {
        "schema":SCHEMA,"classification":"PASS","champion_ready":True,"release_authority":False,
        "release_requirement":"same v5tx must authenticate and consume this exact receipt before pointer write",
        "manifest_sha256":manifest["sha256"],"target_count":manifest["target_count"],
        "fixture_count":len(manifest["fixtures"]),"cell_count":expected_cells,
        "v31_source_commit":identity["v31_source_commit"],
        "v31_submission_id":identity["v31_submission_id"],
        "v31_archive_sha256":v31_sha,"incumbent_archive_sha256":inc_sha,"candidate_archive_sha256":cand_sha,
        "harness":harness,"shards":cand["shards"],
        "source_digests":{"v31":v31["source_digest"],"incumbent":inc["source_digest"],"candidate":cand["source_digest"]},
        "run_authority":{"v31":v31["run_authority"],"incumbent":inc["run_authority"],"candidate":cand["run_authority"]},
        **score,
    }

def _atomic(path:Path, value):
    payload=_canon(value)+b"\n"; path=Path(path)
    if path.exists(): raise FileExistsError(path)
    tmp=path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("xb") as f: f.write(payload); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        try: tmp.unlink(missing_ok=True)
        except OSError: pass

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--kg-root",type=Path,required=True); p.add_argument("--engine-dir",type=Path,required=True)
    p.add_argument("--manifest",type=Path); p.add_argument("--v31-archive",type=Path,required=True)
    p.add_argument("--incumbent-archive",type=Path,required=True); p.add_argument("--candidate-archive",type=Path,required=True)
    p.add_argument("--v31-root",type=Path,action="append",required=True)
    p.add_argument("--incumbent-root",type=Path,action="append",required=True)
    p.add_argument("--candidate-root",type=Path,action="append",required=True)
    p.add_argument("--v31-source-commit",type=str,default=None)
    p.add_argument("--v31-submission-id",type=int,default=None)
    p.add_argument("--output",type=Path,required=True); a=p.parse_args(argv)
    manifest=a.manifest or a.kg_root/CORPUS_REL
    try:
        receipt=evaluate(kg_root=a.kg_root,engine_dir=a.engine_dir,manifest_path=manifest,
                         v31_archive=a.v31_archive,incumbent_archive=a.incumbent_archive,candidate_archive=a.candidate_archive,
                         v31_roots=a.v31_root,incumbent_roots=a.incumbent_root,candidate_roots=a.candidate_root,
                         claimed_v31_source_commit=a.v31_source_commit,
                         claimed_v31_submission_id=a.v31_submission_id)
        _atomic(a.output,receipt)
    except (ChampionError,OSError,TypeError,ValueError) as exc:
        print(f"champion_gate: {exc}",file=sys.stderr); return 2
    print(json.dumps({"classification":"PASS","cell_count":receipt["cell_count"],
                      "own_sum_delta_vs_v31":receipt["own_sum_delta_vs_v31"],
                      "release_authority":receipt["release_authority"]},sort_keys=True))
    return 0

if __name__=="__main__": raise SystemExit(main())
