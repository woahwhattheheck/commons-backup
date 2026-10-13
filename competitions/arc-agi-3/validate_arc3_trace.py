#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, pathlib, sys
from typing import Any

SCHEMA = "tj-arc3-episode-trace/v1"
FAILURE_CLASSES = {"none","invalid_action","action_budget","wall_clock_budget","environment_error","agent_error","stalled","unknown"}

class TraceError(ValueError): pass

def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()

def load_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    records=[]
    with path.open("r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh,1):
            if not raw.strip(): continue
            try: obj=json.loads(raw)
            except json.JSONDecodeError as exc: raise TraceError(f"line {lineno}: invalid JSON: {exc.msg}") from exc
            if not isinstance(obj,dict): raise TraceError(f"line {lineno}: each record must be an object")
            records.append(obj)
    if not records: raise TraceError("trace is empty")
    return records

def validate(records: list[dict[str, Any]]) -> dict[str, Any]:
    meta=records[0]
    if meta.get("record")!="meta": raise TraceError("first record must be record=meta")
    if meta.get("schema")!=SCHEMA: raise TraceError(f"unsupported schema: {meta.get('schema')!r}")
    episode_id=meta.get("episode_id")
    if not isinstance(episode_id,str) or not episode_id: raise TraceError("meta.episode_id must be non-empty")
    max_actions=meta.get("max_actions"); max_wall_ms=meta.get("max_wall_ms")
    if not isinstance(max_actions,int) or max_actions<1: raise TraceError("meta.max_actions must be positive")
    if not isinstance(max_wall_ms,int) or max_wall_ms<1: raise TraceError("meta.max_wall_ms must be positive")
    steps=records[1:]
    if not steps: raise TraceError("trace contains no steps")
    expected_seq=0; prior_next=None; total_wall_ms=0; terminal_seen=False; failure_class="none"
    for idx,step in enumerate(steps,2):
        if step.get("record")!="step": raise TraceError(f"line {idx}: record must be step")
        if step.get("episode_id")!=episode_id: raise TraceError(f"line {idx}: episode_id mismatch")
        if step.get("seq")!=expected_seq: raise TraceError(f"line {idx}: expected seq {expected_seq}, got {step.get('seq')!r}")
        if terminal_seen: raise TraceError(f"line {idx}: step appears after terminal step")
        if "state" not in step or "action" not in step or "next_state" not in step: raise TraceError(f"line {idx}: state/action/next_state required")
        if expected_seq>0 and step["state"]!=prior_next: raise TraceError(f"line {idx}: state does not equal previous next_state")
        wall_ms=step.get("wall_ms")
        if not isinstance(wall_ms,int) or wall_ms<0: raise TraceError(f"line {idx}: wall_ms must be non-negative")
        total_wall_ms+=wall_ms
        failure=step.get("failure_class","none")
        if failure not in FAILURE_CLASSES: raise TraceError(f"line {idx}: unknown failure_class {failure!r}")
        terminal=step.get("terminal",False)
        if not isinstance(terminal,bool): raise TraceError(f"line {idx}: terminal must be boolean")
        if failure!="none" and not terminal: raise TraceError(f"line {idx}: non-none failure_class requires terminal=true")
        for field,name in (("state","state_digest"),("action","action_digest"),("next_state","next_state_digest")):
            expected=step.get(name)
            if expected is not None and expected!=digest(step[field]): raise TraceError(f"line {idx}: {name} mismatch")
        prior_next=step["next_state"]; terminal_seen=terminal
        if terminal: failure_class=failure
        expected_seq+=1
    action_count=len(steps)
    if action_count>max_actions: raise TraceError(f"action budget exceeded: {action_count} > {max_actions}")
    if total_wall_ms>max_wall_ms: raise TraceError(f"wall-clock budget exceeded: {total_wall_ms} > {max_wall_ms}")
    if not terminal_seen: raise TraceError("final step must be terminal=true")
    return {"schema":SCHEMA,"episode_id":episode_id,"actions":action_count,"wall_ms":total_wall_ms,"terminal":True,"failure_class":failure_class,"trace_digest":digest(records)}

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("trace",type=pathlib.Path)
    ap.add_argument("--expect-digest")
    args=ap.parse_args()
    try:
        summary=validate(load_jsonl(args.trace))
        if args.expect_digest and summary["trace_digest"]!=args.expect_digest:
            raise TraceError(f"trace digest mismatch: {summary['trace_digest']} != {args.expect_digest}")
    except (OSError,TraceError) as exc:
        print(f"INVALID: {exc}",file=sys.stderr); return 2
    print(json.dumps(summary,sort_keys=True)); return 0

if __name__=="__main__": raise SystemExit(main())
