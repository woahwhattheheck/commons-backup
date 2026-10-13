package org.commons.android

import org.json.JSONArray
import org.json.JSONObject
import java.util.Base64

interface HandsBackend {
    fun snapshot(maxNodes: Int): Snapshot
    fun perform(action: JSONObject): JSONObject
    fun capturePng(): CaptureResult
    fun accessibilityReady(): Boolean
    fun implementation(): String
}

data class Snapshot(
    val nodes: List<SemanticNode>,
    val focusId: String = "",
    val serial: String = "phone",
)

data class CaptureResult(
    val ok: Boolean,
    val png: ByteArray? = null,
    val failureReason: String = "",
    val message: String = "",
)

class HandsEngine(private val backend: HandsBackend) {
    private val tracker = DeltaTracker()

    fun handle(request: JSONObject): JSONObject {
        return try {
            val op = request.optString("op").trim().lowercase()
            when (op) {
                "capabilities" -> capabilities()
                "observe" -> tracker.observe(snapshotObject(request))
                "reset" -> {
                    tracker.reset()
                    JSONObject()
                        .put("ok", true)
                        .put("protocol", PROTOCOL_VERSION)
                        .put("kind", "reset")
                        .put("platform", "android")
                        .put("transport", "lan")
                }
                "act" -> act(request)
                "capture" -> capture()
                "targets" -> capabilities()
                else -> failure("UNKNOWN_OPERATION", "op was ${op.ifBlank { "<empty>" }}")
            }
        } catch (exc: BackendFailure) {
            failure(exc.reason, exc.message ?: exc.reason)
        } catch (exc: ProtocolException) {
            failure("INVALID_REQUEST", exc.message ?: "invalid request")
        } catch (exc: Exception) {
            failure("BACKEND_ERROR", exc.message ?: exc.javaClass.simpleName)
        }
    }

    fun capabilities(): JSONObject {
        val ready = backend.accessibilityReady()
        return JSONObject()
            .put("ok", true)
            .put("protocol", PROTOCOL_VERSION)
            .put("kind", "capabilities")
            .put("platform", "android")
            .put("transport", "lan")
            .put("observation", "accessibility-semantic-delta")
            .put("pixels", PIXELS_ON_DEMAND)
            .put("implementation", backend.implementation())
            .put("accessibility_ready", ready)
            .put("online", ready)
            .put("source", "HandsAccessibilityService")
            .put("layer", "LDA-reconciled accessibility snapshot/action")
            .put("actions", JSONArray(listOf(
                "click", "invoke", "focus", "select", "toggle",
                "type_text", "set_value", "key", "scroll", "launch", "wait", "done",
            )))
    }

    private fun snapshotObject(request: JSONObject): JSONObject {
        if (!backend.accessibilityReady()) {
            throw BackendFailure("ACCESSIBILITY_UNAVAILABLE", "enable the Commons accessibility setting on this phone")
        }
        val maxNodes = request.optInt("max_nodes", 400).coerceIn(1, 800)
        val snapshot = backend.snapshot(maxNodes)
        val nodes = JSONArray()
        snapshot.nodes.forEach { nodes.put(it.toJson()) }
        return JSONObject()
            .put("ok", true)
            .put("nodes", nodes)
            .put("kind", "semantic_snapshot")
            .put("platform", "android")
            .put("transport", "lan")
            .put("serial", snapshot.serial)
            .put("focus_id", snapshot.focusId)
            .put("pixels", PIXELS_NOT_CAPTURED)
            .put("implementation", backend.implementation())
    }

    private fun act(request: JSONObject): JSONObject {
        if (!backend.accessibilityReady()) {
            return failure("ACCESSIBILITY_UNAVAILABLE", "enable the Commons accessibility setting on this phone")
        }
        val action = request.optJSONObject("action")
            ?: return failure("INVALID_REQUEST", "act requires an action object")
        val actionType = action.optString("type").ifBlank { action.optString("action") }.trim().lowercase()
        if (actionType.isBlank()) {
            return failure("INVALID_REQUEST", "action.type is required")
        }
        val result = backend.perform(action)
        if (result.optBoolean("ok") && request.optBoolean("observe_after", true)) {
            result.put("observation", tracker.observe(snapshotObject(request)))
        }
        result.put("protocol", PROTOCOL_VERSION)
        result.put("kind", result.optString("kind", "action_outcome"))
        result.put("platform", "android")
        result.put("transport", "lan")
        result.put("action", actionType)
        return result
    }

    private fun capture(): JSONObject {
        if (!backend.accessibilityReady()) {
            return failure("ACCESSIBILITY_UNAVAILABLE", "enable the Commons accessibility setting on this phone")
        }
        val captured = backend.capturePng()
        if (!captured.ok || captured.png == null || captured.png.isEmpty()) {
            return failure(
                captured.failureReason.ifBlank { "CAPTURE_FAILED" },
                captured.message.ifBlank { "screenshot returned empty" },
            )
        }
        val encoded = Base64.getEncoder().encodeToString(captured.png)
        return JSONObject()
            .put("ok", true)
            .put("protocol", PROTOCOL_VERSION)
            .put("kind", "pixel_capture")
            .put("platform", "android")
            .put("transport", "lan")
            .put("visual", "accessibility-screenshot")
            .put("pixels", "on-demand")
            .put("mime", "image/png")
            .put("image_png_b64", encoded)
            .put("bytes", captured.png.size)
            .put("implementation", backend.implementation())
    }
}

class BackendFailure(val reason: String, message: String) : RuntimeException(message)

fun SemanticNode.toJson(): JSONObject {
    val bounds = JSONObject()
        .put("x", this.bounds.x)
        .put("y", this.bounds.y)
        .put("width", this.bounds.width)
        .put("height", this.bounds.height)
    return JSONObject()
        .put("id", id)
        .put("parent", parent)
        .put("role", role)
        .put("name", name)
        .put("automation_id", automationId)
        .put("class_name", className)
        .put("package", packageName)
        .put("content_description", contentDescription)
        .put("value", value)
        .put("bounds", bounds)
        .put("states", JSONArray(states))
        .put("actions", JSONArray(actions))
}
