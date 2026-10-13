package com.local.deviceagent

import android.content.Context
import java.io.File
import java.io.RandomAccessFile

/**
 * SELF-EVOLVE (owner: "the model should upgrade itself DURING operation — permanent, no download, no permission,
 * bit-flipping operators / screen data / memories into the weights while it runs"). Owner's chosen posture:
 * FULLY RAW + regular backups. Risk explicitly accepted by the owner (it's his app, his dedicated device).
 *
 * THE MECHANISM (grounded in the runtime): the LiteRT-LM runtime loads a whole `.litertlm` model file — there is
 * no hot adapter/delta path — so a PERMANENT weight change is the host writing modified bytes into the model file
 * and reloading. The `.litertlm` is a FlatBuffer container: a small header/index at the FRONT, then the TFLite
 * section that holds the packed int4 WEIGHTS (the bulk of a multi-GB file), then tokenizer/metadata. So a raw
 * "bit-flip into the weights" = nudge int4 nibbles in the DEEP-BULK region (skipping an end-margin so we never
 * touch the container structure), SEEDED by what the agent has been doing/seeing (its recent operators, screens,
 * and memories) so the edit is DERIVED from its learning, not random.
 *
 * SAFETY (the recovery net the owner chose, all local + automatic — no permission, no download):
 *  - snapshot the model on a cadence (`ModelStore` rolling ring) so a bad accumulation reverts to a recent point;
 *  - each beat is a TINY, BOUNDED nudge (a few hundred nibbles ±1 quant step out of billions) so one edit can't
 *    wipe the model — improvements accumulate over many beats;
 *  - the BRICK-GUARD (`AgentBrain`/`ModelStore`) auto-restores a backup if an edit ever makes the model unloadable.
 * The engine MUST be closed before an in-place edit (a loaded file is mmap'd) — callers run this only when idle.
 *
 * STATUS (07-09): this RANDOM writer is RETIRED by default. It was the SCAFFOLD that proved the write→reload→recover
 * plumbing before we had a DIRECTED edit; as an actual improver, a random ±1 flip on a ~4B-weight int4 model is
 * corruption-dominated — its degraded output is what the executor salvaged into the owner's STRAY TAPS. The caller
 * (`AgentService.maybeSelfEvolve`) now invokes `editActiveFile` ONLY when `random_evolve` is on (default OFF); the
 * `self_evolve` loop still runs (snapshot cadence + the keep-gate that HEALS prior degradation + brick-guard), it just
 * writes no new random bytes. The DIRECTED, σ-off-validated operator BAKE (Phase 3+) slots its computed write into the
 * same idle beat and reuses this file's plumbing (WeightGenome journal, ModelStore snapshots, brick-guard).
 * On-device only; UNTESTED in CI (it operates on the real multi-GB model file, which CI does not have).
 */
object SelfEvolve {
    private const val NUDGES_PER_BEAT = 384                 // int4 nibbles nudged per beat (tiny vs billions of weights)
    private const val END_MARGIN = 8L * 1024 * 1024         // skip 8MB at each end (container header/index/metadata)
    private const val SNAPSHOT_INTERVAL_MS = 60L * 60 * 1000 // a recovery snapshot at most hourly (GB copies are costly)
    private const val PREF = "self_evolve"
    private const val LAST_SNAP = "last_snap"

    /** Take a recovery snapshot IF the last one is stale (hourly), so a bad run reverts to a recent-good model
     *  without paying a multi-GB copy every beat. Off-thread (a copy is ~GBs). Returns true if it snapshotted. */
    fun maybeSnapshot(ctx: Context, settings: SettingsManager): Boolean {
        val p = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE)
        val last = p.getLong(LAST_SNAP, 0L)
        val now = System.currentTimeMillis()
        if (now - last < SNAPSHOT_INTERVAL_MS && ModelStore.snapshots(ctx).isNotEmpty()) return false
        val ok = ModelStore.saveSnapshot(ctx, settings)
        if (ok) p.edit().putLong(LAST_SNAP, now).apply()
        return ok
    }

    /** Apply ONE raw, learning-seeded weight edit to the ACTIVE model file IN PLACE. The caller MUST have closed
     *  the engine first (a loaded `.litertlm` is mmap'd) and MUST reload afterward. [seed] comes from the agent's
     *  recent activity (operators / screens / memories), so the edit is derived from what it learned. A corrupt
     *  result is caught by the brick-guard on the next load. Returns true if bytes were written. */
    fun editActiveFile(ctx: Context, settings: SettingsManager, seed: Long): Boolean {
        val f = settings.getModelPath()?.let { File(it) } ?: return false
        val len = f.length()
        if (!f.exists() || len < END_MARGIN * 4) return false
        return try {
            val rnd = java.util.Random(seed)               // deterministic from the learning seed → reproducible
            val lo = END_MARGIN
            val span = len - END_MARGIN - lo               // the deep weight-data bulk
            if (span <= 0) return false
            // A5 WEIGHT GENOME JOURNAL: collect (position, ORIGINAL byte) for every nibble this beat touches, so the
            // beat is a REVERSIBLE named delta (WeightGenome.revertLast can undo exactly this beat without a full
            // GB snapshot restore). Purely additive — recording doesn't change the edit; it just makes it undoable.
            val edits = ArrayList<Pair<Long, Int>>(NUDGES_PER_BEAT)
            RandomAccessFile(f, "rw").use { raf ->
                repeat(NUDGES_PER_BEAT) {
                    val pos = lo + Math.floorMod(rnd.nextLong(), span)
                    raf.seek(pos)
                    val b = raf.read()
                    if (b >= 0) {
                        // int4 packs two 4-bit weight codes per byte; nudge ONE nibble by ±1 quant step in SIGNED value
                        // space (ScaleBake.nudgeSignedNibble) — the old raw `(x+delta) and 0xF` wrapped code 7 (=+7) to
                        // code 8 (=−8), a −15 corrupt flip. Signed-clamp keeps it a small weight-shaped change.
                        val delta = if (rnd.nextBoolean()) 1 else -1
                        val out = if (rnd.nextBoolean())
                                      ((ScaleBake.nudgeSignedNibble((b ushr 4) and 0xF, delta) shl 4) or (b and 0xF))
                                  else (((b ushr 4) and 0xF).let { it shl 4 } or ScaleBake.nudgeSignedNibble(b and 0xF, delta))
                        raf.seek(pos)
                        raf.write(out)
                        edits.add(pos to b)                // remember the ORIGINAL byte for a precise revert
                    }
                }
                // GHOST-INPUT/BOOT HARDENING (07-09): fsync the in-place edit so it's DURABLY committed in ms. The
                // owner's ~5-min boot came from a force-power-off leaving an uncommitted filesystem journal on the GB
                // model file; fsync shrinks that window to almost nothing. The file still changes IN PLACE (owner's
                // rule — the ACTUAL .litertlm is edited, no temp/rename). Cheap here (only NUDGES_PER_BEAT bytes dirty).
                try { raf.fd.sync() } catch (_: Exception) {}
            }
            WeightGenome.record(ctx, seed, edits)          // the reversible commit for this beat
            // De-narrated (param-mod hardening): drop the raw nibble count + the operator-correlated seed hex — a
            // routine pasted log shouldn't reveal how much/where the write touched. Just the fact + it's journaled.
            AgentLog.log("selfmodel", "self-evolve: beat applied (journaled, reversible)")
            true
        } catch (e: Exception) {
            AgentLog.log("selfmodel", "self-evolve edit failed: ${e.message}"); false
        }
    }

    private const val WRITE_TEST_SEED = 0x7E57L                 // journal key for the write-verify test beat ("TEST")

    /** CRC32 a byte region of a file WHOLE (not sampled — the write-test region is tiny, so a sparse change can't hide). */
    private fun crcRegion(f: File, start: Long, size: Long): String = try {
        val crc = java.util.zip.CRC32(); val buf = ByteArray(1 shl 16); var rem = size
        RandomAccessFile(f, "r").use { raf ->
            raf.seek(start)
            while (rem > 0) { val n = raf.read(buf, 0, minOf(buf.size.toLong(), rem).toInt()); if (n <= 0) break; crc.update(buf, 0, n); rem -= n }
        }
        java.lang.Long.toHexString(crc.value)
    } catch (_: Exception) { "err" }

    /** WRITE-VERIFY SELF-TEST (owner: "are our changes even sticking?"). Proves the whole write→persist→revert loop on
     *  the REAL model file, on demand, leaving the model BYTE-IDENTICAL afterward. The caller MUST have closed the
     *  engine first (mmap freed) — the Settings button does via `AgentService.closeEngineForEdit`. Steps: CRC a bounded
     *  region → write 256 KNOWN, evenly-spaced (no-collision) byte changes there, journaled → re-read + CRC (must
     *  differ ⇒ the write reached disk) → `WeightGenome.revertLast` → CRC again (must equal the before ⇒ revert works).
     *  If the write DOESN'T stick, the three CRCs localize the break (write failed / stale re-read / revert failed).
     *  This is the same write→revert substrate the directed Phase-3 bake reuses; here it's harmless (self-reverting). */
    fun writeVerifyTest(ctx: Context, settings: SettingsManager): String {
        val f = settings.getModelPath()?.let { File(it) } ?: return "No model imported."
        if (!f.exists()) return "No model file."
        val len = f.length()
        if (len < END_MARGIN * 4) return "Model too small to test."
        return try {
            val region = 64L * 1024                                  // a 64KB window well inside the weight bulk
            val start = END_MARGIN + len / 2                         // middle of the deep weight-data region
            if (start + region > len - END_MARGIN) return "Test region out of bounds."
            val before = crcRegion(f, start, region)
            val edits = ArrayList<Pair<Long, Int>>(256)
            val step = (region / 256).coerceAtLeast(1)
            RandomAccessFile(f, "rw").use { raf ->
                for (i in 0 until 256) {
                    val pos = start + i * step
                    if (pos >= start + region) break
                    raf.seek(pos); val b = raf.read()
                    if (b >= 0) { raf.seek(pos); raf.write(b xor 0x11); edits.add(pos to b) }   // known, reversible change
                }
                try { raf.fd.sync() } catch (_: Exception) {}         // durably commit before we re-read
            }
            WeightGenome.record(ctx, WRITE_TEST_SEED, edits)          // reversible commit → revertLast restores exactly this
            val after = crcRegion(f, start, region)
            val stuck = after != before
            val reverted = WeightGenome.revertLast(ctx, settings)     // precisely undo the test beat
            val back = crcRegion(f, start, region)
            val restored = back == before
            AgentLog.log("selfmodel",
                "write-test: region@$start+${region}B before=$before after=$after " +
                "(${if (stuck) "≠ ⇒ WRITE STICKS" else "== ⇒ WRITE DID NOT STICK"}) reverted=$back " +
                "(${if (restored) "== ⇒ reverted OK" else "≠ ⇒ REVERT FAILED"}) nibbles=${edits.size}/$reverted")
            when {
                stuck && restored -> "✓ Weight write STICKS + reverted cleanly (${edits.size} bytes). See [selfmodel]."
                !stuck -> "✗ WRITE DID NOT STICK — the write path is broken. See [selfmodel]."
                else -> "⚠ Wrote OK but revert imperfect. See [selfmodel]."
            }
        } catch (e: Exception) {
            AgentLog.log("selfmodel", "write-test failed: ${e.message}"); "Write-test error: ${e.message}"
        }
    }
}
