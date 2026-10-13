# ChartTrace Workbench

Local-first, single-case medical-record evidence workbench. Synthetic
build-and-verify only. Real-family records remain HOLD.

This is a Windows-first standalone application, not a GitHub Pages door,
browser tab, public upload surface, or static HTML product. There is no
`doors/charttrace-*.html`.

## What it does

Turns already-digitized records into an immutable source inventory, cited
chronology, ledgers, high-recall investigative leads, an internal review
line, and a named-human-released recipient package.

It does not decide malpractice, negligence, causation, standard-of-care
breach, actionability, damages, or representation.

## Hard boundaries

- No PHI in git, Slack, fixtures, logs, or exports
- No live model call in the synthetic build (`model=none`)
- No public TCP listener, browser launch, Pages dependency, or egress
- No Stripe mutation, Connect, charge, transfer, payout, tax, or spend
- No price, firm, destination, compensation, recovery, or routing inputs
  into peers or evidence generation
- Encrypted-vault *contract* only until a caller proves production encryption

## Lane ownership

| Lane | Paths | Job |
| --- | --- | --- |
| A | `charttrace/core/**`, `schema/**`, `storage/**` | Evidence objects, ledger, vault contract |
| B | `charttrace/peers/**`, `prompts/**`, `grounding/**` | 12-role high-recall swarm |
| C | `charttrace/app/**`, `ui/**`, `legal/**`, `packaging/**`, `launcher.py` | Native window + Legal/Data/Terms |
| D | `charttrace/review/**`, `export/**`, `counsel/**` | Review line + `.ctpkg` |
| E | `charttrace/commercial/**`, `pricing/**`, `affiliates/**` | Workload pricing + isolation |
| F | `charttrace/fixtures/**`, `assurance/**`, `test_charttrace_*.py` | Synthetic oracle + thresholds |
| Integrator | `__init__.py`, this README, `p/charttrace-medical-evidence-review-01.md` | Package + receipt. No door. |

Integrator does not steal lane paths. Interface mismatches are resolved in
this package marker, not by rewriting another lane.

## Tests

After a lane lands, run that lane's declared command. The aggregate suite
is `python -m unittest -v test_charttrace_assurance.py` plus each landed
lane discover command, under network deny. Empty or prose-only branches
are not merge candidates.

## Status

See `p/charttrace-medical-evidence-review-01.md` for the measured
START/PROGRESS/SHIP audit. This README does not claim production,
counsel approval, signed installer, customer delivery, or cash.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../referral-intake-completeness.html)
- [$199 repair diagnostic](../repair-booking-preflight.html)
- [$199 plant diagnostic](../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../titanmcp.html). Cite Latch Pad KEEP.
