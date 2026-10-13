package com.local.deviceagent

import android.animation.ValueAnimator
import android.annotation.SuppressLint
import android.app.Service
import android.content.Intent
import android.graphics.PixelFormat
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.SystemClock
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import android.view.WindowManager
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import kotlin.math.abs

/**
 * Overlay mic button. Tap while idle = start listening; tap while a task is running = END
 * the agent; long-press = open a text box to type a command (no need to open the app).
 * Draggable so the user can move it off whatever it's covering, and translucent.
 */
class FloatingButtonService : Service() {

    private lateinit var windowManager: WindowManager
    private lateinit var floatingView: View
    private var commandBox: View? = null
    private var menuView: View? = null
    // True while the agent is recording a teaching demonstration - the button becomes "finish".
    private var recordingMode = false
    // True while we've pulled the button off-screen for a permission/install dialog (see companion):
    // an overlay window makes Android disable that dialog's Allow button ("screen overlay detected").
    private var overlayHidden = false

    companion object {
        @Volatile private var instance: FloatingButtonService? = null

        /** Called on every foreground-app change. While a runtime PERMISSION or package-installer
         *  dialog is up, our overlay button blocks its Allow button, so temporarily remove the
         *  overlay; restore it the moment anything else comes forward. Helps BOTH the owner and the
         *  agent actually grant permissions. */
        fun reactToForeground(pkg: String?) {
            val p = pkg ?: return
            val isPermissionUi = p.contains("permissioncontroller") || p.contains("packageinstaller")
            val self = instance ?: return
            self.ui.post { self.setOverlayHidden(isPermissionUi) }
        }

        /** NEVER-SLEEP: turn the overlay's FLAG_KEEP_SCREEN_ON on/off live (the keep-awake tick calls this — ON while
         *  safe, OFF at the device-safety floor so a critical battery can still let the screen sleep). Main-thread. */
        fun keepScreenOn(on: Boolean) {
            val self = instance ?: return
            self.ui.post { self.setKeepScreenOn(on) }
        }
    }

    private fun setKeepScreenOn(on: Boolean) {
        val f = if (on) params.flags or WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
                else params.flags and WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON.inv()
        if (f == params.flags) return
        params.flags = f
        try {
            if (::floatingView.isInitialized && floatingView.isAttachedToWindow)
                windowManager.updateViewLayout(floatingView, params)
        } catch (_: Exception) {}
    }

    private fun setOverlayHidden(hidden: Boolean) {
        if (hidden == overlayHidden) return
        overlayHidden = hidden
        try {
            if (hidden) {
                dismissMenu(); dismissCommandBox()
                if (::floatingView.isInitialized && floatingView.isAttachedToWindow)
                    windowManager.removeView(floatingView)
            } else if (::floatingView.isInitialized && !floatingView.isAttachedToWindow) {
                windowManager.addView(floatingView, params)
            }
        } catch (_: Exception) {}
    }
    private val params = WindowManager.LayoutParams(
        150, 150,
        WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
        WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
        PixelFormat.TRANSLUCENT
    )

    private val ui = Handler(Looper.getMainLooper())
    private var pulsing = false
    private val pulseAnimator by lazy {
        ValueAnimator.ofFloat(0.45f, 0.95f).apply {
            duration = 650L
            repeatMode = ValueAnimator.REVERSE
            repeatCount = ValueAnimator.INFINITE
            addUpdateListener { a -> floatingView.alpha = a.animatedValue as Float }
        }
    }

    // Poll the busy flag and pulse the button (+ active accent colour) while a task
    // runs - an on-screen, TEXT-FREE "I'm working" cue. Nothing is drawn over the
    // user's actual screen; only the agent's own button changes.
    private val busyWatcher = object : Runnable {
        override fun run() {
            // Resilience: if the overlay got detached (system reclaimed it under memory pressure
            // while the big model loaded, or another overlay replaced it), put it back so the
            // button never silently disappears.
            if (!overlayHidden && ::floatingView.isInitialized && !floatingView.isAttachedToWindow) {
                try { windowManager.addView(floatingView, params) } catch (_: Exception) {}
            }
            val recording = ActionAccessibilityService.instance?.recording == true
            val busy = AgentService.isAgentBusy && !recording
            // Recording (teaching) takes priority: the button becomes a "finish" control.
            if (recording && !recordingMode) {
                recordingMode = true
                pulsing = false; pulseAnimator.cancel()
                floatingView.alpha = 1f
                floatingView.setBackgroundColor(0xCCAB47BC.toInt())   // purple = teaching
                (floatingView as? Button)?.text = "● fin"
            } else if (!recording && recordingMode) {
                recordingMode = false
                floatingView.setBackgroundColor(0xCC000000.toInt())
                floatingView.alpha = 0.7f
                (floatingView as? Button)?.text = "🎙️"
            }
            if (!recording) {
                if (busy && !pulsing) {
                    pulsing = true
                    floatingView.setBackgroundColor(0xCC1E88E5.toInt())
                    (floatingView as? Button)?.text = "🧠"   // "I'm thinking / making progress"
                    pulseAnimator.start()
                } else if (!busy && pulsing) {
                    pulsing = false
                    pulseAnimator.cancel()
                    floatingView.setBackgroundColor(0xCC000000.toInt())
                    floatingView.alpha = 0.7f
                    (floatingView as? Button)?.text = "🎙️"
                }
            }
            ui.postDelayed(this, 400L)
        }
    }

    @SuppressLint("ClickableViewAccessibility")
    override fun onCreate() {
        super.onCreate()
        instance = this
        windowManager = getSystemService(WINDOW_SERVICE) as WindowManager

        floatingView = Button(this).apply {
            text = "🎙️"
            setBackgroundColor(0xCC000000.toInt())
            alpha = 0.7f
        }

        params.gravity = Gravity.TOP or Gravity.START
        params.x = resources.displayMetrics.widthPixels - 160
        params.y = 300
        // NEVER-SLEEP (owner): the always-present STOP overlay carries FLAG_KEEP_SCREEN_ON while keep_awake is on,
        // so the screen never turns off and the device never suspends. Set here (base context is attached in
        // onCreate, unlike the field initializer). The keep-awake tick toggles it off at the battery/thermal floor.
        try {
            if (SettingsManager(this).isKeepAwakeEnabled())
                params.flags = params.flags or WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
        } catch (_: Exception) {}

        var downRawX = 0f
        var downRawY = 0f
        var startX = 0
        var startY = 0
        var downTime = 0L
        var dragging = false
        val slop = ViewConfiguration.get(this).scaledTouchSlop

        floatingView.setOnTouchListener { _, e ->
            when (e.action) {
                MotionEvent.ACTION_DOWN -> {
                    downRawX = e.rawX; downRawY = e.rawY
                    startX = params.x; startY = params.y
                    downTime = SystemClock.uptimeMillis()
                    dragging = false
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = e.rawX - downRawX
                    val dy = e.rawY - downRawY
                    if (!dragging && (abs(dx) > slop || abs(dy) > slop)) dragging = true
                    if (dragging) {
                        params.x = startX + dx.toInt()
                        params.y = startY + dy.toInt()
                        windowManager.updateViewLayout(floatingView, params)
                    }
                    true
                }
                MotionEvent.ACTION_UP -> {
                    if (!dragging) {
                        val held = SystemClock.uptimeMillis() - downTime
                        when {
                            recordingMode -> {
                                // Tap while teaching = finish the demonstration and learn from it.
                                floatingView.alpha = 1f
                                send(AgentService.ACTION_TRAIN_FINISH)
                            }
                            held >= ViewConfiguration.getLongPressTimeout() ->
                                showCommandBox() // hold: type a command (no app needed)
                            AgentService.isAgentBusy -> {
                                // Tap while running = END THIS TASK (not kill the whole agent). Give
                                // INSTANT visual feedback - the agent may take a moment to abandon an
                                // in-flight think, so the press must never feel ignored. busyWatcher
                                // resets the icon when the task ends.
                                pulseAnimator.cancel()
                                floatingView.alpha = 1f
                                floatingView.setBackgroundColor(0xCCD32F2F.toInt())
                                (floatingView as? Button)?.text = "✋"
                                // STOP_TASK (not STOP): ends the current task, LOGS it to the task log
                                // (the owner's "mic-to-end doesn't show up in the task log" bug - STOP
                                // called stopSelf() and skipped logging), and returns to idle/listening
                                // so the agent stays available for the next command.
                                send(AgentService.ACTION_STOP_TASK)
                            }
                            // Idle tap = a small menu: verbal input, conversation, or train.
                            else -> toggleMenu()
                        }
                    }
                    true
                }
                else -> false
            }
        }

        windowManager.addView(floatingView, params)
        ui.post(busyWatcher)
    }

    private fun send(action: String) {
        startForegroundService(Intent(this, AgentService::class.java).setAction(action))
    }

    /** Idle tap -> a small, light menu: verbal input, conversation mode, or train. Always one
     *  tap away, so teaching is at hand from any app - and picking Train starts recording RIGHT
     *  AWAY, so you go straight to the task instead of navigating to a Train screen first (which
     *  would pollute the captured demonstration). */
    private fun toggleMenu() {
        if (menuView != null) { dismissMenu(); return }
        dismissCommandBox()
        fun item(label: String, onClick: () -> Unit) = Button(this).apply {
            text = label
            setBackgroundColor(0xFF202020.toInt())
            setTextColor(0xFFFFFFFF.toInt())
            setOnClickListener { onClick() }
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)
        }
        val menu = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(0xF0101010.toInt())
            setPadding(8, 8, 8, 8)
            addView(item("⌨  Text chat") { dismissMenu(); openChat() })
            // Run a one-off command from an on-screen field, no app to open (same box as the button's
            // long-press, surfaced in the menu so it's discoverable). The overlay works from ANY app.
            addView(item("⚡  Run command") { dismissMenu(); showCommandBox() })
            addView(item("🎙  Verbal input") { dismissMenu(); send(AgentService.ACTION_LISTEN_NOW) })
            addView(item("💬  Conversation") { dismissMenu(); send(AgentService.ACTION_CONVERSATION) })
            addView(item("🎓  Train") { dismissMenu(); showTrainBox() })
        }
        val screenH = resources.displayMetrics.heightPixels
        val screenW = resources.displayMetrics.widthPixels
        val menuEstH = 775   // ~5 items; used to decide above/below so it never runs off-screen
        // Place the menu BELOW the button if it fits, otherwise ABOVE it - and never overlapping
        // the button (so the button can't get trapped underneath the menu and become un-tappable).
        val below = params.y + 170
        val menuY = if (below + menuEstH <= screenH) below else (params.y - menuEstH - 10).coerceAtLeast(0)
        val p = WindowManager.LayoutParams(
            520, WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = maxOf(0, minOf(params.x, screenW - 520))
            y = menuY
        }
        menuView = menu
        try { windowManager.addView(menu, p) } catch (_: Exception) { menuView = null }
    }

    private fun dismissMenu() {
        menuView?.let { try { windowManager.removeView(it) } catch (_: Exception) {} }
        menuView = null
    }

    private fun openChat() {
        startActivity(Intent(this, ChatActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }

    /** Long-press the button -> type a one-off command (no app needed). */
    private fun showCommandBox() = showInputBox("Type a command for the agent…", "Send") { cmd ->
        if (cmd.isNotEmpty())
            startForegroundService(Intent(this, AgentService::class.java)
                .setAction(AgentService.ACTION_RUN_COMMAND)
                .putExtra(AgentService.EXTRA_COMMAND, cmd))
    }

    /** Train -> name what you're teaching, then start recording immediately (before navigating). */
    private fun showTrainBox() = showInputBox("What do you want to teach me?", "Start") { goal ->
        startForegroundService(Intent(this, AgentService::class.java)
            .setAction(AgentService.ACTION_TRAIN_START)
            .putExtra(AgentService.EXTRA_GOAL, goal))
    }

    /** A focusable text box docked above the keyboard. [onSubmit] receives the trimmed text. */
    @SuppressLint("ClickableViewAccessibility")
    private fun showInputBox(hint: String, submitLabel: String, onSubmit: (String) -> Unit) {
        if (commandBox != null) { dismissCommandBox(); return }
        val input = EditText(this).apply {
            this.hint = hint
            setBackgroundColor(0xFFFFFFFF.toInt())
            setTextColor(0xFF000000.toInt()); setHintTextColor(0xFF888888.toInt())
            setPadding(24, 24, 24, 24)
        }
        val sendBtn = Button(this).apply { text = submitLabel }
        val closeBtn = Button(this).apply { text = "✕" }
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setBackgroundColor(0xEE202020.toInt())
            setPadding(16, 16, 16, 16)
            addView(input, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
            addView(sendBtn); addView(closeBtn)
        }
        val p = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL, // focusable (no NOT_FOCUSABLE) so the keyboard works
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.BOTTOM
            softInputMode = WindowManager.LayoutParams.SOFT_INPUT_STATE_VISIBLE or
                WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE
        }
        val submit = { onSubmit(input.text.toString().trim()); dismissCommandBox() }
        sendBtn.setOnClickListener { submit() }
        closeBtn.setOnClickListener { dismissCommandBox() }
        input.setOnEditorActionListener { _, _, _ -> submit(); true }
        commandBox = root
        try { windowManager.addView(root, p); input.requestFocus() } catch (_: Exception) { commandBox = null }
    }

    private fun dismissCommandBox() {
        commandBox?.let { try { windowManager.removeView(it) } catch (_: Exception) {} }
        commandBox = null
    }

    override fun onDestroy() {
        instance = null
        ui.removeCallbacks(busyWatcher)
        pulseAnimator.cancel()
        dismissCommandBox()
        dismissMenu()
        if (::floatingView.isInitialized && floatingView.isAttachedToWindow)
            try { windowManager.removeView(floatingView) } catch (_: Exception) {}
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
