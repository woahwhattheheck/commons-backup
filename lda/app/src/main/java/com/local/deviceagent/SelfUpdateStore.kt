package com.local.deviceagent

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/**
 * The governance record for the owner-approved self-update loop (INV-46).
 *
 * The automated keep-if-better probe is only a PRE-FILTER: a candidate that clears it becomes a
 * SUBMISSION the OWNER must review and GRADE before it is installed. That final owner gate is what
 * catches a candidate that gamed the probe but isn't truly better (§12 — no fake wins), and the
 * owner's grade is captured as a preference signal the flywheel can learn from. Nothing here installs
 * a model; it only records what the owner needs to decide, and what they decided.
 *
 * Plain SharedPreferences JSON (conventions: persisted state is size-capped + de-duplicated).
 */
object SelfUpdateStore {

    private const val PREF = "self_update"
    private const val SUBS = "submissions"
    private const val MAX = 20

    data class Submission(
        val id: Long,
        val ts: Long,
        val recipe: String,
        val basePassed: Int, val baseTotal: Int, val baseStepMs: Long,
        val candPassed: Int, val candTotal: Int, val candStepMs: Long,
        val status: String,   // "pending" | "approved" | "rejected"
        val grade: Int,       // owner's 1-5 grade, or -1 if not graded
        val note: String
    ) {
        val baseRate: Int get() = if (baseTotal > 0) basePassed * 100 / baseTotal else 0
        val candRate: Int get() = if (candTotal > 0) candPassed * 100 / candTotal else 0
        /** The probe verdict: the candidate cleared keep-if-better (success up, latency not worse). */
        val probeWon: Boolean
            get() = candRate >= baseRate && (baseStepMs <= 0 || candStepMs <= baseStepMs)
    }

    private fun sp(c: Context) = c.getSharedPreferences(PREF, Context.MODE_PRIVATE)

    private fun read(c: Context): JSONArray =
        try { JSONArray(sp(c).getString(SUBS, "") ?: "") } catch (_: Exception) { JSONArray() }

    private fun write(c: Context, arr: JSONArray) {
        // Keep only the newest MAX so the record can't grow without bound.
        val trimmed = JSONArray()
        for (i in maxOf(0, arr.length() - MAX) until arr.length()) trimmed.put(arr.get(i))
        sp(c).edit().putString(SUBS, trimmed.toString()).apply()
    }

    private fun parse(o: JSONObject) = Submission(
        o.optLong("id"), o.optLong("ts"), o.optString("recipe"),
        o.optInt("basePassed"), o.optInt("baseTotal"), o.optLong("baseStepMs"),
        o.optInt("candPassed"), o.optInt("candTotal"), o.optLong("candStepMs"),
        o.optString("status", "pending"), o.optInt("grade", -1), o.optString("note")
    )

    /** Record a probe-passing candidate for owner review (status = pending). Returns its id. */
    fun submit(
        c: Context, ts: Long, recipe: String,
        basePassed: Int, baseTotal: Int, baseStepMs: Long,
        candPassed: Int, candTotal: Int, candStepMs: Long, note: String
    ): Long {
        val arr = read(c)
        val id = ts
        arr.put(JSONObject()
            .put("id", id).put("ts", ts).put("recipe", recipe)
            .put("basePassed", basePassed).put("baseTotal", baseTotal).put("baseStepMs", baseStepMs)
            .put("candPassed", candPassed).put("candTotal", candTotal).put("candStepMs", candStepMs)
            .put("status", "pending").put("grade", -1).put("note", note))
        write(c, arr)
        return id
    }

    fun all(c: Context): List<Submission> =
        read(c).let { arr -> (0 until arr.length()).mapNotNull { arr.optJSONObject(it) }.map { parse(it) } }
            .sortedByDescending { it.ts }

    fun pending(c: Context): List<Submission> = all(c).filter { it.status == "pending" }

    fun get(c: Context, id: Long): Submission? = all(c).firstOrNull { it.id == id }

    /** Owner decision: approve (with a 1-5 grade) or reject a submission. Does NOT install — the caller
     *  (ModelSelfUpdate) installs on approval. The grade is retained as a preference signal. */
    fun decide(c: Context, id: Long, approved: Boolean, grade: Int) {
        val arr = read(c)
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            if (o.optLong("id") == id) {
                o.put("status", if (approved) "approved" else "rejected")
                o.put("grade", grade.coerceIn(-1, 5))
            }
        }
        write(c, arr)
    }
}
