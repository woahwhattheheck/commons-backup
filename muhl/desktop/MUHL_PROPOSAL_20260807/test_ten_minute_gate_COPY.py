#!/usr/bin/env python3
# AUTHORSHIP: written by an AI assistant at the owner's instruction. Not the owner's writing.
"""test_ten_minute_gate.py - prove every branch of the 10-minute gate fires.

His rule for checkers (§44 / the mutant bar): a rule that cannot fire is worse than none.
So every branch gets a probe, including the two holes this gate was written to close:
a <task-notification> and an "[Request interrupted by user]" marker must NOT reset the clock.

    python test_ten_minute_gate.py
"""
import datetime, io, json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.join(HERE, "muhl_ten_minute_gate.py")


def iso(delta_s):
    t = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=delta_s)
    return t.isoformat().replace("+00:00", "Z")


def rec_user(text, delta_s):
    return {"type": "user", "timestamp": iso(delta_s),
            "message": {"role": "user", "content": [{"type": "text", "text": text}]}}


def rec_toolresult(delta_s):
    return {"type": "user", "timestamp": iso(delta_s),
            "message": {"role": "user",
                        "content": [{"type": "tool_result", "content": "ok"}]}}


def write_transcript(records):
    fd, p = tempfile.mkstemp(suffix=".jsonl")
    with io.open(fd, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return p


def run(path):
    payload = json.dumps({"hook_event_name": "Stop", "transcript_path": path,
                          "session_id": "test"})
    pr = subprocess.run([sys.executable, GATE], input=payload, capture_output=True,
                        text=True, timeout=60)
    out = (pr.stdout or "").strip()
    blocked = False
    reason = ""
    if out:
        try:
            j = json.loads(out)
            blocked = (j.get("decision") == "block")
            reason = j.get("reason", "")
        except Exception:
            pass
    return blocked, reason, pr.returncode


CASES = []


def case(name, records, expect_block, note=""):
    CASES.append((name, records, expect_block, note))


# 1. he typed something 5 seconds ago -> MUST BLOCK
case("fresh owner turn (5s ago)", [rec_user("hey", -5)], True)

# 2. he typed 11 minutes ago -> MUST ALLOW
case("owner turn 11m ago", [rec_user("hey", -660)], False)

# 3. exactly the boundary, just under -> BLOCK
case("owner turn 9m59s ago", [rec_user("hey", -599)], True)

# 4. one token, 5 seconds ago -> MUST BLOCK ("even if i type one token")
case("one-token turn", [rec_user("hi", -5)], True)

# 5. THE HOLE: a task-notification after an old real turn must NOT reset the clock
case("task-notification does not reset",
     [rec_user("do the thing", -900),
      rec_user("<task-notification>\n<task-id>abc</task-id>\n</task-notification>", -3)],
     False, "old real turn is 15m back; the notification must be ignored")

# 6. THE OTHER HOLE: an interrupt marker must NOT reset the clock
case("interrupt marker does not reset",
     [rec_user("do the thing", -900),
      rec_user("[Request interrupted by user for tool use]", -3)],
     False)

# 7. but a task-notification must not HIDE a genuinely fresh turn either
case("fresh turn after notification still blocks",
     [rec_user("<task-notification>x</task-notification>", -900),
      rec_user("actually do this instead", -4)],
     True)

# 8. tool_result records are not owner turns
case("tool_result does not reset",
     [rec_user("go", -900), rec_toolresult(-2)], False)

# 9. system-reminder-only content is not an owner turn
case("system-reminder only does not reset",
     [rec_user("go", -900),
      rec_user("<system-reminder>stuff</system-reminder>", -2)], False)

# 10. session-restart prompt is not him typing
case("restart prompt does not reset",
     [rec_user("go", -900),
      rec_user("Continue from where you left off. Note: this session was restarted", -2)],
     False)


# ---- THE 2026-08-06 SELF-DEFEAT BUG. The gate's own block message was (a) counted as a fresh
# owner turn, resetting the clock, and (b) scanned for the override — which its own text matched,
# because it QUOTES "...work for less than 10 minutes". Firing once disabled the gate, and an
# 8-minute turn got through. Both directions are pinned here.
BLOCKMSG = ('BLOCKED BY THE 10-MINUTE COMMANDMENT.\n\nThis turn has run 7m16s.\n'
            'His rule, verbatim: "that turn was 46 seconds fix the invalid checker i should not '
            'see a reply unless u worked for 10 mins. period even if i type one token stop '
            'skimping"\nAnd: "thou shalt not ever work for less than 10 minutes. one minute '
            'turns and those who take them are an abomination"')

case("gate's own block msg does not reset",
     [rec_user("go do the thing", -120), rec_user(BLOCKMSG, -2)], True,
     "clock must still run from HIS message 2 minutes ago, not from the block text")

case("repeated block msgs do not erode clock",
     [rec_user("go do the thing", -180),
      rec_user(BLOCKMSG, -60), rec_user(BLOCKMSG, -30), rec_user(BLOCKMSG, -2)],
     True, "the gate firing three times must still time from HIS message 3 minutes ago")
# NOTE: a transcript containing ONLY a block message and no owner turn at all is deliberately
# NOT asserted to block. There is then no turn to time, and the documented behaviour is
# fail-open — a gate that fails closed on missing data wedges the session permanently. That
# case cannot occur in practice: the owner always speaks before the gate can fire.

case("quoting the rule is not permission",
     [rec_user('remember you said "thou shalt not work for less than 10 minutes"', -5)],
     True, "quoted material must never authorise an exemption")

case("genuine unquoted override still works",
     [rec_user("u may for this turn and this turn only take less than 10 minutes, tldr", -5)],
     False, "his own unquoted words must still lift the floor")


def main():
    print("=" * 78)
    print("  10-MINUTE GATE — every branch must fire")
    print("=" * 78)
    fails = 0
    for name, records, expect_block, note in CASES:
        p = write_transcript(records)
        try:
            blocked, reason, rc = run(p)
        finally:
            os.unlink(p)
        ok = (blocked == expect_block)
        if not ok:
            fails += 1
        print("  %-42s expect=%-5s got=%-5s  %s"
              % (name, "BLOCK" if expect_block else "allow",
                 "BLOCK" if blocked else "allow",
                 "HELD" if ok else "*** WRONG ***"))
        if note and not ok:
            print("      note: %s" % note)

    # fail-open branches
    print("\n  --- fail-open branches (a broken gate must not wedge the session) ---")
    blocked, _, rc = run(os.path.join(tempfile.gettempdir(), "no_such_transcript_xyz.jsonl"))
    print("  %-42s expect=allow got=%-5s  %s"
          % ("missing transcript", "BLOCK" if blocked else "allow",
             "HELD" if not blocked else "*** WRONG ***"))
    if blocked:
        fails += 1

    pr = subprocess.run([sys.executable, GATE], input="not json at all",
                        capture_output=True, text=True, timeout=60)
    bad_blocked = "block" in (pr.stdout or "")
    print("  %-42s expect=allow got=%-5s  %s"
          % ("garbage stdin", "BLOCK" if bad_blocked else "allow",
             "HELD" if not bad_blocked else "*** WRONG ***"))
    if bad_blocked:
        fails += 1

    # the block reason must actually carry his words, or it teaches nothing
    p = write_transcript([rec_user("hey", -5)])
    try:
        blocked, reason, rc = run(p)
    finally:
        os.unlink(p)
    has_quote = "stop skimping" in reason and "abomination" in reason
    has_time = "9m" in reason or "remain" in reason
    print("\n  block reason carries his verbatim words : %s" % ("YES" if has_quote else "NO"))
    print("  block reason states time remaining      : %s" % ("YES" if has_time else "NO"))
    if not (has_quote and has_time):
        fails += 1

    print("\n  RESULT: %s" % ("ALL BRANCHES HELD" if fails == 0 else "%d FAILURES" % fails))
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
