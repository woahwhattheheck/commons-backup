package com.local.deviceagent

import android.content.Context
import org.json.JSONObject

/**
 * THE REGIME KEY (research round 2 keystone, rated 10) — ONE per-step situation signature that every lever can route
 * on AND the acceptance oracle can attribute to.
 *
 * The problem it fixes: today every knob bins the situation its OWN way — adaptive_decode reads model-confidence, the
 * RAM-operator reads a COMPACT/FULL posture, PromptBudget reads dense/lean, the acceptance oracle attributes to
 * (operator, σ, flag), MechanismRouter attributes to a coarse failure-class + a rolling rate. Because there is no
 * COMMON key, credit is smeared across incompatible partitions and no lever can co-optimize with another. On a device
 * with a tiny live sample budget that is the thing starving the whole self-improvement thesis.
 *
 * The fix: derive ONE small enumerable code each step from signals the loop ALREADY computes — the task mode, the
 * world-model EDGE state (proven / exploratory / stalled / novel), and the RAM posture — bounded to a few dozen
 * regimes so per-regime counts actually accumulate. It is deliberately NOT app-specific (app specialization is the
 * per-app σ store's job); the regime is the GENERAL situation class that lets levers share credit. §2/§12-clean: it
 * is a telemetry+context KEY, never an action — nothing here selects a move.
 *
 * This first cut computes the key, logs it, and keeps a per-regime step-advance ledger (the substrate the σ pipeline,
 * the compute router, and the oracle re-key ride on next). Cheap Kotlin, zero inference.
 */
object RegimeKey {
    private const val PREF = "regime_ledger"
    private const val MAX_REGIMES = 64

    /** The per-step regime code, e.g. "explorer/proven/C". Inputs are all live at decide time (AgentOrchestrator).
     *  Order of precedence for the edge state: a stall dominates (recovery), then low-confidence exploration, then a
     *  proven route, else novel. Kept to modes×edges×ram ≈ a few dozen so counts stay dense. */
    fun compute(mode: String, provenRoute: Boolean, compact: Boolean, stalled: Boolean, lowConf: Boolean): String {
        val edge = when { stalled -> "stall"; lowConf -> "explore"; provenRoute -> "proven"; else -> "novel" }
        return "${mode.lowercase()}/$edge/${if (compact) "C" else "F"}"
    }

    /** Credit ONE step to its regime: n++ and adv++ if the step advanced (M>0 / reached a new state). The substrate
     *  the oracle/σ/compute levers will read per-regime. Best-effort + capped. */
    @Synchronized
    fun recordStep(c: Context, regime: String, advanced: Boolean) {
        if (regime.isBlank()) return
        try {
            val p = c.getSharedPreferences(PREF, Context.MODE_PRIVATE)
            val root = JSONObject(p.getString("r", "{}") ?: "{}")
            val cell = root.optJSONObject(regime) ?: JSONObject().also { root.put(regime, it) }
            cell.put("n", cell.optInt("n", 0) + 1).put("adv", cell.optInt("adv", 0) + if (advanced) 1 else 0)
            if (root.length() > MAX_REGIMES) root.keys().asSequence().firstOrNull { it != regime }?.let { root.remove(it) }
            p.edit().putString("r", root.toString()).apply()
        } catch (_: Throwable) {}
    }

    /** Advance-rate (0..1) for a regime, with the count, or null if unseen — for a lever that wants to know "in THIS
     *  situation, how often does a step actually advance?" (e.g. glide vs spend more compute). */
    fun rate(c: Context, regime: String): Pair<Double, Int>? = try {
        val cell = JSONObject(c.getSharedPreferences(PREF, Context.MODE_PRIVATE).getString("r", "{}") ?: "{}")
            .optJSONObject(regime) ?: return null
        val n = cell.optInt("n", 0)
        if (n <= 0) null else (cell.optInt("adv", 0).toDouble() / n) to n
    } catch (_: Throwable) { null }

    /** The single WORST regime (lowest advance rate) with at least [minN] samples, or null — the situation the
     *  agent struggles in most. Returns (regime, advanceRate 0..1, count). This is what U2's router routes on:
     *  a persistently-low worst regime is the signal to throw the best-credited mechanism at it (or, when it stays
     *  stuck across a real sample, escalate to adding capacity). Zero inference; reads the same ledger as [rate]. */
    fun worst(c: Context, minN: Int = 4): Triple<String, Double, Int>? = try {
        val root = JSONObject(c.getSharedPreferences(PREF, Context.MODE_PRIVATE).getString("r", "{}") ?: "{}")
        root.keys().asSequence().map { it to root.optJSONObject(it)!! }
            .map { (k, cell) ->
                val n = cell.optInt("n", 0)
                Triple(k, cell.optInt("adv", 0).toDouble() / n.coerceAtLeast(1), n)
            }
            .filter { it.third >= minN }
            .minByOrNull { it.second }
    } catch (_: Throwable) { null }

    /** Compact owner readout: the regimes seen + their advance rate, worst-first (where the agent struggles most). */
    fun readout(c: Context, max: Int = 6): String = try {
        val root = JSONObject(c.getSharedPreferences(PREF, Context.MODE_PRIVATE).getString("r", "{}") ?: "{}")
        root.keys().asSequence().map { it to root.optJSONObject(it)!! }.filter { it.second.optInt("n", 0) > 0 }
            .sortedBy { it.second.optInt("adv", 0).toDouble() / it.second.optInt("n", 1) }
            .take(max).joinToString(" ") {
                val n = it.second.optInt("n", 1); val a = it.second.optInt("adv", 0)
                "${it.first}=${a * 100 / n}%/${n}"
            }
    } catch (_: Throwable) { "" }

    /** Wipe the regime ledger (called by the owner's "Clear all memory" — this lives in its own prefs, not
     *  AgentMemory's, so a memory wipe must reach it explicitly or a "fresh" agent keeps its learned regimes). */
    fun clear(c: Context) { try { c.getSharedPreferences(PREF, Context.MODE_PRIVATE).edit().clear().apply() } catch (_: Throwable) {} }
}
