package com.local.deviceagent

import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import android.os.PowerManager

/**
 * Lightweight device-health readouts (battery + thermal) used for the safety
 * guards and for diagnostics in the debug log. All calls are cheap and safe to
 * poll once per agent step.
 */
object DeviceStats {

    /** Temporal sense (Batch 10): the wall-clock the agent READS so time-relative commands actually work
     *  - "text Mom I'll be there at 6", "set an alarm 30 min from now", "is the store open". Without this
     *  the model is fully time-blind (nothing else injects a clock). One cheap system read, no Context. */
    fun timeContext(): String = try {
        java.text.SimpleDateFormat("EEE MMM d, h:mm a", java.util.Locale.getDefault()).format(java.util.Date())
    } catch (_: Exception) { "" }

    fun batteryPercent(context: Context): Int {
        val bm = context.getSystemService(Context.BATTERY_SERVICE) as? BatteryManager ?: return -1
        val pct = bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
        return if (pct in 0..100) pct else -1
    }

    fun isCharging(context: Context): Boolean {
        val i = context.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED)) ?: return false
        val status = i.getIntExtra(BatteryManager.EXTRA_STATUS, -1)
        return status == BatteryManager.BATTERY_STATUS_CHARGING ||
            status == BatteryManager.BATTERY_STATUS_FULL
    }

    /** PowerManager thermal status (0 none .. 6 shutdown); -1 if unknown. */
    fun thermalStatus(context: Context): Int {
        val pm = context.getSystemService(Context.POWER_SERVICE) as? PowerManager ?: return -1
        return try { pm.currentThermalStatus } catch (_: Exception) { -1 }
    }

    fun thermalLabel(status: Int): String = when (status) {
        PowerManager.THERMAL_STATUS_NONE -> "none"
        PowerManager.THERMAL_STATUS_LIGHT -> "light"
        PowerManager.THERMAL_STATUS_MODERATE -> "moderate"
        PowerManager.THERMAL_STATUS_SEVERE -> "severe"
        PowerManager.THERMAL_STATUS_CRITICAL -> "critical"
        PowerManager.THERMAL_STATUS_EMERGENCY -> "emergency"
        PowerManager.THERMAL_STATUS_SHUTDOWN -> "shutdown"
        else -> "unknown"
    }

    // --- MEMORY (the owner's #1 failure mode: the RAM ceiling) -----------------

    private fun memInfo(context: Context): android.app.ActivityManager.MemoryInfo? {
        val am = context.getSystemService(Context.ACTIVITY_SERVICE) as? android.app.ActivityManager ?: return null
        val mi = android.app.ActivityManager.MemoryInfo()
        return try { am.getMemoryInfo(mi); mi } catch (_: Exception) { null }
    }

    /** Available / total system RAM in MB (-1 if unknown). availMem is the headroom before the
     *  low-memory killer starts reaping - logging it per step makes the OOM boundary VISIBLE. */
    fun availMemMb(context: Context): Long = memInfo(context)?.let { it.availMem / (1024 * 1024) } ?: -1
    fun totalMemMb(context: Context): Long = memInfo(context)?.let { it.totalMem / (1024 * 1024) } ?: -1

    /** Is there a validated internet connection right now? (Part A — offline-at-use.) Read-only; used ONLY so the
     *  agent doesn't waste steps on a web `search` with no network, and to surface an offline orient hint. The
     *  agent is FULLY functional offline; this never gates any on-device work. Defaults to true on any error so a
     *  read failure can never wrongly declare "offline" and suppress a legitimate search. */
    fun isOnline(context: Context): Boolean = try {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as? android.net.ConnectivityManager ?: return true
        val net = cm.activeNetwork ?: return false
        val caps = cm.getNetworkCapabilities(net) ?: return false
        caps.hasCapability(android.net.NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
            caps.hasCapability(android.net.NetworkCapabilities.NET_CAPABILITY_VALIDATED)
    } catch (_: Throwable) { true }
    /** The OS already considers memory low (the killer is active) - a genuine close-call signal. */
    fun lowMemory(context: Context): Boolean = memInfo(context)?.lowMemory ?: false

    /** LIVE memory pressure (re-read each use, NOT cached) - the single signal the adaptive throttle/degrade
     *  reads so the cache, the image rung, and the inter-step pacing all agree. The owner's directive: run on
     *  budget hardware, "throttle so it never crashes but is just slower", and use as little as necessary while
     *  "breathing" when there's juice. NONE = headroom, run full quality/speed. TIGHT = free RAM getting low,
     *  trim the cheap things (cache, pace a little). CRITICAL = the OS is about to start killing - back off hard
     *  (lean image, real pauses) so the loop survives instead of getting OS-reaped mid-task. */
    enum class MemPressure { NONE, TIGHT, CRITICAL }
    fun memPressure(context: Context): MemPressure {
        // OWNER'S RULE (after the breather fired on a HEALTHY phone): pressure interventions -
        // breather, idle release, throttle, lean image - may only trigger when Android is genuinely
        // about to start killing processes, NEVER on an efficiency guess. So no static thresholds:
        // 1.0-1.2GB free is this phone's NORMAL state with E4B resident, and the old "free <= 1200 =
        // CRITICAL" line paused a working task on the home screen. The OS itself tells the truth:
        // mi.lowMemory = availMem crossed the device's OWN low-memory-killer threshold (that IS
        // "about to force close"). CRITICAL = exactly that flag. TIGHT = within 25% above that same
        // per-device threshold (a real cushion derived from the OS line, not a guess) - it only
        // softens the image/pace, never pauses anything.
        val mi = memInfo(context) ?: return MemPressure.NONE
        return when {
            mi.lowMemory -> MemPressure.CRITICAL
            mi.availMem in 1 until (mi.threshold * 5) / 4 -> MemPressure.TIGHT
            else -> MemPressure.NONE
        }
    }

    // --- HARDWARE / MODEL DETECTION (drives the adaptive "lighter path") -------

    /** Coarse hardware tier from total RAM, so the SAME agent takes a lighter route on a weak phone
     *  (e.g. a 4GB Galaxy A16) and the rich route on a Fold with 12GB+. This is the detection the owner
     *  wants to "guide the path to completion": one build, many devices (the solutions/business vision). */
    enum class DeviceTier { LEAN, MID, RICH }
    fun deviceTier(context: Context): DeviceTier {
        val gb = totalMemMb(context) / 1024.0
        return when {
            gb <= 0 -> DeviceTier.MID          // unknown -> middle, don't over-degrade a device we can't read
            gb < 4.5 -> DeviceTier.LEAN
            gb < 8.5 -> DeviceTier.MID
            else -> DeviceTier.RICH
        }
    }

    /** The Gemma-3n EFFECTIVE-size variant from the model filename, when it says so: "E4B" / "E2B",
     *  else "". (The "E" in E4B is EFFECTIVE parameters, NOT "experts" - Gemma 3n is not a routed
     *  mixture-of-experts. The family uses MatFormer, where E2B is a smaller model NESTED inside E4B,
     *  plus Per-Layer Embeddings the runtime can offload to shrink the accelerator memory footprint.
     *  There are no experts for the app to toggle - the runtime handles the architecture; our only
     *  real lever is recognizing the variant and choosing the one that FITS, and E2B is the edge-sized
     *  sub-model that clears the RAM ceiling.) */
    fun modelVariant(modelPath: String?): String {
        val n = modelPath?.substringAfterLast('/')?.lowercase() ?: return ""
        return when { "e4b" in n -> "E4B"; "e2b" in n -> "E2B"; else -> "" }
    }

    /** Is the imported model a HEAVY one (~E4B, ~4GB+ of weights) vs a light one (~E2B)? Trust the
     *  NAME first (the file usually says E4B/E2B - the most reliable signal), then fall back to file
     *  size. Getting this right propagates everywhere: the lean-path decision, the KV-cache sizing,
     *  and the fitness guard all key off it, so a correctly-recognized variant is adapted-for for free. */
    fun modelIsHeavy(modelPath: String?): Boolean {
        when (modelVariant(modelPath)) { "E4B" -> return true; "E2B" -> return false }
        val len = modelPath?.let { try { java.io.File(it).length() } catch (_: Exception) { 0L } } ?: 0L
        return len > 3_500_000_000L
    }

    /** ABSOLUTE low-free-RAM signal for a HEAVY model — the companion to memPressure(). memPressure keys off the
     *  OS low-memory-killer flag/threshold, which on a LARGE-RAM device (the 11GB Fold) stays NONE even at <1GB
     *  free — so the KV-cache down-size + the pacing surcharge (both gated on memPressure) NEVER fired when a real
     *  premature-end ran at ~864MB free for a ~4.4GB model. This turns the SAME band the "[warn] only NNNMB free"
     *  line already uses into an ACTION signal (not just a warning): a heavy model with less than HEAVY_LOWMEM_MB
     *  free is one bad allocation from an OS kill, so callers pace down / shrink the KV / skip the warm-KV session
     *  there. It NEVER pauses a task (that stays memPressure/safety-gated per the owner's "only when genuinely
     *  about to force-close" rule) — it only softens footprint, exactly like TIGHT. Cheap: one availMem read. */
    const val HEAVY_LOWMEM_MB = 2600
    fun heavyModelRamTight(context: Context, modelPath: String?): Boolean =
        modelIsHeavy(modelPath) && availMemMb(context) in 1..HEAVY_LOWMEM_MB

    /** Should perception take the LIGHTER path on THIS device+model? True when the hardware is weak, or a
     *  heavy model is paired with only mid hardware - the combinations where the rich path courts the RAM
     *  ceiling. A strong device (the dev Fold, RICH) returns false, so the OWNER'S TEST DEVICE is never
     *  degraded - it keeps running the full rich path he's tuning against. */
    fun useLeanPath(context: Context, modelPath: String?): Boolean {
        val tier = deviceTier(context)
        return tier == DeviceTier.LEAN || (tier == DeviceTier.MID && modelIsHeavy(modelPath))
    }

    /** One-line device+model identity for the TOP of a task's log - so a log pasted from ANY device is
     *  self-describing: which phone, Android, how much RAM, which model, light/heavy, the chosen path.
     *  Essential once the agent runs on hardware other than the dev Fold (multi-device / customers). */
    fun deviceHeader(context: Context, modelPath: String?, helperOn: Boolean): String {
        val variant = modelVariant(modelPath).ifBlank { if (modelIsHeavy(modelPath)) "~E4B" else "~E2B" }
        val heavy = if (modelIsHeavy(modelPath)) "heavy $variant" else "light $variant"
        val model = modelPath?.substringAfterLast('/')?.take(40) ?: "none"
        return "${android.os.Build.MODEL} / Android ${android.os.Build.VERSION.RELEASE} / " +
            "ram ${availMemMb(context)}of${totalMemMb(context)}MB / tier ${deviceTier(context)} / " +
            "model $model[$heavy] / helper ${if (helperOn) "on" else "off"} / " +
            "path ${if (useLeanPath(context, modelPath)) "LEAN" else "rich"}"
    }

    /** MODEL-FITNESS GUARD (the A16 / multi-device / business case): a HEAVY model (~E4B, ~4GB of
     *  weights) simply cannot fit a LEAN device's RAM (a 4GB phone) no matter how light perception gets -
     *  the weights alone overflow, so it OOMs on load every time. Detect that combo so the owner/customer
     *  gets a clear "use a smaller model" signal instead of silent black-wallpaper crashes. Conservative:
     *  only flags the clearly-impossible heavy-on-LEAN pairing, never the dev Fold (RICH) or a light model. */
    fun modelTooHeavy(context: Context, modelPath: String?): Boolean =
        modelIsHeavy(modelPath) && deviceTier(context) == DeviceTier.LEAN

    /** A one-line, human-readable warning when the imported model won't fit this device, else "". */
    fun fitnessWarning(context: Context, modelPath: String?): String =
        if (modelTooHeavy(context, modelPath))
            "This ${modelVariant(modelPath).ifBlank { "model" }} is too large for this phone's RAM (${totalMemMb(context)}MB) and will likely crash on load. E2B is the same Gemma-3n family's edge-sized sub-model (nested inside E4B, built for exactly this) — import it for reliable on-device use, not a downgrade."
        else ""

    /** One-line summary for the debug log. */
    fun snapshot(context: Context): String {
        val t = thermalStatus(context)
        return "battery=${batteryPercent(context)}% charging=${isCharging(context)} " +
            "thermal=${thermalLabel(t)}($t) ram=${availMemMb(context)}of${totalMemMb(context)}MB"
    }
}
