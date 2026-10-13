package com.local.deviceagent

import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.Looper
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * The GAUNTLET: run the owner's fixed benchmark tasks back-to-back and score them, so the ONE
 * metric (success rate) is measured the same way every build instead of guessed from memory.
 *
 * MEASUREMENT ONLY (CLAUDE.md §12): this queues objectives and records outcomes. It never feeds
 * the agent hints it wouldn't normally get, never retries with coaching, never auto-confirms -
 * a completion here is the agent's own, and an honest failure is recorded as exactly that.
 */
object GauntletRunner {

    private const val PREF = "gauntlet"
    private const val LAST_SCORE = "last_score"     // human line, e.g. "6/8 · build Jul 3"
    private const val LAST_DETAIL = "last_detail"   // per-task ✓/✗ lines of the last run
    // A/B (G3): a small capped history of COMPLETED runs, each tagged with the config it ran under
    // (head = the fast action-head/helper was enabled+present, else vision-only). The scoreboard reads
    // this to show head-vs-vision on the ONE metric + per-step latency, so a new head is trusted only
    // after it beats vision-only on the same frozen list (§12 - measured wins only).
    private const val RUNS = "runs"
    private const val MAX_RUNS = 8

    /** One task's outcome within a run: latency + step count let us report per-step decision latency
     *  (the head's whole point, §13), not just pass/fail. A deterministic task carries 0/0 and is
     *  excluded from the latency mean (it never ran the model). */
    private data class Res(val task: String, val ok: Boolean, val durationMs: Long, val steps: Int)

    private val main = Handler(Looper.getMainLooper())
    private var queue: MutableList<String> = mutableListOf()
    private var current: String? = null
    private var results = ArrayList<Res>()
    // The config this run is measuring, captured at start() so a mid-run settings change can't mislabel
    // it: "head" iff a helper/head model is enabled AND actually present, else "vision".
    private var runConfig = "vision"
    // Probe mode (Stage 2 self-update): an explicit config LABEL + a completion callback delivering the
    // run's (passed, total, per-step ms), so ModelSelfUpdate can score a candidate model vs the baseline on
    // the SAME frozen list. Null in a normal owner-run gauntlet (unchanged behavior).
    @Volatile private var onComplete: ((Int, Int, Long) -> Unit)? = null
    private var forcedConfig: String? = null
    @Volatile private var running = false
    // Watchdog: longer than the agent's own MAX_RUNTIME (20 min), so its caps always fire first;
    // this only catches a task that ended without the completion hook (e.g. an OS kill).
    private const val TASK_TIMEOUT_MS = 25 * 60_000L
    private val timeout = Runnable {
        val c = ActionAccessibilityService.instance ?: return@Runnable
        val t = current ?: return@Runnable
        AgentLog.log("gauntlet", "timeout on \"${t.take(40)}\" - counting it failed, moving on")
        results.add(Res(t, false, 0, 0))
        next(c)
    }

    fun isRunning(): Boolean = running

    /** Run the frozen list under an explicit [label] and fire [onDone] with (passed, total, per-step ms)
     *  at completion — the probe the self-update loop uses to score baseline vs candidate. If [onDone]'s
     *  `total` is less than the task count, the run was stopped early (don't trust it). No-op if a run is
     *  already going. Measurement-only, same as a normal gauntlet. */
    @Synchronized
    fun startProbe(c: Context, tasks: List<String>, label: String, onDone: (Int, Int, Long) -> Unit) {
        if (running || tasks.isEmpty()) { onDone(0, 0, 0); return }
        forcedConfig = label
        onComplete = onDone
        start(c, tasks)
    }

    @Synchronized
    fun start(c: Context, tasks: List<String>) {
        if (running || tasks.isEmpty()) return
        // OFFLINE MODE: skip tasks that need the network (YouTube/web/weather/Gemini/…) so an offline gauntlet
        // still runs the on-device tasks + REPORTS what it skipped (§13 no silent cap). Baseline + candidate
        // probes both filter identically (isOnline is stable across a run), so the A/B comparison stays fair.
        val runnable = runnableTasks(c, tasks)
        if (runnable.size < tasks.size)
            AgentLog.log("gauntlet", "OFFLINE: skipped ${tasks.size - runnable.size} network task(s) — running ${runnable.size} on-device")
        if (runnable.isEmpty()) { AgentLog.log("gauntlet", "OFFLINE: every task needs the network — nothing to run"); return }
        queue = runnable.toMutableList()
        results = ArrayList()
        runConfig = forcedConfig ?: detectConfig(c)
        running = true
        AgentLog.log("gauntlet", "started: ${queue.size} tasks [config=$runConfig]")
        fireNext(c)
    }

    /** Single-model (07-10): there is no helper/head model — every run is a "vision" (main-model) run. */
    private fun detectConfig(c: Context): String {
        val sm = SettingsManager(c)
        val base = "vision"
        // LANG A/B: tag a codec run distinctly so it is comparable against the labeled baseline (run the same
        // task set with the flag OFF then ON; the config tag + [promptsize]/[iat] logs give tokens + latency +
        // success per config). Suffix-only, so the existing head-vs-vision comparison (which matches the bare
        // base tags) is untouched.
        // OPT A/B: tag the OPTIMIZE flags too (stacking / fold-verify / adaptive-decode), so a run is
        // comparable against the baseline (same task set, flag OFF then ON). Suffix-only; a bare baseline
        // run keeps the plain head/vision tag, so the existing comparisons are untouched.
        val opt = StringBuilder()
        if (sm.isOperatorStackingEnabled()) opt.append("-stack")
        if (sm.isFoldVerifyEnabled()) opt.append("-fold")
        if (sm.isAdaptiveDecodeEnabled()) opt.append("-adec")
        if (sm.isSessionSigmaEnabled()) opt.append("-sigma")
        if (sm.isSelfCalibrateEnabled()) opt.append("-selftune")
        if (sm.isContinuousEngineEnabled()) opt.append("-engine")
        if (sm.isContinuousStreamEnabled()) opt.append("-stream")
        return base + (if (sm.isAgentLanguageEnabled()) "-lang" else "") + opt
    }

    /** Stop the whole run (owner stop / emergency stop). Never auto-restarts anything. */
    @Synchronized
    fun stop(c: Context, reason: String) {
        if (!running) return
        running = false
        main.removeCallbacks(timeout)
        AgentLog.log("gauntlet", "stopped (${reason}) after ${results.size} of ${results.size + queue.size + (if (current != null) 1 else 0)} tasks")
        current = null; queue.clear()
        if (results.isNotEmpty()) persistScore(c, partial = true)
        fireProbeDone()   // deliver partial results so a waiting self-update probe aborts safely
    }

    /** Completion hook, called by AgentService when ANY task ends. No-op unless a gauntlet is
     *  running - while one runs, the ending task is ours (the runner launched it). */
    @Synchronized
    fun onTaskEnded(c: Context, objective: String, success: Boolean, durationMs: Long = 0, steps: Int = 0) {
        if (!running) return
        val t = current ?: return
        main.removeCallbacks(timeout)
        results.add(Res(t, success, durationMs, steps))
        AgentLog.log("gauntlet", "${results.size}/${results.size + queue.size} ${if (success) "✓" else "✗"} \"${t.take(40)}\"" +
            (if (steps > 0 && durationMs > 0) " (${durationMs / steps}ms/step)" else ""))
        next(c)
    }

    private fun next(c: Context) {
        current = null
        if (!running) return
        if (queue.isEmpty()) {
            running = false
            persistScore(c, partial = false)
            AgentLog.log("gauntlet", "done: ${results.count { it.ok }}/${results.size} [config=$runConfig]")
            fireProbeDone()
            return
        }
        // Reset the stage between tasks: go home, give the launcher a moment, then fire.
        ActionAccessibilityService.instance?.performActionJson("{\"action\":\"home\"}")
        main.postDelayed({ fireNext(c) }, 4000L)
    }

    /** Deliver the probe result (passed, total, per-step ms) to a waiting startProbe caller, once, and
     *  clear the probe state. A stopped run delivers partial results (total < task count) so the caller
     *  knows not to trust them. No-op outside probe mode. */
    private fun fireProbeDone() {
        val cb = onComplete ?: return
        onComplete = null; forcedConfig = null
        val passed = results.count { it.ok }
        val timed = results.filter { it.steps > 0 && it.durationMs > 0 }
        val stepMs = if (timed.isEmpty()) 0L else timed.map { it.durationMs / it.steps }.average().toLong()
        cb(passed, results.size, stepMs)
    }

    private fun fireNext(c: Context) {
        if (!running) return
        val t = queue.removeAt(0)
        current = t
        AgentLog.log("gauntlet", "task ${results.size + 1}/${results.size + queue.size + 1} started: \"${t.take(40)}\"")
        c.startForegroundService(Intent(c, AgentService::class.java)
            .setAction(AgentService.ACTION_RUN_COMMAND)
            .putExtra(AgentService.EXTRA_COMMAND, t))
        main.postDelayed(timeout, TASK_TIMEOUT_MS)
    }

    private fun persistScore(c: Context, partial: Boolean) {
        val passed = results.count { it.ok }
        val total = results.size
        // Per-step decision latency, averaged over the tasks that actually ran the model (steps>0) - the
        // number the head is supposed to move (§13). Deterministic/timed-out tasks (0/0) are excluded.
        val timed = results.filter { it.steps > 0 && it.durationMs > 0 }
        val stepMs = if (timed.isEmpty()) 0L else timed.map { it.durationMs / it.steps }.average().toLong()
        val meanSteps = if (timed.isEmpty()) 0 else timed.map { it.steps }.average().toInt()
        val score = "$passed/$total · $runConfig" +
            (if (stepMs > 0) " · ~${"%.1f".format(stepMs / 1000.0)}s/step" else "") +
            (if (partial) " (stopped early)" else "")
        val detail = results.joinToString("\n") { (if (it.ok) "✓ " else "✗ ") + it.task.take(60) }
        c.getSharedPreferences(PREF, Context.MODE_PRIVATE).edit()
            .putString(LAST_SCORE, "$score · ${android.text.format.DateFormat.format("MMM d, HH:mm", System.currentTimeMillis())}")
            .putString(LAST_DETAIL, detail).apply()
        // Only a COMPLETE run enters the A/B history - a partial run isn't a fair comparison point.
        if (!partial && total > 0) appendRun(c, runConfig, passed, total, stepMs, meanSteps)
    }

    /** Append one completed run to the capped A/B history. */
    private fun appendRun(c: Context, config: String, passed: Int, total: Int, stepMs: Long, steps: Int) {
        val sp = c.getSharedPreferences(PREF, Context.MODE_PRIVATE)
        val arr = try { JSONArray(sp.getString(RUNS, "") ?: "") } catch (_: Exception) { JSONArray() }
        arr.put(JSONObject().put("config", config).put("passed", passed).put("total", total)
            .put("stepMs", stepMs).put("steps", steps).put("ts", System.currentTimeMillis()))
        val trimmed = JSONArray()
        for (i in maxOf(0, arr.length() - MAX_RUNS) until arr.length()) trimmed.put(arr.get(i))
        sp.edit().putString(RUNS, trimmed.toString()).apply()
    }

    data class RunRec(val config: String, val passed: Int, val total: Int, val stepMs: Long, val steps: Int, val ts: Long) {
        val rate: Int get() = if (total > 0) passed * 100 / total else 0
    }

    fun runs(c: Context): List<RunRec> {
        val arr = try { JSONArray(c.getSharedPreferences(PREF, Context.MODE_PRIVATE).getString(RUNS, "") ?: "") }
            catch (_: Exception) { return emptyList() }
        return (0 until arr.length()).mapNotNull { arr.optJSONObject(it) }.map {
            RunRec(it.optString("config"), it.optInt("passed"), it.optInt("total"),
                it.optLong("stepMs"), it.optInt("steps"), it.optLong("ts"))
        }
    }

    /** The head-vs-vision A/B line for the scoreboard: the latest COMPLETE run of each config compared on
     *  the ONE metric (success) + per-step latency. "" until BOTH configs have a run (run the frozen list
     *  once with the head on, once with it off). A head is worth trusting only when it holds success AND
     *  cuts latency (§12/§13); a fast-but-worse head is flagged, never celebrated. */
    fun abComparison(c: Context): String {
        val rs = runs(c)
        val head = rs.lastOrNull { it.config == "head" } ?: return ""
        val vis = rs.lastOrNull { it.config == "vision" } ?: return ""
        val succ = "success ${head.rate}% (head) vs ${vis.rate}% (vision)"
        val lat = if (head.stepMs > 0 && vis.stepMs > 0) {
            val pct = (vis.stepMs - head.stepMs) * 100.0 / vis.stepMs
            " · ${"%.1f".format(head.stepMs / 1000.0)}s vs ${"%.1f".format(vis.stepMs / 1000.0)}s/step" +
                (if (pct >= 0) " (head ${pct.toInt()}% faster)" else " (head ${(-pct).toInt()}% slower)")
        } else ""
        val verdict = when {
            head.rate >= vis.rate && head.stepMs in 1..vis.stepMs -> "  → head wins: same-or-better success, faster"
            head.rate < vis.rate -> "  → head LOWERS success; not worth it yet"
            else -> ""
        }
        return succ + lat + verdict
    }

    fun lastScore(c: Context): String =
        c.getSharedPreferences(PREF, Context.MODE_PRIVATE).getString(LAST_SCORE, "") ?: ""

    fun lastDetail(c: Context): String =
        c.getSharedPreferences(PREF, Context.MODE_PRIVATE).getString(LAST_DETAIL, "") ?: ""

    /** The owner-editable benchmark list. Defaults are deliberately HARMLESS - no messages to
     *  real people, no purchases, no settings changes beyond an alarm that's deleted again. */
    fun tasks(c: Context): List<String> {
        val raw = c.getSharedPreferences(PREF, Context.MODE_PRIVATE).getString("tasks", "") ?: ""
        val arr = try { JSONArray(raw) } catch (_: Exception) { JSONArray() }
        val out = (0 until arr.length()).map { arr.optString(it) }.filter { it.isNotBlank() }
        return out.ifEmpty { DEFAULT_TASKS }
    }

    fun setTasks(c: Context, tasks: List<String>) {
        val arr = JSONArray().apply { tasks.forEach { put(it) } }
        c.getSharedPreferences(PREF, Context.MODE_PRIVATE).edit().putString("tasks", arr.toString()).apply()
    }

    val DEFAULT_TASKS = listOf(
        "open YouTube and search for cat videos",
        "open Chrome and search the weather",
        "set an alarm for 9am then delete it",
        "draw a simple house in Samsung Notes",
        "open Gemini and ask it what day it is",
        "open Settings and read the battery percentage back to me"
    )

    /** OFFLINE MODE: the subset of [tasks] runnable with no network (unchanged when online). Used by both the
     *  manual run (start) and the self-update probe so the expected count matches what actually runs. Pure — the
     *  skip is LOGGED in start(), not here, so calling this to size the probe doesn't double-log. */
    fun runnableTasks(c: Context, tasks: List<String>): List<String> =
        if (DeviceStats.isOnline(c)) tasks else tasks.filterNot { needsNetwork(it) }

    /** Heuristic: does this benchmark task require the internet? (web search / a cloud app / a download.) */
    private fun needsNetwork(task: String): Boolean {
        val t = task.lowercase()
        return listOf("search", "weather", "news", "youtube", "web", "browser", "chrome", "google",
            "gemini", "chatgpt", "online", "download", "internet", "stream").any { t.contains(it) }
    }
}
