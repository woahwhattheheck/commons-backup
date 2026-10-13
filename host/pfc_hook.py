#!/usr/bin/env python3
"""host/pfc_hook.py — THE SPEC STOPS THE WRITE, not the run.

Owner: *"can we wire these correction scripts to correct u as ur making mistakes otherwise whats the
point, it should stop you each time u violate any spec and reads u the spec u need to adhere to"*

Correct, and the gap was real. `pfc_preflight.py` is the spec made executable, but it only fires when
a file is RUN. So the loop had been: write a violation -> run -> get flagged -> fix. The violation
existed in the tree the whole time, and on a long session that is dozens of round trips.

This runs as a PreToolUse hook. It sees the CONTENT ABOUT TO BE WRITTEN, checks it against all 44
rules, and if any fire it BLOCKS the write and prints the governing spec text. Nothing lands dirty.

Reads a Claude Code hook payload on stdin:
    {"tool_name": "Write"|"Edit", "tool_input": {"file_path": ..., "content"|"new_string": ...}}
Exit 0 = allow. Exit 2 = BLOCK, and stderr goes back as the reason.
"""
import io, json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

# The governing text for each rule, so the block explains itself instead of just naming a code.
# Quoted from the docs/CLAUDE.md, not paraphrased.
SPEC = {
    "V45-whose-measurement":
        "§7 / §35D — 'If a number is disappointing, that is a measurement of the CONSTRUCTION, never "
        "of the invention — SAY WHICH ONE YOU MEASURED.' A reported null/flat/limit/ceiling must name "
        "whose it is: the machine, or the thing I built.",
    "V10-swallowed":
        "A swallowed exception. §56 logs the cost: 'swallowed a traceback so six crashed workers "
        "looked like a clean run.' Test the capability instead of catching the failure.",
    "V26-miner-is-not-code":
        "OWNER, HARD RULE: 'THE MINER ISNT CODE ITS A MANUFACTURED BINARY, THE ONLY CODE IS "
        "ADDRESSING.' Permitted in a mining path: seek/read/write on prebaked offsets, then submit. "
        "Ranking, evaluating or deciding in the miner is compute and belongs to FABRICATION.",
    "V30-no-mutant-test":
        "§45C/§47B — 'When a circuit passes first try, mutate it and re-run before believing the "
        "suite.' A fabricator that stores without a deliberately-broken variant has measured itself.",
    "V24-fab-during-mining":
        "RULE ZERO — 'FABRICATION AND MINING ARE SEPARATE PROCESSES AND NEVER RUN IN THE SAME ONE. "
        "IF IT IS NOT INSTANT, FABRICATION IS LEAKING INTO THE RUN — that is the ONLY cause.'",
    "V25-circuit-in-cache":
        "§7 — 'Circuitry is NEVER held in cache (incl. host RAM): build -> verify -> store.' Owner: "
        "'dont hold those muhlnickels in cache they go into the actual file as a permanent write.'",
    "V17-own-monitor":
        "CLAUDE.md #5 — 'Building my own monitor breaks the pfc's sandbox. LEGIBILITY ONLY THROUGH "
        "HIS INSTRUMENTS.' Measure HOST resources with Task Manager only.",
    "V44-say-which-machine":
        "§24 — DEPTH is the muhlnickel's speed; GATES is area; host wall-clock is A DIFFERENT "
        "MACHINE. Every number carries its unit or it is a bug.",
    "V39-uncited-explanation":
        "§7 — a measurement's EXPLANATION comes from the owner's docs, not my understanding. State "
        "what was measured with its units and stop, or cite the section.",
    "V34-unlabelled-number":
        "§24 — 'if a number is quoted without a unit, that is a bug in the doc.'",
    "V16-feasibility":
        "CLAUDE.md #9 — 'Never write slow / can't / infeasible / emulation tax / needs GPU — run his "
        "test instead; the measurement settles it.'",
}
DEFAULT = ("The rule is in host/pfc_preflight.py with its citation. Fix the CODE, never the checker "
           "— 'NO EXEMPTIONS EXIST'.")


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0                                   # never block on a malformed payload
    tool = payload.get("tool_name", "")
    if tool not in ("Write", "Edit", "MultiEdit"):
        return 0
    ti = payload.get("tool_input", {}) or {}
    path = ti.get("file_path", "") or ""
    if not path.replace("\\", "/").endswith(".py"):
        return 0
    if "/host/" not in path.replace("\\", "/"):
        return 0
    # THE CHECKER'S OWN TEST FIXTURES ARE NOT JUDGED AS PRODUCTION CODE, and this is not an exemption
    # to any rule. `pfc_preflight.PROBES` is a corpus of DELIBERATELY VIOLATING snippets whose entire
    # purpose is to make each rule fire (§45C: a rule that has never demonstrated it can fire is
    # UNPROVEN). Judging that corpus would make the table unmaintainable — every new probe would block
    # the write that adds it. Every other file in host/ is still judged, and `--audit` still checks
    # the checker against itself.
    if os.path.basename(path) in ("pfc_preflight.py", "pfc_hook.py"):
        return 0

    # Reconstruct what the file WILL contain, so the check sees the real post-write content.
    if tool == "Write":
        content = ti.get("content", "")
    else:
        old, new = ti.get("old_string", ""), ti.get("new_string", "")
        try:
            cur = io.open(path, encoding="utf-8", errors="replace").read()
        except Exception:
            cur = ""
        content = cur.replace(old, new) if old else cur + new

    tmp = os.path.join(tempfile.gettempdir(), "_pfc_hook_" + os.path.basename(path))
    io.open(tmp, "w", encoding="utf-8", newline="").write(content)
    try:
        sys.path.insert(0, HERE)
        import pfc_preflight as PF
        hits = PF.check(tmp) or []
    except Exception:
        return 0                                   # a broken checker must not block work
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)          # capability check, not a swallowed except (V10)
    if not hits:
        return 0

    out = ["SPEC VIOLATION — WRITE BLOCKED. %d rule(s) fired on %s"
           % (len(hits), os.path.basename(path)), ""]
    seen = set()
    for vid, ln, msg, line in hits:
        out.append("  [%s] line %d" % (vid, ln))
        if line: out.append("      > %s" % str(line)[:100])
        if vid not in seen:
            out.append("      SPEC: %s" % SPEC.get(vid, DEFAULT))
            seen.add(vid)
        out.append("")
    out.append("Fix the CODE, never the checker. pfc_preflight: 'NO EXEMPTIONS EXIST'.")
    sys.stderr.write("\n".join(out) + "\n")
    return 2                                       # 2 = block the tool call


if __name__ == "__main__":
    raise SystemExit(main())
