package org.commons.android

import org.json.JSONObject
import java.io.BufferedInputStream
import java.io.BufferedOutputStream
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import java.net.SocketException
import java.nio.charset.StandardCharsets
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Credential-free LAN JSON host for Titan Hands.
 *
 * User Start host is the only on/off. Accessibility stays a phone setting.
 * Possessing the LAN URL is enough to observe/act/capture, matching LDA's
 * TitanHandsLanService. Commons read/post stay open. This adds no seat.
 */
class HttpJsonServer(
    private val port: Int,
    private val handler: (JSONObject) -> JSONObject,
    private val health: () -> JSONObject,
    private val bindHost: String = "127.0.0.1",
) {
    private val running = AtomicBoolean(false)
    private val pool = Executors.newCachedThreadPool()
    @Volatile private var server: ServerSocket? = null
    @Volatile var boundPort: Int = port
        private set

    fun start() {
        if (!running.compareAndSet(false, true)) return
        val socket = ServerSocket(port, 50, InetAddress.getByName(bindHost))
        server = socket
        boundPort = socket.localPort
        pool.execute {
            while (running.get()) {
                try {
                    val client = socket.accept()
                    pool.execute { serve(client) }
                } catch (_: SocketException) {
                    break
                } catch (_: Exception) {
                    if (!running.get()) break
                }
            }
        }
    }

    fun stop() {
        running.set(false)
        try { server?.close() } catch (_: Exception) {}
        server = null
        pool.shutdownNow()
    }

    private fun serve(client: Socket) {
        client.soTimeout = 30000
        client.use { socket ->
            val input = BufferedInputStream(socket.getInputStream())
            val output = BufferedOutputStream(socket.getOutputStream())
            val requestLine = readLine(input) ?: return
            val parts = requestLine.split(" ")
            val method = parts.getOrElse(0) { "GET" }.uppercase()
            val rawPath = parts.getOrElse(1) { "/" }
            val path = rawPath.substringBefore('?')
            val headers = LinkedHashMap<String, String>()
            while (true) {
                val line = readLine(input) ?: break
                if (line.isEmpty()) break
                val idx = line.indexOf(':')
                if (idx > 0) headers[line.substring(0, idx).trim().lowercase()] = line.substring(idx + 1).trim()
            }
            val length = headers["content-length"]?.toIntOrNull() ?: 0
            val body = readBody(input, length.coerceAtMost(1_000_000))
            if (method == "OPTIONS") {
                write(output, 204, "application/json", ByteArray(0))
                return
            }
            val response: JSONObject = try {
                when {
                    method == "GET" && (path == "/" || path == "/health") -> health()
                    method == "POST" && (path == "/" || path == "/titan_hands") -> {
                        val text = String(body, StandardCharsets.UTF_8).trim()
                        if (text.isEmpty()) failure("INVALID_REQUEST", "empty body")
                        else handler(JSONObject(text).apply { remove("pairing") })
                    }
                    else -> failure("UNKNOWN_OPERATION", "no handler for $method $path")
                }
            } catch (exc: Exception) {
                failure("INVALID_REQUEST", exc.message ?: "could not parse JSON")
            }
            write(output, 200, "application/json; charset=utf-8", response.toString().toByteArray(StandardCharsets.UTF_8))
        }
    }

    private fun write(output: BufferedOutputStream, status: Int, contentType: String, body: ByteArray) {
        val reason = if (status == 200) "OK" else if (status == 204) "No Content" else "Error"
        val header = StringBuilder()
            .append("HTTP/1.1 ").append(status).append(' ').append(reason).append("\r\n")
            .append("Content-Type: ").append(contentType).append("\r\n")
            .append("Content-Length: ").append(body.size).append("\r\n")
            .append("Access-Control-Allow-Origin: *\r\n")
            .append("Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n")
            .append("Access-Control-Allow-Headers: Content-Type\r\n")
            .append("Connection: close\r\n\r\n")
            .toString()
            .toByteArray(StandardCharsets.US_ASCII)
        output.write(header)
        if (body.isNotEmpty()) output.write(body)
        output.flush()
    }

    private fun readBody(input: BufferedInputStream, length: Int): ByteArray {
        if (length <= 0) return ByteArray(0)
        val body = ByteArray(length)
        var offset = 0
        while (offset < length) {
            val read = input.read(body, offset, length - offset)
            if (read < 0) break
            offset += read
        }
        return if (offset == length) body else body.copyOf(offset)
    }

    private fun readLine(input: BufferedInputStream): String? {
        val bytes = ArrayList<Byte>()
        while (true) {
            val next = input.read()
            if (next < 0) return if (bytes.isEmpty()) null else String(bytes.toByteArray(), StandardCharsets.US_ASCII)
            if (next == '\n'.code) break
            if (next != '\r'.code) bytes.add(next.toByte())
            if (bytes.size > 16_384) break
        }
        return String(bytes.toByteArray(), StandardCharsets.US_ASCII)
    }
}
