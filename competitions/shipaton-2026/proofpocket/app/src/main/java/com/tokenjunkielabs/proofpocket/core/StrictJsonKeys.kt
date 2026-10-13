package com.tokenjunkielabs.proofpocket.core

/** Structural preflight that rejects duplicate JSON object keys before JSONObject
 * can collapse them. It intentionally authenticates nothing; it only preserves
 * unambiguous receipt semantics at the parser boundary.
 *
 * Parsing is resource-bounded: input strings are capped and recursive descent
 * stops at MAX_JSON_DEPTH before untrusted nesting can approach VM stack limits.
 */
object StrictJsonKeys {
    fun requireNoDuplicateObjectKeys(raw: String) {
        ReceiptImportLimits.requireBoundedString(raw)
        Parser(raw).parseDocument()
    }

    private class Parser(private val raw: String) {
        private var i = 0

        fun parseDocument() {
            skipWs()
            parseValue(0)
            skipWs()
            require(i == raw.length) { "trailing JSON content" }
        }

        private fun parseValue(depth: Int) {
            require(depth <= ReceiptImportLimits.MAX_JSON_DEPTH) {
                "JSON nesting exceeds ${ReceiptImportLimits.MAX_JSON_DEPTH} levels"
            }
            skipWs()
            require(i < raw.length) { "unexpected end of JSON" }
            when (raw[i]) {
                '{' -> parseObject(depth)
                '[' -> parseArray(depth)
                '"' -> parseString()
                't' -> consumeLiteral("true")
                'f' -> consumeLiteral("false")
                'n' -> consumeLiteral("null")
                '-', in '0'..'9' -> parseNumberToken()
                else -> throw IllegalArgumentException("invalid JSON token at offset $i")
            }
        }

        private fun parseObject(depth: Int) {
            i++
            skipWs()
            if (peek('}')) { i++; return }
            val keys = HashSet<String>()
            while (true) {
                skipWs()
                require(peek('"')) { "object key must be a JSON string at offset $i" }
                val key = parseString()
                require(keys.add(key)) { "duplicate JSON object key: $key" }
                skipWs()
                require(peek(':')) { "missing ':' after object key" }
                i++
                parseValue(depth + 1)
                skipWs()
                when {
                    peek(',') -> i++
                    peek('}') -> { i++; return }
                    else -> throw IllegalArgumentException("object must contain ',' or '}' at offset $i")
                }
            }
        }

        private fun parseArray(depth: Int) {
            i++
            skipWs()
            if (peek(']')) { i++; return }
            while (true) {
                parseValue(depth + 1)
                skipWs()
                when {
                    peek(',') -> i++
                    peek(']') -> { i++; return }
                    else -> throw IllegalArgumentException("array must contain ',' or ']' at offset $i")
                }
            }
        }

        private fun parseString(): String {
            require(peek('"')) { "expected JSON string" }
            i++
            val out = StringBuilder()
            while (i < raw.length) {
                val c = raw[i++]
                when (c) {
                    '"' -> return out.toString().also { UnicodeIntegrity.requireWellFormedUtf16(it, "JSON string") }
                    '\\' -> {
                        require(i < raw.length) { "unterminated JSON escape" }
                        when (val e = raw[i++]) {
                            '"', '\\', '/' -> out.append(e)
                            'b' -> out.append('\b')
                            'f' -> out.append('\u000c')
                            'n' -> out.append('\n')
                            'r' -> out.append('\r')
                            't' -> out.append('\t')
                            'u' -> {
                                require(i + 4 <= raw.length) { "short unicode escape" }
                                val hex = raw.substring(i, i + 4)
                                require(hex.all { it in "0123456789abcdefABCDEF" }) { "invalid unicode escape" }
                                out.append(hex.toInt(16).toChar())
                                i += 4
                            }
                            else -> throw IllegalArgumentException("invalid JSON escape: \\$e")
                        }
                    }
                    else -> {
                        require(c.code >= 0x20) { "unescaped control character in JSON string" }
                        out.append(c)
                    }
                }
            }
            throw IllegalArgumentException("unterminated JSON string")
        }

        private fun consumeLiteral(value: String) {
            require(raw.regionMatches(i, value, 0, value.length)) { "invalid JSON literal at offset $i" }
            i += value.length
        }

        private fun parseNumberToken() {
            val start = i
            while (i < raw.length && raw[i] !in charArrayOf(',', '}', ']', ' ', '\t', '\r', '\n')) i++
            val token = raw.substring(start, i)
            require(NUMBER.matches(token)) { "invalid JSON number: $token" }
        }

        private fun skipWs() {
            while (i < raw.length && raw[i] in charArrayOf(' ', '\t', '\r', '\n')) i++
        }

        private fun peek(c: Char): Boolean = i < raw.length && raw[i] == c

        companion object {
            private val NUMBER = Regex("-?(0|[1-9][0-9]*)(\\.[0-9]+)?([eE][+-]?[0-9]+)?")
        }
    }
}
