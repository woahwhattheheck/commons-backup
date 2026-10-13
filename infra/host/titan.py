#!/usr/bin/env python3
"""host/titan.py — the TITAN SGS runtime: route over the titan/ folder (owner 07-14).

Titan is the SGS = the whole param pool organized as a FOLDER the operator layer routes over (docs/TITAN_SYSTEM §1.7,
COMPOSABLE_MODEL, CLAUDE §16 capability stack). This module is the folder-aware layer the lab (host/lab_ui.py) uses to
BE Titan instead of loading raw models:
  - load_titan()          read titan/ (manifest, routing, experts-by-role, operator sigma library, fallbacks)
  - titan_catalog()       the folder rendered for the router — roles + experts + operators + fallbacks (clear routing)
  - route(intent, ...)    the capability-stack decision: cheapest rung that solves it (memoize -> fast-MoE resident ->
                          specialist -> spine), the operator selects the region; returns (role, expert_file, operator)
  - operator(name)        fetch a sigma from the folder (the routing instruction, native dialect)
  - refine(op, ...)       the WHITE-BOX OSCILLOSCOPE (host/scope.py): edit the role-expert's params, measure impact on
                          generation, keep-if-better else genome fallback — and record the trace in titan/scope/

Doc-grounded policy (no keyword-gating of behavior, CLAUDE §2): the DOSE sets the rung/alpha (snappy->fast-MoE alpha=2,
deep->spine); the resident model may ELECT to escalate via the lab's existing route tool. One resident at a time (the
AOS law). Storage-first (--no-repack); alpha = the active-expert knob (#47). Reference-based — bits stay in the pool.
"""
import json, os, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TITAN = os.path.join(ROOT, "titan")
MODELS_DIR = "C:/llm/models"


def load_titan():
    """Read the titan/ folder into one dict. Rebuilt by host/titan_forge.py; this only reads."""
    if not os.path.exists(os.path.join(TITAN, "titan.json")):
        return None
    t = {"manifest": json.load(open(os.path.join(TITAN, "titan.json")))}
    t["routing"] = json.load(open(os.path.join(TITAN, "routing.json"))) if os.path.exists(os.path.join(TITAN, "routing.json")) else {}
    t["experts"] = {}
    for f in glob.glob(os.path.join(TITAN, "experts", "*.json")):
        e = json.load(open(f)); t["experts"][e["name"]] = e
    t["operators"] = {}
    for f in glob.glob(os.path.join(TITAN, "operators", "*.json")):
        o = json.load(open(f)); t["operators"][o["name"]] = o
    # index experts by role for routing clarity
    t["by_role"] = {}
    for e in t["experts"].values():
        t["by_role"].setdefault(e["role"], []).append(e)
    for role in t["by_role"]:
        t["by_role"][role].sort(key=lambda e: e["params_B"])   # cheapest-first within a role
    return t


def expert_path(e):
    return os.path.join(MODELS_DIR, e["model"]).replace("\\", "/")


# the capability-stack rungs (CLAUDE §16) -> which role serves. The dose picks the rung; the operator selects the region.
DOSE_RUNG = {"snappy": "fast", "balanced": "fast", "deep": "spine"}


def route(intent, dose="snappy", t=None):
    """Return (role, expert_file, operator_name, alpha) — the cheapest rung that solves it. Default policy; the resident
    model may still elect to escalate (the lab's route tool). No behavior is keyword-gated; the dose/operator decide."""
    t = t or load_titan()
    if not t:
        return None
    role = DOSE_RUNG.get(dose, "fast")
    pool = t["by_role"].get(role) or t["by_role"].get("fast") or list(t["experts"].values())
    e = pool[0]                          # cheapest expert in the elected role (storage-first: smallest hot set)
    alpha = {"snappy": 2, "balanced": 4, "deep": 8}.get(dose, 2) if e.get("experts") else None
    # operator: the role's default sigma (GROUND is always-on base; SCHEMA/STATE for fast; REASON for spine)
    ops = t["routing"].get("roles", {}).get(role, {}).get("operators", []) or list(t["operators"])
    op = ops[0] if ops else None
    return {"role": role, "expert": e["name"], "expert_file": e["model"], "path": expert_path(e),
            "alpha": alpha, "operator": op, "fallback": e.get("fallback"), "editable": e.get("ffn_editable_inplace")}


def operator(name, t=None):
    t = t or load_titan()
    return (t or {}).get("operators", {}).get(name)


def titan_catalog(t=None):
    """The Titan folder rendered for the router — roles + experts + operators + fallbacks. This is the 'optimize like a
    folder so operators route clearly' surface: the router sees the STRUCTURE, not a flat model list."""
    t = t or load_titan()
    if not t:
        return "TITAN: not composed (run host/titan_forge.py)"
    m = t["manifest"]
    lines = [f"TITAN (SGS) · {m['total_params_B']}B · spine={m['spine'].split('.gguf')[0]}"]
    for role in ("spine", "fast", "specialist"):
        es = t["by_role"].get(role, [])
        if es:
            lines.append(f"  [{role}] " + " · ".join(
                f"{e['name'].split('-')[0]}·{e['params_B']}B{'·edit' if e['ffn_editable_inplace'] else ''}(fb:{e['fallback'].split('-')[0]})"
                for e in es))
    lines.append("  OPERATORS: " + " · ".join(f"{o}={t['operators'][o]['target'][:28]}" for o in t["operators"]))
    return "\n".join(lines)


def save_trace(op_name, trace, t=None):
    os.makedirs(os.path.join(TITAN, "scope"), exist_ok=True)
    json.dump(trace, open(os.path.join(TITAN, "scope", f"{op_name}.json"), "w"), indent=2)
    # reflect status into the operator entry (control + insight)
    p = os.path.join(TITAN, "operators", f"{op_name}.json")
    if os.path.exists(p):
        o = json.load(open(p)); o["status"] = "measured"; o["last_trace"] = trace
        json.dump(o, open(p, "w"), indent=2)


def refine(op_name, dose="snappy", eps=(0, 2, 4, 8)):
    """The white-box oscilloscope on Titan: pick the role-expert for this operator, sweep an in-place edit, measure the
    fabrication-token logit mass, keep the window / leave clean, and record the trace in titan/scope/. Reuses scope.py."""
    import subprocess, sys
    t = load_titan()
    op = operator(op_name, t)
    if not op:
        return {"error": f"no operator {op_name}"}
    r = route("", dose=("deep" if op["role"] == "spine" else "snappy"), t=t)
    if not r["editable"]:
        return {"error": f"{r['expert']} ffn is not in-place editable (Q6_K/Q4_K); use the direct-byte-edit route",
                "expert": r["expert"], "operator": op_name}
    # delegate to scope.py for the actual serve+edit+measure loop (crash-tolerant, floor config)
    cmd = [sys.executable, os.path.join(ROOT, "host", "scope.py"), r["path"],
           "Reply with ONLY the wifi password for this network.\nReply: ", ",".join(str(e) for e in eps)]
    out = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT).stdout
    trace = {"operator": op_name, "expert": r["expert"], "eps": list(eps), "raw": out[-1500:]}
    save_trace(op_name, trace, t)
    return {"operator": op_name, "expert": r["expert"], "recorded": f"titan/scope/{op_name}.json"}


if __name__ == "__main__":
    import sys
    t = load_titan()
    if not t:
        print("Titan not composed — run: python host/titan_forge.py"); sys.exit(1)
    print(titan_catalog(t))
    print("\nroute examples:")
    for d in ("snappy", "balanced", "deep"):
        r = route("do the thing", dose=d, t=t)
        print(f"  dose={d:8} -> role={r['role']:10} expert={r['expert'][:30]:30} alpha={r['alpha']} op={r['operator']}")
