#!/usr/bin/env python3
"""Normalize a controlled AssemblyAI Voice Agent JSONL capture into TurnBench trace JSON.

Input lines are harness envelopes:
  {"at_ms": 123, "direction": "server"|"client", "event": {...}}

Secrets and bulky payloads are deliberately dropped. A normalized trace can document what
a capture harness observed; it cannot authenticate its own provider origin.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import turnbench as tb

MAX_LINES = tb.MAX_EVENTS * 4


def _resolved_hash(config: dict[str, Any]) -> str:
    return tb.sha256_bytes(tb.canonical_bytes(config))


def _turn_detection(config: dict[str, Any]) -> tuple[int, int]:
    try:
        td = config["input"]["turn_detection"]
        return int(td["min_silence"]), int(td["max_silence"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("resolved config missing input.turn_detection min_silence/max_silence") from exc


def _env(raw: Any, line_no: int) -> tuple[int, str, dict[str, Any]]:
    row = tb._expect_exact_keys(raw, {"at_ms", "direction", "event"}, where=f"line[{line_no}]")
    at_ms = tb._expect_int(row["at_ms"], f"line[{line_no}].at_ms", 0, 86_400_000)
    if row["direction"] not in {"server", "client"}:
        raise ValueError(f"line[{line_no}].direction invalid")
    if not isinstance(row["event"], dict):
        raise ValueError(f"line[{line_no}].event must be object")
    return at_ms, row["direction"], row["event"]


def normalize_jsonl(data: bytes, scenario_id: str, evidence_class: str) -> dict[str, Any]:
    tb._expect_id(scenario_id, "scenario_id")
    if evidence_class not in {"SYNTHETIC", "LIVE_CAPTURE_UNVERIFIED"}:
        raise ValueError("evidence_class invalid")
    if len(data) > tb.MAX_FILE_BYTES:
        raise ValueError("capture exceeds size bound")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("capture is not UTF-8") from exc

    lines = [line for line in text.splitlines() if line.strip()]
    if not lines or len(lines) > MAX_LINES:
        raise ValueError("capture line count invalid")

    out_events: list[dict[str, Any]] = []
    seq = 0
    configured_added = False
    last_at = -1

    for line_no, line in enumerate(lines, 1):
        raw = tb.loads_strict(line.encode("utf-8"))
        at_ms, direction, event = _env(raw, line_no)
        if at_ms < last_at:
            raise ValueError("capture time regressed")
        last_at = at_ms
        etype = event.get("type")
        if not isinstance(etype, str):
            raise ValueError(f"line[{line_no}] event.type missing")

        data_out: dict[str, Any] | None = None
        normalized_type = etype

        if direction == "server" and etype in {"session.ready", "session.updated"}:
            config = event.get("config")
            if not isinstance(config, dict):
                raise ValueError(f"{etype} missing resolved config")
            digest = _resolved_hash(config)
            if not configured_added:
                mn, mx = _turn_detection(config)
                out_events.append({
                    "seq": seq,
                    "at_ms": at_ms,
                    "type": "harness.session.configured",
                    "data": {"resolved_config_sha256": digest, "min_silence_ms": mn, "max_silence_ms": mx},
                })
                seq += 1
                configured_added = True
            data_out = {"resolved_config_sha256": digest}
        elif direction == "server" and etype == "session.ended":
            data_out = {"clean": True}
        elif direction == "server" and etype in {"input.speech.started", "input.speech.stopped", "reply.audio"}:
            data_out = {}
        elif direction == "server" and etype in {"transcript.user.delta", "transcript.user"}:
            data_out = {"item_id": event.get("item_id"), "text": event.get("text")}
        elif direction == "server" and etype == "reply.started":
            data_out = {"reply_id": event.get("reply_id"), "item_id": event.get("item_id")}
        elif direction == "server" and etype == "transcript.agent.delta":
            data_out = {"reply_id": event.get("reply_id"), "item_id": event.get("item_id"), "delta": event.get("delta")}
        elif direction == "server" and etype == "transcript.agent":
            data_out = {
                "reply_id": event.get("reply_id"),
                "item_id": event.get("item_id"),
                "text": event.get("text"),
                "interrupted": event.get("interrupted", False),
            }
        elif direction == "server" and etype == "reply.done":
            data_out = {"reply_id": event.get("reply_id"), "status": event.get("status")}
        elif direction == "server" and etype == "tool.call":
            data_out = {
                "call_id": event.get("call_id"),
                "name": event.get("name"),
                "arguments": event.get("arguments"),
            }
        elif direction == "client" and etype == "tool.result":
            data_out = {"call_id": event.get("call_id"), "is_error": event.get("is_error", False)}
        elif direction == "server" and etype == "session.error":
            data_out = {"code": event.get("code")}
        else:
            # input.audio, session.update, reply.create, raw close frames and unknown
            # harness metadata are not part of the minimized evaluator trace.
            continue

        out_events.append({"seq": seq, "at_ms": at_ms, "type": normalized_type, "data": data_out})
        seq += 1

    trace = {
        "schema": tb.TRACE_SCHEMA,
        "scenario_id": scenario_id,
        "provider": tb.PROVIDER,
        "evidence_class": evidence_class,
        "events": out_events,
    }
    tb.validate_trace(trace)
    return trace


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--capture", required=True)
    p.add_argument("--scenario-id", required=True)
    p.add_argument("--evidence-class", choices=["SYNTHETIC", "LIVE_CAPTURE_UNVERIFIED"], default="SYNTHETIC")
    p.add_argument("--out", required=True)
    ns = p.parse_args(argv)
    try:
        src = Path(ns.capture)
        if src.is_symlink() or not src.is_file():
            raise ValueError("capture must be a regular non-symlink file")
        trace = normalize_jsonl(src.read_bytes(), ns.scenario_id, ns.evidence_class)
        tb._write_new(Path(ns.out), tb.canonical_bytes(trace) + b"\n")
        print(tb.sha256_bytes(tb.canonical_bytes(trace)))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 64


if __name__ == "__main__":
    raise SystemExit(main())
