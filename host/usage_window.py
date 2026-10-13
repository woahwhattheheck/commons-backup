#!/usr/bin/env python3
"""Record an active usage window and stop dispatch after an observed special reset.

This tool never fetches a meter, invents a reading, or schedules work. Its caller
must supply actual account-specific observations and their evidence.
"""
from __future__ import annotations

import argparse
import contextlib
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time

SCHEMA = "commons-usage-window/v1"
METER_SCOPE = "codex-work-weekly-plan"
HIGH_BURN = "HIGH-BURN"
CONSERVATION = "CONSERVATION"
KINDS = ("meter", "unavailable", "explicit_reset_applied", "public_signal")
MIN_CONSUMED_POINTS = 5.0
MIN_REPLENISHMENT_POINTS = 5.0


class UsageError(ValueError):
    pass


def timestamp(value):
    if not isinstance(value, str) or not value.strip():
        raise UsageError("an explicit timestamp with a timezone is required")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise UsageError("invalid timestamp: " + value) from error
    if parsed.tzinfo is None:
        raise UsageError("timestamps require a timezone")
    return parsed.astimezone(timezone.utc)


def stamp(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def text_field(value, name):
    if not isinstance(value, str) or not value.strip():
        raise UsageError(name + " must be nonempty text")
    return value.strip()


@contextlib.contextmanager
def locked(path, timeout=10):
    """Serialize readers/writers on a stable sidecar, not the replaced JSON inode."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path) + ".lock", "a", encoding="utf-8") as handle:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise UsageError("usage ledger is busy; retry the same observation")
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def save(path, state):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".usage-window-", delete=False) as handle:
            temporary = handle.name
            json.dump(state, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if temporary is not None:
            os.unlink(temporary)


def read(path):
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        raise UsageError("cannot read usage ledger: " + str(error)) from error
    if (not isinstance(state, dict) or state.get("schema") != SCHEMA
            or state.get("mode") not in (HIGH_BURN, CONSERVATION)
            or state.get("meter_scope") != METER_SCOPE
            or not isinstance(state.get("observations"), list)):
        raise UsageError("usage ledger schema is invalid")
    text_field(state.get("account_id"), "account_id")
    timestamp(state.get("created_at"))
    return state


def initial_state(account, created_at, ordinary_reset_at=None, poll_seconds=120):
    if type(poll_seconds) is not int or not 60 <= poll_seconds <= 180:
        raise UsageError("poll interval must be between 60 and 180 seconds")
    created = timestamp(created_at)
    return {
        "schema": SCHEMA,
        "account_id": text_field(account, "account_id"),
        "meter_scope": METER_SCOPE,
        "mode": HIGH_BURN,
        "created_at": stamp(created),
        "ordinary_reset_at": stamp(timestamp(ordinary_reset_at)) if ordinary_reset_at else None,
        "poll_seconds": poll_seconds,
        "observations": [],
        "reset_evidence": None,
    }


def record(state, *, account, meter_scope, observed_at, kind, source, evidence,
           remaining_percent=None, ordinary_reset_at=None, trusted=False,
           account_specific=False, observation_id=None):
    if account != state["account_id"]:
        raise UsageError("observation account does not match this window")
    if meter_scope != METER_SCOPE or meter_scope != state["meter_scope"]:
        raise UsageError("observation is not the shared weekly plan meter")
    if kind not in KINDS:
        raise UsageError("unknown observation kind")
    observed = timestamp(observed_at)
    if observed < timestamp(state["created_at"]):
        raise UsageError("observation predates this window")
    if type(trusted) is not bool or type(account_specific) is not bool:
        raise UsageError("trust and account-specific flags must be booleans")
    if kind == "public_signal" and (account_specific or ordinary_reset_at is not None):
        raise UsageError("public signals cannot establish this account's reset or ordinary deadline")
    if kind == "meter":
        if (type(remaining_percent) not in (int, float)
                or not math.isfinite(remaining_percent)
                or not 0 <= remaining_percent <= 100):
            raise UsageError("meter reading must be a finite percentage from 0 through 100")
    elif remaining_percent is not None:
        raise UsageError("only a meter observation may include a percentage")
    reset_at = stamp(timestamp(ordinary_reset_at)) if ordinary_reset_at else state["ordinary_reset_at"]
    observation = {
        "account_id": account,
        "meter_scope": meter_scope,
        "observed_at": stamp(observed),
        "kind": kind,
        "source": text_field(source, "source"),
        "evidence": text_field(evidence, "evidence"),
        "remaining_percent": remaining_percent,
        "ordinary_reset_at": reset_at,
        "trusted": trusted,
        "account_specific": account_specific,
    }
    canonical = json.dumps(observation, sort_keys=True, separators=(",", ":"), allow_nan=False)
    observation["id"] = (text_field(observation_id, "observation_id") if observation_id
                         else hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24])
    for previous in state["observations"]:
        if previous["id"] == observation["id"]:
            if previous == observation:
                return False
            raise UsageError("observation ID already has different evidence")
    if state["observations"] and observed <= timestamp(state["observations"][-1]["observed_at"]):
        raise UsageError("new observations must be later than the previous observation")

    transition = None
    if state["mode"] == HIGH_BURN and trusted and account_specific:
        if kind == "explicit_reset_applied":
            transition = {"reason": "account-specific special reset applied notice"}
        elif kind == "meter":
            previous = next((row for row in reversed(state["observations"])
                             if row["kind"] == "meter" and row["trusted"]
                             and row["account_specific"]), None)
            if previous:
                prior_boundary = previous["ordinary_reset_at"]
                # A special reset may also move the next ordinary deadline. It
                # is the old deadline that proves no normal boundary was due.
                same_cycle = (prior_boundary is not None and reset_at is not None
                              and observed < timestamp(prior_boundary)
                              and observed < timestamp(reset_at))
                consumed = previous["remaining_percent"] <= 100 - MIN_CONSUMED_POINTS
                # Concurrent work can consume a reset allocation before the
                # next observation. Its absolute level need not remain near
                # 100%; the material upward jump before the old deadline is
                # the evidence. Initial/repeated readings still do not count.
                replenished = (remaining_percent - previous["remaining_percent"]
                               >= MIN_REPLENISHMENT_POINTS)
                if same_cycle and consumed and replenished:
                    transition = {
                        "reason": "weekly meter replenished before the ordinary reset",
                        "previous_observation_id": previous["id"],
                        "previous_remaining_percent": previous["remaining_percent"],
                        "remaining_percent": remaining_percent,
                        "ordinary_reset_at": reset_at,
                        "previous_ordinary_reset_at": prior_boundary,
                    }
    state["observations"].append(observation)
    # Untrusted entries remain recorded but cannot change the comparison cycle.
    if trusted and account_specific and kind == "meter" and ordinary_reset_at:
        state["ordinary_reset_at"] = reset_at
    if transition:
        state["mode"] = CONSERVATION
        state["reset_evidence"] = {
            **transition, "observed_at": observation["observed_at"],
            "observation_id": observation["id"], "source": observation["source"],
            "evidence": observation["evidence"],
        }
    return True


def status(state, now=None):
    current = datetime.now(timezone.utc) if now is None else timestamp(now)
    observations = state["observations"]
    last = observations[-1] if observations else None
    attempt = next((row for row in reversed(observations)
                    if row["kind"] != "public_signal"), None)
    signal = next((row for row in reversed(observations)
                   if row["kind"] == "public_signal"), None)
    meter = next((row for row in reversed(observations)
                  if row["kind"] == "meter" and row["trusted"] and row["account_specific"]), None)
    age = (current - timestamp(meter["observed_at"])).total_seconds() if meter else None
    warnings = []
    if meter is None:
        warnings.append("Weekly usage is unobservable; no percentage or reset is inferred.")
    elif age < 0:
        warnings.append("The status clock is earlier than the recorded meter observation.")
    elif age > 180:
        warnings.append("The last weekly meter observation is stale; retry the legitimate reading method.")
    if attempt and attempt["kind"] == "unavailable":
        warnings.append("The latest meter-reading attempt was unavailable: " + attempt["evidence"])
    if signal:
        warnings.append("Public reports are advisory; they do not confirm this account's reset or postpone meter polling.")
    if state["ordinary_reset_at"] is None:
        warnings.append("Ordinary reset time is unknown; percentage jumps alone cannot prove the special reset.")
    elif current >= timestamp(state["ordinary_reset_at"]):
        warnings.append("An ordinary reset boundary is due or crossed; refresh its timestamp before interpreting replenishment.")
    next_poll = (timestamp(attempt["observed_at"] if attempt else state["created_at"])
                 + timedelta(seconds=state["poll_seconds"]))
    return {
        "MODE": state["mode"],
        "ACCOUNT_ID": state["account_id"],
        "METER_SCOPE": state["meter_scope"],
        "USAGE_LAST_SEEN": meter["remaining_percent"] if meter else None,
        "USAGE_TIMESTAMP": meter["observed_at"] if meter else None,
        "LAST_OBSERVATION_TIMESTAMP": last["observed_at"] if last else None,
        "LAST_METER_ATTEMPT_TIMESTAMP": attempt["observed_at"] if attempt else None,
        "PUBLIC_SIGNAL": signal,
        "RESET_EVIDENCE": state["reset_evidence"],
        "ALLOW_NEW_WORK": state["mode"] == HIGH_BURN,
        "OBSERVATION_COUNT": len(observations),
        "WARNINGS": warnings,
        "NEXT_POLL_AT": stamp(next_poll) if state["mode"] == HIGH_BURN else None,
        "POLL_DUE": current >= next_poll if state["mode"] == HIGH_BURN else False,
        "NEXT": ("Stop new dispatch; preserve completed state and halt nonessential work."
                 if state["mode"] == CONSERVATION else "Continue useful work; observe the actual weekly meter when available."),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True, help="private active-session JSON ledger")
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("init")
    start.add_argument("--account", required=True)
    start.add_argument("--at", required=True)
    start.add_argument("--ordinary-reset-at")
    start.add_argument("--poll-seconds", type=int, default=120)
    observe = commands.add_parser("observe")
    observe.add_argument("--account", required=True)
    observe.add_argument("--meter-scope", required=True)
    observe.add_argument("--at", required=True)
    observe.add_argument("--kind", choices=KINDS, required=True)
    observe.add_argument("--source", required=True)
    observe.add_argument("--evidence", required=True)
    observe.add_argument("--remaining-percent", type=float)
    observe.add_argument("--ordinary-reset-at")
    observe.add_argument("--trusted", action="store_true")
    observe.add_argument("--account-specific", action="store_true")
    observe.add_argument("--id")
    show = commands.add_parser("status")
    show.add_argument("--now")
    show.add_argument("--allow-new-work", action="store_true",
                      help="exit 2 when conservation forbids new dispatch")
    args = parser.parse_args(argv)
    try:
        with locked(args.state):
            if args.command == "init":
                if args.state.exists():
                    raise UsageError("ledger already exists; observe or inspect it instead of reinitializing")
                state = initial_state(args.account, args.at, args.ordinary_reset_at, args.poll_seconds)
                save(args.state, state)
            else:
                state = read(args.state)
                if args.command == "observe":
                    changed = record(state, account=args.account, meter_scope=args.meter_scope,
                                     observed_at=args.at, kind=args.kind, source=args.source,
                                     evidence=args.evidence, remaining_percent=args.remaining_percent,
                                     ordinary_reset_at=args.ordinary_reset_at, trusted=args.trusted,
                                     account_specific=args.account_specific, observation_id=args.id)
                    if changed:
                        save(args.state, state)
            result = status(state, getattr(args, "now", None))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2 if getattr(args, "allow_new_work", False) and not result["ALLOW_NEW_WORK"] else 0
    except (UsageError, OSError) as error:
        print("USAGE_WINDOW_ERROR: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
