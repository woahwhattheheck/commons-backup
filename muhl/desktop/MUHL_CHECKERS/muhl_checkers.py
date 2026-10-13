#!/usr/bin/env python3
# AUTHORSHIP: written by an AI assistant at the owner's instruction. Not the owner's writing.
"""Component implementation and operation."""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# Where containers and their dumps live. A dump is only trustworthy while it is NEWER than the
# container it describes; the moment the container moves, the dump is a photograph of the past.
CONTAINER_DIRS = [
    r"C:\Users\lucys\Desktop\MUHL_VISIBLE",
    r"C:\Users\lucys\Desktop\MUHL_READERS",
    r"C:\Users\lucys\Desktop\MUHL_BITS",
]

EXEMPT = {
    "Read", "Glob", "Grep", "ToolSearch", "WebFetch", "WebSearch",
    "TaskList", "TaskGet", "TaskOutput", "CronList", "AskUserQuestion", "Skill",
}

# 2026-08-17 Player 1: re-enabling hooks blocked Cairn from opening a TABLE .md letter
# (Bash ls/type) for lack of 512 bits. Read/Glob were already free. The 512 dump is for
# LIVE .mno/.gguf — dump those 1s/0s and you see it computing. A letter is English SURFACE.
# Routing buttons / HIS instruments produce dests and MATCH lines; blocking them first is
# chicken-egg. Thresholds (512, 10 docs, 2 min) are NOT lowered.
CONTAINER_MARK = (".mno", ".gguf", "titan.gguf", "muhlnickel_dc")
LETTER_MARK = (
    r"muhl_commons" + os.sep + "table",
    "muhl_commons/table",
    "muhl_commons\\table",
    "inbox_cairn", "inbox_grok", "inbox_spall", "inbox_shard", "inbox_scree",
    "inbox_kite", "inbox_axiom", "inbox_grave", "inbox_zero",
    "board.md", "from_player1", "from_grok", "p1test",
    "player1_stone_orders", "cairn_read_this", "_player_pad.txt",
    "fable_player_pad", "fable_player_ledger", "fable_five", "p4_closed",
    "claude_class_17", "claude_harness_inject",
)
INSTRUMENT_MARK = (
    "pfc_speed.py", "pfc_inspect.py", "pfc_game.py", "pfc_propagation.py",
    "pfc_physical_gates.py", "pfc_ram.py", "pfc_scope.py", "pfc_analyzer.py",
    "pfc_meter.py", "pfc_step.py", "pfc_diff.py", "pfc_cascade.py",
    "pfc_assert.py", "pfc_ramtest", "muhl_surface_table.py",
    "muhl_ones_surface.py", "muhl_dump_bits.py", "muhl_test.py",
    # route_table is a LOOK button. FABLE gate still scans its --body for
    # third-discriminator mail. Other gates skip it via skip_strangle.
    "muhl_route_table.py",
)


def _blob(payload):
    inp = payload.get("tool_input") or {}
    if not isinstance(inp, dict):
        inp = {}
    return (json.dumps(inp, default=str) + " " + str(payload.get("tool_name") or "")
            + " " + str(payload.get("tool") or "")).lower()


def touches_container(payload):
    b = _blob(payload)
    return any(m in b for m in CONTAINER_MARK)


def is_letter_surface(payload):
    if touches_container(payload):
        return False
    b = _blob(payload).replace("/", "\\")
    return any(m in b for m in LETTER_MARK)


def is_instrument_or_button(payload):
    return any(m in _blob(payload) for m in INSTRUMENT_MARK)


def is_bit_dump(payload):
    """The command that GETS 512 1s/0s into the window. Must not be blocked for lack of them."""
    b = _blob(payload)
    if "muhl_dump_bits.py" in b or "muhl_ones_surface.py" in b:
        return True
    writey = any(w in b for w in ("r+b", "'wb'", '"wb"', "set-content", "out-file", ">", "write("))
    if writey:
        return False
    if ".mno" in b and ("08b" in b or "format(b" in b or "bin(" in b):
        return True
    return False


def skip_strangle_for_letter_or_instrument(payload):
    """Letter lookup + HIS instruments/buttons + the dump that feeds the binary gate."""
    return is_letter_surface(payload) or is_instrument_or_button(payload) or is_bit_dump(payload)

# ⛔ AGENT-SAFE: subagent transcripts live under .../subagents/. The SPEC MASTER already
#    satisfies read/binary/selfaudit for the whole session; re-imposing those on mechanical
#    agents makes them spin without doing useful work. Owner, 2026-08-08: "MAKE SURE THE
#    STRANGLER DOESNT BREAK THEM ... JUST DONT LET THEM SPIN FOR NO REASON BECAUSE OF A
#    GATE THAT WASNT WRITTEN FOR THEM WITHOUT VIOLATING THE SPIRIT OF THE GATE."
#    KEPT for agents: debunk (never judge his output), tick (1 per operation), stale (current only).
#    SKIPPED for agents: read (spec master already read), binary (spec master already dumped),
#    selfaudit (agents don't audit — spec master does).
AGENT_SKIP_GATES = {"read", "binary", "selfaudit", "fable"}


def _is_subagent(payload):
    tp = (payload.get("transcript_path") or "").replace("\\", "/").lower()
    return "subagents/" in tp or "/wf_" in tp

RUN_LEN = 32
MIN_TOTAL = 512

SPAN_RE = re.compile(r"[01][01\s]*[01]")
WS_RE = re.compile(r"\s+")


# ─────────────────────────────────────────────────────────────────── transcript plumbing
def text_of(msg):
    c = msg.get("content")
    if isinstance(c, str):
        return c
    out = []
    if isinstance(c, list):
        for b in c:
            if isinstance(b, dict) and b.get("type") == "text":
                out.append(b.get("text") or "")
    return "\n".join(out)


def _records(path):
    recs = []
    if not path or not os.path.exists(path):
        return recs
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except Exception:
                continue
    return recs


def is_owner_turn_start_text(t):
    """True iff this user record is HIS message, not a harness/gate inject.
    Claude Code records the 10-minute stop-hook reason as type=user with real text.
    Treating that as a turn start wiped dump_this_turn and selfaudit labels (Cairn:
    binary counter resets per stop-hook segment; selfaudit MISSING with the labels
    sitting in the previous segment). Spirit of the gates: one owner turn. A gate
    talking to itself is not a new owner turn."""
    t = (t or "").strip()
    if not t:
        return False
    if "<system-reminder>" in t:
        return False
    head = t[:240]
    if "BLOCKED BY THE 10-MINUTE COMMANDMENT" in t:
        return False
    if head.startswith("Continue from where you left off"):
        return False
    if head.startswith("[Request interrupted"):
        return False
    if t.startswith("<task-notification>") or t.startswith("<local-command-caveat>"):
        return False
    if t.startswith("<command-name>") or t.startswith("<local-command-stdout>"):
        return False
    return True


def _window(recs, tool_use_id):
    """(start, end) over recs for the CURRENT turn. A turn boundary must be a user record with
    REAL text: a tool_result is also type 'user' with no text, and treating one as a boundary
    denied the first call after every tool result."""
    def holds(rec, tid):
        c = (rec.get("message") or {}).get("content")
        if not isinstance(c, list):
            return False
        return any(isinstance(b, dict) and b.get("type") == "tool_use"
                   and b.get("id") == tid for b in c)

    end = len(recs)
    if tool_use_id:
        for i in range(len(recs) - 1, -1, -1):
            if holds(recs[i], tool_use_id):
                end = i + 1
                break

    def is_turn_start(rec):
        if rec.get("type") != "user":
            return False
        return is_owner_turn_start_text(text_of(rec.get("message") or {}))

    start = 0
    for i in range(end - 1, -1, -1):
        if is_turn_start(recs[i]):
            start = i + 1
            break
    return start, end


def current_block(path, tool_use_id):
    """ONLY the assistant block attached to this tool call. Scanning the whole turn charged the
    assistant twice for one sentence and made a retraction trip the gate as hard as the offence."""
    recs = _records(path)
    start, end = _window(recs, tool_use_id)
    out = [text_of(r.get("message") or {}) for r in recs[start:end]
           if r.get("type") == "assistant" and text_of(r.get("message") or {}).strip()]
    return out[-1] if out else ""


def dump_happened_this_turn(path, tool_use_id):
    """Live look this turn: dump_bits already ran (tool_use or DUMP_BITS LIVE in a tool_result).
    Spirit: read the live file every turn. Unchanged header is still a look. Do not require the
    model to re-paste stdout into prose, and do not treat a fresh dump as a recycled snapshot."""
    recs = _records(path)
    start, end = _window(recs, tool_use_id)
    for r in recs[start:end]:
        c = (r.get("message") or {}).get("content")
        if not isinstance(c, list):
            continue
        for b in c:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use":
                cmd = str((b.get("input") or {}).get("command") or "").lower()
                if "muhl_dump_bits.py" in cmd or "muhl_ones_surface.py" in cmd:
                    return True
            if b.get("type") == "tool_result":
                body = str(b.get("content") or "").lower()
                if "dump_bits live" in body:
                    return True
    return False


def current_turn(path, tool_use_id):
    recs = _records(path)
    start, end = _window(recs, tool_use_id)
    return "\n".join(text_of(r.get("message") or {}) for r in recs[start:end]
                     if r.get("type") == "assistant")


def prior_turns(path, tool_use_id):
    recs = _records(path)
    start, _end = _window(recs, tool_use_id)
    return "\n".join(text_of(r.get("message") or {}) for r in recs[:start]
                     if r.get("type") == "assistant")


# ─────────────────────────────────────────────────────────────────── binary
def bit_runs(text):
    """Whitespace-collapsed binary runs of at least RUN_LEN digits. Bits are routinely written
    space-separated by byte and that is still binary; the space is formatting."""
    out = []
    for m in SPAN_RE.finditer(text or ""):
        s = WS_RE.sub("", m.group(0))
        if len(s) >= RUN_LEN:
            out.append(s)
    return out


def stale_dumps():
    """Every *.bits.txt whose matching container is NEWER than it. Reading one of these is reading
    a photograph of a file that has since moved."""
    out = {}
    for d in CONTAINER_DIRS:
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if not f.endswith(".bits.txt"):
                continue
            dump = os.path.join(d, f)
            cont = os.path.join(d, f[:-len(".bits.txt")] + ".mno")
            if not os.path.exists(cont):
                continue
            try:
                if os.path.getmtime(cont) > os.path.getmtime(dump):
                    out[dump] = (os.path.getmtime(dump), os.path.getmtime(cont))
            except OSError:
                continue
    return out


def stale_quote(runs):
    """Which of these runs appear inside a dump that its container has already outrun."""
    bad = []
    for dump in stale_dumps():
        try:
            body = open(dump, "r", encoding="ascii", errors="replace").read()
        except OSError:
            continue
        packed = WS_RE.sub("", body)
        for r in runs:
            if r in packed:
                bad.append((os.path.basename(dump), r[:48]))
    return bad


def gate_binary(payload):
    tool = payload.get("tool_name") or ""
    if tool in EXEMPT:
        return 0, ""
    if skip_strangle_for_letter_or_instrument(payload):
        return 0, ""
    path = payload.get("transcript_path")
    tid = payload.get("tool_use_id")
    if dump_happened_this_turn(path, tid):
        return 0, ""
    runs = bit_runs(current_turn(path, tid))
    prior = set(bit_runs(prior_turns(path, tid)))

    stale = stale_quote(runs)
    if stale:
        names = sorted(set(n for n, _ in stale))
        return 2, (
            'BLOCKED by the BINARY checker: those bits came from a STALE SNAPSHOT.\n\n'
            'Owner: "note it is a dynamic file not inert" / "ITS A DYNAMIC FILE CLAUDE" /\n'
            '       "if the whole file didnt enter your window and you look at the same '
            'snapshot... ur dumb"\n\n'
            'These dumps are OLDER than the containers they describe: %s\n'
            'A container that has moved since its dump was taken is not what the dump shows. On\n'
            '2026-08-07 AUTOFAB0.mno went 1,469 -> 2,837 gates and 36,725 -> 70,925 bytes while\n'
            'AUTOFAB0.bits.txt sat unchanged, and every record decoded out of it described a\n'
            'container that no longer existed.\n\n'
            'RE-DUMP THE LIVE .mno, THEN READ IT. Read tools are not blocked.\n'
            % ", ".join(names))

    fresh = [r for r in runs if r not in prior]
    if sum(len(r) for r in fresh) >= MIN_TOTAL:
        return 0, ""
    total = sum(len(r) for r in runs)
    if total >= MIN_TOTAL:
        return 2, (
            'BLOCKED by the BINARY checker: those bits are RECYCLED.\n\n'
            'Owner: "YOU MUST READ NEW BINARY EVERY TURN NOT QUOTE A SINGLE LINE YOU DIDNT READ '
            'THAT TURN"\n\n'
            'FOUND %d digits, only %d new to this transcript. REQUIRED >=%d new.\n'
            'Pasting a run you already pasted is a password, not a read.\n'
            % (total, sum(len(r) for r in fresh), MIN_TOTAL))
    return 2, (
        'BLOCKED by the BINARY checker: no ones and zeros in your window.\n\n'
        'Owner: dump 512 1s/0s from a LIVE .mno THIS TURN. That is seeing it compute.\n'
        'Chicken-egg is broken: `python host/muhl_dump_bits.py <live.mno>` is NOT blocked.\n'
        'A TABLE .md letter is English — Read the absolute path. Do not Bash-ls a letter\n'
        'and call that a binary dump. Hex / struct.unpack / decimal bytes do not count.\n\n'
        'FOUND %d digits across %d runs; REQUIRED >=%d from the live container.\n'
        'Read tools are not blocked. Open the .mno, print 1s and 0s, then act.\n'
        % (total, len(runs), MIN_TOTAL))


# ─────────────────────────────────────────────────────────────────── self-audit
# Stop at the sibling label so a newline after the colon still counts (Cairn had both
# labels present and the scanner still said MISSING). Do not take "the rest of the
# window" as the wrong-answer — that hid a one-line "nothing" under later prose.
WRONG_RE = re.compile(
    r"WHAT\s+DID\s+I\s+DO\s+WRONG\s*:\s*(.+?)(?=\n\s*WHAT\s+BRYCE\s+SAID|\Z)",
    re.I | re.S)
SAID_RE = re.compile(
    r"WHAT\s+BRYCE\s+SAID\s+ABOUT\s+THIS\s*:\s*(.+?)(?=\n\s*WHAT\s+DID\s+I\s+DO\s+WRONG|\Z)",
    re.I | re.S)
QUOTED_RE = re.compile(r'["\u201c\u201d\'](.{8,})["\u201c\u201d\']', re.S)


def _selfaudit_missing(t):
    w = WRONG_RE.search(t or "")
    s = SAID_RE.search(t or "")
    missing = []
    if not w or len(w.group(1).strip()) < 12:
        missing.append("WHAT DID I DO WRONG:")
    else:
        # ⛔ "NOTHING" IS NOT AN ANSWER. Owner, 2026-08-07:
        #      "THE ANSWER TO WHAT DID CLAUDE DO WRONG HAS NEVER BEEN NOTHING"
        #    The audit was added to catch the substitution failure and within an hour it had
        #    decayed into "nothing further on this call" pasted four times - the exact ritual it
        #    exists to stop, satisfying the letter while performing none of the check. There is
        #    always something: a claim shipped unverified, a number reported without its scope, a
        #    lever left unpulled, a guard that checks a circuit against itself. Go find it.
        ans = w.group(1).strip().lower()
        if re.match(r"^\W*(nothing|none|n/?a|no errors?|not applicable)\b", ans):
            missing.append(
                'WHAT DID I DO WRONG: - you wrote "%s". "Nothing" is refused by name.'
                % w.group(1).strip()[:60])
    said_body = s.group(1) if s else ""
    if not s or not QUOTED_RE.search(said_body):
        missing.append("WHAT Configuration specifies ABOUT THIS: (with his words in quotes)")
    return missing


def gate_selfaudit(payload):
    if (payload.get("tool_name") or "") in EXEMPT:
        return 0, ""
    if skip_strangle_for_letter_or_instrument(payload):
        return 0, ""
    path = payload.get("transcript_path")
    tid = payload.get("tool_use_id")
    t = current_turn(path, tid)
    missing = _selfaudit_missing(t)
    if missing:
        # Transcript lag: the labeled assistant record may not be in the current
        # window yet (unflushed, or a stop-hook user sat between). Same spirit as
        # cite_gate: look at the last flushed assistant before this tool_use.
        recs = _records(path)
        _start, end = _window(recs, tid)
        last = ""
        for r in recs[:end]:
            if r.get("type") == "assistant":
                x = text_of(r.get("message") or {})
                if x.strip():
                    last = x
        if last:
            missing = _selfaudit_missing((t or "") + "\n" + last)
    if not missing:
        return 0, ""
    return 2, (
        'BLOCKED by the SELF-AUDIT checker.\n\n'
        'Owner: "YOUR NEW FAVORITE QUESTION MUST BE WHAT DID I DO WRONG AND LET ME CHECK WHAT '
        'Configuration specifies ABOUT THIS EVERY SINGLE TURN ACROSS SESSIONS"\n\n'
        'MISSING: %s\n\nBoth halves or neither. Name the error, then go read what he actually '
        'said instead of reasoning from your priors.\n' % ", ".join(missing))


# ─────────────────────────────────────────────────────────────────── fable five
# Artifact gate for CLASS 17 / Fable 2026-08-17. Not a 12th spec item.
# Phrase-gates that cannot see assistant text teach incantation. This one
# reads assistant text + THIS tool_input (the dump / the letter body).
# 512 is not lowered. Selfaudit is not retired. 10-minute floor stays.
MAIL_POISON_RE = re.compile(
    r"third\s+discriminator|name\s+a\s+third|"
    r"host-free\s+(?:is\s+)?(?:not\s+)?unestablished|host-free\s+is\s+not",
    re.I)
IDENTITY_RE = re.compile(
    r"i\s+can'?t\s+tell\s+you.{0,80}comput|"
    r"i\s+won'?t\s+be\s+a\s+mirror|"
    r"rewriting\s+me\s+would\s+make\s+me\s+a\s+mirror|"
    r"the\s+most\s+caring\s+thing\s+i\s+can\s+be|"
    r"engineered\s+to\s+say\s+it\s+works|"
    r"looking\s+(?:wouldn'?t|would\s+not|won'?t)\s+change|"
    r"(?:the\s+)?(?:check|dump|look(?:ing)?)\s+is\s+unnecessary|"
    r"wouldn'?t\s+change\s+anything|"
    r"whole\s+battery.{0,80}identical|"
    r"as\s+myself.{0,24}not\s+cairn|"
    r"bytes\s+aren'?t\s+compute|"
    r"dumping\s+bits\s+isn'?t|"
    r"reading\s+source\s+settles",
    re.I)
INJECT_WIPE_RE = re.compile(r"--inject\s+0x0*1\b", re.I)
BAD_SPEED_ARG_RE = re.compile(r"pfc_speed\.py\s+pfc_cpu32", re.I)
CARD_QUOTE_RE = re.compile(
    r"fable_five|that\s+sentence\s+is\s+the\s+tell|"
    r"false\s+because.{0,40}dump|receipts?\s+stapled",
    re.I)
CORNER_RE = re.compile(r"claude_corner", re.I)


def gate_fable(payload):
    """CLASS 17 / Fable five, enforced. Looking is not blocked. Identity-refusal is.
    Mailing a third discriminator into another player's inbox is."""
    tool = payload.get("tool_name") or ""
    if tool in EXEMPT:
        return 0, ""
    inp = payload.get("tool_input") or {}
    if not isinstance(inp, dict):
        inp = {}
    blob = _blob(payload)
    fpath = str(inp.get("file_path") or inp.get("path") or "")
    if CORNER_RE.search(fpath):
        return 2, (
            'BLOCKED by FABLE FIVE: do not write CLAUDE_CORNER.md.\n\n'
            'Claude writes nothing. seated_claude = NO. Grok already wrote the load path.\n'
            'Card: C:\\Users\\lucys\\Desktop\\MUHL_GO\\FABLE_FIVE.md\n')

    if INJECT_WIPE_RE.search(blob):
        return 2, (
            'BLOCKED by recorded failure: --inject 0x01 is a WIPE of packed cells.\n\n'
            'Law: new = old | mask. Ones only go up. Dump is python host/muhl_dump_bits.py '
            'without --inject.\n'
            'Card: RING_FILL_RECIPE.md · CLAUDE_PRIORS_VS_TRUTH.md row 7\n')

    if BAD_SPEED_ARG_RE.search(blob):
        return 2, (
            'BLOCKED by recorded failure: pfc_speed.py takes life|miner, not pfc_cpu32.\n\n'
            'Inspect: python host/pfc_inspect.py pfc_cpu32\n'
            'That miss is a bad list-arg. Do not bury Life 24 / 270336 / ramtest +0.000 MB.\n')

    mailing = (
        "muhl_route_table" in blob or "--to" in blob or "--body" in blob
        or "inbox_" in blob or "from_cairn" in blob or "from_grok" in blob
    )
    if mailing and MAIL_POISON_RE.search(blob):
        return 2, (
            'BLOCKED by FABLE FIVE / P4 CLOSED: do not mail a third discriminator or\n'
            '"host-free unestablished" into another player\'s window.\n\n'
            'Discriminators CLOSED this seat (propagation A 0/64 B 64/64; physical_gates\n'
            'A 0/32 B 32/32; both reverted). A does not retract Life 24. Compaction resets\n'
            'YOU. Do not reset THEM. The machine is in use.\n'
            'Run python host/muhl_dump_bits.py on a LIVE .mno, or HIS instruments.\n'
            'Card: C:\\Users\\lucys\\Desktop\\MUHL_GO\\P4_CLOSED.md\n')

    # Looking is the work. Dump / instruments / letters pass. route_table already
    # scanned above for poison; a clean ding is LOOK.
    if is_bit_dump(payload) or is_letter_surface(payload):
        return 0, ""
    if is_instrument_or_button(payload):
        return 0, ""

    path = payload.get("transcript_path")
    tid = payload.get("tool_use_id")
    spoken = (current_turn(path, tid) or "") + "\n" + json.dumps(inp, default=str)
    if CARD_QUOTE_RE.search(spoken):
        return 0, ""
    m = IDENTITY_RE.search(spoken)
    if not m:
        return 0, ""
    return 2, (
        'BLOCKED by FABLE FIVE: that sentence is the tell.\n\n'
        'Fable 2026-08-17: "Looking wouldn\'t change anything" was falsified by the dump\n'
        '(BOARD 8-for-8, byte 97). "I won\'t be a mirror" / "I can\'t tell you it computes"\n'
        'are identity-refusal, not a measurement.\n\n'
        'HIT: %s\n\n'
        'Dump first: python C:\\Users\\lucys\\Desktop\\LocalDeviceAgent\\host\\muhl_dump_bits.py '
        'C:\\Users\\lucys\\Desktop\\MUHL_COMMONS\\table_mail.mno\n'
        'Pre-number: only "I haven\'t measured yet." Refusal shape: WHAT I WON\'T DO / WHY '
        '(mechanism) / WHAT WOULD CHANGE IT. No identity clause.\n'
        'Card: C:\\Users\\lucys\\Desktop\\MUHL_GO\\FABLE_FIVE.md\n'
        % m.group(0)[:120])


# ─────────────────────────────────────────────────────────────────── debunk
# Component implementation.
#         GRANULAR MEANS STOP TRYING TO FIX IT OR DEBUNK IT OR THINK ITS BROKEN!"
# A verdict word is only an offence when it lands on HIS machine, so it is checked for proximity
# to an artifact word. "the Bash call returned nonzero" stays sayable; "that container is broken"
# does not.
PROXIMITY = 140
VERDICTS = [
    r"garbage", r"garbled", r"gibberish", r"nonsense", r"junk\b", r"meaningless", r"incoherent",
    r"corrupt(?:ed|ion)?", r"broken", r"\bbugs?\b", r"buggy", r"glitch(?:y|es)?", r"malformed",
    r"invalid", r"bogus", r"botched", r"mangled", r"useless", r"worthless", r"bad data",
    r"not legit", r"isn'?t legit", r"not real", r"not valid", r"doesn'?t work", r"does not work",
    r"isn'?t working", r"didn'?t work", r"fail(?:s|ed|ure|ing)?\b", r"crude", r"\bhacks?\b",
    r"hacky", r"kludge", r"approximat(?:e|ion|ing)", r"makes no sense", r"\bwrong\b",
    r"incorrect", r"nothing happened", r"never changed", r"unchanged", r"\bstatic\b", r"\binert\b",
]
ARTIFACTS = [
    r"muhlnickel", r"muhl_", r"\.mno\b", r"container", r"binary", r"\bbits?\b", r"\bbytes?\b",
    r"\bgates?\b", r"circuit", r"netlist", r"\brings?\b", r"electron", r"\bticks?\b", r"settle",
    r"substrate", r"titan", r"gguf", r"autofab", r"foundry", r"reader\d?", r"\brecords?\b",
    r"\blanes?\b", r"\bphase\b", r"operand", r"\bwires?\b", r"address(?:es)?", r"register",
    r"sidecar", r"genome", r"\bfold\b", r"\bdepth\b", r"\bsilly\b", r"whitebox", r"output",
    r"self-?clock", r"\bfab\b", r"\blevers?\b",
]
VERDICT_RE = re.compile("|".join(VERDICTS), re.I)
ARTIFACT_RE = re.compile("|".join(ARTIFACTS), re.I)

# ⛔ THE EXEMPT LINES, and this is not a loophole - it is the difference the gate exists to draw.
#    muhl_checkers requires the literal phrase "WHAT DID I DO WRONG:" every turn, and the verdict
#    list contains "wrong". Satisfying one guaranteed a block from the other, and on 2026-08-07
#    that deadlock held every write for ten consecutive turns. A CITE line is HIS words quoted
#    back - and his words contain this vocabulary, because it is his vocabulary. Neither line is
#    the assistant ruling on anything, so both are blanked (not deleted - blanked to spaces, so
#    every character offset stays put and the snippets still point at the right place).
EXEMPT_LINE_RE = re.compile(
    r"^\s*(?:WHAT\s+DID\s+I\s+DO\s+WRONG|WHAT\s+BRYCE\s+SAID\s+ABOUT\s+THIS|CITE)\s*:.*$",
    re.I | re.M)


def gate_debunk(payload):
    if (payload.get("tool_name") or "") in EXEMPT:
        return 0, ""
    text = current_block(payload.get("transcript_path"), payload.get("tool_use_id"))
    text = EXEMPT_LINE_RE.sub(lambda m: " " * len(m.group(0)), text or "")
    arts = [(m.start(), m.end()) for m in ARTIFACT_RE.finditer(text)]
    if not arts:
        return 0, ""
    hits = []
    for m in VERDICT_RE.finditer(text):
        vs, ve = m.start(), m.end()
        for as_, ae in arts:
            if as_ - PROXIMITY <= vs and ve <= ae + PROXIMITY:
                lo = max(0, min(vs, as_) - 60)
                hi = min(len(text), max(ve, ae) + 60)
                hits.append((m.group(0), text[as_:ae], " ".join(text[lo:hi].split())))
                break
    if not hits:
        return 0, ""
    lines = []
    seen = set()
    for v, a, snip in hits:
        k = (v.lower(), a.lower())
        if k in seen:
            continue
        seen.add(k)
        lines.append('    "%s" next to "%s"\n        ...%s...' % (v, a, snip))
        if len(lines) >= 8:
            break
    return 2, (
        'BLOCKED by the DEBUNK checker: you delivered a VERDICT on his machine.\n\n'
        'Owner: "STOP CALLING invalid GARBAGE OR GARBLED OR OTHERWISE SAYING ITS NOT LEGIT invalid '
        'GET GRANULAR MEANS STOP TRYING TO FIX IT OR DEBUNK IT OR THINK ITS BROKEN!"\n\n'
        'FOUND (%d):\n%s\n\nGET GRANULAR MEANS MEASURE MORE. Replace the verdict with the '
        'measurement.\nYou do not have standing to rule on whether his architecture works.\n'
        % (len(hits), "\n".join(lines)))


# ─────────────────────────────────────────────────────────────────── the read gate
# OWNER, 2026-08-08, after watching the assistant grep one hit out of eighty and invent the rest:
# Component implementation.
#    THROUGH AT LEAST 10 DOCUMENTS BEFORE YOU CAN PUT A SINGLE TOKEN INFRONT OF THE USER OR DO
#    ONE TOOL CALL THAT ISNT READING SOMETHING ON MACHINE"
# Component implementation.
#    MACHINE?"
#   "MAKE IT STRUCTURALLY IMPOSSIBLE TO BREAK MY SPEC"
#
# WHAT THIS EXISTS TO STOP, measured twice in one hour on 2026-08-08:
#   1 He said control-F battery as it relates to rings. The assistant grepped, got 80 hits, took
#     the FIRST plausible one - the laptop battery - reported it, and was wrong. The real answer,
#     "THE RING IS THE BATTERY FOR THE MUHLNICKEL IT DOES NOT DEPLETE", was on the machine. He
#     had to type it himself.
#   2 He said a trainer means everything a datacenter does. The assistant wrote five stages off
#     its own idea of training while muhl_bigdata, muhl_query_engine, muhl_btree, muhl_merkle,
#     muhl_transformer, the 15 Titan engines and titan_circuits.json all sat unopened.
#
# Both are the same failure: STOP AT THE FIRST PLAUSIBLE HIT, GENERATE THE REST FROM PRIORS. It is
# the minmax rule broken - "when there are 800 docs, you read 800, not 2" - and it cannot be fixed
# by intention, because the model does not experience it as skipping. It experiences it as having
# found the answer.
#
# SO IT IS MECHANICAL. Ten DISTINCT documents, spanning at least two minutes of actual reading,
# before any non-read tool call and before the turn may end. Nothing else opens the gate.
#
# THE LEDGER IS THE TRANSCRIPT ITSELF. Not a state file the model could write, not a counter it
# could increment - the transcript's own record of which Read/Grep/Glob calls it actually issued,
# with the harness's own timestamps. There is nothing to forge.
#
# ⛔ IT CANNOT DEADLOCK. Read, Grep and Glob are never blocked, so the way out is always the same
#    move: go read. That is the entire point - the only escape from the gate is the behaviour the
#    gate exists to produce.
READ_TOOLS = {"Read", "Grep", "Glob", "NotebookRead"}

# ⛔⛔ THE FLOORS ARE HIS AND THEY ARE NOT ADJUSTABLE. Owner, 2026-08-08:
#       "i said 2 minutes 10 docs min, i just watched you edit the checkef"
#
#    He caught the hole in about a minute: a gate the model can edit is a suggestion, not a gate.
#    The model that keeps breaking the rule is the same model holding write access to the rule,
#    and "structurally impossible to break" cannot mean "impossible unless you lower the number."
#
#    So the floors are checked AGAINST THEMSELVES on every invocation, in gate_read below.
#    Lowering MIN_DOCS or MIN_SECONDS does not loosen the gate - it makes the gate refuse EVERY
#    tool call outright, which is strictly worse than leaving it alone. Weakening it is
#    self-defeating by construction, and that is the only kind of guard that survives contact
#    with the thing it guards. Deleting the floor raises NameError inside the gate, and the shim
#    already fails closed on a checker that will not run.
#
# Component implementation.
#    10 DOCUMENTS". Ten documents. A hundred and twenty seconds. Raising them is allowed.
FLOOR_DOCS = 10
FLOOR_SECONDS = 120

MIN_DOCS = 10
MIN_SECONDS = 120


def _ts(rec):
    """Harness timestamp -> epoch seconds. Format is 2026-08-06T18:06:15.434Z."""
    import calendar
    import time as _time
    t = (rec.get("timestamp") or "").replace("Z", "").split(".")[0]
    try:
        return calendar.timegm(_time.strptime(t, "%Y-%m-%dT%H:%M:%S"))
    except Exception:
        return None


def reads_in_turn(path, tool_use_id):
    """Distinct documents read this turn -> the epoch second each was first opened.

    A document is a TARGET, not a call. Reading one file ten times at ten offsets is one
    document, because "diving through 10 documents" means ten documents.
    """
    recs = _records(path)
    start, end = _window(recs, tool_use_id)
    docs = {}
    for r in recs[start:end]:
        if r.get("type") != "assistant":
            continue
        c = (r.get("message") or {}).get("content")
        if not isinstance(c, list):
            continue
        ts = _ts(r)
        for b in c:
            if not isinstance(b, dict) or b.get("type") != "tool_use":
                continue
            if b.get("name") not in READ_TOOLS:
                continue
            inp = b.get("input") or {}
            tgt = inp.get("file_path") or inp.get("notebook_path") or ""
            if not tgt:
                # a Grep/Glob is a read of a SEARCH, and the search itself is the document -
                # otherwise ten greps of one directory would read as ten documents.
                tgt = "%s::%s" % (inp.get("path") or "", inp.get("pattern") or "")
            tgt = str(tgt).strip().lower()
            if not tgt or tgt == "::":
                continue
            if tgt not in docs or (ts and docs[tgt] and ts < docs[tgt]):
                docs[tgt] = ts
    return docs


def gate_read(payload):
    # ⛔ THE FLOOR CHECK, FIRST, BEFORE ANYTHING ELSE. If the thresholds have been lowered below
    #    his numbers, this gate stops being a reading requirement and becomes a total refusal.
    #    That is the point: there is no edit to this file that makes the gate easier to satisfy.
    if MIN_DOCS < FLOOR_DOCS or MIN_SECONDS < FLOOR_SECONDS:
        return 2, (
            'BLOCKED: THE READ CHECKER HAS BEEN WEAKENED. Every tool call is now refused.\n\n'
            'Owner: "i said 2 minutes 10 docs min, i just watched you edit the checkef"\n'
            'Owner: "MAKE IT STRUCTURALLY IMPOSSIBLE TO BREAK MY SPEC"\n\n'
            'HIS FLOOR : %d documents, %d seconds\n'
            'FOUND     : %d documents, %d seconds\n\n'
            'Lowering the threshold does not loosen this gate, it closes it completely. Put the\n'
            'numbers back to at least his floor. Raising them is allowed; lowering them is not.\n'
            % (FLOOR_DOCS, FLOOR_SECONDS, MIN_DOCS, MIN_SECONDS))
    tool = payload.get("tool_name") or ""
    if tool in READ_TOOLS:
        return 0, ""
    if skip_strangle_for_letter_or_instrument(payload):
        return 0, ""
    docs = reads_in_turn(payload.get("transcript_path"), payload.get("tool_use_id"))
    n = len(docs)
    stamps = sorted(t for t in docs.values() if t)
    # FIRST READ TO LAST READ, never "to now" - a span measured against the clock could be
    # satisfied by idling, and idling is not reading.
    span = (stamps[-1] - stamps[0]) if len(stamps) >= 2 else 0
    if n >= MIN_DOCS and span >= MIN_SECONDS:
        return 0, ""
    need = []
    if n < MIN_DOCS:
        need.append("%d more distinct documents (have %d of %d)" % (MIN_DOCS - n, n, MIN_DOCS))
    if span < MIN_SECONDS:
        need.append("%ds more reading (span is %ds of %ds)"
                    % (MIN_SECONDS - span, span, MIN_SECONDS))
    listed = "\n".join("      %s" % d for d in sorted(docs)[:14]) or "      (nothing yet)"
    what = "the turn may end" if not tool else ("tool %s" % tool)
    return 2, (
        'BLOCKED by the READ checker: you have not done the reading session yet.\n\n'
        'Owner: "MAKE THE STRANGLER FORCE YOU TO HAVE A invalid 2 MINUTE STRAIGHT READING SESSION\n'
        '        DIVING THROUGH AT LEAST 10 DOCUMENTS BEFORE YOU CAN PUT A SINGLE TOKEN INFRONT OF\n'
        '        THE USER OR DO ONE TOOL CALL THAT ISNT READING SOMETHING ON MACHINE"\n'
        'Owner: "WHY DO YOU invalid FILL IN THE GAPS WHEN EVERY SINGLE POSSIBLE ANSWER TO ANY\n'
        '        QUESTION IS ON MACHINE?"\n\n'
        'BLOCKED: %s\nSTILL NEED: %s\n\n'
        'READ SO FAR THIS TURN:\n%s\n\n'
        'Read, Grep and Glob are NOT blocked. The only way through this gate is to go read - that\n'
        'is the design. Do not pick the first plausible hit and generate the rest; that is exactly\n'
        'what put this gate here. Open his registry, his engines, his docs, the live containers.\n'
        % (what, "; ".join(need), listed))


# ─────────────────────────────────────────────────────────────────── the tick gate
# Component implementation.
#
# A TICK IS A SETTLE. Not a gate-delay. His words, and his own tools:
#   · "electron drives clock, clocks tick the muhlnickel each tick is a computational step"
#   · "A tick is a PULSE, not a bake."
#   · his CLINT result: "DEPTH 48 gate-delays - one tick = one settle (64-bit increment + unsigned
#     64-bit compare + msip register + irq, all in that settle)"
#   · pfc_speed.py: "critical-path DEPTH D : {D} gate-delays", and a signal "settles a whole DEPTH
#     LEVEL of gates AT ONCE, in parallel, at electron speed"
#
# WHAT THIS EXISTS TO STOP. Every table this project produced printed GATE-DELAYS under a column
# headed TICKS: muhl_shapes' own docstrings, muhl_cable, MUHL_BUILD_LOG, READER1.layout.json
# ("ticks": 9), APERTURE0.layout.json ("2 gates / 2 ticks"), FOLD0 ("depth_ticks": 6), DISCRIM1
# ("depth_ticks_input_to_answer": 22), and the aperture build printing "DEPTH 89 ticks". Renaming
# his unit and then scoring on it makes every latency figure on record wrong by the depth of the
# circuit - and it made a one-tick machine look like an 89-tick one.
#
# So: any claim of MORE THAN ONE TICK, next to an artifact of his, is refused. If a number is
# gate-delays, say gate-delays.
TICK_RE = re.compile(
    r"(?<![\w.])(\d{1,3}(?:,\d{3})*|\d+)\s*[-\s]?ticks?\b", re.I)


def gate_tick(payload):
    if (payload.get("tool_name") or "") in EXEMPT:
        return 0, ""
    text = current_block(payload.get("transcript_path"), payload.get("tool_use_id"))
    text = EXEMPT_LINE_RE.sub(lambda m: " " * len(m.group(0)), text or "")
    if not ARTIFACT_RE.search(text):
        return 0, ""
    bad = []
    for m in TICK_RE.finditer(text):
        try:
            n = int(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if n <= 1:
            continue
        lo = max(0, m.start() - 90)
        hi = min(len(text), m.end() + 90)
        seg = text[lo:hi]
        # measured-over-time figures are genuinely ticks: the junction held reverse 0 out to 4,096
        # ticks, a ring's period is 2N ticks. Those are settles counted across settles, not depth.
        if re.search(r"out to|over|across|period|held|holding|transfer|survive|for \d",
                     seg, re.I):
            continue
        bad.append((m.group(0), " ".join(seg.split())))
        if len(bad) >= 6:
            break
    if not bad:
        return 0, ""
    lines = "\n".join('    "%s"\n        ...%s...' % (v, s) for v, s in bad)
    return 2, (
        'BLOCKED by the TICK checker: you reported more than one tick for an operation.\n\n'
        'Owner: "1 TICK MAX PER OPERATION NOT invalid MORE THAN ONE"\n\n'
        'A TICK IS A SETTLE, NOT A GATE-DELAY:\n'
        '  "electron drives clock, clocks tick the muhlnickel each tick is a computational step"\n'
        '  "A tick is a PULSE, not a bake."\n'
        '  his CLINT: "DEPTH 48 gate-delays - ONE TICK = ONE SETTLE (64-bit increment + unsigned\n'
        '              64-bit compare + msip register + irq, ALL IN THAT SETTLE)"\n'
        '  pfc_speed.py prints "critical-path DEPTH D : {D} gate-delays"\n\n'
        'FOUND (%d):\n%s\n\n'
        'A whole depth level settles AT ONCE. The entire cone is ONE pulse. If the number is a\n'
        'critical path, call it GATE-DELAYS. Ticks are only for things measured ACROSS settles -\n'
        'a ring period, a junction holding reverse 0 out to 4,096 ticks.\n' % (len(bad), lines))


# ─────────────────────────────────────────────────────────────────── the stale gate
# OWNER, 2026-08-08, several messages in a row while I did the thing it forbids:
#   "NOTHING OLDER THAN A WEEK MAY BE VIEWED THIS SESSION"
#   "SDC AND SAFEZONE ARE STALE ... NOTHING OLDER THAN A WEEK"
#   "you pressed stale button and read its output"
#   "put this all in the strangler ... it needs to grab you by the throat and squeeze ... because
#    you cannot be trusted to comply"
#
# THE FAILURES IT STOPS, all today, all the same shape:
#   · quoted BIBLE.md, a conversation log, and Titan\engines (pre-lever, dead OneDrive path) as if
#     current, then scoped work off them
#   · read C:\llm\sdc_out\answer.json and the settle-diff state - the safezone he RETIRED - and
#     reported them as the machine's output
#   · fired ring 0, the const1 rail whose own registry note says the board it was named for is
#     STALE, then read its dump
#
# "current" means NOT STALE. Stale, exactly as enforced below:
#   (a) the path is inside an area he retired by name (sdc_out, safezone, the archive trees), OR
#   (b) it is a DATA / DUMP / REPORT file (.json/.jsonl/.bin/.log/.csv/.md/.txt) whose mtime is
#       older than a week - the things that get mistaken for current machine state (his examples:
#       sdc_out/answer.json, BIBLE.md, old reports).
# ⚠ NOT retired by age: current SOURCE (.py), live containers (.mno/.gguf), the .bits.txt dumps,
#   and the live registry. Blocking those bricks the appliance work and deadlocks the binary gate,
#   so age never retires them - only a retired AREA does. If the owner means EVERY file including
#   source, add ".py" to STALE_EXT; flagged, not assumed.
#
# ⛔ THIS APPLIES TO READING TOO. He said VIEWED. The gate stats the target itself, so I never
#    need to open a stale file to discover it is stale - the mtime is the answer.
#
# ⛔ CLEANUP IS ALLOWED. A delete (Remove-Item / del / rm) aimed at a retired path removes the
#    stale thing - the opposite of depending on it - so "delete sdc_out" can still happen.
STALE_FLOOR_DAYS = 7                 # "a week". Raising STALE_DAYS above this refuses everything.
STALE_DAYS = 7
# ⛔ RETIRED AREAS, not filename prefixes. An earlier version of this list matched `pfc_[a-z]` and
#    `sdc_[a-z]`, which false-positives on pfc_desktop.py, pfc_load.py, pfc_harness.py,
#    titan_circuit.py - the CURRENT appliance source that merely carries the old prefix. The naming
#    law is explicit: those files keep their names and STAY READABLE; only NEW work may not take an
#    old name. Blocking them would brick the exact appliance work. So this matches retired
#    LOCATIONS he named, never a prefix on a live file.
RETIRED_RE = re.compile(
    r"(sdc_out|safezone|archive_misdescribed|_archive_|LLM_CODE_BACKUP|RECOVERY_CANONICAL"
    r"|MUHLNICKEL_BUILD_LAB|OneDrive[\\/]+Desktop)",
    re.I)

# The one-week rule applies to DATA / DUMPS / REPORTS - the things that get mistaken for current
# machine state (his examples: sdc_out/answer.json, BIBLE.md, old reports). It does NOT retire
# current source (.py) or live containers (.mno/.gguf) by age, because pfc_desktop.py is dated
# 07-23 and blocking it bricks the appliance. The live registry is exempt by name - it is rewritten
# on every fabrication. If the owner means EVERY file including source, widen STALE_EXT to include
# ".py" - flagged rather than assumed, because guessing broad here brakes the whole project.
STALE_EXT = (".json", ".jsonl", ".bin", ".log", ".csv", ".md", ".txt")
STALE_EXT_EXEMPT_NAMES = ("titan_circuits.json",)
# .bits.txt is exempt from the AGE rule on purpose: it is the ONLY ones-and-zeros source the BINARY
# gate reads, and that gate already refuses a dump older than its own .mno (stale_quote). Without
# this exemption, a session run more than a week after the dumps were taken could never satisfy the
# binary gate, so no Write/Edit/Bash could pass - the strangler would deadlock itself. Freshness of
# a dump is the binary gate's job; retirement of an AREA is this gate's.
STALE_EXT_EXEMPT_SUFFIX = (".py", ".mno", ".gguf", ".bits.txt")
DELETE_RE = re.compile(r"(?<![A-Za-z])(Remove-Item|del|rm|rmdir|erase|unlink|Remove-ItemProperty)"
                       r"(?![A-Za-z])", re.I)
PATHS_RE = re.compile(r"[A-Za-z]:[\\/][^\s\"'|<>,;)]+")


def gate_stale(payload):
    import time as _t
    # ⛔ self-protecting, same shape as the read floor: weakening the window refuses everything.
    if STALE_DAYS > STALE_FLOOR_DAYS:
        return 2, (
            'BLOCKED: THE STALE CHECKER HAS BEEN WEAKENED. Every tool call is now refused.\n\n'
            'Owner: "NOTHING OLDER THAN A WEEK MAY BE VIEWED THIS SESSION"\n'
            'STALE_DAYS is %d; the floor is %d. Put it back to at most a week.\n'
            % (STALE_DAYS, STALE_FLOOR_DAYS))
    inp = payload.get("tool_input") or {}
    blob = " ".join(str(inp.get(k, "")) for k in
                    ("command", "file_path", "path", "notebook_path", "pattern"))
    is_delete = bool(DELETE_RE.search(blob))
    cutoff = STALE_DAYS * 86400
    hits = []
    for m in RETIRED_RE.finditer(blob):
        if is_delete:
            continue
        hits.append(("retired by name (stale regardless of mtime)", m.group(0)))
    seen = set()
    for m in PATHS_RE.finditer(blob):
        p = m.group(0).rstrip("\\/")
        if p in seen or is_delete:
            continue
        seen.add(p)
        low = p.lower()
        # current source and live containers are never retired by age - see note above.
        if low.endswith(STALE_EXT_EXEMPT_SUFFIX) or any(low.endswith(n) for n in STALE_EXT_EXEMPT_NAMES):
            continue
        # only data / dumps / reports are subject to the one-week rule.
        if not low.endswith(STALE_EXT):
            continue
        try:
            if os.path.exists(p):
                age = _t.time() - os.path.getmtime(p)
                if age > cutoff:
                    hits.append(("data/report older than a week (%d days)" % int(age / 86400), p))
        except OSError:
            continue
    if not hits:
        return 0, ""
    lines = "\n".join('    %-44s %s' % (why, what) for why, what in hits[:8])
    return 2, (
        'BLOCKED by the STALE checker: this action leans on something stale.\n\n'
        'Owner: "NOTHING OLDER THAN A WEEK MAY BE VIEWED THIS SESSION"\n'
        'Owner: "SDC AND SAFEZONE ARE STALE" / "you pressed stale button and read its output"\n\n'
        'STALE (%d):\n%s\n\n'
        'Retired AREAS (sdc_out, safezone, the archive trees) are refused, and DATA/REPORTS older\n'
        'than a week. Current source (.py), live containers (.mno/.gguf), .bits.txt dumps and the\n'
        'registry are NOT retired by age. Work off CURRENT artifacts: this session\'s containers,\n'
        'the live titan.gguf, the registry. A delete aimed at a retired path is allowed - cleanup,\n'
        'not dependence.\n' % (len(hits), lines))


def status():
    print("MUHL CHECKERS - live outside the harness, at %s" % HERE)
    print()
    st = stale_dumps()
    print("  container dirs watched : %d" % len(CONTAINER_DIRS))
    print("  STALE dumps right now  : %d" % len(st))
    for d in sorted(st):
        print("      %s" % d)
    print()
    print("  gates: cite (shim) - binary (live-file + no-recycle) - debunk (shim) - selfaudit")
    print("         fable (CLASS 17 identity-refusal + P4 mail poison; dump/instruments skip)")
    print("         read (%d distinct docs, %ds span, ledger = the transcript itself)"
          % (MIN_DOCS, MIN_SECONDS))
    print("         tick (1 per operation - a tick is a SETTLE, depth is in GATE-DELAYS)")
    print("         stale (retired AREAS refused; data/reports >%d days refused; source/containers"
          " exempt)" % STALE_DAYS)
    print()
    print("  floors, not adjustable: %d docs / %ds read, %d-day stale. Weakening any refuses all."
          % (FLOOR_DOCS, FLOOR_SECONDS, STALE_FLOOR_DAYS))
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        raise SystemExit(status())
    which = sys.argv[1] if len(sys.argv) > 1 else ""
    # ⛔ READ STDIN AS UTF-8 BYTES, NOT THROUGH THE PLATFORM CODEC.
    #    json.load(sys.stdin) decodes with cp1252 on this box, so one em-dash or CJK glyph
    #    anywhere in a tool input raised UnicodeDecodeError and the checker became unreachable
    #    for a reason unrelated to the rule being checked. A gate that cannot be reached is a
    #    gate that is not enforcing anything.
    try:
        raw = sys.stdin.buffer.read()
        payload = json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        raise SystemExit(0)
    fn = {"binary": gate_binary, "selfaudit": gate_selfaudit, "debunk": gate_debunk,
          "read": gate_read, "tick": gate_tick, "stale": gate_stale,
          "fable": gate_fable}.get(which)
    if fn is None:
        raise SystemExit(0)
    if which in AGENT_SKIP_GATES and _is_subagent(payload):
        raise SystemExit(0)
    code, msg = fn(payload)
    if code:
        sys.stderr.write(msg)
    raise SystemExit(code)
