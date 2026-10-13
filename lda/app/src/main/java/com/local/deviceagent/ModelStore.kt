package com.local.deviceagent

import android.content.Context
import java.io.File

/**
 * Central model-FILE management for the owner-gated self-update loop (INV-45 / INV-46).
 *
 * The on-device model is a REPLACEABLE artifact on disk (`SettingsManager.getModelPath()` →
 * `filesDir/model/<name>`). This keeps a pristine **baseline** copy in a SEPARATE dir so any
 * self-installed change is instantly reversible — the owner's "just swap it out; recoverability
 * bounds the QUALITY risk" — and a **candidate** slot for a model being probed before the owner
 * approves installing it (Stage 2).
 *
 * Everything here is deterministic host-side file I/O. It is NEVER an agent action and is never
 * reachable from a model decision or on-screen data (the INV-45 exploit gate — the whole point is
 * that the AGENT-as-host can persist a change the MODEL-as-forward-pass cannot). Reversibility is
 * the invariant: the baseline dir is separate from the active `model` dir, so importing/swapping the
 * active model never wipes the rollback target.
 *
 * Copies are large (~GBs) — callers MUST run these off the main thread.
 */
object ModelStore {

    private fun baselineDir(ctx: Context) = File(ctx.filesDir, "model_baseline").apply { mkdirs() }
    private fun candidateDir(ctx: Context) = File(ctx.filesDir, "model_candidate").apply { mkdirs() }
    private fun snapshotDir(ctx: Context) = File(ctx.filesDir, "model_snapshots").apply { mkdirs() }
    private const val MAX_SNAPSHOTS = 3   // rolling backups of the SELF-EVOLVED model (each is ~GBs)

    /** The stashed pristine baseline model file, or null if none stashed yet. */
    fun baselineFile(ctx: Context): File? =
        baselineDir(ctx).listFiles()?.firstOrNull { it.isFile && it.length() > 0 }

    fun hasBaseline(ctx: Context): Boolean = baselineFile(ctx) != null

    /** An imported candidate model awaiting probe/approval, or null (Stage 2). */
    fun candidateFile(ctx: Context): File? =
        candidateDir(ctx).listFiles()?.firstOrNull { it.isFile && it.length() > 0 }

    /**
     * Copy the CURRENT active model into the baseline slot iff one isn't stashed yet (idempotent).
     * Called when the owner enables self-model-edit, and defensively before any swap, so a rollback
     * always has a pristine target. Returns true if a baseline exists afterward.
     */
    fun ensureBaseline(ctx: Context, settings: SettingsManager): Boolean {
        if (hasBaseline(ctx)) return true
        val active = settings.getModelPath()?.let { File(it) } ?: return false
        if (!active.exists() || active.length() == 0L) return false
        return try {
            val dest = File(baselineDir(ctx), active.name)
            active.copyTo(dest, overwrite = true)
            AgentLog.log("selfmodel", "stashed pristine baseline (${dest.length() / (1 shl 20)}MB)")
            true
        } catch (e: Exception) {
            AgentLog.log("selfmodel", "baseline stash failed: ${e.message}"); false
        }
    }

    /**
     * Set the baseline to a freshly owner-blessed model (a deliberate re-import while self-model-edit
     * is on). Overwrites the prior baseline: the rollback target is "the last model the OWNER installed",
     * which only diverges from the active model once a self-installed candidate replaces it.
     */
    fun refreshBaseline(ctx: Context, modelFile: File) {
        if (!modelFile.exists() || modelFile.length() == 0L) return
        try {
            val dir = baselineDir(ctx)
            dir.listFiles()?.forEach { it.delete() }
            modelFile.copyTo(File(dir, modelFile.name), overwrite = true)
            AgentLog.log("selfmodel", "baseline refreshed to owner-installed model")
        } catch (e: Exception) {
            AgentLog.log("selfmodel", "baseline refresh failed: ${e.message}")
        }
    }

    /**
     * Make [src] the ACTIVE model: replace the `model` dir's contents with a copy of [src] and point
     * `getModelPath()` at it. The single primitive behind restore-baseline and candidate-install (a whole
     * model is a monolithic .litertlm — the only install the runtime supports is a whole-file swap; there
     * is no runtime adapter/delta path). The caller MUST reload the engine afterward
     * (`AgentService.instance?.reloadModel()`) — the brain latches its engine and only re-reads the path
     * after a close. Returns true on success.
     */
    private fun activate(ctx: Context, settings: SettingsManager, src: File): Boolean {
        if (!src.exists() || src.length() == 0L) return false
        return try {
            val dir = File(ctx.filesDir, "model").apply { mkdirs() }
            dir.listFiles()?.forEach { it.delete() }
            val dest = File(dir, src.name)
            src.copyTo(dest, overwrite = true)
            settings.setModelPath(dest.absolutePath)
            true
        } catch (e: Exception) {
            AgentLog.log("selfmodel", "activate failed: ${e.message}"); false
        }
    }

    /**
     * Restore the active model from the pristine baseline (the owner's rollback — instant + local, no
     * re-download). Returns true on success; caller reloads the engine.
     */
    fun restoreBaseline(ctx: Context, settings: SettingsManager): Boolean {
        val base = baselineFile(ctx) ?: return false
        val ok = activate(ctx, settings, base)
        if (ok) AgentLog.log("selfmodel", "restored pristine baseline model")
        return ok
    }

    /**
     * Install the imported CANDIDATE as the active model (Stage 2). Used both to PROBE a candidate
     * (temporarily) and to KEEP an owner-APPROVED one. `ensureBaseline` must have run first so the swap
     * is reversible. Returns true on success; caller reloads the engine.
     */
    fun activateCandidate(ctx: Context, settings: SettingsManager): Boolean {
        val cand = candidateFile(ctx) ?: return false
        val ok = activate(ctx, settings, cand)
        if (ok) AgentLog.log("selfmodel", "activated candidate model for probe/install")
        return ok
    }

    /** Copy a picked candidate model (from a SAF stream) into the candidate slot (owner import, Stage 2).
     *  Off-thread — the file is ~GBs. */
    fun importCandidate(ctx: Context, input: java.io.InputStream, name: String): Boolean {
        return try {
            val dir = candidateDir(ctx)
            dir.listFiles()?.forEach { it.delete() }
            java.io.FileOutputStream(File(dir, name.ifBlank { "candidate.litertlm" })).use { out ->
                input.copyTo(out, 1 shl 20)
            }
            true
        } catch (e: Exception) {
            AgentLog.log("selfmodel", "candidate import failed: ${e.message}"); false
        }
    }

    /** Discard a candidate after a reject / after it is kept (frees the ~GBs). */
    fun discardCandidate(ctx: Context) {
        try { candidateDir(ctx).listFiles()?.forEach { it.delete() } } catch (_: Exception) {}
    }

    // ── SELF-EVOLVE: rolling backups + brick-guard (owner's "regular backups" recovery net) ─────────────────────
    // The self-evolve loop writes into the model file. Before each edit we snapshot the current-good model into a
    // rolling ring (last MAX_SNAPSHOTS), so a bad/poisoned/degraded edit can revert to a recent snapshot; the
    // pristine baseline remains the deepest fallback. Copies are ~GBs — call OFF the main thread.

    /** Snapshots newest-first. */
    fun snapshots(ctx: Context): List<File> =
        try { snapshotDir(ctx).listFiles()?.filter { it.isFile && it.length() > 0 && !it.name.endsWith(".tmp") }?.sortedByDescending { it.lastModified() } ?: emptyList() }
        catch (_: Exception) { emptyList() }

    /** Copy the CURRENT active model into the rolling snapshot ring (keeps the newest MAX_SNAPSHOTS). Call BEFORE
     *  a self-evolve edit so there is always a recent-good backup to revert to. Timestamped name (millis) so the
     *  ring orders by recency. Returns true if a snapshot was written. */
    fun saveSnapshot(ctx: Context, settings: SettingsManager): Boolean {
        val active = settings.getModelPath()?.let { File(it) } ?: return false
        if (!active.exists() || active.length() == 0L) return false
        return try {
            val dir = snapshotDir(ctx)
            val dest = File(dir, "${System.currentTimeMillis()}_${active.name}")
            // BOOT HARDENING (07-09): write the GB backup to a .tmp, fsync, then atomic-rename. A force-power-off
            // mid-copy leaves only a discardable .tmp (never a half-written "valid" snapshot the brick-guard could
            // restore), and the fsync shrinks the uncommitted-journal window that caused the owner's ~5-min boot.
            // This is a BACKUP file (temp/rename OK here) — the ACTUAL model is always edited in place elsewhere.
            val tmp = File(dir, dest.name + ".tmp")
            active.copyTo(tmp, overwrite = true)
            try { java.io.FileOutputStream(tmp, true).use { it.flush(); it.fd.sync() } } catch (_: Exception) {}
            if (!tmp.renameTo(dest)) { tmp.delete(); return false }
            // Prune the ring to the newest MAX_SNAPSHOTS (a stale snapshot is ~GBs of dead storage) + any stale .tmp.
            dir.listFiles()?.filter { it.name.endsWith(".tmp") }?.forEach { try { it.delete() } catch (_: Exception) {} }
            dir.listFiles()?.filter { it.isFile && !it.name.endsWith(".tmp") }?.sortedByDescending { it.lastModified() }?.drop(MAX_SNAPSHOTS)?.forEach { try { it.delete() } catch (_: Exception) {} }
            AgentLog.log("selfmodel", "snapshot saved (${dest.length() / (1 shl 20)}MB, ring=${snapshots(ctx).size})")
            true
        } catch (e: Exception) {
            AgentLog.log("selfmodel", "snapshot failed: ${e.message}"); false
        }
    }

    /** Revert the active model to the most recent snapshot (the self-evolve owner-triggered revert). Returns true
     *  on success; caller reloads the engine. */
    fun restoreLatestSnapshot(ctx: Context, settings: SettingsManager): Boolean {
        val snap = snapshots(ctx).firstOrNull() ?: return false
        val ok = activate(ctx, settings, snap)
        if (ok) AgentLog.log("selfmodel", "reverted to snapshot ${snap.name}")
        return ok
    }

    /** BRICK-GUARD: after a self-evolve edit the engine failed to load, so the model file is broken. Restore the
     *  best recover-to target — the most recent snapshot, else the pristine baseline — so the device is never
     *  bricked by a self-edit. Returns true if something was restored (caller reloads). The one automatic floor
     *  kept under the owner's "fully raw" posture: it fires ONLY when the model won't even run. */
    fun recoverFromBrokenModel(ctx: Context, settings: SettingsManager): Boolean {
        if (restoreLatestSnapshot(ctx, settings)) { AgentLog.log("selfmodel", "BRICK-GUARD: restored latest snapshot after a load failure"); return true }
        if (restoreBaseline(ctx, settings)) { AgentLog.log("selfmodel", "BRICK-GUARD: restored pristine baseline after a load failure"); return true }
        return false
    }

    /** A cheap fingerprint of the active model file (name:length) — identifies WHICH model a distilled-
     *  operator flag (INV-46 weak-trigger) applies to, so the flag auto-invalidates on any model swap. */
    fun activeFingerprint(ctx: Context, settings: SettingsManager): String {
        val f = settings.getModelPath()?.let { File(it) } ?: return ""
        return if (f.exists()) "${f.name}:${f.length()}" else ""
    }
}
