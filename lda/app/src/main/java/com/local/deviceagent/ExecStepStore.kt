package com.local.deviceagent

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * P0 GRADER — structured per-run EXECUTED-STEP store (the owner-grade → weight-bake bridge).
 *
 * TaskHistory keeps the human-readable step summaries (for display + the ✓/✗ UI). This store keeps the STRUCTURED
 * fields a ReferenceStore weight-bake needs — {op, screen-sig, rendered prompt, emitted action, operator clause, M}
 * — for each executed step, keyed to the run's TaskHistory id + step index (the missing run↔per-step link). So when
 * the owner grades an EXECUTED step ✓/✗ in the task log, we look the step up here and bank it as a ReferenceStore
 * win (pos) / contrast (neg) — the owner's judgement becomes direct, high-quality training signal for the action-
 * layer bake, distinct from (and stronger than) the agent's own auto-labelled M-based references.
 *
 * filesDir JSONL (NOT SharedPreferences — the rendered prompts are large), one line per run, rolling to the last
 * MAX_RUNS graded-able runs. Read-only w.r.t. the running agent; every call guarded. Nothing leaves the device.
 * Injection-immune by construction: an owner grade is the label, never on-screen text, and the worst a graded
 * negative can drive is a "push AWAY from this action here" bake — never an executed action.
 */
object ExecStepStore {
    private const val FILE = "exec_steps.jsonl"
    private const val MAX_RUNS = 15               // rolling window of graded-able runs (prompts are big; the device has GBs)
    private const val MAX_PROMPT = 16_000         // keep the prompt WHOLE for a faithful σ-off replay (mirrors ReferenceStore)
    private const val MAX_ACTION = 1_200
    private const val MAX_STEPS = 60              // cap steps captured per run

    data class Step(val op: String, val sig: Int, val prompt: String, val action: String, val clause: String, val m: Int)

    private fun file(c: Context) = File(c.filesDir, FILE)

    /** Persist one finished run's structured executed steps, keyed to its TaskHistory [runId] + model [fingerprint].
     *  Best-effort + capped; runs at task end (off the hot path) and a failure never affects the agent. */
    @Synchronized
    fun record(c: Context, runId: Long, fingerprint: String, steps: List<Step>) {
        if (runId <= 0L || steps.isEmpty()) return
        try {
            val arr = JSONArray()
            steps.take(MAX_STEPS).forEach { s ->
                arr.put(JSONObject()
                    .put("op", s.op).put("sig", s.sig).put("m", s.m)
                    .put("action", s.action.take(MAX_ACTION))
                    .put("clause", s.clause.take(8000))   // full-depth σ; mirror ReferenceStore's cap so the σ-off replay strip matches
                    .put("prompt", s.prompt.take(MAX_PROMPT)))
            }
            val line = JSONObject().put("run", runId).put("fp", fingerprint).put("steps", arr).toString()
            val f = file(c)
            f.appendText(line + "\n")
            val lines = f.readLines().filter { it.isNotBlank() }
            if (lines.size > MAX_RUNS) f.writeText(lines.takeLast(MAX_RUNS).joinToString("\n") + "\n")
        } catch (_: Throwable) {}
    }

    /** (fingerprint, steps) for a run, or ("", empty) if none — the grade wire reads step[index] to bank a reference. */
    @Synchronized
    fun forRun(c: Context, runId: Long): Pair<String, List<Step>> {
        return try {
            val f = file(c); if (!f.exists()) return "" to emptyList()
            val line = f.readLines().lastOrNull { ln ->
                ln.isNotBlank() && try { JSONObject(ln).optLong("run") == runId } catch (_: Exception) { false }
            } ?: return "" to emptyList()
            val o = JSONObject(line)
            val arr = o.optJSONArray("steps") ?: return "" to emptyList()
            val steps = (0 until arr.length()).mapNotNull { i ->
                arr.optJSONObject(i)?.let {
                    Step(it.optString("op"), it.optInt("sig"), it.optString("prompt"),
                         it.optString("action"), it.optString("clause"), it.optInt("m"))
                }
            }
            o.optString("fp") to steps
        } catch (_: Throwable) { "" to emptyList() }
    }
}
