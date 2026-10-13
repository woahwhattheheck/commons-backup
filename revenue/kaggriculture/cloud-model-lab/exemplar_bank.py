"""Port of the LDA ExemplarBank to Kaggriculture turns.

Source: app/src/main/java/com/local/deviceagent/ExemplarBank.kt and its call sites in
AgentOrchestrator.kt at LDA 54081cd58d2c45b868b4265c3dcb8990aa1cc9b4. The mechanism
ported, not paraphrased:

  * entries are lean (state digest -> action) DEMONSTRATIONS, append-only JSONL,
    capped and rolling;
  * keyed by a SITUATION CLASS -- the structural abstraction of how a situation of
    this KIND behaves -- so an example generalises rather than memorising a path;
  * recorded ONLY from scored ADVANCING steps (the `pos && m > 0` gate);
  * retrieval returns the newest 1-2 for the class, same-context first then any
    context, DEDUPLICATED by action shape so two entries never teach the same move;
  * placed immediately BEFORE the live state, so continuing the pattern IS the
    action for the live state.

Provenance is explicit and never fabricated. A row is either `model` -- an action
this driver's model actually authored and the engine actually advanced -- or
`teacher:<name>`, a bootstrap demonstration from a named official agent, labelled as
such in the row and in the injected header. A teacher row is never presented as a
past model success.
"""

import json
import os

MAX_ROWS = 4000
MAX_PER_CLASS = 20
MAX_STATE = 320

# Bumped whenever the outcome classifier changes what counts as a bankable turn.
# v3: the end-of-day drop no longer counts as a worker deposit, so rows banked under
# v2 on an hour-23 turn may credit a transition the engine performed regardless of
# the action. Those rows are no longer served.
# Retrieval serves only rows written under the CURRENT version: a row banked by an
# earlier, looser classifier is a demonstration of something that classifier was
# wrong about, and serving it feeds that mistake back into the next decision. A
# four-way duplicate PLACE banked under the old rules was being retrieved and
# re-taught, which is what this guards against.
CLASSIFIER_VERSION = 3


def situation_class(obs, config, seat, adm):
    """The structural class of this turn. Engine-derived shape only, no preference."""
    import constraints as C
    farm = obs["farms"][seat]
    n_units = 1 + len(farm.get("hands", []))
    present = {o[0] for o in adm["units"][0]}
    # ORTHOGONAL situation facts, not the capability string. Keying on the exact set
    # of admissible op names made "DGL" and "DL" different classes even though both
    # are "carrying goods, standing on the shed", so the deposit turn matched nothing
    # while the bank held six rows of exactly that situation. Only the three ops that
    # change what a turn is ABOUT are kept; DROP/PICKUP/PLACE/DIG/CARE/BUILD are
    # implied by carry and access and are dropped from the key.
    caps = "".join(c for c, op in (("W", "WATER"), ("H", "HARVEST"),
                                   ("P", "PLANT")) if op in present) or "-"
    invs = obs["private"].get("inventories", [])
    carrying = any(sum(i.values()) for i in invs)
    K = C.engine()
    access = [tuple(t) for t in K._shed_access_tiles(len(farm["tiles"]))]
    on_access = tuple(int(v) for v in farm["farmer"]) in access
    hz = C.horizon(obs, config, seat)
    dying = any(p["dies_at_refresh_unless_watered"] for p in hz["plants"])
    ripe = any(p["yield_units"] > 0 and p["age_days"] >= p["first_yield_day"]
               for p in hz["plants"])
    shed = obs["private"].get("shed", {})
    cap = int(config.get("shedCapacity", 100) or 100)
    return "|".join([
        f"u{n_units}",
        "can:" + caps,
        "carry" if carrying else "nocarry",
        "access" if on_access else "field",
        "dying" if dying else "safe",
        "ripe" if ripe else "unripe",
        "shedfull" if sum(shed.values()) >= cap else "shedroom",
    ])


def context_of(obs):
    """The coarse bucket retrieval prefers, standing in for the source's `app`."""
    d = int(obs["day"])
    return "early" if d < 8 else "mid" if d < 18 else "late"


def structured_state(obs, config, seat):
    """An explicit digest of the decision facts, built from the observation.

    Clipping rendered prose to a byte budget cut mid-token and lost whichever facts
    happened to sit late in the text. This states the facts a demonstration needs --
    the clock, cash, shed use and room, seeds, and each worker's position, carried
    goods and the tile under it -- as fields, so nothing is truncated arbitrarily.
    """
    import prompt as P
    farm = obs["farms"][seat]
    priv = obs["private"]
    cap = int(config.get("shedCapacity", 100) or 100)
    shed = priv.get("shed", {})
    used = sum(shed.values())
    invs = priv.get("inventories", [])
    day, hour = int(obs["day"]), int(obs["hour"])
    parts = [f"d{day}h{hour}", f"cash{int(farm['money'])}",
             f"shed{used}/{cap}"]
    seeds = ",".join(f"{k}{v}" for k, v in sorted(priv.get("seeds", {}).items()) if v)
    parts.append(f"seeds[{seeds or '-'}]")
    stock = ",".join(f"{k}{v}" for k, v in sorted(shed.items()) if v)
    parts.append(f"stock[{stock or '-'}]")
    units = [("farmer", farm["farmer"])] + [(f"h{i}", p) for i, p in enumerate(farm.get("hands", []))]
    for i, (label, p) in enumerate(units):
        x, y = int(p[0]), int(p[1])
        held = invs[i] if i < len(invs) else {}
        carry = ",".join(f"{k}{v}" for k, v in sorted(held.items()) if v) or "-"
        parts.append(f"{label}@({x},{y})carry[{carry}]on[{P._tile_str(farm['tiles'][y][x], day)}]")
    return " ".join(parts)


def lean_state(state_text):
    """Legacy text digest, retained for the exclude-self comparison only."""
    lines = [ln.strip() for ln in state_text.splitlines() if ln.strip()]
    return " . ".join(lines[:8])[:MAX_STATE]


def make_baseline(src, dst):
    """Write a TEACHER-ONLY copy of `src` to `dst` and describe it.

    Independent comparison arms must each start from the same bank and must not be
    able to hand a later arm an earlier arm's model rows. Building the baseline by
    omitting model provenance -- rather than trusting a file called "snapshot" -- makes
    that a property of the data, and the returned hash and counts let a run record the
    exact bank it started from. No reseeding: the completed teacher rows are reused.
    """
    import hashlib
    kept, omitted = [], 0
    with open(src) as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln:
                continue
            try:
                row = json.loads(ln)
            except Exception:
                continue
            if str(row.get("provenance", "")).startswith("model"):
                omitted += 1
                continue
            kept.append(ln)
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    body = ("\n".join(kept) + "\n") if kept else ""
    with open(dst, "w") as fh:
        fh.write(body)
    return {"source": src, "path": dst, "rows": len(kept),
            "model_rows_omitted": omitted,
            "sha256": hashlib.sha256(body.encode()).hexdigest()}


def describe(path):
    """Row count, model-row count and content hash of a bank file."""
    import hashlib
    if not os.path.exists(path):
        return {"path": path, "rows": 0, "model_rows": 0, "sha256": None}
    body = open(path, "rb").read()
    rows = [l for l in body.decode().splitlines() if l.strip()]
    model = 0
    for l in rows:
        try:
            if str(json.loads(l).get("provenance", "")).startswith("model"):
                model += 1
        except Exception:
            pass
    return {"path": path, "rows": len(rows), "model_rows": model,
            "sha256": hashlib.sha256(body).hexdigest()}


class Bank:
    def __init__(self, path, write_path=None):
        """`path` is READ. `write_path` is WRITTEN.

        They are separate so a run cannot append into the bank another run will read.
        Passing write_path=None makes the bank read-only: `record` is a no-op, which
        is what a comparison arm needs. Defaulting write_path to `path` would restore
        exactly the coupling this separation exists to remove, so it is not the
        default -- a caller that wants to learn names its output explicitly.
        """
        self.path = path
        self.write_path = write_path
        self.rows = []
        if os.path.exists(path):
            with open(path) as fh:
                for ln in fh:
                    ln = ln.strip()
                    if ln:
                        try:
                            self.rows.append(json.loads(ln))
                        except Exception:
                            pass

    def record(self, cls, context, state_text, action, provenance, plan=None):
        """Bank one ADVANCING demonstration. Callers must apply the advancing gate.

        A row carries a `plan` because the emitted turn shape requires one first. A
        teacher row's plan is a factual restatement of what its action did, and the
        row stays labelled `teacher:` so it is never read as a model success.
        """
        if not cls or not state_text or not action:
            return
        if plan and "plan" not in action:
            action = {"plan": plan, **action}
        # The action is stored COMPLETE. Slicing the serialized JSON to a byte budget
        # produced malformed demonstrations for multi-hand turns -- an 8-hand action
        # plus a plan exceeds 200 bytes -- which `_hands_of` then silently discarded,
        # so those rows were dead weight. Retrieval is bounded by per-class retention,
        # not by truncating a row's content.
        if not self.write_path:
            return          # read-only bank: retrieval only, never learns
        row = {"cls": cls, "ctx": context,
               "state": state_text if isinstance(state_text, str) else str(state_text),
               "action": json.dumps(action, separators=(",", ":")),
               "provenance": provenance, "v": CLASSIFIER_VERSION, "n": len(self.rows)}
        self.rows.append(row)
        os.makedirs(os.path.dirname(self.write_path) or ".", exist_ok=True)
        if self.write_path != self.path and not os.path.exists(self.write_path):
            # A learning run's output starts as a copy of what it read, so the output
            # file is a complete bank rather than only the rows this run added.
            with open(self.write_path, "w") as fh:
                for r in self.rows[:-1]:
                    fh.write(json.dumps(r) + "\n")
        with open(self.write_path, "a") as fh:
            fh.write(json.dumps(row) + "\n")
        if len(self.rows) > MAX_ROWS:
            self.trim()

    def trim(self):
        """Keep the newest MAX_PER_CLASS rows PER CLASS, not the newest overall.

        A global trim drops whole classes: seeding three teachers in sequence, the
        last one's rows evicted every single-farmer class the first teacher had
        contributed, leaving 307 rows from one teacher and no coverage for a
        one-unit turn. Retrieval is per class, so the cap has to be per class too.
        """
        kept, per = [], {}
        for r in reversed(self.rows):
            c = r.get("cls")
            if per.get(c, 0) >= MAX_PER_CLASS:
                continue
            per[c] = per.get(c, 0) + 1
            kept.append(r)
        self.rows = list(reversed(kept))
        with open(self.write_path or self.path, "w") as fh:
            for r in self.rows:
                fh.write(json.dumps(r) + "\n")

    @staticmethod
    def _drop_units(cls):
        """The class without its unit-count field."""
        return "|".join(cls.split("|")[1:])

    @staticmethod
    def _hands_of(action_json):
        """How many hand entries a stored action has, for shape compatibility."""
        import json as _j
        try:
            return len(_j.loads(action_json).get("hands") or [])
        except Exception:
            return -1

    def for_class(self, cls, context, n=2, exclude_state=None, n_hands=None):
        """Newest n for this class, deduplicated by action shape.

        Retrieval relaxes in the source's two-pass shape, one step further: exact
        class and same context, then exact class any context, then the class without
        its unit count. The last pass exists because a demonstration is ONE unit's op
        and generalises across how many units the turn has; without it a single-farmer
        turn could match nothing while the bank held the right situation under u5.
        The relaxation level is returned on each row so it stays visible.

        `exclude_state` drops any row whose lean digest matches the live one, so an
        evaluation card is never handed its own answer.
        """
        relaxed = self._drop_units(cls)
        def current(r):
            return r.get("v") == CLASSIFIER_VERSION
        passes = [
            ("exact+ctx", lambda r: current(r) and r.get("cls") == cls
             and r.get("ctx") == context),
            ("exact", lambda r: current(r) and r.get("cls") == cls),
            ("any-unit-count", lambda r: current(r)
             and self._drop_units(r.get("cls", "")) == relaxed),
        ]
        out, seen = [], set()
        for level, pred in passes:
            for r in reversed(self.rows):
                if len(out) >= n:
                    break
                if not pred(r):
                    continue
                # Shape compatibility: a demonstration with a different number of hand
                # entries cannot be continued for this turn -- an 8-hand action shown
                # to a single farmer is noise the output grammar forbids anyway.
                if n_hands is not None and self._hands_of(r["action"]) != n_hands:
                    continue
                if exclude_state and r["state"] == exclude_state:
                    continue
                shape = r["action"].split('"farmer":')[-1][:26]
                if shape in seen:
                    continue
                seen.add(shape)
                row = dict(r)
                row["match"] = level
                out.append(row)
            if len(out) >= n:
                break
        return out


def block(rows):
    """The injected block. Provenance is stated in the header, never implied."""
    if not rows:
        return ""
    prov = {r.get("provenance", "?").split(":")[0] for r in rows}
    if prov == {"model"}:
        head = ("YOUR OWN PAST WINS on this kind of turn "
                "(state -> the action that advanced it):")
    elif prov == {"teacher"}:
        names = sorted({r["provenance"] for r in rows})
        head = (f"DEMONSTRATIONS on this kind of turn from {', '.join(names)} "
                f"(state -> the action that advanced it). These are a teacher's "
                f"turns, not your own past wins:")
    else:
        head = ("PAST ADVANCING TURNS of this kind (state -> the action that "
                "advanced it); each line is labelled with whose turn it was:")
    lines = []
    for r in rows:
        tag = "" if prov == {"model"} or prov == {"teacher"} else f"[{r['provenance']}] "
        lines.append(f"{tag}{r['state']} -> {r['action']}")
    return head + "\n" + "\n".join(lines)
