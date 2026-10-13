# aquatrace-work-order-c-reporting-offline-20260831-01

Working CLI for synthetic AquaTrace reporting and offline contracts.

Offline recovery vs conflict HOLDs. CMDP, netDMR, and Power BI export
test contracts with golden hashes. Named-human release only. Idempotent
replay. Deterministic audit hash.

Cite AquaTrace production swarm. Take the best of AquaTrace into the
swarm as a fail-closed runner. Do not remint the private repo,
acceptance-runner, operations-runner, instrument-fixtures, Billings
lanes, or local private SHA `7a5ca7fe2856c49abf46bc248654a4d6f7af0335`
(`docs/validation/reporting-offline-test-contract.md` is unmerged
private-repo docs — cite, do not inherit).

Adapters stay synthetic and read-only. No City contact. No submission.
No live LIMS. No customer data. No production or certification claim.
cash_usd=0. grok.com dry. State remains NOT_READY / HOLD / BUILD-AND-VERIFY.

## Official commands

```bash
python3 aquatrace_work_order_c_reporting_offline.py
python3 test_aquatrace_work_order_c_reporting_offline.py
```

## Acceptance

| check | expected |
|---|---|
| input events | 80 = 60 recover + 20 conflict HOLD |
| recover | 60, twenty each CMDP / netDMR / Power BI |
| HOLD | 20, five each of four exact codes |
| export contracts | 3 synthetic payloads, matching golden hashes |
| HOLD leak | conflict source hashes never enter an export |
| replay | adds 0 recover / 0 holds; same audit hash |
| autonomous released | 0 |
| human released exports | 3 after SYN-AQUATRACE-REPORTING-OFFICER |
| live submissions | 0 |
| audit_sha256 | `5be4b7ebe6432e675fdb1360ad1125262a014de25eb740dae8ea7aa88c63e51b` |

Hold codes: `HOLD_VERSION_CONFLICT`, `HOLD_CHECKSUM_DIVERGENCE`,
`HOLD_CLOCK_SKEW`, `HOLD_SPLIT_BRAIN`.

Export hashes:

- CMDP `ec2af2de146bfe52b9896cad857ef8fe2f6b26ea12d2900b81d4e4a63e3b11ec`
- netDMR `71babb70499dc8aa47102d5af05d8f5445d06fec5fe7866dfca9e140b64d48dc`
- Power BI `7ef946b249b9d06c73c4c9a49d8dd6f2be9aee99171a268f04c0ad8c7b67b983`

## Paths

- `fixture.json` — 80 frozen synthetic offline events
- `runner.py` — recover / HOLD / export / human-release / replay
- `source.json` — destination and analyte catalogs
- Door: `../../aquatrace-work-order-c-reporting-offline.html`

HARD OFF — cite, do not remint: A (blocked writable checkout), B (Seth, official main 47b36d27),
field-mobility C (Emissary), D / D-QA (Codex), sanair-asbestos-coc-router-lims-01
(Adam, PR 6859 merge f0bf6c84 blob 70c4b31c), wadsworth, highpower, westpak,
ddl, sharp, canyon, pcl, organabio, billings.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

