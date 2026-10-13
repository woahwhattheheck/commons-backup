# Dealer service lead rescue — synthetic run receipt

Status: `WORKING_SYNTHETIC_DEMO`

Fixture `LEAD-SYN-1101` (DEALER-RIVERVIEW-DEMO / VEH-SYN-F150-04-DEMO, oil-change) proves the public engine:

- ordinary processing creates one `FOLLOWUP_EXPRESS` follow-up, one `APPT_QUICK_LANE` booked-service / CRM record, and one timestamped status receipt;
- an operational hold (`preferredWindow=UNKNOWN`) routes once to `HELD_INCOMPLETE` with zero appointments;
- a duplicate web-form submit (`FORM-SYN-2001`) plus an after-hours inquiry (`AFT-SYN-3001`) share the lead-identity idempotency key and keep one appointment;
- crash after classify, after follow-up, or after appointment leaves a timestamped progress receipt;
- a worker restart that reloads the serialized store resumes to exactly one appointment;
- rollback of a crashed run returns a clean un-rescued state; a finished run stays single-rescued;
- same id with different bytes returns `LEAD_CONFLICT`;
- PII-shaped keys (`customerName`, phone) are refused and create zero appointments.

Test command: `node test_dealer_service_lead_rescue.js`

Expected result: `dealer-service-lead-rescue: 10 scenarios PASS`.

Limits: synthetic / no real dealership / no PII / browser-local proof only. Not a live CRM write, not outreach, not a Stripe charge. Entry is $199 for one business day; $2,500 pilot only after fit. cash_usd = 0.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
