# <=2 minute demo script

**0:00–0:15 — problem**
“Screenshots and status messages say work is done, but they are hard to verify later. ProofPocket turns local evidence into a portable deterministic receipt without uploading the evidence.”

**0:15–0:45 — create proof**
Create a project, type a bounded claim, attach two local files. Show each file's byte size and SHA-256 prefix. Tap Create receipt and show the receipt ID.

**0:45–1:05 — verify / tamper**
Export JSON, import the untouched receipt and show “verified.” Change one claim/evidence field in a prepared tampered copy and import it; show rejection.

**1:05–1:35 — monetization**
Show Free's 3-project boundary. Open the RevenueCat-backed Pro purchase surface, complete the real supported test/store purchase, show the observed `pro` entitlement, then export the PDF proof pack. Use Restore Purchases to demonstrate recovery. Do not simulate this segment if provider setup is not real.

**1:35–1:50 — privacy / product**
Show no account required and explain that evidence bytes stay local; RevenueCat handles only purchase/entitlement traffic.

**1:50–2:00 — close**
“ProofPocket: proof of work you can carry in your pocket.”
