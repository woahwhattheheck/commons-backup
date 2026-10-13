# grokbot_control (Astra G2)

Loopback peer gateway for **existing GrokBot pools** (not grok.com, not Cursor cloud accounts).
Default listen: 127.0.0.1:8881. Do **not** relaunch residents on the owner PC until the RAM incident is cleared.

## Run (tests / explicit owner start only)

```text
PYTHONPATH=. python -m integrations.grokbot_control --port 8881 --mode echo
PYTHONPATH=. python -m integrations.grokbot_control --port 8881 --mode inprocess
```

CLI memory floor (default 1024 MiB free; library/tests may pass 0):

```text
PYTHONPATH=. python -m integrations.grokbot_control --port 8881 --mode echo --min-free-mb 1024
```

Env override: GROKBOT_CONTROL_MIN_FREE_MB. Under the floor, POST /v1/runs returns **503** error=memory_guard and **does not** create a run record.

## HTTP

| verb | path |
|---|---|
| health | GET /health (also /) — includes memory_guard |
| pools | GET /v1/pools |
| submit | POST /v1/runs {pool_id, prompt, seat?, async?, case?} |
| inspect | GET /v1/runs/{run_id}?wait_ms= |
| follow-up | POST /v1/runs/{run_id}/follow-up {prompt, async?} |
| cancel | POST /v1/runs/{run_id}/cancel |
| session | GET /v1/sessions/{session_id} |
| events | GET /v1/events?after=&limit=&wait_ms=&pool_id= |

Optional `case` on submit (durable on the run from queued onward; follow-up inherits):

```json
{"offer_id":"sku-…","case_ref":"…","client_reference_id":"…","sku":"…"}
```

Only those four string keys are kept (max 200 chars each). Unknown keys dropped. Empty object omitted.

Paid-case fulfillers: build `case` as an opaque dict (`offer_id`, `case_ref`, optional `client_reference_id`, `sku`) and pass it to `GrokBotControlClient.submit(..., case=...)` or `grokbot_submit`. Does not remint Stripe.

Opaque paid-case receipt: `receipt_row_from_case(case, g2_run_id=…, g2_session_id=…)` builds a public seats `case_row` from caller-supplied opaque identifiers. Its default state is `UNVERIFIED`; it does not observe payment or sanitize PII. Pass an observed `state` only when evidence supports it. Receipt values over 200 characters raise instead of truncating identifiers. Shape: required `offer_id`/`case_ref`/`sku`/`state`; optional `client_reference_id`/`g2_run_id`/`g2_session_id`/`payment_observed_at` (max 200 chars). Hermetic pin: `python test_grokbot_paid_case_receipt.py`.

`receipt_from_g2_submit(case, submit_response)` binds a grokbot_submit/inspect response onto that same opaque `case_row`: nonempty `run_id` is required; nonempty `session_id` is optional. Shared equipment exposes the receipt builder as local tool `grokbot_receipt_row_from_case` (no `:8881` call); the tool prefers `submit_response` when present. Pin: `python test_grokbot_paid_case_receipt.py` (`test_receipt_from_g2_submit`) and `python test_grokbot_shared_equipment.py` (`test_paid_case_equipment_helpers`, `test_paid_case_equipment_live_e2e`).

Attribution on completed runs:

```json
{"pool_id":"grokbot","seat":"SPARK","harness":"grokbot","model":"Grok"}
```

Default pool id: grokbot from clans.json. Extra pool ids only via GROKBOT_CONTROL_POOLS when the owner names them (second-account kebab is not invented).

## Shared equipment

integrations.shared_equipment.peers.GrokBotEquipment exposes:

grokbot_submit, grokbot_inspect, grokbot_follow_up, grokbot_cancel, grokbot_session, grokbot_events, grokbot_pools, grokbot_health, grokbot_receipt_row_from_case

grokbot_submit accepts optional `case`. grokbot_health is GET /health so peers can read memory_guard before submit. `grokbot_receipt_row_from_case` is a local paid_case helper (no control HTTP). Wired into the Gemini peer tool gateway catalog beside Slack/GitHub/Gemini lifecycle tools. CLI: python -m integrations.shared_equipment.services catalog|call|manifest.

Peer client: integrations/grokbot_control/client.py (GrokBotControlClient).

## Tests

```text
python test_grokbot_control.py
python test_grokbot_shared_equipment.py
python test_grokbot_paid_case.py
python test_grokbot_paid_case_receipt.py
python test_grokbot_client_reference_roundtrip.py
```

## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
