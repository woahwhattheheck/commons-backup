package com.local.deviceagent

/**
 * W0 (A1 / JEPA passive world model) — SCREEN-CLASS TAXONOMY.
 *
 * A cheap, deterministic, Android-free classifier that abstracts a raw screen into a small STABLE CLASS
 * (list / dialog / settings / canvas / keyboard / webview / loading / error / home / generic), plus a
 * device-state overlay and a nav-primitive for an action verb. This is the **H-JEPA abstraction key**: the
 * world model banks + bakes its next-screen references keyed by the screen-CLASS, not the specific screen
 * signature — so it learns "how a settings screen behaves" (aptitude / pattern) rather than a memorized
 * path (the owner's "modify abstractions, not paths"). Higher-level predictability = the abstraction, exactly
 * as H-JEPA's higher levels keep only the long-horizon invariant.
 *
 * Pure functions over already-computed signals (the codec string, package, element count, the visible text
 * layer) so it costs ~nothing per step and is unit-testable on the JVM with no Android or engine deps.
 * Class strings are FIXED (they become ReferenceStore `sig` keys) — never rename them. INV: abstraction-keyed
 * on-device weight baking (see docs/PATENT_SUPPORT.md).
 */
object ScreenClass {
    // The closed class vocabulary — STABLE strings (they key the reference/residency pools). Do not rename.
    const val LIST = "list"
    const val DIALOG = "dialog"
    const val SETTINGS = "settings"
    const val CANVAS = "canvas"
    const val KEYBOARD = "keyboard"
    const val WEBVIEW = "webview"
    const val LOADING = "loading"
    const val ERROR = "error"
    const val HOME = "home"
    const val GENERIC = "generic"

    private val LOADING_MARKERS = listOf(
        "loading", "please wait", "just a moment", "getting things ready", "connecting", "one moment")
    private val ERROR_MARKERS = listOf(
        "no internet", "no connection", "check your connection", "try again", "something went wrong",
        "couldn't", "could not", "failed to", "went wrong", "unable to", "offline", "retry", "error")
    private val BROWSER_HINTS = listOf(
        "chrome", "browser", "webview", "firefox", "internet", "duckduckgo", "opera", "brave", "edge")
    private val LAUNCHER_HINTS = listOf("launcher", "nexuslauncher", "trebuchet", "pixel.launcher", "homescreen")
    private val CONFIRM_WORDS = listOf(
        "ok", "cancel", "allow", "deny", "yes", "no", "confirm", "continue", "agree", "dismiss", "got it", "not now")

    /**
     * Classify a screen into ONE stable class. Deterministic priority order (a spinner screen isn't a "list";
     * an IME being up dominates whatever is behind it).
     * @param pkg          current foreground package
     * @param codec        codecScreen() output (id + role/state chars per item) — may be blank
     * @param text         the visible TEXT-ON-SCREEN layer (for marker detection) — may be blank
     * @param elementCount number of perceivable interactive elements
     * @param keyboardUp   an editable field is focused / the IME is up
     */
    fun classify(pkg: String, codec: String, text: String, elementCount: Int, keyboardUp: Boolean): String {
        val p = pkg.lowercase()
        val t = text.lowercase()
        if (elementCount <= 6 && LOADING_MARKERS.any { t.contains(it) }) return LOADING
        if (elementCount <= 12 && ERROR_MARKERS.any { t.contains(it) }) return ERROR
        if (keyboardUp) return KEYBOARD
        // canvas = tree-empty: a game / drawing / video / camera surface where the a11y tree carries almost nothing.
        if (elementCount <= 2) return CANVAS
        if (LAUNCHER_HINTS.any { p.contains(it) }) return HOME
        // dialog = a small screen carrying a confirm/cancel affordance (a permission prompt / alert).
        if (elementCount in 1..8 && CONFIRM_WORDS.any { w -> Regex("(^|\\W)${Regex.escape(w)}(\\W|$)").containsMatchIn(t) }) return DIALOG
        if (p.contains("settings") || toggleDensity(codec) >= 0.34) return SETTINGS
        if (BROWSER_HINTS.any { p.contains(it) }) return WEBVIEW
        if (elementCount >= 6) return LIST
        return GENERIC
    }

    /** Fraction of codec ITEM lines (each starts with a digit id) that carry a toggle role ('t') or a
     *  checkable state ('*' on / 'o' off) in the 2 chars right after the id — a settings screen is toggle-dense. */
    private fun toggleDensity(codec: String): Double {
        val items = codec.lineSequence().filter { it.isNotBlank() && it.first().isDigit() }.toList()
        if (items.isEmpty()) return 0.0
        val toggles = items.count { line ->
            val afterId = line.dropWhile { it.isDigit() }.take(2)
            afterId.startsWith("t") || afterId.contains('*') || afterId.contains('o')
        }
        return toggles.toDouble() / items.size
    }

    /** A device-state overlay tag from the visible text (connectivity/settings state the world model can key
     *  on), or "" when nothing is signalled. The abstraction of "what state the device is in". */
    fun deviceState(text: String): String {
        val t = text.lowercase()
        return when {
            t.contains("airplane mode") || t.contains("airplane") -> "airplane"
            t.contains("no internet") || t.contains("no connection") || t.contains("offline") -> "offline"
            t.contains("mobile data") || t.contains("cellular") -> "mobile"
            t.contains("wi-fi") || t.contains("wifi") -> "wifi"
            t.contains("bluetooth") -> "bluetooth"
            else -> ""
        }
    }

    /** Abstract an action VERB into a nav-primitive class — the "how you move a phone" abstraction the world
     *  model learns (back returns, app-switch changes app, scroll reveals, a tap/type acts), NOT a specific path. */
    fun navPrimitive(verb: String): String = when (verb.lowercase()) {
        "back" -> "back"
        "home" -> "home"
        "open_app", "app_drawer", "recent_apps", "split_screen" -> "app-switch"
        "scroll", "swipe", "next_page", "prev_page" -> "scroll"
        "set_text", "clear", "enter", "send", "type", "input" -> "type"
        "click", "tap_xy", "aim", "tap_grid", "tap_near", "tap_sequence", "long_press", "do" -> "tap"
        "notifications", "quick_settings" -> "system"
        else -> "other"
    }
}
