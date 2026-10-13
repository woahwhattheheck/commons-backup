package com.local.deviceagent

import android.net.Uri
import android.os.Bundle
import android.text.format.DateFormat
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.ActivityResultLauncher
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity

/**
 * The SCOREBOARD: makes the ONE metric (task success rate) visible instead of guessed. Headline
 * rate over recent tasks, the per-BUILD trend (did the last build help or hurt?), the failure-
 * class breakdown (WHERE it fails), and the gauntlet - the owner's fixed benchmark tasks run
 * back-to-back and scored the same way every build. Success counting: the owner's rating always
 * outranks the recorded outcome (TaskHistory.isSuccess).
 */
class ScoreboardActivity : AppCompatActivity() {

    private lateinit var container: LinearLayout

    // SAF picker for importing a CANDIDATE model to probe (Stage 2). Registered before RESUMED.
    private val pickCandidate: ActivityResultLauncher<Array<String>> =
        registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri: Uri? ->
            if (uri == null) return@registerForActivityResult
            val name = uri.lastPathSegment?.substringAfterLast('/')?.substringAfterLast(':') ?: "candidate.litertlm"
            Toast.makeText(this, "Importing candidate model…", Toast.LENGTH_LONG).show()
            Thread {
                val ok = try {
                    contentResolver.openInputStream(uri)?.use {
                        ModelStore.importCandidate(applicationContext, it, name)
                    } ?: false
                } catch (e: Exception) { false }
                runOnUiThread {
                    Toast.makeText(this, if (ok) "Candidate imported — Probe it below." else "Import failed.", Toast.LENGTH_LONG).show()
                    render()
                }
            }.start()
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        title = "Scoreboard"
        val scroll = ScrollView(this).apply { setBackgroundColor(Ui.BG) }
        container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 32, 32, 64)
        }
        scroll.addView(container)
        setContentView(scroll)
        render()
    }

    override fun onResume() { super.onResume(); render() }

    private fun render() {
        container.removeAllViews()
        header("Scoreboard", 22f)

        val all = TaskHistory.list(this)
        val recent = all.take(30)
        if (recent.isEmpty()) {
            caption("No tasks yet. Run some tasks (or the gauntlet below) and the score fills in.")
        } else {
            val ok = recent.count { TaskHistory.isSuccess(it) }
            header("$ok/${recent.size} succeeded (${if (recent.isNotEmpty()) ok * 100 / recent.size else 0}%)", 19f, pad = 20)
            caption("Last ${recent.size} tasks. A task counts as a success when it finished (or you marked it Success); your rating always wins.")
            buildTrend(all)
            failureClasses(recent)
        }
        gauntletSection()
        selfUpdateSection()
    }

    /** The owner-approved self-update review (INV-46), shown only when the owner has enabled it. Import a
     *  candidate model, probe it against the baseline, and review + grade any probe-passing SUBMISSION.
     *  Installing is always the owner's action here — never the agent's. */
    private fun selfUpdateSection() {
        if (!SettingsManager(this).isSelfModelEditEnabled()) return
        header("Self-update", 16f, pad = 28)
        caption("Owner-approved. Import a candidate model, probe it on the gauntlet against your current model, and — only if it wins — review + grade it before it installs. The agent proposes; you decide.")

        ModelSelfUpdate.lastStatus.takeIf { it.isNotBlank() }?.let { line(it) }

        val hasCandidate = ModelStore.candidateFile(this) != null
        container.addView(Button(this).apply {
            text = if (hasCandidate) "Re-import candidate model" else "Import candidate model"
            layoutParams = fullWidth()
            setOnClickListener { pickCandidate.launch(arrayOf("*/*")) }
            Ui.styleButton(this, primary = false)
        })
        if (hasCandidate) {
            container.addView(Button(this).apply {
                text = if (ModelSelfUpdate.isRunning()) "Probing…" else "▶  Probe candidate vs baseline"
                layoutParams = fullWidth()
                isEnabled = !ModelSelfUpdate.isRunning() && !GauntletRunner.isRunning()
                setOnClickListener {
                    val started = ModelSelfUpdate.probeCandidate(this@ScoreboardActivity)
                    if (started) finish()   // the probe drives the phone; get out of the way
                    else Toast.makeText(this@ScoreboardActivity, ModelSelfUpdate.lastStatus, Toast.LENGTH_LONG).show()
                }
                Ui.styleButton(this, primary = !ModelSelfUpdate.isRunning())
            })
            caption("Probing runs the gauntlet twice (baseline, then candidate) and restores your baseline afterward — the candidate is never kept without your approval.")
        }

        val pending = SelfUpdateStore.pending(this)
        if (pending.isNotEmpty()) {
            header("Awaiting your grade", 14f, pad = 20)
            pending.forEach { sub -> renderSubmission(sub) }
        }
    }

    private fun renderSubmission(sub: SelfUpdateStore.Submission) {
        line("Candidate ${sub.candRate}% vs baseline ${sub.baseRate}%  ·  ${DateFormat.format("MMM d, HH:mm", sub.ts)}")
        caption(sub.note)
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, 8, 0, 0) }
        row.addView(Button(this).apply {
            text = "Approve + grade"
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            setOnClickListener { gradeThen(sub) { grade ->
                pickDistilledOps { ops ->
                    Toast.makeText(this@ScoreboardActivity, "Installing approved model…", Toast.LENGTH_SHORT).show()
                    Thread {
                        ModelSelfUpdate.installApproved(applicationContext, sub.id, grade, ops)
                        runOnUiThread { Toast.makeText(this@ScoreboardActivity, ModelSelfUpdate.lastStatus, Toast.LENGTH_LONG).show(); render() }
                    }.start()
                }
            } }
            Ui.styleButton(this, primary = true)
        })
        row.addView(Button(this).apply {
            text = "Reject"
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f).apply { setMargins(12, 0, 0, 0) }
            setOnClickListener { gradeThen(sub) { grade ->
                ModelSelfUpdate.reject(applicationContext, sub.id, grade); render()
            } }
            Ui.styleButton(this, primary = false)
        })
        container.addView(row)
    }

    /** Ask the owner for a 1-5 grade, then run [after] with it — the grade is the certification a real win
     *  happened (and a preference signal), captured on approve AND reject. */
    private fun gradeThen(sub: SelfUpdateStore.Submission, after: (Int) -> Unit) {
        val grades = arrayOf("1 — poor", "2", "3 — ok", "4", "5 — clearly better")
        AlertDialog.Builder(this)
            .setTitle("Your grade for this candidate")
            .setItems(grades) { _, which -> after(which + 1) }
            .setNegativeButton("Cancel", null)
            .show()
    }

    /** After approval, ask which operators (if any) this candidate DISTILLED — those get injected as a short
     *  tag going forward (INV-46 weak-trigger). Optional: for a non-operator recipe (e.g. success-weighted),
     *  the owner selects none and nothing changes about injection. */
    private fun pickDistilledOps(after: (Set<String>) -> Unit) {
        val names = ReasoningOperators.BAKED.map { it.name }.toTypedArray()
        val checked = BooleanArray(names.size)
        AlertDialog.Builder(this)
            .setTitle("Which operators did this candidate bake in? (optional)")
            .setMultiChoiceItems(names, checked) { _, i, isChecked -> checked[i] = isChecked }
            .setNegativeButton("None") { _, _ -> after(emptySet()) }
            .setPositiveButton("Install") { _, _ ->
                after(names.filterIndexed { i, _ -> checked[i] }.toSet())
            }
            .show()
    }

    /** Per-build trend: the regression view - success %, avg steps, avg minutes for each of the
     *  last few builds, so the owner SEES whether a new build helped or hurt. */
    private fun buildTrend(all: List<TaskHistory.Entry>) {
        val byBuild = all.filter { it.build > 0 }.groupBy { it.build }
        if (byBuild.size < 2) return   // one build = no trend to show yet
        header("By build", 16f, pad = 24)
        caption("Each row is one installed build - the regression check.")
        byBuild.entries.sortedByDescending { it.key }.take(5).forEachIndexed { i, (build, entries) ->
            val ok = entries.count { TaskHistory.isSuccess(it) }
            val avgSteps = entries.map { it.steps.size }.average().let { if (it.isNaN()) 0 else it.toInt() }
            val avgMin = entries.filter { it.durationMs > 0 }.map { it.durationMs }.average()
                .let { if (it.isNaN()) 0.0 else it / 60000.0 }
            line("${DateFormat.format("MMM d", build)}${if (i == 0) " (current)" else ""}:  " +
                "$ok/${entries.size} (${ok * 100 / entries.size}%) · ~$avgSteps steps" +
                (if (avgMin > 0) " · ${"%.1f".format(avgMin)} min" else ""))
        }
    }

    private fun failureClasses(recent: List<TaskHistory.Entry>) {
        val classes = recent.filter { !TaskHistory.isSuccess(it) && it.failureClass.isNotBlank() }
            .groupBy { it.failureClass }.mapValues { it.value.size }
        if (classes.isEmpty()) return
        header("Why tasks fail", 16f, pad = 24)
        line(classes.entries.sortedByDescending { it.value }.joinToString(" · ") { "${it.key} ${it.value}" })
    }

    private fun gauntletSection() {
        header("Gauntlet", 16f, pad = 28)
        caption("A fixed benchmark: runs these tasks back-to-back on its own and scores them - the same test every build. The agent gets no extra help; failures count honestly.")
        val last = GauntletRunner.lastScore(this)
        if (last.isNotBlank()) {
            line("Last run: $last")
            GauntletRunner.lastDetail(this).takeIf { it.isNotBlank() }?.let { caption(it) }
        }
        // A/B (G3): head-vs-vision on the same frozen list, once both configs have a run.
        GauntletRunner.abComparison(this).takeIf { it.isNotBlank() }?.let {
            header("A/B — head vs vision", 14f, pad = 16)
            line(it)
            caption("Run the gauntlet once with the fast head on (helper model enabled) and once with it off — this compares the latest of each on success + per-step latency. Trust a head only when it holds success and cuts latency.")
        }
        container.addView(Button(this).apply {
            text = if (GauntletRunner.isRunning()) "■  Stop gauntlet" else "▶  Run gauntlet"
            layoutParams = fullWidth()
            setOnClickListener {
                if (GauntletRunner.isRunning()) GauntletRunner.stop(this@ScoreboardActivity, "stopped from the scoreboard")
                else {
                    GauntletRunner.start(this@ScoreboardActivity, GauntletRunner.tasks(this@ScoreboardActivity))
                    finish()   // get out of the way - the agent needs the screen
                }
            }
            Ui.styleButton(this, primary = !GauntletRunner.isRunning())
        })

        header("Gauntlet tasks", 14f, pad = 20)
        GauntletRunner.tasks(this).forEach { t ->
            val row = TextView(this).apply {
                text = "• $t"; textSize = 13f; setTextColor(Ui.TEXT); setPadding(0, 10, 0, 0)
                setOnClickListener {
                    AlertDialog.Builder(this@ScoreboardActivity)
                        .setMessage("Remove this task from the gauntlet?")
                        .setPositiveButton("Remove") { _, _ ->
                            GauntletRunner.setTasks(this@ScoreboardActivity,
                                GauntletRunner.tasks(this@ScoreboardActivity).filter { it != t })
                            render()
                        }
                        .setNegativeButton("Cancel", null).show()
                }
            }
            container.addView(row)
        }
        val btnRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, 12, 0, 0) }
        btnRow.addView(Button(this).apply {
            text = "Add task"
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            setOnClickListener {
                val input = EditText(this@ScoreboardActivity).apply { hint = "e.g. open Chrome and search the weather" }
                AlertDialog.Builder(this@ScoreboardActivity)
                    .setTitle("Add a gauntlet task")
                    .setView(input)
                    .setPositiveButton("Add") { _, _ ->
                        val t = input.text.toString().trim()
                        if (t.isNotBlank()) GauntletRunner.setTasks(this@ScoreboardActivity,
                            GauntletRunner.tasks(this@ScoreboardActivity) + t)
                        render()
                    }
                    .setNegativeButton("Cancel", null).show()
            }
            Ui.styleButton(this, primary = false)
        })
        btnRow.addView(Button(this).apply {
            text = "Reset defaults"
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                .apply { setMargins(12, 0, 0, 0) }
            setOnClickListener { GauntletRunner.setTasks(this@ScoreboardActivity, GauntletRunner.DEFAULT_TASKS); render() }
            Ui.styleButton(this, primary = false)
        })
        container.addView(btnRow)
    }

    private fun header(text: String, size: Float, pad: Int = 0) = container.addView(TextView(this).apply {
        this.text = text; textSize = size; setTextColor(Ui.TEXT)
        setTypeface(typeface, android.graphics.Typeface.BOLD); setPadding(0, pad, 0, 0)
    })

    private fun line(text: String) = container.addView(TextView(this).apply {
        this.text = text; textSize = 14f; setTextColor(Ui.TEXT); setPadding(0, 8, 0, 0)
    })

    private fun caption(text: String) = container.addView(TextView(this).apply {
        this.text = text; textSize = 12f; setTextColor(Ui.TEXT_DIM); setPadding(0, 4, 0, 0)
    })

    private fun fullWidth() = LinearLayout.LayoutParams(
        LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)
        .apply { setMargins(0, 12, 0, 0) }
}
