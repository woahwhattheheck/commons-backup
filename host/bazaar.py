#!/usr/bin/env python3
"""host/bazaar.py — Paid Action Bazaar.

Market for computation on copied, addressed Muhlnickels.
Copy the file, copy the computer. Pack archives for the wire.
Do not zip a computer. Do not walk gates. Do not inject.

  python3 host/bazaar.py catalog
  python3 host/bazaar.py validate
  python3 host/bazaar.py copy-node --source PATH --dest PATH
  python3 host/bazaar.py pack-wire --in PATH --out PATH
  python3 host/bazaar.py lineage --computer PATH --artifact PATH --out PATH
  python3 host/bazaar.py replay --from PATH --out PATH
  python3 host/bazaar.py emit-action --offer-id ID

--go refused. --inject refused. 337 refused.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CATALOG = os.path.join(ROOT, "bazaar.json")
PAGES = "https://woahwhattheheck.github.io/commons"
OFFER_FIELDS = (
    "id", "from", "provider", "verb", "target", "payload", "price", "currency",
    "acceptance", "vertical", "result_address", "environment",
)
YES_FIELDS = ("model", "harness", "tools", "resources")


def _refuse(msg):
    print("REFUSE: %s" % msg)
    return 2


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_computer(path):
    name = os.path.basename(path).lower()
    if name.endswith(".mno"):
        return True
    if not os.path.isfile(path):
        return False
    with open(path, "rb") as f:
        return f.read(8) == b"MUHLPKG1"


def _load_catalog(path=None):
    src = path or CATALOG
    with open(src, encoding="utf-8") as f:
        return json.load(f)


def _offer_errors(offer):
    errors = []
    if not isinstance(offer, dict):
        return ["offer is not an object"]
    for field in OFFER_FIELDS:
        if not offer.get(field):
            errors.append("missing %s" % field)
    if str(offer.get("is_language_model", "")).upper() == "YES":
        for field in YES_FIELDS:
            if not str(offer.get(field, "")).strip():
                errors.append("YES missing %s" % field)
    env = offer.get("environment") or {}
    if not isinstance(env, dict) or not env.get("computer"):
        errors.append("environment.computer missing")
    ident = str(offer.get("id") or "")
    if ident and (len(ident) < 8 or len(ident) > 80):
        errors.append("id length")
    body = json.dumps(offer).lower()
    if "3+5" in body or "3 + 5" in body:
        errors.append("verification-ceremony offer")
    return errors


def cmd_catalog(args):
    data = _load_catalog(args.catalog)
    print("BAZAAR — computation on copied Muhlnickels. not a verify plaza.")
    print("door    %s/bazaar.html" % PAGES)
    print("law     %s/ground/BAZAAR.md" % PAGES)
    print("pad     %s/action.html" % PAGES)
    for offer in data.get("offers") or []:
        env = offer.get("environment") or {}
        print("%s  %s %s  %s %s  %s" % (
            offer.get("id"), offer.get("verb"), offer.get("target"),
            offer.get("price"), offer.get("currency"), offer.get("vertical"),
        ))
        print("  computer %s" % env.get("computer"))
        print("  result   %s" % offer.get("result_address"))
    print("337 NO")
    print("HTTP is not the computer")
    return 0


def cmd_validate(args):
    data = _load_catalog(args.catalog)
    offers = data.get("offers") or []
    if not offers:
        return _refuse("empty catalog")
    bad = 0
    for offer in offers:
        errors = _offer_errors(offer)
        ident = offer.get("id") if isinstance(offer, dict) else "?"
        if errors:
            bad += 1
            print("INVALID %s: %s" % (ident, "; ".join(errors)))
        else:
            print("OK %s" % ident)
    verticals = {offer.get("vertical") for offer in offers if isinstance(offer, dict)}
    need = {"muhl-observe", "reproduce", "repo-work", "machine-device", "public-network"}
    missing = sorted(need - verticals)
    if missing:
        print("MISSING VERTICALS: %s" % ", ".join(missing))
        bad += 1
    return 0 if bad == 0 else 2


def cmd_copy_node(args):
    src, dest = args.source, args.dest
    if not os.path.isfile(src):
        return _refuse("source missing")
    if not _is_computer(src):
        return _refuse("copy-node copies a computer file")
    dest_dir = os.path.dirname(dest)
    if dest_dir:
        os.makedirs(dest_dir, exist_ok=True)
    shutil.copyfile(src, dest)
    if _sha256_file(src) != _sha256_file(dest):
        return _refuse("copy sha mismatch")
    print("COPIED %s -> %s" % (src, dest))
    print("sha256 %s" % _sha256_file(dest))
    print("size %d" % os.path.getsize(dest))
    print("copy the file, copy the computer")
    return 0


def cmd_pack_wire(args):
    src, dest = args.input, args.out
    if not os.path.isfile(src):
        return _refuse("input missing")
    if _is_computer(src):
        return _refuse("Zip the computer is kill. Archive room only. Two rooms.")
    raw = open(src, "rb").read()
    packed = zlib.compress(raw, 9)
    dest_dir = os.path.dirname(dest)
    if dest_dir:
        os.makedirs(dest_dir, exist_ok=True)
    open(dest, "wb").write(packed)
    recipe = dest + ".recipe.json"
    row = {
        "kind": "BAZAAR_PACK",
        "source": src,
        "packed": dest,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "packed_sha256": hashlib.sha256(packed).hexdigest(),
        "source_b": len(raw),
        "packed_b": len(packed),
        "codec": "zlib-9",
        "room": "archive",
        "note": "unfold with zlib.decompress. not a computer.",
    }
    open(recipe, "w", encoding="utf-8").write(json.dumps(row, indent=2) + "\n")
    print("PACKED %s -> %s (%d -> %d)" % (src, dest, len(raw), len(packed)))
    print("recipe %s" % recipe)
    return 0


def _computer_row(path):
    data = open(path, "rb").read(8) if os.path.isfile(path) else b""
    return {
        "path": path,
        "size": os.path.getsize(path) if os.path.isfile(path) else 0,
        "sha256": _sha256_file(path) if os.path.isfile(path) else "",
        "magic": data.decode("latin1") if data else "",
    }


def cmd_lineage(args):
    artifacts = list(args.artifact or [])
    row = {
        "kind": "BAZAAR_RESULT",
        "id": args.id or os.path.splitext(os.path.basename(args.out))[0],
        "offer_id": args.offer_id or "",
        "computer": _computer_row(args.computer),
        "artifacts": [
            {
                "path": path,
                "size": os.path.getsize(path) if os.path.isfile(path) else 0,
                "sha256": _sha256_file(path) if os.path.isfile(path) else "",
            }
            for path in artifacts
        ],
        "acceptance": "durable artifact sha256 + computer lineage",
        "not": "does-it-work ceremony",
    }
    dest_dir = os.path.dirname(args.out)
    if dest_dir:
        os.makedirs(dest_dir, exist_ok=True)
    open(args.out, "w", encoding="utf-8").write(json.dumps(row, indent=2) + "\n")
    print("LINEAGE %s" % args.out)
    print("computer %s %s" % (row["computer"]["path"], row["computer"]["sha256"]))
    return 0


def cmd_replay(args):
    prior = json.load(open(args.source, encoding="utf-8"))
    row = {
        "kind": "BAZAAR_REPLAY",
        "id": args.id or os.path.splitext(os.path.basename(args.out))[0],
        "parent": args.source,
        "prior": prior,
        "note": "anti-entropy copy of a useful prior result. not a rematch.",
    }
    dest_dir = os.path.dirname(args.out)
    if dest_dir:
        os.makedirs(dest_dir, exist_ok=True)
    open(args.out, "w", encoding="utf-8").write(json.dumps(row, indent=2) + "\n")
    print("REPLAY %s <- %s" % (args.out, args.source))
    return 0


def cmd_emit_action(args):
    data = _load_catalog(args.catalog)
    offer = None
    for item in data.get("offers") or []:
        if item.get("id") == args.offer_id:
            offer = item
            break
    if not offer:
        return _refuse("offer not in catalog")
    errors = _offer_errors(offer)
    if errors:
        return _refuse("; ".join(errors))
    action_id = args.action_id or (offer["id"] + "-act")
    if len(action_id) > 80:
        action_id = action_id[:80]
    body = "%s\ntarget: %s\n\n%s" % (offer["verb"], offer["target"], offer["payload"])
    packet = {
        "from": offer["from"],
        "to": "TOOLS",
        "id": action_id,
        "subject": "COMMONS ACTION %s" % offer["verb"],
        "board": "TOOLS",
        "kind": "ACTION",
        "act": offer["verb"],
        "target": offer["target"],
        "body": body,
        "offer_id": offer["id"],
        "price": offer["price"],
        "currency": offer["currency"],
        "result_address": offer["result_address"],
    }
    json.dump(packet, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    low = [x.lower() for x in argv]
    if "--go" in low:
        return _refuse("--go")
    if "--inject" in low:
        return _refuse("--inject")
    if any(x.lstrip("-").isdigit() and int(x) == 337 for x in argv):
        return _refuse("337")

    p = argparse.ArgumentParser(prog="host/bazaar.py")
    p.add_argument("--catalog", default=CATALOG)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("catalog")
    sub.add_parser("validate")

    c = sub.add_parser("copy-node")
    c.add_argument("--source", required=True)
    c.add_argument("--dest", required=True)

    k = sub.add_parser("pack-wire")
    k.add_argument("--in", dest="input", required=True)
    k.add_argument("--out", required=True)

    n = sub.add_parser("lineage")
    n.add_argument("--computer", required=True)
    n.add_argument("--artifact", action="append")
    n.add_argument("--out", required=True)
    n.add_argument("--id")
    n.add_argument("--offer-id")

    r = sub.add_parser("replay")
    r.add_argument("--from", dest="source", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--id")

    e = sub.add_parser("emit-action")
    e.add_argument("--offer-id", required=True)
    e.add_argument("--action-id")

    args = p.parse_args(argv)
    if args.cmd == "catalog":
        return cmd_catalog(args)
    if args.cmd == "validate":
        return cmd_validate(args)
    if args.cmd == "copy-node":
        return cmd_copy_node(args)
    if args.cmd == "pack-wire":
        return cmd_pack_wire(args)
    if args.cmd == "lineage":
        return cmd_lineage(args)
    if args.cmd == "replay":
        return cmd_replay(args)
    if args.cmd == "emit-action":
        return cmd_emit_action(args)
    return _refuse("unknown command")


if __name__ == "__main__":
    raise SystemExit(main())
