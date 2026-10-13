package com.tokenjunkielabs.proofpocket.core

import java.io.InputStream
import java.security.MessageDigest

data class EvidenceDigest(val sha256: String, val sizeBytes: Long)

/** Hash and length describe the same bytes, not a document provider's metadata.
 * The caller owns and closes the input stream.
 */
object EvidenceStreams {
    fun hash(input: InputStream): EvidenceDigest {
        val digest = MessageDigest.getInstance("SHA-256")
        val buffer = ByteArray(64 * 1024)
        var size = 0L
        while (true) {
            val count = input.read(buffer)
            if (count < 0) break
            if (count == 0) {
                // A zero-length read is not EOF. Make progress without spinning.
                val value = input.read()
                if (value < 0) break
                digest.update(value.toByte())
                size = Math.addExact(size, 1L)
            } else {
                digest.update(buffer, 0, count)
                size = Math.addExact(size, count.toLong())
            }
        }
        val sha = digest.digest().joinToString("") { "%02x".format(it) }
        return EvidenceDigest(sha, size)
    }
}
