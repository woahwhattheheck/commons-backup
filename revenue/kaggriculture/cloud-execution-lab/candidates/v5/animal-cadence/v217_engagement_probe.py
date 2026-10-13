# SPDX-License-Identifier: Apache-2.0
"""Build an observation-only V217 starvation-rescue engagement probe.

The probe preserves the exact production-v3 action stream. It instruments only
V217's existing global future-FEED veto to ask whether the *same* planner would
have produced a rescue after excluding starving animals already covered by an
authored FEED target. A source-transformed copy of the existing offline
evaluator carries the cumulative probe snapshot beside the action IPC packet;
the engine still receives the original action object only.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import importlib.util
import json
import sys
from pathlib import Path, PurePosixPath
import tarfile

PRODUCTION_SHA = "20f201161b14af7755146b08207593f9fa5df641d2f31e680792ea62c0e24239"
ROUTER = "r04_full_router.py"
ROUTER_SHA = "41ea55c5f20c43cd58c5099fbadb212de62ec95a95dfc2e6e1e19c3d4d55b39a"
EVALUATOR_SHA = "e30b3108e0027477ab7ddbc057892a241c41a1f2b38f72caf267477877c4333c"
PRODUCTION_MEMBERS = 92


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def archive_members(raw: bytes, expected_sha: str = PRODUCTION_SHA) -> dict[str, bytes]:
    if digest(raw) != expected_sha:
        raise ValueError("production archive identity mismatch")
    result: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        for member in archive.getmembers():
            name = member.name
            rel = PurePosixPath(name)
            if (not member.isfile() or name in result or rel.is_absolute()
                    or ".." in rel.parts or "\\" in name or str(rel) != name):
                raise ValueError("noncanonical archive member: " + name)
            extracted = archive.extractfile(member)
            if extracted is None:
                raise ValueError("missing archive payload: " + name)
            result[name] = extracted.read()
    return result


def archive_bytes(files: dict[str, bytes]) -> bytes:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as archive:
        for name, body in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.size = len(body)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(body))
    packed = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=packed, mtime=0) as zipped:
        zipped.write(raw.getvalue())
    return packed.getvalue()


_PROBE_HELPERS = r'''_V217_PROBE_REPORT={'schema':'titan-v5-v217-engagement/v1','global_feed_veto':0,
                    'coverage_certified':0,'counterfactual_plan':0,'events':[]}

def _v217_probe_commands(action, actors):
    if not isinstance(action, dict):
        return None
    farmer=action.get('farmer')
    hands=action.get('hands')
    if not isinstance(farmer,list) or not farmer or not isinstance(hands,list):
        return None
    commands=[farmer]+hands
    if len(commands)!=actors or any(not isinstance(cmd,list) or not cmd for cmd in commands):
        return None
    return commands

def _v217_probe_tile(tiles,pos):
    x,y=pos
    if type(x) is not int or type(y) is not int or y<0 or y>=len(tiles):
        return None,False
    row=tiles[y]
    if not isinstance(row,list) or x<0 or x>=len(row):
        return None,False
    return row[x],True

def _v217_probe_advance(tiles,pos,cmd):
    if cmd[0] not in _V217_MOVES:
        return pos
    dx,dy=_V217_MOVES[cmd[0]]
    nxt=(pos[0]+dx,pos[1]+dy)
    tile,valid=_v217_probe_tile(tiles,nxt)
    if not valid or tile=='LOCKED' or (isinstance(tile,dict) and tile.get('kind')=='WEED'):
        return None
    return nxt

def _v217_probe_path(tiles,start,target):
    pos=start;moves=[]
    while pos[0]!=target[0]:
        move='EAST' if pos[0]<target[0] else 'WEST'
        nxt=_v217_probe_advance(tiles,pos,[move])
        if nxt is None:
            return None
        moves.append(move);pos=nxt
    while pos[1]!=target[1]:
        move='SOUTH' if pos[1]<target[1] else 'NORTH'
        nxt=_v217_probe_advance(tiles,pos,[move])
        if nxt is None:
            return None
        moves.append(move);pos=nxt
    return moves

def _v217_probe_feed_coverage(view,action,tape,step,end):
    positions=[tuple(pos) for pos in view.positions]
    if (not positions or any(len(pos)!=2 or any(type(v) is not int for v in pos)
                             for pos in positions)):
        return None
    tiles=view.tiles
    if not isinstance(tiles,list):
        return None
    targets=set();count=0
    sequence=[action]+list(tape[step+1:end])
    for planned in sequence:
        commands=_v217_probe_commands(planned,len(positions))
        if commands is None:
            return None
        for actor,cmd in enumerate(commands):
            if cmd[0]=='FEED':
                tile,valid=_v217_probe_tile(tiles,positions[actor])
                if (not valid or not isinstance(tile,dict)
                        or tile.get('animal') not in ('GOOSE','COW','SHEEP')):
                    return None
                targets.add(positions[actor]);count+=1
        next_positions=[]
        for actor,cmd in enumerate(commands):
            nxt=_v217_probe_advance(tiles,positions[actor],cmd)
            if nxt is None:
                return None
            next_positions.append(nxt)
        positions=next_positions
    return frozenset(targets),count

def _v217_probe_observe(view,st,step,action,pending,tape,end):
    _V217_PROBE_REPORT['global_feed_veto']+=1
    if pending:
        return
    coverage=_v217_probe_feed_coverage(view,action,tape,step,end)
    if coverage is None:
        return
    feed_targets,future_feed_count=coverage
    _V217_PROBE_REPORT['coverage_certified']+=1
    reserved_wheat=0
    for planned in tape[step:end]:
        for cmd in [planned.get('farmer') or []]+list(planned.get('hands') or []):
            if len(cmd)>=2 and cmd[:2]==['PICKUP','WHEAT']:
                qty=cmd[2] if len(cmd)>2 else 1
                if type(qty) is not int or qty<0:
                    return
                reserved_wheat+=qty
    start=tuple(view.positions[0])
    inventory=view.inventory(0)
    if not isinstance(inventory,dict):
        return
    wheat=inventory.get('WHEAT',0)
    if type(wheat) is not int or wheat<0:
        return
    need_pickup=wheat<1
    if need_pickup:
        if any(type(v) is not int or v<0 or v for v in inventory.values()) or not view.beside_shed(start):
            return
        market=action.get('market')
        if not isinstance(market,list):
            return
        if any(isinstance(order,list) and len(order)>1 and order[1]=='WHEAT' for order in market):
            return
        projected=projected_shed(action,view)
        projected_wheat=projected.get('WHEAT',0)
        if type(projected_wheat) is not int or projected_wheat<max(2,reserved_wheat+1):
            return
    targets=[]
    for y,row in enumerate(view.tiles):
        if not isinstance(row,list):
            return
        for x,tile in enumerate(row):
            if not (isinstance(tile,dict) and tile.get('animal') in ('GOOSE','COW','SHEEP')):
                continue
            strikes=tile.get('consecutive_unfed')
            if type(strikes) is not int or strikes<0:
                return
            if tile.get('fed_today') is False and strikes>=1 and (x,y) not in feed_targets:
                targets.append((abs(x-start[0])+abs(y-start[1]),y,x))
    for distance,y,x in sorted(targets):
        moves=_v217_probe_path(view.tiles,start,(x,y))
        if moves is None:
            continue
        opposite={'EAST':'WEST','WEST':'EAST','NORTH':'SOUTH','SOUTH':'NORTH'}
        commands=([['PICKUP','WHEAT']] if need_pickup else [])+[[m] for m in moves]+[['FEED']]+[[opposite[m]] for m in reversed(moves)]
        if len(commands)>end-step or any(_v217_farmer(tape,step+i)!=['PASS'] for i in range(len(commands))):
            continue
        pos=start;safe=True
        for cmd in commands:
            nxt=_v217_probe_advance(view.tiles,pos,cmd)
            if nxt is None:
                safe=False;break
            pos=nxt
        if not safe or pos!=start:
            continue
        _V217_PROBE_REPORT['counterfactual_plan']+=1
        events=_V217_PROBE_REPORT['events']
        if len(events)<64:
            events.append({'step':step,'route':st.get('plan'),'target':[x,y],
                           'feed_targets':[list(p) for p in sorted(feed_targets)],
                           'future_feed_count':future_feed_count,'needs_pickup':bool(need_pickup),
                           'command_count':len(commands)})
        return'''


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"expected exactly one {label} seam")
    return source.replace(old, new, 1)


def instrument_router(source: bytes, expected_sha: str | None = ROUTER_SHA) -> bytes:
    if expected_sha is not None and digest(source) != expected_sha:
        raise ValueError("router source identity mismatch")
    text = source.decode("utf-8")
    moves = "_V217_MOVES={'EAST':(1,0),'WEST':(-1,0),'NORTH':(0,-1),'SOUTH':(0,1)}\n"
    text = _replace_once(text, moves, moves + "\n" + _PROBE_HELPERS + "\n", "V217 moves")
    veto = "            if cmd and cmd[0] == 'FEED':\n                return None"
    observed = "            if cmd and cmd[0] == 'FEED':\n                try:\n                    _v217_probe_observe(view,st,step,action,pending,tape,end)\n                except Exception:\n                    pass\n                return None"
    text = _replace_once(text, veto, observed, "V217 global FEED veto")
    return text.encode("utf-8")


def instrument_evaluator(source: bytes, expected_sha: str | None = EVALUATOR_SHA) -> bytes:
    if expected_sha is not None and digest(source) != expected_sha:
        raise ValueError("evaluator source identity mismatch")
    text = source.decode("utf-8")
    send_old = '''                send({"kind": "action", "action": action, "call_seconds": seconds,\n                      "call_cpu_seconds": cpu_seconds, **usage()})'''
    send_new = '''                probe = None\n                module = sys.modules.get("r04_full_router")\n                if module is not None:\n                    value = getattr(module, "_V217_PROBE_REPORT", None)\n                    if isinstance(value, dict):\n                        probe = value\n                send({"kind": "action", "action": action, "call_seconds": seconds,\n                      "call_cpu_seconds": cpu_seconds, "v217_probe": probe, **usage()})'''
    text = _replace_once(text, send_old, send_new, "worker action response")
    action_old = '                actions.append(response["action"])'
    action_new = '''                actions.append(response["action"])\n                if seat == candidate_seat and isinstance(response.get("v217_probe"), dict):\n                    result["v217_probe"] = response["v217_probe"]'''
    text = _replace_once(text, action_old, action_new, "play action append")
    return text.encode("utf-8")


def build_probe(production_raw: bytes, evaluator_raw: bytes) -> tuple[bytes, bytes, dict]:
    files = archive_members(production_raw)
    if ROUTER not in files or digest(files[ROUTER]) != ROUTER_SHA:
        raise ValueError("production router member mismatch")
    if len(files) != PRODUCTION_MEMBERS:
        raise ValueError("production archive member count mismatch")
    if digest(archive_bytes(files)) != PRODUCTION_SHA:
        raise ValueError("production archive does not reproduce canonically")
    before = {name: digest(body) for name, body in files.items()}
    files[ROUTER] = instrument_router(files[ROUTER])
    after = {name: digest(body) for name, body in files.items()}
    changed = sorted(name for name in before if before[name] != after[name])
    if changed != [ROUTER]:
        raise ValueError("probe must change only r04_full_router.py")
    candidate = archive_bytes(files)
    evaluator = instrument_evaluator(evaluator_raw)
    receipt = {
        "schema": "titan-v5-v217-engagement-probe/v1",
        "production_archive_sha256": PRODUCTION_SHA,
        "candidate_archive_sha256": digest(candidate),
        "member_count": len(files),
        "changed_members": changed,
        "router_before_sha256": ROUTER_SHA,
        "router_after_sha256": digest(files[ROUTER]),
        "evaluator_before_sha256": EVALUATOR_SHA,
        "evaluator_after_sha256": digest(evaluator),
        "action_semantics": "unchanged; probe snapshot is evaluator IPC sidecar only",
        "promotion_hold": True,
    }
    return candidate, evaluator, receipt


def _publication_helper():
    helper = Path(__file__).resolve().parent.parent / "selective-carrot" / "publication_custody.py"
    if not helper.is_file():
        raise FileNotFoundError("shared publication_custody.py is required")
    spec = importlib.util.spec_from_file_location("titan_v5_publication_custody", helper)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load shared publication custody helper")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production", type=Path, required=True)
    parser.add_argument("--evaluator", type=Path, required=True)
    parser.add_argument("--candidate-tar", type=Path, required=True)
    parser.add_argument("--evaluator-out", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    candidate, evaluator, receipt = build_probe(args.production.read_bytes(), args.evaluator.read_bytes())
    receipt_bytes = (json.dumps(receipt, indent=2) + "\n").encode()
    _publication_helper().publish_exclusive([
        (args.candidate_tar, candidate),
        (args.evaluator_out, evaluator),
        (args.receipt, receipt_bytes),
    ])
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
