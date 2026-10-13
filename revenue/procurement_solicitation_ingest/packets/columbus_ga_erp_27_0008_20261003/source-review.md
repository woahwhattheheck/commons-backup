# Columbus ERP — source interpretation

This is original analysis of the two PDF identities in [source_manifest.json](source_manifest.json), read on October 3, 2026. References below use physical PDF pages, which match the printed page numbers. The [normalized worklist](pack.json) records the same citations.

| Topic | Supported reading and owner implication | Source / rows |
|---|---|---|
| Schedule and incomplete addenda coverage | Addendum 1 controls October 14 at 5 PM; the RFP supplies Eastern-time context. Its promised answers remain unestablished. Keep the five-business-day question rule without inventing a calendar cutoff. | [Addendum 1, p. 1](https://columbusga.gov/Portals/finance/Resources/bid-opportunities/2027/Heather%20FY27/RFP27-0008Add1.pdf?ver=cv2WcenM8Clm9ZrVslwP2w%3D%3D); [RFP, pp. 7–8](https://columbusga.gov/Portals/finance/adam/Content/LDQoKeGkfk6iEZfk7wkYyw/SolicitationDocument/RFP27-0008.pdf); CCG-032/036 |
| Firm versus team experience | At least three comparable public-entity clients concern the firm; at least two comparable implementations concern the proposed team. Evidence for one does not automatically satisfy the other. | RFP pp. 18, 33; CCG-011/012 |
| Insurance form | Visual inspection confirms X-marked coverage rows 1, 2, 3, 7, 8 and endorsements 22–25. Generic unmarked rows are not all required coverage. Certificates are a conditional post-award obligation; the response requires Form 8 or insurance evidence. | RFP pp. 14, 35–36; CCG-025/026 |
| Scope | CGI Advantage 4.0 is vendor-hosted SaaS. Migration, parallel payroll, cutover/rollback and support through both first year-end cycles require distinct delivery evidence. No production data or successful conversion is supplied here. | RFP pp. 13, 17–18; CCG-015/017/019/020/033 |
| Disclosure and security | Offshore staffing is a disclosure requirement, not a categorical ban. Named security frameworks do not establish possession of every certification. | RFP pp. 16–17, 25–26; CCG-010/028 |
| Hard-copy conflict | Post-award instructions call for one copy on pages 11 and 38, but two on page 19. This generation preserves the conflict. | RFP pp. 11, 19, 38; CCG-034 |

The response-cost horizon says **up to five years** for maintenance fees; the worklist does not turn the historical specialist workshare into the City's full implementation price (RFP pp. 18–19, CCG-022). Federal-form applicability stays conditional; no federal funding is inferred from including Form 4 (p. 31, CCG-007).

The input groups the functional specifications into selected owner-review rows. It does not claim complete line-by-line coverage of every ERP module or evidence that any bidder satisfies them. Any pursuing prime remains responsible for its own product, references, people, forms, pricing and delivery; the [original acceptance matrix](../../../columbus_ga_erp_27_0008/ACCEPTANCE_MATRIX.md) still governs the proposed specialist evidence workshare.

## Observed use and limits

[Compile and immediate verify](runtime-observation.json) both exited 0 on the actual normalized input. The structural status is `OWNER_REVIEW_READY`; **31 mandatory/scored evidence gaps remain open**. The remaining five rows carry information rather than satisfied qualifications. The selector records the Addendum 1 deadline as October 14, 2026 at 21:00 UTC.

The source operation had two earlier nonzero outcomes that remain in the observation: the acquisition completed its PDF/manifest writes but its final report raised a Python name error; the first manifest stage then stopped before extraction or CLI because of the recorded board timeout. The corrected stage accepted only the explicitly bounded PDF pair, verified their identities and performed no repeated request. These outcomes do not become a complete-source or bidder-readiness claim.

Raw buyer source and extracted text are not published. Source hashes identify the intermediate bytes; they do not imply those bytes exist as repository blobs. The next source change requires its own capture and original analysis. Tyler's existing [SENT / HARD_DNR](https://github.com/woahwhattheheck/commons/issues/15599#issuecomment-5719645747) and Swarm Z ownership remain in force.
