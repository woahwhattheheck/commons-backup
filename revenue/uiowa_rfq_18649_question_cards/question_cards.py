#!/usr/bin/env python3
"""UIOWA-114 -- follow-up interview question cards.

What this is
------------
A generator that turns ONE unresolved observation into the ONE question that
would resolve it, with the context a practitioner needs, a concrete artifact to
ask for, and the decision the answer would change.

Why it is a generator and not a question list
---------------------------------------------
The completion condition is "a reviewer can move from a specific unresolved
observation to an appropriate follow-up *without repeating the entire interview
guide*". A written list of good questions IS the interview guide -- the reviewer
already has one. What they do not have is the path from this particular
uncertainty to the question that closes it. So each observation declares the
SHAPE of its uncertainty, and each shape fills a different question template
from the observation's own fields. Templates live in ``data/templates.json``;
no question text is hard-coded here.

The rule that does the real work
--------------------------------
Every card carries an ``outcome_map``: for each plausible answer, what the draft
finding becomes. **A question whose answers all lead to the same finding is
rejected as USELESS_QUESTION and does not render.** If the answer cannot move
the finding, asking it spends a practitioner's hour for nothing, and no amount
of good phrasing fixes that. It is the mechanical form of "don't re-ask the
guide".

Four more, enforced rather than asserted:
  * a card must name a concrete artifact to request -- "any relevant
    documentation" is VAGUE_EXAMPLE_REQUEST and fails;
  * a question may not presume the gap -- a deliberately NARROW lint rejects
    leading phrasing, narrow because a guard that flags correct prose gets
    switched off and then guards nothing;
  * every ABSENT_EVIDENCE card must carry the caveat that absence in the
    supplied material is not evidence the practice does not happen;
  * no observation may be silently dropped -- every one becomes a card, or
    appears in the coverage list with a stated reason, or appears as an error.

Not in scope, on purpose: ranking. UIOWA-113 owns request prioritization, and
two different rank orders in front of one reviewer is worse than none. Cards are
grouped by interview session so a reviewer runs one sitting.

Python 3 standard library only. No network. No model is called.
"""

import argparse
import csv
import json
import os
import re
import sys
import unicodedata

SEVERITY_ERROR = "ERROR"
SEVERITY_WARNING = "WARNING"
SEVERITY_INFO = "INFO"

NULL_TOKEN = "\\N"
RISKY_LEAD = ("=", "+", "-", "@", "\t", "\r", "\n")

CARD_COLUMNS = [
    "card_id", "observation_id", "group", "assessment_area", "uncertainty_type",
    "session_id", "session_label", "ask_role", "role_title",
    "question", "context", "uncertainty_statement", "example_request",
    "decision_informed", "possible_answers", "absence_caveat",
    "open_findings", "source_ids", "source_locators", "outcome_map_json",
]


# ------------------------------------------------------------------ loading --

def load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_bundle(data_dir, observations_file="observations.json"):
    return {
        "templates": load_json(os.path.join(data_dir, "templates.json")),
        "sources": load_json(os.path.join(data_dir, "sources.json")),
        "interviews": load_json(os.path.join(data_dir, "interview_register.json")),
        "observations": load_json(os.path.join(data_dir, observations_file)),
    }


# ------------------------------------------------------------------ helpers --

def norm(text):
    return unicodedata.normalize("NFC", text)


def fold(text):
    return " ".join(norm(text).casefold().split())


def _diag(severity, code, observation_id, field, message):
    return {"severity": severity, "code": code, "observation_id": observation_id,
            "field": field, "message": message}


def fill(template_text, fields):
    """Fill {placeholders}. Missing placeholders raise, they do not render as
    literal braces -- a card that ships '{reading_b}' to a practitioner is worse
    than no card."""
    missing = [name for name in re.findall(r"\{(\w+)\}", template_text)
               if name not in fields]
    if missing:
        raise KeyError(missing[0])
    return re.sub(r"\{(\w+)\}", lambda m: str(fields[m.group(1)]), template_text)


def unique_records(records, key, register):
    """Do not let a dict silently pick one of two evidence identities.

    Ambiguous register structure is an input error, not a practitioner finding.
    Validate before rendering or writing; the caller must resolve the IDs.
    """
    if not isinstance(records, list):
        raise ValueError(f"INVALID_REGISTER: {register} must be a list")
    indexed, positions = {}, {}
    for position, record in enumerate(records, 1):
        if not isinstance(record, dict):
            raise ValueError(f"INVALID_RECORD: {register} row {position} must be an object")
        identifier = record.get(key)
        if not isinstance(identifier, str) or not identifier.strip():
            raise ValueError(f"INVALID_ID: {register} row {position} needs a nonempty {key}")
        if identifier in indexed:
            raise ValueError(
                f"DUPLICATE_ID: {register} rows {positions[identifier]} and {position} "
                f"share {key}={identifier!r}; no row was selected")
        indexed[identifier], positions[identifier] = record, position
    return indexed


def card_id_for(observation_id):
    # Remove only the leading namespace, never OBS- embedded in the identity.
    return "QC-" + (observation_id[4:] if observation_id.startswith("OBS-")
                    else observation_id)


# ------------------------------------------------------------- card building --

def build_cards(bundle):
    templates = bundle["templates"]["templates"]
    vague_phrases = [fold(p) for p in bundle["templates"]["vague_request_phrases"]]
    leading_phrases = [fold(p) for p in bundle["templates"]["leading_phrases"]]
    caveat_required = set(bundle["templates"]["absence_caveat_required_for"])

    sources = unique_records(bundle["sources"]["sources"], "source_id", "sources")
    roles = unique_records(bundle["interviews"]["roles"], "role_id", "roles")
    sessions = unique_records(bundle["interviews"]["sessions"], "session_id", "sessions")
    observations = unique_records(bundle["observations"]["observations"],
                                  "observation_id", "observations")
    unique_records([{"card_id": card_id_for(oid)} for oid in observations],
                   "card_id", "derived card identities")

    cards, diagnostics, suppressed = [], [], []

    for obs in sorted(bundle["observations"]["observations"],
                      key=lambda o: o["observation_id"]):
        oid = obs["observation_id"]

        if obs.get("no_card"):
            # Suppressing an observation is allowed. Suppressing it silently is
            # not: an unresolved observation that never becomes a question is
            # exactly how uncertainty gets lost between analysts.
            reason = obs.get("no_card_reason")
            if not reason:
                diagnostics.append(_diag(
                    SEVERITY_ERROR, "NO_CARD_WITHOUT_REASON", oid, "no_card_reason",
                    "observation is suppressed but gives no reason; a suppressed "
                    "observation must say why or it is an invisible drop"))
            else:
                suppressed.append({"observation_id": oid, "reason": reason})
                diagnostics.append(_diag(SEVERITY_INFO, "NO_CARD", oid, "no_card",
                                         reason))
            continue

        utype = obs.get("uncertainty_type")
        template = templates.get(utype)
        if template is None:
            diagnostics.append(_diag(
                SEVERITY_ERROR, "UNKNOWN_UNCERTAINTY_TYPE", oid, "uncertainty_type",
                f"{utype!r} has no template; known types: {', '.join(sorted(templates))}"))
            continue

        fields = obs.get("fields", {})
        missing = [name for name in template["requires"] if name not in fields]
        if missing:
            diagnostics.append(_diag(
                SEVERITY_ERROR, "TEMPLATE_FIELD_MISSING", oid, missing[0],
                f"{utype} template needs {', '.join(template['requires'])}; "
                f"missing: {', '.join(missing)}"))
            continue

        try:
            question = obs.get("question_override") or fill(template["question"], fields)
            context = fill(template["context"], fields)
            statement = fill(template["uncertainty_statement"], fields)
        except KeyError as exc:
            diagnostics.append(_diag(
                SEVERITY_ERROR, "TEMPLATE_FIELD_MISSING", oid, str(exc.args[0]),
                f"template placeholder {{{exc.args[0]}}} has no value"))
            continue

        # A question whose answers all land on the same finding is not a
        # question. This is the order's completion condition, made mechanical.
        outcomes = obs.get("outcome_map") or []
        distinct = {o["resulting_finding"] for o in outcomes}
        if len(outcomes) < 2 or len(distinct) < 2:
            diagnostics.append(_diag(
                SEVERITY_ERROR, "USELESS_QUESTION", oid, "outcome_map",
                f"{len(outcomes)} answer(s) leading to {len(distinct)} distinct "
                "finding(s); a question that cannot change the finding does not "
                "earn a practitioner's time"))
            continue

        request = obs.get("example_request", "")
        if not request or any(p in fold(request) for p in vague_phrases):
            diagnostics.append(_diag(
                SEVERITY_ERROR, "VAGUE_EXAMPLE_REQUEST", oid, "example_request",
                "the request must name an artifact a practitioner can hand over, "
                f"not {request!r}"))
            continue

        hit = next((p for p in leading_phrases if p in fold(question)), None)
        if hit:
            diagnostics.append(_diag(
                SEVERITY_ERROR, "LEADING_QUESTION", oid, "question",
                f"phrasing presumes the answer ({hit!r}); ask what the practice is, "
                "not why it is missing"))
            continue

        caveat = obs.get("absence_caveat")
        if utype in caveat_required and not caveat:
            diagnostics.append(_diag(
                SEVERITY_ERROR, "MISSING_ABSENCE_CAVEAT", oid, "absence_caveat",
                "an absent-evidence card must state that absence in the supplied "
                "material is not evidence the practice does not happen"))
            continue

        unknown_sources = [s for s in obs.get("source_ids", []) if s not in sources]
        if unknown_sources:
            diagnostics.append(_diag(
                SEVERITY_ERROR, "UNKNOWN_SOURCE_REF", oid, "source_ids",
                f"source id(s) not in the source register: {', '.join(unknown_sources)}; "
                "a card whose locator goes nowhere sends the reviewer nowhere"))
            continue

        role_id = obs.get("ask_role")
        role = roles.get(role_id)
        if role is None:
            # Not fatal: the question is still the right question. The reviewer
            # just has nobody scheduled to ask it, and needs to be told that.
            diagnostics.append(_diag(
                SEVERITY_WARNING, "NO_SESSION_FOR_ROLE", oid, "ask_role",
                f"role {role_id!r} is not in the interview register; card renders "
                "as UNSCHEDULED"))
            session_id, session_label, role_title = "UNSCHEDULED", "Not yet scheduled", "UNKNOWN"
        else:
            requested_session = role.get("session_id")
            session = sessions.get(requested_session) if isinstance(requested_session, str) else None
            role_title = role["title"]
            if session is None:
                diagnostics.append(_diag(
                    SEVERITY_WARNING, "NO_SESSION_FOR_ROLE", oid, "session_id",
                    f"role {role_id!r} refers to session {requested_session!r}, which "
                    "is not in the interview register; card renders as UNSCHEDULED"))
                session_id, session_label = "UNSCHEDULED", "Not yet scheduled"
            else:
                session_id, session_label = requested_session, session["label"]

        cards.append({
            "card_id": card_id_for(oid),
            "observation_id": oid,
            "group": obs.get("group"),
            "assessment_area": obs.get("assessment_area"),
            "uncertainty_type": utype,
            "uncertainty_label": template["label"],
            "session_id": session_id,
            "session_label": session_label,
            "ask_role": role_id,
            "role_title": role_title,
            "question": norm(question),
            "context": norm(context),
            "uncertainty_statement": norm(statement),
            "example_request": norm(request),
            "decision_informed": obs.get("decision_informed"),
            "outcome_map": outcomes,
            "absence_caveat": caveat,
            "open_findings": obs.get("open_findings", []),
            "source_ids": obs.get("source_ids", []),
            "source_locators": [sources[s]["locator"] for s in obs.get("source_ids", [])],
            "observation_summary": obs.get("summary", ""),
        })

    total = len(bundle["observations"]["observations"])
    errored = sorted({d["observation_id"] for d in diagnostics
                      if d["severity"] == SEVERITY_ERROR})
    coverage = {
        "observations_total": total,
        "cards_built": len(cards),
        "suppressed_with_reason": suppressed,
        "errored_observations": errored,
        # Nothing may vanish between the register and the cards.
        "accounted_for": len(cards) + len(suppressed) + len(errored),
    }
    return cards, diagnostics, coverage


# ------------------------------------------------------------------- search --

class CardIndex:
    """Deterministic local lexical index. No external service, no model.

    Free-text terms AND together; ``field:value`` terms filter exactly. That is
    enough for "find the card for this observation" and "show me everything I
    can ask the IAM administrator", which is what a reviewer actually does.
    """

    FIELDS = ("card_id", "observation_id", "group", "assessment_area",
              "uncertainty_type", "session_id", "ask_role")

    # Short forms a reviewer actually types. Rejecting `type:CONFLICT` with a
    # correct-but-unhelpful error is how a search box gets abandoned.
    ALIASES = {"type": "uncertainty_type", "area": "assessment_area",
               "role": "ask_role", "session": "session_id",
               "obs": "observation_id", "id": "card_id"}

    TEXT_PARTS = ("question", "context", "uncertainty_statement", "example_request",
                  "decision_informed", "observation_summary", "role_title",
                  "session_label")

    def __init__(self, cards):
        self.cards = unique_records(cards, "card_id", "search cards")
        self.tokens = {}
        for card in cards:
            blob = " ".join(str(card.get(p) or "") for p in self.TEXT_PARTS)
            blob += " " + " ".join(card.get("open_findings", []))
            blob += " " + " ".join(card.get("source_ids", []))
            blob += " " + card["observation_id"] + " " + card["card_id"]
            for token in set(re.findall(r"[\w-]+", fold(blob))):
                self.tokens.setdefault(token, set()).add(card["card_id"])

    def search(self, query):
        ids = set(self.cards)
        for term in query.split():
            if ":" in term:
                field, _, value = term.partition(":")
                field = self.ALIASES.get(field.lower(), field.lower())
                if field not in self.FIELDS:
                    raise ValueError(
                        f"unknown filter field {field!r}; use one of "
                        f"{', '.join(self.FIELDS)} (short forms: "
                        f"{', '.join(sorted(self.ALIASES))})")
                ids &= {cid for cid, c in self.cards.items()
                        if fold(str(c.get(field) or "")) == fold(value)}
            else:
                ids &= self.tokens.get(fold(term), set())
        return [self.cards[cid] for cid in sorted(ids)]


# ------------------------------------------------------------------ writing --

def csv_cell(value):
    """Spreadsheet-safe and reversible: NULL is \\N, an empty string is empty,
    and a formula-like value is marked as literal text rather than executed."""
    if value is None:
        return NULL_TOKEN
    text = norm(str(value))
    if text.startswith(RISKY_LEAD) or text.startswith("'"):
        text = "'" + text
    if text.startswith("\\"):
        text = "\\" + text
    return text


def md_cell(value):
    if value is None:
        return "_not recorded_"
    text = norm(str(value)).replace("\\", "\\\\").replace("|", "\\|")
    return text.replace("\r\n", " ⏎ ").replace("\n", " ⏎ ").replace("\r", " ⏎ ")


def write_cards_csv(path, cards):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(CARD_COLUMNS)
        for card in cards:
            row = dict(card)
            row["possible_answers"] = " | ".join(o["answer"] for o in card["outcome_map"])
            # Retain answer -> finding pairs; ASCII JSON also preserves exact
            # Unicode strings through csv_cell's display normalization.
            row["outcome_map_json"] = json.dumps(card["outcome_map"], ensure_ascii=True,
                                                 sort_keys=True, separators=(",", ":"))
            row["open_findings"] = ";".join(card["open_findings"])
            row["source_ids"] = ";".join(card["source_ids"])
            row["source_locators"] = ";".join(card["source_locators"])
            writer.writerow([csv_cell(row.get(name)) for name in CARD_COLUMNS])


def write_cards_markdown(path, cards, coverage, diagnostics):
    by_session = {}
    for card in cards:
        by_session.setdefault((card["session_id"], card["session_label"]), []).append(card)

    with open(path, "w", encoding="utf-8") as fh:
        w = fh.write
        w("# Follow-up interview question cards\n\n")
        w("**UIOWA-114 preparation artifact. Every observation, source, locator and "
          "role below is FICTION** invented for this kit. Nothing here is a University "
          "of Iowa finding, document or person, and no interview has been conducted, "
          "requested or scheduled.\n\n")
        w("Cards are grouped by interview session so a reviewer runs one sitting. "
          "They are deliberately **not ranked** — request prioritization is UIOWA-113's "
          "lane, and two rank orders in front of one reviewer is worse than none.\n\n")
        w(f"{coverage['cards_built']} card(s) from {coverage['observations_total']} "
          f"unresolved observation(s).\n\n")

        for (session_id, label), group in sorted(by_session.items()):
            w(f"## Session {session_id} — {label}\n\n")
            for card in group:
                w(f"### {card['card_id']} · {card['group']} / {card['assessment_area']}"
                  f" · {card['uncertainty_label']}\n\n")
                w(f"**Ask:** {card['role_title']}\n\n")
                w(f"**Question.** {card['question']}\n\n")
                w(f"**Context for the practitioner.** {card['context']}\n\n")
                w(f"**What is unresolved.** {card['uncertainty_statement']}\n\n")
                if card["absence_caveat"]:
                    w(f"> {card['absence_caveat']}\n\n")
                w(f"**Concrete request.** {card['example_request']}\n\n")
                w(f"**Decision this informs.** {card['decision_informed']}\n\n")
                w("**Where each answer leads:**\n\n")
                w("| If the answer is | The draft finding becomes |\n|---|---|\n")
                for outcome in card["outcome_map"]:
                    w(f"| {md_cell(outcome['answer'])} | {md_cell(outcome['resulting_finding'])} |\n")
                w("\n**Traceability.** "
                  f"observation `{card['observation_id']}` · open findings "
                  f"{', '.join('`%s`' % f for f in card['open_findings']) or 'none'} · sources: ")
                w("; ".join(f"`{sid}` → `{loc}`"
                            for sid, loc in zip(card["source_ids"], card["source_locators"])))
                w("\n\n---\n\n")

        w("## Coverage — nothing dropped silently\n\n")
        w(f"- Observations in register: **{coverage['observations_total']}**\n")
        w(f"- Cards built: **{coverage['cards_built']}**\n")
        w(f"- Suppressed with a stated reason: **{len(coverage['suppressed_with_reason'])}**\n")
        for item in coverage["suppressed_with_reason"]:
            w(f"  - `{item['observation_id']}` — {item['reason']}\n")
        w(f"- Rejected with an error: **{len(coverage['errored_observations'])}**"
          f" ({', '.join('`%s`' % o for o in coverage['errored_observations']) or 'none'})\n")
        w(f"- Accounted for: **{coverage['accounted_for']} of "
          f"{coverage['observations_total']}**\n\n")

        w("## Diagnostics\n\n")
        if not diagnostics:
            w("None.\n")
            return
        w("| Severity | Code | Observation | Field | Message |\n|---|---|---|---|---|\n")
        for d in diagnostics:
            w(f"| {d['severity']} | `{d['code']}` | `{d['observation_id']}` | "
              f"`{d['field']}` | {md_cell(d['message'])} |\n")


def build(data_dir, out_dir, observations_file="observations.json"):
    if __package__:
        from .export_publication import build_export
    else:
        from export_publication import build_export
    return build_export(
        data_dir, out_dir, observations_file,
        load_bundle=load_bundle, build_cards=build_cards,
        write_cards_csv=write_cards_csv, write_cards_markdown=write_cards_markdown)


# ---------------------------------------------------------------------- CLI --

def print_status(diagnostics, coverage):
    errors = [d for d in diagnostics if d["severity"] == SEVERITY_ERROR]
    warnings = [d for d in diagnostics if d["severity"] == SEVERITY_WARNING]
    print(f"observations={coverage['observations_total']} cards={coverage['cards_built']} "
          f"suppressed={len(coverage['suppressed_with_reason'])} "
          f"errors={len(errors)} warnings={len(warnings)} "
          f"accounted_for={coverage['accounted_for']}/{coverage['observations_total']}")
    for d in diagnostics:
        if d["severity"] != SEVERITY_INFO:
            print(f"  {d['severity']:<7} {d['code']:<26} {d['observation_id']:<24} {d['field']}")
    return errors


def _main(argv=None):
    root = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("command", choices=["build", "check", "search"])
    parser.add_argument("--data", default=os.path.join(root, "data"))
    parser.add_argument("--observations", default="observations.json")
    parser.add_argument("--out", default=os.path.join(root, "examples"))
    parser.add_argument("--query", default="")
    args = parser.parse_args(argv)

    if args.command == "search":
        bundle = load_bundle(args.data, args.observations)
        cards, diagnostics, coverage = build_cards(bundle)
        try:
            hits = CardIndex(cards).search(args.query)
        except ValueError as exc:
            print(f"bad query: {exc}")
            return 2
        errors = print_status(diagnostics, coverage)
        print(f"{len(hits)} card(s) for {args.query!r}")
        for card in hits:
            print(f"  {card['card_id']}  [{card['session_id']}/{card['ask_role']}]  "
                  f"{card['question'][:96]}")
        return 1 if errors else 0

    cards, diagnostics, coverage = build(args.data, args.out, args.observations)
    errors = print_status(diagnostics, coverage)
    if args.command == "check":
        return 1 if errors else 0
    return 0


def main(argv=None):
    try:
        return _main(argv)
    except (ValueError, OSError) as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
