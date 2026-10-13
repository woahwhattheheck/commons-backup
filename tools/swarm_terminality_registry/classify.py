#!/usr/bin/env python3
"""Pure classification derivation for normalized terminality snapshots."""
from .schema import CLASSIFICATIONS, NEXT_ACTIONS, RegistryError, _timestamp

def _derive(snapshot):
    now = _timestamp(snapshot["evaluated_at_utc"], "evaluated_at_utc")
    iidx = {x["id"]: x for x in snapshot["items"]}
    oidx = {x["id"]: x for x in snapshot["provider_observations"]}
    heartbeat_by_item = {}
    for hb in snapshot["heartbeats"]:
        heartbeat_by_item.setdefault(hb["item_id"], []).append(hb)
    successor_by_pred = {x["predecessor_item_id"]: x for x in snapshot["successors"]}

    def freshness(obs):
        when = _timestamp(obs["observed_at_utc"], "provider_observation.observed_at_utc")
        if when > now:
            return "FUTURE", -1
        age = int((now - when).total_seconds())
        return ("CURRENT" if age <= snapshot["max_provider_age_seconds"] else "STALE"), age

    provider_status = {}
    for item in snapshot["items"]:
        obs = oidx[item["provider_observation_id"]]
        status, age = freshness(obs)
        provider_status[item["id"]] = (status, age)

    rows = []
    for item in snapshot["items"]:
        item_id = item["id"]
        obs = oidx[item["provider_observation_id"]]
        status, age = provider_status[item_id]
        reasons = []
        active_heartbeats = []
        invalid_heartbeats = []
        for hb in heartbeat_by_item.get(item_id, []):
            observed = _timestamp(hb["observed_at_utc"], "heartbeat.observed_at_utc")
            expires = _timestamp(hb["expires_at_utc"], "heartbeat.expires_at_utc")
            if observed > now:
                invalid_heartbeats.append(f"heartbeat {hb['id']} is future-dated")
                continue
            hb_age = int((now - observed).total_seconds())
            if hb_age <= snapshot["max_heartbeat_age_seconds"] and now < expires:
                active_heartbeats.append(hb)
        if invalid_heartbeats:
            reasons.extend(invalid_heartbeats)

        edge = successor_by_pred.get(item_id)
        successor = None
        successor_status = None
        if edge:
            successor = iidx[edge["successor_item_id"]]
            successor_status, _ = provider_status[successor["id"]]

        state = obs["provider_state"]
        classification = None
        action = None

        if status != "CURRENT":
            reasons.append(f"selected provider observation is {status.lower()}")
            classification = "HOLD_INCOMPLETE_EVIDENCE"
            action = "REFRESH_EVIDENCE"
        elif invalid_heartbeats:
            classification = "HOLD_INCOMPLETE_EVIDENCE"
            action = "REFRESH_EVIDENCE"
        elif state in {"UNKNOWN", "ABSENT"}:
            reasons.append(f"provider state {state} is not terminality-authoritative")
            classification = "HOLD_INCOMPLETE_EVIDENCE"
            action = "REFRESH_EVIDENCE"
        elif state == "MERGED":
            classification = "TERMINAL_MERGED"
            action = "NONE"
        elif edge:
            if successor_status != "CURRENT":
                reasons.append("canonical successor provider evidence is not current")
                classification = "HOLD_INCOMPLETE_EVIDENCE"
                action = "REFRESH_EVIDENCE"
            else:
                succ_obs = oidx[successor["provider_observation_id"]]
                if succ_obs["provider_state"] in {"UNKNOWN", "ABSENT"}:
                    reasons.append("canonical successor state is not materially observable")
                    classification = "HOLD_INCOMPLETE_EVIDENCE"
                    action = "REFRESH_EVIDENCE"
                else:
                    classification = "SUPERSEDED"
                    if state in {"OPEN", "PRESENT"} and succ_obs["provider_state"] in {"MERGED", "CLOSED"}:
                        action = "CLOSE_STALE_CARRIER"
                    elif state in {"OPEN", "PRESENT"}:
                        action = "REVIEW_SUCCESSOR"
                    else:
                        action = "NONE"
        elif state == "CLOSED":
            classification = "TERMINAL_CLOSED"
            action = "NONE"
        elif active_heartbeats:
            classification = "ACTIVE_CUSTODY"
            action = "NONE"
        elif state in {"OPEN", "PRESENT"}:
            classification = "RECOVERY_ELIGIBLE"
            action = "RECOVER"
        else:
            reasons.append(f"unhandled provider state {state}")
            classification = "HOLD_INCOMPLETE_EVIDENCE"
            action = "REFRESH_EVIDENCE"

        if classification not in CLASSIFICATIONS or action not in NEXT_ACTIONS:
            raise RegistryError("internal classification contract violation")
        rows.append({
            "item_id": item_id,
            "kind": item["kind"],
            "locator": item["locator"],
            "provider_state": state,
            "provider_observation_id": obs["id"],
            "provider_observation_age_seconds": age,
            "classification": classification,
            "recommended_next_action": action,
            "active_owners": sorted({hb["owner"] for hb in active_heartbeats}),
            "canonical_successor_item_id": edge["successor_item_id"] if edge else None,
            "reasons": sorted(set(reasons)),
        })
    rows.sort(key=lambda x: x["item_id"])
    return rows


