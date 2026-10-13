# SPDX-License-Identifier: Apache-2.0
"""Witnessed ordering for the existing mechanics miner (no gameplay logic).

seqN is recorded player chronology, NOT causality or same-actor identity.
actor_seqN additionally requires a known unit actor. Equal-step market order
is usable only with explicit unique raw slots; CSV order is never evidence.
Ambiguous records are barriers, not records that may be silently skipped.
"""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Callable, Iterable, Iterator, TypeVar

E = TypeVar("E")


def _known(value: object) -> bool:
    return value is not None and str(value).strip() not in ("", "?")


def _slot(value: object) -> bool:
    return type(value) is int and value >= 0


def _windows(groups: Iterable[list[E] | None], prefix: str,
             token: Callable[[E], str]) -> Iterator[tuple[str, tuple[E, ...]]]:
    previous: deque[E] = deque(maxlen=3)
    for group in groups:
        if group is None:
            previous.clear()
            continue
        for event in group:
            previous.append(event)
            for width in (2, 3):
                if len(previous) >= width:
                    witness = tuple(previous)[-width:]
                    yield f"{prefix}{width}|" + ">".join(map(token, witness)), witness


def sequence_windows(events: Iterable[E], token: Callable[[E], str]
                     ) -> Iterator[tuple[str, tuple[E, ...]]]:
    """Emit features and exact input records establishing their ordering.

    Missing seats suppress sequences. Unit simultaneous rows interrupt the
    player chronology but can still contribute independent actor sequences.
    An unknown-actor unit row interrupts every actor stream at that step.
    Gaps in steps are allowed: these are recorded-event motifs, not a claim
    of consecutive callbacks, successful execution, or filled orders.
    """
    streams = defaultdict(list)
    for event in events:
        if _known(event.player):
            streams[(event.team, event.match, event.player, event.source)].append(event)
    for key in sorted(streams):
        rows = streams[key]
        by_step = defaultdict(list)
        for event in rows:
            by_step[event.step].append(event)
        chronology = []
        for step in sorted(by_step):
            group = by_step[step]
            if len(group) == 1:
                chronology.append(group)
            elif key[-1] == "market":
                slots = [getattr(e, "slot", None) for e in group]
                if all(_slot(s) for s in slots) and len(set(slots)) == len(slots):
                    chronology.append(sorted(group, key=lambda e: e.slot))
                else:
                    chronology.append(None)
            else:
                chronology.append(None)
        yield from _windows(chronology, "seq", token)
        if key[-1] != "unit":
            continue
        actor_steps = defaultdict(lambda: defaultdict(list))
        barriers = set()
        for event in rows:
            actor = getattr(event, "actor", None)
            if not _known(actor):
                barriers.add(event.step)
            else:
                actor_steps[str(actor)][event.step].append(event)
        for actor in sorted(actor_steps):
            timeline = actor_steps[actor]
            groups = []
            for step in sorted(set(timeline) | barriers):
                group = timeline.get(step, [])
                if step in barriers or len(group) != 1:
                    groups.append(None)
                else:
                    groups.append(group)
            yield from _windows(groups, "actor_seq", token)


def witness_record(event: E) -> dict:
    """The original row locator survives shuffle/sorting, including seat/actor."""
    return {name: getattr(event, name, None) for name in
            ("match", "team", "player", "step", "source", "verb", "target",
             "qty", "ordinal", "actor", "slot")}


def collect_witnesses(events: Iterable[E], token: Callable[[E], str], *,
                      limit_per_feature: int = 3) -> dict:
    if type(limit_per_feature) is not int or limit_per_feature < 1:
        raise ValueError("limit_per_feature must be a positive integer")
    found = defaultdict(list)
    for feature, witness in sequence_windows(events, token):
        row = [witness_record(e) for e in witness]
        if len(found[feature]) < limit_per_feature and row not in found[feature]:
            found[feature].append(row)
    return dict(sorted(found.items()))
