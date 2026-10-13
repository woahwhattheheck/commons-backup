package com.tokenjunkielabs.proofpocket.core

import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.nio.ByteBuffer
import java.nio.charset.CharacterCodingException
import java.nio.charset.CodingErrorAction
import java.nio.charset.StandardCharsets

/** Resource limits for untrusted portable receipt imports.
 *
 * The receipt schema contains metadata/digests, never evidence bytes. 256 KiB is
 * intentionally far above the largest legitimate v1 receipt while keeping one
 * selected document from becoming an allocation or parser-depth attack.
 */
object ReceiptImportLimits {
    const val MAX_RECEIPT_BYTES = 256 * 1024
    const val MAX_JSON_DEPTH = 64

    fun requireBoundedString(raw: String) {
        require(raw.length <= MAX_RECEIPT_BYTES) {
            "receipt exceeds $MAX_RECEIPT_BYTES-character in-memory limit"
        }
    }

    fun readUtf8Bounded(input: InputStream): String {
        val out = ByteArrayOutputStream(minOf(16 * 1024, MAX_RECEIPT_BYTES))
        val buffer = ByteArray(8 * 1024)
        var total = 0
        while (true) {
            val count = input.read(buffer)
            if (count < 0) break
            if (count == 0) continue
            require(count <= MAX_RECEIPT_BYTES - total) {
                "receipt exceeds $MAX_RECEIPT_BYTES-byte import limit"
            }
            out.write(buffer, 0, count)
            total += count
        }

        val decoder = StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
        return try {
            decoder.decode(ByteBuffer.wrap(out.toByteArray())).toString()
        } catch (e: CharacterCodingException) {
            throw IllegalArgumentException("receipt is not valid UTF-8", e)
        }
    }
}
