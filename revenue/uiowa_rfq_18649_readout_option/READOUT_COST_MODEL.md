# Optional readout cost model

**Internal planning model. All hours and loaded internal rates are illustrative assumptions. They are neither measured delivery costs nor an accepted quote for labor.** The proposed optional service price is $4,000 USD for up to two readout sessions, separate from the proposed $24,000 base workshare. One-session use does not create an automatic discount. No agreement, invoice, payment or earned profit is represented.

The companion `UIowa-optional-readout-cost-model.xlsx` is editable. `readout-cost-assumptions.json` records the same baseline in a machine-readable form. `READOUT_OPTION.md` describes the proposed scope and handoff. These planning files can be used immediately to test assumptions; they do not promise anyone's attendance.

## Work and rate assumptions

The remote baseline uses one production-role cost pool and one analyst/support-role cost pool. These describe person-hours of work, not two committed staff members. The analyst provides the modeled session attendance; production hours are preparation effort. Prime presentation time and University participant time are outside this subcontract cost model.

| Work component | One session, hours | Two sessions, hours | Cost pool |
|---|---:|---:|---|
| Shared core deck, 12-18 slides | 12 | 12 | Production |
| Shared appendix, 8-12 slides | 4 | 4 | Production |
| Speaker notes | 4 | 4 | Production |
| Evidence lookup index | 3 | 3 | Production |
| One consolidated preference-revision round | 4 | 4 | Production |
| Package quality review | 2 | 2 | Production |
| Second-audience tailoring | 0 | 2 | Production |
| Shared analyst review/rehearsal | 2 | 2 | Analyst |
| Session preparation, 1.5 hours each | 1.5 | 3 | Analyst |
| Live support, one person for 60 minutes each | 1 | 2 | Analyst |
| Question capture/follow-up, 0.5 hours each | 0.5 | 1 | Analyst |
| **Total production effort** | **29** | **31** | **$70/hour assumed loaded cost** |
| **Total analyst effort** | **5** | **8** | **$85/hour assumed loaded cost** |
| **Total modeled person-hours** | **34** | **39** | |

The four revision hours are shared across the presentation package, not repeated for each session. Factual errors, broken references and nonconforming authored materials remain subject to correction; the allowance does not turn their correction into an automatic extra charge. Material new evidence or a newly requested deliverable must be distinguished from a defect. A model overrun informs that discussion and does not authorize billing.

## Reconciliation to the $4,000 option

| Cost or balance, USD | One session | Two sessions |
|---|---:|---:|
| Production effort at assumed loaded rate | $2,030.00 | $2,170.00 |
| Analyst effort at assumed loaded rate | $425.00 | $680.00 |
| **Modeled labor cost** | **$2,455.00** | **$2,850.00** |
| Planning contingency, 10% of modeled labor | $245.50 | $285.00 |
| **Planned cost including contingency reserve** | **$2,700.50** | **$3,135.00** |
| **Remaining headroom** | **$1,299.50** | **$865.00** |
| **Price: cost + reserve + remaining headroom** | **$4,000.00** | **$4,000.00** |
| Headroom as percentage of proposed price | 32.4875% | 21.6250% |

Contingency is a planning reserve, not an observed expense. Remaining headroom is a planning balance, not net profit. Replace loaded rates with actual fully burdened cost assumptions and account for taxes, financing, unrecovered overhead and any other omitted costs before relying on a profitability conclusion. The model does not silently price unknown onsite requirements at zero.

## Equations and sensitivity

For session count `n` equal to 1 or 2:

- Production hours = 29 + 2 when `n = 2`, otherwise 29.
- Analyst hours = 2 + n × (1.5 preparation + 1 live + 0.5 follow-up).
- Labor cost = production hours × $70 + analyst hours × $85.
- Contingency reserve = labor cost × 10%.
- Remaining headroom = $4,000 − labor cost − contingency reserve.
- Headroom percentage = remaining headroom ÷ $4,000.

All inputs above are editable design assumptions. A third session is outside the illustrated up-to-two-session option and requires an explicit revised scope and commercial agreement.

| Changed assumption, all others held fixed | One-session result | Two-session result |
|---|---:|---:|
| Live duration increases from 60 to 90 minutes | Labor +$42.50; cost with reserve $2,747.25; headroom $1,252.75 | Labor +$85.00; cost with reserve $3,228.50; headroom $771.50 |
| Preference revision increases from 4 to 8 production hours | Labor +$280.00; cost with reserve $3,008.50; headroom $991.50 | Labor +$280.00; cost with reserve $3,443.00; headroom $557.00 |

The second session adds $395 of modeled labor and $39.50 of reserve at baseline, using two extra production hours and three extra analyst hours. The fixed proposed selling price remains $4,000.

## Onsite costs and unknown inputs

Onsite involvement is unpriced until the selected activity, location, staffing, incremental work and travel assumptions are known. Track incremental production effort, incremental attendance effort, travel time and direct travel expenses separately. Count only additional effort beyond the remote baseline to avoid charging the same live-session hours twice.

The workbook's onsite sheet preserves unknown entries as unknown. Selecting an explicit remote/no-onsite scenario can establish zero incremental onsite cost for that scenario; a blank travel estimate cannot. Any onsite or travel commitment requires separate prior written authorization and agreed cost treatment under the source exhibit. No particular travel route, expense, date or individual's availability is assumed.

## Source and design distinction

The current acceptance exhibit §4.4 establishes the proposed $4,000 separate option. The original sent workshare exhibit p2 WP6 supplies deck/appendix production, speaker notes, evidence lookup and up to two sessions; p3 supplies separate written travel authorization. RFQ p6 attribute 4 §4.4 makes readouts optional and outside the base engagement; p7 describes onsite expectations when reasonable. See `SOURCE_NOTES.md` for exact source versions.

Every slide quantity, duration, hour allocation, rate, reserve percentage and sensitivity in this file is newly proposed planning design. None is claimed as a University requirement, actual measured cost, confirmed staff allocation or accepted commercial term. The base workshare's 40/40/20 triggers remain unchanged, and this model adds no option payment trigger.
