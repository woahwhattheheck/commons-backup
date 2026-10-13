# TITAN V5 animal cadence candidate

Status: **default OFF / evaluation only**. This package is additive to canonical V5 and does not change `main.py`, `titan_runtime.py`, `TITAN-CONFIG.json`, the release archive, or Kaggle submission bytes.

Promotion status: **BLOCKED pending matched current-line simulation evidence.** `certificate_builder.py` provides one source-pinned certificate authority, but only for the narrow completed day-close/reset loop described below. The transform and builder remain uninstalled production candidates.

## Reachable-opportunity probe

`reachable_probe.py` is an evaluation-only wrapper around the exact current
entrypoint. It records only returned FEED/CARE actions, their public animal
prestate, the acting inventory, runtime completion status, parent-call count,
route identity, and an action digest; it returns the canonical action object
unchanged. `summarize_reachable_probe.py` reduces those private observations to
non-observational counts, including whether every otherwise eligible FEED has a
later same-animal CARE in the same day. Raw observations are not published.

The reserved seed `2611124301` was run through the official engine against the
unchanged pinned Arlene opponent in both seats from `main@a7dcbb9e`. Both games
completed all 719 decisions and the wrapper made exactly one completed parent
call per decision. Across the two symmetric current-controller traces, 14 FEEDs
passed the candidate's local public-state guard; all 14 had a later same-animal
CARE in the same day. The care-neutral reachable count was zero. The reduced
receipt is `reachable-probe-2611124301.json`.

This is a negative opportunity result, not strength evidence. Replacing any of
those FEEDs would discard a CARE bonus, so the probe does not relax the
candidate, install a runtime call, enable a default, or justify another paired
panel. A future source change must first produce a nonzero care-neutral
opportunity under this same observational boundary.

## Pinned engine theorem

The preserved engine is `reference/engine/kaggriculture.py` at source blob `3c202c7ee921da239356789e266b694635103fc4`.

The source-real behavior is:

- an animal survives one unfed end-of-day and escapes only when `consecutive_unfed >= 2`;
- scheduled base animal production is awarded even on that first unfed day;
- feeding gates consumption of a pending CARE bonus, so CARE value must not be discarded;
- every surviving animal sets `fertilizer_available = True` at every end-of-day, not every third day;
- duplicate same-tile FEED actions spend at most one WHEAT because the first successful FEED sets `fed_today`;
- end-of-day drops carried inventory into the shed, removes all hands, resets the main farmer, and replaces per-worker inventories with one empty main-farmer inventory;
- `FERTILIZE` consumes one fertilizer and extends `fertilized_until_day`; it does **not** directly increment `yield_units`.

The last point is an explicit negative predecessor for the rejected “infinite fertilizer yield” hypothesis.

## Candidate

`alternate_feed.py::apply_alternate_feed(observation, selected, next_feed_certificate=..., route_identity=..., turns_per_day=...)` is a pure selected-action transform. It replaces a selected `FEED` with `PASS` only when the animal tile is covered by a machine-checkable next-day FEED certificate, the actor actually carries WHEAT, the animal is on the exact zero-strike leg (`consecutive_unfed == 0`), no current or pending CARE value can be lost, and no same-tile selected CARE exists. Once the public state reports one unfed day, the next FEED is retained.

The certificate is bound to the exact public `observation_step`, exact positive plain-int `turns_per_day`, route id, route-source Git blob, and current route-tail SHA256, and gives an exact future FEED step for each certified animal tile. The transform derives the next calendar day's inclusive step window from `(observation_step, turns_per_day)` and rejects both later-same-day FEEDs (which would save no net WHEAT) and FEEDs after the next EOD (which are too late to prevent the second starvation refresh). The caller separately supplies the independently derived current `route_identity` and day length; all provenance must match the certificate.

Route switch, checkpoint/rejoin, reset, source drift, tail drift, clock advance, or calendar changes therefore require a newly minted certificate. Empty, malformed, stale, mismatched, same-day, or too-late evidence fails closed and leaves the selected action untouched.

The transform preserves market rows, other unit actions, action-slot topology, and both inputs. Its report distinguishes actor actions suppressed from actual WHEAT avoided: multiple FEED actions on one animal tile may all be suppressed to skip that day, but count as only one saved WHEAT because that is the pinned engine's baseline spend.

## Source-pinned day-close certificate authority

`certificate_builder.py::build_next_feed_certificate(..., completed=True)` admits only the mechanically closed reset case from a fully completed runtime action. Deadline/fallback actions are rejected before source loading or controller access.

The authority pins the full official engine, extracted mechanics, Arlene producer, landed operating-stock theorem, canonical cadence candidate, canonical entrypoint and runtime, canonical config, FrozenSelected, the installed EXEC-PACE helper, seed funding/budget, redundant-hire, SpatialTempo, crop release, early capital, market-pressure/sell-priority, and town-procurement sources by exact Git blob. Source drift in any of those files invalidates the authority instead of inheriting the theorem implicitly.

The supplied feature profile must exactly match the current production composition: frozen consumer; seed/funding/committed/redundant-hire/market-pressure/operating-stock/idle-fertilizer/crop-release/early-capital/town-procurement enabled; terminal history/route, fourth quadrant, spatial pathing/tempo, committed-seed-retry, and `exec_pace` disabled. The caller must include the entrypoint-owned `town_procurement` flag rather than passing only a partial feature subset.

That exact custody matters because current V5 has several late wrappers. Under the pinned profile, seed/funding, pressure, early-capital, and town-procurement operate on market rows; generic spatial/tempo rewriting is disabled; idle fertilizer owns literal PASS space; weed continuation stops before FEED; crop release's unit substitution is source-bound PLANT-WHEAT to PLANT-CARROT. EXEC-PACE is installed but exact-bool disabled by the authenticated current profile; its helper source is nevertheless pinned so the source closure matches the packaged current runtime. Redundant-hire is the exceptional enabled wrapper that may change worker topology and mutate future route rows. The authority therefore rejects any raw next-day route containing a HIRE before certifying the window.

The authority also binds canonical public clock semantics. After exact `turnsPerDay=24` resolution, redundant `day`/`hour` must either both be absent or both be plain bounded integers satisfying `step == day*turnsPerDay + hour`; partial, malformed, or contradictory clocks fail closed before dynamic module loading.

For one deterministic current animal tile at a time, the builder:

- requires the caller to attest a fully completed runtime action, never a deadline fallback;
- authenticates the live controller route id against pinned Arlene and requires its completed prefix to retain pinned-source lineage;
- hashes the exact live route tail with canonical JSON and binds that SHA256 into `route_identity`;
- rejects a next-day window crossing any pinned producer decision checkpoint;
- rejects any next-day raw HIRE surface under the enabled redundant-hire wrapper;
- asks the canonical #13331 transform to produce a hypothetical current FEED-to-PASS postimage, then computes the exact completed current unit stage including aggregate PLANT atomicity;
- reuses the landed operating-stock `_feed_window` and room bounds with no future sale or requested-purchase credit;
- proves the saved carried WHEAT cannot be discarded by end-of-day capacity;
- requires the main farmer to PICKUP protected WHEAT on the **first unit stage of the next day** at shed access; and
- requires that same carried input to reach a later FEED on the exact skipped animal tile before next day close.

The first-next-day pickup is the key market-ordering boundary. Unit actions run before market processing, so once the saved EOD WHEAT is recovered into the main farmer's inventory on that first next-day unit stage, the pinned market-row transforms cannot consume that carried unit. The landed feed-window theorem separately rejects uncertified transfers, uncovered feeds, intervening route WHEAT sales before protected pickup, unresolved animal replacement, and route checkpoints. The explicit HIRE rejection removes the current wrapper surface that could otherwise change next-day worker topology outside that raw-route model.

This is deliberately narrower than “feed every other day.” It does not certify mid-day skips, late next-day pickups, next-day HIRE surfaces, unpinned route mutations, alternate feature profiles, or deadline/fallback execution. Those cases stay unchanged.

## Focused checks

From `revenue/kaggriculture/cloud-execution-lab`:

```bash
python -B candidates/v5/animal-cadence/test_alternate_feed.py
python -O -B candidates/v5/animal-cadence/test_alternate_feed.py
python -B candidates/v5/animal-cadence/test_certificate_builder.py
python -O -B candidates/v5/animal-cadence/test_certificate_builder.py
python -B candidates/v5/animal-cadence/test_reachable_probe.py
python -O -B candidates/v5/animal-cadence/test_reachable_probe.py
python -m py_compile \
  candidates/v5/animal-cadence/alternate_feed.py \
  candidates/v5/animal-cadence/certificate_builder.py \
  candidates/v5/animal-cadence/reachable_probe.py \
  candidates/v5/animal-cadence/summarize_reachable_probe.py \
  candidates/v5/animal-cadence/test_certificate_builder.py
```

The candidate tests call preserved engine predecessors for starvation, base production, CARE loss, duplicate-FEED spend, fertilizer refresh, and the FERTILIZE negative theorem. The authority suite adds full wrapper/source custody, runtime-completion custody, public-clock identity, route-tail binding, next-day HIRE rejection, first-next-day pickup, checkpoint crossing, feature-profile drift (including exact-bool `exec_pace=False`), reset capacity, source-lineage drift, and canonical candidate round-trip cases.

## Evaluation handoff

The merged donor research artifact `candidates/v5/research/animal-feed-cadence/` pins the official engine and Arlene producer and emits a route census. The certificate authority converts the subset of **completed** live day-close observations satisfying the physical reset and exact current-wrapper theorem into certificates consumable by `alternate_feed.py`.

Matched evaluation should run current canonical V5 twice on identical opponent/seed/seat cells: unchanged baseline versus baseline plus the authority and candidate wrapper. The evaluation adapter must pass the exact current entrypoint feature profile (including `town_procurement` and `exec_pace=False`) and `completed=True` only when the canonical runtime reports a fully completed action. Record builder source pins, route identity/tail hash, authority engagement count, candidate engagement count, actor FEED actions suppressed, unique-tile WHEAT saved, paired own-score and margin deltas, loss flips/new losses, animal escapes, CARE-bonus divergence, and every authority decline reason. Promotion remains blocked until that matched evidence is current-line green; this package itself makes no activation claim.
