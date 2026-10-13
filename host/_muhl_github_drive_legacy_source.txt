#!/usr/bin/env python3
# host/muhl_github_drive.py
# One-shot: pull COMMANDS from kite-mouth-help or the local mirror, act, write
# receipts, die. GitHub is the board + command tickets. The PC files compute.
# Not a watcher. Not an idle loop. Never --inject 0x01. Never smash commons.mno.
#   python host/muhl_github_drive.py --go

from __future__ import annotations

import json, os, re, subprocess, sys, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import muhl_commons_mouth as mouth
import muhl_mail_store as mstore
import muhl_pub_commons as pub
import muhl_route_table as route
import muhl_surface_table as surface

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE. Law is new=old|mask.")
    raise SystemExit(2)

ROOT = r"C:\Users\lucys\Desktop\MUHL_COMMONS"
CMD_ROOT = os.path.join(ROOT, "COMMANDS")
RECEIPT_ROOT = os.path.join(CMD_ROOT, "RECEIPTS")
PUBLIC = os.path.join(ROOT, "PUBLIC")
REPO = "woahwhattheheck/kite-mouth-help"
API = "https://api.github.com/repos/" + REPO + "/contents/"
BLOB = "https://github.com/" + REPO + "/blob/main"
ID_OK = re.compile(r"^[A-Za-z0-9._-]{8,80}$")
SKIP_NAMES = {
    "how.txt", "inbox.txt", "readme.txt",
    "template_say.txt", "template_surface.txt",
}
PLAYERS = mstore.PLAYERS
REFUSE_PURPOSE = frozenset({"VERIFY", "PROOF", "TEST", "BATTERY", "PROVE"})
LIVE_PATHS = {
    os.path.normcase(os.path.abspath(p)): p
    for p in (
        r"C:\Users\lucys\Desktop\MUHL_COMMONS\commons.mno",
        r"C:\Users\lucys\Desktop\MUHL_COMMONS\table_mail.mno",
        r"C:\Users\lucys\Desktop\MUHL_GRAVE\grave_cenotaph_v1.mno",
        r"C:\Users\lucys\Desktop\MUHL_TENANCY\muhl_tenancy.mno",
        r"C:\Users\lucys\Desktop\MUHL_FOUNDRY\foundry_acre.mno",
        r"C:\Users\lucys\Desktop\WEATHER\axiom_probe_pop.mno",
        r"C:\Users\lucys\Desktop\WEATHER\weather_v2_denoms.mno",
    )
}
LDA_HOST = r"C:\Users\lucys\Desktop\LocalDeviceAgent\host"


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text if text.endswith("\n") else text + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _gh_get(path, token=None):
    url = API + path.replace("\\", "/") + "?ref=main"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "muhl-github-drive",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _decode_content(obj):
    import base64
    enc = obj.get("encoding")
    raw = obj.get("content") or ""
    if enc == "base64":
        return base64.b64decode(raw).decode("utf-8", "replace")
    return raw


def parse_command(text, source):
    text = (text or "").replace("\r\n", "\n")
    if text.lstrip().startswith("{"):
        obj = json.loads(text)
        obj["_source"] = source
        return obj
    head, sep, tail = text.partition("\n---\n")
    fields = {}
    for ln in head.splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        if "=" not in s:
            continue
        k, v = s.split("=", 1)
        fields[k.strip().lower()] = v.strip()
    if sep:
        fields["body"] = tail
    elif "body" not in fields:
        fields["body"] = ""
    fields["_source"] = source
    return fields


def load_local_commands():
    out = {}
    if not os.path.isdir(CMD_ROOT):
        return out
    for fn in sorted(os.listdir(CMD_ROOT)):
        low = fn.lower()
        if low in SKIP_NAMES or low.startswith("template"):
            continue
        path = os.path.join(CMD_ROOT, fn)
        if not os.path.isfile(path):
            continue
        if not (low.endswith(".txt") or low.endswith(".json")):
            continue
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        cmd = parse_command(text, "local:" + path)
        mid = (cmd.get("id") or os.path.splitext(fn)[0]).strip()
        cmd["id"] = mid
        out[mid] = cmd
    jsonl = os.path.join(CMD_ROOT, "say.jsonl")
    if os.path.isfile(jsonl):
        with open(jsonl, "r", encoding="utf-8") as f:
            for i, ln in enumerate(f, 1):
                ln = ln.strip()
                if not ln or ln.startswith("#"):
                    continue
                obj = json.loads(ln)
                obj["_source"] = "local:%s:%d" % (jsonl, i)
                mid = (obj.get("id") or "").strip()
                if mid:
                    out[mid] = obj
    return out


def load_github_commands(token=None):
    out = {}
    try:
        listing = _gh_get("COMMANDS", token)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return out
        print("GITHUB list COMMANDS HTTP", e.code)
        return out
    except OSError as e:
        print("GITHUB list COMMANDS fail", type(e).__name__)
        return out
    if not isinstance(listing, list):
        return out
    for item in listing:
        name = (item.get("name") or "")
        low = name.lower()
        if item.get("type") != "file":
            continue
        if low in SKIP_NAMES or low.startswith("template"):
            continue
        if not (low.endswith(".txt") or low.endswith(".json") or low.endswith(".jsonl")):
            continue
        path = item.get("path") or ("COMMANDS/" + name)
        try:
            obj = _gh_get(path, token)
        except (urllib.error.HTTPError, OSError):
            continue
        text = _decode_content(obj)
        if low.endswith(".jsonl"):
            for i, ln in enumerate(text.splitlines(), 1):
                ln = ln.strip()
                if not ln or ln.startswith("#"):
                    continue
                rec = json.loads(ln)
                rec["_source"] = "github:%s:%d" % (path, i)
                mid = (rec.get("id") or "").strip()
                if mid:
                    out[mid] = rec
            continue
        cmd = parse_command(text, "github:" + path)
        mid = (cmd.get("id") or os.path.splitext(name)[0]).strip()
        cmd["id"] = mid
        out[mid] = cmd
    return out


def receipt_path(mid):
    return os.path.join(RECEIPT_ROOT, mid + ".txt")


def load_receipt(mid):
    path = receipt_path(mid)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_receipt(mid, text):
    _write(receipt_path(mid), text)
    pub_path = os.path.join(PUBLIC, "COMMANDS", "RECEIPTS", mid + ".txt")
    _write(pub_path, text)


def purpose_refused(mid, cmd):
    purpose = (cmd.get("purpose") or "USE").strip().upper()
    if purpose not in REFUSE_PURPOSE:
        return None
    rec = (
        "REFUSE id=%s purpose=%s. Verification is not a panel verb. "
        "USE or BUILD only. MATCH is held.\n" % (mid, purpose)
    )
    write_receipt(mid, rec)
    return rec


def resolve_live(cmd):
    raw = (cmd.get("path") or "").strip()
    if not raw:
        return None
    return LIVE_PATHS.get(os.path.normcase(os.path.abspath(raw)))


def _host_script(name):
    here = os.path.join(HERE, name)
    if os.path.isfile(here):
        return here
    alt = os.path.join(LDA_HOST, name)
    if os.path.isfile(alt):
        return alt
    return here


def act_dump(mid, cmd):
    prev = load_receipt(mid)
    if prev:
        return "replay", prev
    path = resolve_live(cmd)
    if not path:
        rec = "REFUSE id=%s dump NEED named live path FROM FILE\n" % mid
        write_receipt(mid, rec)
        return "refuse", rec
    script = _host_script("muhl_dump_bits.py")
    proc = subprocess.run(
        [sys.executable, script, path],
        capture_output=True,
        text=True,
        timeout=60,
    )
    rec = "\n".join([
        "RECEIPT",
        "operation=dump",
        "id=%s" % mid,
        "purpose=USE",
        "path=%s" % path,
        "fire_occurred=NO",
        "github_computes=NO",
        "",
        proc.stdout or proc.stderr,
        "",
    ])
    write_receipt(mid, rec)
    return "fresh", rec


def act_analyzer(mid, cmd):
    prev = load_receipt(mid)
    if prev:
        return "replay", prev
    path = resolve_live(cmd)
    if not path:
        rec = "REFUSE id=%s analyzer NEED named live path FROM FILE\n" % mid
        write_receipt(mid, rec)
        return "refuse", rec
    script = _host_script("pfc_analyzer.py")
    proc = subprocess.run(
        [sys.executable, script, "snap", path],
        capture_output=True,
        text=True,
        timeout=60,
    )
    rec = "\n".join([
        "RECEIPT",
        "operation=analyzer",
        "id=%s" % mid,
        "purpose=USE",
        "path=%s" % path,
        "fire_occurred=NO",
        "github_computes=NO",
        "",
        proc.stdout or proc.stderr,
        "",
    ])
    write_receipt(mid, rec)
    return "fresh", rec


def format_surface_receipt(mid, cmd):
    homes = mstore.HOMES
    pkg = mstore.PKG
    return "\n".join([
        "RECEIPT",
        "operation=surface",
        "id=%s" % mid,
        "replay=NO",
        "kind=surface",
        "claimed_from=%s" % (cmd.get("claimed_from") or cmd.get("from") or "GROK"),
        "authenticated_player=UNKNOWN",
        "home_inferred=NO",
        "commons.mno=UNTOUCHED",
        "commons_sha256=%s" % (mstore.sha256_file(homes) if os.path.isfile(homes) else "MISSING"),
        "table_mail_sha256=%s" % (mstore.sha256_file(pkg) if os.path.isfile(pkg) else "MISSING"),
        "source=%s" % cmd.get("_source", ""),
        "fire_occurred=NO",
        "append_occurred=NO",
        "fire_337=NO",
        "titan_mmap=NO",
        "github_computes=NO",
        "HTTP is not the computer",
        "",
    ])


def act_surface(mid, cmd):
    prev = load_receipt(mid)
    if prev:
        return "replay", prev
    surface.write_board()
    rec = format_surface_receipt(mid, cmd)
    write_receipt(mid, rec)
    return "fresh", rec


def act_say(mid, cmd):
    prev = load_receipt(mid) or mstore.load_receipt(mid)
    if prev:
        return "replay", prev
    src = (cmd.get("from") or cmd.get("claimed_from") or "").strip().upper()
    dest = (cmd.get("to") or "").strip().upper()
    body = cmd.get("body") or ""
    if isinstance(body, list):
        body = "\n".join(str(x) for x in body)
    body = str(body).replace("\x00", "")
    approved = (cmd.get("approved") or "").strip().upper()
    owner_ok = (cmd.get("owner_ok") or "").strip().upper()
    if approved != "YES":
        rec = "REFUSE id=%s kind=say NEED approved=YES\n" % mid
        write_receipt(mid, rec)
        return "refuse", rec
    if not ID_OK.match(mid):
        rec = "REFUSE id=%s NEED id 8-80 [A-Za-z0-9._-]\n" % mid
        write_receipt(mid, rec)
        return "refuse", rec
    if not body.strip():
        rec = "REFUSE id=%s kind=say NEED body\n" % mid
        write_receipt(mid, rec)
        return "refuse", rec
    if src == "KITE" and dest == "GROK" and owner_ok != "BRYCE":
        rec = (
            "REFUSE id=%s KITE->GROK /say dest. "
            "NEED Bryce confirm outbound body (owner_ok=BRYCE).\n" % mid
        )
        write_receipt(mid, rec)
        return "refuse", rec
    env = mstore.store_offered(mid, src, dest, body)
    letter = mstore.envelope_lines(env)
    dests = route.deliver(src, dest, letter, log=print)
    rec = mouth.format_receipt(mid, "NO", src, dest, body, dests)
    mstore.save_receipt(mid, rec)
    write_receipt(mid, rec)
    return "fresh", rec


def inbox_text(cmds, results):
    lines = [
        "COMMANDS INBOX",
        "GitHub is the board + command tickets. GitHub does not compute.",
        "claimed_from is a CLAIM. authenticated_player=UNKNOWN.",
        "Cloud GET cannot push a command. Bryce or Grok writes the ticket, then --go pulls.",
        "kind=surface surfaces dests FROM FILE. kind=dump/analyzer surface bits. kind=say address+fire+die once per id.",
        "Duplicate id = original receipt. Never smash commons.mno. Never --inject 0x01.",
        "",
        "n=%d" % len(cmds),
        "",
    ]
    for mid in sorted(cmds):
        cmd = cmds[mid]
        st = (results.get(mid) or ("pending", ""))[0]
        lines.append("----")
        lines.append("id=%s" % mid)
        lines.append("kind=%s" % (cmd.get("kind") or ""))
        lines.append("approved=%s" % (cmd.get("approved") or ""))
        lines.append("claimed_from=%s" % (cmd.get("claimed_from") or cmd.get("from") or ""))
        lines.append("authenticated_player=UNKNOWN")
        lines.append("to=%s" % (cmd.get("to") or ""))
        lines.append("status=%s" % st)
        lines.append("source=%s" % (cmd.get("_source") or ""))
        lines.append("receipt=%s/COMMANDS/RECEIPTS/%s.txt" % (BLOB, mid))
        lines.append("")
    return "\n".join(lines) + "\n"


def receipts_inbox():
    lines = [
        "COMMAND RECEIPTS",
        "claimed_from is a CLAIM. authenticated_player=UNKNOWN.",
        "GitHub does not compute. These are dests FROM FILE after a --go pull.",
        "",
    ]
    n = 0
    if os.path.isdir(RECEIPT_ROOT):
        for fn in sorted(os.listdir(RECEIPT_ROOT)):
            if not fn.endswith(".txt") or fn == "inbox.txt":
                continue
            n += 1
            lines.append("----")
            lines.append("id=%s" % fn[:-4])
            lines.append("blob=%s/COMMANDS/RECEIPTS/%s" % (BLOB, fn))
            lines.append("")
    lines.insert(4, "n=%d" % n)
    lines.append("")
    return "\n".join(lines)


def publish_after(files, token):
    if not token:
        print("NEED_BRYCE - no GitHub token. Local COMMANDS+BOARD written.")
        print("NEED_BRYCE - python host/muhl_pub_commons.py --go")
        return
    for path, text in files.items():
        pub._put(token, path, text, "drive receipt %s. mutation=NO on this publish." % path)


def main():
    if "--go" not in sys.argv:
        print("NEED_BRYCE — python host/muhl_github_drive.py --go")
        return 1
    os.makedirs(RECEIPT_ROOT, exist_ok=True)
    token = None
    if "--local" not in sys.argv:
        try:
            token = pub._token()
        except SystemExit:
            token = None
        except Exception:
            token = None
    local = load_local_commands()
    remote = load_github_commands(token)
    cmds = dict(remote)
    cmds.update(local)
    results = {}
    acted = 0
    for mid, cmd in sorted(cmds.items()):
        refused = purpose_refused(mid, cmd)
        if refused:
            results[mid] = ("refuse", refused)
            print("DRIVE refuse purpose", mid)
            continue
        kind = (cmd.get("kind") or "").strip().lower()
        if kind == "surface":
            st, rec = act_surface(mid, cmd)
            results[mid] = (st, rec)
            if st == "fresh":
                acted += 1
            print("DRIVE", st, "surface", mid)
        elif kind == "dump":
            st, rec = act_dump(mid, cmd)
            results[mid] = (st, rec)
            if st == "fresh":
                acted += 1
            print("DRIVE", st, "dump", mid)
        elif kind == "analyzer":
            st, rec = act_analyzer(mid, cmd)
            results[mid] = (st, rec)
            if st == "fresh":
                acted += 1
            print("DRIVE", st, "analyzer", mid)
        elif kind == "say":
            st, rec = act_say(mid, cmd)
            results[mid] = (st, rec)
            if st == "fresh":
                acted += 1
            print("DRIVE", st, "say", mid)
        else:
            rec = "REFUSE id=%s NEED kind=say|surface|dump|analyzer\n" % mid
            write_receipt(mid, rec)
            results[mid] = ("refuse", rec)
            print("DRIVE refuse", mid)
    inbox = inbox_text(cmds, results)
    rinbox = receipts_inbox()
    _write(os.path.join(CMD_ROOT, "inbox.txt"), inbox)
    _write(os.path.join(RECEIPT_ROOT, "inbox.txt"), rinbox)
    _write(os.path.join(PUBLIC, "COMMANDS", "inbox.txt"), inbox)
    _write(os.path.join(PUBLIC, "COMMANDS", "RECEIPTS", "inbox.txt"), rinbox)
    files = pub.collect_pub_files()
    files["COMMANDS/inbox.txt"] = inbox
    files["COMMANDS/RECEIPTS/inbox.txt"] = rinbox
    for mid, (_st, rec) in results.items():
        files["COMMANDS/RECEIPTS/%s.txt" % mid] = rec
    pub.write_local_public(files)
    publish_after(files, token)
    print("DRIVE acted", acted, "ids", len(cmds))
    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
