#!/usr/bin/env python3
"""Queue pending GROK.COM ACTION pages into wake_jobs. Never invokes a model.

commons-action-executor is starved by a cancelled workflow_run backlog, so a
landed p/{id}.md never becomes wake_jobs/{id}.json. The scheduled job-watchdog
tick materializes only this addressable grok.com boundary.

One ACTION page must not abort the rest of the tick. First-writer-wins
run_key identity stays; a later page with the same run_key and different
bytes is recorded, not a process crash, so later distinct jobs still queue
and land can still run.
"""
from __future__ import annotations

import json

import action_executor as ae
from independent_commons_mcp.jobs import JobError


def enqueue_pending_grok_com() -> dict:
    queued: list[str] = []
    collisions: list[dict] = []
    errors: list[dict] = []
    for rec in ae.pending("github"):
        if not ae.is_grok_com_target(rec["target"]) or rec["verb"] in {"POST", "REPLY"}:
            continue
        ident = rec["meta"]["id"]
        try:
            result = ae.queue_grok_com_task(rec["meta"], rec["verb"], rec["payload"], ident)
        except JobError as exc:
            row = exc.payload()
            row["id"] = ident
            if exc.code == "RUN_KEY_COLLISION":
                collisions.append(row)
            else:
                errors.append(row)
            continue
        except ValueError as exc:
            errors.append({
                "id": ident,
                "ok": False,
                "code": "VALUE",
                "message": str(exc),
            })
            continue
        queued.append(str(result.get("job_path") or ("wake_jobs/%s.json" % ident)))
    return {
        "ok": True,
        "queued": queued,
        "collisions": collisions,
        "errors": errors,
    }


def main() -> int:
    print(json.dumps(enqueue_pending_grok_com(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
