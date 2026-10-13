package com.local.deviceagent

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/**
 * A4 — THE DREAMING FLYWHEEL (owner: "it dreams about using itself and wakes up sharper"; research: idle+charging
 * replay self-play over the recorded world-model, zero live taps).
 *
 * Directly answers "we update often, but the PC is at the office": the phone improves itself in its OWN idle gaps
 * instead of only during live tasks. In the idle-and-charging gap the agent REPLAYS its own world-model
 * (`AgentMemory.provenArcSample` — the SAME TRANS edges routesFrom/lookaheadFrom read, PROVEN bar n>=2/miss==0) as a
 * simulator and CONSOLIDATES the proven corridors it has actually walked — with ZERO live taps and ZERO writes to
 * the live task-success oracle (A1 stays honest: real agent-driven outcomes only, never inflated by a dream).
 *
 * WHAT IT PRODUCES (this build — the deterministic, zero-inference consolidation core, safe + honest + buildable
 * precisely now): a rolling DREAM QUEUE of proven corridors + a compact DREAM DIGEST that the self-evolve seed
 * (INV-59/65) folds in when both flags are on — so idle dreaming shapes WHERE the weight forge nudges (toward
 * proven-corridor directions) rather than a blind walk. "Sharp-wave-ripple replay": a winning arc compressed into
 * one offline reinforcement of σ's direction, no gradients.
 *
 * The stronger form — model-in-the-loop self-play (the main model re-DECIDES on a remembered screen and is scored
 * against the remembered proven successor) — rides on this substrate and on an on-device log (§16 token-frugality:
 * a heavier idle inference pass is added only when a log shows it earns its keep). The scaffold here makes that a
 * one-method add; nothing about it is blocked.
 *
 * SAFETY (§3/§14-clean): owner-gated (`dreaming` flag, default OFF), owner-INITIATED only (rides the auto-mode idle
 * chain — no boot persistence, a reboot ends it), idle + charging + cadence-bounded, ZERO live actions (it only
 * reads memory and writes its own small store), and it never touches the model file (that's self-evolve's job; the
 * dream only SEEDS it). Nothing leaves the device. §2-clean: it consolidates perception the model later reads; it
 * never selects an action.
 */
object DreamFlywheel {
    private const val PREF = "dream_flywheel"
    private const val QUEUE = "queue"          // JSONArray of {arc, time} — proven corridors consolidated in idle
    private const val COUNT = "dreams"         // lifetime dream-beat counter (telemetry)
    private const val MAX_DREAMS = 24          // rolling window of consolidated corridors (bounded, like every store)

    private fun prefs(c: Context) = c.getSharedPreferences(PREF, Context.MODE_PRIVATE)

    /** One dream beat (the CALLER gates on flag + idle + charging + cadence). Samples proven corridors from the
     *  world-model and consolidates them into the dream queue; logs `[dream]`. Zero inference, zero live taps.
     *  Returns true if it consolidated at least one corridor (nothing proven yet ⇒ false, a no-op). [seed] varies
     *  which corner of the map is dreamt each beat. */
    @Synchronized
    fun maybeDream(c: Context, seed: Long): Boolean {
        return try {
            val arcs = AgentMemory.provenArcSample(c, maxArcs = 4, depth = 3, seed = seed)
            if (arcs.isEmpty()) { AgentLog.log("dream", "no proven corridors yet — nothing to consolidate"); return false }
            val q = try { JSONArray(prefs(c).getString(QUEUE, "[]")) } catch (_: Throwable) { JSONArray() }
            val now = seed                                     // a stamp that varies per beat (no wall-clock in this layer)
            arcs.forEach { q.put(JSONObject().put("arc", it).put("time", now)) }
            while (q.length() > MAX_DREAMS) q.remove(0)
            val n = prefs(c).getInt(COUNT, 0) + 1
            prefs(c).edit().putString(QUEUE, q.toString()).putInt(COUNT, n).apply()
            AgentLog.log("dream", "consolidated ${arcs.size} proven corridor(s) [beat #$n]: " + arcs.joinToString(" | ").take(160))
            true
        } catch (e: Throwable) { AgentLog.log("dream", "dream beat error: ${e.message}"); false }
    }

    /** A compact digest of recently-dreamt proven corridors — folded into the self-evolve/grow SEED (when
     *  `dreaming` is on) so idle dreaming steers WHERE the weight forge nudges (proven-corridor directions), the
     *  gradient-free "wakes up sharper" link. "" when nothing has been dreamt yet. Capped small (it rides a seed). */
    @Synchronized
    fun dreamDigest(c: Context, max: Int = 6): String {
        return try {
            val q = JSONArray(prefs(c).getString(QUEUE, "[]") ?: "[]")
            if (q.length() == 0) return ""
            (q.length() - 1 downTo maxOf(0, q.length() - max)).mapNotNull { q.optJSONObject(it)?.optString("arc") }
                .filter { it.isNotBlank() }.joinToString(" ; ").take(240)
        } catch (_: Throwable) { "" }
    }

    /** Lifetime dream-beat count (owner telemetry). */
    @Synchronized
    fun dreamCount(c: Context): Int = try { prefs(c).getInt(COUNT, 0) } catch (_: Throwable) { 0 }

    @Synchronized
    fun clear(c: Context) { try { prefs(c).edit().clear().apply() } catch (_: Throwable) {} }
}
