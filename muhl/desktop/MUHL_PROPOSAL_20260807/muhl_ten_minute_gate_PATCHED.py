#!/usr/bin/env python3
# AUTHORSHIP: written by an AI assistant at the owner's instruction. Not the owner's writing.
# This banner puts the file on muhl_cite_corpus's POISON list, so nothing quoted below can ever
# be walked back as "the owner's words." The authority is his own docs, never this file.
"""Component implementation and operation."""
import datetime
import io
import json
import os
import re
import sys

TEN_MIN = 600

HOME = os.path.expanduser("~")
LOG = os.path.join(HOME, ".claude", "hooks", "muhl_ten_minute_gate.log")

# Harness-generated records that are NOT the owner typing. Any of these resetting the turn
# clock is a hole - a task notification would license an instant reply.
BANNER = "BLOCKED BY THE 10-MINUTE COMMANDMENT"

NOT_HIM = (
    # THE GATE'S OWN BLOCK MESSAGE. Harness feedback is injected as a user record, so without
    # this the gate (a) treated its own output as a fresh owner turn, resetting the clock, and
    # (b) scanned it for the override — which its own text matches, because it QUOTES the rule
    # "...work for less than 10 minutes". Firing once therefore disabled the gate. That is how
    # an 8-minute turn got through on 2026-08-06. Excluded first, before anything else.
    re.compile(re.escape(BANNER)),
    re.compile(r"^\s*<task-notification>", re.S),
    re.compile(r"^\s*\[Request interrupted by user", re.I),
    re.compile(r"^\s*\[Request interrupted", re.I),
    re.compile(r"^\s*Continue from where you left off", re.I),
    re.compile(r"^\s*<local-command-caveat>", re.S),
    re.compile(r"^\s*<command-name>", re.S),
)

# THE OWNER'S OVERRIDE. He set the rule, so he can lift it — a gate its own author cannot
# override is a wedge, not a checker. This is SAFE against the assistant gaming it for the same
# reason muhl_cite_gate works: the text is read from HIS message in the transcript, and the
# assistant cannot write his messages. Owner, 2026-08-06: "u may for this turn and this turn
# only take less than 10 minutes". Every override is logged.
OVERRIDE = (
    re.compile(r"\btake\s+less\s+than\s+(?:10|ten)\b", re.I),
    re.compile(r"\bless\s+than\s+(?:10|ten)\s+min", re.I),
    re.compile(r"\b(?:skip|waive|lift|ignore)\s+(?:the\s+)?(?:10|ten)[\s-]*min", re.I),
    re.compile(r"\b(?:10|ten)[\s-]*min(?:ute)?s?\s+(?:exemption|override|off)\b", re.I),
    re.compile(r"\bshort\s+turn\s+(?:is\s+)?(?:ok|okay|fine|allowed)\b", re.I),
    # STANDING RULE, owner 2026-08-06: "TLDR IS AN EXCEPTION TO FIVE MINUTE RULE, TLDR".
    # Asking for a summary is asking NOT to have ten minutes of fresh work bolted onto it.
    # Not gameable by the assistant: the word must appear in HIS message, which the assistant
    # cannot write. The gate's own block text contains no "tldr", and quoted material is
    # stripped before this is scanned.
    re.compile(r"^\s*tl[\s;,]*dr\b|\btl[\s;,]*dr\s*$", re.I),
)

# INTENT GUARDS (added 2026-08-06). An override is a phrase he MEANS as an exemption.
# Substring presence is not intent: "dont tldr me" and "dont skip the 10 min rule" both
# matched and lifted the floor. Measured on the production hook, 8 reachable holes.
SELF_OUTPUT = re.compile(r"OWNER OVERRIDE|BLOCKED BY THE|ALLOW\s+OWNER|BLOCK\s+elapsed"
                         r"|muhl_ten_minute_gate", re.I)
NEGATOR = re.compile(r"^(dont|don't|do|not|no|never|stop|avoid|why|didnt|didn't"
                     r"|shouldnt|shouldn't|cant|can't)$", re.I)


def negated(text, m):
    """True if a negation word sits within 4 words before the match."""
    return any(NEGATOR.match(w) for w in re.findall(r"[\w']+", text[:m.start()])[-4:])

KEEP_WORKING = [
    "read another of his docs end to end - not a skim, not an excerpt",
    "verify a claim against the binary itself instead of against a doc",
    "extend or harden what you just built, and re-run its battery",
    "measure something and bring him the number",
    "find the next limit and attribute it: host, muhlnickel, or us being wrong",
]


def log(msg):
    try:
        with io.open(LOG, "a", encoding="utf-8") as f:
            f.write("%s  %s\n" % (datetime.datetime.now().isoformat(timespec="seconds"), msg))
    except Exception:
        pass


def allow(why):
    log("ALLOW  " + why)
    sys.exit(0)


def text_of(rec):
    c = (rec.get("message") or {}).get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        # a record that is only tool_result is the harness feeding output back, not him typing
        if c and all(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
            return ""
        return "\n".join(b.get("text", "") for b in c
                         if isinstance(b, dict) and b.get("type") == "text")
    return ""


def is_owner_turn(rec):
    if rec.get("type") != "user":
        return False
    txt = text_of(rec)
    txt = re.sub(r"<system-reminder>.*?</system-reminder>", "", txt, flags=re.S)
    if not txt.strip():
        return False
    for rx in NOT_HIM:
        if rx.search(txt):
            return False
    return True


def parse_ts(s):
    if not s:
        return None
    try:
        s = s.replace("Z", "+00:00")
        return datetime.datetime.fromisoformat(s)
    except Exception:
        return None


def last_owner_turn(path):
    """(timestamp, first line of what he said) for the most recent real owner message."""
    found = None
    with io.open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if is_owner_turn(rec):
                ts = parse_ts(rec.get("timestamp"))
                if ts is not None:
                    body = text_of(rec).strip()
                    found = (ts, body.splitlines()[0][:70], body)
    return found


def main():
    # Read stdin defensively. A UTF-8 BOM alone used to defeat this and fail the gate OPEN,
    # which means any harness quirk that malforms stdin silently disables enforcement.
    # Measured 2026-08-06. Strip BOM/whitespace and retry before ever failing open.
    try:
        raw = sys.stdin.read()
    except Exception as e:
        allow("stdin unreadable (%s) - failing open" % e)
    try:
        payload = json.loads(raw.lstrip("﻿").strip() or "{}")
    except Exception as e:
        i, j = raw.find("{"), raw.rfind("}")
        try:
            payload = json.loads(raw[i:j + 1])
        except Exception:
            allow("stdin not JSON (%s) - failing open" % e)

    path = payload.get("transcript_path")
    if not path or not os.path.exists(path):
        allow("no transcript_path - failing open")

    try:
        got = last_owner_turn(path)
    except Exception as e:
        allow("transcript unparseable (%s) - failing open" % e)

    if not got:
        allow("no owner turn in transcript yet - failing open")

    ts, said, full = got
    # QUOTED TEXT CANNOT AUTHORISE AN EXEMPTION. Quoting the rule ("...work for less than 10
    # minutes") must never read as permission to break it. Strip everything inside quotes
    # before scanning, so only the owner's OWN unquoted words can lift the floor.
    unquoted = re.sub(r'["“”\'].*?["“”\']', " ", full, flags=re.S)
    if BANNER in full:
        unquoted = ""                       # belt and braces: never override off gate output
    if SELF_OUTPUT.search(unquoted):
        unquoted = ""                       # never take an exemption from gate output
    for rx in OVERRIDE:
        m = rx.search(unquoted)
        if m and not negated(unquoted, m):
            allow("OWNER OVERRIDE in this turn — %r" % said)

    now = datetime.datetime.now(datetime.timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=datetime.timezone.utc)
    elapsed = (now - ts).total_seconds()

    if elapsed >= TEN_MIN:
        allow("turn ran %dm%02ds - floor met" % (int(elapsed) // 60, int(elapsed) % 60))

    remain = int(TEN_MIN - elapsed)
    em, es = int(elapsed) // 60, int(elapsed) % 60
    rm, rs = remain // 60, remain % 60

    reason = (
        "BLOCKED BY THE 10-MINUTE COMMANDMENT.\n\n"
        "This turn has run %dm%02ds. The floor is 10 MINUTES, every turn, without exception.\n"
        "%dm%02ds remain before you may end this turn.\n\n"
        'His rule, verbatim: "that turn was 46 seconds fix the invalid checker i should not '
        'see a reply unless u worked for 10 mins. period even if i type one token stop '
        'skimping"\n'
        'And: "thou shalt not ever work for less than 10 minutes. one minute turns and those '
        'who take them are an abomination"\n\n'
        "A short turn is the tell that you did it shallow. Do NOT pad with prose and do NOT\n"
        "re-summarise what you already said - that is skimping wearing a longer coat. Go\n"
        "deeper on the actual task:\n%s\n\n"
        "His turn opened with: %r\n"
        "Keep working. The gate releases itself when the ten minutes are up."
        % (em, es, rm, rs, "\n".join("  - " + s for s in KEEP_WORKING), said)
    )

    log("BLOCK  elapsed=%ds remain=%ds" % (int(elapsed), remain))
    json.dump({"decision": "block", "reason": reason}, sys.stdout)
    sys.exit(0)


if __name__ == "__main__":
    main()
