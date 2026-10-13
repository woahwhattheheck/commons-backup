# SPDX-License-Identifier: MIT
"""Prequential, censor-aware weights over complete dated public-flow streams.

These are experimental model weights, not calibrated probabilities. No policy
selection, receipt calculation, opponent-private state or random draw occurs.
Use one learner per game/product/threshold family; resolve each window once.
"""
from __future__ import annotations

import copy
import json
import math
from collections import defaultdict
from typing import Any, Iterable, Mapping

NAMES = ("zero", "same_phase", "shift_early", "shift_late")
INTERPRETATION = "experimental weights; unknown mass is a design parameter, not calibrated confidence"


def integer(value: Any, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _field(row: Any, key: str) -> Any:
    return row[key] if isinstance(row, Mapping) else getattr(row, key)


def interval_label(rows: Iterable[Any], *, product: str, now: int, cutoff: int,
                   threshold: int) -> dict:
    """Label total rival sales on [now, cutoff]; missing dates remain unknown.

    A known lower bound can prove a positive event despite other missing dates.
    A negative event requires a finite summed upper bound covering every date.
    Intervals may be T12 FlowInterval objects or their public JSON equivalents.
    """
    integer(now, "now"); integer(cutoff, "cutoff", now)
    integer(threshold, "threshold", 1)
    seen, lower, upper = set(), 0, 0
    for row in rows:
        t = integer(_field(row, "step"), "interval step")
        if _field(row, "product") != product or not now <= t <= cutoff or t in seen:
            raise ValueError("interval must match product/window and have a unique step")
        lo = integer(_field(row, "lower"), "lower")
        hi = _field(row, "upper")
        if hi is not None:
            integer(hi, "upper", lo)
        seen.add(t); lower += lo
        upper = None if upper is None or hi is None else upper + hi
    missing = cutoff - now + 1 - len(seen)
    if missing:
        upper = None
    label = 1 if lower >= threshold else (0 if upper is not None and upper < threshold else None)
    return {"label": label, "lower": lower, "upper": upper, "missing_steps": missing,
            "reason": "identified_threshold" if label is not None else "censored_threshold"}


def experts_from_prediction(prediction: Mapping, *, now: int, end: int) -> dict:
    """Consume T12 window_prediction output without modifying its history.

    Keep each COMPLETE window intact. Shift whole streams, aggregate clamped
    dates, and preserve every historical component even when streams coincide.
    Quantities describe empirical sales, NOT stock feasibility or future fills.
    """
    integer(now, "now"); integer(end, "end", now)
    if prediction.get("now") != now or prediction.get("end") != end:
        raise ValueError("prediction window mismatch")
    windows = prediction.get("windows", [])
    if not isinstance(windows, (list, tuple)):
        raise ValueError("windows must be a sequence")
    streams, latest = [], None
    for w in windows:
        start = integer(w["training_start"], "training_start")
        finish = integer(w["training_end"], "training_end", start)
        if finish >= now or finish - start != end - now:
            raise ValueError("training must be a complete past window")
        stream, prev = [], now - 1
        for t, q in w["stream"]:
            integer(t, "stream date", now); integer(q, "stream quantity", 1)
            if t > end or t <= prev:
                raise ValueError("stream dates must be strictly increasing inside the window")
            stream.append((t, q)); prev = t
        if "total" in w and w["total"] != sum(q for _, q in stream):
            raise ValueError("window total does not match its stream")
        streams.append(tuple(stream)); latest = max(finish, latest or finish)
    if not isinstance(prediction.get("ready"), bool):
        raise ValueError("ready must be a boolean from the history predictor")
    ready = prediction["ready"] and bool(streams)
    out = {"zero": {"streams": ((),), "support": 0, "latest_training_step": None}}
    if not ready:
        return out
    for name, shift in (("same_phase", 0), ("shift_early", -1), ("shift_late", 1)):
        moved_streams = []
        for stream in streams:
            moved = defaultdict(int)
            for t, q in stream:
                moved[min(end, max(now, t + shift))] += q
            moved_streams.append(tuple(sorted(moved.items())))
        out[name] = {"streams": tuple(moved_streams), "support": len(streams),
                     "latest_training_step": latest}
    return out


def _loss(p: float, y: int) -> dict:
    clipped = min(1 - 1e-12, max(1e-12, p))
    return {"brier": (p - y) ** 2,
            "log_loss": -math.log(clipped if y else 1 - clipped)}


class CausalWindowEnsemble:
    """Bounded online learner; one pending non-overlapping window at a time.

    Updates use frozen expert predictions, never predictions recomputed after
    seeing outcomes. Brier losses update log weights with forgetting gamma.
    Censored events change neither weights nor the prior-rate control. Pending
    state is bounded; historical records are returned to the caller, not stored.
    """
    def __init__(self, game_id: str, product: str, *, eta: float = 2.0,
                 gamma: float = 1.0, unknown_mass: float = 0.25,
                 max_window: int = 24, max_streams: int = 64):
        if not isinstance(game_id, str) or not game_id or not isinstance(product, str) or not product:
            raise ValueError("game_id and product must be nonempty strings")
        for name, x in (("eta", eta), ("gamma", gamma), ("unknown_mass", unknown_mass)):
            if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
                raise ValueError(f"{name} must be finite")
        if not 0 < eta <= 1e6 or not 0 < gamma <= 1 or not 0 < unknown_mass < 1:
            raise ValueError("require 0<eta<=1e6, 0<gamma<=1, 0<unknown_mass<1")
        self.game_id, self.product = game_id, product
        self.eta, self.gamma, self.unknown_mass = eta, gamma, unknown_mass
        self.max_window = integer(max_window, "max_window", 1)
        self.max_streams = integer(max_streams, "max_streams", 1)
        self._logs = {name: 0.0 for name in NAMES}
        self._pending = None
        self._clock, self._last_end, self._sequence = -1, -1, 0
        self._positive, self._identified, self._censored = 0, 0, 0
        self._threshold = None

    def state(self) -> dict:
        top = max(self._logs.values())
        weights = {k: math.exp(max(-700., v - top)) for k, v in self._logs.items()}
        total = sum(weights.values())
        return {"game_id": self.game_id, "product": self.product,
                "weights": {k: v / total for k, v in weights.items()},
                "identified": self._identified, "positive": self._positive,
                "censored": self._censored, "clock": self._clock,
                "pending": None if self._pending is None else self._pending["ticket"],
                "recommended_alpha": 0.0, "interpretation": INTERPRETATION}

    def predict(self, prediction: Mapping, *, now: int, end: int,
                cutoff: int, threshold: int) -> dict:
        """Freeze one threshold event and its whole-stream mixture.

        Target: at least threshold units sold by END OF MARKET at cutoff,
        inclusive. It is not a claim about order position within that market.
        Missing historical experts remain untrained rather than getting zeros.
        A learner's threshold and cutoff offset stay fixed for comparable losses.
        """
        integer(now, "now"); integer(end, "end", now)
        integer(cutoff, "cutoff", now); integer(threshold, "threshold", 1)
        if cutoff > end or end - now + 1 > self.max_window:
            raise ValueError("forecast exceeds its bounded window")
        event_family = (threshold, cutoff - now, end - now)
        if self._threshold is not None and event_family != self._threshold:
            raise ValueError("use a separate learner for a different event family")
        # Copy nested input now. Returned objects never alias the private ticket.
        experts = experts_from_prediction(prediction, now=now, end=end)
        if any(len(e["streams"]) > self.max_streams for e in experts.values()):
            raise ValueError("too many whole streams")
        signature = (now, end, cutoff, threshold, experts)
        if self._pending is not None:
            if signature == self._pending["signature"]:
                return copy.deepcopy(self._pending["public"])
            raise ValueError("resolve the pending window before another prediction")
        if now < self._clock or now <= self._last_end:
            raise ValueError("forecast time reversed or windows overlap")
        probabilities = {name: sum(sum(q for t, q in s if t <= cutoff) >= threshold
                                   for s in e["streams"]) / len(e["streams"])
                         for name, e in experts.items()}
        top = max(self._logs[k] for k in experts)
        weights = {k: math.exp(max(-700., self._logs[k] - top)) for k in experts}
        total = sum(weights.values()); weights = {k: v / total for k, v in weights.items()}
        model_p = sum(weights[k] * probabilities[k] for k in weights)
        # No empirical support: all scenario mass is unknown, not a zero-flow belief.
        rho = self.unknown_mass if len(experts) > 1 else 1.0
        lower, upper = (1 - rho) * model_p, (1 - rho) * model_p + rho
        midpoint = (lower + upper) / 2
        prior = (self._positive + 1) / (self._identified + 2)
        components = []
        for name, e in experts.items():
            for index, stream in enumerate(e["streams"]):
                components.append({"expert": name, "component": index, "stream": stream,
                                   "mass": (1 - rho) * weights[name] / len(e["streams"]),
                                   "latest_training_step": e["latest_training_step"]})
        components.append({"expert": "unknown", "component": None, "stream": None,
                           "mass": rho, "latest_training_step": None})
        self._sequence += 1
        ticket = json.dumps([self.game_id, self.product, *event_family, self._sequence], separators=(",", ":"))
        public = {"ticket": ticket, "game_id": self.game_id, "product": self.product,
                  "now": now, "end": end, "cutoff": cutoff, "threshold": threshold,
                  "expert_probabilities": probabilities, "expert_weights": weights,
                  "support": max(e["support"] for e in experts.values()),
                  "model_probability": model_p, "probability_interval": [lower, upper],
                  "diagnostic_midpoint": midpoint, "prior_rate_control": prior,
                  "unknown_mass": rho, "components": components,
                  "recommended_alpha": 0.0, "interpretation": INTERPRETATION}
        self._pending = {"ticket": ticket, "signature": copy.deepcopy(signature),
                         "public": copy.deepcopy(public)}
        self._clock, self._threshold = now, event_family
        return copy.deepcopy(public)

    def resolve(self, ticket: str, intervals: Iterable[Any], *, observed_at: int) -> dict:
        """Consume one matured public outcome; missing/ambiguous totals censor it."""
        integer(observed_at, "observed_at")
        if self._pending is None or ticket != self._pending["ticket"]:
            raise ValueError("unknown or already resolved ticket")
        f = self._pending["public"]
        if observed_at <= f["end"] or observed_at < self._clock:
            raise ValueError("outcome precedes completion of the predicted window")
        result = interval_label(intervals, product=self.product, now=f["now"],
                                cutoff=f["cutoff"], threshold=f["threshold"])
        result.update({"forecast": copy.deepcopy(f), "observed_at": observed_at})
        y = result["label"]
        result["scores"] = {}
        if y is None:
            self._censored += 1
        else:
            ps = dict(f["expert_probabilities"])
            ps.update({"model": f["model_probability"], "unknown_midpoint": f["diagnostic_midpoint"],
                       "zero_control": 0.0, "prior_rate_control": f["prior_rate_control"]})
            result["scores"] = {k: {"prediction": p, **_loss(p, y)} for k, p in ps.items()}
            updated = {k: self.gamma * v for k, v in self._logs.items()}
            for k, p in f["expert_probabilities"].items():
                updated[k] -= self.eta * (p - y) ** 2
            top = max(updated.values())
            self._logs = {k: max(-700., v - top) for k, v in updated.items()}
            self._identified += 1; self._positive += y
        self._clock, self._last_end = observed_at, f["end"]
        self._pending = None
        result["state_after"] = self.state()
        return result


def predict_history(learner: CausalWindowEnsemble, history: Any, *, now: int,
                    end: int, cutoff: int, threshold: int) -> dict:
    """Duck-typed actual T12 FlowHistory adapter; no core import or parent call."""
    if history.last.get(learner.product, -1) >= now:
        raise ValueError("history already contains the predicted present/future")
    prediction = history.window_prediction(learner.product, now, end)
    return learner.predict(prediction, now=now, end=end, cutoff=cutoff, threshold=threshold)


def summarize(records: Iterable[Mapping]) -> dict:
    """Conditional-on-identification diagnostics, grouped by complete game metadata.

    Family/split are REPORTING labels only and never used to choose predictions.
    Reliability bins are descriptive; no confidence intervals or calibration claim.
    """
    groups = {}
    game_split, seen_tickets = {}, set()
    for row in records:
        f = row["forecast"]
        if f["ticket"] in seen_tickets:
            raise ValueError("duplicate outcome ticket in diagnostics")
        seen_tickets.add(f["ticket"])
        split, family = row.get("split", "unspecified"), row.get("opponent_family", "unspecified")
        old = game_split.setdefault(f["game_id"], (split, family))
        if old != (split, family):
            raise ValueError("one game cannot cross splits or opponent families")
        key = (split, family, f["game_id"], f["product"], f["threshold"],
               f["cutoff"] - f["now"], f["end"] - f["now"] + 1, f["now"] % 24, f["support"])
        g = groups.setdefault(key, {"windows": 0, "identified": 0, "censored": 0, "scores": {}})
        g["windows"] += 1
        g["censored" if row["label"] is None else "identified"] += 1
        for name, score in row["scores"].items():
            s = g["scores"].setdefault(name, {"n": 0, "brier_sum": 0., "log_loss_sum": 0., "bins": {}})
            s["n"] += 1; s["brier_sum"] += score["brier"]; s["log_loss_sum"] += score["log_loss"]
            p = score["prediction"]; bin_id = min(9, int(p * 10))
            b = s["bins"].setdefault(bin_id, {"n": 0, "prediction_sum": 0., "positive": 0})
            b["n"] += 1; b["prediction_sum"] += p; b["positive"] += row["label"]
    output = []
    for key, g in sorted(groups.items()):
        for s in g["scores"].values():
            s["mean_brier"] = s["brier_sum"] / s["n"]
            s["mean_log_loss"] = s["log_loss_sum"] / s["n"]
        output.append(dict(zip(("split", "opponent_family", "game_id", "product", "threshold", "cutoff_offset", "window_length", "phase24", "support"), key), **g))
    return {"groups": output, "scoring_population": "identifiable threshold labels only; censoring may bias this subset",
            "game_count": len(game_split), "recommended_alpha": 0., "interpretation": INTERPRETATION}
