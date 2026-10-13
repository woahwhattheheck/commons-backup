# Multi-photo evidence packet: executed synthetic rehearsal

Nine deterministic image-packet cases and one local S3-shaped fixture. Every image is generated here; no real inspection or person appears.

| Case | Observed next step |
|---|---|
| `distinct` | ACCEPT_FOR_HUMAN_REVIEW |
| `missing` | REQUEST_MISSING_VIEW |
| `exact-duplicate` | HOLD_DUPLICATE_EVIDENCE |
| `near-duplicate` | HOLD_DUPLICATE_EVIDENCE |
| `blur` | REQUEST_RECAPTURE |
| `shadow` | REQUEST_RECAPTURE |
| `highlight` | REQUEST_RECAPTURE |
| `corrupt` | HOLD_UNSAFE_OR_UNREADABLE |
| `digest-mismatch` | INPUT_REJECTED |

The S3-shaped fixture verifies its manifest, object bytes and outer receipt. An altered envelope fails fixture verification. Objects are supplied by an in-process dictionary; no AWS deployment or execution is evidenced.

A passing packet reaches human review only. The quality measures do not establish correct viewpoint, identity, authenticity, fraud, compliance or business approval. Thresholds are illustrative and require calibration on the intended imagery.

Observed runtime: OpenCV 4.13.0. Competition eligibility or submission is not evaluated by this rehearsal.

## Reproduce these outputs

Run `python competitions/opencv-ai-2026/visual-evidence-gate/packet_rehearsal.py NEW_DIRECTORY` from the repository root. This creates the complete image/input/receipt bundle; its paths are relative to the selected directory. Normal and optimized runs produced 55 byte-identical files totaling 671,143 bytes.

This readout is generated from the actual recorded rehearsal, not a forecast of results. See [the operating guide](PACKET_GUIDE.md) for the contract and [the clarification execution receipt](PACKET_CLARIFICATION_EXECUTION.json) for exact source and test identities.
