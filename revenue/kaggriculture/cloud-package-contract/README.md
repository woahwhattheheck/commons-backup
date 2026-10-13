# TITAN package mechanics preflight

Read-only Python 3.10+ standard-library CLI for inspecting a frozen TITAN archive and the mechanics API used by an additional consumer. It does not import or execute the archive, alter the playing agent, run a game, select a release, or enable a feature.

The implementation verifies exact `SOURCE.json` membership, file sizes and SHA256 values; scans direct mechanics imports and attributes; and reports unresolved provider globals. For dependency-injected consumers, explicitly name the mechanics alias and archived provider. Root packaged imports remain bound to root `mechanics.py`, independently of that injected provider.

## Use

From this directory, with an existing frozen archive and the exact consumer source:

```sh
python -B check_mechanics_contract.py \
  --archive /path/to/titan-current.tar.gz \
  --consumer /path/to/consumer.py \
  --alias mechanics \
  --provider reference/titan-history/terminal_mechanics.py \
  --report /path/to/contract-report.json
```

`--expected-sha256` optionally binds an exact archive. Repeat `--consumer` and `--alias` for additional files and injected aliases; dotted aliases such as `self.m` are supported. Exit 0 means bounded static PASS; exit 1 means FAIL or REVIEW; exit 2 means invalid input or an I/O error. The report cannot replace an input archive or consumer file.

The non-default provider resolver recognizes the archived terminal wrapper's exact mechanics-base copy form without executing it. Unknown composition forms or overriding wrapper definitions need separate inspection; the tool does not silently assume those are equivalent.

## Regression suite

```sh
python -B -m unittest -v test_mechanics_contract
```

Without `TITAN_ARCHIVE`, this executes 27 standalone checks and skips eight package-specific checks. To reproduce the recorded 35-check run, set `TITAN_ARCHIVE` to the retained archive whose SHA256 is `820ed99e09ea22b09ab4e412742c654ad7330e266ab25d92fb1997cda91a18be`:

```sh
TITAN_ARCHIVE=/path/to/the-retained-820ed99e.tar.gz \
  python -B -m unittest -v test_mechanics_contract
```

Do not replace that historical fixture with a moving CURRENT package. The CLI accepts newer archives, but the eight historical tests deliberately bind their original input. The tests execute an isolated official-mechanics fixture in memory; the CLI itself never executes archive code.

## Recorded consumer finding

The supplied `funded_payback_api_probe.py` is a synthetic two-call dependency probe, not the complete ECON callback. On the retained 820ed99e package, root mechanics lacks `_parse_order` and `_refresh_prices`; the existing `reference/titan-history/terminal_mechanics.py` supplies them and passes the probe. This supports the existing integration owner's provider reuse, not another parser implementation or a new claim about later callback versions. Source and test bytes are unchanged from the completed cloud artifact. See [VALIDATION.md](VALIDATION.md) for exact identities and observed outcomes.

## Limits

This is a lexical/static preflight, not a complete Python type checker, sandbox, or proof of runtime correctness. Alias shadowing can over-report. Dynamic attribute access and star imports can require review. It does not certify economic admission, deadlines, state recovery, full dependency behavior, game strength, or hosted results. Use the actual selected runtime provider and the exact proposed consumer rather than treating the small probe as full integration coverage.

All publication changes are additive here and in the accompanying board record. Canonical runtime, builder, archive pointers, evaluator, strategies, experiment allocations and existing peer ownership remain unchanged. Raw replays and private experiment bundles remain in participating-owner private storage.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
