package com.local.deviceagent

import android.graphics.Typeface
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.InputType
import android.view.Gravity
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * BAKING — the dedicated menu for everything weight-baking (owner, 07-10: "all baking features should have their
 * own menu", "give it a loading screen … make sure I can monitor progress", "a place for a custom bake to put my
 * own operators in one by one", "a page to track all the bakes with them explained"). Programmatic UI (no XML),
 * mirroring `CalibrationActivity`. Nothing here leaves the device.
 *
 * Sections: (1) Bake the built-in operators — a live PROGRESS view over `AgentService.runDefinedBake`; (2) Custom
 * bake — author your own operators (name + rule) and bake them one at a time; (3) Bake history — every attempt,
 * explained; (4) Tools — the residency / divergence / write-test / revert diagnostics, re-captioned in plain words.
 */
class BakingActivity : AppCompatActivity() {

    private lateinit var settings: SettingsManager
    private lateinit var root: LinearLayout
    private val handler = Handler(Looper.getMainLooper())
    @Volatile private var baking = false

    // The live progress view (persistent across a rebuild-free bake).
    private var progressText: TextView? = null
    private var progressBar: ProgressBar? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        settings = SettingsManager(this)
        title = "Baking"
        val scroll = ScrollView(this)
        root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(48, 40, 48, 72) }
        scroll.addView(root)
        setContentView(scroll)
        build()
    }

    // ---- tiny view helpers (match the codebase's raw-px programmatic style) ------------------------
    private fun sectionHeader(t: String) = root.addView(TextView(this).apply {
        text = t; textSize = 20f; setTypeface(typeface, Typeface.BOLD); setPadding(0, 36, 0, 8)
    })
    private fun caption(t: String) = root.addView(TextView(this).apply {
        text = t; textSize = 13f; alpha = 0.7f; setPadding(0, 0, 0, 12)
    })
    private fun line(t: String, into: LinearLayout = root) = into.addView(TextView(this).apply {
        text = t; textSize = 14f; setPadding(0, 4, 0, 4)
    })
    private fun button(t: String, into: LinearLayout = root, onClick: () -> Unit) = into.addView(Button(this).apply {
        text = t; isAllCaps = false; setOnClickListener { onClick() }
    })

    private fun build() {
        root.removeAllViews()
        buildDiagnostic()
        buildBakeOperators()
        buildCustomBake()
        buildHistory()
        buildTiersAndState()
        buildStateMap()
        buildTools()
    }

    // ---- ONE-TAP FULL DIAGNOSTIC (07-11 — first thing on the screen; the owner's "one test button") ----
    private fun buildDiagnostic() {
        sectionHeader("Full diagnostic")
        button("▶ RUN FULL DIAGNOSTIC — dump everything to the log") {
            runMap("Running the full diagnostic (~30s)…") { AgentService.instance?.runFullDiagnostic() ?: "Start the agent first." }
        }
        caption("ONE tap dumps EVERYTHING as a single [diag] block in the debug log — INSTANTLY (no model decodes): engine/RAM, the [tiers] scaffold breakdown (which block is fattest to bake), [metrics], weight divergence, and baked ops. (The Tier-2 durable-state read is the separate button below — it's slow, 8 decodes.) Also runnable over adb — `adb shell am broadcast -a com.local.deviceagent.DIAG -n com.local.deviceagent/.DiagReceiver` (debug build) — so a tethered session can run it too. Read-only; nothing here drives the phone or touches accounts.")
    }

    /** Rebuild the lists (history / custom ops) after a change, WITHOUT clobbering a running bake's progress view. */
    private fun rebuild() { if (!baking) build() }

    // ---- 1. Bake the built-in operators (with live progress) --------------------------------------
    private fun buildBakeOperators() {
        sectionHeader("Bake operators into the model")
        caption("Installs the agent's built-in thinking operators and its action vocabulary directly into the model's weights, so they no longer take up prompt space (they cost ~0 tokens once resident). It's reference-free — canned internal probes, no tasks. Takes a few minutes; watch the progress below. Resident operators are skipped instantly, so you can tap again to continue.")

        root.addView(TextView(this).apply {
            text = "Weight baking (must be ON to write)"; textSize = 14f; setPadding(0, 8, 0, 0)
        })
        val toggleRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        val toggleBtn = Button(this).apply {
            isAllCaps = false
            text = if (settings.isDirectedBakeEnabled()) "ON — tap to turn off" else "OFF — tap to turn on"
            setOnClickListener {
                val now = !settings.isDirectedBakeEnabled(); settings.setDirectedBakeEnabled(now)
                text = if (now) "ON — tap to turn off" else "OFF — tap to turn on"
            }
        }
        toggleRow.addView(toggleBtn); root.addView(toggleRow)

        // The live progress view — hidden until a bake starts.
        progressBar = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            isIndeterminate = true; visibility = android.view.View.GONE; setPadding(0, 16, 0, 8)
        }
        progressText = TextView(this).apply {
            textSize = 14f; setPadding(0, 8, 0, 8); setTypeface(typeface, Typeface.BOLD)
            visibility = android.view.View.GONE
        }
        root.addView(progressBar); root.addView(progressText)

        button("Bake the built-in operators") {
            startDefinedBake()
        }
    }

    private fun showProgress(text: String, index: Int, total: Int, done: Boolean) {
        progressBar?.visibility = android.view.View.VISIBLE
        progressText?.visibility = android.view.View.VISIBLE
        progressBar?.apply {
            if (total > 0) { isIndeterminate = false; max = total; progress = index } else isIndeterminate = true
        }
        val head = if (total > 0 && index in 1..total) "Operator $index/$total — " else ""
        progressText?.text = head + text
    }

    private fun startDefinedBake() {
        val svc = AgentService.instance
        if (svc == null) { toast("Start the agent first (needs the model loaded)."); return }
        if (baking) { toast("A bake is already running."); return }
        if (!settings.isDirectedBakeEnabled()) { toast("Turn weight baking ON first (the toggle above)."); return }
        baking = true
        showProgress("Starting…", 0, 0, false)
        Thread {
            svc.runDefinedBake { p ->
                handler.post { showProgress(if (p.status.isBlank()) "…" else p.status, p.index, p.total, p.done) }
                if (p.finished) handler.post { baking = false; rebuild(); toast("Bake finished — see Bake history below.") }
            }
            // Safety: if no 'finished' progress ever arrived (guard rejected the run), clear the flag.
            handler.post { if (baking) { baking = false; rebuild() } }
        }.start()
    }

    // ---- 2. Custom bake — your own operators ------------------------------------------------------
    private fun buildCustomBake() {
        sectionHeader("Custom bake — your own operators")
        caption("Write your own operator as a formal rule (a constraint on what the model may output/reason), give it a NAME, and bake it into the weights one at a time — the same install path as the built-ins. A rule reads like: \"∀ value v in output: grounded(v); ¬grounded(v) ⊢ get it first\". Math/formal syntax binds harder than prose.")

        val nameField = EditText(this).apply {
            hint = "NAME (e.g. MY_RULE)"; inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS; setSingleLine(true)
        }
        val ruleField = EditText(this).apply {
            hint = "the formal rule / constraint to install"; inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
            minLines = 2
        }
        val noteField = EditText(this).apply {
            hint = "note to yourself (optional)"; inputType = InputType.TYPE_CLASS_TEXT; setSingleLine(true)
        }
        root.addView(nameField); root.addView(ruleField); root.addView(noteField)
        button("Save operator") {
            val n = nameField.text?.toString()?.trim().orEmpty()
            val r = ruleField.text?.toString()?.trim().orEmpty()
            if (n.length < 2 || r.isBlank()) { toast("Give it a name and a rule."); return@button }
            CustomOperatorStore.save(this, n, r, noteField.text?.toString()?.trim().orEmpty())
            nameField.setText(""); ruleField.setText(""); noteField.setText("")
            toast("Saved. Bake it below.")
            rebuild()
        }

        val ops = CustomOperatorStore.list(this)
        if (ops.isEmpty()) { caption("No custom operators yet — add one above."); return }
        for (op in ops) {
            val card = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(0, 12, 0, 12) }
            card.addView(TextView(this).apply { text = op.name; setTypeface(typeface, Typeface.BOLD); textSize = 15f })
            if (op.note.isNotBlank()) card.addView(TextView(this).apply { text = op.note; textSize = 13f; alpha = 0.7f })
            card.addView(TextView(this).apply { text = op.rule; textSize = 12f; alpha = 0.6f })
            val rowBtns = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            button("Bake this one", rowBtns) { startCustomBake(op.name, op.rule) }
            button("Delete", rowBtns) { CustomOperatorStore.delete(this, op.name); rebuild() }
            card.addView(rowBtns)
            root.addView(card)
        }
    }

    private fun startCustomBake(name: String, rule: String) {
        val svc = AgentService.instance
        if (svc == null) { toast("Start the agent first (needs the model loaded)."); return }
        if (baking) { toast("A bake is already running."); return }
        if (!settings.isDirectedBakeEnabled()) { toast("Turn weight baking ON first (the toggle above)."); return }
        baking = true
        showProgress("Baking $name…", 1, 1, false)
        Thread {
            svc.runCustomBake(name, rule) { p ->
                handler.post { showProgress(if (p.status.isBlank()) "…" else p.status, p.index, p.total, p.done) }
                if (p.finished) handler.post { baking = false; rebuild(); toast("Baked $name — see Bake history below.") }
            }
            handler.post { if (baking) { baking = false; rebuild() } }
        }.start()
    }

    // ---- 3. Bake history (the tracker) ------------------------------------------------------------
    private fun buildHistory() {
        sectionHeader("Bake history")
        caption("Every bake, explained — for your review. RESIDENT = the model already had it. INSTALLED = newly baked in (dropped from the prompt). PARTIAL = moved partway, kept. NO-OP = didn't move, reverted (nothing written). SKIP = no rule to install.")
        val rows = BakeHistory.recent(this, 200)
        if (rows.isEmpty()) { caption("No bakes recorded yet."); return }
        val fmt = SimpleDateFormat("MMM d h:mm a", Locale.getDefault())
        for (row in rows) {
            val ts = row.optLong("ts", 0L)
            val when0 = if (ts > 0) fmt.format(Date(ts)) else ""
            val custom = if (row.optBoolean("custom", false)) " ·custom" else ""
            root.addView(TextView(this).apply {
                text = "$when0$custom — ${BakeHistory.explain(row)}"; textSize = 13f; setPadding(0, 6, 0, 6)
            })
        }
        button("Clear history") { BakeHistory.clear(this); rebuild() }
    }

    // ---- Tiers & state (M1 — "see the machine": the observability instruments) -------------------
    private fun buildTiersAndState() {
        sectionHeader("Tiers & state")
        caption("The instruments that make the three-tier program state VISIBLE. [tiers] logs automatically on every decide step during a task — watch 'inv' (the bakeable scaffold: operators, action menu, rules) fall toward 0 as operators bake, while 'var' (the live screen + objective) is the irreducible floor. The buttons below read the durable runtime state and a metrics snapshot on demand. Log-only; nothing here changes the model or an action. Copy the [tier2] / [metrics] lines back.")

        button("Read the durable state now (Tier-2 canary)") { runMap("Reading the durable runtime state — a battery of canned decisions (~10-20s)…") { AgentService.instance?.runTier2Canary() ?: "Start the agent first." } }
        caption("Reads the state battery and reports HELD / DRIFTED / DEGENERATE vs a saved baseline (first run sets the baseline). DEGENERATE = a probe went incoherent — the R3-corruption signature, which '2b · CORRUPTOR' below should trip and a real process restart should clear. This is how you SEE Tier 2 live.")

        button("Log a metrics snapshot now") {
            if (AgentService.instance == null) { toast("Start the agent first."); return@button }
            val r = AgentService.instance?.runMetricsSnapshot() ?: "Start the agent first."
            toast(r)
        }
        caption("Emits a [metrics] line: agent-driven success, decision latency, prompt-token size, and baked-op count — every core metric on one line so you can watch the fold-in move them. Also fires automatically at the end of each task.")
    }

    // ---- Map the stored state (R3 — the 07-11 finding) -------------------------------------------
    private fun buildStateMap() {
        sectionHeader("Map the stored state")
        caption("Measures the durable change an operator stores IN THE LOADED MODEL (not context). It uses a fixed battery of canned, no-history decisions decoded deterministically, so any change between two readings is a REAL shift in the model. Each run takes a few minutes; nothing here writes the model. Copy the [statemap] log lines back. Run in order: 1 → 2 → 3, and 4 after a restart.")

        button("1 · Fingerprint the model now (baseline)") { runMap("Fingerprinting the model…") { AgentService.instance?.runStateFingerprint() ?: "Start the agent first." } }
        caption("Records how the model answers the battery right now — the reference to compare against.")

        button("2 · Induce an operator + measure the shift") { runMap("Reading baseline, inducing via the chat path, re-measuring (several minutes)…") { AgentService.instance?.runInduceAndMeasure() ?: "Start the agent first." } }
        caption("Reads the battery, processes a well-formed operator through the model VIA THE CHAT PATH (temperature sampler — the only path that tips R3; greedy provably can't), then reads the battery AGAIN with the operator text ABSENT. A shift proves the operator stored state in the loaded model. (Uses your saved ACCURACY if present, else first custom, else built-in REFUSE — the log names which.)")

        button("2b · POSITIVE CONTROL — induce the CORRUPTOR σ") { runMap("Inducing the corruptor via the chat path, re-measuring (several minutes)…") { AgentService.instance?.runInduceAndMeasure("CORRUPTOR") ?: "Start the agent first." } }
        caption("CALIBRATES the instrument against the KNOWN R3 case: induces a dense corruptor σ (the class that tipped R3 in your chat) via the chat/temperature path. If the battery then reads garbage↑ / big content-div → the instrument WORKS and R3 is confirmed by our OWN tools. If it reads 0% here too → the instrument still can't reach the carrier. Run this BEFORE trusting a 0% on a real operator.")

        button("3 · Re-measure after an engine reload") { runMap("Reloading the engine, then re-measuring…") { AgentService.instance?.runReloadReprobe() ?: "Start the agent first." } }
        caption("Drops and rebuilds the model engine inside the SAME app process, then re-reads. If the shift survives, the state lives in the loaded model a fresh engine re-attaches to — not the conversation.")

        button("4 · Compare to saved state (AFTER a restart)") { runMap("Comparing the current model to the saved induced state…") { AgentService.instance?.runCompareToSaved() ?: "Start the agent first." } }
        caption("Run this AFTER a REAL process kill (the button below — swiping the app away is NOT enough). Matches the induced state → survived the restart, it's in the FILE. Back to baseline → the restart cleared it, it was in the loaded model.")

        button("RESTART the app process now (real kill)") {
            toast("Killing the process — reopen the app, then tap Compare.")
            handler.postDelayed({ android.os.Process.killProcess(android.os.Process.myPid()) }, 1000)
        }
        caption("Swiping the app away does NOT kill it — the agent's foreground service + keep-awake wake lock keep the process (and the loaded model, with its R3 state) alive. This ends the process for real, so the model re-loads fresh from the file on reopen. Use this BETWEEN Induce and Compare; reopen the app afterward.")

        button("Log engine + memory state") { AgentService.instance?.logEngineState("manual"); toast("Logged — see [statemap].") }
        caption("Snapshots the engine instance id + native memory, for the carrier hunt.")
    }

    /** Run a long state-map op off the UI thread with a running-toast then a result-toast. */
    private fun runMap(running: String, op: () -> String) {
        if (AgentService.instance == null) { toast("Start the agent first (needs the model loaded)."); return }
        if (baking) { toast("A bake or map is already running."); return }
        toast(running)
        Thread {
            val result = try { op() } catch (e: Throwable) { "error: ${e.message}" }
            handler.post { toast(result) }
        }.start()
    }

    // ---- 4. Tools (moved from Settings, plain captions) -------------------------------------------
    private fun buildTools() {
        sectionHeader("Tools")

        button("Show what's baked into the model") {
            toast("Reading what's resident + the byte diff…")
            Thread {
                val fp = try { ModelStore.activeFingerprint(applicationContext, settings) } catch (_: Throwable) { "" }
                val distilled = try { AgentMemory.distilledOperators(applicationContext, fp) } catch (_: Throwable) { emptySet<String>() }
                val status = try { ModelManifest.divergence(applicationContext) } catch (e: Exception) { "divergence read failed: ${e.message}" }
                AgentLog.log("selfmodel", "baked ops (resident): ${if (distilled.isEmpty()) "(none yet)" else distilled.sorted().joinToString(", ")}")
                runOnUiThread { toast("Resident: ${if (distilled.isEmpty()) "nothing yet" else "${distilled.size} op(s)"} · $status") }
            }.start()
        }
        caption("Lists the operators now resident in your model's weights (they've dropped from the prompt) and runs a byte-diff proving the model changed. Read-only; copy the [selfmodel] lines back.")

        button("Dump weight divergence (how far the model has changed)") {
            toast("Comparing your live model to the baseline…")
            Thread {
                val status = ModelManifest.divergence(applicationContext)
                runOnUiThread { toast(status) }
            }.start()
        }
        caption("Compares your live model file to the stored baseline and logs exactly how many bytes the baking/self-evolve has changed. This is the proof the weight editing worked. Reads the GB files on-device; nothing leaves the phone.")

        button("Test weight write (prove it sticks)") {
            if (AgentService.isAgentBusy) { toast("Agent is busy — run this when idle."); return@button }
            toast("Writing a test change + reverting…")
            Thread {
                AgentService.instance?.closeEngineForEdit()
                val status = SelfEvolve.writeVerifyTest(applicationContext, settings)
                runOnUiThread { toast(status) }
            }.start()
        }
        caption("Proves the weight WRITE path works, harmlessly: writes a known change to your model, confirms it stuck to disk, then reverts it (model left byte-identical). Answers 'are edits sticking?' in the [selfmodel] log.")

        button("Score operator residency (which need baking)") {
            toast("Scoring operators vs banked references… (can take minutes).")
            Thread {
                val svc = AgentService.instance
                if (svc == null) { runOnUiThread { toast("Start the agent first (needs the model loaded).") } }
                else { svc.runResidencyScoring(); runOnUiThread { toast("Residency scoring done — see the [selfmodel] agreement lines.") } }
            }.start()
        }
        caption("For the AUTOMATIC learned bake (world model + experience). Replays a decision with an operator's rule removed and checks whether the model still makes the same choice — LOW agreement means the operator is doing real work not yet in the weights. Needs banked references (use the agent normally). No model writes.")

        button("Revert the model to the last backup") {
            if (ModelStore.snapshots(applicationContext).isEmpty() && !ModelStore.hasBaseline(applicationContext)) {
                toast("No backups saved yet.")
            } else {
                toast("Reverting to the last good backup…")
                Thread {
                    val ok = ModelStore.restoreLatestSnapshot(applicationContext, settings) ||
                        ModelStore.restoreBaseline(applicationContext, settings)
                    if (ok) AgentService.instance?.reloadModel()
                    runOnUiThread { toast(if (ok) "Reverted to the last backup." else "Revert failed.") }
                }.start()
            }
        }
        caption("Undoes weight edits by restoring the most recent model backup (or the pristine baseline). Use it if a bake ever makes the model worse — the bakes are reversible by design, this is the belt-and-suspenders restore.")
    }

    private fun toast(t: String) = Toast.makeText(this, t, Toast.LENGTH_LONG).show()
}
