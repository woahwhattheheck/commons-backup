package com.local.deviceagent

import android.content.Context
import org.json.JSONObject
import java.io.File

/**
 * THE DATA FLYWHEEL (owner-approved). Every real run produces (perceived screen -> chosen action ->
 * outcome) tuples - the exact examples that seed an EVAL suite and, later, a FINE-TUNED action model
 * (the README's Function-Gemma idea). We capture them so daily use compounds into a training asset.
 *
 * PRIVACY: written ONLY to the app's private files dir; NOTHING leaves the device unless the owner
 * deliberately exports the file. Consistent with the no-exfiltration rule. Compact + size-bounded so it
 * can never bloat storage (a rolling window of recent experience). Off by a Settings toggle.
 *
 * Each line is one step the AGENT decided: { obj, app, screen (capped), action, result }. The screen +
 * objective approximate the model's input; the action is the label; the result is the reward signal -
 * enough to build an eval set and a first supervised-fine-tune. The owner can later opt to capture the
 * full prompt / screenshots for richer training.
 *
 * REWARD ENRICHMENT (the plan's "make the JSONL weightable" step): when the operator layer is on, a step
 * also carries the model-chosen operator ("op"), and the NEXT step tops up a { stepScore, m, op } sentinel
 * with the metric M (progress - cost) that only becomes knowable after the following screen is seen. The
 * task-end marker carries the failure class + step count. All fields are OPTIONAL and additive - a reader
 * that ignores them still sees today's { obj, app, screen, action, result } / { taskEnd, obj, success }.
 */
object TrainingData {
    private const val FILE = "training_data.jsonl"
    private const val MAX_BYTES = 4_000_000L   // ~4MB rolling cap; oldest quarter trimmed when exceeded
    private const val SCREEN_CAP = 2000        // cap the screen text per record (privacy + size)

    fun file(c: Context): File = File(c.filesDir, FILE)

    /** Append one decided step. Best-effort and fully guarded - a capture failure must NEVER disturb the
     *  agent loop. Tiny synchronous append (well under the per-step decision time). `op` is the model-chosen
     *  reasoning operator for this step ("" when the operator layer is off / DIRECT) - emitted only when
     *  present so baseline captures are byte-identical to before. */
    @Synchronized
    fun record(c: Context, objective: String, app: String, screen: String, action: String, result: String, op: String = "") {
        try {
            val o = JSONObject()
                .put("obj", objective.take(200))
                .put("app", app.take(60))
                .put("screen", screen.take(SCREEN_CAP))
                .put("action", action.take(400))
                .put("result", result)
            if (op.isNotBlank() && op != "DIRECT") o.put("op", op.take(24))
            val f = file(c)
            f.appendText(o.toString() + "\n")
            if (f.length() > MAX_BYTES) trim(f)
        } catch (_: Throwable) {}
    }

    /** Top up the PRECEDING step with its realized reward once the next screen reveals it: M = progress -
     *  cost (ReasoningOperators.computeM). Its own sentinel line so the append-only file stays intact; the
     *  converter pairs it to the step line just above it (the operator path scores step N at the top of
     *  step N+1, so this always lands right after step N's line and before step N+1's). Only fires when the
     *  operator layer is on, so it's absent from baseline captures. */
    @Synchronized
    fun recordStepScore(c: Context, m: Int, op: String) {
        try {
            file(c).appendText(JSONObject().put("stepScore", true)
                .put("m", m).put("op", op.take(24)).toString() + "\n")
        } catch (_: Throwable) {}
    }

    /** Mark the end of a task with its outcome, so the converter can keep only steps from SUCCESSFUL
     *  tasks (the clean positive examples) while the raw file still retains everything for analysis.
     *  `fclass` (the failure taxonomy) + `steps` let the converter weight/segment by HOW a task failed,
     *  not just pass/fail - both optional, so an older reader is unaffected. */
    @Synchronized
    fun recordTaskEnd(c: Context, objective: String, success: Boolean, failureClass: String = "", steps: Int = 0) {
        try {
            val o = JSONObject().put("taskEnd", true)
                .put("obj", objective.take(200)).put("success", success)
            if (failureClass.isNotBlank()) o.put("fclass", failureClass.take(40))
            if (steps > 0) o.put("steps", steps)
            file(c).appendText(o.toString() + "\n")
        } catch (_: Throwable) {}
    }

    /** Drop the oldest quarter when the file exceeds the cap: unbounded in TIME, bounded in SIZE. */
    private fun trim(f: File) {
        try {
            val lines = f.readLines()
            f.writeText(lines.drop(lines.size / 4).joinToString("\n") + "\n")
        } catch (_: Throwable) {}
    }

    fun count(c: Context): Int =
        try { if (file(c).exists()) file(c).readLines().size else 0 } catch (_: Throwable) { 0 }

    fun clear(c: Context) { try { file(c).delete() } catch (_: Throwable) {} }
}
