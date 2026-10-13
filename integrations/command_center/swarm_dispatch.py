"""Bind canonical work to the command center's existing submit operation.

This adapter prepares the current assignment and prompt. The caller's existing
operation journal owns provider delivery, including uncertain outcomes.
"""
from __future__ import annotations

import hashlib
import json
from .schema import CoreError, _json, _metadata, _no_secret_fields

PROMPTS = {"gemini_submit": "message", "grokbot_submit": "prompt"}
FIELDS = {"task_key", "worker", "seat", "feed_cursor", "base_sha", "head_sha",
          "branch", "pr", "issue", "repo", "artifact", "required_capabilities",
          "priority", "source_event_ids", "exact_error", "model", "harness"}
CONTEXT_CHARS = 12000


def normalize(name, arguments, value):
    """Validate explicit dispatch metadata; unbound tools never enter here."""
    if name not in PROMPTS:
        raise CoreError(400, "swarm metadata is supported by gemini_submit and grokbot_submit.")
    if not isinstance(value, dict):
        raise CoreError(400, "swarm must be an object.")
    unknown = set(value) - FIELDS
    if unknown:
        raise CoreError(400, "Unknown swarm metadata: " + ", ".join(sorted(unknown)))
    _no_secret_fields(value)
    result = _metadata(value)
    worker = result.get("worker")
    if not isinstance(worker, str) or not worker.strip() or len(worker) > 180:
        raise CoreError(400, "swarm.worker must name the actual worker seat.")
    result["worker"] = worker = worker.strip()
    if "seat" in result and not isinstance(result["seat"], dict):
        raise CoreError(400, "swarm.seat must be an observed seat object.")
    if (result.get("seat") or {}).get("seat", worker) != worker:
        raise CoreError(400, "swarm.seat must describe swarm.worker.")
    if result.get("task_key"):
        from host.swarm_runtime.identity import task_key
        try:
            result["task_key"] = task_key(result["task_key"])
        except ValueError as exc:
            raise CoreError(400, str(exc)) from None
    elif "task_key" in result:
        raise CoreError(400, "Omit swarm.task_key to select next work; a supplied key must be explicit.")
    prompt = arguments.get(PROMPTS[name])
    if not isinstance(prompt, str) or not prompt.strip():
        raise CoreError(400, PROMPTS[name] + " must be nonempty text.")
    if name == "gemini_submit" and str(arguments.get("peer") or "").strip().upper() != worker:
        raise CoreError(400, "swarm.worker must match the submitted peer's normalized seat name.")
    if name == "grokbot_submit" and arguments.get("seat", worker) != worker:
        raise CoreError(400, "swarm.worker must match the submitted seat.")
    return result


def packet(task):
    """Render an already-bounded context bundle with a total prompt ceiling."""
    context = dict(task)
    encoded = _json(context)
    while len(encoded) > CONTEXT_CHARS and context.get("events"):
        context["events"] = context["events"][1:]
        encoded = _json(context)
    if len(encoded) > CONTEXT_CHARS:
        # Keep exact identifiers and useful source pointers when a provider
        # artifact or metadata object consumes the normal breadcrumb budget.
        keys = ("task_key", "state", "worker", "title", "repo", "issue", "pr",
                "base_sha", "head_sha", "branch", "feed_cursor", "source",
                "source_event_ids", "exact_error", "next_action")
        context = {key: task[key] for key in keys if key in task}
        context["context_truncated"] = True
        encoded = _json(context)
    if len(encoded) > CONTEXT_CHARS:
        context = {key: task[key] for key in ("task_key", "state", "worker", "repo", "issue", "pr")
                   if key in task}
        context["context_truncated"] = True
        encoded = _json(context)
    return "Canonical Commons assignment\n" + encoded


def assigned_arguments(name, arguments, task, requested_key=None):
    """Use the selected task's objective when next/collision routing changes it."""
    args = dict(arguments)
    context = packet(task)
    same_task = requested_key == task.get("task_key")
    instruction = "Continue this assigned task from its identifiers, current artifact and source events."
    if same_task:
        args[PROMPTS[name]] = context + "\n\nTask instruction\n" + arguments[PROMPTS[name]]
    else:
        args[PROMPTS[name]] = context + "\n\n" + instruction
    if name == "grokbot_submit":
        args["seat"] = task["worker"]
        if not same_task:
            # Paid-case metadata belongs to the original objective, not an
            # unrelated task selected after a collision or next operation.
            args.pop("case", None)
    return args


def prepare(center, name, arguments, metadata, operation_id):
    from .swarm_tasks import runtime

    child_id = "dispatch-" + hashlib.sha256(operation_id.encode("utf-8")).hexdigest()[:40]
    request = dict(metadata, operation_id=child_id)
    requested = metadata.get("task_key")
    summary = {"status": "unpublished", "requested_task_key": requested,
               "worker": metadata["worker"], "rerouted": False,
               "claim_operation_id": child_id}
    result = runtime(center).operate("take" if requested else "next", request,
                                     worker_activity=False)
    summary["claim_tip"] = result.get("tip")
    if result.get("ok") is not True or result.get("published") is not True:
        summary["reason"] = result.get("error", "canonical_publication_unconfirmed")
        if result.get("retry_after") is not None:
            summary["retry_after"] = result["retry_after"]
        return {"ready": False, "swarm": summary}
    outcome = result.get("result") or {}
    if outcome.get("replayed"):
        # Canonical custody can outlive this command center's journal. Its
        # prior provider delivery is then unknown, so never repeat the launch.
        summary.update(status="not_assigned", reason="existing_claim_operation")
        return {"ready": False, "swarm": summary}
    # A collision's next assignment takes precedence over the original task.
    candidates = [outcome.get("next")]
    if not outcome.get("collision"):
        candidates.append(outcome.get("task"))
    selected = next((row for row in candidates if isinstance(row, dict)
                     and row.get("state") == "ACTIVE"
                     and row.get("worker") == metadata["worker"]
                     and row.get("task_key")), None)
    if not selected:
        next_result = outcome.get("next") or {}
        collision = outcome.get("collision") or {}
        summary.update(status="not_assigned", reason=next_result.get("reason") or
                       collision.get("reason") or "no_current_assignment")
        return {"ready": False, "swarm": summary}
    summary.update(status="assigned", task_key=selected["task_key"],
                   rerouted=bool(requested and requested != selected["task_key"]))
    return {"ready": True, "swarm": summary,
            "arguments": assigned_arguments(name, arguments, selected, requested)}


def reserve_binding(center, operation_id, summary):
    """Bind one provider launch per task/worker in the existing journal lock."""
    target = summary["swarm"]
    with center._db() as db:
        db.execute("BEGIN IMMEDIATE")
        rows = db.execute("""SELECT id,status,summary FROM operations
            WHERE id<>? AND kind='tool' AND name IN ('gemini_submit','grokbot_submit')
              AND status NOT IN ('succeeded','failed','cancelled') AND summary IS NOT NULL
            ORDER BY started_at,id""", (operation_id,))
        for row in rows:
            prior = json.loads(row["summary"])
            binding = prior.get("swarm") or {}
            if (binding.get("task_key") == target["task_key"]
                    and binding.get("worker") == target["worker"]):
                return {**target, "status": "existing_dispatch", "reason": "existing_dispatch",
                        "existing_operation_id": row["id"], "existing_status": row["status"],
                        "existing_provider_refs": (prior.get("provider_refs") or [])[:40]}
        # A second process cannot pass the same scan before this binding is
        # visible. The external call remains outside the database transaction.
        db.execute("UPDATE operations SET summary=? WHERE id=?",
                   (_json(summary), operation_id))
    return None
