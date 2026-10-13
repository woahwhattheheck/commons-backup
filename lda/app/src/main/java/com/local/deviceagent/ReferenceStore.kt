package com.local.deviceagent

import android.content.Context
import org.json.JSONObject
import java.io.File

/**
 * REFERENCE STORE — Phase 1 of operator→weight baking: the self-labelled SUPERVISION FEED.
 *
 * When the agent's OWN decision worked — a non-DIRECT operator's rule HELD and the step ADVANCED (M>0) — we persist the
 * exact evidence of that success: {operator, model fingerprint, screen signature, the EXACT rendered model input, the
 * emitted action}. This is the dataset the later phases score residency against: does the model still emit the same
 * action with the operator turned OFF (behaviour resident in the weights) vs ON? So it is captured self-supervised from
 * the agent's own PROVEN screens — never scraped, never external (§3-clean: nothing here comes from off-screen data, and
 * a hostile screen cannot make something PROVEN, so it cannot poison the feed).
 *
 * Append-only JSONL in filesDir, capped + rolling (mirrors `TrainingData`). Nothing leaves the device. The newest ~20%
 * is reserved as a HELD-OUT tail (`split`) so Phase 2 scores generalization, not memorization. NO model writes here.
 * Read-only w.r.t. the running agent: every call is guarded, so a capture failure can never touch a decision or action.
 */
object ReferenceStore {
    private const val FILE = "reference_data.jsonl"
    private const val MAX_BYTES = 8_000_000          // ~ hundreds of full-prompt references; the owner's dedicated device has GBs
    private const val MAX_PROMPT = 16_000            // a dense action prompt is ~4096 tok ≈ 12-16K chars; keep it WHOLE for faithful replay
    private const val MAX_ACTION = 1_200

    private fun file(c: Context) = File(c.filesDir, FILE)

    /** Record one operator supervision example. Guarded + capped; a failure is swallowed (never affects the agent).
     *  `clause` = the operator clause embedded in `prompt` (verbatim substring), so Phase 2 can replay σ-off by removing it.
     *  `pos` = whether this is a PROVEN-WIN reference (true, the default) or a FAILURE/CONTRAST reference (false — the
     *  operator's move regressed or violated its own rule). LEARN-FROM-FAILURE (owner): the success feed alone banks
     *  nothing on a failed run, so the model can't learn from a mistake it never recorded — the negative half is the
     *  CONTRAST the off-device failure-contrast recipe + a contrastive residency signal consume. Still injection-immune:
     *  the label is the agent's OWN measured outcome (advance vs regression/rule-kickback), never on-screen text, and the
     *  worst a negative can ever drive is a "push AWAY from this action here" bake — never an executed action. */
    @Synchronized
    fun record(c: Context, op: String, fingerprint: String, sig: Int, prompt: String, action: String, m: Int, clause: String = "", pos: Boolean = true) {
        try {
            if (op.isBlank() || op == ReasoningOperators.DIRECT || prompt.isBlank()) return
            val o = JSONObject()
                .put("op", op.uppercase())
                .put("fp", fingerprint)
                .put("sig", sig)
                .put("m", m)
                .put("pos", pos)                      // true = proven win; false = failure/contrast (the learn-from-failure half)
                .put("ts", System.currentTimeMillis())
                .put("action", action.take(MAX_ACTION))
                .put("clause", clause.take(8000))     // the injected operator clause (full-depth σ), for the Phase-2 σ-off replay — must not clip or the replace-strip no-ops and σ-off==σ-on (false "resident")
                .put("prompt", prompt.take(MAX_PROMPT))
            val f = file(c)
            f.appendText(o.toString() + "\n")            // append is O(1); never read the whole file back on the hot path
            if (f.length() > MAX_BYTES) trim(f)
            AgentLog.log("selfmodel", (if (pos) "reference +1: " else "failure-reference +1: ") + "$op m=$m sig=$sig")
        } catch (_: Exception) {}
    }

    /** Drop the oldest quarter when over the byte cap (same idiom as TrainingData.trim), so the feed rolls forward. */
    private fun trim(f: File) {
        try {
            val lines = f.readLines()
            if (lines.size > 8) f.writeText(lines.drop(lines.size / 4).joinToString("\n", "", "\n"))
        } catch (_: Exception) {}
    }

    private fun lineCount(f: File): Int = try { if (f.exists()) f.readLines().count { it.isNotBlank() } else 0 } catch (_: Exception) { 0 }
    fun count(c: Context): Int = lineCount(file(c))

    /** The PROVEN-WIN references for one operator on the ACTIVE fingerprint, oldest→newest. (Phase 2's σ-off scorer reads
     *  this — it must score against GOOD actions, so failure/contrast rows are excluded here. Old rows with no `pos`
     *  field predate learn-from-failure and are all wins ⇒ default true, so nothing is lost.) */
    fun forOperator(c: Context, op: String, fingerprint: String): List<JSONObject> {
        return try {
            val f = file(c); if (!f.exists()) return emptyList()
            val want = op.uppercase()
            f.readLines().mapNotNull { ln -> if (ln.isBlank()) null else try { JSONObject(ln) } catch (_: Exception) { null } }
                .filter { it.optString("op") == want && it.optString("fp") == fingerprint && it.optBoolean("pos", true) }
        } catch (_: Exception) { emptyList() }
    }

    /** The FAILURE/CONTRAST references for one operator (the operator's move regressed or violated its rule). The
     *  learn-from-failure half: the off-device failure-contrast recipe + a contrastive residency signal consume these to
     *  push the weights AWAY from a proven-bad move. Kept separate from forOperator so a negative can never leak into the
     *  σ-off SUCCESS scoring. */
    fun failuresFor(c: Context, op: String, fingerprint: String): List<JSONObject> {
        return try {
            val f = file(c); if (!f.exists()) return emptyList()
            val want = op.uppercase()
            f.readLines().mapNotNull { ln -> if (ln.isBlank()) null else try { JSONObject(ln) } catch (_: Exception) { null } }
                .filter { it.optString("op") == want && it.optString("fp") == fingerprint && !it.optBoolean("pos", true) }
        } catch (_: Exception) { emptyList() }
    }

    /** Counts of (proven-win, failure/contrast) references on the active fingerprint — surfaced in the residency dump so
     *  the owner SEES failure being banked, not just success. */
    fun counts(c: Context, fingerprint: String): Pair<Int, Int> {
        return try {
            val f = file(c); if (!f.exists()) return 0 to 0
            var pos = 0; var neg = 0
            f.readLines().forEach { ln ->
                if (ln.isNotBlank()) try {
                    val o = JSONObject(ln)
                    if (o.optString("fp") == fingerprint) { if (o.optBoolean("pos", true)) pos++ else neg++ }
                } catch (_: Exception) {}
            }
            pos to neg
        } catch (_: Exception) { 0 to 0 }
    }

    /** Split an operator's references into (train, held-out newest) so Phase 2 scores generalization. The tail is the
     *  newest slice — most representative of current behaviour, never seen while tuning against the train set.
     *  P0.2 (07-10 reframe): an operator is a KNOWN operational state (valid by construction), so residency is a
     *  SELECTION + non-degradation MEASUREMENT, not a proof-of-validity gate — it needs only enough held-out to read
     *  the σ-on/σ-off delta, not a large statistical sample. So the tail is a ~third (not a fifth) and appears at ≥4
     *  refs (not 5): with `ScaleBake.MIN_HELDOUT=2` a bake becomes reachable at ~6 refs on one operator, not ~15 —
     *  the fix for the starved pipeline (device log: `no scored operators`, `delta=0B`) that does NOT weaken the
     *  keep-gate (the AcceptanceOracle non-degradation check is the real guard). */
    fun split(c: Context, op: String, fingerprint: String): Pair<List<JSONObject>, List<JSONObject>> {
        val all = forOperator(c, op, fingerprint)
        if (all.size < 4) return all to emptyList()          // too few to hold any out; keep them all as train
        val cut = all.size - (all.size / 3).coerceAtLeast(1)  // newest ~third held out (enough to read the σ-delta)
        return all.subList(0, cut) to all.subList(cut, all.size)
    }

    /** Wipe the whole supervision feed (all banked references, every fingerprint). Called by the owner's
     *  "Clear all memory" so a memory wipe reaches the SM4 VERB/SCHEMA + world-model PREDICT bank too — it
     *  was silently surviving before (it lives in its own file, not AgentMemory prefs). Guarded. */
    @Synchronized
    fun clear(c: Context) { try { file(c).delete() } catch (_: Exception) {} }

    /** The distinct operators that have banked references on the active fingerprint (Phase 2 iterates these). */
    fun operators(c: Context, fingerprint: String): Set<String> {
        return try {
            val f = file(c); if (!f.exists()) return emptySet()
            f.readLines().mapNotNull { ln -> if (ln.isBlank()) null else try { JSONObject(ln) } catch (_: Exception) { null } }
                .filter { it.optString("fp") == fingerprint }.map { it.optString("op") }.filter { it.isNotBlank() }.toSet()
        } catch (_: Exception) { emptySet() }
    }
}
