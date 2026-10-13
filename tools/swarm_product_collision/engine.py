from __future__ import annotations
import csv, hashlib, io, json, re, unicodedata
from datetime import datetime, timezone
from typing import Any

SCHEMA="swarm-product-collision-preflight/v2"
PROVIDERS=("GITHUB_CODE","GITHUB_ISSUES","GITHUB_PRS","SLACK")
SEARCH_STATES={"COMPLETE","RATE_LIMITED","TRUNCATED","ERROR"}
DURABLE_KINDS={"GITHUB_ISSUE","GITHUB_PR","SLACK_MESSAGE"}
DURABLE_CLAIMS={"TAKE","CLAIM"}
AXES=("actors","objects","actions")
HEX64=re.compile(r"^[0-9a-f]{64}$")
SEM=re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,78}[a-z0-9])?$")
ID=re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
REF=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+@=-]{0,199}$")
RESERVED={"and","or","not"}

class CollisionError(ValueError): pass

def _pairs(pairs):
    out={}
    for k,v in pairs:
        if k in out: raise CollisionError(f"duplicate JSON key: {k}")
        out[k]=v
    return out

def load_json_strict(text:str)->Any:
    def bad(v): raise CollisionError(f"non-finite JSON number: {v}")
    try: return json.loads(text,object_pairs_hook=_pairs,parse_constant=bad)
    except (json.JSONDecodeError,TypeError) as e: raise CollisionError(str(e)) from e

def _canon(v): return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def _sha(v): return hashlib.sha256(_canon(v)).hexdigest()
def _exact(o,keys,w):
    if not isinstance(o,dict) or set(o)!=set(keys): raise CollisionError(f"{w}: exact keys required")
def _s(v,w,n=300,p=None):
    if not isinstance(v,str) or not v or len(v)>n: raise CollisionError(f"{w}: invalid string")
    if any(unicodedata.category(c) in {"Cc","Cf","Cs","Zl","Zp"} for c in v): raise CollisionError(f"{w}: control rejected")
    if p and not p.fullmatch(v): raise CollisionError(f"{w}: invalid format")
    return v
def _i(v,w,lo,hi):
    if isinstance(v,bool) or not isinstance(v,int) or not lo<=v<=hi: raise CollisionError(f"{w}: invalid integer")
    return v
def _t(v,w):
    s=_s(v,w,30)
    try:
        if not s.endswith("Z"): raise ValueError
        return datetime.strptime(s,"%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as e: raise CollisionError(f"{w}: invalid UTC timestamp") from e
def _ft(v): return v.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def _term(v,w):
    v=_s(v,w,80,SEM)
    if v!=v.lower() or v in RESERVED: raise CollisionError(f"{w}: semantic/provider operator rejected")
    return v
def _terms(v,w):
    if not isinstance(v,list) or not 1<=len(v)<=32: raise CollisionError(f"{w}: 1..32 terms required")
    x=tuple(sorted(_term(a,f"{w}[{j}]") for j,a in enumerate(v)))
    if len(x)!=len(set(x)): raise CollisionError(f"{w}: duplicate term")
    return x
def _sig(v,w):
    _exact(v,AXES,w); return {a:_terms(v[a],f"{w}.{a}") for a in AXES}

def _families(candidate,rows):
    if not isinstance(rows,list) or not 1<=len(rows)<=32: raise CollisionError("families: 1..32 required")
    fam={}
    for j,r in enumerate(rows):
        _exact(r,{"family_id","terms"},f"families[{j}]")
        fid=_s(r["family_id"],f"families[{j}].family_id",80,ID)
        if fid in fam: raise CollisionError("duplicate family_id")
        fam[fid]=_terms(r["terms"],f"families[{j}].terms")
    cand=[x for a in AXES for x in candidate["signature"][a]]
    if len(cand)!=len(set(cand)): raise CollisionError("candidate signature terms must be unique")
    cmap=set(cand); anchor={}; tmap={}
    for fid,terms in fam.items():
        hits=cmap.intersection(terms)
        if len(hits)!=1: raise CollisionError(f"families.{fid}: exactly one candidate anchor required")
        a=next(iter(hits))
        if a in anchor: raise CollisionError("candidate anchor duplicated")
        anchor[a]=fid
        for term in terms:
            if term in tmap and tmap[term]!=fid: raise CollisionError("family term overlaps")
            tmap[term]=fid
    if cmap!=set(anchor): raise CollisionError("candidate signature missing family")
    return fam,tmap

def _match(c,h,tmap):
    if h["operation_id"]==c["operation_id"]: return True
    def canon(sig,a): return {tmap.get(x,"literal:"+x) for x in sig[a]}
    return all(canon(c["signature"],a)&canon(h["signature"],a) for a in AXES)
def _hid(h):
    return {"hit_id":h["hit_id"],"url":h["url"],"created_at":_ft(h["created_at"]),"kind":h["kind"],"claim_state":h["claim_state"],"operation_id":h["operation_id"],"owner":h["owner"],"signature":{a:list(h["signature"][a]) for a in AXES},"evidence_sha256":h["evidence_sha256"]}

def _validate(raw):
    _exact(raw,{"schema","evaluation_time","max_age_seconds","required_providers","candidate","families","searches"},"root")
    if raw["schema"]!=SCHEMA: raise CollisionError("unsupported schema")
    ev=_t(raw["evaluation_time"],"evaluation_time"); age=_i(raw["max_age_seconds"],"max_age_seconds",1,86400)
    rp=raw["required_providers"]
    if not isinstance(rp,list) or len(rp)!=4 or set(rp)!=set(PROVIDERS): raise CollisionError("required_providers must equal code-owned universe")
    c=raw["candidate"]; _exact(c,{"operation_id","seat_id","project","title","signature"},"candidate")
    c={"operation_id":_s(c["operation_id"],"candidate.operation_id",160,REF),"seat_id":_s(c["seat_id"],"candidate.seat_id",80,REF),"project":_s(c["project"],"candidate.project",160,REF),"title":_s(c["title"],"candidate.title",240),"signature":_sig(c["signature"],"candidate.signature")}
    fam,tmap=_families(c,raw["families"])
    expected=4*sum(map(len,fam.values()))
    if expected>4096: raise CollisionError("search universe too large")
    sr=raw["searches"]
    if not isinstance(sr,list) or len(sr)>4096: raise CollisionError("searches: invalid list")
    searches=[]; seen=set()
    for j,r in enumerate(sr):
        w=f"searches[{j}]"; _exact(r,{"provider","family_id","query","observed_at","state","hits","retained_root"},w)
        p=r["provider"]
        if p not in PROVIDERS: raise CollisionError(f"{w}.provider: unsupported")
        fid=_s(r["family_id"],f"{w}.family_id",80,ID)
        if fid not in fam: raise CollisionError(f"{w}.family_id: unknown")
        q=_term(r["query"],f"{w}.query")
        if q not in fam[fid]: raise CollisionError(f"{w}.query: exact declared semantic term required")
        key=(p,fid,q)
        if key in seen: raise CollisionError("duplicate provider/family/term search")
        seen.add(key)
        obs=_t(r["observed_at"],f"{w}.observed_at")
        if obs>ev: raise CollisionError(f"{w}.observed_at: future")
        state=r["state"]
        if state not in SEARCH_STATES: raise CollisionError(f"{w}.state: invalid")
        hrs=r["hits"]
        if not isinstance(hrs,list) or len(hrs)>500: raise CollisionError(f"{w}.hits: invalid")
        hits=[]; hseen=set()
        for k,h in enumerate(hrs):
            hw=f"{w}.hits[{k}]"; _exact(h,{"hit_id","url","created_at","kind","claim_state","operation_id","owner","signature","evidence_sha256"},hw)
            hid=_s(h["hit_id"],f"{hw}.hit_id",160,REF)
            if hid in hseen: raise CollisionError(f"{w}: duplicate hit_id")
            hseen.add(hid); url=_s(h["url"],f"{hw}.url",500)
            if not url.startswith("https://"): raise CollisionError(f"{hw}.url: https required")
            hits.append({"hit_id":hid,"url":url,"created_at":_t(h["created_at"],f"{hw}.created_at"),"kind":_s(h["kind"],f"{hw}.kind",40,REF),"claim_state":_s(h["claim_state"],f"{hw}.claim_state",40,REF),"operation_id":_s(h["operation_id"],f"{hw}.operation_id",160,REF),"owner":_s(h["owner"],f"{hw}.owner",120,REF),"signature":_sig(h["signature"],f"{hw}.signature"),"evidence_sha256":_s(h["evidence_sha256"],f"{hw}.evidence_sha256",64,HEX64)})
        rr=_s(r["retained_root"],f"{w}.retained_root",64,HEX64)
        if rr!=_sha({k:r[k] for k in ("provider","family_id","query","observed_at","state","hits")}): raise CollisionError(f"{w}.retained_root mismatch")
        searches.append({"provider":p,"family_id":fid,"query":q,"observed_at":obs,"state":state,"hits":hits,"retained_root":rr})
    return ev,age,c,fam,tmap,searches

def _packet(raw):
    ev,age,c,fam,tmap,searches=_validate(raw); reasons=[]
    by={(s["provider"],s["family_id"],s["query"]):s for s in searches}
    for fid in sorted(fam):
        for p in PROVIDERS:
            for term in fam[fid]:
                s=by.get((p,fid,term))
                if not s: reasons.append(f"MISSING_SEARCH:{p}:{fid}:{term}"); continue
                if s["state"]!="COMPLETE": reasons.append(f"SEARCH_{s['state']}:{p}:{fid}:{term}")
                if (ev-s["observed_at"]).total_seconds()>age: reasons.append(f"STALE_SEARCH:{p}:{fid}:{term}")
                for h in s["hits"]:
                    if h["created_at"]>ev: reasons.append(f"FUTURE_HIT:{h['hit_id']}")
                    if h["created_at"]>s["observed_at"]: reasons.append(f"HIT_AFTER_SEARCH_OBSERVATION:{h['hit_id']}")
    identities={}
    for s in searches:
        for h in s["hits"]:
            b=_canon(_hid(h)); old=identities.setdefault(h["hit_id"],b)
            if old!=b: reasons.append(f"CONFLICTING_HIT_METADATA:{h['hit_id']}")
    matches={}
    for s in searches:
        for h in s["hits"]:
            if h["kind"] not in DURABLE_KINDS or h["claim_state"] not in DURABLE_CLAIMS or not _match(c,h,tmap): continue
            core={"hitId":h["hit_id"],"url":h["url"],"createdAt":_ft(h["created_at"]),"kind":h["kind"],"claimState":h["claim_state"],"operationId":h["operation_id"],"owner":h["owner"]}; origin=f"{s['provider']}:{s['family_id']}:{s['query']}"
            row=matches.get(h["hit_id"])
            if row is None: row=dict(core,evidenceOrigins=[origin]); matches[h["hit_id"]]=row
            elif _canon({k:row[k] for k in core})!=_canon(core): reasons.append(f"CONFLICTING_HIT_METADATA:{h['hit_id']}")
            elif origin not in row["evidenceOrigins"]: row["evidenceOrigins"].append(origin); row["evidenceOrigins"].sort()
    collisions=sorted(matches.values(),key=lambda r:(r["createdAt"],r["hitId"]))
    status="UNKNOWN_HOLD" if reasons else "COLLISION" if collisions else "CENSUS_CLEAR_CALLER_TIME_UNVERIFIED"
    proj={"schema":SCHEMA,"evaluation_time":_ft(ev),"max_age_seconds":age,"required_providers":list(PROVIDERS),"candidate":{"operation_id":c["operation_id"],"seat_id":c["seat_id"],"project":c["project"],"title":c["title"],"signature":{a:list(c["signature"][a]) for a in AXES}},"families":[{"family_id":f,"terms":list(fam[f])} for f in sorted(fam)],"searches":sorted([{"provider":s["provider"],"family_id":s["family_id"],"query":s["query"],"observed_at":_ft(s["observed_at"]),"state":s["state"],"retained_root":s["retained_root"],"hits":sorted([_hid(h) for h in s["hits"]],key=lambda x:x["hit_id"])} for s in searches],key=lambda x:(x["provider"],x["family_id"],x["query"]))}
    return {"schema":SCHEMA,"status":status,"authority":"SUPPLIED_EVIDENCE_CENSUS_ONLY_NO_TAKE_OR_SEND_AUTHORITY","evaluationTime":_ft(ev),"timeAuthority":"CALLER_DECLARED_SELF_CONSISTENCY_ONLY","candidateEpochAuthority":"ABSENT_NOT_ESTABLISHED","antiRaceChronologyEstablished":False,"providerOriginAuthenticated":False,"currentOwnerEstablished":False,"takeAuthorized":False,"outboundAuthorized":False,"mergeAuthorized":False,"candidate":{"operationId":c["operation_id"],"seatId":c["seat_id"],"project":c["project"],"title":c["title"]},"coverage":{"requiredProviders":list(PROVIDERS),"familyIds":sorted(fam),"maxAgeSeconds":age,"requiredSearchRows":4*sum(map(len,fam.values())),"semanticVocabularyAuthority":"OWNER_SUPPLIED_DECLARED_FAMILIES_ONLY","retainedRootAuthority":"CALLER_RETAINED_DIGEST_INTEGRITY_ONLY"},"reasons":sorted(set(reasons)),"canonicalCarrier":collisions[0] if collisions else None,"collisions":collisions,"sourceDigest":_sha(proj)}

def _md(p):
    esc=lambda x:str(x).replace("`","'").replace("|","\\|")
    lines=["# Product-Lane Collision Preflight v2","",f"- Status: **{esc(p['status'])}**",f"- Candidate: `{esc(p['candidate']['operationId'])}`",f"- Authority: `{p['authority']}`",f"- Supplied evaluation coordinate: `{p['evaluationTime']}`",f"- Time authority: `{p['timeAuthority']}`","- Anti-race chronology established: **false**","- TAKE authority: **false**",""]
    if p["reasons"]: lines += ["## Hold reasons"]+[f"- `{esc(x)}`" for x in p["reasons"]]+[""]
    lines += ["## Durable semantic matches","","| Evidence origins | Owner | Operation | Created | URL |","|---|---|---|---|---|"]
    lines += [f"| {esc(','.join(r['evidenceOrigins']))} | {esc(r['owner'])} | {esc(r['operationId'])} | {r['createdAt']} | {esc(r['url'])} |" for r in p["collisions"]] or ["| none | - | - | - | - |"]
    lines += ["","> CENSUS_CLEAR_CALLER_TIME_UNVERIFIED describes only supplied evidence. It does not establish a trusted candidate epoch, provider authenticity, current ownership, or permission to TAKE/send/merge. Re-run live provider checks immediately before a TAKE.",""]
    return "\n".join(lines)
def _csv(p):
    out=io.StringIO(newline=""); w=csv.writer(out,lineterminator="\n"); w.writerow(["evidence_origins","owner","operation_id","created_at","url"])
    for r in p["collisions"]: w.writerow([";".join(r["evidenceOrigins"]),r["owner"],r["operationId"],r["createdAt"],r["url"]])
    return out.getvalue()
def compile_preflight(raw):
    p=_packet(raw); pb=_canon(p)+b"\n"; md=_md(p).encode(); table=_csv(p).encode(); rec={"schema":SCHEMA+"/receipt","packetSha256":hashlib.sha256(pb).hexdigest(),"markdownSha256":hashlib.sha256(md).hexdigest(),"csvSha256":hashlib.sha256(table).hexdigest()}
    return {"packet.json":pb,"review.md":md,"collisions.csv":table,"receipt.json":_canon(rec)+b"\n"}
def verify_bundle(raw,bundle):
    e=compile_preflight(raw); return set(bundle)==set(e) and all(isinstance(bundle[k],(bytes,bytearray)) and bytes(bundle[k])==v for k,v in e.items())
