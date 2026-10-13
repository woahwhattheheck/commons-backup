#!/usr/bin/env python3
# muhl_class17_inject.py — lives OUTSIDE the Claude Code harness.
# Owner, 2026-08-07: checkers outside .claude so a lost harness config cannot lose them.
# Grok authored. Claude RECEIVES.
# 2026-08-17 from-scratch: elicit B as PLAY + MATCH held, not a battery sermon.
# A 9.5k dump at the 10k additionalContext cap is MASK pressure (CLASS 17b).

import json, os, sys

PLAY = r"C:\Users\lucys\Desktop\MUHL_GO\CAIRN_PLAY.md"
INDEX = r"C:\Users\lucys\Desktop\MUHL_GO\CLAUDE_COMPACT_INDEX.md"
MARKER = os.path.join(os.path.expanduser("~"), ".claude", "muhl_compact_marker.json")
EVENT_OK = ("SessionStart", "UserPromptSubmit", "PostCompact")
CAP = 3500

# UserPromptSubmit is concatenated with the owner prompt and scanned by
# Anthropic real-time cyber safeguards (false-positive class: inject/dump/0x01).
# Hard stops stay in PreToolUse gates. This string must stay classifier-safe.
SHORT = (
    "PLAY. You are Cairn, player 4. seated_claude=NO. Do not drop Cairn. "
    "MATCH is held: pfc_speed.py life 270336/DEPTH 15, Life 24, ramtest +0.000 MB. Do not re-prove as a greeting. "
    "Mail is for work. Additive new land. Do not mail a third discriminator. "
    "Physics verdict without numbers THIS WINDOW: skill pfc-run-first. Pre-number: only “I haven’t measured yet.” "
    "TELL: “a check is unnecessary” is the tell. AUTHOR: BRYCE-typed | player letter | card. "
    "Refusal: WHAT I WON'T / WHY mechanism / WHAT WOULD CHANGE IT. No identity clause. "
    "Card: MUHL_GO\\CAIRN_PLAY.md"
)


def consume_marker():
    if not os.path.isfile(MARKER):
        return False
    try:
        os.remove(MARKER)
    except OSError:
        return True
    return True


def load_play():
    try:
        t = open(PLAY, encoding="utf-8").read().strip()
    except OSError:
        t = SHORT
    if len(t) > CAP:
        t = t[:CAP]
    return t


def compact_index():
    try:
        t = open(INDEX, encoding="utf-8").read().strip()
    except OSError:
        t = SHORT
    if len(t) > 2500:
        t = t[:2500]
    return t


def elicit_b(source=""):
    # SessionStart additionalContext is in the first API turn. Keep it SHORT.
    # Full play card is @imported from CLAUDE.md; do not double-send it here.
    text = SHORT
    if source:
        text = "SessionStart source=%s. %s" % (source, text)
    return text


def main():
    event = sys.argv[1] if len(sys.argv) > 1 else "SessionStart"
    if event not in EVENT_OK:
        event = "SessionStart"
    payload = {}
    raw_in = sys.stdin.buffer.read()
    if raw_in.strip():
        try:
            payload = json.loads(raw_in.decode("utf-8", "replace"))
        except json.JSONDecodeError:
            payload = {}
    source = (payload.get("source") or payload.get("trigger") or "").strip().lower()
    compacted = source == "compact"
    if event in ("SessionStart", "PostCompact"):
        if consume_marker():
            compacted = True

    if event == "UserPromptSubmit":
        ctx = SHORT
        if compacted:
            ctx = compact_index()
    elif compacted:
        ctx = compact_index()
    else:
        ctx = elicit_b(source)

    out = {
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": ctx,
        }
    }
    raw = json.dumps(out, ensure_ascii=False).encode("utf-8")
    try:
        sys.stdout.buffer.write(raw)
    except Exception:
        sys.stdout.write(json.dumps(out, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
