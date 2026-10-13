package com.local.deviceagent

import android.content.Context
import org.json.JSONObject

/**
 * PHASE 2 — σ-OFF OPERATOR RESIDENCY FITNESS (the scorer that tells us WHICH operators to bake, and later whether a bake
 * WORKED). Cheap, on-device, no model writes.
 *
 * The idea: an operator earns a permanent bake only if it's actually DOING something the base weights don't already do.
 * We measure that WITHOUT gradients: for each proven-operator reference the agent banked (`ReferenceStore`), take the
 * action the model emitted WITH the operator (σ-ON = the stored `action`), then REPLAY the exact same rendered prompt with
 * the operator's clause REMOVED (σ-OFF, `AgentBrain.decideFromFrozen`) and see if the model still emits the same action.
 *  - **Low σ-OFF agreement** ⇒ the operator is carrying real work NOT resident in the weights ⇒ a strong BAKE candidate.
 *  - **High agreement** ⇒ the behaviour is already in W ⇒ nothing to gain from baking (or it's already baked).
 * After a Phase-3 bake, re-score: agreement RISING on the held-out tail ⇒ the bake moved the behaviour into W (the keep
 * signal). Scored on the HELD-OUT ~20% tail (`ReferenceStore.split`) so it measures generalization, not memorization.
 *
 * Caveat (honest): the replay is TEXT-ONLY (the banked reference stored the prompt, not the screenshot), so the ABSOLUTE
 * agreement here is approximate. The before/after-bake DELTA is what Phase 3 gates on, and it uses the SAME lossy replay
 * both times, so the image-absence bias cancels. See `AgentBrain.decideFromFrozen`.
 */
object ResidencyScore {

    // SM4 (fuel-fix): each held-out reference costs ONE full main-model σ-off decode (`decideFromFrozen`, ~15-40s).
    // Before always-on VERB/SCHEMA banking a held-out tail was 1-4 refs; now the always-on capabilities accrue MANY
    // references per task, so an uncapped tail would make "Score residency" / a bake beat run tens of minutes. Cap
    // the tail SCORED to the NEWEST N (most representative of current behaviour) so it stays a few minutes, bounded.
    private const val MAX_HELD_OUT_SCORE = 6

    data class OpScore(val op: String, val n: Int, val verbAgree: Double, val exactAgree: Double)

    /** Score one operator on its held-out tail (newest ≤MAX_HELD_OUT_SCORE) for the active fingerprint. Null if it
     *  has no held-out references yet. */
    fun scoreOperator(ctx: Context, brain: AgentBrain, op: String, fingerprint: String): OpScore? {
        val (_, heldOutAll) = ReferenceStore.split(ctx, op, fingerprint)
        if (heldOutAll.isEmpty()) return null
        val heldOut = heldOutAll.takeLast(MAX_HELD_OUT_SCORE)   // newest N — bound the σ-off decode cost
        var scored = 0; var verbHits = 0; var exactHits = 0
        for (ref in heldOut) {
            val prompt = ref.optString("prompt")
            val clause = ref.optString("clause")
            val storedAction = ref.optString("action")
            if (prompt.isBlank() || storedAction.isBlank()) continue
            val onAct = extractAction(storedAction) ?: continue                 // σ-ON = the model's real output WITH the operator
            // σ-OFF = the SAME prompt with the operator clause stripped (a verbatim substring, so removal is exact).
            val sigmaOffPrompt = if (clause.isNotBlank()) prompt.replace(clause, "") else prompt
            val offRaw = brain.decideFromFrozen(sigmaOffPrompt) ?: continue
            val offAct = extractAction(offRaw) ?: continue
            scored++
            val verbMatch = offAct.first == onAct.first
            if (verbMatch) verbHits++
            if (verbMatch && targetsAgree(op, offAct.second, onAct.second)) exactHits++   // W8: Hamming for PREDICT_PIX
        }
        if (scored == 0) return null
        return OpScore(op, scored, verbHits.toDouble() / scored, exactHits.toDouble() / scored)
    }

    /** Score every operator that has banked references on the active fingerprint. */
    fun scoreAll(ctx: Context, brain: AgentBrain): List<OpScore> {
        val fp = ModelStore.activeFingerprint(ctx, SettingsManager(ctx))
        return ReferenceStore.operators(ctx, fp).mapNotNull { scoreOperator(ctx, brain, it, fp) }
    }

    /** U3 — CONTRAST residency: the mirror of [scoreOperator] over the FAILURE references (the learn-from-failure
     *  half we already bank but never consumed). σ-ON = the stored BAD action (the move that regressed / violated
     *  the operator's rule); σ-OFF = the same prompt with the operator clause stripped. HIGH agreement here means
     *  the BAD behaviour is resident in the base weights (a target to push W AWAY from — the sign-flip bake); LOW
     *  means the operator's presence, not W, produced the bad move. Uses ALL failure refs (they're rarer than wins,
     *  so no held-out split). Read-only, no model write; same lossy text-only replay as [scoreOperator], so a
     *  before/after-bake DELTA cancels the image-absence bias. Null if there are no failure references yet. */
    fun scoreContrast(ctx: Context, brain: AgentBrain, op: String, fingerprint: String): OpScore? {
        val failuresAll = ReferenceStore.failuresFor(ctx, op, fingerprint)
        if (failuresAll.isEmpty()) return null
        val failures = failuresAll.takeLast(MAX_HELD_OUT_SCORE)   // SM4: bound the σ-off decode cost like scoreOperator
        var scored = 0; var verbHits = 0; var exactHits = 0
        for (ref in failures) {
            val prompt = ref.optString("prompt")
            val clause = ref.optString("clause")
            val badAction = ref.optString("action")
            if (prompt.isBlank() || badAction.isBlank()) continue
            val badAct = extractAction(badAction) ?: continue                   // σ-ON = the model's real BAD output WITH the operator
            val sigmaOffPrompt = if (clause.isNotBlank()) prompt.replace(clause, "") else prompt
            val offRaw = brain.decideFromFrozen(sigmaOffPrompt) ?: continue
            val offAct = extractAction(offRaw) ?: continue
            scored++
            val verbMatch = offAct.first == badAct.first
            if (verbMatch) verbHits++
            if (verbMatch && targetsAgree(op, offAct.second, badAct.second)) exactHits++   // W8: Hamming for PREDICT_PIX
        }
        if (scored == 0) return null
        return OpScore(op, scored, verbHits.toDouble() / scored, exactHits.toDouble() / scored)
    }

    // W8 (canvas generality): the PREDICT_PIX world model predicts a PERCEPTUAL HASH (PixelMap 64-bit avg-hash) of the
    // next canvas/blind screen — where there are no elements to key on, only pixels. An exact string match on a hash is
    // far too strict (one flipped bit = "wrong"), so PREDICT_PIX agreement is scored by HAMMING DISTANCE: a near-match
    // (≤ tolerance of 64 bits) counts as a correct prediction. This is the ONE comparator branch that makes the world
    // model element-INDEPENDENT (the MiniCPM/AgentCPM harvest — operate on the canvas, not just the accessibility tree).
    private const val PIX_HAMMING_TOL = 12   // of 64 bits — a close perceptual-hash match counts as agreement

    /** Whether two prediction targets AGREE, op-aware: PREDICT_PIX compares its hex pixel-hashes by Hamming distance
     *  (near-match = agree); every other op uses exact equality (unchanged behaviour for VERB/SCHEMA/PREDICT/…). */
    private fun targetsAgree(op: String, a: String, b: String): Boolean {
        if (op.equals(ReasoningOperators.PREDICT_PIX, ignoreCase = true)) {
            val ha = a.toLongOrNull(16); val hb = b.toLongOrNull(16)
            if (ha != null && hb != null) return PixelMap.distance(ha, hb) <= PIX_HAMMING_TOL
        }
        return a == b
    }

    /** PART R (v3 direct install): public (verb, target) extractor so `ScaleBake.bakeOperatorDirect` can compare
     *  a canned probe's σ-ON vs σ-OFF output with the SAME proven parser the residency scorer uses. Exact-equality
     *  agreement is fine for the defined-operator install set (no PREDICT_PIX there); the op-aware Hamming path
     *  stays internal to [targetsAgree]. */
    fun actionOf(raw: String): Pair<String, String>? = extractAction(raw)

    /** (verb, primaryTarget) from an action JSON blob, or from free text that CONTAINS one (σ-off replay output). */
    private fun extractAction(s: String): Pair<String, String>? {
        // Scan each balanced top-level {…} object in order and return the FIRST that carries a non-blank "action". A
        // reasoning-shaped object (e.g. an operator's own `Output := {named Sub, …}` under σ-ON) can precede the action
        // object, so taking literally the first object would misparse it; requiring an "action" key skips that noise.
        for (blob in jsonObjects(s)) {
            val hit = try {
                val o = JSONObject(blob)
                val verb = o.optString("action").lowercase().trim()
                if (verb.isBlank()) null
                else {
                    // Whatever field carries the action's target — first non-blank wins; truncated so trivial text
                    // differences in a long message don't dominate the exact-match signal.
                    val target = listOf("id", "text", "label", "that", "message", "app", "query", "cell")
                        .firstNotNullOfOrNull { k -> o.optString(k).takeIf { it.isNotBlank() }?.take(40)?.lowercase()?.trim() } ?: ""
                    verb to target
                }
            } catch (_: Exception) { null }
            if (hit != null) return hit
        }
        return null
    }

    /** Every balanced top-level `{…}` object in [s], in order (brace-matched, string/escape aware). Handles output where
     *  the action JSON is surrounded by — or preceded by — other generated text/objects (no streaming action-stop on the
     *  "plan" phase, or a σ-ON reasoning object ahead of the action). */
    private fun jsonObjects(s: String): List<String> {
        val out = ArrayList<String>()
        var i = s.indexOf('{')
        while (i >= 0) {
            var depth = 0; var inStr = false; var esc = false; var end = -1
            for (j in i until s.length) {
                val c = s[j]
                if (inStr) {
                    if (esc) esc = false
                    else if (c == '\\') esc = true
                    else if (c == '"') inStr = false
                } else when (c) {
                    '"' -> inStr = true
                    '{' -> depth++
                    '}' -> { depth--; if (depth == 0) { end = j; break } }
                }
            }
            if (end < 0) break                          // unbalanced tail — stop
            out.add(s.substring(i, end + 1))
            i = s.indexOf('{', end + 1)
        }
        return out
    }
}
