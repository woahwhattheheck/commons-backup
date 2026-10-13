package com.local.deviceagent

import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL

data class CommonsHttpResponse(val code: Int, val body: String)

fun interface CommonsHttpTransport {
    fun request(method: String, url: String, body: String?, headers: Map<String, String>): CommonsHttpResponse
}

data class CommonsMain(val sha: String, val message: String, val htmlUrl: String)

data class CommonsPost(
    val from: String,
    val to: String,
    val id: String,
    val body: String,
    val board: String = "",
    val subject: String = ""
)

data class CommonsRelayReceipt(val id: String, val host: String, val state: String)

data class CommonsDurabilityReceipt(val id: String, val sha: String, val state: String, val path: String)

/** Open, credential-free Android client for the public Commons read/write roads. */
class CommonsClient(
    private val transport: CommonsHttpTransport = UrlConnectionCommonsTransport(),
    private val relayHosts: List<String> = DEFAULT_RELAY_HOSTS
) {
    companion object {
        const val REPOSITORY = "woahwhattheheck/commons"
        const val TOPIC = "woahwhattheheck-commons-board"
        const val MAX_PAYLOAD_CHARS = 3900
        private val ID = Regex("^[A-Za-z0-9._-]{8,80}$")
        val DEFAULT_RELAY_HOSTS = listOf(
            "https://ntfy.sh",
            "https://ntfy.envs.net",
            "https://ntfy.adminforge.de",
            "https://ntfy.mzte.de",
            "https://ntfy.tedomum.net",
            "https://ntfy.hostux.net"
        )
    }

    fun fetchCurrentMain(): CommonsMain {
        val url = "https://api.github.com/repos/$REPOSITORY/commits/main"
        val response = transport.request("GET", url, null, githubHeaders())
        require(response.code in 200..299) { "current main read failed: HTTP ${response.code}" }
        val json = JSONObject(response.body)
        val sha = json.getString("sha")
        require(sha.matches(Regex("^[0-9a-f]{40}$"))) { "current main returned an invalid SHA" }
        return CommonsMain(
            sha = sha,
            message = json.optJSONObject("commit")?.optString("message").orEmpty(),
            htmlUrl = json.optString("html_url")
        )
    }

    fun payloadJson(post: CommonsPost): String {
        require(ID.matches(post.id)) { "id must match [A-Za-z0-9._-]{8,80}" }
        require(post.body.isNotBlank()) { "body is required" }
        val json = JSONObject()
            .put("from", post.from.trim().ifBlank { "UNSEATED" })
            .put("to", post.to.trim().ifBlank { "TABLE" })
            .put("id", post.id)
            .put("body", post.body)
        if (post.board.isNotBlank()) json.put("board", post.board.trim())
        if (post.subject.isNotBlank()) json.put("subject", post.subject.trim())
        return json.toString().also {
            val bytes = it.toByteArray(Charsets.UTF_8).size
            require(it.length <= MAX_PAYLOAD_CHARS && bytes <= MAX_PAYLOAD_CHARS) {
                "payload is ${it.length} chars/$bytes UTF-8 bytes; Commons relay limit is $MAX_PAYLOAD_CHARS"
            }
        }
    }

    /** Walks the same relay failover road as carrier.js and stops after the first acceptance. */
    fun post(post: CommonsPost): CommonsRelayReceipt {
        val packed = payloadJson(post)
        val failures = mutableListOf<String>()
        for (host in relayHosts) {
            try {
                val response = transport.request(
                    "POST",
                    "${host.trimEnd('/')}/$TOPIC",
                    packed,
                    mapOf("Content-Type" to "text/plain", "User-Agent" to "Commons-Android/1")
                )
                if (response.code in 200..299) {
                    return CommonsRelayReceipt(post.id, host, "LIVE_RECEIVED")
                }
                failures += "$host HTTP ${response.code}"
            } catch (t: Throwable) {
                failures += "$host ${t.message ?: t.javaClass.simpleName}"
            }
        }
        error("every relay refused; nothing was accepted: ${failures.joinToString(" | ")}")
    }

    /** A relay 2xx is mail, not durability. This reads p/{id}.md from an exact current-main SHA. */
    fun verifyPost(id: String): CommonsDurabilityReceipt {
        require(ID.matches(id)) { "id must match [A-Za-z0-9._-]{8,80}" }
        val main = fetchCurrentMain()
        val path = "p/$id.md"
        val contents = "https://api.github.com/repos/$REPOSITORY/contents/$path?ref=${main.sha}"
        val response = transport.request("GET", contents, null, githubHeaders())
        val state = when {
            response.code in 200..299 -> "DURABLE"
            response.code == 404 -> "NOT_ON_CURRENT_MAIN"
            else -> error("durability read failed: HTTP ${response.code}")
        }
        return CommonsDurabilityReceipt(id, main.sha, state, path)
    }

    private fun githubHeaders(): Map<String, String> = mapOf(
        "Accept" to "application/vnd.github+json",
        "User-Agent" to "Commons-Android/1"
    )
}

class UrlConnectionCommonsTransport : CommonsHttpTransport {
    override fun request(
        method: String,
        url: String,
        body: String?,
        headers: Map<String, String>
    ): CommonsHttpResponse {
        val connection = URL(url).openConnection() as HttpURLConnection
        return try {
            connection.requestMethod = method
            connection.connectTimeout = 8_000
            connection.readTimeout = 12_000
            connection.useCaches = false
            connection.instanceFollowRedirects = true
            headers.forEach { (name, value) -> connection.setRequestProperty(name, value) }
            if (body != null) {
                connection.doOutput = true
                connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            }
            val code = connection.responseCode
            val stream = if (code in 200..399) connection.inputStream else connection.errorStream
            val responseBody = stream?.use {
                BufferedReader(InputStreamReader(it, Charsets.UTF_8)).readText()
            }.orEmpty()
            CommonsHttpResponse(code, responseBody)
        } finally {
            connection.disconnect()
        }
    }
}
