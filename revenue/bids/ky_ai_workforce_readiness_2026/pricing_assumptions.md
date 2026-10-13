# Pricing assumptions worksheet — no approved dollars yet

**State: DRAFTED / NOT PRICED.** This worksheet creates a scalable calculation contract. It intentionally contains no proposal price, rate, budget ceiling, or revenue claim.

The public Q&A says SCWDB has not established a guaranteed participant minimum, fixed Service-A/Service-B split, fixed pathway distribution, standard cohort size, or final contract ceiling. Pricing should therefore expose assumptions instead of multiplying the ~980 planning target into a fake guaranteed contract value.

## 1. Variables requiring an authorized commercial owner

| Variable | Meaning | Approved value |
|---|---|---|
| `I` | one-time implementation/customization cost | `[OPEN]` |
| `CR` | per-completed-participant Service-B career-readiness rate | `[OPEN]` |
| `MFG` | per-completed-participant manufacturing pathway rate | `[OPEN]` |
| `CON` | construction pathway rate | `[OPEN]` |
| `LOG` | logistics pathway rate | `[OPEN]` |
| `HC` | healthcare pathway rate | `[OPEN]` |
| `BUS` | business-operations pathway rate | `[OPEN]` |
| `S_remote` | minimum/alternative remote cohort/session charge if proposed | `[OPEN]` |
| `S_inperson` | minimum/alternative in-person cohort/session charge if proposed | `[OPEN]` |
| `T_policy` | approved travel treatment: included / actuals / capped / other | `[OPEN]` |
| `L` | technology/licensing/credential cost treatment | `[OPEN]` |
| `C_window` | cancellation/reschedule window and any charge | `[OPEN]` |
| `N_min/N_pref/N_max` | class-size assumptions by delivery mode | `[OPEN]` |

## 2. Scenario variables — planning only, never guaranteed

Use scenario counts to test affordability/cash needs after rates are approved:

- `n_cr` = completed Service-B participants;
- `n_mfg`, `n_con`, `n_log`, `n_hc`, `n_bus` = completed participants by Accelerator pathway;
- `r_remote`, `r_inperson` = delivered sessions when session pricing applies;
- `travel_approved` = specifically authorized reimbursable travel;
- `licenses` = approved license/technology cost;
- `optional` = separately authorized optional services.

## 3. Transparent formulas

When participant-based pricing is used:

```text
participant_delivery =
    n_cr*CR + n_mfg*MFG + n_con*CON + n_log*LOG + n_hc*HC + n_bus*BUS
```

Illustrative total (only after every component is approved):

```text
total = I + participant_delivery + approved_session_minimums + travel_approved + licenses + optional
```

Do not double-bill the same delivery through both a participant rate and a cohort minimum. The final Appendix-B owner must document precedence.

## 4. Completion/invoice assumption

The proposal should recommend a completion standard but state that SCWDB will approve the final uniform standard. A defensible draft evidence bundle is:

1. verified attendance;
2. required hands-on activity;
3. approved learning check/demonstration;
4. instructor completion disposition;
5. durable participant-level record supporting certificate/reporting/invoicing.

Registration or partial attendance alone is not completion.

## 5. Low-volume / cancellation economics

Before prices are approved, the commercial owner must answer:

- minimum/preferred/maximum class size for remote and in-person;
- whether a minimum cohort/session charge applies when referrals are below the preferred size;
- cancellation/rescheduling lead time and cost;
- when instructor/travel costs become nonrecoverable;
- whether a no-show/partial-attendance participant generates any billable amount (do not assume yes);
- how the team avoids pricing that requires the buyer to guarantee the ~980 planning target.

## 6. Working-capital / subcontractor check

Because final payment terms are negotiated, calculate before final approval:

```text
peak_cash_need = implementation_labor_before_payment
               + partner/instructor payments_due_before_buyer_receipt
               + approved_travel_and_license_prepaids
               + contingency
```

Bind payment timing with each proposed subcontractor so the prime does not promise terms it cannot finance.

## 7. Approval record

- Rate owner:
- Partner cost confirmation date:
- Travel policy confirmation:
- License/tool cost confirmation:
- Working-capital reviewer:
- Final Appendix B version/hash:
- Final approved total/scenario basis:
- Approval timestamp:

Until these fields and the readiness manifest commercial gate are resolved, no dollar amount in working notes is a proposal commitment.
