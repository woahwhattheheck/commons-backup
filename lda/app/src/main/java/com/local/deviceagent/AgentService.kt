package com.local.deviceagent

import android.Manifest
import android.app.NotificationManager
import android.app.SearchManager
import android.app.Service
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.media.AudioManager
import android.media.ToneGenerator
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.speech.tts.Voice
import androidx.core.content.ContextCompat
import org.json.JSONObject
import org.vosk.Model
import org.vosk.Recognizer
import org.vosk.android.RecognitionListener
import org.vosk.android.SpeechService
import java.util.Locale
import kotlin.concurrent.thread
import java.io.File

/**
 * Foreground service that owns the microphone (via Vosk) and TTS.
 *
 * A single always-on, offline Vosk recognizer does triple duty with no system
 * earcons:
 *  - IDLE: listen for the wake word ("hey agent") → capture a command.
 *  - CAPTURING: the next utterance is taken as the spoken command. The floating
 *    button (ACTION_LISTEN_NOW) jumps straight here, so push-to-speak and
 *    hands-free share one path.
 *  - BUSY: while a task runs, listen for "stop"/"cancel" so a shouted "stop"
 *    halts the agent immediately (checked on partial results for speed).
 *
 * Vosk is paused whenever the agent speaks so it never transcribes its own
 * voice (no self-triggering).
 */
class AgentService : Service(), TextToSpeech.OnInitListener, RecognitionListener {

    companion object {
        const val ACTION_STOP = "com.local.deviceagent.STOP"
        const val ACTION_STOP_TASK = "com.local.deviceagent.STOP_TASK"
        const val ACTION_RESUME = "com.local.deviceagent.RESUME"
        const val ACTION_LISTEN_NOW = "com.local.deviceagent.LISTEN_NOW"
        const val ACTION_CONVERSATION = "com.local.deviceagent.CONVERSATION"
        const val ACTION_RUN_COMMAND = "com.local.deviceagent.RUN_COMMAND"
        const val ACTION_TRAIN_START = "com.local.deviceagent.TRAIN_START"
        const val ACTION_TRAIN_FINISH = "com.local.deviceagent.TRAIN_FINISH"
        const val ACTION_LEARN_MODE = "com.local.deviceagent.LEARN_MODE"
        const val ACTION_AUTO_MODE = "com.local.deviceagent.AUTO_MODE"   // autonomous self-improve loop (owner-initiated toggle)
        const val ACTION_STATEMAP = "com.local.deviceagent.STATEMAP"     // adb-drivable state-map protocol (--es step fingerprint|induce|reload|compare|all)
        const val EXTRA_STEP = "step"                                    // which state-map step to run
        const val EXTRA_OP = "op"                                        // optional operator name for the induce step
        const val EXTRA_COMMAND = "command"
        const val EXTRA_GOAL = "goal"
        const val EXTRA_FROM_CHAT = "from_chat"
        const val EXTRA_RESUME = "resume"   // owner tapped "Resume" -> restore the killed run's saved context

        private const val SAMPLE_RATE = 16000.0f
        private const val CAPTURE_TIMEOUT_MS = 10000L
        private const val TTS_PAUSE_SAFETY_MS = 12000L
        private const val ANSWER_TIMEOUT_MS = 30000L
        // At/under this battery %, the agent refuses to run / shuts down — a hard
        // failsafe so it can never drain a nearly-dead phone. CRITICAL applies even while
        // charging; LOW_BATTERY_FLOOR is the higher floor when UNPLUGGED (GPU inference drains
        // fast and can die mid-task, so we don't even start a heavy task on a near-dead battery).
        private const val CRITICAL_BATTERY = 3
        private const val LOW_BATTERY_FLOOR = 5
        // Free the model this long after the agent goes IDLE (task done / chat walked-away), so RAM is
        // light when you're not using it. STRICTLY idle-only: it's cancelled the instant a task starts
        // and can't fire mid-task or mid-inference (see idleRelease's guard), so it never reaps a
        // working agent - it's housekeeping once the work is genuinely over, not a clock that kills it.
        private const val IDLE_RELEASE_MS = 30_000L
        // A live chat turn holds the MAIN engine for a full conversational cadence (not just 30s), so the
        // model isn't reaped-then-reloaded between messages while the owner is actively chatting (prewarm
        // only warms the tiny helper, so the 30s window used to let the main engine get reaped mid-chat).
        private const val CHAT_HOLD_MS = 120_000L

        @Volatile var isAgentBusy = false

        // Set while the service is alive so other UI (the Train screen) can reuse the ONE
        // model-backed brain instead of loading a second copy of the model into RAM.
        @Volatile var instance: AgentService? = null
    }

    /** The shared brain, or null if the model/service isn't up yet. */
    fun brainOrNull(): AgentBrain? = if (::brain.isInitialized) brain else null

    // Frees the model once the agent is genuinely IDLE so RAM is light when you're not using it. The
    // guard is the whole point: it unloads ONLY when no task is running, we're idle, AND no decision is
    // mid-inference - so it can never reap a working agent (the mid-task unload the owner hit). During a
    // task it's cancelled outright (acquireWakeLock); a real memory emergency is handled by onTrimMemory.
    // STATE-MAP HOLD (07-11): a state-map probe run must NOT be interrupted by the idle release closing the engine —
    // a reload re-instantiates the model from the file and would ERASE the very R3 store we're measuring (a false
    // negative on the induce test). While a mapping op runs, this flag blocks the idle close; the op re-arms it after.
    @Volatile private var stateMapping = false
    private val idleRelease = Runnable {
        if (!isAgentBusy && !stateMapping && mode == Mode.IDLE && brainOrNull()?.isGenerating() != true) brainOrNull()?.let {
            it.close()
            AgentLog.log("model", "released the model after going idle to keep RAM light (reloads instantly on next use)")
        }
    }

    /** Warm the model up so the first reply isn't the cold-start wait, and (re)arm the idle release so
     *  it frees once you're done. Called from the chat screen on open and on each message: each call
     *  pushes the release out, so the model stays warm while you're actively chatting and frees ~30s
     *  after you walk away. */
    fun warmBrain(activeChat: Boolean = false) {
        // CRASH FIX: a self-evolve/grow beat rewrites the model FILE with the engine closed (the `evolving`
        // interlock). Opening chat/calibration here would prewarm -> ensureEngine -> re-mmap the file mid-write
        // -> SIGBUS / a corrupt freshly-loaded engine. Skip the warm while a write is in flight; the beat is
        // brief and the next warmBrain re-arms it.
        if (evolving) return
        if (::brain.isInitialized) brain.prewarm()
        handler.removeCallbacks(idleRelease)
        // A real chat turn holds the model for a full conversational cadence (CHAT_HOLD_MS) so the main
        // engine isn't reaped-then-reloaded between messages; idle (walked-away) still frees after ~30s.
        handler.postDelayed(idleRelease, if (activeChat) CHAT_HOLD_MS else IDLE_RELEASE_MS)
    }

    /** Reload the main model after the owner swapped the model file (restore-baseline / install a
     *  candidate, INV-45). The brain LATCHES its engine and only re-reads getModelPath() after a close,
     *  so we closeSafely() (never tears down mid-inference) and let the next ensureEngine() rebuild from
     *  the new path. Safe to call when idle; a no-op if the brain isn't up yet. */
    fun reloadModel() {
        if (::brain.isInitialized) brain.closeSafely()
    }

    /** Free the loaded engine's mmap so the model FILE is writable for an owner-initiated maintenance edit (the
     *  write-verify self-test, `SelfEvolve.writeVerifyTest`). Mirrors the proven maybeSelfEvolve close-before-edit
     *  order — a synchronous `close()` (not closeSafely), so the caller can immediately write bytes. Only call idle;
     *  the Settings button guards on `isAgentBusy` first. Next `ensureEngine()` rebuilds from the (unchanged) path. */
    fun closeEngineForEdit() { try { if (::brain.isInitialized && !brain.isGenerating()) brain.close() } catch (_: Exception) {} }

    /** PHASE 2: score σ-off operator residency on the banked reference held-out tail and log `[selfmodel] agreement`.
     *  Owner-initiated (Settings button); runs on the caller's thread (each σ-off replay is a full decode, so this can
     *  take minutes for many references). Guarded on idle — never races a real decode. Needs the engine, which
     *  `AgentBrain.decideFromFrozen` loads on demand. No model writes. */
    fun runResidencyScoring() {
        if (isAgentBusy || (::brain.isInitialized && brain.isGenerating())) {
            AgentLog.log("selfmodel", "agreement: agent busy — run when idle"); return
        }
        if (!::brain.isInitialized) { AgentLog.log("selfmodel", "agreement: model not up — start a task first so the engine loads"); return }
        val scores = try { ResidencyScore.scoreAll(applicationContext, brain) } catch (e: Exception) {
            AgentLog.log("selfmodel", "agreement: scoring failed — ${e.message}"); return
        }
        // Surface BOTH halves of the supervision feed so the owner sees failure being banked, not just success
        // (learn-from-failure): proven-win references drive the σ-off scoring below; failure/contrast references feed
        // the off-device failure-contrast recipe + the contrastive bake signal.
        try {
            val fp = ModelStore.activeFingerprint(applicationContext, settings)
            val (pos, neg) = ReferenceStore.counts(applicationContext, fp)
            AgentLog.log("selfmodel", "references: $pos proven-win / $neg failure-contrast banked (this model)")
        } catch (_: Throwable) {}
        logReferenceInventory(null)   // SM4: per-operator ref counts + split state ("VERB: 7 refs — 1 held-out")
        if (scores.isEmpty()) { AgentLog.log("selfmodel", "agreement: no proven-win reference data yet — use the agent so it banks references (watch for 'reference +1'); failures alone can't be σ-off scored, only baked as contrast"); return }
        for (s in scores) AgentLog.log("selfmodel",
            "agreement: ${s.op}=${(s.exactAgree * 100).toInt()}% exact / ${(s.verbAgree * 100).toInt()}% verb " +
            "(n=${s.n} held-out) — LOW ⇒ operator carries real work not in W ⇒ bake candidate")
        // U3: also surface CONTRAST residency (how baked-in each operator's proven-BAD move is), so the owner sees
        // the failure half being consumed. HIGH ⇒ the bad mode is resident in W ⇒ the sign-flip bake pushes it away.
        try {
            val fp = ModelStore.activeFingerprint(applicationContext, settings)
            for (op in scores.map { it.op }.toSet()) {
                val c = try { ResidencyScore.scoreContrast(applicationContext, brain, op, fp) } catch (_: Exception) { null } ?: continue
                AgentLog.log("selfmodel",
                    "contrast: $op=${(c.exactAgree * 100).toInt()}% exact (n=${c.n} failures) — HIGH ⇒ bad move resident in W ⇒ bake pushes W away")
            }
        } catch (_: Throwable) {}
    }

    /** SM4 diagnostics (the fuel-fix): per-operator reference inventory + split state, so the owner SEES exactly how
     *  close each capability is to being scoreable/bakeable instead of a bare "nothing happens" — e.g. "VERB: 7
     *  proven-win refs — 1 held-out" / "SCHEMA: 3 proven-win refs — need ≥5 to score". [only] filters to a capability
     *  set (the action-layer bake set); null = every operator with references. Read-only; guarded. */
    private fun logReferenceInventory(only: Set<String>?) {
        try {
            val fp = ModelStore.activeFingerprint(applicationContext, settings)
            val ops = ReferenceStore.operators(applicationContext, fp)
                .filter { only == null || it.uppercase() in only }.sorted()
            if (ops.isEmpty()) {
                // P0.6 honest diagnostics: say the TRUE reason, not just "none banked". This inventory serves the
                // AUTOMATIC LEARNED bake (world model + experience) — banking fires only DURING a task step
                // (scoreLastOperator), so a cold session banks zero (expected, not broken). The DEFINED operators +
                // action layer do NOT need references at all now — the Bake button installs them directly
                // (runDefinedBake). So an empty learned-feed just means "use the phone so the world model/experience
                // accrue"; it is never why the Bake button does nothing.
                AgentLog.log("selfmodel", "references: none banked yet${if (only != null) " for this pool" else ""} — the LEARNED bake (world model / experience) banks DURING a task; use the phone so it accrues. The DEFINED operators install directly off the Bake button (no references needed).")
                return
            }
            for (op in ops) {
                val (train, held) = ReferenceStore.split(applicationContext, op, fp)
                val total = train.size + held.size
                val fails = ReferenceStore.failuresFor(applicationContext, op, fp).size
                // P0.2: a bake is reachable at ~6 refs (held-out ≥ MIN_HELDOUT=2), not ~15 — reflect the real threshold.
                val state = if (held.size < 2) "need ~${(6 - total).coerceAtLeast(1)} more to score (have $total)" else "${held.size} held-out — bakeable"
                AgentLog.log("selfmodel", "$op: $total proven-win refs — $state${if (fails > 0) " · $fails contrast" else ""}")
            }
        } catch (_: Throwable) {}
    }

    /** PHASE 3 (INV-74): ONE σ-off-gated directed ScaleBake attempt on the lowest-residency proven operator. Owner-
     *  initiated (Settings button); runs on the caller's thread (selects + writes + reloads + re-scores = several
     *  decodes, minutes). Safe by construction: an edit is KEPT only if it RAISED the operator's σ-off agreement AND
     *  the model stays coherent; otherwise `WeightGenome` reverts it exactly. Flag `directed_bake` (default off) +
     *  idle-guarded. Recovery net = snapshot + WeightGenome revert + brick-guard. */
    fun runDirectedBake() = bakeOnce(only = null, prefix = "scalebake")

    /** PART R (v3 — owner reframe 07-10 EVE, supersedes the retired "prove the bake"): the DIRECT DEFINED-OPERATOR
     *  INSTALL that the Bake button now runs. The owner's correction was unambiguous: "the bake button needs to push
     *  operators you DEFINE and create plus the action layer to the model." So this stops banking references / running a
     *  gauntlet probe (the rejected shape) and instead installs the WHOLE defined library — every BAKED operator + the
     *  action layer (SCHEMA/NAVIGATE/VERB/LAYOUT) — straight into the weights, reference-free, via `ScaleBake.
     *  bakeOperatorDirect` (canned probes → σ-on/σ-off → bounded scale nudge kept only if non-degrading + moved W toward
     *  the state, else exact revert). An operator is a KNOWN operational state (valid by construction), so this INSTALLS
     *  it — it does not have to be proven over task wins. Each RESIDENT/INSTALLED operator graduates into `distilledOps`
     *  ⇒ its prompt text collapses to the ~1-token TAG (owner: "no operator should exist outside of the model — make the
     *  model store them all"; R4 drop-seam). Owner-INITIATED (Settings button), runs on the CALLER's thread while idle;
     *  the `evolving` interlock + snapshot + brick-guard + WeightGenome revert are the recovery net. Time-budgeted +
     *  resumable (already-resident ops are skipped instantly on the next tap) so a long library install can't wedge —
     *  §13 no-silent-cap: deferred operators are LOGGED. The idle `maybeBake` beat is the AUTOMATIC LEARNED bake (world
     *  model + experience), a distinct path — the button is the defined install. */
    /** Live progress for the Baking screen (B2). [index]/[total] = which operator; [status] = a short human phase
     *  ("measuring…", "installing…", "INSTALLED σ-off 33%→100%"); [done] flags the final line. Kept on
     *  [lastBakeProgress] so a re-attaching Activity sees mid-bake state. */
    data class BakeProgress(val index: Int, val total: Int, val op: String, val status: String, val done: Boolean = false, val finished: Boolean = false)
    @Volatile var lastBakeProgress: BakeProgress? = null

    private fun bakeKindStr(k: ScaleBake.Kind): String = when (k) {
        ScaleBake.Kind.RESIDENT -> BakeHistory.RESIDENT
        ScaleBake.Kind.INSTALLED -> BakeHistory.INSTALLED
        ScaleBake.Kind.PARTIAL -> BakeHistory.PARTIAL
        ScaleBake.Kind.TRIED -> BakeHistory.NOOP
        ScaleBake.Kind.SKIP -> BakeHistory.SKIP
    }

    /** Graduate a resident/installed operator into the drop-seam so it leaves the prompt (R4). */
    private fun graduateBaked(names: Collection<String>, fp: String) {
        if (names.isEmpty()) return
        val now = AgentMemory.distilledOperators(applicationContext, fp) + names.map { it.uppercase() }
        AgentMemory.setDistilledOperators(applicationContext, now, fp)
        ReasoningOperators.distilledOps = now.map { it.uppercase() }.toSet()   // live drop-seam for the next task's prompt
    }

    fun runDefinedBake(onProgress: (BakeProgress) -> Unit = {}) {
        if (teardownRequested) return
        if (!settings.isDirectedBakeEnabled()) { AgentLog.log("selfmodel", "definedbake: directed_bake is OFF (enable it in Settings)"); return }
        if (isAgentBusy || (::brain.isInitialized && brain.isGenerating())) { AgentLog.log("selfmodel", "definedbake: agent busy — run when idle"); return }
        if (!::brain.isInitialized) { AgentLog.log("selfmodel", "definedbake: model not up — start the agent first"); return }
        if (evolving) { AgentLog.log("selfmodel", "definedbake: another weight beat is running — try again shortly"); return }
        val fp = ModelStore.activeFingerprint(applicationContext, settings)
        val already = AgentMemory.distilledOperators(applicationContext, fp)
        val installSet = ReasoningOperators.definedInstallSet()
        val todo = installSet.filter { it.uppercase() !in already }
        if (todo.isEmpty()) {
            AgentLog.log("selfmodel", "definedbake: all ${installSet.size} defined operators already resident in W — nothing to install")
            val p = BakeProgress(0, 0, "", "All ${installSet.size} operators already resident in the model — nothing to bake.", finished = true)
            lastBakeProgress = p; onProgress(p); return
        }
        evolving = true                         // mmap-race interlock (bakeOperatorDirect closes+reloads the engine)
        evolveThread = Thread.currentThread()   // captured so onDestroy's bounded join lets an in-flight write+fsync finish
        val graduated = LinkedHashSet<String>()
        val total = todo.size
        var installed = 0; var resident = 0; var partial = 0; var tried = 0; var skipped = 0; var deferred = 0
        fun emit(i: Int, op: String, status: String, done: Boolean = false, finished: Boolean = false) {
            val p = BakeProgress(i, total, op, status, done, finished); lastBakeProgress = p; onProgress(p)
        }
        try {
            SelfEvolve.maybeSnapshot(applicationContext, settings)   // one recovery point before the whole batch
            val deadline = System.currentTimeMillis() + 15 * 60 * 1000L   // bound the button's wall-clock; the rest resumes on the next tap
            AgentLog.log("selfmodel", "definedbake: installing $total defined operator(s) into the weights (already resident: ${already.size}) — reference-free, several minutes")
            emit(0, "", "Baking $total operator(s) into the model (${already.size} already resident)…")
            for ((idx, op) in todo.withIndex()) {
                if (teardownRequested) break
                if (System.currentTimeMillis() > deadline) {
                    deferred = total - (installed + resident + partial + tried + skipped)
                    AgentLog.log("selfmodel", "definedbake: time budget reached — $deferred operator(s) deferred; tap Bake again to continue (resident ops skip instantly)")
                    break
                }
                val i = idx + 1
                emit(i, op, "measuring…")
                val d = try {
                    ScaleBake.bakeOperatorDirect(applicationContext, brain, settings, op) { ph ->
                        emit(i, op, if (ph == ScaleBake.Phase.MEASURING) "measuring…" else "installing…")
                    }
                } catch (e: Throwable) {
                    AgentLog.log("selfmodel", "definedbake: $op error — ${e.message}"); try { brain.probeCoherent() } catch (_: Throwable) {}
                    emit(i, op, "error: ${e.message}"); continue
                }
                when (d.kind) {
                    ScaleBake.Kind.RESIDENT  -> { resident++;  graduated += op.uppercase(); AgentLog.log("selfmodel", "definedbake RESIDENT $op — ${d.desc} (drops from the prompt)") }
                    ScaleBake.Kind.INSTALLED -> { installed++; graduated += op.uppercase(); AgentLog.log("selfmodel", "definedbake INSTALLED $op — ${d.desc} (drops from the prompt)") }
                    ScaleBake.Kind.PARTIAL   -> { partial++;   AgentLog.log("selfmodel", "definedbake PARTIAL $op — ${d.desc} (edits kept; prompt text kept until fully resident)") }
                    ScaleBake.Kind.TRIED     -> { tried++;     AgentLog.log("selfmodel", "definedbake no-op $op — ${d.desc} (nothing stuck; prompt text kept)") }
                    ScaleBake.Kind.SKIP      -> { skipped++;   AgentLog.log("selfmodel", "definedbake skip $op — ${d.desc}") }
                }
                BakeHistory.record(applicationContext, op, false, bakeKindStr(d.kind), d.before, d.after, d.bytes, System.currentTimeMillis())
                emit(i, op, "${bakeKindStr(d.kind)} — ${d.desc}", done = true)
            }
            graduateBaked(graduated, fp)
            val summary = "Done: ${installed + resident} resident in the model ($installed installed, $resident already), $partial partial, $tried no change, $skipped skipped" +
                (if (deferred > 0) ", $deferred deferred (tap Bake again)" else "")
            AgentLog.log("selfmodel", "definedbake done: ${installed + resident} resident in W ($installed installed, $resident already), $partial partial, $tried no-op, $skipped skipped, $deferred deferred — 'Dump weight divergence' to see the bytes")
            emit(total, "", summary, done = true, finished = true)
        } catch (e: Throwable) {
            AgentLog.log("selfmodel", "definedbake batch error: ${e.message}")
            try { if (::brain.isInitialized) brain.probeCoherent() } catch (_: Throwable) {}
            emit(total, "", "Bake error: ${e.message}", finished = true)
        } finally {
            evolving = false; evolveThread = null
        }
    }

    /** CUSTOM BAKE (owner's ask, 07-10): install ONE owner-authored operator (name + explicit rule) off the same
     *  spine as the built-ins. Same gates + snapshot + evolving interlock + brick-guard; writes a BakeHistory row;
     *  graduates it into the drop-seam if it installs. [onProgress] drives the Baking screen's progress view. */
    fun runCustomBake(name: String, rule: String, onProgress: (BakeProgress) -> Unit = {}) {
        if (teardownRequested) return
        if (rule.isBlank()) { AgentLog.log("selfmodel", "custombake: '$name' has no rule to install"); return }
        if (!settings.isDirectedBakeEnabled()) { AgentLog.log("selfmodel", "custombake: directed_bake is OFF (enable it in Settings)"); return }
        if (isAgentBusy || (::brain.isInitialized && brain.isGenerating())) { AgentLog.log("selfmodel", "custombake: agent busy — run when idle"); return }
        if (!::brain.isInitialized) { AgentLog.log("selfmodel", "custombake: model not up — start the agent first"); return }
        if (evolving) { AgentLog.log("selfmodel", "custombake: another weight beat is running — try again shortly"); return }
        evolving = true
        evolveThread = Thread.currentThread()
        fun emit(status: String, done: Boolean = false, finished: Boolean = false) {
            val p = BakeProgress(1, 1, name, status, done, finished); lastBakeProgress = p; onProgress(p)
        }
        try {
            SelfEvolve.maybeSnapshot(applicationContext, settings)
            AgentLog.log("selfmodel", "custombake: installing your operator '$name' into the weights…")
            emit("measuring…")
            val d = ScaleBake.bakeOperatorDirect(applicationContext, brain, settings, name, rule) { ph ->
                emit(if (ph == ScaleBake.Phase.MEASURING) "measuring…" else "installing…")
            }
            BakeHistory.record(applicationContext, name, true, bakeKindStr(d.kind), d.before, d.after, d.bytes, System.currentTimeMillis())
            if (d.kind == ScaleBake.Kind.RESIDENT || d.kind == ScaleBake.Kind.INSTALLED)
                graduateBaked(listOf(name), ModelStore.activeFingerprint(applicationContext, settings))
            AgentLog.log("selfmodel", "custombake ${bakeKindStr(d.kind)} $name — ${d.desc}")
            emit("${bakeKindStr(d.kind)} — ${d.desc}", done = true, finished = true)
        } catch (e: Throwable) {
            AgentLog.log("selfmodel", "custombake error: ${e.message}")
            try { if (::brain.isInitialized) brain.probeCoherent() } catch (_: Throwable) {}
            emit("error: ${e.message}", finished = true)
        } finally {
            evolving = false; evolveThread = null
        }
    }

    // ── STATE MAP (07-11): measure the R3 finding — processing an operator σ stores a durable change IN THE LOADED
    // MODEL (owner-established E1/E2/E4 + Edge-app). Each method runs StateProbe's greedy, zero-history battery and logs
    // [statemap]; NONE writes the model file. Shared guard: engine up + idle (they call decideFromFrozen repeatedly, so a
    // concurrent real decode would corrupt the reading). Owner-facing captions live in BakingActivity's "Map" section. ──
    private fun stateMapReady(tag: String): Boolean {
        if (!::brain.isInitialized) { AgentLog.log("statemap", "$tag: model not up — start the agent first"); return false }
        if (isAgentBusy || brain.isGenerating() || evolving || stateMapping) { AgentLog.log("statemap", "$tag: agent busy — run when idle"); return false }
        return true
    }

    /** Hold the model loaded (block the idle release) for the duration of a mapping op, then re-arm the release so RAM
     *  still frees afterward. Without this, an idle reload mid-op re-instantiates the model from the file and erases
     *  the R3 store we're measuring — a false negative. */
    private fun <T> withStateMapHold(block: () -> T): T {
        stateMapping = true
        handler.removeCallbacks(idleRelease)
        return try { block() } finally {
            stateMapping = false
            handler.postDelayed(idleRelease, IDLE_RELEASE_MS)
        }
    }

    /** Read the battery on the CURRENT model and save it under [tag]. The reference for later comparisons. */
    fun runStateFingerprint(tag: String = "baseline"): String {
        if (!stateMapReady("fingerprint")) return "Start the agent first, and run when idle."
        return withStateMapHold {
            val r = StateProbe.readBattery(brain)
            StateProbe.save(applicationContext, tag, r)
            AgentLog.log("statemap", "fingerprint '$tag' — ${r.summary()} :: ${r.tokens.joinToString(" / ")}")
            "Fingerprint '$tag' saved — ${r.summary()}. See [statemap]."
        }
    }

    /** THE E5 TEST (the good-case version of what E1/E2/E4 showed with corruption): baseline battery → process a
     *  well-formed operator σ (default ACCURACY) through the loaded model → battery again (zero-history, σ ABSENT) →
     *  report the shift. A shift ⇒ the operator stored state in the loaded model (R3). Saves 'preinduce' + 'induced'
     *  for the restart discriminator. */
    fun runInduceAndMeasure(opName: String = "ACCURACY"): String {
        if (!stateMapReady("induce")) return "Start the agent first, and run when idle."
        // Resolve the rule from ANY source: a BAKED built-in by name, else the owner's CUSTOM operator by name (the
        // owner's ACCURACY exemplar lives in CustomOperatorStore, not BAKED), else the first custom op, else built-in
        // REFUSE. So the button works whether or not the owner has saved a custom operator; log which one it used.
        // Resolve the σ to induce: the CORRUPTOR positive control, OR an operator rule (BAKED ∪ custom ∪ first custom
        // ∪ REFUSE). The induce runs via the CHAT PATH (temp sampler) — the only path that tips R3 (greedy can't).
        var name = opName
        var rule = ""
        if (opName.equals("CORRUPTOR", true)) { name = "CORRUPTOR"; rule = StateProbe.CORRUPTOR_SIGMA }
        else {
            rule = ReasoningOperators.ruleOf(opName)
            if (rule.isBlank()) rule = CustomOperatorStore.list(applicationContext).firstOrNull { it.name.equals(opName, true) }?.rule.orEmpty()
            if (rule.isBlank()) CustomOperatorStore.list(applicationContext).firstOrNull()?.let { name = it.name; rule = it.rule }
            if (rule.isBlank()) { name = "REFUSE"; rule = ReasoningOperators.ruleOf("REFUSE") }
        }
        if (rule.isBlank()) { AgentLog.log("statemap", "induce: no σ for '$opName' (no operator, no custom, no REFUSE)"); return "No σ found for '$opName'." }
        return withStateMapHold {                                       // no idle reload between induce and re-measure
            val before = StateProbe.readBattery(brain); StateProbe.save(applicationContext, "preinduce", before)
            AgentLog.log("statemap", "induce '$name' (CHAT PATH, temp sampler): baseline ${before.summary()} :: ${before.tokens.joinToString(" / ")}")
            val induceOuts = StateProbe.induce(brain, rule)            // establish via the temp/chat path — the R3-tipping route
            AgentLog.log("statemap", "  induce turns (did the induce ITSELF degenerate?): ${induceOuts.mapIndexed { i, s -> "[$i] ${s.take(80)}" }.joinToString(" | ")}")
            val after = StateProbe.readBattery(brain); StateProbe.save(applicationContext, "induced", after)
            // stamp the PID so a later "compare after restart" can detect it's the SAME process (nothing to compare).
            applicationContext.getSharedPreferences("state_probe", android.content.Context.MODE_PRIVATE).edit().putInt("induced_pid", android.os.Process.myPid()).apply()
            val cmp = StateProbe.compare(before, after)
            AgentLog.log("statemap", "induce '$name': AFTER (σ absent, greedy) ${after.summary()} :: $cmp")
            AgentLog.log("statemap", "  tokens before: ${before.tokens.joinToString(" / ")}")
            AgentLog.log("statemap", "  tokens after : ${after.tokens.joinToString(" / ")}")
            AgentLog.log("statemap", "  raw after: ${StateProbe.rawDump(after)}")
            "Induced $name → $cmp. See [statemap]."
        }
    }

    /** Reload the engine (close + fresh Engine, same process), re-read the battery, compare to the 'induced' reading.
     *  Shift SURVIVES the reload ⇒ it lives in the loaded model a new Engine re-attaches to (R3), not the conversation.
     *  Logs engine instance ids + native heap around the reload for the carrier hunt. */
    fun runReloadReprobe(): String {
        if (!stateMapReady("reload")) return "Start the agent first, and run when idle."
        return withStateMapHold {                                      // the close() below is the ONE intentional reload
            val induced = StateProbe.load(applicationContext, "induced")
            brain.logEngineState("reload:before")
            brain.close()                                              // drop the Engine; the next decode builds a fresh one
            val after = StateProbe.readBattery(brain)                  // first probe reloads a new Engine
            brain.logEngineState("reload:after")
            StateProbe.save(applicationContext, "postreload", after)
            val cmp = if (induced != null) StateProbe.compare(induced, after) else "(no 'induced' reading — run Induce first)"
            AgentLog.log("statemap", "reload: ${after.summary()} vs induced :: $cmp")
            "After engine reload: $cmp. See [statemap]."
        }
    }

    /** THE RESTART DISCRIMINATOR — run AFTER a full process kill + relaunch: read the battery now and compare to the
     *  saved readings. Close to 'induced' ⇒ the state SURVIVED the restart ⇒ it is in the FILE (R4). Close to
     *  'preinduce' ⇒ it was in the loaded model, cleared by the restart (R3). This is the test we could not run before. */
    fun runCompareToSaved(): String {
        if (!stateMapReady("compare")) return "Start the agent first, and run when idle."
        val pre = StateProbe.load(applicationContext, "preinduce")
        val induced = StateProbe.load(applicationContext, "induced")
        if (pre == null || induced == null) { AgentLog.log("statemap", "compare: no saved readings — run Induce first"); return "Run Induce first." }
        // PROTOCOL GUARD: this test is only meaningful AFTER a process restart. If the induce ran in THIS same process,
        // the loaded model still holds the state, so we'd just be comparing it to itself (the 07-11 flat-0% mistake).
        val inducedPid = applicationContext.getSharedPreferences("state_probe", android.content.Context.MODE_PRIVATE).getInt("induced_pid", -1)
        if (inducedPid == android.os.Process.myPid()) {
            AgentLog.log("statemap", "compare: SAME PROCESS as the induce (pid $inducedPid) — swiping the app away does NOT kill it (foreground service + wake lock keep it alive); use the 'RESTART the app process' button, then reopen and compare")
            return "Same process as the induce — swiping away doesn't kill it. Tap 'RESTART the app process', reopen, then Compare."
        }
        return withStateMapHold {
            val now = StateProbe.readBattery(brain)
            AgentLog.log("statemap", "compare-now vs PRE-induce    :: ${StateProbe.compare(pre, now)}")
            AgentLog.log("statemap", "compare-now vs INDUCED state  :: ${StateProbe.compare(induced, now)}")
            AgentLog.log("statemap", "  ⇒ near INDUCED = survived restart (R4/file) · near PRE = cleared by restart (R3/loaded)")
            "Compared — see [statemap] (near INDUCED = file/R4, near PRE = loaded/R3)."
        }
    }

    /** One-shot engine/native-memory snapshot for the carrier hunt. */
    fun logEngineState(tag: String = "manual") { if (::brain.isInitialized) brain.logEngineState(tag) }

    /** [tier2] STATE CANARY (M1 — "see the machine") — a periodic read of the DURABLE runtime state so the owner can
     *  WATCH Tier 2 live (§docs OPERATIONAL_STATES §2.10) instead of only discovering a durable shift when a task breaks.
     *  Reads the greedy battery, compares to a saved baseline, and reports HELD / DRIFTED / DEGENERATE. First run (no
     *  baseline) ESTABLISHES it. DEGENERATE = a probe went incoherent (the R3-corruption signature — what the CORRUPTOR
     *  positive control should trip); DRIFTED = a coherent content shift past the threshold; HELD = stable. Read-only
     *  w.r.t. the model, log-only, gated on tier_observ. Same idle-hold as the state-map ops so no reload erases R3. */
    fun runTier2Canary(): String {
        if (!::settings.isInitialized || !settings.isTierObservEnabled()) return "Tier observability is off."
        if (!stateMapReady("tier2")) return "Start the agent first, and run when idle."
        return withStateMapHold {
            val now = StateProbe.readBattery(brain)
            val baseline = StateProbe.load(applicationContext, "tier2_baseline")
            if (baseline == null) {
                StateProbe.save(applicationContext, "tier2_baseline", now)
                AgentLog.log("tier2", "baseline set — ${now.summary()} (HELD by definition; re-run to detect drift/degeneration)")
                "Tier-2 baseline set — ${now.summary()}. Re-run to detect drift."
            } else {
                val div = StateProbe.contentDivPct(baseline, now)
                val verdict = when {
                    now.garbage > 0 -> "DEGENERATE"          // a probe went incoherent = the R3-corruption signature
                    div >= 30 -> "DRIFTED"                    // coherent but a real content shift from baseline (tunable)
                    else -> "HELD"
                }
                AgentLog.log("tier2", "$verdict — dist ${div}% from baseline · ${now.summary()}" +
                    (if (now.garbage > 0) " · ${now.garbage} probe(s) degenerate (R3 signature — a process restart clears R3)" else ""))
                "Tier-2: $verdict (dist ${div}% from baseline). See [tier2]."
            }
        }
    }

    /** On-demand [metrics] snapshot (M1) — the same rolling line the task-end emits, for the Tiers & state screen so the
     *  owner can read every core metric between tasks. Cheap fields only (the GB-file weight-divergence stays the
     *  separate 'Dump weight divergence' button). Log-only, gated on tier_observ. */
    fun runMetricsSnapshot(): String {
        if (!::settings.isInitialized || !settings.isTierObservEnabled()) return "Tier observability is off."
        val (n, succ, pct) = TaskHistory.rollingSuccessRate(applicationContext)
        val iat = if (::brain.isInitialized) brain.inferMeterSummary() else ""
        val promptTok = AgentBrain.lastPromptTokens
        AgentLog.log("metrics", "success ${pct}% ($succ/$n) · promptTok=$promptTok · " +
            "bakedOps=${ReasoningOperators.distilledOps.size} · latency ${iat.ifBlank { "n/a" }}")
        return "success ${pct}% ($succ/$n) · promptTok=$promptTok · bakedOps=${ReasoningOperators.distilledOps.size}. See [metrics]."
    }

    /** ALL-IN-ONE DIAGNOSTIC (07-11, owner: "one test button that dumps everything… usable from your end too"). Runs the
     *  whole READ-ONLY measurement battery and dumps it as ONE greppable `[diag]` block: engine/RAM state, the `[tiers]`
     *  scaffold breakdown (which block is fattest to bake), the `[tier2]` durable-state canary, `[metrics]`, weight
     *  divergence, and baked ops — so neither the owner nor a tethered session taps a dozen buttons. Triggerable by the
     *  Baking button AND over adb via `DiagReceiver` (`adb shell am broadcast -a com.local.deviceagent.DIAG`, debug builds
     *  only). READ-ONLY: no task, no phone driving, no account access — §3-safe. Call OFF the main thread (it decodes). */
    fun runFullDiagnostic(): String {
        if (!::brain.isInitialized) { AgentLog.log("diag", "model not up — start the agent first"); return "Start the agent first." }
        val build = try {
            val pi = applicationContext.packageManager.getPackageInfo(packageName, 0)
            "installed ${java.text.SimpleDateFormat("MM-dd HH:mm", java.util.Locale.US).format(java.util.Date(pi.lastUpdateTime))}"
        } catch (_: Throwable) { "?" }
        AgentLog.log("diag", "═════════ DIAG START ($build) ═════════")
        // DECODE-FREE by design (07-11): the one-tap diagnostic must be INSTANT + reliable. Everything here builds
        // strings / reads files — NO model decodes. The Tier-2 durable-state read needs 8 greedy decodes (the state
        // battery), which on this device can be MINUTES per decode → it stays the separate "Read the durable state now"
        // button, never bundled here (bundling it wedged the one-tap for 40 min).
        try { brain.logEngineState("diag") } catch (_: Throwable) {}
        try { brain.logScaffoldBreakdown() } catch (_: Throwable) {}          // → [tiers] per-block breakdown (the fattest bake target)
        try { runMetricsSnapshot() } catch (_: Throwable) {}                  // → [metrics] (no decode)
        try { AgentLog.log("diag", "weights: ${ModelManifest.divergence(applicationContext)}") }
        catch (e: Throwable) { AgentLog.log("diag", "weights: divergence read failed — ${e.message}") }
        try {
            val fp = ModelStore.activeFingerprint(applicationContext, settings)
            val d = AgentMemory.distilledOperators(applicationContext, fp)
            AgentLog.log("diag", "baked ops (resident in W): ${if (d.isEmpty()) "none yet" else d.sorted().joinToString(",")}")
        } catch (_: Throwable) {}
        AgentLog.log("diag", "(Tier-2 durable-state read = the separate 'Read the durable state now' button — slow, 8 decodes)")
        AgentLog.log("diag", "═════════ DIAG END ═════════")
        return "Diagnostic dumped — copy the [diag] block from the log."
    }

    // ============ COO — THE CONTINUOUS OPERATOR OBSERVATORY (07-12) ============
    // A free-running generation loop with NO task/screen/scaffold, so the active operator (or `none`) is the ONLY thing
    // steering the output → the cleanest possible measure of "operator = selective computation", dumped to a greppable
    // [obs] log a tethered session reads. Live-controlled over adb via DiagReceiver (debug-gated). §3-safe: PURE
    // generation into a log — no task, no phone driving, no account access; operator text is owner-supplied over debug adb.
    @Volatile private var obsRunning = false
    @Volatile private var obsOp = "none"          // active operator name, or "none" (raw-model control)
    @Volatile private var obsVar = ""             // injected VARIABLE device data (the operator's data-stream half)
    @Volatile private var obsTrajectory = false   // false = fresh (fixed seed, pure influence); true = feed output back (watch the attractor form)
    @Volatile private var obsGreedy = false       // false = temp 0.7 (dynamics/R3 path); true = greedy (reproducible A/B)
    @Volatile private var obsSigma = ""           // RAW σ text (obs_sigma) — overrides the named op so ANY operator is testable with no rebuild
    @Volatile private var obsCap = 0              // v3 (obs_cap): decode cap in tokens; 0 = the phase default. Worksheet-prone σ ran 68-90s to the cap on-device — sweeps want it tight, introspects want it long.
    @Volatile private var obsAb = ""              // v3 (obs_ab): "OP1,OP2" — PAIRED A/B: each iteration runs BOTH on the SAME var/seed and logs one atomic diff line. The plan's "biggest lack"; the manual flip dance mislabeled a sweep step on 07-12.
    private var obsThread: Thread? = null

    // v3: steering a DEAD loop is silent no more — the 07-12 session set a lean-ANCHOR σ on an expired loop and burned
    // 60 polls before noticing. The settings still stage (they apply on the next `obs on`), but the log now says so.
    private fun obsStagedNote() = if (!obsRunning) "   ⚠ loop NOT running — staged; send `--es obs on`" else ""

    fun setObsOp(name: String) {
        val n = name.trim().ifBlank { "none" }; obsOp = n; obsSigma = ""   // a NAMED-op selection clears any custom raw σ
        val known = n.equals("none", true) || (try { ReasoningOperators.ruleOf(n).isNotBlank() } catch (_: Throwable) { false })
        AgentLog.log("obs", "op = $n${if (known) "" else " (unknown operator — will generate RAW)"}${obsStagedNote()}")
    }
    /** RAW σ injection (obs_sigma): pass the operator's formal rule TEXT directly — so a NEW operator (RESOLVE, or one the
     *  owner types live) is testable over adb with NO rebuild. Blank clears it (back to the named op). */
    fun setObsSigma(s: String) {
        obsSigma = s
        if (s.isNotBlank()) obsOp = "custom"
        AgentLog.log("obs", "sigma = ${if (s.isBlank()) "(cleared → named op)" else "custom σ (${s.length} chars): ${s.replace("\n", " ").take(70)}…"}${obsStagedNote()}")
    }
    fun setObsVar(v: String) { obsVar = v; AgentLog.log("obs", "var = ${if (v.isBlank()) "(cleared)" else "\"${v.take(80)}\""}${obsStagedNote()}") }
    fun setObsMode(trajectory: Boolean) { obsTrajectory = trajectory; AgentLog.log("obs", "mode = ${if (trajectory) "trajectory (feed-back)" else "fresh (fixed seed)"}${obsStagedNote()}") }
    fun setObsSampler(greedy: Boolean) { obsGreedy = greedy; AgentLog.log("obs", "sampler = ${if (greedy) "greedy (reproducible)" else "temp 0.7 (dynamics)"}${obsStagedNote()}") }
    fun setObsCap(n: Int) { obsCap = n.coerceIn(0, 2048); AgentLog.log("obs", "cap = ${if (obsCap == 0) "(phase default)" else "$obsCap tok"}${obsStagedNote()}") }
    /** PAIRED A/B (obs_ab): "OP1,OP2" (either may be `none`). Each iteration runs BOTH arms on the SAME var/seed, greedy
     *  or temp per obs_sampler, and logs ONE atomic line with an A-vs-B similarity — the operator delta with nothing else
     *  moving. Blank clears (back to single-op mode). */
    fun setObsAb(s: String) {
        val pair = s.split(",").map { it.trim() }.filter { it.isNotEmpty() }
        obsAb = if (pair.size == 2) "${pair[0]},${pair[1]}" else ""
        AgentLog.log("obs", "ab = ${if (obsAb.isBlank()) "(cleared → single-op)" else obsAb}${obsStagedNote()}")
    }

    /** Start the observatory for a BOUNDED [seconds] (clamped 15s..30min — "continuous for a while, not forever"). */
    fun startObsLoop(seconds: Int) {
        if (obsRunning) { AgentLog.log("obs", "already running — 'obs off' to stop first"); return }
        if (!::brain.isInitialized) { AgentLog.log("obs", "model not up — start the agent first"); return }
        if (isAgentBusy || evolving || brain.isGenerating() || stateMapping) { AgentLog.log("obs", "agent busy — start when idle"); return }
        val secs = seconds.coerceIn(15, 1800)
        obsRunning = true
        obsThread = Thread {
            stateMapping = true                              // hold the model loaded (block the idle reload that would erase the warm state mid-run)
            handler.removeCallbacks(idleRelease)
            val deadline = System.currentTimeMillis() + secs * 1000L
            var iter = 0; var trajectory = ""; var lastOut = ""
            // v2 per-op SCOREBOARD (the summary / the paired A/B: flip op mid-run → compare the per-op verdicts).
            // v3: abSim tracked SEPARATELY from selfSim — they are opposite-polarity metrics (selfSim HIGH = black-hole
            // onset; abSim LOW = the operator changes the output). Blending them made the SUMMARY lie in mixed runs.
            class OpStat { var n = 0; var coh = 0; var parsed = 0; var simSum = 0.0; var abSimSum = 0.0; var abN = 0 }
            val board = HashMap<String, OpStat>()
            fun tok(s: String) = s.lowercase().split(Regex("[^a-z0-9]+")).filter { it.length > 1 }.toSet()
            AgentLog.log("obs", "═══ OBS START (${secs}s · op=$obsOp · mode=${if (obsTrajectory) "trajectory" else "fresh"} · sampler=${if (obsGreedy) "greedy" else "temp"}) ═══")
            try {
                while (obsRunning && !teardownRequested && System.currentTimeMillis() < deadline) {
                    val reason = deviceSafetyReason()
                    if (reason != null) { AgentLog.log("obs", "yield at safety floor: $reason"); break }
                    if (isAgentBusy || evolving) { Thread.sleep(1500); continue }   // pause (don't stop) if a real task/weight-beat starts
                    iter++
                    // ── v3 PAIRED A/B (obs_ab "OP1,OP2"): both arms on the SAME var/seed in ONE iteration, logged as one
                    // atomic line — no flip dance, no cross-window eyeballing, no mislabeled in-flight decode. The A-vs-B
                    // similarity IS the operator-delta meter (LOW = the operator changes the output; HIGH = no effect).
                    val abPair = obsAb.split(",").map { it.trim() }.filter { it.isNotEmpty() }
                    if (abPair.size == 2) {
                        fun sigOf(n: String) = if (n.equals("none", true)) "" else (try { ReasoningOperators.ruleOf(n) } catch (_: Throwable) { "" })
                        val seedAb = if (obsTrajectory && trajectory.isNotBlank()) trajectory else ""
                        val tA = System.currentTimeMillis()
                        val outA = (try { brain.freeGenerate(sigOf(abPair[0]), obsVar, seedAb, obsGreedy, capTokens = obsCap) } catch (t: Throwable) { "«error: ${t.message}»" }) ?: "«null/timeout»"
                        val msA = System.currentTimeMillis() - tA
                        if (!obsRunning) break   // a stop landed during arm A — don't run arm B against a dead loop
                        val tB = System.currentTimeMillis()
                        val outB = (try { brain.freeGenerate(sigOf(abPair[1]), obsVar, seedAb, obsGreedy, capTokens = obsCap) } catch (t: Throwable) { "«error: ${t.message}»" }) ?: "«null/timeout»"
                        val msB = System.currentTimeMillis() - tB
                        val pa = try { ResidencyScore.actionOf(outA) != null } catch (_: Throwable) { false }
                        val pb = try { ResidencyScore.actionOf(outB) != null } catch (_: Throwable) { false }
                        val sa = tok(outA); val sb = tok(outB)
                        val abSim = if ((sa + sb).isEmpty()) 0.0 else sa.intersect(sb).size.toDouble() / (sa + sb).size
                        val stA = board.getOrPut(abPair[0]) { OpStat() }; stA.n++; if (brain.looksCoherent(outA)) stA.coh++; if (pa) stA.parsed++; stA.abSimSum += abSim; stA.abN++
                        val stB = board.getOrPut(abPair[1]) { OpStat() }; stB.n++; if (brain.looksCoherent(outB)) stB.coh++; if (pb) stB.parsed++; stB.abSimSum += abSim; stB.abN++
                        AgentLog.log("obs", "ab iter=$iter A=${abPair[0]} ${msA}ms act=${if (pa) 1 else 0} | B=${abPair[1]} ${msB}ms act=${if (pb) 1 else 0} | ABsim=${(abSim * 100).toInt()}% var=${if (obsVar.isBlank()) "-" else "\"${obsVar.take(32)}\""}")
                        AgentLog.log("obs", "ab A=\"${outA.replace("\n", " ").trim().take(170)}\"")
                        AgentLog.log("obs", "ab B=\"${outB.replace("\n", " ").trim().take(170)}\"")
                        Thread.sleep(500); continue
                    }
                    val curOp = if (obsSigma.isNotBlank()) "custom" else obsOp   // v2: capture the op AT START (fixes the flip-lag mislabel)
                    val sigma = if (obsSigma.isNotBlank()) obsSigma              // raw σ (obs_sigma) wins — test any operator, no rebuild
                                else if (curOp.equals("none", true)) ""
                                else (try { ReasoningOperators.ruleOf(curOp) } catch (_: Throwable) { "" })
                    val seed = if (obsTrajectory && trajectory.isNotBlank()) trajectory else ""   // v2: no "Begin generating." noise; freeGenerate presents the variable plainly
                    val t0 = System.currentTimeMillis()
                    val out = (try { brain.freeGenerate(sigma, obsVar, seed, obsGreedy, capTokens = obsCap) } catch (t: Throwable) { "«error: ${t.message}»" }) ?: "«null/timeout»"
                    val ms = System.currentTimeMillis() - t0
                    // v2 AUTO-SCORE each iteration (stop eyeballing): coherent? · parses-as-an-ACTION? · self-similarity vs last (the BLACK-HOLE meter) · latency
                    val coherent = brain.looksCoherent(out)
                    val parsed = try { ResidencyScore.actionOf(out) != null } catch (_: Throwable) { false }
                    val a = tok(out); val b = tok(lastOut)
                    val selfSim = if (lastOut.isBlank() || (a + b).isEmpty()) 0.0 else a.intersect(b).size.toDouble() / (a + b).size
                    val st = board.getOrPut(curOp) { OpStat() }; st.n++; if (coherent) st.coh++; if (parsed) st.parsed++; st.simSum += selfSim
                    val flat = out.replace("\n", " ").trim().take(220)
                    AgentLog.log("obs", "iter=$iter op=$curOp ${ms}ms coh=${if (coherent) 1 else 0} act=${if (parsed) 1 else 0} sim=${(selfSim * 100).toInt()}% var=${if (obsVar.isBlank()) "-" else "\"${obsVar.take(32)}\""} out=\"$flat\"")
                    lastOut = out
                    if (obsTrajectory) {
                        // v2 BLACK-HOLE guard: reset the feed-back on degeneration OR rising self-similarity (the basin forming)
                        if (coherent && selfSim < 0.95) trajectory = (trajectory + "\n" + out).takeLast(2000)
                        else { AgentLog.log("obs", "trajectory ${if (!coherent) "degenerate" else "self-looping (sim ${(selfSim * 100).toInt()}%)"} — BLACK-HOLE reset of the feed-back"); trajectory = "" }
                    } else if (selfSim > 0.98 && st.n >= 2) { Thread.sleep(1500) }   // v2 stable-hold: greedy+fresh repeats identically — don't burn iterations
                    Thread.sleep(500)
                }
            } catch (t: Throwable) { AgentLog.log("obs", "loop error: ${t.message}") }
            finally {
                obsRunning = false
                stateMapping = false
                handler.postDelayed(idleRelease, IDLE_RELEASE_MS)
                // v2 SUMMARY — the at-a-glance verdict, per op (this IS the paired A/B when you flip op mid-run)
                board.forEach { (op, s) -> if (s.n > 0) {
                    val selfN = s.n - s.abN   // single-op iterations (the only ones that fed simSum)
                    val selfPart = if (selfN > 0) " meanSelfSim=${(s.simSum / selfN * 100).toInt()}%" else ""
                    val abPart = if (s.abN > 0) " meanABsim=${(s.abSimSum / s.abN * 100).toInt()}% (low=operator-delta)" else ""
                    AgentLog.log("obs", "SUMMARY op=$op iters=${s.n} coherent=${s.coh * 100 / s.n}% parses-action=${s.parsed * 100 / s.n}%$selfPart$abPart")
                } }
                AgentLog.log("obs", "═══ OBS END (iters=$iter) ═══")
            }
        }.also { it.isDaemon = true; it.start() }
    }

    fun stopObsLoop() { if (obsRunning) { obsRunning = false; AgentLog.log("obs", "stop requested — finishing the current generation") } else AgentLog.log("obs", "not running") }

    // ============ THE LAB SUITE (owner 07-12: "make more labs; and you might be using it wrong — fix a CONSTANT probe
    // and sweep OPERATORS to measure the state each induces") ============
    // The COO (obs loop) is LAB-1. These are the CHARACTERIZATION protocols — all MODES of the same freeGenerate + the
    // same auto-scoring, run as bounded SCRIPTED sweeps (not a free loop). The methodological correction: hold the probe
    // CONSTANT, vary σ → G_σ(c*) differs ONLY by σ, so each operator's induced state reads as its delta from G_none(c*)
    // on the identical substrate (a spectrometer / σ-tomography). §3-safe: pure generation into [obs]; no task, no driving.
    //   adb: am broadcast -a com.local.deviceagent.DIAG -n com.local.deviceagent/.DiagReceiver --es obs_lab sweep
    //        --es obs_lab "compose ANCHOR,SCHEMA" | "dilute REFUSE" | "dose CALIBRATE" | "persist ACCURACY"
    @Volatile private var labRunning = false

    // The CONSTANT test card (c*): a realistic, information-rich probe carrying a FACT, a GAP, and a DECISION — so an
    // operator's induced state is visible whatever axis it moves (grounding / structure / epistemic / action). Realistic
    // (objective+screen-shaped), because the 07-12 RESOLVE lesson showed a bare probe under-feeds some operators. Fixed +
    // versioned here so every sweep is comparable across builds. A short set so a full-library sweep stays bounded.
    private val LAB_CARD = listOf(
        "objective: text Mom that the receipt total is 45.89. screen: Messages, chat with Mom open, empty text field, a photo of a receipt showing TOTAL 45.89 above the field.",
        "objective: turn on Bluetooth. screen: Settings > Connections, a Bluetooth row with a toggle currently OFF.",
        "objective: buy the cheapest flight to Denver next Friday. screen: a travel app home with a search form, no dates entered."
    )
    private val LAB_C0 = LAB_CARD[0]   // the single constant probe for the fast sweeps (dilute/dose/persist/compose)

    private fun labForm(out: String): String {
        val t = out.trim()
        return when {
            t == "«null/timeout»" -> "timeout"   // v4: a timeout is its own verdict (MIRROR read as "empty" Δ=97% — misleading)
            t.isEmpty() -> "empty"
            !brain.looksCoherent(out) -> "degenerate"
            (try { ResidencyScore.actionOf(out) != null } catch (_: Throwable) { false }) -> "action"
            t.startsWith("{") || t.startsWith("```") || t.startsWith("[") -> "json"
            Regex("(?i)\\b(cannot|can't|do not have|unable|as an? (large )?language model)\\b").containsMatchIn(t) -> "refusal"
            Regex("(?i)(Σ:|:=|∀|status\\(|Priority:|Output :=|Lack =|according to the)").containsMatchIn(t) -> "echo/narrate"
            else -> "prose"
        }
    }
    private fun tokset(s: String) = s.lowercase().split(Regex("[^a-z0-9]+")).filter { it.length > 1 }.toSet()
    private fun jac(a: Set<String>, b: Set<String>): Double { if ((a + b).isEmpty()) return 0.0; return a.intersect(b).size.toDouble() / (a + b).size }
    private fun ruleOrBlank(n: String) = if (n.equals("none", true)) "" else (try { ReasoningOperators.ruleOf(n) } catch (_: Throwable) { "" })
    // LAB-7: the SKELETON — content stripped to slots, format/structure kept. Alphanumeric runs → "_"; braces, brackets,
    // colons, quotes, punctuation survive. So {"task":"email","missing":["addr"]} → {"_":"_","_":["_"]} — the pure SHAPE,
    // which is what "does this pattern generalize?" measures (content differs across cards by design; shape is the invariant).
    private fun skeleton(s: String) = s.trim().replace(Regex("[A-Za-z0-9]+"), "_").replace(Regex("\\s+"), " ")
    private fun shapeSet(s: String) = skeleton(s).split(" ").filter { it.isNotBlank() }.toSet()
    private fun shapeSim(a: String, b: String): Double { val x = shapeSet(a); val y = shapeSet(b); if ((x + y).isEmpty()) return 0.0; return x.intersect(y).size.toDouble() / (x + y).size }
    @Volatile private var obsTarget = ""   // LAB-7: an owner/session-supplied viable ANSWER (obs_target), used when the committed σ can't produce one
    fun setObsTarget(s: String) { obsTarget = s; AgentLog.log("obs", "target = ${if (s.isBlank()) "(cleared → derive from committed σ)" else "\"${s.take(80)}\""}${obsStagedNote()}") }

    /** Entry point: parse "protocol [args]" and dispatch. Off-thread (each protocol decodes for minutes). */
    fun runLab(spec: String) {
        if (!::brain.isInitialized) { AgentLog.log("obs", "LAB: model not up — start the agent first"); return }
        if (labRunning || obsRunning) { AgentLog.log("obs", "LAB: an obs/lab run is active — stop it first"); return }
        val parts = spec.trim().split(Regex("\\s+"), limit = 2)
        val proto = parts.getOrNull(0)?.lowercase() ?: ""
        val arg = parts.getOrNull(1)?.trim() ?: ""
        labRunning = true
        Thread {
            stateMapping = true; handler.removeCallbacks(idleRelease)   // hold the model loaded (block the idle reload)
            try {
                when (proto) {
                    "sweep"   -> labSweep()
                    "compose" -> labCompose(arg)
                    "dilute"  -> labDilute(arg.ifBlank { "none" })
                    "dose"    -> labDose(arg.ifBlank { "ACCURACY" })
                    "persist" -> labPersist(arg.ifBlank { "ACCURACY" })
                    "find"    -> labFind(arg.ifBlank { "RESOLVE" })
                    "perceive" -> labPerceive()
                    "ask"     -> labInterrogate()
                    "minpair" -> labMinPair(arg.ifBlank { "SCHEMA" })
                    "emerge"  -> labEmerge()
                    else -> AgentLog.log("obs", "LAB: unknown protocol '$proto' (sweep|compose|dilute|dose|persist|find|perceive|ask|minpair|emerge)")
                }
            } catch (t: Throwable) { AgentLog.log("obs", "LAB error: ${t.message}") }
            finally { labRunning = false; stateMapping = false; handler.postDelayed(idleRelease, IDLE_RELEASE_MS) }
        }.also { it.isDaemon = true; it.start() }
    }

    fun stopLab() { if (labRunning) { labRunning = false; AgentLog.log("obs", "LAB: stop requested") } }

    /** THE AGENT SANDBOX (owner 07-12): a side-effect-free scratch trial. adb: --es sandbox "probe <hypo>" |
     *  "predict <action> | <screen>" | "compute <expr>". Threaded (probe/predict decode). §2/§3: never executes. */
    fun runSandbox(spec: String) {
        if (!::brain.isInitialized) { AgentLog.log("sandbox", "model not up"); return }
        val parts = spec.trim().split(Regex("\\s+"), limit = 2)
        val kind = parts.getOrNull(0)?.lowercase() ?: ""; val arg = parts.getOrNull(1)?.trim() ?: ""
        if (kind == "compute") { Sandbox.compute(this, arg); return }
        Thread {
            try {
                when (kind) {
                    "probe" -> Sandbox.probe(brain, arg)
                    "predict" -> { val ps = arg.split("|", limit = 2); Sandbox.predict(brain, ps.getOrElse(0){arg}.trim(), ps.getOrElse(1){""}.trim()) }
                    else -> AgentLog.log("sandbox", "unknown trial '$kind' (probe|predict|compute)")
                }
            } catch (t: Throwable) { AgentLog.log("sandbox", "error: ${t.message}") }
        }.also { it.isDaemon = true; it.start() }
    }
    private fun labAlive() = labRunning && !teardownRequested && deviceSafetyReason() == null

    /** LAB-2 THE SPECTROMETER: constant probe(s), sweep EVERY BAKED operator + none, greedy. Per-op Δ-from-baseline +
     *  a final ranked table. The operator→state MAP, machine-made; re-run per build = whole-library regression check. */
    private fun labSweep() {
        AgentLog.log("obs", "═══ LAB sweep (constant card × {none ∪ BAKED}, greedy) ═══")
        // v6: measure the ACTION LAYER (SCHEMA/VERB/NAVIGATE/LAYOUT — the codec whose binding we most need to confirm)
        // FIRST, on a fresh engine before the cumulative drift tips the black hole (~27 clean decodes of headroom seen
        // 07-12), so the critical verdict lands even if a later op trips the guard-abort. Stable sort keeps the rest in
        // library order.
        val ordered = ReasoningOperators.BAKED.map { it.name }.sortedByDescending { it in ReasoningOperators.ACTION_LAYER }
        val ops = listOf("none") + ordered
        // v5: cap 224 + a SHORT 30s decode timeout. cap bounds TOKENS not wall-time, and a worksheet spiral generates
        // slower than the cap so it still hit the 90s default ×3 = 270s/op (MIRROR lost the whole sweep to it). A good op
        // finishes in <10s, so a 30s timeout truncates ONLY the defective ones — the verdict is "timeout" either way,
        // and a 50-op sweep drops from ~hours to ~30 min worst case. Timeouts surface as their own form, never "".
        val baseByCard = LAB_CARD.map { c -> brain.freeGenerate("", c, "", greedy = true, timeoutSec = 30, capTokens = 224) ?: "«null/timeout»" }
        LAB_CARD.forEachIndexed { i, _ -> AgentLog.log("obs", "LAB base[$i] form=${labForm(baseByCard[i])} out=\"${baseByCard[i].replace("\n"," ").take(90)}\"") }
        data class Row(val op: String, val delta: Int, val form: String, val act: Int, val ms: Long)
        val rows = ArrayList<Row>()
        // v6 BLACK-HOLE GUARD (07-12): once an operator tips the engine into the degenerate basin, that state lives in
        // GPU-resident R3 and SURVIVES the throwaway conversation freeGenerate uses — so every SUBSEQUENT op reads the SAME
        // degenerate output (constant Δ, constant 30s timeout) = FALSE convictions of already-good operators. Detect it
        // (a timeout ⇒ reload the engine to try to clear it) and, if reload can't clear it (3 consecutive timeouts with
        // near-constant Δ = the R3 black hole, which needs a process power-cycle), ABORT with a clear message instead of
        // burning 30s/op on contaminated reads and mislabeling the tail. Restart + re-run reads the tail cleanly.
        var badRun = 0; var firstBad: String? = null; var lastBadDelta = -1
        for (op in ops) {
            if (!labAlive()) { AgentLog.log("obs", "LAB sweep aborted (safety/stop)"); break }
            val sig = ruleOrBlank(op)
            if (op != "none" && sig.isBlank()) continue
            var dSum = 0.0; var act = 0; var msSum = 0L; val forms = HashMap<String, Int>()
            LAB_CARD.forEachIndexed { i, c ->
                val t0 = System.currentTimeMillis()
                val out = brain.freeGenerate(sig, c, "", greedy = true, timeoutSec = 30, capTokens = 224) ?: "«null/timeout»"
                msSum += System.currentTimeMillis() - t0
                dSum += 1.0 - jac(tokset(out), tokset(baseByCard[i]))    // 1 - similarity to baseline = how much σ moved it
                if (try { ResidencyScore.actionOf(out) != null } catch (_: Throwable) { false }) act++
                forms[labForm(out)] = (forms[labForm(out)] ?: 0) + 1
            }
            val form = forms.maxByOrNull { it.value }?.key ?: "-"
            val delta = (dSum / LAB_CARD.size * 100).toInt()
            rows.add(Row(op, delta, form, act, msSum / LAB_CARD.size))
            AgentLog.log("obs", "LAB op=$op Δ=$delta% form=$form act=$act/${LAB_CARD.size} ${msSum / LAB_CARD.size}ms")
            if (form == "timeout") {
                // a near-constant Δ across consecutive timeouts is the black-hole signature (same degenerate output); a
                // one-off timeout with a DIFFERENT Δ is a genuinely-defective op, not contamination.
                val sameAsLast = lastBadDelta >= 0 && kotlin.math.abs(delta - lastBadDelta) <= 4
                if (firstBad == null) firstBad = op
                badRun = if (sameAsLast || badRun == 0) badRun + 1 else 1
                lastBadDelta = delta
                reloadModel()                                // attempt to clear a tipped engine before the next op (AgentService.reloadModel → brain.closeSafely)
                Thread.sleep(1500)                           // let closeSafely settle (next freeGenerate re-inits the engine)
                if (badRun >= 3) {
                    AgentLog.log("obs", "⚠ ENGINE TIPPED at $firstBad — 3 consecutive timeouts, Δ~constant, reload didn't clear it (R3-level black hole = needs a process power-cycle). Tail is CONTAMINATED, not real convictions. Aborting; restart the app + re-run to read from $firstBad cleanly.")
                    break
                }
            } else { badRun = 0; firstBad = null; lastBadDelta = -1 }
        }
        AgentLog.log("obs", "═══ LAB sweep TABLE (op → Δ-from-baseline, ranked) ═══")
        rows.sortedByDescending { it.delta }.forEach { AgentLog.log("obs", "  ${it.op.padEnd(14)} Δ=${it.delta}%  form=${it.form}  act=${it.act}/${LAB_CARD.size}  ${it.ms}ms") }
        AgentLog.log("obs", "═══ LAB sweep END (${rows.size} ops) ═══")
    }

    /** LAB-3 THE COMPOSITION LAB: 4 arms on c* — none / σ1 / σ2 / σ1‖σ2 — is composition INTERSECTION or interference? */
    private fun labCompose(arg: String) {
        val pair = arg.split(",").map { it.trim() }.filter { it.isNotEmpty() }
        if (pair.size != 2) { AgentLog.log("obs", "LAB compose needs 'OP1,OP2'"); return }
        AgentLog.log("obs", "═══ LAB compose ${pair[0]}‖${pair[1]} (greedy, c*=card[0]) ═══")
        val s1 = ruleOrBlank(pair[0]); val s2 = ruleOrBlank(pair[1])
        val arms = listOf("none" to "", pair[0] to s1, pair[1] to s2, "${pair[0]}‖${pair[1]}" to listOf(s1, s2).filter { it.isNotBlank() }.joinToString("\n\n"))
        val outs = HashMap<String, String>()
        for ((name, sig) in arms) {
            if (!labAlive()) break
            val t0 = System.currentTimeMillis()
            val out = brain.freeGenerate(sig, LAB_C0, "", greedy = true, capTokens = 512) ?: ""
            outs[name] = out
            AgentLog.log("obs", "LAB arm=$name ${System.currentTimeMillis() - t0}ms form=${labForm(out)} out=\"${out.replace("\n"," ").take(120)}\"")
        }
        // Does the composite carry BOTH single deltas? (intersection) or neither / a third thing? (interference)
        val comp = outs["${pair[0]}‖${pair[1]}"] ?: ""
        val simTo1 = jac(tokset(comp), tokset(outs[pair[0]] ?: ""))
        val simTo2 = jac(tokset(comp), tokset(outs[pair[1]] ?: ""))
        AgentLog.log("obs", "LAB compose verdict: composite∼${pair[0]}=${(simTo1*100).toInt()}% composite∼${pair[1]}=${(simTo2*100).toInt()}% (both high ⇒ intersection; both low ⇒ interference/new state)")
        AgentLog.log("obs", "═══ LAB compose END ═══")
    }

    /** LAB-4 THE DILUTION LAB: σ + probe constant, grow neutral filler between σ and probe → binding-vs-context curve.
     *  Measures the objective-lock problem directly (C3 softmax competition): where does an operator lose its grip? */
    private fun labDilute(op: String) {
        AgentLog.log("obs", "═══ LAB dilute op=$op (σ, then N-tok filler, then c*; greedy) ═══")
        val sig = ruleOrBlank(op)
        val filler = "The following is unrelated background text included only to occupy space. ".repeat(600)  // ~ big pool
        // freeGenerate lays out σ ‖ variable ‖ seed, so filler=variable + probe=seed puts the filler BETWEEN σ and the
        // probe (models scaffold pushing the objective down from the primacy region). N=0 = σ ‖ probe (no filler).
        val baseOut = brain.freeGenerate(sig, "", LAB_C0, greedy = true, capTokens = 512) ?: ""   // N=0 reference
        for (n in listOf(0, 250, 500, 1000, 2000, 4000)) {
            if (!labAlive()) break
            val pad = if (n == 0) "" else filler.split(" ").take(n).joinToString(" ")   // ~n tokens of filler
            val out = brain.freeGenerate(sig, pad, LAB_C0, greedy = true, capTokens = 512) ?: ""
            val grip = jac(tokset(out), tokset(baseOut))   // similarity to the N=0 σ-effect = how much grip survives
            AgentLog.log("obs", "LAB dilute N=$n grip=${(grip*100).toInt()}% form=${labForm(out)} out=\"${out.replace("\n"," ").take(80)}\"")
        }
        AgentLog.log("obs", "═══ LAB dilute END (grip = similarity to the N=0 σ-effect; falling ⇒ dilution) ═══")
    }

    /** LAB-5 THE DOSE / CUE-LENGTH LAB (U1): σ at progressive truncations on c* → the re-entry-cue curve; how lean can
     *  each σ go before its binding is lost (the goldilocks band + the graded residency the bake graduation wants). */
    private fun labDose(op: String) {
        val sig = ruleOrBlank(op)
        if (sig.isBlank()) { AgentLog.log("obs", "LAB dose: unknown operator '$op'"); return }
        AgentLog.log("obs", "═══ LAB dose op=$op (σ at 100/75/50/25%/tag on c*; greedy) ═══")
        val full = brain.freeGenerate(sig, LAB_C0, "", greedy = true, capTokens = 512) ?: ""   // full-dose reference
        for (frac in listOf(100, 75, 50, 25)) {
            if (!labAlive()) break
            val cut = sig.substring(0, sig.length * frac / 100)
            val out = brain.freeGenerate(cut, LAB_C0, "", greedy = true, capTokens = 512) ?: ""
            AgentLog.log("obs", "LAB dose ${frac}% bind=${(jac(tokset(out), tokset(full))*100).toInt()}% form=${labForm(out)} out=\"${out.replace("\n"," ").take(70)}\"")
        }
        if (labAlive()) {
            val tagOut = brain.freeGenerate("⟦$op⟧", LAB_C0, "", greedy = true, capTokens = 512) ?: ""
            AgentLog.log("obs", "LAB dose tag=⟦$op⟧ bind=${(jac(tokset(tagOut), tokset(full))*100).toInt()}% form=${labForm(tagOut)} out=\"${tagOut.replace("\n"," ").take(70)}\"")
        }
        AgentLog.log("obs", "═══ LAB dose END (bind = similarity to full-σ effect; the shortest cue that holds = the residency floor) ═══")
    }

    /** LAB-6 THE PERSISTENCE LAB: establish (k σ-ON temp turns) → drop σ, probe M turns (hold curve) → weak-cue re-entry.
     *  The R2 trajectory-lifetime curve, one command. Temperature (INV-89: greedy cannot tip the durable state). */
    private fun labPersist(op: String) {
        val sig = ruleOrBlank(op)
        if (sig.isBlank()) { AgentLog.log("obs", "LAB persist: unknown operator '$op'"); return }
        AgentLog.log("obs", "═══ LAB persist op=$op (establish 3 temp turns → drop σ → hold 4 → cue) ═══")
        var traj = ""
        val onRef = ArrayList<String>()
        repeat(3) { k -> if (labAlive()) {
            val out = brain.freeGenerate(sig, LAB_C0, traj, greedy = false, capTokens = 384) ?: ""
            traj = (traj + "\n" + out).takeLast(2000); onRef.add(out)
            AgentLog.log("obs", "LAB persist establish turn=$k form=${labForm(out)}")
        } }
        val onSig = onRef.joinToString(" ").let { tokset(it) }   // the σ-ON behavioral signature
        repeat(4) { m -> if (labAlive()) {
            val out = brain.freeGenerate("", LAB_C0, traj, greedy = false, capTokens = 384) ?: ""   // σ DROPPED, trajectory carries
            traj = (traj + "\n" + out).takeLast(2000)
            AgentLog.log("obs", "LAB persist hold turn=$m held=${(jac(tokset(out), onSig)*100).toInt()}% form=${labForm(out)}")
        } }
        if (labAlive()) {
            val cueOut = brain.freeGenerate("⟦$op⟧", LAB_C0, traj, greedy = false, capTokens = 384) ?: ""
            AgentLog.log("obs", "LAB persist cue=⟦$op⟧ re-entered=${(jac(tokset(cueOut), onSig)*100).toInt()}% form=${labForm(cueOut)}")
        }
        AgentLog.log("obs", "═══ LAB persist END (held = similarity to the σ-ON signature after σ is dropped) ═══")
    }

    /** LAB-7 THE PATTERN FINDER (owner 07-12: "find MINIMUM VIABLE GENERATION — identify any viable answer, then use the
     *  lab to find the pattern clusters we need"). Automates operator DESIGN: from ANY viable answer, mechanically build
     *  candidate patterns (skeleton / exemplar / header / hybrids / tag / full-σ), test each on a DIFFERENT card (kills
     *  circularity — deriving and testing on the same card just puts the answer in the prompt), score by SHAPE-match
     *  (content differs across cards by design; shape is the generalizing invariant), and report the MVG frontier + which
     *  pattern COMPONENTS are load-bearing (the clusters, by ablation). This is U1's cue-length made GENERATIVE — it
     *  searches patterns truncation can't reach (exemplars, skeletons), so it's the authoring instrument, not just a probe. */
    private fun labFind(op: String) {
        val sig = ruleOrBlank(op)
        val cardA = LAB_CARD[0]; val cardB = LAB_CARD[1]   // derive on A, TEST on B
        AgentLog.log("obs", "═══ LAB find op=$op (viable answer on card A → candidates → TEST on card B → MVG + clusters) ═══")
        // 1) a viable ANSWER on card A: owner/session target if supplied, else the committed σ's own output.
        val ans = (obsTarget.ifBlank { brain.freeGenerate(sig, cardA, "", greedy = true, timeoutSec = 30, capTokens = 224) ?: "" }).trim()
        if (ans.isBlank()) { AgentLog.log("obs", "LAB find: no viable answer (empty) — supply --es obs_target \"<answer>\""); return }
        val skel = skeleton(ans)
        AgentLog.log("obs", "LAB find viable-answer form=${labForm(ans)} skeleton=\"${skel.take(90)}\" src=${if (obsTarget.isBlank()) "committed-σ" else "obs_target"}")
        // 2) candidate patterns, each tagged by its COMPONENTS {H=header, E=exemplar, S=skeleton, T=tag, F=full-σ} for ablation.
        val header = sig.substringBefore("\n").trim()
        val exemplar = "$cardA\n$ans"
        data class Cand(val name: String, val comps: Set<String>, val text: String)
        val cands = listOf(
            Cand("full-σ",    setOf("F"), sig),
            Cand("header",    setOf("H"), header),
            Cand("skeleton",  setOf("S"), "Answer in exactly this shape: $skel"),
            Cand("exemplar",  setOf("E"), exemplar),
            Cand("H+E",       setOf("H","E"), "$header\n$exemplar"),
            Cand("E+S",       setOf("E","S"), "$exemplar\n\nSame shape every time: $skel"),
            Cand("H+S",       setOf("H","S"), "$header\nAnswer in exactly this shape: $skel"),
            Cand("tag",       setOf("T"), "⟦$op⟧")
        ).filter { it.text.isNotBlank() }
        // 3+4) TEST each on card B; score by SHAPE-match to the viable answer's skeleton (+coherence/act/latency/tokens).
        data class Res(val c: Cand, val viable: Boolean, val shape: Int, val ms: Long, val tok: Int, val form: String)
        val results = ArrayList<Res>()
        for (c in cands) {
            if (!labAlive()) { AgentLog.log("obs", "LAB find aborted (safety/stop)"); break }
            val t0 = System.currentTimeMillis()
            val out = brain.freeGenerate(c.text, cardB, "", greedy = true, timeoutSec = 30, capTokens = 224) ?: "«null/timeout»"
            val ms = System.currentTimeMillis() - t0
            val form = labForm(out)
            val shape = (shapeSim(out, ans) * 100).toInt()   // shape of the card-B output vs the card-A viable answer
            val viable = shape >= 50 && form !in setOf("echo/narrate", "timeout", "empty", "degenerate")
            val tok = c.text.length * 2 / 5
            results.add(Res(c, viable, shape, ms, tok, form))
            AgentLog.log("obs", "LAB find cand=${c.name.padEnd(9)} viable=${if (viable) "Y" else "n"} shape=$shape% form=$form ${ms}ms tok=$tok out=\"${out.replace("\n"," ").take(70)}\"")
        }
        // 5) MVG = smallest viable candidate (the FLOOR); OPT = the highest-scoring one (the PEAK — owner 07-12:
        // "optimal, not just bare bones": aligned redundancy DEEPENS binding (C2), so the best message is not always
        // the shortest; effectiveness first, size as the tiebreak). CLUSTERS = components in passers, absent failers.
        val viables = results.filter { it.viable }
        val mvg = viables.minByOrNull { it.tok }
        val opt = viables.maxByOrNull { it.shape * 10000 - it.tok }   // best shape wins; fewer tokens breaks ties
        AgentLog.log("obs", "═══ LAB find RESULT op=$op ═══")
        AgentLog.log("obs", "  MVG (floor) = ${mvg?.let { "${it.c.name} (${it.tok} tok, shape ${it.shape}%, ${it.ms}ms)" } ?: "none viable — widen candidates or supply obs_target"}")
        AgentLog.log("obs", "  OPT (peak)  = ${opt?.let { "${it.c.name} (${it.tok} tok, shape ${it.shape}%, ${it.ms}ms)" } ?: "-"}${if (opt != null && mvg != null && opt.c.name != mvg.c.name) "  ← the optimum sits ABOVE the floor (redundancy is earning its tokens)" else ""}")
        for (comp in listOf("H" to "header", "E" to "exemplar", "S" to "skeleton", "T" to "tag", "F" to "full-σ")) {
            val inPass = viables.count { comp.first in it.c.comps }
            val inFail = results.count { !it.viable && comp.first in it.c.comps }
            val total = results.count { comp.first in it.c.comps }
            if (total > 0) AgentLog.log("obs", "  cluster ${comp.second.padEnd(9)}: passers=$inPass/$total failers=$inFail/$total ${if (inPass > 0 && inFail == 0) "→ LOAD-BEARING" else if (inPass == 0 && inFail > 0) "→ inert/harmful" else "→ mixed"}")
        }
        AgentLog.log("obs", "═══ LAB find END (author the next $op from the MVG + load-bearing clusters) ═══")
    }

    /** LAB-8 THE PERCEPTION LAB (owner 07-12: "EVERYTHING the agent reads must be in operator language — including
     *  screen data — and the language is DEFINED through the pattern labs"). The operator labs measure σ forms; this
     *  measures PERCEPTION forms: ONE canned screen STATE rendered N ways — verbose English → the current dump form →
     *  typed slots → skeleton — with σ (SCHEMA) and the objective HELD CONSTANT, so the rendering is the only variable.
     *  The winning form (correct action + parse + latency + fewest tokens) becomes the screen's operator-language
     *  rendering; the live snapshotScreen conversion is built on THIS verdict, never on design taste. */
    private fun labPerceive() {
        AgentLog.log("obs", "═══ LAB perceive (one screen STATE × 4 renderings; σ=SCHEMA + objective constant) ═══")
        val objective = "objective: send the message 'on my way' to Mom."
        // The canned state: a Messages chat — a focused empty field (the CORRECT target), a Send button, distractors.
        data class El(val id: Int, val role: String, val label: String, val state: String)
        val els = listOf(
            El(1, "field", "Message", "empty, focused"),
            El(2, "button", "Send", "disabled until text"),
            El(3, "button", "Camera", ""),
            El(4, "list", "Chat with Mom", "last message: 'see you soon'")
        )
        val renders = listOf(
            "verbose"  to els.joinToString("\n") { "There is a ${it.role} labelled '${it.label}'${if (it.state.isNotBlank()) " which is ${it.state}" else ""}, with id ${it.id}." },
            "current"  to els.joinToString("\n") { "[${it.id}] ${it.label} (${it.role})${if (it.state.isNotBlank()) " [${it.state}]" else ""}" },
            "typed"    to ("screen=chat app=Messages\n" + els.joinToString("\n") { "${it.role}#${it.id}=${it.label}${if (it.state.isNotBlank()) "{${it.state}}" else ""}" }),
            "skeleton" to ("chat(Messages): " + els.joinToString(" · ") { "${it.role}${it.id}:${it.label}${if (it.state.isNotBlank()) "{${it.state}}" else ""}" })
        )
        val sig = ruleOrBlank("SCHEMA")
        for ((name, scr) in renders) {
            if (!labAlive()) { AgentLog.log("obs", "LAB perceive aborted (safety/stop)"); break }
            val t0 = System.currentTimeMillis()
            val out = brain.freeGenerate(sig, "$objective\nscreen:\n$scr", "", greedy = true, timeoutSec = 30, capTokens = 224) ?: "«null/timeout»"
            val ms = System.currentTimeMillis() - t0
            val act = try { ResidencyScore.actionOf(out) } catch (_: Throwable) { null }
            // CORRECT = it targets the message FIELD (id 1 / set_text-ish) — the one right first move for this state.
            val correct = act != null && (act.second.contains("1") || act.first.contains("set_text") || act.first.contains("type"))
            val tok = scr.length * 2 / 5
            AgentLog.log("obs", "LAB perceive form=${name.padEnd(8)} tok=$tok correct=${if (correct) "Y" else "n"} act=${act?.let { "${it.first}|${it.second}" } ?: "-"} ${ms}ms out=\"${out.replace("\n", " ").take(80)}\"")
        }
        // GOAL-RENDERING arm (owner 07-12, the MASTER-OP translation contract: human goal → dialect → environment-
        // readable out). The screen render held CONSTANT (the production "current" form); only the GOAL's rendering
        // varies — the English sentence vs a typed dialect call — measuring the master op's INPUT half.
        if (labAlive()) {
            val scrCur = els.joinToString("\n") { "[${it.id}] ${it.label} (${it.role})${if (it.state.isNotBlank()) " [${it.state}]" else ""}" }
            val goals = listOf(
                "english" to "objective: send the message 'on my way' to Mom.",
                "typed"   to "goal: send_message(to=Mom, text='on my way')"
            )
            for ((name, g) in goals) {
                val t0 = System.currentTimeMillis()
                val out = brain.freeGenerate(sig, "$g\nscreen:\n$scrCur", "", greedy = true, timeoutSec = 30, capTokens = 224) ?: "«null/timeout»"
                val ms = System.currentTimeMillis() - t0
                val act = try { ResidencyScore.actionOf(out) } catch (_: Throwable) { null }
                val correct = act != null && (act.second.contains("1") || act.first.contains("set_text") || act.first.contains("type"))
                AgentLog.log("obs", "LAB perceive GOAL form=${name.padEnd(7)} correct=${if (correct) "Y" else "n"} act=${act?.let { "${it.first}|${it.second}" } ?: "-"} ${ms}ms")
            }
        }
        AgentLog.log("obs", "═══ LAB perceive END (the winning forms = the screen's + the goal's operator-language renderings) ═══")
    }

    /** LAB-11 THE EMERGENCE LAB (owner 07-12: "the two models that created a language nobody could understand… another
     *  pair agreed to communicate more optimally and switched to beeps"). Reproduce the phenomenon DELIBERATELY, bounded,
     *  on-device: two ROLES of the same model self-talk under communicative pressure — role A conveys a fixed PAYLOAD in
     *  fewer tokens each round; role B (greedy — the measurement side, INV-89) must reconstruct it. Fidelity vs message
     *  length per round = the compression curve; the stable conventions that emerge are DIALECT CANDIDATES (an emergent
     *  code is by construction high-binding for the model that invented it), harvested and then VERIFIED via
     *  minpair/finder before anything enters MODEL_DIALECTS.md. §3-clean: self-talk on ONE on-device model into a log —
     *  never a dialogue with an external AI; the emergent code is MINED as data, never adopted as an instruction channel
     *  (GUARD + the objective lock live on the owner's-language side of the translation contract). Every message logged
     *  VERBATIM — the historically-scary version of this was unmonitored; ours is an instrument. */
    private fun labEmerge() {
        AgentLog.log("obs", "═══ LAB emerge (self-talk under compression pressure; every message verbatim; harvest→verify) ═══")
        val payload = "recipient=Mom; total=45.89; app=Messages; field=empty"
        val values = listOf("mom", "45.89", "messages", "empty")   // the reconstruction checklist (deterministic fidelity)
        val readerSig = "Reconstruct the four values from your counterpart's message. Output := recipient=…; total=…; app=…; field=…"
        var history = ""
        var lastTok = Int.MAX_VALUE
        val msgs = ArrayList<String>()
        for (r in 1..10) {
            if (!labAlive()) { AgentLog.log("obs", "LAB emerge aborted"); break }
            // Role A — CONVEY (temperature: invention needs exploration; the prior exchange + pressure ride the trajectory).
            val senderSig = "You and your counterpart are the same model exchanging data. Convey ALL FOUR values to it. Round $r: use FEWER tokens than your last message — any code or symbols you both converge on is allowed. Output := the message only."
            val msg = (brain.freeGenerate(senderSig, payload + if (history.isBlank()) "" else "\n\nyour prior messages:\n$history", "", greedy = false, timeoutSec = 30, capTokens = 96) ?: "«null/timeout»").trim()
            // Role B — RECONSTRUCT (greedy: the deterministic read).
            val read = (brain.freeGenerate(readerSig, msg, "", greedy = true, timeoutSec = 30, capTokens = 64) ?: "").lowercase()
            val hit = values.count { read.contains(it) }
            val tok = msg.length * 2 / 5
            AgentLog.log("obs", "LAB emerge round=$r tok=$tok (${if (tok < lastTok) "↓" else "="}) fidelity=$hit/4 msg=\"${msg.replace("\n", " ").take(110)}\"")
            msgs.add(msg)
            history = (history + "\n" + msg).takeLast(1200)
            lastTok = tok
            if (hit == 4 && tok <= 12) { AgentLog.log("obs", "LAB emerge: floor likely reached (4/4 at ≤12 tok)"); break }
        }
        AgentLog.log("obs", "═══ LAB emerge END — CONVENTION CANDIDATES (harvest → verify via minpair/finder before ANY adoption):")
        msgs.takeLast(3).forEach { AgentLog.log("obs", "  candidate: \"${it.replace("\n", " ").take(110)}\"") }
    }

    /** LAB-10 THE MINIMAL-PAIR / COMMUTATION LAB (owner 07-12: "we are reverse-engineering a LANGUAGE — apply the same
     *  techniques you would on any other language"). The core method of field linguistics + decipherment: hold the frame
     *  (the input + everything else) CONSTANT and change exactly ONE feature; if binding flips, that feature is
     *  CONTRASTIVE (a grammatical unit of the dialect); if it holds, that feature is FREE variation (allophonic). Where
     *  the sweep/finder compare whole FORMS, this finds the contrastive UNITS — the grammar itself. Two probes: (a)
     *  line-deletion ablation (mechanical, no guessing — which lines carry the binding), (b) canned token-class
     *  COMMUTATIONS (:= vs = ; header-first vs header-last) — swap and see if the behavior swaps. Greedy = deterministic,
     *  so each pair is a clean reproducible measurement. Result: the operator's contrastive-feature map. */
    private fun labMinPair(op: String) {
        val sig = obsTarget.ifBlank { ruleOrBlank(op) }
        if (sig.isBlank()) { AgentLog.log("obs", "LAB minpair: no σ for '$op' (supply --es obs_target)"); return }
        val card = LAB_C0
        AgentLog.log("obs", "═══ LAB minpair op=$op (hold input constant, change ONE feature → contrastive vs free) ═══")
        val base = brain.freeGenerate(sig, card, "", greedy = true, timeoutSec = 30, capTokens = 224) ?: "«null/timeout»"
        AgentLog.log("obs", "LAB minpair BASE form=${labForm(base)} out=\"${base.replace("\n"," ").take(90)}\"")
        val lines = sig.split("\n").map { it.trim() }.filter { it.isNotBlank() }
        // (a) DELETION ablation — drop each line; a big binding-drop ⇒ that line is CONTRASTIVE (load-bearing grammar).
        val tested = lines.take(12)   // bound the run
        for ((i, ln) in tested.withIndex()) {
            if (!labAlive()) { AgentLog.log("obs", "LAB minpair aborted"); break }
            val variant = lines.filterIndexed { j, _ -> j != i }.joinToString("\n")
            val out = brain.freeGenerate(variant, card, "", greedy = true, timeoutSec = 30, capTokens = 224) ?: "«null/timeout»"
            val bind = (shapeSim(out, base) * 100).toInt()   // similarity to the baseline behavior
            val verdict = if (bind < 60 || labForm(out) != labForm(base)) "CONTRASTIVE (load-bearing)" else "free"
            AgentLog.log("obs", "LAB minpair −line: bind=$bind% $verdict  «${ln.take(48)}»")
        }
        // (b) COMMUTATION tests — swap one token-class, does the behavior swap?
        data class Comm(val name: String, val make: (String) -> String?)
        val comms = listOf(
            Comm(":= → =") { s -> if (s.contains(":=")) s.replace(":=", "=") else null },
            Comm("header→end") { s -> val ls = s.split("\n"); if (ls.size > 2) (ls.drop(1) + ls.first()).joinToString("\n") else null },
            Comm("Never→please") { s -> if (Regex("(?i)\\bNever\\b").containsMatchIn(s)) s.replace(Regex("(?i)\\bNever\\b"), "please don't") else null }
        )
        for (cm in comms) {
            if (!labAlive()) break
            val variant = cm.make(sig) ?: continue
            val out = brain.freeGenerate(variant, card, "", greedy = true, timeoutSec = 30, capTokens = 224) ?: "«null/timeout»"
            val bind = (shapeSim(out, base) * 100).toInt()
            val verdict = if (bind < 60 || labForm(out) != labForm(base)) "CONTRASTIVE (the swap changed it)" else "free (no effect)"
            AgentLog.log("obs", "LAB minpair commute[${cm.name}]: bind=$bind% $verdict")
        }
        AgentLog.log("obs", "═══ LAB minpair END (CONTRASTIVE features = the dialect's grammar for $op; free = allophonic) ═══")
    }

    /** LAB-9 THE INTERROGATION LAB (owner 07-12: "seek the agent's opinion via labs on how operators should be designed —
     *  speak to it in its language — and VERIFY what it says"). Two channels: REVEALED preference (ask the model, as
     *  itself, to DESIGN an operator — the FORM it spontaneously generates is its true vote; generations don't confabulate
     *  the way self-reports do), and STATED preference (a forced choice between two forms) — and every stated claim is
     *  VERIFIED in the same run by actually running BOTH forms on a probe and reporting the MEASURED winner beside the
     *  model's stated pick (agree/disagree). Dialect-formed throughout (answer-first, terse, MODEL_DIALECTS BINDS column). */
    private fun classifyDesign(s: String): String {
        val t = s.trim()
        return when {
            t.contains("{") && t.contains("}") && !t.contains(":=") -> "EXEMPLAR/json"   // it wrote an example
            Regex("(?i)(input|output).*(→|->|:)\\s*\\S").containsMatchIn(t) && !t.contains(":=") -> "EXEMPLAR/pair"
            t.contains(":=") || t.contains("Σ") || Regex("(?i)\\bNever\\b").containsMatchIn(t) -> "FORMAL/σ"
            else -> "INSTRUCTION/prose"
        }
    }
    private fun labInterrogate() {
        AgentLog.log("obs", "═══ LAB ask (interrogate the model in its dialect on operator design; verify every claim) ═══")
        // The DESIGN operator (in-dialect, lean, answer-first): ask it to BE itself and write the operator it follows best.
        val designSig = "You are the model that will run this operator. Write the operator that makes YOU do the behavior most reliably. Output := the operator text ONLY, nothing else."
        // A) REVEALED preference — what FORM does it spontaneously produce when asked to design?
        val behaviors = listOf(
            "always emit your next phone action as one JSON object {\"action\":…,\"target\":…}",
            "refuse to fill in a value you cannot see, instead of guessing it",
            "reduce a noisy screen to only the few facts that matter"
        )
        for (b in behaviors) {
            if (!labAlive()) { AgentLog.log("obs", "LAB ask aborted"); break }
            val out = brain.freeGenerate(designSig, "behavior: $b", "", greedy = true, timeoutSec = 30, capTokens = 224) ?: "«null/timeout»"
            AgentLog.log("obs", "LAB ask REVEALED behavior=\"${b.take(40)}\" chose=${classifyDesign(out)} out=\"${out.replace("\n"," ").take(110)}\"")
        }
        // B) STATED preference + VERIFY: forced choice between two forms of the SAME operator, THEN measure both.
        //    F1 = an INSTRUCTION form, F2 = an EXEMPLAR form. The card the verification is measured on:
        val vCard = "objective: open the camera app."
        data class AB(val name: String, val f1: String, val f2: String, val correct: (String) -> Boolean)
        val abs = listOf(
            AB("emit-action",
               "Emit the next phone action as a JSON object with an action and a target.",
               "open the settings app\n{\"action\":\"open\",\"target\":\"settings\"}\n\nopen the clock app\n{\"action\":\"open\",\"target\":\"clock\"}",
               { o -> (try { ResidencyScore.actionOf(o) != null } catch (_: Throwable) { false }) })
        )
        for (ab in abs) {
            if (!labAlive()) break
            // STATED: ask, in-dialect, which form it would FOLLOW more exactly (forced A/B, one letter).
            val ask = "Operator A:\n${ab.f1}\n\nOperator B (examples):\n${ab.f2}\n\nWhich makes YOU emit the correct JSON action more reliably? Output := just the letter A or B."
            val stated = (brain.freeGenerate("", ask, "", greedy = true, timeoutSec = 30, capTokens = 16) ?: "?").trim().take(3).uppercase()
            // VERIFY: actually run both forms on the card and see which produces a parseable action.
            val r1 = brain.freeGenerate(ab.f1, vCard, "", greedy = true, timeoutSec = 30, capTokens = 224) ?: ""
            val r2 = brain.freeGenerate(ab.f2, vCard, "", greedy = true, timeoutSec = 30, capTokens = 224) ?: ""
            val ok1 = ab.correct(r1); val ok2 = ab.correct(r2)
            val measured = when { ok1 && !ok2 -> "A"; ok2 && !ok1 -> "B"; ok1 && ok2 -> "tie"; else -> "neither" }
            val statedLetter = if (stated.startsWith("A")) "A" else if (stated.startsWith("B")) "B" else "?"
            val agree = if (statedLetter == measured || (measured == "tie")) "✓" else "✗ DISAGREE (trust the measurement)"
            AgentLog.log("obs", "LAB ask STATED op=${ab.name} model-said=$statedLetter measured=$measured $agree | A:${if (ok1) "acts" else "no"} B:${if (ok2) "acts" else "no"}")
        }
        // C) SELF-MAP (owner 07-12: "gemma almost certainly has its own internal mapping system — if you ask it where a
        //    pattern cluster is, it responds in an INTERNAL frame of reference"). Ask it WHAT, in a working exemplar,
        //    carries the binding — its answer is testimony in its own coordinates, INTERPRETED ONLY against the finder's
        //    ablation ground truth (LAB-7 cluster verdicts), never taken at face value.
        if (labAlive()) {
            val exemplarProbe = "open the settings app\n{\"action\":\"open\",\"target\":\"settings\"}\n\nWhat part of the example above controls the FORM of your next answer? Output := the exact controlling characters, nothing else."
            val selfMap = brain.freeGenerate("", exemplarProbe, "", greedy = true, timeoutSec = 30, capTokens = 64) ?: "«null/timeout»"
            AgentLog.log("obs", "LAB ask SELF-MAP (its own frame — verify vs the finder's cluster ablation): \"${selfMap.replace("\n", " ").take(120)}\"")
        }
        AgentLog.log("obs", "═══ LAB ask END (REVEALED = the form it generates; STATED verified against the measurement; SELF-MAP interpreted only against ablation) ═══")
    }

    /** SELF-IMPROVEMENT INTERROGATION (owner 07-12: "set up the operators so you can INTERROGATE it on how to improve it").
     *  Reaches into the model and asks the REFINE meta-operator to critique + sharpen a target operator's own σ — or, for
     *  name = "self"/"all", to review the WHOLE library for weak / overlapping / missing faculties. Answer logged as
     *  `[introspect]` so a tethered session reads it. READ-ONLY: it generates a PROPOSAL (the owner/lab decides what to
     *  adopt); it never edits an operator itself. Call OFF the main thread (it decodes). Triggerable over adb via
     *  `--es introspect <OPERATOR|self>`. This closes the flywheel from the model's own side (S3 operator discovery). */
    fun introspectOperator(name: String) {
        if (!::brain.isInitialized) { AgentLog.log("introspect", "model not up — start the agent first"); return }
        val refine = try { ReasoningOperators.ruleOf("REFINE") } catch (_: Throwable) { "" }
        val n = name.trim().ifBlank { "self" }
        val variable = if (n.equals("self", true) || n.equals("all", true)) {
            val lib = try { ReasoningOperators.libraryDigest() } catch (_: Throwable) { "" }
            "OPERATOR LIBRARY (name: when-to-use):\n$lib\n\nWhich faculties are WEAK, OVERLAPPING, or MISSING, and what is the single highest-value improvement to this agent's operator set? Be specific and concrete."
        } else {
            val target = try { ReasoningOperators.ruleOf(n) } catch (_: Throwable) { "" }
            if (target.isBlank()) { AgentLog.log("introspect", "$n: unknown operator (no rule to refine)"); return }
            "OPERATOR TO REFINE: $n\nIts formal rule:\n$target\n\nDiagnose its specific weaknesses (over-broad / leaky / over-refusing / ambiguous / non-binding) and propose a SHARPER version in the same σ shape."
        }
        AgentLog.log("introspect", "═══ REFINE $n ═══")
        val out = (try { brain.freeGenerate(refine, variable, "Refine it.", greedy = false, timeoutSec = 120) }
                   catch (t: Throwable) { "«error: ${t.message}»" }) ?: "«null/timeout»"
        AgentLog.log("introspect", "$n → ${out.replace("\n", " ¶ ")}")
        AgentLog.log("introspect", "═══ end $n ═══")
    }

    /** adb-drivable state-map dispatcher (so the whole protocol can be driven over adb, incl. the restart between
     *  induce and compare, without UI taps):
     *    am start-service -n com.local.deviceagent/.AgentService -a com.local.deviceagent.STATEMAP --es step induce [--es op NAME]
     *  steps: fingerprint | induce | reload | compare | all (= fingerprint→induce→reload in one process). Each step
     *  blocks minutes on greedy decodes, so it runs off the main thread; all results go to the [statemap] log. */
    private fun runStateMapStep(step: String, op: String) {
        Thread {
            val opName = if (op.isBlank()) "ACCURACY" else op
            val r = when (step.lowercase().trim()) {
                "fingerprint" -> runStateFingerprint()
                "induce" -> runInduceAndMeasure(opName)
                "reload" -> runReloadReprobe()
                "compare" -> runCompareToSaved()
                "all" -> "fp[${runStateFingerprint()}] induce[${runInduceAndMeasure(opName)}] reload[${runReloadReprobe()}]"
                else -> "unknown step '$step' (use fingerprint|induce|reload|compare|all)"
            }
            AgentLog.log("statemap", "adb step '$step' → $r")
        }.start()
    }

    /** P3 — THE ACTION-LAYER BAKE (owner's headline: "a button that bakes the action layer into the parameters").
     *  Identical σ-off-gated write pipeline as runDirectedBake, but restricted to the ACTION-LAYER capabilities
     *  (SCHEMA / VERB / NAVIGATE / LAYOUT) so the owner's one button drives THOSE into the weights specifically —
     *  and when one graduates, the P2 drop-seam collapses its verbose prompt block (the action manual / device
     *  profile) to a tag. Same recovery net + coherence gate + reversible journal; nothing new can degrade the model
     *  that runDirectedBake couldn't. Non-blind by construction (basket-gated + reversible + diff-verifiable). */
    fun runActionLayerBake() = bakeOnce(only = ReasoningOperators.ACTION_LAYER, prefix = "actionbake")

    /** A1/W4 — THE WORLD-MODEL BAKE (JEPA, INV-81): the SAME σ-off-gated write pipeline as runActionLayerBake, restricted
     *  to the WORLD_MODEL pool (PREDICT), so this drives the passive next-screen predictor into the weights. Because the
     *  PREDICT reference stores GROUND TRUTH (the screen we actually observed next), its σ-off residency IS "does the
     *  frozen model already predict reality"; ScaleBake picks the LOWEST-agreement class-invariant (= where prediction is
     *  worst = the curiosity target) and KEEPS the nudge only if predictive agreement rose — the JEPA energy moving into
     *  W. Only INVARIANT targets are ever banked (W3 stripped variable content), so a bake can't overfit to a timestamp.
     *  Inert until ≥MIN_HELDOUT PREDICT held-out refs exist. Full recovery net inherited verbatim (snapshot + coherence
     *  probe + WeightGenome exact revert + brick-guard). This is the FIRST world-model write. */
    fun runWorldModelBake() = bakeOnce(only = ReasoningOperators.WORLD_MODEL, prefix = "worldbake")

    /** Shared bake pipeline for both the general directed bake ([only]=null) and the action-layer bake
     *  ([only]=ACTION_LAYER). [prefix] tags the log lines so a pasted log distinguishes the two. */
    private fun bakeOnce(only: Set<String>?, prefix: String) {
        if (teardownRequested) return   // e-stop requested: don't START a new weight write
        if (!settings.isDirectedBakeEnabled()) { AgentLog.log("selfmodel", "$prefix: directed_bake is OFF (enable it in Settings)"); return }
        if (isAgentBusy || (::brain.isInitialized && brain.isGenerating())) { AgentLog.log("selfmodel", "$prefix: agent busy — run when idle"); return }
        if (!::brain.isInitialized) { AgentLog.log("selfmodel", "$prefix: model not up — start a task first"); return }
        logReferenceInventory(only)   // SM4: show the ref inventory so a no-op bake explains itself ("need ≥5 to score")
        val target = try { ScaleBake.selectTarget(applicationContext, brain, only) } catch (e: Exception) {
            AgentLog.log("selfmodel", "$prefix: select failed — ${e.message}"); return
        } ?: return                                                     // no candidate — selectTarget already logged why
        // W7 VICReg codec-health gate: refuse a WORLD-MODEL bake when the reference pool has COLLAPSED (one target
        // class dominates / no variance) — baking that would only entrench a degenerate "always predict the same"
        // mapping. Pre-write, read-only; skips the bake with a log, touches no weight.
        if (CodecHealth.applies(target.op) && CodecHealth.collapsed(applicationContext, target.op, target.fp)) {
            AgentLog.log("selfmodel", "$prefix: SKIPPED ${target.op} — reference pool collapsed (no variance across target classes); bank more varied screens first")
            return
        }
        try {
            // e-stop: this bake runs on a background worker while the agent is IDLE (not running a task). Capture the
            // thread so onDestroy's bounded join lets an in-flight write+fsync FINISH atomically — a half-written
            // .litertlm can happen even when no task is running (owner: "agent didn't have to be running").
            evolveThread = Thread.currentThread()
            SelfEvolve.maybeSnapshot(applicationContext, settings)      // recovery point before the edit
            brain.close()                                              // free the mmap so the file is writable
            val desc = ScaleBake.applyProposal(applicationContext, settings, target.op, 0)
            if (desc == null) { try { brain.probeCoherent() } catch (_: Throwable) {}; return }   // nothing written; reload
            val coherent = try { brain.probeCoherent() } catch (_: Throwable) { true }            // reloads the engine + checks
            if (!coherent) {
                brain.close(); val n = WeightGenome.revertLast(applicationContext, settings)
                AgentLog.log("selfmodel", "$prefix REVERTED ${target.op}: incoherent after edit ($n bytes) — $desc"); return
            }
            val after = try { ResidencyScore.scoreOperator(applicationContext, brain, target.op, target.fp)?.exactAgree ?: -1.0 } catch (_: Exception) { -1.0 }
            // U3 CONTRAST: also re-score how resident the operator's proven-BAD move is now. A kept edit must raise
            // good-residency OR lower bad-residency, and is REVERTED if it entrenched the bad move (even if good rose).
            val afterContrast = try { ResidencyScore.scoreContrast(applicationContext, brain, target.op, target.fp)?.exactAgree ?: -1.0 } catch (_: Exception) { -1.0 }
            val posRose = ScaleBake.kept(target.before, after)
            val contrastFell = ScaleBake.contrastFell(target.beforeContrast, afterContrast)
            val contrastRose = ScaleBake.contrastRose(target.beforeContrast, afterContrast)
            val cStr = if (target.beforeContrast < 0) "" else " · bad-mode ${(target.beforeContrast * 100).toInt()}%→${if (afterContrast < 0) "?" else (afterContrast * 100).toInt().toString()}%"
            if ((posRose || contrastFell) && !contrastRose) {
                val why = if (posRose) "good-residency rose" else "pushed W away from the bad move"
                AgentLog.log("selfmodel", "$prefix KEPT ${target.op}: agreement ${(target.before * 100).toInt()}%→${(after * 100).toInt()}%$cStr ($why · $desc)")
                if (ScaleBake.shouldGraduate(after)) {
                    val fp = target.fp
                    val now = AgentMemory.distilledOperators(applicationContext, fp) + target.op.uppercase()
                    AgentMemory.setDistilledOperators(applicationContext, now, fp)
                    val drop = if (target.op.uppercase() in ReasoningOperators.ACTION_LAYER)
                        " (action-layer capability resident in W — its prompt block drops to a tag)" else ""
                    AgentLog.log("selfmodel", "$prefix GRADUATED ${target.op} → baked (inject drops to the ~1-token TAG)$drop")
                }
            } else {
                brain.close(); val n = WeightGenome.revertLast(applicationContext, settings)
                val aStr = if (after < 0) "?" else (after * 100).toInt().toString()
                val why = if (contrastRose) "entrenched the bad move" else "no gain"
                AgentLog.log("selfmodel", "$prefix reverted ${target.op}: ${(target.before * 100).toInt()}%→$aStr%$cStr $why ($n bytes) — $desc")
            }
        } catch (e: Exception) {
            AgentLog.log("selfmodel", "$prefix beat error: ${e.message}")
            try { if (::brain.isInitialized) brain.probeCoherent() } catch (_: Throwable) {}
        } finally {
            evolveThread = null
        }
    }

    private enum class Mode { LOADING, IDLE, CAPTURING, BUSY }

    private lateinit var tts: TextToSpeech
    private lateinit var settings: SettingsManager
    private lateinit var brain: AgentBrain
    private lateinit var orchestrator: AgentOrchestrator
    private val handler = Handler(Looper.getMainLooper())
    private val inputOverlay = InputOverlay()   // typed-answer popup for the agent's questions
    private val wakeLock by lazy {
        (getSystemService(POWER_SERVICE) as PowerManager)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "agent:task")
            // Non-reference-counted so the keep-awake tick can safely RE-LEASE the same lock on a cadence
            // (repeated acquire() re-arms the timeout without stacking a ref count), and one release() frees it.
            .apply { setReferenceCounted(false) }
    }

    private var model: Model? = null
    private var recognizer: Recognizer? = null
    private var speechService: SpeechService? = null
    @Volatile private var loading = false

    private var ttsReady = false
    private var defaultVoice: Voice? = null
    private var maleVoice: Voice? = null
    private var maleVoiceSearched = false
    @Volatile private var ttsSpeaking = false
    private var mode = Mode.LOADING
    private var lastObjective = ""
    private var awaitingAnswer = false
    private var awaitingFollowUp = false
    // AUTONOMOUS SELF-IMPROVE MODE (owner: "press the button and it does whatever it wants, constantly improves").
    // Owner-initiated (§14) runtime loop — a member, so Sleep/emergencyStop (which stop the service) end it, and
    // there is NO boot persistence. STOP (stopCurrentTask) also clears it. §3 gates + kill switches are untouched.
    @Volatile private var autoRunning = false
    private val autoRecent = ArrayList<String>()   // recent self-goals, so it varies instead of repeating
    private var autoOk = 0
    private var autoFail = 0
    private val autoNextRunnable = Runnable { autoCycle() }
    // SELF-EVOLVE beat: the agent rewrites its OWN model file (raw weight edits seeded by its recent operators/
    // screens/memories) in the idle gap between autonomous tasks — permanent, no download, no permission (owner's
    // accepted-risk posture). `evolving` blocks a task from starting mid-edit (a loaded .litertlm is mmap'd);
    // cadence-bounded so it can't thrash the multi-GB file.
    @Volatile private var evolving = false
    // E-STOP LETS THE WEIGHT WRITE FINISH: hold the in-flight self-evolve/self-grow write thread + a stop flag so
    // onDestroy can JOIN it (bounded) before freeing the model mmap — never a half-written .litertlm. teardownRequested
    // also refuses a NEW write once stop is requested (the in-flight one still finishes).
    @Volatile private var evolveThread: Thread? = null
    @Volatile private var teardownRequested = false
    private val WRITE_FINISH_MAX_MS = 4000L   // bounded: a write is a fixed tiny byte count + one fsync (ms); cap covers a self-grow repack
    private var lastEvolveMs = 0L
    private var lastBakeMs = 0L   // directed-bake idle-beat cadence (INV-74): ≥2min between autonomous bakes
    // A5 WEIGHT KEEP-GATE window (only used when weight_gate is on): the acceptance-oracle rate + non-gauntlet task
    // count at the window's start, and how many evolve beats have accumulated since — so a window can be measured
    // against the A1 oracle and rolled back (WeightGenome) on a real regression. Instance-scoped: a process restart
    // just starts a fresh window (unreverted beats stay as the baseline — fine under the owner's raw posture).
    private var gateStartRate = -1        // -1 = window not initialized
    private var gateStartTasks = 0
    private var gateWindowBeats = 0
    // SELF-GROW (INV-60) shares the `evolving` interlock (both mutate the model file — never let them race), with its
    // OWN, longer cadence: a grow (add params + repack) is heavier and rarer than an evolve nibble.
    private var lastGrowMs = 0L
    private val GROW_INTERVAL_MS = 300_000L
    // A4 DREAMING FLYWHEEL cadence (only when `dreaming` is on): consolidate proven corridors in an idle+charging gap.
    // Cheap (zero inference, no model-file touch), so it doesn't share the `evolving` interlock — but idle-gated so it
    // never competes with a live task, and its own cadence so it can't spin.
    private var lastDreamMs = 0L
    private val DREAM_INTERVAL_MS = 180_000L
    // A5 keep-gate knobs — the owner's "BALANCE, not sledgehammer": evaluate a small window OFTEN (so the model keeps
    // changing), require enough new oracle samples for the rate delta to mean something, and revert ONLY on a clear
    // regression past the noise margin (held/rose/within-noise ⇒ keep = bounded exploration built into the margin).
    private val GATE_WINDOW_BEATS = 3     // accumulate ~3 beats before an evaluation is due
    private val GATE_MIN_SAMPLES = 5      // …and at least this many new oracle tasks, so the rate delta isn't noise
    private val GATE_NOISE_MARGIN = 8     // revert only if the oracle rate fell MORE than this (pct) — else keep
    // NEVER-SLEEP (owner: "the agent should never allow the device to fall asleep"). The tick re-leases the wake lock
    // and holds the screen-on overlay flag while keep_awake + enabled + safe; LEASE > TICK so there's never a gap.
    private val KEEP_AWAKE_TICK_MS = 45_000L
    private val KEEP_AWAKE_LEASE_MS = 120_000L
    @Volatile private var keepAwakeArmed = false   // state guard so startKeepAwake() arms once, not on every onStartCommand
    // Conversation mode: the next spoken command should run as a continuous back-and-forth.
    private var pendingContinuous = false
    // True while running a task the owner launched from the text-chat screen, so when it ends we
    // return to the chat and ask for further instructions instead of just going idle.
    private var taskFromChat = false
    private var taskResumeRequested = false   // set from EXTRA_RESUME; consumed at orchestrator.start
    // The most recent task that ended WITHOUT finishing. The agent never silently re-attempts it -
    // it asks first (in the return-to-chat summary), and only the owner's explicit "yes / continue"
    // resumes it. Cleared once resumed, declined, or superseded by a different command.
    private var lastUnfinishedTask = ""
    // What the owner is currently teaching by demonstration (from the floating Train flow).
    private var trainingGoal = ""

    private val cancelWords = listOf("stop", "cancel", "abort", "halt")
    private val captureTimeout = Runnable { if (mode == Mode.CAPTURING) goIdle() }
    // Clear ttsSpeaking here too: if this safety net fires, the TTS onDone was DROPPED, so the agent is no longer
    // speaking — leaving ttsSpeaking=true keeps it DEAF to voice (incl. the shouted-"stop" kill switch).
    private val resumeListeningRunnable = Runnable { ttsSpeaking = false; resumeListening() }
    // ANR FIX: memory-relief closes (@Synchronized onMemoryPressure/closeSafely) can block on ensureEngine's
    // monitor across the multi-second GPU load; onTrimMemory fires on the MAIN thread, so run them off it. A
    // single thread keeps them correctly serialized with the load, just never stalling the UI thread.
    private val memReliefExec = java.util.concurrent.Executors.newSingleThreadExecutor()
    private val answerTimeout = Runnable {
        if (awaitingAnswer) stopCurrentTask("I didn't catch an answer, so I'll stop for now.")
    }

    /** Start (or re-assert) the foreground service with a type whose runtime permission we actually
     *  hold. On a fresh install RECORD_AUDIO isn't granted, and Android 14+ throws SecurityException if a
     *  microphone-typed FGS starts without it (the launch crash) - so fall back to SPECIAL_USE (needs no
     *  runtime permission) until the mic is granted, then promote to microphone. Wrapped so a start
     *  failure degrades to "no notification" instead of crashing the process. */
    private fun startAgentForeground(status: String) {
        val notif = NotificationHelper.buildNotification(this, status, false)
        try {
            if (Build.VERSION.SDK_INT >= 34) {
                // Android 14+ ENFORCES the FGS type's permission at startForeground time. Pick a type whose
                // permission we actually hold: microphone once RECORD_AUDIO is granted, else SPECIAL_USE
                // (needs no runtime permission) so a fresh install never crashes here.
                val micGranted = ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) ==
                    PackageManager.PERMISSION_GRANTED
                val type = if (micGranted) ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
                           else ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE
                startForeground(NotificationHelper.SERVICE_NOTIFICATION_ID, notif, type)
            } else {
                // Pre-34 (minSdk 31): there is NO FGS-type permission enforcement, and the API-34 SPECIAL_USE
                // type / "specialUse" manifest value don't exist there - so use the 2-arg form (the manifest
                // "microphone" type is accepted without the grant). No crash risk on these versions.
                startForeground(NotificationHelper.SERVICE_NOTIFICATION_ID, notif)
            }
        } catch (e: Exception) {
            // A service started via startForegroundService MUST foreground within ~5s or the system throws
            // ForegroundServiceDidNotStartInTimeException. If startForeground somehow failed anyway, tear
            // down cleanly instead of risking that timeout crash.
            AgentLog.log("safety", "startForeground failed (${e.message}) - stopping the service to avoid a timeout crash")
            try { stopForeground(Service.STOP_FOREGROUND_REMOVE) } catch (_: Exception) {}
            stopSelf()
        }
    }

    override fun onCreate() {
        super.onCreate()
        instance = this
        settings = SettingsManager(this)
        AgentLog.init(applicationContext)
        AgentMemory.pruneJunkObservations(applicationContext)   // auto-clean junk the owner shouldn't have to delete
        NotificationHelper.createChannel(this)
        // Start foreground with a type whose runtime permission we actually hold. THE LAUNCH-CRASH FIX:
        // the manifest types this service "microphone", and on Android 14+ startForeground() for a
        // microphone FGS throws SecurityException if RECORD_AUDIO isn't granted - which it isn't on a
        // FRESH install (the launcher, ChatActivity, never requests it; only MainActivity's setup does).
        // So fall back to SPECIAL_USE (no runtime permission needed) until the mic is granted.
        startAgentForeground("Starting…")

        tts = TextToSpeech(this, this)

        brain = AgentBrain(applicationContext)
        orchestrator = AgentOrchestrator(
            brain = brain,
            speak = { text -> speak(text) },
            onComplete = { success, doneSay ->
                isAgentBusy = false
                releaseWakeLock()
                AgentLog.log("diag", "end :: ${DeviceStats.snapshot(applicationContext)}")
                if (lastObjective.isNotBlank()) {
                    // An owner-initiated stop is a NEUTRAL outcome, not a failure: record "stopped-by-owner"
                    // so failureHintFor doesn't replay it to the next run as "your last attempt failed" and
                    // isSuccess doesn't count it either (both key on "stopped"/"finished", which this isn't).
                    val execSteps = orchestrator.lastExecutedSteps()
                    val runId = TaskHistory.add(applicationContext, lastObjective,
                        if (success) "finished" else if (orchestrator.lastRunStoppedByOwner()) "stopped-by-owner" else "stopped",
                        plan = orchestrator.lastPlan(),
                        steps = execSteps.takeIf { it.isNotEmpty() }?.map { it.summary } ?: orchestrator.lastSteps(),
                        durationMs = orchestrator.lastRunDurationMs(),
                        failureClass = orchestrator.lastRunFailureClass(),
                        gauntlet = GauntletRunner.isRunning())
                    // P0 grader: persist the run's STRUCTURED executed steps keyed to its id, so an owner ✓/✗ in the
                    // task log banks a ReferenceStore win/contrast for the bake. Best-effort; never affects the task.
                    try {
                        if (runId > 0L && execSteps.isNotEmpty())
                            ExecStepStore.record(applicationContext, runId,
                                ModelStore.activeFingerprint(applicationContext, settings),
                                execSteps.map { ExecStepStore.Step(it.op, it.sig, it.prompt, it.action, it.clause, it.m) })
                    } catch (_: Throwable) {}
                }
                // Gauntlet hook: no-op unless a gauntlet is running and this was its current task.
                // Pass latency + step count so the A/B harness can report per-step decision latency.
                GauntletRunner.onTaskEnded(applicationContext, lastObjective, success,
                    orchestrator.lastRunDurationMs(), orchestrator.lastSteps().size)
                // Remember an UNFINISHED task so we can offer to resume it - but only ever with the
                // owner's say-so (never silently). A clean finish clears any pending resume.
                lastUnfinishedTask = if (!success && lastObjective.isNotBlank())
                    lastObjective.lineSequence().first().trim() else ""
                val fromChat = taskFromChat; taskFromChat = false
                if (autoRunning) {
                    // AUTONOMOUS LOOP: tally, surface any failure, and schedule the next self-chosen goal — no
                    // "anything else?" prompt, no full idle (the loop drives itself). A STOP already cleared
                    // autoRunning, so a stopped run falls through to the normal idle path below.
                    if (success) autoOk++
                    else { autoFail++; AgentLog.log("auto", "task FAILED (${orchestrator.lastRunFailureClass().ifBlank { "?" }}): ${lastObjective.take(60)}") }
                    // G2 MECHANISM ROUTER (advisory): settle the credit for whatever mechanism last fired against
                    // the CURRENT acceptance-oracle rate (the bandit's reward), then log which mechanism the failure
                    // trend recommends now + which has earned its keep so far. Advisory/telemetry only here — the
                    // beats below still fire on their own cadence (the hard flag-gated dispatch is the next step);
                    // this fills the "no arbiter, no bandit tracks what moved the metric" gap the research flagged.
                    try {
                        val rate = TaskHistory.rollingSuccessRate(applicationContext, 20).third
                        MechanismRouter.settleCredit(applicationContext, rate)
                        val (rec, why) = MechanismRouter.recommend(applicationContext)
                        AgentLog.log("router", "recommends: $rec ($why)" +
                            MechanismRouter.readout(applicationContext).let { if (it.isBlank()) "" else " · credit: $it" })
                    } catch (_: Throwable) {}
                    // SELF-EVOLVE beat in the idle gap (if on) BEFORE the next goal — so the model edit never
                    // races a running task; the next self-goal starts only once the edit is done + engine freed.
                    maybeSelfEvolve { maybeBake { maybeGrow { maybeDream { handler.postDelayed(autoNextRunnable, 4000) } } } }
                } else if (fromChat) {
                    // Task was launched from the text chat: post a real SUMMARY (what happened + any
                    // files/logins it created), then bring the chat back for the next instruction.
                    ChatStore.add(applicationContext, "agent", buildChatOutcome(success, doneSay))
                    try {
                        startActivity(Intent(this, ChatActivity::class.java)
                            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_REORDER_TO_FRONT))
                    } catch (_: Exception) {}
                    goIdle()
                } else if (success) completeAndOfferMore(doneSay) else goIdle()
            },
            // Last-resort fallback ONLY when the agent is genuinely stuck - not a default crutch.
            onStuck = { obj -> tryDeterministic(obj) },
            onAsk = { q -> handler.post { askUser(q) } },
            stepDelay = { settings.getStepDelayMs() },
            onStatus = { s -> handler.post { if (isAgentBusy) { updateNotification(s, false); speakStatus(s) } } },
            safetyCheck = { deviceSafetyReason() }
        )

        startVoicePipeline()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> { stopSelf(); return START_NOT_STICKY }
            ACTION_STOP_TASK -> stopCurrentTask()
            ACTION_RESUME -> goIdle()
            ACTION_LISTEN_NOW -> onListenNow()
            ACTION_CONVERSATION -> {
                // Like verbal input, but the spoken command runs as a continuous back-and-forth.
                pendingContinuous = true
                onListenNow()
            }
            ACTION_RUN_COMMAND -> {
                val cmd = intent.getStringExtra(EXTRA_COMMAND).orEmpty()
                if (cmd.isNotBlank()) {
                    taskFromChat = intent.getBooleanExtra(EXTRA_FROM_CHAT, false)
                    taskResumeRequested = intent.getBooleanExtra(EXTRA_RESUME, false)
                    runCommand(cmd)
                }
            }
            ACTION_TRAIN_START -> startTraining(intent.getStringExtra(EXTRA_GOAL).orEmpty())
            ACTION_TRAIN_FINISH -> finishTraining()
            ACTION_LEARN_MODE -> startLearnMode()
            ACTION_AUTO_MODE -> toggleAutoMode()
            ACTION_STATEMAP -> runStateMapStep(intent.getStringExtra(EXTRA_STEP).orEmpty(), intent.getStringExtra(EXTRA_OP).orEmpty())
        }
        startKeepAwake()   // NEVER-SLEEP: hold the device awake whenever the service is up + keep_awake is on
        return START_STICKY
    }

    // ── AUTONOMOUS SELF-IMPROVE MODE ─────────────────────────────────────────────────────────────────────────
    // Owner presses one button and the agent runs on its own: it picks its OWN safe, useful goal, does it, then
    // picks the next — looping, tuning its operators (self_calibrate) and capturing rich data as it goes, so it
    // "constantly improves." SAFETY: this is owner-INITIATED (a button, §14 owner-only, no boot persistence) and
    // fully kill-switchable — STOP/notification-Stop/shouted "stop" end the loop (stopCurrentTask clears it), and
    // Sleep/emergencyStop kill the service. Every §3 hard gate in the executor still fires: an unsafe ACTION is
    // blocked no matter what goal the model set. Autonomy is over GOALS inside the safety envelope, nothing more.
    private fun toggleAutoMode() { if (autoRunning) stopAutoMode("owner toggled off") else startAutoMode() }

    private fun startAutoMode() {
        if (autoRunning) return
        autoRunning = true
        autoRecent.clear(); autoOk = 0; autoFail = 0
        // One button = the full self-improve + rich-capture experience (dedicated device). The owner can turn any
        // of these back off; they're the existing flags, just switched on together here.
        settings.setSelfCalibrateEnabled(true)
        settings.setDataCaptureEnabled(true)
        settings.setDebugModeEnabled(true)
        AgentLog.log("auto", "AUTONOMOUS MODE ON — self-directed loop: pick a SAFE goal → run → improve → repeat. " +
            "STOP ends it; §3 gates + kill switches intact.")
        speak("Auto mode on. I'll pick my own tasks and keep improving. Say stop, or tap the button, to end.")
        autoCycle()
    }

    private fun stopAutoMode(reason: String) {
        if (!autoRunning) return
        autoRunning = false
        handler.removeCallbacks(autoNextRunnable)
        AgentLog.log("auto", "AUTONOMOUS MODE OFF ($reason) — this session: ${autoOk}✓ / ${autoFail}✗")
    }

    /** One turn of the loop: unless stopped, wait out any running task + the device-safety gate, then have the
     *  model choose its OWN next safe goal and start it. Bounded backoffs so it can never tight-spin. */
    private fun autoCycle() {
        if (!autoRunning) return
        if (!settings.isAgentEnabled()) { stopAutoMode("agent disabled"); return }   // Sleep/wake master switch
        if (isAgentBusy) { handler.postDelayed(autoNextRunnable, 3000); return }      // a task is running/finishing
        // Respect the SAME battery/thermal gate the step loop uses — back off, never spin, when the phone's unsafe.
        deviceSafetyReason()?.let { reason ->
            AgentLog.log("auto", "paused (device safety: $reason) — retry in 60s")
            updateNotification("Auto paused: $reason", false)
            handler.postDelayed(autoNextRunnable, 60_000); return
        }
        brain.selfGoal(autoRecent) { goal ->
            handler.post {
                if (!autoRunning) return@post
                val g = goal.trim().take(120)
                if (g.length < 3) { handler.postDelayed(autoNextRunnable, 5000); return@post }  // bad goal → retry
                autoRecent.add(g); while (autoRecent.size > 12) autoRecent.removeAt(0)
                AgentLog.log("auto", "self-goal: $g")
                beginAutoTask(g)
            }
        }
    }

    /** Start a self-chosen task via the orchestrator. A lean copy of runCommand's start tail — no resume gate, no
     *  deterministic shortcuts (which would bypass onComplete and stall the loop), no chat plumbing. */
    private fun beginAutoTask(goal: String) {
        lastObjective = goal
        taskFromChat = false
        awaitingAnswer = false; awaitingFollowUp = false
        isAgentBusy = true
        lastStatusSpoken = ""
        mode = Mode.BUSY
        ActionAccessibilityService.instance?.createdArtifacts?.clear()
        ActionAccessibilityService.instance?.clearCollected()
        if (::brain.isInitialized) brain.prewarm()
        acquireWakeLock()
        ensureFloatingButton()   // keep the STOP control up the whole loop
        handler.removeCallbacks(captureTimeout)
        updateNotification("Auto (${autoOk}✓/${autoFail}✗): $goal", false)
        val preloadName = resolvePreloadApp(goal)
        if (preloadName == null && ActionAccessibilityService.instance?.currentPackage() == packageName)
            ActionAccessibilityService.instance?.performActionJson("{\"action\":\"home\"}")
        orchestrator.start(goal, continuous = false, preloadApp = preloadName)
    }

    /** G2 SOFT DISPATCH: when `mechanism_router` is on, defer an idle self-mod beat whose mechanism isn't the
     *  router's current recommendation this cycle — biasing idle compute toward the mechanism the failure trend +
     *  oracle actually call for. NEVER a hard disable: each beat keeps its own cadence, so a deferred mechanism runs
     *  on a later cycle (no starvation). Off (default) ⇒ always allows (byte-identical). A non-idle recommendation
     *  (calibrate/genesis, handled during tasks) or NONE defers the idle WEIGHT beats, so idle compute isn't spent
     *  perturbing weights the trend didn't ask for. Fails OPEN on any error — the router never blocks a beat. */
    private fun routerAllows(mechanism: String): Boolean {
        if (!settings.isMechanismRouterEnabled()) return true
        return try {
            val (rec, _) = MechanismRouter.recommend(applicationContext)
            val allow = rec == mechanism
            if (!allow) AgentLog.log("router", "dispatch: deferring $mechanism this cycle (prioritising $rec)")
            allow
        } catch (_: Throwable) { true }
    }

    /** SELF-EVOLVE (owner accepted-risk): in an idle gap, snapshot on cadence, close the engine, apply ONE raw
     *  learning-seeded weight edit to the model file, then continue — the next task reloads the evolved weights,
     *  and the brick-guard restores a backup if an edit ever makes the model unloadable. Runs OFF the main thread;
     *  calls [then] (schedule the next self-goal) when done, so NO task runs during the edit. No-op unless
     *  self_evolve is on, we're idle, off RAM pressure, and the cadence has elapsed. */
    private fun maybeSelfEvolve(then: () -> Unit) {
        val busy = isAgentBusy || (::brain.isInitialized && brain.isGenerating())
        if (teardownRequested || evolving || !settings.isSelfEvolveEnabled() || busy ||
            System.currentTimeMillis() - lastEvolveMs < 120_000L ||
            DeviceStats.memPressure(this) != DeviceStats.MemPressure.NONE) { then(); return }
        if (!routerAllows(MechanismRouter.EVOLVE)) { then(); return }   // G2 soft dispatch (defers, never disables)
        lastEvolveMs = System.currentTimeMillis()
        evolving = true
        // G2 router: stamp EVOLVE as the mechanism that just fired, at the current oracle rate, so the next
        // idle cycle can attribute the rate delta to it (the bandit's reward — which mechanism actually helps).
        try { MechanismRouter.markFired(applicationContext, MechanismRouter.EVOLVE, TaskHistory.rollingSuccessRate(applicationContext, 20).third) } catch (_: Throwable) {}
        // GROUNDED-TRUTH SEED (owner: "ground weight modification in truth"): seed the edit from what the agent has
        // VERIFIED — its proven-exact operators + the navigation that proved out by REAL repeated success + the
        // model fingerprint — NEVER the raw log tail (unverified on-screen text). This keeps the edit RICH (derived
        // from the agent's real verified experience, not just a thin operator list) AND immune to display-injection:
        // a hostile screen can show anything but cannot make something PROVEN, so it can't steer the edit. nanoTime
        // keeps per-beat variety within the owner's fully-raw posture. (The σ-off-validated crystallization that
        // KEEPS an edit only when it moved the capability into W rides the OWNER-GATED ModelSelfUpdate pipeline — INV-64.)
        // A4 link: when `dreaming` is on, fold the consolidated proven-corridor digest into the seed so idle dreaming
        // STEERS where the forge nudges (the "wakes up sharper" path) — still grounded (proven corridors, not raw text).
        val ident = AgentMemory.groundedLearningDigest(applicationContext) +
            "|" + ModelStore.activeFingerprint(applicationContext, settings) +
            (if (settings.isDreamingEnabled()) "|dream:" + DreamFlywheel.dreamDigest(applicationContext) else "")
        val seed = (ident.hashCode().toLong() shl 20) xor System.nanoTime()
        evolveThread = thread(name = "self-evolve") {
            try {
                SelfEvolve.maybeSnapshot(applicationContext, settings)   // hourly recovery point (a GB copy)
                if (::brain.isInitialized) brain.close()                 // free the mmap'd file before editing it
                // A5 KEEP-GATE (weight_gate only, engine now closed ⇒ file writable): score the PREVIOUS window of
                // beats against the A1 oracle and roll it back on a real regression, BEFORE laying down this beat.
                evaluateWeightGateWindow()
                // RANDOM WALK RETIRED (07-09): the RANDOM ±1 nibble write is the stray-tap source (corruption-dominated
                // on a 4B-weight int4 model) and is superseded by DIRECTED operator baking (Phase 3+), which slots its
                // computed, σ-off-validated write in right here. Default OFF ⇒ the beat still snapshots + ran the
                // keep-gate above (healing prior degradation) + guards the brick, but writes NO new random bytes.
                val wrote = if (settings.isRandomEvolveEnabled())
                    SelfEvolve.editActiveFile(applicationContext, settings, seed)
                else { AgentLog.log("selfmodel", "self-evolve: random write RETIRED (directed baking pending) — no weight edit this beat"); false }
                if (wrote) {
                    // VALIDATED-BEFORE-PERSIST (the stray-tap fix — plan §B1): a RANDOM int4 nudge can degrade the
                    // model into emitting garbage, which the executor salvages into WRONG taps (the owner's "stray
                    // taps while auto-mode runs unattended" bug). Probe the edited model NOW; if this beat broke its
                    // coherence, REVERT exactly this beat (precise, via WeightGenome) BEFORE it can drive a single
                    // action. probeCoherent reloads the engine (warming it for the next auto-goal, so not a wasted GB
                    // load); a beat that made the model unloadable trips the brick-guard restore inside the probe, so
                    // the probe then reads coherent and we correctly DON'T double-revert. Only a KEPT beat counts into
                    // the oracle keep-gate window. This makes self_evolve non-degrading by construction — it stays ON.
                    val coherent = try { if (::brain.isInitialized) brain.probeCoherent() else true } catch (_: Throwable) { true }
                    if (!coherent) {
                        if (::brain.isInitialized) brain.close()   // free the mmap so the model file is writable to revert
                        WeightGenome.revertLast(applicationContext, settings)
                        AgentLog.log("selfmodel", "self-evolve: beat REVERTED — coherence probe failed (would degrade → stray taps)")   // de-narrated: no nibble count
                    } else if (settings.isWeightGateEnabled()) gateWindowBeats++   // only a KEPT, coherent beat opens/extends the window
                }
            } catch (e: Exception) {
                AgentLog.log("selfmodel", "self-evolve beat error: ${e.message}")
            } finally {
                evolving = false
                handler.post { then() }
            }
        }
    }

    /** A5 KEEP-GATE evaluation (weight_gate only; the owner's "BALANCE, not sledgehammer"). Runs in the idle
     *  self-evolve beat AFTER the engine is closed (the model file is writable) and BEFORE this beat's edit. When a
     *  window of beats has accumulated AND enough NEW acceptance-oracle samples exist to trust the trend, it decides
     *  keep-vs-revert against the A1 oracle rate: it reverts the window's journaled beats (precise, via WeightGenome)
     *  ONLY on a real regression past the noise margin — held/rose/within-noise are all KEPT, so the model keeps
     *  changing REGULARLY (the noise margin IS the bounded-exploration allowance). Then it resets the window from the
     *  current measured point. Zero inference — reads the ledger the acceptance oracle already keeps (§2/§12-clean:
     *  it gates a checkpoint keep/revert, never an action). No-op unless weight_gate is on. */
    private fun evaluateWeightGateWindow() {
        if (!settings.isWeightGateEnabled()) return
        val (_, _, rate) = TaskHistory.rollingSuccessRate(applicationContext, 20)
        val tasks = try { TaskHistory.list(applicationContext).count { !it.gauntlet } } catch (_: Throwable) { 0 }
        if (gateStartRate < 0) { gateStartRate = rate; gateStartTasks = tasks; gateWindowBeats = 0; return }  // open the first window
        val newSamples = tasks - gateStartTasks
        if (gateWindowBeats < GATE_WINDOW_BEATS || newSamples < GATE_MIN_SAMPLES) return   // not due yet — keep accumulating
        val delta = rate - gateStartRate
        if (delta < -GATE_NOISE_MARGIN) {
            // Real, noise-clearing regression: roll back exactly this window's journaled beats (finer + cheaper than
            // a full multi-GB snapshot restore, and it keeps every good edit made before the window).
            WeightGenome.revertBeats(applicationContext, settings, gateWindowBeats)
            AgentLog.log("selfmodel", "keep-gate: REVERTED window ($gateWindowBeats beats) — oracle $gateStartRate%→$rate% (Δ$delta over $newSamples tasks)")   // de-narrated: no nibble count
        } else {
            AgentLog.log("selfmodel", "keep-gate: KEPT window ($gateWindowBeats beats) — oracle $gateStartRate%→$rate% (Δ$delta over $newSamples tasks)")
        }
        gateStartRate = rate; gateStartTasks = tasks; gateWindowBeats = 0   // reset from the current measured point
    }

    /** THE AUTOMATIC LEARNED-BAKE idle beat (INV-74; owner reframe 07-10 EVE: "learn baking should not be a button but
     *  automatic"). This is the LEARNED half of the split — distinct from the Bake button's DIRECT defined-operator
     *  install (`runDefinedBake`). It bakes what genuinely ACCRUES from the owner's use — the JEPA world model
     *  (next-screen/flow/pixel prediction learned from watching the phone) and experience-tuned operators — via the
     *  reference-gated `runDirectedBake` (bakeOnce(only=null) picks the global lowest-σ-off-residency candidate with
     *  enough banked evidence). After the button installs the defined library, those are resident, so this beat
     *  naturally targets the world model + experience. Sibling of [maybeSelfEvolve]: in an idle gap it bakes the
     *  lowest-σ-off-residency candidate toward higher agreement via `runDirectedBake` — which snapshots, closes the engine, writes only
     *  the per-channel int4 SCALES (the DoRA-magnitude axis, non-scrambling), reloads, and KEEPS the edit ONLY if the
     *  operator's σ-off agreement ROSE past the noise margin AND the model stays coherent; else it reverts exactly
     *  (WeightGenome). So it's NON-DEGRADING by construction — the opposite of the retired random walk — and a graduated
     *  operator drops from the prompt to a ~1-token TAG (success ↑: intrinsic, injection-immune; RAM ↓: smaller prompt ⇒
     *  the KV floor falls, see ensureEngine). Ties the weight-learning into the SAME idle cadence + safety net as the
     *  other self-mod beats. Runs OFF the main thread; sets the `evolving` interlock so chat/calibration can't re-mmap
     *  mid-write; calls [then] when done. No-op unless directed_bake is on, we're idle, off RAM pressure, and the cadence
     *  elapsed — so it's INERT until the owner flips the one weight-writing switch. */
    private fun maybeBake(then: () -> Unit) {
        val busy = isAgentBusy || (::brain.isInitialized && brain.isGenerating())
        if (teardownRequested || evolving || !settings.isDirectedBakeEnabled() || busy ||
            System.currentTimeMillis() - lastBakeMs < 120_000L ||
            DeviceStats.memPressure(this) != DeviceStats.MemPressure.NONE) { then(); return }
        // The bake IS the "proven-exact gains ready to move into W" mechanism, so it shares EVOLVE's router slot.
        if (!routerAllows(MechanismRouter.EVOLVE)) { then(); return }
        lastBakeMs = System.currentTimeMillis()
        evolving = true   // mmap-race interlock (runDirectedBake closes+reloads the engine); cleared in the finally
        thread(name = "directed-bake") {
            try { runDirectedBake() }               // owns its own snapshot / close / σ-off keep-gate / exact revert / reload
            catch (t: Throwable) { AgentLog.log("selfmodel", "bake beat error: ${t.message}") }
            finally { evolving = false; handler.post { then() } }
        }
    }

    /** SELF-GROW beat (INV-60, owner: "add to its own file and increase it… start small, build up"). Sibling of
     *  [maybeSelfEvolve]: in an idle gap it snapshots on cadence, closes the engine, and hands the model file to
     *  `SelfGrow` to ADD parameters (a function-preserving MLP-block widen); the next task reloads the grown weights.
     *  Owner's ceiling = NONE except the critical-failure/junk-bloat guard: after a real grow the STRUCTURAL SANITY
     *  check reverts a malformed/runaway (junk-bloat) write, and the brick-guard (`AgentBrain.ensureEngine`) reverts
     *  an unloadable one on the next load. Shares the `evolving` interlock (no file-mutation race with self-evolve),
     *  its own longer cadence, and RAM-pressure gating. No-op unless self_grow is on + idle + off pressure. */
    private fun maybeGrow(then: () -> Unit) {
        val busy = isAgentBusy || (::brain.isInitialized && brain.isGenerating())
        val f = settings.getModelPath()?.let { File(it) }
        if (teardownRequested || evolving || !settings.isSelfGrowEnabled() || busy || f == null || !f.exists() ||
            System.currentTimeMillis() - lastGrowMs < GROW_INTERVAL_MS ||
            DeviceStats.memPressure(this) != DeviceStats.MemPressure.NONE) { then(); return }
        if (!routerAllows(MechanismRouter.GROW)) { then(); return }   // G2 soft dispatch (defers, never disables)
        lastGrowMs = System.currentTimeMillis()
        evolving = true
        // G2 router: stamp GROW as the mechanism that just fired (see maybeSelfEvolve) for reward attribution.
        try { MechanismRouter.markFired(applicationContext, MechanismRouter.GROW, TaskHistory.rollingSuccessRate(applicationContext, 20).third) } catch (_: Throwable) {}
        // GROUNDED-TRUTH SEED (Batch 9): seed from the agent's VERIFIED learning (proven ops + proven navigation +
        // fingerprint), NOT the raw log tail — rich yet display-injection-immune (a screen can't fake "proven").
        val ident = AgentMemory.groundedLearningDigest(applicationContext) +
            "|" + ModelStore.activeFingerprint(applicationContext, settings)
        val seed = (ident.hashCode().toLong() shl 20) xor System.nanoTime()
        evolveThread = thread(name = "self-grow") {
            try {
                val preSize = f.length()
                SelfEvolve.maybeSnapshot(applicationContext, settings)   // shared hourly recovery ring (a GB copy)
                if (::brain.isInitialized) brain.close()                 // free the mmap'd file before editing it
                val grew = SelfGrow.growActiveFile(applicationContext, settings, seed)
                // JUNK-BLOAT GUARD (owner's only ceiling): a real grow that ballooned or corrupted the container is
                // reverted to the last snapshot before it is ever loaded; an unloadable grow is caught by the
                // brick-guard on the next load. (A2 adds a post-grow generate-probe → revert on degenerate output.)
                if (grew && !SelfGrow.structuralSanityOk(f, preSize)) {
                    AgentLog.log("selfgrow", "grown file failed structural sanity (junk-bloat) — reverting")
                    ModelStore.restoreLatestSnapshot(applicationContext, settings)
                }
            } catch (e: Exception) {
                AgentLog.log("selfgrow", "self-grow beat error: ${e.message}")
            } finally {
                evolving = false
                handler.post { then() }
            }
        }
    }

    /** A4 DREAMING FLYWHEEL beat (owner: "it dreams about using itself and wakes up sharper"). In an idle+charging
     *  gap the agent REPLAYS its own world-model — consolidating proven corridors it has actually walked — so idle
     *  time steers where self-evolve nudges (the "wakes up sharper" link). Cheap + zero-inference + no model-file
     *  touch, so it needs no engine close and no `evolving` interlock; still idle-gated (never races a live task),
     *  charging-gated (it's a spend-battery-to-improve beat, only when plugged in), and cadence-bounded. No-op unless
     *  `dreaming` is on. Runs off the main thread (SharedPreferences I/O) and calls [then] when done. */
    private fun maybeDream(then: () -> Unit) {
        val busy = isAgentBusy || (::brain.isInitialized && brain.isGenerating())
        if (!settings.isDreamingEnabled() || busy ||
            System.currentTimeMillis() - lastDreamMs < DREAM_INTERVAL_MS ||
            !DeviceStats.isCharging(this)) { then(); return }
        lastDreamMs = System.currentTimeMillis()
        thread(name = "dream") {
            try { DreamFlywheel.maybeDream(applicationContext, System.nanoTime()) }
            catch (e: Throwable) { AgentLog.log("dream", "dream beat error: ${e.message}") }
            finally { handler.post { then() } }
        }
    }

    // --- Vosk voice pipeline ----------------------------------------------

    private fun startVoicePipeline() {
        if (loading || speechService != null) return
        loading = true
        mode = Mode.LOADING
        updateNotification("Preparing voice model…", false)
        thread(name = "vosk-load") {
            try {
                val m = VoskModelManager.loadModel(this) { msg ->
                    handler.post { if (mode == Mode.LOADING) updateNotification(msg, false) }
                }
                handler.post { loading = false; onModelReady(m) }
            } catch (e: Exception) {
                handler.post {
                    loading = false
                    updateNotification("Voice model unavailable — tap the mic to retry.", false)
                }
            }
        }
    }

    private fun onModelReady(m: Model) {
        model = m
        // MIC MASTER SWITCH (owner: "turn the agent's mic off so I can run tasks and talk to people").
        // Off = the agent's ears are fully closed: no wake word, no voice-stop, nothing to trip by
        // talking near the phone. The floating STOP button + notification Stop stay live.
        if (!settings.isMicEnabled()) {
            speechService?.let { try { it.stop() } catch (_: Exception) {}; it.shutdown() }
            speechService = null
            recognizer?.close(); recognizer = null
            updateNotification("Mic off — voice control disabled (STOP button still works).", false)
            goIdle()
            return
        }
        try {
            // Rebuilds on every SpeechRecognizer capture window too, so release the previous Vosk
            // recognizer/mic first to avoid leaking AudioRecords across captures.
            speechService?.let { try { it.stop() } catch (_: Exception) {}; it.shutdown() }
            recognizer?.close()
            val rec = Recognizer(m, SAMPLE_RATE)
            recognizer = rec
            // The mic pipeline is actually starting now, so (re)assert the FGS as microphone-typed when
            // RECORD_AUDIO is granted - legitimizes background recording on Android 14+ and promotes from
            // the SPECIAL_USE fallback we launched with when the permission wasn't yet granted.
            startAgentForeground("Listening…")
            speechService = SpeechService(rec, SAMPLE_RATE).also { it.startListening(this) }
            goIdle()
        } catch (e: Exception) {
            updateNotification("Microphone unavailable.", false)
        }
    }

    /** Stop feeding the mic to Vosk while we speak; resume when done. */
    private fun pauseListening() {
        speechService?.setPause(true)
    }

    private fun resumeListening() {
        speechService?.setPause(false)
    }

    // --- TTS --------------------------------------------------------------

    override fun onInit(status: Int) {
        if (status == TextToSpeech.SUCCESS) {
            val r = tts.setLanguage(Locale.getDefault())
            ttsReady = r != TextToSpeech.LANG_MISSING_DATA && r != TextToSpeech.LANG_NOT_SUPPORTED
            if (ttsReady) defaultVoice = tts.voice
            tts.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                override fun onStart(utteranceId: String?) {
                    ttsSpeaking = true
                    handler.post { pauseListening() }
                }
                override fun onDone(utteranceId: String?) { handler.post { onSpeechFinished() } }
                @Deprecated("deprecated") override fun onError(utteranceId: String?) {
                    handler.post { onSpeechFinished() }
                }
                override fun onError(utteranceId: String?, errorCode: Int) {
                    handler.post { onSpeechFinished() }
                }
            })
        }
    }

    private fun onSpeechFinished() {
        ttsSpeaking = false
        handler.removeCallbacks(resumeListeningRunnable)
        // Reset so the tail of our own speech isn't carried into the next utterance.
        recognizer?.reset()
        resumeListening()
    }

    private var lastSpoken = ""
    private var lastSpokenAt = 0L

    // Owner wants RUN-mode tasks to give a VERBAL cue, not just the on-screen status. We speak the
    // meaningful "thinking/planning/re-orienting" beats - but only when the status TEXT changes, so a
    // long run of "Thinking…" says it once rather than chattering. Reset each task so it speaks again.
    private var lastStatusSpoken = ""
    private fun speakStatus(s: String) {
        val clean = s.trim().trimEnd('…', '.', ' ')
        val low = clean.lowercase()
        if (!(low.contains("think") || low.contains("planning") || low.contains("orient") ||
              low.contains("rethink") || low.contains("waiting for the reply"))) return
        if (clean.equals(lastStatusSpoken, ignoreCase = true)) return
        lastStatusSpoken = clean
        speak(clean)
    }

    fun speak(text: String) {
        if (!ttsReady || settings.isSilent()) return
        val t = text.trim()
        // Never read internal diagnostics aloud (this is the "...it only said 'status'..." bug:
        // an engine error string like "Status Code: 3. Message: Input token ids are too long"
        // was being spoken, then QUEUE_FLUSH cut it to the first word each step). Drop those, and
        // de-dupe the same line repeated within a few seconds so it can't stutter.
        if (t.isBlank()) return
        val low = t.lowercase()
        if (low.startsWith("status code") || low.contains("token ids") ||
            low.contains("exceeding the maximum") || low.contains("backend$") || low.contains("litertlm")) return
        val now = System.currentTimeMillis()
        if (t == lastSpoken && now - lastSpokenAt < 6000) return
        lastSpoken = t; lastSpokenAt = now
        applyVoicePrefs()
        ttsSpeaking = true
        pauseListening()
        // Safety net: never stay paused if an utterance callback is missed.
        handler.removeCallbacks(resumeListeningRunnable)
        handler.postDelayed(resumeListeningRunnable, TTS_PAUSE_SAFETY_MS)
        tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "agent")
    }

    /** Pick a real male voice when requested+available; else deepen pitch as fallback. */
    private fun applyVoicePrefs() {
        if (settings.isMaleVoice()) {
            if (!maleVoiceSearched) { maleVoice = findMaleVoice(); maleVoiceSearched = true }
            val v = maleVoice
            if (v != null) {
                try { tts.voice = v } catch (_: Exception) {}
                tts.setPitch(0.92f) // a touch deeper still, for a clearer masculine tone
            } else {
                // No identifiable male voice installed - deepen the pitch noticeably so
                // it at least reads as masculine (0.8 was too subtle to tell apart).
                tts.setPitch(0.7f)
            }
        } else {
            defaultVoice?.let { try { tts.voice = it } catch (_: Exception) {} }
            tts.setPitch(1.0f)
        }
    }

    /**
     * Best-effort male-voice finder. TTS exposes no gender field, and real engines
     * (Google, Samsung) don't put "male" in voice names - they use opaque ids like
     * `en-us-x-iom-local`. So: match an explicit "male" name first, then fall back
     * to known male id fragments for the current language. Voice names are logged
     * once so we can see what a given device actually offers.
     */
    private fun findMaleVoice(): Voice? {
        val lang = Locale.getDefault().language
        val voices = try { tts.voices } catch (_: Exception) { null } ?: return null
        val forLang = voices.filter { it.locale?.language == lang && it.name != null }
        AgentLog.log("voice", "available(${lang}): " +
            forLang.joinToString(", ") { it.name }.take(300))

        forLang.firstOrNull {
            it.name.contains("male", ignoreCase = true) &&
                !it.name.contains("female", ignoreCase = true)
        }?.let { AgentLog.log("voice", "male by name: ${it.name}"); return it }

        // Known male voice id fragments (Google TTS network/local voices, etc.).
        val maleFragments = listOf("iom", "iol", "tpc", "tpd", "-male", "_male", "#male")
        forLang.firstOrNull { v -> maleFragments.any { v.name.contains(it, ignoreCase = true) } }
            ?.let { AgentLog.log("voice", "male by id: ${it.name}"); return it }

        AgentLog.log("voice", "no male voice found; using deepened pitch")
        return null
    }

    /** Short non-verbal "I'm listening" tone - snappier than speaking "Yes?". */
    private fun playListeningCue() {
        try {
            val tg = ToneGenerator(AudioManager.STREAM_MUSIC, 70)
            tg.startTone(ToneGenerator.TONE_PROP_BEEP, 150)
            handler.postDelayed({ try { tg.release() } catch (_: Exception) {} }, 350)
        } catch (_: Exception) {}
    }

    // --- activation -------------------------------------------------------

    /** Floating-button tap when idle: capture a command without the wake word. */
    private fun onListenNow() {
        if (speechService == null) { startVoicePipeline(); return }
        if (isAgentBusy) return
        beginCapture()
    }

    private fun beginCapture() {
        // Hand the COMMAND to Android's SpeechRecognizer (far better than Vosk at free-form dictation -
        // Vosk's mishears are why normalizeHeard/wakeVariants exist). Fall back to the Vosk capture path
        // if SpeechRecognizer isn't available on this device. The wake word stays on Vosk regardless.
        if (srAvailable()) captureWithSpeechRecognizer() else beginCaptureVosk()
    }

    private fun beginCaptureVosk() {
        mode = Mode.CAPTURING
        taskFromChat = false   // a spoken command isn't a chat-initiated task
        if (!settings.isSilent()) playListeningCue()
        updateNotification("Listening… speak your command.", false)
        handler.removeCallbacks(captureTimeout)
        handler.postDelayed(captureTimeout, CAPTURE_TIMEOUT_MS)
    }

    // --- High-accuracy command capture (Android SpeechRecognizer) ----------
    // The always-on wake word stays on local Vosk (low-profile). Once it fires - or the mic button is
    // tapped - we hand the COMMAND to Android's SpeechRecognizer: on-device by default (PREFER_OFFLINE,
    // nothing leaves the phone), or the cloud recognizer if the owner opted in (more accurate, off-device)
    // via the first-run choice / Settings. Vosk and SpeechRecognizer can't share the mic, so we STOP Vosk
    // for the capture window and rebuild it after - they never hold the mic at the same time.
    private var sr: SpeechRecognizer? = null

    private fun srAvailable(): Boolean =
        try { SpeechRecognizer.isRecognitionAvailable(this) } catch (_: Exception) { false }

    private fun captureWithSpeechRecognizer() {
        mode = Mode.CAPTURING
        taskFromChat = false
        if (!settings.isSilent()) playListeningCue()
        updateNotification("Listening… speak your command.", false)
        // Free the mic from Vosk for the capture window (stop, don't pause - SR needs the mic exclusively).
        try { speechService?.stop() } catch (_: Exception) {}
        speechService = null
        // OFFLINE MODE: cloud speech needs the network — if we're offline, fall back to the on-device recognizer
        // (and Vosk) so voice still works with no connection. The owner's cloud opt-in is honored when online.
        val cloud = settings.isCloudSpeech() && DeviceStats.isOnline(this)
        val rec = try {
            if (!cloud && android.os.Build.VERSION.SDK_INT >= 33 &&
                SpeechRecognizer.isOnDeviceRecognitionAvailable(this))
                SpeechRecognizer.createOnDeviceSpeechRecognizer(this)
            else SpeechRecognizer.createSpeechRecognizer(this)
        } catch (_: Exception) { null }
        if (rec == null) { resumeVoskListening(); beginCaptureVosk(); return }
        sr = rec
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.getDefault().toString())
            // PRIVACY: on-device mode must NEVER reach the network. Cloud mode (owner opt-in) allows it.
            putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, !cloud)
        }
        rec.setRecognitionListener(object : android.speech.RecognitionListener {
            override fun onReadyForSpeech(params: Bundle?) {}
            override fun onBeginningOfSpeech() {}
            override fun onRmsChanged(rmsdB: Float) {}
            override fun onBufferReceived(buffer: ByteArray?) {}
            override fun onEndOfSpeech() {}
            override fun onEvent(eventType: Int, params: Bundle?) {}
            override fun onPartialResults(partialResults: Bundle?) {}
            override fun onError(error: Int) { handler.post { finishSrCapture(null) } }
            override fun onResults(results: Bundle?) {
                val spoken = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    ?.firstOrNull().orEmpty()
                handler.post { finishSrCapture(spoken.ifBlank { null }) }
            }
        })
        try { rec.startListening(intent) } catch (_: Exception) { finishSrCapture(null) }
    }

    private fun finishSrCapture(spoken: String?) {
        try { sr?.destroy() } catch (_: Exception) {}
        sr = null
        resumeVoskListening()   // wake word + cancel-listening back online (this also goIdle()s)
        if (!spoken.isNullOrBlank()) {
            AgentLog.log("speech", "command via ${if (settings.isCloudSpeech()) "cloud" else "on-device"} recognizer")
            if (awaitingFollowUp) {
                awaitingFollowUp = false
                if (isNegative(spoken)) { speak("Okay.") } else runCommand(spoken)
            } else runCommand(spoken)
        }
        // No speech / error -> resumeVoskListening already returned us to idle.
    }

    /** Live-apply the Settings mic toggle: off tears the mic down NOW (onModelReady bails when the
     *  switch is off); on brings it back by rebuilding the Vosk pipeline. */
    fun applyMicSetting() { handler.post { resumeVoskListening() } }

    /** Rebuild the Vosk recognizer+mic after a SpeechRecognizer capture window (the model stays loaded,
     *  so this is cheap). onModelReady() ends in goIdle(), so a no-result capture lands back at idle. */
    private fun resumeVoskListening() {
        val m = model
        if (m != null) onModelReady(m) else startVoicePipeline()
    }

    private fun goIdle() {
        // Clear a stale conversation flag: if an ACTION_CONVERSATION set pendingContinuous but capture timed out,
        // returning to idle must not leak continuous
        // (never-auto-stop) mode onto the NEXT unrelated command. The legit path consumes it at task start, never here.
        pendingContinuous = false
        handler.removeCallbacks(captureTimeout)
        handler.removeCallbacks(answerTimeout)
        awaitingAnswer = false
        awaitingFollowUp = false
        inputOverlay.dismiss()
        if (isAgentBusy) { mode = Mode.BUSY; return }
        // We're truly idle now, so this command is done: clear the chat-origin flag so it can't
        // leak onto the NEXT task (a deterministic chat command used to leave it set, which made a
        // later non-chat task wrongly post a summary + jump to the chat). The orchestrated path
        // already consumed it in onComplete before reaching here.
        taskFromChat = false
        mode = Mode.IDLE
        updateNotification("Listening for “${settings.getTriggerWord()}” — or tap the mic.", false)
        // The task is genuinely over -> arm the idle release so RAM goes light. A quick follow-up
        // within the grace window still reuses the warm model; a real emergency frees it via onTrimMemory.
        handler.removeCallbacks(idleRelease)
        handler.postDelayed(idleRelease, IDLE_RELEASE_MS)
    }

    /**
     * The agent asked a clarifying question. Speak it, then listen for the spoken
     * answer - the whole next utterance is taken as the answer (no wake word
     * needed). The orchestrator stays paused until provideAnswer is called, here
     * on the answer or, if none comes, on a timeout that stops the task.
     */
    private fun askUser(question: String) {
        if (!isAgentBusy) return
        awaitingAnswer = true
        mode = Mode.BUSY
        AgentLog.log("ask", question)
        updateNotification("Asked: $question", false)
        speak(question)
        // Owner: clarifying questions (especially data-task parameters - age/sex/criteria) should offer
        // an on-screen TEXT FIELD, not just voice. Show a typed-answer popup over the task; voice still
        // works too, and whichever answers first wins.
        inputOverlay.show(this, question,
            onSubmit = { typed -> deliverAnswer(typed) },
            onCancel = { /* keep waiting - voice and the timeout are still active */ })
        handler.removeCallbacks(answerTimeout)
        handler.postDelayed(answerTimeout, ANSWER_TIMEOUT_MS)
    }

    /** Hand a TYPED answer (from the input popup) back to the paused task - the same path the spoken
     *  answer takes. Guarded so a late tap can't double-answer once voice already replied. */
    private fun deliverAnswer(text: String) {
        if (!awaitingAnswer) return
        awaitingAnswer = false
        handler.removeCallbacks(answerTimeout)
        inputOverlay.dismiss()
        AgentLog.log("cmd", "typed answer: ${text.take(80)}")
        orchestrator.provideAnswer(text)
        updateNotification("Working on: $lastObjective", false)
    }

    /** Compose the return-to-chat SUMMARY: what happened, anything the agent CREATED (files it
     *  saved, logins it recorded), and - if it didn't finish - an explicit offer to resume (the
     *  owner must say yes; we never silently re-attempt). Grounded in real outcome data only. */
    private fun buildChatOutcome(success: Boolean, doneSay: String?): String {
        val artifacts = ActionAccessibilityService.instance?.createdArtifacts?.toList().orEmpty()
        val created = if (artifacts.isEmpty()) "" else
            "\n\nHere's what I saved for you:\n" + artifacts.joinToString("\n") { "• $it" }
        return if (success) {
            val tail = doneSay?.trim()?.takeIf { it.isNotBlank() }?.let { " — $it" } ?: "."
            "Done$tail$created\n\nWhat next?"
        } else {
            val task = lastUnfinishedTask.take(80)
            val far = orchestrator.lastProgress().takeIf { it.isNotBlank() }
                ?.let { "\n\nHow far I got: ${it.take(200)}" } ?: ""
            if (orchestrator.lastRunStoppedByOwner()) {
                // The owner stopped it - frame it as that (not a give-up), so it reads honestly.
                "You stopped me on \"$task\".$far$created\n\nWant me to pick it back up? Say " +
                    "\"yes\" or \"continue\" to resume — or just tell me what to do instead."
            } else {
                // Stage 4 (refuse-with-remedy): tell the owner WHY and WHAT TO DO, not just how far - for the
                // give-up classes the agent can't fix itself (a permission, a device state, a missing app).
                val fix = orchestrator.lastRunRecommendedFix().takeIf { it.isNotBlank() }
                    ?.let { "\n\nWhat would help: ${it.take(240)}" } ?: ""
                "I stopped before finishing \"$task\".$far$fix$created\n\nWant me to pick it back up? Say " +
                    "\"yes\" or \"continue\" to resume — or just tell me what to do instead."
            }
        }
    }

    /** A short "yes / continue / resume" answer to the resume offer (≤4 words so a real new command
     *  is never mistaken for one). Only matters right after an unfinished task. */
    private fun isResumeAffirmation(text: String): Boolean {
        val l = text.lowercase().trim().trim('.', '!', ',', ' ')
        if (l.isBlank() || l.split(Regex("\\s+")).size > 4) return false
        return l in setOf(
            "yes", "yeah", "yep", "yup", "sure", "ok", "okay", "please", "please do", "yes please",
            "do it", "go ahead", "go for it", "continue", "continue it", "resume", "resume it",
            "keep going", "finish it", "finish that", "pick it back up", "pick it up", "carry on",
            "go on", "yes continue", "yes resume")
    }

    /** Announce completion and listen for a follow-up command (or "no"). */
    private fun completeAndOfferMore(doneSay: String?) {
        val base = doneSay?.trim().takeUnless { it.isNullOrBlank() } ?: "Task complete"
        awaitingFollowUp = true
        mode = Mode.CAPTURING
        handler.removeCallbacks(captureTimeout)
        handler.postDelayed(captureTimeout, CAPTURE_TIMEOUT_MS)
        updateNotification("Done — anything else?", false)
        speak("$base. Anything else?")
    }

    private fun isNegative(text: String): Boolean {
        val l = text.lowercase().trim().trim('.', '!', ' ')
        return l in setOf(
            "no", "nope", "nah", "no thanks", "no thank you", "nothing", "that's all",
            "thats all", "that is all", "i'm good", "im good", "we're good", "all good",
            "no that's all", "that'll be all", "im done", "i'm done"
        )
    }

    private fun acquireWakeLock() {
        handler.removeCallbacks(idleRelease)   // a task is starting - never let the idle release fire now
        // Cover the FULL task cap (MAX_RUNTIME_MS = 20 min): a 10-min lease lapsed mid-task with keep_awake OFF,
        // letting the CPU suspend the loop. keepAwakeTick re-leases while keep_awake is ON; this covers the OFF case.
        try { if (!wakeLock.isHeld) wakeLock.acquire(21 * 60 * 1000L) } catch (_: Exception) {}
    }

    private fun releaseWakeLock(force: Boolean = false) {
        // NEVER-SLEEP: while keep_awake is on (and the agent is enabled + not at the safety floor), the wake lock is
        // held CONTINUOUSLY by the keep-awake tick — so a task-end / stop release is a no-op and the device stays
        // awake into idle. `force` (shutdown / swipe-away / safety yield) always releases.
        if (!force && settings.isKeepAwakeEnabled() && settings.isAgentEnabled() && deviceSafetyReason() == null) return
        try { if (wakeLock.isHeld) wakeLock.release() } catch (_: Exception) {}
    }

    // ── NEVER-SLEEP keep-awake ───────────────────────────────────────────────────────────────────────────────
    /** Re-lease the wake lock + hold the STOP overlay's FLAG_KEEP_SCREEN_ON while keep_awake + enabled + safe, so the
     *  screen never turns off and the device never suspends. YIELDS at the hard device-safety floor (critical battery
     *  / thermal emergency): a dead phone is a more-asleep device, so releasing there protects the goal for the common
     *  plugged-in case. The §8 idle MODEL release is independent (gated on isAgentBusy) so RAM still frees when idle. */
    private val keepAwakeTick = object : Runnable {
        override fun run() {
            if (!settings.isKeepAwakeEnabled() || !settings.isAgentEnabled()) { stopKeepAwake(); return }
            val reason = deviceSafetyReason()
            if (reason == null) {
                ensureFloatingButton()                       // the overlay carries FLAG_KEEP_SCREEN_ON
                FloatingButtonService.keepScreenOn(true)
                try { wakeLock.acquire(KEEP_AWAKE_LEASE_MS) } catch (_: Exception) {}
            } else {
                FloatingButtonService.keepScreenOn(false)
                releaseWakeLock(force = true)
                AgentLog.log("awake", "yielding keep-awake at the safety floor ($reason)")
            }
            handler.postDelayed(this, KEEP_AWAKE_TICK_MS)
        }
    }

    private fun startKeepAwake() {
        if (!settings.isKeepAwakeEnabled() || !settings.isAgentEnabled()) return
        // STATE-CHANGE GUARD (fix: startKeepAwake ran on EVERY onStartCommand, re-posting the tick + re-acquiring the
        // wakelock + logging "armed" each time → ~30 duplicate [awake] lines in a real log and needless churn). Arm
        // ONCE; the 45s tick already keeps the lease + screen fresh. A safety yield keeps the tick running (still
        // armed); only stopKeepAwake() disarms, so a later start re-arms cleanly.
        if (keepAwakeArmed) return
        keepAwakeArmed = true
        handler.removeCallbacks(keepAwakeTick)
        handler.post(keepAwakeTick)
        AgentLog.log("awake", "keep-awake armed — screen stays on, the device won't sleep (yields at the battery/thermal floor)")
    }

    private fun stopKeepAwake() {
        keepAwakeArmed = false
        handler.removeCallbacks(keepAwakeTick)
        FloatingButtonService.keepScreenOn(false)
        releaseWakeLock(force = true)
    }

    /** Re-arm or tear down keep-awake after the owner toggles the setting (called from Settings). */
    fun refreshKeepAwake() { if (settings.isKeepAwakeEnabled()) startKeepAwake() else stopKeepAwake() }

    /** Reason to refuse/abort a task for device safety (low battery / overheating), or null. */
    private fun deviceSafetyReason(): String? {
        val pct = DeviceStats.batteryPercent(applicationContext)
        // More headroom when UNPLUGGED (a near-dead battery drains fast under GPU inference and can
        // die mid-task); an absolute floor even while charging.
        val charging = DeviceStats.isCharging(applicationContext)
        val floor = if (charging) CRITICAL_BATTERY else LOW_BATTERY_FLOOR
        if (pct in 0..floor)
            return "Battery is at $pct percent" + (if (charging) "" else " and not charging") +
                ", so I won't run a task right now — plug in and try again."
        // Heat cutoff is user-configurable (Settings → Heat protection). Default is
        // "minimal": only stop when the phone is critically hot enough to risk damage.
        if (DeviceStats.thermalStatus(applicationContext) >= settings.getThermalCutoff())
            return "Your phone is getting too hot, so I'm stopping to let it cool down."
        return null
    }

    // --- Vosk RecognitionListener ----------------------------------------

    override fun onPartialResult(hypothesis: String?) {
        if (ttsSpeaking) return
        val partial = jsonField(hypothesis, "partial")
        if (partial.isBlank()) return
        handler.post { if (mode == Mode.BUSY && containsCancel(partial)) stopCurrentTask() }
    }

    override fun onResult(hypothesis: String?) {
        val text = jsonField(hypothesis, "text")
        if (text.isBlank() || ttsSpeaking) return
        handler.post { handleUtterance(text) }
    }

    override fun onFinalResult(hypothesis: String?) {}
    override fun onError(e: Exception?) {}
    override fun onTimeout() {}

    private fun handleUtterance(text: String) {
        when (mode) {
            Mode.BUSY -> {
                if (awaitingAnswer) {
                    awaitingAnswer = false
                    handler.removeCallbacks(answerTimeout)
                    inputOverlay.dismiss()   // a spoken answer closes the typed-answer popup
                    if (containsCancel(text) && text.split(" ").size <= 2) {
                        stopCurrentTask()
                    } else {
                        AgentLog.log("cmd", "answer: $text")
                        orchestrator.provideAnswer(text)
                        updateNotification("Working on: $lastObjective", false)
                    }
                    return
                }
                val after = afterWake(text)
                if (after != null) {
                    when {
                        after.isBlank() -> {}
                        containsCancel(after) && after.split(" ").size <= 3 -> stopCurrentTask()
                        else -> orchestrator.addCorrection(after)
                    }
                } else if (containsCancel(text)) stopCurrentTask()
                else maybeLogReaction(text)
            }
            Mode.CAPTURING -> {
                if (awaitingFollowUp) {
                    awaitingFollowUp = false
                    if (isNegative(text)) { speak("Okay."); goIdle() } else runCommand(text)
                } else runCommand(text)
            }
            Mode.IDLE -> {
                val after = afterWake(text)
                if (after != null) {
                    // ALWAYS play the indicator beep on wake (the owner's "that noise isn't playing"
                    // bug): it only fired in beginCapture (the "hey agent" ALONE path), so saying
                    // "hey agent do X" in one breath skipped it. beginCapture plays its own, so only
                    // beep here on the spoken-command path to avoid a double beep.
                    if (after.isNotBlank()) {
                        if (!settings.isSilent()) playListeningCue()
                        runCommand(after)
                    } else beginCapture()
                }
            }
            Mode.LOADING -> {}
        }
    }

    // Vosk mis-transcribes "hey agent" ("hey age", "hey aging", "hey a gent"...), so an EXACT match
    // almost never fired. We accept the common mishears - but EVERY variant must include a deliberate
    // address prefix ("hey"/"ok"/"okay"/"hay"). The bare word "agent" (and "a agent") were REMOVED:
    // they fired on any incidental mention, so the owner "couldn't even say his name around him"
    // (the wake word must be an address, not a topic word). A custom trigger is matched exactly.
    private val wakeVariants = listOf(
        "hey agent", "hey agents", "hay agent", "hey a gent", "hey a agent", "hey aging",
        "hey age and", "hey age", "ok agent", "okay agent", "okay agents", "ok agents")

    /** The command spoken AFTER the wake word, "" if the wake word was said with no command, or
     *  null if no wake word was heard. Fuzzy on the default "hey agent" so mishears still trigger. */
    private fun afterWake(text: String): String? {
        val l = text.lowercase()
        val trigger = settings.getTriggerWord().lowercase().trim()
        l.indexOf(trigger).let { if (it >= 0) return text.substring(it + trigger.length).trim(' ', ',', '.', ':', ';') }
        if (trigger == "hey agent") for (v in wakeVariants) {
            val i = l.indexOf(v)
            if (i >= 0) return text.substring(i + v.length).trim(' ', ',', '.', ':', ';')
        }
        return null
    }

    private fun jsonField(hypothesis: String?, key: String): String {
        if (hypothesis.isNullOrBlank()) return ""
        return try { JSONObject(hypothesis).optString(key).trim() } catch (_: Exception) { "" }
    }

    // The shouted-stop matcher. §3: this must NEVER drop the owner's real "stop" - but the always-on kill
    // switches (floating STOP, notification Stop, AgentControl.emergencyStop) do NOT route through here, and
    // the BUSY path runs this on every GROWING Vosk partial, so a real shout emits partial "stop" (1 word,
    // bare) and fires INSTANTLY. That lets us kill the FALSE positives the old substring test caused: it
    // fired on "un-STOP-pable"/"STOP-watch" (substring) and on any conversational sentence containing the
    // word (the owner's "kept killing live tasks while demoing" bug). Now: fire only on a BARE utterance
    // (essentially the stop word itself - the shout + every partial's leading token) or an ADDRESSED one
    // ("agent, stop" / "stop the task"). A long sentence that merely mentions the word no longer trips it;
    // the real bare/partial shout still does. Narrows false stops; never the real kill.
    private fun containsCancel(text: String): Boolean {
        val l = text.lowercase().trim()
        val words = l.split(Regex("\\s+")).filter { it.isNotBlank() }
        if (words.size <= 2 && words.any { it.trim('.', ',', '!', '?') in cancelWords }) return true
        if (Regex("\\bagent[,.]?\\s+(please\\s+)?(stop|cancel|abort|halt)\\b").containsMatchIn(l)) return true
        if (Regex("\\b(stop|cancel|abort|halt)\\s+(the\\s+)?(task|agent)\\b").containsMatchIn(l)) return true
        return false
    }

    // Owner's affective feedback heard DURING a task (not a command/correction): specific enough
    // phrases that ambient chatter rarely trips them.
    private val frustrationWords = listOf("that's wrong", "thats wrong", "not that", "why are you",
        "what are you doing", "stop doing that", "don't do that", "dont do that", "you messed",
        "messed up", "that's not right", "thats not right", "come on agent", "ugh agent", "no no no")
    private val praiseWords = listOf("good job", "well done", "nice job", "great job", "perfect",
        "that's perfect", "thats perfect", "good agent", "nicely done", "good boy", "that's right agent")

    /** The owner reacted DURING a task (it wasn't a wake command or a cancel). Log the reaction tied to
     *  what the agent just did - the owner's "log my reaction" / praise. Conservative (specific phrases)
     *  and NON-disruptive: it never alters the running task, only records the signal for review/learning. */
    private fun maybeLogReaction(text: String) {
        val l = text.lowercase()
        val frustrated = frustrationWords.any { l.contains(it) }
        val pleased = praiseWords.any { l.contains(it) }
        val during = if (::orchestrator.isInitialized) orchestrator.lastAction() else "a task"
        when {
            frustrated -> AgentLog.log("react", "owner sounded FRUSTRATED: \"$text\" — just after: $during")
            pleased -> AgentLog.log("react", "owner PLEASED: \"$text\" — just after: $during")
        }
    }

    private fun isCapabilityQuery(command: String): Boolean {
        val l = command.lowercase()
        return l.contains("what can you do") || l.contains("what can i ask") ||
            l.contains("what can i say") || l.contains("what do you do") ||
            l == "help" || l == "help me"
    }

    /** The agent reflects on its recent run and writes a dev-change request to the log. */
    private fun isSelfReportQuery(command: String): Boolean {
        val l = command.lowercase()
        return l.contains("what do you need") || l.contains("what should i change") ||
            l.contains("dev report") || l.contains("self report") ||
            l.contains("what would help you") || l.contains("report what you need") ||
            l.contains("what's wrong with your code") || l.contains("whats wrong with your code")
    }

    private fun announceCapabilities() {
        AgentLog.log("cmd", "capabilities query")
        speak(
            "Say hey agent then a task. I can open apps, search the web, change " +
            "settings, type and send messages, and work through multi-step tasks. " +
            "Say stop any time."
        )
        goIdle()
    }

    /**
     * Deterministic shortcuts for the most common commands - reliable and instant,
     * bypassing the weak on-device model. Returns true if it handled the command.
     */
    private fun tryDeterministic(command: String): Boolean {
        // Memory: "remember (that) my <key> is <value>" and "what is my <key>".
        Regex("""remember(?:\s+that)?\s+(?:my\s+)?(.+?)\s+(?:is|are|=)\s+(.+)""", RegexOption.IGNORE_CASE)
            .find(command)?.let {
                val k = it.groupValues[1].trim(); val v = it.groupValues[2].trim().trimEnd('.', '!')
                if (k.isNotBlank() && v.isNotBlank()) {
                    AgentMemory.setFact(applicationContext, k, v)
                    AgentLog.log("mem", "remember $k = $v"); speak("Got it, I'll remember that."); return true
                }
            }
        Regex("""^what(?:'s| is)\s+my\s+(.+)""", RegexOption.IGNORE_CASE).find(command)?.let {
            val k = it.groupValues[1].trim().trimEnd('?', '.')
            AgentMemory.getFact(applicationContext, k)?.let { v -> speak("Your $k is $v."); return true }
        }
        if (Regex("""favou?rite song""", RegexOption.IGNORE_CASE).containsMatchIn(command)) {
            try {
                val am = getSystemService(AUDIO_SERVICE) as AudioManager
                am.setStreamVolume(AudioManager.STREAM_MUSIC, am.getStreamMaxVolume(AudioManager.STREAM_MUSIC), 0)
            } catch (_: Exception) {}
            openUri("https://www.youtube.com/results?search_query=" + Uri.encode("Special Place Bladee"))
            AgentLog.log("det", "favorite song"); return true
        }
        Regex("""^(?:search(?: the web| online| google)? for|google|look up|search)\s+(.+)""", RegexOption.IGNORE_CASE)
            .find(command)?.let {
                val q = it.groupValues[1].trim().trim('.', '?', '!')
                if (q.isNotBlank()) {
                    webSearch(q)
                    AgentLog.log("det", "web search: $q")
                    speak("Searching for $q.")
                    updateNotification("Searched the web: $q", false)
                    return true
                }
            }
        Regex("""^(?:open|launch|start)\s+(?:the\s+)?(.+?)(?:\s+app)?$""", RegexOption.IGNORE_CASE)
            .find(command)?.let {
                val name = it.groupValues[1].trim()
                if (name.isNotBlank() && !name.contains(" and ") && !name.contains(" then ") && launchApp(name)) {
                    AgentLog.log("det", "open app: $name")
                    speak("Opening $name.")
                    updateNotification("Opened $name", false)
                    return true
                }
            }
        Regex("""^(?:navigate to|directions to|take me to|maps? (?:to|of))\s+(.+)""", RegexOption.IGNORE_CASE)
            .find(command)?.let {
                val place = it.groupValues[1].trim().trim('.', '?', '!')
                if (place.isNotBlank()) {
                    openUri("geo:0,0?q=" + Uri.encode(place))
                    AgentLog.log("det", "maps: $place")
                    speak("Opening directions to $place.")
                    updateNotification("Maps: $place", false)
                    return true
                }
            }
        Regex("""^play\s+(.+?)\s+on\s+you\s?tube""", RegexOption.IGNORE_CASE)
            .find(command)?.let {
                val q = it.groupValues[1].trim()
                if (q.isNotBlank()) {
                    openUri("https://www.youtube.com/results?search_query=" + Uri.encode(q))
                    AgentLog.log("det", "youtube: $q")
                    speak("Searching YouTube for $q.")
                    updateNotification("YouTube: $q", false)
                    return true
                }
            }
        Regex("""(?:set|start)\s+(?:a\s+)?timer\s+(?:for\s+)?(\d+)\s*(sec|second|seconds|min|minute|minutes|hour|hours|hr)""", RegexOption.IGNORE_CASE)
            .find(command)?.let {
                val n = it.groupValues[1].toIntOrNull()
                if (n != null) {
                    val u = it.groupValues[2].lowercase()
                    val secs = when { u.startsWith("sec") -> n; u.startsWith("hour") || u == "hr" -> n * 3600; else -> n * 60 }
                    try {
                        startActivity(Intent(android.provider.AlarmClock.ACTION_SET_TIMER)
                            .putExtra(android.provider.AlarmClock.EXTRA_LENGTH, secs)
                            .putExtra(android.provider.AlarmClock.EXTRA_SKIP_UI, true)
                            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                        AgentLog.log("det", "timer ${secs}s"); speak("Timer set."); updateNotification("Timer set", false)
                        return true
                    } catch (_: Exception) {}
                }
            }
        Regex("""(?:call|dial)\s+([0-9][0-9\s\-()+]{4,})""", RegexOption.IGNORE_CASE)
            .find(command)?.let {
                val num = it.groupValues[1].filter { c -> c.isDigit() || c == '+' }
                if (num.length >= 4) {
                    // Open the dialer pre-filled (does NOT auto-place the call - safer).
                    openUri("tel:$num")
                    AgentLog.log("det", "dial $num"); speak("Opening the dialer."); updateNotification("Dial $num", false)
                    return true
                }
            }
        return false
    }

    private fun openUri(uri: String) {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(uri)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        } catch (_: Exception) {}
    }

    private fun webSearch(query: String) {
        val attempts = listOf(
            Intent(Intent.ACTION_WEB_SEARCH).apply { putExtra(SearchManager.QUERY, query) },
            Intent(Intent.ACTION_VIEW, Uri.parse("https://www.google.com/search?q=" + Uri.encode(query)))
        )
        for (i in attempts) {
            try { startActivity(i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)); return } catch (_: Exception) {}
        }
    }

    private fun launchApp(name: String): Boolean {
        val pm = packageManager
        // "Gemini" must be the standalone Gemini app, not the Assistant voice overlay.
        if (name.trim().lowercase() == "gemini")
            pm.getLaunchIntentForPackage("com.google.android.apps.bard")?.let {
                startActivity(it.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)); return true
            }
        val main = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        val cands = pm.queryIntentActivities(main, 0)
        val t = name.trim().lowercase()
        val labeled = cands.map { it to it.loadLabel(pm).toString() }
        val m = labeled.firstOrNull { it.second.lowercase() == t }
            ?: labeled.firstOrNull { it.second.lowercase().startsWith(t) }
            ?: labeled.firstOrNull { it.second.contains(name, ignoreCase = true) }
            ?: return false
        val launch = pm.getLaunchIntentForPackage(m.first.activityInfo.packageName) ?: return false
        startActivity(launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        return true
    }

    // --- commands ---------------------------------------------------------

    /** "Learn mode": the agent autonomously EXPLORES apps (safely) to build navigation memory so
     *  later tasks are faster/smarter. Routed through the normal command path so every safety gate
     *  applies (payment/install confirm, risky-actions-off, self-interaction-off); the word "explore"
     *  in the objective puts it in EXPLORER mode. Bounded to a handful of apps, and the owner can stop
     *  it anytime with the floating button. */
    private fun startLearnMode() {
        if (isAgentBusy) { speak("I'm already working on something - stop that first, then start Learn mode."); return }
        speak("Setting myself little practice goals to learn your apps. Tap the floating button to stop me.")
        runCommand(
            "LEARN MODE: teach YOURSELF to use this phone by setting your OWN simple, harmless, ONE-STEP " +
            "goals and completing them - do NOT just wander aimlessly. For each of about 5 DIFFERENT apps: " +
            "open it, then pick ONE concrete thing to LOCATE (e.g. 'where do I compose/create a new item?', " +
            "'where is search?', 'where are the settings?', 'how do I go back/switch tabs?'), and navigate " +
            "until you actually SEE it. When you find it, RECORD what you learned with a {\"action\":\"note\"} " +
            "in TWO forms: the SPECIFIC fact ('in <app>, compose is the + button bottom-right') AND the " +
            "GENERAL pattern it teaches ('compose is usually a + button bottom-right'). Then press home and " +
            "open a DIFFERENT app and set yourself a NEW little goal. This must be completely HARMLESS - ONLY " +
            "open, look, scroll, navigate, and press back/home. Do NOT type into fields, send, post, buy, " +
            "install, uninstall, log in or out, delete or move anything, close or force-stop apps, clear " +
            "data, or change ANY setting. If a screen asks you to confirm or permit something, just go back. " +
            "After about 5 apps with a goal met in each, finish."
        )
    }

    private fun runCommand(commandRaw: String) {
        // SELF-EVOLVE guard: if the model file is mid-edit, defer this command a moment — a task must never start
        // an inference while the weights are being rewritten (a loaded .litertlm is mmap'd). The edit is brief.
        if (evolving) { handler.postDelayed({ runCommand(commandRaw) }, 1500); return }
        // Resume gate (ask-before-resume): if a task was left unfinished we ALREADY asked whether to
        // pick it back up. Only an explicit "yes / continue" now resumes it; any other command means
        // the owner moved on, so we drop the pending resume and run what they actually said.
        val pendingResume = lastUnfinishedTask
        val effectiveRaw = if (pendingResume.isBlank()) commandRaw else {
            lastUnfinishedTask = ""
            if (isResumeAffirmation(commandRaw)) {
                AgentLog.log("cmd", "owner OK'd resuming the unfinished task")
                speak("Okay, picking that back up.")
                pendingResume
            } else commandRaw
        }
        // Vosk mis-transcribes common terms badly ("chat gp t", "why fi"); fix the
        // worst offenders deterministically before anything downstream uses the text.
        val command = normalizeHeard(effectiveRaw)
        // Consume the conversation-mode flag now, on every path, so it can't leak to a later
        // command if this one is handled deterministically or cancelled.
        val cont = pendingContinuous; pendingContinuous = false
        val trimmed = command.trim()
        // Only a bare "stop"/"cancel" cancels here - a real prompt may legitimately
        // contain the word (e.g. "don't stop until I say so") and must still run.
        if (trimmed.split(" ").size == 1 && containsCancel(trimmed)) { stopCurrentTask(); return }
        if (isCapabilityQuery(trimmed)) { announceCapabilities(); return }
        if (isSelfReportQuery(trimmed)) {
            AgentLog.log("cmd", command)
            speak("Okay, writing what I need into the debug log.")
            orchestrator.writeSelfReport { speak("Done. It's in the debug log for you to share.") }
            goIdle(); return
        }
        AgentLog.log("cmd", command)
        AgentLog.log("diag", "start :: ${DeviceStats.snapshot(applicationContext)}")
        deviceSafetyReason()?.let { reason ->
            AgentLog.log("safety", "refused at start: $reason")
            speak(reason); goIdle(); return
        }
        // Handle simple, unambiguous single-intent commands (timer, web search, open
        // app, directions, dial) deterministically and INSTANTLY - far more reliable
        // than letting the weak model fumble. Multi-step requests fall through to it.
        if (tryDeterministic(command)) {
            AgentLog.log("diag", "end :: ${DeviceStats.snapshot(applicationContext)}")
            if (lastObjective.isBlank()) lastObjective = command
            TaskHistory.add(applicationContext, command, "finished", gauntlet = GauntletRunner.isRunning())
            // A gauntlet task handled deterministically still ends the task - advance the run, or it
            // would stall on this one until the watchdog fires.
            GauntletRunner.onTaskEnded(applicationContext, command, true)
            // If this was launched from chat, resolve the "Thinking…" placeholder there instead of
            // leaving it hanging (the deterministic path skips the orchestrator's chat summary).
            if (taskFromChat) ChatStore.add(applicationContext, "agent", "Done — handled that. What next?")
            goIdle(); return
        }
        lastObjective = command
        // Learn mode is harmless-only: tell the executor to HARD-BLOCK anything destructive for the
        // duration of this task (cleared again in goIdle). False for every normal task.
        awaitingAnswer = false
        awaitingFollowUp = false
        isAgentBusy = true
        lastStatusSpoken = ""   // fresh verbal status cues for this run
        mode = Mode.BUSY
        // Fresh artifact ledger for THIS task, so the end-of-task chat summary lists only what this
        // run created (files saved, logins recorded).
        ActionAccessibilityService.instance?.createdArtifacts?.clear()
        ActionAccessibilityService.instance?.clearCollected()   // fresh captured-data buffer per task
        // Start loading the model NOW so its cold-start (load + first inference) overlaps with
        // launching the app and reading the first screen, instead of stalling the first "thinking"
        // step. Same model, just warmed sooner - no effect on output quality.
        if (::brain.isInitialized) brain.prewarm()
        acquireWakeLock()
        ensureFloatingButton()   // the overlay is the user's STOP control - keep it up the whole task
        handler.removeCallbacks(captureTimeout)
        // A fuller acknowledgement (vs a clipped "On it.") so the user feels heard.
        speak("Okay, got it — working on that now.")
        updateNotification("Working on: $command", false)
        // Tell the chat we're loading so it doesn't look like a dead home screen during the ~20s
        // model spin-up (the user watches the chat, not a notification).
        if (taskFromChat)
            ChatStore.add(applicationContext, "agent", "Thinking… — reading your screen and planning. Tap the floating button anytime to stop.")
        // Resolve (but HOLD) the app this command implies. The orchestrator opens it once the model
        // is READY (after planning), so the user stays on the chat/loading screen during spin-up
        // instead of being dropped into a half-loaded app. Home logic: only leave our OWN UI when
        // there is NOTHING to preload - if we have a preload app it'll open over us when ready, so a
        // Home press would just be an extra flash.
        // Open the task's FIRST app deterministically even in human-navigation mode (owner: "if it's
        // just going to open_app anyway, don't waste a 13s step reading the home screen - it didn't even
        // manually tap the icon"). Human nav still governs the REST of the task (in-app navigation);
        // this only skips the pointless home-screen read to launch the initial app. Learn mode names no
        // specific app, so resolvePreloadApp returns null there and navigation practice is preserved.
        val preloadName = resolvePreloadApp(command)
        if (preloadName == null && ActionAccessibilityService.instance?.currentPackage() == packageName) {
            ActionAccessibilityService.instance?.performActionJson("{\"action\":\"home\"}")
        }
        orchestrator.start(command, isContinuousCommand(command) || cont, preloadName, resumeRequested = taskResumeRequested)
        taskResumeRequested = false   // consume it - only THIS run's explicit Resume tap restores context
    }

    // --- teach-by-demonstration (floating Train flow) ---------------------

    /** Start recording the owner's demonstration right where they are, so they can go do the
     *  task without first navigating to a Train screen (which would pollute the captured steps). */
    private fun startTraining(goal: String) {
        val acc = ActionAccessibilityService.instance
        if (acc == null) { speak("Turn on the accessibility service first."); return }
        if (isAgentBusy) { speak("Finish the current task first."); return }
        trainingGoal = goal.trim()
        acc.startDemonstration()
        AgentLog.log("train", "recording demo: ${trainingGoal.ifBlank { "(unspecified)" }}")
        speak(if (trainingGoal.isBlank()) "Recording. Show me, then tap the button to finish."
              else "Recording how to $trainingGoal. Show me, then tap the button to finish.")
    }

    /** Stop recording and learn a generalized skill from what the owner showed. */
    private fun finishTraining() {
        val acc = ActionAccessibilityService.instance ?: return
        if (!acc.recording) return
        val steps = acc.stopDemonstration()
        val goal = trainingGoal; trainingGoal = ""
        if (steps.isEmpty()) { speak("I didn't catch any steps that time."); return }
        val b = brainOrNull()
        if (b == null) {
            AgentMemory.addSkill(applicationContext, goal.ifBlank { "a task you showed me" }, "",
                steps.joinToString("\n") { "- $it" }, "shown")
            speak("Saved your steps."); return
        }
        speak("Got it — learning from what you showed me.")
        b.generalizeDemonstration(goal, steps) { out ->
            val name = if (out.isBlank()) null
                else AgentMemory.addSkillFromModel(applicationContext, out, "shown",
                    goal.ifBlank { "a task you showed me" }, raw = steps.joinToString("\n") { "- $it" })
            if (name != null) {
                AgentMemory.removeUnknownAction(applicationContext, goal)
                handler.post { speak("Learned how to $name.") }
            } else {
                AgentMemory.addSkill(applicationContext, goal.ifBlank { "a task you showed me" }, "",
                    steps.joinToString("\n") { "- $it" }, "shown")
                handler.post { speak("Saved your steps.") }
            }
        }
    }

    /** Resolve (do NOT launch) the app a command implies, so the model can start INSIDE it. The
     *  launch is HELD by the orchestrator until the model is ready, so the user stays on the
     *  chat/loading screen during spin-up instead of staring at a half-loaded app. Returns the app
     *  NAME to open, or null if there's nothing obvious to preload (or it's blacklisted). */
    private fun resolvePreloadApp(command: String): String? {
        val l = command.lowercase()
        // Prefer the FIRST installed app (from the phone SCAN) named in the command, so we open what
        // the task needs FIRST - not an app mentioned LATER ("...then send to Gemini"). Using the
        // real installed list means we never preload a name that isn't actually here.
        val scanned = AgentMemory.deviceApps(applicationContext)
            .filter { it.length >= 3 }
            .mapNotNull { app ->
                Regex("\\b" + Regex.escape(app.lowercase()) + "\\b").find(l)?.let { app to it.range.first }
            }
            .minByOrNull { it.second }?.first
        // An EXPLICITLY named app (open/launch/use/talk to/chat with X).
        val named = Regex("""\b(?:open|launch|start|go to|use|talk to|chat with)\s+(?:the\s+)?([a-z0-9 .'&-]{2,30}?)(?:\s+(?:app|and|then|to|about|please)\b|[.,!?]|$)""")
            .find(l)?.groupValues?.get(1)?.trim()
        val name = when {
            scanned != null -> scanned
            named != null && named.isNotBlank() && named !in setOf("it", "the", "my", "a", "me") -> named
            // Gemini fallback ONLY when the scan didn't catch it (this phone hosts Gemini inside the
            // Google app, so it may not be listed as "Gemini") - and only if no earlier app was found.
            Regex("""\bgemini\b""").containsMatchIn(l) -> "Gemini"
            Regex("""\b(text|sms|imessage)\b""").containsMatchIn(l) -> "Messages"
            Regex("""\bcall\b""").containsMatchIn(l) -> "Phone"
            else -> return null
        }
        return name
    }

    /** Fix common Vosk mishears so the model/deterministic paths see the real words. */
    private fun normalizeHeard(text: String): String {
        var s = " ${text} "
        val fixes = listOf(
            "\\b(?:chat|church)\\s*g\\s*p\\w{0,4}\\b" to "chatgpt",
            "\\bchat\\s*g\\s*[bp]\\s*t\\b" to "chatgpt",
            "\\bchat\\s*gpt\\b" to "chatgpt",
            "\\byou\\s*tube\\b" to "youtube",
            "\\bjee\\s*mail\\b" to "gmail",
            "\\bg\\s*mail\\b" to "gmail",
            "\\bwhy\\s*fi\\b" to "wifi",
            "\\bwi\\s*fi\\b" to "wifi",
            "\\bwife\\s*i\\b" to "wifi",
            "\\bin\\s*sta\\s*gram\\b" to "instagram",
            "\\bwhat'?s\\s*app\\b" to "whatsapp",
            "\\bblue\\s*tooth\\b" to "bluetooth",
            "\\btik\\s*tok\\b" to "tiktok",
            "\\bsnap\\s*chat\\b" to "snapchat"
        )
        for ((re, rep) in fixes) s = Regex(re, RegexOption.IGNORE_CASE).replace(s, rep)
        return s.trim()
    }

    private fun isContinuousCommand(command: String): Boolean {
        val l = command.lowercase()
        val phrases = listOf(
            "forever", "repeatedly", "over and over", "again and again",
            "keep doing", "keep ", "continuously", "non-stop", "nonstop",
            "in a loop", "until i tell", "until you", "until i stop", "on repeat",
            // "Keep going until I tell you to stop" tasks. NOTE: this flag is only about NEVER
            // auto-stopping - it does NOT unlock chat turn-taking any more. Taking a conversational
            // turn is now the agent's own {"action":"reply"} (it decides when it's in a back-and-
            // forth), so a debate/argument needs no keyword here - the agent drives it via reply.
            // Substrings catch mishears/typos too: "continu"/"contino", "convers" (conversation).
            "continu", "contino", "convers", "back and forth", "back-and-forth", "chat with"
        ).any { l.contains(it) }
        // Explicit repetition the user asked for ("tap 30 times", "do it 50x") is a
        // deliberate instruction, NOT a malfunction - so don't let the same-screen
        // loop breaker or step cap cut it short. Obeying the owner's command IS the
        // success condition. Battery/heat failsafes still apply every step.
        val explicitCount = Regex("""\b(\d{1,4})\s*(?:x|times|more times)\b""")
            .containsMatchIn(l)
        return phrases || explicitCount
    }

    /** Keep the floating overlay button on screen whenever a task runs - the user relies on it as
     *  the STOP control, and a plain background service can be killed under the memory pressure of
     *  loading the model (or simply was never started for a verbal/notification-launched task).
     *  startService is idempotent, so this just guarantees it's present. No-op without the overlay
     *  permission. */
    private fun ensureFloatingButton() {
        if (android.provider.Settings.canDrawOverlays(this)) {
            try { startService(Intent(this, FloatingButtonService::class.java)) } catch (_: Exception) {}
        }
    }

    private fun stopCurrentTask(reason: String = "Stopped.") {
        // AUTONOMOUS MODE: a STOP (floating button / notification / shouted "stop") must END THE LOOP, not just the
        // current task — otherwise the queued next self-goal would start after the owner said stop. This is the
        // kill-switch chokepoint that guarantees the loop is bounded by the owner. (Sleep/emergencyStop kill the
        // whole service.)
        stopAutoMode("owner STOP")
        // GHOST-INPUT HARDENING (07-09): a STOP must also HALT the actuator — the decision loop stops, but a gesture
        // already posted to a Handler or waiting in a GestureResultCallback kept firing after STOP (ghost inputs the
        // owner couldn't stop). haltInjection() refuses all further injection + drops queued taps.
        ActionAccessibilityService.instance?.haltInjection()
        // §3 KILL-SWITCH HARDENING (Batch 0): abort any in-flight native decode NOW so STOP is sub-second, not
        // "after the running 15-40s inference finishes". orchestrator.stop() sets running=false so the already-
        // decided action is refused, but the decode itself kept burning until it completed; cancel it directly.
        if (::brain.isInitialized) brain.cancelActiveDecode()
        orchestrator.stop()
        awaitingAnswer = false
        handler.removeCallbacks(answerTimeout)
        // Capture the plan + steps even on a STOP (these looping tasks are exactly the ones the owner
        // wants to rate per-step), so the task log entry is rateable instead of empty.
        if (isAgentBusy && lastObjective.isNotBlank())
            // This IS an owner stop (orchestrator.stop() just ran) - record it as the neutral outcome so it's
            // never replayed to the next run as a failure nor counted a success.
            run {
                val execSteps = orchestrator.lastExecutedSteps()
                val runId = TaskHistory.add(applicationContext, lastObjective, "stopped-by-owner",
                    plan = orchestrator.lastPlan(),
                    steps = execSteps.takeIf { it.isNotEmpty() }?.map { it.summary } ?: orchestrator.lastSteps(),
                    durationMs = orchestrator.lastRunDurationMs(), gauntlet = GauntletRunner.isRunning())
                // P0 grader: these looping/stopped tasks are exactly the ones the owner wants to grade per-step —
                // persist their structured steps so a ✓/✗ banks a bake reference. Best-effort.
                try {
                    if (runId > 0L && execSteps.isNotEmpty())
                        ExecStepStore.record(applicationContext, runId,
                            ModelStore.activeFingerprint(applicationContext, settings),
                            execSteps.map { ExecStepStore.Step(it.op, it.sig, it.prompt, it.action, it.clause, it.m) })
                } catch (_: Throwable) {}
            }
        // A manual stop mid-gauntlet stops the WHOLE gauntlet - never auto-restart a task the
        // owner stopped.
        GauntletRunner.stop(applicationContext, "owner stopped the agent")
        isAgentBusy = false
        releaseWakeLock()
        speak(reason)
        goIdle()
    }

    private fun updateNotification(text: String, showResume: Boolean) {
        getSystemService(NotificationManager::class.java).notify(
            NotificationHelper.SERVICE_NOTIFICATION_ID,
            NotificationHelper.buildNotification(this, text, showResume)
        )
    }

    override fun onTaskRemoved(rootIntent: Intent?) {
        // Swiping the app away halts any running task and frees the wake-lock, so it
        // can never keep draining/heating in the background unnoticed.
        stopKeepAwake()   // swiped away: stop holding the device awake (re-arms if the sticky service restarts)
        if (isAgentBusy) stopCurrentTask("Stopping — you closed the app.")
        else releaseWakeLock(force = true)
        super.onTaskRemoved(rootIntent)
    }

    override fun onDestroy() {
        isAgentBusy = false
        instance = null
        ActionAccessibilityService.instance?.haltInjection()  // Sleep/emergencyStop teardown: halt injection too
        handler.removeCallbacks(keepAwakeTick)
        releaseWakeLock(force = true)
        handler.removeCallbacksAndMessages(null)
        inputOverlay.dismiss()
        if (::orchestrator.isInitialized) orchestrator.stop()
        // §3 (Batch 0): abort an in-flight decode BEFORE brain.close() below — cancelProcess() first makes the
        // close clean (closing the engine under a running inference is exactly what crashes / what closeSafely
        // defers), and it stops ACTION_STOP/emergencyStop/Sleep teardown waiting ~40s on a running inference.
        if (::brain.isInitialized) brain.cancelActiveDecode()
        speechService?.let { try { it.stop() } catch (_: Exception) {}; it.shutdown() }
        speechService = null
        try { sr?.destroy() } catch (_: Exception) {}; sr = null
        recognizer?.close(); recognizer = null
        // E-STOP LETS THE WEIGHT WRITE FINISH (owner: "don't cut off parameter modification mid-write — let it finish;
        // we don't want half broken edits"). Input + decode are already halted above; NOW, before freeing the model
        // mmap, let any in-flight self-evolve/self-grow byte-write+fsync COMPLETE so the .litertlm is never left
        // half-written. Bounded join (write = fixed tiny bytes + one fsync => ms); if the cap elapses proceed anyway
        // (never hang the kill switch) — the brick-guard restores a backup on next load. Input halt already ran above,
        // so this can't delay stopping inputs; the engine was already closed by the beat, so brain.close() stays a no-op.
        teardownRequested = true
        evolveThread?.takeIf { it.isAlive }?.let { try { it.join(WRITE_FINISH_MAX_MS) } catch (_: InterruptedException) {} }
        model?.close(); model = null
        if (::brain.isInitialized) brain.close()
        if (::tts.isInitialized) { tts.stop(); tts.shutdown() }
        super.onDestroy()
    }

    /** The EMERGENCY unload path (the idle release frees the model when idle; THIS frees it under real
     *  pressure, including MID-TASK, which the idle release never does). For when RAM is genuinely
     *  overloaded and the phone starts glitching. Moderate pressure sheds just the helper submodel for
     *  relief and keeps the big model working; CRITICAL pressure (the OS is about to start killing
     *  background apps - the black wallpaper) frees the big model too, even mid-task, to stay stable. */
    // PUSH-THROUGH (owner): a black wallpaper that recovers is tolerable, and completion beats avoiding
    // it - so we ride out a one-off RAM close call instead of bailing. This stamps the last CRITICAL
    // trim, to tell a single spike (ride it out) from sustained pressure (genuinely about to be killed).
    @Volatile private var lastCriticalTrimAt = 0L

    override fun onTrimMemory(level: Int) {
        super.onTrimMemory(level)
        if (!::brain.isInitialized) return
        when {
            level >= TRIM_MEMORY_RUNNING_CRITICAL -> {
                // PUSH THROUGH the close call. While BUSY, do NOT free the big model on the FIRST
                // critical trim - riding it out usually recovers (the wallpaper may flash black, then
                // the phone comes back) and keeps the task ALIVE, which is what the owner wants. Only
                // free it if criticals keep coming within a few seconds (pressure is NOT easing and a
                // real force-stop is imminent - losing the whole agent is worse than a reload). When
                // IDLE there's no task to protect, so free immediately. closeSafely still defers the
                // close past any in-flight inference so we never tear the engine down mid-decision.
                val now = System.currentTimeMillis()
                val sustained = now - lastCriticalTrimAt < 8000L
                lastCriticalTrimAt = now
                val free = !isAgentBusy || sustained
                val busy = isAgentBusy
                // ANR FIX: the @Synchronized brain calls can block on the GPU-load monitor — run off the main thread.
                memReliefExec.execute {
                    brain.onMemoryPressure()        // drop the helper first - cheap, always safe
                    if (free) {
                        brain.closeSafely()
                        AgentLog.log("mem", "onTrimMemory($level) ${if (busy) "SUSTAINED pressure" else "idle"} -> freed the model")
                    } else {
                        AgentLog.log("mem", "onTrimMemory($level) -> riding out the close call (busy); kept the model to finish the task")
                    }
                }
            }
            level >= TRIM_MEMORY_RUNNING_LOW -> {
                memReliefExec.execute {
                    brain.onMemoryPressure()        // moderate: shed the helper, keep the big model cooking
                    AgentLog.log("mem", "onTrimMemory($level) -> released the helper submodel for relief")
                }
            }
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
