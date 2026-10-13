package com.local.deviceagent

import android.content.Context
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Debug log. Keeps a large in-memory ring buffer for the on-screen viewer AND appends
 * every line to a file on disk so the full history survives (the owner wants to keep as
 * much of this rich data as possible and export it). The file is shareable from the
 * Debug Log screen. A soft size cap keeps it from filling storage outright.
 */
object AgentLog {
    private const val MAX_LINES = 6000
    private const val MAX_FILE_BYTES = 24L * 1024 * 1024 // ~24 MB, then rotate once
    // A distinctive boundary written when a new task starts, so the viewer can chop the
    // stream up by task. Kept in the [task] tag so it survives reload/search.
    const val TASK_MARK = "═══ TASK ═══"
    private val lines = ArrayDeque<String>()
    private val fmt = SimpleDateFormat("MM-dd HH:mm:ss", Locale.US)
    @Volatile private var logFile: File? = null

    /** Point the log at a persistent file AND reload its tail into memory, so the on-screen
     *  viewer still shows history after a restart/crash (previously the file survived but the
     *  in-memory buffer the viewer reads started empty, so logs "disappeared").
     *
     *  On every app UPDATE the previous build's log is ARCHIVED (moved aside, kept under
     *  log_archive/) and a fresh log is started - so old-build behavior never pollutes the agent's
     *  training/context (`tail()` is fed to the model), while the valuable history is preserved. */
    fun init(context: Context) {
        try {
            val f = File(context.filesDir, "agent_log.txt")
            logFile = f
            val meta = context.getSharedPreferences("agent_log_meta", Context.MODE_PRIVATE)
            val updated = try {
                context.packageManager.getPackageInfo(context.packageName, 0).lastUpdateTime
            } catch (_: Exception) { 0L }
            val seen = meta.getLong("last_update", 0L)
            // An update happened (or this is the first run of the build that added archiving) AND
            // there's an old log to keep -> archive it and start fresh.
            if (updated != seen && f.exists() && f.length() > 0) {
                archive(context, f)
                f.writeText("")
                synchronized(this) { lines.clear() }
                meta.edit().putLong("last_update", updated).apply()
                log("log", "new build detected - archived the previous log, starting fresh")
                return
            }
            meta.edit().putLong("last_update", updated).apply()
            if (f.exists()) {
                val prior = f.readLines()
                val tail = if (prior.size > MAX_LINES) prior.subList(prior.size - MAX_LINES, prior.size) else prior
                synchronized(this) {
                    lines.clear()
                    tail.forEach { if (it.isNotEmpty()) lines.addLast(it) }
                }
            }
        } catch (_: Exception) {}
    }

    /** Copy the current log into log_archive/ (timestamped), keeping only the most recent few. */
    private fun archive(context: Context, f: File) {
        try {
            val dir = File(context.filesDir, "log_archive"); dir.mkdirs()
            val stamp = SimpleDateFormat("yyyyMMdd-HHmmss", Locale.US).format(Date())
            f.copyTo(File(dir, "log_$stamp.txt"), overwrite = true)
            dir.listFiles()?.sortedByDescending { it.lastModified() }?.drop(8)?.forEach { it.delete() }
        } catch (_: Exception) {}
    }

    /** Archived past-build logs (newest first), for the viewer / export. */
    fun archives(context: Context): List<File> =
        try { File(context.filesDir, "log_archive").listFiles()?.sortedByDescending { it.lastModified() } ?: emptyList() }
        catch (_: Exception) { emptyList() }

    /** Lines from ALL archived (previous-build) logs, OLDEST archive first, each preceded by a task
     *  boundary so the viewer shows where a past build begins. The current build's log excludes these
     *  (so old behavior never pollutes the model's context), but the owner asked to keep this valuable
     *  data viewable on demand - this is what the "Old builds" toggle in the log viewer loads. */
    fun oldBuildLines(context: Context): List<String> {
        val out = ArrayList<String>()
        archives(context).asReversed().forEach { f ->   // oldest first
            out.add("${fmt.format(Date(f.lastModified()))}  [task] $TASK_MARK OLD BUILD — ${f.name}")
            try { f.readLines().forEach { if (it.isNotEmpty()) out.add(it) } } catch (_: Exception) {}
        }
        return out
    }

    /** Write a clear task boundary so the viewer/owner can read the log chopped up by task. */
    fun task(label: String) = log("task", "$TASK_MARK ${label.ifBlank { "(no objective)" }}")

    @Synchronized
    fun log(tag: String, msg: String) {
        val line = "${fmt.format(Date())}  [$tag] $msg"
        while (lines.size >= MAX_LINES) lines.removeFirst()
        lines.addLast(line)
        logFile?.let { f ->
            try {
                if (f.length() > MAX_FILE_BYTES) {
                    val old = File(f.parentFile, "agent_log.1.txt")
                    old.delete(); f.renameTo(old)
                }
                f.appendText(line + "\n")
            } catch (_: Exception) {}
        }
    }

    @Synchronized
    fun dump(): String = if (lines.isEmpty()) "(no activity yet)" else lines.joinToString("\n")

    /** A stable copy of the buffered lines for the viewer to filter/group (search, per-task). */
    @Synchronized
    fun snapshot(): List<String> = lines.toList()

    /** Distinct tags currently in the buffer (e.g. brain, act, screen, plan, context), sorted -
     *  so the viewer can offer a tag filter. */
    @Synchronized
    fun tags(): List<String> {
        val set = sortedSetOf<String>()
        for (l in lines) {
            val a = l.indexOf('['); val b = l.indexOf(']')
            if (a in 0 until b) set.add(l.substring(a + 1, b))
        }
        return set.toList()
    }

    /** Size of the on-disk log in bytes (0 if none) - shown in the viewer's status line. */
    fun fileBytes(): Long = logFile?.takeIf { it.exists() }?.length() ?: 0L

    /** Last [n] log lines (for the agent's self-report). */
    @Synchronized
    fun tail(n: Int): String =
        if (lines.isEmpty()) "(no activity yet)" else lines.toList().takeLast(n).joinToString("\n")

    /** The persistent log file (for sharing/export), or null if not initialized. */
    fun file(): File? = logFile?.takeIf { it.exists() }

    @Synchronized
    fun clear() {
        lines.clear()
        try { logFile?.writeText("") } catch (_: Exception) {}
    }
}
