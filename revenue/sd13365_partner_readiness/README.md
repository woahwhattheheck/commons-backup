# San Diego RFP 13365 — public-evidence partner readiness

Operation: `R-SD13365-PROBATION-AI-TEAMING-ZCAS913455-20260913`

This package is a hostile, source-linked **public-evidence** assessment for a potential prime contractor considering Cognisen for County of San Diego Probation RFP 13365 / BuyNet `BPM013365`, *Artificial Intelligence (AI) Report Writing Services*.

It is not a compliance certification, bid, recommendation to award, vendor representation, or claim about private evidence. `PASS`, `UNKNOWN`, and `RED` mean only:

- `PASS`: current public evidence directly and specifically supports the full named requirement;
- `UNKNOWN`: evidence is missing, generic, adjacent, stale, or narrower than the full requirement;
- `RED`: current public evidence directly contradicts the full named requirement.

## Result at the 2026-09-13 evidence cutoff

All thirteen hard controls remain `UNKNOWN` on public evidence. That is not a finding of noncompliance. It means the public record does not close the requirement without configuration-specific, current artifacts.

| Control | Status | Strongest public signal | Exact gap |
|---|---|---|---|
| FIPS 140-3 | UNKNOWN | San Mateo public memo says FIPS 140-2 validated encryption | Current 140-3 CMVP module inventory and deployment mapping |
| SAML/OAuth SSO | UNKNOWN | Role-based access and identity controls | Protocol, PKCE/state, claim mapping, logout, County IdP test |
| Seven-year audit retention | UNKNOWN | Audit visibility, edit history, timestamped logging | Retention, immutability, retrieval, export, hold and deletion proof |
| Intune mobile deployment | UNKNOWN | Apple/Android FieldAssist and remote wipe | Intune packaging, policy, conditional access, update/rollback proof |
| U.S.-only support | UNKNOWN | AWS GovCloud, U.S.-person access, U.S. residency | All support locations, staff and subcontractor enforcement |
| WCAG 2.1 AA / VPAT | UNKNOWN | Website references accessibility | Current product VPAT/ACR and generated HTML/PDF test evidence |
| Annual penetration test | UNKNOWN | SOC 2 Type 2 and general security posture | Current independent annual test and remediation closure |
| 180-day backup | UNKNOWN | AWS GovCloud hosting | Daily cadence, 180-day retention and successful restore/DR exercise |
| 24/7 incident response | UNKNOWN | Monitoring and security posture | 24/7 staffing, AI scenarios, notice clocks and exercise evidence |
| AI BOM | UNKNOWN | One county memo identifies Claude 3.5 Sonnet / Anthropic / Bedrock | Maintained full AI-component inventory and update lineage |
| Artifact signing | UNKNOWN | General access and hosting controls | Signed model/data/plugin/config artifacts and deployment verification |
| Prompt-injection defenses | UNKNOWN | Underlying-model adversarial testing | End-to-end application/retrieval/tool defense and replayable tests |
| Data-poisoning detection | UNKNOWN | Generic anomaly monitoring and no County-data training | Provenance, quarantine, poisoning-specific detection and rollback |

Core product fit is separately strong: public material describes probation-specific report workflows, human review/edit/approval, audit visibility, AWS GovCloud, role-based access, no training on agency records, and no third-party LLM API calls. Those facts do not automatically answer the thirteen narrower controls.

## Bounded subcontract wedge

The package defines four useful tasks that a prime can procure without representing Cognisen compliance:

1. **Evidence closure** — receive prime-supplied artifacts, verify source/freshness/coverage, and emit a deterministic gap receipt.
2. **Synthetic AI-abuse testing** — exercise prompt injection, retrieval leakage, unauthorized tool calls, poisoning signals and rollback in a non-production environment using synthetic records.
3. **Supply-chain receipts** — independently verify a prime-supplied AI BOM, hashes/signatures, approvals, revocation state and rollback lineage without signing or approving vendor artifacts.
4. **Deployment and accessibility review** — review Intune, VPAT/ACR, generated-document accessibility, backup/restore, penetration-test closure and incident-response exercise evidence.

Explicitly excluded: vendor or County contact, bid submission, pricing, compliance certification, contract signature, production access, and CJI/PHI handling.

## Reproduce

```bash
cd revenue/sd13365_partner_readiness
python assemble_requirements.py
python -m unittest -v test_matrix.py test_assembly.py
python -O -m unittest -v test_matrix.py test_assembly.py
python matrix.py requirements.json --output /tmp/sd13365-receipt.json
```

The bounded source payload materializes only after exact SHA-256 and semantic validation. The CLI rejects duplicate JSON keys, non-finite values, missing or duplicate controls, untrusted/insecure evidence URLs, optimistic status promotion without direct evidence, contradictory classifications, changed opportunity identity, authority escalation, and weakened subcontract boundaries. The receipt is canonical and content-addressed by SHA-256.

## Primary sources

- County of San Diego official BuyNet record: `https://sdbuynet.sandiegocounty.gov/page.aspx/en/bpm/process_manage_extranet/13586`
- County of San Diego official RFP package: the `bare.aspx` URL recorded in `requirements.json`
- Indexed text of County Attachments 1–3: GovTribe URLs recorded per requirement; these are a readable index of the official attachments, not a replacement for BuyNet authority.
- Cognisen current product/security pages: `https://cognisen.com/security-compliance`, `https://cognisen.com/docassist`, and `https://cognisen.com/fieldassist`
- County of San Mateo public Cognisen board memo: the Legistar URL recorded in `requirements.json`

The Cognisen website disclaimer states that public descriptions can vary by configuration and do not themselves guarantee compliance; executed agreements and implementation evidence control.
