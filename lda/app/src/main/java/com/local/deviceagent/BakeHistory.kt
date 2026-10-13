package com.local.deviceagent

import android.content.Context
import org.json.JSONObject
import java.io.File

/**
 * BAKE HISTORY (owner's ask, 07-10: "a page to track all the bakes with them explained just for my own personal
 * use"). One append-only, capped, on-device record per operator bake ATTEMPT — built-in or custom — so the
 * Baking screen can show every install/no-op/revert with its σ-off before→after numbers and a plain-English
 * explanation. Mirrors `ReferenceStore`'s idiom (filesDir JSONL, guarded, capped, rolling) so it never touches
 * a decision or leaves the device. NO model writes here; it only records what the bake did.
 */
object BakeHistory {
    private const val FILE = "bake_history.jsonl"
    private const val MAX_BYTES = 400_000          // hundreds of rows; the tracker is a personal log, kept small
    private const val KEEP_ON_TRIM = 300           // rows retained when rolling

    // The five outcomes bakeOperatorDirect can produce, kept as constants so the UI + this store agree.
    const val RESIDENT = "RESIDENT"                // already in the weights ⇒ dropped from the prompt, no write
    const val INSTALLED = "INSTALLED"              // newly baked in ⇒ dropped from the prompt
    const val PARTIAL = "PARTIAL"                  // moved partway (kept), still keeps its prompt text
    const val NOOP = "NO-OP"                        // didn't move ⇒ reverted, nothing written
    const val SKIP = "SKIP"                        // no formal rule / no signal

    private fun file(c: Context) = File(c.filesDir, FILE)

    /** Record one bake attempt. Guarded + capped; a failure is swallowed (must never affect the bake). */
    @Synchronized
    fun record(c: Context, op: String, custom: Boolean, kind: String, before: Double, after: Double, bytes: Int, tsMs: Long) {
        try {
            val o = JSONObject()
                .put("ts", tsMs)
                .put("op", op.take(64))
                .put("custom", custom)
                .put("kind", kind)
                .put("before", before)
                .put("after", after)
                .put("bytes", bytes)
            val f = file(c)
            f.appendText(o.toString() + "\n")
            if (f.length() > MAX_BYTES) trim(f)
        } catch (_: Exception) {}
    }

    /** Newest-first rows for the tracker (bounded). */
    fun recent(c: Context, limit: Int = 200): List<JSONObject> {
        return try {
            val f = file(c); if (!f.exists()) return emptyList()
            f.readLines().mapNotNull { ln -> if (ln.isBlank()) null else try { JSONObject(ln) } catch (_: Exception) { null } }
                .asReversed().take(limit)
        } catch (_: Exception) { emptyList() }
    }

    fun count(c: Context): Int = try { file(c).takeIf { it.exists() }?.readLines()?.count { it.isNotBlank() } ?: 0 } catch (_: Exception) { 0 }

    @Synchronized
    fun clear(c: Context) { try { file(c).delete() } catch (_: Exception) {} }

    private fun trim(f: File) {
        try {
            val lines = f.readLines().filter { it.isNotBlank() }
            if (lines.size > KEEP_ON_TRIM) f.writeText(lines.takeLast(KEEP_ON_TRIM).joinToString("\n", "", "\n"))
        } catch (_: Exception) {}
    }

    /** A plain-English one-liner for a row (the tracker renders this — owner: "explained"). Self-contained so the
     *  Activity just formats it. */
    fun explain(row: JSONObject): String {
        val op = row.optString("op")
        val kind = row.optString("kind")
        val before = (row.optDouble("before", -1.0) * 100).toInt()
        val after = (row.optDouble("after", -1.0) * 100).toInt()
        val bytes = row.optInt("bytes", 0)
        val ag = if (before < 0) "" else " (agreement $before%→$after%)"
        return when (kind) {
            INSTALLED -> "$op — INSTALLED: baked into the model$ag, $bytes bytes changed. Now resident, so it dropped from the prompt."
            RESIDENT  -> "$op — RESIDENT: the model already had this${if (before < 0) "" else " (agreement $before%)"}. Nothing written; dropped from the prompt."
            PARTIAL   -> "$op — PARTIAL: the model moved toward it$ag and the change was kept, but it isn't fully resident yet — its prompt text stays for now."
            NOOP      -> "$op — no change$ag: the nudge didn't move the model, so it was reverted and nothing was written."
            SKIP      -> "$op — skipped: no formal rule to install."
            else      -> "$op — $kind$ag."
        }
    }
}
