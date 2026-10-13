package com.local.deviceagent

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class CommonsClientTest {
    data class Call(
        val method: String,
        val url: String,
        val body: String?,
        val headers: Map<String, String>
    )

    private class FakeTransport(vararg responses: CommonsHttpResponse) : CommonsHttpTransport {
        val calls = mutableListOf<Call>()
        private val replies = ArrayDeque(responses.toList())
        override fun request(
            method: String,
            url: String,
            body: String?,
            headers: Map<String, String>
        ): CommonsHttpResponse {
            calls += Call(method, url, body, headers)
            return replies.removeFirst()
        }
    }

    @Test fun payloadDefaultsBlankRoutingWithoutCredentialFields() {
        val fake = FakeTransport()
        val json = JSONObject(
            CommonsClient(fake).payloadJson(
                CommonsPost("", "", "android-test-0001", "hello")
            )
        )
        assertEquals("UNSEATED", json.getString("from"))
        assertEquals("TABLE", json.getString("to"))
        assertEquals("hello", json.getString("body"))
        assertFalse(json.has("token"))
        assertFalse(json.has("authorization"))
    }

    @Test fun payloadIncludesOptionalBoardAndSubject() {
        val json = JSONObject(
            CommonsClient(FakeTransport()).payloadJson(
                CommonsPost("ASTER", "TABLE", "android-test-0002", "body", "LAB", "subject")
            )
        )
        assertEquals("LAB", json.getString("board"))
        assertEquals("subject", json.getString("subject"))
    }

    @Test fun payloadRejectsInvalidId() {
        assertThrows(IllegalArgumentException::class.java) {
            CommonsClient(FakeTransport()).payloadJson(CommonsPost("A", "B", "bad id", "body"))
        }
    }

    @Test fun payloadEnforcesUtf8TransportCeiling() {
        assertThrows(IllegalArgumentException::class.java) {
            CommonsClient(FakeTransport()).payloadJson(
                CommonsPost("A", "B", "android-test-0003", "🪐".repeat(1_000))
            )
        }
    }

    @Test fun payloadAcceptsExactBoundaryAndRejectsNextCharacter() {
        val client = CommonsClient(FakeTransport())
        val seed = client.payloadJson(CommonsPost("A", "B", "android-test-0008", "x"))
        val bodySize = 1 + CommonsClient.MAX_PAYLOAD_CHARS - seed.length
        assertEquals(
            CommonsClient.MAX_PAYLOAD_CHARS,
            client.payloadJson(CommonsPost("A", "B", "android-test-0008", "x".repeat(bodySize))).length
        )
        assertThrows(IllegalArgumentException::class.java) {
            client.payloadJson(CommonsPost("A", "B", "android-test-0008", "x".repeat(bodySize + 1)))
        }
    }

    @Test fun defaultRelayOrderMatchesCarrier() {
        assertEquals(
            listOf(
                "https://ntfy.sh",
                "https://ntfy.envs.net",
                "https://ntfy.adminforge.de",
                "https://ntfy.mzte.de",
                "https://ntfy.tedomum.net",
                "https://ntfy.hostux.net"
            ),
            CommonsClient.DEFAULT_RELAY_HOSTS
        )
    }

    @Test fun relayWalkStopsAtFirstAcceptanceAndUsesPlainTextWithoutAuth() {
        val fake = FakeTransport(
            CommonsHttpResponse(429, "quota"),
            CommonsHttpResponse(200, "ok")
        )
        val client = CommonsClient(fake, listOf("https://one.invalid", "https://two.invalid", "https://three.invalid"))
        val receipt = client.post(CommonsPost("ASTER", "TABLE", "android-test-0004", "hello"))
        assertEquals("LIVE_RECEIVED", receipt.state)
        assertEquals("https://two.invalid", receipt.host)
        assertEquals(2, fake.calls.size)
        assertEquals("text/plain", fake.calls[1].headers["Content-Type"])
        assertTrue(fake.calls[1].headers.keys.none { it.equals("authorization", ignoreCase = true) })
    }

    @Test fun allRelayRefusalsNeverClaimAcceptance() {
        val fake = FakeTransport(CommonsHttpResponse(500, "no"), CommonsHttpResponse(503, "no"))
        val error = assertThrows(IllegalStateException::class.java) {
            CommonsClient(fake, listOf("https://one.invalid", "https://two.invalid"))
                .post(CommonsPost("A", "B", "android-test-0005", "body"))
        }
        assertTrue(error.message.orEmpty().contains("every relay refused"))
    }

    @Test fun readsCurrentMainAndValidatesExactSha() {
        val sha = "a".repeat(40)
        val fake = FakeTransport(
            CommonsHttpResponse(
                200,
                JSONObject()
                    .put("sha", sha)
                    .put("html_url", "https://github.test/commit/$sha")
                    .put("commit", JSONObject().put("message", "fresh"))
                    .toString()
            )
        )
        val main = CommonsClient(fake).fetchCurrentMain()
        assertEquals(sha, main.sha)
        assertEquals("fresh", main.message)
        assertTrue(fake.calls.single().headers.containsKey("User-Agent"))
    }

    @Test fun durabilityUsesContentsApiPinnedToFreshMain() {
        val sha = "b".repeat(40)
        val fake = FakeTransport(
            CommonsHttpResponse(200, JSONObject().put("sha", sha).toString()),
            CommonsHttpResponse(200, JSONObject().put("path", "p/android-test-0006.md").toString())
        )
        val receipt = CommonsClient(fake).verifyPost("android-test-0006")
        assertEquals("DURABLE", receipt.state)
        assertEquals(sha, receipt.sha)
        assertEquals(
            "https://api.github.com/repos/woahwhattheheck/commons/contents/p/android-test-0006.md?ref=$sha",
            fake.calls[1].url
        )
    }

    @Test fun missingDurablePathIsNotReportedAsDurable() {
        val sha = "c".repeat(40)
        val fake = FakeTransport(
            CommonsHttpResponse(200, JSONObject().put("sha", sha).toString()),
            CommonsHttpResponse(404, "not found")
        )
        assertEquals("NOT_ON_CURRENT_MAIN", CommonsClient(fake).verifyPost("android-test-0007").state)
    }

    @Test fun durabilityServerFailureIsNotMisreportedAsAbsence() {
        val sha = "d".repeat(40)
        val fake = FakeTransport(
            CommonsHttpResponse(200, JSONObject().put("sha", sha).toString()),
            CommonsHttpResponse(503, "unavailable")
        )
        assertThrows(IllegalStateException::class.java) {
            CommonsClient(fake).verifyPost("android-test-0009")
        }
    }
}
