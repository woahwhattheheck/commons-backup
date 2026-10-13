package com.local.deviceagent

import android.content.Intent
import android.os.Bundle
import android.text.format.DateUtils
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity

/** User-facing task log with thumbs up/down + a "why" note that the agent learns from. */
class TaskLogActivity : AppCompatActivity() {

    private lateinit var container: LinearLayout

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val scroll = ScrollView(this)
        container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 32, 32, 32)
        }
        scroll.addView(container)
        setContentView(scroll)
        render()
    }

    override fun onResume() { super.onResume(); render() }

    private fun render() {
        container.removeAllViews()
        container.addView(TextView(this).apply {
            text = "Task log"; textSize = 22f
            setTypeface(typeface, android.graphics.Typeface.BOLD)
            setTextColor(Ui.TEXT); setPadding(0, 0, 0, 16)
        })
        // The scoreboard (success rate, per-build trend, gauntlet) lives beside its raw data.
        container.addView(Button(this).apply {
            text = "📊  Scoreboard"
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)
                .apply { setMargins(0, 0, 0, 8) }
            setOnClickListener {
                startActivity(Intent(this@TaskLogActivity, ScoreboardActivity::class.java))
            }
            Ui.styleButton(this, primary = false)
        })

        val entries = TaskHistory.list(this)
        if (entries.isEmpty()) {
            container.addView(TextView(this).apply {
                text = "No tasks yet on this build."; setTextColor(Ui.TEXT_DIM)
            })
            return
        }

        for (e in entries) {
            // Tapping the task opens its per-step rating screen (the owner's "click a task to
            // give feedback, see the plan, rate each step" flow).
            container.addView(TextView(this).apply {
                text = e.objective.ifBlank { "(no objective)" }
                textSize = 15f; setTextColor(Ui.TEXT)
                setPadding(0, 18, 0, 0)
                setOnClickListener {
                    startActivity(Intent(this@TaskLogActivity, TaskDetailActivity::class.java)
                        .putExtra(TaskDetailActivity.EXTRA_TASK_ID, e.id))
                }
            })
            // Show how many steps are already rated, so progress is visible at a glance.
            val rated = e.stepRatings.count { it != 0 }
            if (e.steps.isNotEmpty()) container.addView(TextView(this).apply {
                text = "${e.steps.size} steps · tap to rate each" + if (rated > 0) " ($rated rated)" else ""
                textSize = 11f; setTextColor(Ui.TEXT_DIM)
            })
            val ratingMark = when (e.rating) { 1 -> " · marked success"; -1 -> " · marked fail"; else -> "" }
            container.addView(TextView(this).apply {
                text = "${e.outcome} · ${DateUtils.getRelativeTimeSpanString(e.time)}$ratingMark" +
                    if (e.note.isNotBlank()) "\nnote: ${e.note}" else ""
                textSize = 12f
                setTextColor(Ui.TEXT_DIM)
            })
            // Good / Bad are the thumbs-up / thumbs-down rating (same function as before); the
            // currently-selected one is FILLED so the rating is visible at a glance.
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, 6, 0, 0) }
            row.addView(logButton("Success", selected = e.rating == 1) {
                TaskHistory.setFeedback(this@TaskLogActivity, e.id, 1, e.note)
                // Flipping to Success retracts an earlier Fail's taught memory (verdict reversed).
                AgentMemory.recordTaskFeedback(this@TaskLogActivity, e.objective, 1, e.note)
                render()
            })
            row.addView(logButton("Fail", selected = e.rating == -1) { promptNote(e, -1) })
            row.addView(logButton("Note") { promptNote(e, e.rating) })
            row.addView(logButton("Logs") {
                startActivity(Intent(this@TaskLogActivity, DebugLogActivity::class.java)
                    .putExtra(DebugLogActivity.EXTRA_TASK_QUERY, e.objective))
            })
            container.addView(row)
            // Re-run the exact task (the owner's "re-run-task button"): start the agent on this same
            // objective and close the log so it has the screen. Only when there's a command to repeat.
            if (e.objective.isNotBlank()) container.addView(Button(this).apply {
                text = "▶  Run this task again"
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)
                    .apply { setMargins(0, 8, 0, 0) }
                setOnClickListener {
                    startForegroundService(Intent(this@TaskLogActivity, AgentService::class.java)
                        .setAction(AgentService.ACTION_RUN_COMMAND)
                        .putExtra(AgentService.EXTRA_COMMAND, e.objective))
                    finish()   // get out of the way so the agent operates the screen
                }
                Ui.styleButton(this, primary = false)
            })
        }
    }

    private fun logButton(label: String, selected: Boolean = false, onClick: () -> Unit) = Button(this).apply {
        text = label
        layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            .apply { setMargins(0, 0, 12, 0) }
        setOnClickListener { onClick() }
        Ui.styleButton(this, primary = selected)   // the active rating is filled, like a lit-up thumb
    }

    private fun promptNote(e: TaskHistory.Entry, rating: Int) {
        val input = EditText(this).apply { setText(e.note); hint = "Why? (optional)" }
        AlertDialog.Builder(this)
            .setTitle("Feedback")
            .setView(input)
            .setPositiveButton("Save") { _, _ ->
                val note = input.text.toString()
                TaskHistory.setFeedback(this, e.id, rating, note)
                // A Fail verdict (+ the "why" note) is the owner's diagnosis - teach memory from it,
                // like the per-step ratings already do (before this it was stored and never learned).
                AgentMemory.recordTaskFeedback(this, e.objective, rating, note)
                render()
            }
            .setNegativeButton("Cancel", null)
            .show()
    }
}
