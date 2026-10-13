package org.commons.android

import org.json.JSONArray
import org.json.JSONObject
import java.security.MessageDigest

const val PROTOCOL_VERSION = "titan-hands-deltaui/0.1"
const val HANDS_PORT = 8745
const val PIXELS_NOT_CAPTURED = "not-captured"
const val PIXELS_ON_DEMAND = "on-demand-only"

class ProtocolException(message: String) : RuntimeException(message)

fun failure(reason: String, message: String, evidence: JSONObject? = null): JSONObject {
    val result = JSONObject()
        .put("ok", false)
        .put("protocol", PROTOCOL_VERSION)
        .put("kind", "failure")
        .put("failure_reason", reason)
        .put("message", message)
    if (evidence != null && evidence.length() > 0) {
        result.put("evidence", evidence)
    }
    return result
}

fun canonical(value: Any?): String {
    return when (value) {
        null, JSONObject.NULL -> "null"
        is JSONObject -> {
            val keys = value.keys().asSequence().toMutableList().sorted()
            keys.joinToString(",", prefix = "{", postfix = "}") { key ->
                JSONObject.quote(key) + ":" + canonical(value.get(key))
            }
        }
        is JSONArray -> {
            (0 until value.length()).joinToString(",", prefix = "[", postfix = "]") { index ->
                canonical(value.get(index))
            }
        }
        is Boolean -> if (value) "true" else "false"
        is Int, is Long -> value.toString()
        is Double, is Float -> {
            val number = (value as Number).toDouble()
            if (number % 1.0 == 0.0 && number in Long.MIN_VALUE.toDouble()..Long.MAX_VALUE.toDouble()) {
                number.toLong().toString()
            } else {
                number.toString()
            }
        }
        is Number -> value.toString()
        is String -> JSONObject.quote(value)
        else -> JSONObject.quote(value.toString())
    }
}

fun sha256Hex(text: String): String {
    val digest = MessageDigest.getInstance("SHA-256").digest(text.toByteArray(Charsets.UTF_8))
    return digest.joinToString("") { byte -> "%02x".format(byte) }
}

fun digest(value: Any?): String = sha256Hex(canonical(value))

fun normalizeNode(raw: JSONObject): JSONObject {
    val nodeId = raw.optString("id").trim()
    if (nodeId.isEmpty()) throw ProtocolException("every node requires a stable id")
    val node = JSONObject(raw.toString())
    node.put("id", nodeId)
    node.put("parent", node.optString("parent"))
    node.put("role", node.optString("role", "unknown"))
    val actions = node.optJSONArray("actions") ?: JSONArray()
    val states = node.optJSONArray("states") ?: JSONArray()
    node.put("actions", sortedUnique(actions))
    node.put("states", sortedUnique(states))
    return node
}

private fun sortedUnique(values: JSONArray): JSONArray {
    val items = (0 until values.length())
        .map { values.optString(it) }
        .filter { it.isNotBlank() }
        .toSortedSet()
    val out = JSONArray()
    items.forEach { out.put(it) }
    return out
}

class DeltaTracker {
    var sequence: Int = 0
        private set
    private var previous: Map<String, JSONObject> = emptyMap()
    private var metaJson: String = "{}"

    fun reset() {
        sequence = 0
        previous = emptyMap()
        metaJson = "{}"
    }

    fun observe(snapshot: JSONObject): JSONObject {
        val rawNodes = snapshot.optJSONArray("nodes") ?: JSONArray()
        val current = LinkedHashMap<String, JSONObject>()
        for (index in 0 until rawNodes.length()) {
            val node = normalizeNode(rawNodes.getJSONObject(index))
            val nodeId = node.getString("id")
            if (current.containsKey(nodeId)) {
                throw ProtocolException("duplicate node id: $nodeId")
            }
            current[nodeId] = node
        }
        val baseSequence = sequence
        sequence += 1
        val previousKeys = previous.keys
        val currentKeys = current.keys
        val added = JSONArray()
        val updated = JSONArray()
        val removed = JSONArray()
        (currentKeys - previousKeys).sorted().forEach { added.put(current[it]) }
        (previousKeys - currentKeys).sorted().forEach { removed.put(it) }
        (currentKeys intersect previousKeys).sorted().forEach { nodeId ->
            if (canonical(current[nodeId]!!) != canonical(previous[nodeId]!!)) {
                updated.put(current[nodeId])
            }
        }
        val meta = JSONObject()
        val metaKeys = snapshot.keys()
        while (metaKeys.hasNext()) {
            val key = metaKeys.next()
            if (key != "nodes" && key != "ok") {
                meta.put(key, snapshot.get(key))
            }
        }
        val nextMeta = canonical(meta)
        val metaChanged = nextMeta != metaJson
        previous = current
        metaJson = nextMeta
        val digestSource = JSONObject().put("nodes", mapToArrayObject(current)).put("meta", meta)
        return JSONObject()
            .put("ok", true)
            .put("protocol", PROTOCOL_VERSION)
            .put("kind", "observation_delta")
            .put("sequence", sequence)
            .put("base_sequence", baseSequence)
            .put("full", baseSequence == 0)
            .put("added", added)
            .put("updated", updated)
            .put("removed", removed)
            .put("unchanged", current.size - added.length() - updated.length())
            .put("node_count", current.size)
            .put("meta_changed", metaChanged)
            .put("meta", if (metaChanged || baseSequence == 0) meta else JSONObject())
            .put("state_digest", digest(digestSource))
    }

    private fun mapToArrayObject(nodes: Map<String, JSONObject>): JSONObject {
        val out = JSONObject()
        nodes.keys.sorted().forEach { key -> out.put(key, nodes[key]) }
        return out
    }
}
