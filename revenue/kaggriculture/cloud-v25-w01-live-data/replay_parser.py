#!/usr/bin/env python3
"""Parse a Kaggriculture public replay into causal per-transition rows.

For replay transition t>=1, steps[t].action is interpreted against the prior
observation steps[t-1].observation and the current steps[t].observation is the
post-transition observation.  This matches inventory/money deltas in the pinned
1.32.7 public replays.  Only the requested own seat's private state is emitted;
rival-private state is never copied.
"""
from __future__ import annotations
import argparse, gzip, hashlib, json
from pathlib import Path
from typing import Any

OUR_TEAM = "Bryce Muhlnickel"
ANIMALS = ("COW", "SHEEP", "GOOSE")
CROPS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON")
PRODUCTS = CROPS + ("EGG", "MILK", "WOOL", "FERTILIZER")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def count_unlocked(farm: dict[str, Any]) -> int:
    value = farm.get("unlocked_quadrants")
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    # Fallback from the 10x10 tile encoding, counting unlocked 5x5 quadrants.
    tiles = farm.get("tiles") or []
    anchors = ((0, 0), (0, 5), (5, 0), (5, 5))
    return sum(1 for r,c in anchors if r < len(tiles) and c < len(tiles[r]) and tiles[r][c] != "LOCKED")


def sum_carried(private: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for bag in private.get("inventories") or []:
        if not isinstance(bag, dict):
            continue
        for key, value in bag.items():
            if isinstance(value, (int,float)) and not isinstance(value, bool):
                out[key] = out.get(key, 0) + int(value)
    return dict(sorted(out.items()))


def compact_action(action: Any) -> dict[str, Any]:
    if not isinstance(action, dict):
        action = {}
    farmer = action.get("farmer") or ["PASS"]
    hands = action.get("hands") if isinstance(action.get("hands"), list) else []
    market = action.get("market") if isinstance(action.get("market"), list) else []
    def op(order: Any) -> str | None:
        return order[0] if isinstance(order, list) and order and isinstance(order[0], str) else None
    counts: dict[str,int] = {}
    for order in [farmer, *hands, *market]:
        name = op(order)
        if name:
            counts[name] = counts.get(name, 0) + 1
    return {"farmer": farmer, "hands": hands, "market": market,
            "op_counts": dict(sorted(counts.items()))}


def public_farm(farm: dict[str, Any]) -> dict[str, Any]:
    return {
        "money": farm.get("money"),
        "hires_today": farm.get("hires_today"),
        "unlocked_quadrants": count_unlocked(farm),
        "farmer": farm.get("farmer"),
        "hand_count": len(farm.get("hands") or []),
    }


def private_own(obs: dict[str, Any]) -> dict[str, Any]:
    p = obs.get("private") if isinstance(obs.get("private"), dict) else {}
    shed = p.get("shed") if isinstance(p.get("shed"), dict) else {}
    seeds = p.get("seeds") if isinstance(p.get("seeds"), dict) else {}
    return {
        "shed": {k: int(shed.get(k,0)) for k in PRODUCTS + ANIMALS},
        "seeds": {k: int(seeds.get(k,0)) for k in CROPS},
        "carried": sum_carried(p),
    }


def market_snapshot(obs: dict[str, Any]) -> dict[str, Any]:
    m = obs.get("market") if isinstance(obs.get("market"), dict) else {}
    prices = m.get("prices") if isinstance(m.get("prices"), dict) else {}
    inventory = m.get("inventory") if isinstance(m.get("inventory"), dict) else {}
    return {
        "prices": {k: prices.get(k) for k in PRODUCTS},
        "inventory": {k: inventory.get(k) for k in PRODUCTS},
    }


def parse(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw = path.read_bytes()
    text = gzip.decompress(raw)
    replay = json.loads(text)
    info = replay.get("info") or {}
    teams = info.get("TeamNames") or []
    if OUR_TEAM not in teams:
        raise ValueError(f"{path}: {OUR_TEAM!r} not in TeamNames={teams!r}")
    seat = teams.index(OUR_TEAM)
    other = 1 - seat
    steps = replay.get("steps") or []
    if len(steps) < 2:
        raise ValueError(f"{path}: short replay")
    rewards = replay.get("rewards") or []
    index = {
        "episode_id": int(info.get("EpisodeId")),
        "info_seed": int(info.get("seed")),
        "configuration_seed": replay.get("configuration",{}).get("seed"),
        "team_names": teams,
        "own_seat": seat,
        "rival_seat": other,
        "rewards": rewards,
        "own_reward": rewards[seat] if len(rewards)>seat else None,
        "rival_reward": rewards[other] if len(rewards)>other else None,
        "result": ("WIN" if rewards[seat] > rewards[other] else
                   "LOSS" if rewards[seat] < rewards[other] else "TIE"),
        "steps": len(steps),
        "statuses": replay.get("statuses"),
        "module_version": replay.get("module_version"),
        "raw_gzip_bytes": len(raw),
        "raw_gzip_sha256": sha256_bytes(raw),
        "decompressed_bytes": len(text),
        "decompressed_sha256": sha256_bytes(text),
        "own_log": None,
        "own_log_status": "not_found_in_shared_titan-v2-runs_search",
    }
    rows = []
    for t in range(1, len(steps)):
        pre_rec = steps[t-1][seat]
        post_rec = steps[t][seat]
        rival_post_rec = steps[t][other]
        pre = pre_rec.get("observation") or {}
        post = post_rec.get("observation") or {}
        rival_post = rival_post_rec.get("observation") or {}
        action = compact_action(post_rec.get("action"))
        own_pre_farms = pre.get("farms") or []
        own_post_farms = post.get("farms") or []
        rival_post_farms = rival_post.get("farms") or []
        own_pre = own_pre_farms[seat] if len(own_pre_farms)>seat else {}
        own_post = own_post_farms[seat] if len(own_post_farms)>seat else {}
        rival_pub = rival_post_farms[other] if len(rival_post_farms)>other else {}
        pre_money = own_pre.get("money")
        post_money = own_post.get("money")
        row = {
            "episode_id": index["episode_id"],
            "info_seed": index["info_seed"],
            "own_seat": seat,
            "transition": t,
            "pre_day": pre.get("day"), "pre_hour": pre.get("hour"),
            "post_day": post.get("day"), "post_hour": post.get("hour"),
            "eod_transition": pre.get("day") != post.get("day"),
            "agent_status": post_rec.get("status"),
            "step_reward": post_rec.get("reward"),
            "pre_remaining_overage_time": pre.get("remainingOverageTime"),
            "post_remaining_overage_time": post.get("remainingOverageTime"),
            "own_pre": public_farm(own_pre),
            "own_post": public_farm(own_post),
            "rival_post_public": public_farm(rival_pub),
            "own_money_delta": (post_money - pre_money if isinstance(pre_money,(int,float)) and isinstance(post_money,(int,float)) else None),
            "action": action,
            "own_private_post": private_own(post),
            "market_pre": market_snapshot(pre),
            "market_post": market_snapshot(post),
        }
        rows.append(row)
    # Strong causal consistency boundary used by W01 consumers.
    if len(rows) != len(steps)-1:
        raise AssertionError("transition count mismatch")
    return index, rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("replays", nargs="+", type=Path)
    ap.add_argument("--index", type=Path, required=True)
    ap.add_argument("--timeline", type=Path, required=True)
    args = ap.parse_args()
    indexes=[]; all_rows=[]
    for p in args.replays:
        idx, rows=parse(p); indexes.append(idx); all_rows.extend(rows)
    indexes.sort(key=lambda x:x["episode_id"])
    args.index.write_text(json.dumps(indexes,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
    with args.timeline.open("wb") as raw_out:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw_out, mtime=0) as gz:
            for row in all_rows:
                line=(json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode("utf-8")
                gz.write(line)
    print(json.dumps({"episodes":len(indexes),"transitions":len(all_rows),
                      "losses":sum(x["result"]=="LOSS" for x in indexes)},sort_keys=True))

if __name__ == "__main__": main()
