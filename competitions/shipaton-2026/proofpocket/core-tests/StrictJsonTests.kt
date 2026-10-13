import com.tokenjunkielabs.proofpocket.core.ReceiptImportLimits
import com.tokenjunkielabs.proofpocket.core.StrictJsonKeys
import java.io.ByteArrayInputStream

private fun expectStrictFailure(raw: String) {
    var failed = false
    try { StrictJsonKeys.requireNoDuplicateObjectKeys(raw) } catch (_: IllegalArgumentException) { failed = true }
    check(failed) { "expected strict JSON failure" }
}

private fun expectImportFailure(bytes: ByteArray) {
    var failed = false
    try { ReceiptImportLimits.readUtf8Bounded(ByteArrayInputStream(bytes)) } catch (_: IllegalArgumentException) { failed = true }
    check(failed) { "expected bounded import failure" }
}

fun main() {
    StrictJsonKeys.requireNoDuplicateObjectKeys("{\"a\":1,\"b\":{\"x\":2},\"c\":[{\"z\":3},{\"z\":4}]}")
    expectStrictFailure("{\"a\":1,\"a\":2}")
    expectStrictFailure("{\"a\":{\"x\":1,\"x\":2}}")
    expectStrictFailure("{\"id\":1,\"\\u0069d\":2}")
    StrictJsonKeys.requireNoDuplicateObjectKeys("[{\"id\":1},{\"id\":2}]")
    expectStrictFailure("{\"x\":\"\\uD800\"}")
    expectStrictFailure("{\"x\":\"\\uDC00\"}")
    StrictJsonKeys.requireNoDuplicateObjectKeys("{\"x\":\"\\uD83D\\uDE80\"}")

    val safeDepth = "[".repeat(32) + "0" + "]".repeat(32)
    StrictJsonKeys.requireNoDuplicateObjectKeys(safeDepth)
    val overDepth = "[".repeat(ReceiptImportLimits.MAX_JSON_DEPTH + 2) + "0" + "]".repeat(ReceiptImportLimits.MAX_JSON_DEPTH + 2)
    expectStrictFailure(overDepth)
    val hostileDepth = "[".repeat(5_000) + "{\"unknown\":true}" + "]".repeat(5_000)
    expectStrictFailure(hostileDepth)

    val exactLimit = ByteArray(ReceiptImportLimits.MAX_RECEIPT_BYTES) { ' '.code.toByte() }
    check(ReceiptImportLimits.readUtf8Bounded(ByteArrayInputStream(exactLimit)).length == ReceiptImportLimits.MAX_RECEIPT_BYTES)
    expectImportFailure(ByteArray(ReceiptImportLimits.MAX_RECEIPT_BYTES + 1) { 'x'.code.toByte() })
    expectImportFailure(byteArrayOf(0xC3.toByte(), 0x28))

    println("STRICT_JSON_BOUNDED_OK maxBytes=${ReceiptImportLimits.MAX_RECEIPT_BYTES} maxDepth=${ReceiptImportLimits.MAX_JSON_DEPTH}")
}
