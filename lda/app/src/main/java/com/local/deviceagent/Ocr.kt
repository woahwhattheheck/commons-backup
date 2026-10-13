package com.local.deviceagent

import android.graphics.Bitmap
import com.google.android.gms.tasks.Tasks
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import java.util.concurrent.TimeUnit

/**
 * On-device OCR (ML Kit, BUNDLED) used as a PERCEPTION fallback on accessibility-blind screens -
 * Flutter apps, games, some webviews and custom-rendered UIs that expose little or no node tree, where
 * the agent could see a screenshot but the small model struggles to read the text in it. OCR makes that
 * text explicit + locatable so the agent can act on it. It only makes the screen READABLE; the agent
 * still decides (this is the deterministic perception layer, never a decision).
 *
 * Runs 100% on-device: the model ships in the APK, there is NO network call and nothing leaves the
 * phone - consistent with the no-exfiltration rule. Every path is exception-guarded and returns an
 * EMPTY result on any failure/timeout, so perception silently degrades to the existing behavior (a
 * labeled grid the agent taps) rather than ever breaking the loop.
 */
object Ocr {

    /** One recognized line: its text and the CENTER of its box in source-image pixels. */
    data class Word(val text: String, val cx: Int, val cy: Int)

    private val recognizer by lazy { TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS) }

    /** Blocking recognition with a hard timeout. MUST be called OFF the main thread (it's invoked from
     *  the brain's Dispatchers.IO decision coroutine). Returns the recognized lines, capped, or an empty
     *  list on ANY error/timeout. */
    fun recognize(bmp: Bitmap): List<Word> = try {
        val text = Tasks.await(recognizer.process(InputImage.fromBitmap(bmp, 0)), 4, TimeUnit.SECONDS)
        val out = ArrayList<Word>()
        loop@ for (block in text.textBlocks) for (line in block.lines) {
            val b = line.boundingBox ?: continue
            val t = line.text.trim()
            if (t.isNotEmpty()) out.add(Word(t.take(48), b.centerX(), b.centerY()))
            if (out.size >= 40) break@loop
        }
        out
    } catch (_: Throwable) { emptyList() }

    /** A ready-to-inject perception block: the on-screen text mapped to tap_xy fractions (resolution-
     *  independent, so they line up whatever size the image was). Empty string when OCR found nothing,
     *  so the caller can append it unconditionally. The agent acts on a label by tap_xy at its fraction -
     *  no new action verb needed, so this composes with the existing grid/pixel tapping. */
    fun blockFor(bmp: Bitmap): String {
        val words = recognize(bmp)
        if (words.isEmpty()) return ""
        val w = bmp.width.toFloat().coerceAtLeast(1f)
        val h = bmp.height.toFloat().coerceAtLeast(1f)
        val items = words.take(30).joinToString("  ·  ") {
            "\"${it.text}\"@${"%.2f".format(it.cx / w)},${"%.2f".format(it.cy / h)}"
        }
        return "\nREADABLE TEXT (OCR - this screen exposes few/no tappable elements; to act on a label, " +
            "tap_xy at its fraction): $items"
    }

    /** ON-DEMAND READ: the agent asked to read THIS screen's text (a value not in the a11y tree - inside
     *  a web page / canvas). BOUNDED on both ends so a "look" can never overload the agent or Android:
     *  the bitmap is downscaled to cap OCR memory/time (on top of recognize()'s 4s timeout + 40-line cap),
     *  and the returned text is hard-capped to ~500 chars so it can't bloat the prompt into an overflow.
     *  MUST be called off the main thread. */
    fun readScreen(bmp: Bitmap): String {
        val maxDim = maxOf(bmp.width, bmp.height)
        val small = if (maxDim > 1500) {
            val s = 1500f / maxDim
            try { Bitmap.createScaledBitmap(bmp, (bmp.width * s).toInt(), (bmp.height * s).toInt(), true) }
            catch (_: Throwable) { bmp }
        } else bmp
        val words = recognize(small)
        if (words.isEmpty()) return "(no readable text found on this screen)"
        val sb = StringBuilder()
        for (wd in words) {
            if (sb.length >= 500) { sb.append(" …"); break }
            if (sb.isNotEmpty()) sb.append(" · ")
            sb.append(wd.text)
        }
        return sb.toString()
    }

    private fun isCloseLabel(t: String): Boolean {
        val s = t.trim().lowercase()
        if (s.length > 14) return false
        return s == "x" || s == "✕" || s == "✖" || s == "×" || s == "⨯" ||
            Regex("\\b(close|dismiss|skip|no thanks|not now|maybe later)\\b").containsMatchIn(s)
    }

    /** OVERLAY-CLOSE LOCALIZATION: find dismiss-style controls (X / Close / Skip / Not now …) by OCR and
     *  return them as CANDIDATE tap_xy targets - for the case a pop-up/ad with NO accessibility node is
     *  blocking the task. This is the gap the a11y tree can't fill. It NEVER taps; the caller surfaces it
     *  only when the agent is stuck, and the agent itself decides whether a pop-up is actually blocking.
     *  Empty string when nothing close-like is found. MUST be called off the main thread. */
    fun closeCandidates(bmp: Bitmap): String {
        val hits = recognize(bmp).filter { isCloseLabel(it.text) }
        if (hits.isEmpty()) return ""
        val w = bmp.width.toFloat().coerceAtLeast(1f)
        val h = bmp.height.toFloat().coerceAtLeast(1f)
        val items = hits.take(4).joinToString("  ·  ") {
            "\"${it.text}\"@${"%.2f".format(it.cx / w)},${"%.2f".format(it.cy / h)}"
        }
        return "\nIF a pop-up / ad is BLOCKING the task (and ONLY then), a dismiss control looks to be at: " +
            "$items - tap_xy it to close. If nothing is actually blocking you, IGNORE this and continue your task."
    }
}
