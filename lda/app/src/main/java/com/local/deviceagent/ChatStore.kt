package com.local.deviceagent

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/**
 * Persistent store for the on-screen text chat with the agent. Plain JSON in SharedPreferences,
 * size-capped. Roles are "you" (the owner) and "agent".
 *
 * Supports MULTIPLE conversations (like any chat app) so a fresh chat doesn't inherit old answers
 * from a previous build - the owner can start a NEW conversation and ask questions without the
 * previous context polluting it. The single legacy thread is migrated into "Conversation 1" on
 * first use (kept, not deleted). add()/messages()/clear() all operate on the CURRENT conversation.
 */
object ChatStore {
    private const val PREF = "agent_chat"
    private const val OLD_KEY = "messages"       // legacy single thread (migrated once)
    private const val CONVOS = "conversations"   // JSONArray of {id,title,msgs:[{role,text,time}],time}
    private const val CURRENT = "current_id"
    private const val DRAFT = "draft"
    private const val MAX = 200
    private const val MAX_CONVOS = 20

    data class Msg(val role: String, val text: String, val time: Long)
    data class Convo(val id: String, val title: String, val count: Int, val time: Long)

    private fun prefs(c: Context) = c.getSharedPreferences(PREF, Context.MODE_PRIVATE)

    @Synchronized
    fun add(c: Context, role: String, text: String) {
        val t = text.trim()
        if (t.isEmpty()) return
        val (arr, cur) = currentConvo(c)
        val msgs = cur.optJSONArray("msgs") ?: JSONArray().also { cur.put("msgs", it) }
        msgs.put(JSONObject().put("role", role).put("text", t).put("time", System.currentTimeMillis()))
        while (msgs.length() > MAX) msgs.remove(0)
        if (cur.optString("title").isBlank() || cur.optString("title").startsWith("New chat"))
            cur.put("title", titleFrom(msgs))
        cur.put("time", System.currentTimeMillis())
        save(c, arr)
    }

    @Synchronized
    fun messages(c: Context): List<Msg> {
        val msgs = currentConvo(c).second.optJSONArray("msgs") ?: JSONArray()
        return (0 until msgs.length()).map {
            val o = msgs.getJSONObject(it); Msg(o.optString("role"), o.optString("text"), o.optLong("time"))
        }
    }

    /** Clear the CURRENT conversation's messages (the conversation itself stays). */
    @Synchronized
    fun clear(c: Context) {
        val (arr, cur) = currentConvo(c)
        cur.put("msgs", JSONArray()); cur.put("title", "New chat")
        save(c, arr)
    }

    /** Start a brand-new, empty conversation and make it current. Old ones are kept (capped). */
    @Synchronized
    fun newConversation(c: Context): String {
        val arr = convosArr(c)
        val id = System.currentTimeMillis().toString(36)
        arr.put(JSONObject().put("id", id).put("title", "New chat")
            .put("msgs", JSONArray()).put("time", System.currentTimeMillis()))
        while (arr.length() > MAX_CONVOS) arr.remove(0)
        prefs(c).edit().putString(CONVOS, arr.toString()).putString(CURRENT, id).apply()
        return id
    }

    /** All conversations, newest activity first, for a switcher. */
    @Synchronized
    fun conversations(c: Context): List<Convo> {
        val arr = convosArr(c)
        return (0 until arr.length()).mapNotNull { arr.optJSONObject(it) }.map {
            Convo(it.optString("id"), it.optString("title").ifBlank { "New chat" },
                it.optJSONArray("msgs")?.length() ?: 0, it.optLong("time"))
        }.sortedByDescending { it.time }
    }

    @Synchronized
    fun switchTo(c: Context, id: String) {
        if (convosArr(c).let { (0 until it.length()).any { i -> it.optJSONObject(i)?.optString("id") == id } })
            prefs(c).edit().putString(CURRENT, id).apply()
    }

    @Synchronized
    fun currentId(c: Context): String = currentConvo(c).second.optString("id")

    /** The whole CURRENT conversation as plain text, for the "Copy conversation" button. */
    @Synchronized
    fun asPlainText(c: Context): String =
        messages(c).joinToString("\n\n") { "${if (it.role == "you") "You" else "Agent"}: ${it.text}" }

    // Draft input is saved so text typed into the box survives leaving the screen / the app.
    fun saveDraft(c: Context, text: String) = prefs(c).edit().putString(DRAFT, text).apply()
    fun draft(c: Context): String = prefs(c).getString(DRAFT, "") ?: ""

    // --- internals ---------------------------------------------------------

    /** The (array, currentConversationObject) pair, creating/migrating as needed. */
    private fun currentConvo(c: Context): Pair<JSONArray, JSONObject> {
        val arr = convosArr(c)
        val curId = prefs(c).getString(CURRENT, null)
        var cur = (0 until arr.length()).mapNotNull { arr.optJSONObject(it) }
            .firstOrNull { it.optString("id") == curId }
        if (cur == null) {
            // No valid current -> use the newest, or make one.
            cur = (0 until arr.length()).mapNotNull { arr.optJSONObject(it) }.maxByOrNull { it.optLong("time") }
            if (cur == null) {
                cur = JSONObject().put("id", System.currentTimeMillis().toString(36))
                    .put("title", "New chat").put("msgs", JSONArray()).put("time", System.currentTimeMillis())
                arr.put(cur)
                prefs(c).edit().putString(CONVOS, arr.toString()).apply()
            }
            prefs(c).edit().putString(CURRENT, cur.optString("id")).apply()
        }
        return arr to cur
    }

    private fun save(c: Context, arr: JSONArray) = prefs(c).edit().putString(CONVOS, arr.toString()).apply()

    private fun convosArr(c: Context): JSONArray {
        migrateIfNeeded(c)
        return try { JSONArray(prefs(c).getString(CONVOS, "[]")) } catch (_: Exception) { JSONArray() }
    }

    /** One-time: fold the legacy single thread into "Conversation 1" (kept, not deleted). */
    private fun migrateIfNeeded(c: Context) {
        val p = prefs(c)
        if (p.contains(CONVOS)) return
        val legacy = try { JSONArray(p.getString(OLD_KEY, "[]")) } catch (_: Exception) { JSONArray() }
        val id = "conv1"
        val convo = JSONObject().put("id", id)
            .put("title", if (legacy.length() > 0) titleFrom(legacy) else "Conversation 1")
            .put("msgs", legacy).put("time", System.currentTimeMillis())
        p.edit().putString(CONVOS, JSONArray().put(convo).toString())
            .putString(CURRENT, id).remove(OLD_KEY).apply()
    }

    /** Title from the first thing the owner said in the thread. */
    private fun titleFrom(msgs: JSONArray): String {
        for (i in 0 until msgs.length()) {
            val o = msgs.optJSONObject(i) ?: continue
            if (o.optString("role") == "you") {
                val t = o.optString("text").trim().replace("\n", " ")
                if (t.isNotEmpty()) return t.take(36) + if (t.length > 36) "…" else ""
            }
        }
        return "New chat"
    }
}
