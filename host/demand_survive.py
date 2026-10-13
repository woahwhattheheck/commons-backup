#!/usr/bin/env python3
"""host/demand_survive.py — demands that survive the conversation.

Astra D5 / QUILL. Reuses Commons demand/assignment/job patterns:
  - open_work: Slack CLAIMED is not a land; receipt on main is truth
  - current_work: unfinished ledger until bytes on main
  - occupancy.md: presence is a file; parallel allowed; collisions visible

This is a durable pickup/continuation surface for prose demands.
Never an admission.
No forced authoring template. Does not remint C1/G2/M3/R4 files.

  python3 host/demand_survive.py list
  python3 host/demand_survive.py show --id <id>
  python3 host/demand_survive.py record --id <id> --prose "..." --source slack:...
  python3 host/demand_survive.py correct --id <id> --prose "..."
  python3 host/demand_survive.py occupy --id <id> --who QUILL --slice <slice>
  python3 host/demand_survive.py interrupt --id <id> --who QUILL --note "..."
  python3 host/demand_survive.py handoff --id <id> --from-who A --to-who B --note "..." --next "..."
  python3 host/demand_survive.py complete --id <id> --pointer <url> --receipt p/....md
  python3 host/demand_survive.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone


SCHEMA = "commons-demand-survive-v1"
DEFAULT_ROOT = "."
STORE_DIR = os.path.join("ground", "demands")
INDEX_REL = os.path.join("ground", "DEMANDS.json")
ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,80}$")
OCCUPANT_ACTIVE = frozenset({"active", "interrupted"})
STATUSES = ("open", "occupied", "done")
WHO_KEY = "who"


def _utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


def _write(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
        if not text.endswith("\n"):
            handle.write("\n")


def demand_path(root, demand_id):
    return os.path.join(root, STORE_DIR, "%s.json" % demand_id)


def empty_demand(demand_id, prose, source="", from_who="", ts=None):
    return {
        "schema": SCHEMA,
        "id": demand_id,
        "original": {
            "prose": str(prose or ""),
            "source": str(source or ""),
            "from": str(from_who or ""),
            "ts": ts or _utc_now(),
        },
        "corrections": [],
        "occupants": [],
        "result": None,
        "status": "open",
    }


def derive_status(demand):
    if demand.get("result"):
        return "done"
    occupants = demand.get("occupants") or []
    if any(str(o.get("status") or "") in OCCUPANT_ACTIVE for o in occupants):
        return "occupied"
    return "open"


def refresh_status(demand):
    out = dict(demand)
    out["status"] = derive_status(out)
    return out


def validate_demand(demand):
    problems = []
    if not isinstance(demand, dict):
        return ["demand is not an object"]
    if demand.get("schema") != SCHEMA:
        problems.append("schema must be %s" % SCHEMA)
    demand_id = str(demand.get("id") or "")
    if not ID_RE.match(demand_id):
        problems.append("id must match %s" % ID_RE.pattern)
    original = demand.get("original") or {}
    if not isinstance(original, dict):
        problems.append("original must be an object")
    elif len(str(original.get("prose") or "").strip()) < 8:
        problems.append("original.prose too short")
    corrections = demand.get("corrections")
    if corrections is None:
        corrections = []
    if not isinstance(corrections, list):
        problems.append("corrections must be a list")
    occupants = demand.get("occupants")
    if occupants is None:
        occupants = []
    if not isinstance(occupants, list):
        problems.append("occupants must be a list")
    else:
        for row in occupants:
            if not isinstance(row, dict):
                problems.append("occupant is not an object")
                continue
            if not str(row.get(WHO_KEY) or "").strip():
                problems.append("occupant who-label empty")
            if str(row.get("status") or "") not in (
                "active",
                "interrupted",
                "handed_off",
                "complete",
            ):
                problems.append("occupant.status invalid")
    result = demand.get("result")
    if result is not None and not isinstance(result, dict):
        problems.append("result must be object or null")
    status = demand.get("status")
    if status not in STATUSES:
        problems.append("status not in enum")
    return problems


def load_demand(root, demand_id):
    raw = _read(demand_path(root, demand_id))
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return {"error": "demand is not JSON", "id": demand_id}
    return data


def save_demand(root, demand):
    demand = refresh_status(demand)
    problems = validate_demand(demand)
    if problems:
        return demand, problems
    path = demand_path(root, demand["id"])
    _write(path, json.dumps(demand, indent=2, sort_keys=True))
    rebuild_index(root)
    return demand, []


def list_demands(root):
    folder = os.path.join(root, STORE_DIR)
    rows = []
    if not os.path.isdir(folder):
        return rows
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".json"):
            continue
        raw = _read(os.path.join(folder, name))
        try:
            data = json.loads(raw or "{}")
        except ValueError:
            continue
        if not isinstance(data, dict) or data.get("schema") != SCHEMA:
            continue
        data = refresh_status(data)
        rows.append(data)
    return rows


def rebuild_index(root):
    rows = list_demands(root)
    index = {
        "schema": SCHEMA,
        "n": len(rows),
        "note": (
            "Never an admission. Durable demand pickup/continuation surface. "
            "Prose demands keep original + corrections. "
            "Parallel occupancy is visible; collisions are not silent. "
            "Slack CLAIMED alone does not close a demand — result.pointer does. "
            "Instrument: host/demand_survive.py. Door: demand-survive.html."
        ),
        "by_status": {name: 0 for name in STATUSES},
        "demands": [],
    }
    for row in rows:
        status = derive_status(row)
        index["by_status"][status] = index["by_status"].get(status, 0) + 1
        active = [
            o
            for o in (row.get("occupants") or [])
            if str(o.get("status") or "") in OCCUPANT_ACTIVE
        ]
        index["demands"].append(
            {
                "id": row.get("id"),
                "status": status,
                "source": (row.get("original") or {}).get("source") or "",
                "title": _title_of(row),
                "occupants": [
                    {
                        WHO_KEY: o.get(WHO_KEY),
                        "status": o.get("status"),
                        "slice_id": o.get("slice_id"),
                    }
                    for o in active
                ],
                "result": row.get("result"),
                "href": "./ground/demands/%s.json" % row.get("id"),
            }
        )
    _write(
        os.path.join(root, INDEX_REL),
        json.dumps(index, indent=2, sort_keys=True),
    )
    return index


def _title_of(demand):
    prose = str((demand.get("original") or {}).get("prose") or "").strip()
    line = prose.splitlines()[0] if prose else demand.get("id") or ""
    return line[:120]


def current_prose(demand):
    """Latest owner-facing text: last correction if any, else original."""
    corrections = demand.get("corrections") or []
    if corrections:
        return str(corrections[-1].get("prose") or "")
    return str((demand.get("original") or {}).get("prose") or "")


def record_demand(root, demand_id, prose, source="", from_who="", ts=None):
    if not ID_RE.match(demand_id):
        return None, ["id must match %s" % ID_RE.pattern]
    existing = load_demand(root, demand_id)
    if existing and not existing.get("error"):
        prior = str((existing.get("original") or {}).get("prose") or "")
        if prior == str(prose or ""):
            return refresh_status(existing), []
        return existing, [
            "CONFLICT demand already exists with different original prose: %s" % demand_id
        ]
    demand = empty_demand(
        demand_id, prose, source=source, from_who=from_who, ts=ts
    )
    return save_demand(root, demand)


def append_correction(root, demand_id, prose, from_who="", ts=None):
    demand = load_demand(root, demand_id)
    if not demand or demand.get("error"):
        return None, ["demand not found: %s" % demand_id]
    corrections = list(demand.get("corrections") or [])
    corrections.append(
        {
            "prose": str(prose or ""),
            "from": str(from_who or ""),
            "ts": ts or _utc_now(),
        }
    )
    demand["corrections"] = corrections
    return save_demand(root, demand)


def occupy_demand(root, demand_id, who, slice_id="", note="", ts=None):
    demand = load_demand(root, demand_id)
    if not demand or demand.get("error"):
        return None, ["demand not found: %s" % demand_id]
    if demand.get("result"):
        return demand, ["demand already done: %s" % demand_id]
    who = str(who or "").strip()
    if not who:
        return demand, ["need a nonempty who"]
    occupants = list(demand.get("occupants") or [])
    for row in occupants:
        if (
            str(row.get(WHO_KEY) or "") == who
            and str(row.get("slice_id") or "") == str(slice_id or "")
            and str(row.get("status") or "") == "active"
        ):
            return refresh_status(demand), []
    collision = [
        o
        for o in occupants
        if str(o.get("status") or "") == "active" and str(o.get(WHO_KEY) or "") != who
    ]
    occupants.append(
        {
            WHO_KEY: who,
            "slice_id": str(slice_id or ""),
            "occupied_at": ts or _utc_now(),
            "status": "active",
            "note": str(note or ""),
            "handoff_note": "",
            "next_decision": "",
            "collision_with": [o.get(WHO_KEY) for o in collision],
        }
    )
    demand["occupants"] = occupants
    saved, problems = save_demand(root, demand)
    if collision and not problems:
        return saved, []
    return saved, problems


def interrupt_occupant(root, demand_id, who, note="", next_decision="", ts=None):
    demand = load_demand(root, demand_id)
    if not demand or demand.get("error"):
        return None, ["demand not found: %s" % demand_id]
    who = str(who or "").strip()
    found = False
    occupants = []
    for row in demand.get("occupants") or []:
        row = dict(row)
        if str(row.get(WHO_KEY) or "") == who and str(row.get("status") or "") == "active":
            row["status"] = "interrupted"
            row["handoff_note"] = str(note or "")
            row["next_decision"] = str(next_decision or "")
            row["interrupted_at"] = ts or _utc_now()
            found = True
        occupants.append(row)
    if not found:
        return demand, ["no active occupant for who: %s" % who]
    demand["occupants"] = occupants
    return save_demand(root, demand)


def handoff_demand(
    root, demand_id, from_who, to_who, note="", next_decision="", slice_id="", ts=None
):
    demand = load_demand(root, demand_id)
    if not demand or demand.get("error"):
        return None, ["demand not found: %s" % demand_id]
    from_who = str(from_who or "").strip()
    to_who = str(to_who or "").strip()
    if not from_who or not to_who:
        return demand, ["need nonempty from_who and to_who"]
    occupants = []
    handed = False
    for row in demand.get("occupants") or []:
        row = dict(row)
        if str(row.get(WHO_KEY) or "") == from_who and str(row.get("status") or "") in (
            "active",
            "interrupted",
        ):
            row["status"] = "handed_off"
            row["handoff_note"] = str(note or "")
            row["next_decision"] = str(next_decision or "")
            row["handed_off_at"] = ts or _utc_now()
            row["handed_to"] = to_who
            handed = True
        occupants.append(row)
    if not handed:
        return demand, ["no active/interrupted occupant for who: %s" % from_who]
    occupants.append(
        {
            WHO_KEY: to_who,
            "slice_id": str(slice_id or ""),
            "occupied_at": ts or _utc_now(),
            "status": "active",
            "note": "handoff from %s" % from_who,
            "handoff_note": str(note or ""),
            "next_decision": str(next_decision or ""),
            "collision_with": [],
            "received_from": from_who,
        }
    )
    demand["occupants"] = occupants
    return save_demand(root, demand)


def complete_demand(root, demand_id, pointer, receipt="", who="", ts=None):
    demand = load_demand(root, demand_id)
    if not demand or demand.get("error"):
        return None, ["demand not found: %s" % demand_id]
    pointer = str(pointer or "").strip()
    if len(pointer) < 4:
        return demand, ["need a nonempty result.pointer"]
    demand["result"] = {
        "pointer": pointer,
        "receipt": str(receipt or ""),
        WHO_KEY: str(who or ""),
        "landed_at": ts or _utc_now(),
    }
    occupants = []
    for row in demand.get("occupants") or []:
        row = dict(row)
        if str(row.get("status") or "") == "active":
            row["status"] = "complete"
            row["completed_at"] = ts or _utc_now()
        occupants.append(row)
    demand["occupants"] = occupants
    return save_demand(root, demand)


def project(root, status_filter=""):
    rows = list_demands(root)
    if status_filter:
        wanted = str(status_filter or "").strip()
        if wanted not in STATUSES:
            return {
                "schema": SCHEMA,
                "n": 0,
                "demands": [],
                "error": "status filter must be one of open|occupied|done",
            }
        rows = [r for r in rows if derive_status(r) == wanted]
    return {
        "schema": SCHEMA,
        "n": len(rows),
        "demands": [
            {
                "id": r.get("id"),
                "status": derive_status(r),
                "title": _title_of(r),
                "current_prose": current_prose(r),
                "original_preserved": True,
                "corrections_n": len(r.get("corrections") or []),
                "occupants": r.get("occupants") or [],
                "result": r.get("result"),
                "source": (r.get("original") or {}).get("source") or "",
            }
            for r in rows
        ],
        "open": [r.get("id") for r in rows if derive_status(r) == "open"],
        "occupied": [r.get("id") for r in rows if derive_status(r) == "occupied"],
        "done": [r.get("id") for r in rows if derive_status(r) == "done"],
        "instrument": "host/demand_survive.py",
        "index": INDEX_REL,
        "store": STORE_DIR,
        "compatible": {
            "open_work": "host/open_work.py",
            "current_work": "host/current_work.py",
            "occupancy": "occupancy.md",
            "note": "Does not remint C1/G2/M3/R4 implementation files.",
        },
    }


def self_test():
    import tempfile

    root = tempfile.mkdtemp(prefix="demand-survive-")
    d, err = record_demand(
        root,
        "astra-d5-fixture-20260904-01",
        "Build demands that survive the conversation. Discover open work.",
        source="slack:C0BU51F1PL3/1788567261.579059",
        from_who="BRYCE",
        ts="2026-09-04T20:14:21Z",
    )
    assert err == [], err
    assert d["status"] == "open"
    assert d["original"]["prose"].startswith("Build demands")

    _, err2 = record_demand(
        root,
        "astra-d5-fixture-20260904-01",
        "Different prose must not erase the original.",
        source="noise",
    )
    assert err2 and "CONFLICT" in err2[0]

    d, err = occupy_demand(
        root,
        "astra-d5-fixture-20260904-01",
        "PEER_A",
        slice_id="a-slice",
        ts="2026-09-04T20:20:00Z",
    )
    assert err == []
    d, err = occupy_demand(
        root,
        "astra-d5-fixture-20260904-01",
        "PEER_B",
        slice_id="b-slice",
        ts="2026-09-04T20:20:05Z",
    )
    assert err == []
    active = [o for o in d["occupants"] if o["status"] == "active"]
    assert len(active) == 2
    assert d["status"] == "occupied"
    b = [o for o in active if o[WHO_KEY] == "PEER_B"][0]
    assert "PEER_A" in (b.get("collision_with") or [])

    d, err = append_correction(
        root,
        "astra-d5-fixture-20260904-01",
        "Ship and merge already approved; do not wait for another yes.",
        from_who="BRYCE",
        ts="2026-09-04T20:15:11Z",
    )
    assert err == []
    assert d["original"]["prose"].startswith("Build demands")
    assert len(d["corrections"]) == 1
    assert "Ship and merge" in current_prose(d)

    d, err = interrupt_occupant(
        root,
        "astra-d5-fixture-20260904-01",
        "PEER_A",
        note="context window ending",
        next_decision="finish tests then open PR",
        ts="2026-09-04T20:30:00Z",
    )
    assert err == []
    d, err = handoff_demand(
        root,
        "astra-d5-fixture-20260904-01",
        from_who="PEER_A",
        to_who="PEER_C",
        note="tests green locally; open PR next",
        next_decision="open PR and merge",
        slice_id="c-slice",
        ts="2026-09-04T20:31:00Z",
    )
    assert err == []
    whos = {o[WHO_KEY]: o["status"] for o in d["occupants"]}
    assert whos["PEER_A"] == "handed_off"
    assert whos["PEER_C"] == "active"
    assert whos["PEER_B"] == "active"

    d, err = complete_demand(
        root,
        "astra-d5-fixture-20260904-01",
        pointer="https://github.com/woahwhattheheck/commons/pull/9999",
        receipt="p/astra-d5-fixture-20260904-01.md",
        who="PEER_C",
        ts="2026-09-04T21:00:00Z",
    )
    assert err == []
    assert d["status"] == "done"
    assert d["result"]["pointer"].endswith("/9999")

    proj = project(root)
    assert "astra-d5-fixture-20260904-01" in proj["done"]
    assert proj["open"] == []
    index = rebuild_index(root)
    assert index["by_status"]["done"] == 1

    record_demand(
        root,
        "open-fixture-work-20260904-01",
        "Another prose demand waiting for a peer.",
        source="synthetic",
    )
    proj2 = project(root, status_filter="open")
    assert proj2["n"] == 1
    assert proj2["demands"][0]["id"] == "open-fixture-work-20260904-01"

    print("self-test ok")
    return 0


def _need(args, *names):
    missing = [n for n in names if not str(getattr(args, n, "") or "").strip()]
    if missing:
        sys.stderr.write("missing args: %s\n" % ", ".join(missing))
        return False
    return True


def main(argv=None):
    # Never an admission. Free-form CLI flags only — no verb/action enum window.
    parser = argparse.ArgumentParser(description="Demands that survive the conversation")
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--self-test", default=False, const=True, nargs="?")
    sub = parser.add_subparsers(dest="cmd")

    p_list = sub.add_parser("list", help="project demands")
    p_list.add_argument("--status", default="")

    p_show = sub.add_parser("show", help="show one demand")
    p_show.add_argument("--id", default="")

    p_rec = sub.add_parser("record", help="record a prose demand")
    p_rec.add_argument("--id", default="")
    p_rec.add_argument("--prose", default="")
    p_rec.add_argument("--source", default="")
    p_rec.add_argument("--from-who", default="")

    p_cor = sub.add_parser("correct", help="append owner correction; keep original")
    p_cor.add_argument("--id", default="")
    p_cor.add_argument("--prose", default="")
    p_cor.add_argument("--from-who", default="")

    p_occ = sub.add_parser("occupy", help="record occupancy (parallel visible)")
    p_occ.add_argument("--id", default="")
    p_occ.add_argument("--who", default="")
    p_occ.add_argument("--slice", dest="slice_id", default="")
    p_occ.add_argument("--note", default="")

    p_int = sub.add_parser("interrupt", help="mark builder interrupted")
    p_int.add_argument("--id", default="")
    p_int.add_argument("--who", default="")
    p_int.add_argument("--note", default="")
    p_int.add_argument("--next", dest="next_decision", default="")

    p_hand = sub.add_parser("handoff", help="hand demand to another builder")
    p_hand.add_argument("--id", default="")
    p_hand.add_argument("--from-who", default="")
    p_hand.add_argument("--to-who", default="")
    p_hand.add_argument("--note", default="")
    p_hand.add_argument("--next", dest="next_decision", default="")
    p_hand.add_argument("--slice", dest="slice_id", default="")

    p_done = sub.add_parser("complete", help="attach result pointer")
    p_done.add_argument("--id", default="")
    p_done.add_argument("--pointer", default="")
    p_done.add_argument("--receipt", default="")
    p_done.add_argument("--who", default="")

    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.cmd:
        parser.print_help()
        return 2

    root = args.root
    if args.cmd == "list":
        status = str(getattr(args, "status", "") or "").strip()
        if status and status not in STATUSES:
            sys.stderr.write("status must be open, occupied, or done\n")
            return 2
        json.dump(project(root, status_filter=status), sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    if args.cmd == "show":
        if not _need(args, "id"):
            return 2
        data = load_demand(root, args.id)
        if not data:
            sys.stderr.write("not found\n")
            return 1
        json.dump(refresh_status(data), sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    if args.cmd == "record":
        if not _need(args, "id", "prose"):
            return 2
        data, err = record_demand(
            root, args.id, args.prose, source=args.source, from_who=args.from_who
        )
    elif args.cmd == "correct":
        if not _need(args, "id", "prose"):
            return 2
        data, err = append_correction(
            root, args.id, args.prose, from_who=args.from_who
        )
    elif args.cmd == "occupy":
        if not _need(args, "id", "who"):
            return 2
        data, err = occupy_demand(
            root, args.id, args.who, slice_id=args.slice_id, note=args.note
        )
    elif args.cmd == "interrupt":
        if not _need(args, "id", "who"):
            return 2
        data, err = interrupt_occupant(
            root, args.id, args.who, note=args.note, next_decision=args.next_decision
        )
    elif args.cmd == "handoff":
        if not _need(args, "id", "from_who", "to_who"):
            return 2
        data, err = handoff_demand(
            root,
            args.id,
            args.from_who,
            args.to_who,
            note=args.note,
            next_decision=args.next_decision,
            slice_id=args.slice_id,
        )
    elif args.cmd == "complete":
        if not _need(args, "id", "pointer"):
            return 2
        data, err = complete_demand(
            root, args.id, args.pointer, receipt=args.receipt, who=args.who
        )
    else:
        parser.print_help()
        return 2

    if err:
        sys.stderr.write("\n".join(err) + "\n")
        if data:
            json.dump(data, sys.stdout, indent=2)
            sys.stdout.write("\n")
        return 1
    json.dump(data, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
