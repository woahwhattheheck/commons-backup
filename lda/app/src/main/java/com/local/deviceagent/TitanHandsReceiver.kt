package com.local.deviceagent

import android.app.Activity
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Base64
import org.json.JSONArray
import org.json.JSONObject

/**
 * Thin ADB transport for TITAN Hands.
 *
 * This is deliberately not a second handset operator. Perception and actuation stay in the LDA's
 * existing [ActionAccessibilityService.snapshotScreen] and
 * [ActionAccessibilityService.performActionJson] implementation. The receiver only transports one
 * operation in and one result out so an off-device model can drive the same translated handset.
 *
 * Input and output JSON are base64-wrapped because `adb shell am broadcast` otherwise damages
 * quotes, spaces, and Unicode. The receiver does not listen to accessibility events. Normal
 * observations stay the compact numbered LDA screen representation. An explicit capture/marks
 * operation returns the LDA Set-of-Marks screenshot rather than a raw ADB framebuffer.
 */
class TitanHandsReceiver : BroadcastReceiver() {

    companion object {
        const val ACTION = "com.local.deviceagent.TITAN_HANDS"
        const val BRIDGE_VERSION = "lda-titan-hands/1"
        const val GENERATION_MISMATCH_REASON = TitanHandsMarks.GENERATION_MISMATCH_REASON
    }

    override fun onReceive(context: Context, intent: Intent?) {
        val op = intent?.getStringExtra("op")?.trim()?.lowercase()
        // takeScreenshot's callback runs on the main executor. Blocking this thread with a latch
        // would deadlock, so capture uses goAsync and finishes from that callback.
        if (op == "capture" || op == "marks") {
            val pending = goAsync()
            try {
                captureAsync { response ->
                    pending.setResultCode(
                        if (response.optBoolean("ok")) Activity.RESULT_OK else Activity.RESULT_CANCELED
                    )
                    pending.setResultData(encode(response.toString()))
                    pending.finish()
                }
            } catch (t: Throwable) {
                val response = failure("BRIDGE_ERROR", t.message ?: t.javaClass.simpleName)
                pending.setResultCode(Activity.RESULT_CANCELED)
                pending.setResultData(encode(response.toString()))
                pending.finish()
            }
            return
        }
        val response = try {
            when (op) {
                "capabilities" -> capabilities()
                "observe" -> observe()
                "act" -> act(intent!!)
                else -> failure("UNKNOWN_OPERATION", "op must be capabilities, observe, act, or capture")
            }
        } catch (t: Throwable) {
            failure("BRIDGE_ERROR", t.message ?: t.javaClass.simpleName)
        }
        setResultCode(if (response.optBoolean("ok")) Activity.RESULT_OK else Activity.RESULT_CANCELED)
        setResultData(encode(response.toString()))
    }

    private fun capabilities(): JSONObject = JSONObject()
        .put("ok", true)
        .put("bridge", BRIDGE_VERSION)
        .put("platform", "android")
        .put("implementation", "lda-kotlin")
        .put("accessibility_ready", ActionAccessibilityService.instance != null)
        .put("perception", "ActionAccessibilityService.snapshotScreen")
        .put("actuation", "ActionAccessibilityService.performActionJson")
        .put("capture", "ActionAccessibilityService.captureScreenshot")
        .put("marks", "ActionAccessibilityService.currentMarks")
        .put("visual", "set-of-marks")

    private fun observe(): JSONObject {
        val service = ActionAccessibilityService.instance
            ?: return failure("ACCESSIBILITY_UNAVAILABLE", "enable Local Agent accessibility service")
        return JSONObject()
            .put("ok", true)
            .put("bridge", BRIDGE_VERSION)
            .put("platform", "android")
            .put("implementation", "lda-kotlin")
            .put("pixels", "not-captured")
            .put("snapshot", service.snapshotScreen())
    }

    private fun act(intent: Intent): JSONObject {
        val service = ActionAccessibilityService.instance
            ?: return failure("ACCESSIBILITY_UNAVAILABLE", "enable Local Agent accessibility service")
        val encoded = intent.getStringExtra("action_b64").orEmpty()
        if (encoded.isBlank()) return failure("INVALID_REQUEST", "act requires action_b64")
        val raw = try { decode(encoded) } catch (_: Throwable) {
            return failure("INVALID_REQUEST", "action_b64 is not valid UTF-8 base64")
        }
        if (raw.isBlank()) return failure("INVALID_REQUEST", "action JSON is empty")

        // Populate the numbered currentNodes table immediately before resolving an action. This is
        // the LDA's own perceive -> act contract and prevents stale/wrong-window element targeting.
        val before = service.snapshotScreen()
        val wasBusy = AgentService.isAgentBusy
        AgentService.isAgentBusy = true
        service.resumeInjection()
        return try {
            val outcome = service.performActionJson(raw)
            JSONObject()
                .put("ok", outcome.result != ActionResult.FAILED)
                .put("bridge", BRIDGE_VERSION)
                .put("platform", "android")
                .put("implementation", "lda-kotlin")
                .put("result", outcome.result.name)
                .put("summary", outcome.summary)
                .put("kickback", outcome.kickback)
                .put("say", outcome.say ?: JSONObject.NULL)
                .put("question", outcome.question ?: JSONObject.NULL)
                .put("before", before)
        } finally {
            AgentService.isAgentBusy = wasBusy
        }
    }

    private fun captureAsync(done: (JSONObject) -> Unit) {
        val service = ActionAccessibilityService.instance
        if (service == null) {
            done(failure("ACCESSIBILITY_UNAVAILABLE", "enable Local Agent accessibility service"))
            return
        }
        // Populate lastRenderedIds first so currentMarks badges match the numbered [N] list.
        val snapshotBefore = service.snapshotScreen()
        val marksBefore = service.currentMarks()
        val generationBefore = TitanHandsMarks.generationToken(snapshotBefore, marksBefore)
        service.captureScreenshot { bmp ->
            try {
                if (bmp == null) {
                    done(failure("CAPTURE_FAILED", "LDA screenshot returned null"))
                    return@captureScreenshot
                }
                val snapshotAfter = service.snapshotScreen()
                val marksAfter = service.currentMarks()
                val generationAfter = TitanHandsMarks.generationToken(snapshotAfter, marksAfter)
                val generation = TitanHandsMarks.sameGenerationOrNull(generationBefore, generationAfter)
                if (generation == null) {
                    recycleCapture(bmp)
                    done(
                        failure(
                            GENERATION_MISMATCH_REASON,
                            "semantics/marks changed around screenshot; pixels were not paired with a different generation",
                        )
                    )
                    return@captureScreenshot
                }
                // Tokens match, so marksAfter equals marksBefore. Overlay the pre-capture marks on
                // the screenshot taken before snapshotAfter; do not invent a later pairing.
                val jpeg = TitanHandsMarks.jpeg(bmp, marksBefore)
                recycleCapture(bmp)
                val ids = JSONArray()
                for (id in marksBefore.ids) ids.put(id)
                done(
                    JSONObject()
                        .put("ok", true)
                        .put("bridge", BRIDGE_VERSION)
                        .put("platform", "android")
                        .put("implementation", "lda-kotlin")
                        .put("kind", "pixel_capture")
                        .put("visual", "set-of-marks")
                        .put("pixels", "lda-marked-screenshot")
                        .put("source", "ActionAccessibilityService.captureScreenshot")
                        .put("marks_source", "ActionAccessibilityService.currentMarks")
                        .put("mime", TitanHandsMarks.JPEG_MIME)
                        .put("format", TitanHandsMarks.JPEG_FORMAT)
                        .put("suffix", TitanHandsMarks.JPEG_SUFFIX)
                        .put("generation", generation)
                        .put("image_b64", Base64.encodeToString(jpeg, Base64.NO_WRAP))
                        .put("mark_ids", ids)
                        .put("screen_w", marksBefore.screenW)
                        .put("screen_h", marksBefore.screenH)
                        .put("snapshot", snapshotBefore)
                )
            } catch (t: Throwable) {
                recycleCapture(bmp)
                done(failure("BRIDGE_ERROR", t.message ?: t.javaClass.simpleName))
            }
        }
    }

    private fun recycleCapture(bmp: android.graphics.Bitmap?) {
        if (bmp != null && !bmp.isRecycled) try { bmp.recycle() } catch (_: Exception) {}
    }

    private fun failure(reason: String, message: String): JSONObject = JSONObject()
        .put("ok", false)
        .put("bridge", BRIDGE_VERSION)
        .put("platform", "android")
        .put("implementation", "lda-kotlin")
        .put("failure_reason", reason)
        .put("message", message)

    private fun encode(value: String): String =
        Base64.encodeToString(value.toByteArray(Charsets.UTF_8), Base64.NO_WRAP)

    private fun decode(value: String): String =
        String(Base64.decode(value, Base64.DEFAULT), Charsets.UTF_8)
}
