# Owner/provider gates — do not mark complete without authenticated evidence

Source is not the submission, and this repository deliberately cannot promote itself to competition READY.

1. Complete/confirm the RevenueCat account email verification on the actual provider account.
2. Confirm an eligible Android developer account (Google Play or Samsung Galaxy Store) with authority to publish a **new** app.
3. Create the Android app record for exact package `com.tokenjunkielabs.proofpocket` and upload a signed release/closed-test build as the store requires.
4. In RevenueCat, bind the exact store app, create a product/package/offering, attach it to entitlement **`pro`**, and supply the app's **public** SDK key at build time.
5. Exercise purchase + restore on a supported real store/test path; record observed entitlement behavior. Do not use a local boolean as purchase proof.
6. Publish the first public ProofPocket store version inside the Shipaton eligibility window and before **2026-09-30 23:45 PDT / 2026-10-01 06:45 UTC**; capture the exact public U.S.-available store URL and package/version readback.
7. Capture the app icon and screenshot; record a <2-minute demo showing the app, local digest/receipt workflow, verification/tamper rejection, and actual RevenueCat purchase/restore path. Retain content digests for the exact submitted media.
8. Complete Devpost registration/submission and terms under the authorized owner identity; retain the provider submission identity and timestamp.
9. Bind all of the above through a **separate authenticated host/provider adapter** that reacquires provider truth and owns current-time/deadline evaluation. A local JSON file, hash, `authority` label, source commit, or `shipaton/readiness.py --witness ...` invocation is not authority. The current compiler will preserve a caller-authored witness digest for audit history but will remain `HOLD_EXTERNAL_AUTHORITY` forever by design.

Never commit signing keys, provider secrets, bank/card data, store passwords, or private RevenueCat API keys. Never treat a screenshot filename, arbitrary URL, local boolean, or self-generated digest as provider verification.
