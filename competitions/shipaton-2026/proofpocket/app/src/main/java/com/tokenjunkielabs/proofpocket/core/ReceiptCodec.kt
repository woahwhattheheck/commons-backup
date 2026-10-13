package com.tokenjunkielabs.proofpocket.core

import org.json.JSONObject

object ReceiptCodec {
    private val hex64 = Regex("^[0-9a-f]{64}$")
    private val topFields = setOf("receiptId", "payload")
    private val payloadFields = setOf("schema", "projectId", "projectTitle", "claim", "issuedAtUtc", "evidence")
    private val evidenceFields = setOf("id", "name", "mimeType", "sha256", "sizeBytes", "sourceModifiedAtUtc")

    fun decodeAndVerify(json: String): Pair<Receipt?, ReceiptVerification> = try {
        StrictJsonKeys.requireNoDuplicateObjectKeys(json)
        val root = JSONObject(json)
        requireExactKeys(root, topFields, "receipt root")
        val receiptId = root.getString("receiptId")
        require(hex64.matches(receiptId)) { "receiptId must be 64 lowercase hex chars" }

        val payload = root.getJSONObject("payload")
        requireExactKeys(payload, payloadFields, "receipt payload")
        require(payload.getString("schema") == "proofpocket.receipt.v1") { "unsupported receipt schema" }
        val evidenceJson = payload.getJSONArray("evidence")
        val evidence = buildList {
            for (i in 0 until evidenceJson.length()) {
                val e = evidenceJson.getJSONObject(i)
                requireExactKeys(e, evidenceFields, "evidence[$i]")
                val sizeRaw = e.get("sizeBytes")
                require(sizeRaw is Int || sizeRaw is Long) { "evidence[$i].sizeBytes must be an integer" }
                add(Evidence(
                    id = e.getString("id"),
                    name = e.getString("name"),
                    mimeType = e.getString("mimeType"),
                    sha256 = e.getString("sha256"),
                    sizeBytes = (sizeRaw as Number).toLong(),
                    sourceModifiedAtUtc = if (e.isNull("sourceModifiedAtUtc")) null else e.getString("sourceModifiedAtUtc"),
                ))
            }
        }
        val receipt = Receipt(
            receiptId = receiptId,
            projectId = payload.getString("projectId"),
            projectTitle = payload.getString("projectTitle"),
            claim = payload.getString("claim"),
            issuedAtUtc = payload.getString("issuedAtUtc"),
            evidence = evidence,
        )
        receipt to ReceiptEngine.verify(receipt)
    } catch (e: Exception) {
        null to ReceiptVerification(false, "invalid receipt JSON: ${e.message}")
    }

    private fun requireExactKeys(obj: JSONObject, expected: Set<String>, label: String) {
        val actual = HashSet<String>()
        val iterator = obj.keys()
        while (iterator.hasNext()) actual.add(iterator.next())
        require(actual == expected) {
            "$label fields mismatch: expected=${expected.sorted()} actual=${actual.sorted()}"
        }
    }
}
