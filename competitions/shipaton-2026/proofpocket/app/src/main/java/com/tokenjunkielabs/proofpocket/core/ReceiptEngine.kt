package com.tokenjunkielabs.proofpocket.core

import java.security.MessageDigest
import java.time.Instant

data class Evidence(
    val id: String,
    val name: String,
    val mimeType: String,
    val sha256: String,
    val sizeBytes: Long,
    val sourceModifiedAtUtc: String? = null,
)

data class Receipt(
    val receiptId: String,
    val projectId: String,
    val projectTitle: String,
    val claim: String,
    val issuedAtUtc: String,
    val evidence: List<Evidence>,
)

data class ReceiptVerification(val valid: Boolean, val reason: String)

object ReceiptEngine {
    private val hex64 = Regex("^[0-9a-f]{64}$")
    private val safeId = Regex("^[A-Za-z0-9._:-]{1,128}$")

    fun sha256(bytes: ByteArray): String = MessageDigest.getInstance("SHA-256")
        .digest(bytes).joinToString("") { "%02x".format(it) }

    fun stableProjectId(title: String, createdAtUtc: String): String {
        require(title.isNotBlank()) { "project title is required" }
        UnicodeIntegrity.requireWellFormedUtf16(title, "project title")
        validateInstant(createdAtUtc)
        return "p_" + sha256("proofpocket-project-v1\n${title.trim()}\n$createdAtUtc".toByteArray()).take(24)
    }

    fun evidenceId(sha256: String): String {
        val normalized = sha256.lowercase()
        require(hex64.matches(normalized)) { "evidence sha256 must be 64 lowercase hex chars" }
        return "e_" + normalized.take(24)
    }

    fun issue(
        projectId: String,
        projectTitle: String,
        claim: String,
        issuedAtUtc: String,
        evidence: List<Evidence>,
    ): Receipt {
        validate(projectId, projectTitle, claim, issuedAtUtc, evidence)
        val normalizedEvidence = evidence.map { it.copy(sha256 = it.sha256.lowercase()) }.sortedBy { it.id }
        val provisional = Receipt("", projectId, projectTitle.trim(), claim.trim(), issuedAtUtc, normalizedEvidence)
        val receiptId = sha256(canonicalPayload(provisional).toByteArray())
        return provisional.copy(receiptId = receiptId)
    }

    fun verify(receipt: Receipt): ReceiptVerification = try {
        val rebuilt = issue(receipt.projectId, receipt.projectTitle, receipt.claim, receipt.issuedAtUtc, receipt.evidence)
        if (rebuilt.receiptId == receipt.receiptId.lowercase()) {
            ReceiptVerification(true, "receipt hash matches canonical payload")
        } else {
            ReceiptVerification(false, "receipt hash mismatch: payload or evidence changed")
        }
    } catch (e: IllegalArgumentException) {
        ReceiptVerification(false, e.message ?: "invalid receipt")
    }

    fun canonicalPayload(receipt: Receipt): String = buildString {
        append("{\"schema\":\"proofpocket.receipt.v1\"")
        append(",\"projectId\":\"").append(jsonEscape(receipt.projectId)).append('"')
        append(",\"projectTitle\":\"").append(jsonEscape(receipt.projectTitle)).append('"')
        append(",\"claim\":\"").append(jsonEscape(receipt.claim)).append('"')
        append(",\"issuedAtUtc\":\"").append(jsonEscape(receipt.issuedAtUtc)).append('"')
        append(",\"evidence\":[")
        receipt.evidence.sortedBy { it.id }.forEachIndexed { index, item ->
            if (index > 0) append(',')
            append("{\"id\":\"").append(jsonEscape(item.id)).append('"')
            append(",\"name\":\"").append(jsonEscape(item.name)).append('"')
            append(",\"mimeType\":\"").append(jsonEscape(item.mimeType)).append('"')
            append(",\"sha256\":\"").append(item.sha256.lowercase()).append('"')
            append(",\"sizeBytes\":").append(item.sizeBytes)
            append(",\"sourceModifiedAtUtc\":")
            item.sourceModifiedAtUtc?.let { append('"').append(jsonEscape(it)).append('"') } ?: append("null")
            append('}')
        }
        append("]}")
    }

    fun exportJson(receipt: Receipt): String =
        "{\"receiptId\":\"${receipt.receiptId}\",\"payload\":${canonicalPayload(receipt)}}"

    private fun validate(
        projectId: String,
        projectTitle: String,
        claim: String,
        issuedAtUtc: String,
        evidence: List<Evidence>,
    ) {
        require(safeId.matches(projectId)) { "invalid project id" }
        require(projectTitle.trim().length in 1..160) { "project title must be 1..160 chars" }
        require(claim.trim().length in 1..2000) { "claim must be 1..2000 chars" }
        validateInstant(issuedAtUtc)
        require(evidence.size <= 128) { "receipt supports at most 128 evidence items" }
        val ids = HashSet<String>()
        evidence.forEach { item ->
            require(safeId.matches(item.id)) { "invalid evidence id" }
            require(ids.add(item.id)) { "duplicate evidence id: ${item.id}" }
            require(item.name.trim().length in 1..255) { "evidence name must be 1..255 chars" }
            require(item.mimeType.trim().length in 1..127) { "mime type must be present" }
            require(hex64.matches(item.sha256.lowercase())) { "invalid evidence sha256" }
            require(item.id == evidenceId(item.sha256)) { "evidence id must derive from evidence sha256" }
            require(item.sizeBytes >= 0) { "evidence size cannot be negative" }
            item.sourceModifiedAtUtc?.let(::validateInstant)
        }
    }

    private fun validateInstant(value: String) {
        require(value.endsWith("Z")) { "timestamp must use canonical UTC Z form: $value" }
        try {
            Instant.parse(value)
        } catch (_: Exception) {
            throw IllegalArgumentException("timestamp must be an ISO-8601 UTC instant: $value")
        }
    }

    private fun jsonEscape(value: String): String {
        UnicodeIntegrity.requireWellFormedUtf16(value, "canonical JSON string")
        return buildString(value.length + 8) {
            value.forEach { c ->
                when (c) {
                    '\\' -> append("\\\\")
                    '"' -> append("\\\"")
                    '\b' -> append("\\b")
                    '\u000C' -> append("\\f")
                    '\n' -> append("\\n")
                    '\r' -> append("\\r")
                    '\t' -> append("\\t")
                    else -> if (c.code < 0x20) append("\\u%04x".format(c.code)) else append(c)
                }
            }
        }
    }
}
