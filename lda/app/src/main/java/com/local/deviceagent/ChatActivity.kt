package com.local.deviceagent

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Typeface
import android.os.Build
import android.os.Bundle
import android.view.Gravity
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

/**
 * The main screen: a text chat with the agent itself. It answers from its own perspective (it can
 * see the current screen, its memory, and its recent runs), so it's the place to debug ("why did
 * that task fail?") and to ask it to do things - it proposes the action and asks before running.
 * Setup, settings, memory, training, and logs all live one tap away behind the Menu button. The
 * verbal conversation mode is kept (the 🎙 button) and is also on the floating button's menu.
 */
class ChatActivity : AppCompatActivity() {

    private lateinit var convo: LinearLayout
    private lateinit var scroll: ScrollView
    private lateinit var input: EditText
    private lateinit var modeBtn: Button
    private lateinit var powerRow: LinearLayout
    private var thinking = false
    // false = talk to the agent (debug/converse); true = type a command it RUNS on the phone.
    private var commandMode = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        title = "Agent"

        val rootCol = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(0, 0, 0, 0) }

        // Top bar: a short casual instruction + a Menu button to everything else.
        val top = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(36, 28, 24, 8)
        }
        top.addView(TextView(this).apply {
            text = "Talk to your agent. Ask it to do something, or ask why a run failed."
            textSize = 13f; setTextColor(Ui.TEXT_DIM)
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
        })
        top.addView(chatButton("New") {   // start a FRESH conversation (old ones kept) so new questions aren't polluted
            ChatStore.newConversation(this@ChatActivity); render()
            Toast.makeText(this@ChatActivity, "New conversation — fresh context.", Toast.LENGTH_SHORT).show()
        })
        top.addView(chatButton("Chats") { showConversationPicker() })
        top.addView(chatButton("Menu") { startActivity(Intent(this@ChatActivity, MainActivity::class.java)) })
        rootCol.addView(top)

        // Prominent power controls: Sleep (-> passive learning only) and Emergency stop.
        powerRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(24, 0, 24, 6)
        }
        rootCol.addView(powerRow)

        scroll = ScrollView(this).apply {
            layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f)
        }
        convo = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(36, 8, 36, 8) }
        scroll.addView(convo)
        rootCol.addView(scroll)

        // Input row: type + Send + mic (verbal conversation mode).
        val inputRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(24, 8, 24, 20)
        }
        input = EditText(this).apply {
            hint = "Message the agent…"
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            setText(ChatStore.draft(this@ChatActivity))
        }
        // Mode toggle: switch the box between "chat with the agent" and "run a command".
        modeBtn = Button(this).apply {
            setOnClickListener {
                commandMode = !commandMode
                applyMode()
                Toast.makeText(this@ChatActivity,
                    if (commandMode) "Command mode — what you send is RUN on the phone."
                    else "Chat mode — talk to the agent.", Toast.LENGTH_SHORT).show()
            }
        }
        val send = Button(this).apply { text = "Send"; setOnClickListener { onSend() }; Ui.styleButton(this, primary = true) }
        val mic = chatButton("Voice") {
            startForegroundService(Intent(this@ChatActivity, AgentService::class.java)
                .setAction(AgentService.ACTION_CONVERSATION))
            Toast.makeText(this@ChatActivity, "Listening — verbal conversation mode.", Toast.LENGTH_SHORT).show()
        }
        Ui.styleButton(modeBtn, primary = false)
        inputRow.addView(modeBtn); inputRow.addView(input); inputRow.addView(send); inputRow.addView(mic)
        applyMode()
        rootCol.addView(inputRow)

        // Conversation tools.
        val tools = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(24, 0, 24, 16) }
        tools.addView(chatButton("Copy conversation") {
            val cm = getSystemService(CLIPBOARD_SERVICE) as android.content.ClipboardManager
            cm.setPrimaryClip(android.content.ClipData.newPlainText("agent chat", ChatStore.asPlainText(this@ChatActivity)))
            Toast.makeText(this@ChatActivity, "Conversation copied", Toast.LENGTH_SHORT).show()
        })
        tools.addView(chatButton("Clear") { ChatStore.clear(this@ChatActivity); render() })
        rootCol.addView(tools)

        setContentView(rootCol)
        refreshPower()
        render()
        // First-run onboarding FROM THE LAUNCHER: the launch crash's root cause was that ChatActivity (the
        // launcher) never requested the mic, so the mic FGS blew up - and even after that fix, voice would
        // stay dead until the owner dug into Menu -> setup. Ask here so a fresh install is fully functional.
        maybeRequestPermissions()
        // If the PREVIOUS launch crashed, show the stored trace as a dismissible popup OVER the now
        // fully-built, working app - NEVER an early return that leaves the activity half-initialized (the
        // bug that caused the endless crash loop). The app always opens; the trace is just informational.
        maybeShowCrashTrace()
    }

    /** Show the previous-launch crash trace (if any) as a dismissible dialog over the working app, then
     *  clear it. The app is already fully built and usable underneath - so the viewer can never leave the
     *  activity half-initialized or block launch. The trace is also mirrored to last_crash.txt by AgentApp. */
    private fun maybeShowCrashTrace() {
        val trace = try {
            val cp = getSharedPreferences("agent_crash", MODE_PRIVATE)
            val t = cp.getString("last", null)
            if (t != null) cp.edit().remove("last").commit()
            t
        } catch (_: Throwable) { null } ?: return
        try {
            val tv = TextView(this).apply {
                text = "The app crashed on the previous launch. Screenshot this and send it to Claude — " +
                    "then just keep using the app.\n\n$trace"
                setTextIsSelectable(true); setPadding(40, 32, 40, 32); textSize = 11f
            }
            androidx.appcompat.app.AlertDialog.Builder(this)
                .setTitle("Previous crash (the app still works)")
                .setView(ScrollView(this).apply { addView(tv) })
                .setPositiveButton("Dismiss", null)
                .show()
        } catch (_: Throwable) {}
    }

    /** A secondary-styled button for the chat chrome (modern flat look, sentence case). */
    private fun chatButton(label: String, onClick: () -> Unit) = Button(this).apply {
        text = label
        setOnClickListener { onClick() }
        Ui.styleButton(this, primary = false)
    }

    /** Sleep + Emergency-stop (when active) or Wake (when asleep/stopped), side by side. */
    private fun refreshPower() {
        powerRow.removeAllViews()
        fun cell(label: String, danger: Boolean = false, onClick: () -> Unit) = Button(this).apply {
            text = label
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                .apply { setMargins(0, 0, 16, 0) }
            setOnClickListener { onClick() }
            Ui.styleButton(this, primary = false)
            if (danger) setTextColor(Ui.DANGER)
        }
        if (AgentControl.isActive(this)) {
            powerRow.addView(cell("Sleep") {
                AgentControl.sleep(this)
                Toast.makeText(this, "Sleeping — passively learning. Tap Wake to use me.", Toast.LENGTH_SHORT).show()
                refreshPower()
            })
            powerRow.addView(cell("Emergency stop", danger = true) { confirmStop() })
        } else {
            powerRow.addView(cell("Wake agent") {
                AgentControl.wake(this)
                Toast.makeText(this, "Waking up…", Toast.LENGTH_SHORT).show()
                refreshPower()
            })
        }
    }

    private fun confirmStop() {
        androidx.appcompat.app.AlertDialog.Builder(this)
            .setTitle("Emergency stop?")
            .setMessage("Shuts the model down and stops everything, including passive learning.")
            .setNegativeButton("Cancel", null)
            .setPositiveButton("Stop") { _, _ ->
                AgentControl.emergencyStop(this)
                Toast.makeText(this, "Stopped. Model shut down.", Toast.LENGTH_SHORT).show()
                refreshPower()
            }
            .show()
    }

    override fun onResume() {
        super.onResume()
        ensureServices()
        // Warm the model up now (and arm idle-release) so the first reply isn't the cold-start
        // wait, but the model still frees itself to save battery once the chat goes idle.
        AgentService.instance?.warmBrain()
        maybeCalibrate()
        input.setText(ChatStore.draft(this))
        input.setSelection(input.text.length)
        refreshPower()
        render()
    }

    /** STARTUP CALIBRATION: when enabled, calibrate to this owner/device once per app start (and after a model
     *  swap). Only fires with a model present and calibration stale for the active model; gated once-per-process
     *  so it never loops. Flag OFF (default) => nothing happens => cold boot as today. */
    private fun maybeCalibrate() {
        if (calibratePrompted) return
        try {
            val s = SettingsManager(this)
            if (!s.isStartupCalibrationEnabled() || s.getModelPath().isNullOrBlank()) return
            val fp = ModelStore.activeFingerprint(this, s)
            if (!AgentMemory.needsCalibration(this, fp)) return
            calibratePrompted = true
            startActivity(android.content.Intent(this, CalibrationActivity::class.java))
        } catch (_: Throwable) {}
    }

    /** Bring up the agent service (holds the brain the chat talks to) and the floating button
     *  when the agent is enabled - since this is now the launcher screen, not MainActivity. */
    private fun ensureServices() {
        val settings = SettingsManager(this)
        if (!settings.isAgentEnabled()) return
        try { startForegroundService(Intent(this, AgentService::class.java)) } catch (_: Exception) {}
        if (android.provider.Settings.canDrawOverlays(this)) {
            try { startService(Intent(this, FloatingButtonService::class.java)) } catch (_: Exception) {}
        }
    }

    /** Request the runtime permissions the agent needs (mic for voice/wake word; notifications on 13+ so the
     *  Stop control is visible) once, from the launcher. Non-blocking - the chat is already usable while the
     *  prompt is up, and denial just leaves voice off (the app still works). Reuses the same permission as
     *  MainActivity's setup so there's one source of truth. */
    private fun maybeRequestPermissions() {
        val needed = mutableListOf<String>()
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED)
            needed.add(Manifest.permission.RECORD_AUDIO)
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED)
            needed.add(Manifest.permission.POST_NOTIFICATIONS)
        if (needed.isNotEmpty())
            try { ActivityCompat.requestPermissions(this, needed.toTypedArray(), REQ_PERMS) } catch (_: Exception) {}
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != REQ_PERMS) return
        // If RECORD_AUDIO was just granted, tell the running service to rebuild the mic pipeline and promote
        // its FGS from SPECIAL_USE to the microphone type - so voice/wake word start immediately, no restart.
        val micIdx = permissions.indexOf(Manifest.permission.RECORD_AUDIO)
        if (micIdx in grantResults.indices && grantResults[micIdx] == PackageManager.PERMISSION_GRANTED)
            AgentService.instance?.applyMicSetting()
    }

    companion object {
        private const val REQ_PERMS = 7001
        @Volatile private var calibratePrompted = false   // startup calibration fires at most once per process
    }

    override fun onPause() {
        super.onPause()
        ChatStore.saveDraft(this, input.text.toString())
    }

    /** Reflect the current mode in the toggle button + input hint. */
    private fun applyMode() {
        modeBtn.text = if (commandMode) "Run" else "Chat"
        input.hint = if (commandMode) "Command to run on the phone…" else "Message the agent…"
    }

    /** Command mode: what the owner types is run as a phone task (and returns to chat when done). */
    private fun runAsCommand(cmd: String) {
        ChatStore.add(this, "you", cmd)
        input.setText(""); ChatStore.saveDraft(this, "")
        ChatStore.add(this, "agent", "Thinking… — on it now, I'll come back here when done. Tap the floating button to stop me.")
        render()
        startForegroundService(Intent(this, AgentService::class.java)
            .setAction(AgentService.ACTION_RUN_COMMAND)
            .putExtra(AgentService.EXTRA_COMMAND, cmd)
            .putExtra(AgentService.EXTRA_FROM_CHAT, true))
    }

    private fun onSend() {
        if (commandMode) {
            val c = input.text.toString().trim()
            if (c.isNotEmpty()) runAsCommand(c)
            return
        }
        if (thinking) { Toast.makeText(this, "One sec — still thinking.", Toast.LENGTH_SHORT).show(); return }
        val msg = input.text.toString().trim()
        if (msg.isEmpty()) return
        // Conversation BEFORE this turn (so we don't double-add the new message on rebuild).
        val priorHistory = ChatStore.messages(this).map { it.role to it.text }
        ChatStore.add(this, "you", msg)
        input.setText(""); ChatStore.saveDraft(this, "")
        render()

        val brain = AgentService.instance?.brainOrNull()
        if (brain == null) {
            ensureServices() // start warming the model up
            ChatStore.add(this, "agent", "My model isn't up yet — I'm starting it. Give me a few seconds, then send that again. (If it never comes up, open Menu → make sure the agent is on and a model is set.)")
            render(); return
        }
        AgentService.instance?.warmBrain(activeChat = true)   // a live chat turn - hold the model across the conversation, not just 30s
        thinking = true
        ChatStore.add(this, "agent", "Thinking…"); render()
        // Don't feed the agent its OWN chat UI as "the screen" - that made it analyze its own Send
        // button and report it as a struggle. When we're the foreground app, there's no task screen.
        val acc = ActionAccessibilityService.instance
        val screen = if (acc?.currentPackage() == packageName)
            "(Your own chat app is in the foreground - there is no task screen right now.)"
            else acc?.snapshotScreen().orEmpty()
        val memory = AgentMemory.forPrompt(this)
        val tasks = TaskHistory.list(this).take(8).joinToString("\n") {
            "• \"${it.objective.take(70)}\" → ${it.outcome}${if (it.note.isNotBlank()) " (you noted: ${it.note})" else ""}"
        }
        val recentLog = AgentLog.tail(60)
        brain.chat(priorHistory, msg, screen, memory, tasks, recentLog) { reply ->
            runOnUiThread {
                thinking = false
                // Replace the "…" placeholder with the real reply (rebuild from prior + this turn).
                ChatStore.clear(this)
                priorHistory.forEach { (r, t) -> ChatStore.add(this, r, t) }
                ChatStore.add(this, "you", msg)
                val cleaned = captureLearned(reply)
                val (body, run) = splitRun(cleaned)
                ChatStore.add(this, "agent", body.ifBlank { "(no reply)" })
                render()
                if (run.isNotBlank()) proposeAction(run)
            }
        }
    }

    /** Pull any "LEARN: ..." lines the agent emitted (durable facts/knowledge it picked up from the
     *  conversation), persist them to memory, and return the reply with those lines removed so they're
     *  never shown in the chat. "LEARN: key = value" stores a fact; "LEARN: <text>" stores a lesson. */
    private fun captureLearned(reply: String): String {
        val kept = ArrayList<String>()
        for (line in reply.lines()) {
            val m = Regex("^\\s*LEARN:\\s*(.+)$", RegexOption.IGNORE_CASE).find(line)
            if (m == null) { kept.add(line); continue }
            val item = m.groupValues[1].trim()
            if (item.length < 3) continue
            val eq = item.indexOf('=')
            if (eq in 1 until item.length - 1)
                AgentMemory.setFact(this, item.substring(0, eq).trim(), item.substring(eq + 1).trim())
            else
                AgentMemory.addLesson(this, item)
        }
        return kept.joinToString("\n").trim()
    }

    private fun splitRun(reply: String): Pair<String, String> {
        val idx = reply.lastIndexOf("RUN:")
        if (idx < 0) return reply.trim() to ""
        val run = reply.substring(idx + 4).trim()
        val body = reply.substring(0, idx).trim()
        return body to (if (run.equals("none", true) || run.isBlank()) "" else run)
    }

    /** Ask-before-acting: the agent proposes a phone task; nothing runs until you confirm. */
    private fun proposeAction(command: String) {
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(36, 4, 36, 12) }
        row.addView(TextView(this).apply {
            text = "Run on phone: “$command”?"
            textSize = 13f; setTextColor(0xFFFFC107.toInt())
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
        })
        row.addView(Button(this).apply {
            text = "Run it"
            setOnClickListener {
                startForegroundService(Intent(this@ChatActivity, AgentService::class.java)
                    .setAction(AgentService.ACTION_RUN_COMMAND)
                    .putExtra(AgentService.EXTRA_COMMAND, command)
                    .putExtra(AgentService.EXTRA_FROM_CHAT, true))
                ChatStore.add(this@ChatActivity, "agent", "On it — running \"$command\". I'll come back here when I'm done. Tap the floating button to stop me.")
                convo.removeView(row); render()
            }
        })
        row.addView(Button(this).apply { text = "Not now"; setOnClickListener { convo.removeView(row) } })
        convo.addView(row)
        scrollToEnd()
    }

    /** Switch between saved conversations (old threads are kept, not deleted). */
    private fun showConversationPicker() {
        val convos = ChatStore.conversations(this)
        if (convos.isEmpty()) { ChatStore.newConversation(this); render(); return }
        val curId = ChatStore.currentId(this)
        val labels = convos.map { (if (it.id == curId) "● " else "") + it.title + "  (${it.count})" }.toTypedArray()
        androidx.appcompat.app.AlertDialog.Builder(this)
            .setTitle("Conversations")
            .setItems(labels) { _, i -> ChatStore.switchTo(this, convos[i].id); render() }
            .setPositiveButton("New") { _, _ -> ChatStore.newConversation(this); render() }
            .setNegativeButton("Close", null)
            .show()
    }

    private fun render() {
        convo.removeAllViews()
        for (m in ChatStore.messages(this)) {
            convo.addView(TextView(this).apply {
                text = if (m.role == "you") "You" else "Agent"
                textSize = 11f
                setTypeface(typeface, Typeface.BOLD)
                setTextColor(if (m.role == "you") Ui.TEXT_DIM else Ui.TEXT)
                setPadding(0, 14, 0, 2)
            })
            convo.addView(TextView(this).apply {
                text = m.text
                textSize = 15f
                setTextIsSelectable(true)
            })
        }
        scrollToEnd()
    }

    private fun scrollToEnd() = scroll.post { scroll.fullScroll(ScrollView.FOCUS_DOWN) }
}
