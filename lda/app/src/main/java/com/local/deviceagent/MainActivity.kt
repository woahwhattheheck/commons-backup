package com.local.deviceagent

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.text.InputType
import android.view.Gravity
import android.accessibilityservice.AccessibilityServiceInfo
import android.view.accessibility.AccessibilityManager
import android.widget.*
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.app.AlertDialog
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.activity.result.contract.ActivityResultContracts
import java.io.File
import java.io.FileOutputStream

class MainActivity : AppCompatActivity() {

    companion object {
        private const val REQUEST_PERMISSIONS = 1001
        // Per-PROCESS flag (static, so it survives Activity recreation but resets on a cold start):
        // the intro shows once each time the app is opened "fresh", per the owner's request.
        private var introShownThisProcess = false

        // Best-effort auto-download source. Gemma weights are license-gated, so
        // this may return 401 (then the user uses Import instead). Point this at a
        // reachable .litertlm/.task file when one is available.
        private const val MODEL_URL =
            "https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm/resolve/main/gemma-4-E2B-it-int4.litertlm"
        // SMS triggering was deliberately removed (spoofing / prompt-injection risk),
        // so the only runtime-dangerous permission left is the microphone.
        private val DANGEROUS_PERMISSIONS = arrayOf(
            Manifest.permission.RECORD_AUDIO
        )
    }

    private lateinit var statusLayout: LinearLayout
    private lateinit var settings: SettingsManager
    // Show the one-time first-run welcome at most once per app launch (it persists its choice).
    private var firstRunShown = false
    // AGENT DEVICE MODE: guided "grant everything" flow state. devGrantPrompted = system-toggle perms already
    // opened THIS flow (so we never re-open the same Settings screen and loop); devGrantActive = mid-sequence.
    private val devGrantPrompted = LinkedHashSet<String>()
    private var devGrantActive = false
    private var speechChoiceShown = false

    // Must be registered before the activity is STARTED, so it lives as a field.
    private val importModelLauncher =
        registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
            uri?.let { importModel(it) }
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // (The crash trace is shown by ChatActivity - the launcher - as a dismissible popup over the
        // working app, and mirrored to last_crash.txt. MainActivity no longer duplicates that viewer.)
        settings = SettingsManager(this)
        NotificationHelper.createChannel(this)
        setupUI()
        checkAndRequestPermissions()
    }

    override fun onResume() {
        super.onResume()
        updateUI()
        // AGENT DEVICE MODE: returning from a Settings screen advances the guided grant to the next missing perm.
        if (devGrantActive) statusLayout.postDelayed({ advanceDeviceGrant() }, 500)
    }

    private fun setupUI() {
        val scroll = ScrollView(this)
        statusLayout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 64, 48, 48)
        }
        scroll.addView(statusLayout)
        setContentView(scroll)
    }

    private fun checkAndRequestPermissions() {
        val missing = DANGEROUS_PERMISSIONS.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, missing.toTypedArray(), REQUEST_PERMISSIONS)
        } else {
            updateUI()
        }
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQUEST_PERMISSIONS) {
            updateUI()
            // Runtime perms done -> continue the device-mode flow into the system-toggle perms.
            if (devGrantActive) statusLayout.postDelayed({ advanceDeviceGrant() }, 300)
        }
    }

    private fun updateUI() {
        statusLayout.removeAllViews()

        val title = TextView(this).apply {
            text = "Local Agent"
            textSize = 28f
            setTypeface(typeface, android.graphics.Typeface.BOLD)
            setTextColor(Ui.TEXT)
            letterSpacing = 0.01f
            setPadding(0, 0, 0, 8)
        }
        statusLayout.addView(title)
        statusLayout.addView(TextView(this).apply {
            text = "Patent Pending"
            textSize = 12f
            setTextColor(0xFF888888.toInt())
            setPadding(0, 0, 0, 12)
        })

        val audioGranted = ContextCompat.checkSelfPermission(
            this, Manifest.permission.RECORD_AUDIO
        ) == PackageManager.PERMISSION_GRANTED

        val overlayGranted = Settings.canDrawOverlays(this)
        val accessibilityEnabled = isAccessibilityEnabled()
        val allReady = audioGranted && overlayGranted && accessibilityEnabled

        // Only show the permissions section while something is still MISSING - each granted
        // permission (and the whole section once all are granted) disappears, so the landing
        // page isn't cluttered with already-handled prompts.
        if (!allReady) {
            statusLayout.addView(TextView(this).apply {
                text = "Grant each permission below to get started."
                textSize = 14f
                setPadding(0, 0, 0, 32)
            })
            if (!audioGranted) addPermissionRow("Microphone", false, null)
            if (!overlayGranted) addPermissionRow("Draw Over Other Apps", false) {
                startActivity(
                    Intent(
                        Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                        Uri.parse("package:$packageName")
                    )
                )
            }
            if (!accessibilityEnabled) addPermissionRow("Accessibility Service", false) {
                startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
                Toast.makeText(this, "Find 'Local Agent' and enable it", Toast.LENGTH_LONG).show()
            }
            if (!audioGranted) {
                addButton("Grant Microphone Permission") {
                    ActivityCompat.requestPermissions(
                        this, DANGEROUS_PERMISSIONS, REQUEST_PERMISSIONS
                    )
                }
            }
        }

        // AGENT DEVICE MODE: one guided "grant everything" for a dedicated agent device (owner: "I don't want to
        // click each one"). Shows whenever any perm — runtime or a system toggle (incl. battery) — is still missing.
        if (!deviceFullPerms()) {
            addButton("⚡ Agent Device Mode — grant everything", emphasize = true) { startAgentDeviceMode() }
        }

        if (allReady) {
            val enabled = settings.isAgentEnabled()

            val readyText = TextView(this).apply {
                text = if (enabled)
                    "Agent ready. Say “${settings.getTriggerWord()}”, or tap the floating mic button."
                else
                    "Agent is off. Tap “Wake agent” when you want it listening."
                textSize = 15f
                setTextColor(if (enabled) Ui.SUCCESS else Ui.WARNING)
                gravity = Gravity.CENTER
                setPadding(0, 32, 0, 16)
            }
            statusLayout.addView(readyText)

            if (enabled) {
                val note = TextView(this).apply {
                    text = "It taps and types on your real phone, so glance at it now and then " +
                        "while it works. You can stop it anytime with the floating button or by saying “stop.”"
                    textSize = 12f
                    setTextColor(Ui.TEXT_DIM)
                    gravity = Gravity.CENTER
                    setPadding(0, 0, 0, 16)
                }
                statusLayout.addView(note)
            }

            // #10 RESUME: an earlier task was interrupted. A clean finish clears the checkpoint, so a
            // leftover one means the process was killed mid-task - usually the OOM/black-wallpaper case.
            // Offer to resume it; the agent re-runs that objective and now AUTO-CONTINUES from its own saved
            // rolling context (the self-authored resume-context restore in AgentOrchestrator.start) instead
            // of starting cold. We no longer clear the checkpoint here - start() consumes/refreshes it.
            if (enabled) AgentMemory.getCheckpoint(this)?.let { cp ->
                val obj = cp.first; val steps = cp.third
                statusLayout.addView(TextView(this).apply {
                    text = "Interrupted: \"${obj.take(70)}\"${if (steps > 0) " · $steps steps in" else ""}"
                    textSize = 13f
                    setTextColor(Ui.WARNING)
                    setPadding(0, 16, 0, 4)
                })
                addButtonRow(
                    "Resume", {
                        // Tapping Resume IS the prompt (owner: default doesn't spring to life). EXTRA_RESUME
                        // tells start() to restore the saved rolling context and continue; a plain re-run
                        // without this extra starts fresh unless the auto-resume toggle is on. Don't clear
                        // the checkpoint - start() consumes it, then refreshes/clears it via the run.
                        startForegroundService(Intent(this, AgentService::class.java)
                            .setAction(AgentService.ACTION_RUN_COMMAND)
                            .putExtra(AgentService.EXTRA_COMMAND, obj)
                            .putExtra(AgentService.EXTRA_RESUME, true))
                        Toast.makeText(this, "Resuming…", Toast.LENGTH_SHORT).show()
                    },
                    "Dismiss", { AgentMemory.clearCheckpoint(this); updateUI() }
                )
            }

            // Power controls: Sleep (-> passive learning only) and Emergency stop, side by side.
            if (enabled) {
                val powerRow = LinearLayout(this).apply {
                    orientation = LinearLayout.HORIZONTAL
                    setPadding(0, 12, 0, 0)
                }
                powerRow.addView(Button(this).apply {
                    text = "Sleep"
                    layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                    setOnClickListener {
                        AgentControl.sleep(this@MainActivity)
                        Toast.makeText(this@MainActivity, "Sleeping — passively learning.", Toast.LENGTH_SHORT).show()
                        updateUI()
                    }
                    Ui.styleButton(this, primary = false)
                })
                powerRow.addView(Button(this).apply {
                    text = "Emergency stop"
                    layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                        .apply { setMargins(20, 0, 0, 0) }
                    setOnClickListener {
                        AlertDialog.Builder(this@MainActivity)
                            .setTitle("Emergency stop?")
                            .setMessage("Shuts the model down and stops everything, including passive learning.")
                            .setNegativeButton("Cancel", null)
                            .setPositiveButton("Stop") { _, _ -> AgentControl.emergencyStop(this@MainActivity); updateUI() }
                            .show()
                    }
                    Ui.styleButton(this, primary = false)
                    setTextColor(Ui.DANGER)
                })
                statusLayout.addView(powerRow)
            } else {
                addButton("Wake agent", emphasize = true) { AgentControl.wake(this); updateUI() }
            }

            if (enabled) addCommandBox()

            // Primary way to interact with the agent - kept prominent at the top. Debug log sits right
            // beside it: the owner opens it constantly (he pastes the on-device logs back), so it earns
            // a top-level spot instead of being buried at the bottom under Diagnostics.
            addButtonRow(
                "Open chat", { startActivity(Intent(this, ChatActivity::class.java)) },
                "Debug log", { startActivity(Intent(this, DebugLogActivity::class.java)) }
            )

            addModelControls()

            // Everything else grouped into tidy 2-up rows under headers, so the home screen is a
            // few labelled sections instead of one long wall of identical buttons. No menu removed.
            addSectionHeader("Tools")
            addButton("Learn mode — explore & improve navigation") { startLearnMode() }
            addButton("🤖 Auto mode — run & self-improve on its own") { startAutoModeFlow() }
            addButtonRow(
                "Train me", { startActivity(Intent(this, TrainingActivity::class.java)) },
                "Agent memory", { startActivity(Intent(this, MemoryActivity::class.java)) }
            )
            addButtonRow(
                "Voice commands", { showCommandsDialog() },
                "Settings", { startActivity(Intent(this, SettingsActivity::class.java)) }
            )

            addSectionHeader("Diagnostics")
            // Debug log moved up beside Open chat (owner uses it constantly); Task log stays here.
            addButton("Task log") { startActivity(Intent(this, TaskLogActivity::class.java)) }

            if (enabled) {
                startForegroundService(Intent(this, AgentService::class.java))
                startService(Intent(this, FloatingButtonService::class.java))
            } else {
                stopService(Intent(this, FloatingButtonService::class.java))
                stopService(Intent(this, AgentService::class.java))
            }

            // On a fresh open: the "How it works" intro (until dismissed), then the one-time scan offer.
            maybeShowIntro()
        }
    }

    /** The startup "How it works" intro - shown once per cold start unless the owner hid it - then
     *  chains to the one-time scan offer so the two dialogs don't stack on the very first run. */
    private fun maybeShowIntro() {
        if (introShownThisProcess || settings.isIntroHidden()) { maybeShowFirstRun(); return }
        introShownThisProcess = true
        IntroDialog.show(this) { maybeShowFirstRun() }
    }

    /** One-time welcome: with the owner's explicit yes, scan the installed apps so the agent
     *  knows what's on the phone. Nothing is sent anywhere; it's a local navigation aid. */
    private fun maybeShowFirstRun() {
        if (firstRunShown || settings.isFirstRunDone()) { maybeShowSpeechChoice(); return }
        firstRunShown = true
        AlertDialog.Builder(this)
            .setTitle("Welcome — can I learn your phone?")
            .setMessage("I can scan which apps are installed and how your phone is set up (model, " +
                "screen, and your default browser/texting/phone apps) so I navigate to the right " +
                "place, and you can teach me new things anytime under “Train me”. Scan now? " +
                "Nothing leaves your phone.")
            .setCancelable(false)
            .setNegativeButton("Not now") { _, _ -> settings.setFirstRunDone(true); maybeShowSpeechChoice() }
            .setPositiveButton("Scan my phone") { _, _ ->
                settings.setFirstRunDone(true)
                val acc = ActionAccessibilityService.instance
                if (acc != null) {
                    acc.scanAll()
                    val n = AgentMemory.deviceApps(this).size
                    Toast.makeText(this, "Learned $n apps + your phone's defaults. Teach me tasks under “Train me”.",
                        Toast.LENGTH_LONG).show()
                } else {
                    Toast.makeText(this, "I'll scan once the accessibility service is fully on — " +
                        "use “Re-scan installed apps” under Train me.", Toast.LENGTH_LONG).show()
                }
                maybeShowSpeechChoice()
            }
            .show()
    }

    /** One-time choice (then changeable in Settings): on-device speech (private, default) vs cloud speech
     *  (more accurate, but the spoken command is sent off the device). The wake word stays on-device either
     *  way. The owner explicitly authorized cloud as an opt-in, so this is a labeled, informed choice. */
    private fun maybeShowSpeechChoice() {
        if (speechChoiceShown || settings.isSpeechChoiceMade()) return
        speechChoiceShown = true
        AlertDialog.Builder(this)
            .setTitle("Understanding your voice")
            .setMessage("How should I recognize your spoken commands?\n\n" +
                "• On-device (private): nothing leaves your phone. Solid accuracy.\n" +
                "• Cloud (Google): more accurate, but your spoken command is sent off the device.\n\n" +
                "The wake word always stays on-device either way. Change this anytime in Settings.")
            .setCancelable(false)
            .setNegativeButton("Cloud — more accurate") { _, _ ->
                settings.setSpeechMode("cloud"); settings.setSpeechChoiceMade(true)
                Toast.makeText(this, "Using cloud speech recognition (spoken commands go off-device).", Toast.LENGTH_LONG).show()
            }
            .setPositiveButton("On-device — private") { _, _ ->
                settings.setSpeechMode("ondevice"); settings.setSpeechChoiceMade(true)
                Toast.makeText(this, "Using on-device speech recognition (private).", Toast.LENGTH_SHORT).show()
            }
            .show()
    }

    /** Learn mode: the agent autonomously explores apps to build up its navigation memory, so later
     *  tasks are faster. Needs the agent on (accessibility granted); stop it via the floating button. */
    /** AUTONOMOUS SELF-IMPROVE MODE (owner: "press the button and it does whatever it wants, constantly
     *  improves"). Owner-initiated with an explicit confirmation of the autonomy + the safety envelope. Toggles
     *  in the service; STOP / "stop" / the floating button end it. Best on a dedicated agent device. */
    private fun startAutoModeFlow() {
        if (ActionAccessibilityService.instance == null) {
            Toast.makeText(this, "Turn the agent on first (grant accessibility), then start Auto mode.",
                Toast.LENGTH_LONG).show()
            return
        }
        AlertDialog.Builder(this)
            .setTitle("Auto mode (self-improve)")
            .setMessage("The agent will pick its OWN safe tasks and do them on this phone, over and over — " +
                "practicing, tuning itself, and saving rich logs so it keeps getting better. It stays inside the " +
                "safety rules (no buying, no settings/OS changes, no deleting, no messaging real people) and you " +
                "can stop it anytime with the floating button or by saying “stop.” Best on a device you've " +
                "dedicated to the agent. Start?")
            .setNegativeButton("Cancel", null)
            .setPositiveButton("Start") { _, _ ->
                startService(Intent(this, AgentService::class.java).setAction(AgentService.ACTION_AUTO_MODE))
                Toast.makeText(this, "Auto mode on. Tap the floating button or say “stop” to end.", Toast.LENGTH_LONG).show()
            }
            .show()
    }

    private fun startLearnMode() {
        if (ActionAccessibilityService.instance == null) {
            Toast.makeText(this, "Turn the agent on first (grant accessibility), then start Learn mode.",
                Toast.LENGTH_LONG).show()
            return
        }
        AlertDialog.Builder(this)
            .setTitle("Learn mode")
            .setMessage("The agent will explore your apps on its own — opening them, looking around, and " +
                "learning how to get around — so it's faster and smarter on later tasks. It won't type, " +
                "send, buy, or change settings; it just looks. Keep an eye on it, and tap the floating " +
                "button anytime to stop. Start now?")
            .setNegativeButton("Cancel", null)
            .setPositiveButton("Explore") { _, _ ->
                startService(Intent(this, AgentService::class.java).setAction(AgentService.ACTION_LEARN_MODE))
                Toast.makeText(this, "Learning… tap the floating button to stop.", Toast.LENGTH_LONG).show()
            }
            .show()
    }

    /** Quick reference of the spoken phrases that trigger special behaviors, so the
     *  user doesn't have to memorize exact wording. (Easter eggs intentionally omitted.) */
    private fun showCommandsDialog() {
        val w = settings.getTriggerWord()
        val msg = """
            Say "$w" then your command — or type it in the box. Most tasks are freeform,
            just say what you want:
            •  "send a text to mom saying hi"
            •  "turn on wi-fi"
            •  "open YouTube and play a cat video"

            Handy exact phrases:
            •  "open <app>"  — opens an app (installs from Play Store if missing)
            •  "search for <thing>"  /  "google <thing>"
            •  "set a timer for <N> minutes"
            •  "directions to <place>"
            •  "call <number>"
            •  "remember my <thing> is <value>"  — saves a fact
            •  "what is my <thing>"  — recalls it
            •  "what do you need fixed?"  — the agent writes the code change it needs
               into the Debug log for you to share
            •  "what can you do?"  — capabilities
            •  "stop"  /  "cancel"  — halt immediately

            Mid-task: say "$w …" to correct it, or "stop" to halt.
        """.trimIndent()
        AlertDialog.Builder(this)
            .setTitle("Voice commands")
            .setMessage(msg)
            .setPositiveButton("Got it", null)
            .show()
    }

    /** Type-a-command box (alternative to speaking). Shown only while the agent
     *  is on. Advanced toggles (wake word, voice, navigation, speed, heat) live in
     *  [SettingsActivity]. */
    private fun addCommandBox() {
        val cmdLabel = TextView(this).apply {
            text = "Or type a command"
            textSize = 14f
            setPadding(0, 24, 0, 4)
        }
        val cmdField = EditText(this).apply {
            hint = "e.g. open settings and turn on Wi-Fi"
            inputType = InputType.TYPE_CLASS_TEXT
            setSingleLine(true)
        }
        val goButton = Button(this).apply {
            text = "Go"
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { setMargins(0, 8, 0, 0) }
            setOnClickListener {
                val cmd = cmdField.text?.toString()?.trim().orEmpty()
                if (cmd.isNotBlank()) {
                    startForegroundService(
                        Intent(this@MainActivity, AgentService::class.java)
                            .setAction(AgentService.ACTION_RUN_COMMAND)
                            .putExtra(AgentService.EXTRA_COMMAND, cmd)
                    )
                    cmdField.setText("")
                    Toast.makeText(this@MainActivity, "Sent to agent", Toast.LENGTH_SHORT).show()
                }
            }
        }
        statusLayout.addView(cmdLabel)
        statusLayout.addView(cmdField)
        statusLayout.addView(goButton)
    }

    /** AI model (brain) status + download/import. Always available so the user can
     *  set up the model even while the agent is turned off. */
    // Declutter: once the model is set up (the usual case after first run), the whole model/helper
    // block collapses to a one-line status + a "Model setup" button; it only expands on request, or
    // automatically when NO model is imported yet so first-run setup is unmissable. Loses no control.
    private var showModelSetup = false

    private fun addModelControls() {
        val modelPath = settings.getModelPath()
        val modelReady = modelPath != null && File(modelPath).exists()
        // Model-fitness guard (A16 / multi-device): warn prominently when the imported model is too big
        // for this phone's RAM, so the owner/customer swaps to a smaller one instead of hitting silent
        // crash-on-load. Only shows on the clearly-impossible heavy-model-on-a-weak-device pairing.
        val fitWarn = DeviceStats.fitnessWarning(this, modelPath)
        if (fitWarn.isNotBlank()) statusLayout.addView(TextView(this).apply {
            text = "⚠ $fitWarn"
            textSize = 13f
            setTextColor(Ui.WARNING)
            setPadding(0, 16, 0, 4)
        })
        if (modelReady && !showModelSetup) {
            addSectionHeader("Model")
            statusLayout.addView(TextView(this).apply {
                text = "Brain ready ✓"
                textSize = 13f
                setTextColor(Ui.SUCCESS)
                setPadding(0, 8, 0, 4)
            })
            addButton("Model setup") { showModelSetup = true; updateUI() }
            return
        }
        val modelLabel = TextView(this).apply {
            text = "AI model (brain)"
            textSize = 14f
            setPadding(0, 24, 0, 4)
        }
        val modelStatus = TextView(this).apply {
            text = if (modelReady) "Model ready — the agent can think."
                else "No model yet. Download it (automatic) or Import a file."
            textSize = 13f
            setTextColor(if (modelReady) Ui.SUCCESS else Ui.DANGER)
        }
        statusLayout.addView(modelLabel)
        statusLayout.addView(modelStatus)
        if (!modelReady) addButton("Download model (automatic)") { downloadModel() }
        addButton(if (modelReady) "Replace model (import file)" else "Import model file") {
            importModelLauncher.launch(arrayOf("*/*"))
        }

        // (07-10) The optional "helper"/sub-model was removed — single-model only (§16). No helper import UI.
        // Collapse the setup block back down once the owner is done (only when there's a model to
        // collapse to - while none is imported the block stays open so setup can't be hidden away).
        if (modelReady && showModelSetup) addButton("Hide setup") { showModelSetup = false; updateUI() }
    }

    /** Best-effort automatic model download into private storage. */
    private fun downloadModel() {
        Toast.makeText(this, "Downloading model... large file, keep Wi-Fi on.", Toast.LENGTH_LONG).show()
        Thread {
            val ok = try {
                val dir = File(filesDir, "model").apply { mkdirs() }
                dir.listFiles()?.forEach { it.delete() }
                val dest = File(dir, "model.litertlm")
                val conn = (java.net.URL(MODEL_URL).openConnection() as java.net.HttpURLConnection).apply {
                    connectTimeout = 30000; readTimeout = 60000; instanceFollowRedirects = true
                }
                val code = conn.responseCode
                if (code in 200..299) {
                    conn.inputStream.use { i -> FileOutputStream(dest).use { o -> i.copyTo(o, 1 shl 20) } }
                    settings.setModelPath(dest.absolutePath)
                    // A deliberate owner install becomes the new rollback baseline (only when self-model-edit
                    // is on; otherwise no baseline behavior at all — byte-identical to before).
                    if (settings.isSelfModelEditEnabled()) ModelStore.refreshBaseline(applicationContext, dest)
                    true
                } else {
                    AgentLog.log("model", "download HTTP $code (gated? use Import)"); false
                }
            } catch (e: Exception) {
                AgentLog.log("model", "download error ${e.message}"); false
            }
            runOnUiThread {
                Toast.makeText(
                    this,
                    if (ok) "Model downloaded." else "Auto-download blocked - use Import instead.",
                    Toast.LENGTH_LONG
                ).show()
                updateUI()
            }
        }.start()
    }

    /** Copy the picked model file into private storage (off the main thread). */
    private fun importModel(uri: Uri) {
        Toast.makeText(this, "Importing model… this can take a few minutes.", Toast.LENGTH_LONG).show()
        Thread {
            val ok = try {
                val dir = File(filesDir, "model").apply { mkdirs() }
                dir.listFiles()?.forEach { it.delete() }  // keep only the latest
                val name = queryDisplayName(uri) ?: "model.bin"
                val dest = File(dir, name)
                contentResolver.openInputStream(uri)?.use { input ->
                    FileOutputStream(dest).use { out -> input.copyTo(out, 1 shl 20) }
                } ?: throw IllegalStateException("could not open file")
                settings.setModelPath(dest.absolutePath)
                // A deliberate owner install becomes the new rollback baseline (only when self-model-edit
                // is on; otherwise no baseline behavior at all — byte-identical to before).
                if (settings.isSelfModelEditEnabled()) ModelStore.refreshBaseline(applicationContext, dest)
                true
            } catch (e: Exception) {
                false
            }
            runOnUiThread {
                Toast.makeText(
                    this,
                    if (ok) "Model imported." else "Model import failed.",
                    Toast.LENGTH_LONG
                ).show()
                updateUI()
            }
        }.start()
    }


    private fun queryDisplayName(uri: Uri): String? =
        contentResolver.query(uri, null, null, null, null)?.use { c ->
            val idx = c.getColumnIndex(android.provider.OpenableColumns.DISPLAY_NAME)
            if (idx >= 0 && c.moveToFirst()) c.getString(idx) else null
        }

    private fun addPermissionRow(label: String, granted: Boolean, onFix: (() -> Unit)?) {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(0, 14, 0, 14)
            gravity = Gravity.CENTER_VERTICAL
        }

        val icon = TextView(this).apply {
            text = if (granted) "✓" else "✗"
            textSize = 18f
            setTextColor(if (granted) 0xFF4CAF50.toInt() else 0xFFF44336.toInt())
            setPadding(0, 0, 20, 0)
        }

        val name = TextView(this).apply {
            text = label
            textSize = 15f
            layoutParams = LinearLayout.LayoutParams(
                0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f
            )
        }

        row.addView(icon)
        row.addView(name)

        if (!granted && onFix != null) {
            val btn = Button(this).apply {
                text = "Enable"
                textSize = 12f
                setOnClickListener { onFix() }
            }
            row.addView(btn)
        }

        statusLayout.addView(row)
    }

    private fun addButton(label: String, emphasize: Boolean = false, onClick: () -> Unit) {
        val btn = Button(this).apply {
            text = label
            if (emphasize) textSize = 17f
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { setMargins(0, if (emphasize) 16 else 12, 0, 0) }
            setOnClickListener { onClick() }
        }
        Ui.styleButton(btn, primary = emphasize)
        statusLayout.addView(btn)
    }

    /** A small muted section label, so the home screen reads as a few grouped sections
     *  instead of one long column of identical buttons. */
    private fun addSectionHeader(text: String) {
        statusLayout.addView(TextView(this).apply {
            this.text = text.uppercase()
            textSize = 12f
            setTextColor(Ui.TEXT_DIM)
            letterSpacing = 0.10f
            setPadding(4, 32, 0, 4)
        })
    }

    /** Two equal-width buttons side by side - the building block of the decluttered menu.
     *  Keeps every destination, just two per row instead of one. */
    private fun addButtonRow(label1: String, click1: () -> Unit, label2: String, click2: () -> Unit) {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(0, 8, 0, 0)
        }
        row.addView(Button(this).apply {
            text = label1
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            setOnClickListener { click1() }
            Ui.styleButton(this, primary = false)
        })
        row.addView(Button(this).apply {
            text = label2
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                .apply { setMargins(20, 0, 0, 0) }
            setOnClickListener { click2() }
            Ui.styleButton(this, primary = false)
        })
        statusLayout.addView(row)
    }

    private fun isAccessibilityEnabled(): Boolean {
        val am = getSystemService(ACCESSIBILITY_SERVICE) as AccessibilityManager
        return am.getEnabledAccessibilityServiceList(AccessibilityServiceInfo.FEEDBACK_ALL_MASK)
            .any { it.resolveInfo.serviceInfo.packageName == packageName }
    }

    // ── AGENT DEVICE MODE ──────────────────────────────────────────────────────────────────────────────────────
    // A dedicated agent device: one guided "grant everything" flow. It requests the runtime perms together, then
    // walks straight to each missing system-toggle perm in sequence so the owner never hunts each one. It grants
    // NOTHING on its own — every system toggle still requires the owner's tap (an Android security invariant); the
    // flow just drives you to each screen. Purely a setup convenience; it changes no agent behavior.
    private data class SysPerm(val key: String, val label: String, val granted: () -> Boolean, val intent: () -> Intent)

    private fun systemPerms(): List<SysPerm> = listOf(
        SysPerm("overlay", "Draw Over Other Apps", { Settings.canDrawOverlays(this) },
            { Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")) }),
        SysPerm("accessibility", "Accessibility (the agent's hands)", { isAccessibilityEnabled() },
            { Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS) }),
        SysPerm("battery", "Unrestricted battery (stay alive)",
            { (getSystemService(POWER_SERVICE) as android.os.PowerManager).isIgnoringBatteryOptimizations(packageName) },
            { Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS) })
    )

    /** True once the agent has the full set the device-mode flow grants: mic + notifications + every system toggle. */
    private fun deviceFullPerms(): Boolean =
        ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED &&
        (android.os.Build.VERSION.SDK_INT < 33 ||
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED) &&
        systemPerms().all { it.granted() }

    private fun startAgentDeviceMode() {
        settings.setAgentDeviceMode(true)
        devGrantPrompted.clear()
        devGrantActive = true
        // Runtime perms first, all together (one system dialog): mic + notifications.
        val runtime = ArrayList<String>()
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED)
            runtime.add(Manifest.permission.RECORD_AUDIO)
        if (android.os.Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED)
            runtime.add(Manifest.permission.POST_NOTIFICATIONS)
        if (runtime.isNotEmpty()) {
            // The result callback (or the next onResume) continues into the system-toggle perms.
            ActivityCompat.requestPermissions(this, runtime.toTypedArray(), REQUEST_PERMISSIONS)
            return
        }
        advanceDeviceGrant()
    }

    /** Open the next missing system-toggle perm we haven't already opened this flow (dedup => no re-open loop).
     *  When none remain, end the flow and report. Driven from onResume / the permission-result callback. */
    private fun advanceDeviceGrant() {
        if (!devGrantActive) return
        val next = systemPerms().firstOrNull { !it.granted() && it.key !in devGrantPrompted }
        if (next == null) {
            devGrantActive = false
            val done = systemPerms().all { it.granted() }
            Toast.makeText(this,
                if (done) "Agent has full device access ✓" else "A permission still needs a tap — see the list below.",
                Toast.LENGTH_LONG).show()
            updateUI()
            return
        }
        devGrantPrompted.add(next.key)
        Toast.makeText(this, "Enable: ${next.label}, then come back", Toast.LENGTH_LONG).show()
        try { startActivity(next.intent()) } catch (_: Exception) { advanceDeviceGrant() }
    }
}
