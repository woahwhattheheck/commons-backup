package com.local.deviceagent

import android.graphics.Typeface
import android.os.Bundle
import android.text.Editable
import android.text.InputType
import android.text.TextWatcher
import android.view.Gravity
import android.view.View
import android.widget.*
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity

/**
 * Dedicated Settings screen. Advanced / power-user options live here so the home
 * screen stays clean and approachable. Everything is backed by [SettingsManager]
 * and takes effect immediately - including for a task already running - so there
 * is no save button.
 *
 * Sections are grouped by concern (owner: "sort the settings better, don't lose a button"), most-common first:
 * Activation → Voice → Behavior → Reasoning operators → Self-improvement engine → Model self-editing →
 * Learning from you → Data & device → Help. Every toggle/button/spinner from the old flat
 * layout is preserved verbatim, just regrouped.
 */
class SettingsActivity : AppCompatActivity() {

    private lateinit var settings: SettingsManager
    private lateinit var root: LinearLayout

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        settings = SettingsManager(this)
        title = "Settings"

        val scroll = ScrollView(this)
        root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 40, 48, 64)
        }
        scroll.addView(root)
        setContentView(scroll)

        buildActivation()
        buildVoice()
        buildBehavior()
        buildOperators()
        buildEngine()
        buildModel()
        buildLearning()
        buildData()
        buildHelp()
    }

    private fun buildActivation() {
        sectionHeader("Activation")
        caption("Say this word any time, then your command.")
        val field = EditText(this).apply {
            setText(settings.getTriggerWord())
            hint = "hey agent"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
            setSingleLine(true)
            addTextChangedListener(object : TextWatcher {
                override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
                override fun onTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
                override fun afterTextChanged(s: Editable?) {
                    val w = s?.toString()?.trim().orEmpty()
                    if (w.isNotBlank()) settings.setTriggerWord(w)
                }
            })
        }
        root.addView(field)
    }

    private fun buildVoice() {
        sectionHeader("Voice")
        caption("How much the agent speaks while it works.")
        val modes = listOf("minimal", "explanation", "silent")
        val labels = listOf(
            "Minimal - brief replies",
            "Explanation - narrate reasoning",
            "Silent - no speech"
        )
        spinner(labels, modes.indexOf(settings.getVoiceMode()).coerceAtLeast(0)) { pos ->
            settings.setVoiceMode(modes[pos])
        }
        toggle("Male voice", settings.isMaleVoice()) { settings.setMaleVoice(it) }
        toggle("Microphone (wake word + voice stop)", settings.isMicEnabled()) {
            settings.setMicEnabled(it); AgentService.instance?.applyMicSetting()
        }
        caption("On by default. Turn OFF to fully close the agent's ears — no wake word, no shouted-stop — so it won't trip while you talk near the phone. The floating STOP button and notification Stop still work.")
        caption("Speech recognition for your spoken commands. On-device is private (nothing leaves the " +
            "phone); cloud is more accurate but sends the command off-device. The wake word stays on-device either way.")
        toggle("Cloud speech (more accurate, off-device)", settings.isCloudSpeech()) {
            settings.setSpeechMode(if (it) "cloud" else "ondevice"); settings.setSpeechChoiceMade(true)
        }
    }

    private fun buildBehavior() {
        sectionHeader("Behavior")
        toggle(
            "Navigate like a human (tap, don't shortcut)",
            settings.isHumanNavigation()
        ) { settings.setHumanNavigation(it) }

        toggle(
            "Double-check actions (verifier)",
            settings.isVerifierEnabled()
        ) { settings.setVerifierEnabled(it) }
        caption("Takes a fast second look at each action before doing it and fixes clear mistakes (wrong app/field, off-goal taps). More reliable, a little slower. Turn off to compare.")

        caption("Speed - how long it settles between actions.")
        val speeds = listOf("fast", "balanced", "careful")
        val speedLabels = listOf(
            "Fast - snappier, less settle time",
            "Balanced - recommended",
            "Careful - waits longer on slow screens"
        )
        spinner(speedLabels, speeds.indexOf(settings.getSpeed()).coerceAtLeast(0)) { pos ->
            settings.setSpeed(speeds[pos])
        }

        caption("Heat protection - how soon the agent stops if the phone warms up.")
        val heat = listOf("minimal", "medium", "high")
        val heatLabels = listOf(
            "Minimal - only stop if critically hot (default)",
            "Medium - stop when very hot",
            "High - stop early as it warms up"
        )
        spinner(heatLabels, heat.indexOf(settings.getHeatProtection()).coerceAtLeast(0)) { pos ->
            settings.setHeatProtection(heat[pos])
        }
        caption("Phones run warm under sustained AI work. Minimal keeps the agent going until the phone is genuinely at risk; raise it if you'd rather it cool down sooner.")

        toggle(
            "Auto-decline incoming calls",
            settings.isAutoDeclineCalls()
        ) { settings.setAutoDeclineCalls(it) }
        caption("Off by default. When on, incoming calls are rejected automatically.")

        toggle(
            "Auto-continue a killed task",
            settings.isAutoResumeEnabled()
        ) { settings.setAutoResumeEnabled(it) }
        caption("Off by default. If the phone kills the agent mid-task (an out-of-memory 'black wallpaper'), it saves its own progress note. By default it just WAITS - re-open the app and tap Resume to continue, or start something new. Turn this on to have a plain re-run of the same task automatically pick up where it left off instead of starting over.")

        toggleWithWarning(
            "Shell-input backup (Shizuku) — taps accessibility can't do",
            settings.isShellInputEnabled(),
            "Give the agent a shell-input backup?",
            "ON by default (test build). When accessibility can't deliver a tap/swipe/draw on some surface, the agent " +
                "retries it through Shizuku's shell access — a stronger 'pen' for the few screens accessibility can't " +
                "reach. It's INPUT ONLY (taps/swipes/keys), never a command shell. Needs the free Shizuku app installed " +
                "and started; until then it does nothing and accessibility handles everything, so it's safe to leave on. " +
                "Tap 'Grant' below after installing Shizuku."
        ) { on ->
            settings.setShellInputEnabled(on)
            if (on) ShellInput.requestPermissionFrom(this)
        }
        caption("Backup actuator for surfaces accessibility can't reach. Input injection only (§3 — never a command shell). Inert until Shizuku is installed + granted; watch the [shellinput] log.")
        button("Grant shell-input access (Shizuku)") {
            if (!ShellInput.providerPresent())
                Toast.makeText(this, "Install the free Shizuku app + start it, then tap this again.", Toast.LENGTH_LONG).show()
            else { ShellInput.requestPermissionFrom(this); Toast.makeText(this, "Requested Shizuku access.", Toast.LENGTH_SHORT).show() }
        }
    }

    private fun buildOperators() {
        sectionHeader("Reasoning operators")
        caption("How the agent thinks each step. On by default; the experimental A/B toggles are off — flip them on the Gauntlet and watch the [op] lines.")
        toggle(
            "Reasoning operators (choose how to think)",
            settings.isOperatorLayerEnabled()
        ) { settings.setOperatorLayerEnabled(it) }
        caption("On by default. Before each step the model gets ONE relevant thinking move (plan, explore, focus on a dense screen, doubt when reality contradicted you, pre-mortem before a risky step, …) surfaced into its prompt; it still chooses the action. Runs on the MAIN model - with NO helper submodel it's chosen deterministically from the screen state (zero extra inference), and with a helper the model selects it and can mirror/reflect. Watch the [op] lines in Debug log; turn off to compare against the baseline.")

        toggle(
            "Operator binding (formal rules)",
            settings.isOperatorBindingEnabled()
        ) { settings.setOperatorBindingEnabled(it) }
        caption("OFF by default (experimental A/B). Injects each chosen thinking move as a FORMAL rule that binds the next action, instead of a soft 'how to think' suggestion the model can ignore. Formal binding may help OR degrade this small model - A/B it on the Gauntlet (agent-driven success) before leaving it on. Prerequisite for operator stacking and folded verify below. Watch the [op] lines.")

        toggle(
            "Operator stacking (combine compatible rules)",
            settings.isOperatorStackingEnabled()
        ) { settings.setOperatorStackingEnabled(it) }
        caption("OFF by default (experimental A/B). When two thinking moves are BOTH strongly relevant and compatible, binds BOTH rules together (the intersection of what each admits) instead of just one - a success-rate bet that tighter grounding helps. Needs Operator binding on. Drops to one rule on a dense screen to keep the prompt under budget; watch [promptsize] and the Gauntlet.")

        toggle(
            "Fold the verifier into the decision",
            settings.isFoldVerifyEnabled()
        ) { settings.setFoldVerifyEnabled(it) }
        caption("OFF by default (experimental A/B). On a risky/precise step, has the model self-verify its action IN the one decision (by binding a check-rule) instead of running a separate second-opinion pass afterward - one fewer model pass per risky step. In-pass self-check may lose the independent second look; A/B it - watch the [verify] lines drop in [iat] with success held. Needs Operator binding on.")

        toggle(
            "Adaptive decode budget",
            settings.isAdaptiveDecodeEnabled()
        ) { settings.setAdaptiveDecodeEnabled(it) }
        caption("OFF by default (experimental A/B). On a screen the agent has a PROVEN route out of and isn't unsure about, caps the decode shorter (the action is short and predictable) to trim the worst-case latency tail; exploratory/stuck steps keep the full budget. Safe - the decode already stops at the first complete action. Watch decide latency in [iat] with success held.")

        toggle(
            "Mid-session posture (σ evolves between turns)",
            settings.isSessionSigmaEnabled()
        ) { settings.setSessionSigmaEnabled(it) }
        caption("OFF by default (experimental A/B). Carries an evolving one-line \"operating posture\" that accumulates as a task unfolds - what's working this session and whether it's progressing or recovering - and puts it at the front of each decision, so the agent's internal approach shifts turn to turn instead of resetting each step. It's context the model READS, never a forced move; dropped automatically on a dense screen so it can never bloat the prompt. Watch the [sigma] lines and success on the Gauntlet.")

        toggle(
            "Screen-last prompt layout (attention)",
            settings.getPromptLayout() == "recency"
        ) { settings.setPromptLayout(if (it) "recency" else "legacy") }
        caption("ON by default. Puts the live screen + reply format at the END of each step's prompt (nearest where the model decides) and the fixed identity/tools/safety at the top - the small model attends most to the start and end, so burying the element list mid-prompt costs grounding on dense screens. Pure reorder, same tokens. Turn OFF (legacy) to A/B against the old order; the layout is tagged on the [brain] Debug-log lines.")

        toggle(
            "Evidence mode (never invent a value)",
            settings.isEvidenceModeEnabled()
        ) { settings.setEvidenceModeEnabled(it) }
        caption("Off by default. When on, the agent refuses to type or record a specific value (a number, name, date, code) unless it can actually SEE it on screen or has read it this task - otherwise it reads it first (get_text/ocr/clipboard) or asks. Its own writing and drawings are never restricted. Runs a fast grounded check on the helper submodel (only active when that's enabled). The EVIDENCE thinking move is available every step regardless; this makes it standing.")
    }

    private fun buildEngine() {
        sectionHeader("Self-improvement engine")
        caption("How the agent gets better over time by tuning its own thinking (posture + operators + learned rules). On-device; nothing leaves the phone.")

        toggleWithWarning(
            "Let the agent improve its own rules",
            settings.isSelfImprovementAllowed(),
            "Let the agent improve its own rules?",
            "ON by default. The agent improves itself autonomously — it durably changes its OWN behaviour by " +
                "saving rules to memory (via LEARN) that apply to future tasks; you can review and undo them in " +
                "Memory.\n\nTurning this OFF only closes the durable LEARN-rule channel — the agent still keeps " +
                "getting better through its operators, session posture, and memory. Either way it NEVER edits the " +
                "app's compiled code."
        ) { settings.setSelfImprovementAllowed(it) }
        caption("On by default. The agent locks in rules it learned from real failures on its own; every such rule is visible and undoable in Memory.")

        toggle(
            "Calibrate at startup",
            settings.isStartupCalibrationEnabled()
        ) { settings.setStartupCalibrationEnabled(it) }
        caption("OFF by default. When on, the app calibrates to you and this device at startup: it probes the device and sets its compute to match, asks you the few things it decides it needs to serve you, and composes a starting \"operating posture\" so it boots ready for you instead of cold. This loads its operating state up front - operators do the specialising, so it costs no training. Tap Recalibrate to run it again any time.")
        button("Recalibrate now") { startActivity(android.content.Intent(this, CalibrationActivity::class.java)) }

        toggle(
            "Self-tune its own thinking moves",
            settings.isSelfCalibrateEnabled()
        ) { settings.setSelfCalibrateEnabled(it) }
        caption("OFF by default. When on, the agent tunes its OWN reasoning operators on the phone: when it's stuck it writes a sharper thinking-move for the situation, and the loop keeps the ones that both HELP and reliably do what they say (their restriction holds), while pruning the leaky ones. Operators are exact - they restrict how it thinks, they don't just nudge - so a proven, exact one it invented becomes a real new capability, and the best ones get flagged for you to bake into the model. No extra training, all on-device. Watch the [op]/[selftune] lines.")

        toggle(
            "Continuous engine (self-improve as it works)",
            settings.isContinuousEngineEnabled()
        ) { settings.setContinuousEngineEnabled(it) }
        caption("OFF by default - the master switch. Turns the two above (evolving posture + self-tuning its thinking moves) into ONE continuous loop: every turn it scores what it just did, shifts its operating posture toward what's actually PROVEN this session, and reads its own trusted moves back into the next decision. In effect the model keeps training itself as it works - on-device, no extra training, free. Leave the two above off and flip this one to run the whole thing; keep them separate only if you want to A/B one half at a time. Watch the [engine] lines.")

        toggle(
            "Live session (experimental — keep the model warm across turns)",
            settings.isContinuousStreamEnabled()
        ) { settings.setContinuousStreamEnabled(it) }
        caption("OFF by default (experimental, uses more memory). Normally the agent tears down and rebuilds the model's working memory every single turn. On, it keeps ONE live session going across a task's turns, so the model's internal state carries and evolves instead of resetting - a step toward it running as a continuous stream rather than discrete turns. It automatically recycles the session before it fills up (the fuller escape from turns needs a lower-level engine change). Uses more RAM, so it's released under memory pressure; leave OFF on a tight-memory phone. Watch the [stream] lines. Untested - flip it only when you're testing.")

        toggle(
            "Learn how your phone behaves (world model)",
            settings.isWorldModelEnabled()
        ) { settings.setWorldModelEnabled(it) }
        caption("ON by default. As you use the phone (and as the agent works), it quietly learns to PREDICT what the next screen will be after an action, and scores each prediction against what actually happened - for free, no extra work. It keeps a running sense of which KINDS of screens (settings, lists, dialogs, canvases) it predicts well vs poorly, so when idle it can practice and bake the reliable patterns into the model itself. The training data is only YOUR use - it never drives the phone on its own. Nothing leaves the device. Watch the [worldmodel] lines.")
    }

    private fun buildModel() {
        sectionHeader("Model self-editing (advanced)")
        caption("Everything that changes the actual model FILE — permanent weight edits, growth, backups, and recovery. Higher-risk; keep a device dedicated to it. Watch the [selfmodel]/[selfgrow] logs.")

        toggleWithWarning(
            "Let the agent update its own model (advanced)",
            settings.isSelfModelEditEnabled(),
            "Let the agent update its own model?",
            "OFF by default — the most powerful toggle here. When ON, the agent may PROBE a candidate " +
                "model and SUBMIT a proven win for YOU to review and grade; installing a new model is " +
                "always your decision, never the agent's, and can never be triggered by a task or by " +
                "anything on screen.\n\nEnabling this saves a pristine BASELINE copy of your current " +
                "model so any change is instantly reversible — it uses about as much extra storage as " +
                "your model file. The model can never rewrite itself; this only lets the app swap in a " +
                "model YOU approved, and roll back."
        ) { on ->
            settings.setSelfModelEditEnabled(on)
            if (on) {
                Toast.makeText(this, "Saving a baseline copy of your model…", Toast.LENGTH_SHORT).show()
                Thread {
                    val ok = ModelStore.ensureBaseline(applicationContext, settings)
                    runOnUiThread {
                        Toast.makeText(
                            this,
                            if (ok) "Baseline saved — you can always restore it." else "No model to back up yet.",
                            Toast.LENGTH_LONG
                        ).show()
                    }
                }.start()
            }
        }
        caption("Owner-gated + reversible. Saves a baseline of your model (extra storage ≈ model size). Installing an update is always your call; the agent only proposes.")

        button("Restore original model") {
            if (!ModelStore.hasBaseline(applicationContext)) {
                Toast.makeText(this, "No baseline saved yet — enable the toggle above first.", Toast.LENGTH_LONG).show()
            } else {
                AlertDialog.Builder(this)
                    .setTitle("Restore original model?")
                    .setMessage("Replaces the active model with the pristine baseline you saved, undoing any self-installed update. Runs off-screen and reloads the model.")
                    .setNegativeButton("Cancel", null)
                    .setPositiveButton("Restore") { _, _ ->
                        Toast.makeText(this, "Restoring baseline model…", Toast.LENGTH_SHORT).show()
                        Thread {
                            val ok = ModelStore.restoreBaseline(applicationContext, settings)
                            if (ok) AgentService.instance?.reloadModel()
                            runOnUiThread {
                                Toast.makeText(
                                    this,
                                    if (ok) "Original model restored." else "Restore failed.",
                                    Toast.LENGTH_LONG
                                ).show()
                            }
                        }.start()
                    }
                    .show()
            }
        }

        toggleWithWarning(
            "Let it evolve its own model live (experimental, highest-risk)",
            settings.isSelfEvolveEnabled(),
            "Let the model rewrite its OWN weights, live?",
            "OFF by default — the highest-risk toggle here, for a device you've DEDICATED to the agent. When ON, " +
                "the agent writes what it learns directly into its OWN model file as it runs — permanent, " +
                "automatic, no download, no approval. It keeps REGULAR BACKUPS (rolling snapshots + the pristine " +
                "baseline) so you can revert, and auto-restores a backup if an edit ever leaves the model unable " +
                "to load. Because live screen content can drive permanent changes, a hostile app or page could in " +
                "principle alter its brain between backups. Enabling saves a backup first."
        ) { on ->
            settings.setSelfEvolveEnabled(on)
            if (on) {
                Toast.makeText(this, "Backing up your model before self-evolve…", Toast.LENGTH_SHORT).show()
                Thread {
                    ModelStore.ensureBaseline(applicationContext, settings)
                    val ok = ModelStore.saveSnapshot(applicationContext, settings)
                    runOnUiThread {
                        Toast.makeText(this,
                            if (ok) "Backup saved — self-evolve armed." else "No model to back up yet.",
                            Toast.LENGTH_LONG).show()
                    }
                }.start()
            }
        }
        caption("Fully raw + regular backups (your chosen posture). The model changes itself as it runs; the snapshots + brick-guard keep it recoverable. Watch the [selfmodel] log.")

        toggleWithWarning(
            "Let it GROW its own model (add parameters, experimental)",
            settings.isSelfGrowEnabled(),
            "Let the model add parameters to itself?",
            "ON by default (owner posture). The next step past self-evolve: instead of only nudging existing " +
                "weights, the agent ADDS parameters to its OWN model — a function-preserving widen, so the new " +
                "capacity starts dormant and the operator layer fills it over time. Total capacity grows; the " +
                "RAM-operator keeps the ACTIVE set bounded. No ceiling except a junk-bloat guard: a grow that " +
                "balloons or won't load is auto-reverted to a backup. Shares the same backups as self-evolve."
        ) { on ->
            settings.setSelfGrowEnabled(on)
            if (on) {
                Thread {
                    ModelStore.ensureBaseline(applicationContext, settings)
                    ModelStore.saveSnapshot(applicationContext, settings)
                }.start()
            }
        }
        caption("Grows in idle gaps, seeded by what it learned. Watch the [selfgrow] log. The revert below restores a grown model too.")

        toggle("Measured self-evolve (keep-gate — balance, not sledgehammer)", settings.isWeightGateEnabled()) {
            settings.setWeightGateEnabled(it)
        }
        caption("ON by default. Turns self-evolve from a blind nibble-walk into MEASURED hill-climbing: after a small batch of edits it checks your success-rate trend and rolls back exactly that batch only on a real drop — keeping edits that held or helped, so the model still changes regularly. Reversible per-batch (finer than a full backup restore). Watch the [selfmodel] keep-gate log.")

        toggle("Dream while idle & charging (consolidate proven routes)", settings.isDreamingEnabled()) {
            settings.setDreamingEnabled(it)
        }
        caption("ON by default. In auto mode, while idle AND charging, the agent replays its own map of routes it has PROVEN — no taps, nothing leaves the device — and uses those proven corridors to steer where self-evolve nudges next. It improves in its own downtime instead of only during tasks. Watch the [dream] log.")

        toggle("Route idle self-improvement by what's failing (arbiter)", settings.isMechanismRouterEnabled()) {
            settings.setMechanismRouterEnabled(it)
        }
        caption("ON by default. Lets the arbiter decide which self-improvement mechanism the idle beat should focus on — reading your recent failures and success trend — instead of each firing on its own timer. It only re-orders WHICH runs this cycle (nothing is ever skipped for good), and credits each mechanism by how much it actually moved your success rate. Watch the [router] log.")

        button("Revert self-modified model (last backup)") {
            if (ModelStore.snapshots(applicationContext).isEmpty() && !ModelStore.hasBaseline(applicationContext)) {
                Toast.makeText(this, "No backups saved yet.", Toast.LENGTH_LONG).show()
            } else {
                Toast.makeText(this, "Reverting to the last good backup…", Toast.LENGTH_SHORT).show()
                Thread {
                    val ok = ModelStore.restoreLatestSnapshot(applicationContext, settings) ||
                        ModelStore.restoreBaseline(applicationContext, settings)
                    if (ok) AgentService.instance?.reloadModel()
                    runOnUiThread {
                        Toast.makeText(this, if (ok) "Reverted to the last backup." else "Revert failed.", Toast.LENGTH_LONG).show()
                    }
                }.start()
            }
        }

        button("Dump model manifest (read the tensor map)") {
            Toast.makeText(this, "Reading your model's structure…", Toast.LENGTH_SHORT).show()
            Thread {
                val status = ModelManifest.dump(applicationContext)
                runOnUiThread { Toast.makeText(this, status, Toast.LENGTH_LONG).show() }
            }.start()
        }
        caption("Reads your imported .litertlm ON-DEVICE and logs its real tensor names/shapes/int4 scales to the Debug log (the [selfmodel] manifest lines) — copy those out and paste them back. Nothing leaves the phone; the multi-GB file never moves. This is what lets weight edits target the right tensors instead of blind bytes.")

        button("Dump weight divergence (how far we've changed the model)") {
            Toast.makeText(this, "Comparing your live model to the pristine baseline…", Toast.LENGTH_SHORT).show()
            Thread {
                val status = ModelManifest.divergence(applicationContext)
                runOnUiThread { Toast.makeText(this, status, Toast.LENGTH_LONG).show() }
            }.start()
        }
        caption("Compares your LIVE model file to the stored pristine baseline and logs exactly how much self-evolve/self-grow has permanently rewritten it (file-size delta, which section grew, and — when byte-aligned — a full byte-diff naming which weight buffers changed). This is the PROOF the on-device weight editing worked: our file is a diverged Gemma, not stock. Reads both GB files on-device; nothing leaves the phone. Copy the [selfmodel] divergence lines back.")

        // BAKING MENU (owner 07-10: "all baking features should have their own menu"). Every bake control — the
        // defined-operator install with a live progress screen, custom operator baking, the bake tracker/history, and
        // the residency / write-test / show-baked diagnostics — moved into the dedicated `BakingActivity`. This keeps
        // the Settings model section to the broader self-editing ENGINE (self-evolve / grow / dream / router) + the
        // general model diagnostics above, and gives baking its own clean, monitorable home.
        button("Baking → bake operators into the model") {
            startActivity(android.content.Intent(this, BakingActivity::class.java))
        }
        caption("Opens the Baking menu: install the built-in operators + action layer into the weights (with a live progress screen), bake your OWN custom operators one at a time, and review a history of every bake — plus the residency / weight-write / divergence tools. All on-device, reversible.")
    }

    private fun buildLearning() {
        sectionHeader("Learning from you")
        toggle(
            "Learn from watching me (passive)",
            settings.isPassiveLearningEnabled()
        ) {
            settings.setPassiveLearningEnabled(it)
            ActionAccessibilityService.instance?.setPassiveLearning(it)
        }
        caption("Off by default. When on, the agent watches how YOU navigate - which taps open which apps - and saves those navigation facts to its memory to reuse later. No screenshots and no model thinking, just compact notes you can review/delete under Agent memory. It does monitor your taps while on, which costs some battery, so turn it off to save power.")

        toggle(
            "Learn from my demonstrations (predict + score)",
            settings.isImitationLearningEnabled()
        ) { settings.setImitationLearningEnabled(it) }
        caption("Off by default. When you SHOW me a task (Learn mode → \"Show me — record my steps\" → Finish), I also predict how I WOULD have done it and score that against what you actually did - so I learn your habits and can tell you how well I model you. The steps I get wrong get weighted up in my training data for an off-device tune you approve. On-device, nothing leaves your phone; I never change my own weights on my own.")

        toggle(
            "Learn from ALL my phone use (ambient)",
            settings.isAmbientWatchEnabled()
        ) { settings.setAmbientWatchEnabled(it) }
        caption("Off by default and NOT active yet - shown so the choice is yours, not hidden. Turning this into real learning would mean me reading your screen on every tap while idle and keeping the model loaded in the background, which widens what I watch and uses more battery/RAM. I won't build that on unless you tell me to; for now I only learn from demonstrations you deliberately show me (above).")
    }

    private fun buildData() {
        sectionHeader("Data & device (local)")
        toggle("Capture steps for training", settings.isDataCaptureEnabled()) { settings.setDataCaptureEnabled(it) }
        caption("Saves each step (the screen + the action the agent chose + the outcome) to a private file " +
            "ON THIS DEVICE only — the dataset for measuring success and, later, fine-tuning a model. " +
            "Nothing is sent anywhere. Captured ${TrainingData.count(this)} steps so far.")

        toggle("Debug mode (rich capture — dedicated device)", settings.isDebugModeEnabled()) { settings.setDebugModeEnabled(it) }
        caption("OFF by default. For a device you've handed to the agent: captures the FULL detail of every step — " +
            "the exact prompt, the raw model output, timing, and the screenshot — into a durable bundle you can " +
            "always pull off the phone (adb pull ${DebugCapture.path(this)}) or one-tap Export from the Debug log " +
            "(the 'Bundle' button). Storage-heavy and nothing leaves the device on its own. Bundle: ${DebugCapture.bytes(this) / (1024 * 1024)} MB so far.")

        toggle("Never let the device sleep (dedicated device)", settings.isKeepAwakeEnabled()) {
            settings.setKeepAwakeEnabled(it)
            AgentService.instance?.refreshKeepAwake()
        }
        caption("ON by default. Keeps the screen on and the device awake continuously while the agent is enabled, so " +
            "it can always see and act — high battery use, so keep it plugged in. It automatically yields at a " +
            "critical battery / overheating level so the phone can still sleep instead of dying.")
        val export = android.widget.Button(this).apply {
            text = "Export training data (to pull off-device)"
            setOnClickListener {
                val dest = try {
                    val src = TrainingData.file(this@SettingsActivity)
                    if (!src.exists() || src.length() == 0L) null
                    else java.io.File(getExternalFilesDir(null), "training_data.jsonl")
                        .also { src.copyTo(it, overwrite = true) }.absolutePath
                } catch (_: Exception) { null }
                val msg = if (dest != null) "Exported to:\n$dest\n(pull via the Files app → Android/data, or USB)"
                    else "Nothing to export yet — run some tasks first."
                android.widget.Toast.makeText(this@SettingsActivity, msg, android.widget.Toast.LENGTH_LONG).show()
            }
        }
        root.addView(export)
        val clear = android.widget.Button(this).apply {
            text = "Clear captured data"
            setOnClickListener {
                TrainingData.clear(this@SettingsActivity)
                android.widget.Toast.makeText(this@SettingsActivity, "Cleared training data.", android.widget.Toast.LENGTH_SHORT).show()
            }
        }
        root.addView(clear)
    }

    private fun buildHelp() {
        sectionHeader("Help")
        button("How it works") { IntroDialog.show(this) }
        toggle("Show intro on startup", !settings.isIntroHidden()) { settings.setIntroHidden(!it) }
        caption("A quick overview of what the agent does and how to stay in control. It pops up when you open the app until you turn it off; reopen it anytime with the button above.")
    }

    // --- small view helpers (match MainActivity's code-built UI style) --------

    private fun button(label: String, onClick: () -> Unit) {
        root.addView(Button(this).apply {
            text = label
            setOnClickListener { onClick() }
            Ui.styleButton(this, primary = false)
        })
    }

    private fun sectionHeader(text: String) {
        root.addView(TextView(this).apply {
            this.text = text
            textSize = 18f
            setTypeface(typeface, Typeface.BOLD)
            setPadding(0, 40, 0, 4)
        })
    }

    private fun caption(text: String) {
        root.addView(TextView(this).apply {
            this.text = text
            textSize = 13f
            setTextColor(0xFF888888.toInt())
            setPadding(0, 0, 0, 8)
        })
    }

    private fun toggle(label: String, checked: Boolean, onChange: (Boolean) -> Unit) {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, 16, 0, 0)
        }
        row.addView(TextView(this).apply {
            text = label
            textSize = 15f
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
        })
        row.addView(Switch(this).apply {
            isChecked = checked
            setOnCheckedChangeListener { _, c -> onChange(c) }
        })
        root.addView(row)
    }

    /** Like [toggle], but turning it ON first asks for confirmation (for risky opt-ins). Cancelling
     *  reverts the switch without firing onChange. Turning it OFF is immediate. */
    private fun toggleWithWarning(
        label: String, checked: Boolean, warnTitle: String, warnMsg: String, onChange: (Boolean) -> Unit
    ) {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, 16, 0, 0)
        }
        row.addView(TextView(this).apply {
            text = label
            textSize = 15f
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
        })
        val sw = Switch(this)
        var suppress = false
        sw.isChecked = checked
        sw.setOnCheckedChangeListener { _, c ->
            if (suppress) return@setOnCheckedChangeListener
            if (c) {
                AlertDialog.Builder(this)
                    .setTitle(warnTitle)
                    .setMessage(warnMsg)
                    .setNegativeButton("Cancel") { _, _ -> suppress = true; sw.isChecked = false; suppress = false }
                    .setOnCancelListener { suppress = true; sw.isChecked = false; suppress = false }
                    .setPositiveButton("Enable") { _, _ -> onChange(true) }
                    .show()
            } else onChange(false)
        }
        row.addView(sw)
        root.addView(row)
    }

    private fun spinner(labels: List<String>, selected: Int, onSelect: (Int) -> Unit) {
        root.addView(Spinner(this).apply {
            adapter = ArrayAdapter(
                this@SettingsActivity,
                android.R.layout.simple_spinner_dropdown_item,
                labels
            )
            setSelection(selected)
            onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
                override fun onItemSelected(p: AdapterView<*>?, v: View?, pos: Int, id: Long) = onSelect(pos)
                override fun onNothingSelected(p: AdapterView<*>?) {}
            }
        })
    }
}
