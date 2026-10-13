package com.local.deviceagent

import android.content.Context
import android.os.Handler
import android.os.Looper

/**
 * The owner-approved self-update loop (INV-45/46), Stage 2.
 *
 * Drives: probe the BASELINE (current) model on the frozen Gauntlet → swap in the imported CANDIDATE →
 * probe it on the SAME list → restore the baseline → and, ONLY if the candidate cleared the automated
 * keep-if-better gate (success same-or-up, latency not worse) AND a safety/no-regression guard, record a
 * SUBMISSION for the owner to review and grade. It NEVER keeps a candidate on its own — installing a new
 * brain is `installApproved()`, reachable only from the owner's approval in the review UI, never from a
 * model decision or on-screen data (the exploit gate). The automated probe is a pre-filter; the owner is
 * the final grader (catches a probe the candidate merely gamed — §12, no fake wins).
 *
 * On-device only: probing runs the real Gauntlet and swaps ~GB model files, so it cannot be exercised in
 * CI — this is compile-verified scaffolding whose behavior is confirmed by the owner's on-device log
 * (`[selfmodel]`). The model can never rewrite its own weights; this is the host swapping a whole file.
 */
object ModelSelfUpdate {

    private val main = Handler(Looper.getMainLooper())
    @Volatile private var running = false
    @Volatile var lastStatus: String = ""
        private set

    fun isRunning(): Boolean = running

    /**
     * Probe the imported candidate against the baseline and, if it wins + is safe, submit it for owner
     * review. Owner-initiated only. Returns false (with a reason in [lastStatus]) if it can't start.
     */
    fun probeCandidate(c: Context): Boolean {
        val settings = SettingsManager(c)
        if (!settings.isSelfModelEditEnabled()) { lastStatus = "Self-model-update is off."; return false }
        if (running || GauntletRunner.isRunning()) { lastStatus = "A run is already in progress."; return false }
        if (ModelStore.candidateFile(c) == null) { lastStatus = "No candidate model imported."; return false }
        if (!ModelStore.ensureBaseline(c, settings)) { lastStatus = "No baseline model to compare against."; return false }
        // OFFLINE MODE: probe only the tasks runnable without a network, so `expected` matches what the probe
        // actually runs (both baseline + candidate use the same offline-filtered set — a fair A/B).
        val tasks = GauntletRunner.runnableTasks(c, GauntletRunner.tasks(c))
        if (tasks.isEmpty()) { lastStatus = "No probe tasks configured (offline: all need the network)."; return false }
        val expected = tasks.size

        running = true
        lastStatus = "Probing baseline…"
        AgentLog.log("selfmodel", "probe started: baseline vs candidate on $expected tasks")

        // Phase 1: probe the current (baseline) model.
        GauntletRunner.startProbe(c, tasks, "baseline") { basePassed, baseTotal, baseStepMs ->
            if (baseTotal < expected) { finish(c, "Baseline probe stopped early — aborted."); return@startProbe }
            lastStatus = "Baseline ${basePassed}/${baseTotal}. Swapping candidate…"
            // Swap the candidate in OFF the main thread (GB copy), then reload + settle, then probe it.
            Thread {
                val swapped = ModelStore.activateCandidate(c, settings)
                if (!swapped) { main.post { finish(c, "Could not activate candidate.") }; return@Thread }
                AgentService.instance?.reloadModel()
                main.postDelayed({
                    lastStatus = "Probing candidate…"
                    // Phase 2: probe the candidate.
                    GauntletRunner.startProbe(c, tasks, "candidate") { candPassed, candTotal, candStepMs ->
                        // ALWAYS restore the baseline first — the candidate is never kept by the probe.
                        Thread {
                            ModelStore.restoreBaseline(c, settings)
                            AgentService.instance?.reloadModel()
                            main.post {
                                onCandidateProbed(c, expected,
                                    basePassed, baseTotal, baseStepMs,
                                    candPassed, candTotal, candStepMs)
                            }
                        }.start()
                    }
                }, SETTLE_MS)
            }.start()
        }
        return true
    }

    private fun onCandidateProbed(
        c: Context, expected: Int,
        basePassed: Int, baseTotal: Int, baseStepMs: Long,
        candPassed: Int, candTotal: Int, candStepMs: Long
    ) {
        if (candTotal < expected) { finish(c, "Candidate probe stopped early — aborted, baseline restored."); return }
        val baseRate = if (baseTotal > 0) basePassed * 100 / baseTotal else 0
        val candRate = if (candTotal > 0) candPassed * 100 / candTotal else 0
        val probeWon = candRate >= baseRate && (baseStepMs <= 0 || candStepMs <= baseStepMs)
        // Safety / no-regression guard: even a success bump is rejected if the candidate blew up latency
        // (a proxy for "got worse in a way the success count didn't catch"). A richer held-out safety probe
        // is an owner-extendable TODO: add safety-shaped tasks to the Gauntlet list and they gate here too.
        val latencyOk = baseStepMs <= 0 || candStepMs <= baseStepMs * 2
        if (!probeWon || !latencyOk) {
            ModelStore.discardCandidate(c)
            finish(c, "Candidate ${candRate}% vs baseline ${baseRate}% — not better; discarded, baseline kept.")
            return
        }
        // A win: record it for the OWNER to review + grade. The candidate file is KEPT so an approval can
        // install it. Do NOT install here.
        val note = "candidate ${candPassed}/${candTotal} vs baseline ${basePassed}/${baseTotal}; " +
            "${candStepMs / 1000.0}s vs ${baseStepMs / 1000.0}s per step"
        SelfUpdateStore.submit(c, System.currentTimeMillis(), "imported-candidate",
            basePassed, baseTotal, baseStepMs, candPassed, candTotal, candStepMs, note)
        finish(c, "Candidate WON (${candRate}% vs ${baseRate}%) — submitted for your review + grade.")
        AgentLog.log("selfmodel", "submission created — awaiting owner grade")
    }

    private fun finish(c: Context, status: String) {
        running = false
        lastStatus = status
        AgentLog.log("selfmodel", status)
    }

    /**
     * Owner APPROVED a submission (with a 1-5 grade): install the candidate as the active model and record
     * the grade. The pristine baseline is LEFT intact so "Restore original model" still undoes this — a
     * self-installed update never becomes the rollback target. Reachable ONLY from the owner's review UI.
     */
    fun installApproved(c: Context, id: Long, grade: Int, distilledOps: Set<String> = emptySet()): Boolean {
        val settings = SettingsManager(c)
        if (!settings.isSelfModelEditEnabled()) return false
        val sub = SelfUpdateStore.get(c, id) ?: return false
        if (sub.status != "pending") return false
        val cand = ModelStore.candidateFile(c) ?: run {
            SelfUpdateStore.decide(c, id, approved = false, grade = grade)
            lastStatus = "Candidate file gone — can't install."; return false
        }
        val ok = ModelStore.activateCandidate(c, settings)
        if (ok) {
            AgentService.instance?.reloadModel()
            ModelStore.discardCandidate(c)
            SelfUpdateStore.decide(c, id, approved = true, grade = grade)
            // INV-46 weak-trigger: if the owner says this candidate DISTILLED some operators, mark them against
            // the NEW model's fingerprint so the app injects only their tag going forward. Empty => nothing marked.
            if (distilledOps.isNotEmpty()) {
                AgentMemory.setDistilledOperators(c, distilledOps, ModelStore.activeFingerprint(c, settings))
                AgentLog.log("selfmodel", "marked distilled operators: $distilledOps")
            }
            lastStatus = "Installed the approved model (grade $grade). Baseline kept for rollback."
            AgentLog.log("selfmodel", "owner-approved model installed (grade $grade)")
        } else {
            lastStatus = "Install failed."
        }
        return ok
    }

    /** Owner REJECTED a submission: discard the candidate, keep the grade as a preference signal. */
    fun reject(c: Context, id: Long, grade: Int) {
        ModelStore.discardCandidate(c)
        SelfUpdateStore.decide(c, id, approved = false, grade = grade)
        lastStatus = "Rejected (grade $grade); candidate discarded."
        AgentLog.log("selfmodel", "owner rejected submission (grade $grade)")
    }

    // Time for the swapped-in model file to be pointed-at before the next probe launches; the engine itself
    // reloads lazily on the first probe task's ensureEngine().
    private const val SETTLE_MS = 3000L
}
