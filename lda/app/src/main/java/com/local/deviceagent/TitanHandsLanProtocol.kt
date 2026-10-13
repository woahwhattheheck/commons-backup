package com.local.deviceagent

import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.nio.ByteBuffer
import java.nio.charset.CharacterCodingException
import java.nio.charset.CodingErrorAction
import java.util.Base64

data class TitanHandsLanCommand(
    val requestId: String,
    val op: String,
    val actionBase64: String?
)

/** One-request-per-connection JSONL framing for the credential-free LAN bridge. */
object TitanHandsLanProtocol {
    const val VERSION = "lda-titan-hands-lan/1"
    const val DEFAULT_PORT = 42171
    const val MAX_REQUEST_BYTES = 65_536

    fun readRequest(input: InputStream, maxBytes: Int = MAX_REQUEST_BYTES): String? {
        require(maxBytes > 0)
        val bytes = ByteArrayOutputStream()
        while (true) {
            val next = input.read()
            if (next == -1) {
                if (bytes.size() == 0) return null
                throw IllegalArgumentException("request ended before newline")
            }
            if (next == '\n'.code) {
                val frame = bytes.toByteArray()
                val content = if (frame.lastOrNull() == '\r'.code.toByte()) frame.copyOf(frame.size - 1) else frame
                return decodeUtf8(content)
            }
            if (bytes.size() >= maxBytes) throw IllegalArgumentException("request exceeds $maxBytes bytes")
            bytes.write(next)
        }
    }

    fun parseRequest(line: String): TitanHandsLanCommand {
        require(line.isNotBlank()) { "request is empty" }
        val json = JSONObject(line)
        val op = json.optString("op").trim().lowercase()
        require(op.isNotBlank()) { "op is required" }
        val requestId = json.optString("request_id").trim().ifBlank { "anonymous" }
        require(requestId.length <= 120) { "request_id exceeds 120 characters" }

        val actionBase64 = if (op == "act") {
            val action = json.opt("action")
            val raw = when (action) {
                is JSONObject -> action.toString()
                is String -> action
                else -> throw IllegalArgumentException("act requires action JSON")
            }
            require(raw.isNotBlank()) { "act action JSON is empty" }
            // Parse before transport so malformed JSON never reaches the existing handset executor.
            JSONObject(raw)
            Base64.getEncoder().encodeToString(raw.toByteArray(Charsets.UTF_8))
        } else null
        return TitanHandsLanCommand(requestId, op, actionBase64)
    }

    fun decorateReceiverResponse(receiverJson: String, requestId: String): String {
        val result = JSONObject(receiverJson)
        result.put("lan", VERSION)
        result.put("request_id", requestId)
        return result.toString()
    }

    fun failure(reason: String, message: String, requestId: String = "anonymous"): String =
        JSONObject()
            .put("ok", false)
            .put("lan", VERSION)
            .put("request_id", requestId)
            .put("failure_reason", reason)
            .put("message", message)
            .toString()

    fun decodeReceiverResult(encoded: String): String =
        String(Base64.getDecoder().decode(encoded), Charsets.UTF_8)

    private fun decodeUtf8(bytes: ByteArray): String {
        return try {
            Charsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes))
                .toString()
        } catch (e: CharacterCodingException) {
            throw IllegalArgumentException("request is not valid UTF-8", e)
        }
    }
}
