package com.local.deviceagent

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.ContentValues
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Environment
import android.provider.MediaStore
import android.graphics.Bitmap
import android.graphics.Path
import android.graphics.PointF
import android.graphics.Rect
import android.os.Build
import android.os.Bundle
import android.view.Display
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo
import org.json.JSONObject

/** Reference grid drawn on canvas/game screenshots so the model taps a labeled CELL
 *  (column letter A.. + row number 1..) instead of hallucinating raw pixels. The drawing
 *  (AgentBrain.drawGrid) and the tap mapping (tap_grid here) MUST share these dimensions. */
object GridSpec { const val COLS = 8; const val ROWS = 12 }

/** Set-of-Marks data: the on-screen bounds (in screen pixels) of each interactive element,
 *  index-aligned with the `[N]` ids in the element list. The brain draws the matching number
 *  on each element in the screenshot so the model taps a label it can SEE (kills id/pixel
 *  hallucination - the #1 grounding failure). [screenW]/[screenH] let it scale to the image. */
data class ScreenMarks(val screenW: Int, val screenH: Int, val boxes: List<Rect>, val ids: List<Int> = emptyList())

enum class ActionResult { CONTINUE, DONE, FAILED, WAIT, ASK }
data class ActionOutcome(
    val result: ActionResult,
    val say: String?,
    val summary: String,
    val question: String? = null,
    // W4 (owner: "malformed json or whatever shouldn't be REJECTED, but KICKED BACK to the operator"):
    // FAILED only. true (default) = a fixable improper call (unparseable/off-list/off-target) the loop hands
    // straight back to the model to correct - a strong corrective steer + it does NOT count toward the
    // stuck/stop caps for a bounded number of tries, so a JSON fumble can never REJECT/dead-end the task.
    // false = a SOVEREIGN §3 refusal (ChatGPT/OS-update/code-exec/self-repo) where a REPEATED attempt SHOULD
    // escalate normally, not be coddled - the one place code stops the action outright stays sovereign (§3).
    val kickback: Boolean = true
)

class ActionAccessibilityService : AccessibilityService() {

    companion object {
        var instance: ActionAccessibilityService? = null
        // Stop hunting the app drawer after this many paging steps - paging forever is a
        // dead end; open_app (exact name) or the drawer's Search field is the reliable way.
        private const val DRAWER_PAGE_CAP = 6
        // The agent sees at most this many interactive elements at once (the owner: "a fixed number,
        // and move to the next set to find what it needs without seeing them all"). A busy screen is
        // paged instead of dumped whole - bounds the prompt and lets the agent search set by set.
        private const val ELEMENT_PAGE_SIZE = 20
        // Send strategies at/after this index are GEOMETRIC (fixed-coordinate, state-
        // dependent): usable as a last resort but NEVER learned/replayed, since the same
        // pixel is the send arrow in one state and Stop/Live/mic in another (the bug Bryce
        // watched stop replies / trigger Live mode). The tree-based strategies before it
        // (labeled button, trailing send icon, Enter key) re-derive from the live UI, so
        // they're safe to remember.
        private const val GEOMETRIC_SEND_FROM = 3
        // Char budget for the text screen snapshot. ~1300 chars keeps the element list + a screenshot
        // under the model's 4096-token input limit even on a DENSE screen (a 38-48 icon launcher used
        // to overflow WITH the image - and even text-only - which stalled the agent into endless
        // "wait"). The screenshot carries the visual; the list just supplies ids, so a tighter cap is
        // the right trade. (Paired with leaner instructions and dropping memory hints on dense screens.)
        private const val MAX_SNAPSHOT_CHARS = 1300
        // We COLLECT up to this many interactive nodes into currentNodes (for find/click RESOLUTION and
        // paging), even though only ELEMENT_PAGE_SIZE are RENDERED/badged per page. The old 60-node cap
        // aborted the whole tree WALK at 60, so a real visible control at position 61+ was unfindable -
        // a silent "never make a control inaccessible" violation. The token budget is protected by what's
        // RENDERED, not by refusing to look, so the collection cap can be generous.
        private const val MAX_NODES = 200
        // Max strokes drawn in ONE sketch gesture. The platform HARD-caps a GestureDescription at 10 strokes
        // (GestureDescription.getMaxStrokeCount()); addStroke throws past that and the whole figure fails to
        // draw. Stay AT the cap so a chunk dispatches the most strokes it safely can (more = "add the rest
        // next", the model continues from the partial drawing it can see). Was 16 — an out-of-range crash.
        private const val MAX_SKETCH_STROKES = 10
        // `reveal` scrolls at most this many steps to bring a named target into view before giving up -
        // BOUNDED so the deterministic seek can never loop (it also stops early the moment a scroll moves
        // nothing, i.e. the list's edge).
        private const val REVEAL_CAP = 5
    }

    /** Trim a label to [max] chars with an ellipsis, collapsing internal newlines. */
    private fun clip(s: String, max: Int): String {
        val one = s.replace('\n', ' ').trim()
        return if (one.length <= max) one else one.take(max) + "…"
    }

    private val currentNodes = mutableListOf<AccessibilityNodeInfo>()
    // A2: the exact element ids RENDERED as text lines this snapshot (post-paging, post-collapse), in
    // render order. currentMarks() badges EXACTLY these, so a homogeneous-collapsed row or a budget-cut
    // node is never badged without a matching [N] line (the off-page-badge bug). ONE source of truth for
    // "what the model sees as a numbered line" - both the list and the set-of-marks read it.
    private val lastRenderedIds = ArrayList<Int>()
    // LANG: the read-only EXACT-value layer (carrying-clipboard + TEXT ON SCREEN) that snapshotScreen appends
    // but codecScreen() would otherwise drop. codecScreen re-appends it so codec mode keeps the zero-
    // hallucination exact text (which the compact handles omit and get_text/find can't recover verbatim).
    private var lastValueLayer: String = ""
    // Set during snapshotScreen's walk when a visible INDETERMINATE progress spinner is seen, so
    // loadingHint() can warn the agent a screen is still loading WITHOUT a second tree walk (the walk
    // already visits every node). Determinate bars (downloads/sliders, which expose a range) don't count.
    @Volatile private var sawSpinner = false
    // AFFORDANCE-TAG DEDUP (owner's OOM log: a launcher grid put the SAME [long-press]/[do:…] tag-set on
    // all ~15 icons = ~200 tokens of pure repetition that pushed every prompt past the 4096 ceiling and
    // forced the lean-retry path each step). The first element with a given tag-set shows it; identical
    // repeats are hidden and one footer line says the options apply to the items above - organize, never
    // delete (`do` with no name still lists any element's actions). Both reset per snapshot.
    private val seenAffordanceTags = HashSet<String>()
    private var affordanceTagsSuppressed = false
    // Agent-carried value for moving DATA BETWEEN APPS (owner's "use the clipboard"). Stored here (not
    // just the system clipboard) so `paste` re-types it reliably - immune to Android's background
    // clipboard-read limits. Mirrored to the system clipboard on copy so other apps can use it too.
    private var carriedText: String? = null
    /** Forget the carried clipboard value (called at task start so a stale carry can't bleed in). */
    fun clearCarried() { carriedText = null; stash.clear() }
    // STASH - the pragmatic version of the owner's "dynamic context windows" on 4GB of RAM: the agent
    // PARKS bulky info outside its context window under a named key (search results, a gathered list,
    // an error message) and pulls it back only when it needs it. One model, one KV cache - but the
    // context stays small because the data lives HERE, not in the prompt. Task-scoped (cleared with
    // the carry at task start), capped so it can't grow unbounded.
    private val stash = LinkedHashMap<String, String>()
    /** True while we're carrying a value to move between apps (so the engine can tell the retrieve
     *  phase from the deliver phase on a cross-app data task). */
    fun isCarrying(): Boolean = !carriedText.isNullOrBlank()
    /** The carried value the EVIDENCE gate treats as grounded evidence (what the agent read/copied). */
    fun carriedValue(): String = carriedText.orEmpty()
    // Captured DATA buffer (the owner's "read a spreadsheet too big to view at once - break it into
    // parts, capture ALL of it, but don't throttle the phone"). The agent sweeps a big data surface
    // chunk by chunk; the `capture` action appends each chunk's EXACT visible text here, OUTSIDE the
    // prompt - so everything accumulates without any one step being huge or hallucinated. Deduped and
    // hard-capped so a giant sheet can't exhaust RAM; cleared at task start.
    private val collectedData = LinkedHashSet<String>()
    fun clearCollected() { collectedData.clear() }
    fun collectedCount(): Int = collectedData.size
    fun collectedDataText(): String = collectedData.joinToString("\n")
    /** Append every visible on-screen text value to the captured-data buffer (exact, deduped). Returns
     *  how many NEW values this call added, so the agent knows whether scrolling revealed fresh data
     *  (keep going) or it's seen everything (done). */
    fun captureVisibleData(): Int {
        val root = rootInActiveWindow ?: return 0
        val before = collectedData.size
        fun walk(n: AccessibilityNodeInfo) {
            if (collectedData.size >= 4000) return        // hard cap: a runaway sheet can't exhaust RAM
            if (n.isVisibleToUser) {
                val t = n.text?.toString()?.trim()
                if (!t.isNullOrEmpty() && t.length <= 200) collectedData.add(t)
            }
            for (i in 0 until n.childCount) n.getChild(i)?.let { walk(it) }
        }
        walk(root)
        return collectedData.size - before
    }
    /** Total ms the last dispatched sketch gesture will take to play out. The orchestrator waits this
     *  long before finishing a procedural drawing, so a multi-stroke figure isn't cut off mid-draw
     *  (the owner's "it stopped part way through - one whisker"). */
    @Volatile var lastSketchDurationMs: Long = 0L
    // Set by the orchestrator when we're in a drawing canvas with the pen ready. Lets the click
    // executor REFUSE guaranteed-waste taps (Insert / Attach / overflow menu) that can never help a
    // drawing - the owner: "it shouldn't even try stuff that logically makes no sense, like checking
    // the menu instead of drawing". Pen / color / eraser / undo stay allowed.
    var drawingMode = false
    private val settings by lazy { SettingsManager(this) }
    // Artifacts the agent CREATED during the current task (logins recorded, notes/files saved), so
    // the service can tell the owner exactly what was produced when it returns to chat. Reset at the
    // start of each task by the service.
    val createdArtifacts = mutableListOf<String>()
    // Consecutive app_drawer requests. The FIRST opens the drawer; further ones
    // page through it (re-opening would just jump back to the top, which is why the
    // agent used to get stuck seeing the same apps forever). Reset by any other action.
    private var drawerSteps = 0
    // Which page of the element list the agent is viewing (ELEMENT_PAGE_SIZE per page). next_page/
    // prev_page move it; ANY real action resets it to 0 so a fresh screen always starts at the top.
    private var elementPage = 0
    // Turn-taking memory: the exact text we last pushed via Send, and when. Lets the
    // executor itself (not the easily-confused model) enforce type→send→WAIT: it won't
    // re-type or re-send a message that's already gone out, and it won't fire Send at an
    // empty box. This is what breaks the "type forever / send-spam" loops in the logs.
    private var lastSentText = ""
    private var lastSentAt = 0L

    // Teach-by-demonstration: while the owner shows us how to do something, we capture the
    // SEMANTIC steps they take (which app, which labelled button/field) - never coordinates -
    // so the model can later generalize them into a reusable skill. Off by default; we only
    // widen our event subscription for the duration of an explicit, owner-started session and
    // restore the idle minimum after, so the "we don't passively monitor" guarantee holds.
    @Volatile var recording = false
        private set
    private val demoSteps = mutableListOf<String>()
    private var lastDemoStep = ""
    private var lastDemoPkg = ""

    // Passive learning (opt-in): when on, we watch how the OWNER navigates (taps + app switches)
    // and record compact navigation facts. Cheap - no model inference, rate-limited, and skipped
    // while the agent itself is driving (so we learn the owner's habits, not our own actions).
    @Volatile var passiveLearning = false
        private set
    private var lastUserTapLabel = ""
    private var lastUserTapApp = ""
    private var lastUserTapAt = 0L
    private var lastObsAt = 0L
    // Live-sight staleness clock (Batch D): the timestamp of the last window/screen SWITCH during an
    // active task (a new activity, dialog, or app coming to front). The orchestrator's staleness gate
    // compares it to a decision's dispatch time so a consequential action never fires blind against a
    // screen that changed DURING the 15-40s decision (§13: never act on a screen you haven't just
    // confirmed). Rides the already-subscribed WINDOW_STATE_CHANGED - zero new monitoring, reads no
    // content (§14). Finer content-level sight is a separate opt-in.
    @Volatile var lastWindowStateChangeAt = 0L

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
        passiveLearning = settings.isPassiveLearningEnabled()
        applyEventSubscription()
        // Make sure the agent knows the phone: if it's never been scanned (fresh install, or the
        // owner skipped the welcome scan), learn the installed apps + device profile now. Local
        // only, runs once, off the UI - so the agent is never blind to what's on the device.
        if (AgentMemory.deviceProfile(this).isBlank() && AgentMemory.deviceApps(this).isEmpty()) {
            Thread { scanAll() }.start()
        }
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null) return
        // Pull the floating overlay off-screen while a permission/install dialog is up, or Android
        // disables its Allow button ("screen overlay detected" - why Chrome wouldn't ask for perms).
        if (event.eventType == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) {
            FloatingButtonService.reactToForeground(event.packageName?.toString())
            // Live-sight staleness clock: while a task runs, note WHEN the window/screen switched, so the
            // orchestrator can catch a consequential action about to fire against a screen that changed
            // during the decision. Timestamp only (§14).
            if (AgentService.isAgentBusy) lastWindowStateChangeAt = System.currentTimeMillis()
        }
        if (recording) recordDemoEvent(event)
        else if (passiveLearning && !AgentService.isAgentBusy) recordPassive(event)
    }
    override fun onInterrupt() {}

    /** Subscribe to exactly the events the current mode needs - and no more (idle = window
     *  changes only, so we never stream taps unless demonstrating or passive-learning). */
    private fun applyEventSubscription() {
        serviceInfo = serviceInfo?.apply {
            eventTypes = when {
                recording -> AccessibilityEvent.TYPE_VIEW_CLICKED or AccessibilityEvent.TYPE_VIEW_LONG_CLICKED or
                    AccessibilityEvent.TYPE_VIEW_SCROLLED or AccessibilityEvent.TYPE_VIEW_TEXT_CHANGED or
                    AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED
                passiveLearning -> AccessibilityEvent.TYPE_VIEW_CLICKED or AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED
                else -> AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED
            }
        }
    }

    /** Toggle passive learning at runtime (from Settings). */
    fun setPassiveLearning(on: Boolean) {
        passiveLearning = on
        applyEventSubscription()
        AgentLog.log("passive", if (on) "passive learning ON" else "passive learning OFF")
    }

    /** Record how the OWNER navigates: a cross-app tap ("tapping X in A opens B") becomes a
     *  reusable navigation fact. Deduped + capped by AgentMemory; rate-limited here. */
    private fun recordPassive(event: AccessibilityEvent) {
        when (event.eventType) {
            AccessibilityEvent.TYPE_VIEW_CLICKED -> {
                val now = System.currentTimeMillis()
                if (now - lastObsAt < 500) return            // rate limit - cheap on battery
                lastObsAt = now
                val app = event.packageName?.toString() ?: return
                // Don't learn "navigation" from taps inside the KEYBOARD, the status bar / System UI,
                // or our own app - those produce nonsense facts ("In Samsung Keyboard, tapping and
                // opens System UI"). Only a tap in a real app or the launcher can teach navigation.
                if (isNoiseSurfacePkg(app)) return
                // Typing into a field is NOT navigation - skip editable sources, or we capture the
                // owner's TYPED TEXT (a whole sentence / a pasted message) as a "button label".
                if (event.source?.isEditable == true) return
                // Just the visible LABEL (e.g. "Chrome"), not the verbose node dump.
                val label = ((event.source?.text ?: event.source?.contentDescription)?.toString()
                    ?: eventText(event)).trim()
                if (isJunkNavLabel(label)) return            // dynamic text / system control = not a button
                lastUserTapLabel = label.take(40); lastUserTapApp = app; lastUserTapAt = now
            }
            AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED -> {
                val app = event.packageName?.toString() ?: return
                // CAUSALITY WINDOW: a tap only OPENS an app if the app appears almost immediately. A
                // window-change long after the tap is a COINCIDENCE - a song auto-advancing, a
                // notification, the owner switching apps by hand - which produced the garbage the owner
                // saw ("tapping Next track opens Google"). 1.2s is generous for a real launch.
                if (lastUserTapLabel.isBlank() || System.currentTimeMillis() - lastUserTapAt > 1200) {
                    lastUserTapLabel = ""; lastUserTapApp = ""; return
                }
                // The window that appeared must be a REAL app we navigated TO. The KEYBOARD popping
                // up, the status bar/recents/PiP (System UI), going HOME (launcher), and our own UI
                // are NOT navigation. Require a launchable destination app, different from the source.
                if (isNoiseSurfacePkg(app) || isLauncherPkg(app)) return
                if (packageManager.getLaunchIntentForPackage(app) == null) return
                if (lastUserTapApp.isNotBlank() && lastUserTapApp != app) {
                    val destLabel = appLabelFor(app)
                    // Skip the TRIVIAL "an app's own icon opens that app" (launcher icon -> its app):
                    // correct but redundant clutter; the agent already opens apps by name.
                    if (isLauncherPkg(lastUserTapApp) &&
                        (lastUserTapLabel.equals(destLabel, true) ||
                         destLabel.contains(lastUserTapLabel, true) ||
                         lastUserTapLabel.contains(destLabel, true))) {
                        lastUserTapLabel = ""; lastUserTapApp = ""; return
                    }
                    // From INSIDE one app to a DIFFERENT app: only believe it if the tapped label
                    // plainly names the destination (a real link/share), e.g. "Open in YouTube" ->
                    // YouTube. Otherwise it's coincidence (a media control, a stray tap) - the bulk of
                    // the cross-app garbage. Launcher taps are exempt (icons legitimately open apps).
                    if (!isLauncherPkg(lastUserTapApp)) {
                        val l = lastUserTapLabel.lowercase(); val d = destLabel.lowercase()
                        val related = d.split(" ").any { it.length > 2 && l.contains(it) } ||
                            l.split(" ").any { it.length > 2 && d.contains(it) }
                        if (!related) { lastUserTapLabel = ""; lastUserTapApp = ""; return }
                    }
                    // SEEN-MORE-THAN-ONCE rule (owner's idea): only COMMIT a navigation fact after
                    // observing it at least twice. A one-off is probably coincidence; a repeat is a
                    // real pattern. The count is PERSISTED (AgentMemory), so a path the owner does once
                    // per session still accumulates and is eventually learned - this filters garbage
                    // WITHOUT permanently blocking legit navigation (the owner's explicit constraint).
                    val candKey = "${lastUserTapApp}|${lastUserTapLabel.lowercase()}|$app"
                    if (!AgentMemory.passiveSightingReached(this, candKey, 2)) {
                        lastUserTapLabel = ""; lastUserTapApp = ""; return
                    }
                    // Same loop as active learning, keyed by the app the owner tapped IN, so the
                    // agent reuses this navigation next time it's in that same app.
                    AgentMemory.addObservation(this,
                        "In ${appLabelFor(lastUserTapApp)}, tapping ${lastUserTapLabel} opens $destLabel",
                        key = lastUserTapApp.substringAfterLast('.'))
                    lastUserTapLabel = ""; lastUserTapApp = ""
                }
            }
        }
    }

    /** The KEYBOARD / IME, the status bar & System UI, and our own app aren't navigation surfaces -
     *  a tap in them or a window change to them teaches nothing useful. */
    private fun isNoiseSurfacePkg(pkg: String): Boolean =
        pkg == packageName ||
        pkg == "com.android.systemui" || pkg.contains("systemui") ||
        pkg.contains("honeyboard") || pkg.contains("inputmethod") || pkg.contains(".ime") ||
        pkg.endsWith(".keyboard") || pkg.endsWith("cocktailbarservice")

    /** Home-screen launchers. OK as the SOURCE of navigation ("tapping YouTube opens YouTube"),
     *  but going TO the launcher is just pressing Home, not navigation - so excluded as a target. */
    private fun isLauncherPkg(pkg: String): Boolean =
        pkg.contains("launcher") || pkg.contains("nexuslauncher") || pkg.contains("trebuchet") ||
        pkg == "com.sec.android.app.launcher"

    /** A real, reusable control label is short and STABLE (e.g. "Chrome", "New tab"). Reject the
     *  owner's typed text, dynamic content (prices, badge counts, versions), and window/media/system
     *  chrome (Pause, Maximize, "Change app aspect ratio", "4 notifications") - storing those as
     *  navigation is exactly the garbage the owner saw. */
    private fun isJunkNavLabel(s: String): Boolean {
        val l = s.lowercase().trim()
        if (l.length < 2 || l.length > 28) return true
        if (s.contains('\n') || s.contains('*') || s.contains('#')) return true
        if (l.split(Regex("\\s+")).size > 4) return true
        // Dynamic / non-stable content: prices, badge counts, versions, clock times, dates - the
        // owner's "variable vs persistent" distinction, so we only learn controls that are always there.
        if (AgentMemory.looksLikeVariableContent(s)) return true
        // Exact-match window/media/system controls (exact so app names like "Google Home" survive).
        val controls = setOf("pause", "play", "stop", "expand", "collapse", "maximize", "minimize",
            "close", "back", "home", "forward", "up", "down", "mute", "unmute", "upgrade", "pay",
            "copy", "paste", "cut", "share", "menu", "settings", "next", "previous", "skip", "done", "cancel")
        if (l in controls) return true
        // STATE-DEPENDENT navigation controls: where these land depends on HISTORY (whatever app
        // was last used / the previous screen), not structure - so "clicking Recents opens
        // ChatGPT" is true one minute and false the next. The owner found memory full of exactly
        // these ("too vague or not always true"); they can never be a navigation fact.
        if (Regex("""^(recents?|recent apps|overview|switch apps?|app drawer|apps|last app)$""").containsMatchIn(l))
            return true
        if (Regex("""aspect ratio|toolbar function|picture.?in.?picture|view details|more options|navigate up|(pause|play|stop) video""").containsMatchIn(l))
            return true
        return false
    }

    override fun onDestroy() {
        instance = null
        super.onDestroy()
    }

    // --- TEACH-BY-DEMONSTRATION + DEVICE SCAN ------------------------------

    /** Start watching the owner's own taps/types/scrolls so we can learn a procedure from a
     *  real demonstration. Widens the event subscription only for this session. */
    fun startDemonstration() {
        demoSteps.clear(); lastDemoStep = ""; lastDemoPkg = ""
        recording = true
        applyEventSubscription()
        AgentLog.log("train", "demonstration recording started")
    }

    /** Stop watching, restore the idle (or passive-learning) subscription, return the steps. */
    fun stopDemonstration(): List<String> {
        recording = false
        applyEventSubscription()
        AgentLog.log("train", "demonstration stopped (${demoSteps.size} steps)")
        return demoSteps.toList()
    }

    private fun recordDemoEvent(event: AccessibilityEvent) {
        val dm = resources.displayMetrics
        val w = dm.widthPixels; val h = dm.heightPixels
        val step: String = when (event.eventType) {
            AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED -> {
                val pkg = event.packageName?.toString() ?: return
                if (pkg == packageName || pkg == lastDemoPkg) return   // skip our own UI / repeats
                lastDemoPkg = pkg
                "open the ${appLabelFor(pkg)} app"
            }
            AccessibilityEvent.TYPE_VIEW_CLICKED, AccessibilityEvent.TYPE_VIEW_LONG_CLICKED -> {
                val verb = if (event.eventType == AccessibilityEvent.TYPE_VIEW_LONG_CLICKED) "long-press" else "tap"
                val label = event.source?.let { describe(it, w, h) }.takeUnless { it.isNullOrBlank() }
                    ?: eventText(event).ifBlank { return }
                "$verb $label"
            }
            AccessibilityEvent.TYPE_VIEW_TEXT_CHANGED -> {
                val t = eventText(event).ifBlank { return }
                "type \"${t.take(80)}\" into the text field"
            }
            AccessibilityEvent.TYPE_VIEW_SCROLLED -> "scroll the screen"
            else -> return
        }
        if (step == lastDemoStep) return
        // Coalesce incremental typing: replace the previous "type ..." with the fuller value.
        if (step.startsWith("type \"") && lastDemoStep.startsWith("type \"") && demoSteps.isNotEmpty()) {
            demoSteps[demoSteps.size - 1] = step
        } else if (demoSteps.size < 40) {
            demoSteps.add(step)
        }
        lastDemoStep = step
    }

    private fun eventText(event: AccessibilityEvent): String =
        event.text?.joinToString(" ") { it?.toString().orEmpty() }?.trim().orEmpty()

    /** Labels of every launchable app installed on this phone (sorted), for the optional
     *  first-run scan that gives the agent a navigation aid. */
    fun scanInstalledApps(): List<String> {
        val pm = packageManager
        val cands = pm.queryIntentActivities(
            Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER), 0)
        return cands.mapNotNull { runCatching { it.loadLabel(pm).toString().trim() }.getOrNull() }
            .filter { it.isNotBlank() }
            .distinct()
            .sortedBy { it.lowercase() }
    }

    /** Full device scan: installed apps + a durable device profile (model / OS / screen + the
     *  DEFAULT app for each common job). Stored in [AgentMemory]. Run from Setup/Train with the
     *  owner's consent, and opportunistically on connect so a fresh install isn't blind. Local
     *  only - nothing leaves the phone. */
    fun scanAll() {
        try {
            val apps = scanInstalledApps()
            AgentMemory.setDeviceApps(this, apps)
            AgentMemory.setDeviceProfile(this, scanDeviceProfile())
            AgentLog.log("scan", "device scan: ${apps.size} apps + profile")
        } catch (e: Exception) {
            AgentLog.log("scan", "scan failed: ${e.message}")
        }
    }

    /** Stable facts about THIS phone (model, Android version, screen, DeX) plus its DEFAULT apps,
     *  so the agent routes correctly instead of guessing (e.g. it learns the real default browser
     *  / texting app on this device). One compact line. */
    fun scanDeviceProfile(): String {
        val sb = StringBuilder()
        val maker = (Build.MANUFACTURER ?: "").replaceFirstChar { it.uppercase() }
        val name = listOf(maker, Build.MODEL ?: "").filter { it.isNotBlank() }.joinToString(" ").trim()
        if (name.isNotBlank()) sb.append(name)
        sb.append(" (Android ${Build.VERSION.RELEASE}, sdk ${Build.VERSION.SDK_INT})")
        try {
            val dm = resources.displayMetrics
            sb.append(", screen ${dm.widthPixels}x${dm.heightPixels}")
        } catch (_: Exception) {}
        if (isDexMode()) sb.append(", DeX desktop active")
        scanDefaultApps().let { if (it.isNotBlank()) sb.append(". Default apps: ").append(it) }
        return sb.toString().trim()
    }

    /** The phone's DEFAULT handler app for each common job, by resolving a representative intent.
     *  Names only ("browser=Chrome, texts=Messages, ..."); needs no special permission. */
    private fun scanDefaultApps(): String {
        val pm = packageManager
        fun labelFor(intent: Intent): String? = try {
            val ri = pm.resolveActivity(intent, PackageManager.MATCH_DEFAULT_ONLY)
            val pkg = ri?.activityInfo?.packageName ?: ""
            val nm = ri?.loadLabel(pm)?.toString()?.trim()
            // Skip the system resolver / "no default chosen" chooser placeholders.
            if (nm.isNullOrBlank() || nm.equals("android", true) ||
                pkg == "android" || pkg.contains("resolver") || pkg.contains("android.internal")) null else nm
        } catch (_: Exception) { null }
        val jobs = listOf(
            "browser" to Intent(Intent.ACTION_VIEW, Uri.parse("https://example.com")),
            "texts" to Intent(Intent.ACTION_VIEW, Uri.parse("sms:")),
            "phone" to Intent(Intent.ACTION_DIAL, Uri.parse("tel:")),
            "email" to Intent(Intent.ACTION_SENDTO, Uri.parse("mailto:")),
            "maps" to Intent(Intent.ACTION_VIEW, Uri.parse("geo:0,0?q=coffee")),
            "camera" to Intent("android.media.action.IMAGE_CAPTURE")
        )
        return jobs.mapNotNull { (job, intent) -> labelFor(intent)?.let { "$job=$it" } }.joinToString(", ")
    }

    /** Write text the agent produced to a .txt in Downloads/AgentNotes (via MediaStore, no storage
     *  permission needed) so the owner can open it. Returns the visible path, or null on failure. */
    private fun saveNote(name: String, text: String): String? = try {
        val safe = name.ifBlank { "agent_note" }.replace(Regex("[^A-Za-z0-9 ._-]"), "_").trim().take(60)
        val fname = if (safe.endsWith(".txt", true)) safe else "$safe.txt"
        val values = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, fname)
            put(MediaStore.MediaColumns.MIME_TYPE, "text/plain")
            put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/AgentNotes")
        }
        val uri = contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
        if (uri == null) null else {
            contentResolver.openOutputStream(uri)?.use { it.write(text.toByteArray()) }
            AgentLog.log("note", "saved note: Downloads/AgentNotes/$fname (${text.length} chars)")
            "Downloads/AgentNotes/$fname"
        }
    } catch (e: Exception) { AgentLog.log("note", "save failed: ${e.message}"); null }

    // --- SCREEN READING ---------------------------------------------------

    fun currentPackage(): String? = rootInActiveWindow?.packageName?.toString()

    /** Samsung DeX (desktop mode on an external monitor) is active. Detected via Samsung's
     *  documented Configuration fields (reflection, fully guarded), with the generic desktop
     *  ui-mode as a fallback. When on, the agent is reading the MONITOR's windowed/desktop UI. */
    fun isDexMode(): Boolean {
        try {
            val config = resources.configuration
            val cls = config.javaClass
            val enabled = cls.getField("SEM_DESKTOP_MODE_ENABLED").getInt(cls)
            val current = cls.getField("semDesktopModeEnabled").getInt(config)
            if (enabled == current) return true
        } catch (_: Exception) {}
        return try {
            (resources.configuration.uiMode and android.content.res.Configuration.UI_MODE_TYPE_MASK) ==
                android.content.res.Configuration.UI_MODE_TYPE_DESK
        } catch (_: Exception) { false }
    }

    /** Tier-aware perception budgets (owner's one-build-many-devices): a weak setup (LEAN device, or a heavy
     *  model on MID hardware - the existing useLeanPath signal) gets a SMALLER element page / char budget /
     *  node cap so the snapshot fits its tighter context and stays fast; the dev Fold (RICH) is unchanged.
     *  pageSize is the SINGLE source so snapshotScreen and currentMarks always agree (badge == list). */
    private fun leanPerception(): Boolean = DeviceStats.useLeanPath(this, settings.getModelPath())
    private fun perceptionPageSize(): Int = if (leanPerception()) 14 else ELEMENT_PAGE_SIZE

    fun snapshotScreen(): String {
        currentNodes.clear()
        lastRenderedIds.clear()             // rebuilt by the post-walk render/collapse pass (A2)
        sawSpinner = false                  // recomputed by the walk below (feeds loadingHint())
        seenAffordanceTags.clear()          // per-snapshot affordance-tag dedup (the launcher-grid OOM)
        affordanceTagsSuppressed = false
        val w = resources.displayMetrics.widthPixels
        val h = resources.displayMetrics.heightPixels
        val pageSz = perceptionPageSize()
        val lp = leanPerception()
        val charBudget = if (lp) 1000 else MAX_SNAPSHOT_CHARS
        val nodeCap = if (lp) 120 else MAX_NODES
        // #8 MULTI-PANE: read EVERY visible APP window, not just the focused one, so the agent perceives
        // BOTH halves of a split screen / DeX / unfolded fold (the owner's multi-device priority). A
        // single app window - the common case - behaves exactly as before. System chrome, the keyboard,
        // and our own STOP overlay are filtered out (not TYPE_APPLICATION). Falls back to the active
        // window if the window list is empty/unavailable. Ordered top-to-bottom, left-to-right.
        val appRoots: List<AccessibilityNodeInfo> = try {
            windows?.filter { it.type == android.view.accessibility.AccessibilityWindowInfo.TYPE_APPLICATION }
                ?.sortedBy { val r = Rect(); it.getBoundsInScreen(r); r.top * 100000L + r.left }
                ?.mapNotNull { it.root }
                ?.takeIf { it.isNotEmpty() }
                ?: listOfNotNull(rootInActiveWindow)
        } catch (_: Exception) { listOfNotNull(rootInActiveWindow) }
        if (appRoots.isEmpty()) return "Screen is empty or unavailable."
        val sb = StringBuilder()
        // Exact, read-only text from NON-interactive nodes (dashboard values, prices, results). Kept
        // separate from the tappable [N] list so the model READS it for values without trying to tap it.
        val readText = LinkedHashSet<String>()
        // Rendered list lines seen this snapshot, to DISAMBIGUATE byte-identical ones (two "More" icons, or
        // two long labels sharing a 70-char prefix) - else only badge geometry tells them apart, forcing a
        // vision fallback / wrong tap. A minimal tiebreaker is appended ONLY on a collision (see below).
        val renderedDescs = HashSet<String>()
        // A2: collect the page's renderable lines (id, node, desc) during the walk, then emit them AFTER the
        // walk so a run of structurally-identical rows (a feed / long settings list) can be COLLAPSED to a
        // few representatives + a count marker before rendering - the honest 80-90% token cut on uniform
        // lists. Every node still lands in currentNodes (ids stable; find/click/next_page reach every one);
        // only the rendered LINE is folded. Collecting != rendering, so nothing becomes unreachable (§12).
        val pageEntries = ArrayList<Triple<Int, AccessibilityNodeInfo, String>>()

        fun consider(node: AccessibilityNodeInfo, listedAncestorLabel: String?) {
            // COLLECT deep (up to MAX_NODES) so find/click can reach every visible control; the RENDERED
            // text + badges stay bounded (paged + the char budget below). The old cap returned here at 60,
            // aborting the WALK, which made controls at 61+ silently unfindable. Token budget is protected
            // by what's rendered, not by refusing to look.
            // Free spinner check (we're already visiting every node): a VISIBLE indeterminate
            // ProgressBar/CircularProgressIndicator = "still loading". rangeInfo != null means a
            // DETERMINATE bar (a real value, e.g. a download), which is not a loading spinner.
            if (!sawSpinner && node.isVisibleToUser) {
                val cn = (node.className ?: "").toString()
                val isSpinner = (cn.contains("ProgressBar") || cn.contains("CircularProgress")) &&
                    (try { node.rangeInfo == null } catch (_: Exception) { true })
                // Generalize past the ProgressBar WIDGET to the loading STATE: an app that shows a
                // "Loading…"/"Please wait" label (or a custom/Lottie spinner carrying that as its desc)
                // instead of a stock spinner is still loading. Short text only; loadingHint()'s sparse-
                // screen gate keeps a stray "loading" label on a populated screen from tripping it.
                val lt = (node.text ?: node.contentDescription)?.toString()?.trim()?.lowercase().orEmpty()
                val isLoadingText = lt.length in 1..20 &&
                    (lt.startsWith("loading") || lt.contains("please wait"))
                if (isSpinner || isLoadingText) sawSpinner = true
            }
            if (currentNodes.size >= nodeCap) return
            // A focusable-ONLY node counts only if it carries a label (real target). Bare
            // focusable containers (layouts/scrollviews) are noise that bloats the list,
            // clutters the set-of-marks badges, and lures the model toward non-targets - and
            // anything genuinely tappable is still caught by isClickable (click() walks up to
            // the clickable parent anyway).
            val hasLabel = !node.text.isNullOrBlank() || !node.contentDescription.isNullOrBlank()
            val interactive = node.isClickable || node.isEditable || node.isLongClickable ||
                node.isCheckable || (node.isFocusable && hasLabel)
            // This node's own label (raw, for the dedup compare below).
            val myLabel = node.text?.toString()?.trim()?.ifBlank { null }
                ?: node.contentDescription?.toString()?.trim()?.ifBlank { null }
            var childAncestorLabel = listedAncestorLabel
            if (interactive && node.isVisibleToUser) {
                // DEDUP nested duplicate clickables (the owner: "not every element - just where to interact").
                // A clickable nested inside an ALREADY-LISTED clickable that adds NO new label (same text, or
                // no label of its own) is the SAME visual control listed twice - the #1 list bloat on feeds /
                // lists / settings rows (row + wrapper + inner text all tap the same thing). Drop it; click()
                // walks up to the clickable parent anyway, so its id still works. A child with its OWN distinct
                // label IS a separate action, so it's kept; and a field/toggle is NEVER dropped (a distinct
                // type/tap target even when its label matches the row). Generic (label-only), never objective-
                // specific - this ORGANIZES perception, it doesn't decide what's relevant.
                // Only an EXACT-label duplicate (child's label == the listed ancestor's) is dropped. A
                // LABEL-LESS child is KEPT - it might be a distinct unlabeled action (a close/"more" icon with
                // no description), and the owner's rule is to NEVER make a real control inaccessible by guessing
                // it's redundant. Dedup the certain duplicates only; organize, don't delete.
                val redundant = !node.isEditable && !node.isCheckable &&
                    myLabel != null && myLabel == listedAncestorLabel
                if (!redundant) {
                    val index = currentNodes.size
                    currentNodes.add(node)
                    // What to LIST (ids always map to the FULL node list, so a known id works off-screen):
                    //  - PEEKING a region (foveated zoom) -> just that region's controls.
                    //  - otherwise -> a fixed-size PAGE of the list, so a busy screen is searched set by set
                    //    (next_page) instead of dumped whole. Both keep the prompt small.
                    val onPage = index >= elementPage * pageSz &&
                        index < (elementPage + 1) * pageSz
                    // COLLECT the text line for the listed window (or peeked region) into pageEntries; the
                    // post-walk pass renders + collapses + honours the char budget. Collecting past the
                    // budget here is free (a Triple, no tokens) and lets collapse shrink a run BEFORE the
                    // budget bites, so an actionable control isn't budget-cut behind 20 identical rows.
                    if (if (zoomRegion != null) nodeInZoom(node, w, h) else onPage) {
                        var desc = describe(node, w, h)
                        if (!renderedDescs.add(desc)) {
                            // Byte-identical to a line already shown: append a minimal tiebreaker (short
                            // view-id, else @position) so the two are distinguishable in text, not just by badge.
                            val vid = node.viewIdResourceName?.substringAfterLast('/')?.takeIf { it.isNotBlank() }
                            if (vid != null) desc += " id:$vid"
                            else {
                                val rr = Rect(); node.getBoundsInScreen(rr)
                                val pos = "@" + positionHint(rr.centerX(), rr.centerY(), w, h)
                                // Only add the @position tiebreaker if the descriptor doesn't ALREADY end with it. A
                                // cluster of identical label-less controls in the same coarse bucket (e.g. a chat
                                // screen's nav-drawer scrim toggles) each already carry that @position from describe(),
                                // so re-appending it just DOUBLED the token ("@top-left @top-left") without actually
                                // disambiguating - and that padding helped tip a dense screen over the 4096 budget
                                // every step (the "[4188 >= 4096] degrading" overflow spam). The [N] badge already
                                // tells identical controls apart.
                                if (!desc.endsWith(pos)) desc += " $pos"
                            }
                        }
                        pageEntries.add(Triple(index, node, desc))
                    }
                    // Children are now nested under THIS listed control - carry its label for their dedup.
                    childAncestorLabel = myLabel ?: listedAncestorLabel
                }
            } else if (node.isVisibleToUser && !node.text.isNullOrBlank() && readText.size < 24) {
                // Visible NON-interactive text = on-screen content to READ (a value on a dashboard,
                // a price, a status). Capture the EXACT string so data reads don't rely on OCR.
                val t = node.text.toString().trim()
                if (t.length in 1..64) readText.add(t)
            }
            for (i in 0 until node.childCount) {
                node.getChild(i)?.let { consider(it, childAncestorLabel) }
            }
        }
        // #8: walk every app pane. With one window this is just consider(root) as before; with two+ (split
        // screen / DeX / fold) each pane's controls are still collected with GLOBAL ids (a click works
        // regardless of pane); a single note flags the split and each element's @position (from describe)
        // shows its side, so the collapse pass below treats the page as one list.
        if (appRoots.size > 1)
            sb.append("— split screen: ${appRoots.size} panes; each element's @position shows its side —\n")
        appRoots.forEach { paneRoot -> consider(paneRoot, null) }
        // A2 HOMOGENEOUS-LIST COLLAPSE: emit the collected page lines, folding a run of >= 6 consecutive
        // structurally-identical rows (same role + label-shape + interaction flags + STATE) to 3
        // representatives + one "… +N more [ids A-B]" marker. A state difference ([selected]/[checked]/
        // [disabled]/[focused] / editable / checkable) changes the sig, so a distinct row breaks the run and
        // renders in full. Every row stays in currentNodes (find/next_page/scroll reach any); only the LINE
        // is folded, and lastRenderedIds records exactly what got a line so the set-of-marks badges match.
        run {
            val sigs = pageEntries.map { structuralSig(it.second) }
            var i = 0
            while (i < pageEntries.size && sb.length < charBudget) {
                var j = i + 1
                while (j < pageEntries.size && sigs[j] == sigs[i]) j++
                val runLen = j - i
                if (runLen >= 6) {
                    for (k in i until i + 3) {
                        val e = pageEntries[k]
                        sb.append("[").append(e.first).append("] ").append(e.third).append("\n")
                        lastRenderedIds.add(e.first)
                    }
                    sb.append("… +${runLen - 3} more similar rows [ids ${pageEntries[i + 3].first}–${pageEntries[j - 1].first}] " +
                        "(find/next_page/scroll to reach any)\n")
                    i = j
                } else {
                    val e = pageEntries[i]
                    sb.append("[").append(e.first).append("] ").append(e.third).append("\n")
                    lastRenderedIds.add(e.first)
                    i++
                }
            }
        }
        val total = currentNodes.size
        val pages = (total + pageSz - 1) / pageSz
        // Paging note (not while peeking): say the agent is seeing ONE set of a longer list and how to
        // move through it to find its target - rather than dumping every control at once.
        if (zoomRegion == null && pages > 1) {
            // Speak in the SAME 0-based id space as the [N] list + badges. It used to print "elements 1-20"
            // while page 1 actually lists [0]..[19] - a small model then off-by-ones (taps [1] as the first,
            // or targets a [20] that's really on the next page).
            val lo = elementPage * pageSz
            val hi = minOf((elementPage + 1) * pageSz, total) - 1
            // Steer to the FAST path first: if you know what you want, find/open_app jump straight to
            // it in one step. Paging is for BROWSING when you don't - don't page set by set to hunt a
            // control you can name (that's a slow vision step per set).
            sb.append("— showing ids [$lo]–[$hi] of $total (set ${elementPage + 1}/$pages). Looking for a SPECIFIC " +
                "control? {\"action\":\"find\",\"text\":\"its label\"} taps it instantly wherever it is (and " +
                "open_app opens any app) - don't page to hunt. Only to BROWSE the rest: {\"action\":\"next_page\"}")
            if (elementPage > 0) sb.append(" / {\"action\":\"prev_page\"}")
            sb.append(".\n")
        }
        if (total >= 60)
            sb.append("(busy screen - rather than take it all in, {\"action\":\"peek\",\"region\":\"top/bottom/left/right/center/a corner\"} to focus on JUST the chunk where you expect your target; or find/scroll.)\n")
        if (affordanceTagsSuppressed)
            sb.append("(identical [long-press]/[do:…] options hidden - same as shown above)\n")
        confirmPendingSend()  // learn whether a previous send actually landed

        // Lead with the current app so the model is always grounded in WHERE it is
        // (cheap reorientation - cuts wrong-app drift). Not an element, so the "[" count
        // and element ids are unaffected.
        val appLine = "app: ${currentPackage()?.substringAfterLast('.') ?: "?"}\n"
        // If we're carrying a value to move between apps, show it so the model can paste/verify it.
        val clipLine = carriedText?.takeIf { it.isNotBlank() }?.let { "carrying (clipboard): \"${clip(it, 80)}\"\n" }.orEmpty()
        // READ-ONLY TEXT layer (the owner's "read a dashboard / pull exact values without misreading"):
        // the EXACT visible text the model can READ for values, instead of OCR-guessing it from the
        // screenshot (zero-hallucination data reads). Only when budget remains - a dashboard has few
        // controls but many values, while a dense app screen is already truncated - and deduped against
        // the controls already listed + capped, so it never pushes a busy screen over the token limit.
        val seen = sb.toString()
        // The exact-value TEXT layer used to be DROPPED entirely once the list got dense (>70% budget), and
        // SILENTLY - so on value-packed screens (a dashboard with many controls AND numbers) the model
        // OCR-guessed believing no exact text existed, exactly where a misread hurts most. Now: SHRINK it
        // under pressure instead of zeroing, and if anything was omitted, SAY so (never leave the model
        // believing it must guess).
        val tight = sb.length > charBudget * 7 / 10
        val maxPicks = if (tight) 5 else 14
        val maxChars = if (tight) 140 else 360
        val readLine = run {
            val picks = ArrayList<String>(); var chars = 0; var omitted = false
            for (t in readText) {
                if (seen.contains(t)) continue
                if (chars >= maxChars || picks.size >= maxPicks) { omitted = true; break }
                picks.add(t); chars += t.length + 3
            }
            if (picks.isEmpty()) "" else
                "\nTEXT ON SCREEN (read-only, EXACT - use these for any value you report/copy; do NOT tap them): " +
                picks.joinToString(" · ") +
                (if (omitted) " · …(more exact text on screen - zoom/peek to read it; do NOT guess it from the image)" else "")
        }
        val body = if (sb.isEmpty()) "No tappable elements detected." else sb.toString().trim()
        // When peeking, say so: the list is just this region's controls, and how to widen back out.
        val peekLine = if (zoomRegion == null) "" else
            "PEEKING a region (the screen was too dense to show whole) - only this spot's controls are " +
            "listed; {\"action\":\"zoom_out\"} to see the whole screen, or zoom a different region.\n"
        lastValueLayer = clipLine + readLine   // LANG: the exact-value layer codecScreen re-appends (captured fresh each snapshot)
        return appLine + clipLine + peekLine + body + keyControlsHint() + readLine
    }

    /** KEY CONTROLS (the owner's idea: "identify the search button and map coords, do this for other
     *  buttons"): scan the listed elements for the high-value controls the agent often fumbles and name
     *  them with their [N] id so it taps the right one instead of a lookalike chip. Three roles, the ones
     *  that actually advance a task and are easy to miss among similar-looking elements:
     *    - the SEARCH box (the input you type a query into - mistaken for a suggestion chip),
     *    - the SEND control (commit a typed message), and
     *    - the primary SUBMIT/advance button (Continue / Next / Submit / Go / Sign in / Done / Save).
     *  Recognizes the control TYPE on the screen (perception); it never decides WHAT to do, and stays
     *  quiet when nothing matches, so it's near-free and not noisy. Ids tap by coordinate under the hood,
     *  so this IS "map coords to the button". */
    private fun keyControlsHint(): String {
        // Two tiers for the search box on purpose: the Google app's whole namespace is literally
        // "...googlequicksearchbox", so a bare "searchbox" substring ALSO matches the mic and the account
        // disc that sit in the search bar - the bug that once made this point at the account button (=[1])
        // instead of the real facade_search_box (=[5]). So we take the SPECIFIC signal first and only fall
        // back to the loose one, and exclude the known non-box siblings either way.
        var searchStrong = -1; var searchWeak = -1; var send = -1; var submit = -1; var msgBox = -1
        currentNodes.forEachIndexed { i, n ->
            // Id part ONLY - the full resource name starts with the PACKAGE, and in the Gemini/Google
            // app that package is ".googlequicksearchbox", so the FULL-name read made every node in the
            // app match the weak "searchbox" tier and the CHAT INPUT got labeled "search box" (the
            // owner's log: the model then treated the chat like a search and flailed re-typing instead
            // of pressing send).
            val vid = (n.viewIdResourceName ?: "").substringAfterLast('/').lowercase()
            val desc = ((n.text ?: "").toString() + " " + (n.contentDescription ?: "")).lowercase().trim()
            val notBoxSibling = !vid.contains("mic") && !vid.contains("voice") && !vid.contains("lens") &&
                !vid.contains("avatar") && !vid.contains("account") && !vid.contains("clear") && !vid.contains("logo")
            if (searchStrong < 0 && notBoxSibling && (vid.contains("facade_search") || vid.contains("search_box") ||
                    vid.contains("search_plate") || vid.contains("search_bar") || vid.contains("search_field") ||
                    vid.contains("search_src_text") || (n.isEditable && desc.startsWith("search")))) searchStrong = i
            if (searchWeak < 0 && notBoxSibling && (vid.contains("searchbox") || (n.isEditable && desc.contains("search")))) searchWeak = i
            if (send < 0 && !desc.contains("resend") && (Regex("(^|_)send($|_)").containsMatchIn(vid) ||
                    desc == "send" || desc == "send message")) send = i
            // The one button that commits/advances a flow. Tappable, NOT the typed field, and the label is
            // essentially JUST a commit verb (short) - so it flags the real CTA, not every chrome button or a
            // paragraph that happens to contain "continue". First match wins (there's normally one per screen).
            if (submit < 0 && n.isClickable && !n.isEditable && desc.length in 1..16 &&
                    Regex("^(submit|continue|next|confirm|sign ?in|log ?in|go|done|save)\\b").containsMatchIn(desc)) submit = i
            // A CHAT/COMPOSE input reads differently from a search box - flag it as a POSSIBILITY only
            // (the model still chooses the id). id contains chat_input/message/compose, or the shared
            // looksLikeMessageInput heuristic. Surfaced (not decided) below.
            if (msgBox < 0 && n.isEditable && (vid.contains("chat_input") || vid.contains("message") ||
                    vid.contains("compose") || looksLikeMessageInput(n))) msgBox = i
        }
        val search = if (searchStrong >= 0) searchStrong else searchWeak
        // Make the commit control's GATE state explicit: a DISABLED Send/Submit means a prerequisite isn't
        // met (type first, fill a field), so tapping it does nothing. Flagging it stops the weak-model loop
        // of hammering a greyed button. Enabled = bare id (the default = tappable).
        fun blockedTag(i: Int) = if (currentNodes.getOrNull(i)?.isEnabled == false)
            " (DISABLED - do the prerequisite first; tapping it does nothing)" else ""
        val parts = ArrayList<String>()
        // A chat/compose input and a search box are BOTH editables, and in a chat app one box can read
        // either way. Rather than CODE deciding which it is (and suppressing the other), SURFACE the
        // possibilities and let the MODEL pick the id (the owner's steer: inform, don't pre-decide).
        when {
            // The composer node itself also matched the search heuristic -> one honest ambiguous label.
            msgBox >= 0 && msgBox == search ->
                parts.add("editable=[$msgBox] (chat composer or search box - you decide)")
            // A likely composer AND a SEPARATE search box are both present -> surface BOTH; model picks.
            msgBox >= 0 && search >= 0 -> {
                parts.add("editable=[$msgBox] (looks like a chat/compose box)")
                parts.add("search box=[$search]")
            }
            // Only a likely composer.
            msgBox >= 0 -> parts.add("editable=[$msgBox] (looks like a chat/compose box)")
            // Only a search box.
            search >= 0 -> parts.add("search box=[$search]")
        }
        if (send >= 0) parts.add("send=[$send]" + blockedTag(send))
        if (submit >= 0) parts.add("submit/next=[$submit]" + blockedTag(submit))
        return if (parts.isEmpty()) "" else
            "\nKEY CONTROLS here (tap by id - the important targets): ${parts.joinToString(", ")}"
    }

    /** True if [node] sits in the currently-peeked region (or there's no peek). A little slack so a
     *  control straddling the region's edge still lists. Centre-based; fractions of the screen. */
    private fun nodeInZoom(node: AccessibilityNodeInfo, w: Int, h: Int): Boolean {
        val z = zoomRegion ?: return true
        val r = Rect(); node.getBoundsInScreen(r)
        val cx = r.exactCenterX() / w; val cy = r.exactCenterY() / h
        return cx >= z.left - 0.05f && cx <= z.right + 0.05f && cy >= z.top - 0.05f && cy <= z.bottom + 0.05f
    }

    /** World-state slice: is the soft keyboard (IME) currently shown? If so, controls at the
     *  very bottom (Send / Next / Submit) may be COVERED - telling the model this stops it
     *  looping while hunting for a button it physically can't see. Uses the window list
     *  (flagRetrieveInteractiveWindows is enabled in the service config). */
    fun isKeyboardOpen(): Boolean = try {
        windows?.any { it.type == AccessibilityWindowInfo.TYPE_INPUT_METHOD } == true
    } catch (_: Exception) { false }

    /** Connected DEVICES the agent should be aware of (the owner's "be aware of connected devices and
     *  hopefully interact with them"). Reports external audio outputs - Bluetooth earbuds/speakers,
     *  wired/USB headphones, a car, HDMI/cast/TV, a dock - by name; no extra permission needed.
     *  Interaction is then via the normal UI (open the device's app or Bluetooth settings). */
    /** External audio-output devices currently connected, as readable labels. [withProduct] appends
     *  the product name ("Bluetooth audio (Galaxy Buds)") for the full scan; the brief form drops it.
     *  Shared by the on-demand action and the always-on action-space feed so they never diverge. */
    private fun outputDeviceLabels(withProduct: Boolean): LinkedHashSet<String> {
        val out = LinkedHashSet<String>()
        val am = getSystemService(android.content.Context.AUDIO_SERVICE) as android.media.AudioManager
        for (d in am.getDevices(android.media.AudioManager.GET_DEVICES_OUTPUTS)) {
            val label = when (d.type) {
                android.media.AudioDeviceInfo.TYPE_BLUETOOTH_A2DP,
                android.media.AudioDeviceInfo.TYPE_BLUETOOTH_SCO -> "Bluetooth audio"
                android.media.AudioDeviceInfo.TYPE_WIRED_HEADPHONES,
                android.media.AudioDeviceInfo.TYPE_WIRED_HEADSET -> "Wired headphones"
                android.media.AudioDeviceInfo.TYPE_USB_HEADSET,
                android.media.AudioDeviceInfo.TYPE_USB_DEVICE -> "USB audio"
                android.media.AudioDeviceInfo.TYPE_HDMI -> "HDMI / TV"
                android.media.AudioDeviceInfo.TYPE_DOCK -> "Dock"
                else -> null
            } ?: continue
            val pname = d.productName?.toString()?.trim().orEmpty()
            out.add(if (withProduct && pname.isNotBlank() && !pname.equals(Build.MODEL, true)) "$label ($pname)" else label)
        }
        return out
    }

    fun connectedDevices(): String = try {
        val names = outputDeviceLabels(withProduct = true)
        if (names.isEmpty()) "No external devices connected (phone speaker only)."
        else "Connected: " + names.joinToString(", ") + " - to control one, open its app or Bluetooth settings."
    } catch (_: Exception) { "Couldn't read connected devices." }

    /** Short CSV of connected external devices, or "" when it's only the phone speaker - so the
     *  action space can surface the hardware context every step cheaply, without spending a turn on
     *  a scan. The full connected_devices action still gives the controllable detail. */
    fun connectedDevicesBrief(): String = try {
        outputDeviceLabels(withProduct = false).joinToString(", ")
    } catch (_: Exception) { "" }

    /** Structured navigation scrape of the current screen (the tabs/sections + which one is selected,
     *  the bottom-nav items, the standard affordances, scrollability). Read off the already-captured
     *  elements - no re-walk. Both the action-space string and the persisted destination map use it. */
    private class NavScan {
        val tabs = LinkedHashSet<String>(); var current: String? = null
        val bottom = LinkedHashSet<String>()
        val afford = LinkedHashSet<String>(); var scrollable = false
    }
    private fun scanNav(): NavScan {
        val s = NavScan()
        val h = resources.displayMetrics.heightPixels
        for (n in currentNodes) {
            if (n.isScrollable) s.scrollable = true
            val label = n.text?.toString()?.trim().orEmpty()
                .ifBlank { n.contentDescription?.toString()?.trim().orEmpty() }
            val cd = n.contentDescription?.toString()?.lowercase().orEmpty()
            when {
                cd.contains("navigate up") || cd == "back" || cd == "go back" -> s.afford.add("↑ up")
                cd.contains("navigation drawer") || cd.contains("open drawer") ||
                    cd.contains("show navigation") || cd.contains("show menu") -> s.afford.add("☰ drawer")
                cd.contains("more options") || cd.contains("overflow") || cd == "more" -> s.afford.add("⋮ more")
                cd.contains("search") && label.length <= 14 -> s.afford.add("⌕ search")
            }
            val cn = n.className?.toString() ?: ""
            if (cn.contains("Tab", true) && label.isNotBlank() && label.length <= 24) {
                s.tabs.add(label); if (n.isSelected) s.current = label
            } else if (n.isClickable && label.isNotBlank() && label.length <= 16) {
                // Bottom navigation: a short-labelled clickable sitting in the bottom strip.
                val r = Rect(); n.getBoundsInScreen(r)
                if (r.centerY() > h * 0.86) s.bottom.add(label)
            }
        }
        s.bottom.removeAll(s.tabs)
        return s
    }

    /** Best-effort scrape of the NAVIGATION on this screen for the action space (owner: "scrape
     *  navigation info, not just devices"): "where can I go from here" - tab/section you're on and
     *  the siblings, bottom-nav, the affordances (up, drawer, overflow, search), and scrollability. */
    fun navigationAffordances(): String = try {
        val s = scanNav()
        val parts = ArrayList<String>(4)
        if (s.tabs.isNotEmpty())
            parts.add("tabs " + s.tabs.take(7).joinToString("·") + (s.current?.let { " (on $it)" } ?: ""))
        if (s.bottom.isNotEmpty()) parts.add("bottom-nav " + s.bottom.take(6).joinToString("·"))
        if (s.afford.isNotEmpty()) parts.add(s.afford.joinToString(" "))
        // Read the MAIN scrollable (same node scroll()/find move, found by a full-tree walk so a
        // non-interactive container isn't missed) so this perception matches the action it feeds.
        val ms = mainScrollable()
        if (ms != null) {
            // DIRECTION-aware: a native list exposes only the scroll actions that still have content
            // (a list at the bottom offers BACKWARD only, the top offers FORWARD only), so we can tell
            // the agent which way to scroll - and NOT to scroll when it's already at the end. Gesture-only
            // lists (many Compose UIs) expose no actions; we stay neutral there rather than falsely claim
            // "at the end" and stop the agent scrolling a list that really has more (the Gemini-chat bug).
            // This only INFORMS - if it misjudges, the model can still scroll the other way.
            // NOTE: AccessibilityAction's constants are Java STATIC fields - the class can't be
            // aliased as a value (`val A = ...` broke the whole build); reference them qualified,
            // same as every other use in this file.
            val ids = ms.actionList?.map { it.id } ?: emptyList()
            val fwd = ids.contains(AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_FORWARD.id) ||
                ids.contains(AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_DOWN.id) ||
                ids.contains(AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_RIGHT.id)
            val back = ids.contains(AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_BACKWARD.id) ||
                ids.contains(AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_UP.id) ||
                ids.contains(AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_LEFT.id)
            parts.add(when {
                fwd && back -> "↕ more content both ways (scroll)"
                fwd -> "↓ more below - scroll down to reveal it"
                back -> "↑ at the bottom (more above) - don't scroll down further"
                else -> "↕ scrollable"
            })
        }
        parts.joinToString(" · ")
    } catch (_: Exception) { "" }

    /** The navigation DESTINATIONS visible on this screen (tab + bottom-nav labels) - the "places you
     *  can go". Persisted/merged per app so the agent accumulates an app's full set of destinations
     *  across visits, including ones not on the current screen. */
    fun navDestinations(): List<String> = try {
        scanNav().let { (it.tabs + it.bottom).toList() }
    } catch (_: Exception) { emptyList() }

    /** Bounds of a picture-in-picture video window if one is floating over the screen, else null. A
     *  PiP is a small APPLICATION window that ISN'T the active/focused one (the owner is interacting
     *  with the app behind it). The agent reads only the active window, so PiP controls aren't in its
     *  element list anyway; this lets us also warn the model to leave the PiP alone and to refuse a
     *  blind pixel tap that lands on it. */
    fun pipWindowBounds(): Rect? = try {
        val ws = windows
        val dm = resources.displayMetrics
        val screenArea = dm.widthPixels.toLong() * dm.heightPixels
        var found: Rect? = null
        if (ws != null && screenArea > 0) {
            for (w in ws) {
                if (w.type != AccessibilityWindowInfo.TYPE_APPLICATION) continue
                if (w.isActive || w.isFocused) continue
                val r = Rect(); w.getBoundsInScreen(r)
                val area = r.width().toLong() * r.height()
                // A PiP tile is small (well under a third of the screen) and not full-width.
                if (area in 1 until (screenArea / 3) && r.width() < dm.widthPixels * 0.7) { found = r; break }
            }
        }
        found
    } catch (_: Exception) { null }

    /** True if [x],[y] (screen pixels) fall inside a picture-in-picture video window. */
    fun isInsidePip(x: Int, y: Int): Boolean = pipWindowBounds()?.contains(x, y) == true

    /** Click the listed node whose accessibility id ends with [idSuffix] (deterministic navigation for
     *  known controls, e.g. the pen tool or "Create note"). Returns true if it found and tapped one. */
    fun tapByViewId(idSuffix: String): Boolean {
        val n = currentNodes.firstOrNull { (it.viewIdResourceName ?: "").endsWith(idSuffix) } ?: return false
        click(n)
        return true
    }

    /** Select the Pen drawing tool (Samsung Notes opens new notes in Text mode with the keyboard up,
     *  which blocks drawing). Returns true if it tapped the pen-mode button. */
    fun selectPenMode(): Boolean = tapByViewId("hw_toolbar_pen")

    /** Tap a node by its exact content-description (case-insensitive) - for controls that expose a
     *  desc but no stable view-id. */
    fun tapByDesc(desc: String): Boolean {
        val d = desc.trim().lowercase()
        val n = currentNodes.firstOrNull { (it.contentDescription?.toString() ?: "").trim().lowercase() == d } ?: return false
        click(n); return true
    }

    /** Is Samsung Notes' brush PICKER open (the dedicated Drawing surface opens with it over the
     *  canvas)? The agent must SEE the brushes to choose one, so we keep the full list when it's up. */
    fun isBrushPickerOpen(): Boolean =
        currentNodes.any { (it.viewIdResourceName ?: "").endsWith("brush_done_button") }

    /** Some chat composers (e.g. Gemini's half-sheet) show a COLLAPSED input PREVIEW with no Send
     *  button visible until it's tapped to expand the full composer. Detecting it lets us tell the
     *  model to expand first, instead of typing into the preview and hunting for a Send that isn't
     *  there yet (the slow churn the owner saw in Gemini). */
    fun isCollapsedComposerPresent(): Boolean = try {
        val editables = currentNodes.filter { it.isEditable }
        // Only when the collapsed preview is the SOLE input (the expanded box isn't open yet) - so the
        // hint stops once it's expanded, matching expandCollapsedComposer's gate.
        editables.isNotEmpty() && editables.all { isCollapsedComposerNode(it) }
    } catch (_: Exception) { false }

    /** Set-of-Marks for the CURRENT snapshot: bounds of each listed element, index-aligned
     *  with the `[N]` ids. Call right after [snapshotScreen] so it matches the element list
     *  and the screenshot taken at the same moment. */
    fun currentMarks(): ScreenMarks {
        val w = resources.displayMetrics.widthPixels
        val h = resources.displayMetrics.heightPixels
        // Badge EXACTLY the ids snapshotScreen rendered as [N] lines this snapshot - lastRenderedIds is
        // post-paging AND post-collapse, so a folded/budget-cut row is never badged without a matching text
        // line (the off-page-badge bug, where badges 20..59 had no listed line). find/click still resolve
        // over the full currentNodes. Fallback to the page window only if a snapshot hasn't run yet.
        val boxes = ArrayList<Rect>(); val ids = ArrayList<Int>()
        val rendered = if (lastRenderedIds.isNotEmpty()) lastRenderedIds.toList() else {
            val pageSz = perceptionPageSize()
            currentNodes.indices.filter {
                if (zoomRegion != null) nodeInZoom(currentNodes[it], w, h)
                else it >= elementPage * pageSz && it < (elementPage + 1) * pageSz
            }
        }
        for (i in rendered) {
            val n = currentNodes.getOrNull(i) ?: continue
            val r = Rect(); n.getBoundsInScreen(r); boxes.add(r); ids.add(i)
        }
        return ScreenMarks(w, h, boxes, ids)
    }

    /** Batch B (foveated flashlight): region-relative Set-of-Marks so the numbered `[N]` badges survive
     *  INSIDE a `peek` crop. The old code suppressed marks while zoomed (the badges were positioned for
     *  the full screen and wouldn't line up on a crop), so a peek lost its numbered targets. Here we
     *  RE-BASE each in-region node's bounds onto the crop's origin and declare screenW/H = the crop's
     *  extent (in display pixels), carrying the SAME GLOBAL id - so drawMarks (which scales by
     *  bmp.width/screenW) lands each badge correctly on the magnified crop, and a `click`/`tap` by that id
     *  still resolves against the node's real bounds (the id path is region-independent). [region] is a
     *  0..1 fractional rect (== zoomRegion); null delegates to the full-screen currentMarks(). */
    fun currentMarks(region: android.graphics.RectF?): ScreenMarks {
        if (region == null) return currentMarks()
        val w = resources.displayMetrics.widthPixels
        val h = resources.displayMetrics.heightPixels
        val regLeftPx = region.left * w
        val regTopPx = region.top * h
        val cropW = ((region.right - region.left) * w).toInt().coerceAtLeast(1)
        val cropH = ((region.bottom - region.top) * h).toInt().coerceAtLeast(1)
        val boxes = ArrayList<Rect>(); val ids = ArrayList<Int>()
        // lastRenderedIds is already zoom-filtered by snapshotScreen when a region is active; fall back to
        // an explicit in-region filter only if no snapshot has run yet.
        val rendered = if (lastRenderedIds.isNotEmpty()) lastRenderedIds.toList()
            else currentNodes.indices.filter { nodeInZoom(currentNodes[it], w, h) }
        for (i in rendered) {
            val n = currentNodes.getOrNull(i) ?: continue
            val r = Rect(); n.getBoundsInScreen(r)
            boxes.add(Rect((r.left - regLeftPx).toInt(), (r.top - regTopPx).toInt(),
                           (r.right - regLeftPx).toInt(), (r.bottom - regTopPx).toInt()))
            ids.add(i)
        }
        return ScreenMarks(cropW, cropH, boxes, ids)
    }

    /** Batch B (foveated flashlight): the objective-INDEPENDENT name of the BUSIEST region of the screen,
     *  so a too-dense screen has a cheap answer to "read it without going blind" - the agent PEEKs there
     *  at full detail. A 3x3 node-density tally of what's already been collected -> the hottest cell -> one
     *  of the region names parseZoomRegion already understands (top/bottom/left/right/center/corners). NEVER
     *  boosted by the objective (§2/§12: perception, not a decision; nothing is hidden - find/next_page/zoom
     *  still reach every node). "" when the screen is small enough to read whole or already zoomed. */
    fun regionMap(): String {
        val nodes = currentNodes
        if (nodes.size < 24 || zoomRegion != null) return ""
        val w = resources.displayMetrics.widthPixels.toFloat()
        val h = resources.displayMetrics.heightPixels.toFloat()
        if (w <= 0f || h <= 0f) return ""
        val grid = IntArray(9)
        for (n in nodes) {
            val r = Rect(); try { n.getBoundsInScreen(r) } catch (_: Exception) { continue }
            val cx = ((r.exactCenterX() / w) * 3f).toInt().coerceIn(0, 2)
            val cy = ((r.exactCenterY() / h) * 3f).toInt().coerceIn(0, 2)
            grid[cy * 3 + cx]++
        }
        val hot = grid.indices.maxByOrNull { grid[it] } ?: return ""
        if (grid[hot] == 0) return ""
        val row = hot / 3; val col = hot % 3
        val vert = when (row) { 0 -> "top"; 2 -> "bottom"; else -> "" }
        val horiz = when (col) { 0 -> "left"; 2 -> "right"; else -> "" }
        return listOf(vert, horiz).filter { it.isNotBlank() }.joinToString("-").ifBlank { "center" }
    }

    /** Semantic role for an element - the "vector space" idea: the model reasons over
     *  roles (button/field/toggle/tab/icon) instead of raw widget class names. */
    private fun role(node: AccessibilityNodeInfo): String {
        val cn = node.className?.toString()?.substringAfterLast('.') ?: ""
        return when {
            node.isEditable || cn.contains("EditText") -> "field"
            node.isCheckable || cn.contains("Switch") || cn.contains("CheckBox") || cn.contains("RadioButton") -> "toggle"
            cn.contains("Tab", true) -> "tab"
            // TOKEN-LIGHT (owner: "translate elements into something less token-heavy"): a plain tappable
            // control is the DEFAULT - every listed element is something you can tap - so stamping "button"/
            // "icon" on each of ~20 lines is pure prompt weight (and prefill time, and overflow pressure).
            // Emit NOTHING for them; the [N] + label already say "tap this". Only the genuinely different
            // types (field/toggle/tab, or a rare non-clickable view) keep a word, because they change HOW the
            // agent interacts (type vs toggle vs tap).
            cn.contains("Button") -> ""
            cn.contains("ImageView") && node.isClickable -> ""
            cn.contains("TextView") && node.isClickable -> ""
            node.isClickable -> ""
            else -> cn.ifBlank { "view" }
        }
    }

    /** A2 collapse key: two CONSECUTIVE siblings with the same sig are "the same kind of row" and can fold.
     *  Built from role + label-shape + interaction flags + STATE, so a [selected]/[checked]/[disabled]/
     *  [focused] row, or a field/toggle among plain rows, gets a different sig and always renders in full. */
    private fun structuralSig(node: AccessibilityNodeInfo): String {
        val hasText = !node.text.isNullOrBlank()
        val hasDesc = !node.contentDescription.isNullOrBlank()
        return "${role(node)}|${if (hasText) "t" else ""}${if (hasDesc) "d" else ""}|" +
            "${node.isClickable}${node.isEditable}${node.isCheckable}${node.isLongClickable}|" +
            "${node.isSelected}${node.isChecked}${node.isEnabled}${node.isFocused}|" +
            "${node.childCount.coerceAtMost(4)}"
    }

    private fun describe(node: AccessibilityNodeInfo, w: Int, h: Int): String {
        val parts = mutableListOf<String>()
        val r = role(node); if (r.isNotEmpty()) parts.add(r) // most controls are the default tap -> no role word
        // Truncate long labels (a whole chat paragraph or a giant browser-tab title can be
        // hundreds of chars) so one element can't blow the model's input-token budget. The
        // model only needs enough to identify the element, not its full contents.
        val text = node.text?.toString()?.trim()?.let { clip(it, 70) }
        val desc = node.contentDescription?.toString()?.trim()?.let { clip(it, 70) }
        // A field's HINT (placeholder) is its NAME when it carries no text/desc - "Reply to Claude…",
        // "Search", "Email". Modern Compose/Flutter UIs (the Claude app, and many others) expose the composer
        // + search boxes with ONLY a hint and no label/resource-id, so without this the element list is a
        // BLIND row of identical `field [editable]` entries and the model types into the WRONG field (the
        // owner's repeated "wrong text field" correction, and the cl17-vs-st17 mis-pick). Surface it, tagged
        // `hint:` so it's read as the field's purpose, never mistaken for typed content (the [ALREADY SENT] /
        // turn-taking checks all key off node.text, never the hint).
        val hint = node.hintText?.toString()?.trim()?.let { clip(it, 70) }
        // Render text AND contentDescription the same way - as "label". The text-vs-desc distinction is
        // irrelevant to the agent (both are just the element's name), so the old "desc:" prefix was 5 chars
        // of pure weight on every icon/image-button (the bulk of a launcher/toolbar). Drop it. The hint is
        // the last resort - only when there's no real label - and IS marked, because a placeholder is
        // semantically different from content (it means the field is empty and what it's FOR).
        when {
            !text.isNullOrBlank() -> parts.add("\"$text\"")
            !desc.isNullOrBlank() -> parts.add("\"$desc\"")
            !hint.isNullOrBlank() -> parts.add("hint:\"$hint\"")
        }
        // TOKEN-LIGHT ELEMENTS (owner: "translate elements into something less token-heavy"): the model
        // targets by the [N] index, NOT by this resource-id string (the executor looks up currentNodes[N]),
        // so on a LABELED element id:xxx is pure prompt weight. Keep it ONLY for a label-less control,
        // where it's the one human-readable identifier the model has. Drops ~3-6 tokens off every labeled
        // element - the bulk of a dense list - buying budget headroom (less OOM) and a lighter path that
        // helps weaker models/hardware get the SAME list within their limits.
        if (text.isNullOrBlank() && desc.isNullOrBlank() && hint.isNullOrBlank())
            node.viewIdResourceName?.substringAfterLast('/')?.let {
                if (it.isNotBlank()) parts.add("id:$it")
            }
        if (node.isEditable) {
            parts.add("[editable]")
            // If the box still shows a message we ALREADY sent (some chats keep it there after
            // sending), say so explicitly - otherwise the model reads its own sent text in the
            // field and re-sends it. This is the repeated-message loop.
            val full = node.text?.toString()?.trim().orEmpty()
            if (full.isNotEmpty() && isRecentlySent(full))
                parts.add("[ALREADY SENT - do NOT resend; write a NEW message or wait for the reply]")
        }
        if (node.isCheckable) parts.add(if (node.isChecked) "[checked]" else "[unchecked]")
        // Deterministic STATE the model otherwise has to GUESS (owner: "reason about the screen,
        // minimize inference"). High-signal, only emitted when true:
        //  - DISABLED: tapping does nothing (a greyed-out Send/Next the model loops on - it should do
        //    the prerequisite first), so we flag it and the click executor refuses it.
        //  - SELECTED: this tab/item is ALREADY the current one - re-tapping is a wasted step.
        //  - FOCUSED: a focused field is where typed text will land.
        if (!node.isEnabled) parts.add("[disabled]")
        if (node.isSelected) parts.add("[selected]")
        if (node.isFocused && node.isEditable) parts.add("[focused]")
        // RANGE controls (slider / seekbar / volume / brightness / rating / progress): the a11y tree carries
        // the EXACT current value the screenshot pixels only approximate. Surface it as [val N%] so the model
        // reads a scrubber/volume position precisely and can target set_value instead of eyeballing a drag.
        // The RangeInfo is already walked by the tree — near-zero cost; null on every non-range control, so
        // it only ever appears where it means something (owner: "reason about the screen, minimize inference").
        try {
            node.rangeInfo?.let { ri ->
                val lo = ri.min; val hi = ri.max
                if (hi > lo) parts.add("[val " + (((ri.current - lo) / (hi - lo)) * 100f).toInt().coerceIn(0, 100) + "%]")
            }
        } catch (_: Exception) {}
        // AFFORDANCES the model can't see in a screenshot but the tree knows - perception that FEEDS the
        // action space (owner: "it should feed action space"). Only NON-obvious verbs (tap/type are already
        // implied by clickable/[editable]); without these the model literally never tries them:
        //  - long-press: a clickable item that ALSO long-presses = a context menu (delete/share/select/
        //    rename/move). Gated to real items (clickable, not a field/toggle) so it isn't list bloat.
        //  - expand/collapse: an accordion/section opened with a normal click - the model can't tell a
        //    collapsed section from a leaf otherwise, so it never expands it.
        //  - opens a menu: a dropdown/spinner/picker (canOpenPopup) - the agent EXPECTS options after the tap.
        //  - named app actions ([do: …]): LABELED custom actions (Archive/Delete/Reply/Pin) baked into the
        //    a11y tree from the swipe/long-press menu that a plain tap can't reach - fire one via {"action":
        //    "do",…}. EXCLUDE the standard verbs already implied elsewhere; cap 3 + clip (full set via `do`
        //    with no name). All tags DEDUPED per snapshot (see seenAffordanceTags - the launcher-grid OOM).
        val aff = mutableListOf<String>()
        if (node.isLongClickable && node.isClickable && !node.isEditable && !node.isCheckable)
            aff.add("[long-press for options]")
        val acts = node.actionList
        when {
            acts.any { it.id == AccessibilityNodeInfo.AccessibilityAction.ACTION_EXPAND.id } -> aff.add("[expandable]")
            acts.any { it.id == AccessibilityNodeInfo.AccessibilityAction.ACTION_COLLAPSE.id } -> aff.add("[expanded-tap to collapse]")
        }
        if (try { node.canOpenPopup() } catch (_: Exception) { false }) aff.add("[opens a menu]")
        val standardActIds = setOf(
            AccessibilityNodeInfo.AccessibilityAction.ACTION_CLICK.id,
            AccessibilityNodeInfo.AccessibilityAction.ACTION_LONG_CLICK.id,
            AccessibilityNodeInfo.AccessibilityAction.ACTION_EXPAND.id,
            AccessibilityNodeInfo.AccessibilityAction.ACTION_COLLAPSE.id,
            AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_FORWARD.id,
            AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_BACKWARD.id,
            AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_UP.id,
            AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_DOWN.id,
            AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_LEFT.id,
            AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_RIGHT.id,
            AccessibilityNodeInfo.AccessibilityAction.ACTION_SET_TEXT.id,
            AccessibilityNodeInfo.AccessibilityAction.ACTION_FOCUS.id,
            AccessibilityNodeInfo.AccessibilityAction.ACTION_SELECT.id,
            AccessibilityNodeInfo.AccessibilityAction.ACTION_CLEAR_FOCUS.id,
            AccessibilityNodeInfo.AccessibilityAction.ACTION_CLEAR_SELECTION.id)
        val namedActs = acts.filter { it.id !in standardActIds && !it.label?.toString()?.trim().isNullOrEmpty() }
            .map { clip(it.label.toString().trim(), 16) }
        if (namedActs.isNotEmpty()) aff.add("[do: " + namedActs.take(3).joinToString("·") + "]")
        if (acts.any { it.id == AccessibilityNodeInfo.AccessibilityAction.ACTION_DISMISS.id }) aff.add("[dismissable]")
        if (aff.isNotEmpty()) {
            // First element with this exact tag-set shows it; identical repeats are suppressed (footer notes it).
            if (seenAffordanceTags.add(aff.joinToString(""))) parts.addAll(aff) else affordanceTagsSuppressed = true
        }
        if (text.isNullOrBlank() && desc.isNullOrBlank()) {
            val r = Rect(); node.getBoundsInScreen(r)
            parts.add("@" + positionHint(r.centerX(), r.centerY(), w, h))
        }
        return parts.joinToString(" ")
    }

    private fun positionHint(cx: Int, cy: Int, w: Int, h: Int): String {
        val col = when { cx < w / 3 -> "left"; cx > 2 * w / 3 -> "right"; else -> "center" }
        val row = when { cy < h / 3 -> "top"; cy > 2 * h / 3 -> "bottom"; else -> "middle" }
        return "$row-$col"
    }

    /** LANG (docs/AGENT_LANGUAGE.md): a COMPACT re-render of the SAME elements the last snapshotScreen()
     *  badged (`lastRenderedIds`), for the MODEL prompt only, gated by the agent_language flag + vision. Each
     *  item is AgentLanguage.renderItem(id, role, state, iconLabel) — ~≤2 tokens; the a11y label is dropped
     *  for a text-bearing element (the screenshot pixels show it) and KEPT (short) only for an icon-only one
     *  (contentDescription, no visible text — pixels can't carry it). Reuses the just-built currentNodes (no
     *  extra tree walk); ids/badges/tap path untouched, so internal logic keeps using the labeled
     *  snapshotScreen() output and the exact text stays reachable via get_text/find (§12). */
    fun codecScreen(): String {
        val sb = StringBuilder()
        sb.append("app: ").append(currentPackage()?.substringAfterLast('.') ?: "?").append("\n")
        for (id in lastRenderedIds) {
            val node = currentNodes.getOrNull(id) ?: continue
            val roleC = AgentLanguage.roleChar(role(node))
            val stateC = AgentLanguage.stateChar(node.isEnabled, node.isSelected, node.isFocused,
                node.isEditable, node.isCheckable, node.isChecked)
            val hasText = !node.text?.toString()?.trim().isNullOrBlank()
            val iconLabel = if (!hasText) node.contentDescription?.toString()?.trim()
                ?.takeIf { it.isNotBlank() }?.let { clip(it, 14) } else null
            sb.append(AgentLanguage.renderItem(id, roleC, stateC, iconLabel)).append("\n")
        }
        // More elements exist than were rendered (paging/collapse) — say so, so nothing reads as hidden.
        if (currentNodes.size > lastRenderedIds.size)
            sb.append("… more elements — next_page/scroll/find to reach them\n")
        // Keep the read-only EXACT-value layer (TEXT ON SCREEN + carrying-clipboard) the compact handles drop
        // and get_text/find can't reproduce verbatim — the zero-hallucination text stays available in codec mode.
        if (lastValueLayer.isNotBlank()) sb.append(lastValueLayer)
        return sb.toString().trimEnd()
    }

    // --- ACTION EXECUTION -------------------------------------------------

    /**
     * Pull the action object out of the raw model text. Handles two real failure
     * modes seen in logs: a stray quote after a number ("id":5"}), and the model
     * emitting the thought and the action as SEPARATE objects ({"thought":..}{"action":..}) -
     * in which case grabbing first-brace..last-brace used to merge them into invalid
     * JSON (a whole wasted step). We prefer the object that actually has "action".
     */
    private fun parseActionObject(raw: String): JSONObject? {
        // Canonical action verbs - used to tell a DOUBLED verb apart from a mis-keyed text payload.
        val salvageVerbs = setOf("click", "tap", "tap_xy", "aim", "snap_tap", "aim_tap",
            "reveal", "scroll_to", "reveal_text", "tap_near", "tap_relative", "tap_grid", "tap_sequence",
            "set_text", "type", "input", "enter_text", "settext", "send", "scroll", "back", "home",
            "done", "wait", "ask", "open_app", "launch", "open", "openapp", "app_drawer", "drawer",
            "copy", "paste", "read_clipboard", "recent_apps", "connected_devices", "devices",
            "sketch", "draw", "drag", "zoom", "zoom_out", "long_press", "swipe", "search",
            "save_note", "save_login", "enter", "split_screen", "notifications", "quick_settings",
            "dial", "call", "sms", "text_to", "set_alarm", "navigate", "directions", "web", "url", "batch",
            "ocr", "read_text", "read_screen", "read_pixels", "capture", "reply",
            "clear", "clear_field", "erase", "assert", "verify", "check", "confirm",
            "get_text", "read_field", "read_value", "find", "longpress", "long_click", "hold",
            "set_value", "set_progress", "set_slider", "press_key", "key", "keypress",
            "do", "perform", "act", "menu_action",
            "drag_drop", "drag_and_drop", "move_item", "stash", "park", "note_down",
            "recall", "recall_stash", "unstash", "wait_for", "wait_until", "await", "help", "usage")
        val fix = { s: String ->
            // Salvage common model JSON typos: a stray quote after a NUMERIC VALUE ("id":5" -> "id":5)
            // and a trailing comma before a } or ]. The numeric-quote fix is anchored to a colon (a
            // value), so it never strips the legitimate closing quote of a text string that ends in a
            // digit, e.g. {"text":"452*12/4+75"} - that false match was breaking number input.
            // Also COLLAPSE a runaway repeated char (the model spiral that emitted thousands of
            // zeros, blew the token limit, and took 40s) down to a few.
            s.replace(Regex("(.)\\1{15,}"), "$1$1$1")
                // {"action":"verb":"X"}: if X is a verb it's a DOUBLED verb (keep the first); if it
                // isn't, the model mis-keyed the TEXT after the verb ({"action":"set_text":"I argue..."})
                // - rescue it as "text" instead of DROPPING the message (the debate turns E4B kept losing).
                .replace(Regex("(\"action\"\\s*:\\s*\"\\w+\")\\s*:\\s*\"([^\"]*)\"")) { m ->
                    if (m.groupValues[2].trim().lowercase() in salvageVerbs) m.groupValues[1]
                    else "${m.groupValues[1]},\"text\":\"${m.groupValues[2].replace("\\", "\\\\")}\""
                }
                .replace(Regex(""":(\s*[\d.]+)"(\s*[,}\]])"""), ":$1$2")
                .replace(Regex(""",(\s*[}\]])"""), "$1")
        }
        // Try each top-level {...} object; return the first one that has "action".
        var depth = 0; var objStart = -1
        var firstParsed: JSONObject? = null
        for (i in raw.indices) {
            when (raw[i]) {
                '{' -> { if (depth == 0) objStart = i; depth++ }
                '}' -> {
                    depth--
                    if (depth == 0 && objStart >= 0) {
                        val obj = runCatching { JSONObject(fix(raw.substring(objStart, i + 1))) }.getOrNull()
                        if (obj != null) {
                            if (obj.has("action")) return obj
                            if (firstParsed == null) firstParsed = obj
                        }
                    }
                }
            }
        }
        // No object had "action": fall back to the widest span (best-effort), then
        // to the first thing that parsed at all.
        val start = raw.indexOf('{'); val end = raw.lastIndexOf('}')
        if (start in 0 until end)
            runCatching { JSONObject(fix(raw.substring(start, end + 1))) }.getOrNull()?.let { return it }
        if (firstParsed != null) return firstParsed
        // Last-ditch: the JSON is broken (e.g. a model spiral left an UNTERMINATED string, so
        // nothing parses). Pull out action + id + text directly with regex and rebuild a clean
        // object, ignoring the trailing garbage - turns a wasted step into a usable action.
        val collapsed = raw.replace(Regex("(.)\\1{15,}"), "$1$1$1")
        val act = Regex("\"action\"\\s*:\\s*\"(\\w+)\"").find(collapsed)?.groupValues?.get(1)
            ?: return null
        return JSONObject().apply {
            put("action", act)
            // toIntOrNull + digit cap: the salvage runs on runaway/malformed output, and an 11+-digit id
            // (which the (.)\1{15,} collapse above misses when the digits differ or run <16) overflows a raw
            // toInt() -> NumberFormatException that crashed the whole decision. Bound + parse-safe instead.
            Regex("\"id\"\\s*:\\s*\"?(\\d+)").find(collapsed)?.groupValues?.get(1)?.take(9)?.toIntOrNull()?.let { put("id", it) }
            Regex("\"text\"\\s*:\\s*\"(.*?)(?:\"|$)", setOf(RegexOption.DOT_MATCHES_ALL))
                .find(collapsed)?.let { put("text", it.groupValues[1].take(200)) }
        }
    }

    /** Shared coordinate-tap core for tap_xy (LITERAL) and aim (forgiving SNAP). The caller has already
     *  mapped fractions/cells to real screen PIXELS. This validates display coordinates and dispatches. `snap`=
     *  true (aim only) nudges a near-miss onto the nearest clickable center first - the Agent S2 grounding
     *  lesson: small models NAME targets well but AIM poorly, so the near-miss tap that lands on dead space
     *  and wastes the whole step becomes a hit. tap_xy passes snap=false so a literal pixel tap - and a
     *  deliberate canvas stroke - lands EXACTLY where asked. */
    private fun tapAtPoint(x: Int, y: Int, say: String?, snap: Boolean): ActionOutcome {
        val w = resources.displayMetrics.widthPixels
        val h = resources.displayMetrics.heightPixels
        // Reject hallucinated off-screen coordinates (the model's "token spiral" emits x=3000 / y=333333).
        if (x < 0 || y < 0 || x > w || y > h)
            return ActionOutcome(ActionResult.FAILED, say, "tap ($x,$y) is off-screen; the screen is ${w}x${h}")
        // SNAP-TO-TARGET (aim only): if the point hits NO element but a clickable's center is within a
        // thumb-radius, snap to that center. Pure aim-correction, tightly bound so it can never redirect a
        // deliberate tap: never in a drawing canvas (blank space IS the target there), never when zoomed
        // (coords are already precise), never when the point already lands on something, never beyond 48px.
        var sx = x; var sy = y; var snapped = false
        if (snap && !drawingMode && zoomRegion == null && findNodeAt(x, y) == null) {
            currentNodes.filter { it.isClickable && it.isVisibleToUser }
                .mapNotNull { n ->
                    val r = Rect(); n.getBoundsInScreen(r)
                    val d = Math.hypot((r.centerX() - x).toDouble(), (r.centerY() - y).toDouble())
                    if (d <= 44.0 * resources.displayMetrics.density) Pair(n, d) else null   // density-scaled thumb radius (was a hard 48px ≈ 18dp on the Fold — smaller than a fingertip, so most real near-misses never snapped)
                }.minByOrNull { it.second }?.first?.let { n ->
                    val r = Rect(); n.getBoundsInScreen(r)
                    sx = r.centerX(); sy = r.centerY(); snapped = true
                    AgentLog.log("act", "aim ($x,$y) snapped to \"${clip(nodeLabel(n), 24)}\" center ($sx,$sy)")
                }
        }
        val node = findNodeAt(sx, sy)
        val label = (node?.text ?: node?.contentDescription)?.toString()?.trim().orEmpty()
        tap(sx.toFloat(), sy.toFloat())
        // Batch 6 DEAD-SPACE AIM NOTE: an aim tap that snapped to nothing and lands on no node is likely a
        // mis-aim at a static label/image (the one uncovered [9iv] cross-modal slice). Still tap (a deliberate
        // canvas tap stays legal via !drawingMode), but hand back a read-only note so the model recovers in ONE
        // move instead of silently wasting the step. NOT "suspicious" - dead space is a legitimate canvas /
        // tap_xy condition; only the aim-vs-tree discrepancy is surfaced. tap_xy passes snap=false so it's exempt.
        val tail = when {
            label.isNotEmpty() -> " ($label)"
            snap && !snapped && !drawingMode && zoomRegion == null && node == null ->
                " - no interactive control at that point (likely a static label/image); if you meant a control, find/zoom/ocr it first; if it's a canvas, tap_xy is right"
            else -> ""
        }
        return ActionOutcome(ActionResult.CONTINUE, say, "tapped ($sx,$sy)$tail")
    }

    fun performActionJson(raw: String): ActionOutcome {
        // ── STRAY-TAP-IN-SLEEP INVARIANT (07-09c, owner: "stray taps happened while asleep") ──────────────────────
        // The bulletproof rule: the agent may inject an input ONLY while a task is actually running. In sleep,
        // AgentService is gone and isAgentBusy=false, so EVERY action here — a gesture OR a performGlobalAction
        // home/back — is refused, whatever the source (a leftover callback, a future bug). Legit task/auto/learn/
        // gauntlet flows all set isAgentBusy=true before their first action, so nothing real is blocked. If stray
        // taps somehow continue after this, the software is provably not the source (⇒ digitizer/hardware).
        if (!AgentService.isAgentBusy) {
            AgentLog.log("act", "refused action — no active task (idle/sleep)")
            return ActionOutcome(ActionResult.FAILED, null, "no active task — injection refused while idle/sleep")
        }
        // LANG (docs/AGENT_LANGUAGE.md): when the agent-language flag is on and the model emitted a bare
        // compact CODE (`cl5`, `pk9`, `oa:Chrome`) instead of JSON, expand it to canonical JSON first.
        // decodeAction is correct-or-abstain (returns null for JSON / natural text / complex verbs), so this
        // is inert when the flag is off and never disturbs the existing salvage — a code just becomes JSON.
        val decoded = if (settings.isAgentLanguageEnabled()) AgentLanguage.decodeAction(raw) else null
        if (decoded != null) AgentLog.log("act", "lang code -> $decoded")
        val json = parseActionObject(decoded ?: raw)
            ?: run {
                // ACTION GUARD (light, deterministic): the salvage in parseActionObject couldn't recover a
                // valid action. This is the one improper-call path that lands BEFORE the [audit] line below,
                // so log it as [guard] for visibility - and it becomes a plain FAILED the loop retries (never
                // a crash, never a silent execution, never a dead-end).
                AgentLog.log("guard", "unparseable model output - salvage failed; retried as a no-op")
                return ActionOutcome(ActionResult.FAILED, null, "could not parse model output")
            }

        val say = if (json.has("say")) json.optString("say").ifBlank { null } else null
        // Strip leading/trailing junk the model sometimes wraps a verb in (a stray '_' / quote / bullet /
        // markdown emphasis) BEFORE matching - the owner's "_app_drawer" log: it had used app_drawer fine
        // the step before, then a token glitch added a leading '_' and the whole step was wasted as "unknown
        // action". Internal underscores (set_text, tap_xy, app_drawer) are untouched - only the ends are trimmed.
        val action = when (val a = json.optString("action").lowercase().trim(' ', '_', '-', '.', '*', ':', '"', '\'', '`')) {
            // Salvage common off-list names the model invents (wasted whole steps).
            "type", "input", "enter_text", "settext" -> "set_text"
            "open_app_drawer", "open_drawer", "drawer", "apps", "app_tray" -> "app_drawer"
            "launch", "open", "open_app_app", "openapp", "launch_app", "start_app" -> "open_app"
            "save_file", "write_note", "write_file", "save_document", "save_text" -> "save_note"
            // "drag" is its OWN verb now (element-to-element press-hold-drag); only the
            // canvas-flavored names still route to draw.
            "drag_path", "draw_path", "trace", "stroke", "gesture", "path" -> "draw"
            // wait_for is intercepted by the LOOP (engine-watched condition); one reaching the
            // executor named no condition, so degrade it honestly to a plain wait.
            "wait_for", "wait_until", "await" -> "wait"
            "sketch", "picture", "figure", "draw_shape", "draw_shapes", "shapes", "drawing" -> "sketch"
            "zoom_in", "zoomin", "magnify", "look", "look_closer", "inspect", "focus",
            "peek", "peek_region", "foveate", "look_at", "examine" -> "zoom"
            "zoomout", "unzoom", "zoom_full", "wide" -> "zoom_out"
            "next", "next_set", "more_elements", "page_down", "more_controls" -> "next_page"
            "prev", "previous", "prev_set", "page_up" -> "prev_page"
            // long_press + find had NO aliases, so these natural variants died as "unknown action" (a wasted
            // step) - for the two most weak-model-friendly verbs. Conservative, unambiguous synonyms only.
            "longpress", "long_click", "long_tap", "hold", "press_and_hold" -> "long_press"
            "tap_label", "tap_text", "click_text", "find_text", "locate_text" -> "find"
            // CODEC-IN-JSON salvage (from the on-device log): with the LANG codec on, the model sometimes
            // emits a bare 2-char CODE inside JSON - {"action":"ad"} (ad = app_drawer), {"action":"oa",…} -
            // instead of as a standalone code line. decodeAction only decodes a bare code LINE, so the code
            // reaches here as an unknown verb and the whole step is wasted ("unknown action 'ad'"). When the
            // codec is on, expand a known code in the action slot to its verb; off => byte-identical (no map).
            else -> if (settings.isAgentLanguageEnabled()) (AgentLanguage.CODE_TO_VERB[a] ?: a) else a
        }
        // Track whether THIS action is a zoom request, so the orchestrator can keep the zoom for a
        // re-target but clear it (back to full screen) after any real action - a one-shot magnifier.
        lastActionWasZoom = action == "zoom" || action == "zoom_out"
        // The model's reasoning (chain-of-thought) - logged so we can see inside the
        // black box what it's actually trying to do.
        json.optString("thought").trim().takeIf { it.isNotEmpty() }?.let { AgentLog.log("think", it) }

        // AUDIT TRAIL (the owner's "what did the agent just DO?" guarantee, after the Device-Care
        // scare): EVERY executor invocation - model-chosen, engine-steered, or batch
        // sub-action, Learn mode - passes through here, so one persisted line records what ran,
        // where, and whether a running task owned it. §14 says an action with NO active task is
        // impossible; if one ever fires, it logs loudly instead of hiding - the log answers the
        // question either way.
        run {
            val tgt = json.optInt("id", -1).takeIf { it >= 0 }?.let { "#$it" }
                ?: json.optString("name").ifBlank { json.optString("text") }
                    .replace('\n', ' ').take(28).ifBlank { "" }
            AgentLog.log("audit", "$action${if (tgt.isEmpty()) "" else " $tgt"} in ${currentPackage() ?: "?"} (executor)" +
                if (AgentService.isAgentBusy) "" else " ⚠ NO ACTIVE TASK - should be impossible (§14)")
        }

        // Any non-drawer action means we've moved on, so the next app_drawer should
        // open fresh rather than continue paging a previous drawer session.
        if (action != "app_drawer") drawerSteps = 0
        // Any REAL action means a new situation, so the element list returns to set 1; only the paging
        // actions move within the current screen's sets.
        if (action != "next_page" && action != "prev_page") elementPage = 0

        return when (action) {
            "done" -> ActionOutcome(ActionResult.DONE, say, "done")
            "wait" -> ActionOutcome(ActionResult.WAIT, say, "waiting")
            "ask" -> {
                val q = json.optString("question").ifBlank { "What would you like me to do?" }
                ActionOutcome(ActionResult.ASK, say, "asked a question", question = q)
            }
            "back" -> { performGlobalAction(GLOBAL_ACTION_BACK); ActionOutcome(ActionResult.CONTINUE, say, "pressed back") }
            "home" -> { performGlobalAction(GLOBAL_ACTION_HOME); ActionOutcome(ActionResult.CONTINUE, say, "went home") }
            "next_page", "prev_page" -> {
                // Move through the element list a fixed set at a time to find a control without
                // listing them all. Cyclic (wraps) so the agent can never strand itself on an empty
                // set. Operates on the LAST snapshot's count; the next snapshot redraws the new set.
                val pages = maxOf(1, (currentNodes.size + perceptionPageSize() - 1) / perceptionPageSize())
                elementPage = if (action == "next_page") (elementPage + 1) % pages
                              else (elementPage - 1 + pages) % pages
                ActionOutcome(ActionResult.CONTINUE, say, "showing element set ${elementPage + 1} of $pages")
            }
            "find", "find_element", "locate", "search_screen" -> {
                // INSTANT, deterministic search of the WHOLE element list (every page at once) for a
                // named control, then tap it. This is what makes paging cheap: the agent doesn't burn a
                // slow vision decision per set to hunt for something it can name - it just `find`s it
                // (the owner's "don't spend 60s scanning each page"). For opening an APP, open_app is
                // still better than finding an icon.
                val q = json.optString("text").ifBlank { json.optString("query") }
                    .ifBlank { json.optString("name") }.trim()
                if (q.isBlank()) ActionOutcome(ActionResult.FAILED, say, "find needs text - the label of the control you want")
                else {
                    fun label(n: AccessibilityNodeInfo) =
                        effectiveText(n).ifBlank { n.contentDescription?.toString().orEmpty() }.trim()
                    // Normalize (lowercase, punctuation -> space) so "sign-in" finds "Sign in", and match in
                    // BOTH directions: the label contains the query (normal), OR an OVER-specified query ("the
                    // Send button") contains the short label as a WHOLE WORD. The reverse direction is now gated
                    // to a SHORT query (<=3 words, i.e. a control reference) + a WHOLE-WORD label match, because
                    // the old unbounded "query contains label as any substring" let "current weather in london"
                    // match "Current" (a banking app) and open it (the owner's payment-app incident). Tightest
                    // match (least extra text) still wins, so "Send" hits the Send button, not a paragraph.
                    fun norm(s: String) = s.lowercase().replace(Regex("[^a-z0-9]+"), " ").trim()
                    val qn = norm(q)
                    val qWordCount = qn.split(" ").count { it.isNotBlank() }
                    val hit = currentNodes.filter {
                        val ln = norm(label(it))
                        ln.isNotEmpty() && (ln.contains(qn) ||
                            (ln.length >= 4 && qWordCount <= 3 && Regex("\\b" + Regex.escape(ln) + "\\b").containsMatchIn(qn)))
                    }.minByOrNull { label(it).length }
                    if (hit == null) {
                        // NEAR-MISS: name the similar labels that ARE here, so the agent instantly knows
                        // whether it merely misnamed the target (tap the right one next step) or should
                        // keep paging - instead of blind page-flipping after every wording mismatch. Pure
                        // perception: `find` stays a PURE QUERY, it does NOT scroll or mutate the screen
                        // (that reveal path is a separate later batch); the existing scroll/paginate
                        // guidance is unchanged.
                        val qWords = q.lowercase().split(Regex("[^a-z0-9]+")).filter { it.length >= 3 }
                        val near = currentNodes.mapNotNull { n ->
                            val l = label(n)
                            if (l.isNotBlank() && qWords.any { l.lowercase().contains(it) }) clip(l, 28) else null
                        }.distinct().take(3)
                        val nearNote = if (near.isEmpty()) "" else " Similar here: ${near.joinToString(" · ")}."
                        ActionOutcome(ActionResult.FAILED, say,
                            "no control matching \"$q\" here - to open an app use open_app; otherwise scroll for more or try different wording.$nearNote")
                    } else { click(hit); ActionOutcome(ActionResult.CONTINUE, say, "found and tapped \"${clip(label(hit), 40)}\"") }
                }
            }
            "reveal", "scroll_to", "reveal_text" -> {
                // SEEK: scroll a NAMED target into view WITHOUT tapping it (distinct from `find`, which
                // locates+TAPS). `reveal` only brings the control on screen so the model LOOKS and decides
                // next - the reveal path the find near-miss handler deferred ("a separate later batch").
                // BOUNDED: at most REVEAL_CAP scrolls, and it stops the instant a scroll MOVES NOTHING
                // (edge reached), so it can never loop.
                val q = json.optString("text").ifBlank { json.optString("query") }
                    .ifBlank { json.optString("name") }.trim()
                if (q.isBlank())
                    ActionOutcome(ActionResult.FAILED, say, "reveal needs text - the label of the control to scroll into view")
                else {
                    fun norm(s: String) = s.lowercase().replace(Regex("[^a-z0-9]+"), " ").trim()
                    val qn = norm(q)
                    // Walk the LIVE tree (not the stale currentNodes, which only refreshes on the next
                    // perceive) for a VISIBLE node whose label matches - bidirectional like find/findByLabel
                    // so a wording near-miss still counts.
                    fun visibleMatch(): Boolean {
                        var hit = false
                        fun walk(n: AccessibilityNodeInfo?) {
                            if (n == null || hit) return
                            if (n.isVisibleToUser) {
                                val ln = norm(nodeLabel(n))
                                if (ln.isNotEmpty() && (ln.contains(qn) || (ln.length >= 4 && qn.contains(ln)))) { hit = true; return }
                            }
                            for (i in 0 until n.childCount) { walk(n.getChild(i)); if (hit) return }
                        }
                        walk(rootInActiveWindow)
                        return hit
                    }
                    // Compact signature of what's on screen (top + short label of each visible text node) to
                    // detect a scroll that MOVED NOTHING - the existing edge detection, reused so the loop
                    // stops early at the end of the list instead of grinding all REVEAL_CAP scrolls.
                    fun sig(): String {
                        val sb = StringBuilder()
                        fun walk(n: AccessibilityNodeInfo?) {
                            if (n == null || sb.length > 400) return
                            if (n.isVisibleToUser) {
                                val l = nodeLabel(n)
                                if (l.isNotBlank()) { val r = Rect(); n.getBoundsInScreen(r); sb.append(r.top).append(':').append(l.take(16)).append('|') }
                            }
                            for (i in 0 until n.childCount) walk(n.getChild(i))
                        }
                        walk(rootInActiveWindow)
                        return sb.toString()
                    }
                    when {
                        // Already on screen: nothing to reveal - hand it back so the model looks/decides.
                        visibleMatch() -> ActionOutcome(ActionResult.CONTINUE, say,
                            "\"$q\" is already visible - look and decide (find to tap it)")
                        // Reuse mainScrollable() (the largest visible scrollable), else the first scrollable.
                        (mainScrollable() ?: findScrollable(rootInActiveWindow)) == null ->
                            ActionOutcome(ActionResult.CONTINUE, say,
                                "nothing scrollable here to reveal \"$q\" - it may not be in this list")
                        else -> {
                            var revealed = false; var moved = true; var i = 0
                            while (i < REVEAL_CAP && !revealed && moved) {
                                val before = sig()
                                scroll("down")               // reuses main-scrollable + performAction/gesture fallback
                                moved = sig() != before      // no-more-movement -> at the edge, stop early
                                revealed = visibleMatch()
                                i++
                            }
                            AgentLog.log("act", "reveal \"${clip(q, 24)}\": ${if (revealed) "into view after $i scroll(s)" else "not found after $i scroll(s)"}")
                            if (revealed) ActionOutcome(ActionResult.CONTINUE, say,
                                "scrolled \"$q\" into view - look and decide (find to tap it)")
                            else ActionOutcome(ActionResult.CONTINUE, say,
                                "couldn't reveal \"$q\" after scrolling - it may not be in this list")
                        }
                    }
                }
            }
            "recent_apps" -> {
                // Open the overview/recents so the agent can SWITCH between running apps (multi-app
                // workflows) or return to the previous one - then tap an app card. More reliable than
                // hunting for an app switcher in-UI.
                performGlobalAction(GLOBAL_ACTION_RECENTS)
                ActionOutcome(ActionResult.CONTINUE, say, "opened recent apps - tap the app card you want, or open_app to launch one")
            }
            "drag", "drag_drop", "drag_and_drop", "move_item" -> {
                // COMPOSITE PRIMITIVE (owner: "combine actions for more sophisticated actions"):
                // press-HOLD-drag one thing onto/next to another - reorder a list, drop a file on a
                // folder, pull a slider, move a home-screen icon. Targets are MAPPABLE: element ids
                // (from_id/to_id), labels (from_text/to_text), or coordinates (0..1 fractions or px).
                fun coord(xv: Double, yv: Double): android.graphics.Point =
                    // Fractions (0..1, through the zoom mapping) or raw pixels - same as tap_xy.
                    if (xv <= 1.0 && yv <= 1.0) viewFracToScreenPx(xv, yv)
                    else android.graphics.Point(xv.toInt(), yv.toInt())
                fun point(idKey: String, textKey: String, xKey: String, yKey: String, arrKey: String): android.graphics.Point? {
                    currentNodes.getOrNull(json.optInt(idKey, -1))?.let {
                        val r = Rect(); it.getBoundsInScreen(r); return android.graphics.Point(r.centerX(), r.centerY())
                    }
                    json.optString(textKey).trim().takeIf { it.isNotBlank() }?.let { q ->
                        findByLabel(q)?.let {
                            val r = Rect(); it.getBoundsInScreen(r); return android.graphics.Point(r.centerX(), r.centerY())
                        }
                    }
                    json.optJSONArray(arrKey)?.let { a ->   // the draw-style {"from":[x,y]} shape still works
                        if (a.length() >= 2) return coord(a.optDouble(0, -1.0), a.optDouble(1, -1.0))
                    }
                    if (json.has(xKey) && json.has(yKey)) {
                        val xv = json.optDouble(xKey, -1.0); val yv = json.optDouble(yKey, -1.0)
                        if (xv >= 0 && yv >= 0) return coord(xv, yv)
                    }
                    return null
                }
                val from = point("from_id", "from_text", "x1", "y1", "from")
                val to = point("to_id", "to_text", "x2", "y2", "to")
                if (from == null || to == null)
                    ActionOutcome(ActionResult.FAILED, say,
                        "drag needs a start and an end - from_id/from_text/x1,y1 and to_id/to_text/x2,y2")
                else {
                    dragGesture(from.x.toFloat(), from.y.toFloat(), to.x.toFloat(), to.y.toFloat())
                    ActionOutcome(ActionResult.CONTINUE, say,
                        "drag-held from (${from.x},${from.y}) to (${to.x},${to.y}) - LOOK to confirm it moved")
                }
            }
            "stash", "park", "note_down" -> {
                // DYNAMIC-CONTEXT LITE (owner's "multiple context windows on one model / limited
                // RAM"): PARK bulky info OUTSIDE the context window under a named key and pull it
                // back only when needed - search results, a gathered list, a long error. The prompt
                // stays small; the data lives here. Task-scoped; capped.
                val key = json.optString("key").ifBlank { json.optString("name") }.trim().take(24)
                val id = json.optInt("id", -1)
                val text = (currentNodes.getOrNull(id)?.let { nodeLabel(it) }?.ifBlank { null }
                    ?: json.optString("text")).take(4000)
                when {
                    key.isBlank() -> ActionOutcome(ActionResult.FAILED, say, "stash needs a \"key\" name")
                    text.isBlank() -> ActionOutcome(ActionResult.FAILED, say, "nothing to stash - give \"text\" or an element id")
                    else -> {
                        if (stash.size >= 8 && !stash.containsKey(key)) stash.remove(stash.keys.first())
                        stash[key] = text
                        ActionOutcome(ActionResult.CONTINUE, say,
                            "stashed ${text.length} chars under \"$key\" - {\"action\":\"recall\",\"key\":\"$key\"} brings it back when you need it")
                    }
                }
            }
            "recall", "recall_stash", "unstash" -> {
                val key = json.optString("key").ifBlank { json.optString("name") }.trim().take(24)
                when {
                    stash.isEmpty() -> ActionOutcome(ActionResult.CONTINUE, say, "the stash is empty - nothing parked this task")
                    key.isBlank() || !stash.containsKey(key) -> ActionOutcome(ActionResult.CONTINUE, say,
                        "stashed keys: " + stash.entries.joinToString(", ") { "\"${it.key}\" (${it.value.length} chars)" } +
                            (if (key.isBlank()) "" else " - no \"$key\""))
                    // Clip what comes back so a huge stash can't blow the prompt budget it was
                    // parked to protect; the agent can stash smaller keyed chunks if it needs all of it.
                    else -> ActionOutcome(ActionResult.CONTINUE, say,
                        "stash \"$key\": ${clip(stash.getValue(key), 1200)}")
                }
            }
            "help", "usage" -> {
                // DEFERRED ACTION DOCS (the MCP tool-search pattern; Anthropic measured 49%->74%
                // tool-selection accuracy from few-full + rest-on-demand): rare verbs live as a
                // one-line INDEX in the prompt (nothing hidden - §12), and the agent self-serves
                // the full format here, paying the tokens only when it actually wants the verb.
                val name = json.optString("about").ifBlank { json.optString("text") }
                    .ifBlank { json.optString("name") }.trim().lowercase().replace(Regex("[^a-z_]"), "")
                val doc = actionHelp(name)
                if (doc.isBlank()) ActionOutcome(ActionResult.CONTINUE, say,
                    "\"$name\" works as shown in the ACTIONS list - no extra detail. (help has full format for: peek, find, reveal, aim, tap_grid, tap_near, tap_sequence, reply, capture, search, copy, ocr, get_text, assert, sketch, draw, save_note, save_login, connected_devices, split_screen, batch, drag, stash, do, wait_for, expect, note)")
                else ActionOutcome(ActionResult.CONTINUE, say, "HOW TO $name: $doc")
            }
            "copy" -> {
                // MOVE DATA BETWEEN APPS: grab a value to carry elsewhere. Source = an element id's
                // text, else literal "text". Store agent-side (paste re-types it reliably) AND mirror to
                // the system clipboard so other apps / the owner can use it.
                val id = json.optInt("id", -1)
                val fromNode = if (id >= 0) currentNodes.getOrNull(id) else null
                val text = (fromNode?.let { effectiveText(it).ifBlank { it.contentDescription?.toString().orEmpty() } }
                    ?.ifBlank { null }) ?: json.optString("text").take(2000)
                if (text.isBlank())
                    ActionOutcome(ActionResult.FAILED, say, "nothing to copy - give an element id that has text, or a \"text\" value")
                else {
                    carriedText = text
                    try { (getSystemService(android.content.Context.CLIPBOARD_SERVICE) as? android.content.ClipboardManager)
                        ?.setPrimaryClip(android.content.ClipData.newPlainText("agent", text)) } catch (_: Exception) {}
                    ActionOutcome(ActionResult.CONTINUE, say, "copied \"${clip(text, 60)}\" - switch to the other app and paste it")
                }
            }
            "paste" -> {
                // Paste the carried value into a field (id, else the focused/lone editable). Uses the
                // agent-carried text; falls back to the system clipboard if we never copied this session.
                val id = json.optInt("id", -1)
                val field = (if (id >= 0) currentNodes.getOrNull(id) else null)
                    ?: rootInActiveWindow?.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)
                    ?: currentNodes.firstOrNull { it.isEditable }
                val value = carriedText ?: try {
                    (getSystemService(android.content.Context.CLIPBOARD_SERVICE) as? android.content.ClipboardManager)
                        ?.primaryClip?.getItemAt(0)?.coerceToText(this)?.toString() } catch (_: Exception) { null }
                when {
                    value.isNullOrBlank() -> ActionOutcome(ActionResult.FAILED, say, "nothing to paste - copy a value first")
                    field == null || !field.isEditable -> ActionOutcome(ActionResult.FAILED, say, "no text field to paste into - tap the field first")
                    setText(field, value) -> {
                        // Verify the paste actually LANDED - cross-app data-carry silently no-ops in some
                        // fields (custom editors, paste swallowed by an autofill/IME), and moving on
                        // assuming success poisons every later step. Read the field back and confirm.
                        field.refresh()
                        val now = field.text?.toString().orEmpty()
                        // Long values: a field may visually truncate, so confirm on the leading slice.
                        val needle = if (value.length > 20) value.take(20) else value
                        if (now.contains(needle, ignoreCase = true))
                            ActionOutcome(ActionResult.CONTINUE, say, "pasted and confirmed: \"${clip(value, 60)}\"")
                        else
                            ActionOutcome(ActionResult.CONTINUE, say, "pasted but the field shows \"${clip(now, 60)}\" - it didn't take; tap the field and paste again")
                    }
                    else -> ActionOutcome(ActionResult.FAILED, say, "couldn't paste into that field")
                }
            }
            "read_clipboard" -> {
                val value = carriedText ?: try {
                    (getSystemService(android.content.Context.CLIPBOARD_SERVICE) as? android.content.ClipboardManager)
                        ?.primaryClip?.getItemAt(0)?.coerceToText(this)?.toString() } catch (_: Exception) { null }
                if (value.isNullOrBlank()) ActionOutcome(ActionResult.CONTINUE, say, "the clipboard is empty - nothing copied yet")
                else ActionOutcome(ActionResult.CONTINUE, say, "clipboard holds: \"${clip(value, 120)}\"")
            }
            "capture", "read_data", "collect" -> {
                // Read a chunk of a big data surface (spreadsheet / long list / table) into the captured
                // buffer EXACTLY, then the agent scrolls to the next chunk and captures again - so all of
                // it is collected without any one screen being too big to handle. Deterministic capture =
                // zero hallucination.
                val added = captureVisibleData()
                val total = collectedData.size
                if (total == 0) ActionOutcome(ActionResult.FAILED, say, "nothing readable on screen to capture")
                else ActionOutcome(ActionResult.CONTINUE, say,
                    "captured $added new value(s) ($total total). If there's more, SCROLL to the next part and " +
                    "capture again; once a scroll+capture adds nothing new you've got it all - then save_note to write it out.")
            }
            "connected_devices", "devices" -> ActionOutcome(ActionResult.CONTINUE, say, connectedDevices())
            "quick_settings" -> {
                // Deterministic way to reach Wi-Fi / Bluetooth / brightness / flashlight
                // tiles - the model is unreliable at swiping down from the status bar.
                val ok = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S)
                    performGlobalAction(GLOBAL_ACTION_QUICK_SETTINGS) else false
                ActionOutcome(if (ok) ActionResult.CONTINUE else ActionResult.FAILED, say,
                    if (ok) "opened quick settings" else "couldn't open quick settings")
            }
            "notifications" -> {
                performGlobalAction(GLOBAL_ACTION_NOTIFICATIONS)
                ActionOutcome(ActionResult.CONTINUE, say, "opened notifications")
            }
            "search" -> {
                // The model often emits a bare "search"; do a real web search deterministically.
                val q = json.optString("text").ifBlank { json.optString("query") }
                when {
                    q.isBlank() -> ActionOutcome(ActionResult.FAILED, say, "search needs text")
                    // Part A (offline-at-use): a web search needs network. If we're offline, say so clearly so the
                    // agent does the task ON-DEVICE (an installed app) or asks the owner instead of burning steps
                    // launching a browser that just shows an offline page. Everything else works fully offline.
                    !DeviceStats.isOnline(this) -> ActionOutcome(ActionResult.FAILED, say,
                        "OFFLINE - a web search can't return. Do this on-device (open an installed app) or ask the owner; don't retry search.")
                    else -> {
                        val ok = try {
                            startActivity(Intent(Intent.ACTION_VIEW,
                                android.net.Uri.parse("https://www.google.com/search?q=" + android.net.Uri.encode(q)))
                                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)); true
                        } catch (_: Exception) { false }
                        ActionOutcome(if (ok) ActionResult.CONTINUE else ActionResult.FAILED, say,
                            if (ok) "web-searched: $q" else "couldn't search")
                    }
                }
            }
            // DEEP-LINK PRIMITIVES (#4): agent-CHOSEN shortcuts that land on a ready screen in ONE step
            // instead of piloting 6-10 fragile GUI taps. None of them auto-commit a consequential action -
            // dial opens the dialer (agent still taps Call), sms opens a pre-filled draft (the normal Send
            // path/confirmation still runs), set_alarm shows the Clock UI - so they're reliable navigation,
            // not autonomous sends. The agent picks them from the action doc; nothing is keyword-gated.
            "dial", "call" -> {
                val num = json.optString("number").ifBlank { json.optString("text") }
                if (num.isBlank()) ActionOutcome(ActionResult.FAILED, say, "dial needs a number")
                else {
                    val ok = fireIntent(Intent(Intent.ACTION_DIAL, android.net.Uri.parse("tel:" + android.net.Uri.encode(num))))
                    ActionOutcome(if (ok) ActionResult.CONTINUE else ActionResult.FAILED, say,
                        if (ok) "opened the dialer for $num - tap the call button to place the call" else "couldn't open the dialer")
                }
            }
            "sms", "text_to" -> {
                val num = json.optString("number").ifBlank { json.optString("to") }
                val body = json.optString("text").ifBlank { json.optString("message") }
                if (num.isBlank()) ActionOutcome(ActionResult.FAILED, say, "sms needs a recipient number")
                else {
                    val ok = fireIntent(Intent(Intent.ACTION_SENDTO, android.net.Uri.parse("smsto:" + android.net.Uri.encode(num)))
                        .putExtra("sms_body", body))
                    ActionOutcome(if (ok) ActionResult.CONTINUE else ActionResult.FAILED, say,
                        if (ok) "opened Messages with a draft to $num - review it, then press Send" else "couldn't open Messages")
                }
            }
            "set_alarm" -> {
                val hour = json.optInt("hour", -1)
                val minute = json.optInt("minute", 0)
                val label = json.optString("label").ifBlank { json.optString("text") }
                if (hour < 0) ActionOutcome(ActionResult.FAILED, say, "set_alarm needs an hour (0-23)")
                else {
                    val intent = Intent(android.provider.AlarmClock.ACTION_SET_ALARM)
                        .putExtra(android.provider.AlarmClock.EXTRA_HOUR, hour)
                        .putExtra(android.provider.AlarmClock.EXTRA_MINUTES, minute)
                    if (label.isNotBlank()) intent.putExtra(android.provider.AlarmClock.EXTRA_MESSAGE, label)
                    val ok = fireIntent(intent)
                    ActionOutcome(if (ok) ActionResult.CONTINUE else ActionResult.FAILED, say,
                        if (ok) "set an alarm for ${"%02d:%02d".format(hour, minute)}${if (label.isNotBlank()) " ($label)" else ""}"
                        else "couldn't set the alarm directly - open the Clock app and add it")
                }
            }
            "navigate", "directions" -> {
                val dest = json.optString("to").ifBlank { json.optString("text").ifBlank { json.optString("query") } }
                if (dest.isBlank()) ActionOutcome(ActionResult.FAILED, say, "navigate needs a destination")
                else {
                    val ok = fireIntent(Intent(Intent.ACTION_VIEW, android.net.Uri.parse("geo:0,0?q=" + android.net.Uri.encode(dest))))
                    ActionOutcome(if (ok) ActionResult.CONTINUE else ActionResult.FAILED, say,
                        if (ok) "opened Maps for \"$dest\"" else "couldn't open Maps")
                }
            }
            "web", "url" -> {
                // A bare query should use `search`; this opens the specific URL the agent chose.
                val url0 = json.optString("url").ifBlank { json.optString("text") }.trim()
                val url = if (url0.startsWith("http", true)) url0 else "https://$url0"
                if (url0.isBlank()) ActionOutcome(ActionResult.FAILED, say, "web needs a url")
                else {
                    val ok = fireIntent(Intent(Intent.ACTION_VIEW, android.net.Uri.parse(url)))
                    ActionOutcome(if (ok) ActionResult.CONTINUE else ActionResult.FAILED, say,
                        if (ok) "opened $url" else "couldn't open that url")
                }
            }
            "batch" -> {
                // Execute each model-authored sub-step in order. The orchestrator still uses its
                // fresh-snapshot path when it intercepts a guarded batch; this fallback does not
                // narrow the verbs available to a direct batch request.
                val steps = json.optJSONArray("steps")
                    ?: return ActionOutcome(ActionResult.FAILED, say, "batch needs a \"steps\" array of actions")
                var ran = 0; var last = ""
                for (i in 0 until minOf(steps.length(), 4)) {
                    val sub = steps.optJSONObject(i)
                        ?: return ActionOutcome(ActionResult.FAILED, say, "batch step $i must be an action object")
                    val out = performActionJson(sub.toString())
                    ran++; last = out.summary
                    if (out.result != ActionResult.CONTINUE)
                        return ActionOutcome(out.result, say, "batch: $last (stopped after $ran - look and continue)")
                }
                ActionOutcome(ActionResult.CONTINUE, say, "batch: $ran input(s) done ($last)")
            }
            "save_login" -> {
                // Record a credential the agent just created, so it's auditable in
                // Agent memory and reusable later. Secrets are never put in the prompt.
                val svc = json.optString("service")
                val user = json.optString("username")
                AgentMemory.addLogin(this, svc, user,
                    json.optString("password").ifBlank { json.optString("secret") })
                createdArtifacts.add("login for $svc" + (if (user.isNotBlank()) " (user: $user)" else ""))
                ActionOutcome(ActionResult.CONTINUE, say, "saved login for $svc")
            }
            "save_note" -> {
                // The agent WROTE something (notes, a draft, gathered results) and wants to keep it
                // as a file the owner can open. Saved to Downloads/AgentNotes and surfaced in the
                // return-to-chat summary as a created artifact.
                // No text given but a capture sweep is in the buffer -> write the whole collected
                // dataset out (the spreadsheet-reading payoff: sweep in chunks, then save_note once).
                val text = json.optString("text").ifBlank { json.optString("content") }
                    .ifBlank { if (collectedData.isNotEmpty()) collectedDataText() else "" }
                val nm = json.optString("name").ifBlank { json.optString("title") }
                if (text.isBlank()) ActionOutcome(ActionResult.CONTINUE, say, "save_note needs text to save")
                else saveNote(nm, text)?.let {
                    createdArtifacts.add("note: $it")
                    ActionOutcome(ActionResult.CONTINUE, say, "saved a note to $it")
                } ?: ActionOutcome(ActionResult.FAILED, say, "couldn't save the note")
            }
            "app_drawer" -> {
                val w = resources.displayMetrics.widthPixels
                val h = resources.displayMetrics.heightPixels
                if (drawerSteps == 0) {
                    // First call: go home FIRST so this always OPENS the drawer instead
                    // of toggling it shut - this is what caused the open/close ping-pong.
                    performGlobalAction(GLOBAL_ACTION_HOME)
                    android.os.Handler(android.os.Looper.getMainLooper()).postDelayed({
                        swipe(w / 2f, h * 0.92f, w / 2f, h * 0.25f, 250L)
                    }, 350L)
                    drawerSteps++
                    ActionOutcome(ActionResult.CONTINUE, say, "opened app drawer")
                } else if (drawerSteps >= DRAWER_PAGE_CAP) {
                    // Paged the whole drawer without finding it - stop hunting (the "stop
                    // drawer-scrolling" backstop). The reliable paths are a named open_app or
                    // the drawer's Search field.
                    drawerSteps = 0
                    ActionOutcome(ActionResult.FAILED, say,
                        "couldn't find it by paging the drawer - use open_app with the app's exact name, or tap the drawer's Search field and type it")
                } else {
                    // Drawer already open: PAGE it using the drawer's OWN scroll direction.
                    // NEVER alternate axes - on a launcher whose drawer pages sideways (One
                    // UI), a vertical swipe DISMISSES the drawer, which is exactly what made
                    // the app search ping-pong. ACTION_SCROLL_FORWARD moves the grid the way
                    // it actually scrolls; only if no scrollable is exposed do we fall back to
                    // a single, CONSISTENT horizontal page (still never a vertical one).
                    val scrollable = findScrollable(rootInActiveWindow)
                    val scrolled = scrollable?.performAction(
                        AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_FORWARD.id) ?: false
                    if (scrollable != null && !scrolled) {
                        // The drawer's OWN scroller reports it can't advance - we're at the END (the
                        // owner's "swiped right while already at the end of the drawer" flail). A blind
                        // swipe just hits a wall, so stop paging and steer to the reliable paths.
                        drawerSteps = 0
                        ActionOutcome(ActionResult.FAILED, say,
                            "reached the end of the app drawer without finding it - use open_app with the app's exact name, or tap the drawer's Search field and type it")
                    } else {
                        // No scrollable exposed: a single CONSISTENT horizontal page is the only way.
                        if (!scrolled) swipe(w * 0.85f, h * 0.5f, w * 0.15f, h * 0.5f, 250L)
                        drawerSteps++
                        ActionOutcome(ActionResult.CONTINUE, say, "paged the app drawer (looking for the app)")
                    }
                }
            }
            "enter" -> {
                val focused = rootInActiveWindow?.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)
                val ok = focused?.performAction(
                    AccessibilityNodeInfo.AccessibilityAction.ACTION_IME_ENTER.id
                ) ?: false
                ActionOutcome(if (ok) ActionResult.CONTINUE else ActionResult.FAILED, say,
                    if (ok) "pressed enter" else "no focused field to submit")
            }
            "split_screen" -> {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N)
                    performGlobalAction(GLOBAL_ACTION_TOGGLE_SPLIT_SCREEN)
                ActionOutcome(ActionResult.CONTINUE, say, "toggled split screen")
            }
            "open_app" -> {
                // Always allowed: launching by name beats hunting the drawer. But if
                // the app is ALREADY in front, do NOT relaunch - that no-op was the
                // cause of endless open_app spam. Tell the model to get on with it.
                val name = normalizeAppName(json.optString("name"))
                // Blank name (the model emitted open_app with only a "thought") used to fall
                // through to a pointless Play Store search. Don't act on nothing.
                if (name.isBlank())
                    return ActionOutcome(ActionResult.FAILED, say,
                        "open_app needs an app name (e.g. open_app Gemini) - none given")
                val pkg = resolvePackage(name)
                if (isAlreadyForeground(name, pkg)) {
                    // The "new chat" warning only applies to a chat app (Gemini) - don't leak it onto
                    // Notes/etc. where it's just confusing. Push the model to ACT on the screen instead.
                    val pkgL = pkg ?: ""
                    val chatWarn = if (name.lowercase().contains("gemini") || pkgL.contains("bard") ||
                        pkgL.contains("quicksearchbox")) " (re-opening starts a NEW chat - never do that)" else ""
                    ActionOutcome(ActionResult.FAILED, say,
                        "$name is already open - ACT on the screen you SEE now (tap an element, or press back if a pop-up is on top); do NOT open $name again$chatWarn")
                }
                else if (openApp(name))
                    ActionOutcome(ActionResult.CONTINUE, say, "opened app $name")
                else {
                    // Not installed: open the Play Store search so it can be installed,
                    // instead of dead-ending on "could not find app".
                    val ok = try {
                        startActivity(Intent(Intent.ACTION_VIEW,
                            android.net.Uri.parse("market://search?q=" + android.net.Uri.encode(name)))
                            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)); true
                    } catch (_: Exception) { false }
                    ActionOutcome(if (ok) ActionResult.CONTINUE else ActionResult.FAILED, say,
                        if (ok) "$name isn't installed - opened Play Store to get it (tap Install)"
                        else "could not find or install app $name")
                }
            }
            "send" -> {
                // What's actually in the box? If it's empty there is nothing to send: either
                // we just sent (turn-taking → WAIT for the reply; do NOT fire Send at empty
                // air, which used to tap random UI) or the model jumped ahead of typing.
                val field = rootInActiveWindow?.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)
                    ?: currentNodes.firstOrNull { it.isEditable }
                field?.refresh()
                val content = field?.text?.toString()?.trim().orEmpty()
                if (content.isBlank()) {
                    if (recentlySentAny())
                        ActionOutcome(ActionResult.WAIT, say,
                            "already sent - waiting for the reply, not sending again")
                    else
                        ActionOutcome(ActionResult.FAILED, say,
                            "nothing typed to send yet - type the message first, then send")
                } else {
                    // Press the app's real Send control (labeled first; never the mic). pressSend
                    // marks it pending; confirmPendingSend marks it sent only once it actually lands.
                    val ok = pressSend(content)
                    when {
                        ok -> ActionOutcome(ActionResult.CONTINUE, say, "pressed Send")
                        // pressSend just expanded a collapsed composer instead of sending - that's
                        // progress, not a failure: the real Send appears now, so send next.
                        System.currentTimeMillis() - lastExpandAt < 1500L ->
                            ActionOutcome(ActionResult.CONTINUE, say, "opened the collapsed composer - the Send button is ready now, send again")
                        else -> ActionOutcome(ActionResult.FAILED, say,
                            "no Send button found - tap the send arrow (far right, NOT the mic) with tap_xy")
                    }
                }
            }
            "scroll" -> {
                val dir = json.optString("direction", "down")
                val id = json.optInt("id", -1)
                val from = if (id >= 0) currentNodes.getOrNull(id) else null
                val ok = scroll(dir, from)
                ActionOutcome(if (ok) ActionResult.CONTINUE else ActionResult.FAILED, say,
                    if (ok) "scrolled $dir" + (if (id >= 0) " (element $id)" else "")
                    // The engine REMINDS clearly when a scroll did nothing (at the edge), instead of the
                    // old misleading "scrolled $dir": this is the owner's "remind him it won't work".
                    else "can't scroll $dir - already at the EDGE; scrolling this way does NOTHING. Go a DIFFERENT direction, or use find/open_app/back.")
            }
            "set_text" -> {
                val id = json.optInt("id", -1)
                // The text to type. E4B has a failure mode where it puts the MESSAGE into the "id"
                // slot ({"action":"set_text","id":"I argue ..."}) and omits "text" - the field then
                // gets typed EMPTY and the message is lost (the debate turns it never conducted). If
                // "id" isn't a number and there's no "text", the id's own string value IS the text.
                // PAYLOAD CAP raised 500->4000 (the owner's "cutoff sentence" bug): a legitimate long
                // message (a compose / argue-a-stance task) was being truncated mid-sentence at 500 chars,
                // and because set_text REPLACES the field the model kept re-typing "the rest" and getting
                // cut again. A true model spiral is already collapsed UPSTREAM in parseActionObject
                // (the (.)\1{15,} squash), so this cap now only bounds real content, never a runaway.
                val textSrc = json.optString("text")
                var text = textSrc.take(4000)
                var textCappedFrom = if (textSrc.length > 4000) textSrc.length else 0
                if (text.isBlank()) {
                    val idRaw = json.optString("id")
                    if (idRaw.isNotBlank() && idRaw.toIntOrNull() == null) {
                        text = idRaw.take(4000); textCappedFrom = if (idRaw.length > 4000) idRaw.length else 0
                    }
                }
                var node = currentNodes.getOrNull(id)
                if (node == null) {
                    // Out-of-range id (a small-model hallucination - e.g. "22222" for field 22):
                    // if there's an unambiguous text field, type into THAT instead of burning the
                    // step on a hard FAIL. General; only fires when the target is obvious.
                    val focused = rootInActiveWindow?.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)
                    val editables = currentNodes.filter { it.isEditable }
                    node = when {
                        focused != null && focused.isEditable -> focused
                        editables.size == 1 -> editables[0]
                        else -> return ActionOutcome(ActionResult.FAILED, say,
                            "no element $id (only 0..${currentNodes.size - 1} exist)")
                    }
                }
                // Don't type into a non-field (toggle/button). Retarget intelligently so the
                // model can't get stuck hammering set_text on a non-field (an observed loop):
                //  - use the focused field if any; else the ONLY field on screen; else name the
                //    field ids; else say there's NO field here so it does something else.
                if (!node.isEditable) {
                    val focused = rootInActiveWindow?.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)
                    val editables = currentNodes.withIndex().filter { it.value.isEditable }
                    node = when {
                        focused != null && focused.isEditable -> focused
                        editables.size == 1 -> editables[0].value
                        editables.isNotEmpty() -> return ActionOutcome(ActionResult.FAILED, say,
                            "element $id is not a text field - the field(s) are ${editables.joinToString(", ") { "id ${it.index}" }}; set_text one of those")
                        else -> {
                            // The editable field COLLAPSED after typing (e.g. Gemini's half-sheet
                            // hides it once a Send button appears). If a real Send button is now
                            // showing, PRESS IT - the message is already typed, just send it -
                            // instead of giving up with "no text field" (the missed-send window).
                            // pressSend marks it pending; confirmPendingSend verifies it landed.
                            if (text.isNotBlank() && pressSend(text)) {
                                return ActionOutcome(ActionResult.CONTINUE, say, "the input collapsed after typing; pressed Send")
                            }
                            return ActionOutcome(ActionResult.FAILED, say,
                                "element $id is not a text field and there is NO text field on this screen - stop typing; do something else (scroll, open the right screen, or go back)")
                        }
                    }
                }
                // Calculator / keypad fields don't accept programmatic text (set_text silently
                // fails - the field stayed "0" while the model looped). Enter the value by
                // TAPPING the on-screen number/operator buttons instead, deterministically.
                if (text.isNotBlank() && isCalcOrKeypadField(node) && typeViaKeypad(text)) {
                    return ActionOutcome(ActionResult.CONTINUE, say,
                        "entered \"$text\" by tapping the keypad (then tap = to evaluate)")
                }
                // Read the field's CURRENT text accurately (refresh clears the stale cache
                // that made set_text look like it failed, causing endless re-typing).
                node.refresh()
                var before = node.text?.toString().orEmpty()
                // Some apps report an EMPTY box's PLACEHOLDER as its text (Gemini's "Ask Gemini"),
                // which defeated the "box is blank" turn-taking check and let the model re-type a
                // message it already sent into a box that only LOOKED non-empty. Treat text that
                // equals the hint as blank.
                val hint = node.hintText?.toString()?.trim().orEmpty()
                if (hint.isNotEmpty() && before.trim() == hint) before = ""
                val key = text.trim().take(24)
                // Anti-repeat (the repeated-intro loop): the model is trying to (re)type a message we
                // ALREADY sent. Don't - drop any stale copy still sitting in the box and WAIT for the
                // reply; in a conversation the autopilot writes the next NEW message. This fires
                // whatever the box shows (blank, placeholder, or the stale duplicate), so it no longer
                // depends on the app clearing the box.
                if (text.isNotBlank() && isRecentlySent(text) && pendingSendText != norm(text)) {
                    if (before.lowercase().contains(norm(text))) setText(node, "") // clear the duplicate
                    val reply = latestReplyText()
                    return ActionOutcome(ActionResult.WAIT, say,
                        if (reply != null) "You already sent that. They replied: \"${reply.take(120)}\". Don't retype it - a new reply is being written."
                        else "You already sent that - waiting for the reply; don't retype it.")
                }
                if (text.isNotBlank() && before.contains(key, ignoreCase = true)) {
                    // CONFIRMED already sent (we SAW it land) -> never resend. The field may just be
                    // retaining the text (some chats keep it). Surface the reply, else wait.
                    if (isRecentlySent(text)) {
                        val reply = latestReplyText()
                        if (reply != null) return ActionOutcome(ActionResult.CONTINUE, say,
                            "ALREADY SENT - and they replied: \"${reply.take(140)}\". Do NOT resend. Reply with a NEW message that builds on it, or finish (done) if the task is complete.")
                        return ActionOutcome(ActionResult.WAIT, say,
                            if (looksSent()) "already sent - their reply is generating; wait, do NOT resend"
                            else "already sent it - waiting for the reply; do NOT resend the same message")
                    }
                    // We just pressed Send for THIS exact message and are waiting to confirm it
                    // landed -> don't press again (avoid double-posting) until we know.
                    if (pendingSendText == norm(text)) return ActionOutcome(ActionResult.WAIT, say,
                        "sent it - confirming it went through; do NOT resend")
                    // First send of this typed message: press the real Send button (labeled first,
                    // then the keyboard send key, then the far-right arrow - never the microphone).
                    val chatLike = editableFieldCount() <= 1 || looksLikeMessageInput(node)
                    if (chatLike && pressSend(text)) {
                        return ActionOutcome(ActionResult.CONTINUE, say, "pressed Send")
                    }
                    return ActionOutcome(ActionResult.CONTINUE, say,
                        if (chatLike) "your text is in the field - tap the SEND arrow at the far right (NOT the microphone), do NOT type again"
                        else "element $id already contains that text - move on to the next step, do NOT retype")
                }
                // A DISABLED editable takes NOTHING - set_text on it goes into the VOID (the owner's
                // Meta AI log: the composer disables WHILE the AI writes its reply; the agent typed into
                // the dead field for minutes, then opened a new chat out of frustration). Don't type into
                // the void - but this is NOT a hard error: SURFACE the real state (the AI is still writing)
                // as a soft WAIT so the MODEL chooses to wait and stays in THIS conversation. Per the
                // owner's steer: inform + let the agent decide, don't script a refusal (a FAILED here reads
                // like a dead end). The payment/install/etc. gates below/elsewhere are untouched.
                if (!node.isEnabled)
                    return ActionOutcome(ActionResult.WAIT, say,
                        "the composer is DISABLED right now - the AI is still writing its reply, so the field takes nothing yet. WAIT for it to re-enable, then continue THIS conversation (do NOT open a new chat).")
                val ok = setText(node, text)
                node.refresh()
                val now = node.text?.toString().orEmpty()
                val landed = text.isBlank() || now.contains(key, ignoreCase = true)
                // H (diagnostic, owner's "make as much visible as possible"): a pasted log now shows a
                // truncation or a void-write at a glance - payload length, whether the 4000 cap bit, the
                // field's before->after lengths, and whether it landed. Lengths/flags only (no message
                // CONTENT in the normal log for privacy; DebugCapture keeps the full text when debug_mode is on).
                AgentLog.log("act", "set_text len=${text.length}${if (textCappedFrom > 0) " CAPPED(from $textCappedFrom)" else ""}" +
                    " field:${before.length}->${now.length} landed=${if (landed) "Y" else "N"}")
                // LINKED ACTION (saves a step): typing a message and sending it is ONE intent - the
                // prompt already says "to send a message, set_text then send". When the text clearly
                // landed in a MESSAGE/chat input, chain the Send now instead of spending a whole
                // vision step to decide it. Gated to message inputs (not search/forms), and it reuses
                // the SAME robust pressSend ladder + pending-send confirmation, so it can't fire the
                // mic or double-post; if pressSend can't find a send control it falls through to the
                // normal "now SEND" path. Other fields are completely unaffected.
                if (ok && landed && text.isNotBlank() && looksLikeMessageInput(node) && pressSend(text)) {
                    return ActionOutcome(ActionResult.CONTINUE, say, "typed it and pressed Send")
                }
                // SEARCH box: typing then submitting is one intent. Press the keyboard Search/Enter so
                // the search actually runs (otherwise the model re-taps the field/suggestions forever).
                if (ok && landed && text.isNotBlank() && looksLikeSearchField(node) && sendImeEnter()) {
                    return ActionOutcome(ActionResult.CONTINUE, say, "typed it and pressed Search - results should load")
                }
                ActionOutcome(if (ok) ActionResult.CONTINUE else ActionResult.FAILED, say,
                    if (landed) "typed it - now SEND (do not type again)"
                    else "typed \"$text\" into element $id but field still shows \"$now\"")
            }
            "click" -> {
                val id = json.optInt("id", -1)
                // MAPPABLE TARGETING (owner: "actions should be mappable to variable elements" -
                // click X, not just click id-7): a click may NAME its target - {"action":"click",
                // "text":"Install"} - instead of, or as a fallback for, the id. The id stays the
                // fast path; the label is the STABLE one (survives ids shifting under a re-render).
                // Reuses findByLabel (the same resolver the batch/drag by-text paths use); acts on
                // the CURRENT screen only - `find` is the verb that also scrolls-to-reveal.
                val byText = json.optString("text").ifBlank { json.optString("label") }.trim()
                val node = currentNodes.getOrNull(id)
                    ?: byText.takeIf { it.isNotBlank() }?.let { findByLabel(it) }
                    ?: return ActionOutcome(ActionResult.FAILED, say,
                        "no element $id (only 0..${currentNodes.size - 1} exist)" +
                            (if (byText.isBlank()) "" else " and nothing labeled \"$byText\" here"))
                val label = (node.text ?: node.contentDescription)?.toString()?.trim().orEmpty()

                // A DISABLED control does nothing when tapped - the model loops on a greyed-out
                // Send/Next/Continue forever. Refuse it and point at the real blocker: a prerequisite
                // step (fill the field, check the box, pick an option) must be done to enable it.
                if (!node.isEnabled && node.className?.toString()?.contains("EditText") != true)
                    return ActionOutcome(ActionResult.FAILED, say,
                        "\"${label.ifBlank { "that control" }}\" is DISABLED (greyed out) - tapping it does nothing. Something is required first to enable it: fill the empty field, check a box, or pick an option, THEN tap it.")

                click(node)
                ActionOutcome(ActionResult.CONTINUE, say, "clicked element $id ($label)")
            }
            "tap_xy", "tap" -> {
                // Accept pixels OR fractions of the screen (0..1), so the model can tap
                // a button it can SEE but has no id for - e.g. {"x":0.92,"y":0.95} = the
                // send arrow at bottom-right. Fractions sidestep pixel hallucination.
                val rawX = json.optDouble("x", -1.0)
                val rawY = json.optDouble("y", -1.0)
                // Fractions (0..1) map through any active zoom region onto the real screen; raw pixels
                // pass straight through (a zoomed model is told to use fractions).
                val fracXY = rawX in 0.0..1.0 && rawY in 0.0..1.0
                val tp = if (fracXY) viewFracToScreenPx(rawX, rawY) else android.graphics.Point(rawX.toInt(), rawY.toInt())
                if (rawX < 0 || rawY < 0) {
                    // Salvage: model sent a tap with an element id instead of coordinates.
                    val sid = json.optInt("id", -1)
                    val snode = currentNodes.getOrNull(sid)
                        ?: return ActionOutcome(ActionResult.FAILED, say,
                            "no element $sid (only 0..${currentNodes.size - 1} exist)")
                    val slabel = (snode.text ?: snode.contentDescription)?.toString()?.trim().orEmpty()
                    click(snode)
                    return ActionOutcome(ActionResult.CONTINUE, say, "clicked element $sid ($slabel)")
                }
                // tap_xy stays LITERAL: snap=false so a deliberate pixel tap lands EXACTLY where asked
                // (a canvas stroke, a precise game target). `aim` is the forgiving snap-tap sibling.
                tapAtPoint(tp.x, tp.y, say, snap = false)
            }
            "aim", "snap_tap", "aim_tap" -> {
                // AIM = a FORGIVING coordinate tap: same coordinate forms as tap_xy (raw px or 0..1
                // fraction) OR a grid cell like tap_grid, but it SNAPS a near-miss onto the nearest
                // clickable center (~48px) inside tapAtPoint. The agent picks `aim` when it can NAME the
                // target but AIMS imprecisely (a canvas/game/unlabeled control); `tap_xy` for an EXACT
                // pixel. Snap is gated off in drawing/zoom (a deliberate stroke must land exactly). Routes
                // through the SAME PiP + payment/install/update gates tap_xy uses (via tapAtPoint).
                val cell = json.optString("cell").trim()
                val tp: android.graphics.Point? = if (cell.isNotBlank()) {
                    // Grid-cell form (column letter + row number, e.g. "C4") -> that cell's center, mapped
                    // back through any active zoom region, exactly like tap_grid.
                    val m = Regex("([A-Za-z])\\s*0*(\\d{1,2})").find(cell)
                    if (m == null) null
                    else {
                        val col = m.groupValues[1].uppercase()[0] - 'A'
                        val row = m.groupValues[2].toInt() - 1
                        if (col !in 0 until GridSpec.COLS || row !in 0 until GridSpec.ROWS) null
                        else viewFracToScreenPx((col + 0.5) / GridSpec.COLS, (row + 0.5) / GridSpec.ROWS)
                    }
                } else {
                    val rawX = json.optDouble("x", -1.0); val rawY = json.optDouble("y", -1.0)
                    if (rawX < 0 || rawY < 0) null
                    else {
                        val fracXY = rawX in 0.0..1.0 && rawY in 0.0..1.0
                        if (fracXY) viewFracToScreenPx(rawX, rawY) else android.graphics.Point(rawX.toInt(), rawY.toInt())
                    }
                }
                if (tp == null)
                    ActionOutcome(ActionResult.FAILED, say, "aim needs x,y (pixels or 0..1) or a grid cell like \"C4\"")
                else tapAtPoint(tp.x, tp.y, say, snap = true)
            }
            "tap_sequence", "tap_keys", "type_taps" -> {
                // Fire several taps in a row - "type" on the on-screen keyboard the model SEES, or
                // drive a keypad/field/game that rejects programmatic set_text. Each point is pixels
                // OR a 0..1 fraction (like tap_xy); only IN-BOUNDS points are dispatched, and the
                // list is capped so a token-spiral can't fire a thousand taps. (P1: type via taps.)
                val arr = json.optJSONArray("taps")
                    ?: return ActionOutcome(ActionResult.FAILED, say, "tap_sequence needs a 'taps' list of [x,y] points")
                val w = resources.displayMetrics.widthPixels
                val h = resources.displayMetrics.heightPixels
                val pts = mutableListOf<android.graphics.Point>()
                var i = 0
                while (i < arr.length() && pts.size < 40) {
                    val p = arr.optJSONArray(i)
                    if (p != null && p.length() >= 2) {
                        val rx = p.optDouble(0, -1.0); val ry = p.optDouble(1, -1.0)
                        val frac = rx in 0.0..1.0 && ry in 0.0..1.0
                        val tp = if (frac) viewFracToScreenPx(rx, ry) else android.graphics.Point(rx.toInt(), ry.toInt())
                        if (tp.x in 0..w && tp.y in 0..h) pts.add(tp)
                    }
                    i++
                }
                if (pts.isEmpty()) return ActionOutcome(ActionResult.FAILED, say, "no in-bounds taps in the sequence")
                tapSequence(pts)
                ActionOutcome(ActionResult.CONTINUE, say, "tapped ${pts.size} points in a row")
            }
            "tap_near", "tap_relative" -> {
                // Anchor-relative tap: tap just OUTSIDE a known element in a direction.
                // Robust across fold/keyboard/resolution since it references a stable
                // element, not absolute pixels. Key use: tap right of the text field to
                // hit an unlabeled send arrow.
                val id = json.optInt("id", -1)
                val anchor = currentNodes.getOrNull(id)
                    ?: return ActionOutcome(ActionResult.FAILED, say,
                        "no element $id (only 0..${currentNodes.size - 1} exist)")
                val r = Rect(); anchor.getBoundsInScreen(r)
                val w = resources.displayMetrics.widthPixels
                val h = resources.displayMetrics.heightPixels
                val pad = (28 * resources.displayMetrics.density).toInt()
                val dir = json.optString("dir", json.optString("direction", "right")).lowercase()
                val tx: Int; val ty: Int
                when (dir) {
                    "left" -> { tx = r.left - pad; ty = r.centerY() }
                    "up", "above", "top" -> { tx = r.centerX(); ty = r.top - pad }
                    "down", "below", "bottom" -> { tx = r.centerX(); ty = r.bottom + pad }
                    else -> { tx = r.right + pad; ty = r.centerY() }
                }
                val ntx = tx.coerceIn(0, w); val nty = ty.coerceIn(0, h)
                tap(ntx.toFloat(), nty.toFloat())
                ActionOutcome(ActionResult.CONTINUE, say, "tapped $dir of element $id")
            }
            "tap_grid" -> {
                // Discrete, always-in-bounds tap for canvas/game screens: the model names a
                // grid cell (column letter + row number, e.g. "C4") shown on the screenshot,
                // and we tap that cell's center. Sidesteps raw-pixel hallucination entirely.
                val cell = json.optString("cell").ifBlank { json.optString("text") }.trim().uppercase()
                val m = Regex("([A-Z])\\s*0*(\\d{1,2})").find(cell)
                if (m == null)
                    ActionOutcome(ActionResult.FAILED, say,
                        "tap_grid needs a cell like \"C4\" (column letter + row number)")
                else {
                    val col = m.groupValues[1][0] - 'A'
                    val row = m.groupValues[2].toInt() - 1
                    if (col !in 0 until GridSpec.COLS || row !in 0 until GridSpec.ROWS)
                        ActionOutcome(ActionResult.FAILED, say,
                            "cell $cell is off the grid (columns A..${'A' + GridSpec.COLS - 1}, rows 1..${GridSpec.ROWS})")
                    else {
                        // Sub-cell precision: optional fx/fy (0..1 WITHIN the cell) nudge off the center
                        // so a small target between cell centers is still hittable without raw pixels.
                        val fx = json.optDouble("fx", 0.5).coerceIn(0.0, 1.0).toFloat()
                        val fy = json.optDouble("fy", 0.5).coerceIn(0.0, 1.0).toFloat()
                        // The grid is drawn over the CURRENT view (the zoom crop, if any), so the cell's
                        // view-fraction maps back onto the real screen through the zoom region.
                        val gp = viewFracToScreenPx((col + fx).toDouble() / GridSpec.COLS, (row + fy).toDouble() / GridSpec.ROWS)
                        tap(gp.x.toFloat(), gp.y.toFloat())
                        ActionOutcome(ActionResult.CONTINUE, say,
                            "tapped grid $cell" + if (fx != 0.5f || fy != 0.5f) " (offset ${"%.1f".format(fx)},${"%.1f".format(fy)})" else "")
                    }
                }
            }
            "swipe" -> {
                val rx1 = json.optDouble("x1", -1.0); val ry1 = json.optDouble("y1", -1.0)
                val rx2 = json.optDouble("x2", -1.0); val ry2 = json.optDouble("y2", -1.0)
                if (rx1 < 0 || ry1 < 0 || rx2 < 0 || ry2 < 0)
                    return ActionOutcome(ActionResult.FAILED, say, "bad swipe coordinates")
                val w = resources.displayMetrics.widthPixels
                val h = resources.displayMetrics.heightPixels
                // Accept fractions (0..1) like tap_xy, else pixels; clamp into the display
                // (the model often overshoots e.g. 5000 on an ~1800px screen). Swipe/scroll is a
                // full-screen gesture, so it is NOT mapped through a zoom region.
                val frac = rx1 <= 1.0 && ry1 <= 1.0 && rx2 <= 1.0 && ry2 <= 1.0
                fun sx(v: Double) = (if (frac) v * w else v).toInt().coerceIn(0, w)
                fun sy(v: Double) = (if (frac) v * h else v).toInt().coerceIn(0, h)
                val sx1 = sx(rx1); val sy1 = sy(ry1); val sx2 = sx(rx2); val sy2 = sy(ry2)
                val dur = json.optLong("duration", 250L).coerceIn(50L, 3000L)
                swipe(sx1.toFloat(), sy1.toFloat(), sx2.toFloat(), sy2.toFloat(), dur)
                ActionOutcome(ActionResult.CONTINUE, say, "swiped ($sx1,$sy1)->($sx2,$sy2)")
            }
            "draw" -> {
                // If this is a drawing stroke (a notes/sketch canvas) and the keyboard is up, close it
                // first so the stroke marks the page instead of the keys. (A drag elsewhere is fine -
                // only guard when we're in a drawing canvas band.)
                if (isKeyboardOpen() && drawCanvasBand() != null) { performGlobalAction(GLOBAL_ACTION_BACK)
                    return ActionOutcome(ActionResult.CONTINUE, say, "closed the keyboard first - the canvas is clear now; draw again") }
                // Trace a coordinate PATH with a continuous press-drag - for drawing a shape, or for
                // dragging when there's no element to click (a block in Block Blast, a slider, a map).
                // Coordinates are [x,y] pairs, as fractions of the screen (0..1) OR pixels, like tap_xy.
                // Forms: {"points":[[x,y],...]} for a path, or {"from":[x,y],"to":[x,y]} for a drag.
                val w = resources.displayMetrics.widthPixels
                val h = resources.displayMetrics.heightPixels
                fun toPx(a: org.json.JSONArray?): PointF? {
                    if (a == null || a.length() < 2) return null
                    val rx = a.optDouble(0, -1.0); val ry = a.optDouble(1, -1.0)
                    if (rx < 0 || ry < 0) return null
                    // Fractions map through any active zoom region (so "zoom in, then draw the detail
                    // there" lands in that region); raw pixels pass straight through.
                    if (rx <= 1.0 && ry <= 1.0) { val p = viewFracToScreenPx(rx, ry); return PointF(p.x.toFloat(), p.y.toFloat()) }
                    return PointF(rx.toFloat().coerceIn(0f, w.toFloat()), ry.toFloat().coerceIn(0f, h.toFloat()))
                }
                val pts = ArrayList<PointF>()
                val arr = json.optJSONArray("points")
                if (arr != null) for (i in 0 until minOf(arr.length(), 60)) toPx(arr.optJSONArray(i))?.let { pts.add(it) }
                else { toPx(json.optJSONArray("from"))?.let { pts.add(it) }; toPx(json.optJSONArray("to"))?.let { pts.add(it) } }
                if (pts.size < 2)
                    return ActionOutcome(ActionResult.FAILED, say,
                        "draw needs >=2 points: {\"points\":[[x,y],...]} or {\"from\":[x,y],\"to\":[x,y]}")
                // Safety net for the owner's "draw below the toolbar" rule: in a notes/sketch app the
                // top strip is tools (pen/color/undo) and the bottom strip is the system nav/taskbar.
                // Coerce every point into the canvas band so a stray coordinate can't switch tools or
                // hit a nav button mid-drawing instead of marking the page.
                drawCanvasBand()?.let { (top, bottom) -> pts.forEach { it.y = it.y.coerceIn(top, bottom) } }
                val hold = json.optLong("hold", 0L).coerceIn(0L, 2000L)
                val dur = json.optLong("duration", (50L * pts.size).coerceIn(250L, 2500L)).coerceIn(100L, 4000L)
                if (tracePath(pts, dur, hold))
                    ActionOutcome(ActionResult.CONTINUE, say,
                        "traced a ${pts.size}-point path" + if (hold > 0) " (held to grab first)" else "")
                else ActionOutcome(ActionResult.FAILED, say, "couldn't dispatch the gesture")
            }
            "sketch" -> {
                // Never draw while the keyboard is up: that's typing mode and the keyboard covers the
                // lower canvas, so strokes would land on the keys (the owner's "tries to draw while the
                // keyboard is up"). Close it first; the next step draws on the clear page.
                if (isKeyboardOpen()) { performGlobalAction(GLOBAL_ACTION_BACK)
                    return ActionOutcome(ActionResult.CONTINUE, say, "closed the keyboard first - the canvas is clear now; sketch again") }
                // Draw a WHOLE picture cohesively: the model plots ALL the key points of the figure
                // together (so it stays proportional) and lists the strokes connecting them; we draw
                // them in ONE multi-stroke gesture, lifting the pen between strokes. Each stroke is a
                // primitive (circle/line/polygon - we generate the points) or an explicit point path.
                val w = resources.displayMetrics.widthPixels
                val h = resources.displayMetrics.heightPixels
                val arr = json.optJSONArray("strokes")
                    ?: return ActionOutcome(ActionResult.FAILED, say,
                        "sketch needs {\"strokes\":[ {\"shape\":\"circle\",\"center\":[x,y],\"r\":0.1}, {\"points\":[[x,y],...]}, ... ]}")
                val band = drawCanvasBand()
                val strokes = ArrayList<List<PointF>>()
                // LENIENT: the small model often emits a FLAT list of [x,y] pairs instead of stroke
                // OBJECTS (e.g. "strokes":[["0.25","0.5"],["0.6","0.7"],...] - even with string numbers).
                // Treat that whole list as ONE free curve so its attempt actually draws instead of being
                // rejected with "no valid strokes".
                val flatPairs = arr.length() >= 2 && arr.optJSONObject(0) == null &&
                    (arr.optJSONArray(0)?.length() ?: 0) >= 2
                if (flatPairs) {
                    val pts = org.json.JSONArray()
                    for (i in 0 until arr.length()) { val p = arr.optJSONArray(i); if (p != null && p.length() >= 2) pts.put(p) }
                    val one = strokeToPoints(org.json.JSONObject().put("points", pts), w, h)
                    if (one.size >= 2) {
                        band?.let { (top, bottom) -> one.forEach { p -> p.y = p.y.coerceIn(top, bottom) } }
                        strokes.add(one)
                    }
                } else for (i in 0 until minOf(arr.length(), MAX_SKETCH_STROKES)) {
                    val pts = strokeToPoints(arr.optJSONObject(i), w, h)
                    if (pts.size < 2) continue
                    band?.let { (top, bottom) -> pts.forEach { p -> p.y = p.y.coerceIn(top, bottom) } }
                    strokes.add(pts)
                }
                if (strokes.isEmpty())
                    return ActionOutcome(ActionResult.FAILED, say, "no valid strokes in sketch")
                val capped = arr.length() > MAX_SKETCH_STROKES
                if (dispatchSequentialStrokes(strokes))
                    ActionOutcome(ActionResult.CONTINUE, say,
                        "sketched ${strokes.size} strokes" +
                        if (capped) " (first $MAX_SKETCH_STROKES of ${arr.length()}; add the rest next)" else "")
                else ActionOutcome(ActionResult.FAILED, say, "couldn't dispatch the sketch gesture")
            }
            "zoom" -> {
                // Perception only: set (or clear) the region the model wants magnified. The orchestrator
                // crops the next screenshot to it; coordinate taps map back through it. No phone action.
                val region = parseZoomRegion(json)
                zoomRegion = region
                if (region == null) ActionOutcome(ActionResult.CONTINUE, say, "showing the full screen")
                else ActionOutcome(ActionResult.CONTINUE, say,
                    "zoomed in - that area is magnified now; read it, then tap the control (click an id, or tap_grid/tap_xy on this view)")
            }
            "zoom_out" -> { zoomRegion = null; ActionOutcome(ActionResult.CONTINUE, say, "showing the full screen") }
            "long_press" -> {
                val id = json.optInt("id", -1)
                val node = if (id >= 0) currentNodes.getOrNull(id) else null
                if (id >= 0 && node == null)
                    return ActionOutcome(ActionResult.FAILED, say, "no element $id")
                if (node != null && node.performAction(AccessibilityNodeInfo.ACTION_LONG_CLICK)) {
                    ActionOutcome(ActionResult.CONTINUE, say, "long-pressed element $id")
                } else {
                    val cx: Float; val cy: Float
                    if (node != null) {
                        val r = Rect(); node.getBoundsInScreen(r); cx = r.centerX().toFloat(); cy = r.centerY().toFloat()
                    } else {
                        // Coordinate long-press now honors the SAME conventions as every other coordinate
                        // verb: a grid "cell" ("C4"), or x/y as a 0..1 FRACTION (mapped through any zoom) or
                        // raw pixels. It used to read x/y with optInt, which TRUNCATED a fraction (0.5 -> 0)
                        // and failed with "bad long_press target" - so a model trained to emit fractions
                        // everywhere silently broke on every coordinate long-press.
                        val cellM = Regex("([A-Z])\\s*0*(\\d{1,2})").find(json.optString("cell").trim().uppercase())
                        if (cellM != null) {
                            val col = cellM.groupValues[1][0] - 'A'; val row = cellM.groupValues[2].toInt() - 1
                            if (col !in 0 until GridSpec.COLS || row !in 0 until GridSpec.ROWS)
                                return ActionOutcome(ActionResult.FAILED, say, "cell off the grid")
                            val gp = viewFracToScreenPx((col + 0.5) / GridSpec.COLS, (row + 0.5) / GridSpec.ROWS)
                            cx = gp.x.toFloat(); cy = gp.y.toFloat()
                        } else {
                            val rx = json.optDouble("x", -1.0); val ry = json.optDouble("y", -1.0)
                            if (rx < 0 || ry < 0) return ActionOutcome(ActionResult.FAILED, say, "bad long_press target")
                            val p = if (rx <= 1.0 && ry <= 1.0) viewFracToScreenPx(rx, ry)
                                    else android.graphics.Point(rx.toInt(), ry.toInt())
                            cx = p.x.toFloat(); cy = p.y.toFloat()
                        }
                    }
                    longPress(cx, cy)
                    ActionOutcome(ActionResult.CONTINUE, say, "long-pressed ($cx,$cy)")
                }
            }
            "do", "perform", "act", "menu_action" -> {
                // Fire a named app-defined accessibility action (shown as [do: …]) - the swipe/long-press menu
                // options (Archive, Delete, Mark read, Reply, Pin) baked into the a11y tree that a screenshot
                // can't show and a plain tap can't reach. The agent picks WHICH (it read the labels); we only
                // translate "do Archive on row N" into the node's action id. NOT scripted - it's a primitive.
                val id = json.optInt("id", -1)
                val node = currentNodes.getOrNull(id)
                    ?: return ActionOutcome(ActionResult.FAILED, say,
                        "no element $id (only 0..${currentNodes.size - 1} exist)")
                val name = json.optString("name").ifBlank { json.optString("text") }.trim()
                // The element's LABELED custom actions only (the [do: …] set) - what we can name and fire.
                val labeled = node.actionList.filter { !it.label?.toString()?.trim().isNullOrEmpty() }
                if (labeled.isEmpty())
                    return ActionOutcome(ActionResult.FAILED, say, "element $id has no named actions to perform")
                fun avail() = labeled.joinToString(", ") { it.label.toString().trim() }
                // No name given: list what's available so the agent's NEXT step can name one (don't guess).
                if (name.isBlank())
                    return ActionOutcome(ActionResult.CONTINUE, say, "element $id can: ${avail()} - say which with \"name\"")
                // Match the name to a label: normalize (lowercase, punctuation -> space) and match in BOTH
                // directions (label contains name, or an over-specified name contains the label), tightest
                // (shortest) label winning - the same forgiving scheme `find` uses for on-screen labels.
                fun norm(s: String) = s.lowercase().replace(Regex("[^a-z0-9]+"), " ").trim()
                val nn = norm(name)
                val match = labeled.filter {
                    val ln = norm(it.label.toString())
                    ln.isNotEmpty() && (ln.contains(nn) || (ln.length >= 3 && nn.contains(ln)))
                }.minByOrNull { it.label.toString().trim().length }
                if (match == null)
                    return ActionOutcome(ActionResult.FAILED, say, "no action like \"$name\" on element $id - it can: ${avail()}")
                val label = match.label.toString().trim()
                if (node.performAction(match.id))
                    ActionOutcome(ActionResult.CONTINUE, say, "did \"$label\" on element $id")
                else
                    ActionOutcome(ActionResult.FAILED, say, "\"$label\" didn't take on element $id - it can: ${avail()}")
            }
            "clear", "clear_field", "erase", "clear_text" -> {
                // Empty a pre-filled field (a stale search box, an autofilled value) without the model
                // having to discover the buried clear path. Reuses set_text's retargeting: the given id,
                // else the focused field, else the lone editable. Separate verb so the tuned set_text path
                // (anti-repeat / send-chaining) is untouched.
                val id = json.optInt("id", -1)
                val node = currentNodes.getOrNull(id)
                    ?: rootInActiveWindow?.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)?.takeIf { it.isEditable }
                    ?: currentNodes.filter { it.isEditable }.singleOrNull()
                if (node == null || !node.isEditable)
                    ActionOutcome(ActionResult.FAILED, say, "no text field to clear here")
                else { setText(node, ""); ActionOutcome(ActionResult.CONTINUE, say, "cleared the field") }
            }
            "assert", "verify", "check", "confirm" -> {
                // CHECKPOINT primitive: return TRUTH, not a tap, so the agent catches a step that did the
                // wrong thing instead of assuming success (the top long-task failure: compounding silent
                // errors). High-confidence structural checks first (text-in-field / Send-reachable / keyboard);
                // else a CONSERVATIVE presence check over what's on screen now. A wrong ✓ is worse than none,
                // so the fallback only says ✓ when most key words actually appear.
                val id = json.optInt("id", -1)
                val state = json.optString("state").trim().lowercase()
                val that = json.optString("that").ifBlank { json.optString("text") }
                    .ifBlank { json.optString("expect") }.trim()
                if (id >= 0 && state.isNotEmpty()) {
                    // ELEMENT-STATE assertion: verify a toggle flipped / a button is enabled / a tab is
                    // selected, reading the live node state as truth - a frequent multi-step precondition.
                    val n = currentNodes.getOrNull(id)
                    val actual = when {
                        n == null -> null
                        state.startsWith("check") || state.startsWith("on") || state.startsWith("toggl") -> n.isChecked
                        state.startsWith("enab") || state == "ready" -> n.isEnabled
                        state.startsWith("disab") || state.startsWith("grey") || state.startsWith("gray") -> !n.isEnabled
                        state.startsWith("select") -> n.isSelected
                        state.startsWith("focus") -> n.isFocused
                        else -> null
                    }
                    when (actual) {
                        true -> ActionOutcome(ActionResult.CONTINUE, say, "✓ element $id IS $state")
                        false -> ActionOutcome(ActionResult.CONTINUE, say, "✗ element $id is NOT $state - adapt, don't assume")
                        null -> ActionOutcome(ActionResult.CONTINUE, say, "can't check that (no element $id, or unknown state - try checked/enabled/disabled/selected)")
                    }
                } else if (that.isBlank())
                    ActionOutcome(ActionResult.FAILED, say, "assert needs \"that\":\"what you expect\" (or \"id\"+\"state\")")
                else {
                    val structural = verifyExpectation(that)
                    val verdict = structural ?: run {
                        val visible = currentNodes.joinToString(" ") {
                            (it.text?.toString() ?: "") + " " + (it.contentDescription?.toString() ?: "")
                        }.lowercase()
                        val keys = that.lowercase().replace(Regex("[^a-z0-9 ]"), " ").split(" ").filter { it.length >= 4 }
                        if (keys.isNotEmpty() && keys.count { visible.contains(it) } * 2 >= keys.size)
                            "✓ looks true - \"${clip(that, 80)}\" appears on screen"
                        else "✗ can't confirm \"${clip(that, 80)}\" - it does NOT appear here; adapt, don't assume it worked"
                    }
                    ActionOutcome(ActionResult.CONTINUE, say, verdict)
                }
            }
            "get_text", "read_field", "read_value" -> {
                // Pull ONE element's exact text back as the next step's feedback (a verification code, a
                // balance, a field's value) - a checkable value without copy's clipboard side effect, and the
                // FULL text (the element list clips labels to 70 chars).
                val id = json.optInt("id", -1)
                val node = currentNodes.getOrNull(id)
                if (node == null) ActionOutcome(ActionResult.FAILED, say, "no element $id to read")
                else {
                    val t = (node.text?.toString()?.ifBlank { null } ?: node.contentDescription?.toString())?.trim().orEmpty()
                    if (t.isBlank()) ActionOutcome(ActionResult.CONTINUE, say, "element $id has no readable text")
                    else ActionOutcome(ActionResult.CONTINUE, say, "element $id says: \"${clip(t, 200)}\"")
                }
            }
            "set_value", "set_progress", "set_slider" -> {
                // Set a slider/seekbar/volume/rating/progress to an EXACT value (pairs with the [val N%] read).
                // The model gives a range-agnostic "percent" 0..100 (the common form) or a raw "value"; we map
                // it onto the node's real min..max and fire ACTION_SET_PROGRESS. Only a control that actually
                // carries rangeInfo accepts it — anything else fails honestly so the model drags/taps instead.
                val id = json.optInt("id", -1)
                val node = currentNodes.getOrNull(id)
                val ri = try { node?.rangeInfo } catch (_: Exception) { null }
                when {
                    node == null -> ActionOutcome(ActionResult.FAILED, say, "no element $id to set")
                    ri == null -> ActionOutcome(ActionResult.FAILED, say,
                        "element $id isn't a slider/progress with a settable value — drag or tap it instead")
                    else -> {
                        val lo = ri.min; val hi = ri.max
                        val target = when {
                            json.has("value") -> json.optDouble("value").toFloat().coerceIn(lo, hi)
                            else -> {
                                val pct = (if (json.has("percent")) json.optDouble("percent")
                                           else json.optDouble("pct", 50.0)).toFloat().coerceIn(0f, 100f)
                                if (hi > lo) lo + (pct / 100f) * (hi - lo) else lo
                            }
                        }
                        val args = Bundle().apply {
                            putFloat(AccessibilityNodeInfo.ACTION_ARGUMENT_PROGRESS_VALUE, target)
                        }
                        val ok = try {
                            node.performAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_SET_PROGRESS.id, args)
                        } catch (_: Exception) { false }
                        if (ok) ActionOutcome(ActionResult.CONTINUE, say, "set element $id to $target")
                        else ActionOutcome(ActionResult.FAILED, say,
                            "element $id refused the value — try dragging it to the position instead")
                    }
                }
            }
            "press_key", "key", "keypress" -> {
                // Hardware/media keys the touch verbs cannot express. Accept either Android's semantic
                // KEYCODE_* name or a numeric keycode instead of narrowing the platform to an app allowlist.
                val requested = json.optString("key").ifBlank { json.optString("name") }.trim()
                val explicitCode = json.optInt("keycode", -1).takeIf { it >= 0 }
                    ?: requested.toIntOrNull()?.takeIf { it >= 0 }
                val semantic = requested.uppercase().replace(' ', '_').let {
                    if (it.startsWith("KEYCODE_")) it else "KEYCODE_$it"
                }
                val code = explicitCode ?: android.view.KeyEvent.keyCodeFromString(semantic).takeIf { it != android.view.KeyEvent.KEYCODE_UNKNOWN }
                when {
                    code == null -> ActionOutcome(ActionResult.FAILED, say,
                        "press_key needs an Android KEYCODE_* name or numeric keycode")
                    !ShellInput.available(this) -> ActionOutcome(ActionResult.FAILED, say,
                        "the $requested key needs Android's Shizuku bridge enabled — the platform bridge is unavailable")
                    ShellInput.key(code) -> ActionOutcome(ActionResult.CONTINUE, say, "pressed ${requested.ifBlank { code.toString() }}")
                    else -> ActionOutcome(ActionResult.FAILED, say, "couldn't send ${requested.ifBlank { code.toString() }}")
                }
            }
            // ORCHESTRATOR-LEVEL verbs: the loop intercepts these BEFORE this executor (runAction handles
            // ocr + reply on its own thread / turn). If one reaches HERE it's because it was nested where it
            // can't run - notably inside a batch sub-step - so fail HONESTLY instead of the opaque "unknown
            // action", telling the model to emit it on its own.
            "ocr", "read_text", "read_screen", "read_pixels", "capture" ->
                ActionOutcome(ActionResult.FAILED, say, "ocr/read is a top-level action - emit it ALONE, not inside a batch")
            "reply" ->
                ActionOutcome(ActionResult.FAILED, say, "reply is a top-level action - emit it ALONE, not inside a batch")
            else -> {
                // ACTION GUARD (light, deterministic): an off-list verb the alias table above couldn't
                // normalize. Surfaced as [guard] + a FAILED with an actionable reason the agent reads and
                // re-decides from - an improper tool call becomes a reorient, not a crash or a dead-end.
                AgentLog.log("guard", "off-list action '$action' - not a known verb; agent will re-decide")
                ActionOutcome(ActionResult.FAILED, say, "unknown action '$action'")
            }
        }
    }

    /** Set while LEARN MODE runs so prompts can describe the current learning posture. */
    /** Fire a deep-link Intent (the #4 primitives). NEW_TASK so it launches from the service
     *  context; swallow any failure to a false so the agent gets a clean "couldn't" and adapts. */
    private fun fireIntent(intent: Intent): Boolean = try {
        startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)); true
    } catch (_: Exception) { false }

    private fun click(node: AccessibilityNodeInfo) {
        var n: AccessibilityNodeInfo? = node
        while (n != null && !n.isClickable) n = n.parent
        if (n != null) {
            n.performAction(AccessibilityNodeInfo.ACTION_CLICK)
        } else {
            val r = Rect(); node.getBoundsInScreen(r)
            tap(r.centerX().toFloat(), r.centerY().toFloat())
        }
    }

    private fun setText(node: AccessibilityNodeInfo, text: String): Boolean {
        node.performAction(AccessibilityNodeInfo.ACTION_FOCUS)
        val args = Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
        }
        return node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
    }

    private fun scroll(direction: String, from: AccessibilityNodeInfo? = null): Boolean {
        // When an id is given, scroll that pane (its nearest scrollable) - needed for
        // split/foldable layouts with several independent scroll areas.
        val scrollable = (from?.let { nearestScrollable(it) })
            ?: mainScrollable() ?: findScrollable(rootInActiveWindow) ?: return false
        val dir = direction.lowercase()
        // Try the SEMANTIC action first. For vertical scrolls prefer FORWARD/BACKWARD: many lists -
        // notably Compose UIs like Gemini's chat - expose ONLY those, so ACTION_SCROLL_DOWN/UP
        // silently return false and the view never moves (the owner's "it never scrolled the Gemini
        // chat" bug). Try the directional action as a secondary. For horizontal, prefer directional.
        val acts = when (dir) {
            "up" -> listOf(AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_BACKWARD,
                           AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_UP)
            "left" -> listOf(AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_LEFT,
                             AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_BACKWARD)
            "right" -> listOf(AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_RIGHT,
                              AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_FORWARD)
            else -> listOf(AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_FORWARD,
                           AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_DOWN)
        }
        if (acts.any { scrollable.performAction(it.id) }) return true
        // GESTURE FALLBACK: a real finger swipe scrolls ANY view regardless of which accessibility
        // actions it exposes. Swipe INSIDE the scrollable's own bounds so it stays in the right pane
        // on the unfolded Fold (a full-width swipe could grab the wrong column).
        return swipeScroll(dir, scrollable)
    }

    // Edge-detection state for the gesture scroll fallback. The swipe gesture is ASYNC (dispatchGesture
    // fires and returns), so swipeScroll can't observe the post-scroll tree synchronously. Instead we
    // remember the scrollable's visible-content fingerprint from the PREVIOUS gesture-scroll of the same
    // node+direction: if the current fingerprint is IDENTICAL, the previous swipe moved nothing ⇒ we're
    // at the edge ⇒ report the honest FAILED (fixes the false-success where the a11y-action path already
    // returns false at an edge but this fallback masked it by always returning true).
    private var lastGestureScrollSig = ""      // "<nodeBounds>|<dir>" of the last gesture scroll
    private var lastGestureScrollContent = 0   // its content fingerprint

    /** A cheap fingerprint of a scrollable's VISIBLE content: the text + top/bottom of its first ~24
     *  direct children. When content scrolls this changes; at an edge a swipe leaves it identical. */
    private fun scrollFingerprint(scrollable: AccessibilityNodeInfo): Int {
        val sb = StringBuilder()
        val n = minOf(scrollable.childCount, 24)
        for (i in 0 until n) {
            val c = scrollable.getChild(i) ?: continue
            val cr = Rect().also { c.getBoundsInScreen(it) }
            sb.append(c.text ?: "").append('@').append(cr.top).append(',').append(cr.bottom).append('|')
        }
        return sb.toString().hashCode()
    }

    /** Swipe-drag to scroll a node when its accessibility scroll actions don't work (or aren't
     *  exposed). Gesture stays within the scrollable's bounds when they're a real content pane.
     *  Returns FALSE when the previous identical gesture scroll moved nothing (at the edge), so the
     *  agent is told the truth instead of a false "scrolled". */
    private fun swipeScroll(dir: String, scrollable: AccessibilityNodeInfo): Boolean {
        val w = resources.displayMetrics.widthPixels
        val h = resources.displayMetrics.heightPixels
        val r = Rect().also { scrollable.getBoundsInScreen(it) }
        // Edge check: same scrollable (keyed by bounds) + same direction as last time, and its content is
        // byte-identical to what it was right before that swipe ⇒ that swipe did nothing ⇒ this direction
        // is a dead edge. Don't re-swipe it; report the truth.
        val key = "${r.left},${r.top},${r.right},${r.bottom}|$dir"
        val content = scrollFingerprint(scrollable)
        if (key == lastGestureScrollSig && content == lastGestureScrollContent) return false
        lastGestureScrollSig = key
        lastGestureScrollContent = content
        val tall = r.height() > h / 5            // a genuine content pane, not a thin strip
        val cx = if (tall && r.width() > 0) r.centerX().toFloat() else w / 2f
        val cy = if (tall && r.height() > 0) r.centerY().toFloat() else h / 2f
        val lo = if (tall) r.top + r.height() * 0.22f else h * 0.24f   // upper point
        val hi = if (tall) r.top + r.height() * 0.78f else h * 0.74f   // lower point
        val lft = if (tall) r.left + r.width() * 0.22f else w * 0.24f
        val rgt = if (tall) r.left + r.width() * 0.78f else w * 0.74f
        when (dir) {
            "up" -> swipe(cx, lo, cx, hi, 280L)        // finger DOWN -> content moves down (reveal above)
            "left" -> swipe(lft, cy, rgt, cy, 280L)
            "right" -> swipe(rgt, cy, lft, cy, 280L)
            else -> swipe(cx, hi, cx, lo, 280L)        // down: finger UP -> content moves up (reveal below)
        }
        return true
    }

    private fun findScrollable(node: AccessibilityNodeInfo?): AccessibilityNodeInfo? {
        if (node == null) return null
        if (node.isScrollable) return node
        for (i in 0 until node.childCount) {
            findScrollable(node.getChild(i))?.let { return it }
        }
        return null
    }

    /** The MAIN scrollable = the LARGEST-area visible scrollable in the active window. findScrollable
     *  returns the FIRST in tree order, which is often a small inner carousel, not the content list the
     *  user means - so scroll/find/the direction-affordance must agree on ONE node (perception that says
     *  "more below" has to move the SAME list the agent then scrolls). Walks the full tree because a
     *  scrollable CONTAINER usually isn't interactive, so it's absent from currentNodes. null if none. */
    private fun mainScrollable(): AccessibilityNodeInfo? {
        var best: AccessibilityNodeInfo? = null; var bestArea = 0L
        fun walk(n: AccessibilityNodeInfo?) {
            if (n == null) return
            if (n.isScrollable && n.isVisibleToUser) {
                val r = Rect(); n.getBoundsInScreen(r)
                val area = r.width().toLong() * r.height()
                if (area > bestArea) { bestArea = area; best = n }
            }
            for (i in 0 until n.childCount) walk(n.getChild(i))
        }
        walk(rootInActiveWindow)
        return best
    }

    /** Nearest scrollable from a node: walk up to a scrollable ancestor, else search its descendants. */
    private fun nearestScrollable(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        var n: AccessibilityNodeInfo? = node
        while (n != null) { if (n.isScrollable) return n; n = n.parent }
        return findScrollable(node)
    }

    // Where the agent last tapped/ended a gesture, as a FRACTION of the screen (0..1) + when. The
    // brain draws a marker here on the next screenshot so the model can SEE where it just acted -
    // paired with the pixel-map change check, that's "I tapped here and nothing moved -> I missed".
    @Volatile var lastTapFrac: android.graphics.PointF? = null
    @Volatile var lastTapAt: Long = 0L

    // ZOOM (owner: "see the bare minimum - if the button's in the corner don't check every pixel").
    // When set, the model is shown only THIS fractional region of the screen, blown up - so it can
    // READ small controls (a toolbar of tiny tool icons, DeX targets) it can't resolve in the full
    // downscaled shot. Coordinate actions (tap_xy/tap_grid/draw/sketch/swipe) given as VIEW fractions
    // are mapped back onto the real screen through this region; click-by-id is unaffected (it uses the
    // element's real bounds). null = whole screen. The orchestrator does the actual cropping + clears
    // it after one action so we never get stuck zoomed.
    @Volatile var zoomRegion: android.graphics.RectF? = null
    @Volatile var lastActionWasZoom = false
    // Track 1 change-sense: the named region where the screen last visibly changed (set by the
    // orchestrator from the frame-hash delta - zero new monitoring). Surfaced in the REGION MAP and
    // resolved by `peek region:"changed"` so the agent can look at WHAT MOVED between snapshots.
    @Volatile var lastChangedRegion = ""

    /** Map a fractional coordinate in the CURRENT VIEW (0..1) to a screen PIXEL, applying the active
     *  zoom region so a tap on the magnified crop lands on the right real-screen spot. Identity (just
     *  ×screen size) when not zoomed. */
    private fun viewFracToScreenPx(vfx: Double, vfy: Double): android.graphics.Point {
        val z = zoomRegion
        val sfx = if (z == null) vfx else z.left + vfx * (z.right - z.left)
        val sfy = if (z == null) vfy else z.top + vfy * (z.bottom - z.top)
        val w = resources.displayMetrics.widthPixels; val h = resources.displayMetrics.heightPixels
        return android.graphics.Point((sfx * w).toInt().coerceIn(0, w), (sfy * h).toInt().coerceIn(0, h))
    }

    /** Parse a zoom request into a fractional screen region (or null = zoom out / invalid). Accepts a
     *  named region (top/bottom/left/right/center/corners), a grid cell, or x,y fractions. */
    private fun parseZoomRegion(json: org.json.JSONObject): android.graphics.RectF? {
        fun rect(l: Float, t: Float, r: Float, b: Float) = android.graphics.RectF(l, t, r, b)
        fun centered(cx: Float, cy: Float): android.graphics.RectF {
            var l = cx - 0.22f; var t = cy - 0.18f; var r = cx + 0.22f; var b = cy + 0.18f
            if (l < 0) { r -= l; l = 0f }; if (t < 0) { b -= t; t = 0f }
            if (r > 1) { l -= (r - 1); r = 1f }; if (b > 1) { t -= (b - 1); b = 1f }
            return rect(l.coerceIn(0f, 1f), t.coerceIn(0f, 1f), r.coerceIn(0f, 1f), b.coerceIn(0f, 1f))
        }
        // "changed" resolves to the region the screen last visibly changed (Track 1); falls back to
        // center if nothing's been recorded. Any other name flows through unchanged.
        val regionName = json.optString("region").lowercase().trim()
            .let { if (it == "changed") lastChangedRegion.ifBlank { "center" } else it }
        when (regionName) {
            "top", "top-half", "tophalf" -> return rect(0f, 0f, 1f, 0.42f)
            "bottom", "bottom-half", "bottomhalf" -> return rect(0f, 0.58f, 1f, 1f)
            "left", "left-half" -> return rect(0f, 0f, 0.52f, 1f)
            "right", "right-half" -> return rect(0.48f, 0f, 1f, 1f)
            "center", "centre", "middle" -> return rect(0.22f, 0.30f, 0.78f, 0.70f)
            "top-left", "topleft" -> return rect(0f, 0f, 0.55f, 0.46f)
            "top-right", "topright" -> return rect(0.45f, 0f, 1f, 0.46f)
            "bottom-left", "bottomleft" -> return rect(0f, 0.54f, 0.55f, 1f)
            "bottom-right", "bottomright" -> return rect(0.45f, 0.54f, 1f, 1f)
            "full", "all", "out", "none" -> return null
        }
        val cell = json.optString("cell").trim().uppercase()
        Regex("([A-Z])\\s*0*(\\d{1,2})").find(cell)?.let { m ->
            val col = m.groupValues[1][0] - 'A'; val row = m.groupValues[2].toInt() - 1
            if (col in 0 until GridSpec.COLS && row in 0 until GridSpec.ROWS)
                return centered((col + 0.5f) / GridSpec.COLS, (row + 0.5f) / GridSpec.ROWS)
        }
        val x = json.optDouble("x", -1.0); val y = json.optDouble("y", -1.0)
        if (x in 0.0..1.0 && y in 0.0..1.0) return centered(x.toFloat(), y.toFloat())
        return null
    }

    private fun noteTap(x: Float, y: Float) {
        val w = resources.displayMetrics.widthPixels.toFloat()
        val h = resources.displayMetrics.heightPixels.toFloat()
        if (w > 0 && h > 0) { lastTapFrac = android.graphics.PointF(x / w, y / h); lastTapAt = System.currentTimeMillis() }
    }

    private val mainHandler by lazy { android.os.Handler(android.os.Looper.getMainLooper()) }

    // ── FIRE-TIME KILL-GATE (ghost-input hardening 07-09) ────────────────────────────────────────────────────────
    // The owner's "couldn't stop it / ghost inputs kept landing after STOP" bug: `running` is checked BEFORE
    // performActionJson, but a gesture already posted to a Handler or waiting in a GestureResultCallback fired
    // unconditionally. This flag is the missing FIRE-TIME gate — every emitter re-checks it at dispatch, so a STOP
    // truly halts injection mid-sequence. Set by haltInjection() from the stop path; cleared by resumeInjection() at
    // task start. @Volatile: written on the stop thread, read on the main/gesture threads.
    @Volatile private var injectionHalted = false
    private var seqHandler: android.os.Handler? = null   // retained so a halt can cancel tapSequence's pending taps

    /** Called from every STOP path (stopCurrentTask / emergencyStop / onDestroy) via the companion instance: refuse
     *  all further injection and drop any queued taps, so a stopped agent can't keep touching the screen. */
    fun haltInjection() {
        injectionHalted = true
        ShellInput.halted = true    // fire-time barrier for the DEFERRED shell actuator (a worker spawned pre-STOP)
        try { seqHandler?.removeCallbacksAndMessages(null) } catch (_: Throwable) {}
        AgentLog.log("act", "injection HALTED (stop) — pending gestures dropped")
    }

    /** Called at task start: allow injection again for the new task. */
    fun resumeInjection() { injectionHalted = false; ShellInput.halted = false }

    // ── SCREEN-FRESHNESS gate (the chronic stray-tap: a blind tap decided against a 15–40s-old snapshot lands on a
    // screen that CHANGED). The orchestrator stamps the foreground package at decision time; a coordinate tap that
    // fires after the app changed is refused (the "tapped in the wrong app" class the code documents at ~1915). Only
    // a PACKAGE change (the worst class) is refused, never a minor in-app redraw, so legit taps are unharmed.
    @Volatile private var decisionPackage: String? = null
    fun markDecisionScreen() { decisionPackage = currentPackage() }
    private fun staleForBlindTap(): Boolean {
        val dp = decisionPackage ?: return false
        val now = currentPackage()
        return if (now != null && now != dp) { AgentLog.log("act", "stale tap refused: decided in $dp, now $now"); true } else false
    }

    /** Deliver a DECIDED input via the actuator MOST LIKELY to work here (owner: "choose whichever is most likely to
     *  work", not only-on-failure). Accessibility is the default (fast, no shell spawn); once a11y has REFUSED a
     *  gesture in this app (dispatchGesture==false, the hard "a11y can't reach this surface" signal) ShellInput
     *  learns it and [preferShell] flips to shell-FIRST there. Whichever runs first, the other is the fallback, so a
     *  surface either can handle still gets the input. §2-clean: the model DECIDED the action; this only picks HOW to
     *  deliver it (a deterministic translation-layer choice). a11y() must run on the main thread (node access);
     *  shell() runs off-thread (a process spawn), with the a11y fallback posted back to main. */
    private fun actuate(kind: String, a11y: () -> Boolean, shell: () -> Boolean) {
        // SLEEP INVARIANT (07-09c): never inject unless a task is running — catches a leftover queued tap/gesture
        // that reaches an emitter directly (bypassing performActionJson) after the task/service is gone.
        if (!AgentService.isAgentBusy) { AgentLog.log("act", "refused $kind — no active task (idle/sleep)"); return }
        if (injectionHalted) return                           // FIRE-TIME GATE: a STOP halts all injection incl. queued taps
        val app = currentPackage()?.lowercase() ?: ""
        val shellOn = settings.isShellInputEnabled() && ShellInput.available(this)
        if (shellOn && ShellInput.preferShell(this, app)) {
            Thread {
                // FIRE-TIME re-check in the DEFERRED body: a STOP after the gate above but before this worker runs
                // must not still exec the shell tap (the primary ghost-input escape). ShellInput.halted also guards.
                if (injectionHalted || !AgentService.isAgentBusy) return@Thread
                val ok = try { shell() } catch (_: Throwable) { false }
                if (ok) AgentLog.log("shellinput", "$kind via shell (preferred in $app)")
                else mainHandler.post {
                    if (injectionHalted || !AgentService.isAgentBusy) return@post   // re-check the posted a11y fallback too
                    if (!a11y()) AgentLog.log("shellinput", "$kind: shell+a11y both refused")
                }
            }.start()
        } else if (!a11y()) {                                 // a11y refused this gesture — learn it + fall to shell
            ShellInput.noteA11yRefusal(this, app)
            if (shellOn) Thread {
                if (injectionHalted || !AgentService.isAgentBusy) return@Thread   // fire-time re-check (deferred body)
                val ok = try { shell() } catch (_: Throwable) { false }
                AgentLog.log("shellinput", "a11y refused $kind -> shell ${if (ok) "landed" else "failed"}")
            }.start()
        }
    }

    private fun tap(x: Float, y: Float) {
        if (staleForBlindTap()) return                        // the app changed since the decision — don't tap a stale coord
        noteTap(x, y)
        actuate("tap",
            a11y = { dispatchGesture(GestureDescription.Builder()
                .addStroke(GestureDescription.StrokeDescription(Path().apply { moveTo(x, y) }, 0, 80)).build(), null, null) },
            shell = { ShellInput.tap(x.toInt(), y.toInt()) })
    }

    /** Fire a list of taps in quick succession (the model "types" by tapping keys it SEES, or drives
     *  a field that rejects set_text). Small gaps so each tap registers and something is always
     *  visibly happening. Points are pre-validated in-bounds by the caller. */
    private fun tapSequence(points: List<android.graphics.Point>) {
        // Retain the handler so haltInjection() can cancel the pending taps (the old freshly-created handler was
        // unreachable, so a STOP couldn't stop the remaining taps — a source of ghost inputs after stop).
        val handler = android.os.Handler(android.os.Looper.getMainLooper())
        seqHandler = handler
        points.forEachIndexed { i, p ->
            handler.postDelayed({ if (!injectionHalted) tap(p.x.toFloat(), p.y.toFloat()) }, i * 150L)
        }
    }

    private fun swipe(x1: Float, y1: Float, x2: Float, y2: Float, duration: Long) {
        noteTap(x2, y2)
        actuate("swipe",
            a11y = { dispatchGesture(GestureDescription.Builder()
                .addStroke(GestureDescription.StrokeDescription(Path().apply { moveTo(x1, y1); lineTo(x2, y2) }, 0, duration)).build(), null, null) },
            shell = { ShellInput.swipe(x1.toInt(), y1.toInt(), x2.toInt(), y2.toInt(), duration) })
    }

    private fun longPress(x: Float, y: Float) {
        actuate("long_press",
            a11y = { dispatchGesture(GestureDescription.Builder()
                .addStroke(GestureDescription.StrokeDescription(Path().apply { moveTo(x, y) }, 0, 600L)).build(), null, null) },
            shell = { ShellInput.longPress(x.toInt(), y.toInt()) })
    }

    /** A real DRAG: press-and-HOLD at the start (so the item lifts / drag mode engages - a plain
     *  fast swipe just scrolls), then move to the target and release. Two-phase stroke via
     *  willContinue, same pattern the draw hold uses. */
    private fun dragGesture(x1: Float, y1: Float, x2: Float, y2: Float, holdMs: Long = 450L, moveMs: Long = 600L) {
        // FIRE-TIME GATE: dragGesture bypasses actuate(), so gate its initial press-and-hold here — a STOP just
        // before this landed the hold anyway (the move-phase callback already re-checks at onCompleted).
        if (injectionHalted || !AgentService.isAgentBusy) return
        noteTap(x2, y2)
        val holdPath = Path().apply { moveTo(x1, y1) }
        val hold = GestureDescription.StrokeDescription(holdPath, 0, holdMs, true)
        dispatchGesture(GestureDescription.Builder().addStroke(hold).build(),
            object : AccessibilityService.GestureResultCallback() {
                override fun onCompleted(g: GestureDescription?) {
                    if (injectionHalted) return                 // STOP mid-drag: don't fire the move phase
                    val movePath = Path().apply { moveTo(x1, y1); lineTo(x2, y2) }
                    val move = hold.continueStroke(movePath, 0, moveMs, false)
                    dispatchGesture(GestureDescription.Builder().addStroke(move).build(), null, null)
                }
            }, null)
    }

    /** Node's visible label (text, else content-description) - shared by find/click-by-text/drag/stash. */
    private fun nodeLabel(n: AccessibilityNodeInfo): String =
        effectiveText(n).ifBlank { n.contentDescription?.toString().orEmpty() }.trim()

    /** The one label matcher for "reach a control by NAME" (drag's from_text/to_text): normalized
     *  (lowercase, punctuation -> space) so "sign-in" finds "Sign in"; matched in BOTH directions
     *  (label contains query, or an over-specified query contains a short label); TIGHTEST label
     *  wins so "Send" hits the Send button, not a paragraph containing the word. */
    private fun findByLabel(q: String): AccessibilityNodeInfo? {
        fun norm(s: String) = s.lowercase().replace(Regex("[^a-z0-9]+"), " ").trim()
        val qn = norm(q)
        if (qn.isEmpty()) return null
        return currentNodes.filter {
            val ln = norm(nodeLabel(it))
            ln.isNotEmpty() && (ln.contains(qn) || (ln.length >= 4 && qn.contains(ln)))
        }.minByOrNull { nodeLabel(it).length }
    }

    /** ARMED-TRIGGER helper: is a control matching this label present+visible on the CURRENT screen right
     *  now? Side-effect-free (no scroll-to-reveal - that's the `find` verb), so deterministic code can watch
     *  for an element to appear/disappear at sub-second cadence without moving anything. Reuses findByLabel
     *  (the same resolver click/find/batch use) after a fresh snapshotScreen refreshes currentNodes. */
    fun labelPresent(q: String): Boolean = q.isNotBlank() && findByLabel(q) != null

    /** On-demand docs for the RARE verbs the prompt only indexes (see the help action). */
    private fun actionHelp(name: String): String = when (name) {
        "tap_near" -> """{"action":"tap_near","id":N,"dir":"right"} - tap just OUTSIDE element N (right/left/up/down), e.g. the send arrow beside a field"""
        "tap_sequence" -> """{"action":"tap_sequence","taps":[[x,y],[x,y],...]} - several taps in a row (pixels or 0..1 fractions); "type" on the keys you SEE when a field rejects set_text"""
        "ocr" -> """{"action":"ocr"} - read the screen's PIXEL text (web page/canvas values the element list can't see); next step you'll see the text, then act"""
        "get_text" -> """{"action":"get_text","id":N} - read element N's EXACT full text back (a code/balance/value); no clipboard, no tap"""
        "assert" -> """{"action":"assert","that":"my message is in the field"} - ✓/✗ check a step worked before moving on; or {"action":"assert","id":N,"state":"checked"/"enabled"/"selected"}"""
        "save_note" -> """{"action":"save_note","name":"...","text":"..."} - save text to a Downloads file (full Markdown/CSV). After a capture sweep, omit "text" to write the whole dataset"""
        "save_login" -> """{"action":"save_login","service":"...","username":"...","password":"..."} - record a credential you just created"""
        "connected_devices" -> """{"action":"connected_devices"} - list Bluetooth/headphones/USB/cast/TV/dock"""
        "set_value" -> """{"action":"set_value","id":N,"percent":75} - set a slider/seekbar/volume/brightness/rating to an EXACT value (0..100 percent, or "value":X in its own units); read the current one off the [val N%] tag. Beats eyeballing a drag"""
        "press_key" -> """{"action":"press_key","key":"volume_up"} - a semantic hardware/media key: volume_up/down/mute, media_play_pause/next/previous/stop, dpad_up/down/left/right/center, page_up/down. Needs Shizuku"""
        "split_screen" -> """{"action":"split_screen"} - two apps at once (DeX/split)"""
        "batch" -> """{"action":"batch","steps":[{...},{...}]} - chain up to 4 SAME-SCREEN inputs (set_text/toggle/clear/copy/stash) in one round; a navigating step ends it"""
        "drag" -> """{"action":"drag","from_id":N,"to_id":M} - press-HOLD-drag (reorder/move/slider); from_text/to_text labels or x1,y1,x2,y2 (0..1) work too"""
        "stash", "recall" -> """{"action":"stash","key":"k","text":"..."} parks info outside your view; {"action":"recall","key":"k"} brings it back (no key = list)"""
        "do" -> """{"action":"do","id":N,"name":"Archive"} - run a named [do: …] option a control exposes; no name = list element N's options"""
        "wait_for" -> """{"action":"wait_for","that":"results are visible"} - the engine watches every beat and wakes you the moment it's true (or reports it never came)"""
        // A1: the COMMON verbs the lean ACTIONS menu lists with a terse gist - their full detail lives HERE so
        // it's one help away (nothing removed, agent-piloted, §12). Only verbs with non-obvious detail need an
        // entry; click/set_text/scroll/back/home/etc. are self-evident from the lean gist.
        "peek" -> """{"action":"peek","region":"top/bottom/left/right/center/a corner"} (or "cell":"C4", or "x"/"y" 0..1) - see ONLY that region's controls + a close-up; your DEFAULT on a busy/dense screen. zoom_out widens back"""
        "find" -> """{"action":"find","text":"label"} - INSTANTLY locate AND TAP a control by its label across ALL sets, wherever it is; don't page to hunt. (reveal only scrolls it into view; find taps it)"""
        "reveal" -> """{"action":"reveal","text":"label"} - SCROLL a named control into view WITHOUT tapping (bounded); then you LOOK and decide"""
        "aim" -> """{"action":"aim","x":N,"y":N} (px, 0..1, or "cell":"C4") - a FORGIVING tap that SNAPS to the nearest button when you're a bit off; tap_xy is exact, aim self-corrects"""
        "tap_grid" -> """{"action":"tap_grid","cell":"C4"} - tap the labeled grid cell (col letter+row num) drawn on the shot; hits anything with no [N] id. Add "fx"/"fy" 0..1 for a spot in the cell"""
        "reply" -> """{"action":"reply"} - take YOUR turn in a chat: a fast helper reads their last message and writes+SENDS your next one, no repeats. Use for EVERY conversation/debate turn instead of typing"""
        "capture" -> """{"action":"capture"} - read THIS screen's table/list/sheet into your buffer EXACTLY; too big? capture, SCROLL, capture again until nothing new. Then save_note (no "text") writes it all out"""
        "search" -> """{"action":"search","text":"..."} - a web search in ONE step; reach for this to look something up instead of fumbling the browser address bar/tab UI"""
        "copy", "paste", "read_clipboard" -> """{"action":"copy","id":N} (or "text":"...") grabs a value to carry; {"action":"paste","id":N} drops it; {"action":"read_clipboard"} shows what you're carrying - never retype a value from memory"""
        "sketch" -> """{"action":"sketch","strokes":[STROKE,...]} - draw a whole picture on a notes canvas with 0..1 coords (full format is given once you're on the canvas); draw lays ONE stroke, sketch lays many"""
        "draw" -> """{"action":"draw","points":[[x,y],...]} - ONE stroke (x,y 0..1); drag: {"from":[x,y],"to":[x,y]} (+"hold":200). In notes keep y 0.18-0.90"""
        "expect" -> """add "expect":"my message shows as sent" to a consequential action - next step the engine checks it actually happened, so you catch a tap that did the WRONG thing. Pair "confidence":"low" on a costly send/pay/delete to look before it commits"""
        "note" -> """add "note":"Send hides behind the keyboard" to any action - remembers ONE short fact for later this task; don't repeat one"""
        else -> ""
    }

    /** Engine check for the loop's wait_for watch: is the agent-NAMED condition visibly true now?
     *  Fresh snapshot each beat (that's the point of the watch), then the structural verifiers
     *  (text-in-field / send-reachable / keyboard), else the same conservative keyword-presence
     *  test the assert fallback uses - most key words must actually be on screen, so a ✓ is never
     *  invented. The AGENT chose the condition; this only does the looking. NOTE: the actual per-beat
     *  WATCH that calls this lives in the orchestrator loop (cross-file wiring - see the report). */
    fun conditionMet(that: String): Boolean = try {
        snapshotScreen()
        val structural = verifyExpectation(that)
        if (structural != null) structural.startsWith("✓")
        else {
            val visible = currentNodes.joinToString(" ") {
                (it.text?.toString() ?: "") + " " + (it.contentDescription?.toString() ?: "")
            }.lowercase()
            val keys = that.lowercase().replace(Regex("[^a-z0-9 ]"), " ").split(" ").filter { it.length >= 4 }
            keys.isNotEmpty() && keys.count { visible.contains(it) } * 2 >= keys.size
        }
    } catch (_: Throwable) { false }

    /** The [top, bottom] y-pixel band that is the actual DRAWING CANVAS in a notes/sketch app: BELOW
     *  the tool toolbar (pens/colors/undo) at the top and ABOVE the system nav bar / One UI taskbar at
     *  the bottom. Null (no clamp) when we're not in such an app - the draw action is the only caller,
     *  so this never affects normal tapping. Fractions calibrated against the Samsung Notes layout
     *  (toolbar bottom ~16%, bottom nav/taskbar ~last 9%); realizes the owner's "draw below the
     *  toolbar" rule and also keeps strokes off the bottom nav buttons. */
    private fun drawCanvasBand(): Pair<Float, Float>? {
        val pkg = (currentPackage() ?: "").lowercase()
        val drawingApp = pkg.contains("notes") || pkg.contains("sketch") || pkg.contains("draw") ||
            pkg.contains("canvas") || pkg.contains("paint") || pkg.contains("squid") ||
            pkg.contains("noteshelf") || pkg.contains("penup") || pkg.contains("colornote")
        if (!drawingApp) return null
        val h = resources.displayMetrics.heightPixels.toFloat()
        return (h * 0.17f) to (h * 0.90f)
    }

    /** Resolve ONE sketch stroke spec into screen-pixel points. A stroke is either a primitive we
     *  sample into points - circle/ellipse (round), line, polygon (closed) - or an explicit
     *  {"points":[[x,y],...]} polyline. Coords are fractions 0..1 of the screen OR pixels (like
     *  tap_xy). This is what lets the model "plot points and connect them" and pick the right tool
     *  for the complexity: a clean circle for a head, a few points for a curve, a polygon for ears. */
    private fun strokeToPoints(o: org.json.JSONObject?, w: Int, h: Int): List<PointF> {
        if (o == null) return emptyList()
        // Points map through any active zoom region (so "zoom in, then sketch detail there" lands
        // in that region); raw pixels pass straight through.
        fun toPx(a: org.json.JSONArray?): PointF? {
            if (a == null || a.length() < 2) return null
            val rx = a.optDouble(0, -1.0); val ry = a.optDouble(1, -1.0)
            if (rx < 0 || ry < 0) return null
            if (rx <= 1.0 && ry <= 1.0) { val p = viewFracToScreenPx(rx, ry); return PointF(p.x.toFloat(), p.y.toFloat()) }
            return PointF(rx.toFloat().coerceIn(0f, w.toFloat()), ry.toFloat().coerceIn(0f, h.toFloat()))
        }
        // A radius given as a fraction (<=1) is a fraction of the screen WIDTH, applied to BOTH axes
        // so a "circle" comes out round in pixels. When zoomed it scales by the crop's width, so a
        // circle drawn in a magnified region is sized to that region, not the whole screen.
        val zScale = zoomRegion?.let { it.right - it.left } ?: 1f
        fun rad(key: String, fallback: Double): Float {
            val r = o.optDouble(key, fallback)
            return (if (r in 0.0..1.0) r * w * zScale else r).toFloat()
        }
        // Render shapes CLEANLY. Accuracy comes from the model choosing the right shapes to represent
        // the subject (a cat = contours, not circles), NOT from roughening strokes - a task that calls
        // for a clean circle/line should get a clean one. So no artificial wobble here.
        val pts = ArrayList<PointF>()
        when (o.optString("shape").lowercase()) {
            "circle", "ellipse", "oval" -> {
                val c = toPx(o.optJSONArray("center")) ?: return emptyList()
                val rx = rad("rx", o.optDouble("r", 0.08)); val ry = rad("ry", o.optDouble("r", 0.08))
                val steps = 28
                for (i in 0..steps) {
                    val t = 2.0 * Math.PI * i / steps
                    pts.add(PointF((c.x + rx * Math.cos(t)).toFloat(), (c.y + ry * Math.sin(t)).toFloat()))
                }
            }
            "line" -> { toPx(o.optJSONArray("from"))?.let { pts.add(it) }; toPx(o.optJSONArray("to"))?.let { pts.add(it) } }
            "polygon", "poly", "closed" -> {
                val a = o.optJSONArray("points")
                if (a != null) for (i in 0 until minOf(a.length(), 40)) toPx(a.optJSONArray(i))?.let { pts.add(it) }
                if (pts.size >= 2) pts.add(PointF(pts[0].x, pts[0].y))   // close the loop
            }
            else -> {   // plain polyline through the given points
                val a = o.optJSONArray("points")
                if (a != null) for (i in 0 until minOf(a.length(), 40)) toPx(a.optJSONArray(i))?.let { pts.add(it) }
            }
        }
        return pts
    }

    /** Draw several strokes as ONE cohesive gesture: each stroke is a separate finger press-move-up,
     *  SEQUENCED (stroke i+1 starts after stroke i lifts) so the whole figure is drawn in order with
     *  the pen lifting between parts. This is how a multi-part picture (a cat: head, ears, eyes, body,
     *  tail) lands proportional and connected instead of as disjoint taps re-derived each step. */
    private fun dispatchSequentialStrokes(strokes: List<List<PointF>>): Boolean {
        if (strokes.isEmpty()) return false
        // FIRE-TIME GATE: sketch bypasses actuate() and dispatches one long (multi-second) gesture, so a STOP just
        // before this would otherwise draw the whole figure after halt. Refuse it. (Mid-figure interruption of an
        // ALREADY-dispatched sketch is a follow-up: chain per-stroke via GestureResultCallback like tracePath.)
        if (injectionHalted || !AgentService.isAgentBusy) return false
        noteTap(strokes.last().last().x, strokes.last().last().y)
        return try {
            val builder = GestureDescription.Builder()
            var start = 0L
            val gap = 40L
            for (s in strokes) {
                if (s.size < 2) continue
                val path = Path().apply {
                    moveTo(s[0].x, s[0].y)
                    for (i in 1 until s.size) lineTo(s[i].x, s[i].y)
                }
                val dur = (24L * s.size).coerceIn(200L, 1200L)
                builder.addStroke(GestureDescription.StrokeDescription(path, start, dur))
                start += dur + gap
            }
            lastSketchDurationMs = start   // how long the whole gesture runs, for the finish delay
            dispatchGesture(builder.build(), null, null)
        } catch (_: Exception) { false }
    }

    /** Trace a continuous stroke through [pts] (a press-move-...-release), for drawing a shape or for
     *  dragging where there's no accessibility element to click - e.g. moving a block in Block Blast.
     *  [holdMs] presses and HOLDS at the first point before moving (to "grab" a draggable); the move
     *  then plays out over [durationMs]. One finger, so the path is a single connected gesture. */
    private fun tracePath(pts: List<PointF>, durationMs: Long, holdMs: Long): Boolean {
        if (pts.size < 2 || injectionHalted) return false     // FIRE-TIME GATE: a STOP refuses new strokes
        noteTap(pts.last().x, pts.last().y)
        val drag = Path().apply {
            moveTo(pts[0].x, pts[0].y)
            for (i in 1 until pts.size) lineTo(pts[i].x, pts[i].y)
        }
        return try {
            if (holdMs <= 0L) {
                val g = GestureDescription.Builder()
                    .addStroke(GestureDescription.StrokeDescription(drag, 0L, durationMs)).build()
                dispatchGesture(g, null, null)
            } else {
                // Press & HOLD at the start to "grab" a draggable, then continue the SAME finger along
                // the path. continueStroke is the correct way to chain one logical finger-down gesture.
                val grabPath = Path().apply { moveTo(pts[0].x, pts[0].y) }
                val grab = GestureDescription.StrokeDescription(grabPath, 0L, holdMs, true)
                val g1 = GestureDescription.Builder().addStroke(grab).build()
                dispatchGesture(g1, object : AccessibilityService.GestureResultCallback() {
                    override fun onCompleted(d: GestureDescription?) {
                        if (injectionHalted) return             // STOP mid-stroke: don't continue the drag
                        val cont = grab.continueStroke(drag, 0L, durationMs, false)
                        try {
                            dispatchGesture(GestureDescription.Builder().addStroke(cont).build(), null, null)
                        } catch (_: Exception) {}
                    }
                }, null)
            }
        } catch (_: Exception) { false }
    }

    /** A few ambiguous names map to a SPECIFIC package when installed, so we don't grab the
     *  wrong same-labelled surface. "Gemini" must be the standalone Gemini chat app, NOT the
     *  Google Assistant voice half-sheet (googlequicksearchbox), whose send button is a mess. */
    private fun preferredPackage(name: String): String? = when (name.trim().lowercase()) {
        "gemini" -> "com.google.android.apps.bard"
        // Samsung Notes' launcher LABEL is often just "Notes", so a request for "Samsung Notes" used
        // to fail to resolve (the query was longer than the label) and we wrongly went to Play Store.
        "samsung notes", "samsung note" -> "com.samsung.android.app.notes"
        else -> null
    }

    /** True if [name]/[pkg] is ALREADY the foreground app - so open_app no-ops instead of
     *  relaunching (which would start a NEW chat and lose the conversation). Handles Gemini's
     *  split hosting: the conversation can run in the standalone Gemini app (bard) OR inside the
     *  Google app (googlequicksearchbox), so either counts as "Gemini is already open". */
    private fun isAlreadyForeground(name: String, pkg: String?): Boolean {
        val cur = currentPackage() ?: return false
        if (pkg != null && cur == pkg) return true
        if (name.trim().lowercase() != "gemini") return false
        if (cur == "com.google.android.apps.bard") return true
        // The Google app (googlequicksearchbox) hosts search, the feed, and a YouTube lightbox too -
        // NOT only Gemini. Treat it as "Gemini already open" ONLY when Gemini's chat UI is actually
        // present, so open_app can still NAVIGATE to Gemini from a search/YouTube screen.
        return cur == "com.google.android.googlequicksearchbox" &&
            currentNodes.any { (it.viewIdResourceName ?: "").contains("assistant_robin") }
    }

    private fun openApp(name: String): Boolean {
        if (name.isBlank()) return false
        // One robust resolver for both "can I open it" and "open it" (was duplicated + one-directional,
        // which is why "Samsung Notes" went to the Play Store when the icon's label is just "Notes").
        val pkg = resolvePackage(name) ?: return false
        val launch = packageManager.getLaunchIntentForPackage(pkg) ?: return false
        launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        startActivity(launch)
        return true
    }

    /** Deterministic unstick: tap a common popup-dismiss or progress button. Used by
     *  the orchestrator when the same screen recurs, so a blocking dialog/ad (rate
     *  prompt, consent, "Got it", ad close) doesn't end the task. Returns true if it
     *  clicked something. Priority: dismiss the blocker, else advance. */
    fun tryAdvance(): Boolean = clickByKeyword(listOf(
            "no thanks", "not now", "skip", "dismiss", "close", "got it", "maybe later",
            "continue", "next", "get started", "start", "allow", "accept", "ok", "done"
        ))

    /** If a modal dialog / permission popup is on screen, a short note so the model handles it
     *  FIRST instead of ignoring it and looping on the screen behind it (a top stuck cause). ""
     *  when none. Deliberately CONSERVATIVE - only the permission-controller package or an explicit
     *  AlertDialog signature - so it never false-flags a normal screen. */
    fun dialogHint(): String {
        if ((currentPackage() ?: "").lowercase().contains("permissioncontroller"))
            return "a system PERMISSION dialog"
        val isAlert = currentNodes.any { n ->
            val s = ((n.className ?: "").toString() + " " + (n.viewIdResourceName ?: "")).lowercase()
            s.contains("alertdialog") || s.endsWith("id/alerttitle") || s.contains("alert_dialog")
        }
        if (!isAlert) return ""
        val title = currentNodes.mapNotNull { it.text?.toString()?.trim() }.firstOrNull { it.length in 3..50 }
        return if (title != null) "a dialog (\"$title\")" else "a dialog"
    }

    /** A SOFT "still loading" note for the orient: a visible indeterminate spinner AND a sparse screen
     *  (few interactive controls rendered) = content probably hasn't arrived yet. Deliberately NOT an
     *  auto-wait reflex: a spinner can also be a harmless background refresh on a fully usable screen,
     *  so we report the state and let the AGENT decide to wait or act (owner's rule: report, don't force).
     *  The sparse gate is what keeps a populated screen with a corner refresh spinner from triggering it.
     *  "" when not loading. Reads sawSpinner set during the last snapshot walk (no extra tree walk). */
    fun loadingHint(): String =
        if (sawSpinner && currentNodes.size <= 4) "this screen looks like it's still loading (little has rendered yet)" else ""

    /** Generic "the AI I'm chatting with has finished replying" signal: a reply RATING row (Good/
     *  Bad + Copy/Share) is on screen - apps only show it under a COMPLETED assistant reply - and
     *  when the composer is [disabled] it's still finishing up. This is what tells the agent its
     *  message WAS sent even when the app gave no other feedback (the owner's Meta AI run: the send
     *  worked, the agent never realized, and it opened a new chat). App-agnostic: keyed to the
     *  rating-row pattern, not any app's ids. */
    fun replyFinishedHint(): String = try {
        val labels = currentNodes.mapNotNull { nodeLabel(it).lowercase().ifBlank { null } }
        val rating = labels.any { it == "good" || it == "good response" } &&
            labels.any { it == "bad" || it == "bad response" } &&
            labels.any { it == "copy" || it == "share" }
        if (!rating) ""
        else if (currentNodes.any { it.isEditable && !it.isEnabled })
            "the AI you're messaging HAS REPLIED (its rating row is on screen) - your message WAS sent. The input is briefly disabled while it finishes; do NOT resend, wait for the field to re-enable, then continue the conversation"
        else "the AI you're messaging HAS REPLIED (its rating row is on screen) - your message WAS sent; do NOT resend it. Read the reply and respond to IT"
    } catch (_: Throwable) { "" }

    /** A blocked-FORM note for the orient: a primary submit button that's DISABLED while a required
     *  field is still empty - the top reason fill-then-submit tasks stall (the agent hunts a Submit
     *  it can't yet press and loops). PERCEPTION ONLY - we report the state; the AGENT decides what to
     *  fill (owner's rule: never script/auto-fill). Deliberately CONSERVATIVE - fires only when BOTH a
     *  disabled clickable whose label reads like a primary submit AND at least one empty editable are
     *  present - so a normal screen (an enabled button, or a disabled button with no blank field) never
     *  trips it. Reads wrapped in try/catch like the other hints (a stale node can throw mid-walk). */
    fun formHint(): String {
        try {
            val empty = currentNodes.any { it.isEditable && effectiveText(it).isBlank() }
            if (!empty) return ""
            val submitWords = Regex("^(submit|continue|next|save|send|done|sign in|log in|pay|post|confirm|finish|apply|create)$")
            val submit = currentNodes.firstOrNull { n ->
                if (n.isEnabled || !n.isClickable) return@firstOrNull false
                val label = effectiveText(n).ifBlank { n.contentDescription?.toString().orEmpty() }.trim()
                label.length in 2..16 && submitWords.containsMatchIn(label.lowercase())
            } ?: return ""
            val label = effectiveText(submit).ifBlank { submit.contentDescription?.toString().orEmpty() }.trim()
            return "the \"$label\" button is DISABLED - fill the empty field(s) first; it enables once the form is complete"
        } catch (_: Throwable) { return "" }
    }

    /** Common spoken names the model uses for built-in apps -> a launchable label. */
    private fun normalizeAppName(name: String): String {
        val l = name.trim().lowercase()
        return when {
            l.isBlank() -> name
            l.contains("browser") || l == "web" || l == "internet" || l == "google search" -> "Chrome"
            l == "text" || l == "texts" || l == "sms" || l == "text message" || l == "text messages" -> "Messages"
            l == "dialer" || l == "phone app" -> "Phone"
            else -> name
        }
    }

    /** Is there an installed app whose launcher label matches [name]? Lets callers
     *  avoid issuing open_app for junk (e.g. a vague plan line like "a chat application"). */
    fun isAppInstalled(name: String): Boolean = resolvePackage(name) != null

    /** Public: the launcher PACKAGE an app name resolves to (via the same robust resolver open_app uses), or null
     *  if it can't be resolved. The preload foreground poll uses this to confirm the CURRENT foreground package
     *  actually EQUALS the target — instead of just "not the launcher" — so it can't false-positive "foregrounded
     *  X" while the launcher is really on screen (the app-drawer-hunting bug). */
    fun packageForApp(name: String): String? = resolvePackage(name)

    /** Launcher package for an app name, resolved ROBUSTLY (also used by openApp). Brand prefixes are
     *  stripped ("Samsung Notes" <-> "Notes") and matching is BIDIRECTIONAL - the request may be
     *  LONGER or shorter than the icon's label - so a more-specific name than the label ("Samsung
     *  Notes" when the icon just reads "Notes") still resolves instead of looking "not installed". */
    private fun resolvePackage(name: String): String? {
        if (name.isBlank()) return null
        val pm = packageManager
        // Honor a known-good package (real Gemini app, Samsung Notes) when it's actually installed.
        preferredPackage(name)?.let { if (pm.getLaunchIntentForPackage(it) != null) return it }
        val t = normalizeAppName(name).trim().lowercase()
        if (t.isBlank()) return null
        fun strip(s: String) = s.removePrefix("samsung ").removePrefix("google ")
            .removePrefix("microsoft ").removePrefix("the ").removeSuffix(" app").trim()
        val ts = strip(t)
        val labeled = pm.queryIntentActivities(
            Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER), 0)
            .map { it.activityInfo.packageName to it.loadLabel(pm).toString().lowercase() }
        // Exact (incl. brand-stripped) wins first so "Google" beats "Google TV"; then either-direction
        // prefix; then either-direction contains (length-guarded so short queries don't grab anything).
        val m = labeled.firstOrNull { it.second == t }
            ?: labeled.firstOrNull { strip(it.second) == ts }
            ?: labeled.firstOrNull { it.second.startsWith(t) || t.startsWith(it.second) }
            ?: labeled.firstOrNull { val ls = strip(it.second); ls.isNotEmpty() && (ls.startsWith(ts) || ts.startsWith(ls)) }
            ?: labeled.firstOrNull { it.second.contains(t) || (t.length >= 4 && it.second.length >= 4 && t.contains(it.second)) }
            ?: return null
        return m.first
    }

    /** Press the Send control. Chat send arrows are frequently unlabeled visual icons, so
     *  there's no single reliable method - we keep an ORDERED list of strategies and ESCALATE
     *  through them across attempts (so a repeated send tries a DIFFERENT method instead of
     *  re-missing the same spot), starting from whatever last WORKED in this app (learned +
     *  remembered in AgentMemory). */
    // Order matters: a POSITIVELY-labeled Send button first (never the mic); then the OUTERMOST
    // trailing icon next to the field (the send arrow sits outboard of the mic, so picking the
    // outermost hits Send, not the mic - this is what was broken: a plain "right of the field" tap
    // hit the mic, and dropping it entirely left nothing to press when Send is unlabeled); then the
    // keyboard's send action (taps nothing); then far-right/corner geometry as a last resort.
    private val sendStrategies: List<Pair<String, () -> Boolean>> = listOf(
        "labeled Send button" to ::sendLabeled,
        "the send icon at the input's trailing edge" to ::sendTrailingIcon,
        "the keyboard Enter key" to ::sendImeEnter,
        "the send arrow at the input's far right" to ::sendGeomFieldRight,
        "the bottom-right corner" to ::sendGeomBottomRight,
    )
    private var sendKey = ""
    private var sendAttempt = 0
    // We expand a collapsed composer at most ONCE per message (then fall through to the send
    // strategies), so a half-sheet that doesn't expand on tap can't trap us re-tapping the field.
    private var expandedForSend = false
    private var pendingSendText = ""
    private var pendingSendPkg = ""
    private var pendingSendStrategy = -1
    private var pendingSendAt = 0L
    private var pendingReplyAtSend = ""
    // Captured at send time, persisted as the structural SendSkill only once the send is CONFIRMED.
    private var pendingSendFieldId = ""
    private var pendingSendBtnId = ""
    private var pendingSendBtnDesc = ""
    private var pendingSendNeedsExpand = false

    private fun markPending(content: String, pkg: String, strat: Int) {
        pendingSendText = norm(content); pendingSendPkg = pkg; pendingSendStrategy = strat
        pendingSendAt = System.currentTimeMillis()
        // Snapshot the other side's CURRENT reply: when it changes, that NEW reply is proof our
        // message landed (the one signal that works when the app keeps our text in the box and
        // doesn't expose the sent bubble as readable text - Gemini).
        pendingReplyAtSend = latestReplyText() ?: ""
        // Capture the EXACT controls for the structural SendSkill (persisted only after the send is
        // CONFIRMED). Field = the editable holding our text; send = the clearest Send button on
        // screen now (by id/desc, never the mic). Lets a later send click the known control directly.
        pendingSendFieldId = currentNodes.firstOrNull { it.isEditable &&
            it.text?.toString()?.trim()?.lowercase()?.contains(norm(content)) == true }
            ?.viewIdResourceName?.substringAfterLast('/').orEmpty()
        val sb = identifiableSendNode()
        pendingSendBtnId = sb?.viewIdResourceName?.substringAfterLast('/').orEmpty()
        pendingSendBtnDesc = sb?.contentDescription?.toString().orEmpty()
        pendingSendNeedsExpand = expandedForSend
    }

    /** The clearest Send control on screen by id/desc (NEVER the mic) - what the structural SendSkill
     *  records so a later send in this app clicks the exact known button instead of re-deriving it. */
    private fun identifiableSendNode(): AccessibilityNodeInfo? = currentNodes.firstOrNull { n ->
        if (isVoiceControl(n)) return@firstOrNull false
        val s = ((n.viewIdResourceName?.substringAfterLast('/') ?: "") + " " +
            (n.contentDescription ?: "")).lowercase()
        (s.contains("send") || s.contains("submit")) &&
            !s.contains("voice") && !s.contains("mic") && !s.contains("wave")
    }

    /** Find the learned SendSkill's control on the CURRENT screen (exact short-id or desc match). */
    private fun findSendBySkill(skill: AgentMemory.SendSkill): AccessibilityNodeInfo? =
        currentNodes.firstOrNull { n ->
            if (isVoiceControl(n)) return@firstOrNull false
            val id = n.viewIdResourceName?.substringAfterLast('/') ?: ""
            val desc = n.contentDescription?.toString() ?: ""
            (skill.sendId.isNotBlank() && id == skill.sendId) ||
                (skill.sendDesc.isNotBlank() && desc.equals(skill.sendDesc, ignoreCase = true))
        }

    /** A Send/Submit control is actually present on screen (labeled, not the mic). Lets us know a
     *  collapsed composer has already been expanded so we don't tap to expand again. */
    private fun hasReachableSend(): Boolean = currentNodes.any { n ->
        val s = ((n.viewIdResourceName ?: "") + " " + (n.contentDescription ?: "") + " " +
            (n.text ?: "")).lowercase()
        (s.contains("send") || s.contains("submit")) && !isVoiceControl(n)
    }

    private var lastExpandAt = 0L

    /** Deterministic fix for the Gemini-style COLLAPSED composer (half-sheet preview with no Send
     *  button until tapped to expand): if one is on screen and no Send is reachable yet, TAP it to
     *  open the full composer so the real Send appears - then the caller retries on the next snapshot.
     *  No learned recipe needed: it just makes the Send button EXIST so the normal ladder can find it.
     *  Gated to collapsed composers, so ordinary chat apps are never touched; rate-limited so it can't
     *  loop. */
    private fun expandCollapsedComposer(): Boolean {
        if (System.currentTimeMillis() - lastExpandAt < 3000L) return false
        if (hasReachableSend()) return false
        val editables = currentNodes.filter { it.isEditable }
        // Expand ONLY when the collapsed preview is the only input present - i.e. the real expanded
        // box isn't open yet. Once it's open (a second, non-collapsed editable appears) we leave it
        // alone, or we'd tap it shut. This keeps it to the genuine "can't send yet" state.
        if (editables.isEmpty() || !editables.all { isCollapsedComposerNode(it) }) return false
        val r = Rect(); editables.first().getBoundsInScreen(r)
        if (r.width() <= 0) return false
        lastExpandAt = System.currentTimeMillis()
        tap(r.centerX().toFloat(), r.centerY().toFloat())
        return true
    }

    private fun isCollapsedComposerNode(n: AccessibilityNodeInfo): Boolean {
        val id = (n.viewIdResourceName ?: "").lowercase()
        return id.contains("collapsed") || id.contains("half_sheet")
    }

    private fun pressSend(content: String): Boolean {
        val pkg = currentPackage() ?: ""
        // A NEW message restarts the escalation; the SAME message being retried keeps the advanced
        // attempt (confirmPendingSend bumps it when a method misses), so a repeat tries the NEXT
        // method instead of re-missing the same spot. We no longer START from a learned recipe.
        val key = "$pkg|${norm(content)}"
        if (key != sendKey) { sendKey = key; sendAttempt = 1; expandedForSend = false }
        // STRUCTURAL SEND SKILL (learned, exact control): if a send in this app was CONFIRMED before,
        // click the precise Send button we remembered - the single most reliable path, and it can't
        // wander onto the mic. If a collapsed composer hides it, expand once first. Falls through to
        // the heuristic ladder if the remembered control isn't on the current screen.
        AgentMemory.getSendSkill(this, recipeKey(pkg))?.let { skill ->
            if (skill.needsExpand && !hasReachableSend() && !expandedForSend && expandCollapsedComposer()) {
                expandedForSend = true; return false
            }
            findSendBySkill(skill)?.let { node -> click(node); markPending(content, pkg, 0); return true }
        }
        // If the composer is COLLAPSED (no Send button can possibly be hit yet), expand it ONCE and
        // let the caller retry once it's open - this is what made Gemini take ~16 tries. BUT only once
        // per message: Gemini's googlequicksearchbox half-sheet does NOT expand on tap, so if we kept
        // re-expanding we'd tap the field forever and never reach the send-arrow strategies (the bug
        // that broke sending entirely). After the one expand attempt, fall through to the strategies -
        // the trailing send icon / far-right geometry hits the arrow on a non-expanding half-sheet.
        if (!expandedForSend && expandCollapsedComposer()) { expandedForSend = true; return false }
        // ALWAYS try a real labeled/id Send button FIRST - the most reliable when present, and it
        // never hits the mic.
        if (sendStrategies[0].second()) { markPending(content, pkg, 0); return true }
        // No labeled Send button: escalate through the fallbacks IN ORDER (trailing send icon first
        // - the reliable visual send on chat composers), from wherever the last attempt left off.
        // We deliberately do NOT jump to a learned "recipe" strategy here: that preempted the
        // trailing-icon and, when the learned strategy was a non-working one (IME-enter on Gemini's
        // collapsed half-sheet returns true but sends nothing), it broke sending ENTIRELY. Plain
        // order-based escalation is more robust - a learned habit must never override what works.
        var i = sendAttempt.coerceIn(1, sendStrategies.size - 1)
        while (i < sendStrategies.size) {
            if (sendStrategies[i].second()) { sendAttempt = i; markPending(content, pkg, i); return true }
            i++
        }
        sendAttempt = 1 // exhausted; wrap (a labeled button may appear on a later snapshot)
        return false
    }

    private fun focusedField(): AccessibilityNodeInfo? =
        rootInActiveWindow?.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)

    /** A voice/mic/dictation control - NEVER tap it when trying to send text, or we toggle
     *  voice input instead of sending (Gemini's half-sheet "Stops the voice input" button was
     *  eating every send). Matched by id or description. */
    private fun isVoiceControl(n: AccessibilityNodeInfo?): Boolean {
        if (n == null) return false
        val s = ((n.viewIdResourceName ?: "") + " " + (n.contentDescription ?: "")).lowercase()
        return s.contains("voice") || s.contains("mic") || s.contains("speech") ||
            s.contains("_wave") || s.contains("dictat") || s.contains("listen")
    }

    private fun sendLabeled(): Boolean =
        clickByKeyword(listOf("send", "post", "submit", "reply", "tweet"))

    private fun sendImeEnter(): Boolean {
        val focused = focusedField() ?: return false
        return focused.performAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_IME_ENTER.id)
    }

    private fun sendGeomFieldRight(): Boolean {
        val focused = focusedField() ?: currentNodes.firstOrNull { it.isEditable } ?: return false
        val fr = Rect(); focused.getBoundsInScreen(fr)
        if (fr.width() <= 0) return false
        // The send arrow sits just PAST the field's own right edge. Tap relative to the FIELD, not a
        // fraction of the whole screen: on an UNFOLDED foldable the composer is in ONE pane, so
        // 0.93*fullWidth overshoots past the pane into dead space - which is the Gemini "pressed Send
        // but nothing sent" loop the owner hit. This lands on the immediate trailing control.
        val x = minOf(fr.right + fr.height() * 0.6f, resources.displayMetrics.widthPixels - 4f)
        val y = fr.centerY().toFloat()
        if (isVoiceControl(findNodeAt(x.toInt(), y.toInt()))) return false // don't toggle the mic
        tap(x, y); return true
    }

    private fun sendGeomBottomRight(): Boolean {
        // Last resort, still FIELD-relative (stays in the composer's pane on an unfolded foldable,
        // unlike the old full-screen 0.93x/0.92y that hit the screen's far corner). Reaches FURTHER
        // out than fieldRight, so if the mic is the inner icon this catches the send arrow outboard.
        val focused = focusedField() ?: currentNodes.firstOrNull { it.isEditable } ?: return false
        val fr = Rect(); focused.getBoundsInScreen(fr)
        if (fr.width() <= 0) return false
        val x = minOf(fr.right + fr.height() * 1.5f, resources.displayMetrics.widthPixels - 4f)
        val y = fr.centerY().toFloat()
        if (isVoiceControl(findNodeAt(x.toInt(), y.toInt()))) return false
        tap(x, y); return true
    }

    /** The Send arrow in a chat composer is usually an UNLABELED icon at the trailing (right) edge
     *  of the input row, and the microphone sits just INSIDE it. We pick the OUTERMOST trailing
     *  icon beside the field - skipping any voice/mic control and obvious clear/attach/menu icons -
     *  so we hit Send and never the mic, even when both are unlabeled. General across chat apps;
     *  this is the case the geometry strategies couldn't handle (they bail on the mic and then tap
     *  nothing). */
    private fun sendTrailingIcon(): Boolean {
        val field = focusedField() ?: currentNodes.firstOrNull { it.isEditable } ?: return false
        val fr = Rect(); field.getBoundsInScreen(fr)
        if (fr.width() <= 0) return false
        val w = resources.displayMetrics.widthPixels
        val h = resources.displayMetrics.heightPixels
        val maxIcon = (minOf(w, h) * 0.4f).toInt()   // an icon button, not a full-width wrapper
        val r = Rect()
        val cands = currentNodes.filter { n ->
            if (n === field || n.isEditable) return@filter false
            // The icon's click flag often lives on a parent, and we tap by COORDINATE anyway, so
            // accept a clickable node OR a button/image icon.
            val cn = n.className?.toString() ?: ""
            if (!(n.isClickable || cn.contains("Button") || cn.contains("Image"))) return@filter false
            // Skip attach/clear/nav and active STOP/cancel controls - but NOT a plain mic/voice button.
            if (isClearOrNavControl(n) || isStopControl(n)) return@filter false
            n.getBoundsInScreen(r)
            val small = r.width() in 1 until maxIcon && r.height() < maxIcon
            val rowBand = r.centerY() in (fr.top - fr.height() / 2)..(fr.bottom + fr.height() * 3 / 2)
            val trailing = r.centerX() > fr.centerX()
            small && rowBand && trailing
        }
        // Generalized (owner's rule): the trailing button is voice ONLY when the field is EMPTY; once
        // there's text it morphs into Send - and we ONLY get here with text to send. So the rightmost
        // trailing icon IS the send; a dedicated mic, if any, sits inboard of it. Don't second-guess
        // its label (blanket-skipping "voice" used to throw the morphed Send away and tap nothing).
        // STOP/cancel controls are already excluded above so we never halt generation instead.
        val send = cands.maxByOrNull { it.getBoundsInScreen(r); r.centerX() } ?: return false
        send.getBoundsInScreen(r)
        tap(r.centerX().toFloat(), r.centerY().toFloat())
        return true
    }

    /** An active STOP / cancel control (stop generating, stop listening, cancel) - never tap it when
     *  sending; it would halt generation/voice instead of sending. (A plain mic/voice button is NOT
     *  this - that one morphs into Send, so it must stay tappable.) */
    private fun isStopControl(n: AccessibilityNodeInfo?): Boolean {
        if (n == null) return false
        val s = ((n.viewIdResourceName ?: "") + " " + (n.contentDescription ?: "") + " " +
            (n.text ?: "")).lowercase()
        return s.contains("stop") || s.contains("cancel") || s.contains("listening")
    }

    /** Trailing-edge controls that are NOT Send, so sendTrailingIcon never taps them: clear/close
     *  the field, attach media, emoji/keyboard toggles, overflow menus. Matches LABELED ones only,
     *  so the typically-unlabeled Send arrow is never excluded. */
    private fun isClearOrNavControl(n: AccessibilityNodeInfo?): Boolean {
        if (n == null) return false
        val s = ((n.viewIdResourceName ?: "") + " " + (n.contentDescription ?: "") + " " +
            (n.text ?: "")).lowercase()
        if (s.isBlank()) return false
        return listOf("clear", "close", "delete", "remove", "cancel", "dismiss", "back",
            "attach", "camera", "gallery", "photo", "image", "file", "emoji", "sticker", "gif",
            "keyboard", "more option", "overflow", "expand").any { s.contains(it) }
    }

    /** After a send, confirm on a LATER snapshot whether it ACTUALLY landed - and only THEN mark
     *  the message as sent. "Landed" = the input cleared OR there's positive evidence the message
     *  went (a reply, the other side generating, or a conversation thread) - NOT just "the box is
     *  empty", because some chats keep the text in the box after sending. This is what prevents
     *  the false "already sent -> wait forever" when the press actually missed (e.g. hit the mic):
     *  if there's no evidence it landed, we DON'T mark it sent, so the agent will try again. A
     *  generous timeout clears a truly stuck pending so it can never deadlock. General, not
     *  app-specific. */
    private fun confirmPendingSend() {
        if (pendingSendText.isBlank()) return
        if ((currentPackage() ?: "") != pendingSendPkg) { resetPendingSend(); return }
        // PRIMARY proof it sent: our exact message now appears as a NON-editable element - i.e. it
        // became a sent bubble in the conversation, not just text sitting in the input box. This is
        // reliable for the 1st AND every later message (each send adds a new bubble) and does NOT
        // false-confirm on some OTHER reply that was already on screen. General, not app-specific.
        val inThread = currentNodes.any { n ->
            !n.isEditable && n.text?.toString()?.trim()?.lowercase()?.contains(pendingSendText) == true }
        val stillInBox = currentNodes.any { it.isEditable &&
            it.text?.toString()?.trim()?.lowercase()?.contains(pendingSendText) == true }
        // A NEW reply from the other side is proof our message went through. This is what Gemini
        // needs: it keeps our text in the box after sending AND its sent-message bubble has no
        // readable text, so neither inThread nor a cleared box ever fires - but every successful
        // send produces a fresh reply. General to any chat.
        val reply = latestReplyText()
        val replyChanged = reply != null && reply != pendingReplyAtSend
        // Secondary (for apps that don't expose the bubble text): the box cleared AND there's a
        // reply/thread/generating indicator.
        val landed = inThread || replyChanged || (!stillInBox && looksSent())
        if (landed) {
            rememberSent(pendingSendText)   // NOW we know it really sent
            // Some chats (Gemini's half-sheet) LEAVE our text in the box after sending. Clear it so
            // the screen reflects reality - otherwise the model SEES its sent message still in the
            // field and re-sends it (the repeated-message loop). Only clear a field that still holds
            // exactly our just-sent message, so we never wipe a new message being typed.
            currentNodes.firstOrNull { it.isEditable &&
                it.text?.toString()?.trim()?.lowercase()?.contains(pendingSendText) == true }
                ?.let { setText(it, "") }
            // LEARN only the tree-derived strategies (labeled button / trailing send icon / Enter
            // key re-find their target on the live screen each time). Never persist a geometric
            // recipe (it can drift onto the mic), so we don't replay a bad positional habit.
            if (pendingSendStrategy in 0 until GEOMETRIC_SEND_FROM) {
                AgentMemory.recordSendRecipe(this, recipeKey(pendingSendPkg), pendingSendStrategy)
                AgentMemory.addLesson(this,
                    "In ${appLabelFor(pendingSendPkg)}, Send works via ${sendStrategies[pendingSendStrategy].first}.")
            }
            // STRUCTURAL SEND SKILL: persist the exact field+send control captured at send time, so a
            // later send in this app clicks the known button directly (the high-priority send skill).
            if (pendingSendBtnId.isNotBlank() || pendingSendBtnDesc.isNotBlank()) {
                AgentMemory.recordSendSkill(this, recipeKey(pendingSendPkg),
                    pendingSendFieldId, pendingSendBtnId, pendingSendBtnDesc, pendingSendNeedsExpand)
            }
            resetPendingSend()
        } else if (System.currentTimeMillis() - pendingSendAt > 12_000L) {
            // 12s with no evidence it went -> that method MISSED. Advance to the next strategy so the
            // retry tries a DIFFERENT method (not the same miss), and clear the pending text so the
            // agent is free to press Send again. Keep sendKey so the advance sticks; wrap past the
            // end back to the first fallback.
            val next = pendingSendStrategy + 1
            sendAttempt = if (next >= sendStrategies.size) 1 else next.coerceAtLeast(1)
            pendingSendText = ""; pendingSendPkg = ""; pendingSendStrategy = -1; pendingSendAt = 0L
            pendingReplyAtSend = ""
        }
    }

    private fun resetPendingSend() {
        pendingSendText = ""; pendingSendPkg = ""; pendingSendStrategy = -1; pendingSendAt = 0L; pendingReplyAtSend = ""; sendKey = ""; sendAttempt = 0
        pendingSendFieldId = ""; pendingSendBtnId = ""; pendingSendBtnDesc = ""; pendingSendNeedsExpand = false
    }

    private fun appLabelFor(pkg: String): String = try {
        packageManager.getApplicationLabel(packageManager.getApplicationInfo(pkg, 0)).toString()
    } catch (_: Exception) { pkg.substringAfterLast('.') }

    /** Memory key for a per-app send recipe, made CONTEXT-dependent: the same app on a
     *  folding phone's two screens or different orientations has a different layout, so its
     *  send control sits in a different place. Keying by screen size keeps a recipe learned
     *  on one screen from misfiring on the other. */
    private fun recipeKey(pkg: String): String =
        "$pkg|${resources.displayMetrics.widthPixels}x${resources.displayMetrics.heightPixels}"

    /** Click the first clickable element whose text/desc/id matches a keyword (e.g. "send"). */
    /** A calculator/keypad input field - it rejects programmatic set_text, so we tap keys. */
    private fun isCalcOrKeypadField(node: AccessibilityNodeInfo): Boolean {
        val rid = node.viewIdResourceName?.lowercase().orEmpty()
        val pkg = (currentPackage() ?: "").lowercase()
        return rid.contains("formula") || rid.contains("calc") || pkg.contains("calculator")
    }

    /** Enter [text] into a calculator by TAPPING its on-screen buttons (digits + operators),
     *  since set_text doesn't take on these fields. Returns true only if EVERY character mapped
     *  to a button we tapped; otherwise false (caller falls back). Handles digits, . % = ( ),
     *  + - x / (mapped to the real − × ÷ glyph buttons) and sqrt -> the √ button. */
    private fun typeViaKeypad(text: String): Boolean {
        fun keyFor(label: String): AccessibilityNodeInfo? = currentNodes.firstOrNull { n ->
            !n.isEditable && (n.text?.toString()?.trim() == label ||
                n.contentDescription?.toString()?.trim().equals(label, ignoreCase = true))
        }
        // Pre-resolve the button for each glyph; if any needed key is absent, bail before tapping.
        val plan = mutableListOf<AccessibilityNodeInfo>()
        var i = 0
        val s = text.trim()
        while (i < s.length) {
            val c = s[i]
            if (c == ' ') { i++; continue }
            // sqrt( -> the Square root button
            if (s.regionMatches(i, "sqrt", 0, 4, ignoreCase = true)) {
                val k = keyFor("Square root") ?: return false; plan.add(k); i += 4
                if (i < s.length && s[i] == '(') i++ // √ already opens a paren
                continue
            }
            val label = when (c) {
                in '0'..'9' -> c.toString()
                '.' -> "."; '%' -> "%"; '=' -> "="
                '+' -> "+"; '-', '−' -> "−"; '*', '×', 'x', 'X' -> "×"; '/', '÷' -> "÷"
                '(', ')' -> "( )"
                '√' -> "Square root"
                else -> return false // unmappable char -> let the caller fall back to set_text
            }
            val k = keyFor(label) ?: return false
            plan.add(k); i++
        }
        if (plan.isEmpty()) return false
        plan.forEach { click(it) }
        return true
    }

    private fun clickByKeyword(keywords: List<String>): Boolean {
        for (kw in keywords) {
            val re = Regex("\\b" + Regex.escape(kw) + "\\b")
            val node = currentNodes.firstOrNull { n ->
                if (n.isEditable) return@firstOrNull false
                val t = (n.text ?: n.contentDescription)?.toString()?.lowercase().orEmpty()
                if (t.contains("search") || t.contains("inbox")) return@firstOrNull false
                val rid = n.viewIdResourceName?.substringAfterLast('/')?.lowercase().orEmpty()
                // ...endsWith handles "robin_send"; contains("send_button") catches Gemini's
                // real arrow id "...manual_endpointing_send_button_compose".
                re.containsMatchIn(t) || rid == kw || rid.endsWith("_$kw") ||
                    rid.endsWith("${kw}_button") || rid.contains("${kw}_button")
            } ?: continue
            click(node); return true
        }
        return false
    }

    /** Element from the last snapshot whose bounds contain (x, y), if any. §3 (Batch 0): return the
     *  SMALLEST-area containing node, PREFERRING one that is clickable or carries a label — not the first
     *  enclosing container. The old firstOrNull could resolve a coordinate tap (tap_xy/aim) to a big blank
     *  wrapper, whose empty label made the §3 payment/install confirm gate (performActionJson ~1449, which
     *  only fires when the label is non-empty) silently skip over a canvas/webview "Pay $40" target.
     *  Smallest-area is the standard innermost-hit tiebreak; the label/clickable preference only breaks ties
     *  toward the node the gate can actually read. Null iff nothing contains the point (the ~1424 null-check
     *  semantics are unchanged). */
    private fun findNodeAt(x: Int, y: Int): AccessibilityNodeInfo? {
        val r = Rect()
        val containing = currentNodes.filter { node -> node.getBoundsInScreen(r); r.contains(x, y) }
        if (containing.isEmpty()) return null
        fun area(n: AccessibilityNodeInfo): Long { n.getBoundsInScreen(r); return r.width().toLong() * r.height() }
        fun labeled(n: AccessibilityNodeInfo): Boolean =
            n.isClickable || !n.text.isNullOrBlank() || !n.contentDescription.isNullOrBlank()
        return containing.filter { labeled(it) }.minByOrNull { area(it) }
            ?: containing.minByOrNull { area(it) }
    }

    // --- TURN-TAKING / SEND MEMORY ----------------------------------------

    private fun norm(s: String) = s.trim().lowercase().take(120)

    /** Evidence that the last message ACTUALLY sent (vs. just sitting typed in the box): a reply
     *  is visible, the other side is generating one, or a conversation thread/history is present.
     *  Lets us wait for a slow reply for as long as it takes, while still detecting a send that
     *  never landed (none of these present) so we can retry it instead of deadlocking. */
    private fun looksSent(): Boolean {
        if (latestReplyText() != null) return true
        return currentNodes.any { n ->
            val id = (n.viewIdResourceName ?: "").lowercase()
            val desc = (n.contentDescription ?: "").toString().lowercase()
            id.contains("history_list") || id.contains("message_text_container") ||
                id.contains("chat_history") || desc.contains("list of conversations") ||
                desc.contains("stop generating") || desc.contains("stop response") ||
                desc.contains("answer now") || (desc.contains("stop") && desc.contains("generat"))
        }
    }

    /** Remember a message we just pushed via Send, so we don't re-type or re-send it. */
    private val recentSent = ArrayDeque<Pair<String, Long>>()

    private fun rememberSent(text: String) {
        val n = norm(text); val now = System.currentTimeMillis()
        lastSentText = n; lastSentAt = now
        recentSent.addLast(n to now)
        while (recentSent.size > 6) recentSent.removeFirst()
    }

    /** The last few messages we actually sent - so the conversation autopilot can be told NOT to
     *  repeat them (the repeated-intro loop). Most-recent last. */
    fun recentSentTexts(): List<String> = recentSent.map { it.first }.distinct()

    /** True if [text] matches (or is a slight rewording of) ANY message we sent in the last ~90s -
     *  so the model can't keep re-typing the same intro instead of reading the reply and moving on.
     *  Fuzzy: the vision model kept re-sending the SAME opening with a different tail
     *  ("...How shall we proceed?" vs "...with the conversation?"), which an EXACT match missed. */
    private fun isRecentlySent(text: String): Boolean {
        val n = norm(text); val now = System.currentTimeMillis()
        return recentSent.any { (sent, t) ->
            now - t < 90_000L && (sent == n || sharesLongPrefix(sent, n))
        }
    }

    /** Same message reworded: a long shared prefix (the whole intro) means it's a near-duplicate. */
    private fun sharesLongPrefix(a: String, b: String): Boolean {
        val k = minOf(a.length, b.length)
        if (k < 50) return false
        var i = 0
        while (i < k && a[i] == b[i]) i++
        return i >= 50
    }

    /** True if we sent ANY message very recently - turns a redundant Send into a WAIT, and lets a
     *  conversation WAIT for the reply instead of re-deciding (and re-typing the intro). */
    fun recentlySentAny(): Boolean =
        lastSentText.isNotEmpty() && System.currentTimeMillis() - lastSentAt < 20_000L

    /** Did we send within [ms]? Used to keep a conversation WAITING for the reply (not looping)
     *  for a generous window after our last message, since the other side can be slow. */
    fun sentWithinMs(ms: Long): Boolean =
        lastSentText.isNotEmpty() && System.currentTimeMillis() - lastSentAt < ms

    /** R6: is this plausibly a CHAT surface - a message composer plus a way to send - so turn-taking,
     *  latestReplyText, and the `reply` verb make sense here? STRUCTURAL, never a hardcoded package list
     *  (§12 - capability, not a name): an editable composer field AND either a Send-like control next to it
     *  or a composer whose hint invites a message. A browser SERP / search page has a long text body and an
     *  editable address bar but NEITHER a send control nor a message-composer hint, so it no longer reads as
     *  "a conversation" (the owner's bug: `reply` offered on a Chrome results page). Cheap: reuses the
     *  already-walked currentNodes, no extra tree pass. */
    fun isChatSurface(): Boolean {
        val editable = currentNodes.firstOrNull { it.isEditable } ?: return false
        val hint = (editable.hintText?.toString() ?: "").lowercase()
        val composerHint = hint.contains("message") || hint.contains("reply") || hint.contains("chat") ||
            hint.contains("type a") || hint.contains("ask ") || hint.contains("send a")
        val sendish = currentNodes.any { n ->
            val l = effectiveText(n).ifBlank { n.contentDescription?.toString().orEmpty() }.lowercase().trim()
            l == "send" || l == "post" || l == "reply" || l == "send message" || l == "send now" || l.startsWith("send ")
        }
        return composerHint || sendish
    }

    /** Longest non-editable on-screen text - a good proxy for the other side's latest reply.
     *  Excludes messages WE just sent so the conversation autopilot never replies to itself. R6: gated to a
     *  chat surface, so a browser/search page's longest paragraph is never mistaken for an unanswered reply. */
    fun latestReplyText(): String? =
        if (!isChatSurface()) null
        else currentNodes.filter { !it.isEditable }
            .mapNotNull { it.text?.toString()?.trim() }
            .filter { it.length > 40 && !isRecentlySent(it) }
            .maxByOrNull { it.length }

    /** True if the input box still shows a message we ALREADY sent recently - a stale draft the
     *  app didn't clear. Lets the autopilot overwrite it and move the conversation on instead of
     *  looping on a send that never cleared the box. */
    fun inputIsStaleSentDraft(): Boolean {
        val t = inputText()
        return t.isNotEmpty() && isRecentlySent(t)
    }

    /** Current text in the input box (focused field, else the lone editable field). */
    fun inputText(): String {
        val f = rootInActiveWindow?.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)
            ?: currentNodes.firstOrNull { it.isEditable }
        f?.refresh()
        return effectiveText(f)
    }

    /** A field's REAL text, treating a placeholder/hint shown AS the text as empty. Gemini's empty
     *  box reports its hint ("Ask Gemini") as text, which made inputText() look non-empty and
     *  silently BLOCKED the conversation autopilot's "box is ready" gate from ever opening - so the
     *  helper never took over and the big model looped on the intro. Used everywhere we ask "is the
     *  box empty / what did the user actually type". */
    private fun effectiveText(n: AccessibilityNodeInfo?): String {
        if (n == null) return ""
        val t = n.text?.toString()?.trim().orEmpty()
        val hint = n.hintText?.toString()?.trim().orEmpty()
        return if (hint.isNotEmpty() && t == hint) "" else t
    }

    /** Type text into the input box (focused field, else the lone editable field). */
    fun setInputText(text: String): Boolean {
        val f = rootInActiveWindow?.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)
            ?: currentNodes.firstOrNull { it.isEditable } ?: return false
        return setText(f, text)
    }

    private fun editableFieldCount(): Int = currentNodes.count { it.isEditable }

    /** ENGINE-SIDE state verification (the owner's "intelligent peek"): given the agent's stated
     *  expectation, CHECK the common, deterministically-checkable conditions against the live
     *  accessibility tree - cheap and reliable - and return a verdict the agent RECEIVES, instead of
     *  making the slow/fallible model re-perceive to verify itself. null = nothing we can check
     *  deterministically here, so the caller falls back (the agent looks, or a visual pixel check). */
    fun verifyExpectation(expect: String): String? {
        val e = expect.lowercase()
        // ONLY conditions we can check with HIGH confidence go here - a wrong "✓" is worse than no
        // check (it could tell the agent something landed when it didn't). Deliberately NO "did it
        // send" check: that needs the pre-send state and is already handled reliably by
        // confirmPendingSend (a chat history list is always present, so it would false-positive here).
        return when {
            // Text landed in the input box (after a set_text/type). inputText() is hint-aware.
            (e.contains("text") || e.contains("typed") || e.contains("message") || e.contains("prompt")) &&
                (e.contains("field") || e.contains("box") || e.contains("input") || e.contains("typed") || e.contains("entered")) ->
                if (inputText().isNotBlank()) "✓ text IS in the field now" else "✗ the field looks EMPTY - the text may not have landed"
            // A Send/submit control is reachable (before a send).
            e.contains("send") || e.contains("submit") ->
                if (hasReachableSend()) "✓ a Send control IS on screen" else "✗ no Send control is visible yet"
            // The keyboard is up (e.g. expecting to type).
            e.contains("keyboard") ->
                if (isKeyboardOpen()) "✓ the keyboard IS open" else "✗ the keyboard is NOT open"
            else -> null
        }
    }

    /** True if a chat/compose field still holds non-blank text that was never sent - a
     *  strong signal the task is NOT actually done (the model typed but never pressed Send).
     *  Used to veto a premature `done`. Deliberately narrow (message-like fields only) so it
     *  never blocks a finished task or trips on a search box. */
    fun hasUnsentMessage(): Boolean {
        fun pending(n: AccessibilityNodeInfo?): Boolean {
            if (n == null || !n.isEditable) return false
            n.refresh()
            val t = effectiveText(n)   // ignore the "Ask Gemini" placeholder
            return t.isNotEmpty() && looksLikeMessageInput(n)
        }
        if (pending(rootInActiveWindow?.findFocus(AccessibilityNodeInfo.FOCUS_INPUT))) return true
        return currentNodes.any { pending(it) }
    }

    /** Heuristic: does this field look like a chat/compose box (vs a form field)? Decides
     *  whether "text already present" should auto-send. */
    private fun looksLikeMessageInput(node: AccessibilityNodeInfo): Boolean {
        val hay = listOf(
            // SHORT id only - the full viewIdResourceName carries the package
            // (e.g. "...googlequicksearchbox:id/...") whose name can contain words like
            // "search" and wrongly flip the classification for EVERY field in that app.
            node.viewIdResourceName?.substringAfterLast('/'), node.contentDescription?.toString(),
            node.hintText?.toString(), node.text?.toString()
        ).joinToString(" ") { it ?: "" }.lowercase()
        return listOf("message", "chat", "ask", "compose", "tweet", "post", "reply",
            "comment", "send", "say something").any { hay.contains(it) }
    }

    /** A SEARCH box (as opposed to a chat/compose input or a form field). Typing into one and
     *  submitting is one intent, so after the text lands we press the keyboard Search/Enter - the
     *  model otherwise re-taps the field forever (the YouTube "typed cats, never searched" loop). */
    private fun looksLikeSearchField(node: AccessibilityNodeInfo): Boolean {
        val hay = listOf(
            // SHORT id only (see looksLikeMessageInput): otherwise the "googlequicksearchbox"
            // PACKAGE made Gemini's chat input look like a search box, so set_text pressed IME
            // "Search" - which Gemini ignores - instead of the Send arrow, and the message never went.
            node.viewIdResourceName?.substringAfterLast('/'), node.contentDescription?.toString(), node.hintText?.toString()
        ).joinToString(" ") { it ?: "" }.lowercase()
        return hay.contains("search") || hay.contains("query") || hay.contains("find")
    }

    // --- SCREENSHOT (for the vision model) --------------------------------

    /** Capture the current screen as a software Bitmap (async). Returns null on failure. */
    fun captureScreenshot(onResult: (Bitmap?) -> Unit) {
        try {
            takeScreenshot(Display.DEFAULT_DISPLAY, mainExecutor, object : TakeScreenshotCallback {
                override fun onSuccess(result: ScreenshotResult) {
                    val bmp = try {
                        val hb = result.hardwareBuffer
                        val raw = Bitmap.wrapHardwareBuffer(hb, result.colorSpace)
                        val copy = raw?.copy(Bitmap.Config.ARGB_8888, false)
                        raw?.recycle()
                        hb.close()
                        copy
                    } catch (e: Exception) { null }
                    onResult(bmp)
                }
                override fun onFailure(errorCode: Int) {
                    AgentLog.log("shot", "fail code=$errorCode")
                    onResult(null)
                }
            })
        } catch (e: Exception) {
            AgentLog.log("shot", "exc ${e.message}")
            onResult(null)
        }
    }
}
