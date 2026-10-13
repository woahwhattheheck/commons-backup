# UNTESTED — shipped but not yet confirmed on-device

**Standard (owner's):** a feature counts as *tested* only once a real on-device run / log shows it
working. Anything below has been written and compile-reasoned only — **no confirming log seen yet**,
so treat it as unverified. Tick a box when a log proves it; move proven ones out of this file.

Each entry says **what to watch for** in the log (`[tag]`) or behavior to confirm it.

> Note: doc-only commits (CLAUDE.md merge, the "agent-driven completion" rule, README updates) aren't
> listed — nothing to test. The compile itself is also unverified (no Android SDK in the dev env);
> a green CI run would at least confirm the whole stack builds.

## Voice / speech
- [ ] **High-accuracy command capture (Android SpeechRecognizer)** — the wake word stays on local Vosk;
      once it fires (or the mic button is tapped) the COMMAND is captured by Android's SpeechRecognizer
      instead of Vosk (which mishears free-form speech). Watch: after "hey agent" (alone) or a mic-button
      tap, `[speech]` *"command via on-device/cloud recognizer"*, and far fewer mishears than Vosk. Vosk
      and SR hand off the mic (Vosk stops, SR runs, Vosk rebuilds) - confirm the wake word still works
      after a command, and that cancel-listening works during a task. Falls back to Vosk capture if SR is
      unavailable. NOTE: the one-breath "hey agent do X" still uses Vosk (can't re-capture mid-utterance).
- [ ] **On-device / cloud speech toggle** — first-run dialog asks on-device (private, default) vs cloud
      (more accurate, off-device); also in Settings → Voice. Watch: on-device mode sets PREFER_OFFLINE
      (nothing leaves the phone); cloud mode allows the network recognizer. KEY: confirm on-device mode
      truly stays offline.

## Action space, memory, adaptive compute & data flywheel (latest batch)
- [ ] **Learned ✗ mistake-memory** (`d4de320`) — an action that did NOTHING on an app+screen is
      remembered and surfaced next time as "✗ TRIED HERE & DID NOTHING"; success clears it. Watch: the
      recall block shows a `✗` line on a screen where an action repeatedly failed before; the agent then
      avoids it; a control that later works (Gemini Send) loses its ✗. `[brain]` memory-pull shows `tried✗`.
- [ ] **Adaptive compute by confidence** (`86b5864`) — the model can emit `"confidence":"low"/"high"`.
      Watch: after a low-confidence step, vision is KEPT next step (no text-only shortcut); on a confident
      "unproductive" step the verifier is SKIPPED. Prompt now invites the field.
- [ ] **Bitmap recycle + lean/shrink JPEG quality** (`ecfbbbf`) — per-encode intermediates recycled;
      lean=512/q50, shrink=384/q40 now actually compress lighter (was hardcoded q60). Watch: no OOM
      regression; lean image path is genuinely smaller.
- [ ] **Data flywheel + fine-tune pipeline** (`fffe2fb`,`505ce08`,`3b48db2`) — each step + task outcome
      captured to a private JSONL; Settings → Training data toggles/exports/clears it; `tools/
      prepare_finetune_data.py` converts an export to SFT data. Watch: count climbs during tasks; export
      writes to Android/data/<pkg>/files; the converter produces chat examples from a real export. See
      `docs/FINE_TUNING.md`.
- [ ] **Action-space picks** (`2d149ab`, plus `assert`/`get_text`) — `long_press` now takes a 0..1
      fraction or a grid `cell` (was pixels-only, truncated fractions → "bad long_press target"); verb
      synonyms (hold/long_tap/tap_text/click_text…) resolve; `ocr`/`reply` fail honestly if nested in a
      `batch` (not "unknown action"); new `clear` (empty a field), `assert` (✓/✗ a step worked), and
      `get_text` (read one element's exact value) verbs. Watch: each new verb executes as documented;
      `assert` returns a ✓/✗ the agent acts on; `long_press` with a fraction works.

## Reliability deep-dive builds
- [ ] **Loop breaker keyed on structure** (`42557f6`) — screenSeen counts by structural sig, so a clock/
      spinner/growing list can't mask a stuck screen. Watch: a stuck screen with changing text now trips the
      breaker; conversations still progress on new replies.
- [ ] **Nudge before motor recovery** (`14822d2`) — first time a screen hits the loop limit, the agent is
      NUDGED (with what it already tried) to self-escape; only the 2nd time does back/home fire. Watch:
      `[loop]` "nudging the agent to self-escape before motor recovery", then a model choice, before any back/home.
- [ ] **Multi-screen oscillation detection** — A→B→A→B (or A→B→C cycle) with no progress now nudges to
      break the path. Watch: `[loop]` "multi-screen oscillation - nudging to break the cycle" on a 2-screen
      ping-pong; never fires while drawing / a reply streams / awaiting a reply / continuous.

## Broad success-rate builds (autonomous)
- [ ] **Change-aware perception** — after an action, the orient surfaces "JUST APPEARED since your last
      action: …" when a few new items show on the SAME screen (a dialog/field/expanded section). Watch:
      after a tap that opens a dialog/menu, the prompt's orient names what appeared; suppressed on a full
      navigation (no overlap) and on dense screens. The universal "did my action work" signal for any task.
- [ ] **Device-tier perception budgets** — a weak setup (useLeanPath: LEAN device, or heavy model on MID
      hardware) gets a smaller element page (14 vs 20), char budget (1000 vs 1300), and node cap (120 vs
      200); the Fold (RICH) is byte-identical. pageSize is single-sourced so badges stay aligned with the
      list. Watch (only on a weak device): smaller pages, still reaches controls via find/next_page.

## Perception deep-dive — verified-bug fixes
- [ ] **Badge ↔ list alignment** — set-of-marks badges now show the element's REAL `[N]` id and are drawn
      ONLY for the listed page (was: all ~60 nodes badged, but text lines only for the current 20 → badges
      20+ had no matching `[N]` line). Watch: on a 30+ element screen, every numbered badge has a matching
      `[N] label` line; no badge points at an unlisted control.
- [ ] **Walk no longer aborts at 60** — `consider()` collects up to `MAX_NODES`=200 so `find`/`click` reach
      controls past 60 (was: tree walk returned at 60 → control 61+ silently unfindable). Rendered list +
      badges stay paged. Watch: on a very long list, `find` reaches a control that's far down.
- [ ] **Exact-text layer shrinks, doesn't vanish** — on a dense screen the read-only TEXT layer is trimmed
      (5 picks/140 chars) and appends "…(more exact text - zoom/peek)" instead of being silently dropped.
      Watch: a dashboard with many controls still shows some exact values + the "more" marker (not blank).
- [ ] **Paging note id space fixed** — reads "showing ids [0]–[19] of 45" (0-based, matches `[N]`/badges),
      not "elements 1–20". Watch: the note's numbers match the actual `[N]` ids.

## Efficiency / latency pass (the Z-Fold "still slow / still crashes" bottleneck)
- [ ] **Vision-skip on text-complete screens** (`590ced2`, CI-green) — the big per-decision win: skip
      the ~15-30s vision ENCODE when the fresh a11y tree already names (almost) every element. Watch:
      `[perf]` *"screen fully labeled (…% of N els) -> text-only this step (saved the vision encode)"* on
      a launcher/menu, and a much smaller `[brain] (…ms)` (logged *"(text)"*-style, not *", vision"*). On
      the Google RESULTS page (many bare image-buttons) vision must STAY (no such line). Confirm the agent
      still picks the right element on the text-only steps.
- [ ] **Adaptive throttle** (`72d28a6`, CI-green) — trade speed for not-crashing, only under live
      pressure. Watch: as free RAM drops / the phone warms, `[throttle]` *"resource pressure (ram=…MB
      thermal=…) -> +Nms between steps (slower, to avoid a crash)"*, and *"pressure cleared -> full speed"*
      when it eases. A healthy run logs nothing (full speed). The task should get SLOWER, not killed.
- [ ] **Lean image + cache under live pressure** (`72d28a6`) — Watch (CRITICAL RAM on any device):
      a 512px image rung and `[model]` *"low RAM at load (…MB free) -> KV cache 3072…"*; back to full once
      pressure eases.
- [ ] **Tier-aware vision-skip bar** (`72d28a6`) — Watch (budget device only): vision skipped at a lower
      labeled bar (LEAN 0.65 / MID 0.75); the Fold stays at 0.85 (unchanged behavior).
- [ ] **Token-light element FORMAT** (`7939c19`) — the per-line role word and `desc:` prefix are gone.
      Watch: element lines now read `[0] "Zoom"` and `[5] id:… @top-center`, NOT `[0] button desc:"Zoom"`;
      a text box still shows `field [editable]`, a switch `[unchecked]`, a tab `tab`. KEY risk to confirm:
      the model still targets controls cleanly (clicks the right `[N]`) under the lighter format.
- [ ] **Element-list dedup (nested clickables)** — compress to "where to interact, not every element": a
      clickable child whose label EXACTLY matches its already-listed clickable ancestor is dropped (the
      row + its inner text that tap the same thing → ONE `[N]`). Conservative on purpose: a LABEL-LESS child
      is KEPT (might be a distinct unlabeled icon), and fields/toggles are always kept. Watch (a feed/list/
      settings screen): `[trace]` `els=` lower than before, no duplicate-looking entries, and the agent still
      reaches every distinct control (nothing made inaccessible).
- [ ] **Resolution ladder (512px under pressure on dense screens)** — Watch: on a DENSE screen that needs
      vision while RAM is TIGHT (or any screen at CRITICAL), the image is the 512px rung; a healthy device
      keeps 640px so badges stay crisp. Confirm the agent still targets via `[N]`/zoom when the badge is small.

## Safety
- [ ] **Self-repo guard** (`20423aa`) — agent backs out of its own GitHub repo page.
      Watch: land it on `github.com/woahwhattheheck/localdeviceagent` → `[act]` *"this is the agent's
      own code repo - off-limits; backed out without touching it"*. Settings shows "Protect the
      agent's own repo" (default on).

## Reliability fixes (each was shipped against a symptom log; need a POST-fix log)
- [ ] **OOM silent-stall fix** (`fa6c620`) — an out-of-memory on a dense vision screen no longer
      vanishes. Watch: where it used to go silent, a line appears — `[brain]` *"out of memory on
      vision THIS step (vision stays on); retrying text-only"* or *"FATAL … fed the loop a wait"* —
      and the task keeps going instead of freezing.
- [ ] **Loading-screen reflex** (`db95c9b`) — no blind tap on a still-loading app. Watch: just after
      opening an app, `[task]` *"screen not ready (root null) - waiting N/6"*, THEN a real decision on
      the loaded screen (not a `tap_grid` on a blank screen → wrong target like "Daily brief").
- [ ] **Drawer end-detection** (`db95c9b`) — no pointless swipe at the end of the app drawer. Watch:
      `[act]` *"reached the end of the app drawer without finding it - use open_app…"*.
- [ ] **Mid-task correction honored** (`aa7f66d`) — a spoken correction breaks the agent's fixation.
      Watch: say e.g. "press send" mid-task → `[cmd] correction: …`, then it actually changes course
      (stale "scroll/read" fixation dropped, correction surfaced at top of feedback).
- [ ] **Send no longer misrouted as Search** (`aa7f66d`) — Gemini's chat field treated as chat, not
      search. Watch: `set_text` into Gemini → `[act]` *"typed it and pressed Send"* (NOT *"pressed
      Search"*), and the message actually leaves the box.
- [ ] **Scroll actually scrolls** (`2bb7354`) — Compose lists (Gemini chat) scroll via swipe
      fallback. Watch: `{"action":"scroll"}` in the Gemini reply → the screen CHANGES (not
      `stalled=true` every time). The owner's headline bug: it never scrolled that chat.
- [ ] **Dense-screen token regression FIXED** (`98e673a`) — the new always-present prompt
      words (identity continuity clause + novelty nudge) pushed the dense launcher OVER 4096
      (`4101 >= 4096`), forcing the overflow→retry path at peak RAM → black-wallpaper OOM. Both are
      now dropped on dense screens (kept on normal ones). Watch: on the launcher, NO
      *"Input token ids are too long … 4101 >= 4096"* / *"screen too dense for vision"* line, and the
      app is NOT killed (wallpaper stays).

## New capabilities / concepts
- [ ] **Structural SendSkill** (`69202a6`) — remembers the exact send control per app, reuses it.
      Watch (indirect — no dedicated log line): after a confirmed send in an app, the NEXT send in
      that same app is reliable/fast (clicks the known button, never the mic). Best confirmed by a
      second send in the same app working first try.
- [ ] **`tap_sequence`** (`69202a6`) — "type" by tapping keys. Watch: only fires if the model chooses
      it (on a set_text-rejecting field) → `[act]` *"tapped N points in a row"*.
- [ ] **Persistent identity** (`27e4144`) — same entity across sessions. Watch (in-prompt, not
      normally logged): identity survives a SLEEP / EMERGENCY STOP and a relaunch (memory intact);
      `tasks` count grows; only a full memory wipe resets it. Confirm by: stop the agent, reopen,
      check memory/skills are still there.
- [ ] **Conversation turn-taking state machine** (`e660038` + `3385db4`) — explicit phase + state
      nudge. Watch: in a chat, `[conv] NONE -> SENT -> GENERATING -> COMPLETE` transitions, and at
      COMPLETE the injection *"Their reply is finished generating - it's your turn."* appears (no
      "you must" forcing).
- [ ] **Memory confidence + decay** (`658c4bc`) — a "✓ worked here" step ages out after 21 days.
      Watch (slow — needs a 3-week-old proven step, or a clock change to test): recall shows *"⚠
      worked before but NOT lately - re-confirm"* instead of ✓, and the on-button ✓ disappears until
      it's re-confirmed.
- [ ] **Action outcome expectations + ENGINE verification** (`60eecde`, `0460889`) — the agent
      attaches `"expect":"…"` (→ `[expect] …`), and now the ENGINE checks it and hands back the result
      instead of the agent re-perceiving: a deterministic tree peek (`verifyExpectation`: text-in-field
      / send-present / sent / keyboard), else a PixelMap visual change check (no fresh image), else the
      agent self-checks. Watch: next-step feedback reads *"ENGINE-CHECKED your expectation … ✓/✗ …"* or
      *"VISUAL CHECK (pixel map): the screen did/didn't change …"*. Only fires if the model uses `expect`.
- [ ] **Failure taxonomy** (`516adaf`) — give-ups get classified. Watch: when a task gives up,
      `[failure] NAVIGATION — …` / `RECOGNITION` / `VISIBILITY` / `TIMING` / `INPUT` / `PERMISSION` /
      `CAPACITY` instead of a flat "stuck".
- [ ] **Novelty detection** (`397cbc2`) — first-time-on-this-screen signal. Watch: the
      FIRST time on a screen, the orient carries "this screen is NEW to you - read the elements before
      acting"; on a return visit the line is gone. (No dedicated `[tag]`; visible in the prompt /
      behavior. Familiar screens stay silent.)
- [ ] **Protected skills (plasticity-stability)** (`fed14d1`) — owner-taught + proven
      skills aren't evicted. Watch (indirect): teach/accumulate >40 skills; an owner-taught one (or a
      task completed ≥3×) survives while old experimental ones drop. Confirm a taught skill persists
      after the cap is exceeded. (No `[tag]`; memory-internal — check the Skills view over time.)
- [ ] **Pin/unpin Skills UI** — the manual half of protected skills. Watch (direct, no log):
      open Agent memory → Skills, tap a skill → the dialog has a **📌 Pin** / **Unpin** button;
      pinned skills show a 📌 in their row and survive the eviction cap. Easiest entry to confirm —
      pure UI, no agent run needed.
- [ ] **Peek-by-default extended** (`76f3d58`) — `peek` verb + foveate-everything when peeking.
      Watch: agent emits `{"action":"peek","region":"…"}` on a busy screen → next snapshot shows only
      that region's controls, a cropped close-up, and NO `DEVICE SCAN`/nav-map block. Busy screens (60+
      controls) now nudge peek-first. (`peek` normalizes to `zoom`.)
- [ ] **Principle-when-stuck retrieval** — when the loop is spinning, surface the single most-
      relevant past lesson as a *candidate*. Watch (non-dense screen, agent stuck — `unproductive ≥ 3`
      or repeating an action): the step feedback gains *"A PAST LESSON that may fit (a candidate, NOT
      an order …): \"<lesson>\""*, and only when a stored lesson really overlaps the objective+screen
      (≥2 keywords). On a healthy run, or a dense screen, the line never appears. Confirm it does NOT
      force the action (agent may still choose otherwise).

## Latest round (token/RAM/multi-device + remaining suggestions)
- [ ] **Token-light elements** (`ea574d5`, format further trimmed in `7939c19`) — `id:` dropped from
      labeled elements (and later the role word + `desc:` too). Watch: a labeled control reads `"Send"`
      (not `button "Send" id:send_button`); label-less controls still keep `id:` + `@position`.
- [ ] **#6 same-screen batching** (`ea574d5`/`829e03c`) — Watch: agent emits `{"action":"batch","steps":[…]}`
      → `[act]` *"batch: N input(s) done"*; a navigating step ends it (*"now LOOK… need a fresh screen"*).
- [ ] **Push through RAM close calls** (`ea574d5`) — Watch: under a one-off memory spike while busy,
      `[mem]` *"riding out the close call (busy); kept the model"* (not freeing); only *"SUSTAINED → freed"*
      if it keeps coming. A black wallpaper that recovers should NOT end the task.
- [ ] **Logs: device header + RAM/size** (`f9de2a9`) — Watch: each task starts with `[device]` *Model /
      Android / ram …MB / tier … / model …[heavy/light] / path LEAN-or-rich*; every `[trace]` shows
      `ram=…MB els=… chars=…` (and `(LOW)` when the OS killer is active).
- [ ] **#9 adaptive lean path** (`f9de2a9`) — Watch (only on a weak device): `[device]` shows `path LEAN`,
      a 512px image, an earlier dense-cutoff. On the Fold it shows `path rich` and behaves exactly as before.
- [ ] **#7 hang watchdog → reorient** (`c29713d`) — Watch: if the loop wedges ~90s with no action and it
      isn't legitimately waiting, `[recover]` *"watchdog: …s with no action… reorienting (wedged)"* and a
      re-plan (NOT a kill). A streaming reply / pending confirm is never interrupted.
- [ ] **#11 stuck → sharp question** (`30a3668`) — Watch: at a no-progress give-up, `[recover]` *"offering
      one sharp question before giving up"*, then the agent either asks a specific question or finishes.
- [ ] **#10 durable corrections** (`30a3668`) — Watch: after a mid-task correction, a lesson appears (*"the
      owner corrected you in <app>: …"*) and is recalled on a later similar task.
- [ ] **#12 reactive capability learning** (`5141d4e`) — Watch: when `set_text` doesn't land in an app, a
      lesson is stored (*"In <app>, set_text often doesn't take - … tap_sequence …"*) and pulled next time.
- [ ] **#6 parameterized playbooks** (`5141d4e`) — Watch (memory view): a saved playbook shows `{text}`/
      `{number}` slots instead of the literal message/number, and the plan injection says to fill them.
- [ ] **#8 multi-pane perception** (`d0d8776`) — Watch (split screen / DeX / unfolded fold): the element
      list shows *"— pane @… —"* headers for each app window; a click on either pane works (global ids).
      Single-app screens are unchanged.
- [ ] **#1 OCR fallback** (`5f587ee`, CI-green incl. the ML Kit dep) — Watch (an a11y-blind screen:
      a game/Flutter app/webview with no tappable elements): `[ocr]` *"read N text regions on a blind
      screen"* and a *"READABLE TEXT (OCR …)"* block of labels@fractions the agent can `tap_xy`. Normal
      tree screens never trigger it.
- [ ] **Model-fitness guard** (`0bb7eb9`) — Watch (a heavy ~E4B model on a <4.5GB phone): the home screen
      shows *"⚠ This model is too large for this phone's RAM…"* and task start logs `[warn] …`. Never fires
      on the Fold or a light model. (Pure UI/log — easy to confirm without an agent run on a weak device.)

## Big-picture batch (owner-approved suggestions 1-13,15)
- [ ] **Deep-link primitives** (`ed21508`) — `sms`/`dial`/`set_alarm`/`navigate`/`web` as agent-chosen
      shortcuts. Watch: agent emits e.g. `{"action":"sms","number":"...","text":"..."}` → `[act]`
      *"opened Messages with a draft to …"*; none auto-send; `web` to ChatGPT/own-repo is refused.
      Doc is dropped on dense screens (token budget).
- [ ] **Structural screen signature** (`ff7b83a`) — `triedHere` negative memory keyed on the id-skeleton,
      not full text. Watch (indirect): on a screen with changing text (a chat, a clock), the "already
      tried X here" steer persists across the change instead of resetting.
- [ ] **Graceful image-shrink before blind** (`88c52e9`) — #9/#17. Watch: where a dense screen used to
      go straight to text-only/OOM, a `[brain]` *"(shrunk vision)"* line appears and the agent keeps
      SEEING; next step is back to the full overview. The answer to "full grabs crash E4B" without
      dropping the default overview.
- [ ] **Action validate (no-verb → wait)** (`88c52e9`) — #2 stand-in. Watch: a pure-prose model reply
      becomes a `wait` with the prose as `say`, not a hard "could not parse" FAILED. (True token-level
      constrained decoding is a README TODO — the LiteRT-LM build exposes no grammar hook.)
- [ ] **Confidence gate** (`3e15e4f`) — #11. Watch: agent adds `"confidence":"low"` to a `send`/PRECISION
      `click` → `[act]` *"low-confidence consequential action - looking closer before committing"*, and the
      next feedback says to peek the target first. Fires at most once per step; zero cost when unflagged.
- [ ] **Failure class → behavior** (`3e15e4f`) — #13. Watch: after a give-up, a lesson appears keyed to
      the objective (NAVIGATION → "prefer open_app/deep-links", etc.), and the NEXT similar task's `[plan]`
      reflects it. CAPACITY/PERMISSION write nothing.
- [ ] **Resumable tasks + UI declutter** (`2c5c56e`) — #10. Watch: kill the app mid-task (OOM) → on
      relaunch the home screen shows *Interrupted: "…"* with Resume/Dismiss. A clean finish shows nothing.
      Also: Debug log is now top-level beside Open chat; the model block collapses to "Brain ready ✓" +
      "Model setup" once a model is imported.
- [ ] **Post-task fast-path reflection** (`951862b`) — #12. Watch: complete a texting/calling task the
      slow GUI way → `[learn]` *"fast-path reflection: noted a deep-link shortcut for next time"*, and a
      lesson suggesting `sms`/`dial` next time.
- [ ] **In-task app-path world model** (`951862b`) — #3. Watch: a task that crosses apps → orient carries
      *"PATH THIS TASK: gemini → messages → gemini"* (only when it actually changed apps; dropped on dense).
- [ ] **Fast head (helper-routed actions)** (`ff621ec`) — #1, DORMANT unless the helper model is enabled
      (RAM-safe default). Watch (helper ON, familiar non-visual screen): `[mini]` *"(fast action) …"* and a
      much faster step; novel/visual screens still log a `[brain]` vision decision. With the helper OFF
      (default) this never fires — confirm the default config is unchanged.
- Already implemented before this batch (no new test needed, just confirm): **#8** semantic a11y actions
      (click/set_text/scroll/long_press use node actions), **#5** `find`/linked `set_text`→`send` macros,
      **#15** "Show me — record my steps" demonstration teaching (Train screen).

## Earlier shipped
- [ ] **Plan marks SURE vs EXPLORE steps** (`a7f2c5a`) — the plan now tags each step `[SURE]`
      (a guaranteed action) or `[EXPLORE]` (screen unknown → look + adapt), so it stops pretending to
      know screens it hasn't seen. Watch: the `[plan]` log shows `1. [EXPLORE] …` / `2. [SURE] …`
      tags, and the agent treats explore steps as look-first. (Also: the objective is now capped to
      500 chars on dense screens — keeps the plan markers from re-tightening the 4096 budget.)

## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../referral-intake-completeness.html)
- [$199 repair diagnostic](../repair-booking-preflight.html)
- [$199 plant diagnostic](../plant-downtime-handoff.html)

