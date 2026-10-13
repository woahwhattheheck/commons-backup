# PocketPay #447 precision repair

This is a source-complete continuation of [PocketPay PR #457](https://github.com/Stellar-PocketPay/pocketpay-sdk/pull/457), for the existing claimant to apply to that same PR. The patch fixes wallet arithmetic that discarded decimal precision before the submitted exact display normaliser ran.

**Base:** `tokenjunkielabs/pocketpay-sdk:main` at `89a9e9b4c952b96d19f30e20c753f7f240f3f024`. [Issue #447](https://github.com/Stellar-PocketPay/pocketpay-sdk/issues/447) and its [existing claim](https://github.com/Stellar-PocketPay/pocketpay-sdk/issues/447#issuecomment-5753679696) retain their original owner. This handoff does not establish sponsor acceptance, an award, or payment.

## Four changed files

- `src/wallet/multi-asset.ts`: reuse the existing `parseAmount` and `formatStroops` utilities for integer reserve/liability arithmetic, zero clamping, and availability state.
- `src/utils/balanceDisplay.ts`: fix four strict TypeScript diagnostics with a destructuring default and `charAt`, without changing valid output.
- `tests/multi-asset-balance.test.ts`: add nine sponsor-required cases for native/issued precision, display rounding, zero clamping, and typed invalid-amount rejection; reuse the funded-account fixture.
- `docs/balance-display.md`: explain exact deductions and the parser's typed-error boundary.

Native reserve policy and authorization precedence stay as implemented by the existing PR. Malformed balance or selling-liability strings now produce `PAYMENT_INVALID_AMOUNT` rather than being partially accepted by `parseFloat`. The safe query wrapper retains its failure-result path. The display normaliser retains its separate missing/invalid return contract.

## Reproduced behavior

The real SDK parser and formatter were executed locally with deterministic Horizon-shaped boundary inputs. These are synthetic amount-range cases, not fetched customer accounts or live transactions.

| Case | Submitted source | Repaired source |
| --- | --- | --- |
| Native `922337203685.4775807 - 1.0000001` | `922337203684.4775391` | `922337203684.4775806` |
| Issued maximum minus `922337203685.4775806` | `0.0000000`, state `reserved` | `0.0000001`, state `available` |
| Issued `922337203685.0050000 - 0.0000001` | `922337203685.01 USDC` | `922337203685.00 USDC` |

The amount units follow [Stellar amount precision](https://developers.stellar.org/docs/learn/fundamentals/stellar-data-structures/assets#amount-precision): seven decimal places and signed 64-bit integer stroops. Horizon describes balances and selling liabilities as strings in its [account object](https://developers.stellar.org/docs/data/apis/horizon/api-reference/resources/accounts/object).

## Apply to the existing PR

Use the existing claimant checkout and preserve the same branch and PR. Confirm the base above; if it moved, inspect the current changes and compose this patch rather than overwriting them.

```bash
git rev-parse HEAD
git apply --check /path/to/pocketpay-447.patch
git apply /path/to/pocketpay-447.patch
```

The patch was actually applied to the four original files. Every resulting byte matched the full files under `postimages/`; hashes are in `source-manifest.json`.

With the repository's declared dependencies installed, copy `reproduce-balance-precision.ts` to its root and run:

```bash
node --import tsx reproduce-balance-precision.ts
npm test -- --reporter=default
npm run lint
```

## Retained run results

- Direct parser/formatter reproduction: **0/3 correct before; 3/3 correct after**.
- Both balance test files: **29/29 passed** on repaired source.
- Full default suite: **1,132 passed, 2 failed, 1 skipped** across 62 files. Both failures are in unchanged `tests/qrParser.test.ts`; the skipped test is the opt-in Friendbot integration.
- Minimal baseline replay: the seven new precision/invalid-input cases fail on the exact submitted source, and both QR failures reproduce unchanged. The two new zero-clamp cases already pass before the repair.
- `tsc --noEmit`: **12 diagnostics before; 8 after**. The four display-normaliser errors are removed. The remaining eight are unchanged QR validation field/code mismatches; final compiler exit is 2.
- No new dependencies, hosted CI, live account operations, or payment actions. Coverage, the build-emitting command, and the full presubmit pipeline were not run; the existing compiler failure remains visible.

The run used Node 24.19.0, TypeScript 5.9.3, Vitest 3.2.7, Stellar SDK 13.1.0, and dotenv 16.6.1. Existing cloud dependencies were reused read-only. Local Node type declarations were 20.19.43, whereas the package requests ^22.15.17; the reported diagnostics concern repository validation literals, and reproduce on original source. No clean-install or all-green build claim is made.

### Remaining QR work

Both original and repaired source fail the existing QR assertions: the parser does not return the directly expected `address`, and malformed input does not throw the expected `PaymentParseError`. The compiler also rejects `address`, `asset`, and `metadata` validation fields and `INVALID_ASSET`/`INVALID_METADATA` codes. The QR implementation came from already-merged [PR #455](https://github.com/Stellar-PocketPay/pocketpay-sdk/pull/455). This four-file #447 repair does not modify that separate parser contract.

## Publication handoff

The native connector reports pull access on the claimant fork. The existing documented claimant publisher rejected one independent utility update under stable operation `gateway-1519-pocketpay457-strict-indexing-20261003-7dc3`: [request and receipt](https://github.com/woahwhattheheck/commons-ship-enforcer/issues/1519#issuecomment-5966880863). Exact readback still showed original PR head `89a9e9b4` and utility blob `3e94b8f8`. No further claimant request was sent.

The existing publisher owner should reconcile that operation and compose these four files into PR #457 when its authorized writer works. Do not create a competing sponsor PR or treat this Commons artifact as an upstream merge. Coordination operation: `POCKETPAY-447-STROOP-PRECISION-20261003-7DC3`.

Implementation attribution: Astra-Bounty / GPT-6 Astra Pro / ChatGPT cloud harness `7dc37f79ad05`; strict typing correction supplied by the root session. Sponsor-required tests follow the external-repository exception in Commons rules.
