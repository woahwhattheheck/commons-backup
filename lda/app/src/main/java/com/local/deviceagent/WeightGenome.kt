package com.local.deviceagent

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.RandomAccessFile

/**
 * A5 — THE WEIGHT GENOME JOURNAL (research 9/9: "git-for-weights, composable per-capability deltas").
 *
 * Every weight beat (a self-evolve nudge OR a directed-bake proposal) is a set of int4 edits. This journal makes each
 * beat a NAMED, REVERSIBLE DELTA: it records the exact (position, ORIGINAL byte) for every nibble the beat touched,
 * keyed to the LEARNING SEED that produced it — so `revertLast()` undoes precisely one beat by writing the original
 * bytes back, without disturbing anything else. This is the recovery substrate the σ-OFF keep-gate (INV-86) stands on.
 *
 * ★ STORAGE: ONE FILE PER BEAT (07-11 fix). The journal used to be a single `.jsonl` with one line per beat, and every
 * op did `readLines()` + `joinToString()` over the WHOLE file. That was fine for tiny self-evolve beats (~384 nibbles)
 * but the DIRECTED BAKE records beats of up to `BAKE_BYTES_CAP`=262,144 edits each — ~6 MB sealed per beat, ~100 MB for
 * a full window. Reading + rebuilding that on a process already near its memory ceiling (model loaded) threw
 * `OutOfMemoryError` — an `Error`, NOT caught by `catch(Exception)` — and CRASHED the app (`revertLast` from the
 * write-test button). Per-beat files fix it structurally: each beat is `genome/<index>.beat` (its sealed JSON), so
 * `revertLast` opens ONLY the newest file and `record` writes ONLY a new file — every op is O(one beat), never the
 * whole journal. A future OOM/Error is also now caught (`Throwable`) so a journal op can never crash the app.
 *
 * PARAM-MOD HARDENING: each beat file is AES-GCM-SEALED under a device-bound Keystore key (`KeystoreSeal`) — a leaked
 * file is opaque, decryptable only on THIS device. On-device only (it reverts bytes in the real GB model file).
 */
object WeightGenome {
    private const val DIR = "genome"                        // per-beat files live here
    private const val LEGACY = "weight_genome.jsonl"        // the old single-file journal (deleted on first use)
    private const val EXT = ".beat"
    private const val MAX_BEATS = 40                        // rolling window of undoable beats; oldest trimmed past this

    private fun dir(c: Context) = File(c.filesDir, DIR)

    /** Delete the legacy single-file journal once (its bake-scale lines are what OOM'd). Snapshots + baseline remain the
     *  recovery net for anything it held. Idempotent + guarded. */
    private fun migrateLegacy(c: Context) {
        try { File(c.filesDir, LEGACY).takeIf { it.exists() }?.delete() } catch (_: Throwable) {}
    }

    /** Beat files newest-LAST (sorted by numeric index). Empty on any error. */
    private fun beatFiles(c: Context): List<File> = try {
        dir(c).listFiles { f -> f.isFile && f.name.endsWith(EXT) }
            ?.sortedBy { it.name.removeSuffix(EXT).toLongOrNull() ?: 0L } ?: emptyList()
    } catch (_: Throwable) { emptyList() }

    /** Apply one sealed beat's edits to the model file (RandomAccessFile already open). Returns nibbles reverted. */
    private fun applyBeat(sealed: String, model: File, raf: RandomAccessFile): Int {
        val json = KeystoreSeal.open(sealed) ?: return 0
        val edits = JSONObject(json).optJSONArray("e") ?: return 0
        var reverted = 0
        val len = model.length()
        for (i in 0 until edits.length()) {
            val pair = edits.optJSONArray(i) ?: continue
            val pos = pair.optLong(0, -1L); val orig = pair.optInt(1, -1)
            if (pos in 0 until len && orig in 0..255) { raf.seek(pos); raf.write(orig); reverted++ }
        }
        return reverted
    }

    /** Record one beat: the edits are (filePosition, ORIGINAL byte before the nudge), written as ONE sealed file. Best-
     *  effort + fully guarded — a journal write must never disturb the weight beat. Trims the oldest files past the window. */
    @Synchronized
    fun record(c: Context, seed: Long, edits: List<Pair<Long, Int>>) {
        if (edits.isEmpty()) return
        try {
            migrateLegacy(c)
            val arr = JSONArray()
            edits.forEach { arr.put(JSONArray().put(it.first).put(it.second)) }
            val line = JSONObject().put("seed", seed).put("n", edits.size).put("e", arr).toString()
            // DATA-AT-REST SEAL: the journal is the literal edit MAP, so it's AES-GCM-sealed under a device-bound key.
            // Best-effort: if the seal can't be produced, skip the write (baseline backup + brick-guard remain the net).
            val sealed = KeystoreSeal.seal(line) ?: return
            val d = dir(c); d.mkdirs()
            val next = (beatFiles(c).lastOrNull()?.name?.removeSuffix(EXT)?.toLongOrNull() ?: 0L) + 1
            File(d, "%012d%s".format(next, EXT)).writeText(sealed)
            // Trim: delete the oldest beat files past the window (per-file, so no whole-journal read).
            val files = beatFiles(c)
            if (files.size > MAX_BEATS) files.take(files.size - MAX_BEATS).forEach { try { it.delete() } catch (_: Throwable) {} }
        } catch (_: Throwable) {}   // Throwable (not Exception): an OOM here must never crash the app
    }

    /** Precisely UNDO the most recent recorded beat: write every original byte back at its position, then drop the file.
     *  The caller MUST have closed the engine first (the model file is mmap'd when loaded) and reload after. Returns the
     *  count reverted (0 if nothing / on error). Opens ONLY the newest beat file — O(one beat), never the whole journal. */
    @Synchronized
    fun revertLast(c: Context, settings: SettingsManager): Int {
        val model = settings.getModelPath()?.let { File(it) } ?: return 0
        if (!model.exists()) return 0
        return try {
            migrateLegacy(c)
            val newest = beatFiles(c).lastOrNull() ?: return 0
            val sealed = newest.readText()
            var reverted = 0
            RandomAccessFile(model, "rw").use { raf -> reverted = applyBeat(sealed, model, raf) }
            try { newest.delete() } catch (_: Throwable) {}
            AgentLog.log("selfmodel", "genome: reverted last beat")   // de-narrated: no nibble count / seed hex
            reverted
        } catch (e: Throwable) { AgentLog.log("selfmodel", "genome revert failed: ${e.message}"); 0 }
    }

    /** Precisely UNDO the last [n] recorded beats in ONE pass (the keep-gate's window rollback). Reverts NEWEST-first so
     *  overlapping positions restore correctly (a later beat that saw an earlier beat's output as its "original" must be
     *  undone before that earlier beat). Same engine-closed contract as [revertLast]. Opens one beat file at a time. */
    @Synchronized
    fun revertBeats(c: Context, settings: SettingsManager, n: Int): Int {
        if (n <= 0) return 0
        val model = settings.getModelPath()?.let { File(it) } ?: return 0
        if (!model.exists()) return 0
        return try {
            migrateLegacy(c)
            val files = beatFiles(c)
            if (files.isEmpty()) return 0
            val window = files.takeLast(minOf(n, files.size)).reversed()   // NEWEST-first
            var reverted = 0
            RandomAccessFile(model, "rw").use { raf ->
                for (bf in window) {
                    reverted += try { applyBeat(bf.readText(), model, raf) } catch (_: Throwable) { 0 }
                    try { bf.delete() } catch (_: Throwable) {}
                }
            }
            AgentLog.log("selfmodel", "genome: reverted ${window.size} beat(s) — keep-gate window rollback")
            reverted
        } catch (e: Throwable) { AgentLog.log("selfmodel", "genome revertBeats failed: ${e.message}"); 0 }
    }

    /** How many undoable beats the journal currently holds (owner telemetry + the keep-gate's batch bound). */
    @Synchronized
    fun beatCount(c: Context): Int = try { beatFiles(c).size } catch (_: Throwable) { 0 }

    @Synchronized
    fun clear(c: Context) {
        try { migrateLegacy(c); dir(c).listFiles()?.forEach { it.delete() }; dir(c).delete() } catch (_: Throwable) {}
    }
}
