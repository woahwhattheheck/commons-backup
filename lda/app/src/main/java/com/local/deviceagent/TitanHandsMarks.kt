package com.local.deviceagent

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import java.io.ByteArrayOutputStream
import java.security.MessageDigest

/**
 * TITAN Set-of-Marks renderer and same-generation binder.
 *
 * This is not a second executor. Perception still comes from
 * [ActionAccessibilityService.captureScreenshot] plus [ActionAccessibilityService.currentMarks].
 * Numbering uses [GridSpec] plus the real `[N]` ids in [ScreenMarks.ids].
 *
 * [AgentBrain.toJpegBytes] delegates marks/grid/downscale to [overlay]. drawLastTap stays on
 * AgentBrain: that marker is on-device loop state, not part of an off-device capture.
 */
object TitanHandsMarks {
    const val DEFAULT_MAX_PX = 640
    const val DEFAULT_JPEG_QUALITY = 60
    const val JPEG_MIME = "image/jpeg"
    const val JPEG_FORMAT = "jpeg"
    const val JPEG_SUFFIX = ".jpg"
    const val GENERATION_MISMATCH_REASON = "SCREEN_GENERATION_MISMATCH"

    fun jpeg(
        bmp: Bitmap,
        marks: ScreenMarks,
        maxPx: Int = DEFAULT_MAX_PX,
        quality: Int = DEFAULT_JPEG_QUALITY,
    ): ByteArray {
        val ready = overlay(bmp, marks, maxPx)
        val out = ByteArrayOutputStream()
        ready.compress(Bitmap.CompressFormat.JPEG, quality, out)
        if (ready !== bmp) try { ready.recycle() } catch (_: Exception) {}
        return out.toByteArray()
    }

    fun overlay(bmp: Bitmap, marks: ScreenMarks?, maxPx: Int = DEFAULT_MAX_PX): Bitmap {
        val small = downscale(bmp, maxPx)
        val hasMarks = marks != null && marks.boxes.isNotEmpty()
        val gridded = drawGrid(small, faint = hasMarks)
        val ready = if (hasMarks) drawMarks(gridded, marks!!) else gridded
        if (small !== gridded && small !== ready && small !== bmp) try { small.recycle() } catch (_: Exception) {}
        if (gridded !== ready && gridded !== bmp) try { gridded.recycle() } catch (_: Exception) {}
        return ready
    }

    fun generationToken(snapshot: String, marks: ScreenMarks): String =
        generationToken(
            snapshot,
            marks.ids,
            marks.boxes.map { intArrayOf(it.left, it.top, it.right, it.bottom) },
            marks.screenW,
            marks.screenH,
        )

    fun generationToken(
        snapshot: String,
        markIds: List<Int>,
        boxCells: List<IntArray>,
        screenW: Int,
        screenH: Int,
    ): String {
        val material = buildString {
            append("som-generation-v1\n")
            append(snapshot)
            append('\n')
            append(markIds.joinToString(","))
            append('\n')
            append(screenW)
            append('x')
            append(screenH)
            append('\n')
            for (box in boxCells) {
                append(box.joinToString(","))
                append(';')
            }
        }
        val digest = MessageDigest.getInstance("SHA-256").digest(material.toByteArray(Charsets.UTF_8))
        return digest.joinToString("") { b -> "%02x".format(b) }
    }

    fun sameGenerationOrNull(before: String, after: String): String? {
        if (before.isEmpty() || after.isEmpty() || before != after) return null
        return before
    }

    private fun drawMarks(src: Bitmap, marks: ScreenMarks): Bitmap {
        if (marks.screenW <= 0 || marks.screenH <= 0) return src
        val bmp = src.copy(Bitmap.Config.ARGB_8888, true) ?: return src
        val c = Canvas(bmp)
        val sx = bmp.width.toFloat() / marks.screenW
        val sy = bmp.height.toFloat() / marks.screenH
        val ts = maxOf(11f, bmp.height / 42f)
        val label = Paint().apply {
            color = Color.WHITE; textSize = ts; isFakeBoldText = true; isAntiAlias = true
        }
        val badge = Paint().apply { color = 0xF01E88E5.toInt(); isAntiAlias = true }
        val outline = Paint().apply {
            color = 0x99FFC107.toInt(); style = Paint.Style.STROKE
            strokeWidth = maxOf(1.5f, bmp.width / 320f); isAntiAlias = true
        }
        val placed = ArrayList<android.graphics.RectF>()
        val order = marks.boxes.indices.sortedBy { marks.boxes[it].width().toLong() * marks.boxes[it].height() }
        for (i in order) {
            val r = marks.boxes[i]
            val left = (r.left * sx).coerceIn(0f, bmp.width.toFloat())
            val top = (r.top * sy).coerceIn(0f, bmp.height.toFloat())
            val right = (r.right * sx).coerceIn(0f, bmp.width.toFloat())
            val bottom = (r.bottom * sy).coerceIn(0f, bmp.height.toFloat())
            if (right - left < 1f || bottom - top < 1f) continue
            c.drawRect(left, top, right, bottom, outline)
            val s = (marks.ids.getOrNull(i) ?: i).toString()
            val tw = label.measureText(s)
            val bw = tw + ts * 0.6f; val bh = ts * 1.25f
            val big = (right - left) > bw * 2f && (bottom - top) > bh * 2f
            val anchors = if (big)
                listOf((left + right) / 2f - bw / 2f to (top + bottom) / 2f - bh / 2f,
                    left to top, right - bw to top, left to bottom - bh, right - bw to bottom - bh)
            else
                listOf(left to top, right - bw to top, left to bottom - bh, right - bw to bottom - bh,
                    left - bw to top, right to top)
            var bx = left; var by = top; var best = Int.MAX_VALUE
            for ((ax, ay) in anchors) {
                val cx = ax.coerceIn(0f, bmp.width - bw); val cy = ay.coerceIn(0f, bmp.height - bh)
                val cand = android.graphics.RectF(cx, cy, cx + bw, cy + bh)
                val overlap = placed.count { android.graphics.RectF.intersects(it, cand) }
                if (overlap < best) { best = overlap; bx = cx; by = cy }
                if (overlap == 0) break
            }
            placed.add(android.graphics.RectF(bx, by, bx + bw, by + bh))
            c.drawRoundRect(bx, by, bx + bw, by + bh, ts * 0.3f, ts * 0.3f, badge)
            c.drawText(s, bx + ts * 0.3f, by + ts, label)
        }
        return bmp
    }

    private fun drawGrid(src: Bitmap, faint: Boolean = false): Bitmap {
        val bmp = src.copy(Bitmap.Config.ARGB_8888, true) ?: return src
        val c = Canvas(bmp)
        val w = bmp.width.toFloat(); val h = bmp.height.toFloat()
        val cols = GridSpec.COLS; val rows = GridSpec.ROWS
        val gridPaint = Paint().apply {
            color = if (faint) 0x33FF5252.toInt() else 0x88FF1744.toInt()
            strokeWidth = maxOf(1f, w / (if (faint) 520f else 360f)); isAntiAlias = true
        }
        val ts = h / (if (faint) 44f else 38f)
        val label = Paint().apply {
            color = Color.WHITE; textSize = ts; isFakeBoldText = true; isAntiAlias = true
            setShadowLayer(ts * 0.35f, 0f, 0f, Color.BLACK)
        }
        val box = Paint().apply { color = if (faint) 0x66000000.toInt() else 0xCCD50000.toInt() }
        for (i in 1 until cols) { val x = w * i / cols; c.drawLine(x, 0f, x, h, gridPaint) }
        for (j in 1 until rows) { val y = h * j / rows; c.drawLine(0f, y, w, y, gridPaint) }
        for (i in 0 until cols) {
            val cx = w * (i + 0.5f) / cols
            val s = ('A' + i).toString()
            val tw = label.measureText(s)
            c.drawRect(cx - tw, 1f, cx + tw, 1f + ts * 1.3f, box)
            c.drawText(s, cx - tw / 2, 1f + ts, label)
        }
        for (j in 0 until rows) {
            val cy = h * (j + 0.5f) / rows
            val s = (j + 1).toString()
            val tw = label.measureText(s)
            c.drawRect(1f, cy - ts * 0.7f, 1f + tw * 1.6f, cy + ts * 0.6f, box)
            c.drawText(s, 3f, cy + ts * 0.35f, label)
        }
        return bmp
    }

    private fun downscale(bmp: Bitmap, max: Int = DEFAULT_MAX_PX): Bitmap {
        val w = bmp.width; val h = bmp.height
        if (w <= max && h <= max) return bmp
        val s = max.toFloat() / maxOf(w, h)
        return Bitmap.createScaledBitmap(bmp, (w * s).toInt(), (h * s).toInt(), true)
    }
}
