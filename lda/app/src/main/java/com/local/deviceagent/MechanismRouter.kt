package com.local.deviceagent

import android.content.Context
import org.json.JSONObject

/**
 * G2 / A6 — THE MECHANISM ROUTER (research completeness gap #2, verified against the tree).
 *
 * The self-improvement stack — self_calibrate, operator-genesis, self_evolve (crystallize), self_grow — each
 * fires on its OWN fixed cadence with only the `evolving` interlock. NOBODY reads the FAILURE TYPE and routes to
 * the mechanism that actually addresses it, and no bandit tracks which mechanism moved the ONE metric. So the
 * device can be grinding self_grow (add capacity) when the real problem is miscalibration, or perturbing weights
 * when it's simply MISSING a capability an operator would supply. This is the arbiter.
 *
 * Two jobs, both pure telemetry+advice (§2/§12): it NEVER executes a mechanism or an action — it recommends WHICH
 * mechanism the idle beat should prioritise, and it CREDITS each mechanism by the A1 acceptance-oracle rate delta
 * that followed it firing, so over time the router learns which mechanism earns its keep on THIS device. Acting
 * on the recommendation is a SOFT, flag-gated bias in AgentService (the cadences still eventually run everything,
 * so no mechanism is ever starved); off => the beats fire exactly as before (byte-identical).
 *
 * Grounded in the real failure taxonomy classifyFailure() already produces (NAVIGATION / PERCEPTION / CAPACITY /
 * PERMISSION / LOOP / …), read from TaskHistory's per-task failureClass. Storage: its own small SharedPreferences
 * (a rolling credit ledger), never the model file — this is a scheduler, not a self-editor.
 */
object MechanismRouter {
    private const val PREF = "mechanism_router"
    private const val CREDIT = "credit"      // {mechanism: {n, sumDelta}}  realized oracle-rate delta after it fired
    private const val LAST = "lastFired"     // the mechanism that fired most recently + the oracle rate at that time

    // The FULL mechanism vocabulary the router arbitrates between (the strings AgentService's beats gate on). The
    // first four have live idle beats; CRYSTALLIZE (F2 Operator Crystallizer) + MERGE (N7 Genome-Merge) are named
    // here so the router already speaks the full set — they become routable the moment their beats land.
    const val CALIBRATE = "calibrate"        // self_calibrate: the operator posture is mis-tuned to the device/app
    const val GENESIS = "genesis"            // operator-genesis: a recurring wrong-call needs a NEW operator authored
    const val EVOLVE = "evolve"              // self_evolve/directed BAKE: proven-exact gains are ready to move into W
    const val BAKE = "bake"                  // directed ScaleBake (rides the EVOLVE beat today — the real crystalliser)
    const val GROW = "grow"                  // self_grow: a capability CEILING (stuck everywhere → add MLP capacity)
    const val DREAM = "dream"                // DreamFlywheel idle consolidation (un-gated: cheap + always useful)
    const val CRYSTALLIZE = "crystallize"    // F2 ROME closed-form into grown rows (beat pending)
    const val MERGE = "merge"                // N7 TIES/DARE genome merge (beat pending)
    const val NONE = "none"

    private const val REGIME_MIN_SAMPLES = 5        // a worst regime needs this many steps before it can route
    private const val REGIME_STRUGGLE_RATE = 0.50   // advance-rate below this in the worst regime = struggling
    private const val REGIME_STAGNANT_SAMPLES = 18  // struggling across this many steps = a capability CEILING → GROW

    private fun prefs(c: Context) = c.getSharedPreferences(PREF, Context.MODE_PRIVATE)

    /** Wipe the router's credit ledger (owner's "Clear all memory" — own prefs, not AgentMemory's, so a
     *  memory wipe must reach it explicitly). Guarded. */
    fun clear(c: Context) { try { prefs(c).edit().clear().apply() } catch (_: Throwable) {} }

    /** Map ONE failure class to the mechanism that addresses it. The taxonomy strings come from
     *  AgentOrchestrator.classifyFailure (CAPACITY/PERMISSION/NAVIGATION/INPUT/VISIBILITY/TIMING/RECOGNITION),
     *  matched loosely so a taxonomy tweak doesn't silently break routing. Note GROW is deliberately NOT a
     *  failure-class response — self_grow ADDS parameters (more RAM), so it's the wrong answer to an OOM/CAPACITY
     *  stop; GROW is reserved for the MetaFitness capability-ceiling escalation in [recommend]. */
    fun mechanismFor(failureClass: String): String {
        val f = failureClass.lowercase()
        return when {
            // A recurring "couldn't make the right call" / a genuinely missing capability → author a new operator.
            f.contains("recognition") || f.contains("missing") || f.contains("capab") -> GENESIS
            // Perception / navigation / timing / loop / visibility / input / OOM-posture → re-tune the operating
            // posture (self_calibrate is the general in-task self-improvement response to these).
            f.contains("perception") || f.contains("calibr") || f.contains("navigation") || f.contains("loop") ||
                f.contains("timing") || f.contains("visibility") || f.contains("input") || f.contains("capacity") -> CALIBRATE
            // PERMISSION (owner must sign in / grant) and anything unclassified → no self-mechanism helps.
            else -> NONE
        }
    }

    /** Recommend the mechanism the idle beat should PRIORITISE now — the loop-closure heart of U2. Deterministic,
     *  legible, worst-first: (1) if recent failures cluster on one class, route to its mechanism; (2) else if the
     *  oracle shows a healthy CONVERGED state, the gains are worth CRYSTALLISING (EVOLVE — the beat that runs the
     *  directed bake); (3) else consult the RegimeKey ledger — the agent may be persistently STRUGGLING in its
     *  worst situation-regime with no clear failure cluster: MetaFitness escalates a regime that stays stuck across
     *  a real sample to GROW (a capability ceiling, not a mis-tune — add capacity), otherwise it throws the
     *  best-credited mechanism at the weak regime (keep the loop learning where it's weakest); (4) else NONE.
     *  Returns (mechanism, one-line reason) for the [router] log. */
    fun recommend(c: Context): Pair<String, String> {
        return try {
            val recent = TaskHistory.list(c).asSequence().filter { !it.gauntlet && it.failureClass.isNotBlank() }
                .take(8).map { it.failureClass }.toList()
            if (recent.isNotEmpty()) {
                val top = recent.groupingBy { mechanismFor(it) }.eachCount()
                    .filterKeys { it != NONE }.maxByOrNull { it.value }
                if (top != null && top.value >= 2)
                    return top.key to "recent failures cluster on ${top.key} (${top.value}/${recent.size})"
            }
            val (n, s, pct) = TaskHistory.rollingSuccessRate(c, 20)
            if (n >= 8 && pct >= 70) return EVOLVE to "converged: $s/$n=$pct% clean — crystallise the proven gains"
            // U2 RegimeKey consumption: no failure cluster and not yet converged, but the agent may be stuck in its
            // worst situation. Don't idle — target where it's weakest (or escalate a genuine capability ceiling).
            RegimeKey.worst(c)?.let { (regime, adv, cnt) ->
                if (cnt >= REGIME_MIN_SAMPLES && adv < REGIME_STRUGGLE_RATE) {
                    val pctAdv = (adv * 100).toInt()
                    if (cnt >= REGIME_STAGNANT_SAMPLES)
                        return GROW to "regime $regime stuck at $pctAdv%/$cnt across a real sample — capability ceiling, add capacity"
                    bestCreditedMechanism(c)?.let { best ->
                        return best to "regime $regime weak ($pctAdv%/$cnt) — apply best-credited $best"
                    }
                }
            }
            NONE to "no clear failure cluster and not yet converged — hold"
        } catch (_: Throwable) { NONE to "router error — hold" }
    }

    /** The mechanism with the highest AVERAGE realized oracle-rate delta (its earned keep), or null if none has a
     *  settled sample — "throw the best mechanism at a struggling situation." Only returns one whose average is
     *  non-negative (never recommend a mechanism that has, on average, HURT the metric on this device). */
    private fun bestCreditedMechanism(c: Context): String? = try {
        val root = JSONObject(prefs(c).getString(CREDIT, "{}") ?: "{}")
        root.keys().asSequence().map { it to root.optJSONObject(it)!! }
            .filter { it.second.optInt("n", 0) > 0 && it.second.optInt("sumDelta", 0) >= 0 }
            .maxByOrNull { it.second.optInt("sumDelta", 0).toDouble() / it.second.optInt("n", 1) }
            ?.first
    } catch (_: Throwable) { null }

    /** Record that [mechanism] just fired, stamping the oracle rate at fire time so the NEXT call can attribute
     *  the delta to it (the bandit's reward signal). Best-effort. */
    fun markFired(c: Context, mechanism: String, oracleRatePct: Int) {
        try {
            // First settle any pending credit from the previously-fired mechanism against the new rate.
            settleCredit(c, oracleRatePct)
            prefs(c).edit().putString(LAST, JSONObject().put("m", mechanism).put("rate", oracleRatePct).toString()).apply()
        } catch (_: Throwable) {}
    }

    /** Attribute the change in the oracle rate since the last-fired mechanism to that mechanism (its realized
     *  reward). Called at the start of markFired and can be called standalone at a task end. */
    fun settleCredit(c: Context, currentRatePct: Int) {
        try {
            val lastRaw = prefs(c).getString(LAST, null) ?: return
            val last = JSONObject(lastRaw)
            val m = last.optString("m"); val was = last.optInt("rate", -1)
            if (m.isBlank() || was < 0) return
            val delta = currentRatePct - was
            val root = JSONObject(prefs(c).getString(CREDIT, "{}") ?: "{}")
            val cell = root.optJSONObject(m) ?: JSONObject().also { root.put(m, it) }
            cell.put("n", cell.optInt("n", 0) + 1).put("sumDelta", cell.optInt("sumDelta", 0) + delta)
            prefs(c).edit().putString(CREDIT, root.toString()).remove(LAST).apply()
        } catch (_: Throwable) {}
    }

    /** A compact one-line readout of which mechanism has earned its keep (average oracle-rate delta after it
     *  fired), for the owner + the [router] log. "" until a mechanism has a settled sample. */
    fun readout(c: Context): String {
        return try {
            val root = JSONObject(prefs(c).getString(CREDIT, "{}") ?: "{}")
            if (root.length() == 0) return ""
            root.keys().asSequence().map { it to root.optJSONObject(it)!! }
                .filter { it.second.optInt("n", 0) > 0 }
                .sortedByDescending { it.second.optInt("sumDelta", 0).toDouble() / it.second.optInt("n", 1) }
                .joinToString(" ") {
                    val n = it.second.optInt("n", 1); val avg = it.second.optInt("sumDelta", 0).toDouble() / n
                    "${it.first} ${if (avg >= 0) "+" else ""}${String.format("%.1f", avg)}%/${n}"
                }
        } catch (_: Throwable) { "" }
    }
}
