#!/usr/bin/env python3
"""Hive #045 interview logistics: coordinate; never rank, reject, or send."""
from __future__ import annotations
import argparse, copy, json, os, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DEMAND_ID = "bm-hive-20260908-045"
OFFER = "$299/month for a bounded interview pipeline"
FORBIDDEN = {"rank","ranking","score","rating","recommendation","decision","accept","accepted","reject","rejected","hire","hired"}

class CoordinationError(ValueError): pass

def dt(value: Any) -> datetime:
    try: out = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc: raise CoordinationError(f"invalid datetime: {value!r}") from exc
    if out.tzinfo is None or out.utcoffset() is None: raise CoordinationError("datetime must include UTC offset")
    return out.astimezone(timezone.utc)

def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def need(value: Any, field: str) -> str:
    out = str(value or "").strip()
    if not out: raise CoordinationError(f"{field} is required")
    return out

def no_decisions(value: Any, path="workspace") -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            if str(k).lower() in FORBIDDEN: raise CoordinationError(f"hiring-decision field {k!r} is not allowed at {path}")
            no_decisions(v, f"{path}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value): no_decisions(v, f"{path}[{i}]")

def validate(w: dict[str, Any]) -> None:
    no_decisions(w)
    if w.get("schema") != "recruiting-coordination-v1": raise CoordinationError("bad schema")
    if not isinstance(w.get("people"), list) or not isinstance(w.get("candidates"), list) or not isinstance(w.get("interviews", []), list): raise CoordinationError("people/candidates/interviews must be lists")
    people = {}
    for p in w["people"]:
        if not isinstance(p, dict): raise CoordinationError("person must be object")
        pid, kind = need(p.get("id"), "person.id"), need(p.get("kind"), "person.kind")
        if pid in people: raise CoordinationError(f"duplicate person: {pid}")
        if kind not in {"candidate","interviewer","recruiter"}: raise CoordinationError(f"bad person kind: {kind}")
        need(p.get("name"), "person.name"); need(p.get("contact"), "person.contact")
        if not isinstance(p.get("availability", []), list): raise CoordinationError("availability must be list")
        for a in p.get("availability", []):
            if dt(a.get("end")) <= dt(a.get("start")): raise CoordinationError("availability end must follow start")
        people[pid] = p
    candidates = {}
    for c in w["candidates"]:
        cid, pid = need(c.get("id"), "candidate.id"), need(c.get("person_id"), "candidate.person_id")
        if cid in candidates: raise CoordinationError(f"duplicate candidate: {cid}")
        if people.get(pid, {}).get("kind") != "candidate": raise CoordinationError("candidate person missing")
        panel = c.get("interviewer_ids")
        if not isinstance(panel, list) or len(panel) != 2 or len(set(panel)) != 2: raise CoordinationError("exactly two unique interviewers required")
        if any(people.get(str(x), {}).get("kind") != "interviewer" for x in panel): raise CoordinationError("bad interviewer")
        if people.get(str(c.get("recruiter_id")), {}).get("kind") != "recruiter": raise CoordinationError("bad recruiter")
        need(c.get("role"), "candidate.role"); candidates[cid] = c
    seen = set()
    for row in w.get("interviews", []):
        iid = need(row.get("id"), "interview.id")
        if iid in seen or row.get("candidate_id") not in candidates: raise CoordinationError("bad interview identity")
        if dt(row.get("end")) <= dt(row.get("start")): raise CoordinationError("interview end must follow start")
        if row.get("status") not in {"scheduled","rescheduled","cancelled"}: raise CoordinationError("bad interview status")
        if not isinstance(row.get("previous_slots", []), list): raise CoordinationError("previous_slots must be list")
        seen.add(iid)

def load(path: Path) -> dict[str, Any]:
    w = json.loads(path.read_text(encoding="utf-8"));
    if not isinstance(w, dict): raise CoordinationError("workspace must be object")
    validate(w); return w

def save(path: Path, w: dict[str, Any]) -> None:
    validate(w); path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as h:
            h.write(json.dumps(w, indent=2, sort_keys=True) + "\n"); h.flush(); os.fsync(h.fileno())
        os.replace(tmp, path)
    except BaseException:
        try: os.unlink(tmp)
        except FileNotFoundError: pass
        raise

def maps(w): return {str(p["id"]): p for p in w["people"]}, {str(c["id"]): c for c in w["candidates"]}
def intervals(p): return sorted((dt(a["start"]), dt(a["end"])) for a in p.get("availability", []))
def participants(c): return [str(c["person_id"]), *map(str, c["interviewer_ids"])]
def candidate(w, cid):
    _, cs = maps(w)
    if cid not in cs: raise CoordinationError(f"unknown candidate: {cid}")
    return cs[cid]
def available(w, cid, start, end, ignore=None):
    people, _ = maps(w); c = candidate(w, cid)
    if any(not any(a <= start and end <= b for a,b in intervals(people[pid])) for pid in participants(c)): return False
    mine = set(participants(c))
    for row in w.get("interviews", []):
        if row.get("status") == "cancelled" or row.get("id") == ignore or row.get("candidate_id") == cid: continue
        if not mine.intersection(participants(candidate(w, str(row["candidate_id"])))): continue
        if start < dt(row["end"]) and dt(row["start"]) < end: return False
    return True

def slots(w, cid, duration=45, step=15):
    validate(w)
    if duration <= 0 or step <= 0: raise CoordinationError("duration/step must be positive")
    people,_ = maps(w); c = candidate(w,cid); base = intervals(people[str(c["person_id"])])
    out=[]; dur=timedelta(minutes=duration); inc=timedelta(minutes=step)
    for a,b in base:
        cur=a
        while cur+dur <= b:
            if available(w,cid,cur,cur+dur): out.append({"start":iso(cur),"end":iso(cur+dur)})
            cur += inc
    return out

def schedule(w, cid, start, duration=45):
    validate(w); s=dt(start); e=s+timedelta(minutes=duration)
    if duration <= 0 or not available(w,cid,s,e): raise CoordinationError("requested slot is not available")
    if any(r.get("candidate_id")==cid and r.get("status")!="cancelled" for r in w.get("interviews", [])): raise CoordinationError("candidate already has active interview")
    used={str(r.get("id")) for r in w.get("interviews", [])}; n=1
    while f"int-{cid}-{n}" in used: n+=1
    row={"id":f"int-{cid}-{n}","candidate_id":cid,"start":iso(s),"end":iso(e),"status":"scheduled","version":1,"previous_slots":[]}
    w.setdefault("interviews", []).append(row); validate(w); return copy.deepcopy(row)

def interview(w, iid):
    for r in w.get("interviews", []):
        if r.get("id") == iid: return r
    raise CoordinationError(f"unknown interview: {iid}")
def reschedule(w, iid, start):
    validate(w); row=interview(w,iid)
    if row["status"] == "cancelled": raise CoordinationError("cancelled interview cannot move")
    old_s, old_e = dt(row["start"]), dt(row["end"]); s=dt(start); e=s+(old_e-old_s); cid=str(row["candidate_id"])
    if not available(w,cid,s,e,ignore=iid): raise CoordinationError("requested reschedule slot is not available")
    row.setdefault("previous_slots", []).append({"start":iso(old_s),"end":iso(old_e)})
    row.update(start=iso(s),end=iso(e),status="rescheduled",version=int(row.get("version",1))+1); validate(w); return copy.deepcopy(row)

def packet(w, iid, reminder=False):
    validate(w); row=interview(w,iid); people,cs=maps(w); c=cs[str(row["candidate_id"])]
    cp=people[str(c["person_id"])]; panel=[people[str(x)] for x in c["interviewer_ids"]]; recruiter=people[str(c["recruiter_id"])]
    when=f"{row['start']}–{row['end']}"; word="updated" if row["status"]=="rescheduled" else "scheduled"
    drafts=[{"recipient_id":cp["id"],"recipient_kind":"candidate","recipient_contact":cp["contact"],"subject":f"Interview {word}: {c['role']}","body":f"Hi {cp['name']}, your interview for {c['role']} is {word} for {when}. You’ll meet with {panel[0]['name']} and {panel[1]['name']}. Reply to {recruiter['name']} if the time no longer works.","send":False}]
    for p in panel: drafts.append({"recipient_id":p["id"],"recipient_kind":"interviewer","recipient_contact":p["contact"],"subject":f"Interview {word}: {c['role']}","body":f"Hi {p['name']}, the {c['role']} interview with {cp['name']} is {word} for {when}. Coordinate logistics with {recruiter['name']} if needed.","send":False})
    if reminder:
        for d in drafts: d["subject"]="Reminder: "+d["subject"]; d["body"]="Reminder — "+d["body"]
    out={"demand_id":DEMAND_ID,"offer":OFFER,"candidate_id":c["id"],"interview":copy.deepcopy(row),"drafts":drafts,"handoff":{"candidate_id":c["id"],"candidate_name":cp["name"],"role":c["role"],"interview_id":row["id"],"status":row["status"],"version":row["version"],"start":row["start"],"end":row["end"],"interviewer_names":[p["name"] for p in panel],"recruiter_id":recruiter["id"],"recruiter_name":recruiter["name"],"previous_slots":copy.deepcopy(row.get("previous_slots",[])),"next_action":"Recruiter reviews drafts and sends them through the employer's existing tools."},"automatic_sends":0,"hiring_decisions":False,"ranking":False,"rejection":False}
    if reminder: out["kind"]="reminder"
    dumped=json.dumps(out,sort_keys=True)
    for other in w["candidates"]:
        if other["id"] == c["id"]: continue
        op=people[str(other["person_id"])]
        if any(str(x) in dumped for x in (other["id"],op["name"],op["contact"])): raise CoordinationError("cross-candidate data leak")
    return out

# Public names stay descriptive for library consumers and tests.
validate_workspace = validate

def available_slots(w, candidate_id, *, duration_minutes=45, step_minutes=15):
    return slots(w, candidate_id, duration_minutes, step_minutes)

def schedule_interview(w, candidate_id, start, *, duration_minutes=45):
    return schedule(w, candidate_id, start, duration_minutes)

def reschedule_interview(w, interview_id, new_start):
    return reschedule(w, interview_id, new_start)

def coordination_packet(w, interview_id):
    return packet(w, interview_id)

def reminder_packet(w, interview_id):
    return packet(w, interview_id, True)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("workspace",type=Path); sub=p.add_subparsers(dest="cmd",required=True)
    q=sub.add_parser("slots"); q.add_argument("candidate_id"); q.add_argument("--duration",type=int,default=45); q.add_argument("--step",type=int,default=15)
    q=sub.add_parser("schedule"); q.add_argument("candidate_id"); q.add_argument("start"); q.add_argument("--duration",type=int,default=45)
    q=sub.add_parser("reschedule"); q.add_argument("interview_id"); q.add_argument("start")
    sub.add_parser("packet").add_argument("interview_id"); sub.add_parser("reminder").add_argument("interview_id")
    a=p.parse_args(argv); w=load(a.workspace)
    if a.cmd=="slots": out=slots(w,a.candidate_id,a.duration,a.step)
    elif a.cmd=="schedule": out=schedule(w,a.candidate_id,a.start,a.duration); save(a.workspace,w)
    elif a.cmd=="reschedule": out=reschedule(w,a.interview_id,a.start); save(a.workspace,w)
    elif a.cmd=="packet": out=packet(w,a.interview_id)
    else: out=packet(w,a.interview_id,True)
    print(json.dumps(out,indent=2,sort_keys=True)); return 0
if __name__ == "__main__": raise SystemExit(main())
