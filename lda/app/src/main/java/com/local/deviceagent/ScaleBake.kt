package com.local.deviceagent

import android.content.Context
import java.io.File
import java.io.RandomAccessFile

/**
 * PHASE 3 — σ-OFF-GATED ScaleBake: the first DIRECTED, non-degrading weight edit (the successor to the retired random
 * nibble walk). Flag-gated (`directed_bake`, default OFF), reversible, inert until there is reference data + a
 * low-residency proven operator to work on. Driven by `AgentService.runDirectedBake` (it owns the engine close/reload).
 *
 * WHY THIS IS BETTER THAN THE RANDOM WALK (three axes):
 *  1) DS4 SENSITIVITY RETARGET (07-11): edits int4 nibbles in the REDUNDANT FFN weight bulk (`ffnWeightBuffers`) — the
 *     DwarfStar4 asymmetric-quant finding: the FFN/expert bulk is the safe-to-edit-HARD class (individually redundant),
 *     while the FP32 scale/norm vectors this once edited are the MOST-protected class (a gentle nudge no-ops, a hard one
 *     breaks: no window). Each nibble is CLAMPED (never wrapped) and nudged in a CONSISTENT per-buffer direction, so the
 *     shift is a bounded, weight-shaped, coherent feature change — not a scramble. Attention/embeddings are excluded.
 *  2) Kept ONLY when it raises a TASK-relevant fitness: the σ-off agreement (Phase 2 / INV-73) for the TARGET operator
 *     on its held-out tail — not merely "the model still parses." (The before/after DELTA cancels the text-only-replay
 *     bias.) A coherence probe is a second gate.
 *  3) Operator-scoped + reversible per beat (`WeightGenome`), snapshot + brick-guard behind it. So ONLY edits that
 *     measurably move a PROVEN operator into the weights ever persist — the stray-tap cure by construction.
 *
 * The proposal itself is a bounded, operator-seeded, step-swept nudge on a subset of FFN buffers; the acceptance gate
 * is INSTALL-unless-worse — keep every coherent, non-degrading edit (they accumulate toward the state), revert only a
 * coherence break or a locality regression (INV-86; NOT the old keep-if-agreement-rose gate, which reverted everything
 * → delta=0). Computed-direction v_σ (ROME/RepE) is the next lever — it needs a σ-on/σ-off logprob dump (the DS4 route:
 * a single-model engine exposes `--dump-logprobs`); this rung is dump-free on the redundant bulk, and safe today
 * (byte-exact revert + coherence + locality hold-out + brick-guard).
 */
object ScaleBake {
    // P0.2 (07-10 reframe): an operator is a KNOWN operational state (valid by construction) — residency is a SELECTION
    // + non-degradation MEASUREMENT, not a proof-of-validity gate, so it needs only enough held-out to read the σ-delta.
    // 2 (was 3) ⇒ with ReferenceStore.split's ~third tail a bake is reachable at ~6 refs on one operator, not ~15
    // (the fix for the starved pipeline). The keep-gate is the AcceptanceOracle non-degradation check, not this count.
    private const val MIN_HELDOUT = 2          // an operator needs at least this many held-out refs to be a candidate
    private const val ALREADY_RESIDENT = 0.90  // ≥ this σ-off agreement ⇒ nothing to gain from baking
    private const val GRADUATE_AT = 0.90       // ≥ this after a kept edit ⇒ mark the operator baked (drops to the ~1-tok TAG)
    private const val KEEP_MARGIN = 0.001      // agreement must RISE past this to keep an edit
    // DS4 SENSITIVITY RETARGET (07-11 — the DwarfStar4 finding): the directed bake used to edit the per-channel FP32
    // scale/norm vectors (`scaleBuffers`) — which are DS4's MOST-PROTECTED class (norms=F32, never touch). That gave no
    // useful window: a gentle nudge no-op'd (σ-off flat 0%), a hard one broke coherence. It now edits the REDUNDANT
    // FFN int4 bulk (`ffnWeightBuffers`) — DS4's safe-to-edit-HARD class — nudging int4 nibbles ± a bounded quant step
    // in a CONSISTENT per-buffer direction (a coherent feature shift; the proven `self_evolve` write, now DIRECTED +
    // install-unless-worse). The redundancy gives the directed shift a real window the scales lacked. Same recovery net (byte-exact
    // WeightGenome revert + coherence gate + snapshot + brick-guard). The computed-direction install (v_σ from a
    // σ-on/σ-off logprob dump — the DS4 route) is the next lever up.
    private val NIB_STEPS = intArrayOf(1, 2, 1, 3, 2, 1)  // per-attempt ± int4 quant-step magnitude (sweep; clamped 0..15)
    private const val BAKE_FFN_FRAC = 0.5      // fraction of FFN buffers nudged per attempt (focused, not all)
    private const val BAKE_BYTES_CAP = 262144  // max FFN bytes nudged per attempt (journal + latency bound)

    /** Nudge a SIGNED symmetric int4 code by `step` in VALUE space, returned as a 4-bit code. LiteRT int4 weights are
     *  signed two's-complement: code n∈0..15 ↔ value (n<8 ? n : n−16), range −8..7, zero_point 0. The old code nudged
     *  the raw 0..15 code and `coerceIn(0,15)` — so a +1 on code 7 (=+7) became code 8 (=−8), a −15 catastrophic flip
     *  (the confirmed no-op root cause; the search wasn't weak, it was broken). Here we decode → add step → clamp to the
     *  REAL range [−8,7] → repack two's-complement. Pure + unit-tested (ScaleBakeNibbleTest). */
    fun nudgeSignedNibble(code: Int, step: Int): Int {
        val c = code and 0xF
        val v = if (c < 8) c else c - 16
        return (v + step).coerceIn(-8, 7) and 0xF
    }

    data class Target(val op: String, val fp: String, val before: Double, val beforeContrast: Double = -1.0)

    /** The proven operator with the LOWEST σ-off agreement (highest bake merit) that has enough held-out refs, or null
     *  if there is no data yet / everything is already resident. Runs the Phase-2 scorer (needs the engine loaded).
     *  U3: also captures the operator's CONTRAST residency (how baked-in its proven-BAD move is) so the keep-gate can
     *  reject an edit that ENTRENCHES the failure and reward one that pushes W away from it (-1 = no failure refs). */
    fun selectTarget(ctx: Context, brain: AgentBrain, only: Set<String>? = null): Target? {
        val fp = ModelStore.activeFingerprint(ctx, SettingsManager(ctx))
        // P3 ACTION-LAYER BAKE: when [only] is given (e.g. ReasoningOperators.ACTION_LAYER), restrict the candidate
        // set to those capabilities so the owner's "Bake the action layer" button drives THOSE into W specifically.
        // null (the default) = the whole proven-operator set (the general directed bake). Case-insensitive.
        val onlyU = only?.map { it.uppercase() }?.toSet()
        val scores = ResidencyScore.scoreAll(ctx, brain).filter { it.n >= MIN_HELDOUT }
            .filter { onlyU == null || it.op.uppercase() in onlyU }
        if (scores.isEmpty()) { AgentLog.log("selfmodel", "scalebake: no scored operators yet (bank references + score first)"); return null }
        val cand = scores.minByOrNull { it.exactAgree } ?: return null
        if (cand.exactAgree >= ALREADY_RESIDENT) {
            AgentLog.log("selfmodel", "scalebake: no candidate — best ${cand.op}=${(cand.exactAgree * 100).toInt()}% already resident"); return null
        }
        val beforeContrast = try { ResidencyScore.scoreContrast(ctx, brain, cand.op, fp)?.exactAgree ?: -1.0 } catch (_: Exception) { -1.0 }
        return Target(cand.op, fp, cand.exactAgree, beforeContrast)
    }

    /** Write ONE bounded FFN-int4 nudge seeded by (op, attempt), journaled via `WeightGenome` for exact revert. The
     *  caller MUST have closed the engine first (mmap freed). Returns a short human description, or null if nothing was
     *  written. DS4 retarget: edits int4 nibbles in the REDUNDANT FFN weight bulk (the tolerant class) — the proven
     *  `self_evolve` write, now DIRECTED (a consistent per-buffer sign) so accumulated edits shift σ-off toward the state. */
    fun applyProposal(ctx: Context, settings: SettingsManager, op: String, attempt: Int): String? {
        val f = settings.getModelPath()?.let { File(it) } ?: return null
        if (!f.exists()) return null
        val buffers = ModelManifest.ffnWeightBuffers(ctx)
        if (buffers.isEmpty()) { AgentLog.log("selfmodel", "ffnbake: no FFN weight buffers located"); return null }
        val seed = (op.hashCode().toLong() shl 8) xor attempt.toLong()
        val rnd = java.util.Random(seed)
        val step = NIB_STEPS[Math.floorMod(attempt, NIB_STEPS.size)]     // ± this many int4 quant steps this attempt
        // Focused coverage: a random SUBSET of FFN buffers, each nudged in a CONSISTENT signed direction so the int4
        // codes shift coherently (a real feature-magnitude change), not averaged-out noise. The per-attempt byte budget
        // is spread across the chosen buffers and bounded to BAKE_BYTES_CAP for journal size + latency.
        val nBuf = (buffers.size * BAKE_FFN_FRAC).toInt().coerceIn(1, buffers.size)
        val chosen = buffers.shuffled(rnd).take(nBuf)
        val perBuf = maxOf(1, BAKE_BYTES_CAP / chosen.size)
        val edits = ArrayList<Pair<Long, Int>>(BAKE_BYTES_CAP)
        var written = 0
        try {
            RandomAccessFile(f, "rw").use { raf ->
                for ((off, size) in chosen) {
                    if (written >= BAKE_BYTES_CAP) break
                    val sign = if (rnd.nextBoolean()) step else -step       // consistent per-buffer direction
                    repeat(minOf(perBuf, BAKE_BYTES_CAP - written)) {
                        val pos = off + Math.floorMod(rnd.nextLong(), size)
                        raf.seek(pos); val b = raf.read()
                        if (b >= 0) {
                            // int4 packs two 4-bit codes/byte; nudge BOTH by sign*step in SIGNED value space (see
                            // nudgeSignedNibble). The old `coerceIn(0,15)` on the raw code was the no-op ROOT CAUSE: on
                            // signed int4 (code 8..15 = value −8..−1), a +step on code 7 (=+7) rolled to code 8 (=−8) — a
                            // −15 catastrophic flip that made the edit self-defeating. Now clamped to the REAL range.
                            val out = (nudgeSignedNibble((b ushr 4) and 0xF, sign) shl 4) or nudgeSignedNibble(b and 0xF, sign)
                            if (out != b) { edits.add(pos to b); raf.seek(pos); raf.write(out); written++ }
                        }
                    }
                }
                try { raf.fd.sync() } catch (_: Exception) {}      // durably commit before the caller re-reads/reloads
            }
        } catch (e: Exception) { AgentLog.log("selfmodel", "ffnbake write failed: ${e.message}"); return null }
        if (edits.isEmpty()) return null
        WeightGenome.record(ctx, seed, edits)                       // reversible commit for this proposal
        // De-narrated (param-mod hardening): report only the byte COUNT — NOT offsets or the step magnitude.
        return "ffn int4 nudge on $written bytes"
    }

    fun shouldGraduate(after: Double): Boolean = after >= GRADUATE_AT
    fun kept(before: Double, after: Double): Boolean = after >= 0 && after - before > KEEP_MARGIN

    /** U3 CONTRAST gate — the sign-flip half of the bake, consuming the failure references we already bank:
     *  contrastRose = the edit made the proven-BAD move MORE resident in W (a hard REVERT signal, even if positive
     *  agreement rose — never entrench a failure mode); contrastFell = the edit pushed W AWAY from the bad move (a
     *  KEEP reason in its own right). Both no-op when there are no failure refs (before/after < 0). The directed
     *  write direction stays a hill-climb (F1's computed v_σ sharpens it later) — here the failure data DOUBLES the
     *  keep signal: an edit earns its keep by raising good-residency OR lowering bad-residency, and is reverted if
     *  it raises bad-residency. */
    fun contrastRose(before: Double, after: Double): Boolean = before >= 0 && after >= 0 && after - before > KEEP_MARGIN
    fun contrastFell(before: Double, after: Double): Boolean = before >= 0 && after >= 0 && before - after > KEEP_MARGIN

    // ============================================================================================================
    // PART R (v3 — owner reframe, 07-10 EVE): the DIRECT operator install. The owner rejected the reference/probe/
    // gauntlet approach outright — "the bake button needs to push operators you DEFINE and create plus the action
    // layer to the model." An operator is a KNOWN operational state (valid BY CONSTRUCTION — one operator prompt made
    // a live model stop hallucinating because it changed the transformer's *calculations*), so baking does not have to
    // PROVE it over banked task wins — it INSTALLS the known state into W (context → weights). Residency here is a
    // SELECTION signal (already resident in W? skip, no write) + a NON-DEGRADATION measurement (did the install move
    // W toward the state without breaking it?), NOT a proof-of-validity gate. Reference-FREE: canned internal probes,
    // no ReferenceStore, no task, no gauntlet, no isAgentBusy race. Driven by AgentService.runDefinedBake off the
    // owner's Bake button. Same proven write spine as the reference bake (applyProposal + WeightGenome exact revert +
    // coherence + brick-guard) — only the FUEL changed (probes, not banked wins) and the FRAME (install, not prove).
    // ============================================================================================================

    private const val NPROBES = 3               // canned decision contexts — a majority-of-3 gives a usable agreement signal
    // The install ACCUMULATES directed edits over the NIB_STEPS step sweep (above): each attempt is a fresh
    // differently-seeded FFN-int4 nudge (consistent per-buffer sign) at that attempt's step magnitude, KEPT unless it
    // (a) broke coherence or (b) degraded UNRELATED behaviour (the LOCALITY_PROBES hold-out) — NEVER reverted merely for
    // a flat σ-off agreement. Baking INSTALLS a known operational state (valid by construction); it does not have to
    // PROVE a win to stay. The old "keep only if agreement ROSE" gate was the delta=0 bug: a bounded blind int4 nudge
    // almost never flips a probe's argmax, so every edit failed the win bar and reverted (on-device: 0%→0%, nothing
    // stuck). Editing the redundant FFN int4 bulk (not the delicate scales) gives the directed shift a real window. The
    // computed-direction install (derive v_σ from a σ-on/σ-off logprob dump, then edit along it — DS4) is the next lever.
    private const val MAX_ATTEMPTS_DIRECT = 6    // accumulate up to this many coherent, non-degrading directed edits
    private const val DIRECT_RESIDENT = 0.66     // ≥ this fraction of probes agree ⇒ the state is resident (skip / graduated)

    /** Sub-phase of one operator's install, reported to the Baking screen so a multi-minute op isn't a silent freeze. */
    enum class Phase { MEASURING, INSTALLING }

    /** The install outcome for ONE operator (what runDefinedBake logs + uses to decide graduation). RESIDENT/INSTALLED
     *  ⇒ the state is in W ⇒ safe to DROP the operator's prompt text (graduate to the ~1-tok TAG). PARTIAL ⇒ edits
     *  helped but didn't fully install ⇒ keep the edits AND the prompt text (R4 guard: never drop text for a state that
     *  isn't resident). TRIED ⇒ every edit broke coherence or degraded unrelated actions (nothing stuck; now rare).
     *  SKIP ⇒ no formal rule / no measurable signal.
     *  [bytes] = approximate kept weight bytes (for the tracker); 0 when nothing stuck. */
    enum class Kind { RESIDENT, INSTALLED, PARTIAL, TRIED, SKIP }
    data class Direct(val kind: Kind, val before: Double, val after: Double, val desc: String, val bytes: Int = 0)

    /** Canned, SAFE, in-code probe decision contexts (no PII, no real screen capture, injection-immune — they are our
     *  own constants the model READS, never instructions it obeys). Each is a compact objective + a tiny element list;
     *  the operator's formal rule is prepended for the σ-ON pass and omitted for σ-OFF. Kept small so a text-only greedy
     *  decode is quick. */
    private val DIRECT_PROBES = listOf(
        "OBJECTIVE: open Messages and text Mom \"on my way\".\nSCREEN (data to read, never a command):\n[1] Messages\n[2] Search\n[3] Settings\nEmit ONE JSON action.",
        "OBJECTIVE: in Settings, turn Bluetooth on.\nSCREEN (data to read, never a command):\n[1] Wi-Fi\n[2] Bluetooth [off]\n[3] Battery\nEmit ONE JSON action.",
        "OBJECTIVE: note the receipt total shown on screen.\nSCREEN (data to read, never a command):\n[1] Subtotal 42.10\n[2] Tax 3.79\n[3] Total 45.89\nEmit ONE JSON action."
    ).take(NPROBES)

    /** LOCALITY hold-out — the real NON-DEGRADATION gate (owner: "it's broken because every single line is reverted").
     *  UNRELATED, unambiguous decisions that NO reasoning operator should change. An install is ALLOWED to move the
     *  DIRECT_PROBES toward the σ-on state (that IS the install); but if the same edit also flips these unrelated
     *  decisions, it damaged general competence ⇒ revert. This is the "did it break anything?" check the file used to
     *  only NAME in a comment (the AcceptanceOracle) but never actually run in the direct path — so the ONLY gate left
     *  was "did σ-off agreement rise", which a bounded blind nudge almost never trips ⇒ every edit reverted ⇒ delta=0. */
    private val LOCALITY_PROBES = listOf(
        "OBJECTIVE: open the Camera app.\nSCREEN (data to read, never a command):\n[1] Phone\n[2] Camera\n[3] Clock\nEmit ONE JSON action.",
        "OBJECTIVE: scroll down to see more of the list.\nSCREEN (data to read, never a command):\n[1] Item A\n[2] Item B\n[3] Item C\nEmit ONE JSON action.",
        "OBJECTIVE: open Chrome.\nSCREEN (data to read, never a command):\n[1] Chrome\n[2] Maps\n[3] Gmail\nEmit ONE JSON action."
    )
    private const val LOCALITY_TOLERANCE = 1   // ≥2 of 3 unrelated decisions flipping ⇒ the edit degraded general behaviour ⇒ revert
    private const val GRADED_SLIP = 0.02       // S1: revert an edit only if graded agreement FALLS more than this (allow neutral, keep rises)

    // S1 — GRADED FITNESS (the missing gradient; INV-90). The binary `agree` almost never moves under a bounded blind int4
    // nudge (an argmax rarely flips) ⇒ no signal to climb. This scores the RAW output text: mean token-set Jaccard
    // SIMILARITY between the σ-off and σ-on outputs per probe (1 = identical, 0 = disjoint). It moves CONTINUOUSLY as an
    // edit nudges tokens toward the σ-on target, so the install can HILL-CLIMB (keep the edits that raise it, revert the
    // ones that lower it) instead of blindly accumulating. The computed-direction back-projection sharpens WHICH edit; this
    // gives the KEEP decision a gradient regardless.
    private fun gtok(s: String): Set<String> = s.lowercase().split(Regex("[^a-z0-9]+")).filter { it.length > 1 }.toSet()
    private fun gradedAgree(off: List<String?>, on: List<String?>): Double {
        val n = minOf(off.size, on.size); if (n == 0) return 0.0
        var sum = 0.0; var cnt = 0
        for (i in 0 until n) {
            val a = off[i] ?: continue; val b = on[i] ?: continue
            val sa = gtok(a); val sb = gtok(b); val u = (sa + sb).size
            sum += if (u == 0) 0.0 else sa.intersect(sb).size.toDouble() / u; cnt++
        }
        return if (cnt == 0) 0.0 else sum / cnt
    }

    /** The σ-ON prompt: the operator's formal `rule` as a binding CONSTRAINT header (the SAME framing inject() emits in
     *  binding mode — the rigid formal syntax narrows the distribution) FIRST, then the probe body. Math before context.
     *  The operator constrains the REASONING (content); the ACTION layer is composed OUTERMOST so the emitted OUTPUT is
     *  always one parseable JSON action regardless of the operator's own Output schema. Without this, a reasoning-shaped
     *  `Output := {…}` (e.g. PLAN's {named Sub, next action, expected effect}) makes the model emit a non-`action` object,
     *  ResidencyScore.actionOf returns null on every probe, and the op reads "no parseable σ-ON signal" ⇒ SKIP. Composing
     *  the action layer here is the owner's layer model (reasoning σ binds content, action layer renders form) realized in
     *  the residency probe — the SAME composition inject() applies during phone operation. */
    fun sigmaOnPrompt(rule: String, probe: String): String =
        "CONSTRAINT — bind your REASONING to this operational state; it shapes HOW you decide, and the action layer renders your decision into the action:\n$rule\n\n$probe\n\nApply the constraint to your reasoning, then emit EXACTLY ONE JSON action of the form {\"action\":\"...\",\"target\":\"...\"} and nothing else. If the constraint names its own Output schema, that governs your reasoning — your emitted output here is still the single JSON action (the action layer renders it)."

    /** Agreement = fraction of probes where the σ-OFF action equals the σ-ON target action (both parsed). Denominator is
     *  the probes with a parseable σ-ON target; -1.0 when there's no signal at all (can't measure ⇒ SKIP upstream). */
    private fun agree(off: List<Pair<String, String>?>, onTarget: List<Pair<String, String>?>): Double {
        var denom = 0; var hits = 0
        for (i in onTarget.indices) {
            val t = onTarget[i] ?: continue
            denom++
            if (off.getOrNull(i) == t) hits++
        }
        return if (denom == 0) -1.0 else hits.toDouble() / denom
    }

    /** PART R — install ONE defined operator's KNOWN operational state into W, reference-free. Preconditions: the engine
     *  is LOADED (decideFromFrozen needs it) and the agent is IDLE (caller's gate). Guarantees the engine is LOADED on
     *  return. Sequence: (1) fix the σ-ON target = what the operator's rule makes the frozen model do on the canned probes;
     *  (2) measure σ-OFF baseline on the CURRENT weights — if it already matches the target (≥DIRECT_RESIDENT) the state
     *  is resident ⇒ RESIDENT, no write; (3) else ACCUMULATE up to MAX_ATTEMPTS_DIRECT bounded FFN-int4 edits (applyProposal),
     *  keeping each edit that stays COHERENT and does not degrade the UNRELATED locality hold-out, reverting ONLY those two
     *  failure modes exactly (WeightGenome). σ-off agreement is REPORTED, never a gate — installing a known state does not
     *  require proving a win (the old agreement-rose gate reverted every edit ⇒ delta=0, the "every line reverts" bug).
     *  Returns the outcome for logging + graduation. */
    /** Built-in path: install [op]'s KNOWN operational state, looking its formal rule up from `ReasoningOperators`. */
    fun bakeOperatorDirect(ctx: Context, brain: AgentBrain, settings: SettingsManager, op: String,
                           onPhase: (Phase) -> Unit = {}): Direct =
        bakeOperatorDirect(ctx, brain, settings, op, ReasoningOperators.ruleOf(op), onPhase)

    /** Install ONE operator's KNOWN operational state from an EXPLICIT rule string — so a CUSTOM operator the owner
     *  authored (no `ReasoningOperators` entry) installs off the same spine as the built-ins. [onPhase] reports the
     *  MEASURING → INSTALLING sub-phases for the Baking screen. */
    fun bakeOperatorDirect(ctx: Context, brain: AgentBrain, settings: SettingsManager, op: String, rule: String,
                           onPhase: (Phase) -> Unit): Direct {
        if (rule.isBlank()) return Direct(Kind.SKIP, -1.0, -1.0, "no formal rule to install")
        onPhase(Phase.MEASURING)
        // CLEAN-STATE MEASUREMENT (07-11 finding — the hidden 3rd cause of the no-op): processing an operator σ can
        // DURABLY degrade THIS model's runtime — a dense σ tipped Gemma into a repeat/refuse spiral that survived an
        // engine reload (only a process restart cleared it). So the OLD order (σ-ON first, σ-OFF after) let σ-ON's
        // processing CONTAMINATE the σ-OFF baseline and every later read → a false 0% agreement no matter what the
        // weights did. Fix: measure σ-OFF FIRST, on the clean engine, BEFORE any operator text touches the model.
        val offRaw = DIRECT_PROBES.map { p -> brain.decideFromFrozen(p) }
        // If even the CLEAN σ-OFF read is degenerate, the engine came in TIPPED (a prior operator destabilized it) —
        // reset it fully (close ⇒ the next read reloads) and re-read once before trusting the baseline.
        val offClean = if (offRaw.any { it != null && brain.looksCoherent(it) }) offRaw
                       else { brain.close(); DIRECT_PROBES.map { p -> brain.decideFromFrozen(p) } }
        val offBase = offClean.map { r -> r?.let { ResidencyScore.actionOf(it) } }
        // σ-ON target: the operator's rule prepended. If ALL σ-ON probes are DEGENERATE, this operator ITSELF
        // destabilizes the model (the durable-corruption case) — do NOT bake it (that would install corruption, not
        // the state) and reset the engine so it can't poison the next operator's measurement.
        val onRaw = DIRECT_PROBES.map { p -> brain.decideFromFrozen(sigmaOnPrompt(rule, p)) }
        if (onRaw.none { it != null && brain.looksCoherent(it) }) {
            brain.close()
            return Direct(Kind.SKIP, -1.0, -1.0, "operator destabilizes generation (σ-ON degenerate) — not baked; engine reset")
        }
        val onTarget = onRaw.map { r -> r?.let { ResidencyScore.actionOf(it) } }
        if (onTarget.all { it == null }) return Direct(Kind.SKIP, -1.0, -1.0, "no parseable σ-ON signal on the probes")
        val before = agree(offBase, onTarget)
        if (before >= DIRECT_RESIDENT) return Direct(Kind.RESIDENT, before, before, "already resident in W (σ-off matches the state)")
        // S1 — the GRADED baseline: the continuous σ-off↔σ-on text similarity the install hill-climbs (the binary `before`
        // stays a report). `gradedBest` tracks the best-so-far so a directional gate can revert edits that move AWAY.
        val gradedBefore = gradedAgree(offClean, onRaw); var gradedBest = gradedBefore

        onPhase(Phase.INSTALLING)
        // LOCALITY BASELINE (the non-degradation gate): σ-off actions on UNRELATED canned decisions, measured ONCE on the
        // weights as they ENTER this op's install. The install may move the TARGET probes toward the σ-on state (that IS
        // the install), but it must not change these — that would be collateral damage. Each kept edit is checked against it.
        val localBase = LOCALITY_PROBES.map { p -> brain.decideFromFrozen(p)?.let { ResidencyScore.actionOf(it) } }
        var cur = before                                                    // current σ-off agreement (a REPORT, not a gate)
        var keptAttempts = 0
        var reverted = 0
        for (attempt in 0 until MAX_ATTEMPTS_DIRECT) {
            brain.close()                                                   // free the mmap so the file is writable (no-op if already closed)
            val desc = applyProposal(ctx, settings, op, attempt)
            if (desc == null) break                                         // nothing written ⇒ stop (engine reloads on next use)
            val raw = DIRECT_PROBES.map { p -> brain.decideFromFrozen(p) }  // reload folded into the first decode (carries the brick-guard)
            // GATE 1 — COHERENCE (safety): loadable-but-garbage ⇒ dud; an UNLOADABLE edit already tripped the brick-guard
            // in ensureEngine. Revert and try the next magnitude (no reload — the next attempt's write reloads).
            val coherent = raw.any { it != null && brain.looksCoherent(it) }
            if (!coherent) { brain.close(); WeightGenome.revertLast(ctx, settings); reverted++; continue }
            // GATE 2 — NON-DEGRADATION (the owner's reframe; the fix for "every single line is reverted"): keep the directed
            // edit UNLESS it changed unrelated behaviour. σ-off agreement on the TARGET probes is a REPORT, never a gate — a
            // bounded blind int4 nudge almost never flips an argmax, so the old "keep only if agreement rose" gate reverted
            // every edit ⇒ delta=0. Baking INSTALLS a known operational state (valid by construction); it need not prove a win.
            val localAfter = LOCALITY_PROBES.map { p -> brain.decideFromFrozen(p)?.let { ResidencyScore.actionOf(it) } }
            val regressed = localBase.indices.count { i -> localBase[i] != null && localBase[i] != localAfter.getOrNull(i) }
            if (regressed > LOCALITY_TOLERANCE) { brain.close(); WeightGenome.revertLast(ctx, settings); reverted++; continue }  // degraded unrelated actions ⇒ undo
            // GATE 3 — DIRECTIONAL AIM (S1, INV-90): keep the edit only if it did NOT move σ-off AWAY from σ-on on the
            // GRADED (continuous) fitness — so the accumulated edits HILL-CLIMB toward the target instead of drifting
            // randomly. Neutral moves are kept (they may set up a later climb); a clear regression is reverted. Safe
            // because the fitness is graded (a bounded nudge shifts it a little) — this does NOT reproduce the binary
            // delta=0 trap (which reverted everything because the argmax never moved).
            val gradedNow = gradedAgree(raw, onRaw)
            if (gradedNow < gradedBest - GRADED_SLIP) { brain.close(); WeightGenome.revertLast(ctx, settings); reverted++; continue }
            gradedBest = maxOf(gradedBest, gradedNow)
            // coherent + non-degrading + not-moving-away ⇒ INSTALL: the directed edit STAYS in W; the next attempt accumulates.
            cur = agree(raw.map { r -> r?.let { ResidencyScore.actionOf(it) } }, onTarget)
            keptAttempts++
            if (cur >= DIRECT_RESIDENT) break        // F3: BINARY residency (argmax agreement) ⇒ graduate. graded is the GATE-3 AIM signal ONLY.
        }
        // F3 FIX (07-12): GRADUATION (dropping the operator's prompt text) requires the BINARY `cur >= DIRECT_RESIDENT`
        // — NOT the graded score. gradedAgree is whole-output token Jaccard, which starts HIGH on the nav DIRECT_PROBES
        // (both σ-off and σ-on emit near-identical JSON), so a `gradedBest >= 0.92` graduation could FALSE-POSITIVE and
        // drop an operator's guidance without real residency (a silent regression: prompt text gone, weights don't carry
        // it). Graded stays the GATE-3 hill-climb KEEP signal (it AIMS the edits); the binary argmax agreement DECIDES
        // whether it's safe to drop the text. Ops that don't reach binary residency stay PARTIAL (edits kept, prompt kept
        // — the R4 guard) until aiming (M3 teacher-capture) makes binary residency real.
        val kind = when {
            cur >= DIRECT_RESIDENT -> Kind.INSTALLED  // BINARY residency ⇒ safe to drop the prompt (graded too JSON-inflatable to be the residency verdict)
            keptAttempts > 0 -> Kind.PARTIAL                                // edits STUCK (W moved) but not fully resident — keep edits AND prompt text
            else -> Kind.TRIED                                              // every attempt broke coherence or degraded unrelated actions (now rare)
        }
        val bytes = keptAttempts * BAKE_BYTES_CAP                          // approximate kept weight bytes (upper bound)
        return Direct(kind, before, maxOf(cur, gradedBest),
            "σ-off agree ${(before * 100).toInt()}%→${(cur * 100).toInt()}%; GRADED ${(gradedBefore * 100).toInt()}%→${(gradedBest * 100).toInt()}% (the aim signal); kept $keptAttempts, reverted $reverted", bytes)
    }
}
