package com.local.deviceagent

import java.io.File
import org.json.JSONObject

/**
 * SelfFab — the self-fabricating agent's OBSERVE → IDENTIFY → (auto) FABRICATE → ADDRESS driver.
 *
 * The agent watches what it computes. When a named function accumulates enough DISTINCT (input -> output) pairs — a
 * recurring deterministic need worth ADDRESSING instead of RE-DERIVING (the ENERGY/addressing thesis, applied to the
 * agent's own capabilities) — SelfFab hands the observed pairs to PfcFab, which fabricates + byte-exact-verifies a LUT
 * circuit and bakes it into filesDir/selffab/. From then on the agent ADDRESSES its own fabricated hardware.
 *
 * SAFETY (§3 HARD BOUNDARY): this only records I/O pairs and writes additive .pfc circuit data (via PfcFab). It NEVER
 * edits weights or app/safety code, NEVER runs host code. It grows the agent's COMPUTE capabilities, never its guardrails.
 */
object SelfFab {

    private const val FILE = "selffab/needs.json"
    private const val THRESHOLD = 4               // distinct pairs before a need is worth fabricating (demo-small)
    private const val MAX_IN_BITS = 20            // keep LUT gate-count bounded

    private class Need {
        val pairs = HashMap<Long, Long>()
        var fabricated = false
    }
    private val needs = HashMap<String, Need>()
    @Volatile private var loaded = false

    private fun bitsFor(v: Long): Int = if (v <= 0) 1 else 64 - java.lang.Long.numberOfLeadingZeros(v)

    private fun load(filesDir: File) {
        if (loaded) return
        loaded = true
        try {
            val f = File(filesDir, FILE)
            if (!f.exists()) return
            val root = JSONObject(f.readText())
            for (fn in root.keys()) {
                val o = root.getJSONObject(fn); val n = Need(); n.fabricated = o.optBoolean("fab", false)
                val p = o.getJSONObject("pairs")
                for (k in p.keys()) n.pairs[k.toLong()] = p.getLong(k)
                needs[fn] = n
            }
        } catch (_: Throwable) {}
    }

    private fun save(filesDir: File) {
        try {
            val root = JSONObject()
            for ((fn, n) in needs) {
                val p = JSONObject(); for ((k, v) in n.pairs) p.put(k.toString(), v)
                root.put(fn, JSONObject().put("fab", n.fabricated).put("pairs", p))
            }
            val f = File(filesDir, FILE); f.parentFile?.mkdirs(); f.writeText(root.toString())
        } catch (_: Throwable) {}
    }

    /** Record one observed (input -> output) the agent computed for function [fn]. Auto-fabricates once it recurs enough. */
    @Synchronized
    fun observe(filesDir: File, fn: String, input: Long, output: Long) {
        load(filesDir)
        val n = needs.getOrPut(fn) { Need() }
        val fresh = !n.pairs.containsKey(input)
        n.pairs[input] = output
        if (fresh && !n.fabricated && n.pairs.size >= THRESHOLD) tryFabricate(filesDir, fn, n)
        save(filesDir)
    }

    private fun tryFabricate(filesDir: File, fn: String, n: Need) {
        val nIn = n.pairs.keys.maxOf { bitsFor(it) }.coerceAtMost(MAX_IN_BITS)
        val nOut = n.pairs.values.maxOf { bitsFor(it) }
        if (n.pairs.keys.any { bitsFor(it) > MAX_IN_BITS }) {
            AgentLog.log("selffab", "need '$fn' skipped: input width > $MAX_IN_BITS bits (LUT too big) — needs a synthesized circuit, not a ROM")
            return
        }
        AgentLog.log("selffab", "IDENTIFIED need '$fn' (${n.pairs.size} recurring pairs, ${nIn}b→${nOut}b) — fabricating a circuit for it")
        val r = PfcFab.fabricate(filesDir, fn, n.pairs, nIn, nOut)
        if (r != null && r.verified) { n.fabricated = true; AgentLog.log("selffab", "need '$fn' is now HARDWARE — the agent addresses it instead of re-deriving") }
    }

    /** Answer [fn]([input]) by ADDRESSING the fabricated circuit if it exists; null if not yet learned/fabricated. */
    @Synchronized
    fun ask(filesDir: File, fn: String, input: Long): Long? {
        load(filesDir)
        val n = needs[fn] ?: return null
        if (!n.fabricated) return null
        return PfcFab.address(filesDir, fn, input)
    }

    @Synchronized
    fun report(filesDir: File): String {
        load(filesDir)
        if (needs.isEmpty()) return "no observed needs yet"
        return needs.entries.joinToString("; ") { (fn, n) ->
            "$fn[${n.pairs.size} pairs]${if (n.fabricated) " ✓fabricated" else " (needs ${THRESHOLD - n.pairs.size} more)"}"
        }
    }
}
