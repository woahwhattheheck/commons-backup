import com.tokenjunkielabs.proofpocket.core.*

private fun expectFailure(block: () -> Unit) {
    var failed = false
    try { block() } catch (_: IllegalArgumentException) { failed = true }
    check(failed) { "expected IllegalArgumentException" }
}

fun main() {
    val time = "2026-09-14T01:30:00Z"
    val shaA = ReceiptEngine.sha256("photo-A".toByteArray())
    val shaB = ReceiptEngine.sha256("log-B".toByteArray())
    val a = Evidence(ReceiptEngine.evidenceId(shaA), "after.jpg", "image/jpeg", shaA, 7)
    val b = Evidence(ReceiptEngine.evidenceId(shaB), "build.txt", "text/plain", shaB, 5)
    val project = ReceiptEngine.stableProjectId("Hotel room turn", time)

    val r1 = ReceiptEngine.issue(project, "Hotel room turn", "Room 214 reset and checked", time, listOf(a, b))
    val r2 = ReceiptEngine.issue(project, "Hotel room turn", "Room 214 reset and checked", time, listOf(b, a))
    check(r1.receiptId == r2.receiptId) { "evidence ordering changed receipt" }
    check(ReceiptEngine.verify(r1).valid)

    val tamperedClaim = r1.copy(claim = "Room 215 reset and checked")
    check(!ReceiptEngine.verify(tamperedClaim).valid)
    val tamperedEvidence = r1.copy(evidence = listOf(a.copy(sha256 = ReceiptEngine.sha256("changed".toByteArray())), b))
    check(!ReceiptEngine.verify(tamperedEvidence).valid)

    expectFailure { ReceiptEngine.issue(project, "Hotel room turn", "x", time, listOf(a, a)) }
    expectFailure { ReceiptEngine.issue(project, "Hotel room turn", "x", "not-time", listOf(a)) }
    expectFailure { ReceiptEngine.issue(project, "Hotel room turn", "x", time, listOf(a.copy(sha256 = "abc"))) }
    expectFailure { ReceiptEngine.issue(project, "Hotel room turn", "x", time, listOf(a.copy(id = "e_spoofed"))) }
    expectFailure { ReceiptEngine.issue(project, "Hotel room turn", "x", "2026-09-14T02:30:00+01:00", listOf(a)) }

    val loneHigh = "\uD800"
    val loneLow = "\uDC00"
    val rocket = "\uD83D\uDE80"
    expectFailure { ReceiptEngine.stableProjectId("bad-$loneHigh", time) }
    expectFailure { ReceiptEngine.issue(project, "Hotel room turn", loneHigh, time, listOf(a)) }
    expectFailure { ReceiptEngine.issue(project, loneLow, "claim", time, listOf(a)) }
    expectFailure { ReceiptEngine.issue(project, "Hotel room turn", "claim", time, listOf(a.copy(name = loneHigh))) }
    expectFailure { ReceiptEngine.issue(project, "Hotel room turn", "claim", time, listOf(a.copy(mimeType = loneLow))) }
    expectFailure { ReceiptEngine.canonicalPayload(r1.copy(claim = loneHigh)) }
    val paired = ReceiptEngine.issue(project, "Hotel room turn $rocket", "paired supplementary $rocket", time, listOf(a))
    check(ReceiptEngine.verify(paired).valid)
    val question = ReceiptEngine.issue(project, "Hotel room turn", "?", time, listOf(a))
    check(question.receiptId != paired.receiptId)

    check(!EntitlementPolicy.evaluate(false, true, true).pro)
    check(!EntitlementPolicy.evaluate(true, false, true).pro)
    check(!EntitlementPolicy.evaluate(true, true, false).pro)
    check(EntitlementPolicy.evaluate(true, true, true).pro)

    println("CORE_OK receipt=${r1.receiptId} canonical_bytes=${ReceiptEngine.canonicalPayload(r1).toByteArray().size}")
}
