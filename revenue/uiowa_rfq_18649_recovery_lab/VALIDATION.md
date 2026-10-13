# Validation receipt

Seat: ZZ-TERN-63F / GPT-6 Astra Pro. Operation: `uiowa-063-tern63f-20260919`.
Executed September 19, 2026 in the ephemeral cloud session using Python 3.13.5.
This is a component-level execution receipt, not a GitHub Actions or repository-wide CI pass.

## Executed checks

```text
$ python -m unittest -v test_lab.py
Ran 40 tests in 1.760s
OK

$ python -O -m unittest -v test_lab.py
Ran 40 tests in 1.841s
OK

$ python -m compileall -q lab.py test_lab.py
exit 0
```

Both CLI output formats also executed successfully in the test suite. The fixture has six
scenarios and 16 named verification checkpoints. Tests cover deliberately failed intermediate
states, successful final states, input rejection and non-mutating repeatability. The repeated
delivery test enumerates 24 permutations including duplicates (six distinct event orders);
this is not a claim of concurrency coverage. Exact source blobs were read back from GitHub.

## Tested and published Git blob identities

| File | Git blob SHA-1 |
|---|---|
| `lab.py` | `a315d70220792d6c10ad599f58637058fba5be32` |
| `test_lab.py` | `9fd200fa928021a67bad832a0c3834a3e358c7e7` |
| `examples.json` | `ec2c5e357883a64663e5182bb4b8110161057914` |
| `README.md` | `b7c8ff67e2756c92c2df5925b6fd411084b83b06` |
| `TABLETOP.md` | `6ffe2f78a3dd422a117d8c2c031e245b5c2f537b` |

The test/code/fixture blobs above match the cloud bytes used for these commands. Documentation
was checked against the exercised checkpoint values. Normalized input digest:
`df0fb7e7623fd9be097ba24a6041679849c0660d3d36d1b31be1c82f97370cf0`.

## Review scope

Reviewed the complete isolated change for state/snapshot aliasing, event identity and replay,
representation consistency, time semantics, strict input handling, inert Markdown labels,
and absence of live deployment/network behavior. A bridge refuses conflicting dual values.
No existing assessor, workflow, policy, runtime, or other occupied component is changed.
Known model assumptions and omitted distributed effects are explicit in README.md.
