"""Deathstar decision rows over the existing /api/work state.

One exception queue and one row per active operation; receipts and typed
stage records are drilldowns. Pure reducer plus a reader that reuses the
existing local work snapshot and coordination-head cache. Adds no collector,
provider call or data store.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import math
import time

from .observability import _heartbeat_state, LIVE_S, QUIET_S, STALE_S
from .summary import MAX_ROWS, MONEY_KINDS, canonical_pr, epoch, scalar, short, source_freshness
# Decision rows: one per active operation; receipts are a drilldown. An item
# joins an operation only through an explicit operation key, never by title.
# Eligibility-to-payout is a list of typed stage records per program, each
# with who acts, a deadline if any, and evidence or "unknown: <source>".
STAGES = ("pre_work_application", "claim_or_attempt_posted", "platform_import", "sponsor_pr_open",
          "accepted_or_merged", "payout_requested", "payout_onboarding", "paid")
STAGE_ALIASES = {"application": "pre_work_application", "claim": "claim_or_attempt_posted",
                 "attempt": "claim_or_attempt_posted", "import": "platform_import",
                 "pr_open": "sponsor_pr_open", "merged": "accepted_or_merged", "accepted": "accepted_or_merged",
                 "expense_requested": "payout_requested", "onboarding": "payout_onboarding",
                 "settled": "paid"}
# Expected days in a stage before it reads stalled.
GATE_WINDOW_DAYS = {"pre_work_application": 14, "claim_or_attempt_posted": 14, "platform_import": 7,
                    "sponsor_pr_open": 21, "accepted_or_merged": 7, "payout_requested": 30,
                    "payout_onboarding": 7}
# Who acts on a pending stage unless the record says otherwise.
DEFAULT_WHO_ACTS = {"payout_onboarding": "owner_only", "accepted_or_merged": "us"}
PENDING_TEXT = {"pre_work_application": "acknowledgment", "claim_or_attempt_posted": "claim acceptance",
                "platform_import": "platform import", "sponsor_pr_open": "sponsor merge",
                "accepted_or_merged": "acceptance", "payout_requested": "payment",
                "payout_onboarding": "payout onboarding"}
NEXT_STAGE_ACTION = {"accepted_or_merged": "File the expense or payout request.",
                     "sponsor_pr_open": "Request the expense after the sponsor merges.",
                     "payout_requested": "Follow up on the payout request."}
# grantfox_execution_readiness application_state vocabulary, plus acknowledgments.
STATE_DONE = {"done", "acknowledged", "accepted", "approved", "assigned_current_contributor", "merged",
              "imported", "paid", "settled", "complete", "completed"}
STATE_MISSING = {"missing", "not_submitted", "not_posted", "not_imported"}
STATE_REFUSED = {"rejected", "withdrawn", "ineligible", "assigned_other", "closed_unmerged"}
PUBLICATION = {"OUTBOUND_ROUTE_BLOCKED": "held:route", "OUTBOUND_IDENTITY_BLOCKED": "held:identity",
               "PUBLICATION_BLOCKED": "held:terms"}
PUBLICATION_STATES = {"clear", "held:route", "held:identity", "held:terms", "retry_pending"}
DEADLINE_WINDOW = 7 * 86400
PAID_STATES = {"paid", "settled"}
UNKNOWN = "unknown"


def _dict(value):
    return value if isinstance(value, dict) else {}


def operation_key(item):
    meta, refs = _dict(item.get("metadata")), _dict(item.get("refs"))
    for value in (meta.get("operation"), meta.get("operation_id"), refs.get("operation")):
        if isinstance(value, str) and value.strip():
            return short(value.strip(), 160)
    return None


def _stage_name(value):
    text = short(value, 60).strip().lower().replace(" ", "_").replace("-", "_")
    text = STAGE_ALIASES.get(text, text)
    return text if text in STAGES else None


def _observed_at(item):
    """Provider update/read time, then ingestion time; never stage-entry time."""
    for name in ("updated_at", "activity_observed_at", "last_seen_at"):
        value = item.get(name)
        if epoch(value) is not None:
            return value
    return None


def stage_record(item):
    """A typed stage record from explicit fields, else typed PR/payment facts."""
    meta, refs = _dict(item.get("metadata")), _dict(item.get("refs"))
    kind, status = short(item.get("kind")).lower(), short(item.get("status")).lower()
    stage = _stage_name(item.get("stage") or meta.get("provider_stage"))
    if stage is None and kind == "application":
        stage = "pre_work_application"
    if stage is None and kind == "pull_request":
        stage = ("accepted_or_merged" if refs.get("merged_at") or status == "merged"
                 else "sponsor_pr_open" if status == "open" else None)
    if stage is None and kind in MONEY_KINDS:
        stage = ("paid" if status in PAID_STATES else "payout_requested"
                 if status in {"payment_pending", "pending", "payable", "invoiced"} else None)
    if stage is None:
        return None
    raw = short(meta.get("stage_state") or status, 60).lower()
    state = ("done" if raw in STATE_DONE or stage == "accepted_or_merged" and (refs.get("merged_at") or status == "merged")
             or stage == "paid" and raw in PAID_STATES
             else "missing" if raw in STATE_MISSING else "refused" if raw in STATE_REFUSED
             else UNKNOWN if raw in {"", "unknown", "unavailable", "unverified"} else "pending")
    who = short(meta.get("who_acts"), 20).lower()
    if who not in {"us", "them", "owner_only"}:
        who = ("us" if state in {"missing", "refused"} else DEFAULT_WHO_ACTS.get(stage, "them")
               if state == "pending" else UNKNOWN)
    entered = (meta.get("stage_entered_at") or (refs.get("merged_at") if stage == "accepted_or_merged" else None)
               or item.get("updated_at") or item.get("activity_observed_at"))
    observed = meta.get("stage_observed_at")
    observed = observed if epoch(observed) is not None else _observed_at(item)
    deadline = meta.get("deadline") or item.get("due_at")
    url = short(item.get("url") or meta.get("evidence_url"), 1024)
    return {"stage": stage, "state": state, "who_acts": who,
            "label": short(item.get("title") or stage.replace("_", " ")),
            "party": short(meta.get("party") or item.get("provider") or UNKNOWN, 80),
            "owner_account": short(meta.get("owner_account") or item.get("owner"), 120) or UNKNOWN,
            "deadline": deadline if epoch(deadline) is not None else None,
            "entered_at": entered if epoch(entered) is not None else None,
            "observed_at": observed,
            "evidence": url if url.startswith(("https://", "http://")) else
                        "unknown: " + short(meta.get("answer_source") or "provider record for this stage", 200),
            "action": short((item.get("owner_work") or {}).get("next_action") or item.get("next_action")
                            or meta.get("action"), 280) or None,
            "item": (item.get("source_id"), item.get("id"))}


def _amount(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return amount if amount.is_finite() and amount >= 0 else None


def _money(amount, currency):
    return {"currency": currency, "amount": str(amount)}


def _publication(meta):
    raw = meta.get("publication_state")
    hold = _dict(meta.get("publication"))
    state = PUBLICATION.get(str(hold.get("state") or ""), raw if raw in PUBLICATION_STATES else None)
    if state is None:
        return None
    fields = [short(v, 60) for v in (hold.get("matched_fields") or [])[:10]]
    terms = [short(v, 60) for v in (hold.get("matched_terms") or [])[:10]]
    instruction = (f"Remove {', '.join(terms) or 'the matched terms'} from {', '.join(fields) or 'the matched fields'}, then retry the same operation."
                   if state.startswith("held") else "Retry the same operation id." if state == "retry_pending" else None)
    return {"state": state, "matched_fields": fields, "matched_terms": terms, "instruction": instruction}


def _health_index(work):
    health = _dict(work.get("source_health"))
    rows = {}
    for row in list(health.get("sources") or [])[:500]:
        if isinstance(row, dict) and isinstance(row.get("source_id"), str):
            rows[row["source_id"]] = row
    return health, rows


def _source_state(source, health, tick):
    """Freshness, cooldown and last cycle from source_health; unknown when absent."""
    row = health or {}
    cooldown = _dict(row.get("cooldown"))
    age = row.get("last_success_age_seconds")
    if type(age) is not int:
        stamp = epoch(row.get("last_success_at") or source.get("last_good_observed_at"))
        age = None if stamp is None else max(0, int(tick - stamp))
    return {"id": short(source.get("id"), 512),
            "collector": scalar(row.get("collector")) or UNKNOWN,
            "freshness": ("stale" if row.get("data_stale") is True else "fresh" if row.get("data_stale") is False
                          else source_freshness(source, tick)),
            "last_success_age_seconds": age,
            "last_cycle": scalar(row.get("last_cycle")) or UNKNOWN,
            "last_cycle_reason": scalar(row.get("last_cycle_reason"), 280),
            "cooldown": ("rate_limited" if cooldown.get("active") is True else "ready"
                         if cooldown.get("active") is False else UNKNOWN),
            "retry_not_before": scalar(cooldown.get("retry_not_before")),
            "coverage": "complete" if _dict(source.get("coverage")).get("complete") is True else "partial"}


def _waiting(records):
    """(waiting_on, waiting_for, blocking record or None, default next action)."""
    ordered = sorted(records, key=lambda r: STAGES.index(r["stage"]))
    for record in ordered:
        if record["state"] == "done":
            continue
        name = record["label"]
        if record["state"] in {"missing", "refused"}:
            verb = "submit" if record["state"] == "missing" else "resolve " + record["state"]
            party = record["party"]
            text = f"{verb} {name}" + ("" if party == UNKNOWN or name.lower().startswith(party.lower()) else " to " + party)
            return "waiting_on_us", text, record, record["action"] or text[0].upper() + text[1:] + "."
        if record["state"] == UNKNOWN:
            return UNKNOWN, name, record, record["action"] or f"Read the {name} state."
        if record["who_acts"] in {"us", "owner_only"}:
            return ("waiting_on_us", name + (" (owner only)" if record["who_acts"] == "owner_only" else ""),
                    record, record["action"] or f"Complete {name}.")
        text = PENDING_TEXT.get(record["stage"], "response")
        party = record["party"]
        target = (name if party != UNKNOWN and name.lower().startswith(party.lower())
                  else f"{text}: {name}" if party == UNKNOWN else f"{party} {text}: {name}")
        return ("waiting_on_them", target, record,
                record["action"] or NEXT_STAGE_ACTION.get(record["stage"]) or f"Follow up on {name}.")
    last = ordered[-1]["stage"] if ordered else None
    if last == "paid":
        return "none", "nothing", None, "Close the operation."
    if last == "accepted_or_merged":
        return "waiting_on_us", "expense or payout request", None, NEXT_STAGE_ACTION[last]
    if last == "payout_requested":
        return "waiting_on_them", "payment", None, NEXT_STAGE_ACTION[last]
    return UNKNOWN, UNKNOWN, None, "Record the provider stage."


def build_decisions(work, now=None, operator_control=None):
    current = datetime.now(timezone.utc) if now is None else now
    tick = current.timestamp()
    sources = {source["id"]: source for source in work.get("sources", []) if isinstance(source, dict)}
    health, health_rows = _health_index(work)
    groups = {}
    for item in work.get("items", []):
        key = operation_key(item) if isinstance(item, dict) else None
        if key is not None:
            groups.setdefault(key, []).append(item)
    rows, blocked_agents, exceptions = [], [], []
    for key, members in groups.items():
        records, agents, merged_prs, payments, advertised, owner = [], {}, set(), {}, {}, {}
        publication, recorded_next = None, None
        money_conflicts = set()
        for item in members:
            meta, refs = _dict(item.get("metadata")), _dict(item.get("refs"))
            record = stage_record(item)
            if record is not None:
                records.append(record)
                if short(item.get("kind")).lower() == "pull_request" and record["stage"] == "accepted_or_merged":
                    merged_prs.add(canonical_pr(item, refs) or record["item"])
            currency = short(item.get("currency") or meta.get("currency"), 8).upper() or "UNKNOWN"
            listed = _amount(meta.get("advertised_amount"))
            if listed is not None:
                advertised[currency] = max(advertised.get(currency, Decimal(0)), listed)
            if short(item.get("kind")).lower() in MONEY_KINDS:
                provider = str(item.get("provider") or sources.get(item.get("source_id"), {}).get("provider") or "").lower()
                payment_id = refs.get("payment_id") or refs.get("transaction_id")
                # Provider transaction ids are shared; connector-local row ids are not.
                identity = (("payment", provider, str(payment_id)) if provider and payment_id is not None
                            else ("source", str(item.get("source_id")), str(item.get("id"))))
                seen = (epoch(item.get("updated_at")) or epoch(item.get("activity_observed_at"))
                        or epoch(item.get("last_seen_at")) or 0)
                value = (currency, short(item.get("status")).lower(), _amount(item.get("amount")))
                if identity not in payments or seen > payments[identity][0]:
                    payments[identity] = (seen, *value)
                    money_conflicts.discard(identity)
                elif seen == payments[identity][0] and value != payments[identity][1:]:
                    money_conflicts.add(identity)
            for field in ("owner_account", "seat"):
                if meta.get(field) and field not in owner:
                    owner[field] = short(meta[field], 120)
            if item.get("owner"):
                owner.setdefault("owner_account", short(item["owner"], 120))
            publication = _publication(meta) or publication
            if record is None:
                recorded_next = recorded_next or (item.get("owner_work") or {}).get("next_action")
            beat = meta.get("heartbeat_at") or refs.get("heartbeat_at")
            if beat is not None or meta.get("seat"):
                ident = str(meta.get("session_id") or meta.get("seat") or item.get("id"))
                liveness, age = _heartbeat_state(beat, current, (LIVE_S, QUIET_S, STALE_S))
                declared = short(meta.get("agent_state")).lower()
                status = short(item.get("status")).lower()
                state = (declared if declared in {"blocked", "active", "idle"}
                         else "blocked" if status == "blocked" or item.get("needs_attention") is True
                         else UNKNOWN if beat is None or str(liveness).lower() == UNKNOWN
                         else "active" if liveness == "LIVE" else "idle")
                agent = {"seat": scalar(meta.get("seat")) or UNKNOWN,
                         "model_family": scalar(meta.get("model_family") or meta.get("family")) or UNKNOWN,
                         "session": scalar(meta.get("session_id"), 512), "heartbeat_at": scalar(beat),
                         "heartbeat_age_seconds": age if isinstance(age, int) else None, "state": state,
                         "blocker": scalar(meta.get("blocker") or item.get("attention_reason"), 280)}
                if ident not in agents or (epoch(beat) or 0) >= (epoch(agents[ident]["heartbeat_at"]) or 0):
                    agents[ident] = agent
        # One record per stage: the latest observation of that stage wins.
        latest = {}
        for record in records:
            prior = latest.get(record["stage"])
            seen = epoch(record["observed_at"]) or 0
            prior_seen = (epoch(prior["observed_at"]) or 0) if prior else 0
            if prior is None or seen > prior_seen:
                latest[record["stage"]] = record
            elif seen == prior_seen and (record["state"], record["who_acts"]) != (prior["state"], prior["who_acts"]):
                latest[record["stage"]] = {**prior, "state": UNKNOWN, "who_acts": UNKNOWN,
                    "action": "Reconcile conflicting observations of this stage.",
                    "evidence": "unknown: provider stage records disagree at the same observation time"}
        records = sorted(latest.values(), key=lambda r: STAGES.index(r["stage"]))
        waiting_on, waiting_for, blocking, next_action = _waiting(records)
        reasons = ["stage:" + blocking["stage"]] if blocking else []
        next_action = recorded_next or next_action
        reached = [r for r in records if r["state"] in {"done", "pending"}]
        stage = reached[-1] if reached else (records[-1] if records else None)
        paid_stage = stage is not None and stage["stage"] == "paid" and stage["state"] == "done"
        collected, unresolved_payment = {}, bool(money_conflicts)
        for identity, (_, currency, status, paid) in payments.items():
            if identity in money_conflicts or status not in PAID_STATES:
                continue
            if paid is None or currency == "UNKNOWN":
                unresolved_payment = True
                continue
            collected[currency] = collected.get(currency, Decimal(0)) + paid
        # A paid transaction can be an installment, not settlement of the operation.
        # Never net currencies or replace a remaining advertised amount with zero.
        at_risk = {c: max(Decimal(0), v - collected.get(c, Decimal(0))) for c, v in advertised.items()}
        remaining = {c: v for c, v in at_risk.items() if v > 0}
        # Closing an operation requires a known total and matching-currency cash.
        # Missing totals and unmatched currencies are reconciliation, not zero due.
        unreconciled_basis = paid_stage and (not advertised or not collected
                            or "UNKNOWN" in advertised or bool(set(collected) - set(advertised)))
        settlement = ("amount_unknown" if unresolved_payment or unreconciled_basis else
                      "partial" if paid_stage and remaining else "covered" if paid_stage else "not_observed")
        payout_issue, payout_action, payout_actor = None, None, "them"
        if unresolved_payment or unreconciled_basis:
            payout_issue, payout_actor = "unreconciled_payout", "us"
            payout_action = "Reconcile the operation total and latest payment amounts/currencies with the provider; retain the operation."
        elif paid_stage and remaining:
            payout_issue = "partial_payout"
            balance = "; ".join(f"{c} {v}" for c, v in sorted(remaining.items()))
            payout_action = "Follow up on the remaining advertised amount: " + balance + "."
        recorded_payout_action = (recorded_next or (stage or {}).get("action")) if payout_issue else None
        if payout_issue:
            payout_action = recorded_payout_action or payout_action
            if (stage or {}).get("action") and stage["who_acts"] in {"us", "them", "owner_only"}:
                payout_actor = stage["who_acts"]
            reasons.append("payout:" + payout_issue)
            if blocking is None:
                waiting_on = "waiting_on_us" if payout_actor in {"us", "owner_only"} else "waiting_on_them"
                waiting_for = "payment reconciliation" if payout_issue == "unreconciled_payout" else "remaining advertised amount"
                next_action = payout_action
        if publication and publication["state"] != "clear":
            waiting_on, waiting_for = "waiting_on_us", "held outward write (" + publication["state"] + ")"
            next_action = publication["instruction"]
            reasons.insert(0, "publication:" + publication["state"])
        terminal = bool(paid_stage and not payout_issue and blocking is None
                        and (publication is None or publication["state"] == "clear"))
        # A gate stalls when the blocking stage, or the furthest stage reached
        # while payout is still open, sits past its window.
        gate, window, age_days, stalled = blocking or stage, None, None, False
        for candidate in ([blocking] if blocking else []) + ([stage] if stage and not terminal else []):
            limit = GATE_WINDOW_DAYS.get(candidate["stage"])
            days = None if epoch(candidate["entered_at"]) is None else round((tick - epoch(candidate["entered_at"])) / 86400, 1)
            if limit is not None and days is not None and days > limit:
                gate, window, age_days, stalled = candidate, limit, days, True
                break
            if candidate is gate:
                window, age_days = limit, days
        account = owner.get("owner_account") or UNKNOWN
        found = []
        for record in records:
            if record["state"] == "done":
                continue
            due = epoch(record["deadline"])
            if due is not None and due - tick <= DEADLINE_WINDOW:
                found.append(("deadline_past" if due < tick else "deadline_within_7d", record))
            if record["who_acts"] == "owner_only":
                found.append(("owner_only", record))
        if stalled:
            found.append(("stalled", gate))
        if payout_issue:
            found.append((payout_issue, stage))
        if publication and publication["state"] != "clear":
            found.append(("publication_" + publication["state"].replace(":", "_"), None))
        for reason, record in found:
            exceptions.append({
                "operation": key, "reason": reason, "stage": record["stage"] if record else None,
                "deadline": record["deadline"] if record else None,
                "stage_age_days": age_days if reason == "stalled" else None,
                "gate_window_days": window if reason == "stalled" else None,
                "who_acts": (payout_actor if reason == payout_issue else
                             ((blocking or {}).get("who_acts") or "us") if reason == "stalled" else record["who_acts"] if record else "us"),
                "account": (record["owner_account"] if record and record["owner_account"] != UNKNOWN else account),
                "action": (payout_action if reason == payout_issue else next_action if reason == "stalled" else
                           record["action"] if record and record["action"] else
                           publication["instruction"] if record is None else
                           next_action if record is blocking else f"Complete {record['label']}."),
                "waiting_on": waiting_on, "waiting_for": waiting_for})
        unknowns = [{"field": "stage", "answer_source": "provider stage on the operation record (stage or metadata.provider_stage)"}] if not records else []
        if not advertised:
            unknowns.append({"field": "money_at_risk", "answer_source": "advertised amount on the bounty/program listing (metadata.advertised_amount)"})
        if unreconciled_basis:
            unknowns.append({"field": "settlement", "answer_source": "advertised operation total and matching-currency paid amounts on provider records"})
        if unresolved_payment:
            unknowns.append({"field": "money_collected", "answer_source": "latest provider payment records; displayed amounts include only unconflicted payments with known amounts and currencies"})
        if account == UNKNOWN:
            unknowns.append({"field": "owner", "answer_source": "claim holder in state/claims or metadata.owner_account"})
        if waiting_on == UNKNOWN and blocking is not None:
            unknowns.append({"field": "waiting_on", "answer_source": blocking["evidence"]})
        used = sorted({item.get("source_id") for item in members if item.get("source_id") in sources})
        agent_rows = sorted(agents.values(), key=lambda a: (a["state"] != "blocked", a["seat"]))
        rows.append({
            "operation": key, "stage": stage["stage"] if stage else UNKNOWN,
            "stage_state": ("partial" if payout_issue == "partial_payout" else "unreconciled"
                            if payout_issue else stage["state"]) if stage else UNKNOWN,
            "settlement_state": settlement,
            "stages": [{k: v for k, v in r.items() if k != "item"} for r in records],
            "stage_age_days": age_days, "gate_window_days": window, "gate_stale": stalled,
            "merged_prs": len(merged_prs),
            "waiting_on": waiting_on, "waiting_for": waiting_for, "waiting_reasons": reasons,
            "next_action": short(next_action, 280), "next_action_recorded": bool(recorded_next or (blocking or {}).get("action") or recorded_payout_action),
            "owner": {"owner_account": account, "seat": owner.get("seat") or UNKNOWN},
            "publication_state": publication["state"] if publication else "clear",
            "publication": publication,
            "money_at_risk": [_money(v, c) for c, v in sorted(at_risk.items())] or UNKNOWN,
            "money_collected": [_money(v, c) for c, v in sorted(collected.items())] or (
                [_money(Decimal(0), c) for c in sorted(advertised)] if advertised and not unresolved_payment else UNKNOWN),
            "payment_conflicts": len(money_conflicts),
            "terminal": terminal,
            "agents": agent_rows[:MAX_ROWS],
            "sources": [_source_state(sources[s], health_rows.get(s), tick) for s in used][:MAX_ROWS],
            "unknown": unknowns,
            "receipt_count": len(members),
            "receipts": [{"source_id": short(i.get("source_id"), 512), "item_id": short(i.get("id"), 512),
                          "kind": short(i.get("kind"), 60), "status": short(i.get("status"), 60),
                          "title": short(i.get("title")), "url": short(i.get("url"), 1024) or None,
                          "last_ingested_at": i.get("last_seen_at")}
                         for i in sorted(members, key=lambda i: str(i.get("last_seen_at") or ""), reverse=True)[:25]],
        })
        blocked_agents += [{"operation": key, **a} for a in agent_rows if a["state"] == "blocked"]
    active = [r for r in rows if not r["terminal"]]
    order = {"waiting_on_us": 0, UNKNOWN: 1, "waiting_on_them": 2, "none": 3}
    flagged = {e["operation"] for e in exceptions}
    active.sort(key=lambda r: (r["operation"] not in flagged,
                               not any(a["state"] == "blocked" for a in r["agents"]),
                               order.get(r["waiting_on"], 1), r["operation"]))
    exceptions.sort(key=lambda e: (e["reason"] not in {"deadline_past", "deadline_within_7d"},
                                   epoch(e["deadline"]) or math.inf, e["operation"]))
    totals = {"at_risk": {}, "collected": {}}
    for row in rows:
        for field, total in (("money_at_risk", totals["at_risk"]), ("money_collected", totals["collected"])):
            for money in row[field] if isinstance(row[field], list) else []:
                total[money["currency"]] = total.get(money["currency"], Decimal(0)) + Decimal(money["amount"])
    control = _dict(operator_control)
    mode = control.get("mode") if control.get("mode") in {"RUN", "DRAIN", "ABORT"} else (
        "RUN" if operator_control is None else UNKNOWN)
    coverage = _dict(health.get("coverage"))
    return {
        "ok": True, "schema": "commons-deathstar-decisions/v2",
        "operator_control": {"mode": mode, **{k: scalar(control.get(k), 280) for k in ("set_by", "set_at", "note", "source")}},
        "collection": {"schema": scalar(health.get("schema")) or UNKNOWN,
                       "complete": coverage.get("complete") if isinstance(coverage.get("complete"), bool) else UNKNOWN,
                       **{k: coverage.get(k) if type(coverage.get(k)) is int else None for k in
                          ("expected_count", "fetched_count", "failed_count", "deferred_count", "skipped_count")},
                       "cooldowns": [{k: scalar(c.get(k)) for k in ("scope", "reason", "retry_not_before", "retry_remaining_seconds")}
                                     for c in list(health.get("cooldowns") or [])[:MAX_ROWS] if isinstance(c, dict)]},
        "generated_at": current.isoformat().replace("+00:00", "Z"), "provider_requests": 0,
        "operations": {"active": len(active), "terminal": len(rows) - len(active), "shown": min(len(active), 50)},
        "exceptions": exceptions[:MAX_ROWS * 2], "exceptions_omitted": max(0, len(exceptions) - MAX_ROWS * 2),
        "blocked_agents": blocked_agents[:MAX_ROWS],
        "money": {key: [_money(v, c) for c, v in sorted(value.items())] for key, value in totals.items()},
        "rows": active[:50],
        "stage_order": list(STAGES),
        "grouping": "Items join an operation only through metadata.operation / metadata.operation_id / refs.operation; rows join /api/work items and /api/mail threads by that id.",
        "scope": "Projection of the /api/work state (source_health included); no provider reads of its own. Receipts are a drilldown; unknown names the source that would answer it.",
    }


def read(center, repo_root=None):
    """Cache-only reader; work_state()/observability() can start provider reads."""
    with center._summary_lock:
        work, cache = center._shared_work_snapshot_locked()
    with center._bakes_lock:
        cached = dict(center._bakes.get("\0coordination-head") or {})
    observed = _dict(cached.get("read"))
    age = time.time() - cached.get("fetched", 0)
    fresh = observed.get("ok") is True and 0 <= age < center.BAKE_TTL
    control = {"mode": UNKNOWN, "note": "Coordination cache is missing or stale; refresh the existing observability view."}
    if fresh:
        value = _dict(observed.get("value"))
        control = value.get("operator_control")
        # A successfully observed head with no override preserves the RUN default.
        if control is not None and not isinstance(control, dict):
            control = {"mode": UNKNOWN}
    result = build_decisions(work, operator_control=control)
    result["cache"] = cache
    result["operator_control_source"] = {"cache_only": True, "fresh": fresh,
                                          "observed_at": scalar(observed.get("observed_at"))}
    return result
