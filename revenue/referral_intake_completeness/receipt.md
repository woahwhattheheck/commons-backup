# Referral intake completeness — synthetic run receipt

Status: `WORKING_SYNTHETIC_DEMO`

Fixture `REF-SYN-4401` (CLINIC-NORTHBRIDGE-DEMO → CLINIC-CEDAR-HOLLOW-DEMO, imaging-slot) proves the public engine:

- ordinary processing creates one required-field checklist, one `IMAGING_SCHEDULING` queue ticket, and one timestamped intake receipt;
- an operational hold (`insuranceAuthFlag=MISSING`) routes once to `INCOMPLETE_INTAKE`;
- replay returns `REPLAY_NOOP` and keeps the same queue id;
- crash after checklist or after queue leaves a timestamped progress receipt and resumes to exactly one queue ticket;
- rollback of a crashed run clears the ticket and records `ROLLED_BACK`;
- same id with different bytes returns `REFERRAL_CONFLICT`;
- PHI-shaped keys (`patientName`, `diagnosis`) are refused and create zero queue tickets.

Test command: `node test_referral_intake_completeness.js`

Expected result: `referral-intake-completeness: 9 scenarios PASS`.

Limits: synthetic / no-PHI / browser-local proof only. Not a clinical decision, not a care approval, not outreach, not a Stripe charge. Entry is $199 for one business day; $2,500 pilot only after fit. cash_usd = 0.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
