package com.local.deviceagent

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * CUSTOM OPERATOR STORE (owner's ask, 07-10: "a place for a custom bake to put my own operators in one by one").
 * A small, editable, on-device list of operators the OWNER authors — {name, rule, note} — that the Baking screen
 * can bake individually via the same `ScaleBake.bakeOperatorDirect` spine as the built-ins (which supply their
 * rule from `ReasoningOperators.ruleOf`; a custom operator supplies its rule text directly). Nothing here is ever
 * SELECTABLE in the action loop (custom operators are a bake target, not a runtime menu entry) and nothing leaves
 * the device. A single JSON-array file (read/rewrite) so add + delete are trivial; guarded so a store failure can
 * never affect a bake.
 */
object CustomOperatorStore {
    private const val FILE = "custom_operators.json"
    private const val MAX = 100
    private const val MAX_RULE = 4_000    // room for a full 8-part operational-state σ (e.g. the owner's ACCURACY) without clipping

    data class Op(val name: String, val rule: String, val note: String)

    private fun file(c: Context) = File(c.filesDir, FILE)

    private fun read(c: Context): MutableList<Op> {
        return try {
            val f = file(c); if (!f.exists()) return mutableListOf()
            val arr = JSONArray(f.readText())
            (0 until arr.length()).mapNotNull { i ->
                val o = arr.optJSONObject(i) ?: return@mapNotNull null
                val n = o.optString("name").trim(); if (n.isBlank()) return@mapNotNull null
                Op(n, o.optString("rule"), o.optString("note"))
            }.toMutableList()
        } catch (_: Exception) { mutableListOf() }
    }

    private fun write(c: Context, ops: List<Op>) {
        try {
            val arr = JSONArray()
            for (op in ops.take(MAX)) arr.put(JSONObject().put("name", op.name).put("rule", op.rule).put("note", op.note))
            file(c).writeText(arr.toString())
        } catch (_: Exception) {}
    }

    /** All saved custom operators (insertion order). */
    fun list(c: Context): List<Op> = read(c)

    /** Add or replace (by case-insensitive name) a custom operator. Name uppercased + sanitized to match the
     *  operator-name convention (so it can graduate into `distilledOps` like a built-in). Blank rule is rejected. */
    @Synchronized
    fun save(c: Context, name: String, rule: String, note: String = "") {
        val n = name.trim().uppercase().replace(Regex("[^A-Z0-9_]"), "").take(24)
        val r = rule.trim().take(MAX_RULE)
        if (n.length < 2 || r.isBlank()) return
        val ops = read(c)
        ops.removeAll { it.name.equals(n, ignoreCase = true) }
        ops.add(Op(n, r, note.trim().take(200)))
        write(c, ops)
    }

    @Synchronized
    fun delete(c: Context, name: String) {
        val ops = read(c); ops.removeAll { it.name.equals(name, ignoreCase = true) }; write(c, ops)
    }

    fun ruleFor(c: Context, name: String): String? =
        read(c).firstOrNull { it.name.equals(name, ignoreCase = true) }?.rule?.takeIf { it.isNotBlank() }
}
