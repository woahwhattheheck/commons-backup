#!/usr/bin/env python3
"""Load/verify the split comparable-corpus component manifest."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any
try:
    from . import validate_corpus as validator
except ImportError:
    import validate_corpus as validator
MANIFEST_SCHEMA="public-procurement-comparable-corpus-manifest/v1"

def _json(path:Path)->Any:
    raw=path.read_bytes()
    if len(raw)>validator.MAX_BYTES: raise validator.CorpusError(f"{path}: JSON is too large")
    try: text=raw.decode("utf-8")
    except UnicodeDecodeError as exc: raise validator.CorpusError(f"{path}: must be UTF-8") from exc
    def hook(pairs):
        out={}
        for key,value in pairs:
            if key in out: raise validator.CorpusError(f"duplicate JSON key {key!r}")
            out[key]=value
        return out
    try:
        return json.loads(text,object_pairs_hook=hook,parse_constant=lambda token: (_ for _ in ()).throw(validator.CorpusError(f"non-finite JSON constant {token}")))
    except json.JSONDecodeError as exc: raise validator.CorpusError(f"{path}: invalid JSON") from exc

def load_bundle(path:str|Path)->dict[str,Any]:
    path=Path(path); manifest=_json(path)
    if type(manifest) is not dict or manifest.get("schema")!=MANIFEST_SCHEMA: raise validator.CorpusError("manifest schema mismatch")
    required={"schema","operation","generated_at_utc","truth_boundary","authority","components","summary"}
    if set(manifest)!=required: raise validator.CorpusError("manifest keys mismatch")
    components=manifest["components"]
    if type(components) is not dict or set(components)!={"sources","records","exclusions"}: raise validator.CorpusError("manifest components mismatch")
    assembled={"schema":validator.SCHEMA,"operation":manifest["operation"],"generated_at_utc":manifest["generated_at_utc"],"truth_boundary":manifest["truth_boundary"],"authority":manifest["authority"],"sources":[],"records":[],"exclusions":[],"summary":manifest["summary"]}
    for kind in ("sources","records","exclusions"):
        entries=components[kind]
        if type(entries) is not list or not entries: raise validator.CorpusError(f"manifest {kind} components must be non-empty")
        seen=set()
        for index,entry in enumerate(entries):
            if type(entry) is not dict or set(entry)!={"path","sha256","count"}: raise validator.CorpusError(f"manifest {kind}[{index}] malformed")
            name=entry["path"]
            if not isinstance(name,str) or not name or Path(name).name!=name or "/" in name or "\\" in name: raise validator.CorpusError(f"manifest {kind}[{index}] unsafe component path")
            if name in seen: raise validator.CorpusError(f"manifest duplicate component path {name}")
            seen.add(name)
            if not isinstance(entry["sha256"],str) or validator.SHA.fullmatch(entry["sha256"]) is None: raise validator.CorpusError(f"manifest {kind}[{index}] invalid component SHA")
            if isinstance(entry["count"],bool) or not isinstance(entry["count"],int) or entry["count"]<0: raise validator.CorpusError(f"manifest {kind}[{index}] invalid count")
            component=_json(path.parent/name)
            if type(component) is not list: raise validator.CorpusError(f"component {name} must be a list")
            if len(component)!=entry["count"]: raise validator.CorpusError(f"component {name} count mismatch")
            if validator.digest(component)!=entry["sha256"]: raise validator.CorpusError(f"component {name} digest mismatch")
            assembled[kind].extend(component)
    validator.validate(assembled); return assembled

def main(argv=None)->int:
    p=argparse.ArgumentParser(); p.add_argument("manifest",nargs="?",default="revenue/procurement_award_price_intelligence/comparable_corpus_20260916/manifest.json"); p.add_argument("--out"); a=p.parse_args(argv)
    corpus=load_bundle(a.manifest)
    if a.out:
        target=Path(a.out)
        if target.exists(): p.error("output already exists")
        target.write_bytes(validator.canonical(corpus)+b"\n")
    s=corpus["summary"]; print(f"VALID records={s['record_count']} sources={s['source_count']} buyers={s['buyer_counts']} readiness={s['promotability_counts']}"); return 0
if __name__=="__main__": raise SystemExit(main())
