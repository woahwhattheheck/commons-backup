package com.tokenjunkielabs.proofpocket.core

/** Reject malformed UTF-16 before any logical receipt string is serialized or hashed.
 * Java/Kotlin's default UTF-8 encoder replaces an unpaired surrogate with '?', which
 * would otherwise allow distinct logical strings to collapse onto identical bytes.
 */
object UnicodeIntegrity {
    fun requireWellFormedUtf16(value: String, label: String = "string") {
        var i = 0
        while (i < value.length) {
            val c = value[i]
            when {
                Character.isHighSurrogate(c) -> {
                    require(i + 1 < value.length && Character.isLowSurrogate(value[i + 1])) {
                        "$label contains an unpaired high surrogate"
                    }
                    i += 2
                }
                Character.isLowSurrogate(c) -> throw IllegalArgumentException("$label contains an unpaired low surrogate")
                else -> i += 1
            }
        }
    }
}
