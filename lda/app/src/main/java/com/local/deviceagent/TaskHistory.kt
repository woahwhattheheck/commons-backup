package com.local.deviceagent

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/**
 * Persistent, capped log of finished tasks with optional user feedback (thumbs up/down + a "why"
 * note). Stored as JSON in SharedPreferences.
 *
 * Three correctness rules learned from the owner's report ("feedback jumped to another task; the
 * order was wrong; it showed old-build tasks and dropped current ones"):
 *  1. Every entry gets a UNIQUE, monotonic id (a stored counter) - never System.currentTimeMillis(),
 *     which collided for back-to-back tasks and made feedback land on the wrong entry. Legacy entries
 *     with no id (=0) are no longer matchable, so a stray feedback can't bleed onto them.
 *  2. Entries are tagged with the BUILD they ran under and the list shows ONLY the current build, so
 *     stale tasks from older builds never pollute (and are pruned from storage on the next add).
 *  3. The list is sorted by actual time (newest first), and an immediate duplicate add (the same task
 *     recorded twice by two code paths) is skipped.
 */
object TaskHistory {
    private const val PREF = "task_history"
    private const val KEY = "entries"
    private const val SEQ = "seq"        // monotonic id counter, so ids never collide
    private const val MAX = 60

    data class Entry(
        val id: Long, val time: Long, val objective: String,
        val outcome: String, val rating: Int, val note: String,
        // The agent's authored PLAN (its STEPS) and the actions it actually TOOK, so the log can show
        // them back for PER-STEP rating. stepRatings runs parallel to steps (0=unrated,1=worked,-1=failed).
        val plan: String = "", val steps: List<String> = emptyList(),
        val stepRatings: List<Int> = emptyList(),
        // Scoreboard stats: run duration, failure class (from the [failure] taxonomy, "" on
        // success), the APK build it ran under (per-build trend), and whether it was a gauntlet run.
        val durationMs: Long = 0, val failureClass: String = "",
        val build: Long = 0, val gauntlet: Boolean = false
    )

    /** True iff this task counts as a SUCCESS for the scoreboard: the owner's rating outranks the
     *  recorded outcome (same rule as failureHintFor). */
    fun isSuccess(e: Entry): Boolean = e.rating == 1 || (e.outcome == "finished" && e.rating != -1)

    /** ACCEPTANCE ORACLE (the completeness critic's gap): the rolling AGENT-DRIVEN success rate over the last
     *  [window] non-gauntlet tasks — the ONE metric (§12), surfaced so the owner can SEE whether the flywheel /
     *  binding / σ work is actually raising completion, instead of inferring it from spot-logs. (count, successes,
     *  pct); (0,0,0) with no history. Owner-facing telemetry only — never a prompt, never an auto-tune (§2/§12). */
    @Synchronized
    fun rollingSuccessRate(c: Context, window: Int = 20): Triple<Int, Int, Int> {
        val recent = list(c).filter { !it.gauntlet }.take(window)
        if (recent.isEmpty()) return Triple(0, 0, 0)
        val succ = recent.count { isSuccess(it) }
        return Triple(recent.size, succ, succ * 100 / recent.size)
    }

    private fun prefs(c: Context) = c.getSharedPreferences(PREF, Context.MODE_PRIVATE)

    /** Identifies the current build, so older-build tasks don't mix in (same source as AgentLog). */
    private fun buildTag(c: Context): Long = try {
        c.packageManager.getPackageInfo(c.packageName, 0).lastUpdateTime
    } catch (_: Exception) { 0L }

    /** Returns the new entry's monotonic id (so a caller can key per-step structured data to this run, e.g.
     *  ExecStepStore for the grader), or 0L if this add was skipped as an immediate duplicate. */
    @Synchronized
    fun add(c: Context, objective: String, outcome: String,
            plan: String = "", steps: List<String> = emptyList(),
            durationMs: Long = 0, failureClass: String = "", gauntlet: Boolean = false): Long {
        val arr = load(c)
        val now = System.currentTimeMillis()
        val build = buildTag(c)
        // Skip an immediate duplicate: the same task recorded twice in quick succession (e.g. a stop
        // path + the completion callback) shouldn't create two entries.
        if (arr.length() > 0) {
            val last = arr.optJSONObject(arr.length() - 1)
            if (last != null && last.optString("objective") == objective &&
                last.optString("outcome") == outcome && now - last.optLong("time") < 20_000L) return 0L
        }
        val id = prefs(c).getLong(SEQ, 1L)
        prefs(c).edit().putLong(SEQ, id + 1).apply()
        val stepsArr = JSONArray().apply { steps.take(40).forEach { put(it) } }
        val ratingsArr = JSONArray().apply { repeat(minOf(steps.size, 40)) { put(0) } }
        arr.put(
            JSONObject()
                .put("id", id)
                .put("time", now)
                .put("objective", objective)
                .put("outcome", outcome)
                .put("rating", 0)
                .put("note", "")
                .put("build", build)
                .put("plan", plan)
                .put("steps", stepsArr)
                .put("sratings", ratingsArr)
                .put("dur", durationMs)
                .put("fclass", failureClass)
                .put("gauntlet", gauntlet)
        )
        // Keep tasks across builds (the owner reinstalls a new APK constantly; filtering to the
        // current build made the task log "completely empty after several tasks" every update). The
        // task log is the owner's record of what the agent DID, not a build-specific debug view, so we
        // retain ALL builds' entries and just cap the total. (Feedback still lands correctly because
        // every entry has a unique monotonic id - that, not build-filtering, was the collision fix.)
        while (arr.length() > MAX) arr.remove(0)
        save(c, arr)
        // Acceptance oracle: log the rolling agent-driven success rate each task end, so the owner can watch the
        // ONE metric move as the flywheel/binding/σ work lands (a real success bar, not spot-logs). Non-gauntlet.
        if (!gauntlet) {
            val (n, s, pct) = rollingSuccessRate(c)
            if (n > 0) AgentLog.log("rate", "agent-driven success: $s/$n recent = $pct%")
            // [metrics] (07-11 replan) — one rolling line on EVERY task end. add() is the true chokepoint every end
            // hits (normal finish, owner-stop, AND the deterministic fast-path), so [metrics] belongs HERE — the old
            // placement in AgentOrchestrator.finish() missed owner-stops + fast-paths (all 3 test tasks never fired it).
            // Cheap fields only (success + prompt size + baked-op count); latency stays in [iat], divergence stays the
            // on-demand button. Gated on tier_observ; telemetry only (§2/§12).
            if (n > 0 && (try { SettingsManager(c).isTierObservEnabled() } catch (_: Throwable) { false })) {
                AgentLog.log("metrics", "success ${pct}% ($s/$n) · promptTok=${AgentBrain.lastPromptTokens} · " +
                    "bakedOps=${ReasoningOperators.distilledOps.size}")
            }
        }
        return id
    }

    @Synchronized
    fun setFeedback(c: Context, id: Long, rating: Int, note: String) {
        if (id <= 0L) return   // 0 = a legacy/unidentified entry; never match it (collision guard)
        val arr = load(c)
        for (i in 0 until arr.length()) {
            val o = arr.getJSONObject(i)
            if (o.optLong("id") == id) { o.put("rating", rating); o.put("note", note); break }
        }
        save(c, arr)
    }

    /** Rate ONE executed step of a task (the owner's per-step feedback): 1=worked, -1=failed, 0=clear.
     *  Stored in the parallel "sratings" array so the agent can later reinforce what worked and avoid
     *  what didn't. Returns the step text (so the caller can feed it to memory), or null if not found. */
    @Synchronized
    fun setStepRating(c: Context, id: Long, index: Int, rating: Int): String? {
        if (id <= 0L) return null
        val arr = load(c)
        for (i in 0 until arr.length()) {
            val o = arr.getJSONObject(i)
            if (o.optLong("id") != id) continue
            val steps = o.optJSONArray("steps") ?: return null
            if (index < 0 || index >= steps.length()) return null
            val ratings = o.optJSONArray("sratings") ?: JSONArray().also { o.put("sratings", it) }
            while (ratings.length() <= index) ratings.put(0)
            ratings.put(index, rating)
            save(c, arr)
            return steps.optString(index)
        }
        return null
    }

    @Synchronized
    fun list(c: Context): List<Entry> {
        val arr = load(c)
        val out = ArrayList<Entry>(arr.length())
        for (i in 0 until arr.length()) {
            val o = arr.getJSONObject(i)
            val stepsArr = o.optJSONArray("steps")
            val steps = if (stepsArr == null) emptyList()
                else (0 until stepsArr.length()).map { stepsArr.optString(it) }
            val ratingsArr = o.optJSONArray("sratings")
            val sratings = if (ratingsArr == null) emptyList()
                else (0 until ratingsArr.length()).map { ratingsArr.optInt(it) }
            out.add(
                Entry(
                    o.optLong("id"), o.optLong("time"), o.optString("objective"),
                    o.optString("outcome"), o.optInt("rating"), o.optString("note"),
                    o.optString("plan"), steps, sratings,
                    o.optLong("dur"), o.optString("fclass"),
                    o.optLong("build"), o.optBoolean("gauntlet")
                )
            )
        }
        return out.sortedByDescending { it.time }   // newest first, by actual time
    }

    /** One entry by id (for the per-step rating detail screen), or null. */
    @Synchronized
    fun get(c: Context, id: Long): Entry? = list(c).firstOrNull { it.id == id }

    // Function words that would fake a similarity match; keep it minimal so real words decide.
    private val STOP = setOf("the", "and", "for", "with", "that", "this", "then", "them", "your",
        "from", "into", "please", "can", "you", "about", "some", "what", "when", "how", "are",
        "was", "will", "would", "should", "just", "like", "want", "need", "make", "get", "use")

    private fun keyWords(s: String): Set<String> =
        Regex("[a-z0-9']+").findAll(s.lowercase()).map { it.value }
            .filter { it.length >= 3 && it !in STOP }.toSet()

    /**
     * PRE-TASK FAILURE RECALL ("stop repeating the same failed run"): if the MOST RECENT similar
     * attempt at this objective failed - the owner marked it Fail, or it ended "stopped" - return a
     * short planner block naming what went wrong (the owner's note, any steps they marked failed,
     * how far it got) so the new plan routes AROUND it instead of re-driving the same dead end.
     * Playbooks already carry successes forward; this is the missing negative half.
     *
     * Returns "" when the newest similar attempt SUCCEEDED (the failure is stale - stay quiet, a
     * warning would just spook a solved task), when nothing similar is recent (14 days), or when
     * the match is weak (wrong recall is noise that pulls a healthy plan off course).
     */
    @Synchronized
    fun failureHintFor(c: Context, objective: String): String {
        val want = keyWords(objective)
        if (want.isEmpty()) return ""
        val cutoff = System.currentTimeMillis() - 14L * 24 * 3600_000L
        for (e in list(c)) {   // newest first; the first similar entry decides
            if (e.time < cutoff) break
            val have = keyWords(e.objective)
            val shared = want.intersect(have).size
            // Tiny objectives ("text mom") must match fully; longer ones need >=3 shared real words.
            val bar = minOf(3, minOf(want.size, have.size))
            if (shared < bar) continue
            val ownerFail = e.rating == -1
            val gaveUp = e.outcome == "stopped" && e.rating != 1
            if (!ownerFail && !gaveUp) return ""   // newest similar attempt worked - nothing to warn
            val sb = StringBuilder("YOUR LAST ATTEMPT AT THIS TASK FAILED (it ${e.outcome}")
            if (ownerFail) sb.append("; the owner marked it a FAIL")
            sb.append(").")
            if (e.note.isNotBlank()) sb.append(" Owner's note: \"${e.note.trim().take(120)}\".")
            // The owner's per-step Fail marks are the precise poison; else show how far it got.
            val failed = e.steps.filterIndexed { i, _ -> e.stepRatings.getOrElse(i) { 0 } == -1 }
            if (failed.isNotEmpty())
                sb.append(" Steps the owner marked FAILED: ${failed.take(3).joinToString("; ") { "\"${it.take(60)}\"" }}.")
            else if (e.steps.isNotEmpty())
                sb.append(" It got as far as: ${e.steps.takeLast(3).joinToString(" -> ") { it.take(60) }}.")
            sb.append("\nPlan a DIFFERENT route past where it went wrong - do not repeat that same run.")
            return sb.toString()
        }
        return ""
    }

    @Synchronized
    fun clear(c: Context) = prefs(c).edit().remove(KEY).apply()

    private fun load(c: Context): JSONArray =
        try { JSONArray(prefs(c).getString(KEY, "[]")) } catch (e: Exception) { JSONArray() }

    private fun save(c: Context, arr: JSONArray) =
        prefs(c).edit().putString(KEY, arr.toString()).apply()
}
