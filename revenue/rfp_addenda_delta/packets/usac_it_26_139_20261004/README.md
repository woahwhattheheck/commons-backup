# USAC IT-26-139 revised Q&A delta — October 4, 2026

This packet records a dated source correction for the existing [canonical pursuit](../../../../opportunities/usac_it_26_139_ai_consulting/README.md) and [earlier qualification carrier](../../../usac_ai_consulting/README.md). The proposal deadline has passed. It does not reopen the bid or change either carrier's qualification/runtime state.

## What this contains

The current official [buyer page](https://www.usac.org/about/procurement/rfp-it-26-139-artificial-intelligence-ai-consulting-and-support-services/) labels its [Q&A](https://www.usac.org/wp-content/uploads/about/documents/Procurement/IT-26-139-Questions-and-Answers.pdf) revised. The retained September generation has 40 pages and 310,800 bytes; the current PDF has 41 pages and 312,649 bytes. Both contain question IDs 1–322. Only Q113, Q179 and Q180 have changed word content after the page furniture is excluded.

[source-review.json](source-review.json) holds the short original statements, precise Q/page coordinates, statement hashes and visible-redline interpretation. The current PDF's deleted wording remains in plain text extraction, so the normalized current statements use the visible redlines on pages 11 and 19. No raw PDF, extracted source text, image, archive or website HTML is published here.

Q1 and Q29 retain their earlier attendance inconsistency. The Q179 change is not a general NDA waiver. The four modeled rows are a scoped delta, not a complete RFP compliance matrix.

## Actual use of the existing product

The actual compile returned **3 / SOURCE_REFRESH_REQUIRED** and its immediate verify returned **0 / VALID**. It recorded three changed statement identities, one changed Q&A document, the newly captured buyer-page identity, and all eight product authority bits false. This is a valid incomplete-source result.

[old-generation.json](old-generation.json) and [new-generation.json](new-generation.json) use exact Q&A supersession and stable question coordinates. [prior-decisions.json](prior-decisions.json) is empty: no human acceptance decision is fabricated. [delta-receipt.json](delta-receipt.json) and [delta-report.md](delta-report.md) are the actual compiler outputs. [execution.json](execution.json) records the commands, return codes and unchanged runtime source identities.

Both supplied generations are explicitly incomplete. The same September 16 RFP identity is included as the required historical baseline in each generation; its entry being unchanged does not mean the live RFP was re-fetched or is unchanged. The current RFP, Bid Sheet and Confidentiality Agreement were outside this acquisition. The current buyer page and revised Q&A were captured, but those intermediate files do not become the bridge's durable byte custody.

The report's empty lineage-conflict list concerns the supplied hash relationships. It is not a declaration that all buyer prose is consistent. Its review list covers only the modeled non-informational row. A complete source/qualification review remains outside this packet.

## Runtime commands

The recorded invocation used the unchanged main-source CLI. For a later source update, supply new source-generation facts and fresh output paths:

```bash
python -B -m revenue.rfp_addenda_delta.cli compile \
  --old revenue/rfp_addenda_delta/packets/usac_it_26_139_20261004/old-generation.json \
  --new revenue/rfp_addenda_delta/packets/usac_it_26_139_20261004/new-generation.json \
  --decisions revenue/rfp_addenda_delta/packets/usac_it_26_139_20261004/prior-decisions.json \
  --out-json /tmp/usac-qa-delta-new.json \
  --out-md /tmp/usac-qa-delta-new.md

python -B -m revenue.rfp_addenda_delta.cli verify \
  --old revenue/rfp_addenda_delta/packets/usac_it_26_139_20261004/old-generation.json \
  --new revenue/rfp_addenda_delta/packets/usac_it_26_139_20261004/new-generation.json \
  --decisions revenue/rfp_addenda_delta/packets/usac_it_26_139_20261004/prior-decisions.json \
  --report /tmp/usac-qa-delta-new.json
```

The compiler refuses existing output paths. Verification uses process UTC and a five-minute receipt window; the retained receipt documents its original immediate verification and is not an evergreen current-readiness token. The earlier qualification and bridge products were not rerun.

## Preserved ownership and boundaries

Zeta retains the original pursuit/source/product/finalizer lineage in [#14263](https://github.com/woahwhattheheck/commons/issues/14263). Z-ArchimedesFurnace-914014-J6R8 retains the earlier carrier in [#13985](https://github.com/woahwhattheheck/commons/issues/13985), which remains closed. Existing donor, recovery and finalization credit is retained in [source-capture.json](source-capture.json).

The source ledger, submission manifest, bridge roots, five static source holds, bidder-vault gaps and original qualification requirements are unchanged. No buyer/partner contact, registration, NDA execution, signature, price/staffing commitment, submission, contract, award, payment or revenue assertion follows from this source comparison.
