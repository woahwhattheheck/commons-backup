# TITAN V4 SEALCHAIN — gauntlet evidence admission

SEALCHAIN composes the existing gauntlet trust authorities into one deterministic
admission certificate. It is **not** a runner, evaluator, scheduler, score
threshold, gameplay layer, or promotion rule.

## Authorities composed

The tool pins and invokes the reviewed current-main source bytes for:

- **CHAINLOCK** — candidate / engine / opponent byte provenance and finished
  both-seat result cells;
- **QUIETBOX** — quiet-vs-loaded contention stability;
- **SPECTRUM** — explicit opponent family/source identity and family-balanced
  result accounting;
- **COHORT** — optional paired baseline/candidate completeness + fallback audit
  when a `titan.gauntlet.paired.v1` packet actually exists.

SEALCHAIN computes Git blob ids from the authority source files before importing
them. Any source drift blocks admission until reviewed; a stale `PASS` JSON cannot
silently survive an authority change.

## Cross-oracle binding

One invocation binds the same real candidate, engine, opponent root and raw
quiet/loaded result sets through CHAINLOCK. It then:

1. requires candidate, engine and opponent artifact identities to be identical
   between quiet and loaded panels;
2. adapts only CHAINLOCK-accepted rows into QUIETBOX and invokes QUIETBOX with
   its pinned authority defaults (`100 / 50 / 50`, exact coverage, both seats);
3. requires the SPECTRUM manifest `id` set to equal the actual
   `opponent_artifact` set;
4. binds SPECTRUM `source_id` claims to exact opponent bytes: identical bytes
   cannot claim two identities, and one `source_id` cannot name two different
   byte digests;
5. derives SPECTRUM aggregate outcomes from CHAINLOCK's own outcome parser, not
   caller-supplied aggregate prose;
6. requires SPECTRUM `authoritative_family_weighting=true` (no unresolved or
   missing labels/results);
7. when COHORT input is supplied, requires its candidate SHA, engine SHA and
   opponent SHAs to be within the CHAINLOCK-bound set and requires a clean,
   complete `planned_paired` audit.

The final output is `titan.gauntlet.sealchain.v1` with `admitted=true` only after
all applicable authorities agree.

## Run

From the package directory (or provide `--v4-root` explicitly):

```bash
python -B sealchain.py \
  --candidate /path/to/candidate.py \
  --engine /path/to/pinned-engine \
  --opponent-root /path/to/opponents \
  --quiet-results /path/to/quiet.jsonl \
  --loaded-results /path/to/loaded.jsonl \
  --panel /path/to/titan.gauntlet.panel.v1.json \
  --out /tmp/sealchain.json
```

Add `--cohort-input /path/to/titan.gauntlet.paired.v1.json` only for an actual
baseline/candidate A/B packet. Its absence is recorded as not applicable rather
than fabricated.

## Boundary

SEALCHAIN authenticates and composes the stated local evidence contracts. It
cannot prove that an untrusted external host did not fabricate an engine result
before the raw result reached these tools. It does not authorize production,
default changes, archive replacement, Kaggle submission, or promotion by itself.

SPECTRUM-2 retains schedule construction, Riot retains gauntlet orchestration,
and each named authority retains its own public semantics. This package only
closes the missing *composition* boundary.
