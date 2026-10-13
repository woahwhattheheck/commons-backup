package org.commons.android

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Path
import android.graphics.Rect
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Display
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

class HandsAccessibilityService : AccessibilityService(), HandsBackend {
    companion object {
        @Volatile var instance: HandsAccessibilityService? = null
            private set
    }

    private val main = Handler(Looper.getMainLooper())
    private var lastNodes: Map<String, SemanticNode> = emptyMap()

    override fun onServiceConnected() {
        instance = this
    }

    override fun onDestroy() {
        if (instance === this) instance = null
        super.onDestroy()
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        // On-demand only. Window-state events are subscribed so the service stays bound.
    }

    override fun onInterrupt() = Unit

    override fun accessibilityReady(): Boolean = instance != null

    override fun implementation(): String = "commons-accessibility"

    override fun snapshot(maxNodes: Int): Snapshot = onMain {
        val root = rootInActiveWindow
            ?: throw BackendFailure("OBSERVATION_INVALID", "no active window")
        val raw = toRaw(root)
        val nodes = NodeWalk.walk(raw, serial = "phone", maxNodes = maxNodes)
        lastNodes = nodes.associateBy { it.id }
        val focusId = nodes.firstOrNull { "focused" in it.states }?.id.orEmpty()
        Snapshot(nodes = nodes, focusId = focusId, serial = "phone")
    }

    override fun perform(action: JSONObject): JSONObject {
        val actionType = action.optString("type").ifBlank { action.optString("action") }.trim().lowercase()
        if (actionType == "wait") {
            val seconds = action.optDouble("seconds", 1.0).coerceIn(0.0, 60.0)
            Thread.sleep((seconds * 1000).toLong())
            return JSONObject()
                .put("ok", true)
                .put("kind", "action_outcome")
                .put("platform", "android")
                .put("implementation", implementation())
        }
        return onMain {
        when (actionType) {
            "click", "invoke", "select", "toggle", "focus" -> {
                val node = liveNode(action)
                    ?: return@onMain failure("ELEMENT_STALE", "Android node is no longer present")
                if (actionType == "focus") {
                    if (!node.performAction(AccessibilityNodeInfo.ACTION_FOCUS) && !tap(node)) {
                        return@onMain failure("ACTION_FAILED", "focus did not land")
                    }
                } else if (!click(node)) {
                    return@onMain failure("ACTION_FAILED", "click did not land")
                }
            }
            "type_text", "set_value" -> {
                val value = action.optString("value").ifBlank { action.optString("text") }
                val node = liveNode(action)
                if (node != null) {
                    node.performAction(AccessibilityNodeInfo.ACTION_FOCUS)
                    if (actionType == "set_value") {
                        val args = Bundle()
                        args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, value)
                        if (!node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)) {
                            tap(node)
                            return@onMain typedFallback(value)
                        }
                    } else {
                        tap(node)
                        val existing = node.text?.toString().orEmpty()
                        val args = Bundle()
                        args.putCharSequence(
                            AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,
                            existing + value,
                        )
                        if (!node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)) {
                            return@onMain typedFallback(value)
                        }
                    }
                } else if (value.isNotEmpty()) {
                    return@onMain typedFallback(value)
                }
            }
            "key" -> {
                val key = action.optString("key").trim().lowercase()
                val ok = when (key) {
                    "back" -> performGlobalAction(GLOBAL_ACTION_BACK)
                    "home" -> performGlobalAction(GLOBAL_ACTION_HOME)
                    "recents", "recent" -> performGlobalAction(GLOBAL_ACTION_RECENTS)
                    "enter" -> liveNode(action)?.performAction(AccessibilityNodeInfo.ACTION_CLICK) == true
                    else -> false
                }
                if (!ok) return@onMain failure("ACTION_FAILED", "key $key did not land")
            }
            "scroll" -> {
                val node = liveNode(action) ?: rootInActiveWindow
                    ?: return@onMain failure("ELEMENT_STALE", "no scroll target")
                val direction = action.optString("direction", "down").lowercase()
                val actionId = if (direction in setOf("up", "left", "backward")) {
                    AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD
                } else {
                    AccessibilityNodeInfo.ACTION_SCROLL_FORWARD
                }
                if (!node.performAction(actionId) && !swipe(node, direction)) {
                    return@onMain failure("ACTION_FAILED", "scroll did not land")
                }
            }
            "launch" -> {
                val packageName = action.optString("package").ifBlank { action.optString("name") }.trim()
                if (packageName.isBlank()) return@onMain failure("INVALID_REQUEST", "launch requires package")
                val launch = packageManager.getLaunchIntentForPackage(packageName)
                    ?: return@onMain failure("WINDOW_MISS", "no launcher for $packageName")
                launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                startActivity(launch)
            }
            "done" -> Unit
            else -> return@onMain failure("UNKNOWN_OPERATION", "no Android handler for $actionType")
        }
        JSONObject()
            .put("ok", true)
            .put("kind", "action_outcome")
            .put("platform", "android")
            .put("implementation", implementation())
        }
    }

    override fun capturePng(): CaptureResult {
        if (Build.VERSION.SDK_INT < 30) {
            return CaptureResult(false, failureReason = "CAPTURE_FAILED", message = "takeScreenshot needs API 30")
        }
        val latch = CountDownLatch(1)
        val box = arrayOfNulls<CaptureResult>(1)
        onMain {
            takeScreenshot(
                Display.DEFAULT_DISPLAY,
                mainExecutor,
                object : TakeScreenshotCallback {
                    override fun onSuccess(screenshot: ScreenshotResult) {
                        try {
                            val hardware = Bitmap.wrapHardwareBuffer(screenshot.hardwareBuffer, screenshot.colorSpace)
                            if (hardware == null) {
                                box[0] = CaptureResult(false, failureReason = "CAPTURE_FAILED", message = "hardware buffer empty")
                                return
                            }
                            val software = hardware.copy(Bitmap.Config.ARGB_8888, false) ?: hardware
                            val bytes = ByteArrayOutputStream()
                            software.compress(Bitmap.CompressFormat.PNG, 100, bytes)
                            box[0] = CaptureResult(true, png = bytes.toByteArray())
                        } catch (exc: Exception) {
                            box[0] = CaptureResult(false, failureReason = "CAPTURE_FAILED", message = exc.message ?: "compress failed")
                        } finally {
                            latch.countDown()
                        }
                    }

                    override fun onFailure(errorCode: Int) {
                        box[0] = CaptureResult(false, failureReason = "CAPTURE_FAILED", message = "screenshot error $errorCode")
                        latch.countDown()
                    }
                },
            )
        }
        if (!latch.await(20, TimeUnit.SECONDS)) {
            return CaptureResult(false, failureReason = "CAPTURE_FAILED", message = "screenshot timed out")
        }
        return box[0] ?: CaptureResult(false, failureReason = "CAPTURE_FAILED", message = "no screenshot result")
    }

    private fun liveNode(action: JSONObject): AccessibilityNodeInfo? {
        val wanted = action.optString("id").trim()
        if (wanted.isBlank()) return null
        val root = rootInActiveWindow ?: return null
        val found = arrayOfNulls<AccessibilityNodeInfo>(1)
        fun visit(node: AccessibilityNodeInfo, path: String) {
            if (found[0] != null) return
            val id = NodeWalk.nodeId("phone", path, node.viewIdResourceName.orEmpty(), node.className?.toString().orEmpty())
            if (id == wanted) {
                found[0] = node
                return
            }
            for (index in 0 until node.childCount) {
                val child = node.getChild(index) ?: continue
                visit(child, "$path.$index")
            }
        }
        visit(root, "0")
        return found[0]
    }

    private fun click(node: AccessibilityNodeInfo): Boolean {
        if (node.performAction(AccessibilityNodeInfo.ACTION_CLICK)) return true
        return tap(node)
    }

    private fun tap(node: AccessibilityNodeInfo): Boolean {
        val bounds = Rect()
        node.getBoundsInScreen(bounds)
        if (bounds.width() <= 0 || bounds.height() <= 0) return false
        val path = Path()
        path.moveTo(bounds.exactCenterX(), bounds.exactCenterY())
        val stroke = GestureDescription.StrokeDescription(path, 0, 40)
        val gesture = GestureDescription.Builder().addStroke(stroke).build()
        val latch = CountDownLatch(1)
        val ok = booleanArrayOf(false)
        dispatchGesture(gesture, object : GestureResultCallback() {
            override fun onCompleted(gestureDescription: GestureDescription?) {
                ok[0] = true
                latch.countDown()
            }
            override fun onCancelled(gestureDescription: GestureDescription?) {
                latch.countDown()
            }
        }, null)
        latch.await(2, TimeUnit.SECONDS)
        return ok[0]
    }

    private fun swipe(node: AccessibilityNodeInfo, direction: String): Boolean {
        val bounds = Rect()
        node.getBoundsInScreen(bounds)
        val cx = bounds.exactCenterX()
        val cy = bounds.exactCenterY()
        val dx = (bounds.width() * 0.25f).coerceAtLeast(40f)
        val dy = (bounds.height() * 0.25f).coerceAtLeast(40f)
        val path = Path()
        when (direction) {
            "up" -> { path.moveTo(cx, cy + dy); path.lineTo(cx, cy - dy) }
            "left" -> { path.moveTo(cx + dx, cy); path.lineTo(cx - dx, cy) }
            "right" -> { path.moveTo(cx - dx, cy); path.lineTo(cx + dx, cy) }
            else -> { path.moveTo(cx, cy - dy); path.lineTo(cx, cy + dy) }
        }
        val stroke = GestureDescription.StrokeDescription(path, 0, 280)
        val gesture = GestureDescription.Builder().addStroke(stroke).build()
        val latch = CountDownLatch(1)
        val ok = booleanArrayOf(false)
        dispatchGesture(gesture, object : GestureResultCallback() {
            override fun onCompleted(gestureDescription: GestureDescription?) {
                ok[0] = true
                latch.countDown()
            }
            override fun onCancelled(gestureDescription: GestureDescription?) {
                latch.countDown()
            }
        }, null)
        latch.await(2, TimeUnit.SECONDS)
        return ok[0]
    }

    private fun typedFallback(value: String): JSONObject {
        return failure("ACTION_FAILED", "could not set text (${value.length} chars)")
    }

    private fun toRaw(node: AccessibilityNodeInfo): RawNode {
        val bounds = Rect()
        node.getBoundsInScreen(bounds)
        val children = ArrayList<RawNode>(node.childCount)
        for (index in 0 until node.childCount) {
            val child = node.getChild(index) ?: continue
            children += toRaw(child)
        }
        val className = node.className?.toString().orEmpty()
        return RawNode(
            className = className,
            text = node.text?.toString().orEmpty(),
            contentDescription = node.contentDescription?.toString().orEmpty(),
            viewId = node.viewIdResourceName.orEmpty(),
            packageName = node.packageName?.toString().orEmpty(),
            bounds = Bounds(bounds.left, bounds.top, bounds.width(), bounds.height()),
            enabled = node.isEnabled,
            focusable = node.isFocusable,
            focused = node.isFocused,
            selected = node.isSelected,
            checked = node.isChecked,
            checkable = node.isCheckable,
            clickable = node.isClickable,
            longClickable = node.isLongClickable,
            scrollable = node.isScrollable,
            editable = node.isEditable,
            password = node.isPassword,
            children = children,
        )
    }

    private fun <T> onMain(block: () -> T): T {
        if (Looper.myLooper() == Looper.getMainLooper()) return block()
        val latch = CountDownLatch(1)
        val box = arrayOfNulls<Any>(2)
        main.post {
            try {
                box[0] = block()
            } catch (thrown: Throwable) {
                box[1] = thrown
            } finally {
                latch.countDown()
            }
        }
        if (!latch.await(30, TimeUnit.SECONDS)) {
            throw BackendFailure("BACKEND_ERROR", "main-thread timeout")
        }
        val thrown = box[1]
        if (thrown is BackendFailure) throw thrown
        if (thrown is Throwable) throw BackendFailure("BACKEND_ERROR", thrown.message ?: thrown.javaClass.simpleName)
        @Suppress("UNCHECKED_CAST")
        return box[0] as T
    }
}
