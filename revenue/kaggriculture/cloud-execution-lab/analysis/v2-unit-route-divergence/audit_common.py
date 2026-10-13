#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Strict input loading and transition primitives for the unit-route audit."""
from __future__ import annotations

from dataclasses import dataclass
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = 1
MAX_COMPRESSED_BYTES = 64 * 1024 * 1024
MAX_JSON_BYTES = 128 * 1024 * 1024
MOVES = {
    "NORTH": (0, -1),
    "SOUTH": (0, 1),
    "WEST": (-1, 0),
    "EAST": (1, 0),
}
QUANTITY_MARKET_OPS = {
    "SELL", "BUY_PRODUCT", "BUY_SEED", "BUY_ANIMAL",
}
QUANTITY_UNIT_OPS = {"PICKUP", "PLACE"}

class AuditError(ValueError):
    """Raised when an input cannot support an exact, fail-closed report."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise AuditError(f"duplicate JSON key: {key!r}")
        out[key] = value
    return out


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest(value: Any) -> str:
    return sha256_bytes(canonical_json(value))


def _strict_int(value: Any, label: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AuditError(f"{label} must be an integer, not {type(value).__name__}")
    if minimum is not None and value < minimum:
        raise AuditError(f"{label} must be >= {minimum}")
    return value


def _strict_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AuditError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise AuditError(f"{label} must be a finite number")
    return result


def _require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AuditError(f"{label} must be an object")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise AuditError(f"{label} must be an array")
    return value


def _read_limited(path: Path, limit: int) -> bytes:
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise AuditError(f"{path.name}: input exceeds {limit} bytes")
    return data


def _inflate_limited(raw: bytes, name: str) -> bytes:
    if raw[:2] != b"\x1f\x8b":
        if len(raw) > MAX_JSON_BYTES:
            raise AuditError(f"{name}: JSON exceeds {MAX_JSON_BYTES} bytes")
        return raw
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(raw), mode="rb") as handle:
            data = handle.read(MAX_JSON_BYTES + 1)
    except (OSError, EOFError) as exc:
        raise AuditError(f"{name}: invalid gzip stream: {exc}") from exc
    if len(data) > MAX_JSON_BYTES:
        raise AuditError(f"{name}: inflated JSON exceeds {MAX_JSON_BYTES} bytes")
    return data


def _parse_json_bytes(data: bytes, name: str) -> Any:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AuditError(f"{name}: JSON is not UTF-8") from exc
    try:
        return json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except AuditError:
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        raise AuditError(f"{name}: invalid JSON: {exc}") from exc


def _validate_action_atom(action: Any, label: str, *, market: bool) -> list[Any]:
    row = _require_list(action, label)
    if not row:
        if market:
            return row
        raise AuditError(f"{label}: unit action cannot be empty")
    if not isinstance(row[0], str) or not row[0]:
        raise AuditError(f"{label}[0] must be a nonempty string")
    op = row[0]
    if market and op in QUANTITY_MARKET_OPS:
        if len(row) != 3:
            raise AuditError(f"{label}: {op} must have exactly three fields")
        _strict_int(row[2], f"{label}[2]", minimum=0)
    if not market and op in QUANTITY_UNIT_OPS and len(row) > 2:
        _strict_int(row[2], f"{label}[2]", minimum=0)
    return row


def _validate_action(action: Any, label: str) -> dict[str, Any]:
    value = _require_dict(action, label)
    required = {"farmer", "hands", "market"}
    if not required.issubset(value):
        missing = sorted(required - set(value))
        raise AuditError(f"{label}: missing keys {missing}")
    _validate_action_atom(value["farmer"], f"{label}.farmer", market=False)
    hands = _require_list(value["hands"], f"{label}.hands")
    for index, row in enumerate(hands):
        _validate_action_atom(row, f"{label}.hands[{index}]", market=False)
    market = _require_list(value["market"], f"{label}.market")
    for index, row in enumerate(market):
        _validate_action_atom(row, f"{label}.market[{index}]", market=True)
    return value


def _validate_position(value: Any, label: str) -> list[int]:
    row = _require_list(value, label)
    if len(row) != 2:
        raise AuditError(f"{label} must contain exactly x,y")
    return [
        _strict_int(row[0], f"{label}[0]", minimum=0),
        _strict_int(row[1], f"{label}[1]", minimum=0),
    ]


def _validate_inventory(value: Any, label: str) -> dict[str, int]:
    row = _require_dict(value, label)
    for key, quantity in row.items():
        if not isinstance(key, str) or not key:
            raise AuditError(f"{label}: inventory keys must be nonempty strings")
        _strict_int(quantity, f"{label}.{key}", minimum=0)
    return row  # type: ignore[return-value]


def _validate_observation(
    observation: Any,
    label: str,
    *,
    expected_step: int,
    seat: int,
    team_count: int,
    turns_per_day: int,
) -> dict[str, Any]:
    obs = _require_dict(observation, label)
    # Hosted Kaggle replay observations normally omit the synthetic ``step``
    # injected by the local driver.  Bind the frame by its canonical day/hour
    # pair, and validate ``step`` only when a producer actually retained it.
    retained_step = obs.get("step")
    if retained_step is not None:
        step = _strict_int(retained_step, f"{label}.step", minimum=0)
        if step != expected_step:
            raise AuditError(f"{label}.step={step}, expected {expected_step}")
    player = _strict_int(obs.get("player"), f"{label}.player", minimum=0)
    if player != seat:
        raise AuditError(f"{label}.player={player}, expected seat {seat}")
    day = _strict_int(obs.get("day"), f"{label}.day", minimum=0)
    hour = _strict_int(obs.get("hour"), f"{label}.hour", minimum=0)
    if day != expected_step // turns_per_day or hour != expected_step % turns_per_day:
        raise AuditError(f"{label}: day/hour disagree with step")
    farms = _require_list(obs.get("farms"), f"{label}.farms")
    if len(farms) != team_count:
        raise AuditError(f"{label}.farms has {len(farms)} entries, expected {team_count}")
    farm = _require_dict(farms[seat], f"{label}.farms[{seat}]")
    _strict_number(farm.get("money"), f"{label}.farms[{seat}].money")
    _strict_int(farm.get("hires_today"), f"{label}.farms[{seat}].hires_today", minimum=0)
    _validate_position(farm.get("farmer"), f"{label}.farms[{seat}].farmer")
    hands = _require_list(farm.get("hands"), f"{label}.farms[{seat}].hands")
    for index, position in enumerate(hands):
        _validate_position(position, f"{label}.farms[{seat}].hands[{index}]")
    tiles = _require_list(farm.get("tiles"), f"{label}.farms[{seat}].tiles")
    if not tiles:
        raise AuditError(f"{label}.farms[{seat}].tiles cannot be empty")
    size = len(tiles)
    for y, tile_row in enumerate(tiles):
        row = _require_list(tile_row, f"{label}.farms[{seat}].tiles[{y}]")
        if len(row) != size:
            raise AuditError(f"{label}: tile board must be square")
    private = _require_dict(obs.get("private"), f"{label}.private")
    inventories = _require_list(private.get("inventories"), f"{label}.private.inventories")
    if len(inventories) != 1 + len(hands):
        raise AuditError(
            f"{label}: inventories={len(inventories)} but actors={1 + len(hands)}"
        )
    for index, inventory in enumerate(inventories):
        _validate_inventory(inventory, f"{label}.private.inventories[{index}]")
    _validate_inventory(private.get("seeds"), f"{label}.private.seeds")
    _validate_inventory(private.get("shed"), f"{label}.private.shed")
    return obs


@dataclass(frozen=True)
class Replay:
    declared_name: str
    path: Path
    raw_sha256: str
    json_sha256: str
    root: dict[str, Any]
    episode_id: int
    seed: int
    seat: int
    opponent: str
    agent_name: str
    episode_steps: int
    turns_per_day: int
    max_market_orders: int

    @property
    def reward(self) -> float:
        return float(self.root["rewards"][self.seat])

    @property
    def rival_reward(self) -> float:
        return float(self.root["rewards"][1 - self.seat])

    def row(self, step: int) -> dict[str, Any]:
        return self.root["steps"][step][self.seat]

    def action(self, step: int) -> dict[str, Any]:
        return self.row(step)["action"]

    def observation(self, step: int) -> dict[str, Any]:
        return self.row(step)["observation"]

    def own_farm(self, step: int) -> dict[str, Any]:
        return self.observation(step)["farms"][self.seat]

    def private(self, step: int) -> dict[str, Any]:
        return self.observation(step)["private"]


def _load_manifest(path: Path) -> dict[str, Any]:
    raw = _read_limited(path, 2 * 1024 * 1024)
    value = _parse_json_bytes(raw, path.name)
    manifest = _require_dict(value, "manifest")
    version = _strict_int(manifest.get("schema_version"), "manifest.schema_version", minimum=1)
    if version != SCHEMA_VERSION:
        raise AuditError(f"unsupported manifest schema_version {version}")
    agent = manifest.get("agent_name")
    if not isinstance(agent, str) or not agent:
        raise AuditError("manifest.agent_name must be a nonempty string")
    _strict_int(manifest.get("expected_episode_steps"), "manifest.expected_episode_steps", minimum=2)
    rows = _require_list(manifest.get("replays"), "manifest.replays")
    if len(rows) < 2:
        raise AuditError("manifest must contain at least two replays")
    return manifest


def _load_replay(
    declaration: Mapping[str, Any], *, agent_name: str, expected_steps: int, replay_dir: Path,
) -> Replay:
    name = declaration.get("file")
    if not isinstance(name, str) or not name or Path(name).name != name:
        raise AuditError("replay.file must be one basename")
    path = replay_dir / name
    if not path.is_file():
        raise AuditError(f"missing replay: {name}")
    raw = _read_limited(path, MAX_COMPRESSED_BYTES)
    raw_sha = sha256_bytes(raw)
    expected_sha = declaration.get("gzip_sha256")
    if not isinstance(expected_sha, str) or len(expected_sha) != 64:
        raise AuditError(f"{name}: declaration gzip_sha256 must be 64 hex characters")
    try:
        int(expected_sha, 16)
    except ValueError as exc:
        raise AuditError(f"{name}: declaration gzip_sha256 is not hexadecimal") from exc
    if raw_sha != expected_sha.lower():
        raise AuditError(f"{name}: gzip SHA mismatch")
    data = _inflate_limited(raw, name)
    root = _require_dict(_parse_json_bytes(data, name), name)
    info = _require_dict(root.get("info"), f"{name}.info")
    episode_id = _strict_int(info.get("EpisodeId"), f"{name}.info.EpisodeId", minimum=0)
    seed = _strict_int(info.get("seed"), f"{name}.info.seed", minimum=0)
    teams = _require_list(info.get("TeamNames"), f"{name}.info.TeamNames")
    if len(teams) != 2 or any(not isinstance(team, str) or not team for team in teams):
        raise AuditError(f"{name}: exactly two nonempty TeamNames are required")
    seats = [index for index, team in enumerate(teams) if team == agent_name]
    if len(seats) != 1:
        raise AuditError(f"{name}: agent {agent_name!r} must occur exactly once")
    seat = seats[0]
    declared_episode = _strict_int(declaration.get("episode_id"), f"{name}.episode_id", minimum=0)
    declared_seed = _strict_int(declaration.get("seed"), f"{name}.seed", minimum=0)
    declared_seat = _strict_int(declaration.get("seat"), f"{name}.seat", minimum=0)
    opponent = declaration.get("opponent")
    if episode_id != declared_episode or seed != declared_seed or seat != declared_seat:
        raise AuditError(f"{name}: episode/seed/seat declaration mismatch")
    if opponent != teams[1 - seat]:
        raise AuditError(f"{name}: opponent declaration mismatch")
    configuration = _require_dict(root.get("configuration"), f"{name}.configuration")
    episode_steps = _strict_int(
        configuration.get("episodeSteps"), f"{name}.configuration.episodeSteps", minimum=2
    )
    if episode_steps != expected_steps:
        raise AuditError(f"{name}: episodeSteps={episode_steps}, expected {expected_steps}")
    turns_per_day = _strict_int(
        configuration.get("turnsPerDay"), f"{name}.configuration.turnsPerDay", minimum=1
    )
    max_market_orders = _strict_int(
        configuration.get("maxMarketOrdersPerTurn", 10),
        f"{name}.configuration.maxMarketOrdersPerTurn", minimum=1,
    )
    steps = _require_list(root.get("steps"), f"{name}.steps")
    if len(steps) != episode_steps:
        raise AuditError(f"{name}: steps={len(steps)}, expected {episode_steps}")
    rewards = _require_list(root.get("rewards"), f"{name}.rewards")
    if len(rewards) != 2:
        raise AuditError(f"{name}: rewards must have two entries")
    for index, reward in enumerate(rewards):
        _strict_number(reward, f"{name}.rewards[{index}]")
    for step, frame in enumerate(steps):
        rows = _require_list(frame, f"{name}.steps[{step}]")
        if len(rows) != 2:
            raise AuditError(f"{name}.steps[{step}] must contain two agent rows")
        row = _require_dict(rows[seat], f"{name}.steps[{step}][{seat}]")
        _validate_action(row.get("action"), f"{name}.steps[{step}][{seat}].action")
        _validate_observation(
            row.get("observation"), f"{name}.steps[{step}][{seat}].observation",
            expected_step=step, seat=seat, team_count=2, turns_per_day=turns_per_day,
        )
    replay = Replay(
        declared_name=name,
        path=path,
        raw_sha256=raw_sha,
        json_sha256=sha256_bytes(data),
        root=root,
        episode_id=episode_id,
        seed=seed,
        seat=seat,
        opponent=teams[1 - seat],
        agent_name=agent_name,
        episode_steps=episode_steps,
        turns_per_day=turns_per_day,
        max_market_orders=max_market_orders,
    )
    _prove_orientation(replay)
    return replay


def _hire_count(replay: Replay, step: int) -> int:
    market = replay.action(step)["market"][: replay.max_market_orders]
    return sum(1 for order in market if order and order[0] == "HIRE")


def _prove_orientation(replay: Replay) -> None:
    witnesses = 0
    for step in range(1, replay.episode_steps):
        previous = replay.observation(step - 1)
        current = replay.observation(step)
        if previous["day"] != current["day"]:
            continue
        before = len(replay.own_farm(step - 1)["hands"])
        after = len(replay.own_farm(step)["hands"])
        delta = after - before
        hires = _hire_count(replay, step)
        if delta < 0:
            raise AuditError(
                f"{replay.declared_name}: hands decreased inside a day at step {step}"
            )
        if delta > hires:
            raise AuditError(
                f"{replay.declared_name}: step {step} adds {delta} hands but row action has "
                f"only {hires} executable HIRE orders; action/observation alignment is invalid"
            )
        if delta > 0:
            if hires == 0:
                raise AuditError(
                    f"{replay.declared_name}: hand increase without aligned HIRE at step {step}"
                )
            witnesses += 1
    if witnesses == 0:
        raise AuditError(f"{replay.declared_name}: no same-day HIRE transition proves orientation")


def _physical_state(replay: Replay, step: int) -> dict[str, Any]:
    farm = replay.own_farm(step)
    private = replay.private(step)
    return {
        "farmer": farm["farmer"],
        "hands": farm["hands"],
        "hires_today": farm["hires_today"],
        "tiles": farm["tiles"],
        "unlocked_quadrants": farm.get("unlocked_quadrants", []),
        "inventories": private["inventories"],
        "seeds": private["seeds"],
        "shed": private["shed"],
    }


def _economic_state(replay: Replay, step: int) -> dict[str, Any]:
    obs = replay.observation(step)
    farm = replay.own_farm(step)
    return {
        **_physical_state(replay, step),
        "money": farm["money"],
        "market": obs.get("market"),
        "town": obs.get("town"),
    }


def _unit_action(action: Mapping[str, Any]) -> dict[str, Any]:
    return {"farmer": action["farmer"], "hands": action["hands"]}

