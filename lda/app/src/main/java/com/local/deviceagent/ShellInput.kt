package com.local.deviceagent

import android.app.Activity
import android.content.Context
import android.content.pm.PackageManager
import rikka.shizuku.Shizuku

/**
 * SHELL INPUT — a privileged BACKUP actuator for taps/swipes/strokes/keys accessibility can't dispatch.
 *
 * Owner's call (dedicated device): "give the agent whatever access it needs to function; gate it with a warning;
 * default on; choose whichever is most likely to work." The executor picks the actuator MOST LIKELY to land: a11y is
 * the default (fast, no shell spawn), but once a11y has REFUSED a gesture in an app ([noteA11yRefusal]/[preferShell])
 * the executor tries the SHELL actuator FIRST there — either way the other is the fallback. It runs the platform
 * `input` binary through the SHELL uid that Shizuku grants an app without root (the standard on-device path) — the
 * owner installs the free Shizuku app and starts it once per boot.
 *
 * GRACEFUL BY DESIGN: with no Shizuku running / not permitted, [available] is false and every inject returns false,
 * so the caller falls straight back to accessibility exactly as before. That is why default-on is harmless — it
 * simply does nothing until the owner sets Shizuku up, then the extra reach turns on with zero code change.
 *
 * SAFETY (§3): SCOPED TO INPUT INJECTION ONLY. The only thing it ever runs is the platform `input` command with
 * numeric/coordinate/keycode args THIS CLASS builds — it deliberately exposes NO arbitrary-command runner to the
 * model (a general shell / code-runner is the §3-blocked attack surface another AI tried to exploit). Text passed
 * to [text] is shell-quoted here, never interpolated raw, and the model never supplies a command string. It is
 * reached only through the agent's own decided verbs in the executor, behind the same §3 gates as every action, and
 * is never triggerable by on-screen/external data. All Shizuku access is wrapped so a missing/older Shizuku can
 * never crash or break the build.
 */
object ShellInput {

    // KILL-SWITCH fire-time barrier for the DEFERRED shell actuator. actuate() may spawn a shell worker just
    // BEFORE a STOP flips injectionHalted; that worker would otherwise still exec `input tap …` post-halt (a ghost
    // input — the owner's "still lands after HALTED"). haltInjection() sets this; resumeInjection() clears it at
    // task start. Checked immediately before the exec so a stopped shell never lands.
    @Volatile var halted = false

    /** True only when Shizuku's service is alive AND has granted us the shell uid. Re-checked every call (cheap),
     *  so it flips on the instant the owner grants it — no restart. Any error (Shizuku absent) ⇒ false ⇒ a11y. */
    fun available(context: Context): Boolean = try {
        Shizuku.pingBinder() && Shizuku.checkSelfPermission() == PackageManager.PERMISSION_GRANTED
    } catch (_: Throwable) { false }

    /** Whether Shizuku is present at all (installed + service reachable), regardless of our permission — so
     *  Settings can tell "install Shizuku" apart from "grant the permission". */
    fun providerPresent(): Boolean = try { Shizuku.pingBinder() } catch (_: Throwable) { false }

    // ── ACTUATOR POLICY (owner: "choose whichever is most likely to work", not only-on-failure) ────────────────
    // The only HARD "which actuator can act here" signal available without a landing-check is an accessibility
    // gesture REFUSAL (dispatchGesture==false ⇒ a11y definitely can't reach this surface). We LEARN from it per app:
    // once a11y has refused in an app, shell is the more-likely-to-work actuator there, so [preferShell] returns true
    // and the executor tries shell FIRST next time (a11y stays the fallback). Cheap SharedPreferences counter, capped.
    // (When the landing-signature reflex ships, it upgrades this from refusal-only to real per-regime success credit.)
    private const val POLICY = "actuator_policy"
    private const val MAX_APPS = 60

    fun noteA11yRefusal(c: Context, app: String) {
        if (app.isBlank()) return
        try {
            val p = c.getSharedPreferences(POLICY, Context.MODE_PRIVATE)
            val n = p.getInt(app, 0) + 1
            val e = p.edit().putInt(app, n)
            // keep the map bounded — drop an arbitrary other app if we're over cap (rough LRU-free trim)
            if (p.all.size > MAX_APPS) p.all.keys.firstOrNull { it != app }?.let { e.remove(it) }
            e.apply()
        } catch (_: Throwable) {}
    }

    /** True when shell is available AND a11y has refused in this app before ⇒ shell is the more-likely actuator here,
     *  so the caller should try it first. Cold-start (never refused) ⇒ false ⇒ a11y-first (fast, no shell spawn). */
    fun preferShell(c: Context, app: String): Boolean = try {
        app.isNotBlank() && available(c) && c.getSharedPreferences(POLICY, Context.MODE_PRIVATE).getInt(app, 0) >= 1
    } catch (_: Throwable) { false }

    /** Ask Shizuku for the permission (interactive — call from an Activity, e.g. the Settings toggle). No-op if
     *  Shizuku isn't running or it's already granted. The result is read back lazily by [available]; no listener
     *  needed. */
    fun requestPermissionFrom(activity: Activity, code: Int = 4711) {
        try {
            if (!Shizuku.pingBinder()) return
            if (Shizuku.checkSelfPermission() == PackageManager.PERMISSION_GRANTED) return
            if (Shizuku.shouldShowRequestPermissionRationale()) return   // owner previously denied — respect it
            Shizuku.requestPermission(code)
        } catch (_: Throwable) {}
    }

    fun tap(x: Int, y: Int): Boolean = run("input tap $x $y")
    fun swipe(x1: Int, y1: Int, x2: Int, y2: Int, ms: Long): Boolean = run("input swipe $x1 $y1 $x2 $y2 $ms")
    fun longPress(x: Int, y: Int, ms: Long = 600L): Boolean = run("input swipe $x $y $x $y $ms")  // zero-length hold
    fun key(keycode: Int): Boolean = run("input keyevent $keycode")
    /** Type text via the shell. Quoted here (never raw interpolation) so it stays input-only, not a command. */
    fun text(s: String): Boolean {
        val safe = "'" + s.replace("'", "'\\''") + "'"       // single-quote + escape embedded quotes
        return run("input text $safe")
    }

    /** Run ONE `input …` command through Shizuku's shell process. newProcess is a restricted Shizuku API, so it's
     *  invoked by REFLECTION (lint-proof, version-tolerant) and fully guarded. Returns true iff the process exited 0.
     *  Off the main thread expected (the caller is already in an executor action). */
    private fun run(inputCmd: String): Boolean {
        if (halted) return false   // KILL-SWITCH: refuse a deferred shell exec that a STOP has since halted
        return try {
            if (!Shizuku.pingBinder() || Shizuku.checkSelfPermission() != PackageManager.PERMISSION_GRANTED) return false
            val m = Shizuku::class.java.getMethod(
                "newProcess", Array<String>::class.java, Array<String>::class.java, String::class.java)
            m.isAccessible = true
            val proc = m.invoke(null, arrayOf("sh", "-c", inputCmd), null, null) ?: return false
            val exit = proc.javaClass.getMethod("waitFor").invoke(proc) as? Int ?: -1
            if (exit != 0) AgentLog.log("shellinput", "input exit=$exit for: ${inputCmd.take(40)}")
            exit == 0
        } catch (e: Throwable) {
            AgentLog.log("shellinput", "shell input failed (${e.javaClass.simpleName}) — falling back to accessibility")
            false
        }
    }
}
