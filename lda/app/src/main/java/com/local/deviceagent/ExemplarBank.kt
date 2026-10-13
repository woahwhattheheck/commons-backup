package com.local.deviceagent

import android.content.Context
import org.json.JSONObject
import java.io.File

/**
 * THE EXEMPLAR BANK (owner 07-12, approved with the PATTERN HYPOTHESIS: "the model speaks patterns, not english").
 *
 * The agent's own PROVEN wins, stored as lean (screen → action) DEMONSTRATIONS and re-injected as few-shot PATTERNS —
 * the model's native tongue — instead of reaching it as English recall text. This is the memory system's strongest
 * signal (what actually worked) finally delivered in the form the small model actually reads: a pattern to continue,
 * not an instruction to interpret. Pattern geometry at injection: past (screen → action) pairs sit immediately BEFORE
 * the live screen + contract, so the continuation of the pattern IS the action for the live screen.
 *
 * §3-clean like ReferenceStore: entries come ONLY from the agent's own scored, ADVANCING steps (pos ∧ m>0) — never
 * scraped, never external; a hostile screen cannot make itself a PROVEN win, so it cannot poison the bank. §2-clean:
 * exemplars are perception the model READS; it still chooses every action. Nothing leaves the device.
 *
 * Append-only JSONL, capped + rolling (the TrainingData/ReferenceStore idiom). Keyed by SCREEN CLASS (the H-JEPA
 * abstraction — "how does a list/form/settings screen behave", not a memorized path) so an exemplar generalizes to
 * screens of the same KIND.
 */
object ExemplarBank {
    private const val FILE = "exemplar_bank.jsonl"
    private const val MAX_BYTES = 2_000_000
    private const val MAX_SCREEN = 320     // the lean digest — exemplars must stay CHEAP (they ride the prompt)
    private const val MAX_ACTION = 200

    private fun file(c: Context) = File(c.filesDir, FILE)

    /** Bank one proven win as a demonstration. Guarded + capped; a failure is swallowed (never affects the agent).
     *  [screenLean] is the compact screen digest (top lines), [action] the emitted JSON that ADVANCED the task. */
    @Synchronized
    fun record(c: Context, cls: String, app: String, screenLean: String, action: String) {
        try {
            if (cls.isBlank() || screenLean.isBlank() || action.isBlank()) return
            // Dedup the trivial case: the newest entry for this class already teaches this exact action shape.
            val f = file(c)
            val o = JSONObject()
                .put("cls", cls)
                .put("app", app.take(40))
                .put("screen", screenLean.take(MAX_SCREEN))
                .put("action", action.take(MAX_ACTION))
                .put("ts", System.currentTimeMillis())
            f.appendText(o.toString() + "\n")
            if (f.length() > MAX_BYTES) trim(f)
            AgentLog.log("exemplar", "banked: cls=$cls ${action.take(60)}")
        } catch (_: Exception) {}
    }

    private fun trim(f: File) {
        try {
            val lines = f.readLines()
            if (lines.size > 8) f.writeText(lines.drop(lines.size / 4).joinToString("\n", "", "\n"))
        } catch (_: Exception) {}
    }

    /** The newest [n] demonstrations for this screen class (same-app first, then any app), action-deduped —
     *  formatted by the caller. Read path is cold (once per decide), guarded, never throws. */
    fun forClass(c: Context, cls: String, app: String, n: Int = 2): List<Pair<String, String>> {
        return try {
            val f = file(c); if (!f.exists() || cls.isBlank()) return emptyList()
            val rows = f.readLines().mapNotNull { ln -> if (ln.isBlank()) null else try { JSONObject(ln) } catch (_: Exception) { null } }
                .filter { it.optString("cls") == cls }
                .asReversed()   // newest first
            val out = ArrayList<Pair<String, String>>()
            val seen = HashSet<String>()
            // same-app exemplars first (closest pattern), then any-app of the same class
            for (pass in 0..1) {
                for (r in rows) {
                    if (out.size >= n) break
                    val a = r.optString("action")
                    val sameApp = r.optString("app").equals(app, ignoreCase = true)
                    if ((pass == 0 && !sameApp) || (pass == 1 && sameApp)) continue
                    val verb = a.substringAfter("\"action\"").take(24)   // dedup by verb-ish shape, keep variety
                    if (!seen.add(verb)) continue
                    out.add(r.optString("screen") to a)
                }
                if (out.size >= n) break
            }
            out
        } catch (_: Exception) { emptyList() }
    }

    fun count(c: Context): Int = try { if (file(c).exists()) file(c).readLines().count { it.isNotBlank() } else 0 } catch (_: Exception) { 0 }
}
