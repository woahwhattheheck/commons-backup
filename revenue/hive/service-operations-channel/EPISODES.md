# Service Operations Channel · 10-episode slate

The series teaches practical operation of the landed intake/customer/job/task workflow without inventing a separate application.

1. **Intake to a trackable job** — turn one source request into one customer, one job, tasks and a queued event.
2. **Move a job through task completion** — use the checklist to progress a job from `new` to `in_progress` to `complete`.
3. **Retry only the selected delivery** — demonstrate PR #10513's selected-event retry without consuming an unrelated queued event.
4. **Idempotent intake replay** — resubmit the same source ID and payload without creating duplicate customer/job state.
5. **Source-ID conflict recovery** — distinguish a true replay from a changed payload that requires a new source ID.
6. **Local notification delivery** — use the blank-endpoint local feed and explain durable outbox state.
7. **HTTP receiver handoff** — configure a synthetic loopback receiver and preserve the `Idempotency-Key` contract.
8. **Lease expiry and retry** — show why a failed acknowledgement retries the same event ID instead of creating a new event.
9. **Field-mapping intake** — map a different source JSON shape into the canonical service-operation fields.
10. **Export and operator recovery** — export a workspace, inspect linked records, and resume the operator's next action without implying external backup.

---

## Episode 1 · Intake to a trackable job

**Description:** Create one synthetic cleaning request and watch the landed intake workflow produce one customer, one job, three tasks, and one queued delivery without a duplicate record.

**Scene 1 — 00:00–00:04**  
Start in a clean local workspace backed by the landed Hive intake application. Point out the zeroed customer/job/open-task/awaiting-delivery counters and the empty job panel.

**Scene 2 — 00:04–00:08**  
Enter a synthetic request with stable source ID `demo-episode-01`, customer `Maya Chen`, a sample address, requested service, date and a training-only note. Emphasize that the date is a request, not a confirmed appointment.

**Scene 3 — 00:08–00:12**  
Submit once. The live application records one customer and one job, creates three open tasks and queues one delivery event. The counters reflect those actual persisted records.

**Scene 4 — 00:12–00:16**  
Read the job card: customer identity, source intake ID, requested service/date, task list and delivery state are together for follow-through. No customer or external provider is involved.

## Episode 2 · Move a job through task completion

**Description:** Use the landed job checklist to move a synthetic job from new to in-progress to complete, showing that task state persists in the same local workspace.

**Scene 1 — 00:00–00:04**  
A synthetic recurring-clean job begins with three open tasks and `new` status.

**Scene 2 — 00:04–00:08**  
Check **Confirm requested service and preferred date**. The live app changes the job to `in_progress`; the other two tasks remain open.

**Scene 3 — 00:08–00:12**  
Check **Assign cleaning team**. The same job remains in progress with one action left.

**Scene 4 — 00:12–00:16**  
Check **Complete cleaning and follow up**. The job becomes `complete`, while its customer and source identity remain linked.

## Episode 3 · Retry only the selected delivery

**Description:** Create two synthetic jobs and use the PR #10513 selected-event retry path: retrying one job delivers only that event, leaving the unrelated queued job untouched until the operator processes it.

**Scene 1 — 00:00–00:04**  
Two independent synthetic jobs each have a pending delivery event.

**Scene 2 — 00:04–00:08**  
Click **Retry delivery** on the newest job. The landed UI sends that exact delivery ID to `/api/retry` and then `/api/process` with the selected ID.

**Scene 3 — 00:08–00:12**  
The chosen job is delivered and appears in the local notification feed. The other job remains pending; it was not consumed as an older queue entry.

**Scene 4 — 00:12–00:16**  
Use **Deliver next notification**. The remaining due event is delivered normally, leaving both events delivered exactly once in this synthetic local workspace.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
