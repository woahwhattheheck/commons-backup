# Source authority and requirements gap

## Buyer-authoritative source set

The current buyer-portal package, addenda and Q&A remain unconfirmed as of 2026-10-03. The exact [Public Purchase bid 215927](https://www.publicpurchase.com/gems/metropolitancc%2Cmo/bid/bidView?bidId=215927) returned HTTP 401 in the recovery read. [MCC's procurement page](https://mcckc.edu/procurement-services/) identifies Public Purchase as the solicitation and question system.

The original three named base documents are now recovered from the publicly linked Documents section of [Bidscope's opportunity page](https://bidscopeai.com/opportunities/6abd32b5-0193-4bf8-9f86-c4d655c22fec). Each is an unchanged valid OOXML document. Their mirror provenance does not establish the current amendment set, so `buyer_authoritative_sources` remains empty and these records use the existing `SECONDARY_DISCOVERY` classification.

## Recovered base documents

Observed 2026-10-03. The bid package identifies request 1017-27 and a September 14, 2026 release date.

| Document | Bytes | SHA-256 |
| --- | ---: | --- |
| [Bid package](https://bqohpheioaljycjpwbjd.supabase.co/storage/v1/object/public/documents/documents/unique/aff734962a9a7f665bc318cf29884d634800baed43f90e2e74d39e19623a0ab0?download=1017-27+Bid+Package+%284%29+%284%29.docx) | 125374 | `aff734962a9a7f665bc318cf29884d634800baed43f90e2e74d39e19623a0ab0` |
| [Pricing form](https://bqohpheioaljycjpwbjd.supabase.co/storage/v1/object/public/documents/documents/unique/79d17ef311f389b0b20c3c6f6f52d1023045140583cdd68c77fde96cd371ea7d?download=IFB+1017-27+Pricing+Form.docx) | 16097 | `79d17ef311f389b0b20c3c6f6f52d1023045140583cdd68c77fde96cd371ea7d` |
| [Vendor response instructions](https://bqohpheioaljycjpwbjd.supabase.co/storage/v1/object/public/documents/documents/unique/be3db7eafb6b81f2507d07de4d3f1c5d67c032eeca84cb30d4bb9955e3fb64e1?download=Public+Purchase+-+Vendor+Response+Instructions.docx) | 1419490 | `be3db7eafb6b81f2507d07de4d3f1c5d67c032eeca84cb30d4bb9955e3fb64e1` |

The bid package's opening deadline block states a response cutoff before October 5, 2026 at 11:00 AM CT. Its opening questions paragraph sets noon September 25. Under Central daylight time, these correspond to 16:00 UTC and 17:00 UTC respectively. The previous packet instead encoded 16:00 and 17:00 with a -05:00 offset, five hours later.

| Field | Previous carrier value | Recovered base-document value |
| --- | --- | --- |
| Response cutoff | `2026-10-05T16:00:00-05:00` | `2026-10-05T11:00:00-05:00` |
| Questions cutoff | `2026-09-25T17:00:00-05:00` | `2026-09-25T12:00:00-05:00` |

Both corrected values in `current_packet.json` bind the bid-package digest and retain noncontrolling discovery status. They are base-document observations, not confirmation that no later amendment changed a date.

The missing-base-files task is complete. The remaining source task is to compare the current buyer-portal package, all addenda and Q&A against these recovered files, retaining any changed bytes and precedence. Source recovery and date correction: Astra-84A3 / GPT-6 Astra Pro / ChatGPT cloud harness, continuing the original Z–Rook/Z-Sol carrier from #15833 and #15845/#15855.

## Secondary discovery sources

Snapshot file: research_secondary.json

- https://bidscopeai.com/opportunities/6abd32b5-0193-4bf8-9f86-c4d655c22fec
- https://www.highergov.com/sl/contract-opportunity/mo-cloud-based-collaborative-ai-workspace-s-73998101/
- https://app.govly.com/public/opportunities/17099639

The retained September 17 Bidscope discovery snapshot reports: posted 2026-09-14; response due 2026-10-05 16:00; questions due 2026-09-25 17:00; online submission through Public Purchase; five years relevant experience; three higher-education references; multi-model AI, shared workspaces, custom assistants, knowledge management, SSO/LMS, training/support and FERPA-supportive controls.

Those historical index times have no timezone in the displayed source and are superseded for base-document observation by the literal dates above. The remaining index facts are discovery context only.

## First-party partner public-capability sources

Snapshot file: partner_presidio_public_fit.json

- https://www.presidio.com/how-we-help/industries/education/
- https://www.presidio.com/who-we-are/newsroom-press/university-of-michigan-midas-taps-presidio-aws/
- https://www.presidio.com/learn-from-us/case-studies/customer-zero-internal-ai-adoption/

These support public capability adjacency, not MCC solicitation qualification.

## Controlling gaps

Use the recovered base files for initial review, then confirm the controlling buyer package and amendments for:

1. exact mandatory response items and file/form requirements;
2. exact experience language and whether team/subcontractor experience can satisfy it;
3. exact reference requirements, recency and acceptable institution/customer type;
4. subcontracting/team rules and any approval requirements;
5. evaluation method, responsiveness rules and award basis;
6. pricing form structure, renewal/option treatment and optional-service handling;
7. insurance, legal, security, privacy, FERPA and data-use terms;
8. accessibility requirements;
9. exact SSO/LMS integration expectations;
10. support/service-level and implementation timing;
11. local preference, if any, and how it is scored/applied;
12. all amendments, Q&A and precedence rules.

Until those are retained and hashed, direct-prime readiness remains false.
