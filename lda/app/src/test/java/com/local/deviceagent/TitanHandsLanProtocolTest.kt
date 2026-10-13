package com.local.deviceagent

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayInputStream
import java.util.Base64

class TitanHandsLanProtocolTest {
    @Test fun readsOneBoundedLfFrame() {
        val input = ByteArrayInputStream("{\"op\":\"observe\"}\nignored".toByteArray())
        assertEquals("{\"op\":\"observe\"}", TitanHandsLanProtocol.readRequest(input))
    }

    @Test fun readsCrLfFrameWithoutCarriageReturn() {
        val input = ByteArrayInputStream("{\"op\":\"capture\"}\r\n".toByteArray())
        assertEquals("{\"op\":\"capture\"}", TitanHandsLanProtocol.readRequest(input))
    }

    @Test fun emptyConnectionHasNoRequest() {
        assertNull(TitanHandsLanProtocol.readRequest(ByteArrayInputStream(byteArrayOf())))
    }

    @Test fun truncatedFrameIsRejected() {
        assertThrows(IllegalArgumentException::class.java) {
            TitanHandsLanProtocol.readRequest(ByteArrayInputStream("{\"op\":\"observe\"}".toByteArray()))
        }
    }

    @Test fun oversizeFrameIsRejectedBeforeUnboundedAllocation() {
        assertThrows(IllegalArgumentException::class.java) {
            TitanHandsLanProtocol.readRequest(
                ByteArrayInputStream("12345\n".toByteArray()),
                maxBytes = 4
            )
        }
    }

    @Test fun exactFrameBoundaryIsAccepted() {
        assertEquals(
            "1234",
            TitanHandsLanProtocol.readRequest(ByteArrayInputStream("1234\n".toByteArray()), maxBytes = 4)
        )
    }

    @Test fun readsSequentialFramesWithoutConsumingTheSecond() {
        val input = ByteArrayInputStream("one\ntwo\n".toByteArray())
        assertEquals("one", TitanHandsLanProtocol.readRequest(input))
        assertEquals("two", TitanHandsLanProtocol.readRequest(input))
    }

    @Test fun invalidUtf8IsRejected() {
        assertThrows(IllegalArgumentException::class.java) {
            TitanHandsLanProtocol.readRequest(
                ByteArrayInputStream(byteArrayOf(0xC3.toByte(), 0x28, '\n'.code.toByte()))
            )
        }
    }

    @Test fun observeRequestNeedsNoCredentialOrApproval() {
        val command = TitanHandsLanProtocol.parseRequest("{\"request_id\":\"r-1\",\"op\":\"observe\"}")
        assertEquals("r-1", command.requestId)
        assertEquals("observe", command.op)
        assertNull(command.actionBase64)
    }

    @Test fun protocolDoesNotAddAnOperationAllowlist() {
        val command = TitanHandsLanProtocol.parseRequest("{\"op\":\"future-bridge-op\"}")
        assertEquals("future-bridge-op", command.op)
    }

    @Test fun canonicalReceiverOperationsAllPassFraming() {
        for (op in listOf("capabilities", "observe", "capture", "marks")) {
            assertEquals(op, TitanHandsLanProtocol.parseRequest("{\"op\":\"$op\"}").op)
        }
    }

    @Test fun actPreservesExactActionJsonThroughBase64() {
        val action = JSONObject().put("action", "tap").put("element", 7)
        val command = TitanHandsLanProtocol.parseRequest(
            JSONObject().put("request_id", "r-2").put("op", "act").put("action", action).toString()
        )
        val decoded = String(Base64.getDecoder().decode(command.actionBase64), Charsets.UTF_8)
        assertEquals("tap", JSONObject(decoded).getString("action"))
        assertEquals(7, JSONObject(decoded).getInt("element"))
    }

    @Test fun actRejectsMissingActionAsMalformedTransport() {
        assertThrows(IllegalArgumentException::class.java) {
            TitanHandsLanProtocol.parseRequest("{\"op\":\"act\"}")
        }
    }

    @Test fun malformedJsonIsRejected() {
        assertThrows(Exception::class.java) {
            TitanHandsLanProtocol.parseRequest("not-json")
        }
    }

    @Test fun decoratesReceiverResponseWithoutChangingReceiverFields() {
        val decorated = JSONObject(
            TitanHandsLanProtocol.decorateReceiverResponse("{\"ok\":true,\"pixels\":\"not-captured\"}", "r-3")
        )
        assertTrue(decorated.getBoolean("ok"))
        assertEquals("not-captured", decorated.getString("pixels"))
        assertEquals(TitanHandsLanProtocol.VERSION, decorated.getString("lan"))
        assertEquals("r-3", decorated.getString("request_id"))
        assertFalse(decorated.has("token"))
    }

    @Test fun failureIsTypedAndCredentialFree() {
        val failure = JSONObject(TitanHandsLanProtocol.failure("INVALID_REQUEST", "bad", "r-4"))
        assertFalse(failure.getBoolean("ok"))
        assertEquals("INVALID_REQUEST", failure.getString("failure_reason"))
        assertFalse(failure.has("authorization"))
    }

    @Test fun invalidReceiverBase64IsRejected() {
        assertThrows(IllegalArgumentException::class.java) {
            TitanHandsLanProtocol.decodeReceiverResult("%%%")
        }
    }
}
