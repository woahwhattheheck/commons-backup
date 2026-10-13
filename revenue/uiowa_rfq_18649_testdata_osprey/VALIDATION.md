# Executed validation and recovery record

Seat: ZZ-OSPREY-86C1 / GPT-6 Astra Pro. Date: 2026-09-19.
Operation: `uiowa-047-osprey86c1-reconcile-20260919`.
Scope: ephemeral cloud source tree with the actual canonical sibling assessor.
No target application was executed. No repository-wide or hosted-CI pass is claimed.

## Executed commands

```text
python -m unittest discover -s . -p 'test_*.py' -v
Ran 98 tests in 13.723s
OK

python -O -m unittest discover -s . -p 'test_*.py' -v
Ran 98 tests in 12.350s
OK

python -m py_compile fixture_lab.py canonical_bridge.py reproduce.py make_example.py \
  test_fixture_lab.py test_canonical_bridge.py test_reproduction.py
PASS

python reproduce.py /mnt/data/osprey-pinned-run --verify-only
PINNED_FICTIONAL_EXAMPLE_MATCH; 15 files
```

Runtime: CPython 3.13.5, GCC 14.2.0, Linux. Times describe this execution, not a
capacity guarantee. All tests ran; none were skipped. There are 67 recovered
fixture tests, 25 new bridge tests, and six retained-output reproduction tests.
The bridge and reproduction CLI paths are explicitly run under normal, `-O`
and `-OO` interpreters and compared byte-for-byte. The original 67-test CLI
helper launches its ordinary interpreter; the added tests separately exercise
its invalid-input rejection under all three modes.

Test log SHA-256:
- Normal: `734d1ba74ef239ccb339627132061f9bd175f2bf4030d0428ed756afa8724dc7`
- Optimized: `5cd429ce8a9455fd4c345e20b26cefdd58b5ce76091b9010a3781a0c86cbc133`

These identify captured local logs; they are not provider job IDs or an assertion
that those logs were uploaded to GitHub Actions.

## Exact executable source identities

| File | Git blob |
|---|---|
| fixture_lab.py | `7991c93887c283ab9496021b48ee54f1332e2745` |
| make_example.py | `0ded0e366e330618b260f9a6e9c1c4b591c60217` |
| test_fixture_lab.py | `e37c1295695bd5b0ea6f2b77f84b8bfcef362eb2` |
| canonical_bridge.py | `d6c2d581eaabe8b2fd6622f7863c4a2dd44d9a49` |
| test_canonical_bridge.py | `9b6c8d498737afec84c327b52b1284704ca8a50d` |
| reproduce.py | `342474690fe9175a0979c81a51e981df3c5ff29b` |
| test_reproduction.py | `c81e526c23a70df55bea8a556266857958d6ecda` |
| EXPECTED_EXAMPLE.json | `e6d84023464d819ca1f9aefb3bfec497761b01cb` |

Actual canonical dependency: `revenue/uiowa_rfq_18649_test_data/assess.py`,
Git blob `8ec595c7cdc2dad80d81dbc4b5f203b152b2f1b3`, 20,251 bytes;
retrieved at merge `0c1e2a9e45cc60461cac39f7e25e15efd4ef0555` from PR #16208.
The reconstructed runtime copy was byte-identified against that Git blob before
execution. It is consumed unchanged, not copied into this product or replaced
with a test double. Negative-control tests deliberately alter a separately loaded
in-memory instance to establish that a promoted result or changed denominator
is rejected; those are not used as the positive integration evidence.

## Worked output identities

The retained source fixture bundle manifest is
`888533539002e343d7f3aaac6445a2d3bc55f078d23ba5babc62602a484e5dd6`.
The bridge mapping is
`1716c3bb8a4615c8f7d4a56cb801168d085dda1e9589a1b2813e750e377a581b`.
The canonical report is
`a89a12d6bbe4a9e60aa426cb209e6d13da2a2bec6426031d36a4ad2dc7632d68`.
All 15 output digests are retained in `EXPECTED_EXAMPLE.json`, which neither the
runner, verifier nor tests rewrite.

Observed: 6 definitions, 28 planned cases, 23 mapped cases and 5 retained-unmapped
cases. There are zero recorded application runs, zero supported cases and zero
recorded failures. All 23 mapped observations stay unknown. The report retains
one retired fixture and one source/target version mismatch. This is a complete
rehearsal of specification-to-assessor composition, not completed application testing.

## Recovery provenance

Original attachment: `ZZ-OSPREY-86C1-uiowa047.zip`, 81,838 bytes, SHA-256
`54b665ae7b49798179ea473b15dd1c4f34d90846e98ce0fa8c79249dc007ae12`.
The archive hash is a provenance reference, not a claim that the zip is stored
in this repository. Its three executable source files and four instruments
were recovered byte-identically. Its 11 generated catalog/review/bundle files
were rebuilt and compared byte-for-byte in the cloud before publication of the
recipe and retained digests. Redundant generated trees are deliberately not
tracked twice. Current README/validation supersede the older operational text.

Historical prior execution recorded 67/67 normal tests in 13.088s and 67/67
optimized tests in 13.752s, with no skips; those were isolated fixture-library
runs, not canonical integration. Current 98-test results above replace that
narrower execution scope. No earlier unsent Slack draft or missing-publication
status is represented as a successful provider action.

## Review boundaries

The example pin is outside generated output and is never automatically healed.
Repeated verification continues rejecting edited output. Generated expectations
cannot become application observations. Input byte trees remain unchanged.
Unknown target contracts and missing observations remain visible. Review cadence
and effort ranges retain their original semantics. Normal and optimized paths
use explicit runtime checks rather than removable assertion-based validation.

Hosted workflows, exact current-main integration state and merge receipts must
be read from the actual pull request; local tests do not imply any of those states.
