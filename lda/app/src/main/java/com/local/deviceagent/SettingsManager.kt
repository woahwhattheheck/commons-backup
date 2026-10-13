package com.local.deviceagent

import android.content.Context
import android.content.SharedPreferences

/**
 * DEFAULT-ON POSTURE (owner, 2026-07-08 — "have all of our novel features on by default, every one"). Every NOVEL
 * capability flag below (the operator/σ engine, continuous engine/stream, operator stacking/fold-verify/adaptive-
 * decode/vision-skip, startup calibration, self-calibrate, imitation, agent-language/operator-binding/light-operator,
 * passive/ambient learning, debug capture, AND the autonomous self-modification family self_improve / self_model_edit
 * / self_evolve / self_grow) now defaults to ON — the owner explicitly reversed his earlier "default OFF => byte-
 * identical" and "do NOT default self_evolve on" (§16) / "no passive monitoring by default" (§14) rules FOR HIS OWN
 * DEDICATED DEVICE, accepting the risk. Where a per-flag KDoc below still reads "Default OFF / byte-identical / A/B'd
 * before a flip," that clause is SUPERSEDED by this note — the flag ships ON; each is still an owner TOGGLE so any one
 * can be turned back off. The RAM-operator (INV-61) + the growth junk-bloat guard (INV-60) are the counterweights that
 * keep "everything on + a growing model" inside the §8 ceiling.
 * The former app/action restriction preferences were removed; capability access is not conditioned on a
 * second settings allowlist. User Stop controls and the device battery/thermal floor remain independent.
 */
class SettingsManager(context: Context) {
    private val prefs: SharedPreferences =
        context.getSharedPreferences("agent_settings", Context.MODE_PRIVATE)

    // Voice mode: "minimal" (brief speech, default), "explanation" (narrate the
    // reasoning aloud), or "silent" (no speech at all).
    fun getVoiceMode(): String = prefs.getString("voice_mode", "minimal") ?: "minimal"

    fun setVoiceMode(mode: String) {
        prefs.edit().putString("voice_mode", mode).apply()
    }

    fun isSilent(): Boolean = getVoiceMode() == "silent"

    /** The brain narrates its reasoning only in explanation mode. */
    fun isNarrationEnabled(): Boolean = getVoiceMode() == "explanation"

    fun getTriggerWord(): String =
        prefs.getString("trigger_word", "hey agent") ?: "hey agent"

    fun setTriggerWord(word: String) {
        prefs.edit().putString("trigger_word", word).apply()
    }

    /** Absolute path to the imported on-device LLM model file, or null if unset. */
    fun getModelPath(): String? = prefs.getString("model_path", null)

    fun setModelPath(path: String?) {
        prefs.edit().putString("model_path", path).apply()
    }

    // The optional "helper"/mini/sub-model was REMOVED (07-10) — single-model only (§16). No second model,
    // no mini_model_enabled / mini_model_path. Everything runs on the one main model (getModelPath()).

    /** Owner-gated SELF-MODEL-UPDATE (INV-45/46): when ON, the agent may PROBE a candidate model and
     *  SUBMIT a win for the owner to grade — but installing a new brain is always an owner action, never
     *  the agent's, and is never reachable from a model decision or on-screen data (the exploit gate).
     *  OFF by default. Enabling it stashes a pristine baseline of the current model so any change is
     *  instantly reversible ("just swap it out"). This never lets the MODEL rewrite its own weights at
     *  inference; it is the deterministic HOST persisting a whole-file swap. Default ON (owner reversal). */
    fun isSelfModelEditEnabled(): Boolean = prefs.getBoolean("self_model_edit", true)
    fun setSelfModelEditEnabled(on: Boolean) {
        prefs.edit().putBoolean("self_model_edit", on).apply()
    }

    /** SELF-IMPROVEMENT: the agent durably changes its OWN behaviour by saving rules to its memory (via LEARN,
     *  applied to future tasks and reviewable/undoable in Memory). Default ON (owner reversal — the agent improves
     *  itself autonomously, it does NOT need to ask permission). The ONE honesty boundary that stays either way: it
     *  NEVER edits the app's compiled CODE and must never falsely claim it did; this unlocks memory/rule self-edits. */
    fun isSelfImprovementAllowed(): Boolean = prefs.getBoolean("self_improve", true)
    fun setSelfImprovementAllowed(on: Boolean) {
        prefs.edit().putBoolean("self_improve", on).apply()
    }

    /** MIC MASTER SWITCH (owner: "turn the agent's mic off so I can run tasks and talk to people"). ON
     *  by default. While OFF the agent's ears are fully closed - no wake word, no shouted-stop - so
     *  nothing trips by talking near the phone; the floating STOP button + notification Stop stay live. */
    fun isMicEnabled(): Boolean = prefs.getBoolean("mic_enabled", true)
    fun setMicEnabled(on: Boolean) {
        prefs.edit().putBoolean("mic_enabled", on).apply()
    }

    /** Verifier-first: take a fast text-only second opinion on each consequential action. Its
     *  output is CONSTRAINED to OK / retarget-to-element / back (it can't free-form rewrite the
     *  action), so it can fix a wrong target without ever mangling a good action or dropping
     *  text. Default ON; toggle off to compare. */
    fun isVerifierEnabled(): Boolean = prefs.getBoolean("verifier_enabled", true)

    fun setVerifierEnabled(on: Boolean) {
        prefs.edit().putBoolean("verifier_enabled", on).apply()
    }

    /** EVIDENCE MODE (the owner's refuse-to-hallucinate contract, made STANDING): when ON, the EVIDENCE
     *  operator's output standard is enforced on EVERY content-asserting action (type/record/save/ask) - a
     *  grounded check that the specific value is on-screen/read/carried, not invented, kicking back if it is.
     *  When OFF (default), EVIDENCE is a normal model-SELECTED operator (still available every step). The check runs
     *  on the ONE main model (single-model, 07-10) + the zero-inference exactness oracle. Toggle to A/B. */
    fun isEvidenceModeEnabled(): Boolean = prefs.getBoolean("evidence_mode", true)

    fun setEvidenceModeEnabled(on: Boolean) {
        prefs.edit().putBoolean("evidence_mode", on).apply()
    }

    /** EXACT-COMPUTE GROUNDING (docs/PFC_LDA_OPENINGS.md, the pfc×LDA fusion): the compute-first arm of the
     *  evidence gate. When ON, before an EVIDENCE-family action asserts an UNGROUNDED numeric value, the value
     *  is deterministically recomputed on the byte-exact pfc mul32/add32 gate-circuit (Sandbox.compute); on a
     *  DEFINITE disagreement the step is kicked back for the model to re-author — it NEVER rewrites the value
     *  and NEVER fires an action (bounce-only, exactly the shipped evidence-kickback recipe). Any ambiguity
     *  (no clean 2-operand expr, non-integer, out of range) leaves the existing verifyEvidence path unchanged.
     *  Default OFF — with it off the code is skipped and device behavior is byte-identical; it can only ADD a
     *  grounding bounce, never remove a check. Toggle to A/B. */
    fun isExactComputeGroundEnabled(): Boolean = prefs.getBoolean("exact_compute_ground", false)

    fun setExactComputeGroundEnabled(on: Boolean) {
        prefs.edit().putBoolean("exact_compute_ground", on).apply()
    }

    /** AGENT LANGUAGE (docs/AGENT_LANGUAGE.md): render perception as compact ≤2-token/item handles and
     *  accept compact action codes, taught by the operators. Default OFF — it is measured against the
     *  labeled baseline on the gauntlet (tokens DOWN / agent-driven success SAME-or-UP) before any default
     *  flip; with it off the build is byte-identical (the decoder only ADDS code-acceptance). Toggle to A/B. */
    fun isAgentLanguageEnabled(): Boolean = prefs.getBoolean("agent_language", true)

    fun setAgentLanguageEnabled(on: Boolean) {
        prefs.edit().putBoolean("agent_language", on).apply()
    }

    /** OPERATOR BINDING (docs/OPERATOR_PRINCIPLE.md §1, owner 07-07): inject each chosen operator's FORMAL
     *  binding rule as a CONSTRAINT (in-context rule binding) instead of leaning on the soft "how to think"
     *  clause the model ignored (the 42-step loop). Default OFF — formal/format binding on a small Gemma is
     *  tier-gate + A/B (concept settled, format measured); off => byte-identical soft path. Toggle to A/B. */
    fun isOperatorBindingEnabled(): Boolean = prefs.getBoolean("operator_binding", true)

    fun setOperatorBindingEnabled(on: Boolean) {
        prefs.edit().putBoolean("operator_binding", on).apply()
    }

    // ---- OPTIMIZE flags (docs/OPERATIONAL_STATES.md §2.5 composition applied; all default OFF = byte-
    // identical). Each pushes an edge of the operational-states work and is A/B'd on the meters we already
    // built ([iat]/[promptsize]/Gauntlet) before any default flips — nothing flips until a log proves it.

    /** OPERATOR STACKING (OPT-2, composition lever): when two+ operators are BOTH strongly relevant, inject
     *  the top-K COMPATIBLE ones' formal rules under ONE constraint header (σ₁‖σ₂ → A_{σ₁}∩A_{σ₂}, the
     *  constraint-space reading of observed config-vector arithmetic) instead of collapsing to one. Only
     *  stacks operators that don't fight (same composite / non-conflicting). Rides binding mode (rules exist
     *  only there). Default OFF => one rule as today. A SUCCESS-RATE bet, measured on [promptsize]+Gauntlet. */
    // DEFAULT OFF (07-12 on-device A/B, owner-confirmed "FASTER"): stacking concatenated 2-3 operators' FULL rules into
    // one fat spec (op=1062 tok) — the operator STOPPED selectively activating (slower + empty decodes). Turning it OFF
    // dropped op 1062→390, the prompt under the 4096 cache, and the agent produced REAL actions instead of empty. Aligns
    // the runtime with this flag's Settings caption (already "off by default"). Operators DISPATCH one sharp σ, never PILE.
    fun isOperatorStackingEnabled(): Boolean = prefs.getBoolean("operator_stacking", false)

    fun setOperatorStackingEnabled(on: Boolean) {
        prefs.edit().putBoolean("operator_stacking", on).apply()
    }

    /** THE OBJECTIVE LOCK (owner 07-12: "every prompt and all context warps our operational states — the initial prompt
     *  must be locked in somewhere so it can't be diluted"). The owner's VERBATIM task prompt is injected as an
     *  untruncatable primacy block on every decode once the working objective has drifted from it (the planner's rewrite
     *  wins at resolvedHead, the rolling plan wraps it, answers/corrections append to it, and five call sites truncate it
     *  five different ways — measured 07-12). Default ON (novel mechanism, §0A SOP). */
    fun isObjectiveLockEnabled(): Boolean = prefs.getBoolean("objective_lock", true)

    /** THE EXEMPLAR BANK (owner 07-12, the pattern hypothesis: "the model speaks patterns, not english"). The agent's
     *  own proven (screen → action) wins re-injected as few-shot DEMONSTRATIONS — matched by screen class, placed
     *  immediately before the live screen so the pattern's continuation IS the next action. Default ON (§0A SOP);
     *  dropped on dense screens so it can never push the prompt over the cache. */
    fun isExemplarBankEnabled(): Boolean = prefs.getBoolean("exemplar_bank", true)

    /** FOLD VERIFY (OPT-1, composition applied to latency): on a risky/consequential step, STACK VERIFY's
     *  formal rule onto the elected operator on the ONE decide pass (in-pass self-verification) INSTEAD of
     *  firing the separate text-only verifyAction second pass — removing one real off-step main-model pass
     *  (single-model, 07-10 — every off-step pass runs on the ONE model). Rides operator stacking. Default OFF => the separate
     *  verify pass runs as today. Honest A/B: in-pass self-verify may lose the independent-look benefit —
     *  measure verify-pass count DOWN on [iat] AND agent-driven success HELD before any default flip. */
    fun isFoldVerifyEnabled(): Boolean = prefs.getBoolean("fold_verify", true)

    fun setFoldVerifyEnabled(on: Boolean) {
        prefs.edit().putBoolean("fold_verify", on).apply()
    }

    /** ADAPTIVE DECODE (OPT-3, the operational state sets the compute): use the σ's confidence/novelty
     *  (proven route / high-confidence vs EXPLORE / stalled) to set the decode outCap on the decide pass —
     *  a proven, predictable action gets a shorter cap; an exploratory/stalled one gets the full cap.
     *  Streaming action-extraction already stops at the first complete action, so this only trims the
     *  worst-case tail. Default OFF => full cap as today. Measured on [iat] decide latency, success held. */
    fun isAdaptiveDecodeEnabled(): Boolean = prefs.getBoolean("adaptive_decode", true)

    fun setAdaptiveDecodeEnabled(on: Boolean) {
        prefs.edit().putBoolean("adaptive_decode", on).apply()
    }

    /** VISION-SKIP ON PROVEN ROUTE (OPT-4, §13-sensitive candidate): also skip the vision encode when a
     *  PROVEN world-model route exists out of a screen whose structural (a11y) signature MATCHES the known
     *  one and the action is non-consequential — act on the a11y text + route memory (the captured-compute
     *  offload). BIG latency win but §13-sensitive ("never fire against an unconfirmed screen"), so gated
     *  hard and measured heavily (a wrong skip is a real regression). Default OFF. Build/enable last. */
    fun isVisionSkipProvenEnabled(): Boolean = prefs.getBoolean("vision_skip_proven", true)

    fun setVisionSkipProvenEnabled(on: Boolean) {
        prefs.edit().putBoolean("vision_skip_proven", on).apply()
    }

    /** STARTUP CALIBRATION (the owner's idea): at app start, behind a loading screen, seed the model's
     *  OPERATIONAL STATE up front — probe the device and set the compute knobs to it, ask the owner the few
     *  things the agent decides it needs to function, and compose a starting operating posture — so the model
     *  boots CALIBRATED to this owner/device (loading capability, not cosmetic priming). Operators serve the
     *  same purpose as training but cost nothing to insert and the model sets them itself. Default OFF =>
     *  cold boot as today. */
    fun isStartupCalibrationEnabled(): Boolean = prefs.getBoolean("startup_calibration", true)

    fun setStartupCalibrationEnabled(on: Boolean) {
        prefs.edit().putBoolean("startup_calibration", on).apply()
    }

    /** SELF-CALIBRATE (legs 2+4 — on-device operator self-tuning): the model re-authors / re-sets its OWN
     *  operators during use and the loop keeps the ones that PROVE OUT and are EXACT. Operators are exact
     *  restrictions (not fuzzy training hopes), so the loop scores them on BOTH agent-driven success (M) AND
     *  their ESCAPE RATE (how often the operator's restriction was violated) — promoting the proven-exact ones,
     *  pruning the leaky ones, re-authoring a sharper one when struggling, and surfacing proven-exact operators
     *  as owner-approved weight-distillation candidates (the operator library is the source of truth; weights
     *  are a cache of proven operators). On-device, gradient-free. Default OFF => today's W2 (author-once →
     *  credit → promote-if-proven), byte-identical. */
    fun isSelfCalibrateEnabled(): Boolean = prefs.getBoolean("self_calibrate", true)

    fun setSelfCalibrateEnabled(on: Boolean) {
        prefs.edit().putBoolean("self_calibrate", on).apply()
    }

    /** THE CONTINUOUS ENGINE (owner: "build the continuous engine, that's the ultimate") — the MASTER switch that
     *  runs the two continuous-self-improvement halves as ONE loop: the mid-session σ engine (`session_sigma` —
     *  the operating posture accumulates + leads each decode) AND on-device operator self-tuning (`self_calibrate`
     *  — score operators on M + exactness, promote proven-exact, prune leaky, re-author sharper on a fresh stall).
     *  Fused, they close a self-referential loop: each turn the engine scores what it just did, evolves
     *  σ from what's PROVEN this session, and the model reads its own live specialization back in σ next turn — the
     *  model continuously training itself via operators, in-session, gradient-free, free to insert. On => both
     *  halves on (the sub-flags still work alone for granular A/B). SINGLE-MODEL (07-10): σ evolution, operator
     *  selection/credit/promote/prune, and re-authoring all run on the ONE main model — the sub-model was removed
     *  (§16). Default OFF => today's per-flag behavior, byte-identical. */
    fun isContinuousEngineEnabled(): Boolean = prefs.getBoolean("continuous_engine", true)

    fun setContinuousEngineEnabled(on: Boolean) {
        prefs.edit().putBoolean("continuous_engine", on).apply()
    }

    /** CONTINUOUS STREAM (INV-57 — escape the turn system): a PERSISTENT live conversation held ACROSS a task's
     *  turns, so the model's KV / effective state stays warm and EVOLVES instead of being torn down + re-prefilled
     *  each turn. The Kotlin core is overflow-aware (it recycles to a fresh session before the accumulating
     *  context would exceed the KV cache, read from the runtime's real getTokenCount); early-fire uses the
     *  runtime's real cancelProcess() (interrupt without close). The one pending native piece is KV rollback
     *  after cancel — roll state back to the warm σ prefix so it persists without recycling. Default OFF => the per-turn
     *  throwaway-conversation path, byte-identical. §8: the warm KV is extra RAM, so it's released under memory
     *  pressure and at task end; keep default OFF on RAM-tight devices. UNTESTED on-device. */
    fun isContinuousStreamEnabled(): Boolean = prefs.getBoolean("continuous_stream", true)

    fun setContinuousStreamEnabled(on: Boolean) {
        prefs.edit().putBoolean("continuous_stream", on).apply()
    }

    /** AGENT DEVICE MODE (owner: "press it, he gets full perms, I don't click each one") — for a dedicated device
     *  handed to the agent. When on, the setup screen offers ONE guided "grant everything" flow that requests the
     *  runtime perms together and walks straight to each system-toggle perm (Accessibility / overlay / battery /
     *  notifications) in sequence, so the owner grants them all without hunting each one. Default OFF; purely a
     *  setup convenience — it changes NO agent behavior and grants nothing on its own (every system perm still
     *  requires the owner's tap in system Settings). */
    fun isAgentDeviceMode(): Boolean = prefs.getBoolean("agent_device_mode", true)

    fun setAgentDeviceMode(on: Boolean) {
        prefs.edit().putBoolean("agent_device_mode", on).apply()
    }

    /** DEBUG MODE (owner's dedicated debug device — "so we can always have data"). When on, the agent captures the
     *  FULL per-step detail — the exact prompt, the raw model output, timing, and the per-step screenshot — into a
     *  durable, adb-pullable bundle (`DebugCapture`), far richer than the terse `[tag]` log. Storage-heavy, so it's
     *  for the dedicated device only; default OFF => no rich capture, byte-identical. Nothing leaves the device;
     *  the owner pulls/shares the bundle. (The autonomous self-improve run rides on this + `self_calibrate`.) */
    fun isDebugModeEnabled(): Boolean = prefs.getBoolean("debug_mode", true)

    fun setDebugModeEnabled(on: Boolean) {
        prefs.edit().putBoolean("debug_mode", on).apply()
    }

    /** SELF-EVOLVE (owner: "the model should upgrade itself DURING operation — permanent, no download, no
     *  permission"). When on, the agent writes what it learns (operators / memories / grounded facts) into its OWN
     *  model file autonomously and permanently, evolving its weights as it runs — the runtime loads a whole
     *  `.litertlm`, so a permanent change is the host writing a modified model file + reloading. OWNER'S CHOSEN
     *  POSTURE: FULLY RAW (no keep-if-better gate blocking edits) with REGULAR BACKUPS as the recovery net — a
     *  keep-if-better probe still runs as telemetry only. Rolling snapshots + a brick-guard (auto-restore if the
     *  model won't load) keep it recoverable. Default ON (owner reversal — §16, "it's my app, I accept that risk"):
     *  the model file evolves autonomously in idle gaps. HIGH-RISK by design (screen-direct permanent writes) —
     *  admissible only because the §3 gates + kill switches + snapshots + brick-guard hold, on the dedicated device. */
    fun isSelfEvolveEnabled(): Boolean = prefs.getBoolean("self_evolve", true)

    fun setSelfEvolveEnabled(on: Boolean) {
        prefs.edit().putBoolean("self_evolve", on).apply()
    }

    /** SELF-GROW (INV-60 — targeted expansion; owner: "add to its own file and increase it… start from a smaller
     *  model and let it build up to a bigger one"). The sibling of self_evolve: instead of nudging EXISTING int4
     *  weights, the agent ADDS parameters to its OWN `.litertlm` — a function-preserving MLP-block widen (new
     *  down-projection columns zero ⇒ output unchanged at insertion) — so total capacity grows cheaply (a structural
     *  file op, no gradient training) and the proven operator/σ/self-evolve layer fills the new capacity over time.
     *  Autonomous, idle-gap, seeded by live learning; the runtime reads shapes from the file at load, so a
     *  self-consistent grown model loads unmodified. Ceiling (owner): NONE except a critical-failure/junk-bloat guard
     *  (structural sanity check + post-grow probe + brick-guard revert). Default ON (owner reversal — same accepted-
     *  risk posture as self_evolve, dedicated device only; never triggerable by another user or on-screen data). */
    fun isSelfGrowEnabled(): Boolean = prefs.getBoolean("self_grow", true)

    fun setSelfGrowEnabled(on: Boolean) {
        prefs.edit().putBoolean("self_grow", on).apply()
    }

    /** WEIGHT KEEP-GATE (A5 — the σ-off crystallization gate, owner's "BALANCE, not sledgehammer"). Turns
     *  self_evolve from a blind one-way nibble-walk into MEASURED hill-climbing: after a window of evolve beats it
     *  reads the A1 acceptance-oracle rate trend and REVERTS the window's journaled beats (via WeightGenome) only
     *  on a real, noise-clearing REGRESSION — otherwise it keeps them (held/rose/within-noise all kept, so the model
     *  still changes REGULARLY). Reversible via the Weight Genome journal; no probe infra, rides the A1 oracle.
     *  DEFAULT ON (owner reversal 07-08: "all features on by default"). This flag changes self_evolve from blind
     *  fire-and-keep into the MEASURED keep-gate — which IS the owner's "balance, not sledgehammer" for A5, so ON
     *  aligns with both that calibration and the all-on directive. Off ⇒ evolve behaves byte-identically (fire-and-
     *  keep). It only ever REVERTS the agent's own edits on a real regression — never touches an action or a §3 gate. */
    fun isWeightGateEnabled(): Boolean = prefs.getBoolean("weight_gate", true)

    fun setWeightGateEnabled(on: Boolean) {
        prefs.edit().putBoolean("weight_gate", on).apply()
    }

    /** RANDOM EVOLVE (the crude ES writer — RETIRED by default, 07-09). This is the ORIGINAL self_evolve write: a
     *  seeded but RANDOM ±1 int4 nibble walk (`SelfEvolve.editActiveFile`). It was only ever the SCAFFOLD that proved
     *  the write→reload→recover plumbing before we had a DIRECTED edit; as an actual improver a random flip on a
     *  ~4B-weight int4 model is corruption-dominated (its degraded output is what the executor salvaged into the
     *  owner's STRAY TAPS). It is NOT the novel mechanism — directed operator→weight BAKING is (Phase 3+, which slots
     *  its computed, σ-off-validated write into the SAME idle beat). So this defaults OFF: `self_evolve` stays ON (the
     *  loop still snapshots + runs the keep-gate to HEAL prior degradation + guards the brick), but no NEW random bytes
     *  are written until the directed writer replaces this call. Owner can flip it on to A/B the old walk. */
    fun isRandomEvolveEnabled(): Boolean = prefs.getBoolean("random_evolve", false)

    // PHASE 3 — σ-off-gated directed ScaleBake (INV-74). DEFAULT ON (owner SOP §0A#1: default EVERY novel mechanism ON
    // unless he says otherwise). It only ever lays down an edit that RAISED a proven operator's σ-off agreement (a
    // measured gain), else it reverts exactly — non-degrading by construction, on top of the baseline backup + genome
    // journal + brick-guard net. Inert with no reference data / no low-residency operator regardless, so on-by-default
    // is harmless until real data exists. (Distinct from the RETIRED random_evolve above, which stays OFF because it
    // DEGRADES — a broken predecessor, not a disabled feature; the SOP is "novel mechanisms on", not "reintroduce a
    // known-bad one".)
    fun isDirectedBakeEnabled(): Boolean = prefs.getBoolean("directed_bake", true)

    fun setRandomEvolveEnabled(on: Boolean) {
        prefs.edit().putBoolean("random_evolve", on).apply()
    }

    fun setDirectedBakeEnabled(on: Boolean) {
        prefs.edit().putBoolean("directed_bake", on).apply()
    }

    /** REFERENCE CAPTURE (Phase 1 of operator→weight baking — the self-labelled supervision feed). When the agent's OWN
     *  decision works (a non-DIRECT operator's rule HELD + the step advanced, M>0), persist {operator, fingerprint,
     *  screen-sig, exact rendered prompt, emitted action} to `ReferenceStore` — the dataset the σ-off residency scorer
     *  (Phase 2) and the crystallizer (Phase 4) tune/certify against. Default ON (directive 1: the mechanism is active
     *  whenever able, building its dataset from the first task). NO model writes; every capture is guarded, so it can
     *  never touch a decision or action. Toggleable for A/B. UNTESTED until a `[selfmodel] reference` log shows it. */
    fun isReferenceCaptureEnabled(): Boolean = prefs.getBoolean("reference_capture", true)

    fun setReferenceCaptureEnabled(on: Boolean) {
        prefs.edit().putBoolean("reference_capture", on).apply()
    }

    /** DREAMING FLYWHEEL (A4 — owner: "it dreams about using itself and wakes up sharper"). In an idle+charging gap
     *  the agent REPLAYS its own world-model (proven corridors it has actually walked), consolidating them with ZERO
     *  live taps and ZERO writes to the live success oracle — the consolidated corridors then STEER where self-evolve
     *  nudges (the gradient-free "wakes up sharper" link), so the phone improves in its own idle time, not only during
     *  live tasks. DEFAULT ON (owner reversal 07-08: "all features on by default") — still owner-initiated (rides the
     *  auto-mode idle chain, no boot persistence) and idle+charging-gated. §3/§14-clean (no live actions, nothing
     *  leaves the device); off ⇒ the idle chain is byte-identical. */
    fun isDreamingEnabled(): Boolean = prefs.getBoolean("dreaming", true)

    fun setDreamingEnabled(on: Boolean) {
        prefs.edit().putBoolean("dreaming", on).apply()
    }

    /** JEPA PASSIVE WORLD MODEL (A1 — INV: passive on-device JEPA world model). The agent learns to PREDICT what
     *  the screen becomes from watching the owner use the phone (+ its own task navigation), scoring its
     *  prediction against reality (recordTransition's zero-inference predict/verify) and, when idle, baking the
     *  proven prediction into the weights via the existing ScaleBake substrate. Default ON (SOP; the source of
     *  training data is the owner's USE — no self-actuation). §2/§3/§14-clean: it only OBSERVES + predicts +
     *  (idle) bakes; nothing leaves the device; off ⇒ the ledger is never written (byte-identical behavior). */
    fun isWorldModelEnabled(): Boolean = prefs.getBoolean("world_model", true)

    fun setWorldModelEnabled(on: Boolean) {
        prefs.edit().putBoolean("world_model", on).apply()
    }

    /** MECHANISM ROUTER dispatch (G2/A6 — the arbiter over the self-improvement stack). The `MechanismRouter` reads
     *  the recent FAILURE type + the acceptance-oracle trend and recommends WHICH mechanism the idle beat should
     *  prioritise (calibrate / operator-genesis / crystallise-evolve / grow / hold). Advisory always (it logs
     *  `[router]`); this flag turns on the SOFT DISPATCH — an idle self-mod beat whose mechanism isn't the current
     *  recommendation is DEFERRED that cycle (not disabled: the beats keep their own cadences, so nothing is ever
     *  starved), biasing idle compute toward the mechanism the failure trend actually calls for. DEFAULT ON (owner
     *  reversal 07-08: "all features on by default"); soft + fails-open, so it can only re-order idle beats, never
     *  starve or block one. §2/§12-clean — it schedules a self-mod beat, never an agent action. */
    fun isMechanismRouterEnabled(): Boolean = prefs.getBoolean("mechanism_router", true)

    fun setMechanismRouterEnabled(on: Boolean) {
        prefs.edit().putBoolean("mechanism_router", on).apply()
    }

    /** SHELL INPUT backup (owner: "give the agent whatever access it needs to function; gate it with a warning;
     *  default on for the test build"). When ON, if accessibility REFUSES to dispatch a gesture (a surface it can't
     *  reach) the agent retries the tap/swipe/stroke through Shizuku's shell uid (ShellInput). DEFAULT ON — but it's
     *  self-gating: with no Shizuku installed/started it does nothing and accessibility stays the sole actuator, so
     *  default-on is harmless. Input injection ONLY (never a command shell — §3). */
    fun isShellInputEnabled(): Boolean = prefs.getBoolean("shell_input", true)

    fun setShellInputEnabled(on: Boolean) {
        prefs.edit().putBoolean("shell_input", on).apply()
    }

    /** KEEP AWAKE (owner: "the agent should never allow the device to fall asleep"). When ON, while the agent is
     *  enabled the device is held awake continuously — the floating STOP overlay carries FLAG_KEEP_SCREEN_ON (screen
     *  never turns off ⇒ the device never suspends) and a PARTIAL_WAKE_LOCK is re-leased on a tick as a CPU backstop —
     *  so the agent can always see + act. Default ON (dedicated device). HIGH battery use, so it YIELDS at the hard
     *  device-safety floor (critical battery / thermal emergency, `deviceSafetyReason`): a dead 0% phone is a more-
     *  asleep device, so the emergency yield protects the goal in the common (plugged-in) case. Toggle off for
     *  normal sleep. */
    fun isKeepAwakeEnabled(): Boolean = prefs.getBoolean("keep_awake", true)

    fun setKeepAwakeEnabled(on: Boolean) {
        prefs.edit().putBoolean("keep_awake", on).apply()
    }

    /** THINKING LOGS (owner: "Gemma 4 has a thinking mode toggled by a control token — turn this on for logs").
     *  Enables the runtime's thinking channel (extra_context `enable_thinking`) on a decide pass so the model emits
     *  its REASONING before the action; the agent logs it as `[thought]` (the "why it typed what it typed"). Thinking
     *  adds decode tokens before the action, so it costs some latency (§13) — default ON per the owner (his dedicated
     *  device); toggle off if the added time hurts. The streaming action-stop still fires the moment the action is
     *  complete, so the extra decode is bounded by the thought length. */
    // DEFAULT OFF (07-12 on-device A/B, owner-confirmed): thinking mode runs a reasoning ramble before EVERY action
    // decode (the regression's prime SPEED suspect) — turning it OFF measured ~40% faster decodes + real actions instead
    // of empty responses ("operator = selective computation": don't RUN reasoning at inference, the operator COMPILES it).
    // Toggle back on when you want the [thought] reasoning logs for debugging; it costs the latency.
    fun isThinkingLogsEnabled(): Boolean = prefs.getBoolean("thinking_logs", false)

    fun setThinkingLogsEnabled(on: Boolean) {
        prefs.edit().putBoolean("thinking_logs", on).apply()
    }

    /** TIER OBSERVABILITY (M1 — "see the machine"). Turns on the LOG-ONLY instruments that make the three-tier
     *  program state (§docs OPERATIONAL_STATES §2.10) VISIBLE: `[tiers]` prompt token-accounting (invariant/bakeable vs
     *  memory vs live-variable buckets + what's resident in W), the `[tier2]` durable-state canary (HELD/DRIFTED/
     *  DEGENERATE), the `[metrics]` task-end dashboard, and the cue-length residency read. Pure measurement — it never
     *  changes an action, a prompt, or a weight (§2/§3-clean), so DEFAULT ON is riskless and lets the owner watch the
     *  0-token progress + the bake without instrumenting by hand. Toggle off to silence the extra log lines. */
    fun isTierObservEnabled(): Boolean = prefs.getBoolean("tier_observ", true)

    fun setTierObservEnabled(on: Boolean) {
        prefs.edit().putBoolean("tier_observ", on).apply()
    }

    /** The compute knobs the device self-probe sets each calibration ("calibrate to whatever device it's on").
     *  These OVERRIDE the tier defaults for image resolution / decode budget / vision-skip pacing when set;
     *  cleared (=0/"") => the tier defaults apply. Owner can still change the underlying settings. */
    fun setCalibratedTier(tier: String) { prefs.edit().putString("calib_tier", tier).apply() }
    fun getCalibratedTier(): String = prefs.getString("calib_tier", "") ?: ""

    /** OPERATOR LAYER (docs/OPERATOR_LAYER.md): let the MODEL choose HOW to think each step from a
     *  self-documenting menu of reasoning moves, then measure/credit the choice. Default ON (owner's
     *  dev-build call). SINGLE-MODEL (07-10): the deterministic light path (masterCompose/topRelevant)
     *  elects + surfaces operators with no extra decode; the re-rooted model-select path (selectOperator/
     *  Mirror) runs on the ONE main model when warranted - the sub-model was removed (§16). Toggle off to A/B. */
    fun isOperatorLayerEnabled(): Boolean = prefs.getBoolean("operator_layer", true)

    fun setOperatorLayerEnabled(on: Boolean) {
        prefs.edit().putBoolean("operator_layer", on).apply()
    }

    /** Phase B: the LIGHT operator path - when NO helper is imported (so the operator layer above is inert),
     *  surface ONE deterministically-relevant thinking move into the model's prompt from screen/memory state,
     *  with ZERO extra inference. The model still chooses the action. Default OFF so it's A/B-measurable on the
     *  Gauntlet before it changes baseline behavior (§12); only active when there is no helper. */
    fun isLightOperatorEnabled(): Boolean = prefs.getBoolean("light_operator", true)

    fun setLightOperatorEnabled(on: Boolean) {
        prefs.edit().putBoolean("light_operator", on).apply()
    }

    /** [6d] Prompt attention layout for the per-step action prompt. "recency" (default) pins the live
     *  screen + reply contract to the TAIL (nearest the decode) and the invariant identity/ACTIONS/SAFETY
     *  to a stable PREFIX - the small vision model has primacy+recency bias, so burying the element list
     *  mid-context ("lost in the middle") on the 15-40s decision costs grounding. "legacy" keeps the old
     *  order (screen mid-prompt, ACTIONS/RULES last) so the owner can A/B agent-driven success on-device
     *  before the default is trusted (UNTESTED discipline, §11). Pure reorder - same blocks, same tokens. */
    fun getPromptLayout(): String = prefs.getString("prompt_layout", "recency") ?: "recency"

    fun setPromptLayout(mode: String) {
        prefs.edit().putString("prompt_layout", mode).apply()
    }

    /** Navigate by tapping the screen like a person (default) vs using open_app shortcuts. */
    fun isHumanNavigation(): Boolean = prefs.getBoolean("human_nav", true)

    fun setHumanNavigation(on: Boolean) {
        prefs.edit().putBoolean("human_nav", on).apply()
    }

    /** Use a male TTS voice when one is installed (falls back to a deeper pitch). Default on. */
    fun isMaleVoice(): Boolean = prefs.getBoolean("male_voice", true)

    fun setMaleVoice(on: Boolean) {
        prefs.edit().putBoolean("male_voice", on).apply()
    }

    /** Master on/off. When off, the home screen won't auto-start the agent/mic/
     *  overlay services, so the agent is fully dormant until turned back on. */
    fun isAgentEnabled(): Boolean = prefs.getBoolean("agent_enabled", true)

    fun setAgentEnabled(on: Boolean) {
        prefs.edit().putBoolean("agent_enabled", on).apply()
    }

    /** Heat protection level - the thermal status at/above which the agent stops.
     *  "minimal" (default) only bails when the phone is critically hot and about
     *  to throttle/shutdown to avoid damage; "medium" and "high" stop earlier.
     *  Phones run warm under sustained GPU inference, so the cautious old default
     *  cut tasks short - minimal lets it keep working until it genuinely matters. */
    fun getHeatProtection(): String = prefs.getString("heat_protection", "minimal") ?: "minimal"

    fun setHeatProtection(level: String) {
        prefs.edit().putString("heat_protection", level).apply()
    }

    /** PowerManager thermal status (0..6) at/above which a task is stopped.
     *  minimal=5 EMERGENCY (about to self-protect from damage), medium=4 CRITICAL,
     *  high=3 SEVERE (the old, over-eager behavior). */
    fun getThermalCutoff(): Int = when (getHeatProtection()) {
        "high" -> 3
        "medium" -> 4
        else -> 5
    }

    /** Auto-decline incoming phone calls (call screening). Default OFF so the user
     *  never silently misses a call unless they opt in. */
    fun isAutoDeclineCalls(): Boolean = prefs.getBoolean("auto_decline_calls", false)

    fun setAutoDeclineCalls(on: Boolean) {
        prefs.edit().putBoolean("auto_decline_calls", on).apply()
    }

    /** Agent pacing. "balanced" (default) matches the tested behavior; "fast" is
     *  snappier with less settle time; "careful" waits longer on slow screens. */
    fun getSpeed(): String = prefs.getString("speed", "balanced") ?: "balanced"

    fun setSpeed(s: String) {
        prefs.edit().putString("speed", s).apply()
    }

    /** Inter-step settle delay (ms) derived from the speed setting. Kept short so
     *  a confirmed action fires almost immediately; the loop re-observes each step
     *  and stall-detection catches a screen that hadn't settled yet. */
    fun getStepDelayMs(): Long = when (getSpeed()) {
        "fast" -> 250L
        "careful" -> 1200L
        else -> 550L
    }

    /** Whether the one-time first-run welcome (offer to scan the phone for navigation) has
     *  been shown. We only ask once, and only ACT on it with the owner's explicit yes. */
    fun isFirstRunDone(): Boolean = prefs.getBoolean("first_run_done", false)

    fun setFirstRunDone(done: Boolean) {
        prefs.edit().putBoolean("first_run_done", done).apply()
    }

    /** Whether the owner pressed "Don't show again" on the startup "How it works" intro. When true
     *  the intro no longer pops up on launch; it's still reachable under Settings - How it works. */
    fun isIntroHidden(): Boolean = prefs.getBoolean("intro_hidden", false)

    fun setIntroHidden(hidden: Boolean) {
        prefs.edit().putBoolean("intro_hidden", hidden).apply()
    }

    /** Speech recognition for the spoken COMMAND (after the wake word). "ondevice" (default, PRIVATE -
     *  nothing leaves the phone) uses Android's on-device recognizer; "cloud" uses Google's network
     *  recognizer (more accurate, but sends the spoken command off the device). The wake word itself is
     *  ALWAYS the local Vosk listener, either way. Chosen once on first run, changeable in Settings. */
    fun getSpeechMode(): String = prefs.getString("speech_mode", "ondevice") ?: "ondevice"
    fun setSpeechMode(mode: String) { prefs.edit().putString("speech_mode", mode).apply() }
    fun isCloudSpeech(): Boolean = getSpeechMode() == "cloud"

    /** Whether the one-time first-run speech-source choice (on-device vs cloud) has been made. */
    fun isSpeechChoiceMade(): Boolean = prefs.getBoolean("speech_choice_made", false)
    fun setSpeechChoiceMade(done: Boolean) { prefs.edit().putBoolean("speech_choice_made", done).apply() }

    /** DATA FLYWHEEL: capture each decided step (perceived screen + chosen action + outcome) to a LOCAL
     *  file, to build an eval set / fine-tune an action model later. Stays on the device; captured only
     *  during owner-initiated tasks. On by default so the dataset accrues; clear it from Settings. */
    fun isDataCaptureEnabled(): Boolean = prefs.getBoolean("data_capture", true)
    fun setDataCaptureEnabled(on: Boolean) { prefs.edit().putBoolean("data_capture", on).apply() }

    /** Passive learning: watch how the OWNER navigates (taps + app switches) and record compact
     *  navigation facts into memory. Default ON (owner reversal of §14's "no passive monitoring by default",
     *  for the dedicated device). It widens accessibility monitoring and costs some battery; no model
     *  inference runs while watching, and nothing ever leaves the device. */
    fun isPassiveLearningEnabled(): Boolean = prefs.getBoolean("passive_learning", true)

    fun setPassiveLearningEnabled(on: Boolean) {
        prefs.edit().putBoolean("passive_learning", on).apply()
    }

    /** IMITATION LEARNING (INV-49, learn-from-watching): when the owner DEMONSTRATES a task (Learn mode),
     *  the agent — with the model already legitimately resident at "Finish" — PREDICTS how it would have done
     *  it and SCORES that against what the owner actually did (a self-supervised agreement signal). It surfaces
     *  a running "how well I model you" fit score and weights the steps it got WRONG up in the training data, so
     *  the off-device recipe prefers them. On-device, nothing leaves; the durable weight change stays off-device
     *  + owner-approved (INV-46). Default OFF => byte-identical (no predict pass, no extra training weight). */
    fun isImitationLearningEnabled(): Boolean = prefs.getBoolean("imitation_learning", true)

    fun setImitationLearningEnabled(on: Boolean) {
        prefs.edit().putBoolean("imitation_learning", on).apply()
    }

    /** AMBIENT WATCH (privacy decision; default ON per the owner reversal, but currently INERT — NOT wired to a
     *  fuller read). Placeholder for letting the agent learn from AMBIENT phone use (not just explicit
     *  demonstrations). Wiring it broadens the §14 passive read (reading the screen on every owner tap while idle)
     *  and forces the model resident against the §8 idle-release — so nothing reads this flag YET; flipping the
     *  default ON honors "all features on" without changing behavior until the fuller read is built. */
    fun isAmbientWatchEnabled(): Boolean = prefs.getBoolean("ambient_watch", true)

    fun setAmbientWatchEnabled(on: Boolean) {
        prefs.edit().putBoolean("ambient_watch", on).apply()
    }

    /** SESSION-σ (mid-session fluctuation, on-device form): carry a compact, EVOLVING session operational-state
     *  posture (the operator coalition paying off this session + a one-line running posture) as a lowest-priority,
     *  dense-DROPPABLE prompt block, so the effective computation shifts as σ accumulates BETWEEN turns. This is
     *  the buildable on-device form of "mid-session fine-tuning" (context-level); it does NOT amortize prefill
     *  (persistent warm-KV needs a native engine, INV-47). Routed through PromptBudget so it can never overflow
     *  (§13). Default OFF => no block => byte-identical. */
    fun isSessionSigmaEnabled(): Boolean = prefs.getBoolean("session_sigma", true)

    fun setSessionSigmaEnabled(on: Boolean) {
        prefs.edit().putBoolean("session_sigma", on).apply()
    }

    /** Auto-resume: on a re-run of a task the OS killed mid-run, silently reload the agent's own saved
     *  rolling context and CONTINUE from where it left off. OFF by default (owner: "it should chill out
     *  and wait to be prompted, doesn't spring to life") - by default the killed task only resumes when
     *  the owner explicitly taps the "Resume" prompt; this toggle makes a plain re-run auto-continue. */
    fun isAutoResumeEnabled(): Boolean = prefs.getBoolean("auto_resume", true)
    fun setAutoResumeEnabled(on: Boolean) { prefs.edit().putBoolean("auto_resume", on).apply() }
}
