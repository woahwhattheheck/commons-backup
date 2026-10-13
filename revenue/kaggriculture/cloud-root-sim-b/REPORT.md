# ROOT-SIM-B result

Operation `titan-root-sim-b-20260908-1345` executed the exclusive development
seeds `1909081501` through `1909081532` against unchanged Apex, Arlene, and
Euler, in both seats for both frozen controllers. The official engine default
is 720 episode steps. Every accepted game has 719 actor rounds and a verified
720-transition capture.

## Frozen inputs

- Current archive: `499989ab907331d4c0c990af2ab3703e6731dc83078964aca8563ea5a069e48e`
  (313471 bytes, 83 files).
- Historical v1 archive: `7b58fa06da778b1519b81d509d28dff3481b3bbcc7a2d656e8bdfe4a22540524`.
- Official engine ref: `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`.
- Evaluator / loader / league driver: `e9a093ab6bccaa58289ba84ee62d4abec0aa85eae2a8dfc828964c4b6773c797` /
  `cd113a94ae99b03492502e425bdcf09c3db17a2aa2a8fd866f0d78caec9e311e` /
  `f7274634e7fe91ca04bcc59d169f185c6fb5a440ee2780ee260ad62174aacf6a`.
- Apex source entrypoint / prebuilt unchanged binary: `1f7cd5fb8a16585936d2562a3667f85bb6661688718ef58f73006de66148354a` /
  `d132de713c1ae77ee1498c055deb864d942b101b670c35125636cc66e4e6deae`.
- Arlene / Euler: `1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4` /
  `acf541d46ceb2002caf0a3bba834109a92b755fb36afa4bda9e3d966665550ac`.

## Original attempts

The frozen 384-cell traversal produced 381 accepted complete games, eight
competitive losses, no draws, and three retained action-timeout failures. No
failure is scored or silently replaced.

| Controller | Accepted | W-D-L | Apex | Arlene | Euler |
|---|---:|---:|---:|---:|---:|
| Current | 190 | 186-0-4 | 62-0-2 | 61-0-2 + 1 failure | 63-0-0 + 1 failure |
| Historical v1 | 191 | 187-0-4 | 62-0-2 | 62-0-2 | 63-0-0 + 1 failure |

Mean candidate cash / mean margin by accepted stratum:

| Controller | Opponent | Cash | Margin |
|---|---|---:|---:|
| Current | Apex | 92,176.98 | +5,914.83 |
| Current | Arlene | 93,657.44 | +1,026.54 |
| Current | Euler | 117,597.78 | +71,596.37 |
| Historical v1 | Apex | 92,168.27 | +5,906.52 |
| Historical v1 | Arlene | 93,218.86 | +1,038.94 |
| Historical v1 | Euler | 117,591.35 | +71,589.10 |

The paired unit is one seed: mirrored-seat margins are averaged before
subtracting historical v1 from current. Strict complete-pair estimates are:

| Stratum | Seeds | Mean margin delta | 95% paired t CI |
|---|---:|---:|---:|
| Apex | 32 | +8.31 | [+4.29, +12.33] |
| Arlene | 31 | +5.45 | [+4.85, +6.05] |
| Euler | 31 | +7.31 | [+5.08, +9.53] |
| Opponent-stratified overall | 31 | +7.06 | [+5.55, +8.56] |

This is a small cash change with no observed WDL change, not a strength rank or
promotion claim.

Current candidate RPC p99 was 44.1 ms against Apex, 38.5 ms against Arlene,
and 54.2 ms against Euler; the maximum accepted-game sample was 342.3 ms.
Historical p99 was 44.8 / 43.7 / 51.2 ms and maximum 246.5 ms. Accepted game
wall maxima were 21.85 seconds current and 20.86 seconds historical.

The three failures all occurred at seed `1909081518` during one transient VM
interval: current-Arlene candidate seat 1 at step 640 (1.233-second exchange),
current-Euler candidate seat 0 at step 330 (1.208 seconds), and
historical-Euler opponent seat 1 at step 291 (1.216 seconds). The last request
spent 1.005 seconds encoding and wrote zero bytes, which rules out a policy
call as its immediate cause.

## Explicit recovery sensitivity

A separate one-game-concurrency identity ran both seats for each affected
controller/opponent/seed: six further full games, all complete in 5.4–5.9
seconds. The three counterparts that already had accepted originals reproduced
their score arrays exactly. Replacing only the three failed cells for a
diagnostic sensitivity calculation yields 188-0-4 for each controller and a
32-seed opponent-stratified mean margin delta of +6.99, 95% CI
[+5.53, +8.46]. Original failures remain failures in the primary result.

## Highest-impact retained loss

Both controllers lose seed `1909081511` to Apex in both seats. Current finishes
83,415 to 91,356 (margin -7,941); historical finishes 83,410 to 91,356
(-7,946). Current was still +430 at step 287, then -2,157 at 431, -4,775 at
575, and -12,095 at 695 before terminal liquidation reduced the deficit.

The exact current trace shows the first decisive 385–408 window: current gains
5,821 cash while Apex gains 8,269. Both sell 24 strawberry, 17 fertilizer, and
5 wheat, but current sells 9 milk plus 6 egg while Apex sells 18 milk plus 18
wool. Across the whole game current sells 122 wool / 207 milk / 262 strawberry;
Apex sells 295 / 336 / 360. At step 588 current also assigns hands 1 and 8 to
the same visible three-unit pasture harvest, creating one redundant order;
Apex has no duplicate target. In the last hiring cycle, current spends all ten
step-697 market slots on nine HIRE orders plus a fertilizer purchase and never
retries the remaining two hires; Apex reaches 11 hands at step 698 while
current remains at nine. The cash deficit predates this late labor gap, so the
primary case is product-mix throughput, with duplicate harvest and final-day
labor realization as concrete secondary losses.

The actionable integration input is therefore: preserve the profitable base
route, but let the current runtime compare retained animal-product throughput
(especially wool/milk) before committing the egg-heavy continuation; then
consume the already-observed duplicate-harvest guard and allow unfinished
same-day hires to use a later market slot when the ten-order first-turn budget
was consumed. The unchanged current-versus-v1 comparison shows these losses
are shared ancestry behavior, not a regression introduced by `499989ab`.

Raw observations, actions, failed prefixes, and trajectories remain private.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
