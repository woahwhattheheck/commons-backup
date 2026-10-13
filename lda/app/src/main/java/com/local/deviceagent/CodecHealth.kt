package com.local.deviceagent

import android.content.Context
import org.json.JSONObject

/**
 * A1 / W7 — VICReg-STYLE CODEC-HEALTH GUARD (the anti-collapse net for the world-model bake).
 *
 * VICReg (Bardes/Ponce/LeCun) keeps a self-supervised representation from COLLAPSING by regularizing the VARIANCE of
 * the embedding pool — if every sample maps to (nearly) the same vector, the representation has degenerated and there
 * is nothing to learn. Our world model faces the exact same failure: if the banked PREDICT references have collapsed
 * to a single target screen-class (e.g. everything classifies GENERIC, or one class dominates the pool), a bake would
 * only entrench that degenerate "predict the same thing always" mapping — a fake gain that hurts real prediction.
 *
 * So this is a PRE-BAKE gate: before the world-model bake writes anything, check the VARIANCE of the reference pool's
 * targets. A collapsed pool (too few distinct target classes, or one class dominating) is REFUSED — the bake is
 * skipped with a log, no weight touched. Cheap (reads the already-banked references), read-only, no model call.
 * Applies to the WORLD_MODEL pool (PREDICT / PREDICT_FLOW); harmless elsewhere. §2/§3-clean.
 */
object CodecHealth {
    private const val MIN_TO_JUDGE = 4      // fewer than this = too early to call collapse; never block initial banking
    private const val DOMINATE_FRAC = 0.9   // one target class covering ≥90% of the pool = collapsed (no variance)

    /** The predicted target screen-class from a banked reference's action (`{"action":"predict","id":"<class>",…}`). */
    private fun targetClass(ref: JSONObject): String? =
        try { Regex("\"id\"\\s*:\\s*\"([^\"]*)\"").find(ref.optString("action"))?.groupValues?.get(1)?.trim()?.takeIf { it.isNotBlank() } }
        catch (_: Exception) { null }

    /** Has the reference pool for [op] COLLAPSED (VICReg variance ≈ 0)? True ⇒ refuse the bake. Conservative: with too
     *  few references, or on any parse error, returns false (never blocks legitimate early banking / a healthy pool). */
    fun collapsed(ctx: Context, op: String, fingerprint: String): Boolean {
        return try {
            val refs = ReferenceStore.forOperator(ctx, op, fingerprint)
            if (refs.size < MIN_TO_JUDGE) return false
            val targets = refs.mapNotNull { targetClass(it) }
            if (targets.size < MIN_TO_JUDGE) return false
            val distinct = targets.toSet().size
            if (distinct < 2) return true                                  // one target only = fully collapsed
            val topFrac = targets.groupingBy { it }.eachCount().values.max().toDouble() / targets.size
            topFrac > DOMINATE_FRAC                                         // one class swamps the pool = near-collapse
        } catch (_: Exception) { false }
    }

    /** True when [op] is a world-model capability the codec-health gate applies to. */
    fun applies(op: String): Boolean = op.uppercase() in ReasoningOperators.WORLD_MODEL
}
