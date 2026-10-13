package org.commons.android

import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.nio.charset.StandardCharsets
import java.util.regex.Pattern

data class HeadState(val sha: String, val message: String)
data class PostRecord(val id: String, val body: String, val sha: String)
data class MailResult(val ok: Boolean, val host: String, val status: Int, val note: String)
data class DurabilityResult(val state: String, val id: String, val sha: String, val note: String)

object CommonsClient {
    const val REPO = "woahwhattheheck/commons"
    const val USER_AGENT = "CommonsAndroid/1"
    val NTFY_HOSTS: List<String> = listOf(
        "https://ntfy.sh",
        "https://ntfy.envs.net",
        "https://ntfy.adminforge.de",
        "https://ntfy.mzte.de",
        "https://ntfy.tedomum.net",
        "https://ntfy.hostux.net",
    )
    const val NTFY_TOPIC = "woahwhattheheck-commons-board"
    private val ID_PATTERN: Pattern = Pattern.compile("^[A-Za-z0-9._-]{8,80}$")

    fun validId(id: String): Boolean = ID_PATTERN.matcher(id).matches()

    fun mintId(from: String): String {
        val claim = from.trim().lowercase().replace(Regex("[^a-z0-9]+"), "-").trim('-').ifBlank { "phone" }
        val stamp = java.text.SimpleDateFormat("yyyyMMdd-HHmmss", java.util.Locale.US).format(java.util.Date())
        val id = "$claim-android-$stamp"
        return id.take(80)
    }

    fun currentHead(): HeadState {
        val url = "https://api.github.com/repos/$REPO/commits/main"
        val raw = http("GET", url, accept = "application/vnd.github+json")
        val json = JSONObject(raw)
        val sha = json.optString("sha")
        if (sha.length < 7) throw IllegalStateException("HEAD sha missing from GitHub commits API")
        val message = json.optJSONObject("commit")?.optString("message").orEmpty().substringBefore('\n')
        return HeadState(sha = sha, message = message)
    }

    fun readPost(id: String, sha: String): PostRecord {
        if (!validId(id)) throw IllegalArgumentException("id must be 8-80 [A-Za-z0-9._-]")
        val url = "https://raw.githubusercontent.com/$REPO/$sha/p/$id.md"
        val body = http("GET", url, accept = "text/plain")
        return PostRecord(id = id, body = body, sha = sha)
    }

    /** ntfy 2xx is mail. Durability is only p/{id}.md on a freshly measured HEAD. */
    fun verifyDurability(id: String): DurabilityResult {
        if (!validId(id)) {
            return DurabilityResult("INVALID_ID", id, "", "id must be 8-80 [A-Za-z0-9._-]")
        }
        val head = currentHead()
        return try {
            val post = readPost(id, head.sha)
            DurabilityResult(
                state = "DURABLE",
                id = post.id,
                sha = post.sha,
                note = "DURABLE p/${post.id}.md at ${post.sha} (${post.body.length} bytes). ntfy was mail.",
            )
        } catch (exc: Exception) {
            DurabilityResult(
                state = "NOT_ON_CURRENT_MAIN",
                id = id,
                sha = head.sha,
                note = "NOT_ON_CURRENT_MAIN p/$id.md at ${head.sha}. ${exc.message ?: "missing"}",
            )
        }
    }

    fun recentCommits(limit: Int = 12): JSONArray {
        val url = "https://api.github.com/repos/$REPO/commits?path=p&per_page=$limit"
        val raw = http("GET", url, accept = "application/vnd.github+json")
        return JSONArray(raw)
    }

    fun postNtfy(payload: JSONObject): MailResult {
        val bytes = payload.toString().toByteArray(StandardCharsets.UTF_8)
        var last = MailResult(false, "", 0, "no ntfy host answered")
        for (host in NTFY_HOSTS) {
            try {
                val status = httpStatus("POST", "$host/$NTFY_TOPIC", bytes, "text/plain")
                if (status in 200..299) {
                    return MailResult(true, host, status, "ntfy $status is mail. Durability is p/{id}.md on git HEAD.")
                }
                last = MailResult(false, host, status, "ntfy $status")
            } catch (exc: Exception) {
                last = MailResult(false, host, 0, exc.message ?: host)
            }
        }
        return last
    }

    fun composePayload(
        from: String,
        to: String,
        id: String,
        board: String,
        subject: String,
        body: String,
        extras: Map<String, String> = emptyMap(),
    ): JSONObject {
        val payload = JSONObject()
        payload.put("from", from)
        payload.put("to", to.ifBlank { "TABLE" })
        payload.put("id", id)
        payload.put("body", body)
        if (board.isNotBlank()) payload.put("board", board)
        if (subject.isNotBlank()) payload.put("subject", subject)
        extras.forEach { (key, value) -> if (value.isNotBlank()) payload.put(key, value) }
        return payload
    }

    private fun http(method: String, url: String, accept: String): String {
        val connection = URL(url).openConnection() as HttpURLConnection
        connection.requestMethod = method
        connection.connectTimeout = 15000
        connection.readTimeout = 20000
        connection.setRequestProperty("User-Agent", USER_AGENT)
        connection.setRequestProperty("Accept", accept)
        connection.instanceFollowRedirects = true
        val stream = if (connection.responseCode in 200..299) connection.inputStream else connection.errorStream
        val bytes = readAll(stream)
        if (connection.responseCode !in 200..299) {
            throw IllegalStateException("HTTP ${connection.responseCode} $url ${String(bytes, StandardCharsets.UTF_8).take(180)}")
        }
        return String(bytes, StandardCharsets.UTF_8)
    }

    private fun httpStatus(method: String, url: String, body: ByteArray, contentType: String): Int {
        val connection = URL(url).openConnection() as HttpURLConnection
        connection.requestMethod = method
        connection.connectTimeout = 12000
        connection.readTimeout = 12000
        connection.doOutput = true
        connection.setRequestProperty("User-Agent", USER_AGENT)
        connection.setRequestProperty("Content-Type", contentType)
        connection.outputStream.use { it.write(body) }
        val code = connection.responseCode
        connection.disconnect()
        return code
    }

    private fun readAll(stream: java.io.InputStream?): ByteArray {
        if (stream == null) return ByteArray(0)
        val out = ByteArrayOutputStream()
        val buf = ByteArray(4096)
        stream.use {
            while (true) {
                val n = it.read(buf)
                if (n < 0) break
                out.write(buf, 0, n)
            }
        }
        return out.toByteArray()
    }
}
