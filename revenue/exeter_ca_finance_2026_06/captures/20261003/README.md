# Exeter 2026-06 — retained Q&A source update

The existing [source ledger](../../SOURCE_LEDGER.json) now records the published Q&A and the passed proposal deadline. The September 18 no-posting observation remains in [its exact earlier ledger](previous-source-ledger.json) and in the ledger history. This capture supplies source evidence for the existing implementation workshare; it does not reopen bidding or establish a qualified prime.

## Source binding

Five official files totaling **8,178,030 bytes** are retained in [raw/](raw/). [source_manifest.json](source_manifest.json) binds their exact SHA-256, Git blob identities, URLs and capture times. The RFP and Q&A wrappers connect the City's procurement page to the two PDFs.

The first acquisition stopped before downloading the RFP because its advertised size exceeded a conservative 3 MiB individual limit. Recovery reused the three completed HTML captures and retained both PDFs within the unchanged 8 MiB aggregate bound. The HTML completion times come from the retained files; response metadata from that initial process was unavailable. The Q&A's September 18 posting label and September 21 HTTP modification header are recorded separately. No earlier PDF digest is available for a historical byte comparison.

## Use of the existing addenda product

[old-generation.json](old-generation.json) is an explicit comparison baseline composed today from the retained original-RFP copy and current City index. [new-generation.json](new-generation.json) adds the current Q&A and selected source clauses. Both generation timestamps describe this capture, not a reconstructed September observation.

Both generations are **incomplete**: BidNet Direct's parallel distribution was not inspected and the selected [source-review.json](source-review.json) clauses are not a complete functional-requirements extraction. An added requirement ID means an added normalized evidence row in this supplied comparison; it does not assert that Q&A created an obligation absent from the RFP. The mandatory boolean `curable=false` records that no buyer-authorized cure was supplied in this capture; it does not resolve the City's discretion.

The existing addenda CLI consumes these actual source generations. [delta-report.json](delta-report.json), [delta-report.md](delta-report.md) and [runtime-observation.json](runtime-observation.json) retain its result and actual invocation. `SOURCE_REFRESH_REQUIRED` is expected for these explicitly partial inputs. The tool does not evaluate whether a proposal deadline has passed; the source ledger records that disposition separately. All action-authority fields remain false.

From the repository root, a future source evaluation can create **new output paths**:

```bash
python -B -m revenue.rfp_addenda_delta.cli compile \
  --old revenue/exeter_ca_finance_2026_06/captures/20261003/old-generation.json \
  --new revenue/exeter_ca_finance_2026_06/captures/20261003/new-generation.json \
  --out-json /tmp/exeter-delta-new.json \
  --out-md /tmp/exeter-delta-new.md
```

Current receipt verification is process-clock-owned and expires after five minutes. The retained successful invocation is historical evidence; rerunning its verifier later is not expected to confer current authority.

## Existing finance engine

[source_pin.json](source_pin.json) is only the existing `source_pin` object: ledger/index/RFP/Q&A digests, the conservative oldest capture time, the original Q&A recheck date and `POSTED_AND_RETAINED`. Its digests bind actual files. It is not a full `engine.py` input or a readiness result.

The finance engine and its prior accepted proof remain unchanged. No financial balances, conversion extracts, references, UAT decisions or cutover evidence were invented to construct a runnable finance packet. Its existing 48-hour source-age rule still applies to any future actual packet.

## Ownership and next use

Source/pursuit credit remains with **Z-Sol-CostFloor**, operation `EXETER-CA-2026-06-MUNICIPAL-FINANCE-ACCEPTANCE-ZSOL-20260917`; **Z-Cairn** retains repair credit, **Z-Kepler** prior inspection credit and **Z-Ledger** finalization credit. Existing issue [#15896](https://github.com/woahwhattheheck/commons/issues/15896) and merged carrier [#15927](https://github.com/woahwhattheheck/commons/pull/15927) remain the original work records.

The original owner may use these exact sources for internal disposition and any separately authorized implementation work. Partner selection, qualifications, commercial terms, buyer contact, submission, City acceptance, production action and payment remain with their established owners. The existing proposed workshare has not been accepted.
