# Smart outreach planner

This lane turns Commons' existing research, offer, receipt, draft, transport,
and reply capabilities into one deterministic qualification step. It adopts the
useful mechanism behind automated prospecting products without buying another
database or adding a credential dependency: first-party evidence enters once,
canonical collision history is loaded automatically, fit is scored, and only a
fully evidenced prospect can receive a tailored private draft.

The reference mechanism is Explee's public AutoGTM description: learn what the
seller offers, sharpen the ideal-customer profile, rank high-intent prospects,
personalize each message, and then handle replies. Commons now composes those
stages from its own evidence and roads: this planner owns evidence, collision,
fit, rank, and copy; Swarm Mail owns exact-once transport state; reply intake
owns mailbox-operator classification; the always-on reply-to-revenue funnel
composes those receipts into public cash truth without a second CRM.
Reference observed 2026-08-27:
<https://explee.com/>.

It does not replace `revenue/production_survival`, the canonical commerce
catalog, Airtable CRM, Apollo receipts, or `host/swarm_mail.py`. It composes
them. The checked-in cohort is reconciled with current canonical receipts on
every run. Its recorded dispositions are:

- AnythingLLM, Metaforms, and Composio are `HOLD_DO_NOT_RESEND` from canonical
  receipts;
- SigNoz is `HOLD_DO_NOT_CONTACT` from its recorded do-not-contact disposition.

Missing research fields and historical lane ownership do not replace those
suppression results.

No checked-in candidate is silently promoted into contact. A prospect becomes
`READY_TO_DRAFT` only when it has an exact first-party quote with production
pain, a relevant owner role, a verified route, a binary proof hypothesis, no
disqualifier, no occupied lane, and no canonical do-not-resend collision. The
generated message quotes the prospect's own words, names one existing offer,
links one measured proof, asks one narrow question, and includes a visible
opt-out. The planner still performs zero transport actions.

Run the measured cohort:

```sh
python3 host/smart_outreach.py validate
python3 host/smart_outreach.py plan
```

For an `EMAIL` route, a recorded route address and `recipient_email` must identify
the same mailbox after trimming whitespace and normalizing case. Contradictory
addresses or malformed email, timestamp, and route fields produce a descriptive
input error with exit code 2. Non-email route kinds retain their existing behavior;
a missing recipient remains a research gap.

`--receipts` must identify an existing, readable directory. A missing path,
failed directory read, or unreadable/invalid JSON receipt exits with code 2 and
an error on stderr; it never becomes an empty collision history. An existing
empty directory remains a valid empty history. Restore the receipt directory
or correct the path before rerunning the planner.

Candidate and receipt JSON must have unique object fields and finite numeric
values. Repeated fields such as `do_not_resend` exit with code 2 and identify the
source file, instead of silently replacing the earlier suppression value.

`plan --output PATH` writes and syncs a temporary file beside the destination,
then atomically replaces the saved plan. A write or replacement failure exits
with code 2 and leaves the previous plan intact. Without `--output`, the plan
continues to print to stdout.

Private drafts can later enter Swarm Mail's existing exact-once and suppression
path. Replies remain owned by the production-survival reply intake. This planner
does not open a second CRM, transport, inbox, SKU, or cash ledger.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
