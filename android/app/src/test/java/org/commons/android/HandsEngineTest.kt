package org.commons.android

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class HandsEngineTest {
    private val tree = RawNode(
        className = "android.widget.FrameLayout",
        children = listOf(
            RawNode(
                className = "android.widget.EditText",
                text = "Hello",
                viewId = "org.commons.android:id/input",
                contentDescription = "Greeting",
                packageName = "org.commons.android",
                bounds = Bounds(20, 100, 480, 80),
                focusable = true,
                focused = true,
                clickable = true,
                editable = true,
            ),
            RawNode(
                className = "android.widget.Button",
                text = "Send",
                viewId = "org.commons.android:id/send",
                packageName = "org.commons.android",
                bounds = Bounds(20, 200, 200, 80),
                clickable = true,
            ),
        ),
    )

    @Test
    fun walkProducesStableIdsAndRoles() {
        val nodes = NodeWalk.walk(tree)
        assertEquals(3, nodes.size)
        val field = nodes.first { it.role == "TextBox" }
        val button = nodes.first { it.role == "Button" }
        assertEquals("Hello", field.value)
        assertTrue(field.actions.contains("set_value"))
        assertTrue(button.actions.contains("click"))
        val again = NodeWalk.walk(tree)
        assertEquals(field.id, again.first { it.role == "TextBox" }.id)
    }

    @Test
    fun observeHasNoPixelsAndCaptureDoes() {
        val backend = FakeBackend(tree)
        val engine = HandsEngine(backend)
        val caps = engine.handle(JSONObject().put("op", "capabilities"))
        assertTrue(caps.getBoolean("ok"))
        assertEquals(PIXELS_ON_DEMAND, caps.getString("pixels"))
        val observed = engine.handle(JSONObject().put("op", "observe"))
        assertTrue(observed.getBoolean("ok"))
        assertEquals("observation_delta", observed.getString("kind"))
        assertFalse(observed.has("image_png_b64"))
        assertEquals(PIXELS_NOT_CAPTURED, observed.getJSONObject("meta").getString("pixels"))
        val second = engine.handle(JSONObject().put("op", "observe"))
        assertEquals(0, second.getJSONArray("added").length())
        assertEquals(0, second.getJSONArray("updated").length())
        val clicked = engine.handle(
            JSONObject()
                .put("op", "act")
                .put("action", JSONObject().put("type", "invoke").put("id", backend.buttonId())),
        )
        assertTrue(clicked.getBoolean("ok"))
        assertFalse(clicked.has("image_png_b64"))
        val captured = engine.handle(JSONObject().put("op", "capture"))
        assertTrue(captured.getBoolean("ok"))
        assertEquals("pixel_capture", captured.getString("kind"))
        assertTrue(captured.getString("image_png_b64").isNotBlank())
        assertEquals(1, backend.captures)
    }

    @Test
    fun typedFailuresStayTyped() {
        val engine = HandsEngine(FakeBackend(tree, ready = false))
        val observed = engine.handle(JSONObject().put("op", "observe"))
        assertFalse(observed.getBoolean("ok"))
        assertEquals("ACCESSIBILITY_UNAVAILABLE", observed.getString("failure_reason"))
        val ready = HandsEngine(FakeBackend(tree))
        val missing = ready.handle(JSONObject().put("op", "nope"))
        assertEquals("UNKNOWN_OPERATION", missing.getString("failure_reason"))
        val stale = ready.handle(
            JSONObject().put("op", "act").put("action", JSONObject().put("type", "click").put("id", "missing")),
        )
        assertEquals("ELEMENT_STALE", stale.getString("failure_reason"))
    }

    @Test
    fun composePayloadKeepsOptionalFrom() {
        val payload = CommonsClient.composePayload(
            from = "",
            to = "TABLE",
            id = "phone-android-20260826-01",
            board = "FEATURES",
            subject = "COMMONS APK",
            body = "PLAIN: hello",
        )
        assertEquals("", payload.getString("from"))
        assertEquals("phone-android-20260826-01", payload.getString("id"))
        assertTrue(CommonsClient.validId(payload.getString("id")))
        assertFalse(CommonsClient.validId("bad id"))
        assertEquals(6, CommonsClient.NTFY_HOSTS.size)
        assertEquals("woahwhattheheck-commons-board", CommonsClient.NTFY_TOPIC)
    }
}

class FakeBackend(
    private val tree: RawNode,
    private val ready: Boolean = true,
) : HandsBackend {
    var captures: Int = 0
        private set
    private var clicked: String = ""

    override fun accessibilityReady(): Boolean = ready
    override fun implementation(): String = "fake"
    override fun snapshot(maxNodes: Int): Snapshot {
        val nodes = NodeWalk.walk(tree, maxNodes = maxNodes).map { node ->
            if (node.id == clicked) node.copy(states = (node.states + "selected").distinct().sorted()) else node
        }
        return Snapshot(nodes = nodes, focusId = nodes.firstOrNull { "focused" in it.states }?.id.orEmpty())
    }

    override fun perform(action: JSONObject): JSONObject {
        val id = action.optString("id")
        if (id.isNotBlank() && NodeWalk.walk(tree).none { it.id == id }) {
            return failure("ELEMENT_STALE", "Android node is no longer present")
        }
        clicked = id
        return JSONObject().put("ok", true).put("kind", "action_outcome")
    }

    override fun capturePng(): CaptureResult {
        captures += 1
        return CaptureResult(ok = true, png = byteArrayOf(0x89.toByte(), 0x50, 0x4E, 0x47))
    }

    fun buttonId(): String = NodeWalk.walk(tree).first { it.role == "Button" }.id
}
