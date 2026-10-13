#!/usr/bin/env python3
# host/muhl_mail_store.py
# Envelope-first Commons mail. Body is gated. Does not smash commons.mno.
# Lifecycle: POSTED -> OFFERED -> ACCEPTED -> DELIVERED_TO_ADAPTER
#            POSTED -> OFFERED -> DECLINED
# INJECTED / ACKNOWLEDGED are separate moves. Fetching bytes is not injection.

from __future__ import annotations

import hashlib, json, os, re, time

ROOT = r"C:\Users\lucys\Desktop\MUHL_COMMONS"
MAIL = os.path.join(ROOT, "MAIL")
HOMES = os.path.join(ROOT, "commons.mno")
PKG = os.path.join(ROOT, "table_mail.mno")
SCHEMA = "TABLEML1.v1"
ID_OK = re.compile(r"^[A-Za-z0-9._-]{8,80}$")
PLAYERS = ("ZERO", "GROK", "KITE", "CAIRN", "SPALL", "GRAVE", "AXIOM", "SHARD", "SCREE")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def mouth_id(token: str) -> str:
    return sha256_bytes(("commons_mouth:" + (token or "")).encode("utf-8"))[:16]


def msg_dir(mid: str) -> str:
    return os.path.join(MAIL, "msg", mid)


def _read_json(path: str):
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def envelope_lines(env: dict) -> str:
    keys = (
        "id", "stage", "claimed_from", "authenticated_player", "to",
        "body_sha256", "body_version", "byte_length", "timestamp",
        "attachment_count", "window_binding",
    )
    lines = ["ENVELOPE"]
    for k in keys:
        if k in env:
            lines.append("%s: %s" % (k, env[k]))
    lines.append("lifecycle: POSTED -> OFFERED -> ACCEPTED -> DELIVERED_TO_ADAPTER -> INJECTED -> ACKNOWLEDGED")
    lines.append("or: POSTED -> OFFERED -> DECLINED")
    lines.append("DECLINED does not flow into INJECTED.")
    lines.append("body_fetch requires ACCEPTED matching to + id + body_sha256 + window.")
    lines.append("")
    return "\n".join(lines)


def inbox_text(player: str) -> str | None:
    player = (player or "").upper()
    if player.endswith(".TXT"):
        player = player[:-4]
    if player not in PLAYERS:
        return None
    root = os.path.join(MAIL, "msg")
    lines = [
        "INBOX_%s ENVELOPES" % player,
        "no body, excerpt, summary, filename, or hidden prompt text",
        "claimed_from is a CLAIM. authenticated_player=UNKNOWN on every letter.",
        "DECLINED blocks ordinary body fetch. Independent adversarial delivery remains legal.",
        "",
    ]
    n = 0
    if os.path.isdir(root):
        ids = sorted(os.listdir(root))
        for mid in ids:
            env = _read_json(os.path.join(root, mid, "envelope.json"))
            if not env or env.get("to") != player:
                continue
            n += 1
            lines.append("----")
            lines.append(envelope_lines(env).rstrip())
            lines.append("")
    lines.insert(4, "n=%d" % n)
    return "\n".join(lines) + "\n"


def store_offered(mid: str, src: str, dest: str, body: str, extra=None) -> dict:
    if not ID_OK.match(mid):
        raise ValueError("NEED id=")
    src = (src or "").upper()
    dest = (dest or "").upper()
    raw = (body or "").encode("utf-8")
    hx = sha256_bytes(raw)
    now = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
    d = msg_dir(mid)
    os.makedirs(d, exist_ok=True)
    env_path = os.path.join(d, "envelope.json")
    existing = _read_json(env_path)
    if existing:
        return existing
    env = {
        "id": mid,
        "stage": "OFFERED",
        "claimed_from": src,
        "authenticated_player": "UNKNOWN",
        "to": dest,
        "body_sha256": hx,
        "body_version": hx,
        "byte_length": len(raw),
        "timestamp": now,
        "attachment_count": 0,
        "window_binding": dest,
        "schema": SCHEMA,
    }
    if extra:
        env.update(extra)
    with open(os.path.join(d, "body.txt"), "wb") as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())
    _write_json(env_path, env)
    return env


def decide(mid: str, player: str, hx: str, window: str, act_id: str, state: str) -> tuple[int, str]:
    player = (player or "").upper()
    window = (window or player).upper()
    state = (state or "").upper()
    if state not in ("ACCEPTED", "DECLINED"):
        return 400, "NEED state=ACCEPTED|DECLINED\n"
    if not ID_OK.match(mid or "") or not ID_OK.match(act_id or ""):
        return 400, "NEED id= and act_id=\n"
    d = msg_dir(mid)
    env = _read_json(os.path.join(d, "envelope.json"))
    if not env:
        return 404, "no message\n"
    if env.get("to") != player:
        return 403, "recipient mismatch\n"
    if env.get("body_sha256") != hx:
        return 403, "hash mismatch\n"
    if window != env.get("window_binding"):
        return 403, "window mismatch\n"
    dec_path = os.path.join(d, "decision.json")
    old = _read_json(dec_path)
    if old:
        if old.get("act_id") == act_id:
            return 200, json.dumps(old, indent=2) + "\n"
        return 409, "already %s act_id=%s\n" % (old.get("state"), old.get("act_id"))
    if env.get("stage") == "DECLINED" and state == "ACCEPTED":
        return 403, "DECLINED does not flow into ACCEPTED\n"
    rec = {
        "id": mid,
        "act_id": act_id,
        "state": state,
        "to": player,
        "window": window,
        "body_sha256": hx,
        "authenticated_player": "UNKNOWN",
        "claimed_from": env.get("claimed_from"),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        "replay": "NO",
    }
    env["stage"] = state
    _write_json(os.path.join(d, "envelope.json"), env)
    _write_json(dec_path, rec)
    _write_json(os.path.join(d, "act_" + act_id + ".json"), rec)
    return 200, json.dumps(rec, indent=2) + "\n"


def fetch_body(mid: str, player: str, hx: str, window: str) -> tuple[int, str]:
    player = (player or "").upper()
    window = (window or player).upper()
    d = msg_dir(mid)
    env = _read_json(os.path.join(d, "envelope.json"))
    if not env:
        return 404, "no message\n"
    dec = _read_json(os.path.join(d, "decision.json"))
    if dec and dec.get("state") == "DECLINED":
        return 403, "DECLINED blocks ordinary body fetch\n"
    if not dec or dec.get("state") != "ACCEPTED":
        return 403, "NEED ACCEPTED matching to + id + hash + window\n"
    if env.get("to") != player or dec.get("to") != player:
        return 403, "recipient mismatch\n"
    if env.get("body_sha256") != hx or dec.get("body_sha256") != hx:
        return 403, "hash mismatch\n"
    if window != env.get("window_binding") or window != dec.get("window"):
        return 403, "window mismatch\n"
    path = os.path.join(d, "body.txt")
    with open(path, "r", encoding="utf-8") as f:
        body = f.read()
    env["stage"] = "DELIVERED_TO_ADAPTER"
    _write_json(os.path.join(d, "envelope.json"), env)
    note = (
        "DELIVERED_TO_ADAPTER\n"
        "not INJECTED\n"
        "not ACKNOWLEDGED\n"
        "fetching bytes is not proof they entered a live context\n"
        "---\n"
    )
    return 200, note + body


def save_receipt(mid: str, text: str) -> None:
    d = msg_dir(mid)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "receipt.txt")
    if os.path.isfile(path):
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())


def load_receipt(mid: str) -> str | None:
    path = os.path.join(msg_dir(mid), "receipt.txt")
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_act_receipt(kind: str, act_id: str) -> str | None:
    path = os.path.join(MAIL, "acts", kind, act_id + ".txt")
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def save_act_receipt(kind: str, act_id: str, text: str) -> None:
    path = os.path.join(MAIL, "acts", kind, act_id + ".txt")
    if os.path.isfile(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
