package com.local.deviceagent

import android.os.Bundle
import android.text.format.DateUtils
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

/**
 * Per-task detail + PER-STEP rating (the owner's idea): show the task's objective, the PLAN the
 * agent authored, and EACH action it actually took - each with Worked / Failed buttons. A rating is
 * fed straight into durable memory (a worked step -> a confirmed lesson, a failed one -> a "mistake
 * to avoid"), so the owner can teach the agent EXACTLY where a task succeeded or went wrong.
 */
class TaskDetailActivity : AppCompatActivity() {

    companion object { const val EXTRA_TASK_ID = "task_id" }

    private lateinit var container: LinearLayout
    private var taskId: Long = 0L

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        taskId = intent.getLongExtra(EXTRA_TASK_ID, 0L)
        val scroll = ScrollView(this).apply { setBackgroundColor(Ui.BG) }
        container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 32, 32, 120)   // bottom pad clears the ownership stamp
        }
        scroll.addView(container)
        setContentView(scroll)
        render()
    }

    override fun onResume() { super.onResume(); render() }

    private fun render() {
        container.removeAllViews()
        val e = TaskHistory.get(this, taskId)
        if (e == null) {
            container.addView(label("This task is no longer in the log.", Ui.TEXT_DIM, 15f))
            return
        }

        container.addView(label(e.objective.ifBlank { "(no objective)" }, Ui.TEXT, 20f, bold = true))
        container.addView(label("${e.outcome} · ${DateUtils.getRelativeTimeSpanString(e.time)}", Ui.TEXT_DIM, 12f))

        // One-tap "why did it do that": open the debug log pre-filtered to THIS task's [think]
        // lines (the owner's requested spot-check view - the reasoning was always logged, but
        // reaching it meant hand-picking the task and tag in the log viewer).
        container.addView(Button(this).apply {
            text = "See its reasoning"
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)
                .apply { setMargins(0, 12, 0, 0) }
            setOnClickListener {
                startActivity(android.content.Intent(this@TaskDetailActivity, DebugLogActivity::class.java)
                    .putExtra(DebugLogActivity.EXTRA_TASK_QUERY, e.objective)
                    .putExtra(DebugLogActivity.EXTRA_TAG, "think"))
            }
            Ui.styleButton(this, primary = false)
        })

        // The plan the agent wrote for itself (read-only context for rating the steps).
        if (e.plan.isNotBlank()) {
            container.addView(label("Plan", Ui.TEXT, 16f, bold = true, topPad = 28))
            container.addView(label(e.plan.trim(), Ui.TEXT_DIM, 13f, topPad = 4))
        }

        // The actions actually taken, each rateable. This is the heart of the screen.
        container.addView(label("Steps it took — rate each", Ui.TEXT, 16f, bold = true, topPad = 28))
        if (e.steps.isEmpty()) {
            container.addView(label("No per-step record for this task (older task, or it ended before acting).",
                Ui.TEXT_DIM, 13f, topPad = 4))
            return
        }
        container.addView(label("Tell me which steps worked and which didn't — I'll remember it for next time.",
            Ui.TEXT_DIM, 12f, topPad = 2))

        e.steps.forEachIndexed { i, step ->
            val rating = e.stepRatings.getOrElse(i) { 0 }
            container.addView(label("${i + 1}. $step", Ui.TEXT, 14f, topPad = 18))
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL; setPadding(0, 6, 0, 0)
            }
            row.addView(rateButton("Worked", selected = rating == 1) { rate(e, i, if (rating == 1) 0 else 1) })
            row.addView(rateButton("Failed", selected = rating == -1) { rate(e, i, if (rating == -1) 0 else -1) })
            container.addView(row)
        }
    }

    /** Persist the per-step rating, teach memory from it, AND bank it as a weight-bake reference, then refresh. */
    private fun rate(e: TaskHistory.Entry, index: Int, rating: Int) {
        val step = TaskHistory.setStepRating(this, e.id, index, rating)
        // rating 0 = the owner toggled it back off; don't write a memory for "un-rated".
        if (rating != 0 && step != null) AgentMemory.recordStepFeedback(this, e.objective, step, rating)
        // P0 GRADER → BAKE: an owner ✓/✗ on the EXECUTED step is direct, high-quality training signal — bank it as a
        // ReferenceStore win (pos) / contrast (neg), the owner's label overriding the agent's auto M-label. Needs the
        // step's structured fields (op / sig / prompt / action / clause) from ExecStepStore, keyed to this run's id.
        // Only steps that ran a real operator with a captured prompt become references (DIRECT/summary-only steps
        // still feed the memory lesson above); injection-immune — the label is the owner's, never on-screen text.
        if (rating != 0) try {
            val sm = SettingsManager(this)
            if (sm.isReferenceCaptureEnabled()) {
                val (fp, steps) = ExecStepStore.forRun(this, e.id)
                val s = steps.getOrNull(index)
                if (s != null && s.op.isNotBlank() && s.op != ReasoningOperators.DIRECT && s.prompt.isNotBlank()) {
                    val fingerprint = fp.ifBlank { ModelStore.activeFingerprint(this, sm) }
                    ReferenceStore.record(this, s.op, fingerprint, s.sig, s.prompt, s.action,
                        rating, s.clause, pos = rating > 0)
                }
            }
        } catch (_: Throwable) {}
        render()
    }

    private fun label(text: String, color: Int, size: Float, bold: Boolean = false, topPad: Int = 0) =
        TextView(this).apply {
            this.text = text; textSize = size; setTextColor(color)
            setPadding(0, topPad, 0, 0)
            if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD)
        }

    private fun rateButton(label: String, selected: Boolean, onClick: () -> Unit) = Button(this).apply {
        text = if (selected) "✓ $label" else label
        layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            .apply { setMargins(0, 0, 12, 0) }
        setOnClickListener { onClick() }
        Ui.styleButton(this, primary = selected)   // the chosen rating is filled
    }
}
