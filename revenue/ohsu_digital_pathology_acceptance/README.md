# OHSU digital-pathology integration acceptance rail

Operation: `OHSU-DIGPATH-EPIC-ACCEPTANCE-ZCHP4S7-20260913`  
Owner: `Z-CyclotomicHarbor-914031-P4S7` (`ZCH-P4S7`) / GPT-5.6 Sol

This is a **specialist integration-acceptance asset**, not a pathology image-management system and not a clinical AI system. It was built against the public integration seam in OHSU RFP-2027-2012: an enterprise digital-pathology IMS with bi-directional Epic Beaker integration and scalable native/third-party AI/image-analysis integration.

The harness consumes **synthetic, no-PHI JSONL evidence** and produces a deterministic receipt. It validates the integration invariants that are easy to lose in a slide/case workflow:

- Beaker-to-IMS order evidence is explicitly bound to `OML^O21`.
- IMS-to-Beaker availability/status evidence is one `SSU^U03` event per slide.
- case/slide deep links are HTTPS and identity-bound instead of merely syntactically present.
- changed replays with the same event ID are conflicts; exact retries are idempotent.
- slide status cannot silently move backward and case close cannot precede image availability.
- optional case-close synchronization is bound to `ORU^R01`.
- any AI adapter evidence is provenance-only: exact model/version/input/artifact digests and an explicit `decision_support_only` authority ceiling. The harness never evaluates an image or authorizes autonomous diagnosis.
- PHI-like fields and unknown schema fields fail closed. The checked-in sample uses synthetic IDs only.

## Run

```bash
cd revenue/ohsu_digital_pathology_acceptance
python -m unittest -v test_acceptance.py
python -O -m unittest -v test_acceptance.py
python acceptance.py sample.jsonl --out /tmp/ohsu-digpath-receipt.json
cat /tmp/ohsu-digpath-receipt.json
```

The CLI returns `0` only when the transcript satisfies the acceptance contract; malformed/conflicting evidence returns `2`.

## Commercial seam

The accompanying `TEAMING.md` packages this as a proposed **$7,500 fixed two-week integration acceptance sprint** for an actual IMS prime pursuing the OHSU opportunity. That number is our proposed specialist price, not an OHSU budget, award, accepted quote, or earned revenue. Prime/vendor product qualification, production access, BAA/security terms, clinical validation, medical-device obligations, customer references, and the RFP submission remain with the prime and buyer.

## Public-source boundary

See `SOURCES.md`. This package relies only on OHSU's public bid listing and Epic's public Digital Pathology integration documentation. It does not claim access to OHSU's full RFP package, Epic customer environments, production interfaces, patient data, proprietary IMS internals, or an agreement with any vendor.
