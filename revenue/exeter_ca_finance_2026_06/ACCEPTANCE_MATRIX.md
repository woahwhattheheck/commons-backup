# Exeter CA RFP 2026-06 — specialist acceptance matrix v2

Operation: \`EXETER-CA-2026-06-MUNICIPAL-FINANCE-ACCEPTANCE-ZSOL-20260917\`  
Recovery: \`EXETER-FINANCE-ACCEPTANCE-RECOVERY-ZCAIRN-20260918\`  
Commercial state: **PROPOSED_NOT_ACCEPTED**  
Prime state: **UNSELECTED / BIDDER_STATUS_UNKNOWN**

This matrix turns the City's implementation/data-conversion/testing seams into a bounded evidence contract. It does not certify ERP product compliance or create City acceptance.

| Gate | Required evidence | PASS condition | HOLD condition | Authority |
|---|---|---|---|---|
| \`SOURCE_PIN\` | retained source-ledger, official procurement-index, RFP, and current Q&A/addenda evidence digests + observed/recheck timestamps | source generation is <=48h old and Q&A/addenda state is explicitly retained/confirmed | stale source; recheck due; official page rechecked with unresolved absence; missing required retained digest | prime owns proposal; TJLabs owns only evidence packet |
| \`INPUT_READY\` | source/target generation digests, mapping rules, interface inventory | bounded content-addressed generations | unbound/live/ambiguous generation | prime supplies; TJLabs validates |
| \`CROSSWALK\` | account/fund, vendor, customer, employee mappings | unique source identity and explicit target/disposition | duplicate/conflicting source identity | TJLabs evidence only |
| \`CONTROL_TOTALS\` | source/target integer-cent GL controls + explicit approved delta + separate adjustment receipt when nonzero | target-source equals approved delta; evidence presence matches delta | unexplained cent drift; numeric plug; missing/extra adjustment receipt | prime owns accounting; TJLabs checks declared evidence |
| \`SUBLEDGER_RECON\` | AP/AR/payroll/utility/cashiering counts/amounts + unique linked GL control + delta evidence | count and amount deltas match approvals; linked control source/target/delta/receipt exactly match | missing/reused control; GL/subledger mismatch; open exception | prime owns corrections; TJLabs analyzes |
| \`BANK_RECON\` | statement/book endings, nonnegative adjustment magnitudes, terminal amount | both equations equal declared terminal amount | negative directional adjustment; hidden plug; unmatched terminal | City/prime accounting authority |
| \`INTERFACES\` | required interface list + source/target + manifest digest + verification state | every required interface occurs once and is verified | missing/duplicate/unverified interface | prime owns integration |
| \`UAT_TRACE\` | case ID, mandatory flag, status, evidence digest | all workshare-mandatory cases remain mandatory and pass with retained evidence | missing evidence; FAIL/HOLD; required case demoted | human UAT remains prime/City |
| \`CUTOVER\` | source-freeze, rollback, replay receipts + unresolved exception set | all receipts retained and unresolved set empty | missing receipt or open cutover exception | prime/City make go-live decision |
| \`REPLAY\` | exact packet and report digests | same admitted packet reproduces same report | semantic result depends on mutable exports/host clock/order | TJLabs |
| \`COMMERCIAL\` | authorized agreement/work order | only separately authorized acceptance may advance commercial state | meeting/interest/proposal treated as sale | authorized counterparty/owner |

## Q&A coverage and functional scope

[QA_REVIEW.md](QA_REVIEW.md) maps all 38 Q&A answers and adds the source context absent from the selected clause rows. Full original-RFP and BidNet coverage remain incomplete.

The fixed mandatory UAT IDs below are the minimum for this specialist evidence contract. They do not certify the complete ERP functional scope, department/role configuration, training, regulatory maintenance or City acceptance. Those require the separately supplied prime/City inventory and evidence described in the Q&A review.

## Mandatory UAT IDs

\`GL_FUND_ACCOUNTING\`, \`AP\`, \`AR\`, \`PAYROLL\`, \`CASHIERING\`, \`BANK_RECONCILIATION\`, \`UTILITY_BILLING\`, \`FINANCIAL_REPORTING\`, \`INTEGRATIONS\`, \`DATA_CONVERSION\`.

## Fail-closed rules

1. \`UNKNOWN != PASS\`.
2. Money is strict integer cents; booleans/floats cannot masquerade as amounts.
3. Approved financial deltas require explicit retained receipts in both the subledger and its linked GL/control row.
4. A single GL/control row cannot be silently reused to satisfy multiple required subledgers.
5. Current procurement-source state is part of executable readiness; documentation HOLD cannot be bypassed by a synthetically clean accounting packet.
6. Bank additions/deductions are magnitudes and therefore cannot be negative.
7. Stable machine evidence does not mint accounting judgment, bank action, payroll authority, go-live authority, buyer acceptance, payment, or revenue.
8. No production/customer/employee data enters TJLabs tooling without separate authorization and controls.
