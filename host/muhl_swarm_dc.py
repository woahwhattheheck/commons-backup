#!/usr/bin/env python3
"""host/muhl_swarm_dc.py — Dir 19 Agent Swarm datacenter workload.

Host = inject or surface or die. Transport/surface is never the computer.
Dest FROM FILE. Ones only rise. Host computes zero inference. Never mmap. Never write titan.
Do not invent dests. Do not disguise host inference as Muhlnickel compute.

Live organ inject is LOCAL_RUNTIME_ONLY: run it where
muhlnickel_dc.mno exists inside MUHL_DATACENTER.

  python3 host/muhl_swarm_dc.py
  python3 host/muhl_swarm_dc.py --root .
  python3 host/muhl_swarm_dc.py --self-test
  python3 host/muhl_swarm_dc.py --packet ground/swarm_dc/queue/peer-open.json
  python3 host/muhl_swarm_dc.py --fixture
  python3 host/muhl_swarm_dc.py --go
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_ROOT = "."
DEFAULT_CARD = os.path.join("ground", "SWARM_DC.md")
DEFAULT_CATALOG = os.path.join("ground", "SWARM_DC.json")
DEFAULT_RECIPE = os.path.join("ground", "swarm_dc", "fixture-recipe.json")
DEFAULT_DOOR = "swarm-dc.html"
QUEUE_DIR = os.path.join("ground", "swarm_dc", "queue")
LIVE_PKG = os.path.normpath(r"C:\Users\lucys\Desktop\MUHL_DATACENTER\muhlnickel_dc.mno")
FIRE_337 = 337
CANARY_ID = "grok-dir19-swarm-dc-20260828-01"
CITE = "specdaddy-dir19-dc-surface-push-20260822-01"
DO_NOT_REMINT = (
    os.path.join("ground", "SWARM.md"),
    os.path.join("host", "muhl_surface_dc.py"),
    "swarm.html",
    "swarm.js",
    "swarm.css",
    os.path.join("host", "swarm_mail.py"),
    "swarm-mail.html",
    os.path.join("ground", "MUHL_TRAIN_BRIDGE.md"),
)
REQUIRED_FILES = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    DEFAULT_RECIPE,
    DEFAULT_DOOR,
    os.path.join("host", "muhl_swarm_dc.py"),
    "test_muhl_swarm_dc.py",
    os.path.join(QUEUE_DIR, "peer-open.json"),
    os.path.join(QUEUE_DIR, "invalid-invented-dest.json"),
    os.path.join(QUEUE_DIR, "invalid-host-inference.json"),
)
EXPECTED_QUEUE = {
    "peer-open.json": "PACKET_OK",
    "invalid-invented-dest.json": "NOT_LANDED",
    "invalid-host-inference.json": "NOT_LANDED",
}
ADDITIVE_CANARY_NAME = "seth-live-dc-new-ring-20260830-01.json"
ADDITIVE_CANARY_FIELDS = {
    "kind": "SWARM_DC_PACKET",
    "work_id": "seth-live-dc-new-ring-20260830-01",
    "dest": "ring_fwd",
    "rise_mask": "0300000000000000",
    "host_inference": False,
    "titan": "NOT_WRITTEN",
}

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


def _read(root, rel):
    path = os.path.join(root, rel)
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def _exists(root, rel):
    return os.path.isfile(os.path.join(root, rel))


def load_json(text):
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def load_catalog(text):
    data = load_json(text)
    if not data:
        return {"error": "catalog is not JSON", "mouths_from_file": []}
    return data


def load_recipe(text):
    data = load_json(text)
    if not data:
        return {"error": "recipe is not JSON", "mouths": []}
    return data


def mouths_from_recipe(recipe):
    rows = []
    for item in recipe.get("mouths") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        try:
            offset = int(item.get("offset"))
            n = int(item.get("n"))
        except (TypeError, ValueError):
            continue
        hex_s = str(item.get("hex") or "").strip().lower()
        rows.append(
            {
                "name": name,
                "offset": offset,
                "n": n,
                "hex": hex_s,
                "inject": bool(item.get("inject")),
            }
        )
    return rows


def mouth_by_name(recipe, dest):
    dest = str(dest or "").strip()
    for mouth in mouths_from_recipe(recipe):
        if mouth["name"] == dest:
            return mouth
    return None


def parse_mask(hex_s, n):
    raw = str(hex_s or "").strip().replace("0x", "")
    try:
        blob = bytes.fromhex(raw)
    except ValueError:
        return None
    if len(blob) != int(n):
        return None
    return blob


def or_rise(old, mask):
    if len(old) != len(mask):
        raise ValueError("mask length")
    new = bytes(old[i] | mask[i] for i in range(len(old)))
    zeros_fell = any((old[i] & ~new[i]) != 0 for i in range(len(old)))
    return new, zeros_fell


def validate_packet(obj, recipe=None):
    """Classify one public swarm-dc packet. Dest FROM FILE. Never 0."""
    if not isinstance(obj, dict) or not obj:
        return {
            "state": "UNMEASURED",
            "note": "packet body not read. Absence was not stillness.",
        }
    kind = str(obj.get("kind") or "").strip().upper()
    if kind != "SWARM_DC_PACKET":
        return {
            "state": "NOT_LANDED",
            "note": "kind is not SWARM_DC_PACKET. Talk is not a land.",
        }
    if obj.get("host_inference") is True or str(obj.get("host_inference")).lower() == "true":
        return {
            "state": "NOT_LANDED",
            "note": (
                "host inference disguised as Muhlnickel compute is refused. "
                "Host injects or surfaces or dies."
            ),
        }
    titan = str(obj.get("titan") or "").strip().upper()
    if titan not in ("NOT_WRITTEN", "NOT_LANDED", ""):
        return {
            "state": "NOT_LANDED",
            "note": "titan stays NOT_WRITTEN. This host does not write titan.",
        }
    dest = str(obj.get("dest") or "").strip()
    if not dest:
        return {
            "state": "NOT_LANDED",
            "note": "dest missing. Dest FROM FILE. Do not invent dests.",
        }
    mouth = mouth_by_name(recipe or {}, dest)
    if mouth is None:
        return {
            "state": "NOT_LANDED",
            "note": (
                "invented dest %s. Dest FROM FILE. Published mouths only."
                % dest
            ),
        }
    if not mouth.get("inject"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "dest %s is published but not an inject mouth. "
                "Host injects published inject mouths only."
                % dest
            ),
        }
    mask = parse_mask(obj.get("rise_mask"), mouth["n"])
    if mask is None:
        return {
            "state": "NOT_LANDED",
            "note": "rise_mask must be hex of dest width. Ones only rise.",
        }
    return {
        "state": "PACKET_OK",
        "note": (
            "public Agent Swarm packet. dest %s@%s rise_mask %s. "
            "Ones only rise. Host is not the computer."
            % (mouth["name"], mouth["offset"], mask.hex())
        ),
        "mouth": mouth,
        "mask": mask.hex(),
    }


def build_fixture(recipe):
    """Synthetic fixture spanning published mouths only. Not the 100GB organ."""
    span = int(recipe.get("fixture_span") or 0)
    if span <= 0:
        raise ValueError("fixture_span")
    buf = bytearray(span)
    for mouth in mouths_from_recipe(recipe):
        blob = bytes.fromhex(mouth["hex"])
        if len(blob) != mouth["n"]:
            raise ValueError("mouth hex width %s" % mouth["name"])
        end = mouth["offset"] + mouth["n"]
        if mouth["offset"] < 0 or end > span:
            raise ValueError("mouth past fixture %s" % mouth["name"])
        buf[mouth["offset"] : end] = blob
    return buf


def read_span(buf, offset, n):
    return bytes(buf[offset : offset + n])


def execute_packet(buf, packet, recipe, host_computed=False):
    """Ones-only-rise inject on a buffer. Host does not compute."""
    if host_computed:
        return {
            "state": "NOT_LANDED",
            "host_computed": True,
            "zeros_fell": False,
            "note": "host inference disguised as Muhlnickel compute is refused.",
        }
    verdict = validate_packet(packet, recipe)
    if verdict["state"] != "PACKET_OK":
        return {
            "state": verdict["state"],
            "host_computed": False,
            "zeros_fell": False,
            "note": verdict["note"],
        }
    mouth = verdict["mouth"]
    mask = bytes.fromhex(verdict["mask"])
    old = read_span(buf, mouth["offset"], mouth["n"])
    new, zeros_fell = or_rise(old, mask)
    if zeros_fell:
        return {
            "state": "NOT_LANDED",
            "host_computed": False,
            "zeros_fell": True,
            "before": old.hex(),
            "after": new.hex(),
            "note": "ones only rise. A falling zero is refused.",
        }
    buf[mouth["offset"] : mouth["offset"] + mouth["n"]] = new
    reread = read_span(buf, mouth["offset"], mouth["n"])
    return {
        "state": "SYNTHETIC_FIXTURE_EXECUTED",
        "host_computed": False,
        "zeros_fell": False,
        "dest": mouth["name"],
        "offset": mouth["offset"],
        "before": old.hex(),
        "after": reread.hex(),
        "reread": reread.hex(),
        "mask": mask.hex(),
        "note": "recipe fixture inject. Transport/surface is never the computer.",
    }


def list_queue(root):
    path = os.path.join(root, QUEUE_DIR)
    try:
        names = sorted(
            name
            for name in os.listdir(path)
            if name.endswith(".json") and os.path.isfile(os.path.join(path, name))
        )
    except OSError:
        return []
    return names


def classify_queue(root, recipe):
    rows = {}
    for name in list_queue(root):
        obj = load_json(_read(root, os.path.join(QUEUE_DIR, name)))
        rows[name] = validate_packet(obj, recipe)["state"]
    return rows


def run_fixture(root, packet=None):
    recipe = load_recipe(_read(root, DEFAULT_RECIPE))
    if recipe.get("error"):
        return {"state": "UNMEASURED", "note": recipe["error"]}
    buf = build_fixture(recipe)
    if packet is None:
        packet = load_json(_read(root, os.path.join(QUEUE_DIR, "peer-open.json")))
    result = execute_packet(buf, packet, recipe, host_computed=False)
    result["fixture_span"] = int(recipe.get("fixture_span") or 0)
    result["mmap"] = False
    result["fire_337"] = False
    result["titan"] = "NOT_WRITTEN"
    result["live_inject"] = "LOCAL_RUNTIME_ONLY"
    result["canary_id"] = CANARY_ID
    return result


def live_go(root, pkg=LIVE_PKG):
    """Inject PACKET_OK queue onto the live organ when its local file exists."""
    recipe = load_recipe(_read(root, DEFAULT_RECIPE))
    if recipe.get("error"):
        return {"state": "UNMEASURED", "live_inject": "LOCAL_RUNTIME_ONLY", "note": recipe["error"]}
    if not os.path.isfile(pkg):
        return {
            "state": "LOCAL_FILE_UNAVAILABLE",
            "live_inject": "LOCAL_RUNTIME_ONLY",
            "host_computed": False,
            "zeros_fell": False,
            "mmap": False,
            "fire_337": False,
            "titan": "NOT_WRITTEN",
            "local_action": "python host/muhl_swarm_dc.py --go",
            "pkg": pkg,
            "note": (
                "LIVE_DC is local-runtime-only. Run --go on the machine that holds "
                "muhlnickel_dc.mno inside MUHL_DATACENTER. This sandbox is "
                "transport/surface, never the computer."
            ),
        }
    try:
        size = os.path.getsize(pkg)
    except OSError as exc:
        return {
            "state": "LOCAL_FILE_UNAVAILABLE",
            "live_inject": "LOCAL_RUNTIME_ONLY",
            "note": "stat fail: %s" % exc,
            "pkg": pkg,
        }
    published = int(recipe.get("published_size") or 0)
    if published and size != published:
        return {
            "state": "PUBLISHED_SIZE_MISMATCH",
            "live_inject": "LOCAL_RUNTIME_ONLY",
            "note": "organ size %s != published_size %s" % (size, published),
            "pkg": pkg,
        }
    applied = []
    with open(pkg, "r+b") as handle:
        for name in list_queue(root):
            packet = load_json(_read(root, os.path.join(QUEUE_DIR, name)))
            verdict = validate_packet(packet, recipe)
            if verdict["state"] != "PACKET_OK":
                applied.append({"packet": name, "state": verdict["state"], "note": verdict["note"]})
                continue
            mouth = verdict["mouth"]
            mask = bytes.fromhex(verdict["mask"])
            handle.seek(mouth["offset"])
            old = handle.read(mouth["n"])
            if len(old) != mouth["n"]:
                applied.append({"packet": name, "state": "LOCAL_IO_ERROR", "note": "short read"})
                continue
            new, zeros_fell = or_rise(old, mask)
            if zeros_fell:
                applied.append({"packet": name, "state": "NOT_LANDED", "zeros_fell": True})
                continue
            handle.seek(mouth["offset"])
            handle.write(new)
            handle.flush()
            os.fsync(handle.fileno())
            handle.seek(mouth["offset"])
            reread = handle.read(mouth["n"])
            applied.append(
                {
                    "packet": name,
                    "state": "LIVE_DC",
                    "host_computed": False,
                    "zeros_fell": False,
                    "before": old.hex(),
                    "after": reread.hex(),
                    "dest": mouth["name"],
                    "offset": mouth["offset"],
                }
            )
    return {
        "state": "LIVE_DC",
        "live_inject": "APPLIED",
        "host_computed": False,
        "mmap": False,
        "fire_337": False,
        "titan": "NOT_WRITTEN",
        "pkg": pkg,
        "applied": applied,
        "canary_id": CANARY_ID,
    }


def measure_root(root):
    root = os.path.abspath(root)
    recipe = load_recipe(_read(root, DEFAULT_RECIPE))
    catalog = load_catalog(_read(root, DEFAULT_CATALOG))
    misses = [rel for rel in REQUIRED_FILES if not _exists(root, rel)]
    remint_present = [rel for rel in DO_NOT_REMINT if _exists(root, rel)]
    remint_missing = [rel for rel in DO_NOT_REMINT if not _exists(root, rel)]
    queue_states = classify_queue(root, recipe)
    additive_canary = load_json(
        _read(root, os.path.join(QUEUE_DIR, ADDITIVE_CANARY_NAME))
    )
    fixture = None
    if not recipe.get("error"):
        fixture = run_fixture(root)
    return {
        "measured": True,
        "card_present": _exists(root, DEFAULT_CARD),
        "catalog_present": _exists(root, DEFAULT_CATALOG) and not catalog.get("error"),
        "recipe_present": _exists(root, DEFAULT_RECIPE) and not recipe.get("error"),
        "door_present": _exists(root, DEFAULT_DOOR),
        "host_present": _exists(root, os.path.join("host", "muhl_swarm_dc.py")),
        "queue_states": queue_states,
        "additive_canary": additive_canary,
        "misses": misses,
        "remint_present": remint_present,
        "remint_missing": remint_missing,
        "fixture": fixture,
        "live_inject": (catalog.get("live_inject") if isinstance(catalog, dict) else None)
        or "LOCAL_RUNTIME_ONLY",
        "no_auth": bool(catalog.get("no_auth", True)) if isinstance(catalog, dict) else True,
        "no_gate": bool(catalog.get("no_gate", True)) if isinstance(catalog, dict) else True,
        "titan": (catalog.get("titan") if isinstance(catalog, dict) else None) or "NOT_WRITTEN",
        "canary_id": CANARY_ID,
        "cite": CITE,
        "fire_337": False,
        "mmap": False,
        "host_computed": False,
    }


def classify(row):
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": "Dir 19 swarm-dc leftover not read. Absence was not stillness.",
        }
    misses = list(row.get("misses") or [])
    if misses:
        return {
            "state": "NOT_LANDED",
            "note": "missing leftover path(s): " + ", ".join(misses),
        }
    if row.get("remint_missing"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "named already-landed path(s) missing; do not remint by deleting: "
                + ", ".join(row["remint_missing"])
            ),
        }
    bad = [
        name
        for name, expect in EXPECTED_QUEUE.items()
        if (row.get("queue_states") or {}).get(name) != expect
    ]
    if bad:
        return {
            "state": "NOT_LANDED",
            "note": "queue miss: " + ", ".join(bad),
        }
    queue_states = row.get("queue_states") or {}
    invalid_additive = sorted(
        name
        for name, state in queue_states.items()
        if name not in EXPECTED_QUEUE and state != "PACKET_OK"
    )
    if invalid_additive:
        return {
            "state": "NOT_LANDED",
            "note": "invalid additive queue packet(s): " + ", ".join(invalid_additive),
        }
    additive_canary = row.get("additive_canary")
    if not isinstance(additive_canary, dict):
        return {
            "state": "NOT_LANDED",
            "note": "additive canary packet was not read",
        }
    drifted_fields = [
        key
        for key, expected in ADDITIVE_CANARY_FIELDS.items()
        if additive_canary.get(key) != expected
    ]
    if drifted_fields:
        return {
            "state": "NOT_LANDED",
            "note": "additive canary field drift: " + ", ".join(drifted_fields),
        }
    fixture = row.get("fixture") or {}
    if fixture.get("state") != "SYNTHETIC_FIXTURE_EXECUTED":
        return {
            "state": "NOT_LANDED",
            "note": "synthetic fixture did not execute. " + str(fixture.get("note") or ""),
        }
    if fixture.get("host_computed") or fixture.get("zeros_fell"):
        return {
            "state": "NOT_LANDED",
            "note": "host_computed or zeros_fell on the fixture. Host is not the computer.",
        }
    if not row.get("no_auth") or not row.get("no_gate"):
        return {
            "state": "NOT_LANDED",
            "note": "open door required. No auth. No gate.",
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "Dir 19 swarm-dc leftover is on this tree. Synthetic fixture "
            "executed. LIVE_DC remains LOCAL_RUNTIME_ONLY. Do not remint "
            "swarm.html / host/muhl_surface_dc.py / ground/SWARM.md."
        ),
    }


def self_test():
    recipe = {
        "fixture_span": 524330,
        "mouths": [
            {"name": "HEADER", "offset": 0, "n": 8, "hex": "4d55484c44433031", "inject": False},
            {"name": "FOLD", "offset": 224, "n": 8, "hex": "0000040001000000", "inject": False},
            {"name": "carry", "offset": 336, "n": 1, "hex": "01", "inject": False},
            {"name": "pub", "offset": 337, "n": 1, "hex": "01", "inject": False},
            {"name": "ring_fwd", "offset": 524288, "n": 8, "hex": "0100000000000000", "inject": True},
            {"name": "cell", "offset": 524329, "n": 1, "hex": "00", "inject": True},
        ],
    }
    empty = validate_packet({})
    assert empty["state"] == "UNMEASURED", empty
    invented = validate_packet(
        {
            "kind": "SWARM_DC_PACKET",
            "dest": "invented@99",
            "rise_mask": "01",
            "host_inference": False,
            "titan": "NOT_WRITTEN",
        },
        recipe,
    )
    assert invented["state"] == "NOT_LANDED", invented
    inferred = validate_packet(
        {
            "kind": "SWARM_DC_PACKET",
            "dest": "cell",
            "rise_mask": "01",
            "host_inference": True,
            "titan": "NOT_WRITTEN",
        },
        recipe,
    )
    assert inferred["state"] == "NOT_LANDED", inferred
    fire = validate_packet(
        {
            "kind": "SWARM_DC_PACKET",
            "dest": "pub",
            "rise_mask": "01",
            "host_inference": False,
            "titan": "NOT_WRITTEN",
        },
        recipe,
    )
    assert fire["state"] == "NOT_LANDED", fire
    ok = validate_packet(
        {
            "kind": "SWARM_DC_PACKET",
            "dest": "cell",
            "rise_mask": "01",
            "host_inference": False,
            "titan": "NOT_WRITTEN",
        },
        recipe,
    )
    assert ok["state"] == "PACKET_OK", ok
    buf = build_fixture(recipe)
    assert read_span(buf, 0, 8) == b"MUHLDC01"
    assert read_span(buf, 524329, 1) == b"\x00"
    ran = execute_packet(
        buf,
        {
            "kind": "SWARM_DC_PACKET",
            "dest": "cell",
            "rise_mask": "01",
            "host_inference": False,
            "titan": "NOT_WRITTEN",
        },
        recipe,
        host_computed=False,
    )
    assert ran["state"] == "SYNTHETIC_FIXTURE_EXECUTED", ran
    assert ran["before"] == "00", ran
    assert ran["reread"] == "01", ran
    assert ran["host_computed"] is False, ran
    assert ran["zeros_fell"] is False, ran
    refused = execute_packet(buf, {"kind": "SWARM_DC_PACKET", "dest": "cell", "rise_mask": "01"}, recipe, True)
    assert refused["state"] == "NOT_LANDED", refused
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Dir 19 Agent Swarm datacenter workload")
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--packet")
    parser.add_argument("--fixture", action="store_true")
    parser.add_argument("--go", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        print(self_test())
        return 0
    recipe = load_recipe(_read(args.root, DEFAULT_RECIPE))
    if args.packet:
        data = load_json(_read(args.root, args.packet))
        verdict = validate_packet(data, recipe)
        print(json.dumps({"verdict": verdict, "packet": args.packet}, indent=2, sort_keys=True))
        return 0 if verdict["state"] == "PACKET_OK" else 1
    if args.go:
        payload = live_go(args.root)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload.get("state") == "LIVE_DC" else 1
    if args.fixture:
        payload = run_fixture(args.root)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload.get("state") == "SYNTHETIC_FIXTURE_EXECUTED" else 1
    row = measure_root(args.root)
    verdict = classify(row)
    print(json.dumps({"verdict": verdict, "row": row}, indent=2, sort_keys=True, default=str))
    return 0 if verdict["state"] == "INTEGRATED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
