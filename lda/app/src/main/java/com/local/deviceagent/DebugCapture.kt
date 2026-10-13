package com.local.deviceagent

import android.content.Context
import android.graphics.Bitmap
import java.io.File
import java.io.FileOutputStream
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

/**
 * DEBUG MODE rich capture (owner: gave the agent a dedicated debug device "so we can always have data").
 *
 * The terse `[tag]` AgentLog is for glance-reading a run; THIS captures the FULL detail a real debug/replay
 * needs — the exact per-step PROMPT, the raw MODEL OUTPUT, timing, and the per-step SCREENSHOT — into a durable
 * bundle in EXTERNAL files so the owner can always pull it off the device with `adb pull` (no root) and share it.
 *
 * Only writes when `debug_mode` is on (default OFF) — it's storage-heavy, so it's for the dedicated device, not
 * a normal user. Nothing leaves the device on its own; the owner pulls/shares it. Everything is size-capped so it
 * can't fill the disk, and every call is wrapped so a capture failure can NEVER affect the running task.
 */
object DebugCapture {
    private const val TRACE = "trace.txt"
    private const val MAX_TRACE_BYTES = 48L * 1024 * 1024   // rotate the text trace once at ~48MB
    private const val MAX_SHOTS = 800                        // keep the most-recent N step screenshots
    private const val EXPORT = "debug_bundle.zip"

    /** The durable bundle dir. External files (`.../Android/data/<pkg>/files/debug`) so `adb pull` works without
     *  root; falls back to internal storage if external is unavailable. Stable path — pull it any time. */
    fun dir(c: Context): File {
        val base = c.getExternalFilesDir(null) ?: c.filesDir
        return File(base, "debug").apply { try { mkdirs() } catch (_: Throwable) {} }
    }

    fun path(c: Context): String = try { dir(c).absolutePath } catch (_: Throwable) { "?" }

    private fun on(c: Context): Boolean = try { SettingsManager(c).isDebugModeEnabled() } catch (_: Throwable) { false }

    /** Record a full text record — the rich detail the `[tag]` log omits: the exact prompt + the raw model output
     *  + a caller header (phase/timing/tokens). No-op unless debug_mode is on. */
    fun record(c: Context, header: String, prompt: String, output: String) {
        if (!on(c)) return
        try {
            val f = File(dir(c), TRACE)
            if (f.exists() && f.length() > MAX_TRACE_BYTES) {
                val old = File(f.parentFile, "trace.1.txt"); old.delete(); f.renameTo(old)
            }
            f.appendText("\n===== $header =====\n--- PROMPT ---\n$prompt\n--- OUTPUT ---\n$output\n")
        } catch (_: Throwable) {}
    }

    /** Save a per-step screenshot (the screen the model saw this step) so a run replays visually.
     *  Bounded: prunes the oldest shots past [MAX_SHOTS]. No-op unless debug_mode is on. */
    fun saveShot(c: Context, tag: String, bmp: Bitmap?) {
        if (bmp == null || !on(c)) return
        try {
            val d = dir(c)
            d.listFiles { f -> f.name.endsWith(".jpg") }?.let { shots ->
                if (shots.size >= MAX_SHOTS) shots.sortedBy { it.lastModified() }
                    .take(shots.size - MAX_SHOTS + 1).forEach { try { it.delete() } catch (_: Throwable) {} }
            }
            val name = "shot_${System.currentTimeMillis()}_${safe(tag)}.jpg"
            FileOutputStream(File(d, name)).use { bmp.compress(Bitmap.CompressFormat.JPEG, 70, it) }
        } catch (_: Throwable) {}
    }

    private fun safe(s: String) = s.replace(Regex("[^A-Za-z0-9_-]"), "_").take(40)

    /** Total size of the bundle on disk (for the viewer's status line). */
    fun bytes(c: Context): Long = try {
        dir(c).walkTopDown().filter { it.isFile }.sumOf { it.length() }
    } catch (_: Throwable) { 0L }

    /** Zip the whole bundle (trace + screenshots) PLUS the terse AgentLog into one shareable/pullable file, so
     *  "export" is one tap. Returns the zip, or null on failure. */
    fun exportZip(c: Context): File? = try {
        val out = File(dir(c), EXPORT)
        ZipOutputStream(out.outputStream().buffered()).use { zos ->
            // The rich bundle (skip the previous export so it doesn't nest).
            dir(c).listFiles()?.forEach { f ->
                if (f.isFile && f.name != EXPORT) addToZip(zos, f, f.name)
            }
            // The terse tag log too, for a complete picture.
            AgentLog.file()?.let { if (it.exists()) addToZip(zos, it, "agent_log.txt") }
        }
        out.takeIf { it.exists() && it.length() > 0 }
    } catch (_: Throwable) { null }

    private fun addToZip(zos: ZipOutputStream, f: File, entryName: String) {
        try {
            zos.putNextEntry(ZipEntry(entryName))
            f.inputStream().use { it.copyTo(zos) }
            zos.closeEntry()
        } catch (_: Throwable) {}
    }

    /** Wipe the bundle (the viewer's Clear). */
    fun clear(c: Context) {
        try { dir(c).listFiles()?.forEach { it.delete() } } catch (_: Throwable) {}
    }
}
