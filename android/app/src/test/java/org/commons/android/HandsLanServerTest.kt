package org.commons.android

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.net.HttpURLConnection
import java.net.URL
import java.nio.charset.StandardCharsets

class HandsLanServerTest {
    @Test
    fun observeWithoutPairingDrives() {
        val server = HttpJsonServer(
            port = 0,
            handler = { request ->
                JSONObject()
                    .put("ok", true)
                    .put("kind", "observation_delta")
                    .put("op", request.optString("op"))
            },
            health = { JSONObject().put("ok", true).put("kind", "health-full").put("host_running", true) },
            bindHost = "127.0.0.1",
        )
        server.start()
        try {
            val port = server.boundPort
            val missing = JSONObject(post(port, """{"op":"observe"}"""))
            assertTrue(missing.getBoolean("ok"))
            assertEquals("observation_delta", missing.getString("kind"))
            val leftoverHeader = JSONObject(post(port, """{"op":"observe"}""", pairing = "deadbeef"))
            assertTrue(leftoverHeader.getBoolean("ok"))
            val empty = JSONObject(post(port, ""))
            assertFalse(empty.optBoolean("ok"))
            assertEquals("INVALID_REQUEST", empty.getString("failure_reason"))
            val health = JSONObject(get(port, "/health"))
            assertEquals("health-full", health.getString("kind"))
            assertTrue(health.getBoolean("host_running"))
        } finally {
            server.stop()
        }
    }

    @Test
    fun lanBindWithoutPairingListens() {
        val server = HttpJsonServer(
            port = 0,
            handler = { JSONObject().put("ok", true).put("kind", "capabilities") },
            health = { JSONObject().put("ok", true).put("kind", "health") },
            bindHost = "0.0.0.0",
        )
        server.start()
        try {
            val port = server.boundPort
            assertTrue(port > 0)
            val health = JSONObject(get(port, "/health"))
            assertTrue(health.getBoolean("ok"))
            val observed = JSONObject(post(port, """{"op":"observe"}"""))
            assertTrue(observed.getBoolean("ok"))
        } finally {
            server.stop()
        }
    }

    private fun post(port: Int, body: String, pairing: String? = null): String {
        var last: Exception? = null
        repeat(40) {
            try {
                val connection = URL("http://127.0.0.1:$port/").openConnection() as HttpURLConnection
                connection.requestMethod = "POST"
                connection.doOutput = true
                connection.connectTimeout = 2000
                connection.readTimeout = 2000
                connection.setRequestProperty("Content-Type", "application/json")
                if (pairing != null) connection.setRequestProperty("X-Commons-Pairing", pairing)
                connection.outputStream.use { it.write(body.toByteArray(StandardCharsets.UTF_8)) }
                val stream = if (connection.responseCode in 200..299) connection.inputStream else connection.errorStream
                return stream.use { it.readBytes().toString(Charsets.UTF_8) }
            } catch (exc: Exception) {
                last = exc
                Thread.sleep(25)
            }
        }
        throw last ?: IllegalStateException("post failed")
    }

    private fun get(port: Int, path: String): String {
        var last: Exception? = null
        repeat(40) {
            try {
                val connection = URL("http://127.0.0.1:$port$path").openConnection() as HttpURLConnection
                connection.requestMethod = "GET"
                connection.connectTimeout = 2000
                connection.readTimeout = 2000
                return connection.inputStream.use { it.readBytes().toString(Charsets.UTF_8) }
            } catch (exc: Exception) {
                last = exc
                Thread.sleep(25)
            }
        }
        throw last ?: IllegalStateException("get failed")
    }
}
